"""Audit Runner — runs the same deep SEO analysis that powers the free audit.

This is the exact same process Jarvis uses when you ask "audit sublettlabs.com".
Reuses all existing analyzers: meta_tags, headings, images, technical, schema_org, scoring.
Produces a comprehensive audit result with all issues, scores, and raw data needed for fix generation.
"""

import time
import json
import asyncio
from typing import Optional
from dataclasses import dataclass, field, asdict

from app.analyzers.fetcher import fetch_page
from app.analyzers.meta_tags import analyze_meta_tags
from app.analyzers.headings import analyze_headings
from app.analyzers.images import analyze_images
from app.analyzers.technical import analyze_technical
from app.analyzers.schema_org import analyze_schema
from app.analyzers.scoring import calculate_seo_score


@dataclass
class AuditIssue:
    """Single SEO issue found during audit."""
    category: str  # meta, headings, images, technical, schema
    severity: str  # critical, high, medium, low
    issue: str  # What's wrong
    evidence: str  # What we found
    fix_type: str  # meta_tag, heading, schema, image, technical, content
    element: str  # The HTML element or area affected
    current_value: str = ""  # What's currently there (before)
    suggested_fix: str = ""  # What it should be (after) — filled by fix_generator


@dataclass
class AuditResult:
    """Complete audit result — mirrors what the free audit returns plus extras for fix generation."""
    url: str
    final_url: str
    seo_score: int  # 0-100
    scores: dict  # Per-category scores
    issues: list = field(default_factory=list)  # List of AuditIssue objects
    page_data: dict = field(default_factory=dict)  # Raw extracted data
    raw_html: str = ""  # Full HTML for fix generation
    response_time_ms: float = 0
    timestamp: float = field(default_factory=time.time)

    # Platform detection
    detected_platform: str = "custom"  # shopify, wordpress, squarespace, custom

    def to_dict(self) -> dict:
        return {
            "url": self.url,
            "final_url": self.final_url,
            "seo_score": self.seo_score,
            "scores": self.scores,
            "issues": [asdict(i) for i in self.issues],
            "page_data": self.page_data,
            "response_time_ms": self.response_time_ms,
            "timestamp": self.timestamp,
            "detected_platform": self.detected_platform,
            "issue_count": len(self.issues),
            "critical_count": sum(1 for i in self.issues if i.severity == "critical"),
            "high_count": sum(1 for i in self.issues if i.severity == "high"),
            "medium_count": sum(1 for i in self.issues if i.severity == "medium"),
            "low_count": sum(1 for i in self.issues if i.severity == "low"),
        }


def _detect_platform(html: str, final_url: str) -> str:
    """Detect the CMS/platform from HTML signatures."""
    html_lower = html.lower()

    # Shopify
    if any(sig in html_lower for sig in [
        'shopify', 'cdn.shopify.com', 'shopify.theme', 'shopify-section',
        'window.shopify', 'shopify_check', '/cdn/shop/'
    ]):
        return "shopify"

    # WordPress
    if any(sig in html_lower for sig in [
        'wp-content', 'wp-includes', 'wordpress', '/wp-json/',
        'wp-emoji', 'wp-rocket'
    ]):
        return "wordpress"

    # Squarespace
    if any(sig in html_lower for sig in [
        'squarespace', 'static.squarespace.com', 'sqs-template'
    ]):
        return "squarespace"

    # Wix
    if any(sig in html_lower for sig in ['wix.com', 'wixpress', 'wix-']):
        return "wix"

    # Webflow
    if any(sig in html_lower for sig in ['webflow', 'wf-domain']):
        return "webflow"

    # Next.js
    if any(sig in html_lower for sig in ['__next', '_next/', 'nextjs']):
        return "nextjs"

    # Vercel
    if 'vercel' in html_lower:
        return "vercel"

    return "custom"


def _categorize_issues(
    meta_results: dict,
    heading_results: dict,
    image_results: dict,
    technical_results: dict,
    schema_results: dict,
) -> list:
    """Convert raw analyzer issues into structured AuditIssue objects with severity and fix_type."""

    issues = []

    # --- Meta tag issues ---
    if not meta_results.get("title"):
        issues.append(AuditIssue(
            category="meta", severity="critical", issue="Missing title tag",
            evidence="No <title> tag found", fix_type="meta_tag", element="title",
            current_value="", suggested_fix=""
        ))
    elif meta_results.get("title_length", 0) < 30:
        issues.append(AuditIssue(
            category="meta", severity="high", issue="Title tag too short",
            evidence=f"Title is {meta_results.get('title_length', 0)} chars: \"{meta_results.get('title', '')}\"",
            fix_type="meta_tag", element="title",
            current_value=meta_results.get("title", ""),
            suggested_fix=""
        ))
    elif meta_results.get("title_length", 0) > 60:
        issues.append(AuditIssue(
            category="meta", severity="high", issue="Title tag too long",
            evidence=f"Title is {meta_results.get('title_length', 0)} chars: \"{meta_results.get('title', '')}\"",
            fix_type="meta_tag", element="title",
            current_value=meta_results.get("title", ""),
            suggested_fix=""
        ))

    if not meta_results.get("description"):
        issues.append(AuditIssue(
            category="meta", severity="critical", issue="Missing meta description",
            evidence="No <meta name='description'> found", fix_type="meta_tag",
            element="meta description", current_value="", suggested_fix=""
        ))
    elif meta_results.get("description_length", 0) < 120:
        issues.append(AuditIssue(
            category="meta", severity="medium", issue="Meta description too short",
            evidence=f"Description is {meta_results.get('description_length', 0)} chars",
            fix_type="meta_tag", element="meta description",
            current_value=meta_results.get("description", ""),
            suggested_fix=""
        ))
    elif meta_results.get("description_length", 0) > 160:
        issues.append(AuditIssue(
            category="meta", severity="medium", issue="Meta description too long",
            evidence=f"Description is {meta_results.get('description_length', 0)} chars",
            fix_type="meta_tag", element="meta description",
            current_value=meta_results.get("description", ""),
            suggested_fix=""
        ))

    if not meta_results.get("canonical"):
        issues.append(AuditIssue(
            category="meta", severity="high", issue="Missing canonical URL",
            evidence="No <link rel='canonical'> found", fix_type="meta_tag",
            element="canonical", current_value="", suggested_fix=""
        ))

    if not meta_results.get("og_title"):
        issues.append(AuditIssue(
            category="meta", severity="medium", issue="Missing Open Graph title",
            evidence="No <meta property='og:title'> found", fix_type="meta_tag",
            element="og:title", current_value="", suggested_fix=""
        ))

    if not meta_results.get("og_image"):
        issues.append(AuditIssue(
            category="meta", severity="medium", issue="Missing Open Graph image",
            evidence="No <meta property='og:image'> found", fix_type="meta_tag",
            element="og:image", current_value="", suggested_fix=""
        ))

    if not meta_results.get("og_description"):
        issues.append(AuditIssue(
            category="meta", severity="low", issue="Missing OG description",
            evidence="No <meta property='og:description'> found", fix_type="meta_tag",
            element="og:description", current_value="", suggested_fix=""
        ))

    # --- Heading issues ---
    h1_count = heading_results.get("h1_count", 0)
    if h1_count == 0:
        issues.append(AuditIssue(
            category="headings", severity="critical", issue="Missing H1 tag",
            evidence="No <h1> tag found on the page", fix_type="heading",
            element="h1", current_value="", suggested_fix=""
        ))
    elif h1_count > 1:
        issues.append(AuditIssue(
            category="headings", severity="medium", issue=f"Multiple H1 tags ({h1_count})",
            evidence=f"Found {h1_count} H1 tags — should be exactly 1",
            fix_type="heading", element="h1",
            current_value=f"{h1_count} H1 tags found", suggested_fix=""
        ))

    if heading_results.get("total_count", 0) < 3:
        issues.append(AuditIssue(
            category="headings", severity="low", issue="Few heading tags",
            evidence=f"Only {heading_results.get('total_count', 0)} heading tags found",
            fix_type="heading", element="heading structure",
            current_value="", suggested_fix=""
        ))

    # --- Image issues ---
    total_images = image_results.get("total", 0)
    missing_alt = image_results.get("missing_alt", 0)
    if total_images > 0 and missing_alt > 0:
        pct = round(missing_alt / total_images * 100)
        severity = "high" if pct > 50 else "medium"
        issues.append(AuditIssue(
            category="images", severity=severity,
            issue=f"{missing_alt} of {total_images} images missing alt text ({pct}%)",
            evidence=f"{missing_alt} images without alt attributes out of {total_images} total",
            fix_type="image", element="img alt attributes",
            current_value=f"{missing_alt}/{total_images} missing alt",
            suggested_fix=""
        ))

    bad_filenames = image_results.get("bad_filenames", 0)
    if bad_filenames > 0:
        issues.append(AuditIssue(
            category="images", severity="low",
            issue=f"{bad_filenames} images with non-descriptive filenames",
            evidence=f"{bad_filenames} images have generic filenames (IMG_, DSC_, etc.)",
            fix_type="image", element="image filenames",
            current_value=f"{bad_filenames} bad filenames", suggested_fix=""
        ))

    # --- Technical issues ---
    if not technical_results.get("is_https"):
        issues.append(AuditIssue(
            category="technical", severity="critical", issue="Site not using HTTPS",
            evidence="URL is HTTP, not HTTPS", fix_type="technical",
            element="SSL/TLS", current_value="HTTP", suggested_fix=""
        ))

    if technical_results.get("internal_links", 0) < 3:
        issues.append(AuditIssue(
            category="technical", severity="medium", issue="Very few internal links",
            evidence=f"Only {technical_results.get('internal_links', 0)} internal links found",
            fix_type="technical", element="internal links",
            current_value=f"{technical_results.get('internal_links', 0)} links",
            suggested_fix=""
        ))

    if technical_results.get("had_redirect"):
        issues.append(AuditIssue(
            category="technical", severity="low", issue="URL redirects",
            evidence=f"Redirected from {technical_results.get('redirect_from', '')}",
            fix_type="technical", element="URL",
            current_value=technical_results.get("redirect_from", ""),
            suggested_fix=""
        ))

    # --- Schema issues ---
    if not schema_results.get("has_schema"):
        issues.append(AuditIssue(
            category="schema", severity="high", issue="No structured data / schema markup",
            evidence="No JSON-LD or microdata found on the page",
            fix_type="schema", element="JSON-LD",
            current_value="None", suggested_fix=""
        ))
    else:
        # Has schema but might be missing recommended types
        schema_types = schema_results.get("types", [])
        has_org = "Organization" in schema_types or "LocalBusiness" in schema_types
        has_website = "WebSite" in schema_types
        has_product = "Product" in schema_types

        if not has_org:
            issues.append(AuditIssue(
                category="schema", severity="medium",
                issue="Missing Organization schema",
                evidence="Schema found but no Organization or LocalBusiness type",
                fix_type="schema", element="Organization JSON-LD",
                current_value="Missing", suggested_fix=""
            ))
        if not has_website:
            issues.append(AuditIssue(
                category="schema", severity="low",
                issue="Missing WebSite schema",
                evidence="Schema found but no WebSite type",
                fix_type="schema", element="WebSite JSON-LD",
                current_value="Missing", suggested_fix=""
            ))

    # Add any raw issues from analyzers that we didn't categorize above.
    # Analyzers may return issues as strings OR dicts with {severity, category, message, detail, fix}.
    # We normalize both formats into AuditIssue objects, deduplicating against our structured issues.
    _raw_categories = [
        ("meta", meta_results),
        ("headings", heading_results),
        ("images", image_results),
        ("technical", technical_results),
        ("schema", schema_results),
    ]

    for cat, results in _raw_categories:
        for raw_issue in results.get("issues", []):
            # Normalize dict-style issues from analyzers
            if isinstance(raw_issue, dict):
                issue_text = raw_issue.get("message", raw_issue.get("issue", str(raw_issue)))
                evidence = raw_issue.get("detail", raw_issue.get("evidence", issue_text))
                severity = raw_issue.get("severity", "medium")
                # Map analyzer severity names to our levels
                severity_map = {"error": "high", "warning": "medium", "info": "low", "critical": "critical"}
                severity = severity_map.get(severity, severity)
                fix_hint = raw_issue.get("fix", "")
                element = raw_issue.get("element", "unknown")

                # Skip positive info messages ("✅ X detected")
                if issue_text.startswith("✅"):
                    continue

                # Dedup against our structured issues
                if any(i.issue == issue_text for i in issues):
                    continue

                issues.append(AuditIssue(
                    category=raw_issue.get("category", cat),
                    severity=severity,
                    issue=issue_text,
                    evidence=evidence,
                    fix_type=cat if cat != "headings" else "heading",
                    element=element,
                    current_value="",
                    suggested_fix=fix_hint or "",
                ))
            elif isinstance(raw_issue, str):
                # Skip positive messages
                if raw_issue.startswith("✅"):
                    continue

                # Dedup against our structured issues
                if any(i.issue == raw_issue for i in issues):
                    continue

                issues.append(AuditIssue(
                    category=cat, severity="medium", issue=raw_issue,
                    evidence=raw_issue, fix_type=cat if cat != "headings" else "heading",
                    element="unknown", current_value="", suggested_fix=""
                ))

    return issues


async def run_full_audit(url: str) -> AuditResult:
    """Run the full SEO audit — same process Jarvis uses when you ask for an audit.

    This is the core function that powers both the free audit and the paid fix.
    It reuses all existing analyzers and produces a structured result with:
    - Per-category scores (0-100)
    - Overall SEO score (0-100)
    - Detailed issues with severity, evidence, and fix_type
    - Raw page data for fix generation
    - Detected CMS/platform
    - Full HTML for fix generation
    """
    # Fetch the page (same as free audit)
    html, response_time, final_url = await fetch_page(url)

    # Run all analyzers (same as free audit)
    meta_results = analyze_meta_tags(html, url)
    heading_results = analyze_headings(html, url)
    image_results = analyze_images(html, url)
    technical_results = analyze_technical(html, url, final_url)
    schema_results = analyze_schema(html, url)

    # Calculate scores (same as free audit)
    scores = calculate_seo_score(
        meta_results, heading_results, image_results,
        technical_results, schema_results
    )

    # Categorize and structure all issues
    issues = _categorize_issues(
        meta_results, heading_results, image_results,
        technical_results, schema_results
    )

    # Detect platform
    platform = _detect_platform(html, final_url)

    # Build page data
    page_data = {
        "title": meta_results.get("title", ""),
        "description": meta_results.get("description", ""),
        "canonical": meta_results.get("canonical", ""),
        "og_title": meta_results.get("og_title", ""),
        "og_description": meta_results.get("og_description", ""),
        "og_image": meta_results.get("og_image", ""),
        "og_type": meta_results.get("og_type", ""),
        "h1_count": heading_results.get("h1_count", 0),
        "total_headings": heading_results.get("total_count", 0),
        "heading_structure": heading_results.get("structure", []),
        "image_count": image_results.get("total", 0),
        "images_missing_alt": image_results.get("missing_alt", 0),
        "bad_filenames": image_results.get("bad_filenames", 0),
        "is_https": technical_results.get("is_https", False),
        "internal_links": technical_results.get("internal_links", 0),
        "external_links": technical_results.get("external_links", 0),
        "has_schema": schema_results.get("has_schema", False),
        "schema_types": schema_results.get("types", []),
        "response_time_ms": response_time,
    }

    return AuditResult(
        url=url,
        final_url=final_url,
        seo_score=scores["total"],
        scores=scores,
        issues=issues,
        page_data=page_data,
        raw_html=html,
        response_time_ms=response_time,
        detected_platform=platform,
    )
"""Fix Generator — takes audit results and generates corrected code for each issue.

This is the AI-powered "fix their stuff" engine. It takes the same audit data we use
for free audits and generates platform-specific fixes — corrected meta tags, schema
markup, OG tags, heading fixes, etc. — just like if you asked Jarvis to fix it.

Uses Claude (via OpenRouter) to generate the fixes, then structures them into
platform-specific implementation guides.
"""

import os
import json
import time
import re
from typing import Optional
from dataclasses import dataclass, field, asdict

from app.fix_engine.audit_runner import AuditResult, AuditIssue
from app.fix_engine.audit_trail import AuditTrail

# LLM API configuration — uses OpenRouter for reliability and model choice
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "")
if not OPENROUTER_API_KEY:
    # Check multiple locations for the key
    for _key_path in [
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".openrouter_key"),
        os.path.join(os.path.expanduser("~/.openclaw/workspace"), ".openrouter_key"),
    ]:
        if os.path.exists(_key_path):
            OPENROUTER_API_KEY = open(_key_path).read().strip()
            break
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
LLM_MODEL = "anthropic/claude-sonnet-4"  # Works via OpenRouter


@dataclass
class FixItem:
    """A single fix — before/after with implementation code."""
    category: str
    severity: str
    issue: str
    element: str
    before_value: str
    after_value: str
    fix_code: str  # The actual corrected HTML/code
    platform_code: dict = field(default_factory=dict)  # Platform-specific variants
    implementation_guide: str = ""  # How to apply this fix
    platform: str = "custom"


@dataclass
class FixPackage:
    """Complete fix package for a customer order."""
    order_token: str
    url: str
    platform: str
    seo_score_before: int
    seo_score_after: int  # Estimated
    scores_before: dict
    scores_after: dict  # Estimated
    total_issues: int
    total_fixes: int
    fixes: list = field(default_factory=list)  # List of FixItem objects
    audit_trail: dict = field(default_factory=dict)  # Audit trail report
    generated_at: float = field(default_factory=time.time)


# Platform-specific implementation templates
PLATFORM_TEMPLATES = {
    "shopify": {
        "meta_tag": 'In your Shopify admin, go to Online Store → Themes → Edit code → theme.liquid. Add/edit the tag in the <head> section.',
        "schema": 'In Shopify admin → Online Store → Themes → Edit code → theme.liquid. Add the JSON-LD script in the <head> section, or use a custom section in settings_schema.json.',
        "heading": 'Edit the template file (e.g., sections/main-page.liquid or sections/main-product.liquid). Change the heading tag.',
        "image": 'In Shopify admin → Products → select product → add Alt text to images. For theme images, edit the section .liquid file.',
        "technical": 'Most technical fixes (HTTPS, redirects) are handled in Shopify Settings. For custom code, edit theme.liquid.',
    },
    "wordpress": {
        "meta_tag": 'Install Yoast SEO or Rank Math plugin. Go to the page/post editor → scroll to the SEO meta box → edit the title/description. Or add to header.php in your theme.',
        "schema": 'Use Yoast SEO → Schema settings, or add JSON-LD via a custom plugin or header.php in your theme.',
        "heading": 'Edit the page in the WordPress block editor. Select the heading block → change the heading level in the block settings.',
        "image": 'Edit the page/post → click the image → add Alt text in the image settings block. For featured images, set alt text in the Media Library.',
        "technical": 'Install Really Simple SSL for HTTPS. Use Redirection plugin for 301 redirects. Most technical SEO is plugin-managed.',
    },
    "squarespace": {
        "meta_tag": 'In Squarespace → Pages → select page → Settings → SEO → edit the title and description.',
        "schema": 'Squarespace auto-generates some schema. For custom JSON-LD, go to Settings → Advanced → Code Injection → Header and add the script.',
        "heading": 'Edit the page → click the text block → format the heading level using the toolbar.',
        "image": 'Edit the page → click the image → add Alt text in the image settings panel.',
        "technical": 'Squarespace handles HTTPS automatically. For redirects, go to Settings → Advanced → URL Mappings.',
    },
    "custom": {
        "meta_tag": 'Edit the HTML file directly. Add or update the tag in the <head> section.',
        "schema": 'Add the JSON-LD script tag in the <head> section of your HTML file.',
        "heading": 'Edit the HTML file directly. Change the heading tag (e.g., <h2> to <h1>).',
        "image": 'Edit the HTML file directly. Add or update the alt attribute on <img> tags.',
        "technical": 'Configure your web server (nginx, Apache, etc.) for HTTPS redirects, caching headers, etc.',
    },
    "nextjs": {
        "meta_tag": 'In your Next.js page, use the metadata export or <Head> component from next/head. Example: export const metadata = { title: "...", description: "..." }',
        "schema": 'Add JSON-LD in your page component or layout. Use next/head or the metadata API for SSR pages.',
        "heading": 'Edit your React component. Change the heading tag (e.g., <h2> to <h1>).',
        "image": 'Use next/image component with alt prop: <Image src="..." alt="Descriptive text" />',
        "technical": 'Configure next.config.js for headers, redirects, and HTTPS. Vercel handles SSL automatically.',
    },
}

# LLM prompt templates for generating fixes
FIX_PROMPT_TEMPLATE = """You are an expert SEO technician. A customer's website has SEO issues that need fixing.

Website: {url}
Platform: {platform}
Current SEO Score: {score}/100

Issues found:
{issues}

Current page data:
{page_data}

For EACH issue, generate the exact corrected HTML/code that fixes it. Follow these rules:

1. For meta tag issues: Generate the complete corrected <meta> or <title> tag
2. For schema issues: Generate a complete JSON-LD script tag
3. For heading issues: Show the corrected heading structure
4. For image alt text: Generate descriptive alt text based on context
5. For technical issues: Provide the exact fix (redirect rule, etc.)

Format your response as JSON array:
```json
[
  {{
    "category": "meta|headings|images|technical|schema",
    "issue": "the issue description",
    "element": "what element is affected",
    "before": "current value or 'MISSING'",
    "after": "the corrected value",
    "fix_code": "the exact HTML/code to add or replace",
    "implementation_guide": "step-by-step instructions for {platform}"
  }}
]
```

Make fixes specific to this website — use the actual URL, business name from the page data, and relevant keywords.
For meta descriptions, write compelling 150-160 character descriptions.
For titles, write 50-60 character titles with primary keyword near the beginning.
For schema, generate complete JSON-LD with real data from the page.
For alt text, write descriptive text that includes relevant keywords naturally.
"""


async def generate_fixes(
    audit_result: AuditResult,
    order_token: str,
    llm_model: str = "anthropic/claude-sonnet-4-6",
) -> FixPackage:
    """Generate fixes for all issues found in the audit.

    This is the core function. It takes the audit results (same ones the free audit produces),
    sends them to Claude for fix generation, and returns a structured FixPackage with:
    - Every issue found
    - Before/after values
    - Platform-specific fix code
    - Implementation guides
    - Estimated score improvement

    Also logs everything to the audit trail.
    """
    import httpx

    trail = AuditTrail(order_token, audit_result.url)

    # Log audit started
    trail.log_audit_started(
        seo_score=audit_result.seo_score,
        scores=audit_result.scores,
        platform=audit_result.detected_platform,
    )

    # Log all issues found
    for issue in audit_result.issues:
        trail.log_issue_found(
            category=issue.category,
            severity=issue.severity,
            issue=issue.issue,
            evidence=issue.evidence,
            element=issue.element,
            before_value=issue.current_value,
        )

    # Prepare issues text for LLM
    issues_text = "\n".join(
        f"- [{i.severity.upper()}] {i.category}: {i.issue} — {i.evidence} (element: {i.element}, current: {i.current_value or 'MISSING'})"
        for i in audit_result.issues
    )

    page_data_text = "\n".join(
        f"- {k}: {v}" for k, v in audit_result.page_data.items()
    )

    # Call LLM to generate fixes
    prompt = FIX_PROMPT_TEMPLATE.format(
        url=audit_result.url,
        platform=audit_result.detected_platform,
        score=audit_result.seo_score,
        issues=issues_text,
        page_data=page_data_text,
    )

    fixes = []
    estimated_score_after = audit_result.seo_score

    try:
        async with httpx.AsyncClient(timeout=90) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": LLM_MODEL,
                    "max_tokens": 4096,
                    "messages": [
                        {"role": "system", "content": "You are an expert SEO technician. Generate exact HTML/code fixes for SEO issues. Always respond with valid JSON."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.3,
                },
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]

            # Parse JSON from LLM response
            # Handle markdown code blocks
            json_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', content)
            if json_match:
                content = json_match.group(1).strip()

            llm_fixes = json.loads(content)

            for lf in llm_fixes:
                platform = audit_result.detected_platform
                platform_templates = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES["custom"])

                # Get platform-specific implementation guide
                fix_type = lf.get("category", "meta")
                impl_key = {
                    "meta": "meta_tag",
                    "headings": "heading",
                    "images": "image",
                    "technical": "technical",
                    "schema": "schema",
                }.get(fix_type, "meta_tag")

                fix = FixItem(
                    category=lf.get("category", "meta"),
                    severity=lf.get("severity", "medium"),
                    issue=lf.get("issue", ""),
                    element=lf.get("element", ""),
                    before_value=lf.get("before", ""),
                    after_value=lf.get("after", ""),
                    fix_code=lf.get("fix_code", ""),
                    platform_code=lf.get("platform_code", {}),
                    implementation_guide=lf.get("implementation_guide", "") or platform_templates.get(impl_key, ""),
                    platform=platform,
                )
                fixes.append(fix)

                # Log each fix generated
                trail.log_fix_generated(
                    category=fix.category,
                    severity=fix.severity,
                    issue=fix.issue,
                    element=fix.element,
                    before_value=fix.before_value,
                    after_value=fix.after_value,
                    fix_code=fix.fix_code,
                    platform=platform,
                )

    except Exception as e:
        # If LLM fails, generate basic fixes from audit data
        # Fallback: create fix items without AI-generated corrections
        for issue in audit_result.issues:
            platform = audit_result.detected_platform
            platform_templates = PLATFORM_TEMPLATES.get(platform, PLATFORM_TEMPLATES["custom"])
            impl_key = {
                "meta": "meta_tag",
                "headings": "heading",
                "images": "image",
                "technical": "technical",
                "schema": "schema",
            }.get(issue.category, "meta_tag")

            fix = FixItem(
                category=issue.category,
                severity=issue.severity,
                issue=issue.issue,
                element=issue.element,
                before_value=issue.current_value,
                after_value="",  # Needs manual correction
                fix_code="",  # Needs manual correction
                implementation_guide=platform_templates.get(impl_key, ""),
                platform=platform,
            )
            fixes.append(fix)

            trail.log_fix_generated(
                category=fix.category,
                severity=fix.severity,
                issue=fix.issue,
                element=fix.element,
                before_value=fix.before_value,
                after_value="(manual correction needed — LLM failed)",
                fix_code="(manual correction needed)",
                platform=platform,
            )

    # Estimate score improvement
    # Each critical fix ≈ 10 points, high ≈ 5, medium ≈ 3, low ≈ 1
    score_map = {"critical": 10, "high": 5, "medium": 3, "low": 1}
    estimated_improvement = sum(score_map.get(f.severity, 1) for f in fixes)
    estimated_score_after = min(100, audit_result.seo_score + estimated_improvement)

    # Log score change
    trail.log_score_change(
        score_before=audit_result.seo_score,
        score_after=estimated_score_after,
        scores_before=audit_result.scores,
        scores_after={},  # Estimated — would need re-audit to get actual
        issue_count_before=len(audit_result.issues),
        issue_count_after=0,  # All should be fixed
    )

    return FixPackage(
        order_token=order_token,
        url=audit_result.url,
        platform=audit_result.detected_platform,
        seo_score_before=audit_result.seo_score,
        seo_score_after=estimated_score_after,
        scores_before=audit_result.scores,
        scores_after={},  # Would need re-audit
        total_issues=len(audit_result.issues),
        total_fixes=len(fixes),
        fixes=fixes,
        audit_trail=trail.generate_report(),
    )


def format_fix_package_email(fix_package: FixPackage) -> dict:
    """Format the fix package for email delivery.

    Returns a dict with email_subject, email_body (HTML), and attachments info.
    """
    platform_name = {
        "shopify": "Shopify",
        "wordpress": "WordPress",
        "squarespace": "Squarespace",
        "wix": "Wix",
        "webflow": "Webflow",
        "nextjs": "Next.js",
        "vercel": "Vercel",
        "custom": "Custom HTML",
    }.get(fix_package.platform, fix_package.platform.title())

    # Build email HTML
    fixes_html = ""
    for i, fix in enumerate(fix_package.fixes, 1):
        severity_color = {
            "critical": "#ef4444",
            "high": "#f97316",
            "medium": "#eab308",
            "low": "#22c55e",
        }.get(fix.severity, "#71717a")

        before_display = fix.before_value if fix.before_value else "<em>Missing</em>"
        after_display = fix.after_value if fix.after_value else "<em>See code below</em>"

        fixes_html += f"""
        <div style="border-left: 4px solid {severity_color}; padding: 12px 16px; margin: 12px 0; background: #f9fafb; border-radius: 4px;">
            <h4 style="margin: 0 0 4px 0; color: #111827;">{i}. {fix.issue}</h4>
            <p style="margin: 0 0 4px 0; color: #6b7280; font-size: 13px;">
                <span style="background: {severity_color}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px;">{fix.severity.upper()}</span>
                &nbsp;·&nbsp; {fix.category.title()} &nbsp;·&nbsp; {fix.element}
            </p>
            <table style="width: 100%; margin: 8px 0; font-size: 13px;">
                <tr><td style="color: #6b7280; width: 80px;">Before:</td><td style="color: #ef4444;">{before_display}</td></tr>
                <tr><td style="color: #6b7280;">After:</td><td style="color: #22c55e;">{after_display}</td></tr>
            </table>
            {f'<pre style="background: #1e293b; color: #e2e8f0; padding: 12px; border-radius: 6px; font-size: 12px; overflow-x: auto; white-space: pre-wrap;">{fix.fix_code}</pre>' if fix.fix_code else ''}
            <p style="margin: 8px 0 0 0; font-size: 13px; color: #4b5563;">
                <strong>How to apply ({platform_name}):</strong> {fix.implementation_guide}
            </p>
        </div>"""

    score_improvement = fix_package.seo_score_after - fix_package.seo_score_before

    email_html = f"""
    <div style="max-width: 600px; margin: 0 auto; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;">
        <div style="background: linear-gradient(135deg, #0a0a0f, #1e1e2e); padding: 32px; border-radius: 12px 12px 0 0; text-align: center;">
            <h1 style="color: #f59e0b; margin: 0; font-size: 24px;">⚡ BoostRank SEO Fix Report</h1>
            <p style="color: #a1a1aa; margin: 8px 0 0 0; font-size: 14px;">Your SEO issues have been analyzed and fixes generated</p>
        </div>

        <div style="background: #111827; padding: 24px; border: 1px solid #1e293b;">
            <table style="width: 100%; margin-bottom: 16px;">
                <tr>
                    <td style="text-align: center; padding: 16px; background: #1e293b; border-radius: 8px; width: 48%;">
                        <div style="font-size: 32px; font-weight: 800; color: #ef4444;">{fix_package.seo_score_before}</div>
                        <div style="font-size: 12px; color: #6b7280;">Score Before</div>
                    </td>
                    <td style="text-align: center; padding: 8px; font-size: 24px;">→</td>
                    <td style="text-align: center; padding: 16px; background: #1e293b; border-radius: 8px; width: 48%;">
                        <div style="font-size: 32px; font-weight: 800; color: #22c55e;">{fix_package.seo_score_after}</div>
                        <div style="font-size: 12px; color: #6b7280;">Score After (est.)</div>
                    </td>
                </tr>
            </table>

            <div style="background: #1e293b; padding: 16px; border-radius: 8px; margin-bottom: 16px; text-align: center;">
                <span style="font-size: 16px; color: #f59e0b; font-weight: 600;">+{score_improvement} points estimated improvement</span>
                <span style="font-size: 13px; color: #6b7280;"> · {fix_package.total_issues} issues found · {fix_package.total_fixes} fixes generated</span>
            </div>

            <div style="background: #1e293b; padding: 12px; border-radius: 8px; margin-bottom: 16px;">
                <span style="font-size: 13px; color: #6b7280;">Website:</span>
                <span style="font-size: 13px; color: #e4e4e7;"> {fix_package.url}</span>
                <span style="font-size: 13px; color: #6b7280;"> · Platform:</span>
                <span style="font-size: 13px; color: #e4e4e7;"> {platform_name}</span>
            </div>

            <h2 style="color: #e4e4e7; font-size: 18px; margin: 24px 0 8px 0;">Your Fixes</h2>
            {fixes_html}

            <div style="background: #1e293b; padding: 16px; border-radius: 8px; margin-top: 24px; text-align: center;">
                <p style="color: #6b7280; font-size: 13px; margin: 0;">
                    Need help implementing these fixes? Reply to this email or visit
                    <a href="https://boostrank.co" style="color: #f59e0b;">boostrank.co</a>
                </p>
            </div>
        </div>

        <div style="background: #0a0a0f; padding: 16px; text-align: center; border-radius: 0 0 12px 12px;">
            <p style="color: #52525b; font-size: 12px; margin: 0;">
                BoostRank by BrandBoost Studio · <a href="https://sublettlabs.com" style="color: #71717a;">Sublett Labs</a>
            </p>
        </div>
    </div>"""

    return {
        "email_subject": f"⚡ Your SEO Fix Report — {fix_package.url} ({fix_package.seo_score_before}→{fix_package.seo_score_after})",
        "email_html": email_html,
        "score_before": fix_package.seo_score_before,
        "score_after": fix_package.seo_score_after,
        "score_improvement": score_improvement,
        "total_fixes": fix_package.total_fixes,
        "platform": fix_package.platform,
    }


def format_fix_package_json(fix_package: FixPackage) -> dict:
    """Format the fix package as a JSON dict for API response / download."""
    return {
        "order_token": fix_package.order_token,
        "url": fix_package.url,
        "platform": fix_package.platform,
        "seo_score_before": fix_package.seo_score_before,
        "seo_score_after": fix_package.seo_score_after,
        "scores_before": fix_package.scores_before,
        "total_issues": fix_package.total_issues,
        "total_fixes": fix_package.total_fixes,
        "fixes": [asdict(f) for f in fix_package.fixes],
        "audit_trail": fix_package.audit_trail,
        "generated_at": fix_package.generated_at,
    }
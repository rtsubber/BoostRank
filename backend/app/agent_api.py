"""
BoostRank — SEO API for AI Agents
REST endpoint that AI agents can POST a URL to and get JSON SEO analysis.
No signup required for free tier. API key auth for paid tiers.
Rate limiting: 5 free/month, then paid.
"""

import time
import hashlib
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, HttpUrl
from typing import Optional

from app.database import (
    check_rate_limit, increment_rate_limit, save_audit,
    log_usage, log_signup, get_db, TIER_LIMITS,
)

router = APIRouter(prefix="/api/v1", tags=["AI Agent API"])


class AgentAuditRequest(BaseModel):
    url: HttpUrl
    detail_level: str = "full"  # "full" or "summary"


class AgentAuditResponse(BaseModel):
    url: str
    seo_score: int
    scores: dict
    issues: list[dict]
    recommendations: list[str]
    page_data: dict
    meta: dict
    cached: bool = False
    credits_remaining: int
    created_at: float


# --- API Key Auth ---

def authenticate_api_key(request: Request) -> dict | None:
    """
    Authenticate via API key. Checks:
    1. X-API-Key header
    2. Authorization: Bearer <key>
    3. api_key query param
    
    Returns dict with user info or None for anonymous.
    """
    api_key = (
        request.headers.get("X-API-Key") or
        request.headers.get("Authorization", "").replace("Bearer ", "") or
        request.query_params.get("api_key", "")
    )

    if not api_key:
        return None

    # Hash the key and look it up
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()

    conn = get_db()
    try:
        key_row = conn.execute(
            "SELECT * FROM api_keys WHERE key_hash = ? AND revoked_at IS NULL",
            (key_hash,),
        ).fetchone()
    finally:
        conn.close()

    if not key_row:
        return None

    # Check if we need to reset monthly counter
    now = time.time()
    month_ago = now - 2592000
    if key_row["last_reset"] and key_row["last_reset"] < month_ago:
        conn = get_db()
        try:
            conn.execute(
                "UPDATE api_keys SET requests_this_month = 0, last_reset = ? WHERE id = ?",
                (now, key_row["id"]),
            )
            conn.commit()
        finally:
            conn.close()
        key_row = dict(key_row)
        key_row["requests_this_month"] = 0
        key_row["last_reset"] = now

    # Get user
    conn = get_db()
    try:
        user = conn.execute("SELECT * FROM users WHERE id = ?", (key_row["user_id"],)).fetchone()
    finally:
        conn.close()

    if not user:
        return None

    return {
        "user_id": user["id"],
        "api_key_id": key_row["id"],
        "tier": key_row["tier"] if key_row["tier"] != "free" else user["tier"],
        "monthly_limit": key_row["monthly_limit"],
        "requests_this_month": key_row["requests_this_month"],
    }


# --- Endpoints ---

@router.get("/")
async def api_info():
    """API info and documentation."""
    return {
        "name": "BoostRank SEO API",
        "version": "1.0.0",
        "description": "AI Agent-friendly SEO analysis API. POST a URL, get JSON results.",
        "docs": "https://boostrank.co/docs/api",
        "auth": {
            "free": "No key needed — 5 audits/month",
            "pro": "X-API-Key header or Bearer token — 50 audits/month",
            "business": "X-API-Key header or Bearer token — 1,000 API calls/month",
            "agency": "X-API-Key header or Bearer token — 10,000 API calls/month",
        },
        "pricing": "https://boostrank.co/pricing",
        "endpoints": {
            "POST /api/v1/audit": "Full SEO audit",
            "POST /api/v1/quick": "Quick meta + heading check",
            "GET /api/v1/credits": "Check remaining credits",
        },
    }


@router.post("/audit", response_model=AgentAuditResponse)
async def agent_audit(request: AgentAuditRequest, req: Request, response: Response):
    """
    Full SEO audit via API.
    Free: 5/month (no key needed)
    Pro: 1,000/month (API key)
    Agency: 10,000/month (API key)
    """
    start_time = time.time()
    auth = authenticate_api_key(req)

    if auth:
        # Authenticated user — check their tier limits
        user_id = auth["user_id"]
        tier = auth["tier"]

        # Check monthly API limit
        allowed, remaining, reset_in = check_rate_limit(user_id, "api", tier)
        if not allowed:
            response.headers["Retry-After"] = str(reset_in)
            raise HTTPException(
                status_code=429,
                detail=f"API rate limit reached. Resets in {reset_in}s. Upgrade at https://boostrank.co/pricing",
            )

        # Increment rate limit and API key counter
        increment_rate_limit(user_id, "api")
        conn = get_db()
        try:
            conn.execute(
                "UPDATE api_keys SET requests_this_month = requests_this_month + 1 WHERE id = ?",
                (auth["api_key_id"],),
            )
            conn.commit()
        finally:
            conn.close()

        credits_remaining = remaining if remaining != -1 else -1  # -1 = unlimited
        api_key_id = auth["api_key_id"]
    else:
        # Anonymous — check IP-based rate limiting
        user_id = None
        tier = "free"
        api_key_id = None

        # Simple IP-based rate limit for anonymous users
        client_ip = req.client.host if req.client else "0.0.0.0"
        ip_key = f"anon:{client_ip}"

        # Use a lightweight check — allow 5/month per IP
        now = time.time()
        month_key = int(now / 2592000)  # Monthly window

        conn = get_db()
        try:
            row = conn.execute(
                "SELECT count FROM rate_limits WHERE user_id = 0 AND action_type = ? AND window_start = ?",
                (ip_key, month_key),
            ).fetchone()

            used = row["count"] if row else 0
            if used >= 5:
                raise HTTPException(
                    status_code=429,
                    detail="Free tier limit (5/month) reached. Get an API key at https://boostrank.co/pricing",
                )

            # Record usage
            # Use action_type as ip_key to avoid FK constraint on user_id=0
            # anon rate limits don't need a user_id reference
            conn.execute(
                """INSERT INTO rate_limits (user_id, action_type, count, window_start)
                   VALUES (?, ?, 1, ?)
                   ON CONFLICT(user_id, action_type, window_start)
                   DO UPDATE SET count = count + 1""",
                (-1, ip_key, month_key),
            )
            conn.commit()
        finally:
            conn.close()

        credits_remaining = 5 - used - 1

    # Run the audit
    url = str(request.url)

    try:
        from app.analyzers.fetcher import fetch_page
        from app.analyzers.meta_tags import analyze_meta_tags
        from app.analyzers.headings import analyze_headings
        from app.analyzers.images import analyze_images
        from app.analyzers.technical import analyze_technical
        from app.analyzers.schema_org import analyze_schema
        from app.analyzers.scoring import calculate_seo_score

        html, response_time, final_url = await fetch_page(url)

        meta = analyze_meta_tags(html, url)
        headings = analyze_headings(html, url)
        images = analyze_images(html, url)
        technical = analyze_technical(html, url, final_url)
        schema = analyze_schema(html, url)

        all_issues = (
            meta["issues"] + headings["issues"] +
            images["issues"] + technical["issues"] + schema["issues"]
        )

        scores = calculate_seo_score(meta, headings, images, technical, schema)

        page_data = {
            "title": meta.get("title", ""),
            "description": meta.get("description", ""),
            "canonical": meta.get("canonical", ""),
            "og_title": meta.get("og_title", ""),
            "og_image": meta.get("og_image", ""),
            "h1_count": headings.get("h1_count", 0),
            "total_headings": headings.get("total_count", 0),
            "image_count": images.get("total", 0),
            "images_missing_alt": images.get("missing_alt", 0),
            "has_schema": schema.get("has_schema", False),
            "schema_types": schema.get("types", []),
            "response_time_ms": response_time,
            "final_url": final_url,
        }

    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch page: {str(e)}")

    # Generate recommendations
    recommendations = _generate_recommendations(scores, all_issues)

    # Save audit
    # Get request metadata for tracking
    audit_ip = req.headers.get("x-forwarded-for", req.headers.get("x-real-ip", req.client.host if req.client else "0.0.0.0")).split(",")[0].strip()
    audit_ua = req.headers.get("user-agent", "")[:500]

    # Log usage for monitoring
    log_usage(
        endpoint="api_audit",
        url=url,
        key_id=str(auth["api_key_id"]) if auth else None,
        ip_address=audit_ip,
        user_agent=audit_ua,
        status_code=200,
        response_time_ms=round((time.time() - start_time) * 1000) if 'start_time' in dir() else None,
    )

    if request.detail_level == "full":
        # Use -1 for anonymous users to avoid NULL FK issues
        save_audit(
            user_id=user_id or -1, api_key_id=api_key_id or -1,
            url=url, seo_score=scores["total"],
            scores=scores, issues=all_issues, page_data=page_data,
            source="api",
            ip_address=audit_ip, user_agent=audit_ua,
            response_time_ms=round((time.time() - start_time) * 1000) if 'start_time' in dir() else None,
        )

    # Format issues based on detail level
    if request.detail_level == "summary":
        issues = [
            {"severity": i["severity"], "category": i["category"], "message": i["message"]}
            for i in sorted(all_issues, key=lambda x: 0 if x["severity"] == "error" else (1 if x["severity"] == "warning" else 2))[:10]
        ]
    else:
        issues = all_issues

    return AgentAuditResponse(
        url=url,
        seo_score=scores["total"],
        scores=scores,
        issues=issues,
        recommendations=recommendations,
        page_data=page_data,
        meta={
            "title": meta.get("title", ""),
            "description": meta.get("description", ""),
            "title_length": meta.get("title_length", 0),
            "description_length": meta.get("description_length", 0),
        },
        credits_remaining=credits_remaining,
        created_at=time.time(),
    )


@router.post("/quick")
async def agent_quick_check(
    request: AgentAuditRequest,
    req: Request,
    response: Response,
):
    """Quick meta + heading check. Uses 1 credit."""
    auth = authenticate_api_key(req)

    # Same rate limiting as full audit but lighter
    # For simplicity, reuse the same counter

    url = str(request.url)

    try:
        from app.analyzers.fetcher import fetch_page
        from app.analyzers.meta_tags import analyze_meta_tags
        from app.analyzers.headings import analyze_headings

        html, response_time, final_url = await fetch_page(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch: {str(e)}")

    meta = analyze_meta_tags(html, url)
    headings = analyze_headings(html, url)

    issues = meta["issues"] + headings["issues"]
    recommendations = _generate_quick_recommendations(meta, headings)

    return {
        "url": url,
        "title": meta.get("title", ""),
        "description": meta.get("description", ""),
        "title_length": meta.get("title_length", 0),
        "description_length": meta.get("description_length", 0),
        "h1_count": headings.get("h1_count", 0),
        "heading_structure": headings.get("structure", []),
        "issues": issues,
        "recommendations": recommendations,
        "response_time_ms": response_time,
    }


@router.get("/credits")
async def check_credits(req: Request):
    """Check remaining API credits."""
    auth = authenticate_api_key(req)

    if not auth:
        # Anonymous — return free tier info
        return {
            "tier": "free",
            "monthly_limit": 5,
            "remaining": "Use POST /api/v1/audit to check",
            "note": "Sign up at https://boostrank.co for higher limits",
        }

    tier = auth["tier"]
    limits = TIER_LIMITS.get(tier, TIER_LIMITS["free"])

    _, remaining, _ = check_rate_limit(auth["user_id"], "api", tier)

    return {
        "tier": tier,
        "monthly_limit": limits["api_per_month"],
        "remaining": remaining if remaining != -1 else "unlimited",
    }


def _generate_recommendations(scores: dict, issues: list) -> list[str]:
    """Generate prioritized recommendations from audit results."""
    recs = []

    # Score-based
    total = scores.get("total", 0)
    if total < 30:
        recs.append("Critical: Your SEO score is very low. Focus on fixing all errors first.")
    elif total < 50:
        recs.append("Your SEO needs significant improvement. Start with the highest-priority issues.")
    elif total < 70:
        recs.append("Decent foundation. Focus on the categories where you score lowest.")
    elif total < 85:
        recs.append("Good SEO health. Fine-tune the remaining issues for maximum impact.")
    else:
        recs.append("Excellent SEO! Minor optimizations could push you to the top.")

    # Category-specific
    for cat in ["meta", "headings", "images", "technical", "schema"]:
        cat_score = scores.get(cat, 0)
        if cat_score < 50:
            tips = {
                "meta": "Add unique title tags (30-60 chars) and meta descriptions (120-160 chars) to every page.",
                "headings": "Fix your heading structure: use exactly one H1, then H2-H6 in logical order.",
                "images": "Add descriptive alt text to all images. Compress large images for faster loading.",
                "technical": "Switch to HTTPS, add internal links, and set the lang attribute on <html>.",
                "schema": "Add Schema.org structured data (Product, Organization, FAQPage) for rich results.",
            }
            recs.append(f"⚠️ {cat.title()} ({cat_score}/100): {tips.get(cat, 'Needs improvement.')}")

    # Count errors
    errors = sum(1 for i in issues if i.get("severity") == "error")
    if errors > 0:
        recs.append(f"Fix {errors} error-level issues first — these have the biggest SEO impact.")

    return recs[:8]


def _generate_quick_recommendations(meta: dict, headings: dict) -> list[str]:
    """Quick recommendations for the /quick endpoint."""
    recs = []

    if not meta.get("title"):
        recs.append("Add a title tag — it's the most important on-page SEO element.")
    elif meta.get("title_length", 0) < 30:
        recs.append("Your title is too short. Aim for 30-60 characters.")
    elif meta.get("title_length", 0) > 60:
        recs.append("Your title is too long. Keep it under 60 characters for best display in search results.")

    if not meta.get("description"):
        recs.append("Add a meta description (120-160 characters) for better click-through rates.")
    elif meta.get("description_length", 0) < 120:
        recs.append("Your meta description is too short. Aim for 120-160 characters.")
    elif meta.get("description_length", 0) > 160:
        recs.append("Your meta description is too long. Keep it under 160 characters.")

    if headings.get("h1_count", 0) == 0:
        recs.append("Add an H1 heading — it tells search engines what the page is about.")
    elif headings.get("h1_count", 0) > 1:
        recs.append("Use only one H1 per page. Extra H1s confuse search engines.")

    if not recs:
        recs.append("Your meta tags and headings look good! Run a full audit for deeper analysis.")

    return recs
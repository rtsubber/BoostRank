"""
BoostRank — SEO Analysis API
FastAPI backend for e-commerce SEO auditing.
A BrandBoost Studio product.

Features:
- Free SEO audits (1/day free, unlimited Pro)
- AI Agent API (100/month free, paid tiers)
- Competitor comparison (Pro: 5/week, Agency: unlimited)
- PDF report generation (Pro: 1/week, Agency: unlimited)
- User signup/login with JWT auth
- Stripe billing integration
"""

import os
import time
from collections import defaultdict
import hmac
from fastapi import FastAPI, HTTPException, Query, Depends, Request, Response, Header
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, HttpUrl
from typing import Optional

from app.analyzers.meta_tags import analyze_meta_tags
from app.analyzers.headings import analyze_headings
from app.analyzers.images import analyze_images
from app.analyzers.technical import analyze_technical
from app.analyzers.schema_org import analyze_schema
from app.analyzers.scoring import calculate_seo_score
from app.waitlist import router as waitlist_router

# New modules
from app.database import (
    init_db, get_db, check_rate_limit, increment_rate_limit,
    save_audit, get_user_audits, get_audit_by_id, TIER_LIMITS,
    log_signup, log_usage,
)
from app.auth import (
    signup, login, create_api_key, list_api_keys, revoke_api_key,
    get_tier_info, get_current_user, get_api_key_user,
    SignupRequest, LoginRequest, UserResponse,
)
from app.compare import router as compare_router
from app.reports import router as reports_router
from app.billing import router as billing_router
from app.agent_api import router as agent_api_router

app = FastAPI(
    title="BoostRank API",
    description="Instant SEO audits for e-commerce stores — a BrandBoost Studio product",
    version="1.0.0",
    docs_url=None,  # Disable Swagger UI in production
    redoc_url=None,  # Disable ReDoc in production
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://boostrank.co", "https://www.boostrank.co", "https://sublime-illumination-production-5373.up.railway.app"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "X-API-Key", "Content-Type"],
)

# Initialize database on startup
@app.on_event("startup")
async def startup():
    init_db()


# --- Models ---

class AuditRequest(BaseModel):
    url: HttpUrl
    include_lighthouse: bool = False

class AuditIssue(BaseModel):
    severity: str
    category: str
    message: str
    detail: Optional[str] = None
    fix: Optional[str] = None

class AuditResponse(BaseModel):
    url: str
    timestamp: float
    seo_score: int
    scores: dict
    issues: list[AuditIssue]
    page_data: dict


# --- Auth Routes ---

# --- Auth Routes ---

# Signup rate limiting
_signup_tracker: dict[str, list[float]] = defaultdict(list)
SIGNUP_RATE_LIMIT = 5  # per IP per hour
SIGNUP_RATE_WINDOW = 3600  # 1 hour


def _check_signup_rate(client_ip: str) -> bool:
    """Returns True if the IP is within signup rate limit."""
    now = time.time()
    timestamps = _signup_tracker.get(client_ip, [])
    recent = [t for t in timestamps if now - t < SIGNUP_RATE_WINDOW]
    _signup_tracker[client_ip] = recent
    if len(recent) >= SIGNUP_RATE_LIMIT:
        return False
    recent.append(now)
    return True


def _get_client_ip(request: Request) -> str:
    """Extract real client IP from X-Forwarded-For or fallback to request.client."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        # X-Forwarded-For: client, proxy1, proxy2
        return forwarded.split(",")[0].strip()
    real_ip = request.headers.get("x-real-ip", "")
    if real_ip:
        return real_ip.strip()
    return request.client.host if request.client else "0.0.0.0"


class APIKeyCreateRequest(BaseModel):
    name: str = "Default"

class APIKeyRevokeRequest(BaseModel):
    key_id: int


@app.post("/api/auth/signup")
async def auth_signup(request: SignupRequest, req: Request):
    """Register a new user account."""
    # Rate limit signups by IP
    client_ip = _get_client_ip(req)
    user_agent = req.headers.get("user-agent", "")[:500]
    if not _check_signup_rate(client_ip):
        raise HTTPException(status_code=429, detail="Signup rate limit exceeded. Try again later.")
    result = signup(request)
    # Log signup for monitoring
    log_signup(email=request.email, tier="free", ip_address=client_ip, user_agent=user_agent)
    return result


@app.post("/api/auth/login")
async def auth_login(request: LoginRequest):
    """Login and get JWT token."""
    result = login(request)
    return result


@app.get("/api/auth/me", response_model=UserResponse)
async def auth_me(user: dict = Depends(get_current_user)):
    """Get current user info."""
    return UserResponse(
        id=user["id"],
        email=user["email"],
        name=user["name"],
        tier=user["tier"],
        created_at=user["created_at"],
    )


@app.get("/api/auth/tier")
async def auth_tier(user: dict = Depends(get_current_user)):
    """Get current tier and limits."""
    return get_tier_info(user["id"])


@app.post("/api/auth/keys")
async def create_key(request: APIKeyCreateRequest, user: dict = Depends(get_current_user)):
    """Create a new API key."""
    return create_api_key(user["id"], name=request.name)


@app.get("/api/auth/keys")
async def list_keys(user: dict = Depends(get_current_user)):
    """List your API keys."""
    return {"keys": list_api_keys(user["id"])}


@app.delete("/api/auth/keys/{key_id}")
async def delete_key(key_id: int, user: dict = Depends(get_current_user)):
    """Revoke an API key."""
    revoke_api_key(user["id"], key_id)
    return {"status": "revoked"}


# --- Audit History ---

@app.get("/api/audits")
async def list_audits(
    limit: int = 50,
    offset: int = 0,
    user: dict = Depends(get_current_user),
):
    """Get your audit history."""
    audits = get_user_audits(user["id"], limit=limit, offset=offset)
    return {"audits": audits}


@app.get("/api/audits/{audit_id}")
async def get_audit(audit_id: int, user: dict = Depends(get_current_user)):
    """Get a specific audit by ID."""
    audit = get_audit_by_id(audit_id)
    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")
    if audit.get("user_id") and audit["user_id"] != user["id"]:
        raise HTTPException(status_code=403, detail="Not your audit")
    return audit


# --- Core Audit Endpoint (web, with rate limiting) ---

@app.post("/api/audit", response_model=AuditResponse)
async def audit_page(
    request: AuditRequest,
    req: Request,
    user: dict = Depends(get_current_user),
):
    """Full SEO audit of a single page (authenticated)."""
    url = str(request.url)
    tier = user["tier"]

    # Check rate limit
    allowed, remaining, reset_in = check_rate_limit(user["id"], "audit", tier)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail=f"Daily audit limit reached. Resets in {reset_in}s. Upgrade at https://boostrank.co/pricing",
            headers={"Retry-After": str(reset_in)},
        )

    try:
        from app.analyzers.fetcher import fetch_page
        html, response_time, final_url = await fetch_page(url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch page: {str(e)}")

    meta_results = analyze_meta_tags(html, url)
    heading_results = analyze_headings(html, url)
    image_results = analyze_images(html, url)
    technical_results = analyze_technical(html, url, final_url)
    schema_results = analyze_schema(html, url)

    all_issues = (
        meta_results["issues"] +
        heading_results["issues"] +
        image_results["issues"] +
        technical_results["issues"] +
        schema_results["issues"]
    )

    scores = calculate_seo_score(
        meta_results, heading_results, image_results,
        technical_results, schema_results
    )

    page_data = {
        "title": meta_results.get("title", ""),
        "description": meta_results.get("description", ""),
        "canonical": meta_results.get("canonical", ""),
        "og_title": meta_results.get("og_title", ""),
        "og_image": meta_results.get("og_image", ""),
        "h1_count": heading_results.get("h1_count", 0),
        "total_headings": heading_results.get("total_count", 0),
        "image_count": image_results.get("total", 0),
        "images_missing_alt": image_results.get("missing_alt", 0),
        "has_schema": schema_results.get("has_schema", False),
        "schema_types": schema_results.get("types", []),
        "response_time_ms": response_time,
        "final_url": final_url,
    }

    # Increment rate limit and save audit
    increment_rate_limit(user["id"], "audit")
    save_audit(
        user_id=user["id"], api_key_id=None,
        url=url, seo_score=scores["total"],
        scores=scores, issues=all_issues, page_data=page_data,
        source="web",
    )

    response = AuditResponse(
        url=url,
        timestamp=time.time(),
        seo_score=scores["total"],
        scores=scores,
        issues=all_issues,
        page_data=page_data,
    )

    # Add rate limit headers
    # Note: FastAPI Response headers would be set on the Response object
    return response


@app.post("/api/quick-check")
async def quick_check(url: HttpUrl = Query(..., description="URL to check")):
    """Fast meta + heading check (no auth required, no rate limit)."""
    url_str = str(url)

    try:
        from app.analyzers.fetcher import fetch_page
        html, response_time, final_url = await fetch_page(url_str)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch: {str(e)}")

    meta = analyze_meta_tags(html, url_str)
    headings = analyze_headings(html, url_str)

    return {
        "url": url_str,
        "title": meta.get("title", ""),
        "description": meta.get("description", ""),
        "title_length": meta.get("title_length", 0),
        "description_length": meta.get("description_length", 0),
        "h1_count": headings.get("h1_count", 0),
        "heading_structure": headings.get("structure", []),
        "issues": meta["issues"] + headings["issues"],
    }


# --- Include Sub-Routers ---

app.include_router(compare_router)
app.include_router(reports_router)
app.include_router(billing_router)
app.include_router(agent_api_router)
app.include_router(waitlist_router)


# --- Admin Monitoring ---

# No hardcoded fallback. If unset, admin routes fail closed (503) rather than
# accepting a publicly-known default key.
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY")
if not ADMIN_API_KEY:
    import logging
    logging.getLogger("boostrank").warning(
        "ADMIN_API_KEY is not set — admin endpoints are disabled until it is configured."
    )


def require_admin(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """Authenticate an admin request.

    The key is read from a request header (never the URL query string, which
    would leak it into logs, browser history, and Referer headers) and compared
    in constant time to avoid a timing side channel.
    """
    if not ADMIN_API_KEY:
        raise HTTPException(status_code=503, detail="Admin access not configured")
    if not hmac.compare_digest(x_admin_key, ADMIN_API_KEY):
        raise HTTPException(status_code=403, detail="Admin access required")
    return True


@app.get("/api/admin/stats")
async def admin_stats(
    days: int = 7,
    _admin: bool = Depends(require_admin),
):
    """Admin dashboard: usage stats, abuse monitoring."""

    conn = get_db()
    now = time.time()
    since = now - (days * 86400)

    # Total audits
    total_audits = conn.execute(
        "SELECT COUNT(*) FROM audit_history WHERE created_at >= ?", (since,)
    ).fetchone()[0]

    # Audits by source
    by_source = dict(conn.execute(
        "SELECT source, COUNT(*) FROM audit_history WHERE created_at >= ? GROUP BY source",
        (since,)
    ).fetchall())

    # Audits by day
    by_day = []
    rows = conn.execute(
        """SELECT date(created_at, 'unixepoch') as day, COUNT(*) as count
           FROM audit_history WHERE created_at >= ?
           GROUP BY day ORDER BY day""",
        (since,)
    ).fetchall()
    for r in rows:
        by_day.append({"date": r[0], "count": r[1]})

    # Top URLs audited
    top_urls = []
    rows = conn.execute(
        "SELECT url, COUNT(*) as cnt FROM audit_history WHERE created_at >= ? GROUP BY url ORDER BY cnt DESC LIMIT 10",
        (since,)
    ).fetchall()
    for r in rows:
        top_urls.append({"url": r[0], "count": r[1]})

    # Unique IPs
    unique_ips = conn.execute(
        "SELECT COUNT(DISTINCT ip_address) FROM audit_history WHERE created_at >= ? AND ip_address IS NOT NULL",
        (since,)
    ).fetchone()[0]

    # Suspicious IPs (5+ audits in a day)
    suspicious_ips = []
    rows = conn.execute(
        """SELECT ip_address, COUNT(*) as cnt FROM audit_history
           WHERE created_at >= ? AND ip_address IS NOT NULL
           GROUP BY ip_address HAVING cnt >= 20
           ORDER BY cnt DESC LIMIT 10""",
        (since,)
    ).fetchall()
    for r in rows:
        suspicious_ips.append({"ip": r[0], "count": r[1]})

    # Usage logs
    usage_count = conn.execute(
        "SELECT COUNT(*) FROM usage_logs WHERE created_at >= ?", (since,)
    ).fetchone()[0]

    # Recent usage
    recent_usage = []
    rows = conn.execute(
        """SELECT endpoint, url, ip_address, user_agent, status_code, created_at
           FROM usage_logs WHERE created_at >= ?
           ORDER BY created_at DESC LIMIT 20""",
        (since,)
    ).fetchall()
    for r in rows:
        recent_usage.append({
            "endpoint": r[0], "url": r[1][:80] if r[1] else None,
            "ip": r[2], "user_agent": (r[3] or "")[:60],
            "status": r[4], "time": r[5],
        })

    # Signups
    total_signups = conn.execute(
        "SELECT COUNT(*) FROM signups WHERE created_at >= ?", (since,)
    ).fetchone()[0]

    signup_ips = conn.execute(
        """SELECT ip_address, COUNT(*) as cnt FROM signups
           WHERE created_at >= ? AND ip_address IS NOT NULL
           GROUP BY ip_address HAVING cnt >= 3
           ORDER BY cnt DESC LIMIT 10""",
        (since,)
    ).fetchall()
    suspicious_signups = [{"ip": r[0], "count": r[1]} for r in signup_ips]

    conn.close()

    return {
        "period_days": days,
        "audits": {
            "total": total_audits,
            "by_source": by_source,
            "by_day": by_day,
            "top_urls": top_urls,
            "unique_ips": unique_ips,
        },
        "usage": {
            "total_calls": usage_count,
            "recent": recent_usage,
        },
        "signups": {
            "total": total_signups,
            "suspicious_ips": suspicious_signups,
        },
        "abuse": {
            "suspicious_ips": suspicious_ips,
            "note": "IPs with 20+ audits in period — potential abuse",
        },
    }


# --- Health & Info ---

@app.get("/")
async def root():
    return {
        "name": "BoostRank",
        "version": "1.0.0",
        "by": "BrandBoost Studio",
        "status": "running",
        "docs": "/docs",
        "api": "/api/v1",
    }


@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": time.time()}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
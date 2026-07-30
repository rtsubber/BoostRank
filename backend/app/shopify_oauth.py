"""
BoostRank — Shopify OAuth Integration
Handles the OAuth flow: install → get token → store credentials → push fixes
"""

import os
import time
import secrets
import sqlite3
import httpx
from fastapi import APIRouter, Request, HTTPException, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
from pathlib import Path

router = APIRouter(prefix="/auth/shopify", tags=["shopify-oauth"])

SHOPIFY_CLIENT_ID = os.getenv("SHOPIFY_CLIENT_ID", "")
SHOPIFY_CLIENT_SECRET = os.getenv("SHOPIFY_CLIENT_SECRET", "")
SHOPIFY_SCOPES = "read_products,write_products,read_themes,write_themes"
APP_URL = os.getenv("APP_URL", "https://boostrank.co")
API_URL = os.getenv("API_URL", "https://api.boostrank.co")

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boostrank_fixes.db"


def _get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_shopify_tables():
    """Create Shopify store credentials and OAuth state tables."""
    conn = _get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS shopify_stores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shop_domain TEXT NOT NULL UNIQUE,
                access_token TEXT NOT NULL,
                scopes TEXT,
                email TEXT,
                installed_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                uninstalled_at REAL,
                is_active INTEGER NOT NULL DEFAULT 1,
                order_token TEXT,
                last_fix_run REAL
            );
            CREATE INDEX IF NOT EXISTS idx_shopify_domain ON shopify_stores(shop_domain);
            CREATE INDEX IF NOT EXISTS idx_shopify_active ON shopify_stores(is_active);

            CREATE TABLE IF NOT EXISTS oauth_states (
                state TEXT PRIMARY KEY,
                shop_domain TEXT NOT NULL,
                order_token TEXT,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now'))
            );
        """)
        conn.commit()
    finally:
        conn.close()


# Initialize on module load
init_shopify_tables()


@router.get("/install")
async def shopify_install(shop: str, order_token: Optional[str] = None):
    """Step 1: Redirect customer to Shopify's OAuth approval page.
    
    Customer visits: /auth/shopify/install?shop=their-store.myshopify.com
    """
    if not SHOPIFY_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Shopify app not configured yet")
    
    # Sanitize shop domain
    shop = shop.strip().lower()
    if not shop.endswith(".myshopify.com"):
        shop = f"{shop}.myshopify.com"
    
    # Generate state token for CSRF protection
    state = secrets.token_urlsafe(32)
    
    # Store state temporarily (30 min TTL)
    conn = _get_db()
    try:
        conn.execute(
            "INSERT OR REPLACE INTO oauth_states (state, shop_domain, order_token, created_at) VALUES (?, ?, ?, strftime('%s','now'))",
            (state, shop, order_token),
        )
        conn.commit()
    finally:
        conn.close()
    
    # Build Shopify OAuth URL
    redirect_uri = f"{API_URL}/auth/shopify/callback"
    auth_url = (
        f"https://{shop}/admin/oauth/authorize?"
        f"client_id={SHOPIFY_CLIENT_ID}"
        f"&scope={SHOPIFY_SCOPES}"
        f"&redirect_uri={redirect_uri}"
        f"&state={state}"
    )
    
    return RedirectResponse(url=auth_url)


@router.get("/callback")
async def shopify_callback(request: Request):
    """Step 2: Shopify redirects back here after customer approves.
    
    Shopify sends: ?code=xxx&state=xxx&shop=their-store.myshopify.com
    We exchange the code for a permanent access token.
    """
    params = request.query_params
    code = params.get("code")
    state = params.get("state")
    shop = params.get("shop", "").strip().lower()
    hmac_value = params.get("hmac")
    
    if not code or not state or not shop:
        raise HTTPException(status_code=400, detail="Missing required OAuth parameters")
    
    if not shop.endswith(".myshopify.com"):
        raise HTTPException(status_code=400, detail="Invalid shop domain")
    
    # Verify state token (CSRF protection)
    conn = _get_db()
    try:
        state_row = conn.execute(
            "SELECT * FROM oauth_states WHERE state = ? AND shop_domain = ?",
            (state, shop),
        ).fetchone()
        
        if not state_row:
            raise HTTPException(status_code=403, detail="Invalid or expired state token")
        
        order_token = state_row["order_token"] if "order_token" in state_row.keys() else None
        
        # Clean up used state
        conn.execute("DELETE FROM oauth_states WHERE state = ?", (state,))
        conn.commit()
    finally:
        conn.close()
    
    # Exchange code for access token
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://{shop}/admin/oauth/access_token",
            json={
                "client_id": SHOPIFY_CLIENT_ID,
                "client_secret": SHOPIFY_CLIENT_SECRET,
                "code": code,
            },
        )
    
    if resp.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to get access token: {resp.text}")
    
    token_data = resp.json()
    access_token = token_data.get("access_token")
    granted_scopes = token_data.get("scope", "")
    
    if not access_token:
        raise HTTPException(status_code=500, detail="No access token in response")
    
    # Get shop info (email, name, etc.)
    async with httpx.AsyncClient() as client:
        shop_resp = await client.get(
            f"https://{shop}/admin/api/2024-01/shop.json",
            headers={"X-Shopify-Access-Token": access_token},
        )
    
    shop_email = ""
    if shop_resp.status_code == 200:
        shop_info = shop_resp.json().get("shop", {})
        shop_email = shop_info.get("email", "")
    
    # Store credentials
    conn = _get_db()
    try:
        conn.execute(
            """INSERT INTO shopify_stores (shop_domain, access_token, scopes, email, order_token)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(shop_domain) DO UPDATE SET
                 access_token = excluded.access_token,
                 scopes = excluded.scopes,
                 email = excluded.email,
                 is_active = 1,
                 uninstalled_at = NULL,
                 installed_at = strftime('%s','now')""",
            (shop, access_token, granted_scopes, shop_email, order_token),
        )
        conn.commit()
    finally:
        conn.close()
    
    # Redirect back to the frontend with success message
    if order_token:
        return RedirectResponse(
            url=f"{APP_URL}/fix?connected=true&shop={shop}&token={order_token}"
        )
    return RedirectResponse(
        url=f"{APP_URL}/fix?connected=true&shop={shop}"
    )


@router.get("/status")
async def shopify_connection_status(shop: str):
    """Check if a shop is connected (has valid access token)."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT shop_domain, is_active, installed_at, email FROM shopify_stores WHERE shop_domain = ? AND is_active = 1",
            (shop.strip().lower()),
        ).fetchone()
        
        if not row:
            return {"connected": False}
        
        return {
            "connected": True,
            "shop": row["shop_domain"],
            "email": row["email"],
            "installed_at": row["installed_at"],
        }
    finally:
        conn.close()


@router.delete("/disconnect")
async def disconnect_shopify(shop: str):
    """Disconnect a shop (mark as inactive, keep token for audit purposes)."""
    conn = _get_db()
    try:
        conn.execute(
            "UPDATE shopify_stores SET is_active = 0, uninstalled_at = strftime('%s','now') WHERE shop_domain = ?",
            (shop.strip().lower(),),
        )
        conn.commit()
    finally:
        conn.close()
    
    return {"status": "disconnected", "shop": shop}


def get_shopify_token(shop_domain: str) -> Optional[str]:
    """Get the access token for a connected shop. Used by the fix applier."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT access_token FROM shopify_stores WHERE shop_domain = ? AND is_active = 1",
            (shop_domain.strip().lower(),),
        ).fetchone()
        return row["access_token"] if row else None
    finally:
        conn.close()
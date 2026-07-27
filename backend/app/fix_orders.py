"""
BoostRank — Fix Orders
One-time and subscription fix orders for SEO issues found in audits.
"""

import os
import json
import time
import secrets
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, HttpUrl
from typing import Optional
from app.database import get_db, init_db

router = APIRouter(prefix="/api/fix-orders", tags=["fix-orders"])

# Stripe configuration
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET_FIX", "")

# Fix products — one-time and subscription
STRIPE_FIX_PRODUCTS = {
    "one_time_fix": {
        "price_id": os.getenv("STRIPE_FIX_ONETIME_PRICE_ID", "price_1TxvlgHTQdr0mtHrh0VCeIaR"),
        "name": "BoostRank SEO Fix",
        "amount": 14900,  # $149
        "description": "One-time fix of all SEO issues found in your audit",
    },
    "seo_subscription": {
        "price_id": os.getenv("STRIPE_FIX_SUB_PRICE_ID", "price_1Txvm8HTQdr0mtHrWtRKq1Hf"),
        "name": "BoostRank SEO Pro",
        "amount": 9900,  # $99/mo
        "description": "Monthly SEO monitoring, fixes, and re-audits",
    },
}


def init_fix_orders_table():
    """Create fix_orders table if it doesn't exist."""
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS fix_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_token TEXT UNIQUE NOT NULL,
                email TEXT NOT NULL,
                url TEXT NOT NULL,
                audit_id INTEGER,
                product_type TEXT NOT NULL CHECK(product_type IN ('one_time_fix', 'seo_subscription')),
                stripe_session_id TEXT,
                stripe_customer_id TEXT,
                stripe_subscription_id TEXT,
                status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'paid', 'processing', 'completed', 'failed', 'refunded')),
                seo_score_before INTEGER,
                seo_score_after INTEGER,
                issues_json TEXT NOT NULL DEFAULT '[]',
                fixes_json TEXT DEFAULT NULL,
                fixed_code_json TEXT DEFAULT NULL,
                delivery_method TEXT NOT NULL DEFAULT 'email' CHECK(delivery_method IN ('email', 'download', 'push')),
                site_platform TEXT DEFAULT NULL,
                site_access_json TEXT DEFAULT NULL,
                created_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                paid_at REAL,
                completed_at REAL
            );
            CREATE INDEX IF NOT EXISTS idx_fix_orders_token ON fix_orders(order_token);
            CREATE INDEX IF NOT EXISTS idx_fix_orders_email ON fix_orders(email);
            CREATE INDEX IF NOT EXISTS idx_fix_orders_status ON fix_orders(status);
        """)
        conn.commit()
    finally:
        conn.close()


# Initialize table on module load
init_fix_orders_table()


class FixOrderRequest(BaseModel):
    email: str
    url: str
    audit_id: Optional[int] = None
    product_type: str  # "one_time_fix" or "seo_subscription"
    seo_score: Optional[int] = None
    issues: Optional[list] = None
    site_platform: Optional[str] = None  # "shopify", "wordpress", "custom", etc.
    success_url: str = "https://boostrank.co/fix/thank-you"
    cancel_url: str = "https://boostrank.co/fix"


class FixOrderStatus(BaseModel):
    order_token: str
    status: str
    url: str
    product_type: str
    seo_score_before: Optional[int] = None
    issues_count: int = 0
    created_at: float


@router.get("/plans")
async def get_fix_plans():
    """Get available fix plans and pricing."""
    plans = {
        "one_time_fix": {
            "name": "One-Time SEO Fix",
            "price": "$149",
            "description": "We fix all the SEO issues found in your audit. You get the corrected code + instructions.",
            "features": [
                "Fix all critical SEO issues",
                "Corrected meta tags, schema, OG tags",
                "Step-by-step implementation guide",
                "Before/after comparison",
                "Delivered within 48 hours",
            ],
        },
        "seo_subscription": {
            "name": "SEO Pro Subscription",
            "price": "$99/mo",
            "description": "Ongoing SEO monitoring, automatic fixes, and monthly re-audits.",
            "features": [
                "Everything in One-Time Fix",
                "Monthly re-audits",
                "New page SEO optimization",
                "Schema & meta tag updates",
                "Priority support",
                "Cancel anytime",
            ],
        },
    }
    return {"plans": plans}


@router.post("/checkout")
async def create_fix_checkout(request: FixOrderRequest):
    """Create a Stripe Checkout session for a fix order."""
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY
    except ImportError:
        raise HTTPException(status_code=500, detail="Stripe SDK not installed")

    if not STRIPE_SECRET_KEY:
        raise HTTPException(status_code=500, detail="Payment system not configured")

    if request.product_type not in STRIPE_FIX_PRODUCTS:
        raise HTTPException(status_code=400, detail=f"Invalid product type: {request.product_type}")

    product = STRIPE_FIX_PRODUCTS[request.product_type]

    # Generate order token
    order_token = f"bfx_{secrets.token_urlsafe(24)}"

    # Save order to DB first
    conn = get_db()
    try:
        cursor = conn.execute(
            """INSERT INTO fix_orders
               (order_token, email, url, audit_id, product_type, status,
                seo_score_before, issues_json, site_platform)
               VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, ?)""",
            (order_token, request.email, request.url, request.audit_id,
             request.product_type, request.seo_score,
             json.dumps(request.issues or []), request.site_platform),
        )
        conn.commit()
        order_id = cursor.lastrowid
    finally:
        conn.close()

    # Create Stripe checkout session
    mode = "payment" if request.product_type == "one_time_fix" else "subscription"

    try:
        session = stripe.checkout.Session.create(
            mode=mode,
            payment_method_types=["card"],
            line_items=[{
                "price": product["price_id"],
                "quantity": 1,
            }],
            success_url=f"{request.success_url}?token={order_token}",
            cancel_url=request.cancel_url,
            customer_email=request.email,
            metadata={
                "order_token": order_token,
                "product_type": request.product_type,
                "url": request.url,
                "audit_id": str(request.audit_id) if request.audit_id else "",
            },
        )

        # Update order with Stripe session ID
        conn = get_db()
        try:
            conn.execute(
                "UPDATE fix_orders SET stripe_session_id = ? WHERE id = ?",
                (session.id, order_id),
            )
            conn.commit()
        finally:
            conn.close()

        return {"checkout_url": session.url, "order_token": order_token, "session_id": session.id}

    except stripe.error.StripeError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/status/{order_token}")
async def get_fix_order_status(order_token: str):
    """Check the status of a fix order."""
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT * FROM fix_orders WHERE order_token = ?",
            (order_token,),
        ).fetchone()

        if not row:
            raise HTTPException(status_code=404, detail="Order not found")

        return {
            "order_token": row["order_token"],
            "status": row["status"],
            "url": row["url"],
            "product_type": row["product_type"],
            "seo_score_before": row["seo_score_before"],
            "seo_score_after": row["seo_score_after"],
            "issues_count": len(json.loads(row["issues_json"])) if row["issues_json"] else 0,
            "created_at": row["created_at"],
            "paid_at": row["paid_at"],
            "completed_at": row["completed_at"],
        }
    finally:
        conn.close()


@router.post("/webhook")
async def fix_order_webhook(request: Request):
    """Handle Stripe webhooks for fix orders."""
    body = await request.body()
    sig = request.headers.get("stripe-signature", "")

    try:
        import stripe
        stripe.api_key = STRIPE_SECRET_KEY

        event = stripe.Webhook.construct_event(
            body, sig, STRIPE_WEBHOOK_SECRET
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Webhook error: {str(e)}")

    event_type = event["type"]

    if event_type == "checkout.session.completed":
        session = event["data"]["object"]
        order_token = session.get("metadata", {}).get("order_token")
        product_type = session.get("metadata", {}).get("product_type")

        if order_token:
            conn = get_db()
            try:
                conn.execute(
                    """UPDATE fix_orders
                       SET status = 'paid', stripe_customer_id = ?,
                           stripe_session_id = ?, paid_at = strftime('%s','now')
                       WHERE order_token = ?""",
                    (session.get("customer"), session.id, order_token),
                )
                conn.commit()
            finally:
                conn.close()

            # TODO: Trigger fix generation — call the AI fix engine
            # For now, mark as processing
            conn = get_db()
            try:
                conn.execute(
                    "UPDATE fix_orders SET status = 'processing' WHERE order_token = ?",
                    (order_token,),
                )
                conn.commit()
            finally:
                conn.close()

    elif event_type == "customer.subscription.created":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")
        # Link subscription to the fix order
        conn = get_db()
        try:
            conn.execute(
                "UPDATE fix_orders SET stripe_subscription_id = ? WHERE stripe_customer_id = ?",
                (subscription.id, customer_id),
            )
            conn.commit()
        finally:
            conn.close()

    elif event_type == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        customer_id = subscription.get("customer")
        # Downgrade to one-time if subscription cancelled
        conn = get_db()
        try:
            conn.execute(
                "UPDATE fix_orders SET status = 'completed' WHERE stripe_customer_id = ? AND product_type = 'seo_subscription'",
                (customer_id,),
            )
            conn.commit()
        finally:
            conn.close()

    return {"received": True}


@router.get("/admin/orders")
async def admin_list_orders(request: Request):
    """Admin endpoint: list all fix orders."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if not expected_key or not hmac.compare_digest(admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Unauthorized")

    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT * FROM fix_orders ORDER BY created_at DESC LIMIT 100"
        ).fetchall()

        orders = []
        for row in rows:
            orders.append({
                "id": row["id"],
                "order_token": row["order_token"],
                "email": row["email"],
                "url": row["url"],
                "product_type": row["product_type"],
                "status": row["status"],
                "seo_score_before": row["seo_score_before"],
                "site_platform": row["site_platform"],
                "created_at": row["created_at"],
                "paid_at": row["paid_at"],
                "completed_at": row["completed_at"],
            })
        return {"orders": orders, "total": len(orders)}
    finally:
        conn.close()


@router.post("/admin/{order_id}/complete")
async def admin_mark_complete(order_id: int, request: Request):
    """Admin endpoint: mark a fix order as completed with fix data."""
    admin_key = request.headers.get("X-Admin-Key", "")
    expected_key = os.getenv("ADMIN_API_KEY", "")
    if not expected_key or not hmac.compare_digest(admin_key, expected_key):
        raise HTTPException(status_code=403, detail="Unauthorized")

    body = await request.json()
    fixes_json = body.get("fixes")
    fixed_code_json = body.get("fixed_code")
    seo_score_after = body.get("seo_score_after")

    conn = get_db()
    try:
        conn.execute(
            """UPDATE fix_orders
               SET status = 'completed', fixes_json = ?, fixed_code_json = ?,
                   seo_score_after = ?, completed_at = strftime('%s','now')
               WHERE id = ?""",
            (json.dumps(fixes_json) if fixes_json else None,
             json.dumps(fixed_code_json) if fixed_code_json else None,
             seo_score_after, order_id),
        )
        conn.commit()
    finally:
        conn.close()

    return {"status": "completed", "order_id": order_id}
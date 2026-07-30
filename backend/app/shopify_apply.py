"""
BoostRank — Shopify Apply Fixes Endpoint
Customer pays → connects store → we push fixes directly via Shopify API
"""

import os
import json
import time
import asyncio
from fastapi import APIRouter, Request, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
from app.shopify_oauth import get_shopify_token
from app.shopify_fix_applier import ShopifyFixApplier, ApplyResult
from app.fix_engine.audit_runner import run_full_audit
from app.fix_engine.fix_generator import generate_fixes
from app.fix_engine.audit_trail import AuditTrail
from dataclasses import asdict

router = APIRouter(prefix="/api/shopify", tags=["shopify-fixes"])


class ApplyFixesRequest(BaseModel):
    shop: str  # e.g. "their-store.myshopify.com"
    order_token: str
    url: str  # URL that was audited


class ApplyFixesResponse(BaseModel):
    order_token: str
    shop: str
    url: str
    total_fixes: int
    applied: int
    failed: int
    skipped: int
    results: list
    seo_score_before: int
    seo_score_after: Optional[int] = None


@router.get("/status/{shop}")
async def check_shop_status(shop: str):
    """Check if a Shopify store is connected to BoostRank."""
    token = get_shopify_token(shop)
    if not token:
        return {"connected": False, "shop": shop}
    
    applier = ShopifyFixApplier(shop, token)
    info = await applier.test_connection()
    return info


@router.post("/apply-fixes")
async def apply_fixes_to_shopify(request: ApplyFixesRequest):
    """Apply SEO fixes directly to a customer's Shopify store.
    
    This is the 'done-for-you' flow:
    1. Run audit on the customer's URL
    2. Generate fixes via OpenRouter (Claude)
    3. Push fixes to Shopify via API
    4. Re-audit to show before/after score
    5. Log everything in audit trail
    """
    shop = request.shop.strip().lower()
    token = get_shopify_token(shop)
    
    if not token:
        raise HTTPException(
            status_code=403,
            detail="Shopify store not connected. Visit /auth/shopify/install?shop=your-store.myshopify.com to connect."
        )
    
    # Step 1: Run audit
    audit_result = await run_full_audit(request.url)
    
    if len(audit_result.issues) == 0:
        return ApplyFixesResponse(
            order_token=request.order_token,
            shop=shop,
            url=request.url,
            total_fixes=0,
            applied=0,
            failed=0,
            skipped=0,
            results=[],
            seo_score_before=audit_result.seo_score,
            seo_score_after=audit_result.seo_score,
        )
    
    # Step 2: Generate fixes
    fix_package = await generate_fixes(audit_result, request.order_token)
    
    # Step 3: Apply fixes to Shopify
    applier = ShopifyFixApplier(shop, token)
    fixes_data = [asdict(f) for f in fix_package.fixes]
    apply_results = await applier.apply_fixes(fixes_data, request.url)
    
    applied_count = sum(1 for r in apply_results if r.status == "applied")
    failed_count = sum(1 for r in apply_results if r.status == "failed")
    skipped_count = sum(1 for r in apply_results if r.status == "skipped")
    
    # Step 4: Log in audit trail
    trail = AuditTrail(request.order_token, request.url)
    for r in apply_results:
        if r.status == "applied":
            trail.log_fix_generated(
                category=r.category,
                severity="medium",
                issue=f"Applied: {r.element}",
                element=r.element,
                before_value="(auto-detected from store)",
                after_value=r.detail,
                fix_code="(applied directly via Shopify API)",
                platform="shopify",
            )
    
    # Step 5: Re-audit to get new score (wait a moment for changes to propagate)
    await asyncio.sleep(3)
    try:
        new_audit = await run_full_audit(request.url)
        seo_score_after = new_audit.seo_score
    except Exception:
        seo_score_after = None
    
    return ApplyFixesResponse(
        order_token=request.order_token,
        shop=shop,
        url=request.url,
        total_fixes=len(apply_results),
        applied=applied_count,
        failed=failed_count,
        skipped=skipped_count,
        results=[asdict(r) for r in apply_results],
        seo_score_before=audit_result.seo_score,
        seo_score_after=seo_score_after,
    )
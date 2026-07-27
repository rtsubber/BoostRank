# BoostRank Fix It — Claude's Stripe Architecture & UX Consultation

**Date:** 2026-07-27  
**Model:** Claude Sonnet 4-6  
**Context:** BoostRank (boostrank.co) SEO audit tool — adding "Fix It" paid feature  
**Options:** One-time fix ($149) + SEO Pro subscription ($99/mo)

---

## 1. Payment Links vs. Custom Checkout Sessions

**Stick with Checkout Sessions.** Payment Links are fine for simple storefronts, but you have context that Links can't carry: which site was audited, which issues are being fixed, which user is paying. You need that metadata to trigger the fix workflow after payment.

Payment Links also can't dynamically inject `client_reference_id`, `metadata`, or pre-fill customer email from your session. Your existing `billing.py` already handles Checkout Sessions — adding Fix It there is ~20 lines, not a rewrite.

The only case for Payment Links: if you want a quick MVP with zero backend changes for the next 48 hours. Ship it as Links, prove demand, then migrate. But you're past that point given your existing infrastructure.

---

## 2. One-Time Fix at $149 — Product+Price vs. Invoice Item

**Use a Stripe Product with a one-time Price.** Invoice items are designed for adding charges to existing subscription invoices (e.g., overages). Using them for a standalone one-time purchase is the wrong abstraction — they require an explicit `Invoice.create()` and `Invoice.finalize_and_send()` flow, which is more work and creates a paper-trail mismatch in your dashboard.

The clean architecture:

```python
# billing.py — create once, store the price_id in your config/env
# Run this once in a setup script or Stripe dashboard

# One-time fix product
product = stripe.Product.create(
    name="BoostRank Fix It — One-Time Site Fix",
    metadata={"type": "fix_it", "billing": "one_time"}
)

price = stripe.Price.create(
    product=product.id,
    unit_amount=14900,  # $149.00
    currency="usd",
    metadata={"fix_type": "one_time"}
)
# Store as STRIPE_FIX_ONETIME_PRICE_ID=price_xxx in your env
```

```python
# When user clicks "Fix My Site" (one-time)
async def create_fix_checkout(
    user_id: str,
    user_email: str,
    audit_id: str,
    site_url: str,
    issues: list[str]
) -> str:
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{
            "price": settings.STRIPE_FIX_ONETIME_PRICE_ID,
            "quantity": 1,
        }],
        customer_email=user_email,  # pre-fill if no stripe customer yet
        client_reference_id=user_id,
        metadata={
            "audit_id": audit_id,
            "site_url": site_url,
            "fix_type": "one_time",
            "issue_count": len(issues),
            # Don't store the full issues list here — 500 char limit per value
            # Store audit_id and look up from your DB in the webhook
        },
        success_url=f"{settings.BASE_URL}/fix/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.BASE_URL}/audit/{audit_id}?fix_cancelled=true",
        payment_intent_data={
            "metadata": {
                "audit_id": audit_id,
                "fix_type": "one_time",
            }
        }
    )
    return session.url
```

**Important:** Put `audit_id` in both `session.metadata` AND `payment_intent_data.metadata`. Your webhook will receive `checkout.session.completed` but downstream disputes/refunds fire on `payment_intent.*` events — you want the context there too.

---

## 3. $99/mo Subscription — Separate Product vs. Add-On

**Separate Product. Absolutely.** Your concern is exactly right. A user who wants ongoing SEO fixes doesn't necessarily want BoostRank SaaS features. Coupling them creates:

- Confusing cancellation flows ("will canceling BoostRank Pro also cancel my fix service?")
- Wrong analytics (MRR from fix subscriptions pollutes SaaS tier data)
- Entitlement logic nightmares in your backend

```python
# Create SEO Pro Fix subscription product (run once)
fix_sub_product = stripe.Product.create(
    name="BoostRank SEO Pro — Managed Fix Service",
    metadata={"type": "fix_it", "billing": "subscription"}
)

fix_sub_price = stripe.Price.create(
    product=fix_sub_product.id,
    unit_amount=9900,  # $99.00
    currency="usd",
    recurring={"interval": "month"},
    metadata={"fix_type": "subscription"}
)
# Store as STRIPE_FIX_SUB_PRICE_ID=price_xxx
```

```python
async def create_fix_subscription_checkout(
    user_id: str,
    user_email: str,
    site_url: str,
) -> str:
    # Retrieve or create Stripe Customer
    stripe_customer_id = await get_or_create_stripe_customer(user_id, user_email)
    
    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=stripe_customer_id,  # Use customer ID, not email, for sub mode
        line_items=[{
            "price": settings.STRIPE_FIX_SUB_PRICE_ID,
            "quantity": 1,
        }],
        client_reference_id=user_id,
        metadata={
            "audit_id": audit_id,
            "site_url": site_url,
            "fix_type": "subscription",
        },
        subscription_data={
            "metadata": {
                "audit_id": audit_id,
                "site_url": site_url,
                "fix_type": "subscription",
            }
        },
        success_url=f"{settings.BASE_URL}/fix/success?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{settings.BASE_URL}/audit/{audit_id}?fix_cancelled=true",
    )
    return session.url
```

**One nuance:** If someone has both a BoostRank Pro SaaS sub AND the Fix It sub, they'll appear in Stripe with two subscriptions on one Customer. That's fine and expected — just make sure your entitlement checks query subscriptions by `metadata.type` or `price_id`, not just "has any active subscription."

---

## 4. Stripe Customer Portal vs. Custom Cancel Page

**Use the Customer Portal, but scope it carefully.** Building cancel flows from scratch means you're also building pause, reactivate, plan-switch, and invoice history — the Customer Portal gives you all of that in an afternoon.

The concern is usually "I don't want users to accidentally cancel the wrong subscription." Fix that with Portal configuration:

```python
# Create a Portal Configuration scoped to Fix It products only
# Do this once via API or Stripe Dashboard

config = stripe.billing_portal.Configuration.create(
    business_profile={
        "headline": "Manage your BoostRank Fix It subscription",
    },
    features={
        "subscription_cancel": {
            "enabled": True,
            "mode": "at_period_end",  # Don't cancel immediately
            "cancellation_reason": {
                "enabled": True,
                "options": [
                    "too_expensive",
                    "missing_features", 
                    "switched_service",
                    "unused",
                    "other"
                ]
            }
        },
        "subscription_update": {
            "enabled": False  # Don't let them switch tiers from this portal
        },
        "invoice_history": {"enabled": True},
        "payment_method_update": {"enabled": True},
    },
    metadata={"portal_type": "fix_it"}
)
# Store config ID, pass it when creating portal sessions
```

```python
async def create_portal_session(user_id: str, return_path: str) -> str:
    customer_id = await get_stripe_customer_id(user_id)
    session = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=f"{settings.BASE_URL}{return_path}",
        configuration=settings.STRIPE_FIX_PORTAL_CONFIG_ID,  # Scoped config
    )
    return session.url
```

This way the Fix It portal only shows Fix It subscriptions, and your SaaS portal (different config) only shows SaaS tiers. Clean separation.

---

## 5. Gotchas Mixing One-Time Payments and Subscriptions

Several real ones to watch for:

**a) Webhook handler routing.** Your `checkout.session.completed` handler needs to branch on `session.mode`:

```python
@router.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig, settings.STRIPE_WEBHOOK_SECRET
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400)
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        
        if session["mode"] == "payment":
            await handle_onetime_fix_payment(session)
        elif session["mode"] == "subscription":
            await handle_fix_subscription_created(session)
    
    elif event["type"] == "customer.subscription.deleted":
        sub = event["data"]["object"]
        # Check metadata to distinguish Fix It sub from SaaS sub
        if sub["metadata"].get("fix_type") == "subscription":
            await handle_fix_subscription_cancelled(sub)
        else:
            await handle_saas_subscription_cancelled(sub)
    
    # Don't forget these for subscriptions:
    elif event["type"] == "invoice.payment_failed":
        await handle_payment_failure(event["data"]["object"])
    
    elif event["type"] == "invoice.payment_succeeded":
        await handle_renewal(event["data"]["object"])
    
    return {"status": "ok"}
```

**b) `checkout.session.completed` fires before payment is confirmed for subscriptions.** For `mode=subscription`, the session completing just means they submitted the form — the invoice still needs to succeed. Listen to `invoice.payment_succeeded` with `billing_reason=subscription_create` as the authoritative signal to provision access.

**c) Idempotency.** Webhooks can fire more than once. Use the Stripe event ID or `payment_intent_id` as an idempotency key before provisioning:

```python
async def handle_onetime_fix_payment(session: dict):
    payment_intent_id = session["payment_intent"]
    
    # Idempotency check
    existing = await db.fix_orders.find_one({"payment_intent_id": payment_intent_id})
    if existing:
        return  # Already processed
    
    await db.fix_orders.insert_one({
        "payment_intent_id": payment_intent_id,
        "audit_id": session["metadata"]["audit_id"],
        "user_id": session["client_reference_id"],
        "status": "paid",
        "created_at": datetime.utcnow(),
    })
    
    await trigger_fix_workflow(session["metadata"]["audit_id"])
```

**d) Refunds on one-time vs. subscription.** Refunding a `PaymentIntent` is different from canceling a subscription. Make sure your admin tooling handles both cases — don't assume "cancel = refund."

---

## 6. Freemium Gate — Audit Free, Gate Details, or Full Audit + Upsell Fix?

**Don't gate the audit details. Keep the full audit free and upsell the fix.**

Here's why the gating approach typically backfires for this use case:

The user's anxiety loop is: *"Is my site actually broken? How bad is it?"* If you gate the answer, they leave to use a free competitor (Ahrefs free audit, SEMrush free tier, etc.) instead of upgrading. You lose them entirely.

If you show them the full picture — "You have 14 missing meta descriptions, 3 broken schema blocks, no OG tags on 8 pages" — now they feel the pain. The CTA isn't "pay to see the problem," it's "pay to make the problem go away." That's a much easier sell.

The conversion psychology is: **awareness → urgency → relief**. Gating cuts off awareness before urgency can build.

**What you can reasonably gate:**
- Priority ordering of fixes ("fix these 3 first")
- Historical audit comparison ("your score dropped 12 points since last month")
- Competitor benchmarking
- Scheduled re-audits

These are analytical features that don't block the user from understanding their problem. Gate those, not the core audit.

One exception: if your audit is *so detailed* that it's genuinely useful as a standalone product (i.e., people would pay $X/mo just for audits), then a freemium tier with limited crawl depth makes sense. But "show 3 issues free, gate the rest" for a fix-it upsell flow is the wrong gate placement.

---

## 7. Best Stripe Architecture — Single Product with Multiple Prices vs. Separate Products

**Separate Products. Here's the full breakdown:**

```
Stripe Account
├── Products (SaaS - existing)
│   ├── BoostRank Pro → Price: $19/mo
│   ├── BoostRank Business → Price: $49/mo  
│   └── BoostRank Agency → Price: $99/mo
│
└── Products (Fix It - new)
    ├── "BoostRank Fix It — One-Time Site Fix"
    │   └── Price: $149 (one-time)
    │
    └── "BoostRank SEO Pro — Managed Fix Service"
        └── Price: $99/mo (recurring)
```

Reasons to keep them separate:

1. **Dashboard clarity.** Your MRR chart for SaaS won't be polluted by Fix It revenue. You can segment by product.
2. **Different refund policies.** One-time fix has a service delivery component; SaaS is pure software. Your policies will diverge.
3. **Different webhook handling.** Already shown above — you'll be branching on metadata anyway, cleaner to also branch on product.
4. **Tax and accounting.** One-time service revenue vs. subscription SaaS revenue may be categorized differently depending on your jurisdiction. Separate products let you add Tax Codes independently.

**Could you use one product with multiple prices?** Yes, and it would work. But the only benefit is marginally fewer rows in the Stripe Products list. The downsides outweigh it.

---

## 8. UX/Conversion Tips for the Checkout Flow

These are specifically for the one-time $149 conversion since that's harder than subscription and likely your primary revenue driver initially.

**a) Show the fix list in the checkout flow.**

Before they hit Stripe, show a summary page: "We'll fix these 14 issues for $149." Concrete > abstract. "Fix My Site" alone doesn't justify $149; "fix these specific 14 problems you just learned about" does.

**b) Anchor the price against time and alternatives.**

"A freelancer charges $300–800 for this. We fix it in 48 hours for $149." Put this on the pre-checkout summary page, not inside the Stripe Checkout (you can't customize it much).

**c) Reduce form friction — pre-fill everything you can.**

```python
session = stripe.checkout.Session.create(
    customer_email=user_email,  # Pre-fill email
    # If they have a Stripe Customer already:
    customer=stripe_customer_id,  # Skips email field entirely
    ...
)
```

If they signed up for BoostRank (even free), you have their email. Use it.

**d) Use `success_url` to reinforce the purchase, not just confirm it.**

```
/fix/success?session_id={CHECKOUT_SESSION_ID}
```

On this page, verify the session server-side and show:
- Confirmation of what will be fixed (pull from your DB via audit_id)
- Timeline ("We'll start within 2 business hours")
- A way to contact you if they need to change the site URL

Don't just show "Payment successful ✓" — show "Your 14 issues will be fixed within 48 hours. Here's what we're fixing..."

**e) Add urgency without being sleazy.**

Show the audit score prominently: "Your site scores 34/100. After our fix, sites average 78/100." This makes the $149 feel like it's buying a concrete outcome, not just a service.

**f) Reduce subscription friction with a trial or guarantee.**

For the $99/mo subscription, consider:
- 7-day free trial (configurable in `subscription_data.trial_end`)
- Or "First fix included, cancel anytime" messaging

```python
subscription_data={
    "metadata": {...},
    "trial_end": int(datetime.now().timestamp()) + 7 * 86400,  # 7-day trial
}
```

**g) Post-purchase upsell.**

After the one-time fix, offer the subscription: "Want us to keep your site optimized? Set up monthly audits + fixes for $99/mo." This is a natural conversion point — they just paid $149 and experienced the value.

**h) Cart recovery.**

If someone starts checkout but doesn't complete, store the `checkout.session.id` and send a follow-up email within 24 hours. Stripe's `checkout.session.expired` webhook event fires when a session times out (default 24h) — use it as a trigger:

```python
elif event["type"] == "checkout.session.expired":
    session = event["data"]["object"]
    if session["metadata"].get("fix_type"):
        await send_cart_recovery_email(session)
```

---

## Summary of Recommendations

| Question | Recommendation |
|----------|---------------|
| Payment Links vs Checkout Sessions | **Checkout Sessions** — need metadata context |
| One-time $149 architecture | **Separate Product + one-time Price** |
| $99/mo subscription | **Separate Product + recurring Price** (not an add-on) |
| Customer Portal | **Use Portal with scoped Configuration** |
| Mixing payments & subs | **Branch on `session.mode` and `metadata.fix_type`** |
| Freemium gating | **Full free audit, upsell the fix** |
| Product architecture | **Separate Products** for SaaS vs Fix It |
| Checkout UX | **Show fix list, anchor price, pre-fill, reinforce on success** |
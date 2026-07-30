"""
BoostRank — Shopify Fix Applier
Actually pushes SEO fixes to the customer's Shopify store via API.
"""

import os
import json
import time
import httpx
import sqlite3
from typing import Optional
from pathlib import Path
from dataclasses import dataclass

DB_PATH = Path(__file__).parent.parent.parent / "data" / "boostrank_fixes.db"


def _get_db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_shopify_token(shop_domain: str) -> Optional[str]:
    """Get the access token for a connected shop."""
    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT access_token FROM shopify_stores WHERE shop_domain = ? AND is_active = 1",
            (shop_domain.strip().lower(),),
        ).fetchone()
        return row["access_token"] if row else None
    finally:
        conn.close()


@dataclass
class ApplyResult:
    """Result of applying a single fix."""
    fix_id: str
    category: str
    element: str
    status: str  # 'applied', 'failed', 'skipped'
    detail: str
    resource_id: Optional[int] = None


class ShopifyFixApplier:
    """Applies SEO fixes directly to a Shopify store via API."""

    def __init__(self, shop_domain: str, access_token: str):
        self.shop = shop_domain.strip().lower()
        self.token = access_token
        self.api_base = f"https://{self.shop}/admin/api/2024-01"
        self.headers = {
            "X-Shopify-Access-Token": self.token,
            "Content-Type": "application/json",
        }

    async def _get(self, endpoint: str, params: dict = None) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.api_base}/{endpoint}",
                headers=self.headers,
                params=params or {},
            )
            resp.raise_for_status()
            return resp.json()

    async def _put(self, endpoint: str, data: dict) -> dict:
        async with httpx.AsyncClient() as client:
            resp = await client.put(
                f"{self.api_base}/{endpoint}",
                headers=self.headers,
                json=data,
            )
            resp.raise_for_status()
            return resp.json()

    async def test_connection(self) -> dict:
        """Verify the token works and get shop info."""
        try:
            data = await self._get("shop.json")
            shop = data.get("shop", {})
            return {
                "connected": True,
                "shop_name": shop.get("name", ""),
                "domain": shop.get("domain", ""),
                "email": shop.get("email", ""),
                "plan": shop.get("plan_display_name", ""),
            }
        except Exception as e:
            return {"connected": False, "error": str(e)}

    async def fix_product_meta_description(self, product_id: int, new_description: str) -> ApplyResult:
        """Update a product's meta description via Shopify API."""
        try:
            # Shopify stores meta description in metafields or product SEO
            data = await self._put(
                f"products/{product_id}.json",
                {"product": {"id": product_id, "metafields_global_title_tag": None,
                             "metafields_global_description_tag": new_description}},
            )
            return ApplyResult(
                fix_id=f"product_{product_id}_meta_desc",
                category="meta",
                element="meta description",
                status="applied",
                detail=f"Updated product {product_id} meta description to {len(new_description)} chars",
                resource_id=product_id,
            )
        except Exception as e:
            return ApplyResult(
                fix_id=f"product_{product_id}_meta_desc",
                category="meta",
                element="meta description",
                status="failed",
                detail=str(e),
                resource_id=product_id,
            )

    async def fix_product_seo(self, product_id: int, seo_title: str = None, seo_description: str = None) -> ApplyResult:
        """Update a product's SEO title and description."""
        try:
            product_data = {"id": product_id}
            if seo_title:
                product_data["metafields_global_title_tag"] = seo_title
            if seo_description:
                product_data["metafields_global_description_tag"] = seo_description

            await self._put(f"products/{product_id}.json", {"product": product_data})
            return ApplyResult(
                fix_id=f"product_{product_id}_seo",
                category="meta",
                element="product SEO",
                status="applied",
                detail=f"Updated product {product_id} SEO (title={bool(seo_title)}, desc={bool(seo_description)})",
                resource_id=product_id,
            )
        except Exception as e:
            return ApplyResult(
                fix_id=f"product_{product_id}_seo",
                category="meta",
                element="product SEO",
                status="failed",
                detail=str(e),
                resource_id=product_id,
            )

    async def fix_theme_liquid(self, theme_id: int, asset_key: str, new_content: str) -> ApplyResult:
        """Update a theme liquid file (for schema, OG tags, etc.)."""
        try:
            await self._put(
                f"themes/{theme_id}/assets.json",
                {"asset": {"key": asset_key, "value": new_content}},
            )
            return ApplyResult(
                fix_id=f"theme_{theme_id}_{asset_key}",
                category="theme",
                element=asset_key,
                status="applied",
                detail=f"Updated theme asset {asset_key}",
                resource_id=theme_id,
            )
        except Exception as e:
            return ApplyResult(
                fix_id=f"theme_{theme_id}_{asset_key}",
                category="theme",
                element=asset_key,
                status="failed",
                detail=str(e),
                resource_id=theme_id,
            )

    async def add_website_schema(self, schema_json: str) -> ApplyResult:
        """Add WebSite JSON-LD schema to the store's theme."""
        try:
            # Get the main theme
            themes = await self._get("themes.json")
            main_theme = None
            for t in themes.get("themes", []):
                if t.get("role") == "main":
                    main_theme = t
                    break

            if not main_theme:
                return ApplyResult(
                    fix_id="schema_website",
                    category="schema",
                    element="WebSite JSON-LD",
                    status="failed",
                    detail="No main theme found",
                )

            theme_id = main_theme["id"]

            # Get current theme.liquid content
            asset = await self._get(f"themes/{theme_id}/assets.json", {"asset[key]": "layout/theme.liquid"})
            current_content = asset.get("asset", {}).get("value", "")

            # Inject schema into <head> (before closing </head>)
            schema_tag = f'\n<script type="application/ld+json">\n{schema_json}\n</script>\n'

            if "application/ld+json" in current_content and "WebSite" in current_content:
                return ApplyResult(
                    fix_id="schema_website",
                    category="schema",
                    element="WebSite JSON-LD",
                    status="skipped",
                    detail="WebSite schema already exists in theme.liquid",
                    resource_id=theme_id,
                )

            # Insert before </head>
            if "</head>" in current_content:
                new_content = current_content.replace("</head>", f"{schema_tag}</head>", 1)
            else:
                new_content = current_content + schema_tag

            return await self.fix_theme_liquid(theme_id, "layout/theme.liquid", new_content)

        except Exception as e:
            return ApplyResult(
                fix_id="schema_website",
                category="schema",
                element="WebSite JSON-LD",
                status="failed",
                detail=str(e),
            )

    async def fix_og_tags(self, og_title: str = None, og_description: str = None, og_image: str = None) -> ApplyResult:
        """Add or fix OG tags in theme.liquid."""
        try:
            themes = await self._get("themes.json")
            main_theme = next((t for t in themes.get("themes", []) if t.get("role") == "main"), None)

            if not main_theme:
                return ApplyResult(
                    fix_id="og_tags",
                    category="meta",
                    element="OG tags",
                    status="failed",
                    detail="No main theme found",
                )

            theme_id = main_theme["id"]
            asset = await self._get(f"themes/{theme_id}/assets.json", {"asset[key]": "layout/theme.liquid"})
            current_content = asset.get("asset", {}).get("value", "")

            new_content = current_content
            changes = []

            # Add OG tags before </head>
            og_tags = []
            if og_title and 'property="og:title"' not in current_content:
                og_tags.append(f'<meta property="og:title" content="{og_title}">')
                changes.append("og:title")
            if og_description and 'property="og:description"' not in current_content:
                og_tags.append(f'<meta property="og:description" content="{og_description}">')
                changes.append("og:description")
            if og_image and 'property="og:image"' not in current_content:
                og_tags.append(f'<meta property="og:image" content="{og_image}">')
                changes.append("og:image")

            if not og_tags:
                return ApplyResult(
                    fix_id="og_tags",
                    category="meta",
                    element="OG tags",
                    status="skipped",
                    detail="OG tags already present",
                    resource_id=theme_id,
                )

            tags_html = "\n" + "\n".join(og_tags) + "\n"
            if "</head>" in new_content:
                new_content = new_content.replace("</head>", f"{tags_html}</head>", 1)
            else:
                new_content += tags_html

            result = await self.fix_theme_liquid(theme_id, "layout/theme.liquid", new_content)
            if result.status == "applied":
                result.detail = f"Added OG tags: {', '.join(changes)}"
            return result

        except Exception as e:
            return ApplyResult(
                fix_id="og_tags",
                category="meta",
                element="OG tags",
                status="failed",
                detail=str(e),
            )

    async def apply_fixes(self, fixes: list, url: str = None) -> list:
        """Apply a batch of fixes to the store. Returns list of ApplyResult."""
        results = []

        for fix in fixes:
            category = fix.get("category", "")
            element = fix.get("element", "")
            fix_code = fix.get("fix_code", "")
            after_value = fix.get("after_value", "")

            if category == "schema" and "WebSite" in element:
                result = await self.add_website_schema(fix_code)
            elif category == "meta" and "og:" in element.lower():
                result = await self.fix_og_tags(og_description=after_value)
            elif category == "meta" and "meta description" in element.lower():
                # Try to find the right product/page to update
                # For homepage meta description, update the theme
                result = await self._fix_homepage_meta_description(after_value)
            else:
                result = ApplyResult(
                    fix_id=f"fix_{category}_{element}",
                    category=category,
                    element=element,
                    status="skipped",
                    detail=f"Auto-fix not yet supported for {category}/{element}",
                )

            results.append(result)

        return results

    async def _fix_homepage_meta_description(self, new_description: str) -> ApplyResult:
        """Fix the homepage meta description via theme.liquid."""
        try:
            themes = await self._get("themes.json")
            main_theme = next((t for t in themes.get("themes", []) if t.get("role") == "main"), None)

            if not main_theme:
                return ApplyResult(
                    fix_id="homepage_meta_desc",
                    category="meta",
                    element="meta description",
                    status="failed",
                    detail="No main theme found",
                )

            theme_id = main_theme["id"]
            asset = await self._get(f"themes/{theme_id}/assets.json", {"asset[key]": "layout/theme.liquid"})
            current_content = asset.get("asset", {}).get("value", "")

            # Check if there's already a meta description
            if 'name="description"' in current_content:
                # Replace existing
                import re
                new_content = re.sub(
                    r'<meta\s+name="description"\s+content="[^"]*"',
                    f'<meta name="description" content="{new_description}"',
                    current_content,
                )
            else:
                # Add new one before </head>
                meta_tag = f'\n<meta name="description" content="{new_description}">\n'
                new_content = current_content.replace("</head>", f"{meta_tag}</head>", 1)

            return await self.fix_theme_liquid(theme_id, "layout/theme.liquid", new_content)

        except Exception as e:
            return ApplyResult(
                fix_id="homepage_meta_desc",
                category="meta",
                element="meta description",
                status="failed",
                detail=str(e),
            )
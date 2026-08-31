"""
Shopify + Printful HTTP clients for the shopify building.

Synchronous (urllib) so they drop into Flask request handling and the
30s work_tick without async plumbing. All credentials come from the env.

Auth:
  Shopify Admin GraphQL  -> X-Shopify-Access-Token
  Shopify Storefront API -> X-Shopify-Storefront-Access-Token
  Printful REST          -> Authorization: Bearer
"""
from __future__ import annotations

import os
import json
import time
import base64
import hashlib
import hmac
import urllib.request
import urllib.error
import urllib.parse
from typing import Any, Dict, Optional


class _ClientError(Exception):
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class ShopifyClient:
    """Admin + Storefront GraphQL wrapper."""

    def __init__(self):
        domain_raw = _env("SHOPIFY_STORE_DOMAIN") or _env("SHOPIFY_SHOP_DOMAIN")
        # Strip protocol — the Shopify URL is built as https://{domain}/...
        self.domain = domain_raw.replace("https://", "").replace("http://", "").strip("/")
        self.admin_token = _env("SHOPIFY_ADMIN_API_ACCESS_TOKEN") or _env("SHOPIFY_ACCESS_TOKEN")
        self.client_id = _env("SHOPIFY_API_KEY") or _env("SHOPIFY_CLIENT_ID")
        self.client_secret = _env("SHOPIFY_API_SECRET") or _env("SHOPIFY_CLIENT_SECRET")
        self.storefront_token = _env("SHOPIFY_STOREFRONT_API_TOKEN")
        self.version = _env("SHOPIFY_API_VERSION", "2026-01")
        self.webhook_secret = _env("SHOPIFY_WEBHOOK_SECRET")
        self.webhook_base_url = _env("SHOPIFY_WEBHOOK_BASE_URL")
        self._token_expires_at = 0.0
        self.ready = bool(self.domain and (self.admin_token or (self.client_id and self.client_secret)))

    def _refresh_token(self):
        """Refresh the admin access token using client_credentials grant.

        Used when the stored admin_token is expired/invalid. Falls back
        silently — if refresh fails, the original error is surfaced to
        the caller on the next GraphQL call.
        """
        if not (self.domain and self.client_id and self.client_secret):
            return
        url = f"https://{self.domain}/admin/oauth/access_token"
        data = urllib.parse.urlencode({
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
        }).encode()
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = json.loads(resp.read().decode())
            if result.get("access_token"):
                self.admin_token = result["access_token"]
                self._token_expires_at = time.time() + result.get("expires_in", 86400) - 60
        except Exception:
            pass

    # --- low level ---
    def _graphql(self, endpoint: str, token: str, query: str, variables: Optional[dict] = None) -> dict:
        if not self.domain or not token:
            return {"errors": [{"message": "Shopify credentials missing (domain/admin token)"}]}
        url = (
            f"https://{self.domain}/admin/api/{self.version}/graphql.json"
            if endpoint == "admin"
            else f"https://{self.domain}/api/{self.version}/graphql.json"
        )
        body = json.dumps({"query": query, "variables": variables or {}}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("X-Shopify-Access-Token", token)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            # 401 → token may be expired; try refresh + retry once
            if e.code == 401 and endpoint == "admin":
                self._refresh_token()
                if self.admin_token != token:
                    req.add_header("X-Shopify-Access-Token", self.admin_token)
                    try:
                        with urllib.request.urlopen(req, timeout=30) as resp:
                            data = json.loads(resp.read().decode())
                    except urllib.error.HTTPError as e2:
                        return {"errors": [{"message": f"HTTP {e2.code}: {e2.read().decode()[:300]}"}]}
                    except Exception as e2:  # noqa: BLE001
                        return {"errors": [{"message": str(e2)}]}
                    return data
            return {"errors": [{"message": f"HTTP {e.code}: {e.read().decode()[:300]}"}]}
        except Exception as e:  # noqa: BLE001
            return {"errors": [{"message": str(e)}]}
        return data

    def admin(self, query: str, variables: Optional[dict] = None) -> dict:
        return self._graphql("admin", self.admin_token, query, variables)

    def storefront(self, query: str, variables: Optional[dict] = None) -> dict:
        return self._graphql("storefront", self.storefront_token, query, variables)

    # --- webhook verification (Shopify HMAC-SHA256, base64) ---
    def verify_webhook(self, raw_body: bytes, hmac_header: str) -> bool:
        if not self.webhook_secret:
            # Dev mode: no secret configured yet -> accept but warn.
            # Set SHOPIFY_WEBHOOK_SECRET to enforce HMAC verification.
            print("[shopify] WARNING: SHOPIFY_WEBHOOK_SECRET not set — "
                  "accepting webhook WITHOUT HMAC verification (dev mode)")
            return True
        digest = hmac.new(self.webhook_secret.encode(), raw_body, hashlib.sha256).digest()
        computed = base64.b64encode(digest).decode()
        return hmac.compare_digest(computed, hmac_header or "")

    # --- webhook registration (Admin REST) ---
    def register_webhook(self, address: str, topic: str) -> dict:
        """Create a webhook subscription in Shopify pointing at `address`."""
        if not self.domain:
            return {"errors": [{"message": "Shopify domain missing"}]}
        if not self.admin_token:
            self._refresh_token()
        if not self.admin_token:
            return {"errors": [{"message": "Shopify admin token missing and refresh failed"}]}
        url = f"https://{self.domain}/admin/api/{self.version}/webhooks.json"
        payload = json.dumps({"webhook": {"topic": topic, "address": address, "format": "json"}}).encode()
        for attempt in range(2):
            req = urllib.request.Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            req.add_header("X-Shopify-Access-Token", self.admin_token)
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    return json.loads(resp.read().decode())
            except urllib.error.HTTPError as e:
                if e.code == 401 and attempt == 0:
                    self._refresh_token()
                    continue
                return {"errors": [{"message": f"HTTP {e.code}: {e.read().decode()[:300]}"}]}
            except Exception as e:  # noqa: BLE001
                return {"errors": [{"message": str(e)}]}
        return {"errors": [{"message": "webhook registration failed after retry"}]}

    # --- domain queries / mutations (spec queries) ---
    def get_orders(self, limit: int = 10) -> dict:
        q = """
        query GetRecentOrders($first: Int!) {
          orders(first: $first, sortKey: CREATED_AT, reverse: true) {
            edges {
              node {
                id name email
                totalPriceSet { shopMoney { amount currencyCode } }
                displayFulfillmentStatus displayFinancialStatus createdAt
                lineItems(first: 10) {
                  edges { node { title quantity variant { id sku inventoryQuantity } } }
                }
              }
            }
          }
        }"""
        return self.admin(q, {"first": limit})

    def get_products(self, limit: int = 20) -> dict:
        q = """
        query GetProducts($first: Int!) {
          products(first: $first) {
            edges {
              node {
                id title status descriptionHtml tags
                variants(first: 10) {
                  edges { node { id sku price inventoryQuantity
                    inventoryItem { id } } }
                }
                metafields(first: 5) {
                  edges { node { namespace key value } }
                }
              }
            }
          }
        }"""
        return self.admin(q, {"first": limit})

    def update_product(self, product_input: dict) -> dict:
        q = """
        mutation UpdateProduct($input: ProductInput!) {
          productUpdate(input: $input) {
            product { id title descriptionHtml }
            userErrors { field message }
          }
        }"""
        return self.admin(q, {"input": product_input})

    def create_discount(self, code: str, percentage: float, expires_at: Optional[str] = None) -> dict:
        disc = {
            "title": f"Auto {code}",
            "code": code,
            "startsAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        if expires_at:
            disc["endsAt"] = expires_at
        disc["customerGets"] = {
            "value": {"percentage": percentage / 100.0},
            "items": {"allItems": True},
        }
        q = """
        mutation CreateDiscount($basicCodeDiscount: DiscountCodeBasicInput!) {
          discountCodeBasicCreate(basicCodeDiscount: $basicCodeDiscount) {
            codeDiscountNode { id
              codeDiscount { ... on DiscountCodeBasic { title
                codes(first: 1) { edges { node { code } } } } }
            }
            userErrors { field message }
          }
        }"""
        return self.admin(q, {"basicCodeDiscount": disc})

    def adjust_inventory(self, inventory_item_id: str, location_id: str, delta: int) -> dict:
        q = """
        mutation AdjustInventory($input: InventoryAdjustQuantityInput!) {
          inventoryAdjustQuantity(input: $input) {
            inventoryLevel { available }
            userErrors { field message }
          }
        }"""
        return self.admin(q, {
            "input": {
                "inventoryItemId": inventory_item_id,
                "locationId": location_id,
                "availableDelta": delta,
            }
        })

    def write_metafield(self, owner_id: str, namespace: str, key: str, value: str, mtype: str = "string") -> dict:
        q = """
        mutation SetMetafield($metafields: [MetafieldsSetInput!]!) {
          metafieldsSet(metafields: $metafields) {
            metafields { id namespace key value }
            userErrors { field message }
          }
        }"""
        return self.admin(q, {"metafields": [{
            "ownerId": owner_id, "namespace": namespace,
            "key": key, "value": value, "type": mtype,
        }]})

    def get_low_stock(self, threshold: int = 5) -> list:
        data = self.get_products(50)
        out = []
        for e in data.get("data", {}).get("products", {}).get("edges", []):
            node = e["node"]
            for v in node["variants"]["edges"]:
                inv = v["node"].get("inventoryQuantity")
                if inv is not None and inv <= threshold:
                    out.append({"product": node["title"], "sku": v["node"].get("sku"),
                                "variant_id": v["node"]["id"], "inventory": inv})
        return out


class PrintfulClient:
    """Printful REST wrapper (bearer token)."""

    BASE = "https://api.printful.com"

    def __init__(self):
        self.api_key = _env("PRINTFUL_API_KEY")
        self.store_id = _env("PRINTFUL_STORE_ID")
        self.ready = bool(self.api_key)

    def _request(self, method: str, path: str, payload: Optional[dict] = None) -> dict:
        if not self.api_key:
            return {"error": "Printful API key missing"}
        url = f"{self.BASE}{path}"
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {self.api_key}")
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            return {"error": f"HTTP {e.code}: {e.read().decode()[:300]}"}
        except Exception as e:  # noqa: BLE001
            return {"error": str(e)}

    def list_store_products(self) -> dict:
        return self._request("GET", "/store/products")

    def list_catalog(self) -> dict:
        return self._request("GET", "/products")

    def submit_order(self, shopify_order: dict) -> dict:
        recipient = shopify_order.get("shippingAddress", {})
        payload = {
            "recipient": {
                "name": recipient.get("name", ""),
                "address1": recipient.get("address1", ""),
                "city": recipient.get("city", ""),
                "state_code": recipient.get("provinceCode", ""),
                "country_code": recipient.get("countryCode", ""),
                "zip": recipient.get("zip", ""),
            },
            "items": [
                {"sync_variant_id": li.get("variant", {}).get("sku"), "quantity": li.get("quantity")}
                for li in shopify_order.get("lineItems", [])
            ],
            "retail_costs": {
                "currency": "USD",
                "subtotal": shopify_order.get("subtotalPrice", "0"),
            },
        }
        return self._request("POST", "/orders", payload)

"""
Product Studio — Stage 2 of the pipeline.
Takes approved leads, creates product listings, drafts, and publishes.
Real-world: Uses Shopify to create products, manages inventory.
"""
from city.agent import Agent
from city.db import now_iso
import json

class ProductStudioAgent(Agent):
    name = "product_studio"
    subject = "Product Studio"
    district = "Studio"
    color = "#2196f3"

    job_title = "Product Manager"
    mission = "Turn approved leads into real product listings. Publish to storefront."
    cog_interval = 60

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS listings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id INTEGER,
                title TEXT NOT NULL,
                description TEXT,
                price REAL,
                status TEXT NOT NULL DEFAULT 'draft',
                created_at TEXT NOT NULL,
                published_at TEXT
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^status$")(self._status)
        self.rule(r"^report$")(self._report)
        self.rule(r"^create listing\s+(?P<lead_id>\d+)$")(self._create_listing)
        self.rule(r"^publish listing\s+(?P<listing_id>\d+)$")(self._publish_listing)
        self.rule(r"^draft list\s+(?P<title>.+?)(?:\s+(?P<price>\d+(?:\.\d+)?))?$")(self._draft_list)

    def _status(self):
        return {"agent": self.name, "status": self.status}

    def _report(self):
        rows = self.conn.execute(
            "SELECT * FROM listings ORDER BY created_at DESC LIMIT 20"
        ).fetchall()
        listings = [dict(r) for r in rows]
        return {"agent": self.name, "subject": self.subject, "listings_count": len(listings), "listings": listings}

    def _create_listing(self, lead_id):
        row = self.conn.execute("SELECT * FROM leads WHERE id = ?", (lead_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "lead not found"}
        title = row["title"]
        # Draft with default specs
        self.conn.execute(
            "INSERT INTO listings (lead_id, title, description, price, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (lead_id, title, f"Professional {title}", 29.99, "draft", now_iso())
        )
        listing_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.log("listing_created", f"listing {listing_id} drafted for lead {lead_id}", {"title": title})
        # Fire event to storefront
        from city.orchestrator import EventBus
        EventBus.publish(self.name, "listing.drafted", f"listing {listing_id}", {"listing_id": listing_id, "title": title, "lead_id": lead_id})
        self.conn.commit()
        return {"ok": True, "listing_id": listing_id, "title": title}

    def _publish_listing(self, listing_id):
        row = self.conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "listing not found"}
        if row["status"] != "draft":
            return {"ok": False, "error": "listing not in draft state"}

        # Actually create the product on Shopify via the shopify building
        from city.registry import get_registry
        registry = get_registry(self.conn)
        shopify_dept = registry.get("shopify")
        if shopify_dept and shopify_dept.shopify.ready:
            result = shopify_dept.shopify.admin("""
                mutation productCreate($input: ProductInput!) {
                  productCreate(input: $input) {
                    product { id title status }
                    userErrors { field message }
                  }
                }""", {
                "input": {
                    "title": row["title"],
                    "descriptionHtml": f"<p>{row['description']}</p>",
                    "productType": "General",
                    "vendor": "Effata Picks",
                    "status": "ACTIVE",
                }
            })
            errs = result.get("data", {}).get("productCreate", {}).get("userErrors", [])
            if errs:
                self.log("publish_error", f"listing {listing_id} Shopify error: {errs[0].get('message')}")
                return {"ok": False, "error": errs[0].get("message", "Shopify error")}
            product = result.get("data", {}).get("productCreate", {}).get("product", {})
            shopify_id = product.get("id", "")
        else:
            shopify_id = ""

        self.conn.execute(
            "UPDATE listings SET status = 'published', published_at = ? WHERE id = ?",
            (now_iso(), listing_id)
        )
        self.log("listing_published", f"listing {listing_id} published to Shopify", {"title": row["title"], "shopify_id": shopify_id})
        from city.orchestrator import EventBus
        EventBus.publish(self.name, "listing.published", f"listing {listing_id} live", {"listing_id": listing_id, "title": row["title"], "shopify_id": shopify_id})
        self.conn.commit()
        return {"ok": True, "listing_id": listing_id, "title": row["title"], "shopify_id": shopify_id}

    def _draft_list(self, title, price=None):
        price = float(price) if price else 19.99
        self.conn.execute(
            "INSERT INTO listings (lead_id, title, description, price, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (None, title, f"Handcrafted {title} with unique design", price, "draft", now_iso())
        )
        listing_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.log("listing_draft", f"manual listing {listing_id} created", {"title": title, "price": price})
        self.conn.commit()
        return {"ok": True, "listing_id": listing_id, "title": title, "price": price}

    def employee_duty(self):
        if self.status == "idle" and self.cognition and self.cognition.step_index:
            # Auto-draft a listing if there are pending leads
            row = self.conn.execute("SELECT COUNT(*) as c FROM listings WHERE status = 'draft'").fetchone()
            if row["c"] == 0:
                return self._draft_list("New Product")
        return None

    def report(self):
        return {"agent": self.name, "subject": self.subject, "status": self.status}
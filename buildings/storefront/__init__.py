"""
Storefront — Stage 3 of the pipeline.
Publishes listings, processes real orders, manages inventory, interacts with customers.
Real-world: The live Shopify store front-end, handling cart, checkout, fulfillment.
"""
from city.agent import Agent
from city.db import now_iso, log_event
import json

class StorefrontAgent(Agent):
    name = "storefront"
    subject = "Storefront"
    district = "Commerce"
    color = "#4caf50"

    job_title = "Store Manager"
    mission = "Run the live store: publish, sell, fulfill, track revenue."
    cog_interval = 90

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                listing_id INTEGER,
                customer TEXT,
                amount REAL NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL,
                fulfilled_at TEXT
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL,
                name TEXT,
                created_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^status$")(self._status)
        self.rule(r"^report$")(self._report)
        self.rule(r"^place order\s+(?P<listing_id>\d+)$")(self._place_order)
        self.rule(r"^fulfill order\s+(?P<order_id>\d+)$")(self._fulfill_order)
        self.rule(r"^add customer\s+(?P<email>.+?)(?:\s+(?P<name>.+?))?$")(self._add_customer)
        self.rule(r"^order history(?:\s+(?P<limit>\d+))?")(self._order_history)

    def _status(self):
        return {"agent": self.name, "status": self.status}

    def _report(self):
        rows = self.conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT 30"
        ).fetchall()
        orders = [dict(r) for r in rows]
        total_rev = sum(o["amount"] for o in orders)
        return {"agent": self.name, "subject": self.subject, "orders_count": len(orders), "total_revenue": total_rev, "orders": orders}

    def _place_order(self, listing_id):
        row = self.conn.execute("SELECT * FROM listings WHERE id = ?", (listing_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "listing not found"}
        if row["status"] != "published":
            return {"ok": False, "error": "listing not published"}
        # Create order
        self.conn.execute(
            "INSERT INTO orders (listing_id, customer, amount, status, created_at) VALUES (?, ?, ?, ?, ?)",
            (listing_id, "Customer", row["price"], row["price"], now_iso())
        )
        order_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.log("order_created", f"order {order_id} for listing {listing_id}", {"listing_id": listing_id, "amount": row["price"]})
        # Fire event to treasury for real money movement
        from city.orchestrator import EventBus
        EventBus.publish(self.name, "shopify.order_paid", f"order {order_id}", {"order_id": order_id, "listing_id": listing_id, "amount": row["price"]})
        self.conn.commit()
        return {"ok": True, "order_id": order_id, "amount": row["price"]}

    def _fulfill_order(self, order_id):
        row = self.conn.execute("SELECT * FROM orders WHERE id = ?", (order_id,)).fetchone()
        if not row:
            return {"ok": False, "error": "order not found"}
        if row["status"] != "pending":
            return {"ok": False, "error": "order not pending"}
        # Mark as fulfilled and update inventory
        self.conn.execute(
            "UPDATE orders SET status = 'fulfilled', fulfilled_at = ? WHERE id = ?",
            (now_iso(), order_id)
        )
        self.log("order_fulfilled", f"order {order_id} fulfilled", {"amount": row["amount"]})
        self.conn.commit()
        return {"ok": True, "order_id": order_id}

    def _add_customer(self, email, name=None):
        self.conn.execute(
            "INSERT INTO customers (email, name, created_at) VALUES (?, ?, ?)",
            (email, name, now_iso())
        )
        customer_id = self.conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        self.log("customer_added", f"customer {customer_id}: {email}", {"email": email, "name": name})
        self.conn.commit()
        return {"ok": True, "customer_id": customer_id}

    def _order_history(self, limit=None):
        limit = int(limit) if limit else 20
        rows = self.conn.execute(
            "SELECT * FROM orders ORDER BY created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        orders = [dict(r) for r in rows]
        return {"orders": orders}

    def employee_duty(self):
        if self.status == "idle" and self.cognitive.step_index:
            # Auto-fulfill pending orders (simulate)
            rows = self.conn.execute(
                "SELECT id FROM orders WHERE status = 'pending' LIMIT 3"
            ).fetchall()
            if rows:
                for r in rows:
                    self._fulfill_order(r["id"])
                return {"auto_fulfilled": len(rows)}
        return None

    def report(self):
        return {"agent": self.name, "subject": self.subject, "status": self.status}
"""
Shopify Store Department — Internal component of Commerce Building.
Handles orders, revenue/profit tracking, top products.
"""
from city.department import Department
from city.db import now_iso


class ShopifyStoreDepartment(Department):
    name = "shopify"
    subject = "Shopify Store Dept"
    district = "Commerce Row"
    color = "#95bf47"

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS shopify_orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                product TEXT NOT NULL,
                revenue REAL NOT NULL,
                cost REAL NOT NULL DEFAULT 0,
                source TEXT NOT NULL DEFAULT 'pod',
                placed_at TEXT NOT NULL
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^order\s+(?P<product>.+?)\s+revenue\s+(?P<revenue>[\d.]+)\s+cost\s+(?P<cost>[\d.]+)\s+(?P<source>pod|dropship)$")(self._order)
        self.rule(r"^revenue$")(self._revenue)
        self.rule(r"^top products$")(self._top_products)
        self.rule(r"^status$")(self._status)

    def _order(self, product, revenue, cost, source):
        self.conn.execute(
            "INSERT INTO shopify_orders (product, revenue, cost, source, placed_at) VALUES (?, ?, ?, ?, ?)",
            (product, float(revenue), float(cost), source, now_iso()),
        )
        self.conn.commit()
        return {"action": "order recorded", "product": product, "revenue": float(revenue), "source": source}

    def _revenue(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(revenue),0) AS rev, COALESCE(SUM(cost),0) AS cost FROM shopify_orders"
        ).fetchone()
        return {
            "orders": row["n"],
            "total_revenue_usd": round(row["rev"], 2),
            "total_cost_usd": round(row["cost"], 2),
            "profit_usd": round(row["rev"] - row["cost"], 2),
        }

    def _top_products(self):
        rows = self.conn.execute(
            "SELECT product, SUM(revenue) AS rev, COUNT(*) AS n FROM shopify_orders GROUP BY product ORDER BY rev DESC LIMIT 5"
        ).fetchall()
        return {"top_products": [dict(r) for r in rows]}

    def _status(self):
        return self.report()

    def work(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(revenue),0) AS rev FROM shopify_orders"
        ).fetchone()
        if row["n"] == 0:
            return
        self.log("tick", f"{row['n']} orders, ${row['rev']:.0f} revenue")

    def report(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS n, COALESCE(SUM(revenue),0) AS rev, COALESCE(SUM(cost),0) AS cost FROM shopify_orders"
        ).fetchone()
        return {
            "department": self.name,
            "subject": self.subject,
            "orders": row["n"],
            "revenue": round(row["rev"], 2),
            "profit": round(row["rev"] - row["cost"], 2),
        }
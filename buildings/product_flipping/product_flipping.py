"""
Product Flipping Department — Internal component of Commerce Building.
Handles inventory sourcing, listing, selling, margin tracking.
"""
from city.department import Department
from city.db import now_iso


class ProductFlippingDepartment(Department):
    name = "product_flipping"
    subject = "Product Flipping Dept"
    district = "Warehouse District"
    color = "#8d6e63"

    def setup_schema(self):
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS flip_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item TEXT NOT NULL,
                cost REAL NOT NULL,
                target_price REAL,
                sale_price REAL,
                status TEXT NOT NULL DEFAULT 'sourced',
                sourced_at TEXT NOT NULL,
                sold_at TEXT
            )
        """)
        self.conn.commit()

    def register_rules(self):
        self.rule(r"^source\s+(?P<item>.+?)\s+cost\s+(?P<cost>[\d.]+)$")(self._source)
        self.rule(r"^list\s+(?P<item>.+?)\s+target\s+(?P<target>[\d.]+)$")(self._list)
        self.rule(r"^sold\s+(?P<item>.+?)\s+for\s+(?P<price>[\d.]+)$")(self._sold)
        self.rule(r"^inventory$")(self._inventory)
        self.rule(r"^margins$")(self._margins)
        self.rule(r"^status$")(self._status)

    def _source(self, item, cost):
        self.conn.execute(
            "INSERT INTO flip_items (item, cost, sourced_at) VALUES (?, ?, ?)",
            (item, float(cost), now_iso()),
        )
        self.conn.commit()
        return {"action": "sourced", "item": item, "cost": float(cost)}

    def _list(self, item, target):
        cur = self.conn.execute(
            "UPDATE flip_items SET status='listed', target_price=? WHERE item=? AND status='sourced'",
            (float(target), item),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            return {"error": f"no sourced item matching '{item}'"}
        return {"action": "listed", "item": item, "target_price": float(target)}

    def _sold(self, item, price):
        cur = self.conn.execute(
            "UPDATE flip_items SET status='sold', sale_price=?, sold_at=? WHERE item=? AND status IN ('sourced','listed')",
            (float(price), now_iso(), item),
        )
        self.conn.commit()
        if cur.rowcount == 0:
            return {"error": f"no open item matching '{item}'"}
        return {"action": "sold", "item": item, "sale_price": float(price)}

    def _inventory(self):
        rows = self.conn.execute("SELECT * FROM flip_items WHERE status != 'sold'").fetchall()
        return {"open_inventory": [dict(r) for r in rows], "count": len(rows)}

    def _margins(self):
        rows = self.conn.execute("SELECT * FROM flip_items WHERE status='sold'").fetchall()
        total_margin = sum((r["sale_price"] or 0) - r["cost"] for r in rows)
        return {"sold_count": len(rows), "total_margin_usd": round(total_margin, 2)}

    def _status(self):
        return self.report()

    def work(self):
        sold = self.conn.execute("SELECT COUNT(*) AS n FROM flip_items WHERE status='sold'").fetchone()["n"]
        open_n = self.conn.execute("SELECT COUNT(*) AS n FROM flip_items WHERE status != 'sold'").fetchone()["n"]
        self.log("tick", f"{open_n} open, {sold} sold")

    def report(self):
        sold = self.conn.execute("SELECT * FROM flip_items WHERE status='sold'").fetchall()
        open_items = self.conn.execute("SELECT * FROM flip_items WHERE status != 'sold'").fetchall()
        margin = sum((r["sale_price"] or 0) - r["cost"] for r in sold)
        return {
            "department": self.name,
            "subject": self.subject,
            "open_inventory": len(open_items),
            "sold_items": len(sold),
            "total_margin_usd": round(margin, 2),
        }
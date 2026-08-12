"""
BTC Building -- core persistence layer for all wallet artifacts.

Reads Electrum wallets, private key files, seed phrases, and UTXO data
into the Virtual City SQLite schema.
"""
from city.db import now_iso


class WalletStore:
    """Unified persistence for addresses, keys, seeds, and UTXOs."""

    def __init__(self, conn):
        self.conn = conn

    def install_schema(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS btc_addresses (
                address TEXT PRIMARY KEY,
                pubkey TEXT,
                addr_type TEXT NOT NULL DEFAULT 'p2pkh',
                wallet_source TEXT,
                label TEXT DEFAULT '',
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS btc_private_keys (
                address TEXT PRIMARY KEY,
                wif TEXT,
                hex_priv TEXT,
                source_file TEXT,
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS btc_seeds (
                seed TEXT NOT NULL,
                source_file TEXT,
                imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS btc_utxos (
                txid TEXT NOT NULL,
                vout INTEGER NOT NULL,
                address TEXT NOT NULL,
                value_sat BIGINT NOT NULL,
                confirmed INTEGER NOT NULL DEFAULT 0,
                first_seen TEXT NOT NULL,
                spent_at TEXT,
                PRIMARY KEY (txid, vout)
            );
            CREATE TABLE IF NOT EXISTS btc_sweep_state (
                txid TEXT NOT NULL,
                vout INTEGER NOT NULL,
                address TEXT NOT NULL,
                sweep_status TEXT NOT NULL DEFAULT 'pending',
                target_address TEXT,
                txid_sweep TEXT,
                swept_at TEXT,
                error TEXT,
                PRIMARY KEY (txid, vout)
            );
            CREATE INDEX IF NOT EXISTS idx_utxo_addr ON btc_utxos(address);
            CREATE INDEX IF NOT EXISTS idx_utxo_conf ON btc_utxos(confirmed);
            CREATE INDEX IF NOT EXISTS idx_sweep_st ON btc_sweep_state(sweep_status);
        """)
        self.conn.commit()

    # -- Queries --

    def get_addresses(self):
        rows = self.conn.execute(
            "SELECT address FROM btc_addresses ORDER BY imported_at"
        ).fetchall()
        return [r["address"] for r in rows]

    def total_balance(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(value_sat), 0) AS bal "
            "FROM btc_utxos WHERE spent_at IS NULL AND confirmed = 1"
        ).fetchone()
        return row["bal"] if row else 0

    def unconfirmed_balance(self):
        row = self.conn.execute(
            "SELECT COALESCE(SUM(value_sat), 0) AS bal "
            "FROM btc_utxos WHERE spent_at IS NULL AND confirmed = 0"
        ).fetchone()
        return row["bal"] if row else 0

    def count_utxos(self):
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM btc_utxos WHERE spent_at IS NULL"
        ).fetchone()
        return row["c"] if row else 0

    def wallet_summary(self):
        a = self.conn.execute("SELECT COUNT(*) AS c FROM btc_addresses").fetchone()["c"]
        k = self.conn.execute("SELECT COUNT(*) AS c FROM btc_private_keys").fetchone()["c"]
        s = self.conn.execute("SELECT COUNT(*) AS c FROM btc_seeds").fetchone()["c"]
        u = self.count_utxos()
        return {
            "addresses": a,
            "private_keys": k,
            "seeds": s,
            "utxos": u,
            "confirmed_btc": self.total_balance() / 1e8,
            "mempool_btc": self.unconfirmed_balance() / 1e8,
            "total_btc": (self.total_balance() + self.unconfirmed_balance()) / 1e8,
        }

    def upsert_utxo(self, txid, vout, address, value, confirmed=0):
        try:
            self.conn.execute(
                """INSERT OR IGNORE INTO btc_utxos
                   (txid, vout, address, value_sat, confirmed, first_seen)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (txid, vout, address, int(value), confirmed, now_iso()),
            )
            self.conn.commit()
            return self.conn.total_changes > 0
        except Exception:
            return False
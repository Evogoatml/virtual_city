#!/usr/bin/env python3
"""
BTC Wallet Recovery Bot v2 - Ubuntu
Persistent SQLite key database. Cross-matches keys across all files.

PIPELINE: INGEST -> DERIVE -> CROSS-MATCH -> SCAN -> REPORT

USAGE:
  pip install base58 ecdsa bech32 bip_utils requests

  python3 btc_recovery_bot_v2.py --ingest ~/btc        # ingest folder
  python3 btc_recovery_bot_v2.py --file wallet_21.txt  # single file
  python3 btc_recovery_bot_v2.py --status              # show DB
  python3 btc_recovery_bot_v2.py --scan                # scan blockchain
  python3 btc_recovery_bot_v2.py --report              # show results
  python3 btc_recovery_bot_v2.py --export              # export spendable
  python3 btc_recovery_bot_v2.py --ingest ~/btc --scan --report  # full run
"""

import os, sys, re, json, csv, gzip, zlib, time, hashlib, sqlite3, argparse
from datetime import datetime
from pathlib import Path

# ── auto-install ──────────────────────────────────────────────────────────
def _install(pkg):
    os.system(f"pip install {pkg} --break-system-packages -q")

try:    import base58
except: _install("base58"); import base58

try:    import ecdsa
except: _install("ecdsa"); import ecdsa

try:    import bech32
except: _install("bech32"); import bech32

try:    import requests
except: _install("requests"); import requests

try:
    from bip_utils import Bip39SeedGenerator, Bip32Slip10Secp256k1
    HAS_BIP = True
except:
    _install("bip_utils")
    try:
        from bip_utils import Bip39SeedGenerator, Bip32Slip10Secp256k1
        HAS_BIP = True
    except:
        HAS_BIP = False

# ── config ────────────────────────────────────────────────────────────────
DB_PATH      = "btc_recovery.db"
ESPLORA      = "https://blockstream.info/api"
API_DELAY    = 0.25
DERIVE_COUNT = 100

INGESTABLE = {'.txt','.csv','.json','.dat','.backup','.gz','.md','.txn'}

DERIVATION_PATHS = {
    "BIP44_legacy":        "m/44'/0'/0'",
    "BIP49_p2sh_segwit":   "m/49'/0'/0'",
    "BIP84_bech32":        "m/84'/0'/0'",
    "BIP44_account1":      "m/44'/0'/1'",
    "BIP84_account1":      "m/84'/0'/1'",
    "Electrum_legacy":     "m/0'",
    "Electrum_segwit":     "m/0",
    "Samourai_deposit":    "m/84'/0'/0'",
    "Samourai_badbank":    "m/84'/0'/2147483644'",
    "Samourai_premix":     "m/84'/0'/2147483645'",
    "Samourai_postmix":    "m/84'/0'/2147483646'",
    "Samourai_ricochet":   "m/84'/0'/2147483647'",
    "BRD":                 "m/0'/0",
    "Multisig_BIP48_p2sh": "m/48'/0'/0'/1'",
    "Multisig_BIP48_wseg": "m/48'/0'/0'/2'",
    "Casa_multisig":       "m/49/0/0",
}

# ════════════════════════════════════════════════════════════════════════════
# CRYPTO
# ════════════════════════════════════════════════════════════════════════════

def sha256d(data):
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def hash160(data):
    return hashlib.new('ripemd160', hashlib.sha256(data).digest()).digest()

def wif_to_bytes(wif):
    try:
        dec = base58.b58decode(wif)
        raw = dec[1:-4]
        if len(raw) == 33 and raw[-1] == 0x01:
            raw = raw[:-1]
        return raw if len(raw) == 32 else None
    except:
        return None

def bytes_to_pubkey(priv):
    try:
        sk = ecdsa.SigningKey.from_string(priv, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key().to_string()
        prefix = b'\x03' if vk[32] & 1 else b'\x02'
        return prefix + vk[:32]
    except:
        return None

def pub_to_legacy(pub):
    try:
        h = hash160(pub)
        ext = b'\x00' + h
        return base58.b58encode(ext + sha256d(ext)[:4]).decode()
    except:
        return None

def pub_to_p2sh(pub):
    try:
        h = hash160(pub)
        redeem = b'\x00\x14' + h
        sh = hash160(redeem)
        ext = b'\x05' + sh
        return base58.b58encode(ext + sha256d(ext)[:4]).decode()
    except:
        return None

def pub_to_bech32(pub, hrp='bc'):
    try:
        h = hash160(pub)
        conv = bech32.convertbits(h, 8, 5)
        return bech32.bech32_encode(hrp, [0] + conv)
    except:
        return None

def derive_all(pub):
    return {'legacy': pub_to_legacy(pub), 'p2sh': pub_to_p2sh(pub), 'bech32': pub_to_bech32(pub)}

def compress_wif(wif5):
    try:
        dec = base58.b58decode(wif5)
        priv = dec[1:-4]
        ext = b'\x80' + priv + b'\x01'
        return base58.b58encode(ext + sha256d(ext)[:4]).decode()
    except:
        return None

def normalize_wif(wif):
    if not wif: return None
    wif = wif.strip()
    if wif.startswith('5'): return compress_wif(wif)
    if wif.startswith(('K','L')): return wif
    return None

def hex_to_wif(h, compressed=True):
    try:
        priv = bytes.fromhex(h.strip().replace('0x',''))
        suffix = b'\x01' if compressed else b''
        ext = b'\x80' + priv + suffix
        return base58.b58encode(ext + sha256d(ext)[:4]).decode()
    except:
        return None

def verify_pair(wif, pubkey_hex):
    try:
        priv = wif_to_bytes(wif)
        if not priv: return False
        derived = bytes_to_pubkey(priv)
        if not derived: return False
        if len(pubkey_hex) == 130:
            pub_b = bytes.fromhex(pubkey_hex)
            prefix = b'\x03' if pub_b[64] & 1 else b'\x02'
            pubkey_hex = (prefix + pub_b[1:33]).hex()
        return derived.hex().lower() == pubkey_hex.lower().strip()
    except:
        return False

def is_valid_address(a):
    return bool(a) and len(a) >= 25 and a.startswith(('1','3','bc1'))

def is_valid_wif(w):
    return bool(w) and len(w) >= 40 and w.startswith(('5','K','L'))

def is_valid_pubkey(p):
    if not p: return False
    p = p.replace('0x','').strip()
    return len(p) in (66,128,130) and all(c in '0123456789abcdefABCDEF' for c in p)

def is_valid_seed(t):
    return len(t.strip().split()) in (12,15,18,21,24)

def is_valid_xpub(t):
    return t.strip().startswith(('xpub','ypub','zpub')) and len(t.strip()) > 100

def is_valid_hex_privkey(h):
    h = h.strip().replace('0x','')
    return len(h) == 64 and all(c in '0123456789abcdefABCDEF' for c in h)

# ════════════════════════════════════════════════════════════════════════════
# KEY DATABASE
# ════════════════════════════════════════════════════════════════════════════

class KeyDB:
    """
    Persistent SQLite store. Every run ADDS to it, never overwrites.

    keys.state values:
      COMPLETE   - privkey + pubkey verified (spendable)
      DERIVED    - privkey only, pubkey+addresses derived from it (spendable)
      PUBKEY_ONLY - pubkey known, no privkey (watch only)
      ADDR_ONLY  - address only (watch only)
      SEED       - seed phrase (HD derivation pending/done)
      XPUB       - extended pubkey
    """
    def __init__(self, db_path=DB_PATH):
        self.path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self._create_tables()

    def _create_tables(self):
        self.conn.executescript("""
            CREATE TABLE IF NOT EXISTS keys (
                id              INTEGER PRIMARY KEY AUTOINCREMENT,
                privkey_wif     TEXT UNIQUE,
                privkey_hex     TEXT,
                pubkey_hex      TEXT,
                state           TEXT DEFAULT 'UNKNOWN',
                verified        INTEGER DEFAULT 0,
                source_file     TEXT,
                source_type     TEXT,
                seed_phrase     TEXT,
                derivation_path TEXT,
                notes           TEXT,
                added_at        TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS addresses (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                address     TEXT UNIQUE NOT NULL,
                addr_type   TEXT,
                key_id      INTEGER REFERENCES keys(id),
                source_file TEXT,
                added_at    TEXT DEFAULT (datetime('now'))
            );
            CREATE TABLE IF NOT EXISTS scan (
                address      TEXT PRIMARY KEY,
                balance_sat  INTEGER DEFAULT 0,
                funded_sat   INTEGER DEFAULT 0,
                spent_sat    INTEGER DEFAULT 0,
                tx_count     INTEGER DEFAULT 0,
                has_history  INTEGER DEFAULT 0,
                scanned_at   TEXT,
                raw_gz       BLOB
            );
            CREATE TABLE IF NOT EXISTS utxos (
                address     TEXT,
                txid        TEXT,
                vout        INTEGER,
                value_sat   INTEGER,
                confirmed   INTEGER DEFAULT 0,
                PRIMARY KEY (txid, vout)
            );
            CREATE TABLE IF NOT EXISTS ingested_files (
                filepath    TEXT PRIMARY KEY,
                file_type   TEXT,
                rows_added  INTEGER DEFAULT 0,
                ingested_at TEXT DEFAULT (datetime('now'))
            );
            CREATE INDEX IF NOT EXISTS idx_addr_keyid ON addresses(key_id);
            CREATE INDEX IF NOT EXISTS idx_scan_bal   ON scan(balance_sat);
            CREATE INDEX IF NOT EXISTS idx_keys_state ON keys(state);
        """)
        self.conn.commit()

    def stats(self):
        c = self.conn
        return {
            'total_keys':   c.execute("SELECT COUNT(*) FROM keys").fetchone()[0],
            'complete':     c.execute("SELECT COUNT(*) FROM keys WHERE state='COMPLETE'").fetchone()[0],
            'derived':      c.execute("SELECT COUNT(*) FROM keys WHERE state='DERIVED'").fetchone()[0],
            'pubkey_only':  c.execute("SELECT COUNT(*) FROM keys WHERE state='PUBKEY_ONLY'").fetchone()[0],
            'addr_only':    c.execute("SELECT COUNT(*) FROM keys WHERE state='ADDR_ONLY'").fetchone()[0],
            'seed':         c.execute("SELECT COUNT(*) FROM keys WHERE state='SEED'").fetchone()[0],
            'total_addrs':  c.execute("SELECT COUNT(*) FROM addresses").fetchone()[0],
            'scanned':      c.execute("SELECT COUNT(*) FROM scan").fetchone()[0],
            'with_balance': c.execute("SELECT COUNT(*) FROM scan WHERE balance_sat > 0").fetchone()[0],
            'with_history': c.execute("SELECT COUNT(*) FROM scan WHERE has_history = 1").fetchone()[0],
            'total_btc':    (c.execute("SELECT COALESCE(SUM(balance_sat),0) FROM scan").fetchone()[0] or 0) / 1e8,
            'files':        c.execute("SELECT COUNT(*) FROM ingested_files").fetchone()[0],
        }

    def print_stats(self):
        s = self.stats()
        print(f"\n{'─'*52}")
        print(f"  DATABASE: {self.path}")
        print(f"{'─'*52}")
        print(f"  Keys:         {s['total_keys']}")
        print(f"  ├ COMPLETE:   {s['complete']}  (privkey+pubkey verified)")
        print(f"  ├ DERIVED:    {s['derived']}  (privkey → all derived)")
        print(f"  ├ PUBKEY_ONLY:{s['pubkey_only']}  (watch only)")
        print(f"  ├ ADDR_ONLY:  {s['addr_only']}  (address only)")
        print(f"  └ SEED/XPUB:  {s['seed']}")
        print(f"  Addresses:    {s['total_addrs']}")
        print(f"  Scanned:      {s['scanned']}")
        print(f"  With balance: {s['with_balance']}")
        print(f"  With history: {s['with_history']}")
        print(f"  Total BTC:    {s['total_btc']:.8f}")
        print(f"  Files done:   {s['files']}")
        print(f"{'─'*52}\n")

    # ── add records ───────────────────────────────────────────────────────

    def add_privkey(self, wif, pubkey_hex=None, source_file=None, source_type=None):
        wif_c = normalize_wif(wif)
        if not wif_c: return -1
        priv_bytes = wif_to_bytes(wif_c)
        if not priv_bytes: return -1
        priv_hex = priv_bytes.hex()
        pub_bytes = bytes_to_pubkey(priv_bytes)
        derived_pub = pub_bytes.hex() if pub_bytes else None
        verified, state = 0, 'DERIVED'
        if pubkey_hex and derived_pub:
            if verify_pair(wif_c, pubkey_hex):
                verified, state = 1, 'COMPLETE'
        try:
            cur = self.conn.execute("""
                INSERT OR IGNORE INTO keys
                  (privkey_wif,privkey_hex,pubkey_hex,state,verified,source_file,source_type)
                VALUES (?,?,?,?,?,?,?)
            """, (wif_c, priv_hex, derived_pub, state, verified, source_file, source_type))
            self.conn.commit()
            key_id = cur.lastrowid
            if key_id and key_id > 0 and pub_bytes:
                self._add_addresses(key_id, pub_bytes, source_file)
            elif key_id == 0:
                row = self.conn.execute("SELECT id FROM keys WHERE privkey_wif=?", (wif_c,)).fetchone()
                key_id = row['id'] if row else -1
            return key_id
        except:
            return -1

    def add_pubkey(self, pubkey_hex, source_file=None):
        pub = pubkey_hex.strip().replace('0x','')
        if not is_valid_pubkey(pub): return -1
        try:
            if len(pub) == 128: pub = '04' + pub
            if len(pub) == 130 and pub.startswith('04'):
                pb = bytes.fromhex(pub)
                prefix = b'\x03' if pb[64] & 1 else b'\x02'
                pub = (prefix + pb[1:33]).hex()
            pub_bytes = bytes.fromhex(pub)
        except:
            return -1
        existing = self.conn.execute("SELECT id FROM keys WHERE pubkey_hex=?", (pub,)).fetchone()
        if existing: return existing['id']
        try:
            cur = self.conn.execute("""
                INSERT OR IGNORE INTO keys (pubkey_hex,state,source_file,source_type)
                VALUES (?,'PUBKEY_ONLY',?,'pubkey')
            """, (pub, source_file))
            self.conn.commit()
            key_id = cur.lastrowid
            if key_id and key_id > 0:
                self._add_addresses(key_id, pub_bytes, source_file)
            return key_id
        except:
            return -1

    def add_address(self, address, source_file=None):
        if not is_valid_address(address): return -1
        existing = self.conn.execute(
            "SELECT key_id FROM addresses WHERE address=?", (address,)
        ).fetchone()
        if existing and existing['key_id']: return existing['key_id']
        try:
            cur = self.conn.execute("""
                INSERT OR IGNORE INTO keys (state,source_file,source_type,notes)
                VALUES ('ADDR_ONLY',?,'address',?)
            """, (source_file, address))
            self.conn.commit()
            key_id = cur.lastrowid
            addr_type = 'bech32' if address.startswith('bc1') else 'p2sh' if address.startswith('3') else 'legacy'
            self.conn.execute("""
                INSERT OR IGNORE INTO addresses (address,addr_type,key_id,source_file)
                VALUES (?,?,?,?)
            """, (address, addr_type, key_id, source_file))
            self.conn.commit()
            return key_id
        except:
            return -1

    def add_seed(self, mnemonic, source_file=None):
        m = mnemonic.strip()
        if not is_valid_seed(m): return -1
        try:
            cur = self.conn.execute("""
                INSERT OR IGNORE INTO keys (seed_phrase,state,source_file,source_type)
                VALUES (?,'SEED',?,'seed')
            """, (m, source_file))
            self.conn.commit()
            return cur.lastrowid
        except:
            return -1

    def _add_addresses(self, key_id, pub_bytes, source_file):
        addrs = derive_all(pub_bytes)
        for addr_type, addr in addrs.items():
            if addr:
                try:
                    self.conn.execute("""
                        INSERT OR IGNORE INTO addresses (address,addr_type,key_id,source_file)
                        VALUES (?,?,?,?)
                    """, (addr, addr_type, key_id, source_file))
                except:
                    pass
        self.conn.commit()

    def mark_ingested(self, filepath, file_type, rows):
        self.conn.execute("""
            INSERT OR REPLACE INTO ingested_files (filepath,file_type,rows_added)
            VALUES (?,?,?)
        """, (filepath, file_type, rows))
        self.conn.commit()

    def is_ingested(self, filepath):
        return bool(self.conn.execute(
            "SELECT 1 FROM ingested_files WHERE filepath=?", (filepath,)
        ).fetchone())

    # ── cross-match ───────────────────────────────────────────────────────

    def cross_match(self):
        """Link partial records from different files"""
        matches = 0

        # PUBKEY_ONLY that matches an existing DERIVED/COMPLETE key's pubkey
        pubkey_only = self.conn.execute(
            "SELECT id, pubkey_hex FROM keys WHERE state='PUBKEY_ONLY' AND pubkey_hex IS NOT NULL"
        ).fetchall()
        for row in pubkey_only:
            existing = self.conn.execute(
                "SELECT id FROM keys WHERE pubkey_hex=? AND state IN ('DERIVED','COMPLETE')",
                (row['pubkey_hex'],)
            ).fetchone()
            if existing:
                self.conn.execute("UPDATE addresses SET key_id=? WHERE key_id=?", (existing['id'], row['id']))
                self.conn.execute("DELETE FROM keys WHERE id=?", (row['id'],))
                self.conn.commit()
                matches += 1

        # ADDR_ONLY addresses that exist in another key's derived addresses
        addr_only = self.conn.execute(
            "SELECT k.id, a.address FROM keys k JOIN addresses a ON a.key_id=k.id WHERE k.state='ADDR_ONLY'"
        ).fetchall()
        for row in addr_only:
            linked = self.conn.execute(
                "SELECT a.key_id FROM addresses a JOIN keys k ON k.id=a.key_id "
                "WHERE a.address=? AND k.state != 'ADDR_ONLY'",
                (row['address'],)
            ).fetchone()
            if linked:
                self.conn.execute("DELETE FROM keys WHERE id=?", (row['id'],))
                self.conn.commit()
                matches += 1

        if matches:
            print(f"[MATCH] Linked {matches} partial records")
        else:
            print(f"[MATCH] No new matches (need more files or shared keys)")
        return matches

    # ── getters ───────────────────────────────────────────────────────────

    def get_unscanned(self):
        return self.conn.execute("""
            SELECT a.address, a.addr_type, a.key_id, k.state, k.privkey_wif
            FROM addresses a JOIN keys k ON k.id=a.key_id
            WHERE a.address NOT IN (SELECT address FROM scan)
        """).fetchall()

    def get_hits(self):
        return self.conn.execute("""
            SELECT s.address, s.balance_sat, s.tx_count, s.has_history,
                   a.addr_type, k.state, k.privkey_wif, k.pubkey_hex,
                   k.seed_phrase, k.derivation_path
            FROM scan s
            JOIN addresses a ON a.address=s.address
            JOIN keys k ON k.id=a.key_id
            WHERE s.balance_sat > 0 OR s.has_history=1
            ORDER BY s.balance_sat DESC
        """).fetchall()

    def save_scan(self, address, data):
        cs = data.get('chain_stats', {})
        ms = data.get('mempool_stats', {})
        funded = cs.get('funded_txo_sum',0) + ms.get('funded_txo_sum',0)
        spent  = cs.get('spent_txo_sum',0)  + ms.get('spent_txo_sum',0)
        tx_cnt = cs.get('tx_count',0)        + ms.get('tx_count',0)
        bal    = funded - spent
        raw_gz = zlib.compress(json.dumps(data).encode(), level=6)
        self.conn.execute("""
            INSERT OR REPLACE INTO scan
              (address,balance_sat,funded_sat,spent_sat,tx_count,has_history,scanned_at,raw_gz)
            VALUES (?,?,?,?,?,?,datetime('now'),?)
        """, (address, bal, funded, spent, tx_cnt, int(tx_cnt > 0), raw_gz))
        self.conn.commit()

    def save_utxos(self, address, utxos):
        for u in utxos:
            try:
                self.conn.execute("""
                    INSERT OR REPLACE INTO utxos (address,txid,vout,value_sat,confirmed)
                    VALUES (?,?,?,?,?)
                """, (address, u['txid'], u['vout'], u['value'],
                      int(u.get('status',{}).get('confirmed',False))))
            except:
                pass
        self.conn.commit()


# ════════════════════════════════════════════════════════════════════════════
# INGESTOR
# ════════════════════════════════════════════════════════════════════════════

class Ingestor:
    def __init__(self, db):
        self.db = db
        self.total_added = 0

    def ingest_folder(self, folder):
        path = Path(folder)
        if not path.exists():
            print(f"[INGEST] Not found: {folder}")
            return
        files = [f for f in path.rglob('*') if f.is_file() and f.suffix.lower() in INGESTABLE]
        print(f"[INGEST] {len(files)} files found in {folder}")
        for f in sorted(files):
            self.ingest_file(str(f))

    def ingest_file(self, filepath):
        path = Path(filepath)
        if not path.exists():
            print(f"[INGEST] Not found: {filepath}")
            return
        if self.db.is_ingested(filepath):
            print(f"[INGEST] Already done: {path.name}")
            return
        print(f"[INGEST] {path.name}")
        content = self._read(filepath)
        if not content:
            return
        added, file_type = 0, 'unknown'
        strategies = [
            ('electrum_json', self._try_electrum_json),
            ('keypair_csv',   self._try_keypair_csv),
            ('seed_file',     self._try_seed_file),
            ('wif_list',      self._try_wif_list),
            ('address_list',  self._try_address_list),
            ('hex_privkeys',  self._try_hex_privkeys),
            ('pubkey_list',   self._try_pubkey_list),
            ('mixed_regex',   self._try_mixed_regex),
        ]
        for name, fn in strategies:
            try:
                n = fn(content, filepath)
                if n > 0:
                    added += n
                    file_type = name
                    print(f"  {name}: +{n}")
            except:
                pass
        self.db.mark_ingested(filepath, file_type, added)
        self.total_added += added
        if added == 0:
            print(f"  nothing extracted")

    def _read(self, filepath):
        try:
            if filepath.endswith('.gz'):
                with gzip.open(filepath, 'rt', encoding='utf-8', errors='ignore') as f:
                    return f.read()
            with open(filepath, 'rb') as f:
                raw = f.read()
            try:    return raw.decode('utf-8')
            except: return raw.decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"  [read error] {e}")
            return ""

    def _try_electrum_json(self, content, filepath):
        added = 0
        data = None
        for length in [len(content)] + list(range(len(content), 0, -2000)):
            try:
                data = json.loads(content[:length])
                break
            except:
                continue
        if not data: return 0
        def find_kp(obj, d=0):
            if d > 5: return {}
            if isinstance(obj, dict):
                if 'keypairs' in obj and isinstance(obj['keypairs'], dict):
                    return obj['keypairs']
                for v in obj.values():
                    r = find_kp(v, d+1)
                    if r: return r
            return {}
        for pub, priv in find_kp(data).items():
            if is_valid_wif(priv):
                self.db.add_privkey(priv, pub if is_valid_pubkey(pub) else None, filepath, 'electrum')
                added += 1
        seed = (data.get('keystore') or {}).get('seed', '')
        if seed and is_valid_seed(seed):
            self.db.add_seed(seed, filepath); added += 1
        xpub = (data.get('keystore') or {}).get('xpub', '')
        if xpub and is_valid_xpub(xpub):
            self.db.conn.execute("INSERT OR IGNORE INTO keys (state,source_file,source_type,notes) VALUES ('XPUB',?,'xpub',?)", (filepath, xpub))
            self.db.conn.commit(); added += 1
        return added

    def _try_keypair_csv(self, content, filepath):
        import io
        added = 0
        try:
            reader = csv.DictReader(io.StringIO(content))
            for row in reader:
                priv = (row.get('Private Key (WIF)') or row.get('private_key') or row.get('privkey') or '').strip()
                pub  = (row.get('Public Key') or row.get('public_key') or row.get('pubkey') or '').strip()
                addr = (row.get('Derived Address') or row.get('address') or '').strip()
                if is_valid_wif(priv):
                    self.db.add_privkey(priv, pub if is_valid_pubkey(pub) else None, filepath, 'csv')
                    added += 1
                elif is_valid_pubkey(pub):
                    self.db.add_pubkey(pub, filepath); added += 1
                elif is_valid_address(addr):
                    self.db.add_address(addr, filepath); added += 1
        except: pass
        return added

    def _try_seed_file(self, content, filepath):
        added = 0
        if is_valid_seed(content.strip()):
            self.db.add_seed(content.strip(), filepath); return 1
        for line in content.splitlines():
            line = line.strip()
            if is_valid_seed(line):
                self.db.add_seed(line, filepath); added += 1
        return added

    def _try_wif_list(self, content, filepath):
        added = 0
        for line in content.splitlines():
            wif = line.strip().split(',')[0].split()[0]
            if is_valid_wif(wif):
                self.db.add_privkey(wif, None, filepath, 'wif_list'); added += 1
        return added

    def _try_address_list(self, content, filepath):
        added = 0
        for line in content.splitlines():
            addr = line.strip().split(',')[0].split()[0]
            if is_valid_address(addr):
                self.db.add_address(addr, filepath); added += 1
        return added

    def _try_hex_privkeys(self, content, filepath):
        added = 0
        for line in content.splitlines():
            h = line.strip().replace('0x','')
            if is_valid_hex_privkey(h):
                wif = hex_to_wif(h)
                if wif: self.db.add_privkey(wif, None, filepath, 'hex_privkey'); added += 1
        return added

    def _try_pubkey_list(self, content, filepath):
        added = 0
        for line in content.splitlines():
            pub = line.strip().replace('0x','')
            if is_valid_pubkey(pub):
                self.db.add_pubkey(pub, filepath); added += 1
        return added

    def _try_mixed_regex(self, content, filepath):
        added = 0
        for wif in re.findall(r'[5KL][1-9A-HJ-NP-Za-km-z]{40,60}', content):
            if is_valid_wif(wif):
                self.db.add_privkey(wif, None, filepath, 'regex'); added += 1
        for addr in re.findall(r'(?:bc1[a-z0-9]{25,}|[13][1-9A-HJ-NP-Za-km-z]{25,34})', content):
            if is_valid_address(addr):
                self.db.add_address(addr, filepath); added += 1
        for pub in re.findall(r'0[23][0-9a-fA-F]{64}', content):
            if is_valid_pubkey(pub):
                self.db.add_pubkey(pub, filepath); added += 1
        for h in re.findall(r'\b[0-9a-fA-F]{64}\b', content):
            if is_valid_hex_privkey(h):
                wif = hex_to_wif(h)
                if wif: self.db.add_privkey(wif, None, filepath, 'regex_hex'); added += 1
        return added


# ════════════════════════════════════════════════════════════════════════════
# HD DERIVER
# ════════════════════════════════════════════════════════════════════════════

class Deriver:
    def __init__(self, db):
        self.db = db

    def run(self):
        if not HAS_BIP:
            print("[DERIVE] bip_utils unavailable — skipping"); return
        seeds = self.db.conn.execute(
            "SELECT id, seed_phrase FROM keys WHERE state='SEED' AND seed_phrase IS NOT NULL"
        ).fetchall()
        if not seeds:
            print("[DERIVE] No seeds found"); return
        print(f"[DERIVE] {len(seeds)} seed(s) × {len(DERIVATION_PATHS)} paths × {DERIVE_COUNT} addrs")
        for sr in seeds:
            seed_id, mnemonic = sr['id'], sr['seed_phrase']
            preview = ' '.join(mnemonic.split()[:3])
            print(f"  Seed {seed_id}: {preview}...")
            try:
                seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
            except Exception as e:
                print(f"  [error] {e}"); continue
            for path_name, path in DERIVATION_PATHS.items():
                try:
                    master = Bip32Slip10Secp256k1.FromSeed(seed_bytes)
                    parts  = path.replace("m/","").split("/")
                    node   = master
                    for part in parts:
                        if not part: continue
                        hardened = part.endswith("'")
                        idx = int(part.rstrip("'"))
                        node = node.ChildKey(idx + (0x80000000 if hardened else 0))
                    for change in [0,1]:
                        cnode = node.ChildKey(change)
                        for i in range(DERIVE_COUNT):
                            child = cnode.ChildKey(i)
                            pub_bytes = child.PublicKey().RawCompressed().ToBytes()
                            addrs = derive_all(pub_bytes)
                            dpath = f"{path}/{change}/{i}"
                            try:
                                cur = self.db.conn.execute("""
                                    INSERT OR IGNORE INTO keys
                                      (pubkey_hex,state,source_file,source_type,derivation_path,notes)
                                    VALUES (?,'SEED',?,'hd_derived',?,?)
                                """, (pub_bytes.hex(), f"seed:{seed_id}", dpath, path_name))
                                self.db.conn.commit()
                                key_id = cur.lastrowid
                                if key_id and key_id > 0:
                                    self.db.conn.executemany("""
                                        INSERT OR IGNORE INTO addresses
                                          (address,addr_type,key_id,source_file)
                                        VALUES (?,?,?,?)
                                    """, [(addrs['legacy'],'legacy',key_id,f"seed:{seed_id}"),
                                          (addrs['p2sh'],'p2sh',key_id,f"seed:{seed_id}"),
                                          (addrs['bech32'],'bech32',key_id,f"seed:{seed_id}")])
                                    self.db.conn.commit()
                            except: pass
                except: continue
        print(f"[DERIVE] Done — {self.db.stats()['total_addrs']} total addresses")


# ════════════════════════════════════════════════════════════════════════════
# ESPLORA CLIENT
# ════════════════════════════════════════════════════════════════════════════

class EsploraClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'Accept-Encoding':'gzip, deflate','User-Agent':'btc-recovery/2.0'})
        self._calls = 0

    def _get(self, path, retries=3):
        url = f"{ESPLORA}{path}"
        for attempt in range(retries):
            try:
                r = self.session.get(url, timeout=15)
                self._calls += 1
                if r.status_code == 200: return r
                if r.status_code == 429: time.sleep(5*(attempt+1))
                else: return r
            except:
                if attempt < retries-1: time.sleep(2)
        return None

    def get_address(self, address):
        r = self._get(f"/address/{address}")
        return r.json() if r and r.status_code == 200 else None

    def get_utxos(self, address):
        r = self._get(f"/address/{address}/utxo")
        if r and r.status_code == 200: return r.json()
        if r and r.status_code == 400: return self._reconstruct_utxos(address)
        return []

    def _reconstruct_utxos(self, address):
        funded, spent, last = {}, set(), None
        while True:
            path = f"/address/{address}/txs" + (f"/chain/{last}" if last else "")
            r = self._get(path)
            if not r or r.status_code != 200: break
            txs = r.json()
            if not txs: break
            for tx in txs:
                txid = tx['txid']
                for i, vout in enumerate(tx.get('vout',[])):
                    if vout.get('scriptpubkey_address') == address:
                        funded[f"{txid}:{i}"] = vout.get('value',0)
                for vin in tx.get('vin',[]):
                    if vin.get('txid'): spent.add(f"{vin['txid']}:{vin['vout']}")
            last = txs[-1]['txid']
            time.sleep(0.5)
            if len(txs) < 25: break
        return [{'txid':k.split(':')[0],'vout':int(k.split(':')[1]),'value':v}
                for k,v in funded.items() if k not in spent]


# ════════════════════════════════════════════════════════════════════════════
# SCANNER
# ════════════════════════════════════════════════════════════════════════════

class Scanner:
    def __init__(self, db, client):
        self.db     = db
        self.client = client

    def run(self, limit=0):
        unscanned = self.db.get_unscanned()
        if limit: unscanned = unscanned[:limit]
        total = len(unscanned)
        if total == 0:
            print("[SCAN] All addresses already scanned"); return
        print(f"[SCAN] {total} addresses to scan...")
        hits = 0
        for i, row in enumerate(unscanned):
            addr = row['address']
            data = self.client.get_address(addr)
            if data:
                self.db.save_scan(addr, data)
                cs  = data.get('chain_stats',{})
                bal = cs.get('funded_txo_sum',0) - cs.get('spent_txo_sum',0)
                txc = cs.get('tx_count',0)
                if bal > 0 or txc > 0:
                    hits += 1
                    sym   = '💰' if bal > 0 else '📜'
                    spend = '✅ SPENDABLE' if row['state'] in ('COMPLETE','DERIVED') else '👁 WATCH-ONLY'
                    print(f"  {sym} {addr}  {bal/1e8:.8f} BTC  {spend}  [{row['addr_type']}]")
                    if bal > 0:
                        utxos = self.client.get_utxos(addr)
                        if utxos: self.db.save_utxos(addr, utxos)
            if (i+1) % 50 == 0:
                print(f"  [{i+1}/{total}] {((i+1)/total)*100:.1f}%  hits={hits}  calls={self.client._calls}")
                time.sleep(1)
            else:
                time.sleep(API_DELAY)
        print(f"\n[SCAN] Done — {hits} hits out of {total}")


# ════════════════════════════════════════════════════════════════════════════
# REPORT + EXPORT
# ════════════════════════════════════════════════════════════════════════════

def report(db):
    hits = db.get_hits()
    s    = db.stats()
    print(f"\n{'='*60}")
    print(f"  RECOVERY REPORT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")
    print(f"  Total BTC:          {s['total_btc']:.8f}")
    print(f"  Addresses w/balance:{s['with_balance']}")
    print(f"  Addresses w/history:{s['with_history']}")
    print(f"{'='*60}")
    spendable = [h for h in hits if h['state'] in ('COMPLETE','DERIVED') and h['balance_sat']>0]
    watch_bal = [h for h in hits if h['state'] not in ('COMPLETE','DERIVED') and h['balance_sat']>0]
    hist_only = [h for h in hits if h['balance_sat']==0]
    if spendable:
        print(f"\n  SPENDABLE (have privkey + balance):")
        for h in spendable:
            print(f"    {h['address']}  {h['balance_sat']/1e8:.8f} BTC")
            if h['privkey_wif']: print(f"    privkey: {h['privkey_wif']}")
    if watch_bal:
        print(f"\n  WATCH-ONLY (balance but NO privkey — need to find key):")
        for h in watch_bal:
            print(f"    {h['address']}  {h['balance_sat']/1e8:.8f} BTC  ← NEED PRIVKEY")
    if hist_only:
        print(f"\n  HISTORY ONLY (funds moved, may still be useful):")
        for h in hist_only[:20]:
            print(f"    {h['address']}  tx_count={h['tx_count']}")
    utxo_rows = db.conn.execute("""
        SELECT u.address, u.txid, u.vout, u.value_sat, k.state, k.privkey_wif
        FROM utxos u
        JOIN addresses a ON a.address=u.address
        JOIN keys k ON k.id=a.key_id
        JOIN scan s ON s.address=u.address
        WHERE s.balance_sat > 0
        ORDER BY u.value_sat DESC
    """).fetchall()
    if utxo_rows:
        print(f"\n  SPENDABLE UTXOs:")
        for u in utxo_rows:
            sym = "✅" if u['state'] in ('COMPLETE','DERIVED') else "👁"
            print(f"    {sym} {u['address']}  {u['value_sat']/1e8:.8f} BTC")
            print(f"       txid:{u['txid']}  vout:{u['vout']}")
    print(f"\n{'='*60}\n")


def export_spendable(db):
    filename = f"spendable_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    rows = db.conn.execute("""
        SELECT k.privkey_wif, k.pubkey_hex, a.address, a.addr_type,
               s.balance_sat, s.tx_count, k.state
        FROM keys k
        JOIN addresses a ON a.key_id=k.id
        LEFT JOIN scan s ON s.address=a.address
        WHERE k.state IN ('COMPLETE','DERIVED')
          AND (s.balance_sat > 0 OR s.has_history=1)
        ORDER BY s.balance_sat DESC
    """).fetchall()
    with open(filename, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['privkey_wif','pubkey_hex','address','addr_type','balance_btc','tx_count','state'])
        for r in rows:
            w.writerow([r['privkey_wif'], r['pubkey_hex'], r['address'], r['addr_type'],
                        f"{(r['balance_sat'] or 0)/1e8:.8f}", r['tx_count'], r['state']])
    with open(filename,'rb') as fi:
        with gzip.open(filename+'.gz','wb') as fo:
            fo.write(fi.read())
    print(f"[EXPORT] {len(rows)} records → {filename} + .gz")


# ════════════════════════════════════════════════════════════════════════════
# MAIN
# ════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="BTC Recovery Bot v2")
    ap.add_argument('--ingest', metavar='FOLDER', help='Ingest all files in folder')
    ap.add_argument('--file',   metavar='FILE',   help='Ingest single file')
    ap.add_argument('--scan',   action='store_true', help='Scan blockchain')
    ap.add_argument('--report', action='store_true', help='Show report')
    ap.add_argument('--export', action='store_true', help='Export spendable keys')
    ap.add_argument('--status', action='store_true', help='Show DB status')
    ap.add_argument('--match',  action='store_true', help='Cross-match only')
    ap.add_argument('--derive', action='store_true', help='Derive seeds only')
    ap.add_argument('--db',     default=DB_PATH,     help=f'DB path (default:{DB_PATH})')
    ap.add_argument('--limit',  type=int, default=0, help='Limit scan addresses')
    args = ap.parse_args()

    if not any([args.ingest, args.file, args.scan, args.report,
                args.export, args.status, args.match, args.derive]):
        ap.print_help(); sys.exit(0)

    print(f"\n{'='*60}")
    print(f"  BTC RECOVERY BOT v2 — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    db = KeyDB(args.db)
    db.print_stats()

    if args.ingest:
        ing = Ingestor(db)
        ing.ingest_folder(args.ingest)
        print(f"[INGEST] Added {ing.total_added} records this run")
        db.cross_match()
        Deriver(db).run()
        db.print_stats()

    if args.file:
        ing = Ingestor(db)
        ing.ingest_file(args.file)
        db.cross_match()
        Deriver(db).run()
        db.print_stats()

    if args.derive: Deriver(db).run(); db.print_stats()
    if args.match:  db.cross_match(); db.print_stats()
    if args.scan:   Scanner(db, EsploraClient()).run(args.limit)
    if args.report: report(db)
    if args.export: export_spendable(db)
    if args.status: db.print_stats()

if __name__ == "__main__":
    main()

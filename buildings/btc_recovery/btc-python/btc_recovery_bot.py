#!/usr/bin/env python3
"""
BTC Wallet Recovery Bot
=======================
Complete pipeline:
  1. Repair / extract keypairs from corrupted Electrum wallets
  2. Convert uncompressed WIF → compressed WIF
  3. Derive ALL address types (Legacy, P2SH-SegWit, Bech32)
  4. Scan derivation paths (BIP44/49/84) from seed/xpub
  5. Query Blockstream Esplora API (gzip) with SQLite cache (zlib)
  6. Report every address that has / had funds
  7. Broadcast signed txs when ready

Usage:
  python btc_recovery_bot.py --wallet wallet.dat
  python btc_recovery_bot.py --csv   full_keypairs.csv
  python btc_recovery_bot.py --keys  private_keys.txt
  python btc_recovery_bot.py --seed  "word1 word2 ..."
  python btc_recovery_bot.py --xpub  xpub6...
"""

import os, sys, re, json, csv, gzip, zlib, time, hashlib, sqlite3, argparse, binascii
import requests
from datetime import datetime
from collections import Counter

# ── optional deps (install if missing) ──────────────────────────────────────
try:
    import base58
except ImportError:
    os.system("pip install base58 --break-system-packages -q")
    import base58

try:
    import ecdsa
except ImportError:
    os.system("pip install ecdsa --break-system-packages -q")
    import ecdsa

try:
    import bech32
except ImportError:
    os.system("pip install bech32 --break-system-packages -q")
    import bech32

try:
    from bip_utils import Bip39MnemonicValidator, Bip39SeedGenerator, Bip32Slip10Secp256k1
    HAS_BIP_UTILS = True
except ImportError:
    os.system("pip install bip_utils --break-system-packages -q")
    try:
        from bip_utils import Bip39MnemonicValidator, Bip39SeedGenerator, Bip32Slip10Secp256k1
        HAS_BIP_UTILS = True
    except:
        HAS_BIP_UTILS = False

# ════════════════════════════════════════════════════════════════════════════
# CONFIG
# ════════════════════════════════════════════════════════════════════════════

ESPLORA_BASE   = "https://blockstream.info/api"
CACHE_DB       = "recovery_cache.db"
RESULTS_FILE   = f"recovery_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
API_DELAY      = 0.25   # seconds between calls
BATCH_SIZE     = 50     # addresses per batch before pause
DERIVE_COUNT   = 100    # addresses to derive per path

# All derivation paths from walletsrecovery.org
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
    "BRD_legacy":          "m/0'/0",
    "Multisig_BIP45":      "m/45'",
    "Multisig_BIP48_p2sh": "m/48'/0'/0'/1'",
    "Multisig_BIP48_wseg": "m/48'/0'/0'/2'",
    "Casa_multisig":       "m/49/0/0",
    "Coinomi_legacy":      "m/44'/0'/0'",
    "Wasabi_deposit":      "m/84'/0'/0'",
}


# ════════════════════════════════════════════════════════════════════════════
# 1. CRYPTO PRIMITIVES
# ════════════════════════════════════════════════════════════════════════════

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

def hash160(data: bytes) -> bytes:
    return hashlib.new('ripemd160', hashlib.sha256(data).digest()).digest()

def wif_to_privkey(wif: str) -> bytes | None:
    try:
        decoded = base58.b58decode(wif)
        raw = decoded[1:-4]
        if len(raw) == 33 and raw[-1] == 0x01:
            raw = raw[:-1]
        if len(raw) != 32:
            return None
        return raw
    except:
        return None

def privkey_to_pubkey(priv: bytes, compressed=True) -> bytes | None:
    try:
        sk = ecdsa.SigningKey.from_string(priv, curve=ecdsa.SECP256k1)
        vk = sk.get_verifying_key()
        raw = vk.to_string()
        if compressed:
            prefix = b'\x03' if raw[32] & 1 else b'\x02'
            return prefix + raw[:32]
        return b'\x04' + raw
    except:
        return None

def pubkey_to_legacy(pubkey: bytes) -> str | None:
    """P2PKH — addresses starting with 1"""
    try:
        h = hash160(pubkey)
        extended = b'\x00' + h
        checksum = sha256d(extended)[:4]
        return base58.b58encode(extended + checksum).decode()
    except:
        return None

def pubkey_to_p2sh_segwit(pubkey: bytes) -> str | None:
    """P2WPKH-P2SH — addresses starting with 3"""
    try:
        h = hash160(pubkey)
        redeem = b'\x00\x14' + h          # OP_0 PUSH20 <hash>
        script_hash = hash160(redeem)
        extended = b'\x05' + script_hash
        checksum = sha256d(extended)[:4]
        return base58.b58encode(extended + checksum).decode()
    except:
        return None

def pubkey_to_bech32(pubkey: bytes, hrp='bc') -> str | None:
    """P2WPKH — native SegWit bc1..."""
    try:
        h = hash160(pubkey)
        converted = bech32.convertbits(h, 8, 5)
        return bech32.bech32_encode(hrp, [0] + converted)
    except:
        return None

def derive_all_addresses(pubkey: bytes) -> dict:
    return {
        'legacy':     pubkey_to_legacy(pubkey),
        'p2sh_segwit': pubkey_to_p2sh_segwit(pubkey),
        'bech32':     pubkey_to_bech32(pubkey),
    }

def compress_wif(uncompressed_wif: str) -> str | None:
    """Convert uncompressed WIF (starts with 5) → compressed WIF (K or L)"""
    try:
        decoded = base58.b58decode(uncompressed_wif)
        priv = decoded[1:-4]
        extended = b'\x80' + priv + b'\x01'
        checksum = sha256d(extended)[:4]
        return base58.b58encode(extended + checksum).decode()
    except:
        return None


# ════════════════════════════════════════════════════════════════════════════
# 2. KEYSTORE / WALLET REPAIR & EXTRACTION
# ════════════════════════════════════════════════════════════════════════════

class WalletExtractor:

    def __init__(self, filepath: str):
        self.filepath = filepath

    def extract(self) -> list[dict]:
        """Try multiple strategies, return list of {pubkey, privkey}"""
        print(f"[EXTRACTOR] Loading: {self.filepath}")
        content = self._read_file()
        if not content:
            return []

        keypairs = {}

        # Strategy 1: valid JSON
        keypairs.update(self._try_json(content))

        # Strategy 2: regex on raw text
        keypairs.update(self._try_regex(content))

        results = []
        for pub, priv in keypairs.items():
            if pub and priv:
                results.append({'pubkey': pub.strip(), 'privkey': priv.strip()})

        print(f"[EXTRACTOR] Found {len(results)} keypairs")
        return results

    def _read_file(self) -> str:
        try:
            with open(self.filepath, 'rb') as f:
                raw = f.read()
            try:
                return raw.decode('utf-8')
            except:
                return raw.decode('utf-8', errors='ignore')
        except Exception as e:
            print(f"[EXTRACTOR] Read error: {e}")
            return ""

    def _try_json(self, text: str) -> dict:
        """Try to parse as JSON, incrementally truncating if needed"""
        for length in [len(text)] + list(range(len(text), 0, -1000)):
            try:
                data = json.loads(text[:length])
                kp = self._dig_keypairs(data)
                if kp:
                    print(f"[EXTRACTOR] JSON strategy: {len(kp)} pairs")
                    return kp
            except:
                continue
        return {}

    def _dig_keypairs(self, data, depth=0) -> dict:
        """Recursively find keypairs dict in JSON"""
        if depth > 5:
            return {}
        if isinstance(data, dict):
            if 'keypairs' in data:
                kp = data['keypairs']
                if isinstance(kp, dict) and kp:
                    return kp
            for v in data.values():
                result = self._dig_keypairs(v, depth + 1)
                if result:
                    return result
        return {}

    def _try_regex(self, text: str) -> dict:
        """Regex extraction — handles partially corrupted files"""
        keypairs = {}

        # Uncompressed pubkey (130 hex chars) → WIF privkey
        patterns = [
            r'"([0-9a-fA-F]{128,130})"\s*:\s*"([5KL][1-9A-HJ-NP-Za-km-z]{40,60})"',
            r'"(0[4x][0-9a-fA-F]{126,128})"\s*:\s*"([5KL][1-9A-HJ-NP-Za-km-z]{40,60})"',
            r'"([0-9a-fA-F]{64,66})"\s*:\s*"([5KL][1-9A-HJ-NP-Za-km-z]{40,60})"',
        ]
        for pat in patterns:
            for pub, priv in re.findall(pat, text):
                if pub not in keypairs:
                    keypairs[pub] = priv

        print(f"[EXTRACTOR] Regex strategy: {len(keypairs)} pairs")
        return keypairs


# ════════════════════════════════════════════════════════════════════════════
# 3. CSV / TEXT KEY LOADER
# ════════════════════════════════════════════════════════════════════════════

def load_from_csv(filepath: str) -> list[dict]:
    """Load keypairs from CSV produced by previous recovery scripts"""
    results = []
    try:
        open_fn = gzip.open if filepath.endswith('.gz') else open
        with open_fn(filepath, 'rt', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                priv = (row.get('Private Key (WIF)', '') or
                        row.get('private_key', '') or
                        row.get('privkey', '')).strip()
                pub  = (row.get('Public Key', '') or
                        row.get('public_key', '') or
                        row.get('pubkey', '')).strip()
                if priv:
                    results.append({'pubkey': pub, 'privkey': priv})
    except Exception as e:
        print(f"[CSV] Error: {e}")
    print(f"[CSV] Loaded {len(results)} keys from {filepath}")
    return results

def load_from_txt(filepath: str) -> list[dict]:
    """Load raw WIF keys, one per line"""
    results = []
    try:
        with open(filepath, 'r') as f:
            for line in f:
                key = line.strip()
                if key.startswith(('5', 'K', 'L')) and len(key) >= 40:
                    results.append({'pubkey': '', 'privkey': key})
    except Exception as e:
        print(f"[TXT] Error: {e}")
    print(f"[TXT] Loaded {len(results)} keys from {filepath}")
    return results


# ════════════════════════════════════════════════════════════════════════════
# 4. KEY PROCESSOR — normalize all keys, derive all addresses
# ════════════════════════════════════════════════════════════════════════════

def process_keypairs(raw_pairs: list[dict]) -> list[dict]:
    """
    Input:  [{pubkey, privkey}]
    Output: [{privkey_orig, privkey_compressed, pubkey_compressed,
              addr_legacy, addr_p2sh, addr_bech32}]
    """
    processed = []
    skipped = 0

    for item in raw_pairs:
        priv_orig = item.get('privkey', '').strip()
        pub_raw   = item.get('pubkey', '').strip()

        if not priv_orig:
            skipped += 1
            continue

        # Compress uncompressed WIF
        if priv_orig.startswith('5'):
            priv_compressed = compress_wif(priv_orig)
        elif priv_orig.startswith(('K', 'L')):
            priv_compressed = priv_orig
        else:
            skipped += 1
            continue

        if not priv_compressed:
            skipped += 1
            continue

        # Derive compressed public key from private key
        priv_bytes = wif_to_privkey(priv_compressed)
        if not priv_bytes:
            skipped += 1
            continue

        pubkey_bytes = privkey_to_pubkey(priv_bytes, compressed=True)
        if not pubkey_bytes:
            skipped += 1
            continue

        addrs = derive_all_addresses(pubkey_bytes)

        processed.append({
            'privkey_orig':       priv_orig,
            'privkey_compressed': priv_compressed,
            'pubkey_compressed':  pubkey_bytes.hex(),
            'addr_legacy':        addrs['legacy'],
            'addr_p2sh':          addrs['p2sh_segwit'],
            'addr_bech32':        addrs['bech32'],
        })

    print(f"[PROCESSOR] Processed: {len(processed)} | Skipped: {skipped}")
    return processed


# ════════════════════════════════════════════════════════════════════════════
# 5. HD DERIVATION (seed / xpub scanning)
# ════════════════════════════════════════════════════════════════════════════

def derive_addresses_from_seed(mnemonic: str, count=DERIVE_COUNT) -> list[dict]:
    """Derive addresses across all known paths from a BIP39 seed"""
    if not HAS_BIP_UTILS:
        print("[SEED] bip_utils not available — skipping seed derivation")
        return []

    results = []
    try:
        seed_bytes = Bip39SeedGenerator(mnemonic).Generate()
    except Exception as e:
        print(f"[SEED] Seed generation failed: {e}")
        return []

    for path_name, path in DERIVATION_PATHS.items():
        try:
            master = Bip32Slip10Secp256k1.FromSeed(seed_bytes)
            # Parse path
            parts = path.replace("m/", "").split("/")
            node = master
            for part in parts:
                if not part:
                    continue
                hardened = part.endswith("'")
                idx = int(part.rstrip("'"))
                if hardened:
                    node = node.ChildKey(idx + 0x80000000)
                else:
                    node = node.ChildKey(idx)

            # Derive receiving (0) and change (1) addresses
            for change in [0, 1]:
                change_node = node.ChildKey(change)
                for i in range(count):
                    child = change_node.ChildKey(i)
                    pub_bytes = child.PublicKey().RawCompressed().ToBytes()
                    addrs = derive_all_addresses(pub_bytes)
                    results.append({
                        'path':       f"{path}/{change}/{i}",
                        'path_name':  path_name,
                        'pubkey':     pub_bytes.hex(),
                        'addr_legacy':  addrs['legacy'],
                        'addr_p2sh':    addrs['p2sh_segwit'],
                        'addr_bech32':  addrs['bech32'],
                    })
        except Exception as e:
            # Some paths won't be valid for all wallets, skip silently
            continue

    print(f"[SEED] Derived {len(results)} addresses across {len(DERIVATION_PATHS)} paths")
    return results


# ════════════════════════════════════════════════════════════════════════════
# 6. COMPRESSED CACHE (SQLite + zlib)
# ════════════════════════════════════════════════════════════════════════════

class Cache:
    def __init__(self, db_path=CACHE_DB):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS addr_cache (
                address     TEXT PRIMARY KEY,
                data_gz     BLOB,
                balance_sat INTEGER,
                has_history INTEGER,
                checked_at  INTEGER
            )
        """)
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS utxo_cache (
                address     TEXT PRIMARY KEY,
                utxos_gz    BLOB,
                checked_at  INTEGER
            )
        """)
        self.conn.commit()
        stats = self.conn.execute("SELECT COUNT(*) FROM addr_cache").fetchone()[0]
        print(f"[CACHE] Loaded — {stats} cached addresses")

    def get_addr(self, address: str):
        row = self.conn.execute(
            "SELECT data_gz, balance_sat, has_history FROM addr_cache WHERE address=?",
            (address,)
        ).fetchone()
        if row:
            data = json.loads(zlib.decompress(row[0]))
            return data, row[1], bool(row[2])
        return None, None, None

    def set_addr(self, address: str, data: dict, balance_sat: int, has_history: bool):
        compressed = zlib.compress(json.dumps(data).encode(), level=6)
        self.conn.execute("""
            INSERT OR REPLACE INTO addr_cache VALUES (?,?,?,?,strftime('%s','now'))
        """, (address, compressed, balance_sat, int(has_history)))
        self.conn.commit()

    def get_utxos(self, address: str):
        row = self.conn.execute(
            "SELECT utxos_gz FROM utxo_cache WHERE address=?", (address,)
        ).fetchone()
        if row:
            return json.loads(zlib.decompress(row[0]))
        return None

    def set_utxos(self, address: str, utxos: list):
        compressed = zlib.compress(json.dumps(utxos).encode(), level=6)
        self.conn.execute("""
            INSERT OR REPLACE INTO utxo_cache VALUES (?,?,strftime('%s','now'))
        """, (address, compressed))
        self.conn.commit()

    def stats(self) -> dict:
        total    = self.conn.execute("SELECT COUNT(*) FROM addr_cache").fetchone()[0]
        with_bal = self.conn.execute(
            "SELECT COUNT(*) FROM addr_cache WHERE balance_sat > 0"
        ).fetchone()[0]
        with_hist = self.conn.execute(
            "SELECT COUNT(*) FROM addr_cache WHERE has_history = 1"
        ).fetchone()[0]
        return {'total': total, 'with_balance': with_bal, 'with_history': with_hist}


# ════════════════════════════════════════════════════════════════════════════
# 7. ESPLORA API CLIENT (gzip compression, rate limited)
# ════════════════════════════════════════════════════════════════════════════

class EsploraClient:
    def __init__(self, base_url=ESPLORA_BASE):
        self.base = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'Accept-Encoding': 'gzip, deflate',
            'User-Agent':      'btc-recovery-bot/2.0',
        })
        self._call_count = 0

    def _get(self, path: str, retries=3):
        url = f"{self.base}{path}"
        for attempt in range(retries):
            try:
                r = self.session.get(url, timeout=15)
                self._call_count += 1
                if r.status_code == 200:
                    return r
                elif r.status_code == 429:
                    wait = 5 * (attempt + 1)
                    print(f"[API] Rate limited — waiting {wait}s")
                    time.sleep(wait)
                else:
                    return r
            except requests.exceptions.RequestException as e:
                if attempt < retries - 1:
                    time.sleep(2)
                else:
                    print(f"[API] Failed {url}: {e}")
        return None

    def get_address_info(self, address: str) -> dict | None:
        r = self._get(f"/address/{address}")
        if r and r.status_code == 200:
            return r.json()
        return None

    def get_utxos(self, address: str) -> list | None:
        r = self._get(f"/address/{address}/utxo")
        if r and r.status_code == 200:
            return r.json()
        if r and r.status_code == 400:
            # Too many entries — reconstruct from history
            return self._reconstruct_utxos(address)
        return None

    def _reconstruct_utxos(self, address: str) -> list:
        """Reconstruct UTXO set from tx history for high-activity addresses"""
        print(f"[API] Reconstructing UTXOs from history for {address[:20]}...")
        funded = {}
        spent  = set()
        last   = None

        while True:
            path = f"/address/{address}/txs"
            if last:
                path += f"/chain/{last}"
            r = self._get(path)
            if not r or r.status_code != 200:
                break
            txs = r.json()
            if not txs:
                break

            for tx in txs:
                txid = tx['txid']
                for i, vout in enumerate(tx.get('vout', [])):
                    if vout.get('scriptpubkey_address') == address:
                        funded[f"{txid}:{i}"] = vout.get('value', 0)
                for vin in tx.get('vin', []):
                    if vin.get('txid'):
                        spent.add(f"{vin['txid']}:{vin['vout']}")

            last = txs[-1]['txid']
            time.sleep(0.5)

            if len(txs) < 25:
                break

        return [
            {'txid': k.split(':')[0], 'vout': int(k.split(':')[1]), 'value': v}
            for k, v in funded.items()
            if k not in spent
        ]

    def get_tx_history(self, address: str) -> list:
        r = self._get(f"/address/{address}/txs")
        return r.json() if r and r.status_code == 200 else []

    def broadcast_tx(self, raw_hex: str) -> str | None:
        url = f"{self.base}/tx"
        try:
            r = self.session.post(url, data=raw_hex, timeout=15)
            if r.status_code == 200:
                return r.text.strip()
            else:
                print(f"[API] Broadcast failed: {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"[API] Broadcast error: {e}")
        return None

    def call_count(self) -> int:
        return self._call_count


# ════════════════════════════════════════════════════════════════════════════
# 8. SCANNER — ties cache + API together
# ════════════════════════════════════════════════════════════════════════════

class Scanner:
    def __init__(self, cache: Cache, client: EsploraClient):
        self.cache  = cache
        self.client = client
        self.found  = []   # addresses with balance or history

    def scan_address(self, address: str, metadata: dict = None) -> dict | None:
        if not address or address in ('None', 'conversion_failed'):
            return None

        # Cache hit
        data, bal_sat, has_hist = self.cache.get_addr(address)
        if data is not None:
            if bal_sat > 0 or has_hist:
                return self._make_result(address, bal_sat, has_hist, metadata, cached=True)
            return None

        # API call
        info = self.client.get_address_info(address)
        if not info:
            return None

        stats    = info.get('chain_stats', {})
        m_stats  = info.get('mempool_stats', {})
        funded   = stats.get('funded_txo_sum', 0) + m_stats.get('funded_txo_sum', 0)
        spent    = stats.get('spent_txo_sum',  0) + m_stats.get('spent_txo_sum',  0)
        tx_count = stats.get('tx_count', 0)        + m_stats.get('tx_count', 0)

        bal_sat   = funded - spent
        has_hist  = tx_count > 0

        self.cache.set_addr(address, info, bal_sat, has_hist)

        if bal_sat > 0 or has_hist:
            return self._make_result(address, bal_sat, has_hist, metadata)
        return None

    def _make_result(self, address, bal_sat, has_hist, metadata, cached=False) -> dict:
        result = {
            'address':    address,
            'balance_btc': bal_sat / 1e8,
            'balance_sat': bal_sat,
            'has_history': has_hist,
            'cached':      cached,
        }
        if metadata:
            result.update(metadata)
        return result

    def scan_all(self, entries: list[dict], progress=True) -> list[dict]:
        """
        entries: list of dicts with at least one of
                 addr_legacy / addr_p2sh / addr_bech32
                 plus optional metadata (privkey_compressed, path, etc.)
        """
        total    = len(entries) * 3   # 3 addr types per entry
        checked  = 0
        hits     = []

        print(f"\n[SCANNER] Scanning {len(entries)} keypairs × 3 addr types = {total} addresses")
        print(f"[SCANNER] Cache has {self.cache.stats()['total']} pre-checked addresses\n")

        for i, entry in enumerate(entries):
            meta = {k: v for k, v in entry.items()
                    if k not in ('addr_legacy', 'addr_p2sh', 'addr_bech32')}

            for addr_type in ('addr_legacy', 'addr_p2sh', 'addr_bech32'):
                addr = entry.get(addr_type)
                result = self.scan_address(addr, {**meta, 'addr_type': addr_type})
                if result:
                    hits.append(result)
                    bal = result['balance_btc']
                    sym = '💰' if bal > 0 else '📜'
                    print(f"{sym} {addr_type:12} {addr} | {bal:.8f} BTC | hist={result['has_history']}")

                checked += 1

                # Rate limiting
                if checked % BATCH_SIZE == 0:
                    if progress:
                        pct = (checked / total) * 100
                        print(f"[SCANNER] Progress: {checked}/{total} ({pct:.1f}%) | "
                              f"Hits: {len(hits)} | API calls: {self.client.call_count()}")
                    time.sleep(1)
                else:
                    time.sleep(API_DELAY)

        self.found = hits
        return hits

    def fetch_utxos_for_hits(self):
        """After scanning, pull UTXOs for all addresses with balance"""
        utxo_map = {}
        for result in self.found:
            if result['balance_sat'] > 0:
                addr = result['address']
                cached = self.cache.get_utxos(addr)
                if cached is not None:
                    utxo_map[addr] = cached
                else:
                    utxos = self.client.get_utxos(addr)
                    if utxos:
                        self.cache.set_utxos(addr, utxos)
                        utxo_map[addr] = utxos
                time.sleep(API_DELAY)
        return utxo_map


# ════════════════════════════════════════════════════════════════════════════
# 9. REPORTING
# ════════════════════════════════════════════════════════════════════════════

def save_results(hits: list[dict], utxos: dict, outfile=RESULTS_FILE):
    if not hits:
        print("\n[REPORT] No addresses with funds or history found.")
        return

    # Sort: balances first, then history-only
    hits_sorted = sorted(hits, key=lambda x: x['balance_sat'], reverse=True)

    with open(outfile, 'w', newline='', encoding='utf-8') as f:
        fieldnames = ['address', 'addr_type', 'balance_btc', 'balance_sat',
                      'has_history', 'privkey_compressed', 'path', 'path_name', 'pubkey_compressed']
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(hits_sorted)

    # Also save compressed version
    gz_file = outfile + '.gz'
    with open(outfile, 'rb') as f_in:
        with gzip.open(gz_file, 'wb') as f_out:
            f_out.write(f_in.read())

    # Console summary
    total_btc = sum(h['balance_sat'] for h in hits) / 1e8
    with_bal  = [h for h in hits if h['balance_sat'] > 0]
    hist_only = [h for h in hits if h['balance_sat'] == 0 and h['has_history']]

    print(f"\n{'='*60}")
    print(f"  RECOVERY REPORT")
    print(f"{'='*60}")
    print(f"  Addresses with balance:    {len(with_bal)}")
    print(f"  Addresses with history:    {len(hist_only)}")
    print(f"  Total BTC found:           {total_btc:.8f}")
    print(f"{'='*60}")

    if with_bal:
        print(f"\n  TOP BALANCES:")
        for h in with_bal[:20]:
            print(f"    {h['address']:42} {h['balance_btc']:.8f} BTC  [{h.get('addr_type','')}]")

    if utxos:
        print(f"\n  SPENDABLE UTXOs:")
        for addr, uxs in utxos.items():
            total_val = sum(u['value'] for u in uxs) / 1e8
            print(f"    {addr[:42]}  {len(uxs)} UTXOs  {total_val:.8f} BTC")
            for u in uxs[:5]:
                print(f"      txid: {u['txid']}  vout:{u['vout']}  val:{u['value']} sat")

    print(f"\n  Results saved to: {outfile}")
    print(f"  Compressed copy:  {gz_file}")


# ════════════════════════════════════════════════════════════════════════════
# 10. MAIN ORCHESTRATOR
# ════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="BTC Wallet Recovery Bot — complete pipeline"
    )
    parser.add_argument('--wallet', help='Electrum wallet file (.dat / .txt / .json)')
    parser.add_argument('--csv',    help='Keypair CSV file (from previous recovery)')
    parser.add_argument('--keys',   help='Plain text file of WIF private keys')
    parser.add_argument('--seed',   help='BIP39 mnemonic seed phrase (in quotes)')
    parser.add_argument('--xpub',   help='Extended public key (xpub)')
    parser.add_argument('--cache',  default=CACHE_DB, help='SQLite cache file path')
    parser.add_argument('--out',    default=RESULTS_FILE, help='Output CSV file')
    parser.add_argument('--limit',  type=int, default=0, help='Limit keys processed (0=all)')
    args = parser.parse_args()

    if not any([args.wallet, args.csv, args.keys, args.seed, args.xpub]):
        parser.print_help()
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  BTC RECOVERY BOT — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    cache  = Cache(args.cache)
    client = EsploraClient()
    scanner = Scanner(cache, client)

    all_entries = []  # unified list for scanner

    # ── WALLET FILE ──────────────────────────────────────────────────────
    if args.wallet:
        extractor = WalletExtractor(args.wallet)
        raw_pairs = extractor.extract()
        processed = process_keypairs(raw_pairs)
        all_entries.extend(processed)

    # ── CSV ──────────────────────────────────────────────────────────────
    if args.csv:
        raw = load_from_csv(args.csv)
        processed = process_keypairs(raw)
        all_entries.extend(processed)

    # ── TXT KEYS ─────────────────────────────────────────────────────────
    if args.keys:
        raw = load_from_txt(args.keys)
        processed = process_keypairs(raw)
        all_entries.extend(processed)

    # ── SEED PHRASE ──────────────────────────────────────────────────────
    if args.seed:
        derived = derive_addresses_from_seed(args.seed, count=DERIVE_COUNT)
        # derived entries already have addr fields, no privkey
        all_entries.extend(derived)

    # Apply limit
    if args.limit and args.limit > 0:
        all_entries = all_entries[:args.limit]
        print(f"[MAIN] Limiting to {args.limit} entries")

    if not all_entries:
        print("[MAIN] No entries to scan. Check your input files.")
        sys.exit(1)

    print(f"[MAIN] Total entries to scan: {len(all_entries)}")

    # ── SCAN ─────────────────────────────────────────────────────────────
    hits = scanner.scan_all(all_entries)

    # ── FETCH UTXOs FOR HITS ─────────────────────────────────────────────
    utxos = {}
    if hits:
        print(f"\n[MAIN] Fetching UTXOs for {len([h for h in hits if h['balance_sat']>0])} addresses with balance...")
        utxos = scanner.fetch_utxos_for_hits()

    # ── REPORT ───────────────────────────────────────────────────────────
    save_results(hits, utxos, args.out)

    print(f"\n[MAIN] Total API calls made: {client.call_count()}")
    print(f"[MAIN] Cache stats: {cache.stats()}")
    print(f"\n✅ Done.\n")


if __name__ == "__main__":
    main()

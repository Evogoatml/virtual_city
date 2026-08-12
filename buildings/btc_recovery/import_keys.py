"""Import plain-text private keys and seed phrases."""
import re
from pathlib import Path
from city.db import now_iso


WIF_PATTERN = re.compile(r"[5KL][1-9A-HJ-NP-Za-km-z]{50,51}")
HEX_PATTERN = re.compile(r"\b[0-9a-fA-F]{64}\b")


def import_keys_file(store, filepath):
    """Scan a text file for WIF/hex private keys."""
    path = Path(filepath)
    if not path.exists():
        return {"error": f"not found: {filepath}"}

    text = path.read_text()
    now = now_iso()

    wifs = WIF_PATTERN.findall(text)
    hexs = HEX_PATTERN.findall(text)
    added = 0

    for wif in wifs:
        store.conn.execute(
            """INSERT OR IGNORE INTO btc_private_keys
               (address, wif, source_file, imported_at)
               VALUES (?, ?, ?, ?)""",
            (f"wif:{wif[:16]}...", wif, str(path.name), now),
        )
        if store.conn.total_changes:
            added += 1
        store.conn.commit()

    for hk in hexs:
        store.conn.execute(
            """INSERT OR IGNORE INTO btc_private_keys
               (address, hex_priv, source_file, imported_at)
               VALUES (?, ?, ?, ?)""",
            (f"hex:{hk[:16]}...", hk, str(path.name), now),
        )
        store.conn.commit()

    return {
        "file": path.name,
        "wif_found": len(wifs),
        "hex_found": len(hexs),
        "keypairs_added": added,
    }


def import_seed_file(store, filepath):
    """Import a seed phrase from a text file."""
    path = Path(filepath)
    if not path.exists():
        return {"error": f"not found: {filepath}"}
    text = path.read_text().strip()
    now = now_iso()
    store.conn.execute(
        "INSERT INTO btc_seeds (seed, source_file, imported_at) VALUES (?, ?, ?)",
        (text, str(path.name), now),
    )
    store.conn.commit()
    return {"file": path.name, "seed_imported": True}


def detect_and_import(store, filepath):
    """Try to detect file type and import accordingly."""
    path = Path(filepath)
    if not path.exists():
        return {"error": f"not found: {filepath}"}

    if path.suffix == ".json":
        from . import import_electrum
        return import_electrum.import_electrum(store, filepath)

    content = path.read_text()
    words = content.split()

    # seed detection: 12-24 words
    if 12 <= len(words) <= 24 and is_probable_seed(words):
        return import_seed_file(store, filepath)

    # fallback: try keys
    return import_keys_file(store, filepath)


def is_probable_seed(words):
    """Rough check: seeds are mostly lowercase alpha words under 9 chars."""
    return all(
        len(w) <= 8 and all(c.islower() for c in w if c.isalpha())
        for w in words[:5]
    )
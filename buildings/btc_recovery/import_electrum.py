"""Import Electrum JSON wallets into the store."""
import json
from pathlib import Path
from city.db import now_iso
from . import store


def import_electrum(store, filepath):
    """Parse any Electrum JSON wallet, insert addresses + keypairs."""
    path = Path(filepath)
    if not path.exists():
        return {"error": f"not found: {filepath}"}

    with open(path) as f:
        wallet = json.load(f)

    addr_map = wallet.get("addresses", {})
    keystore = wallet.get("keystore", {})
    keypairs = keystore.get("keypairs", {})

    now = now_iso()
    imported = 0

    for address, info in addr_map.items():
        if not isinstance(info, dict):
            continue
        store.conn.execute(
            """INSERT OR IGNORE INTO btc_addresses
               (address, pubkey, addr_type, wallet_source, imported_at)
               VALUES (?, ?, ?, ?, ?)""",
            (address, info.get("pubkey", ""),
             info.get("type", "p2pkh"), str(path.name), now),
        )
        if store.conn.total_changes:
            imported += 1
        store.conn.commit()

    pk_added = 0
    for pubkey_hex, wif in keypairs.items():
        store.conn.execute(
            """INSERT OR IGNORE INTO btc_private_keys
               (address, wif, source_file, imported_at)
               VALUES (?, ?, ?, ?)""",
            (_pubkey_to_addr(pubkey_hex), wif, str(path.name), now),
        )
        if store.conn.total_changes:
            pk_added += 1
        store.conn.commit()

    return {
        "wallet": path.name,
        "addresses_added": imported,
        "keypairs_added": pk_added,
    }


def _pubkey_to_addr(pubkey_hex):
    """Placeholder: derive p2pkh from hex pubkey.
    Replace with python-bitcoinlib for real derivation."""
    return None
import os
import re
import json
import hashlib
import requests
from pathlib import Path
from typing import List, Dict, Tuple

# ================= CONFIG =================
import sys
def get_root_folder():
    env = os.environ.get('BTCTOOL_ROOT_FOLDER')
    if env:
        return Path(os.path.expanduser(env))
    if len(sys.argv) > 1:
        return Path(sys.argv[1])
    return Path('.')
ROOT_FOLDER = get_root_folder()
OUTPUT_FILE = "found_wallets_report.txt"

# Regex patterns for common key formats
WIF_PATTERN = re.compile(r'(5[KL][1-9A-HJ-NP-Za-km-z]{50,51}|[KL][1-9A-HJ-NP-Za-km-z]{51})')
HEX_PATTERN = re.compile(r'\b([0-9a-fA-F]{64})\b')
SEED_PATTERN = re.compile(r'\b(?:[a-z]+(?:\s+[a-z]+){11,23})\b')  # 12 or 24 words

def is_valid_wif(wif: str) -> bool:
    # Basic checksum validation (very quick filter)
    try:
        decoded = base58.b58decode_check(wif)
        return len(decoded) in (37, 38)  # uncompressed or compressed
    except:
        return False

def derive_address_from_wif(wif: str) -> str:
    """Very simplified — returns P2PKH address for quick check"""
    try:
        from bitcoinlib.keys import HDKey
        key = HDKey.from_wif(wif)
        return key.address()
    except:
        return "ERROR_DERIVING"

def check_balance(address: str) -> int:
    """Check live balance via mempool.space API"""
    try:
        r = requests.get(f"https://mempool.space/api/address/{address}", timeout=10)
        data = r.json()
        return data.get('chain_stats', {}).get('funded_txo_sum', 0)
    except:
        return 0

def scan_file(file_path: Path) -> List[Dict]:
    hits = []
    try:
        content = file_path.read_text(errors='ignore')
    except:
        try:
            content = file_path.read_bytes().decode('utf-8', errors='ignore')
        except:
            return hits

    # Find WIF keys
    for match in WIF_PATTERN.finditer(content):
        wif = match.group(0)
        if is_valid_wif(wif):
            addr = derive_address_from_wif(wif)
            balance = check_balance(addr)
            hits.append({
                'type': 'WIF',
                'value': wif,
                'address': addr,
                'balance_sats': balance,
                'file': str(file_path)
            })

    # Find hex private keys
    for match in HEX_PATTERN.finditer(content):
        hex_key = match.group(0).lower()
        # Quick filter: try to derive address
        try:
            from bitcoinlib.keys import Key
            key = Key(hex_key)
            addr = key.address()
            balance = check_balance(addr)
            if balance > 0 or True:  # keep all for review
                hits.append({
                    'type': 'HEX',
                    'value': hex_key,
                    'address': addr,
                    'balance_sats': balance,
                    'file': str(file_path)
                })
        except:
            pass

    return hits

def main():
    root = Path(ROOT_FOLDER)
    if not root.exists():
        print(f"Folder not found: {root}")
        return

    print(f"Starting scan of: {root}")
    print("This may take a while if the folder is large...\n")

    all_hits = []
    for file_path in root.rglob("*"):
        if file_path.is_file() and file_path.suffix.lower() in ['.txt', '.dat', '.json', '.csv', '.log', '.bak', '.wallet', '']:
            print(f"Scanning: {file_path.name}")
            hits = scan_file(file_path)
            all_hits.extend(hits)

    # Write report
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"Wallet Hunter Report - {len(all_hits)} potential keys found\n")
        f.write("="*80 + "\n\n")
        for hit in all_hits:
            f.write(f"Type     : {hit['type']}\n")
            f.write(f"File     : {hit['file']}\n")
            f.write(f"Address  : {hit['address']}\n")
            f.write(f"Balance  : {hit['balance_sats']:,} sats ({hit['balance_sats']/100_000_000:.8f} BTC)\n")
            f.write("-"*60 + "\n\n")

    print(f"\nScan complete! Report saved to: {OUTPUT_FILE}")
    print(f"Total potential keys found: {len(all_hits)}")

    # Show hits with balance
    funded = [h for h in all_hits if h['balance_sats'] > 0]
    if funded:
        print(f"\n🚨 FOUND {len(funded)} WALLETS WITH BALANCE! 🚨")
        for h in funded:
            print(f"→ {h['address']} | {h['balance_sats']/100_000_000:.8f} BTC | {h['file']}")

if __name__ == "__main__":
    main()

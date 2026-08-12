import os
import re
import hashlib
import requests
from pathlib import Path
from typing import List, Dict
import PyPDF2  # pip install PyPDF2
from docx import Document  # pip install python-docx

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
OUTPUT_FILE = "found_wallets_v2.txt"

# Expanded patterns
PATTERNS = {
    'WIF_compressed': r'(5[KL][1-9A-HJ-NP-Za-km-z]{50,51})',
    'WIF_uncompressed': r'(5[KHJ][1-9A-HJ-NP-Za-km-z]{50})',
    'mini_key': r'^S[1-9A-HJ-NP-Za-km-z]{21,22}$',  # mini private keys
    'hex_64': r'\b([0-9a-fA-F]{64})\b',
    'bip39_12': r'\b(?:\w+\s+){11}\w+\b',   # 12 words
    'bip39_24': r'\b(?:\w+\s+){23}\w+\b',   # 24 words
    'bip38_enc': r'^6P[1-9A-HJ-NP-Za-km-z]{56}$',  # encrypted BIP38
}

def extract_text_from_file(path: Path) -> str:
    """Try to get readable text from any file type"""
    ext = path.suffix.lower()
    try:
        if ext in ['.txt', '.log', '.csv', '.json', '.bak', '']:
            return path.read_text(errors='ignore')
        elif ext == '.pdf':
            with open(path, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                return '\n'.join(page.extract_text() or '' for page in reader.pages)
        elif ext == '.docx':
            doc = Document(path)
            return '\n'.join(p.text for p in doc.paragraphs)
        else:
            # Binary fallback - last resort
            return path.read_bytes().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Error reading {path}: {e}")
        return ""

def check_balance(address: str) -> int:
    """Check live balance via mempool.space API"""
    try:
        r = requests.get(f"https://mempool.space/api/address/{address}", timeout=8)
        r.raise_for_status()
        data = r.json()
        return data.get('chain_stats', {}).get('funded_txo_sum', 0)
    except Exception as e:
        print(f"Balance check failed for {address}: {e}")
        return -1  # error

def scan_and_report():
    root = Path(ROOT_FOLDER)
    if not root.exists():
        print(f"Folder missing: {root}")
        return

    print(f"Scanning: {root} (recursive)")
    print("This may take a while...\n")

    all_hits = []
    for file_path in root.rglob("*"):
        if not file_path.is_file():
            continue
        print(f"Scanning: {file_path.name}")
        text = extract_text_from_file(file_path)
        if not text.strip():
            continue

        for name, pattern in PATTERNS.items():
            for match in re.finditer(pattern, text, re.IGNORECASE | re.MULTILINE):
                value = match.group(0).strip()
                addr = "N/A"
                balance = -1

                if 'WIF' in name:
                    addr = "Possible P2PKH - import to Electrum/Sparrow manually"
                elif 'hex' in name:
                    addr = "HEX private key - import manually"
                elif 'bip39' in name:
                    addr = "BIP39 seed phrase detected - recover in Electrum/Sparrow (12/24 words)"
                    balance = -1  # Skip balance check for seeds
                elif 'bip38' in name:
                    addr = "BIP38 encrypted - needs passphrase"

                all_hits.append({
                    'type': name,
                    'value': value,
                    'file': str(file_path),
                    'address': addr,
                    'balance': balance
                })

    # Save report
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(f"Wallet Hunter v2 Report - {len(all_hits)} potential hits\n")
        f.write("="*80 + "\n\n")
        for h in all_hits:
            f.write(f"Type     : {h['type']}\n")
            f.write(f"File     : {h['file']}\n")
            f.write(f"Value    : {h['value']}\n")
            f.write(f"Address  : {h['address']}\n")
            if h['balance'] >= 0:
                f.write(f"Balance  : {h['balance']:,} sats ({h['balance']/100_000_000:.8f} BTC)\n")
            else:
                f.write("Balance  : N/A (not checked)\n")
            f.write("-"*60 + "\n\n")

    print(f"\nScan complete! Report saved to: {OUTPUT_FILE}")
    print(f"Found {len(all_hits)} possible keys/seeds. Open the txt file and look for real-looking ones.")

    funded = [h for h in all_hits if h['balance'] > 0]
    if funded:
        print(f"\n🚨 FOUND {len(funded)} ENTRIES WITH POSSIBLE BALANCE! 🚨")
        for h in funded:
            print(f"→ {h['address']} | {h['balance']/100_000_000:.8f} BTC | {h['file']}")

if __name__ == "__main__":
    scan_and_report()

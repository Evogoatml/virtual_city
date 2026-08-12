# bitcoin_key_orchestrator.py
# Full key/seed hunter + extractor + balance checker
# Run: python bitcoin_key_orchestrator.py

import os
import re
import json
import hashlib
import base58
import requests
from pathlib import Path
from typing import List, Dict
import binascii
from ecdsa import SigningKey, SECP256k1
import PyPDF2
from docx import Document
from datetime import datetime
import time

import os
# ================= CONFIG =================
ROOT_FOLDERS = [
    Path(os.getenv("BTC_ORCHESTRATOR_ROOT", ".")),
]

OUTPUT_REPORT = f"orchestrator_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
MAX_FILE_SIZE_MB = 50

# Patterns
PATTERNS = {
    'WIF_compressed': r'\b(5[KL][1-9A-HJ-NP-Za-km-z]{50,51})\b',
    'WIF_uncompressed': r'\b(5[KHJ][1-9A-HJ-NP-Za-km-z]{50})\b',
    'mini_key': r'\bS[1-9A-HJ-NP-Za-km-z]{21,22}\b',
    'hex_privkey': r'\b[0-9a-fA-F]{64}\b',
    'bip38': r'\b6P[1-9A-HJ-NP-Za-km-z]{56}\b',
    'hash160': r'\b[0-9a-fA-F]{40}\b',
    'script_pubkey_p2pkh': r'\b76a914[0-9a-f]{40}88ac\b',
}

def extract_text(path: Path) -> str:
    """Extract readable text from file"""
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
            return path.read_bytes().decode('utf-8', errors='ignore')
    except Exception as e:
        print(f"Extract error {path}: {e}")
        return ""

def derive_p2pkh_from_hex(hex_priv: str) -> str:
    try:
        priv_bytes = binascii.unhexlify(hex_priv)
        sk = SigningKey.from_string(priv_bytes, curve=SECP256k1)
        vk = sk.verifying_key
        pubkey = b'\x02' + vk.to_string()[:32] if vk.to_string()[32] % 2 == 0 else b'\x03' + vk.to_string()[:32]
        sha = hashlib.sha256(pubkey).digest()
        ripemd = hashlib.new('ripemd160', sha).digest()
        extended = b'\x00' + ripemd
        checksum = hashlib.sha256(hashlib.sha256(extended).digest()).digest()[:4]
        return base58.b58encode(extended + checksum).decode()
    except:
        return "INVALID"

def derive_p2pkh_from_script_pubkey(script_hex: str) -> str:
    try:
        script = binascii.unhexlify(script_hex)
        if script.startswith(b'\x76\xa9\x14') and script.endswith(b'\x88\xac'):
            hash160 = script[3:23]
            extended = b'\x00' + hash160
            checksum = hashlib.sha256(hashlib.sha256(extended).digest()).digest()[:4]
            return base58.b58encode(extended + checksum).decode()
        return "INVALID_SCRIPT"
    except:
        return "INVALID_SCRIPT"

def check_balance(addr: str) -> int:
    """Check balance with rate limiting"""
    try:
        time.sleep(0.8)  # 800ms delay to avoid 429
        r = requests.get(f"https://mempool.space/api/address/{addr}", timeout=5)
        r.raise_for_status()
        return r.json()['chain_stats']['funded_txo_sum']
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 429:
            print(f"Rate limit hit on {addr} - sleeping 30s")
            time.sleep(30)
            return check_balance(addr)  # retry
        return -1
    except Exception as e:
        print(f"Balance check error for {addr}: {e}")
        return -1

def extract_keys_from_text(text: str, file_path: str, hits: List[Dict]):
    for name, pattern in PATTERNS.items():
        for match in re.finditer(pattern, text):
            value = match.group(0).strip()
            addr = "N/A"
            balance = -1

            if 'WIF' in name:
                addr = "WIF - sweep manually"
            elif 'hex_privkey' in name:
                addr = derive_p2pkh_from_hex(value)
                balance = check_balance(addr) if addr != "INVALID" else -1
            elif 'hash160' in name:
                extended = b'\x00' + binascii.unhexlify(value)
                checksum = hashlib.sha256(hashlib.sha256(extended).digest()).digest()[:4]
                addr = base58.b58encode(extended + checksum).decode()
                balance = check_balance(addr)
            elif 'script_pubkey_p2pkh' in name:
                addr = derive_p2pkh_from_script_pubkey(value)
                balance = check_balance(addr) if addr != "INVALID_SCRIPT" else -1

            if value:
                hits.append({
                    'type': name,
                    'value': value,
                    'file': file_path,
                    'address': addr,
                    'balance_sats': balance
                })

def scan_file(file_path: Path, hits: List[Dict]):
    if file_path.stat().st_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        print(f"Skipping huge file: {file_path.name}")
        return

    print(f"Scanning: {file_path.name}")

    text = extract_text(file_path)
    if not text.strip():
        return

    # Special handling for large JSON dumps
    if 'wallet_21' in file_path.name.lower() or len(text) > 100000:
        print(f"Large JSON file - chunking...")
        lines = text.splitlines()
        chunk_size = 5000
        for i in range(0, len(lines), chunk_size):
            chunk = '\n'.join(lines[i:i+chunk_size])
            extract_keys_from_text(chunk, str(file_path), hits)
        return

    extract_keys_from_text(text, str(file_path), hits)

def main():
    print("Bitcoin Key Orchestrator v1 - Scanning...")
    print(f"Root folders: {', '.join(str(f) for f in ROOT_FOLDERS)}\n")
    
    all_hits = []
    for root in ROOT_FOLDERS:
        if not root.exists():
            print(f"Missing folder: {root}")
            continue

        for file_path in root.rglob("*"):
            if file_path.is_file():
                scan_file(file_path, all_hits)

    # Save report
    with open(OUTPUT_REPORT, 'w', encoding='utf-8') as f:
        f.write(f"Bitcoin Key Orchestrator Report - {len(all_hits)} hits\n")
        f.write("="*60 + "\n\n")
        for h in all_hits:
            f.write(f"Type     : {h['type']}\n")
            f.write(f"File     : {h['file']}\n")
            f.write(f"Value    : {h['value']}\n")
            f.write(f"Address  : {h['address']}\n")
            if h['balance_sats'] >= 0:
                f.write(f"Balance  : {h['balance_sats']:,} sats ({h['balance_sats']/1e8:.8f} BTC)\n")
            else:
                f.write("Balance  : N/A\n")
            f.write("-"*60 + "\n\n")
    
    print(f"\nScan complete! Report: {OUTPUT_REPORT}")
    
    funded = [h for h in all_hits if h['balance_sats'] > 0]
    if funded:
        print(f"\nFOUND {len(funded)} FUNDED KEYS!")
        for h in funded:
            print(f"→ {h['address']} | {h['balance_sats']/1e8:.8f} BTC | {h['file']}")
            print(f"   Sweep: {h['value'][:10]}...{h['value'][-10:]}")
    else:
        print("No funded keys found in this scan.")

if __name__ == "__main__":
    main()

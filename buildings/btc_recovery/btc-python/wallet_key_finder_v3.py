# wallet_key_finder_v3.py
# Run: python wallet_key_finder_v3.py
# Finds REAL Bitcoin keys/seeds in your files

import re
from pathlib import Path

# ROOT_FOLDER = Path("/mnt/c/Users/Willi/Documents/code/btc")  # ← your folder
import os
from pathlib import Path
def get_root_folder():
    env = os.environ.get('BTCTOOL_ROOT_FOLDER')
    if env:
        return Path(os.path.expanduser(env))
    # default to current directory
    return Path('.')
ROOT_FOLDER = get_root_folder()
OUTPUT_FILE = "real_keys_found.txt"

# Strict patterns (less false positives)
PATTERNS = {
    'WIF_compressed': r'\b(5[KL][1-9A-HJ-NP-Za-km-z]{50,51})\b',
    'WIF_uncompressed': r'\b(5[KHJ][1-9A-HJ-NP-Za-km-z]{50})\b',
    'mini_key': r'\bS[1-9A-HJ-NP-Za-km-z]{21,22}\b',
    'hex_privkey': r'\b[0-9a-fA-F]{64}\b',
    'bip38': r'\b6P[1-9A-HJ-NP-Za-km-z]{56}\b',
    'bip39_12': r'(?:\b[a-z]+\b\s+){11}\b[a-z]+\b',  # stricter: 12 words
    'bip39_24': r'(?:\b[a-z]+\b\s+){23}\b[a-z]+\b',  # stricter: 24 words
}

def is_likely_bip39(words: str) -> bool:
    # Optional: check against real BIP39 wordlist if you download it
    return len(words.split()) in (12, 24) and all(len(w) >= 3 for w in words.split())

print(f"Scanning folder: {ROOT_FOLDER}\n")

with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
    out.write("Real Bitcoin Key Finder v3 Report\n")
    out.write("="*60 + "\n\n")

    for file_path in ROOT_FOLDER.rglob("*"):
        if not file_path.is_file():
            continue

        print(f"→ Checking: {file_path.name}")

        try:
            content = file_path.read_text(errors='ignore')
        except:
            try:
                content = file_path.read_bytes().decode('utf-8', errors='ignore')
            except:
                continue

        for name, pattern in PATTERNS.items():
            for match in re.finditer(pattern, content):
                value = match.group(0).strip()

                # Extra filter for BIP39 (avoid junk)
                if 'bip39' in name and not is_likely_bip39(value):
                    continue

                print(f"  MATCH! Type: {name} | Value: {value}")
                out.write(f"Type     : {name}\n")
                out.write(f"File     : {file_path}\n")
                out.write(f"Value    : {value}\n")
                out.write("-"*60 + "\n\n")

print(f"\nScan finished. Results saved to: {OUTPUT_FILE}")
print("Open the file and look for real keys/seeds.")
print("Next: paste any promising Value lines here (redact most if paranoid).")
print("We'll validate & sweep them.")

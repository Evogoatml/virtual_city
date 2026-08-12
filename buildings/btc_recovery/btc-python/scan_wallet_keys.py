#!/usr/bin/env python3
"""
HD Wallet Key Material Scanner
Scans files/directories for seed phrases, xprv keys, raw seeds, and master key data
"""

import os
import re
import sys
import json
import hashlib
import argparse
from pathlib import Path

# ─── Patterns ───────────────────────────────────────────────────────────────

PATTERNS = {
    "xprv": {
        "regex": r'\bxprv[1-9A-HJ-NP-Za-km-z]{107,108}\b',
        "desc": "BIP32 Master/Child Extended Private Key"
    },
    "xpub": {
        "regex": r'\bxpub[1-9A-HJ-NP-Za-km-z]{107,108}\b',
        "desc": "BIP32 Extended Public Key"
    },
    "wif_compressed": {
        "regex": r'\b[KL][1-9A-HJ-NP-Za-km-z]{51}\b',
        "desc": "WIF Compressed Private Key"
    },
    "wif_uncompressed": {
        "regex": r'\b5[1-9A-HJ-NP-Za-km-z]{50}\b',
        "desc": "WIF Uncompressed Private Key"
    },
    "seed_hex_64": {
        "regex": r'\b(?:seed[_\s=:]+)?([0-9a-fA-F]{128})\b',
        "desc": "Raw 512-bit Seed (hex)"
    },
    "seed_hex_32": {
        "regex": r'\b(?:seed[_\s=:]+)?([0-9a-fA-F]{64})\b',
        "desc": "Raw 256-bit Seed or Master PrivKey (hex)"
    },
    "master_priv_label": {
        "regex": r'(?i)(master[\s_-]?priv(?:ate)?[\s_-]?key|root[\s_-]?key|m_priv|master_key)\s*[=:]+\s*([0-9a-fA-F]{64})',
        "desc": "Labeled Master Private Key"
    },
    "chain_code": {
        "regex": r'(?i)(chain[\s_-]?code|chaincode)\s*[=:]+\s*([0-9a-fA-F]{64})',
        "desc": "Chain Code (64-char hex)"
    },
    "mnemonic_12": {
        "regex": r'\b(?:[a-z]{3,8}\s+){11}[a-z]{3,8}\b',
        "desc": "Possible 12-word BIP39 Mnemonic"
    },
    "mnemonic_24": {
        "regex": r'\b(?:[a-z]{3,8}\s+){23}[a-z]{3,8}\b',
        "desc": "Possible 24-word BIP39 Mnemonic"
    },
    "bip32_path": {
        "regex": r"\bm(?:/\d+'?){2,6}\b",
        "desc": "BIP32 Derivation Path"
    },
    "pbkdf2_salt": {
        "regex": r'(?i)(pbkdf2|mnemonic\s+salt|passphrase)',
        "desc": "PBKDF2/Mnemonic Reference"
    },
    "hmac_bitcoin_seed": {
        "regex": r'(?i)(bitcoin\s+seed|hmac.{0,10}sha512)',
        "desc": "HMAC-SHA512 Bitcoin Seed Reference"
    },
}

# BIP39 wordlist subset for validation (first 100 words as sample)
BIP39_SAMPLE = set([
    "abandon","ability","able","about","above","absent","absorb","abstract",
    "absurd","abuse","access","accident","account","accuse","achieve","acid",
    "acoustic","acquire","across","act","action","actor","actress","actual",
    "adapt","add","addict","address","adjust","admit","adult","advance",
    "advice","aerobic","afford","afraid","again","age","agent","agree","ahead",
    "aim","air","airport","aisle","alarm","album","alcohol","alert","alien",
    "all","alley","allow","almost","alone","alpha","already","also","alter",
    "always","amateur","amazing","among","amount","amused","analyst","anchor",
    "ancient","anger","angle","angry","animal","ankle","announce","annual",
    "another","answer","antenna","antique","anxiety","any","apart","apology",
    "appear","apple","approve","april","arch","arctic","area","arena","argue",
    "arm","armed","armor","army","around","arrange","arrest","arrive","arrow"
])


# ─── Scanner ─────────────────────────────────────────────────────────────────

class WalletKeyScanner:
    def __init__(self, verbose=False, json_out=False, validate=False):
        self.verbose = verbose
        self.json_out = json_out
        self.validate = validate
        self.results = []
        self.scanned = 0
        self.skipped = 0

    def scan_text(self, text, source="<text>"):
        findings = []
        for key, pat in PATTERNS.items():
            matches = re.finditer(pat["regex"], text)
            for m in matches:
                finding = {
                    "type": key,
                    "desc": pat["desc"],
                    "source": source,
                    "match": m.group(0)[:80] + ("..." if len(m.group(0)) > 80 else ""),
                    "offset": m.start(),
                    "line": text[:m.start()].count('\n') + 1
                }
                # Validate mnemonic words if requested
                if self.validate and "mnemonic" in key:
                    words = m.group(0).lower().split()
                    bip39_hits = sum(1 for w in words if w in BIP39_SAMPLE)
                    finding["bip39_word_hits"] = f"{bip39_hits}/{len(words)}"
                    if bip39_hits < 3:
                        continue  # skip low-confidence mnemonic matches

                findings.append(finding)
        return findings

    def scan_file(self, filepath):
        try:
            with open(filepath, 'r', errors='replace') as f:
                text = f.read()
            self.scanned += 1
            findings = self.scan_text(text, str(filepath))
            if findings:
                self.results.append({
                    "file": str(filepath),
                    "size": os.path.getsize(filepath),
                    "findings": findings
                })
            return findings
        except (PermissionError, IsADirectoryError, OSError) as e:
            self.skipped += 1
            if self.verbose:
                print(f"  [SKIP] {filepath}: {e}")
            return []

    def scan_path(self, path):
        p = Path(path)
        if p.is_file():
            self.scan_file(p)
        elif p.is_dir():
            for root, dirs, files in os.walk(p):
                # Skip common non-useful dirs
                dirs[:] = [d for d in dirs if d not in {
                    '.git', 'node_modules', '__pycache__', '.cache',
                    'venv', '.venv', 'dist', 'build'
                }]
                for fname in files:
                    fpath = Path(root) / fname
                    ext = fpath.suffix.lower()
                    # Focus on text-like files
                    if ext in {'.py', '.js', '.ts', '.json', '.txt', '.log',
                               '.env', '.cfg', '.ini', '.yaml', '.yml', '.sh',
                               '.sql', '.db', '.csv', '.md', '.conf', '.key',
                               '.pem', '.dat', '.wallet', '.bak', '', '.enc'}:
                        self.scan_file(fpath)
                    elif ext not in {'.png', '.jpg', '.jpeg', '.gif', '.mp4',
                                     '.zip', '.tar', '.gz', '.exe', '.bin',
                                     '.so', '.pyc', '.class'}:
                        # Try unknown extensions (up to 5MB)
                        try:
                            if fpath.stat().st_size < 5_000_000:
                                self.scan_file(fpath)
                        except OSError:
                            pass
        else:
            print(f"[ERROR] Path not found: {path}")

    def report(self):
        total_findings = sum(len(r["findings"]) for r in self.results)

        if self.json_out:
            print(json.dumps({
                "scanned": self.scanned,
                "skipped": self.skipped,
                "files_with_hits": len(self.results),
                "total_findings": total_findings,
                "results": self.results
            }, indent=2))
            return

        print("\n" + "="*60)
        print(f"  SCAN COMPLETE")
        print(f"  Files scanned : {self.scanned}")
        print(f"  Files skipped : {self.skipped}")
        print(f"  Files with hits: {len(self.results)}")
        print(f"  Total findings : {total_findings}")
        print("="*60)

        for r in self.results:
            print(f"\n📄 {r['file']}  ({r['size']:,} bytes)")
            for f in r["findings"]:
                print(f"  [{f['type']}] Line {f['line']}: {f['desc']}")
                print(f"    → {f['match']}")
                if "bip39_word_hits" in f:
                    print(f"    → BIP39 hits: {f['bip39_word_hits']}")

        if not self.results:
            print("\n  No wallet key material found.")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Scan files/dirs for HD wallet master private key derivation material"
    )
    parser.add_argument("paths", nargs="+", help="Files or directories to scan")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show skipped files")
    parser.add_argument("-j", "--json", action="store_true", help="Output JSON")
    parser.add_argument("--validate", action="store_true", help="Filter mnemonic matches by BIP39 wordlist")
    args = parser.parse_args()

    scanner = WalletKeyScanner(
        verbose=args.verbose,
        json_out=args.json,
        validate=args.validate
    )

    for path in args.paths:
        print(f"[*] Scanning: {path}")
        scanner.scan_path(path)

    scanner.report()


if __name__ == "__main__":
    main()

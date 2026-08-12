#!/usr/bin/env python3
import os, sys, hashlib, binascii, csv
from datetime import datetime
from collections import Counter

def classify(s):
    s = s.strip().replace(' ', '').upper()
    if not s or len(s) < 20: return "too_short"
    if len(s) == 64 and all(c in '0123456789ABCDEF' for c in s): return "raw_hex_privkey"
    if (s.startswith('K') or s.startswith('L')) and 51 <= len(s) <= 52: return "compressed_wif"
    if s.startswith('5') and len(s) == 51: return "uncompressed_wif"
    if len(s) == 30 and s.startswith('S'): return "mini_privkey"
    words = s.split()
    if len(words) in (12,15,18,21,24) and all(w.isalpha() for w in words): return "bip39_seed_phrase"
    if s.startswith(('XPRV','XPUB','YPRV','YPUB','ZPRV','ZPUB','TPRV','TPUB')): return "hd_extended_key"
    if s.startswith(('1','3','BC1')) and 26 <= len(s) <= 62: return "bitcoin_address"
    return "unknown"

def scan_folder(path, recursive=False):
    exts = ('.txt', '.csv', '.json', '.log', '.dat')
    found = []
    if recursive:
        for root, _, fs in os.walk(path):
            for f in fs:
                if f.lower().endswith(exts):
                    found.append(os.path.join(root, f))
    else:
        for f in os.listdir(path):
            if os.path.isfile(os.path.join(path, f)) and f.lower().endswith(exts):
                found.append(os.path.join(path, f))
    return sorted(found)

def main():
    print("\nBitcoin Key Scanner")
    folder = input("Folder to scan (Enter = current): ").strip() or os.getcwd()
    recursive = input("Scan subfolders? (y/n): ").strip().lower().startswith('y')

    files = scan_folder(folder, recursive)
    if not files:
        print("No suitable files found.")
        return

    print(f"Scanning {len(files)} files...")

    lines = []
    for f in files:
        try:
            with open(f, 'r', encoding='utf-8', errors='ignore') as fp:
                for ln in fp:
                    ln = ln.strip()
                    if ln and not ln.startswith('#'):
                        lines.append((f, ln))
        except:
            pass

    if not lines:
        print("No usable lines found.")
        return

    types = Counter(classify(ln) for _, ln in lines)
    total = len(lines)
    print("\nIDENTIFIED TYPES")
    print("-" * 40)
    for t, c in types.most_common():
        print(f"{t:25} : {c:6,}  ({c/total*100:.1f}%)" if total else f"{t:25} : {c:6,}")
    print(f"\nTotal lines: {total:,}")

    while True:
        print("\nOptions:")
        print("1. Show sample lines per type")
        print("2. Save all to CSV")
        print("3. Extract private keys to txt")
        print("4. Quit")
        ch = input("Choose: ").strip()
        if ch == '1':
            by_type = {}
            for f, ln in lines:
                t = classify(ln)
                by_type.setdefault(t, []).append(ln)
            for t in sorted(by_type):
                print(f"\n{t.upper()}:")
                for i, ln in enumerate(by_type[t][:10], 1):
                    print(f"  {i}. {ln}")
                if len(by_type[t]) > 10:
                    print(f"  ... +{len(by_type[t])-10} more")
        elif ch == '2':
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = f"keys_classified_{ts}.csv"
            with open(out, 'w', newline='') as f:
                w = csv.writer(f)
                w.writerow(['file', 'line', 'type'])
                for f, ln in lines:
                    w.writerow([f, ln, classify(ln)])
            print(f"Saved: {out}")
        elif ch == '3':
            privs = [ln for _, ln in lines if classify(ln) in {"raw_hex_privkey", "compressed_wif", "uncompressed_wif", "mini_privkey"}]
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = f"privkeys_{ts}.txt"
            with open(out, 'w') as f:
                for p in privs:
                    f.write(p + '\n')
            print(f"Saved {len(privs)} possible private keys to {out}")
        elif ch == '4':
            print("Done.")
            break

if __name__ == '__main__':
    main()
EOF

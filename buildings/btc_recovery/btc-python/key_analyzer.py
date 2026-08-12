#!/usr/bin/env python3
# key_analyzer.py - analyzes thousands of mixed Bitcoin keys/strings
# Usage: python key_analyzer.py file1.txt file2.csv file3.txt ...
#        python key_analyzer.py *.txt *.csv
#        python key_analyzer.py full_keypairs_*.csv raw_keys.txt

import hashlib
import binascii
import csv
import os
import sys
from datetime import datetime
import ecdsa

# ─── Pure Python base58 (no external dep needed) ──────────────────────────────

BASE58_ALPHABET = '123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'

def base58_encode(b):
    if not b: return ''
    n = int.from_bytes(b, 'big')
    res = []
    while n > 0:
        n, r = divmod(n, 58)
        res.append(BASE58_ALPHABET[r])
    res.reverse()
    return ''.join(res) or BASE58_ALPHABET[0]

def base58_decode(s):
    if not s: return b''
    n = 0
    for c in s:
        n = n * 58 + BASE58_ALPHABET.index(c)
    return n.to_bytes((n.bit_length() + 7) // 8, 'big')

def sha256d(data: bytes) -> bytes:
    return hashlib.sha256(hashlib.sha256(data).digest()).digest()

# ─── Normalization helpers ───────────────────────────────────────────────────

def normalize_to_compressed_wif(raw: str) -> tuple[str | None, str]:
    raw = raw.strip().replace(' ', '').replace('\n', '').upper()
    if not raw or len(raw) < 30:
        return None, "too_short_or_empty"

    try:
        decoded_bytes = base58_decode(raw)
        if len(decoded_bytes) < 5:
            raise ValueError("Too short")

        computed_checksum = sha256d(decoded_bytes[:-4])[:4]
        if decoded_bytes[-4:] != computed_checksum:
            raise ValueError("Checksum mismatch")

        version = decoded_bytes[0]
        payload = decoded_bytes[1:-4]

        if version == 0x80 and len(payload) == 32:           # uncompressed WIF
            priv_bytes = payload
            extended = b'\x80' + priv_bytes + b'\x01'
            chk = sha256d(extended)[:4]
            compressed_wif = base58_encode(extended + chk)
            return compressed_wif, "converted_from_uncompressed"

        if version == 0x80 and len(payload) == 33 and payload[-1] == 1:  # compressed
            return raw, "already_compressed_wif"

        raise ValueError("Invalid version or length")
    except:
        pass

    # Raw 64-char hex private key
    if len(raw) == 64 and all(c in '0123456789ABCDEF' for c in raw):
        try:
            priv_bytes = binascii.unhexlify(raw)
            if len(priv_bytes) == 32:
                extended = b'\x80' + priv_bytes + b'\x01'
                chk = sha256d(extended)[:4]
                return base58_encode(extended + chk), "from_raw_hex"
        except:
            pass

    # Old mini private key (starts with S, 30 chars)
    if len(raw) == 30 and raw.startswith('S'):
        try:
            extended = (raw + '?').encode()
            priv_bytes = hashlib.sha256(extended).digest()
            extended = b'\x80' + priv_bytes + b'\x01'
            chk = sha256d(extended)[:4]
            return base58_encode(extended + chk), "from_mini_key"
        except:
            pass

    return None, "unrecognized_format"

# ─── Derive pubkey + addresses ───────────────────────────────────────────────

def derive_pub_and_addresses(wif: str) -> dict:
    try:
        decoded_bytes = base58_decode(wif)
        version = decoded_bytes[0]
        payload = decoded_bytes[1:-4]
        if version != 0x80 or sha256d(decoded_bytes[:-4])[:4] != decoded_bytes[-4:]:
            raise ValueError("Invalid WIF checksum/version")

        priv_bytes = payload[:-1] if len(payload) == 33 and payload[-1] == 1 else payload

        sk = ecdsa.SigningKey.from_string(priv_bytes, curve=ecdsa.SECP256k1)
        vk = sk.verifying_key
        x = vk.pubkey.point.x().to_bytes(32, 'big')
        prefix = b'\x02' if vk.pubkey.point.y() % 2 == 0 else b'\x03'
        pub_compressed = (prefix + x).hex()

        h160 = hashlib.new('ripemd160', hashlib.sha256(bytes.fromhex(pub_compressed)).digest()).digest()
        vh160 = b'\x00' + h160
        addr_legacy = base58_encode(vh160 + sha256d(vh160)[:4])

        witness = b'\x00\x14' + h160
        sh = hashlib.new('ripemd160', hashlib.sha256(witness).digest()).digest()
        addr_p2sh = base58_encode(b'\x05' + sh + sha256d(b'\x05' + sh)[:4])

        # Native SegWit bc1q... (simple truncated version; full needs bech32 lib)
        addr_bech32 = f"bc1q{hashlib.sha256(h160).hexdigest()[:8]}..."  # placeholder

        return {
            'pub_compressed': pub_compressed,
            'legacy_1_addr': addr_legacy,
            'p2wpkh_p2sh_3_addr': addr_p2sh,
            'native_bc1_addr': addr_bech32,
            'status': 'valid'
        }
    except Exception as e:
        return {
            'status': f'derivation_failed: {str(e)}',
            'pub_compressed': '',
            'legacy_1_addr': '',
            'p2wpkh_p2sh_3_addr': '',
            'native_bc1_addr': ''
        }

# ─── Main logic ───────────────────────────────────────────────────────────────

def analyze_keys(input_files: list[str], output_dir: str = "key_analysis"):
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    all_keys = []
    for filepath in input_files:
        if not os.path.exists(filepath):
            print(f"Skipping missing: {filepath}")
            continue
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if line and 20 < len(line) < 100 and not line.startswith('#'):
                    all_keys.append(f"{filepath}:{line_num}:{line}")

    print(f"Collected {len(all_keys):,} potential key-like lines")

    results = []
    seen = set()
    for entry in all_keys:
        _, _, raw = entry.partition(':')   # rough split, take last part as key
        raw = raw.strip()
        if raw in seen:
            continue
        seen.add(raw)

        norm_wif, reason = normalize_to_compressed_wif(raw)
        row = {
            'original': raw,
            'source_file_line': entry.split(':', 1)[0] if ':' in entry else '',
            'normalized_wif': norm_wif or '',
            'normalize_reason': reason,
            'status': '',
            'pub_compressed': '',
            'legacy_1_addr': '',
            'p2wpkh_p2sh_3_addr': '',
            'native_bc1_addr': ''
        }

        if norm_wif:
            derived = derive_pub_and_addresses(norm_wif)
            row.update(derived)
        else:
            row['status'] = 'no_valid_privkey'

        results.append(row)

    # Stats
    valid_count = sum(1 for r in results if r.get('status') == 'valid')
    total_unique = len(results)
    success_rate = (valid_count / total_unique * 100) if total_unique > 0 else 0.0

    print(f"\nUnique keys processed: {total_unique:,}")
    print(f"Valid normalized keys: {valid_count:,}")
    print(f"Success rate: {success_rate:.1f}%")

    from collections import Counter
    reasons = Counter(r['normalize_reason'] for r in results)
    print("\nBreakdown by reason:")
    for reason, count in reasons.most_common():
        print(f"  {reason}: {count:,}")

    # Save full CSV
    fieldnames = ['original', 'source_file_line', 'normalized_wif', 'normalize_reason',
                  'status', 'pub_compressed', 'legacy_1_addr',
                  'p2wpkh_p2sh_3_addr', 'native_bc1_addr']
    outfile = os.path.join(output_dir, f"analyzed_keys_{timestamp}.csv")
    with open(outfile, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)

    # Summary TXT
    report = os.path.join(output_dir, f"summary_{timestamp}.txt")
    with open(report, 'w') as f:
        f.write(f"Key Analysis Report - {datetime.now()}\n\n")
        f.write(f"Files processed: {len(input_files)}\n")
        f.write(f"Total unique keys: {total_unique:,}\n")
        f.write(f"Valid normalized keys: {valid_count:,}\n")
        f.write(f"Success rate: {success_rate:.1f}%\n\n")
        f.write("Breakdown by reason:\n")
        for reason, count in reasons.most_common():
            f.write(f"  {reason}: {count:,}\n")

    print(f"\nResults saved:")
    print(f"  Full CSV → {outfile}")
    print(f"  Summary  → {report}")
    print("\nNext: open the CSV in Excel / LibreOffice, sort by 'status' == 'valid'")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python key_analyzer.py file1.txt file2.csv ...")
        print("Example:")
        print("  python key_analyzer.py full_keypairs_*.csv raw_keys.txt")
        print("  python key_analyzer.py *.txt *.csv")
        sys.exit(1)

    input_files = sys.argv[1:]
    print(f"Processing {len(input_files)} file(s):")
    for f in input_files:
        print(f"  - {f}")
    analyze_keys(input_files)

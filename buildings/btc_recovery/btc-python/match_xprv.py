#!/usr/bin/env python3
import json
import subprocess
import sys

WALLET_21_ADDRESSES = [
    "1122c5DeM5fs1ivJkZwzMxfwZAFFdCJVbJ",
    "1123SrYwKWHNgyLCFsK1vRFQS5FsE6XBij",
    "1125mSUgqoeaLMBFeZHAjvYV6VZ9TyKWqR",
]

XPRV_KEYS = [
    (
        "xprv9ypTTzMuqDr78NRavpPGjkmwC11BimwGop46HKJohqc8XSBDiTwWwc8EgzF3b1Njfnqxtb3RFJ2WEK4Uf5XL3hnKitu1YJghiDDYuwEGrTz",
        "wallets/seed",
    ),
    (
        "xprv9yMEmdggNa2UqkAnhD1H5bUUV8dUA21CgrAtzSwYB2gFCh5pz817RoZf7o7f164ZXAQwyH1kuBptKP4LFLRYpwPV2TCNL3trBPc7XuoLUpM",
        "wallets/seed1",
    ),
    (
        "xprv9y3Mvw1tyGPNshmo6VwRFMQxHGGXLC5KrAZbLsnjUzSrDa2utZSBbe7RfU7ox8kn56bivs6ZrC9cDYUxiPy8DZYXDpqsGeLNzXDvJcJZUC5",
        "SEEDS/BIP39 Seed",
    ),
    (
        "xprv9s21ZrQH143K3vfqWsGCy3QiqG1NLiGBisMNsXzV8HaebECaBvHiWVozaSefjQwwNvji13vg3bn6pF2gQ2xYW7JmnjpBkYL3Lru6TdBRyKJ",
        "SEEDS/BIP39 Root Key",
    ),
]

print("=" * 60)
print("Bitcoin xprv Key Matcher for wallet_21")
print("=" * 60)
print()
print("Wallet 21 first addresses (P2PKH - Legacy):")
for addr in WALLET_21_ADDRESSES:
    print(f"  {addr}")
print()
print("Testing xprv keys with derivation paths:")
print("  - m/44'/0'/0' (Legacy P2PKH)")
print("  - m/49'/0'/0' (P2SH-P2WPKH)")
print("  - m/84'/0'/0' (Native SegWit)")
print()
print("=" * 60)

try:
    from bit import Key

    for xprv, source in XPRV_KEYS:
        print(f"\nTesting xprv from {source}:")
        print(f"  {xprv[:20]}...{xprv[-10:]}")

        for path_name, path in [
            ("Legacy (m/44'/0'/0')", "m/44'/0'/0'/0/0"),
            ("P2SH (m/49'/0'/0')", "m/49'/0'/0'/0/0"),
            ("SegWit (m/84'/0'/0')", "m/84'/0'/0'/0/0"),
        ]:
            try:
                key = Key(xprv)
                derived = key.derive(path)
                addr = derived.address
                match = addr in WALLET_21_ADDRESSES
                marker = " <-- MATCH!" if match else ""
                print(f"    {path_name}: {addr}{marker}")
                if match:
                    print(f"    *** FOUND MATCH for wallet_21! ***")
                    print(f"    xprv: {xprv}")
                    print(f"    path: {path}")
            except Exception as e:
                print(f"    {path_name}: Error - {str(e)[:50]}")

except ImportError:
    print("\n'bit' library not installed. Trying to install...")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "bit"], check=True)
        print("Installation complete. Please run the script again.")
    except:
        print("Could not install 'bit' library.")
        print("\nAlternative: Use Electrum to test:")
        print("1. Open Electrum")
        print("2. Wallet > Import addresses or private keys")
        print("3. Enter each xprv and check derived addresses")

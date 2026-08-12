#!/usr/bin/env python3
"""
Bitcoin xprv Matcher - Tests all xprv keys against wallet_21 and wallet_1 addresses
"""

WALLET_21_FIRST_ADDRESSES = [
    "1122c5DeM5fs1ivJkZwzMxfwZAFFdCJVbJ",
    "1123SrYwKWHNgyLCFsK1vRFQS5FsE6XBij",
    "1125mSUgqoeaLMBFeZHAjvYV6VZ9TyKWqR",
]

WALLET_1_FIRST_ADDRESSES = [
    "31h2XB4U7vCFtixY4szHuXgqsDCFfUqoiL",
    "31h76YLotEipBdshdUQxKKsRyno1HSzcws",
    "31h89R9b1M7fqzcWZS2eJ7S8CCnNcYWMEp",
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
        "xprv9zAwPRjY6GNaQq3Q9sqSvaKE8QQmLNfmQ6cft88sVsm1UZtN76sm1u3HoiiQbxYFN4JvAdZrFcNjBv8eVj7D57YD6Z4pDb1aTT9oV2WAZty",
        "wallets/seed3",
    ),
    (
        "xprv9zAndnZMJQZpfi8RQDpQtgNuuhWRSh4WofMAp5GPs54mDrggS9Pbnq4iRUz8SQrFqpv7eFetkx1WPCTAh9Z9BfP9neSpVF3t83ain68QLaF",
        "wallets/seed4",
    ),
    (
        "xprv9y3Mvw1tyGPNshmo6VwRFMQxHGGXLC5KrAZbLsnjUzSrDa2utZSBbe7RfU7ox8kn56bivs6ZrC9cDYUxiPy8DZYXDpqsGeLNzXDvJcJZUC5",
        "SEEDS/BIP39",
    ),
    (
        "xprv9s21ZrQH143K3vfqWsGCy3QiqG1NLiGBisMNsXzV8HaebECaBvHiWVozaSefjQwwNvji13vg3bn6pF2gQ2xYW7JmnjpBkYL3Lru6TdBRyKJ",
        "SEEDS/BIP39 Root",
    ),
    (
        "xprv9s21ZrQH143K3QrqRZtEujfdLoZPqvPosPBRkeHJ2XiwTKF5LrpwznD3edkAGTFgsuCTDWZNc5DoBEUcgNgZzfeRJ3HvDr8YeEXb8yMAjb8",
        "wallets/check_recovery",
    ),
]

print("=" * 70)
print("Bitcoin xprv Key Matcher for wallet_21 and wallet_1")
print("=" * 70)
print()
print("Wallet 21 addresses (P2PKH - Legacy):")
for addr in WALLET_21_FIRST_ADDRESSES:
    print(f"  {addr}")
print()
print("Wallet 1 addresses (P2SH):")
for addr in WALLET_1_FIRST_ADDRESSES:
    print(f"  {addr}")
print()
print("Testing xprv keys with derivation paths:")
print("  - m/44'/0'/0'  -> Legacy P2PKH (1...)")
print("  - m/49'/0'/0'  -> P2SH-P2WPKH (3...)")
print("  - m/84'/0'/0'  -> Native SegWit (bc1)")
print()
print("=" * 70)

try:
    from bit import Key

    found_wallet21 = None
    found_wallet1 = None

    for xprv, source in XPRV_KEYS:
        print(f"\nTesting from {source}:")
        print(f"  {xprv[:25]}...{xprv[-15:]}")

        for path_name, path in [
            ("Legacy (m/44'/0'/0')", "m/44'/0'/0'/0/0"),
            ("P2SH   (m/49'/0'/0')", "m/49'/0'/0'/0/0"),
            ("SegWit (m/84'/0'/0')", "m/84'/0'/0'/0/0"),
        ]:
            try:
                key = Key(xprv)
                derived = key.derive(path)
                addr = derived.address

                w21_match = addr in WALLET_21_FIRST_ADDRESSES
                w1_match = addr in WALLET_1_FIRST_ADDRESSES

                if w21_match:
                    marker = " <-- MATCHES wallet_21!"
                    found_wallet21 = (xprv, path, source)
                elif w1_match:
                    marker = " <-- MATCHES wallet_1!"
                    found_wallet1 = (xprv, path, source)
                else:
                    marker = ""

                if w21_match or w1_match:
                    print(f"    {path_name}: {addr}{marker}")

            except Exception as e:
                pass

    print()
    print("=" * 70)
    print("RESULTS:")
    print("=" * 70)

    if found_wallet21:
        print(f"\n*** wallet_21 MATCH FOUND! ***")
        print(f"  Source: {found_wallet21[2]}")
        print(f"  xprv: {found_wallet21[0]}")
        print(f"  Path: {found_wallet21[1]}")
    else:
        print("\nNo match for wallet_21")

    if found_wallet1:
        print(f"\n*** wallet_1 MATCH FOUND! ***")
        print(f"  Source: {found_wallet1[2]}")
        print(f"  xprv: {found_wallet1[0]}")
        print(f"  Path: {found_wallet1[1]}")
    else:
        print("\nNo match for wallet_1")

except ImportError:
    print("\n'bit' library not installed.")
    print("Install with: pip install bit")
    print("\nThen run this script again.")

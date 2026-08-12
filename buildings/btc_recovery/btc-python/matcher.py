# Wrote btc\match_xprv_v3.py
#!/usr/bin/env python3
"""
Bitcoin xprv Matcher - Tests all xprv keys against wallet_21 and wallet_1 addresses
Including hardware wallet (zprv) keys
"""
WALLET_21_FIRST_ADDRESSES = [
    "1122c5DeM5fs1ivJkZwzMxfwZAFFdCJVbJ",
    "1123SrYwKWHNgyLCFsK1vRFQS5FsE6XBij", 
    "1125mSUgqoeaLMBFeZHAjvYV6VZ9TyKWqR"
]
WALLET_1_FIRST_ADDRESSES = [
    "31h2XB4U7vCFtixY4szHuXgqsDCFfUqoiL",
    "31h76YLotEipBdshdUQxKKsRyno1HSzcws",
    "31h89R9b1M7fqzcWZS2eJ7S8CCnNcYWMEp"
]
XPRV_KEYS = [
    ("xprv9ypTTzMuqDr78NRavpPGjkmwC11BimwGop46HKJohqc8XSBDiTwWwc8EgzF3b1Njfnqxtb3RFJ2WEK4Uf5XL3hnKitu1YJghiDDYuwEGrTz", "wallets/seed"),
    ("xprv9yMEmdggNa2UqkAnhD1H5bUUV8dUA21CgrAtzSwYB2gFCh5pz817RoZf7o7f164ZXAQwyH1kuBptKP4LFLRYpwPV2TCNL3trBPc7XuoLUpM", "wallets/seed1"),
    ("xprv9zAwPRjY6GNaQq3Q9sqSvaKE8QQmLNfmQ6cft88sVsm1UZtN76sm1u3HoiiQbxYFN4JvAdZrFcNjBv8eVj7D57YD6Z4pDb1aTT9oV2WAZty", "wallets/seed3"),
    ("xprv9zAndnZMJQZpfi8RQDpQtgNuuhWRSh4WofMAp5GPs54mDrggS9Pbnq4iRUz8SQrFqpv7eFetkx1WPCTAh9Z9BfP9neSpVF3t83ain68QLaF", "wallets/seed4"),
    ("xprv9y3Mvw1tyGPNshmo6VwRFMQxHGGXLC5KrAZbLsnjUzSrDa2utZSBbe7RfU7ox8kn56bivs6ZrC9cDYUxiPy8DZYXDpqsGeLNzXDvJcJZUC5", "SEEDS/BIP39"),
    ("xprv9s21ZrQH143K3vfqWsGCy3QiqG1NLiGBisMNsXzV8HaebECaBvHiWVozaSefjQwwNvji13vg3bn6pF2gQ2xYW7JmnjpBkYL3Lru6TdBRyKJ", "SEEDS/BIP39 Root"),
    ("xprv9s21ZrQH143K3QrqRZtEujfdLoZPqvPosPBRkeHJ2XiwTKF5LrpwznD3edkAGTFgsuCTDWZNc5DoBEUcgNgZzfeRJ3HvDr8YeEXb8yMAjb8", "wallets/check_recovery"),
    # Hardware wallet keys (zprv)
    ("zprvAZeZXCaJb4KgY574yZRjjTcdBWsfbzBnuH9fpcB2ZRWkcSq4Y7EsgnoD8RghnQevaj9GL5rAcRAGojGQbowKNSkjy2Xu49P4kKbCnnkr6J7", "wallets/boss (zprv)"),
    ("zprvAZdo78hALyqzvSkat2Y13zQdGeJMhjnWFiEWcvqisd3ZTiaiW1v6U8JKqyaLa7JMbZmwtLSv31cGXB5wHMzexs5mU2JMuJqYfRKw2zVUrLb", "wallets/goat (zprv)"),
    ("zprvAZDx7CDUJyRcjaJo76KpvQji1KhfYCYWeEaKZx5dV2wt3ibbqe8JNXE8APmqhrq6pd8f4apfpyw2kytwTRw72zHmHtYQxjw8y2hP6YEUqo3", "wallets/sweep (zprv)"),
    ("zprvAdS8rxcvMNey3yQs4Da7heNBzoqJKBHfQCB4cNiksRxv9Qq1M5fboaGva6CvsbK4go79ruWqK9MJqYf8TVwFSqUGF2kBUS4419jbBaNKH1w", "wallets/seed2 (zprv)"),
    # User's new zprv key
    ("zprvawgybbk7jr8gkbyzlvu7qwtwjpihs5upyxvdc5oemfglafvjvcuqyyqtu33p8fk3xq9dcewgidkqasrgnlddygpa9l5sj5v4fmcu5p3ttsn", "USER zprv key"),
]
# Extended derivation paths to test
DERIVATION_PATHS = [
    # Standard BIP44/BIP49/BIP84
    ("Legacy (m/44'/0'/0')", "m/44'/0'/0'/0/0"),
    ("P2SH   (m/49'/0'/0')", "m/49'/0'/0'/0/0"),
    ("SegWit (m/84'/0'/0')", "m/84'/0'/0'/0/0"),
    # Alternative paths sometimes used
    ("Alt Legacy", "m/44'/0'/0'/0"),
    ("Alt P2SH", "m/49'/0'/0'/0"),
    ("Alt SegWit", "m/84'/0'/0'/0"),
    # Account level paths
    ("Account 0", "m/44'/0'/0'"),
    ("Account 1", "m/44'/0'/1'"),
    ("Account 0 no change", "m/44'/0'/0'/0"),
]
print("="*70)
print("Bitcoin xprv Key Matcher for wallet_21 and wallet_1")
print("="*70)
print()
print("Wallet 21 addresses (P2PKH - Legacy):")
for addr in WALLET_21_FIRST_ADDRESSES:
    print(f"  {addr}")
print()
print("Wallet 1 addresses (P2SH):")
for addr in WALLET_1_FIRST_ADDRESSES:
    print(f"  {addr}")
print()
print("="*70)
try:
    from bit import Key
    
    found_wallet21 = None
    found_wallet1 = None
    
    for xprv, source in XPRV_KEYS:
        print(f"\nTesting from {source}:")
        print(f"  {xprv[:25]}...{xprv[-15:]}")
        
        for path_name, path in DERIVATION_PATHS:
            try:
                key = Key(xprv)
                derived = key.derive(path)
                addr = derived.address
                
                w21_match = addr in WALLET_21_FIRST_ADDRESSES
                w1_match = addr in WALLET_1_FIRST_ADDRESSES
                
                if w21_match or w1_match:
                    wallet_type = "wallet_21" if w21_match else "wallet_1"
                    print(f"    *** MATCH for {wallet_type}! ***")
                    print(f"    Path: {path_name} -> {addr}")
                    if w21_match:
                        found_wallet21 = (xprv, path, source)
                    if w1_match:
                        found_wallet1 = (xprv, path, source)
                    
            except Exception as e:
                pass
                
    print()
    print("="*70)
    print("RESULTS:")
    print("="*70)
    
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

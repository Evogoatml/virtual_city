# Wrote btc\extract_keys_fast.py
import json
# Just extract first 10 keys for testing
with open('/home/popi/btc/wallets/wallet_21.json', 'r') as f:
    wallet = json.load(f)
keypairs = wallet.get('keystore', {}).get('keypairs', {})
print(f"Total keypairs: {len(keypairs)}")
print("\nFirst 10 private keys:")
for i, privkey in enumerate(list(keypairs.values())[:10]):
    print(privkey)

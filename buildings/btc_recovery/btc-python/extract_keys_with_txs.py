# Wrote btc\extract_keys_with_txs.py
#!/usr/bin/env python3
"""
Extract private keys for addresses that have transaction history
"""
import json
import sys
WALLET_FILE = "/home/popi/btc/wallets/wallet_21.json"
OUTPUT_FILE = "/home/popi/btc/keys_with_txs.txt"
print("Loading wallet...")
with open(WALLET_FILE, 'r') as f:
    wallet = json.load(f)
# Get addresses with transaction history
addr_history = wallet.get('addr_history', {})
addresses_with_txs = set(addr_history.keys())
print(f"Addresses with transactions: {len(addresses_with_txs)}")
# Get keypairs (pubkey -> private key)
keypairs = wallet.get('keystore', {}).get('keypairs', {})
print(f"Total keypairs: {len(keypairs)}")
# Get address -> pubkey mapping
address_to_pubkey = {}
addresses_data = wallet.get('addresses', {})
for addr, data in addresses_data.items():
    if isinstance(data, dict) and 'pubkey' in data:
        address_to_pubkey[addr] = data['pubkey']
# Create pubkey -> private key mapping
pubkey_to_privkey = {}
for pubkey, privkey in keypairs.items():
    pubkey_to_privkey[pubkey] = privkey
# Find private keys for addresses with txs
keys_with_txs = []
for addr in addresses_with_txs:
    if addr in address_to_pubkey:
        pubkey = address_to_pubkey[addr]
        if pubkey in pubkey_to_privkey:
            privkey = pubkey_to_privkey[pubkey]
            keys_with_txs.append(privkey)
            print(f"  {addr} -> {privkey}")
print(f"\nFound {len(keys_with_txs)} keys with transaction history")
# Save
with open(OUTPUT_FILE, 'w') as f:
    for key in keys_with_txs:
        f.write(key + "\n")
print(f"Saved to: {OUTPUT_FILE}")

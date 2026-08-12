# Wrote btc\check_utxo.py
#!/usr/bin/env python3
"""
Check which keys have current UTXO balance
"""
import json
WALLET_FILE = "/home/popi/btc/wallets/wallet_21.json"
print("Loading wallet...")
with open(WALLET_FILE, 'r') as f:
    wallet = json.load(f)
# Get addresses with transaction history
addr_history = wallet.get('addr_history', {})
addresses_with_txs = set(addr_history.keys())
# Get keypairs
keypairs = wallet.get('keystore', {}).get('keypairs', {})
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
# Check prevouts_by_scripthash for current UTXOs
prevouts = wallet.get('prevouts_by_scripthash', {})
print(f"Current UTXOs: {len(prevouts)}")
# Get addresses with current UTXOs
addresses_with_utxo = set()
for scripthash in prevouts.keys():
    for addr in addresses_with_txs:
        if addr in address_to_pubkey:
            # We need to check which address corresponds to this scripthash
            pass
# Simpler: check txo (transaction outputs) for unspent
txo = wallet.get('txo', {})
unspent_count = 0
for addr, outputs in txo.items():
    if outputs:  # non-empty means unspent
        unspent_count += 1
        print(f"  {addr}: {len(outputs)} UTXO(s)")
print(f"\nAddresses with unspent outputs: {unspent_count}")


import json

with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

addr_history = wallet.get("addr_history", {})

# Get UTXOs for that address - it could be stored differently
utxos = addr_history.get("14qdBdRTvT4i4QZ6iqRhrBj732x9EpoFQC", [])

# Also check prevouts_by_scripthash
prevouts = wallet.get("prevouts_by_scripthash", {})

print("From addr_history:")
print(f"Count: {len(utxos)}")
for utxo in utxos[:3]:
    print(utxo)

# The format might be different - let me check prevouts
print("\nSearching all UTXOs from prevouts_by_scripthash...")

# Look for txid in prevouts
target_tx = "8983ffc8ee3375c7826426ed145d832fa8f0ddd1b283e4dea16e4e4022f192f3"
for key, value in prevouts.items():
    if target_tx in str(key):
        print(f"Found: {key} -> {value}")

import json

with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

# Get all addresses from the addresses dict
addresses = wallet.get("addresses", {})
addr_keys = list(addresses.keys())

# Split into receiving and change (first 1000 receiving, rest change)
receiving = addr_keys[:1000]
change = addr_keys[1000:]

# Replace addresses dict with proper structure
wallet["addresses"] = {"receiving": receiving, "change": change}

# Save fixed wallet
with open("/home/popi/btc/wallets/wallet_21_fixed.json", "w") as f:
    json.dump(wallet, f, indent=1)

print(f"Fixed wallet saved to wallet_21_fixed.json")
print(f"Receiving addresses: {len(receiving)}")
print(f"Change addresses: {len(change)}")

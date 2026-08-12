import json

# Load wallet
with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

# Get all addresses from addresses dict
addresses_dict = wallet.get("addresses", {})
addr_keys = list(addresses_dict.keys())

# Add receiving/change arrays
wallet["addresses"] = {"receiving": addr_keys[:1000], "change": addr_keys[1000:]}

# Save as dict format (Electrum can read both)
# Actually, we need to keep the original dict too
# Let's restructure properly

# Reload
with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

addresses_dict = wallet.get("addresses", {})
addr_keys = list(addresses_dict.keys())

# Create proper structure - dict with arrays added
wallet["addresses"] = addresses_dict
wallet["addresses"]["receiving"] = addr_keys[:1000]
wallet["addresses"]["change"] = addr_keys[1000:]

with open("/home/popi/btc/wallets/wallet_21_proper_fix.json", "w") as f:
    json.dump(wallet, f, indent=1)

print("Saved wallet_21_proper_fix.json")
print(f"Addresses dict: {len(addresses_dict)}")
print(f"Receiving: {len(addr_keys[:1000])}")
print(f"Change: {len(addr_keys[1000:])}")

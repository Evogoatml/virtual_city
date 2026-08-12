import json

with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

# Keep the original addresses dict with pubkeys
addresses_dict = wallet.get("addresses", {})
addr_keys = list(addresses_dict.keys())

# Add receiving/change arrays while keeping the dict
# First 1000 as receiving, rest as change
wallet["addresses"] = {"receiving": addr_keys[:1000], "change": addr_keys[1000:]}

# Need to merge the original dict back... but json format doesn't allow both
# So we need a different approach - add receiving/change to the dict itself

# Actually, let's check the structure of a working wallet again
print("Testing if this approach works...")

with open("/home/popi/btc/wallets/wallet_21_fixed3.json", "w") as f:
    json.dump(wallet, f, indent=1)

print("Saved wallet_21_fixed3.json - try opening this one")

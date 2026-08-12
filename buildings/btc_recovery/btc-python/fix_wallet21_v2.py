import json

with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

# Get addresses from addr_history
addr_history = wallet.get("addr_history", {})
all_addr_history_keys = list(addr_history.keys())

# The addresses dict has pubkey info - get just the keys
addresses = wallet.get("addresses", {})
addr_dict_keys = list(addresses.keys())

print(f"addr_history has {len(all_addr_history_keys)} addresses")
print(f"addresses dict has {len(addr_dict_keys)} addresses")
print(f"\nFirst 5 from addr_history: {all_addr_history_keys[:5]}")
print(f"First 5 from addresses: {addr_dict_keys[:5]}")

# Use addr_history keys for receiving/change
# All are receiving addresses (no way to know which are change)
receiving = all_addr_history_keys[:1000]
change = all_addr_history_keys[1000:]

wallet["addresses"] = {"receiving": receiving, "change": change}

with open("/home/popi/btc/wallets/wallet_21_fixed2.json", "w") as f:
    json.dump(wallet, f, indent=1)

print(f"\nFixed wallet saved to wallet_21_fixed2.json")
print(f"Receiving addresses: {len(receiving)}")
print(f"Change addresses: {len(change)}")

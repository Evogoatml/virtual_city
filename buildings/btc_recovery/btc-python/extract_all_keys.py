import json

with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

# Get all private keys from keystore
keypairs = wallet.get("keystore", {}).get("keypairs", {})

# Extract just the private keys
priv_keys = list(keypairs.values())

print(f"Total keys: {len(priv_keys)}")

# Save to file
with open("/home/popi/btc/wallet_21_all_keys.txt", "w") as f:
    for key in priv_keys:
        f.write(key + "\n")

print(f"Saved to wallet_21_all_keys.txt")
print("\nFirst 5 keys:")
for k in priv_keys[:5]:
    print(k)

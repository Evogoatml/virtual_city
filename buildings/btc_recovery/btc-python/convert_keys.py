import json

with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

keypairs = wallet.get("keystore", {}).get("keypairs", {})

# Save with p2pkh prefix
with open("/home/popi/btc/wallet_21_keys_p2pkh.txt", "w") as f:
    for privkey in keypairs.values():
        f.write(f"p2pkh:{privkey}\n")

# Save regular format too
with open("/home/popi/btc/wallet_21_keys_plain.txt", "w") as f:
    for privkey in keypairs.values():
        f.write(privkey + "\n")

print(f"Keys with p2pkh prefix: {len(keypairs)}")
print("Saved to wallet_21_keys_p2pkh.txt")

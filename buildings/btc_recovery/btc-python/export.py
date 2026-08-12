import json

wallet_path = "/home/ninja/.electrum/wallets/wallet_1"

with open(wallet_path, 'r') as f:
    wallet_data = json.load(f)

print(f"Total private keys: {len(wallet_data['keystore']['keypairs'])}")
print("\nFirst 5 addresses:")
for i, addr in enumerate(list(wallet_data['keystore']['keypairs'].keys())[:5]):
    print(f"  {i+1}. {addr}")

# Export all keys (you'll need the password to decrypt)
print("\n⚠️ Keys are ENCRYPTED - you need your wallet password to use them")

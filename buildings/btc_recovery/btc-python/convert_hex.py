import json
import hashlib


def wif_to_hex(wif):
    # Base58 decode
    chars = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    num = 0
    for c in wif:
        num = num * 58 + chars.index(c)

    # Convert to hex
    hex_bytes = num.to_bytes(33, byteorder="big")
    # Remove version byte (first) and checksum (last 4)
    return hex_bytes[1:-4].hex()


with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

keypairs = wallet.get("keystore", {}).get("keypairs", {})

# Convert WIF to hex
with open("/home/popi/btc/wallet_21_keys_hex.txt", "w") as f:
    for privkey in keypairs.values():
        hex_key = wif_to_hex(privkey)
        f.write(hex_key + "\n")

print(f"Converted {len(keypairs)} keys to hex")
print("\nFirst 3 hex keys:")
for i, k in enumerate(list(keypairs.values())[:3]):
    print(wif_to_hex(k))

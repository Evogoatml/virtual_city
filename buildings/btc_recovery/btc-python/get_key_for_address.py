import json
import hashlib
import base58

# UTXO info from mempool.space
txid = "29edade5fdcd4b332598539f00c41af6bcb4435c"
vout = 0  # The first output (300 BTC to 14qd...)
amount_satoshis = 30000000000

# Destination address (your receiving address)
destination = "14phS7Ug9n6V1hRnkPA5Rdzc4zUdEzAPVk"  # Change this to your address!

# Fee (small fee, e.g., 1000 satoshis)
fee = 1000


# Create raw transaction
def create_raw_tx(txid, vout, amount, fee, destination):
    # This is a simplified P2PKH transaction
    pass


# For now, just extract the key
with open("/home/popi/btc/wallets/wallet_21.json", "r") as f:
    wallet = json.load(f)

keypairs = wallet.get("keystore", {}).get("keypairs", {})

# Find the key for the address
addresses = wallet.get("addresses", {})
target_pubkey = None
for addr, info in addresses.items():
    if addr == "14qdBdRTvT4i4QZ6iqRhrBj732x9EpoFQC":
        target_pubkey = info.get("pubkey")
        break

print(f"Target address: 14qdBdRTvT4i4QZ6iqRhrBj732x9EpoFQC")
print(f"Pubkey: {target_pubkey}")

# Find corresponding private key
if target_pubkey:
    for pub, priv in keypairs.items():
        if pub == target_pubkey:
            print(f"Private key: {priv}")
            break

print("\nUse this key to sweep:")
print("p2pkh:5HpJdCRxej8gzT7i3FXxtwHdYjxeiXoQqBziuqwLHNWfoTi7354")

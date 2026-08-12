import json
from electrum.bitcoin import pw_decode
from electrum.crypto import sha256d

wallet_path = "/home/ninja/.electrum/wallets/wallet_1"
output_file = "/home/ninja/DECRYPTED_KEYS.csv"

# Load wallet
with open(wallet_path, 'r') as f:
    wallet_data = json.load(f)

# Get password
password = input("Enter wallet password: ")

print("\n=== DECRYPTING PRIVATE KEYS ===\n")

keystore = wallet_data['keystore']
keypairs = keystore['keypairs']

decrypted_keys = []
failed_keys = []

print(f"Total keys to decrypt: {len(keypairs)}")

try:
    for i, (pubkey, encrypted_key) in enumerate(keypairs.items()):
        if i % 1000 == 0:
            print(f"Progress: {i}/{len(keypairs)}")
        
        try:
            # Decrypt the private key
            decrypted = pw_decode(encrypted_key, password)
            decrypted_keys.append(f"{pubkey},{decrypted}")
        except Exception as e:
            failed_keys.append(pubkey)
    
    # Save to file
    with open(output_file, 'w') as f:
        f.write("public_key,private_key_wif\n")
        for line in decrypted_keys:
            f.write(line + "\n")
    
    print(f"\n✅ SUCCESS!")
    print(f"✅ Decrypted {len(decrypted_keys)} private keys")
    print(f"❌ Failed: {len(failed_keys)} keys")
    print(f"✅ Saved to: {output_file}")
    print("\n⚠️ KEEP THIS FILE SECURE!")

except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()

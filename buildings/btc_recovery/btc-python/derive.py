derive.py# Run this in a new file derive.py
from ecdsa import SigningKey, SECP256k1
import hashlib
import base58

hex_priv = "3f5f3a33d9f4f9cc26a284a117d19e97eedd4df9485a9c2655208a288fc9d397"
priv_bytes = bytes.fromhex(hex_priv)
sk = SigningKey.from_string(priv_bytes, curve=SECP256k1)
vk = sk.verifying_key
pubkey = b'\x02' + vk.to_string()[:32] if vk.to_string()[32] % 2 == 0 else b'\x03' + vk.to_string()[:32]
sha = hashlib.sha256(pubkey).digest()
ripemd = hashlib.new('ripemd160', sha).digest()
extended = b'\x00' + ripemd
checksum = hashlib.sha256(hashlib.sha256(extended).digest()).digest()[:4]
address = base58.b58encode(extended + checksum).decode()
print("Address:", address)

import hashlib
import base58

# Your mini keys - one per line (copy-pasted from your message)
mini_keys = [
    "KyU5aTzeHiF3Ag3th2uhSpEfuFkVBeK6S8pJiBapuZyvwz8LyGUM",
    "KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M9n3vPphNe5cC7",
    "KwG6g3E8vDXsLoBV38qbLRvs7BgrtPqyUWUfzQYsz8MagXHL7bWh",
    "KxXfqf4FWQAbTjV26jAnA46F2xbc9Gup1Fj3wuCe7Xc6zq64bqgH",
    "KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9MA3Tc94i4bStAe",
    "KxHv1JYWRwtEyYwvMi5AsoNXdvNCqNF1rjBx4x99RmEv5Y3RmhmP",
    "KyboCoVnKLbc3mu2TMboE9GaCncq8o3cLmwtPh6LR8nvP7UzvLfz",
    "KzYKq5nE7yeAvA6c2FF3Mq6JA1HNguwnQsX1ZNFfzwZ7U53zFQWs",
    "KwDiBf89QgGbjEhKnhXJuH7LrciVrZi3qYjgd9M7rFW4KbjsHXvL",
    "KwEX4xYD9DFSikTCXXNGxic8MSXrsBLR1k9Rn5oa51LA4gtSfwLN",
    "L2x8F2ZPC8Gm9fCmJUsb2AMU5nW5ErG2WPkuPhH1eY1f5wK3Y5wqO"
]

def validate_mini_key(mini_key: str) -> dict:
    """Validate one mini key and derive full WIF + address if valid"""
    # Try with ? suffix (standard format)
    extended = mini_key + "?"
    sha1 = hashlib.sha256(extended.encode()).digest()
    sha2 = hashlib.sha256(sha1).digest()

    if sha2[0] == 0:
        priv_bytes = sha1
        extended_priv = b'\x80' + priv_bytes + b'\x01'
        checksum = hashlib.sha256(hashlib.sha256(extended_priv).digest()).digest()[:4]
        wif = base58.b58encode(extended_priv + checksum).decode()

        # Derive P2PKH address
        from ecdsa import SigningKey, SECP256k1
        sk = SigningKey.from_string(priv_bytes, curve=SECP256k1)
        vk = sk.verifying_key
        pubkey_compressed = b'\x02' + vk.to_string()[:32] if vk.to_string()[32] % 2 == 0 else b'\x03' + vk.to_string()[:32]
        sha = hashlib.sha256(pubkey_compressed).digest()
        ripemd = hashlib.new('ripemd160', sha).digest()
        extended_ripemd = b'\x00' + ripemd
        addr_checksum = hashlib.sha256(hashlib.sha256(extended_ripemd).digest()).digest()[:4]
        address = base58.b58encode(extended_ripemd + addr_checksum).decode()

        return {
            'valid': True,
            'mini_key': mini_key,
            'full_wif': wif,
            'address': address,
            'note': 'Valid with ? suffix'
        }

    # Try without ? (some old tools skipped it)
    extended = mini_key
    sha1 = hashlib.sha256(extended.encode()).digest()
    sha2 = hashlib.sha256(sha1).digest()

    if sha2[0] == 0:
        priv_bytes = sha1
        extended_priv = b'\x80' + priv_bytes + b'\x01'
        checksum = hashlib.sha256(hashlib.sha256(extended_priv).digest()).digest()[:4]
        wif = base58.b58encode(extended_priv + checksum).decode()

        # Same address derivation
        from ecdsa import SigningKey, SECP256k1
        sk = SigningKey.from_string(priv_bytes, curve=SECP256k1)
        vk = sk.verifying_key
        pubkey_compressed = b'\x02' + vk.to_string()[:32] if vk.to_string()[32] % 2 == 0 else b'\x03' + vk.to_string()[:32]
        sha = hashlib.sha256(pubkey_compressed).digest()
        ripemd = hashlib.new('ripemd160', sha).digest()
        extended_ripemd = b'\x00' + ripemd
        addr_checksum = hashlib.sha256(hashlib.sha256(extended_ripemd).digest()).digest()[:4]
        address = base58.b58encode(extended_ripemd + addr_checksum).decode()

        return {
            'valid': True,
            'mini_key': mini_key,
            'full_wif': wif,
            'address': address,
            'note': 'Valid without ? suffix (non-standard)'
        }

    return {
        'valid': False,
        'mini_key': mini_key,
        'note': 'Checksum failed both with and without ?'
    }

# Validate all keys in the list
for i, mini in enumerate(mini_keys, 1):
    print(f"\nChecking key #{i}: {mini[:10]}...{mini[-6:]}")
    result = validate_mini_key(mini)
    
    if result['valid']:
        print("  → VALID!")
        print(f"  Full WIF: {result['full_wif']}")
        print(f"  Address: {result['address']}")
        print(f"  Note: {result['note']}")
    else:
        print("  → INVALID")
        print(f"  Note: {result['note']}")

print("\nDone. For any VALID keys, sweep the full WIF in Electrum immediately.")
print("If none validate, these may be fake/generated keys from a vanity search - no funds.")

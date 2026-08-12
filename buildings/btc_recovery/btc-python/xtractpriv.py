#!/usr/bin/env python3
import re
import sys

if len(sys.argv) != 2:
    print("Usage: python3 extract_keys.py your_keypairs_file.txt")
    sys.exit(1)

filename = sys.argv[1]

plain_keys = []
encrypted = []

with open(filename, 'r', encoding='utf-8', errors='ignore') as f:
    content = f.read()

# Pattern for classic WIF private keys (51 or 52 chars)
wif_pattern = r'[5KL][123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz]{50,51}'

# Pattern for long base64 (encrypted keys)
base64_pattern = r'[A-Za-z0-9+/=]{40,}'

for match in re.finditer(wif_pattern, content):
    plain_keys.append(match.group(0))

for match in re.finditer(base64_pattern, content):
    if len(match.group(0)) > 60:  # encrypted are usually longer
        encrypted.append(match.group(0))

print(f"Found {len(plain_keys)} possible plain WIF keys")
print(f"Found {len(encrypted)} possible encrypted/base64 entries")

# Save results
with open('plain_wif_keys.txt', 'w') as f:
    for k in plain_keys:
        f.write(k + '\n')

with open('encrypted_values.txt', 'w') as f:
    for e in encrypted:
        f.write(e + '\n')

print("\nSaved to:")
print("  plain_wif_keys.txt     ← paste these into Electron Cash Sweep")
print("  encrypted_values.txt   ← need password to decrypt these")

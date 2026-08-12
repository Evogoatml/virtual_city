from pathlib import Path
import sys
import os

# Read a file with private keys mixed with other text and outputs clean WIF keys

input_file = sys.argv[1] if len(sys.argv) > 1 else os.getenv("BTC_INPUT_FILE", "")

output_file = "clean_keys.txt"

import re

# regex for WIF keys (start with 5, K, or L)
wif_pattern = r'\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b'

if not input_file:
    print("Error: No input file provided. Set BTC_INPUT_FILE env var or pass as argument.")
    sys.exit(1)

try:
    with open(input_file, "r") as f:
        data = f.read()
except FileNotFoundError:
    print(f"Error: File not found: {input_file}")
    sys.exit(1)

keys = re.findall(wif_pattern, data)

with open(output_file, "w") as f:
    for k in keys:
        f.write(k + "\n")

print(f"Exported {len(keys)} private keys to {output_file}")

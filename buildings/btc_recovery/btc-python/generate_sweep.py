#!/usr/bin/env python3
"""
Generate Electrum sweep commands for all private keys
"""

PRIVATE_KEYS_FILE = "/home/popi/btc/02_PRIVATE_KEYS/electrum_processing_20260130_024908/all_electrum_keys.txt"
OUTPUT_FILE = "/home/popi/btc/sweep_commands.sh"

# Destination wallet address (USER TO FILL IN)
DESTINATION_ADDRESS = "YOUR_DESTINATION_ADDRESS_HERE"

print("=" * 60)
print("Electrum Sweep Generator")
print("=" * 60)
print(f"Source: {PRIVATE_KEYS_FILE}")
print(f"Destination: {DESTINATION_ADDRESS}")
print()

# Read private keys
with open(PRIVATE_KEYS_FILE, "r") as f:
    keys = [line.strip() for line in f if line.strip()]

print(f"Found {len(keys)} private keys")

# Generate sweep commands
with open(OUTPUT_FILE, "w") as f:
    f.write("# Electrum Sweep Commands\n")
    f.write("# Run these commands in Electrum console\n\n")

    for i, key in enumerate(keys):
        # Electrum sweep command format
        f.write(f"wallet.sweep('{key}', '{DESTINATION_ADDRESS}')\n")

print(f"\nGenerated {len(keys)} sweep commands")
print(f"Saved to: {OUTPUT_FILE}")
print()
print("To use:")
print(f"1. Open Electrum")
print(f"2. Go to View > Show Console")
print(f"3. Copy commands from {OUTPUT_FILE}")
print(f"4. OR set DESTINATION_ADDRESS and run via python")

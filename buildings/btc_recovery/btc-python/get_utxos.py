import json
with open('/home/popi/btc/wallets/wallet_21.json', 'r') as f:
    wallet = json.load(f)
addr_history = wallet.get('addr_history', {})
# Get UTXOs for that address
utxos = addr_history.get('14qdBdRTvT4i4QZ6iqRhrBj732x9EpoFQC', [])
print(f"Total UTXOs: {len(utxos)}")
print("\nAll UTXOs (txid, vout):")
for utxo in utxos:
    txid = utxo[0]
    vout = utxo[1]
    print(f"{txid}:{vout}")

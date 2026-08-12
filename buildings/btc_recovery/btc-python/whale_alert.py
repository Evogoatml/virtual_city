import requests
import time

ADDR = "14qdBdRTvT4i4QZ6iqRhrBj732x9EpoFQC"

last_tx = 0
while True:
    try:
        r = requests.get(f"https://mempool.space/api/address/{ADDR}")
        data = r.json()
        tx_count = data['chain_stats']['tx_count']
        bal = data['chain_stats']['funded_txo_sum'] / 1e8
        
        if tx_count > last_tx:
            print(f"🚨 WHALE ALERT! New tx count: {tx_count} | Balance now: {bal} BTC")
            # Add Telegram bot send here if you want real alerts
        else:
            print(f"No move | Balance: {bal} BTC | Tx: {tx_count}")
        
        last_tx = tx_count
    except:
        print("API error - retrying")
    
    time.sleep(300)  # 5 min

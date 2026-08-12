import sqlite3, requests, time
DB  = "btc_recovery.db"
API = "https://blockstream.info/api"
conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
    SELECT a.address, a.addr_type, k.state
    FROM addresses a JOIN keys k ON k.id=a.key_id
    LIMIT 10
""").fetchall()
session = requests.Session()
session.headers.update({'Accept-Encoding':'gzip'})
for row in rows:
    r = session.get(f"{API}/address/{row['address']}", timeout=10)
    if r.status_code == 200:
        cs  = r.json().get('chain_stats',{})
        bal = cs.get('funded_txo_sum',0) - cs.get('spent_txo_sum',0)
        txc = cs.get('tx_count',0)
        sym = '💰' if bal > 0 else ('📜' if txc > 0 else '·')
        print(f"  {sym} {row['address']}  {bal/1e8:.8f} BTC  {row['state']}")
    time.sleep(0.25)
print("\nAPI working correctly" if rows else "No addresses in DB yet")

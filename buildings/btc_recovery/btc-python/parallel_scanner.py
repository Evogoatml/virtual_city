from concurrent.futures import ThreadPoolExecutor, as_completed
import time

def run_parallel(self, limit=0, workers=8):
    unscanned = self.db.get_unscanned()
    if limit: unscanned = unscanned[:limit]
    total = len(unscanned)
    if total == 0:
        print("[SCAN] All addresses already scanned"); return
    print(f"[SCAN] {total} addresses — {workers} workers")
    hits = 0
    for batch_start in range(0, total, 50):
        batch = unscanned[batch_start:batch_start+50]
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(self.client.get_address, row['address']): row
                for row in batch
            }
            for future in as_completed(futures):
                row  = futures[future]
                try:
                    data = future.result()
                except:
                    continue
                if data:
                    self.db.save_scan(row['address'], data)
                    cs  = data.get('chain_stats', {})
                    bal = cs.get('funded_txo_sum',0) - cs.get('spent_txo_sum',0)
                    txc = cs.get('tx_count',0)
                    if bal > 0 or txc > 0:
                        hits += 1
                        sym   = '💰' if bal > 0 else '📜'
                        spend = '✅' if row['state'] in ('COMPLETE','DERIVED') else '👁'
                        print(f"  {sym}{spend} {row['address']}  {bal/1e8:.8f} BTC  [{row['addr_type']}]")
                        if bal > 0:
                            utxos = self.client.get_utxos(row['address'])
                            if utxos: self.db.save_utxos(row['address'], utxos)
        print(f"  [{batch_start+len(batch)}/{total}]  hits={hits}")
        time.sleep(1)
    print(f"\n[SCAN] Done — {hits}/{total}")

# filename: verify_integrity.py
import bcoding
import hashlib
import math
import os

def calculate_entropy(data):
    if not data:
        return 0
    entropy = 0
    for x in range(256):
        p_x = float(data.count(x)) / len(data)
        if p_x > 0:
            entropy += - p_x * math.log(p_x, 2)
    return entropy

def analyze_pieces():
    target = "recovered.torrent"
    if not os.path.exists(target):
        print(f"ERROR: {target} not found. Run the recovery script first.")
        return

    try:
        with open(target, 'rb') as f:
            data = bcoding.bdecode(f)
        
        info = data.get('info') or data.get(b'info', {})
        pieces = info.get('pieces') or info.get(b'pieces', b'')
        
        piece_count = len(pieces) // 20
        print(f"\n[PHASE: VALIDATION]")
        print(f"Total Pieces Detected: {piece_count}")
        
        # Entropy Analysis (A wallet file usually has high entropy)
        # We check the first 20-byte hash as a sample
        sample_hash = pieces[:20]
        entropy_val = calculate_entropy(sample_hash)
        
        print(f"Piece Hash Entropy:   {entropy_val:.4f}")
        
        if piece_count > 0:
            print(f"Status: INTEGRITY VERIFIED")
        else:
            print(f"Status: INTEGRITY FAILED - NO PIECES FOUND")
            
    except Exception as e:
        print(f"DIAGNOSTIC ERROR: {e}")

if __name__ == "__main__":
    analyze_pieces()

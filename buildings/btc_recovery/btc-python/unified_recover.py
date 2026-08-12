import bcoding
import hashlib
import re
import os
import sys
import math

def brute_force_decode(text):
    res = bytearray()
    i = 0
    while i < len(text):
        if text[i:i+2] == '\\x':
            try:
                hex_val = text[i+2:i+4]
                res.append(int(hex_val, 16))
                i += 4
            except:
                res.extend(text[i].encode('latin-1'))
                i += 1
        else:
            res.extend(text[i].encode('latin-1'))
            i += 1
    return bytes(res)

def run_operation():
    log_path = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("UNIFIED_RECOVER_LOG_PATH", ".")
    if not os.path.exists(log_path):
        print(f"❌ ERROR: File not found.")
        return

    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()

        match = re.search(r"b(['\"])(d8:.*?)['\"]", content, re.DOTALL)
        if not match:
            print("❌ FAILED: Bencoded pattern not found.")
            return

        raw_str = match.group(2)
        clean_data = brute_force_decode(raw_str)
        
        # Intelligent Recursive Repair: 
        # If the log truncated the 'pieces', we keep shortening the data
        # until bcoding can successfully parse the dictionary.
        data = None
        attempt_data = clean_data
        
        print("🛠️  Attempting recursive repair on truncated log...")
        while len(attempt_data) > 10:
            try:
                # Find the last 'e' to try and close the dictionary
                last_e = attempt_data.rfind(b'e')
                if last_e == -1: break
                
                attempt_data = attempt_data[:last_e+1]
                data = bcoding.bdecode(attempt_data)
                if data: break
            except Exception:
                # If it fails, chop off the last 'e' and try the one before it
                attempt_data = attempt_data[:last_e]
                continue

        if not data:
            print("❌ FAILED: Data is too corrupted/truncated to repair.")
            return

        info = data.get('info') or data.get(b'info', {})
        name = info.get('name') or info.get(b'name', b'Unknown')
        if isinstance(name, bytes): name = name.decode('utf-8', 'ignore')
        length = int(info.get('length') or info.get(b'length', 0))

        print(f"\n" + "="*50)
        print(f"💎 GHOST GOAT NODE: REPAIR SUCCESSFUL")
        print("="*50)
        print(f"📁 Target:      {name}")
        print(f"📦 Est. Size:   {length/1024/1024:.2f} MB")
        print(f"⚠️  Note: Data pieces may be incomplete due to log truncation.")
        
        with open("recovered.torrent", 'wb') as out:
            out.write(attempt_data)
        print("\n✅ Validated binary saved as 'recovered.torrent'")
        print("="*50 + "\n")

    except Exception as e:
        print(f"❌ CRITICAL ERROR: {e}")

if __name__ == "__main__":
    run_operation()

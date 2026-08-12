# filename: fix_torrent.py
import bcoding
import re
import os
import sys

def repair_torrent(file_path):
    try:
        with open(file_path, 'rb') as f:
            raw = f.read()
        
        # Look for the piece data declaration: pieces10920:
        # We need to find where the actual data starts after the colon
        match = re.search(rb'pieces(\d+):', raw)
        if not match:
            print("❌ Could not find pieces length declaration.")
            return

        expected_length = int(match.group(1))
        header_end = match.end()
        
        # Calculate how much data we actually have after the colon
        actual_data = raw[header_end:]
        # Remove any trailing junk like (ml-dev) ninja...
        if b' ' in actual_data:
            actual_data = actual_data.split(b' ')[0]
            
        current_len = len(actual_data)
        missing_len = expected_length - current_len
        
        print(f"🛠️  Repairing: Expected {expected_length} bytes, found {current_len}.")
        
        # Construct fixed pieces field
        fixed_pieces = actual_data + (b'\x00' * missing_len)
        
        # Rebuild the file: Everything up to the colon + fixed pieces + closing 'ee'
        # Torrent ends with 'ee' (one for info dict, one for root dict)
        fixed_content = raw[:header_end] + fixed_pieces + b'ee'
        
        with open("fixed_wallet.torrent", 'wb') as out:
            out.write(fixed_content)
            
        print("✅ Success: 'fixed_wallet.torrent' created.")
        
        # Final Verification
        with open("fixed_wallet.torrent", 'rb') as f:
            data = bcoding.bdecode(f)
            name = data[b'info'][b'name'].decode()
            print(f"📂 Recovered Name: {name}")
            
    except Exception as e:
        print(f"❌ Repair failed: {e}")

if __name__ == "__main__":
    repair_torrent(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FIX_TORRENT_PATH", "."))

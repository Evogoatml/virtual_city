import bcoding
import hashlib
import re
import os
import sys

def bitwise_decode(text):
    h2n = {c: i for i, c in enumerate("0123456789abcdef")}
    text = text.lower()
    res = bytearray()
    i = 0
    while i < len(text):
        if text[i:i+2] == "\\x":
            try:
                high_n = h2n.get(text[i+2])
                low_n = h2n.get(text[i+3])
                if high_n is not None and low_n is not None:
                    # Bitwise assembly: (High << 4) | Low
                    res.append((high_n << 4) | low_n)
                    i += 4
                    continue
            except:
                pass
        res.append(ord(text[i]) & 0xFF)
        i += 1
    return bytes(res)

def run():
    # path = '/mnt/c/Users/Willi/Documents/btc/jargen.txt.txt'
    import os, sys
    def get_path():
        if len(sys.argv) > 1:
            return sys.argv[1]
        env = os.environ.get('FINAL_RECONSTRUCT_PATH')
        if env:
            return os.path.expanduser(env)
        return '.'  # fallback (current directory)
    path = get_path()
    if not os.path.exists(path):
        print("❌ Path Error")
        return

    with open(path, 'r', encoding='utf-8', errors='ignore') as f:
        log_content = f.read()

    match = re.search(r"b(['\"])(d8:.*?)(\1|$)", log_content, re.DOTALL)
    if not match:
        print("❌ Pattern Match Error")
        return

    # Step 1: Bitwise Reconstruction
    binary_data = bitwise_decode(match.group(2))

    # Step 2: Structural Integrity Check
    len_match = re.search(rb'pieces(\d+):', binary_data)
    if not len_match:
        print("❌ Pieces Header Error")
        return

    expected_len = int(len_match.group(1))
    pieces_start = len_match.end()
    existing_pieces = binary_data[pieces_start:]
    padding = max(0, expected_len - len(existing_pieces))
    
    # Final Stream Construction
    final_stream = binary_data[:pieces_start] + existing_pieces + (b'\x00' * padding) + b'ee'

    try:
        data = bcoding.bdecode(final_stream)
        info = data.get(b'info') or data.get('info')
        
        # Type-Agnostic Extraction
        def safe_name(d):
            n = d.get(b'name') or d.get('name')
            return n.decode('utf-8', 'ignore') if isinstance(n, bytes) else n

        name = safe_name(info)
        info_hash = hashlib.sha1(bcoding.bencode(info)).hexdigest()
        length = info.get(b'length') or info.get('length', 0)

        print("\n" + "="*50)
        print("🦾 BITWISE OPERATOR: RECONSTRUCTION SUCCESS")
        print("="*50)
        print(f"Target:    {name}")
        print(f"Hash:      {info_hash}")
        print(f"Size:      {int(length)/1024/1024:.2f} MB")
        print("="*50)
        
        with open("recovered_wallet.torrent", 'wb') as out:
            out.write(final_stream)
        print("\n✅ Binary: recovered_wallet.torrent")

    except Exception as e:
        print(f"❌ Execution Error: {e}")

if __name__ == "__main__":
    run()

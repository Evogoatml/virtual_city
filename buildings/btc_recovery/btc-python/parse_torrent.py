import bcoding
import hashlib
import re
import os
import sys
from datetime import datetime

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

def parse_torrent(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
        match = re.search(r"b(['\"])(d8:.*?)['\"]", content, re.DOTALL)
        if not match:
            print("FAILED: Data not found.")
            return
        raw_str = match.group(2)
        clean_data = brute_force_decode(raw_str)
        last_e = clean_data.rfind(b'e')
        if last_e != -1:
            clean_data = clean_data[:last_e+1]
        data = bcoding.bdecode(clean_data)
        info = data.get('info') or data.get(b'info', {})
        raw_info = bcoding.bencode(info)
        info_hash = hashlib.sha1(raw_info).hexdigest()
        name = info.get('name') or info.get(b'name', b'Unknown')
        if isinstance(name, bytes): name = name.decode('utf-8', 'ignore')
        print(f"\nRECOVERED TORRENT INFO")
        print(f"Name: {name}")
        print(f"Hash: {info_hash}")
        print(f"Size: {int(info.get(b'length', 0))/1024/1024:.2f} MB")
        with open("recovered.torrent", 'wb') as out:
            out.write(clean_data)
        print("File saved as 'recovered.torrent'\n")
    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    parse_torrent(sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PARSE_TORRENT_PATH", "."))

import os
import json
import sys

def get_search_paths():
    # If command line arguments provided, use them as directories
    if len(sys.argv) > 1:
        return sys.argv[1:]
    # Otherwise, check environment variable BTCTOOL_SEARCH_PATHS (comma-separated)
    env_paths = os.environ.get('BTCTOOL_SEARCH_PATHS')
    if env_paths:
        return [p.strip() for p in env_paths.split(',') if p.strip()]
    # Default to current directory
    return ['.']

search_paths = get_search_paths()

print("=== SEARCHING FOR WALLET FILES ===\n")

for search_dir in search_paths:
    if os.path.exists(search_dir):
        print(f"Checking: {search_dir}")
        for filename in os.listdir(search_dir):
            filepath = os.path.join(search_dir, filename)
            if os.path.isfile(filepath):
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                        if 'wallet_type' in data or 'keystore' in data:
                            print(f"\n✅ WALLET FOUND: {filename}")
                            print(f"   Path: {filepath}")
                            print(f"   Type: {data.get('wallet_type', 'unknown')}")
                            
                            # Check for keys
                            has_keystore = 'keystore' in data
                            has_keypairs = ('keypairs' in data or 
                                          ('keystore' in data and 'keypairs' in data.get('keystore', {})))
                            has_seed = ('seed' in data or 
                                       ('keystore' in data and 'seed' in data.get('keystore', {})))
                            
                            if has_keypairs:
                                print(f"   ✅✅✅ HAS PRIVATE KEYS!")
                                if 'keystore' in data and 'keypairs' in data['keystore']:
                                    print(f"   Key count: {len(data['keystore']['keypairs'])}")
                            if has_seed:
                                print(f"   ✅✅✅ HAS SEED!")
                            if not has_keypairs and not has_seed:
                                print(f"   ⚠️ Watch-only (no keys)")
                except Exception as e:
                    # Silently skip unreadable files
                    pass
    else:
        print(f"❌ Directory not found: {search_dir}\n")

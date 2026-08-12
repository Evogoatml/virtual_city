#!/usr/bin/env python3
"""
Bitcoin Private Key Scanner
Purpose: Scan folders for Bitcoin private keys (WIF, hex formats)
WARNING: Only use on your own systems and data. Unauthorized access is illegal.
"""

import os
import re
import json
import argparse
from pathlib import Path
from typing import List, Dict

class BTCKeyScanner:
    def __init__(self):
        # WIF (Wallet Import Format) patterns
        # Uncompressed: starts with 5, 51 chars base58
        # Compressed: starts with K or L, 52 chars base58
        self.wif_pattern = re.compile(r'\b[5KL][1-9A-HJ-NP-Za-km-z]{50,51}\b')
        
        # Hex private key pattern (64 hex characters)
        self.hex_pattern = re.compile(r'\b[0-9a-fA-F]{64}\b')
        
        # Common file extensions to scan
        self.text_extensions = {'.txt', '.json', '.csv', '.log', '.conf', 
                               '.key', '.dat', '.wallet', '.bak', '.md'}
        
        self.results = []
    
    def is_valid_wif(self, key: str) -> bool:
        """Basic validation for WIF format"""
        if len(key) not in [51, 52]:
            return False
        if key[0] not in ['5', 'K', 'L']:
            return False
        # Base58 character set check
        base58_chars = set('123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz')
        return all(c in base58_chars for c in key)
    
    def is_valid_hex_key(self, key: str) -> bool:
        """Basic validation for hex private key"""
        if len(key) != 64:
            return False
        try:
            int(key, 16)
            return True
        except ValueError:
            return False
    
    def scan_file(self, filepath: Path) -> List[Dict]:
        """Scan a single file for private keys"""
        findings = []
        
        try:
            # Try to read as text
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            
            # Search for WIF format keys
            wif_matches = self.wif_pattern.findall(content)
            for match in wif_matches:
                if self.is_valid_wif(match):
                    findings.append({
                        'file': str(filepath),
                        'type': 'WIF',
                        'key': match[:10] + '...' + match[-10:],  # Truncate for safety
                        'line': self._find_line_number(content, match)
                    })
            
            # Search for hex format keys
            hex_matches = self.hex_pattern.findall(content)
            for match in hex_matches:
                if self.is_valid_hex_key(match):
                    findings.append({
                        'file': str(filepath),
                        'type': 'HEX',
                        'key': match[:16] + '...' + match[-16:],  # Truncate for safety
                        'line': self._find_line_number(content, match)
                    })
            
            # Check for JSON wallet files
            if filepath.suffix == '.json':
                findings.extend(self._scan_json_wallet(filepath, content))
                
        except Exception as e:
            # Skip files that can't be read
            pass
        
        return findings
    
    def _find_line_number(self, content: str, search_str: str) -> int:
        """Find line number of a string in content"""
        lines = content.split('\n')
        for i, line in enumerate(lines, 1):
            if search_str in line:
                return i
        return 0
    
    def _scan_json_wallet(self, filepath: Path, content: str) -> List[Dict]:
        """Scan JSON files for wallet structures"""
        findings = []
        try:
            data = json.loads(content)
            # Common wallet JSON structures
            key_fields = ['private_key', 'privkey', 'privateKey', 'secret', 'key']
            
            def recursive_search(obj, path=""):
                if isinstance(obj, dict):
                    for key, value in obj.items():
                        if key.lower() in key_fields and isinstance(value, str):
                            findings.append({
                                'file': str(filepath),
                                'type': 'JSON_WALLET',
                                'key': value[:16] + '...' if len(value) > 16 else value,
                                'field': f"{path}.{key}" if path else key
                            })
                        else:
                            recursive_search(value, f"{path}.{key}" if path else key)
                elif isinstance(obj, list):
                    for i, item in enumerate(obj):
                        recursive_search(item, f"{path}[{i}]")
            
            recursive_search(data)
        except:
            pass
        
        return findings
    
    def scan_directory(self, directory: Path, recursive: bool = True) -> List[Dict]:
        """Scan directory for private keys"""
        print(f"Scanning directory: {directory}")
        
        if recursive:
            files = directory.rglob('*')
        else:
            files = directory.glob('*')
        
        for filepath in files:
            if not filepath.is_file():
                continue
            
            # Check if file extension is in our list
            if filepath.suffix.lower() in self.text_extensions or filepath.suffix == '':
                findings = self.scan_file(filepath)
                if findings:
                    self.results.extend(findings)
                    print(f"  [!] Found {len(findings)} potential key(s) in: {filepath}")
        
        return self.results
    
    def generate_report(self, output_file: str = None):
        """Generate a report of findings"""
        if not self.results:
            print("\n[+] No private keys found.")
            return
        
        print(f"\n[!] FOUND {len(self.results)} POTENTIAL PRIVATE KEY(S)")
        print("=" * 80)
        
        for i, result in enumerate(self.results, 1):
            print(f"\nFinding #{i}:")
            print(f"  File: {result['file']}")
            print(f"  Type: {result['type']}")
            if 'line' in result:
                print(f"  Line: {result['line']}")
            if 'field' in result:
                print(f"  Field: {result['field']}")
            print(f"  Key (truncated): {result['key']}")
        
        if output_file:
            with open(output_file, 'w') as f:
                json.dump(self.results, f, indent=2)
            print(f"\n[+] Results saved to: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description='Scan folders for Bitcoin private keys (for personal security audits only)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python btc_key_finder.py /path/to/folder
  python btc_key_finder.py /path/to/folder --recursive
  python btc_key_finder.py /path/to/folder --output results.json
  python btc_key_finder.py . --no-recursive

WARNING: Only use this tool on your own systems and data.
Unauthorized access to others' private keys is illegal.
        '''
    )
    
    parser.add_argument('directory', type=str, help='Directory to scan')
    parser.add_argument('-r', '--recursive', action='store_true', default=True,
                       help='Scan subdirectories recursively (default: True)')
    parser.add_argument('--no-recursive', action='store_true',
                       help='Do not scan subdirectories')
    parser.add_argument('-o', '--output', type=str, help='Output JSON file for results')
    
    args = parser.parse_args()
    
    # Print warning
    print("=" * 80)
    print("BITCOIN PRIVATE KEY SCANNER")
    print("=" * 80)
    print("WARNING: This tool is for personal security audits only.")
    print("Only use on systems and data you own. Unauthorized access is illegal.")
    print("=" * 80)
    print()
    
    scanner = BTCKeyScanner()
    directory = Path(args.directory).resolve()
    
    if not directory.exists():
        print(f"Error: Directory does not exist: {directory}")
        return
    
    if not directory.is_dir():
        print(f"Error: Not a directory: {directory}")
        return
    
    # Scan directory
    recursive = args.recursive and not args.no_recursive
    scanner.scan_directory(directory, recursive=recursive)
    
    # Generate report
    scanner.generate_report(output_file=args.output)
    
    print("\n[+] Scan complete.")


if __name__ == '__main__':
    main()

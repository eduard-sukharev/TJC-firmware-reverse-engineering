#!/usr/bin/env python3
"""
TJC TFT Firmware Bootloader Header Parser and Resource Extractor

Usage:
    python3 tjc_bootloader.py                              # Use default tjc.tft
    python3 tjc_bootloader.py firmware.tft                 # Extract from custom file
    python3 tjc_bootloader.py firmware.tft --section 1      # Extract only section 1 (Resources)
    python3 tjc_bootloader.py firmware.tft --sections 0,1  # Extract sections 0 and 1
    python3 tjc_bootloader.py firmware.tft --all            # Extract all sections
"""

import argparse
import os
import struct
import sys

BOOTLOADER_OFFSET = 0x10000
ENTRY_SIZE = 12
NUM_ENTRIES = 12

SECTION_NAMES = {
    0: "Bootloader",
    1: "Resources",
    2: "Font",
    3: "Config",
    4: "Strings",
    5: "Events",
    6: "Code",
    7: "UserData",
    8: "UserCode",
}

def parse_bootloader_header(data):
    """Parse the bootloader header and return list of entries."""
    entries = []
    for i in range(NUM_ENTRIES):
        offset = BOOTLOADER_OFFSET + i * ENTRY_SIZE
        if offset + ENTRY_SIZE > len(data):
            break
        entry = data[offset:offset+ENTRY_SIZE]
        rel_offset = int.from_bytes(entry[0:4], 'little')
        size = int.from_bytes(entry[4:8], 'little')
        meta = int.from_bytes(entry[8:12], 'little')
        entries.append({
            'index': i,
            'rel_offset': rel_offset,
            'size': size,
            'meta': meta,
            'name': SECTION_NAMES.get(i, f"Section_{i}"),
            'file_offset': BOOTLOADER_OFFSET + rel_offset
        })
    return entries

def print_header(entries):
    """Print formatted bootloader header entries."""
    print("=" * 80)
    print(f"{'Idx':<5} {'Name':<12} {'RelOffset':>12} {'Size':>12} {'FileOffset':>12}")
    print("-" * 80)
    for e in entries:
        if e['size'] > 0:
            print(f"{e['index']:<5} {e['name']:<12} 0x{e['rel_offset']:08X} 0x{e['size']:08X} 0x{e['file_offset']:08X}")
    print("=" * 80)

def extract_section(data, entry, output_dir):
    """Extract a single section to a file."""
    abs_offset = entry['file_offset']
    size = entry['size']
    if abs_offset + size > len(data):
        print(f"Warning: Section {entry['index']} extends beyond file, truncating")
        size = len(data) - abs_offset
    
    section_data = data[abs_offset:abs_offset+size]
    filename = f"section_{entry['index']:02d}_{entry['name']}.bin"
    filepath = os.path.join(output_dir, filename)
    
    with open(filepath, 'wb') as f:
        f.write(section_data)
    
    return filepath, len(section_data)

def main():
    parser = argparse.ArgumentParser(
        description='Parse TJC TFT bootloader header and extract sections'
    )
    parser.add_argument(
        'firmware',
        nargs='?',
        default='tjc.tft',
        help='Path to firmware file (default: tjc.tft)'
    )
    parser.add_argument(
        '--section', '-s',
        type=int,
        help='Extract only a specific section by index'
    )
    parser.add_argument(
        '--sections', 
        help='Extract specific sections by index (comma-separated, e.g., "0,1,7")'
    )
    parser.add_argument(
        '--all', '-a',
        action='store_true',
        help='Extract all non-empty sections'
    )
    parser.add_argument(
        '--output', '-o',
        default='.',
        help='Output directory (default: current directory)'
    )
    parser.add_argument(
        '--resources-only',
        action='store_true',
        help='Extract only the Resources section (section 1)'
    )
    
    args = parser.parse_args()
    
    if not os.path.exists(args.firmware):
        print(f"Error: File not found: {args.firmware}")
        sys.exit(1)
    
    with open(args.firmware, 'rb') as f:
        data = f.read()
    
    entries = parse_bootloader_header(data)
    print_header(entries)
    
    os.makedirs(args.output, exist_ok=True)
    
    sections_to_extract = []
    
    if args.resources_only:
        sections_to_extract = [e for e in entries if e['index'] == 1 and e['size'] > 0]
    elif args.section is not None:
        sections_to_extract = [e for e in entries if e['index'] == args.section and e['size'] > 0]
    elif args.sections:
        indices = [int(x.strip()) for x in args.sections.split(',')]
        sections_to_extract = [e for e in entries if e['index'] in indices and e['size'] > 0]
    elif args.all:
        sections_to_extract = [e for e in entries if e['size'] > 0]
    
    if sections_to_extract:
        print(f"\nExtracting {len(sections_to_extract)} section(s) to: {args.output}")
        for e in sections_to_extract:
            filepath, extracted_size = extract_section(data, e, args.output)
            print(f"  [{e['index']}] {e['name']}: {extracted_size} bytes -> {filepath}")
    else:
        print("\nNo sections to extract. Use --all, --section N, --sections N,M, or --resources-only")
    
    largest = max(entries, key=lambda e: e['size'])
    print(f"\nLargest section: {largest['name']} (index {largest['index']}, {largest['size']} bytes)")

if __name__ == "__main__":
    main()
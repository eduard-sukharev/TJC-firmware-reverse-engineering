# TJC_display - TJC TFT Firmware Image Extractor

Extracts bitmap images from TJC TFT firmware for Creality Ender-3 V3 SE 3D printer LCD display. The LCD screen model is TJC3224T132_011N_P04, closest publicly available for sale TJC screen model is TJC3224T132_011N_I_A01.

## Key Files

- `TFT.md` - Reverse engineering attempt at TFT firmware for screens by Nextion. TJC is Chinese ripoff of Nextion.
- `tjc.tft` - Main firmware (7.48 MB)
- `print_resource_table.py` - script to parse and print out Resource/Images table values
- `resource_table.txt` - parsed resource table printout
- `extract_*.py` - Various extraction scripts (check dates for latest working version)
- `extracted/` - Output directory
- `dwin-ico-tools/` - Reference DWIN tools for comparison

## Critical Offsets

- **Bootloader Header: 0x010000** (12 entries × 12 bytes = 144 bytes)
  - Entry 0-8: binary components (bootloader, resources, user code)
  - Entry 7: largest component = Resource/Images block (7.1 MB)
  - Entry 8: User code section (54 KB)

- **Resource/Images table: 0x38cf4** (derived from Entry 7 offset in bootloader header)
  - Found by: parse bootloader header at 0x010000, find entry with largest size
  - Entry size: 24 bytes each
  - Total entries: 2,628 (for this firmware)
  - Entry format: `magic2(4) | id(4) | rel_offset(4) | width(2) | height(2) | size(4) | extra(4)`
  - Actual data at: table_offset + rel_offset + 0x14

## Bootloader Header Parsing

To extract resources from any TJC/Nextion TFT file:

1. Read bootloader header at file offset **0x010000**
2. Each entry is 12 bytes: `rel_offset(4) | size(4) | meta(4)`
3. Calculate file offset: `0x010000 + rel_offset`
4. Find entry with **largest size** → this is the Resource block
5. Parse resource table at that file offset
6. Each resource entry (24 bytes) gives: dimensions, size, relative offset
7. Image data = table_offset + rel_offset + 0x14

Example (TJC3224T132_011N_P04):
- Entry 7: size=7,104,219 → Resource block at 0x38cf4
- Entry 8: size=54,289 → User code at 0x7ef3cf

## Encoding Status

**PARTIALLY RESOLVED**: Image resource block contains 20 bytes of leading metadata per resource. 

- First byte of metadata determines encoding:
  - `0x00` = RAW RGB565 (634 entries, ~24%)
  - `0x04` = TJC PROPRIETARY COMPRESSION (1994 entries, ~76%)

For RAW images, stored size ≈ expected (width × height × 2).
For COMPRESSED images, stored size ~30-60% of expected (e.g., 240x320: 92409 bytes vs 153600 expected).

Metadata structure:
- Bytes 0-3: Encoding flag (0x00=RAW, 0x04=compressed)
- Bytes 4-7: Possibly original size or checksum
- Bytes 8-19: Unknown

**COMPRESSION STILL UNRESOLVED**: Algorithm unknown. TJC uses proprietary encoding.

## Working Extractions

- **64 RAW images extracted**: Using compression flag (first byte of 20-byte metadata = 0x00), excluding 4x2 placeholders
  - 20x20 icons (62 entries)
  - 24x24 icons (2 entries)
  - Convert RGB565 LE to RGB for PNG output

- **1994 COMPRESSED images**: Not yet decodable
  - TJC proprietary compression algorithm unknown

- **570 placeholders skipped**: 4x2 pixel images (likely cursor/indicator placeholders)

## Dependencies

- Python 3
- Pillow (PIL)
- Node.js (for pHash comparison)

## Commands

```bash
# Extract verified icons
python3 extract_verified.py

# Run comparison against reference
node phash.js test.png ref.png  # in ~/.agents/skills/image-compare-phash/scripts/
```

## What NOT to Do

- Don't assume resource table offset is 0x38cf0 - the actual images table offset is defined in Bootloader header as one of the components
- Don't use DWIN 9.ICO format - TJC uses different format
- Don't assume bootloader header has exactly 8 entries - it has 12 (entries 9-11 may be empty)

## Open Questions

1. ~~What is the exact encoding of the image data blocks?~~ - First byte of metadata: 0x00=RAW, 0x04=compressed
2. ~~What is the resource table metadata/magic bit/flag that defines whether the image is raw RGB565 or has some kind of compression applied?~~ - Confirmed: byte 0 of 20-byte metadata = compression flag
3. What is the TJC proprietary compression algorithm?
4. What do bytes 4-19 of the 20-byte metadata encode? (original size? checksum?)

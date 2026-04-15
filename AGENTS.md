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

**UNRESOLVED**: Image resource block contains additional 20 bytes of leading metadata. Actual image data at resource offsets +0x14 is either raw RGB565 (usually for 20x20 images), or some kind of compression encoding (for larger images). Stored data is ~60% of expected raw size.

- 240x320 image: 92409 bytes stored vs 153600 expected (60%)

## Working Extractions

- **20x20 icons at verified offsets**: Extracted using blank separation bytes heuristics, mapped into icons.csv:
  - Small 20x20 icons are mostly confirmed working, use with simple RGB565 LE data encoding
  - These match reference icons 11, 28, 30 from dwin-ico-tools/Marlin_7

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

1. What is the exact encoding of the image data blocks?
2. What is the resource table metadata/magic bit/flag that defines whether the image is raw RGB565 or has some kind of compression applied?
3. Is control word = skip N pixels vs count of valid pixels?
4. When compression used, does each 10-word (20-byte) block encode 8 pixels?

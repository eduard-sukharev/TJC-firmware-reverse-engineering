# TJC_display - TJC TFT Firmware Image Extractor

Extracts bitmap images from TJC TFT firmware for Creality Ender-3 V3 SE 3D printer LCD display.

## Key Files

- `TFT.md` - Reverse engineering attempt at TFT firmware for screens by Nextion. TJC is Chinese ripoff of Nextion.
- `tjc.tft` - Main firmware (7.48 MB)
- `print_resource_table.py` - script to parse and print out Resource table values
- `resource_table.txt` - parsed resource table printout
- `extract_*.py` - Various extraction scripts (check dates for latest working version)
- `extracted/` - Output directory
- `dwin-ico-tools/` - Reference DWIN tools for comparison

## Critical Offsets

- **Resource table: 0x38cf0** (NOT 0x38cf4 - this was the bug)
- Entry size: 24 bytes each
- Entry format: `magic1(4) | magic2:0x0301600a or 0x0301640a(4) | resource_id(4) | offset(4) | image_width(2) | image_height(2) | data_size(4)`

## Encoding Status

**UNRESOLVED**: Image data at resource offsets is either raw RGB565 (usually for 20x20 images), or some kind of compression encoding (for larger images). Stored data is ~60% of expected raw size.

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

- Don't assume resource table offset is 0x38cf4 - it's 0x38cf0
- Don't use DWIN 9.ICO format - TJC uses different format

## Open Questions

1. What is the exact encoding of the image data blocks?
2. What is the resource table metadata/magic bit/flag that defines whether the image is raw RGB565 or has some kind of compression applied?
3. Is control word = skip N pixels vs count of valid pixels?
4. When compression used, does each 10-word (20-byte) block encode 8 pixels?

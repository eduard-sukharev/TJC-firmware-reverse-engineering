# TJC/Nextion display firmware reverse engineering

Nextion/TJC TFT Firmware reverse engineering for Creality Ender-3 V3 SE 3D Printer LCD Display.

The LCD screen model is **TJC3224T132_011N_P04**, closest publicly available for sale is **TJC3224T132_011N_I_A01**. TJC is a Chinese clone of Nextion.

## Background

This project has major goal: be able to modify LCD screen firmware functionality. The minor goal is a bit more realistic: allow extracting and updating the graphical assets from the original firmware.

The original firmware file (`tjc.tft`, 7.48 MB) comes from the Ender-3 V3 SE's LCD controller.

## Reverse Engineering Sources

This reverse engineering effort draws heavily from the following sources:

### Primary References

- **[nxt-doc](https://github.com/UNUF/nxt-doc)** - Comprehensive documentation on Nextion/TJC firmware structure. This repository was the foundational reference for understanding the TFT file format and resource parsing. The current TFT.md file is a fork of their work.

- **[TJC3224 Reverse Engineering](https://jpcurti.github.io/E3V3SE_display_klipper/tjc3224_reverse_engineering.html)** - Detailed walkthrough of TJC firmware internals with specific analysis for the E3V3SE display. Essential for understanding the bootloader header structure and resource tables.

### Honorable Mention

- **[Ender-3V3-SE](https://github.com/navaismo/Ender-3V3-SE)** - Community fork of original firmware, that sparkled this research on the Ender-3 V3 SE display firmware.

## Why This is Still Ongoing

Reverse engineering the TJC firmware is an ongoing effort because:

1. ~~**Proprietary compression**~~ - **SOLVED.** The custom nibble-RLE format is
   fully decoded, including the literal-block escape that caused the long-standing
   misalignment. All 2628 images extract cleanly.

2. ~~**Alignment artifacts**~~ - **SOLVED.** The artifacts came from blocks whose
   control field is `1F 11 11 11`: those are *literal* blocks emitting 8 pixels,
   but a naive run-length reading produced 22, over-running by exactly 14 pixels
   each and shifting everything after them.

3. **No official documentation** - TJC does not publish any firmware specifications. All knowledge is derived from reverse engineering binary files and comparing outputs with known-good images from the display.

4. **Still open** - re-encoding modified images back into a valid `.tft`, and the
   font section (which appears to be a straight copy of the `.zi` files).

## AI-Assisted Research

This reverse engineering project was significantly advanced through conversations with **OpenCode Zen** and its free models:

- **MiniMax M2.5 Free** - Primary reasoning and algorithm discovery
- **Nemotron 3 Super Free** - Pattern analysis and hypothesis refinement
- **BigPickle** - Additional insight and verification

These models helped analyze the binary data, identify patterns in the compression blocks, and work through the nibble-RLE decompression algorithm.

## Project Structure

```
TJC_display/
  tjc.tft               - Main firmware (7.48 MB)
  tjc_decompress.py    - Core decompression module
  extract_all.py       - Extract ALL graphical assets
  extract_image.py     - Extract a single image by id/dimensions
  test_tjc_decompress.py - Whole-firmware validation of the decoder
  print_resource_table.py  - Resource table parser
  resource_table.txt  - Parsed resource table output
  extracted_all/      - Extracted images output directory
```

### Key Files

| File | Description |
|------|-------------|
| `tjc_decompress.py` | Nibble-based RLE decompression and PNG creation |
| `extract_all.py` | Extract all real graphical assets from the firmware |
| `extract_image.py` | Extract and decompress a single image by id or size |
| `test_tjc_decompress.py` | Validates the decoder against every resource |
| `print_resource_table.py` | Parse and print all resources from the firmware |

## Usage

### Extract Everything

```bash
python3 extract_all.py -f tjc.tft -o extracted_all
```

Extracts the 2058 real assets (64 RAW + 1994 compressed) with zero failures.
570 further entries are unassigned placeholder slots (4x2 solid white) and are
skipped unless you pass `--include-placeholders`.

### Extract a Specific Image

```bash
python3 extract_image.py -r Resources.bin -i 2 -o extracted
```

### Parse Resource Table

```bash
python3 print_resource_table.py
```

This parses the resource table and outputs all entries with dimensions, sizes, and offsets.

### Using the Decompression Module

```python
from tjc_decompress import decompress_and_create_image

# Decompress image data (includes 20-byte resource header)
img = decompress_and_create_image(compressed_data, width, height)

# Or use individual functions
from tjc_decompress import decompress_image_data, rgb565_to_rgb

pixels = decompress_image_data(compressed_data)
```

## Compression Algorithm (solved)

### Resource Header (20 bytes per resource)
- **Byte 0**: Compression flag (`0x00` = RAW, `0x04` = COMPRESSED)
- **Bytes 4-7**: uint32 LE, the total *used* length of header + payload. The
  resource table's `size` may be larger; the excess is padding and decoding it
  corrupts the image.

### Block Structure (20 bytes per block)
- **Bytes 0-3**: Control (4 bytes)
- **Bytes 4-19**: 8 RGB565 pixel values, little-endian (16 bytes)

### Two block types

**Literal block** - control field is exactly `1F 11 11 11`. Emit all 8 pixels
once each. Missing this rule is what caused every previously reported
"misalignment artifact".

**RLE block** - split each control byte into nibbles, **low nibble first**,
giving 8 repeat counts paired with the 8 pixels; a count of 0 emits nothing.

```
counts = [b0&0xF, b0>>4, b1&0xF, b1>>4, b2&0xF, b2>>4, b3&0xF, b3>>4]
output = p0*n0, p1*n1, ... p7*n7
```

Output is row-major. The encoder additionally aligns every group of 4 output
rows to a block boundary; decoders don't need this, but it is a powerful
invariant for validating an implementation.

### Verification
Three independent invariants hold at **100%** across all 1994 compressed
resources: exact pixel count, exact 4-row stripe alignment, and exact consumed
byte length. Run `python3 -m pytest test_tjc_decompress.py -v`.

## Critical Offsets

- **Bootloader Header**: `0x010000` (12 entries × 12 bytes = 144 bytes)
  - Entry 0-8: binary components (bootloader, resources, user code)
  - Entry 7: largest component = Resource/Images block (7.1 MB)
  - Entry 8: User code section (54 KB)

- **Resource/Images table**: `0x38cf4`
  - Entry size: 24 bytes each
  - Total entries: 2,628
  - Entry format: `magic2(4) | id(4) | rel_offset(4) | width(2) | height(2) | size(4) | extra(4)`

## Dependencies

- Python 3
- Pillow (PIL)

## License

This project is for educational and research purposes. All firmware files belong to their respective owners.

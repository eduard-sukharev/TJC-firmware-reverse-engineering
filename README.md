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

1. **Proprietary compression** - TJC uses a custom nibble-based run-length encoding that is not documented anywhere. While the basic algorithm has been cracked, edge cases and different compression modes are still being analyzed.

2. **Varying image formats** - Not all images use the same compression scheme. Some images may be stored uncompressed (RAW RGB565), others use the nibble-RLE algorithm, and there may be additional variants yet to discover.

3. **No official documentation** - TJC does not publish any firmware specifications. All knowledge is derived from reverse engineering binary files and comparing outputs with known-good images from the display.

4. **Alignment artifacts** - Some extracted images show block misalignment issues, suggesting there may be additional header or control bytes we haven't fully accounted for.

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
  extract_image_102x115.py - Example extraction script
  print_resource_table.py  - Resource table parser
  resource_table.txt  - Parsed resource table output
  extracted/          - Extracted images output directory
```

### Key Files

| File | Description |
|------|-------------|
| `tjc_decompress.py` | Nibble-based RLE decompression and PNG creation |
| `extract_image_102x115.py` | Script to extract and decompress a 102x115 image |
| `print_resource_table.py` | Parse and print all resources from the firmware |

## Usage

### Extract a Specific Image

```bash
python3 extract_image_102x115.py
```

This extracts the 102x115 image (the first main screen icon, "Print") and saves it to `extracted/image_102x115.png`.

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

## Compression Algorithm

The TJC proprietary compression uses nibble-based run-length encoding:

### Block Structure (20 bytes per block)
- **Bytes 0-3**: Control (4 bytes) = 8 nibbles (repeat counts)
- **Bytes 4-19**: 8 RGB565 pixel values (16 bytes)

### Decompression Process
1. Each control byte is split into 2 nibbles → 8 nibbles total
2. Each nibble = repeat count for corresponding pixel
3. Nibble values: 0-15 (represents how many times to repeat that pixel)
4. For block with nibbles [n0,n1,n2,n3,n4,n5,n6,n7] and pixels [p0,p1...p7]:
   - Output: p0 repeated n0 times, p1 repeated n1 times, etc.

### Resource Header (20 bytes per resource)
Each compressed resource has a 20-byte header:
- **Byte 0**: Compression flag (0x00 = RAW, 0x04 = COMPRESSED)
- **Bytes 1-19**: Additional metadata

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

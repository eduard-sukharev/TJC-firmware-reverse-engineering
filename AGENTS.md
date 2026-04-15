# TJC_display - TJC TFT Firmware Image Extractor

Extracts bitmap images from TJC TFT firmware for Creality Ender-3 V3 SE 3D printer LCD display. The LCD screen model is TJC3224T132_011N_P04, closest publicly available for sale TJC screen model is TJC3224T132_011N_I_A01.

## Key Files

- `TFT.md` - Reverse engineering attempt at TFT firmware for screens by Nextion. TJC is Chinese ripoff of Nextion.
- `tjc.tft` - Main firmware (7.48 MB)
- `tjc_decompress.py` - TJC image decompression module
- `extract_image_102x115.py` - Script to extract and decompress a 102x115 image
- `print_resource_table.py` - Script to parse and print out Resource/Images table values
- `resource_table.txt` - Parsed resource table printout
- `extracted/` - Output directory

## Compression Algorithm SOLVED

The TJC proprietary compression uses nibble-based run-length encoding:

### Block Structure (20 bytes per block)
```
Bytes 0-3:   Control (4 bytes) = 8 nibbles (repeat counts)
Bytes 4-19: 8 RGB565 pixel values (16 bytes)
```

### Decompression Process
1. Each control byte split into 2 nibbles → 8 nibbles total
2. Each nibble = repeat count for corresponding pixel
3. Nibble values: 0-15 (represents how many times to repeat that pixel)
4. For block with nibbles [n0,n1,n2,n3,n4,n5,n6,n7] and pixels [p0,p1...p7]:
   - Output: p0 repeated n0 times, p1 repeated n1 times, etc.

### Resource Header (20 bytes per resource)
Each compressed resource has a 20-byte header:
- Byte 0: Compression flag (0x00 = RAW, 0x04 = COMPRESSED)
- Bytes 1-19: Additional metadata

## Usage

```bash
# Extract and decompress a 102x115 image
python3 extract_image_102x115.py
```

The extraction script will:
1. Find resource entry by dimensions (102x115)
2. Extract compressed data from Resources.bin
3. Skip 20-byte resource header
4. Decompress using nibble-RLE algorithm
5. Save as PNG to extracted/image_102x115.png

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
  - Actual data at: rel_offset (directly in Resources.bin)

## Bootloader Header Parsing

To extract resources from any TJC/Nextion TFT file:

1. Read bootloader header at file offset **0x010000**
2. Each entry is 12 bytes: `rel_offset(4) | size(4) | meta(4)`
3. Calculate file offset: `0x010000 + rel_offset`
4. Find entry with **largest size** → this is the Resource block
5. Parse resource table at that file offset
6. Each resource entry (24 bytes) gives: dimensions, size, relative offset
7. Image data at rel_offset in Resources.bin

## Code Reference

### tjc_decompress.py

```python
from tjc_decompress import decompress_and_create_image

# Decompress image data (includes 20-byte resource header)
img = decompress_and_create_image(compressed_data, width, height)

# Or use individual functions
from tjc_decompress import decompress_image_data, rgb565_to_rgb

pixels = decompress_image_data(compressed_data)
# pixels is list of RGB565 values
```

### extract_image_102x115.py

Find and extract images by modifying these parameters:
- `IMAGE_WIDTH = 102`
- `IMAGE_HEIGHT = 115`

## Dependencies

- Python 3
- Pillow (PIL)

## Commands

```bash
# Extract 102x115 image
python3 extract_image_102x115.py
```

## Remaining Issues

- Some images may have block misalignment in the middle (shifting artifacts)
- Compression flag interpretation needs verification for other image sizes
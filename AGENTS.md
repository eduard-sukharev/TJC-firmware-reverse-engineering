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

### Resource Metadata Header (20 bytes per resource)
Each compressed resource has a 20-byte metadata header:
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

- **Firmware Partition Table: 0x010000** (12 entries × 12 bytes = 144 bytes)
  - Entry 0: Bootloader partition
  - Entry 1: Input partition
  - Entry 2: QR partition
  - Entry 3-6: Various binary components
  - Entry 7: Resources partition (largest, 7.1 MB)
  - Entry 8: User code partition (54 KB)

- **Resource Mapping Table: 0x38cf4** (derived from Entry 7 offset in partition table)
  - Found by: parse partition table at 0x010000, find entry with largest size
  - Entry size: 24 bytes each
  - Total entries: 2,641 (for this firmware)
  - Entry format: `magic2(4) | id(4) | rel_offset(4) | width(2) | height(2) | size(4) | extra(4)`
  - Actual data at: rel_offset (directly in Resources partition)

## Firmware Partition Table Parsing

To extract resources from any TJC/Nextion TFT file:

1. Read firmware partition table at file offset **0x010000**
2. Each partition entry is 12 bytes: `rel_offset(4) | size(4) | meta(4)`
3. Calculate file offset: `0x010000 + rel_offset`
4. Find entry with **largest size** → this is the Resources partition
5. Parse resource mapping table at that file offset
6. Each resource entry (24 bytes) gives: dimensions, size, relative offset
7. Image data at rel_offset in Resources partition (+ 20-byte metadata header)

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

### Flag 0x04 (real firmware compression) is still broken — 2026-09-04 findings

Real firmware (`tjc.tft`/`Resources.bin`) resources use only two compression
flags: `0x00` RAW (634 of 2628) and `0x04` COMPRESSED (1994 of 2628). Flag
`0x01` (the one `tjc_decompress.py`/`test_rle01.py` actually validate,
lo-nibble-first) **never occurs in real firmware** — it only appears in this
repo's own synthetic `test.tft`. So the passing `0x01` test does not validate
the `0x04` path that real icons use.

Deep empirical investigation of resource id=2 (102x115, "Print" icon) found:

- **Structurally validated**: block layout (20B = 4B control → 8 nibbles +
  8×RGB565), hi-nibble-first, LE RGB565, row-major raster, width=102 straight
  from the resource table. Proof: decoding the 32 leading background-only
  blocks lands on an *exact* integer row boundary (row 32.0, zero drift) —
  not possible by chance with a wrong width or wrong nibble scheme. Detail
  block colors also plausibly match the reference icon's real colors.
- **Still broken**: despite the above, decoded content for all 8 sibling
  102x115 icons (Print/Prepare/Control/Leveling x2) lands compressed into the
  upper-left of the canvas instead of matching the reference art. The pattern
  is consistent across all 8 icons, not per-image noise, so it's systematic.
- Brute-forced and ruled out (against `001-reference.jpg` ground truth):
  reversed nibble order, reversed control-byte order, reversed pixel-index
  mapping, big-endian RGB565, nibble+1 off-by-one, column-major scan,
  tiled/banded scan order, alternate reshape widths/strides.
- **New lead**: the 20-byte resource header's bytes 4-7 (LE uint32) is
  *always* an exact multiple of 20, and is roughly 90-95% of the resource's
  total block count (`(size-20)//20`). Looks like it could be an exact
  block/byte stop-position distinct from the naive `width*height` pixel
  target, but the exact relationship isn't nailed down yet.
- `icons.csv` (from an earlier session, perceptual-hash-matched against a
  labeled external icon set) already flags this same resource as
  "broken"/unmatched, and flags most 20x20 icons as "correct" — so the bug is
  size/complexity-correlated, not universal.

Most promising next steps: (1) decode the field at header bytes 4-7 against
many more `0x04` resources to find its exact formula, (2) disassemble the
bootloader partition (partition entry 0, 17570 bytes at file offset
`0x10090`) which contains the actual firmware decompression routine — this is
the authoritative source but requires ISA identification first, (3) compile a
new test asset through the real TJC editor (`USARTHMIsetup_1.65.5.exe`, not
currently runnable in this environment — needs Windows/Wine) sized to force
flag `0x04` output, to get a genuine known-plaintext pair like the one that
validated flag `0x01`.
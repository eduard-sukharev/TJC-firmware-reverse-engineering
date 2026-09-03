# TJC_display - TJC TFT Firmware Image Extractor

Extracts bitmap images from TJC TFT firmware for Creality Ender-3 V3 SE 3D printer LCD display. The LCD screen model is TJC3224T132_011N_P04, closest publicly available for sale TJC screen model is TJC3224T132_011N_I_A01.

## Key Files

- `TFT.md` - Reverse engineering attempt at TFT firmware for screens by Nextion. TJC is Chinese ripoff of Nextion.
- `tjc.tft` - Main firmware (7.48 MB)
- `tjc_decompress.py` - TJC image decompression module (format fully solved)
- `extract_all.py` - Extract **all** graphical assets from a .tft or Resources.bin
- `extract_image.py` - Extract/decompress a single image by id or dimensions
- `test_tjc_decompress.py` - Validates the decoder against the whole firmware
- `print_resource_table.py` - Script to parse and print out Resource/Images table values
- `resource_table.txt` - Parsed resource table printout
- `extracted_all/` - Output directory

## Compression Algorithm SOLVED (fully, verified on all 2628 resources)

### Resource Metadata Header (20 bytes per resource)
- **Byte 0**: Compression flag — `0x00` = RAW, `0x04` = COMPRESSED
- **Bytes 4-7**: uint32 LE — total used byte length of *header + payload*.
  Anything in the resource table's `size` beyond this is trailing padding and
  must NOT be decoded. (This field is what makes the decode exact.)
- Bytes 1-3, 8-19: zero in the stock firmware

RAW payload is just `width*height` little-endian RGB565 pixels.

### Block Structure (20 bytes per block)
```
Bytes 0-3:   Control (4 bytes)
Bytes 4-19:  8 RGB565 pixel values, little-endian (16 bytes)
```

### Two kinds of block

**1. Literal block** — control field is exactly `1F 11 11 11`.
All 8 pixels are emitted **once each** (8 pixels total). This is the key that
was missing for a long time: read naively as run counts that control field
would yield 22 pixels, so every literal block over-produced by exactly 14
pixels and shifted the rest of the image.

**2. RLE block** — each control byte is split into two nibbles,
**low nibble first, then high nibble**, giving 8 repeat counts matched
one-to-one with the 8 pixels. A count of 0 emits nothing.

```
counts = [b0&0xF, b0>>4, b1&0xF, b1>>4, b2&0xF, b2>>4, b3&0xF, b3>>4]
output  = p0*n0, p1*n1, ... p7*n7
```

Pixels are emitted in plain row-major order.

### Encoder stripe alignment (diagnostic, not needed to decode)
The encoder aligns the stream so that **every group of 4 output rows ends on a
20-byte block boundary**, zero-padding unused slots in the last block of each
group. A decoder does not need to implement this, but it is an extremely
useful invariant for validating a candidate decoder: with the literal-block
rule handled correctly, all 4-row stripes sum exactly across all 1994
compressed resources; with any error they do not.

### How it was verified
Three independent invariants, all at **100%** over all 1994 compressed
resources (see `test_tjc_decompress.py`):
1. decoded pixel count == `width * height`
2. every 4-row stripe's counts sum exactly
3. bytes consumed == the length recorded at header bytes 4-7

Plus visual confirmation: decoded icons are pixel-clean and match the
reference art.

## Usage

```bash
# Extract every real graphical asset (2058 images) from the firmware
python3 extract_all.py -f tjc.tft -o extracted_all

# Include the 570 blank placeholder slots as well
python3 extract_all.py -f tjc.tft -o extracted_all --include-placeholders

# Same, from a Resources.bin partition dump, also dumping raw RGB565
python3 extract_all.py -r Resources.bin -o extracted_all --raw

# Extract a single resource by id
python3 extract_image.py -r Resources.bin -i 2 -o extracted

# Verify the decoder against the whole firmware
python3 -m pytest test_tjc_decompress.py -v
```

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

### extract_all.py

Parses the partition table, walks the resource mapping table and decodes every
entry. Reports a per-format tally and a non-zero exit status if anything fails.

## Dependencies

- Python 3
- Pillow (PIL)

## Status

The image compression is **fully solved**. `extract_all.py` decodes all 2628
resource-table entries from `tjc.tft` with zero failures, and
`test_tjc_decompress.py` locks the format in with three independent invariants
that all hold at 100%.

Of those 2628 entries, **570 are placeholders**: unassigned picture slots the
editor emits as a 4x2 solid-white RAW dummy (size 36, `extra=0`). They are
skipped by default, leaving **2058 real assets** (64 RAW + 1994 compressed).
Pass `--include-placeholders` to write them out too.

The split is unambiguous - a colour-count census over every entry gives 570
images with exactly 1 colour, 1 with 2 colours (`id=179`, a genuine 18x18
indicator), and 2057 with 6 or more. There is no ambiguous middle, so
filtering on "solid single colour" discards placeholders and nothing else.

### Remaining work

- Re-encoding (compressing modified images back into a valid `.tft`) is not
  implemented yet; only extraction is.
- Fonts (the section after the pictures) are still unparsed. They appear to be
  a straight copy of the corresponding `.zi` files.
- `icons.csv` / `matches.txt` / `full_mapping.txt` were produced by an older,
  buggy decoder and their "broken"/"correct" labels are obsolete - the
  resource-ID-to-icon-name mapping should be redone against the now-correct
  extraction.
- The user code partition (partition entry 8) is only partially understood.

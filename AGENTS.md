# TJC_display - TJC TFT Firmware Image Extractor

Extracts bitmap images from TJC TFT firmware for Creality Ender-3 V3 SE 3D printer LCD display. The LCD screen model is TJC3224T132_011N_P04, closest publicly available for sale TJC screen model is TJC3224T132_011N_I_A01.

## Key Files

- `TFT.md` - Reverse engineering attempt at TFT firmware for screens by Nextion. TJC is Chinese ripoff of Nextion.
- `tjc.tft` - Main firmware (7.48 MB)
- `tjc_decompress.py` - TJC image decompression module (format fully solved)
- `extract_all.py` - Extract **all** graphical assets from a .tft or Resources.bin
- `build_firmware.py` - Build a customised .tft from a directory of replacement assets
- `tjc_compress.py` - Encoder (inverse of tjc_decompress)
- `tjc_checksums.py` - The four firmware CRCs: verify and re-seal
- `assets/` - Input directory for builds (kept separate from `extracted_all/`)
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

## Building a Customised Firmware

`build_firmware.py` writes a **new** firmware from a directory of replacement
assets. The original is only ever read.

```bash
python3 build_firmware.py                       # assets/ -> tjc_custom.tft
python3 build_firmware.py -a my_icons -o my.tft
python3 build_firmware.py --list                # dry run, writes nothing
```

Only the assets present in the input directory are touched; every other
resource is left byte-for-byte alone, as are the resource table, the section
layout, the file length and the obfuscated header 2. All four CRCs are
recomputed afterwards and verified before the tool reports success.

Assets are matched to resources by the id in the file name - `id0000_240x320.png`,
`id0000.png` and `0.png` all mean resource 0. When the name carries dimensions
they are checked against the resource table. Files whose name contains no id
are reported and skipped rather than guessed at.

Input and output directories are kept distinct on purpose: the extractor writes
to `extracted_all/`, while builds read from `assets/`, and `build_firmware.py`
refuses to read straight from the extractor's output (`--force` overrides).
Copy in only the images you actually intend to change.

A replacement must fit the space the original image already occupies; `--list`
shows each asset against its budget. The tool aborts without writing if
anything does not fit, unless `--skip-oversized` is given.

Verified end to end: patching 3 of the 2058 assets produced a valid firmware of
identical length where all four CRCs check out, re-extraction showed exactly
those 3 images changed and the other 2055 byte-identical, and outside the
resource payloads only 12 bytes moved - the three CRCs.

## Firmware Modification (no encryption - four CRCs)

The image data is **not encrypted**; it is stored in the clear, which is why it
decodes directly. What guards the file is a set of CRC values plus an
obfuscated second header.

### The CRC primitive
Nextion/TJC "byte based" CRC-32, poly `0x04C11DB7`, MSB-first, no reflection.
Each input byte is fed to the shift register as a full 32-bit word (24 zero
bits then the 8 data bits), the first word is XORed with `0xFFFFFFFF`, and 32
zero bits are appended. See `tjc_checksums.py`.

Note `0x15-0x16` reads `64 00` here, which is neither of the two values
documented for Nextion (`00 00` byte based, `03 00` word based) - but the byte
based variant is what actually verifies on this file.

### The four values

| Stored at | Covers | Broken by an image edit? |
|-----------|--------|--------------------------|
| `0x0044-0x0047` | `fw[0x10000:0x710000]` (bootloader + resources) | **yes** |
| `0x00c4-0x00c7` | `fw[0x00:0xc4]` (header 1) | yes, because it covers `0x44` |
| `0x018c-0x018f` | `fw[0xc8:0x18c]` (header 2) | no |
| last 4 bytes | `fw[:-4]` (whole file) | **yes** |

The whole-file CRC is stored little-endian with its **low byte XORed** by
`fw[0x03] ^ fw[0x2e] ^ fw[0x3c]`.

### Header 2 is obfuscated - and can be avoided
Header 2 (`0xc8-0x18b`, entropy ~6.7) holds section offsets and sizes and is
obfuscated with a position-dependent stream. It is *not* a repeating XOR key:
the three fields documented as zero on Nextion Basic/Enhanced read back as
three different values here.

It never has to be touched, as long as an edit is layout preserving: rewrite a
resource **in place**, leave its table entry (offset and allocated size) alone,
and keep the file length unchanged. `patch_image.py` works this way - patching
the 240x320 boot screen changed only the resource payload plus **12 bytes**
(the three CRCs); header 2, the resource table and the file length were all
untouched.

### Size budget
The replacement must fit the resource's originally allocated `size`. All 1994
stock images re-encode within their own allocation, but an arbitrary
replacement need not: worst case (all literal blocks) costs 2.5 bytes/pixel
versus 2.0 for raw. A busy photograph in the 240x320 slot would not fit, while
flat UI artwork compresses easily.

```bash
# check a file's integrity
python3 tjc_checksums.py tjc.tft

# replace an image and re-seal
python3 patch_image.py -f tjc.tft -i 0 --image new.png -o tjc_patched.tft
python3 patch_image.py -f tjc_patched.tft --verify-only
```

### Encoder fidelity
`tjc_compress.py` is a faithful reimplementation of TJC's encoder. Re-encoding
all 1994 compressed resources reproduces the original **output length and every
control byte** at 100%. Two conventions were recovered from the firmware:

- Run counts are 1..15, but the **first slot of a block is capped at 14**, which
  is how the encoder guarantees it never accidentally emits the literal
  signature `1F 11 11 11`. (No block in the firmware has a first count of 15.)
- A block of 8 single pixels is always written as a literal block; the plain
  form `11 11 11 11` never occurs.

Only the filler bytes in unused (count 0) pixel slots differ from the stock
file, and the decoder never reads those.

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

# TJC_display - TJC TFT firmware asset extractor and builder

Extract and replace the bitmap assets in TJC TFT firmware for the Creality
Ender-3 V3 SE LCD. The panel is a **TJC3224T132_011N_P04**; the closest part
publicly on sale is the TJC3224T132_011N_I_A01. TJC is a Chinese clone of
Nextion, and the file format is shared with it.

**Status: the image format and the firmware integrity checks are fully
solved.** All 2058 real assets extract cleanly, and a modified firmware can be
rebuilt and re-sealed so that every checksum verifies.

Not yet done: font parsing, and **nothing here has been flashed to hardware.**

## Key files

| File | Purpose |
|------|---------|
| `tjc_decompress.py` | Decoder for the image format |
| `tjc_compress.py` | Encoder (faithful reimplementation of TJC's own) |
| `tjc_checksums.py` | The four firmware CRCs: verify and re-seal. Also a CLI |
| `extract_all.py` | Extract assets from a `.tft` or a `Resources.bin` dump |
| `build_firmware.py` | Build a customised `.tft` from a directory of assets |
| `tjc_bootloader.py` | Dump firmware sections/partitions (this produced `Resources.bin`) |
| `assets/` | Input directory for builds, kept separate from `extracted_all/` |
| `extracted_all/` | Extraction output (2058 assets) |
| `tjc.tft` | Stock firmware, 7.48 MB |
| `Resources.bin` | The Resources partition, dumped from `tjc.tft`; used by the tests |
| `test.tft` | A second, smaller TFT sample kept for reference (see note below) |
| `TFT.md` | Format notes, forked from UNUF/nxt-doc |
| `expected_icons.txt` | Marlin's icon-name/id `#define` list, useful for naming work |
| `001-reference.jpg` | External ground-truth art that confirmed the decode visually |

Tests: `test_tjc_decompress.py`, `test_tjc_roundtrip.py`, `test_build_firmware.py`.

> **Note on `test.tft`**: it is kept as a reference sample, but the current
> tools do not parse it - walking its partition table yields 0 valid resource
> entries, so it is laid out differently (probably an older editor version).
> Making the tools generalise to it is open work.

## Quick start

```bash
# extract everything
python3 extract_all.py -f tjc.tft -o extracted_all

# list the resource table, or pull a single id
python3 extract_all.py -f tjc.tft --list
python3 extract_all.py -f tjc.tft --only 2 -o one

# edit some images, then build a new firmware
cp extracted_all/id0000_240x320.png assets/
python3 build_firmware.py                 # assets/ -> tjc_custom.tft

# check any firmware's integrity
python3 tjc_checksums.py tjc_custom.tft

python3 -m pytest -q
```

## Image format

### Resource header (20 bytes, per resource)
- **Byte 0**: compression flag - `0x00` RAW, `0x04` COMPRESSED
- **Bytes 4-7**: uint32 LE, the total *used* length of header + payload. The
  resource table's `size` may be larger; the excess is padding, and decoding it
  corrupts the tail of the image.
- Bytes 1-3, 8-19: zero in the stock firmware

RAW payload is `width*height` little-endian RGB565 pixels.

### Block structure (20 bytes per block)
```
Bytes 0-3:   Control (4 bytes)
Bytes 4-19:  8 RGB565 pixels, little-endian
```

**Literal block** - control is exactly `1F 11 11 11`: emit all 8 pixels once
each. Missing this rule is what caused every previously reported "misalignment
artifact": read as run counts, that control field yields 22 pixels instead of 8,
so each literal block over-ran by exactly 14 pixels and shifted everything after
it. That is why the damage grew with image size and left small icons looking
almost right.

**RLE block** - split each control byte into nibbles, **low nibble first**,
giving 8 repeat counts paired with the 8 pixels. A count of 0 emits nothing.

```
counts = [b0&0xF, b0>>4, b1&0xF, b1>>4, b2&0xF, b2>>4, b3&0xF, b3>>4]
output = p0*n0, p1*n1, ... p7*n7
```

Output is row-major.

### Encoder conventions
Recovered from the stock firmware and reproduced by `tjc_compress.py`:

- The image is encoded in **stripes of 4 output rows**; each stripe is padded to
  a whole number of blocks and runs never cross a stripe boundary. A decoder
  does not need this, but it is a strong validation invariant.
- Run counts are 1..15, **except the first slot of a block, capped at 14**. That
  is how the encoder guarantees it can never emit `1F 11 11 11` by accident. No
  block in the firmware has a first count of 15.
- 8 single pixels are always written as a literal block; `11 11 11 11` never
  occurs in the stock file.

### Verification
Three independent invariants hold at **100%** over all 1994 compressed
resources: exact pixel count, exact 4-row stripe alignment, and consumed bytes
equal to the header length field. Re-encoding reproduces the original **output
length and every control byte** at 100% - only the filler in unused (count 0)
pixel slots differs, and the decoder never reads it.

## Placeholder slots

570 of the 2628 table entries are not artwork: they are unassigned picture
slots, emitted as a 4x2 solid-white RAW dummy (size 36, `extra=0`), scattered
through the id range. `extract_all.py` skips them by default
(`--include-placeholders` keeps them), leaving **2058 real assets**: 64 RAW and
all 1994 compressed.

The split is unambiguous - a colour census gives 570 entries with exactly 1
colour, 1 with 2 (`id=179`, a real 18x18 indicator), and 2057 with 6 or more.
Note every placeholder is RAW, which is why genuine RAW images number only 64.

## Firmware layout

- **Partition table: `0x010000`** - 12 entries x 12 bytes, each
  `rel_offset(4) | size(4) | meta(4)`. File offset is `0x010000 + rel_offset`.
  The largest entry is the Resources partition (entry 7, 7.1 MB); entry 8 is
  user code.
- **Resource table: `0x38cf4`** (start of the Resources partition) - 24-byte
  entries, `magic(4) | id(4) | rel_offset(4) | width(2) | height(2) | size(4) | extra(4)`,
  with magic `0x0301600A` or `0x0301640A`. `rel_offset` is relative to the
  partition. 2628 entries in this firmware.

## Firmware integrity: no encryption, four CRCs

The image data is **not encrypted** - it is stored in the clear, which is why it
decodes directly.

### The CRC primitive
Nextion/TJC "byte based" CRC-32, poly `0x04C11DB7`, MSB-first, no reflection.
Each input byte is fed to the register as a full 32-bit word (24 zero bits then
the 8 data bits), the first word is XORed with `0xFFFFFFFF`, and 32 zero bits
are appended. See `tjc_checksums.py`.

Header field `0x15-0x16` reads `64 00` here, which is neither value documented
for Nextion (`00 00` byte based, `03 00` word based) - but the byte based
variant is what actually verifies.

### The four values

| Stored at | Covers | Broken by an image edit? |
|-----------|--------|--------------------------|
| `0x0044-0x0047` | `fw[0x10000:0x710000]` (bootloader + resources) | **yes** |
| `0x00c4-0x00c7` | `fw[0x00:0xc4]` (header 1) | yes, it covers `0x44` |
| `0x018c-0x018f` | `fw[0xc8:0x18c]` (header 2) | no |
| last 4 bytes | `fw[:-4]` (whole file) | **yes** |

The whole-file CRC is stored little-endian with its **low byte XORed** by
`fw[0x03] ^ fw[0x2e] ^ fw[0x3c]`.

Header 1 also stores the total file length at `0x3c-0x3f`, so changing the file
size means updating that too.

### Header 2 is obfuscated - and avoidable
Header 2 (`0xc8-0x18b`, entropy ~6.7) holds section offsets and sizes and is
obfuscated with a position-dependent stream. It is **not** a repeating XOR key:
the three fields documented as zero on Nextion Basic/Enhanced read back as three
*different* values here, so that documented shortcut does not apply.

It never has to be touched. Rewriting a resource **in place**, leaving its table
entry alone and keeping the file length unchanged, leaves header 2
byte-identical. The build tool works this way.

## Building a customised firmware

```bash
python3 build_firmware.py                       # assets/ -> tjc_custom.tft
python3 build_firmware.py -a my_icons -o my.tft
python3 build_firmware.py --list                # dry run, writes nothing
```

Only the assets present in the input directory are updated; missing ones are
simply not touched. Everything else stays byte-for-byte identical, as do the
resource table, the layout, the file length and header 2. All four CRCs are
recomputed and re-verified before success is reported.

Assets are matched by the id in the file name - `id0000_240x320.png`,
`id0000.png` and `0.png` all mean resource 0 - and dimensions in the name are
checked against the table. Files with no id are reported and skipped, never
guessed at.

Build inputs and extraction outputs are kept apart on purpose: extraction writes
`extracted_all/`, builds read `assets/`, and the tool refuses to read straight
from the extractor's output (`--force` overrides). It also refuses to overwrite
the input firmware.

**Size budget**: a replacement must fit the space the original occupies. Worst
case encoding costs 2.5 bytes/pixel against 2.0 for RAW, so a busy photograph
may not fit where flat UI artwork will. `--list` shows each asset against its
budget; the build aborts without writing if anything is too big, unless
`--skip-oversized` is given. RAW is tried as a fallback when compressed misses.

Verified end to end: patching 3 of the 2058 assets produced a valid firmware of
identical length with all four CRCs passing; re-extraction showed exactly those
3 images changed and the other 2055 byte-identical, and outside the resource
payloads only **12 bytes** moved - the three CRCs.

## Remaining work

- **Nothing has been flashed to a real display.** Before flashing, confirm the
  bootloader does not apply a further check we have not seen.
- Fonts (the section after the pictures) are unparsed; they appear to be a
  straight copy of the corresponding `.zi` files.
- `test.tft` is not parsed by the current tools (0 valid resource entries).
- Resource id to icon-name mapping needs redoing against the corrected
  extraction. The old `icons.csv` / `matches.txt` / `full_mapping.txt` were
  produced by the buggy decoder and have been removed; `expected_icons.txt`
  still holds the name/id `#define` list.
- Header 2's obfuscation stream is not broken, so changes to the file *layout*
  (as opposed to in-place edits) are not yet possible.
- The user code partition (entry 8) is only partly understood.

## Dependencies

Python 3 and Pillow.

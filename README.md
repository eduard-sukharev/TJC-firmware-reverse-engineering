# TJC/Nextion display firmware reverse engineering

Reverse engineering of the TJC TFT firmware for the Creality Ender-3 V3 SE
printer's LCD, with working tools to **extract every graphical asset** and to
**rebuild a customised firmware** that still passes all of its integrity checks.

The panel is a **TJC3224T132_011N_P04**; the closest part publicly on sale is
the **TJC3224T132_011N_I_A01**. TJC is a Chinese clone of Nextion and the file
format is shared with it.

## Status

| | |
|---|---|
| Image compression | **solved**, verified on all 1994 compressed resources |
| Asset extraction | **2058 assets**, zero failures |
| Encoder | **solved** - reproduces TJC's own output length and control bytes exactly |
| Firmware integrity | **solved** - four CRCs, all reproducible |
| Rebuilding a firmware | **working** - in-place, layout preserving, re-sealed |
| Fonts | not parsed |
| Flashed to hardware | **no - completely untested on a real display** |

> The image data is **not encrypted**. What guards the file is a set of CRCs,
> plus one obfuscated header that a layout-preserving edit never has to touch.

## Quick start

```bash
# extract every asset
python3 extract_all.py -f tjc.tft -o extracted_all

# list the resource table, or pull one id
python3 extract_all.py -f tjc.tft --list
python3 extract_all.py -f tjc.tft --only 2 -o one

# change some images and rebuild
cp extracted_all/id0000_240x320.png assets/     # edit it, then:
python3 build_firmware.py                       # assets/ -> tjc_custom.tft

# verify any firmware
python3 tjc_checksums.py tjc_custom.tft
```

Requires Python 3 and Pillow.

## The compression format

Each resource has a 20-byte header (byte 0 is the compression flag, `0x00` RAW
or `0x04` compressed) followed by a stream of 20-byte blocks: 4 control bytes
then 8 little-endian RGB565 pixels.

**The key that unlocked it**: a block whose control field is exactly
`1F 11 11 11` is a **literal block** - emit all 8 pixels once each. Read naively
as run counts it yields 22 pixels instead of 8, so every literal block over-ran
by exactly 14 pixels and shifted the rest of the image. That is why the
long-standing "misalignment artifacts" got worse the larger the image was, and
why small icons looked almost correct.

Otherwise a block is run-length coded: split each control byte into nibbles,
**low nibble first**, giving 8 repeat counts paired with the 8 pixels; a count
of 0 emits nothing.

```
counts = [b0&0xF, b0>>4, b1&0xF, b1>>4, b2&0xF, b2>>4, b3&0xF, b3>>4]
output = p0*n0, p1*n1, ... p7*n7
```

The second thing that mattered: header bytes 4-7 hold the *used* byte length.
The resource table's `size` is often larger, and decoding that trailing padding
corrupted the tail of every image.

### How it was found

The breakthrough was noticing that background regions decoded to exactly
**408 pixels per 4 blocks** = 4 rows x 102, with the 4th block carrying exactly
4 zero-padded slots. That revealed the encoder aligns every group of 4 output
rows to a block boundary, which turned into a per-stripe error detector.
Combined with the header length field (which pins down the exact block count),
the residual error became measurable per image - and it was always an exact
multiple of 14. Regressing that residual against control-byte frequencies
pointed at `0x1F` in position 0 with correlation 1.0000 and an exact match in
600 of 600 images.

### Verification

Three independent invariants hold at **100%** across all 1994 compressed
resources: exact pixel count, exact 4-row stripe alignment, and consumed bytes
equal to the header's length field. Re-encoding reproduces the original output
length and **every control byte**. Run `python3 -m pytest -q`.

## Firmware integrity

All four values use the Nextion/TJC "byte based" CRC-32 (poly `0x04C11DB7`,
MSB-first, no reflection; each byte fed as a full 32-bit word, first word XORed
with `0xFFFFFFFF`, 32 zero bits appended).

| Stored at | Covers | Broken by an image edit? |
|-----------|--------|--------------------------|
| `0x0044-0x0047` | `fw[0x10000:0x710000]` bootloader + resources | **yes** |
| `0x00c4-0x00c7` | `fw[0x00:0xc4]` header 1 | yes, it covers `0x44` |
| `0x018c-0x018f` | `fw[0xc8:0x18c]` header 2 | no |
| last 4 bytes | `fw[:-4]` whole file | **yes** |

The whole-file CRC is stored little-endian with its **low byte XORed** by
`fw[0x03] ^ fw[0x2e] ^ fw[0x3c]`.

Header 2 (`0xc8-0x18b`) is obfuscated with a position-dependent stream - not a
repeating XOR key, contrary to what the Nextion notes suggest. It stores section
offsets and sizes, and is sidestepped entirely by editing resources in place and
keeping the file length unchanged.

## Rebuilding a firmware

`build_firmware.py` reads a directory of replacement images and writes a **new**
firmware; the original is only ever read. Only the assets present in that
directory are updated - everything else, including the resource table, the
layout, the file length and header 2, stays byte-for-byte identical.

Assets are matched by the id in the file name (`id0000_240x320.png`,
`id0000.png` and `0.png` all mean resource 0). Files without an id are reported
and skipped rather than guessed at. A replacement must fit the space the
original occupies; `--list` shows each asset against its budget.

Verified end to end: patching 3 of 2058 assets produced a valid firmware of
identical length with all four CRCs passing, re-extraction showed exactly those
3 images changed and the other 2055 byte-identical, and outside the resource
payloads only **12 bytes** moved - the three CRCs.

## Placeholder slots

570 of the 2628 resource entries are not artwork but unassigned picture slots -
a 4x2 solid-white RAW dummy each. They are skipped by default
(`--include-placeholders` keeps them), leaving 2058 real assets. Every
placeholder is RAW, which is why genuine RAW images number only 64 against 1994
compressed.

## Tools

| File | Purpose |
|------|---------|
| `tjc_decompress.py` | Decoder |
| `tjc_compress.py` | Encoder |
| `tjc_checksums.py` | The four CRCs: verify and re-seal (also a CLI) |
| `extract_all.py` | Extract assets, list the resource table |
| `build_firmware.py` | Build a customised firmware from `assets/` |
| `tjc_bootloader.py` | Dump firmware sections/partitions |

`test.tft` is kept as a second sample for future work, but the current tools do
not parse it - its partition table yields no valid resource entries, so it is
laid out differently (probably an older editor version).

## Sources

- **[nxt-doc](https://github.com/UNUF/nxt-doc)** - documentation of the
  Nextion/TJC TFT structure; `TFT.md` here is a fork of their work.
- **[TFTTool](https://github.com/UNUF/TFTTool)** - its `NextionChecksum.py`
  provided the CRC primitive that all four firmware checksums turned out to use.
- **[TJC3224 reverse engineering](https://jpcurti.github.io/E3V3SE_display_klipper/tjc3224_reverse_engineering.html)** -
  display protocol and bootloader header analysis.
- **[Ender-3V3-SE](https://github.com/navaismo/Ender-3V3-SE)** - the community
  firmware fork that prompted this work.

## AI-assisted research

Earlier stages of this project were explored with OpenCode Zen's free models
(MiniMax M2.5, Nemotron 3 Super, BigPickle). The compression format, the
encoder and the firmware checksums were solved with Claude.

## Caveat

None of this has been flashed to a real display. Before flashing, confirm the
bootloader applies no further check beyond the four CRCs documented here.

## License

For educational and research purposes. All firmware files belong to their
respective owners.

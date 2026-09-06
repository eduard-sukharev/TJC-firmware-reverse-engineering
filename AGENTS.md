# TJC_display - TJC TFT firmware asset extractor and builder

Extract and replace the bitmap assets in TJC TFT firmware for the Creality
Ender-3 V3 SE LCD. The panel is a **TJC3224T132_011N_P04**; the closest part
publicly on sale is the TJC3224T132_011N_I_A01. TJC is a Chinese clone of
Nextion, and the file format is shared with it.

**Status: the image format and the firmware integrity checks are fully
solved.** All 2058 real assets extract cleanly, and a modified firmware can be
rebuilt and re-sealed so that every checksum verifies. **Serial flashing is
also working and has been verified on real hardware** - both the stock
firmware and a custom rebuild have been flashed successfully via
`tjc_serial_upload.py`.

Not yet done: font parsing.

## Key files

| File | Purpose |
|------|---------|
| `tjc_decompress.py` | Decoder for the image format |
| `tjc_compress.py` | Encoder (faithful reimplementation of TJC's own) |
| `tjc_checksums.py` | The four firmware CRCs: verify and re-seal. Also a CLI |
| `extract_all.py` | Extract assets from a `.tft` or a `Resources.bin` dump |
| `build_firmware.py` | Build a customised `.tft` from a directory of assets |
| `tjc_bootloader.py` | Dump firmware sections/partitions (this produced `Resources.bin`) |
| `tjc_serial_upload.py` | Flash a `.tft` to the display over serial (Nextion upload protocol v1.2) |
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

## Flashing over serial

`tjc_serial_upload.py` implements the Nextion/TJC HMI upload protocol v1.2
(the "skip-ahead" variant TJC's own editor uses), following the reference
implementations at https://github.com/UNUF/Nexus (Python, v1.2) and
https://github.com/hagronnestad/nextion-tft-uploader (C#, v1.0), as linked
from `nxt-doc/Protocols/Upload Protocol v1.2.md`.

```bash
python3 tjc_serial_upload.py tjc_custom.tft                    # /dev/ttyUSB0, 115200
python3 tjc_serial_upload.py tjc_custom.tft -u 921600           # faster data phase
python3 tjc_serial_upload.py tjc_custom.tft -p /dev/ttyUSB1 -c 9600
```

**Handshake**: send a junk prefix + `connect` (twice - the first is routinely
swallowed), each terminated by `FF FF FF`. The device replies
`comok 0,<addr>-0,<model>,<fw>,<mcu>,<serial>,<flash_size>`. This is a plain
text protocol - a raw binary DWIN handshake (`AA 00` + tail) also gets an
`OK_V1.5` reply, but that path does **not** understand `whmi-wri*` commands
and just echoes error frames (`24 FF FF FF ...`) back at any data sent to it;
use the text protocol.

**Upload**: burn one throwaway command (`bs=42`) since the first command
after `connect` is always lost, then send
`whmi-wris <file_size>,<upload_baud>,1` (the file size is read from the TFT
header at `0x3c`, not the OS file size - they should match). Close and reopen
the port at `upload_baud`, then send the file in 4 KB blocks. The device acks
each block with `05`; on the *first* block only it may instead send
`08` + a little-endian uint32 offset, meaning "skip ahead to this file
offset" (used when the resources partition already matches, e.g. re-flashing
the same firmware - only the trailing user-code section then gets sent).

**Verified on real hardware** against a TJC3224T132_011N: both the stock
`tjc.tft` and a custom rebuild (via `build_firmware.py`) flashed successfully
end to end.

## The DWIN-like serial protocol lives in the panel's kernel, not in the .tft

The panel answers two mutually exclusive serial protocols: the Nextion/TJC text
protocol (used by `tjc_serial_upload.py`) and a DWIN-style binary one
(`AA <instr> <data> CC 33 C3 3C`, see `tjc_dwin.py`). **Neither parser is in
`tjc.tft`.** Verified four ways:

- The frame tail `CC 33 C3 3C` does not occur in the file at all - in any byte
  order, nor even the substrings `33 C3 3C` / `C3 3C`.
- The handshake reply string is absent. The panel really answers
  `AA 00 "OK_V1.5" 00 00 50 00 01 CC 33 C3 3C`, but `OK_V1.5`, `OK_V`, `V1.5`,
  `DWIN`, `T5UIC`, `TJC` and `Nextion` appear nowhere in the file.
- No frame parser exists. Scanning the whole file for Thumb `CMP Rn,#imm8` /
  `MOVS Rn,#imm8` against the tail bytes finds only two 200-byte windows
  containing three of the four, neither containing `0xC3`, and one of them is
  inside the picture data. A real parser must compare all four close together.
- The two high-entropy components are not a compressed kernel: zlib, raw
  deflate, gzip, lzma and bz2 all fail at 65 offsets each.

What the file contains:

| Entry | Size | Entropy | Content |
|-------|------|---------|---------|
| 0 | 17.5 KB | 7.09 | index table + data blob (`input.bin`). 8-byte records; each record's length field equals the delta to the next record's offset |
| 1 | 120 KB | 7.11 | data table / LUT (halfwords `0x2808`/`0x2909` dominate, long runs of `09`) |
| 2 | 13 KB | 5.34 | **LCD controller driver table** - ARM Thumb code, see below |
| 3 | 1.8 KB | 7.84 | unidentified, no code |
| 4 | 1.5 KB | 5.40 | `syscom.bin` message strings ("Lcd Driver Update OK!"), see below |
| 5, 6 | 3.3 / 9.3 KB | 6.5-6.9 | **ARM Cortex-M plugin blobs**, see below |
| 7 | 7.1 MB | - | resources |
| 8 | 54 KB | 6.64 | Nextion-VM user bytecode |

### The file DOES contain executable ARM code

An earlier pass called parts 2, 5 and 6 data. **That was wrong.** The mistake
was disassembling only from offset 0 (a linear sweep dies on the first header
byte) and reading entropy as proof of packing - Thumb code with literal pools
sits at ~6.5-7.1 entropy quite naturally. Scanning for `push {...,lr}` sites
and walking each forward to a matching `pop {...,pc}` separates them cleanly:

| Part | `push{lr}` sites | reaching a valid `pop{pc}` | |
|---|---|---|---|
| 5 | 16 | 15 (94%) | code |
| 6 | 17 | 17 (100%) | code |
| 2 | 38 | 28 (74%) | code |
| 1 | 469 | 88 (19%) | data (periodic, stride 0x1c; disassembles as nonsense) |
| 0 | 82 | 4 (5%) | data |
| 8 | 42 | 2 (5%) | data |
| 7 (images, control) | 31 | 2 (6%) | data - this is the noise floor |

Architecture is ARM Thumb / Thumb-2 (Cortex-M). Sixteen other capstone
architectures were tried; raw decode coverage does not discriminate (image data
decodes at 99.8% too), but the mnemonic *distribution* does - data gives a
degenerate `movs`/`lsls` pile, parts 5/6 give a flat, realistic
`ldr`/`movs`/`adds`/`str`/`blx` spread.

### Part 2: the LCD controller driver table

```
header(14) | N x [ id(2) | offset(2) | size(2) ] | driver blobs | 1bpp font
```

The table starts at `0x0e` and chains exactly: the first entry's offset equals
the end of the table itself, and each `offset + size` is the next offset. 13
entries, IDs are the controller part numbers:

| id | chip | id | chip |
|---|---|---|---|
| `0x3030` `0x3041` `0x3042` `0x3043` | generic "00"/"A0"/"B0"/"C0" | `0x7795` | ST7795 |
| `0x7735` | ST7735 | `0x7796` | ST7796 |
| `0x7787` | ST7787 | `0x7799` | ST7799 |
| `0x7789` | ST7789 | `0x9307` `0x9308` | ILI93xx |
| | | `0x9A01` | unidentified |

Each blob is Thumb code against a tiny two-slot vtable - `[r4+0]` =
write_command, `[r4+4]` = write_data_byte. The set-window routine is
unmistakable:

```
movs r0,#0x2a ; blx [r4]      ; CASET
put hi/lo of [r4+0x0c], [r4+0x10]   ; x0, x1, big-endian
movs r0,#0x2b ; blx [r4]      ; RASET
put hi/lo of [r4+0x0e], [r4+0x12]   ; y0, y1
movs r0,#0x2c ; blx [r4]      ; RAMWR
```

Coverage ends at `0x20ce`; the remaining 4.7 KB is 1-bit-per-pixel glyph data -
the built-in font for the system messages, needed before resources are loaded.

### Parts 5 and 6: loadable plugins with a kernel API vtable

The container chains exactly, byte for byte, and recurses one level:

```
outer:  magic(4) | count(4) | count x [ id(4)  | offset(4) | size(4) ] | chunks
inner:  magic(4) | count(4) | count x [ offset(4) | size(4) | crc(4)  ] | leaves
```

Note the field order differs between the two levels. Outer IDs are
`0x000EF030 / 0x000EF031 / 0x000EF103` (part 5) and `0x0001F130 / 0x0001F140`
(part 6); each appears exactly once in the whole file, so nothing else
references them - the kernel must locate these by partition index.

**The inner `crc` field is the project's own Nextion/TJC byte-based CRC-32**
(`tjc_checksums.crc`) over the chunk - verified on 25 of 25 chunks. So a
modified blob can be re-sealed with the existing tooling.

Every leaf starts with a real Thumb prologue (`f0b5` `f3b5` `f7b5` `feb5`
`70b5`, or Thumb-2 `2de9f34f` / `2de9f041`). Part 5's `0xEF030` and `0xEF031`
are byte-identical; `0xEF103` is the same code rebuilt as Thumb-2 - i.e. per-core
target variants.

The blobs are position-independent and call back into the kernel through a
vtable handed to them in a context struct (`ldr r4,[r1]` then
`ldr rX,[r4,#imm]` / `blx rX`). Slots observed across the 25 leaves are dense
and contiguous from `+0x00` to `+0x58` - **23 kernel entry points**. Two are
pinned down:

- `[r4+0x08](code)` = show system message. Codes `0x16/0x17/0x19/0x1b` index
  part 4's string table, and the match is exact: a flash-verify routine calls
  `0x17` on checksum failure ("Update Failed:check Error!") and `0x19` on
  success ("Update Successed!").
- `[r4+0x04](x, y, value, digits)` = draw a number. Called in a 2x4 grid of
  coordinates `(0x40|0x90, 0xa0|0xb4|0xc8|0xdc)`. Inferred from the call
  pattern, not proven.

Identified leaf contents: a **QR code generator** in part 6 - conclusive, it
buckets `strlen` against 17/32/49/78/106/134/154/192 to pick version 1-8, loads
26 (v1 codeword count) and computes the module size as `version*4+17` - and in
part 5 a **flash verify/update** routine that CRCs external flash in 0x7D000
chunks and prints a 3-digit percentage. What the two parts are *collectively*
is still open.

Part 4 is their string table: `header(8) | 34 x uint16 offset | strings`, first
offset `0x4c` = end of the table. Each string has a ~10-byte binary prefix
(attributes/coordinates, undecoded).

**What this does and does not change**: the DWIN protocol parser is still not
here. None of this code parses `AA ... CC 33 C3 3C`; the frame tail and the
`OK_V1.5` reply string still appear nowhere in the file, and the blobs are
drawing/QR/flash helpers that call *into* the kernel rather than implementing
it. So the resident-kernel conclusion stands. But the claim that the `.tft`
carries no code at all was wrong, and the previous entropy-based reasoning
should not be reused: parts 0 and 1 are data by the prologue test (5% and a
periodic-data 19% against a 6% noise floor), which is far better evidence than
the failed-decompression argument was.

**Opportunity, tried twice, looks structurally protected**: since the kernel loads code blobs
out of the `.tft` and the chunk CRC is a checksum this repo already computes,
replacing a blob (e.g. the QR generator) with custom Thumb code looked like a
plausible route to native code execution on the panel - and therefore to a
real bitmap blit. A minimal test of this was run on real hardware:

- Identified, in all 5 physical copies (part 5 x3 ISA variants, part 6 x2),
  the exact `movs r0,#0x19 ; blx r1` call that shows the "Update Successed!"
  message (`r1` loaded a few instructions earlier from `[r4+8]`) after a
  successful `.tft` flash - a code path proven to run on every real upload
  this repo has done (see "Flashing over serial" above).
- Patched only the immediate operand, `0x19 -> 0x1d` ("Touch Screen Adjust
  OK!"), in all 5 copies. Zero size change, so no file-layout risk; recomputed
  each patched leaf's own inner CRC and resealed all four firmware-level CRCs
  (`tjc_checksums.reseal`) - `tjc_codeblobs.py --list` confirmed 25/25 leaf
  CRCs still verified, `tjc_checksums.py` confirmed all four firmware CRCs.
- Flashed to the real TJC3224T132_011N panel with `tjc_serial_upload.py`.
  Upload completed cleanly (100%, exit 0, matching kernel v37/MCU 61760). The
  panel then **hung**: solid white screen, no text, and it stopped answering
  *both* serial protocols (Nextion `connect` and DWIN handshake both got zero
  bytes back) - unlike the earlier DWIN-flood incident, this survived the
  tool's announced restart, which points at this check running again (and
  hanging again) very early on normal boot, not just right after upload.
- **Recovered with a plain power cycle** - the serial upload receiver came
  right back (`comok ...,37,61760,...` on the very next `connect`), confirming
  the recovery model held: the upload receiver lives in a part of the resident
  kernel independent of whatever this check does, so it stays reachable even
  when this code path is broken. Re-flashing the untouched stock `tjc.tft`
  (now do this at `-u 921600`, seconds instead of ~11 minutes at 115200)
  brought the panel back to a normal page-0 boot, confirmed visually.

**Follow-up experiment - decisive, and it changes the conclusion.** To tell
apart "our code edit broke real execution" from "something rejects the edit
before it ever runs," a second, more surgical test was run: leave every code
byte untouched and corrupt *only* the inner container CRC field of one leaf
that makes zero kernel vtable calls (the QR version-bucketing helper, a pure
`strlen`-and-thresholds function with no plausible reason to run at boot),
in both of its physical copies. Re-sealed the same way (all four firmware
CRCs recomputed and verified OK; `tjc_codeblobs.py --list` correctly reported
23/25, flagging exactly the two leaves that were deliberately broken).
Flashed it. **Same class of failure**: after a power cycle, the panel showed
`System Data ERROR!` - which is not a generic crash string, it is code `0x05`
in this repo's own decoded `part4` string table (see above), read verbatim
off real hardware. That is independent confirmation the string-table decode
is correct, and, more importantly, direct proof that **something checks these
partitions' integrity at boot and fails closed with a real diagnostic
message, string content produced by this exact firmware, when it doesn't
match.**

**This reframes the first experiment.** Since a content-untouched,
CRC-only-corrupted leaf produces the *same class* of boot failure as the
content-patched leaf did, the simplest explanation covering both is not "the
patched code executed and crashed" - it's that **some integrity check over
partitions 5/6 rejected both edits before any of our changed logic ever ran**.
This matters because the first experiment's leaf CRCs were re-sealed to be
internally self-consistent by our own formula (`tjc_codeblobs.py --list`
reported 25/25 at the time) and it *still* failed - which means our working
model, "the inner container `crc` field is what the kernel checks, using the
same byte-based CRC-32 documented for the firmware-level checksums," is
probably wrong, or at least incomplete. The evidence for that formula was
only ever that it reproduces the *stock, unmodified* values (25/25) - which a
compiler bookkeeping field would also satisfy without the runtime ever
checking it. A brute-force search of the whole file for a CRC-32 (both this
project's byte-based variant and plain zlib) computed over several candidate
ranges (part 5, part 6, part 5+6, the whole bootloader region) found no
matching stored reference anywhere - so if there is a real reference value,
it is not a plain, unobfuscated 4-byte match, or it isn't a checksum-against-
a-stored-value at all (a plausible alternative: the resident kernel itself
holds a compiled-in expected signature for the exact "system library" build
it shipped with, which cannot be discovered or satisfied by editing the
`.tft` - it would need a kernel dump).

**Conclusion: this specific avenue - patching the kernel-loaded blobs in
partitions 2/5/6 - looks structurally protected, not just poorly understood.**
Two independent, differently-shaped edits (content-only; CRC-only) both broke
boot the same way, and the protection could not be reverse-engineered
offline from what's in the `.tft`. That is different from, and a harder
problem than, the earlier vtable-ABI uncertainty. Recommend not spending
further hardware iterations patching these specific partitions without new
information (most plausibly a resident-kernel dump via SWD/JTAG, which would
show what it actually checks). This does not affect the resource/image path
at all - `build_firmware.py`'s in-place edits to partition 7 (images) remain
fully safe and already proven on real hardware, because that content is
apparently validated far more loosely (structurally, by the resource table,
not by an exact hash) - only the small "system library" partitions 2/5/6
exhibit this strict, boot-blocking protection.

**A separate, practical observation from these two recovery cycles**: a full
7.48 MB `.tft` upload at `-u 921600` completed in a few seconds, not the ~11
minutes seen at 115200. That makes "rebuild one image resource with
`build_firmware.py` and reflash the whole firmware" a genuinely fast
operation now - fast enough to matter for staging a new thumbnail before a
print starts, though a full reflash still reboots the whole panel (the tool
prints "the display will restart" and it does), so it is not a substitute for
updating a thumbnail live without disturbing the rest of the running UI. That
remains what the rectangle-based `dwin_blit.py` approach is for.

So the DWIN emulation sits in the panel's **resident kernel, which flashing a
`.tft` does not replace**. The panel reports its own kernel version in the
Nextion handshake reply:

```
comok 0,30599-0,TJC3224T132_011N,37,61760,FCD63401766D1644,8388608
                                 ^^ kernel v37   ^^ MCU     ^^ 8 MB flash
```

Recovering that code means pulling it off the MCU (SWD/JTAG) or finding a TJC
kernel update package; it cannot be extracted from a `.tft`. Black-box opcode
probing over serial is what produced the working-opcode list below, and remains
the cheap option.

The MCU is marked **AiHMI C2 / 2307A / NTPGK** - TJC's own part, so there is no
datasheet, no OpenOCD target config and no published memory map. The board
carries **5 copper test pads**. Note that the 8 MB figure in the `comok` reply
is the external SPI flash (where the `.tft` lands); the kernel is in the MCU's
internal memory, and only that is worth dumping.

### SWD pinout, found and confirmed live

The 5 test pads are a standard SWD debug header. Found by multimeter alone
(no schematic, no datasheet), method fully general and worth reusing on any
similarly undocumented board:

1. **Resistance (Ω) mode, unpowered, all 10 pad-pad pairs plus each pad
   against a known GND point and a known VCC point.** Two pads read exactly
   `0` to GND and to VCC respectively - those are GND and VCC. The other three
   read 10-12 kΩ to *both* rails, consistent with ARM/ESD clamp diodes on a
   real IC pin rather than a passive test point (a genuinely floating pad
   reads open, not 10 kΩ both ways) - this is what told us the remaining 3
   pads are live MCU pins before any power was applied.
2. **Voltage at rest, powered, each of the 3 remaining pads to GND.** Two read
   the VCC rail (`3.23 V`), one reads a flat `0 V`. The `0 V` one is very
   likely **SWCLK** (commonly pulled low at idle so board noise can't forge a
   SWD entry sequence); the two at VCC are ambiguous between **SWDIO**
   (commonly pulled up) and **RESET** (commonly pulled up) from voltage alone.
3. **Disambiguating the last two: momentarily short each to GND while the
   panel is running and watch the screen.** The one that makes the panel
   visibly reboot is **RESET**. The other is **SWDIO**. This step is the only
   one that touches the running board, and it's a standard, low-risk,
   fully-reversible test (worst case is exactly what it's testing for - a
   reboot).

Final mapping, confirmed live end to end:

| Pad | Signal |
|-----|--------|
| 1   | GND |
| 2   | RESET (NRST) |
| 3   | SWCLK |
| 4   | SWDIO |
| 5   | VCC (3.3 V) |

### What a live SWD session reveals

Probe: a Raspberry Pi Pico (RP2040) flashed with `raspberrypi/debugprobe`'s
`debugprobe_on_pico.uf2` (that project is the current name for what used to be
called picoprobe). Its fixed pin map (`include/board_pico_config.h`): SWCLK =
GPIO2, SWDIO = GPIO3, target RESET = GPIO1. Wire GND-GND, those three pins to
pads 3/4/2, and leave the panel's own VCC (pad 5) unconnected to the probe -
the panel stays powered from its own serial adapter, only logic/reset lines
are shared. `lsusb` shows it as `2e8a:000c "Raspberry Pi Debugprobe on Pico
(CMSIS-DAP)"`.

A vendor-agnostic OpenOCD SWD probe - no target config, no flash driver, just
the generic `cortex_m` target type - gets a full core identification and
memory access:

```
openocd -c "adapter driver cmsis-dap" -c "transport select swd" \
        -c "adapter speed 1000" \
        -c "swd newdap dummy cpu -expected-id 0x0bc11477" \
        -c "dap create dummy.dap -chain-position dummy.cpu" \
        -c "target create dummy.cpu cortex_m -dap dummy.dap" \
        -c "init" -c "halt" -c "mdw 0x00000000 16"
```

Result: `SWD DPIDR 0x0bc11477`, then `[dummy.cpu] Cortex-M0+ r0p1 processor
detected` - **the AiHMI C2 core is ARM Cortex-M0+ r0p1**. (`reset halt` timed
out - `SYSRESETREQ` isn't acknowledged the way OpenOCD expects on this chip -
but plain `halt`, a debug-request halt with no reset involved, works fine.
This also confirms why part 5's leaves come in both plain-Thumb and Thumb-2
copies: M0+ is ARMv6-M, Thumb-only, so whichever of TJC's product line uses
this core needs the plain-Thumb build specifically.)

Reading the vector table at `0x00000000` with the core halted:

```
0x00000000: 20001ff0 080018c5 080018d3 080018d5 00000000 08005739 0800fda8 12344321
```

`[0]=0x20001ff0` is the initial SP, placing SRAM at **`0x20000000`**.
`[1]=0x080018c5` is the Reset_Handler (bit 0 set = Thumb), placing flash at
**`0x08000000`** - the same convention STM32 and most Cortex-M vendors use.
`mdw 0x20000000 16` reads back *identical* content to address 0, meaning
address 0 is an alias of SRAM (the boot ROM copies the vector table there),
not of flash.

**Flash read-out protection (RDP) is enabled.** `mdw 0x08000000 16` and a
16 KB `dump_image` from that address both return the single repeating word
`0x20001bac` for the entire range - not real code, a fixed pattern the flash
controller substitutes when the debug port tries to read protected flash.
This is a deliberate, standard anti-cloning feature, not a bug in our
approach, and it is why the resident kernel (confirmed to exist, confirmed to
implement the DWIN protocol, confirmed to load code out of the `.tft`'s
partitions 2/5/6) still can't be dumped even with a fully working, correctly
wired debug port.

**On trying to defeat it: don't reach for a "disable RDP" command.** On
STM32-family chips (and most vendors' equivalent features) lowering the
protection level triggers an automatic mass-erase of the *entire* flash as a
built-in anti-tamper measure - AiHMI C2 has no datasheet to confirm or rule
this out, so the safe assumption is that it behaves the same way, and doing
that would permanently destroy kernel v37, the one thing this whole
investigation has been protecting throughout. No unlock/erase command was
attempted.

**A real, comparatively low-risk lead for later, not yet attempted:** the
DPIDR `0x0bc11477` is also reported by genuine ST STM32G0 parts, i.e. AiHMI C2
likely licenses the same ARM Cortex-M0+ IP. A documented technique for
STM32F0x (lucasteske.dev, "STM32F0x Protected Firmware Dumper") reads
protected flash by racing the SWD read against RDP re-arming after a reset:
RDP on these chips takes a moment to re-engage after `NRST` is released, and
a sufficiently fast raw SWD read can catch one word of real flash content in
that window before it closes, one word per power-cycle. Notably: it never
asks the flash controller to lower protection, so it does not trip the
mass-erase countermeasure above - the risk profile is completely different
from an RDP-downgrade attempt. It's also the same tool we already have (the
author used a Pico) - but it needs custom low-level PIO/bit-bang firmware for
precise microsecond timing (OpenOCD's own reset/halt sequencing is nowhere
near fast enough), a way to power-cycle the panel from a GPIO (not wired
yet), and the exact timing window is chip-specific and completely unknown for
AiHMI C2 - the STM32F0x window doesn't transfer, and the technique may not
work at all if AiHMI C2's flash controller re-arms RDP differently. This is
a real follow-on project, not a quick next step.

### Opcodes: verified working

`0x00` handshake, `0x40` set palette, `0x52` clear screen, `0x59` frame rect,
`0x5B` fill rect, `0x5F` backlight, `0x97` icon show, `0x98` text.

`0x97` draws icons baked into the `.tft` resources and works well - confirmed
visually, including that consecutive icons at the same coordinates overdraw
each other.

### Opcodes: tested and dead

- `0x01`, `0x02`, `0x22` (from the T5UIC1 kernel guide) - do nothing.
- `0xC0` **Write RAM**, `0xC1` write font lib, `0xC2` **Read RAM** (documented
  in the T5L guide as a 32K-word RAM area) - **not implemented**. Writing a
  40x40 RGB565 block to word address 0 changes nothing on screen, and `0xC2`
  returns zero bytes. The panel does not hang, it silently ignores both.
- Using `0x97`'s `lib_id` as a handle to that RAM buffer does not work either:
  sweeping `lib_id` 0-5 always drew the same firmware icon regardless of what
  colour had just been written to RAM, so `lib_id` only ever indexes baked-in
  icon libraries.

**Consequence for dynamic images**: there is no native "upload an arbitrary
RGB565 buffer and blit it" path on this panel. Drawing a G-code thumbnail
really does have to be built out of `0x40`+`0x5B` rectangles, which is what
`dwin_blit.py`'s bucket-sort encoder does - that is not a workaround pending a
better command, it is the only mechanism available.

> Measurement caveat: `Panel.handshake()` returns a latency equal to the
> serial per-call `timeout` when that timeout is large, because `read(64)`
> blocks for the full timeout waiting for 64 bytes the panel never sends. Keep
> `timeout` small (~0.01s) whenever the returned number is used as a timing
> probe.

## Remaining work

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

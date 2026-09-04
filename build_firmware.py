#!/usr/bin/env python3
"""
Build a customised TJC .tft firmware from a directory of replacement assets.

The original firmware is never modified: it is read, patched in memory and
written to a new output file.

Only the assets actually present in the input directory are touched. Every
other resource in the firmware is left byte-for-byte alone, and so are the
resource table, the section layout, the file length and the obfuscated
header 2. Afterwards all four CRCs are recomputed (see tjc_checksums.py).

Asset file naming
-----------------
Files are matched to resources by id, taken from the file name. Both the
extractor's naming and a bare number work::

    id0000_240x320.png      -> resource 0   (dimensions checked against the table)
    id0000.png              -> resource 0
    0.png                   -> resource 0

Any format PIL can read is accepted. Anything that does not parse as an id is
reported and skipped, never guessed at.

Directories
-----------
The input directory defaults to ``assets/`` and is deliberately *not* the
extractor's output directory (``extracted_all/``), so that a build never
silently consumes the files a previous extraction produced. Point ``-a`` at
whatever you like; the two are only refused if they are literally the same
directory.

Usage
-----
    python3 build_firmware.py                                  # assets/ -> tjc_custom.tft
    python3 build_firmware.py -a my_icons -o my_firmware.tft
    python3 build_firmware.py --list                           # dry run, change nothing
"""

import argparse
import re
import struct
import sys
from pathlib import Path

import tjc_checksums
from tjc_compress import build_resource, image_to_rgb565
from tjc_decompress import (
    COMPRESSION_FLAG_RAW,
    RESOURCE_HEADER_SIZE,
    decompress_image_data,
)

DEFAULT_ASSETS_DIR = "assets"
DEFAULT_FIRMWARE = "tjc.tft"
DEFAULT_OUTPUT = "tjc_custom.tft"
EXTRACTOR_OUTPUT_DIR = "extracted_all"  # kept distinct from the build input

PARTITION_TABLE_OFFSET = 0x010000
PARTITION_ENTRY_SIZE = 12
ENTRY_SIZE = 24
MAGICS = (0x0301640A, 0x0301600A)

IMAGE_SUFFIXES = {".png", ".bmp", ".gif", ".jpg", ".jpeg", ".tif", ".tiff", ".webp"}
NAME_RE = re.compile(r"^(?:id)?(\d+)(?:_(\d+)x(\d+))?$", re.IGNORECASE)


def resources_base(fw):
    """File offset and size of the Resources partition (the largest one)."""
    best = None
    for i in range(12):
        o = PARTITION_TABLE_OFFSET + i * PARTITION_ENTRY_SIZE
        rel, size, _meta = struct.unpack("<III", fw[o : o + PARTITION_ENTRY_SIZE])
        if best is None or size > best[1]:
            best = (rel, size)
    return PARTITION_TABLE_OFFSET + best[0], best[1]


def resource_index(fw):
    """Map resource id -> (file_offset, width, height, allocated_size)."""
    base, size = resources_base(fw)
    part = fw[base : base + size]
    index = {}
    for i in range(len(part) // ENTRY_SIZE):
        o = i * ENTRY_SIZE
        magic, rid, rel, wh, alloc, _extra = struct.unpack("<IIIIII", part[o : o + 24])
        if magic not in MAGICS:
            continue
        w, h = wh & 0xFFFF, (wh >> 16) & 0xFFFF
        if w == 0 or h == 0 or alloc == 0 or rel + alloc > size:
            continue
        index.setdefault(rid, (base + rel, w, h, alloc))
    return index


def scan_assets(directory):
    """
    Collect {resource_id: path} from a directory.

    Returns (assets, ignored, duplicates).
    """
    assets, ignored, duplicates = {}, [], []
    for path in sorted(directory.iterdir()):
        if path.is_dir():
            ignored.append((path, "is a directory"))
            continue
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            ignored.append((path, "not a recognised image extension"))
            continue
        m = NAME_RE.match(path.stem)
        if not m:
            ignored.append((path, "file name does not contain a resource id"))
            continue
        rid = int(m.group(1))
        dims = (int(m.group(2)), int(m.group(3))) if m.group(2) else None
        if rid in assets:
            duplicates.append((rid, assets[rid][0], path))
            continue
        assets[rid] = (path, dims)
    return assets, ignored, duplicates


def encode_for_slot(pixels, w, h, alloc):
    """
    Encode pixels to fit the resource's existing allocation.

    Tries the compressed format first, then falls back to RAW, which can win
    for very noisy images. Returns the blob, or None if neither fits.
    """
    blob = build_resource(pixels, w, h)
    if len(blob) <= alloc:
        return blob, "compressed"

    header = bytearray(RESOURCE_HEADER_SIZE)
    header[0] = COMPRESSION_FLAG_RAW
    raw = bytes(header) + b"".join(struct.pack("<H", p) for p in pixels)
    struct.pack_into("<I", header, 4, len(raw))
    raw = bytes(header) + raw[RESOURCE_HEADER_SIZE:]
    if len(raw) <= alloc:
        return raw, "raw"
    return None, f"needs {len(blob)} compressed / {len(raw)} raw, only {alloc} available"


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("-a", "--assets", default=DEFAULT_ASSETS_DIR,
                    help=f"directory of replacement assets (default: {DEFAULT_ASSETS_DIR}/)")
    ap.add_argument("-f", "--firmware", default=DEFAULT_FIRMWARE,
                    help=f"original firmware, never modified (default: {DEFAULT_FIRMWARE})")
    ap.add_argument("-o", "--output", default=DEFAULT_OUTPUT,
                    help=f"output firmware (default: {DEFAULT_OUTPUT})")
    ap.add_argument("--list", action="store_true",
                    help="report what would be patched and exit without writing")
    ap.add_argument("--resize", action="store_true",
                    help="resize assets whose dimensions differ from the resource")
    ap.add_argument("--skip-oversized", action="store_true",
                    help="skip assets that do not fit instead of aborting")
    ap.add_argument("--force", action="store_true",
                    help="allow reading assets straight from the extractor's output dir")
    args = ap.parse_args()

    assets_dir = Path(args.assets)
    firmware = Path(args.firmware)
    output = Path(args.output)

    if not assets_dir.is_dir():
        print(f"error: assets directory '{assets_dir}' does not exist")
        print(f"hint: create it and copy in the images you want to change, e.g.")
        print(f"      mkdir -p {assets_dir} && cp {EXTRACTOR_OUTPUT_DIR}/id0000_240x320.png {assets_dir}/")
        return 1
    if not firmware.is_file():
        print(f"error: firmware '{firmware}' not found")
        return 1

    if assets_dir.resolve() == Path(EXTRACTOR_OUTPUT_DIR).resolve() and not args.force:
        print(f"error: the assets directory is the extractor's output directory "
              f"('{EXTRACTOR_OUTPUT_DIR}').")
        print("       Build inputs are kept separate from extraction outputs so a build "
              "cannot consume\n       a previous extraction wholesale. Copy the few images "
              "you want to change into a\n       separate directory, or pass --force.")
        return 1
    if output.resolve() == firmware.resolve():
        print("error: refusing to overwrite the original firmware; choose another -o")
        return 1

    fw = firmware.read_bytes()
    index = resource_index(fw)
    assets, ignored, duplicates = scan_assets(assets_dir)

    for path, why in ignored:
        print(f"  ignored  {path.name}: {why}")
    for rid, first, second in duplicates:
        print(f"  error    id {rid} claimed by both {first.name} and {second.name}")
    if duplicates:
        return 1
    if not assets:
        print(f"no usable assets found in '{assets_dir}/'. Nothing to do.")
        return 1

    from PIL import Image

    plan, problems = [], []
    for rid in sorted(assets):
        path, named_dims = assets[rid]
        if rid not in index:
            problems.append(f"id {rid} ({path.name}) is not in the firmware's resource table")
            continue
        off, w, h, alloc = index[rid]

        if named_dims and named_dims != (w, h):
            problems.append(
                f"id {rid} ({path.name}): name says {named_dims[0]}x{named_dims[1]} "
                f"but the resource is {w}x{h}"
            )
            continue

        img = Image.open(path)
        if img.size != (w, h):
            if not args.resize:
                problems.append(
                    f"id {rid} ({path.name}): image is {img.size[0]}x{img.size[1]}, "
                    f"resource is {w}x{h} (pass --resize to scale it)"
                )
                continue
            print(f"  resize   id {rid}: {img.size[0]}x{img.size[1]} -> {w}x{h}")

        pixels = image_to_rgb565(img, w, h)
        blob, how = encode_for_slot(pixels, w, h, alloc)
        if blob is None:
            msg = f"id {rid} ({path.name}) does not fit: {how}"
            if args.skip_oversized:
                print(f"  skipped  {msg}")
                continue
            problems.append(msg)
            continue
        plan.append((rid, off, w, h, alloc, blob, how, pixels, path))

    if problems:
        print()
        for p in problems:
            print(f"  error    {p}")
        print(f"\n{len(problems)} problem(s); no output written.")
        return 1

    print(f"\n{len(plan)} asset(s) to patch from '{assets_dir}/':")
    for rid, _off, w, h, alloc, blob, how, _px, path in plan:
        pct = 100 * len(blob) / alloc
        print(f"  id {rid:<5d} {w:>4d}x{h:<4d}  {how:<10s} {len(blob):>7d}/{alloc:<7d} bytes "
              f"({pct:5.1f}% of budget)  <- {path.name}")

    if args.list:
        print("\n--list given: nothing written.")
        return 0

    buf = bytearray(fw)
    for _rid, off, _w, _h, _alloc, blob, _how, _px, _path in plan:
        buf[off : off + len(blob)] = blob  # in place; table entry untouched

    patched = tjc_checksums.reseal(bytes(buf))
    output.write_bytes(patched)
    print(f"\nwrote {output} ({len(patched)} bytes, unchanged length: {len(patched) == len(fw)})")

    ok = True
    for name, (good, got, want) in tjc_checksums.verify(patched).items():
        print(f"  {name:21s}: 0x{got:08x} vs 0x{want:08x}  {'OK' if good else 'FAIL'}")
        ok &= good

    for rid, off, w, h, alloc, _blob, _how, pixels, _path in plan:
        back = decompress_image_data(patched[off : off + alloc])[: w * h]
        if back != pixels:
            print(f"  id {rid}: round-trip MISMATCH")
            ok = False
    print(f"  round-trip of {len(plan)} patched image(s): {'OK' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())

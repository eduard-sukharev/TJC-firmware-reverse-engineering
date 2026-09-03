#!/usr/bin/env python3
"""
Extract every graphical asset from a TJC .tft firmware (or a Resources.bin
partition dump) using the fully reverse-engineered decoder.

Usage:
    python3 extract_all.py -f tjc.tft -o extracted_all
    python3 extract_all.py -r Resources.bin -o extracted_all
    python3 extract_all.py -r Resources.bin -o out --raw   # also dump RGB565
"""

import argparse
import os
import struct
import sys

from tjc_decompress import (
    COMPRESSION_FLAG_COMPRESSED,
    COMPRESSION_FLAG_RAW,
    create_image_from_rgb565,
    decompress_image_data,
)

PARTITION_TABLE_OFFSET = 0x010000
PARTITION_ENTRY_SIZE = 12
ENTRY_SIZE = 24
MAGICS = (0x0301640A, 0x0301600A)


def load_resources_partition(firmware_path):
    """Pull the Resources partition out of a .tft by parsing the partition table."""
    with open(firmware_path, "rb") as f:
        fw = f.read()

    best = None
    for i in range(12):
        o = PARTITION_TABLE_OFFSET + i * PARTITION_ENTRY_SIZE
        rel, size, _meta = struct.unpack("<III", fw[o : o + PARTITION_ENTRY_SIZE])
        if best is None or size > best[1]:
            best = (rel, size)

    rel, size = best
    start = PARTITION_TABLE_OFFSET + rel
    return fw[start : start + size]


def iter_resources(data):
    """Yield (resource_id, offset, width, height, size) for each table entry."""
    for i in range(len(data) // ENTRY_SIZE):
        o = i * ENTRY_SIZE
        magic, rid, rel, wh, size, _extra = struct.unpack("<IIIIII", data[o : o + 24])
        if magic not in MAGICS:
            continue
        w, h = wh & 0xFFFF, (wh >> 16) & 0xFFFF
        if w == 0 or h == 0 or size == 0 or rel + size > len(data):
            continue
        yield rid, rel, w, h, size


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("-f", "--firmware", help="path to the .tft firmware")
    src.add_argument("-r", "--resources", help="path to a Resources.bin dump")
    ap.add_argument("-o", "--output", default="extracted_all", help="output directory")
    ap.add_argument("--raw", action="store_true", help="also write raw RGB565 .bin")
    ap.add_argument(
        "--include-placeholders",
        action="store_true",
        help="also write solid single-colour placeholder slots (570 4x2 white "
        "dummies in the stock firmware); skipped by default",
    )
    args = ap.parse_args()

    if args.firmware:
        data = load_resources_partition(args.firmware)
    else:
        with open(args.resources, "rb") as f:
            data = f.read()

    os.makedirs(args.output, exist_ok=True)

    stats = {"raw": 0, "compressed": 0, "failed": 0, "placeholder": 0}
    failures = []

    for rid, rel, w, h, size in iter_resources(data):
        blob = data[rel : rel + size]
        flag = blob[0]
        try:
            pixels = decompress_image_data(blob)
            if len(pixels) != w * h:
                raise ValueError(f"got {len(pixels)} pixels, expected {w * h}")

            # Unassigned picture slots are emitted by the editor as a minimal
            # solid-colour dummy (4x2 pure white in the stock firmware). They
            # decode correctly but carry no artwork.
            if len(set(pixels)) == 1:
                stats["placeholder"] += 1
                if not args.include_placeholders:
                    continue

            img = create_image_from_rgb565(pixels, w, h)
            name = f"id{rid:04d}_{w}x{h}"
            img.save(os.path.join(args.output, name + ".png"))

            if args.raw:
                with open(os.path.join(args.output, name + ".rgb565"), "wb") as f:
                    f.write(b"".join(struct.pack("<H", p) for p in pixels))

            stats["raw" if flag == COMPRESSION_FLAG_RAW else "compressed"] += 1
        except Exception as exc:  # noqa: BLE001 - report and continue
            stats["failed"] += 1
            failures.append((rid, w, h, f"0x{flag:02X}", str(exc)))

    total = stats["raw"] + stats["compressed"]
    print(f"Extracted {total} images to {args.output}/")
    print(f"  RAW (flag 0x{COMPRESSION_FLAG_RAW:02X})        : {stats['raw']}")
    print(f"  COMPRESSED (flag 0x{COMPRESSION_FLAG_COMPRESSED:02X}) : {stats['compressed']}")
    action = "included" if args.include_placeholders else "skipped"
    print(f"  placeholder slots       : {stats['placeholder']} ({action})")
    print(f"  failed                  : {stats['failed']}")

    for f in failures[:20]:
        print(f"    id={f[0]} {f[1]}x{f[2]} flag={f[3]}: {f[4]}")

    return 1 if stats["failed"] else 0


if __name__ == "__main__":
    sys.exit(main())

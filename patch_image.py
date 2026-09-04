#!/usr/bin/env python3
"""
Replace one image inside a TJC .tft firmware and re-seal the file.

The edit is deliberately layout-preserving: the resource is rewritten **in
place**, its table entry (offset and allocated size) is untouched, the file
length does not change, and therefore the obfuscated header 2 - which stores
section offsets and sizes - never has to be modified or deobfuscated.

What does have to be fixed afterwards are the CRCs. See tjc_checksums.py:
an image edit invalidates the bootloader/resources CRC at 0x44, which in turn
invalidates header 1's own CRC at 0xc4, and finally the whole-file CRC in the
last 4 bytes.

Usage:
    python3 patch_image.py -f tjc.tft -i 0 --image new.png -o tjc_patched.tft
    python3 patch_image.py -f tjc.tft --verify-only
"""

import argparse
import struct
import sys

import tjc_checksums
from tjc_compress import build_resource, image_to_rgb565
from tjc_decompress import decompress_image_data

PARTITION_TABLE_OFFSET = 0x010000
PARTITION_ENTRY_SIZE = 12
ENTRY_SIZE = 24
MAGICS = (0x0301640A, 0x0301600A)


def resources_base(fw):
    """File offset of the Resources partition (the largest partition)."""
    best = None
    for i in range(12):
        o = PARTITION_TABLE_OFFSET + i * PARTITION_ENTRY_SIZE
        rel, size, _meta = struct.unpack("<III", fw[o : o + PARTITION_ENTRY_SIZE])
        if best is None or size > best[1]:
            best = (rel, size)
    return PARTITION_TABLE_OFFSET + best[0], best[1]


def find_resource(fw, base, size, want_id):
    """Locate a resource table entry by id. Returns (table_off, rel, w, h, alloc)."""
    part = fw[base : base + size]
    for i in range(len(part) // ENTRY_SIZE):
        o = i * ENTRY_SIZE
        magic, rid, rel, wh, alloc, _extra = struct.unpack("<IIIIII", part[o : o + 24])
        if magic not in MAGICS:
            continue
        w, h = wh & 0xFFFF, (wh >> 16) & 0xFFFF
        if w == 0 or h == 0 or alloc == 0:
            continue
        if rid == want_id:
            return base + o, rel, w, h, alloc
    return None


def report(fw, label):
    print(f"{label}:")
    declared = struct.unpack("<I", fw[0x3C:0x40])[0]
    ok_len = declared == len(fw)
    print(f"  length field : {declared} ({'ok' if ok_len else 'MISMATCH'})")
    allok = ok_len
    for name, (ok, got, want) in tjc_checksums.verify(fw).items():
        print(f"  {name:21s}: 0x{got:08x} vs 0x{want:08x}  {'OK' if ok else 'FAIL'}")
        allok &= ok
    return allok


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-f", "--firmware", required=True)
    ap.add_argument("-i", "--id", type=int, help="resource id to replace")
    ap.add_argument("--image", help="replacement image (any PIL-readable format)")
    ap.add_argument("-o", "--output")
    ap.add_argument("--verify-only", action="store_true")
    args = ap.parse_args()

    with open(args.firmware, "rb") as f:
        fw = f.read()

    if args.verify_only:
        return 0 if report(fw, args.firmware) else 1

    if args.id is None or not args.image or not args.output:
        ap.error("--id, --image and -o are required unless --verify-only")

    from PIL import Image

    base, psize = resources_base(fw)
    found = find_resource(fw, base, psize, args.id)
    if not found:
        print(f"resource id {args.id} not found")
        return 1
    _tbl, rel, w, h, alloc = found
    off = base + rel
    print(f"resource id={args.id}: {w}x{h}, allocated {alloc} bytes at file offset 0x{off:x}")

    pixels = image_to_rgb565(Image.open(args.image), w, h)
    blob = build_resource(pixels, w, h)
    print(f"re-encoded to {len(blob)} bytes (budget {alloc})")

    if len(blob) > alloc:
        print(
            f"ERROR: does not fit ({len(blob)} > {alloc}). The replacement must "
            f"compress at least as well as the original. Use a flatter image "
            f"with fewer colour transitions."
        )
        return 1

    buf = bytearray(fw)
    buf[off : off + len(blob)] = blob  # table entry and file length untouched
    patched = tjc_checksums.reseal(bytes(buf))

    with open(args.output, "wb") as f:
        f.write(patched)
    print(f"wrote {args.output} ({len(patched)} bytes)\n")

    ok = report(patched, args.output)

    # prove the image really is the one we asked for
    rt = decompress_image_data(patched[off : off + alloc])[: w * h]
    print(f"  round-trip pixels match : {'OK' if rt == pixels else 'FAIL'}")
    return 0 if ok and rt == pixels else 1


if __name__ == "__main__":
    sys.exit(main())

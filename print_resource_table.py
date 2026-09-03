#!/usr/bin/env python3
import struct

FIRMWARE = "/home/devim/Projects/TJC_display/tjc.tft"
TABLE_OFFSET = 0x38CF4
ENTRY_STRIDE = 24

with open(FIRMWARE, "rb") as f:
    print(
        f"{'Magic2':<10} {'ID':<6} {'Rel.Offset':<8} {'Abs.Offset':<8} {'W':<4} {'H':<4} {'Size':<10} {'Extra':<10} {'Format'}"
    )
    print("-" * 70)

    f.seek(TABLE_OFFSET)
    for i in range(2500):
        data = f.read(ENTRY_STRIDE)
        if len(data) < ENTRY_STRIDE:
            break

        current_offset = TABLE_OFFSET + ENTRY_STRIDE * i
        magic, entry_id, offset, wh, size, extra = struct.unpack("<IIIIII", data)

        if magic == 0:
            continue

        if magic not in [0x0301640A, 0x0301600A]:
            print(f"Entry {i}: unknown magic=0x{magic:08x}, stopping")
            break

        width = wh & 0xFFFF
        height = (wh >> 16) & 0xFFFF

        raw_size = width * height * 2

        if size == 0:
            fmt = "EMPTY"
        elif width == 0 or height == 0:
            fmt = "INVALID"
        elif size == raw_size + 20:
            fmt = "RAW"
        elif size < raw_size:
            fmt = "COMPRESSED"
        else:
            fmt = "UNKNOWN"

        print(
            f"0x{magic:<8x} {entry_id:<6} 0x{offset:<6x} 0x{TABLE_OFFSET + offset:<6x} {width:<4} {height:<4} {size:<10} 0x{magic1:<8x} {fmt}"
        )

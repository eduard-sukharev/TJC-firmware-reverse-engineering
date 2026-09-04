"""
Integrity values in a TJC/Nextion .tft firmware file.

There is **no encryption over the image data** - the resources are stored in
the clear (which is why they decode directly). What protects the file is a set
of CRC values, plus an obfuscated second header that a well-behaved edit never
has to touch.

The CRC
-------
All four values use the same primitive: the Nextion "byte based" CRC-32,
polynomial 0x04C11DB7, MSB-first, no reflection.

Each input byte is fed into the shift register as a full 32-bit word (so 24
zero bits then the 8 data bits), the *first* word is XORed with 0xFFFFFFFF,
and 32 zero bits are appended at the end. Equivalently the register holds the
polynomial remainder of that bit stream.

The four values
---------------
=========================  =========================  =========================
Stored at                  Covers                     Notes
=========================  =========================  =========================
0x0044-0x0047              fw[0x10000:0x710000]       bootloader + resources.
                                                      **An image edit breaks
                                                      this one.**
0x00c4-0x00c7              fw[0x000000:0x0000c4]      header 1
0x018c-0x018f              fw[0x0000c8:0x00018c]      header 2 (obfuscated body,
                                                      but the CRC is plain)
last 4 bytes               fw[:-4]                    whole file. Stored little
                                                      endian with the LOW byte
                                                      XORed by
                                                      fw[0x03]^fw[0x2e]^fw[0x3c]
=========================  =========================  =========================

Header 2 (0xc8-0x18b) is obfuscated with a position-dependent stream (entropy
~6.7; the three fields documented as zero on Nextion Basic/Enhanced read back
as three *different* values here, so it is not a repeating XOR key). It holds
section offsets and sizes. As long as an edit keeps the file length and every
section/resource offset identical, header 2 never changes and its obfuscation
does not need to be broken.

Field 0x3c-0x3f of header 1 holds the total file length, so changing the file
size means touching header 1 as well.
"""

import struct

POLY = 0x04C11DB7

# Region definitions: (name, crc_store_offset, start, end)
# `end` of None means "end of file minus the 4 CRC bytes".
FILE_CRC_MASK_OFFSETS = (0x03, 0x2E, 0x3C)


def _mulx32(r):
    """Multiply the register by x^32 modulo the polynomial."""
    for _ in range(32):
        r <<= 1
        if r & 0x100000000:
            r ^= POLY | 0x100000000
    return r & 0xFFFFFFFF


_TABLES = [[_mulx32(b << (8 * i)) for b in range(256)] for i in range(4)]


def _advance(reg):
    t0, t1, t2, t3 = _TABLES
    return (
        t0[reg & 0xFF]
        ^ t1[(reg >> 8) & 0xFF]
        ^ t2[(reg >> 16) & 0xFF]
        ^ t3[(reg >> 24) & 0xFF]
    )


def crc(data):
    """The Nextion/TJC byte-based CRC-32 over `data`."""
    t0, t1, t2, t3 = _TABLES
    reg = 0
    first = True
    for b in data:
        w = (b ^ 0xFFFFFFFF) if first else b
        first = False
        reg = (
            t0[reg & 0xFF]
            ^ t1[(reg >> 8) & 0xFF]
            ^ t2[(reg >> 16) & 0xFF]
            ^ t3[(reg >> 24) & 0xFF]
        ) ^ w
    return _advance(reg)


def bootloader_resources_range(fw):
    """
    Byte range covered by the 0x44-0x47 checksum.

    The section starts at 0x10000 and ends at the start of the user code
    section, which is aligned to the section size recorded at 0x34-0x37.
    """
    section = struct.unpack("<I", fw[0x34:0x38])[0] or 0x10000
    # user code section start, from header 2, is obfuscated; the stock layout
    # ends the section at the last section-size boundary before the tail.
    end = 0x710000
    return 0x10000, end if end <= len(fw) else (len(fw) // section) * section


def file_crc_mask(fw):
    m = 0
    for off in FILE_CRC_MASK_OFFSETS:
        m ^= fw[off]
    return m


def expected_values(fw):
    """Compute what all four CRC fields should be for the given image."""
    lo, hi = bootloader_resources_range(fw)
    out = {
        "bootloader_resources": (0x44, crc(fw[lo:hi])),
        "header1": (0xC4, crc(fw[0x00:0xC4])),
        "header2": (0x18C, crc(fw[0xC8:0x18C])),
    }
    raw = crc(fw[:-4])
    masked = (raw & 0xFFFFFF00) | ((raw & 0xFF) ^ file_crc_mask(fw))
    out["file"] = (len(fw) - 4, masked)
    return out


def stored_values(fw):
    return {
        name: struct.unpack("<I", fw[off : off + 4])[0]
        for name, (off, _v) in expected_values(fw).items()
    }


def verify(fw):
    """Return {name: (ok, stored, expected)} for all four CRC fields."""
    result = {}
    for name, (off, want) in expected_values(fw).items():
        got = struct.unpack("<I", fw[off : off + 4])[0]
        result[name] = (got == want, got, want)
    return result


def reseal(fw):
    """
    Recompute every CRC and return a corrected copy of the firmware.

    Order matters: the bootloader/resources CRC lives inside header 1, and
    header 1's own CRC covers it, and the whole-file CRC covers everything.
    """
    buf = bytearray(fw)

    lo, hi = bootloader_resources_range(buf)
    struct.pack_into("<I", buf, 0x44, crc(bytes(buf[lo:hi])))
    struct.pack_into("<I", buf, 0xC4, crc(bytes(buf[0x00:0xC4])))
    struct.pack_into("<I", buf, 0x18C, crc(bytes(buf[0xC8:0x18C])))

    raw = crc(bytes(buf[:-4]))
    masked = (raw & 0xFFFFFF00) | ((raw & 0xFF) ^ file_crc_mask(buf))
    struct.pack_into("<I", buf, len(buf) - 4, masked)
    return bytes(buf)


def set_file_length(buf):
    """Update header 1's total-file-length field (0x3c-0x3f) to match."""
    struct.pack_into("<I", buf, 0x3C, len(buf))


if __name__ == "__main__":
    import sys

    path = sys.argv[1] if len(sys.argv) > 1 else "tjc.tft"
    with open(path, "rb") as f:
        fw = f.read()
    print(f"{path}: {len(fw)} bytes")
    declared = struct.unpack("<I", fw[0x3C:0x40])[0]
    print(f"  declared length 0x3c-0x3f : {declared} ({'ok' if declared == len(fw) else 'MISMATCH'})")
    for name, (ok, got, want) in verify(fw).items():
        print(f"  {name:22s}: stored 0x{got:08x} expected 0x{want:08x} {'OK' if ok else 'FAIL'}")

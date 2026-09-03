"""
TJC Image Decompression Module

Fully reverse-engineered decoder for the image resources in TJC/Nextion .tft
firmware (Ender-3 V3 SE display, TJC3224T132_011N_P04).

Format
------
Each resource begins with a 20-byte header:

    byte 0      compression flag: 0x00 = RAW, 0x04 = COMPRESSED
    bytes 4-7   uint32 LE: total byte length of (header + payload) that is
                actually used. Anything in the resource table's `size` beyond
                this is trailing padding and must NOT be decoded.

RAW payload is simply width*height RGB565 pixels, little-endian.

COMPRESSED payload is a sequence of 20-byte blocks:

    bytes 0-3    4 control bytes
    bytes 4-19   8 RGB565 pixels (little-endian, 2 bytes each)

There are two kinds of block:

1. Literal block, signalled by the control field being exactly
   ``1F 11 11 11``. All 8 pixels are emitted once each (8 pixels total).

2. RLE block. Each control byte is split into two nibbles, **low nibble
   first, then high nibble**, giving 8 repeat counts that correspond
   one-to-one with the 8 pixels. A count of 0 means the slot emits nothing.

Pixels are emitted in row-major order. (The encoder additionally aligns the
stream so that every group of 4 output rows ends on a block boundary, but a
decoder does not need to care: with the literal block handled correctly the
counts sum exactly to width*height.)

Verification
------------
Across all 1994 compressed resources in the stock firmware, this decoder
satisfies three independent invariants at 100%:

  * decoded pixel count == width * height
  * every 4-row stripe's counts sum exactly (encoder alignment invariant)
  * bytes consumed == the length recorded at header bytes 4-7

See test_tjc_decompress.py.
"""

import struct

# Compression flag constants
COMPRESSION_FLAG_RAW = 0x00
COMPRESSION_FLAG_COMPRESSED = 0x04

RESOURCE_HEADER_SIZE = 20
BLOCK_SIZE = 20
PIXELS_PER_BLOCK = 8

#: Control field marking a literal (uncompressed) block.
LITERAL_CONTROL = b"\x1f\x11\x11\x11"


def control_to_counts(ctrl):
    """
    Convert the 4 control bytes into 8 repeat counts.

    Each byte contributes its low nibble first, then its high nibble.
    """
    counts = []
    for b in ctrl:
        counts.append(b & 0x0F)
        counts.append((b >> 4) & 0x0F)
    return counts


def block_pixels(block):
    """Extract the 8 little-endian RGB565 pixel values from a 20-byte block."""
    return [
        block[4 + j * 2] | (block[4 + j * 2 + 1] << 8)
        for j in range(PIXELS_PER_BLOCK)
    ]


def decompress_block(block):
    """
    Decode one 20-byte block into a list of RGB565 values.

    Handles both literal blocks and RLE blocks.
    """
    if len(block) < BLOCK_SIZE:
        raise ValueError(f"Block too short: {len(block)} bytes (need {BLOCK_SIZE})")

    pixels = block_pixels(block)

    if block[0:4] == LITERAL_CONTROL:
        return list(pixels)

    out = []
    for pixel, count in zip(pixels, control_to_counts(block[0:4])):
        if count:
            out.extend([pixel] * count)
    return out


def payload_length(data):
    """
    Return the number of payload bytes that follow the 20-byte header.

    Read from header bytes 4-7, which record the total used length including
    the header itself. Falls back to the whole buffer if the field looks bogus.
    """
    total = struct.unpack("<I", data[4:8])[0]
    if RESOURCE_HEADER_SIZE <= total <= len(data):
        return total - RESOURCE_HEADER_SIZE
    return len(data) - RESOURCE_HEADER_SIZE


def decompress_image_data(data):
    """
    Decode a full resource (20-byte header + payload) into RGB565 values.

    Args:
        data: bytes - the resource exactly as stored, including its header.

    Returns:
        list of 16-bit RGB565 integers.
    """
    if len(data) < RESOURCE_HEADER_SIZE:
        raise ValueError(
            f"Data too short: {len(data)} bytes "
            f"(need at least {RESOURCE_HEADER_SIZE} for header)"
        )

    flag = data[0]
    n = payload_length(data)
    payload = data[RESOURCE_HEADER_SIZE : RESOURCE_HEADER_SIZE + n]

    if flag == COMPRESSION_FLAG_RAW:
        return [
            payload[i] | (payload[i + 1] << 8) for i in range(0, len(payload) - 1, 2)
        ]

    if flag == COMPRESSION_FLAG_COMPRESSED:
        out = []
        for off in range(0, len(payload) - BLOCK_SIZE + 1, BLOCK_SIZE):
            out.extend(decompress_block(payload[off : off + BLOCK_SIZE]))
        return out

    raise ValueError(f"Unknown compression flag: 0x{flag:02X}")


def rgb565_to_rgb(rgb565):
    """Convert a 16-bit RGB565 value to an (r, g, b) tuple of 0-255 values."""
    r = (rgb565 >> 11) & 0x1F
    g = (rgb565 >> 5) & 0x3F
    b = rgb565 & 0x1F
    return (r * 8, g * 4, b * 8)


def create_image_from_rgb565(pixels, width, height):
    """Build a PIL RGB image from a list of RGB565 values."""
    from PIL import Image

    expected = width * height
    if len(pixels) != expected:
        print(f"Warning: got {len(pixels)} pixels, expected {expected}")

    pixels = pixels[:expected]
    if len(pixels) < expected:
        pixels = pixels + [0] * (expected - len(pixels))

    img = Image.new("RGB", (width, height))
    img.putdata([rgb565_to_rgb(p) for p in pixels])
    return img


def get_resource_header_size():
    """Size of the per-resource metadata header, in bytes."""
    return RESOURCE_HEADER_SIZE


def decompress_and_create_image(data, width, height):
    """
    Decode a resource and return it as a PIL RGB image.

    Args:
        data: bytes - resource including its 20-byte header
        width, height: expected dimensions from the resource table
    """
    return create_image_from_rgb565(decompress_image_data(data), width, height)

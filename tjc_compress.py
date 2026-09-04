"""
Encoder for the TJC image format - the inverse of tjc_decompress.

It reproduces the original encoder's conventions, which were recovered from
the stock firmware:

* The image is encoded in **stripes of 4 output rows**. Each stripe is encoded
  independently and padded to a whole number of 20-byte blocks, with the unused
  trailing slots given a repeat count of 0. Runs never cross a stripe boundary.

* Within a block, run counts are 1..15, **except the first slot which is capped
  at 14**. That is how the encoder guarantees it can never accidentally emit the
  literal-block signature ``1F 11 11 11``. (In the stock firmware the first run
  count is never 15, across all 321975 blocks.)

* A block that would consist of 8 runs of count 1 is emitted as a **literal
  block** instead: control ``1F 11 11 11`` followed by the 8 pixels. The plain
  form ``11 11 11 11`` never appears in the stock firmware.

Unused pixel slots (those with a repeat count of 0) are never read back by the
decoder. The stock encoder leaves stale buffer contents there; this one repeats
the last emitted value, which is why re-encoding is semantically identical to
the original but not always byte-identical.
"""

import struct

from tjc_decompress import (
    BLOCK_SIZE,
    LITERAL_CONTROL,
    PIXELS_PER_BLOCK,
    RESOURCE_HEADER_SIZE,
    COMPRESSION_FLAG_COMPRESSED,
)

STRIPE_ROWS = 4
MAX_RUN = 15
MAX_FIRST_RUN = 14


def _encode_stripe(pixels, out):
    """Encode one stripe (a flat list of pixel values) into whole blocks."""
    i = 0
    n = len(pixels)
    while i < n:
        runs = []
        while len(runs) < PIXELS_PER_BLOCK and i < n:
            limit = MAX_FIRST_RUN if not runs else MAX_RUN
            value = pixels[i]
            count = 1
            while i + count < n and pixels[i + count] == value and count < limit:
                count += 1
            runs.append((value, count))
            i += count

        if len(runs) == PIXELS_PER_BLOCK and all(c == 1 for _v, c in runs):
            out += LITERAL_CONTROL
            for value, _c in runs:
                out += struct.pack("<H", value)
            continue

        filler = runs[-1][0] if runs else 0
        padded = runs + [(filler, 0)] * (PIXELS_PER_BLOCK - len(runs))

        ctrl = bytearray(4)
        for j in range(4):
            lo = padded[2 * j][1]
            hi = padded[2 * j + 1][1]
            ctrl[j] = (lo & 0x0F) | ((hi & 0x0F) << 4)
        assert bytes(ctrl) != LITERAL_CONTROL, "encoder emitted the literal signature"

        out += ctrl
        for value, _c in padded:
            out += struct.pack("<H", value)


def compress_pixels(pixels, width, height):
    """
    Encode RGB565 pixel values into a TJC compressed payload (no header).

    Args:
        pixels: sequence of width*height 16-bit RGB565 values, row-major
        width, height: image dimensions

    Returns:
        bytes - the block stream
    """
    if len(pixels) != width * height:
        raise ValueError(f"expected {width * height} pixels, got {len(pixels)}")

    out = bytearray()
    stripe = STRIPE_ROWS * width
    for start in range(0, len(pixels), stripe):
        _encode_stripe(list(pixels[start : start + stripe]), out)
    return bytes(out)


def build_resource(pixels, width, height):
    """
    Build a complete compressed resource: 20-byte header + payload.

    The header records the compression flag and, at bytes 4-7, the total used
    length (header + payload) exactly as the stock firmware does.
    """
    payload = compress_pixels(pixels, width, height)
    header = bytearray(RESOURCE_HEADER_SIZE)
    header[0] = COMPRESSION_FLAG_COMPRESSED
    struct.pack_into("<I", header, 4, RESOURCE_HEADER_SIZE + len(payload))
    return bytes(header) + payload


def image_to_rgb565(img, width, height):
    """Convert a PIL image to a row-major list of RGB565 values."""
    img = img.convert("RGB")
    if img.size != (width, height):
        img = img.resize((width, height))
    out = []
    for r, g, b in img.getdata():
        out.append(((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3))
    return out

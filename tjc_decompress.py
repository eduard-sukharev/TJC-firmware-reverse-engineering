"""
TJC Image Decompression Module

Decompression algorithm discovered from TJC TFT firmware analysis.
Each 20-byte block contains: 4 bytes control (8 nibbles = repeat counts) + 8 RGB565 pixels.
"""

# Compression flag constants
COMPRESSION_FLAG_RAW = 0x00
COMPRESSION_FLAG_COMPRESSED = 0x04
RESOURCE_HEADER_SIZE = 20


def control_to_nibbles(ctrl):
    """
    Convert 4-byte control to 8 nibbles.
    Each byte split into 2 nibbles: low nibble first, then high nibble.
    """
    nibbles = []
    for b in ctrl:
        nibbles.append(b & 0x0F)  # lower nibble
        nibbles.append((b >> 4) & 0x0F)  # upper nibble
    return nibbles


def decompress_block(block):
    """
    Decompress a single 20-byte block.

    Block structure:
    - Bytes 0-3:   4 bytes control = 8 nibbles (repeat counts)
    - Bytes 4-19:  8 RGB565 pixels (16 bytes)

    Returns: list of RGB565 color values
    """
    if len(block) < 20:
        raise ValueError(f"Block too short: {len(block)} bytes (need 20)")

    # Get control nibbles (repeat counts)
    ctrl = block[0:4]
    nibbles = control_to_nibbles(ctrl)

    # Extract 8 RGB565 pixel values (bytes 4-19)
    pixels = []
    for j in range(8):
        lo = block[4 + j * 2]
        hi = block[4 + j * 2 + 1]
        pixels.append(lo | (hi << 8))

    # Apply nibbles as repeat counts
    decoded = []
    for j, n in enumerate(nibbles):
        if j < len(pixels):
            decoded.extend([pixels[j]] * n)

    return decoded


def decompress_image_data(data):
    """
    Decompress full image data from TJC compressed format.

    Args:
        data: bytes - compressed image data (with 20-byte resource header)

    Returns:
        list of RGB565 color values (16-bit integers)
    """
    # Skip 20-byte resource header
    if len(data) < RESOURCE_HEADER_SIZE:
        raise ValueError(
            f"Data too short: {len(data)} bytes (need at least {RESOURCE_HEADER_SIZE} for header)"
        )

    # Check compression flag
    compression_flag = data[0]

    if compression_flag == COMPRESSION_FLAG_RAW:
        # RAW format: no compression, just 20-byte header + raw RGB565 pixels
        return _decompress_raw(data)
    elif compression_flag == COMPRESSION_FLAG_COMPRESSED:
        # Compressed format
        return _decompress_compressed(data)
    else:
        raise ValueError(f"Unknown compression flag: 0x{compression_flag:02X}")


def _decompress_raw(data):
    """Decompress RAW (uncompressed) image data."""
    image_data = data[RESOURCE_HEADER_SIZE:]

    # Parse as raw RGB565 pairs
    pixels = []
    for i in range(0, len(image_data) - 1, 2):
        lo = image_data[i]
        hi = image_data[i + 1]
        pixels.append(lo | (hi << 8))

    return pixels


def _decompress_compressed(data):
    """Decompress compressed image data."""
    image_data = data[RESOURCE_HEADER_SIZE:]
    decoded = []

    # Process 20-byte blocks: 4 bytes control + 8 RGB565 pixels
    block_count = len(image_data) // 20

    for i in range(block_count):
        start = i * 20
        block = image_data[start : start + 20]

        try:
            pixels = decompress_block(block)
            decoded.extend(pixels)
        except ValueError as e:
            print(f"Warning: Block {i} error: {e}")

    # Handle remaining bytes (if any)
    remaining = len(image_data) % 20
    if remaining > 0:
        # Start position should be after last complete 20-byte block
        start = block_count * 20
        remainder = image_data[start : start + remaining]

        # Remaining should be multiple of 2 (RGB565 pixels)
        for i in range(0, len(remainder) - 1, 2):
            lo = remainder[i]
            hi = remainder[i + 1]
            decoded.append(lo | (hi << 8))

    return decoded


def rgb565_to_rgb(rgb565):
    """
    Convert RGB565 (16-bit) to RGB888 (24-bit) tuple.

    Args:
        rgb565: int - 16-bit RGB565 value

    Returns:
        tuple: (r, g, b) each 0-255
    """
    r = ((rgb565 >> 11) & 0x1F) << 3
    g = ((rgb565 >> 5) & 0x3F) << 2
    b = (rgb565 & 0x1F) << 3

    return (r, g, b)


def create_image_from_rgb565(pixels, width, height):
    """
    Create PIL Image from RGB565 pixel data.
    """
    from PIL import Image

    expected = width * height
    if len(pixels) != expected:
        print(f"Warning: Got {len(pixels)} pixels, expected {expected}")

    # Take exact amount needed
    pixels = pixels[:expected]

    # Create RGB888 data
    rgb_data = [rgb565_to_rgb(p) for p in pixels]

    # Create image
    img = Image.new("RGB", (width, height))
    img.putdata(rgb_data)

    return img


def get_resource_header_size():
    """
    Returns the size of the resource metadata header (20 bytes).
    """
    return RESOURCE_HEADER_SIZE


def decompress_and_create_image(data, width, height):
    """
    Decompress TJC compressed data and create PIL Image.

    Args:
        data: bytes - compressed image data (including 20-byte resource header)
        width: int - expected image width
        height: int - expected image height

    Returns:
        PIL Image in RGB mode
    """
    pixels = decompress_image_data(data)
    return create_image_from_rgb565(pixels, width, height)

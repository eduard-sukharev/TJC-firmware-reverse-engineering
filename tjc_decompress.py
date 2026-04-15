"""
TJC Image Decompression Module

Decompression algorithm discovered from TJC TFT firmware analysis.
Each 20-byte block contains: 4 bytes control (8 nibbles = repeat counts) + 8 RGB565 pixels.

Note: Some images may have block alignment issues in the middle, causing slight
shifting artifacts. This may be due to the relative offset calculation or
specific image dimensions affecting how blocks are processed.
"""


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
    if len(data) < 20:
        raise ValueError(
            f"Data too short: {len(data)} bytes (need at least 20 for header)"
        )

    image_data = data[20:]

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
        remainder = image_data[-remaining:]
        # Remaining should be multiple of 2 (RGB565 pixels)
        for i in range(0, len(remainder) - 1, 2):
            if i + 1 < len(remainder):
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
    r = (rgb565 >> 11) & 0x1F
    g = (rgb565 >> 5) & 0x3F
    b = rgb565 & 0x1F

    # Scale to 8-bit
    r = r << 3
    g = g << 2
    b = b << 3

    return (r, g, b)


def create_image_from_rgb565(pixels, width, height):
    """
    Create PIL Image from RGB565 pixel data.
    """
    from PIL import Image

    if len(pixels) < width * height:
        raise ValueError(f"Not enough pixels: {len(pixels)} (need {width * height})")

    # Take exact amount needed
    pixels = pixels[: width * height]

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
    return 20


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

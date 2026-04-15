"""
TJC Image Decompression Module

Decompression algorithm discovered from TJC TFT firmware analysis.
Each 20-byte segment encodes 8 pixels using nibble-based run-length encoding.
"""


def control_to_nibbles(ctrl):
    """
    Convert 4-byte control to 8 nibbles (in LE order).
    Each byte is split into 2 nibbles: low nibble first, then high nibble.
    """
    nibbles = []
    for b in ctrl:
        nibbles.append(b & 0x0F)  # lower nibble
        nibbles.append((b >> 4) & 0x0F)  # upper nibble
    return nibbles


def decompress_segment(segment):
    """
    Decompress a single 20-byte segment.

    Segment structure:
    - Bytes 0-11:  6 RGB565 pixels (raw)
    - Bytes 12-15: 4 bytes - control (FE + nibble values)
    - Bytes 16-19: 2 RGB565 pixels (raw, part of next segment's first 6)

    Returns: list of RGB565 color values
    """
    if len(segment) < 20:
        raise ValueError(f"Segment too short: {len(segment)} bytes (need 20)")

    # Extract 8 color values from segment
    colors = []

    # First 6 colors (bytes 0-11)
    for j in range(6):
        lo = segment[j * 2]
        hi = segment[j * 2 + 1]
        colors.append(lo | (hi << 8))

    # Last 2 colors (bytes 16-19)
    for j in range(2):
        lo = segment[16 + j * 2]
        hi = segment[17 + j * 2]
        colors.append(lo | (hi << 8))

    # Get control nibbles
    ctrl = segment[12:16]
    nibbles = control_to_nibbles(ctrl)

    # Apply nibbles as repeat counts
    decoded = []
    for j, n in enumerate(nibbles):
        if j < len(colors):
            decoded.extend([colors[j]] * n)

    return decoded


def decompress_image_data(data):
    """
    Decompress full image data from TJC compressed format.

    Args:
        data: bytes - compressed image data

    Returns:
        list of RGB565 color values (16-bit integers)
    """
    decoded = []

    # Process 20-byte segments
    segment_count = len(data) // 20

    for i in range(segment_count):
        start = i * 20
        segment = data[start : start + 20]

        try:
            pixels = decompress_segment(segment)
            decoded.extend(pixels)
        except ValueError as e:
            print(f"Warning: Segment {i} error: {e}")

    # Handle remaining bytes (if any)
    remaining = len(data) % 20
    if remaining > 0:
        # Try to parse remaining as raw pixels
        remainder = data[-remaining:]
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

    Args:
        pixels: list of RGB565 values
        width: int - image width
        height: int - image height

    Returns:
        PIL Image in RGB mode
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


def decompress_and_create_image(data, width, height):
    """
    Decompress TJC compressed data and create PIL Image.

    Args:
        data: bytes - compressed image data
        width: int - expected image width
        height: int - expected image height

    Returns:
        PIL Image in RGB mode
    """
    pixels = decompress_image_data(data)
    return create_image_from_rgb565(pixels, width, height)

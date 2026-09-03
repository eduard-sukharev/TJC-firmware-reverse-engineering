"""
TJC Image Decompression Module

Decompression algorithm discovered from TJC TFT firmware analysis.
Each 20-byte block contains: 4 bytes control (8 nibbles = repeat counts) + 8 RGB565 pixels.
"""

# Compression flag constants
COMPRESSION_FLAG_RAW = 0x00
COMPRESSION_FLAG_COMPRESSED = 0x04
COMPRESSION_FLAG_RLE01 = 0x01  # 2-byte count (LE) + 1-byte value
RESOURCE_HEADER_SIZE = 20


def control_to_nibbles(ctrl, order="lo"):
    """
    Convert 4-byte control to 8 nibbles.
    
    Args:
        ctrl: 4 bytes of control data
        order: "lo" for lo-first (lo nibble then hi nibble), "hi" for hi-first
    
    Returns:
        list of 8 integers (0-15)
    """
    nibbles = []
    for b in ctrl:
        if order == "lo":
            nibbles.append(b & 0x0F)  # lower nibble first
            nibbles.append((b >> 4) & 0x0F)  # upper nibble second
        else:  # hi-first
            nibbles.append((b >> 4) & 0x0F)  # upper nibble first
            nibbles.append(b & 0x0F)  # lower nibble second
    return nibbles


def decompress_block(block, nibble_order="lo"):
    """
    Decompress a single 20-byte block.

    Block structure:
    - Bytes 0-3:   4 bytes control = 8 nibbles (repeat counts)
    - Bytes 4-19:  8 RGB565 pixels (16 bytes)

    Args:
        block: 20 bytes
        nibble_order: "lo" for lo-first, "hi" for hi-first

    Returns: list of RGB565 color values
    """
    if len(block) < 20:
        raise ValueError(f"Block too short: {len(block)} bytes (need 20)")

    # Get control nibbles (repeat counts)
    ctrl = block[0:4]
    nibbles = control_to_nibbles(ctrl, nibble_order)

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


def decompress_image_data(data, nibble_order="lo"):
    """
    Decompress full image data from TJC compressed format.

    Args:
        data: bytes - compressed image data (with 20-byte resource header)
        nibble_order: "lo" for lo-first (test.tft), "hi" for hi-first (tjc.tft main)

    Returns:
        list of RGB565 color values (16-bit integers)
    """
    # Skip 20-byte resource header
    if len(data) < RESOURCE_HEADER_SIZE:
        raise ValueError(
            f"Data too short: {len(data)} bytes (need at least {RESOURCE_HEADER_SIZE} for header)"
        )

    compression_flag = data[0]

    if compression_flag == COMPRESSION_FLAG_RAW:
        return _decompress_raw(data)
    elif compression_flag == COMPRESSION_FLAG_COMPRESSED:
        # 0x04 uses hi-first nibble order for tjc.tft
        try:
            return _decompress_compressed(data[RESOURCE_HEADER_SIZE:], nibble_order="hi")
        except Exception:
            return _decompress_compressed(data[RESOURCE_HEADER_SIZE:], nibble_order="lo")
    elif compression_flag == COMPRESSION_FLAG_RLE01:
        # 0x01 uses lo-first nibble order (test.tft)
        try:
            return _decompress_compressed(data[RESOURCE_HEADER_SIZE:], nibble_order="lo")
        except Exception:
            return _decompress_rle01(data)
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


def _decompress_rle01(data):
    """
    Decompress 0x01 format: 2-byte count (little-endian) + 1-byte value per run.
    
    Format: [count_low(1)][count_high(1)][value(1)][count_low][count_high][value]...
    Count is 16-bit little-endian, value is 8-bit grayscale/palette index.
    
    Returns 8-bit grayscale values (not RGB565).
    """
    image_data = data[RESOURCE_HEADER_SIZE:]
    pixels = []
    i = 0
    
    # Continue until we have enough pixels (or run out of data)
    # No early termination - continue until data ends
    while i + 2 < len(image_data):
        count_low = image_data[i]
        count_high = image_data[i + 1]
        count = count_low | (count_high << 8)
        
        if count == 0:
            i += 3
            continue
        
        value = image_data[i + 2]
        pixels.extend([value] * count)
        i += 3
    
    return pixels


def _decompress_compressed(data, nibble_order="lo"):
    """
    Decompress compressed image data.
    
    Args:
        data: bytes - image data (after 20-byte header)
        nibble_order: "lo" for lo-first (test.tft worked), "hi" for hi-first (tjc.tft)
    """
    decoded = []

    # Process 20-byte blocks: 4 bytes control + 8 RGB565 pixels
    block_count = len(data) // 20

    for i in range(block_count):
        start = i * 20
        block = data[start : start + 20]

        try:
            pixels = decompress_block(block, nibble_order)
            decoded.extend(pixels)
        except ValueError as e:
            print(f"Warning: Block {i} error: {e}")

    # Handle remaining bytes (if any)
    remaining = len(data) % 20
    if remaining > 0:
        start = block_count * 20
        remainder = data[start : start + remaining]

        # Remaining should be multiple of 2 (RGB565 pixels)
        for i in range(0, len(remainder) - 1, 2):
            lo = remainder[i]
            hi = remainder[i + 1]
            decoded.append(lo | (hi << 8))

    return decoded


def rgb565_to_rgb(rgb565):
    """
    Convert RGB565 (16-bit) to RGB888 (24-bit) tuple using simple multiply.

    Args:
        rgb565: int - 16-bit RGB565 value

    Returns:
        tuple: (r, g, b) each 0-255
    """
    r = (rgb565 >> 11) & 0x1F
    g = (rgb565 >> 5) & 0x3F
    b = rgb565 & 0x1F

    return (r * 8, g * 4, b * 8)


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
    from PIL import Image as PILImage
    
    pixels = decompress_image_data(data)
    
    # Check if we got RGB565 values (0-65535) or 8-bit grayscale (0-255)
    # RGB565 values would be > 255, grayscale values are <= 255
    if pixels and isinstance(pixels[0], int) and pixels[0] <= 255:
        # 8-bit grayscale - convert to RGB
        expected = width * height
        # First, trim to exact size
        pixels = pixels[:expected]
        
        # Fill with grayscale value repeated 3 times to make RGB888 tuple
        rgb_data = [(p, p, p) for p in pixels]
        
        img = PILImage.new("RGB", (width, height))
        img.putdata(rgb_data)
    else:
        # RGB565 format
        img = create_image_from_rgb565(pixels, width, height)
    
    return img

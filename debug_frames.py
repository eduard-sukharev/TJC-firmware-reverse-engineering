#!/usr/bin/env python3
"""
Debug script: Create image after each compressed block, pad with marker color.
"""

import os
from PIL import Image
from tjc_decompress import control_to_nibbles, decompress_block, rgb565_to_rgb

# Configuration
RESOURCES_PATH = "Resources.bin"
OUTPUT_DIR = "debug_frames"
IMAGE_WIDTH = 102
IMAGE_HEIGHT = 115

# Padding color for missing pixels (RGB565 0xFD54)
# In RGB: R=((0xFD54>>11)&0x1F)<<3, G=((0xFD54>>5)&0x3F)<<2, B=(0xFD54&0x1F)<<3
# 0xFD54 = 0b1111110101010100
# R = 0xFD54 >> 11 = 0x7E = 126 -> 126 << 3 = 1008 (clamped to 255)
# Actually: (126 & 0x1F) * 8 doesn't work that way
# Let me recalculate: 0xFD54 = 64852
# R = (64852 >> 11) & 0x1F = 0x1F = 31 -> 31 * 8 = 248
# G = (64852 >> 5) & 0x3F = 0x1A = 26 -> 26 * 4 = 104
# B = 64852 & 0x1F = 0x14 = 20 -> 20 * 8 = 160

PAD_COLOR_RGB565 = 0xFD54
PAD_COLOR = (248, 104, 160)  # #F868A0 - pink-ish

def create_image(pixels, width, height, pad_color=PAD_COLOR):
    """Create image, padding missing pixels with marker color."""
    img = Image.new("RGB", (width, height))

    # Fill with pad color first
    for y in range(height):
        for x in range(width):
            img.putpixel((x, y), pad_color)

    # Put actual pixels
    for i, p in enumerate(pixels):
        if i >= width * height:
            break
        x = i % width
        y = i // width
        img.putpixel((x, y), rgb565_to_rgb(p))

    return img


def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load resource data (entry 2: 102x115)
    with open(RESOURCES_PATH, "rb") as f:
        f.seek(0x26560)  # rel_offset for entry 2
        data = f.read(3906)

    # Skip 20-byte header
    image_data = data[20:]

    print(f"Image data: {len(image_data)} bytes")
    print(f"Expected pixels: {IMAGE_WIDTH * IMAGE_HEIGHT}")
    print(f"Blocks: {len(image_data) // 20}")

    # Process each block, save image after each
    decoded_pixels = []

    for block_idx in range(len(image_data) // 20):
        start = block_idx * 20
        block = image_data[start : start + 20]

        # Decompress this block
        pixels = decompress_block(block)
        decoded_pixels.extend(pixels)

        # Get absolute file offset for filename
        abs_offset = 0x26560 + 20 + start  # resource start + header + block offset
        block_hex = f"0x{abs_offset:08x}"

        # Create image with padding
        img = create_image(decoded_pixels, IMAGE_WIDTH, IMAGE_HEIGHT)

        # Save with block number and absolute offset
        filename = f"block_{block_idx:03d}_{block_hex}.png"
        filepath = os.path.join(OUTPUT_DIR, filename)
        img.save(filepath)

        print(
            f"Block {block_idx}: decoded {len(pixels)} pixels, total {len(decoded_pixels)} - saved {filename}"
        )

    print(f"\nDone! Saved {block_idx + 1} frames to {OUTPUT_DIR}/")


if __name__ == "__main__":
    main()

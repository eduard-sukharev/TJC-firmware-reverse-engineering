#!/usr/bin/env python3
"""
Composite image 2 over the lower part of image 1.

Steps:
1. Load image 1 (120x64)
2. Resize image 2 to 120x32 (half height of image 1)
3. Convert to RGB565
4. Overlay onto lower part of image 1
5. Save result
"""

import sys
import os
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tjc_decompress import rgb565_to_rgb


def rgb_to_rgb565(r, g, b):
    """Convert RGB to RGB565."""
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def main():
    # Load images
    img1 = Image.open("test_pattern_120x64.png")  # 120x64
    img2 = Image.open("palette_lofi.png")  # arbitrary size

    # Resize image 2 to 120x32 (half height of image 1)
    img2_resized = img2.resize((120, 32), Image.LANCZOS)

    # Overlay onto lower part of image 1 (rows 32-63)
    result = img1.copy()
    result.paste(img2_resized, (0, 32))  # paste at (0, 32)

    # Save result
    result.save("extracted/composite_result.png")
    print(f"Saved composite to extracted/composite_result.png")

    # Also save as raw RGB565 binary for TJC firmware
    pixels = list(result.getdata())
    rgb565_data = bytearray()
    for r, g, b in pixels:
        rgb565_data.extend(rgb_to_rgb565(r, g, b).to_bytes(2, 'little'))

    with open("extracted/composite_result.rgb565", "wb") as f:
        f.write(rgb565_data)
    print(f"Saved RGB565 to extracted/composite_result.rgb565 ({len(rgb565_data)} bytes)")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Create test image for debugging TJC compression algorithm.

Pattern:
- Even rows (0,2,4,...): 15+13+11+9+7+5+3+1+2+4+6+8+10+12+14+0
- Odd rows (1,3,5,...):   0+14+12+10+8+6+4+2+1+3+5+7+9+11+13+15

Uses 64+ equally spaced RGB565 colors.
"""

from PIL import Image
import struct
import random
import colorsys

# Image dimensions
WIDTH = 240
HEIGHT = 320
STRIPES = 16  # 16 color segments per row
PIXELS_PER_STRIPE = WIDTH // STRIPES  # 7 pixels per stripe (120/16 = 7.5)
EXTRA = WIDTH % STRIPES  # 8 extra pixels to distribute

# Generate 64+ equally distant colors in RGB565
# We need colors indexed 0-15 for the pattern, but with smooth gradient between them
NUM_BASE_COLORS = 64


def create_gradient_colors(n):
    """Create n equally spaced RGB565 colors forming a smooth gradient."""
    colors = []
    for i in range(n):
        # Simple grayscale gradient for testing
        # Map i to 0-255, then to RGB565 (5-bit red, 6-bit green, 5-bit blue)
        v = int((i * 255) // (n - 1))
        r = v >> 3  # 5-bit
        g = v >> 2  # 6-bit
        b = v >> 3  # 5-bit
        rgb565 = (r << 11) | (g << 5) | b
        colors.append(rgb565)
    return colors

def create_random_colors(n, seed=None):
    """
    Generate n random, non-repeating RGB565 colors with high contrast.
    Uses golden ratio hue spacing to maximize perceptual distance between colors,
    then shuffles the order so they aren't sequential on the color wheel.
    """
    if seed is not None:
        random.seed(seed)

    GOLDEN_RATIO = 0.618033988749895
    hue = random.random()  # Random starting point on the color wheel

    colors = []
    for _ in range(n):
        # Convert HSV -> RGB (full saturation + high value = vivid, contrasty colors)
        r_f, g_f, b_f = colorsys.hsv_to_rgb(hue % 1.0, 0.85, 0.95)

        # Convert to RGB565
        r = int(r_f * 31)   # 5-bit (0–31)
        g = int(g_f * 63)   # 6-bit (0–63)
        b = int(b_f * 31)   # 5-bit (0–31)
        rgb565 = (r << 11) | (g << 5) | b
        colors.append(rgb565)

        hue += GOLDEN_RATIO  # Step by golden ratio to maximize hue separation

    random.shuffle(colors)  # Shuffle so adjacent colors in the list aren't hue-adjacent
    return colors

# Create gradient palette
RANDOM_PALETTE = create_random_colors(NUM_BASE_COLORS)
GRADIENT_PALETTE = create_gradient_colors(NUM_BASE_COLORS)

# Map pattern indices to actual colors
# Using 16 colors from the gradient
COLOR_MAP = []
for i in range(32):
    COLOR_MAP.append(GRADIENT_PALETTE[i])

COLOR_MAP = RANDOM_PALETTE

# Pattern sequences
EVEN_PATTERN = [15, 13, 11, 9, 7, 5, 3, 1, 2, 4, 6, 8, 10, 12, 14, 0]
ODD_PATTERN = [0, 14, 12, 10, 8, 6, 4, 2, 1, 3, 5, 7, 9, 11, 13, 15]

print(f'COLOR_MAP: {len(COLOR_MAP)}')

def rgb565_to_rgb(rgb565):
    """Convert RGB565 to RGB888."""
    r = ((rgb565 >> 11) & 0x1F) << 3
    g = ((rgb565 >> 5) & 0x3F) << 2
    b = (rgb565 & 0x1F) << 3
    return (r, g, b)


def create_test_image():
    """Create test image with stripe pattern."""
    img = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = []

    for y in range(HEIGHT):
        pattern = EVEN_PATTERN if y % 2 == 0 else ODD_PATTERN
        row_pixels = []

        for color_idx, stripe in enumerate(pattern):
            rgb565 = COLOR_MAP[color_idx] if y % 2 == 0 else COLOR_MAP[-color_idx]
            rgb = rgb565_to_rgb(rgb565)

            for _ in range(pattern[stripe]):
                row_pixels.append(rgb)

        pixels.extend(row_pixels)

    img.putdata(pixels)
    return img


def save_as_tjc_compressed(img, output_path):
    """
    Save image as TJC compressed format for testing the decompressor.

    Block structure: 4 bytes control (8 nibbles) + 8 RGB565 pixels = 20 bytes
    Each nibble = repeat count for corresponding pixel.
    """
    # Convert to RGB565
    rgb_pixels = list(img.getdata())
    rgb565_pixels = []
    for r, g, b in rgb_pixels:
        r5 = r >> 3
        g6 = g >> 2
        b5 = b >> 3
        rgb565_pixels.append((r5 << 11) | (g6 << 5) | b5)

    # Compress using TJC algorithm
    # Process 8 pixels at a time with nibble repeat counts
    compressed_data = bytearray()

    # For each row, compress 8 pixels at a time
    for y in range(HEIGHT):
        row_start = y * WIDTH
        row_pixels = rgb565_pixels[row_start : row_start + WIDTH]

        # Process in chunks of 8 pixels
        for chunk_start in range(0, WIDTH, 8):
            chunk = row_pixels[chunk_start : chunk_start + 8]
            if len(chunk) < 8:
                # Pad with zeros if needed
                chunk = chunk + [0] * (8 - len(chunk))

            # For test pattern, we use nibble values that match the pattern exactly
            # Since we want each pixel repeated once, nibbles = [1,1,1,1,1,1,1,1]
            # But we want to test the algorithm, so let's encode each pixel once
            # nibble value = 1 means "repeat once" (output 2 pixels total: original + repeat)
            # nibble value = 0 means only the original pixel

            # Actually, for exact reconstruction, if we want 1 pixel, nibble should be 0
            # because nibble represents "additional repeats beyond the first pixel"
            # Let me verify: in decompress_block, we do [pixels[j]] * n
            # So if n=0, we get 1 pixel (the original). If n=1, we get 2 pixels.
            # So for 1x repeat, n=0. For 2x repeat, n=1.

            # For test: encode each pixel once (nibble=0 for all)
            nibbles = [0, 0, 0, 0, 0, 0, 0, 0]

            # But wait - the user's pattern has specific color indices
            # The nibbles are REPEAT COUNTS, not color indices
            # The color indices (15,13,11...) are the actual colors, not nibble values
            # So nibble=0 means "no repeat" = output 1 pixel

            # Control bytes: 4 bytes with 8 nibbles (2 nibbles per byte)
            ctrl = []
            for i in range(4):
                low_nibble = nibbles[i * 2]
                high_nibble = nibbles[i * 2 + 1]
                ctrl.append(low_nibble | (high_nibble << 4))

            compressed_data.extend(ctrl)

            # Add 8 RGB565 pixel values
            for p in chunk:
                compressed_data.extend(struct.pack("<H", p))

    # Write as binary file for testing
    with open(output_path, "wb") as f:
        f.write(compressed_data)

    print(f"Saved compressed data to {output_path}")
    print(f"Compressed size: {len(compressed_data)} bytes")
    print(f"Original size: {WIDTH * HEIGHT * 2} bytes")


if __name__ == "__main__":
    # Create and save test image
    img = create_test_image()
    img.save("test_pattern_120x64.png")
    print(f"Saved test image to test_pattern_120x64.png")

    # Also save compressed version for testing decompressor
    save_as_tjc_compressed(img, "test_pattern_120x64.bin")

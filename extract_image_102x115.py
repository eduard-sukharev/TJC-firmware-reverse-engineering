#!/usr/bin/env python3
"""
Extract and decompress a single 102x115 image from TJC firmware.

This script extracts image data from the Resources component and
uses the TJC decompression algorithm to decode it.
"""

import os
import struct
from tjc_decompress import decompress_and_create_image, get_resource_header_size

# Configuration
FIRMWARE_PATH = "tjc.tft"
RESOURCES_PATH = "Resources.bin"
OUTPUT_DIR = "extracted"

# Image parameters for 102x115 images
IMAGE_WIDTH = 102
IMAGE_HEIGHT = 115

# Entry size in resource table (24 bytes)
ENTRY_SIZE = 24


def find_resource_entry_by_size(resources_data, width, height):
    """
    Find resource entry by image dimensions.
    """
    num_entries = len(resources_data) // ENTRY_SIZE

    for i in range(num_entries):
        offset = i * ENTRY_SIZE

        if offset + ENTRY_SIZE > len(resources_data):
            break

        # Parse entry: magic(4) | id(4) | rel_offset(4) | w(2) | h(2) | size(4) | extra(4)
        rel_offset = struct.unpack("<I", resources_data[offset + 8 : offset + 12])[0]
        w = struct.unpack("<H", resources_data[offset + 12 : offset + 14])[0]
        h = struct.unpack("<H", resources_data[offset + 14 : offset + 16])[0]
        size = struct.unpack("<I", resources_data[offset + 16 : offset + 20])[0]

        if w == width and h == height:
            # Data is at rel_offset directly in Resources.bin
            data_offset = rel_offset

            print(f"Found {width}x{height} at entry {i}:")
            print(f"  Relative offset: 0x{rel_offset:x}")
            print(f"  Data offset: 0x{data_offset:x}")
            print(f"  Compressed size: {size} bytes")

            return (offset, data_offset, size)

    return None


def extract_resource_data(resources_data, data_offset, size):
    """
    Extract compressed data for a resource.
    """
    if data_offset + size > len(resources_data):
        raise ValueError(
            f"Data extends beyond Resources.bin: {data_offset + size} > {len(resources_data)}"
        )

    return resources_data[data_offset : data_offset + size]


def main():
    # Create output directory
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load Resources.bin
    with open(RESOURCES_PATH, "rb") as f:
        resources_data = f.read()

    print(f"Resources.bin: {len(resources_data)} bytes")

    # Find 102x115 image
    result = find_resource_entry_by_size(resources_data, IMAGE_WIDTH, IMAGE_HEIGHT)

    if result is None:
        print(f"Error: Could not find {IMAGE_WIDTH}x{IMAGE_HEIGHT} image")
        return

    entry_offset, data_offset, compressed_size = result

    # Extract compressed data
    compressed_data = extract_resource_data(
        resources_data, data_offset, compressed_size
    )
    print(f"\nExtracted {len(compressed_data)} bytes (with 20-byte header)")

    # Check compression flag in first byte of 20-byte resource header
    compression_flag = compressed_data[0]
    print(f"Compression flag: 0x{compression_flag:02X}")

    # Pass to decompress (it will strip the 20-byte header internally)
    print("Decompressing...")
    img = decompress_and_create_image(compressed_data, IMAGE_WIDTH, IMAGE_HEIGHT)

    # Save output
    output_path = os.path.join(OUTPUT_DIR, f"image_{IMAGE_WIDTH}x{IMAGE_HEIGHT}.png")
    img.save(output_path)
    print(f"\nSaved: {output_path}")

    # Verify
    print(f"Image size: {img.size[0]}x{img.size[1]}")

    # Show sample pixels
    print("\nSample pixels:")
    print(f"  Top-left: {img.getpixel((0, 0))}")
    print(f"  Top-right: {img.getpixel((IMAGE_WIDTH - 1, 0))}")
    print(f"  Bottom-left: {img.getpixel((0, IMAGE_HEIGHT - 1))}")
    print(f"  Bottom-right: {img.getpixel((IMAGE_WIDTH - 1, IMAGE_HEIGHT - 1))}")


if __name__ == "__main__":
    main()

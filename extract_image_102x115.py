#!/usr/bin/env python3
"""
Extract and decompress a single 102x115 image from TJC firmware.

This script extracts image data from the Resources component and
uses the TJC decompression algorithm to decode it.
"""

import os
import struct
from tjc_decompress import decompress_and_create_image

# Configuration
FIRMWARE_PATH = "tjc.tft"
RESOURCES_PATH = "Resources.bin"
OUTPUT_DIR = "extracted"

# Image parameters for 102x115 images
IMAGE_WIDTH = 102
IMAGE_HEIGHT = 115

# Resource table offset in Resources.bin
RESOURCE_TABLE_OFFSET = 0x38CF4 - 0x38CF4  # Relative to Resources.bin start

# Entry size in resource table (24 bytes)
ENTRY_SIZE = 24


def find_resource_entry_by_size(resources_data, width, height):
    """
    Find resource entry by image dimensions.

    Args:
        resources_data: bytes - full Resources.bin contents
        width: int - image width
        height: int - image height

    Returns:
        tuple: (entry_offset, data_offset, compressed_size) or None
    """
    # Scan resource table for matching dimensions
    # Each entry: magic2(4) | id(4) | rel_offset(4) | width(2) | height(2) | size(4) | extra(4)

    num_entries = len(resources_data) // ENTRY_SIZE

    for i in range(num_entries):
        offset = i * ENTRY_SIZE

        if offset + ENTRY_SIZE > len(resources_data):
            break

        # Parse entry (skip first 8 bytes - magic values)
        rel_offset = struct.unpack("<I", resources_data[offset + 8 : offset + 12])[0]
        w = struct.unpack("<H", resources_data[offset + 12 : offset + 14])[0]
        h = struct.unpack("<H", resources_data[offset + 14 : offset + 16])[0]
        size = struct.unpack("<I", resources_data[offset + 16 : offset + 20])[0]

        if w == width and h == height:
            # Calculate actual data offset in Resources.bin
            # Based on analysis: data_offset = rel_offset + 0x44
            # (0x26560 + 0x44 = 0x265a4)
            data_offset = rel_offset + 0x44

            print(f"Found {width}x{height} at entry {i}:")
            print(f"  Relative offset: 0x{rel_offset:x}")
            print(f"  Data offset: 0x{data_offset:x}")
            print(f"  Compressed size: {size} bytes")

            return (offset, data_offset, size)

    return None


def extract_resource_data(resources_data, data_offset, size):
    """
    Extract compressed data for a resource.

    Args:
        resources_data: bytes - Resources.bin contents
        data_offset: int - offset to compressed data
        size: int - size of compressed data

    Returns:
        bytes - compressed image data
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
    if not os.path.exists(RESOURCES_PATH):
        # Try to extract from firmware
        print(f"{RESOURCES_PATH} not found. Extracting from firmware...")

        with open(FIRMWARE_PATH, "rb") as f:
            # Read bootloader header to find resource block
            f.seek(0x010000)
            entries = []
            for i in range(12):
                entry = f.read(12)
                rel_offset, entry_size, meta = struct.unpack("<III", entry)
                entries.append((rel_offset, entry_size))
                if entry_size > 7000000:  # Resource block is ~7MB
                    resource_offset = 0x010000 + rel_offset
                    print(f"Resource block at: 0x{resource_offset:x}")
                    break

            # Find resource table start
            # Resource table is at relative offset in entry 7
            f.seek(resource_offset)
            resources_data = f.read()

        with open(RESOURCES_PATH, "wb") as f:
            f.write(resources_data)

        print(f"Saved Resources.bin: {len(resources_data)} bytes")

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
    print(f"\nExtracted {len(compressed_data)} bytes of compressed data")

    # Decompress
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

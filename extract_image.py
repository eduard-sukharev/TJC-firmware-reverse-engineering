#!/usr/bin/env python3
"""
Extract and decompress images from TJC TFT firmware.

This script parses the firmware partition table and resource mapping table
to extract image data from the Resources partition.
"""

import os
import sys
import struct
import argparse
from tjc_decompress import decompress_and_create_image, get_resource_header_size

# Default configuration
OUTPUT_DIR = "extracted"

# Image parameters for 102x115 images
IMAGE_WIDTH = 68
IMAGE_HEIGHT = 64

# Entry size in resource mapping table (24 bytes)
ENTRY_SIZE = 24

# Firmware partition table offset and entry size
PARTITION_TABLE_OFFSET = 0x010000
PARTITION_ENTRY_SIZE = 12


def parse_partition_table(firmware_data, partition_num=7, debug_fn=None):
    """
    Parse firmware partition table at 0x010000 to extract specified partition.
    Returns (partition_offset, partition_size, entries) or None if not found.
    Default partition_num=7 selects the Resources partition.
    """
    if debug_fn:
        debug_fn(f"Parsing firmware partition table at 0x{PARTITION_TABLE_OFFSET:06x}")

    if len(firmware_data) < PARTITION_TABLE_OFFSET + PARTITION_ENTRY_SIZE * 12:
        print(f"Error: Firmware too small ({len(firmware_data)} bytes)")
        return None

    entries = []
    for i in range(12):
        offset = PARTITION_TABLE_OFFSET + i * PARTITION_ENTRY_SIZE
        rel_offset = struct.unpack("<I", firmware_data[offset : offset + 4])[0]
        size = struct.unpack("<I", firmware_data[offset + 4 : offset + 8])[0]
        meta = struct.unpack("<I", firmware_data[offset + 8 : offset + 12])[0]
        entries.append((i, rel_offset, size, meta))
        if debug_fn:
            debug_fn(f"  Entry {i}: rel_offset=0x{rel_offset:x}, size={size}, meta=0x{meta:x}")

    if partition_num is not None:
        if partition_num < 0 or partition_num >= len(entries):
            print(f"Error: Invalid partition number {partition_num} (valid: 0-11)")
            return None
        entry_idx, rel_offset, size, meta = entries[partition_num]
        if size == 0:
            print(f"Warning: Partition {partition_num} is empty")
    else:
        largest_entry = max(entries, key=lambda e: e[2])
        entry_idx, rel_offset, size, meta = largest_entry

    file_offset = 0x010000 + rel_offset
    print(f"Partition entry {entry_idx}: rel_offset=0x{rel_offset:x}, size={size}, meta=0x{meta:x}")
    print(f"Partition {entry_idx} data at file offset: 0x{file_offset:x}")
    if debug_fn:
        debug_fn(f"Selected partition {entry_idx}")
        debug_fn(f"Partition {entry_idx}: file_offset=0x{file_offset:x}, size={size}")

    return (file_offset, size, entries)


def list_partition_entries(firmware_path):
    """
    List all firmware partition table entries.
    """
    with open(firmware_path, "rb") as f:
        firmware_data = f.read()

    if len(firmware_data) < PARTITION_TABLE_OFFSET + PARTITION_ENTRY_SIZE * 12:
        print(f"Error: Firmware too small ({len(firmware_data)} bytes)")
        return

    print(f"Firmware Partition Table at 0x{PARTITION_TABLE_OFFSET:06x}:")
    print(f"{'Entry':<7} {'RelOffset':<12} {'Size':<12} {'FileOffset':<12} {'Meta':<10}")
    print("-" * 55)

    for i in range(12):
        offset = PARTITION_TABLE_OFFSET + i * PARTITION_ENTRY_SIZE
        rel_offset = struct.unpack("<I", firmware_data[offset : offset + 4])[0]
        size = struct.unpack("<I", firmware_data[offset + 4 : offset + 8])[0]
        meta = struct.unpack("<I", firmware_data[offset + 8 : offset + 12])[0]
        file_offset = PARTITION_TABLE_OFFSET + rel_offset
        print(f"{i:<7} 0x{rel_offset:<10x} {size:<12} 0x{file_offset:<10x} 0x{meta:<8x}")


def load_partition_data(firmware_path, partition_num=7, debug_fn=None):
    """
    Load data from specified partition in firmware file.
    Default partition_num=7 selects the Resources partition.
    """
    with open(firmware_path, "rb") as f:
        firmware_data = f.read()

    result = parse_partition_table(firmware_data, partition_num, debug_fn)
    if result is None:
        return None

    file_offset, size, entries = result
    partition_data = firmware_data[file_offset : file_offset + size]
    if debug_fn:
        debug_fn(f"Extracted partition {partition_num}: {len(partition_data)} bytes")
    return partition_data


def main():
    parser = argparse.ArgumentParser(
        description="Extract and decompress an image from TJC firmware"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-f", "--firmware",
        help="Path to firmware file (partition table will be parsed)"
    )
    group.add_argument(
        "-r", "--resources",
        help="Path to Resources.bin file (parsed directly)"
    )


def find_resource_entry_by_id(partition_data, lookup_id):
    """
    Find resource entry by resource ID.
    """
    num_entries = len(partition_data) // ENTRY_SIZE

    for i in range(num_entries):
        offset = i * ENTRY_SIZE

        if offset + ENTRY_SIZE > len(partition_data):
            break

        # Parse entry: magic(4) | id(4) | rel_offset(4) | w(2) | h(2) | size(4) | extra(4)
        res_id = struct.unpack("<I", partition_data[offset + 4 : offset + 8])[0]
        rel_offset = struct.unpack("<I", partition_data[offset + 8 : offset + 12])[0]
        w = struct.unpack("<H", partition_data[offset + 12 : offset + 14])[0]
        h = struct.unpack("<H", partition_data[offset + 14 : offset + 16])[0]
        size = struct.unpack("<I", partition_data[offset + 16 : offset + 20])[0]

        if res_id == lookup_id:
            data_offset = rel_offset

            print(f"Found ID {lookup_id} at entry {i}:")
            print(f"  Dimensions: {w}x{h}")
            print(f"  Relative offset: 0x{rel_offset:x}")
            print(f"  Data offset: 0x{data_offset:x}")
            print(f"  Compressed size: {size} bytes")

            return (offset, data_offset, size, w, h)

    return None


def find_resource_entry_by_size(partition_data, width, height):
    """
    Find resource entry by image dimensions.
    """
    num_entries = len(partition_data) // ENTRY_SIZE

    for i in range(num_entries):
        offset = i * ENTRY_SIZE

        if offset + ENTRY_SIZE > len(partition_data):
            break

        # Parse entry: magic(4) | id(4) | rel_offset(4) | w(2) | h(2) | size(4) | extra(4)
        rel_offset = struct.unpack("<I", partition_data[offset + 8 : offset + 12])[0]
        w = struct.unpack("<H", partition_data[offset + 12 : offset + 14])[0]
        h = struct.unpack("<H", partition_data[offset + 14 : offset + 16])[0]
        size = struct.unpack("<I", partition_data[offset + 16 : offset + 20])[0]

        if w == width and h == height:
            data_offset = rel_offset

            print(f"Found {width}x{height} at entry {i}:")
            print(f"  Relative offset: 0x{rel_offset:x}")
            print(f"  Data offset: 0x{data_offset:x}")
            print(f"  Compressed size: {size} bytes")

            return (offset, data_offset, size, w, h)

    return None


def extract_resource_data(partition_data, data_offset, size):
    """
    Extract compressed data for a resource.
    """
    if data_offset + size > len(partition_data):
        raise ValueError(
            f"Data extends beyond Resources.bin: {data_offset + size} > {len(partition_data)}"
        )

    return partition_data[data_offset : data_offset + size]


def enumerate_all_resources(partition_data):
    """
    Enumerate all resources in the Resource Mapping Table.
    Returns list of (entry_idx, res_id, rel_offset, width, height, size)
    """
    resources = []
    num_entries = len(partition_data) // ENTRY_SIZE

    for i in range(num_entries):
        offset = i * ENTRY_SIZE

        if offset + ENTRY_SIZE > len(partition_data):
            break

        # Parse entry: magic(4) | id(4) | rel_offset(4) | w(2) | h(2) | size(4) | extra(4)
        magic = struct.unpack("<I", partition_data[offset : offset + 4])[0]
        res_id = struct.unpack("<I", partition_data[offset + 4 : offset + 8])[0]
        rel_offset = struct.unpack("<I", partition_data[offset + 8 : offset + 12])[0]
        w = struct.unpack("<H", partition_data[offset + 12 : offset + 14])[0]
        h = struct.unpack("<H", partition_data[offset + 14 : offset + 16])[0]
        size = struct.unpack("<I", partition_data[offset + 16 : offset + 20])[0]

        # Filter: reasonable ID, dimensions (max 4000x4000) and positive size
        if 0 < res_id < 100000 and 0 < w <= 4000 and 0 < h <= 4000 and 0 < size < 10_000_000:
            # Filter: offset must be within bounds
            if rel_offset + size <= len(partition_data):
                resources.append((i, res_id, rel_offset, w, h, size))

    return resources


def main():
    parser = argparse.ArgumentParser(
        description="Extract and decompress an image from TJC firmware"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "-f", "--firmware",
        help="Path to firmware file (partition table will be parsed)"
    )
    group.add_argument(
        "-r", "--resources",
        help="Path to Resources.bin file (parsed directly)"
    )
    parser.add_argument(
        "-o", "--output",
        default=OUTPUT_DIR,
        help=f"Output directory (default: {OUTPUT_DIR})"
    )
    parser.add_argument(
        "-w", "--width",
        type=int,
        default=IMAGE_WIDTH,
        help=f"Image width (default: {IMAGE_WIDTH})"
    )
    parser.add_argument(
        "-H", "--height",
        type=int,
        default=IMAGE_HEIGHT,
        help=f"Image height (default: {IMAGE_HEIGHT})"
    )
    parser.add_argument(
        "-i", "--id",
        type=int,
        default=None,
        help="Extract image by resource ID (overrides width/height lookup)"
    )
    parser.add_argument(
        "-l", "--list",
        action="store_true",
        help="List all resources in the Resource Mapping Table"
    )
    parser.add_argument(
        "-b", "--partition",
        action="store_true",
        help="List firmware partition table (requires -f/--firmware)"
    )
    parser.add_argument(
        "-p", "--partition-num",
        type=int,
        default=7,
        help="Partition number to use (0-11, default: 7 = Resources)"
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug output"
    )

    args = parser.parse_args()

    # Verbose logging helper
    def debug(msg):
        if args.verbose:
            print(f"[DEBUG] {msg}")

    output_dir = args.output
    image_width = args.width
    image_height = args.height
    resource_id = args.id

    debug(f"Output directory: {output_dir}")
    debug(f"Search criteria: ID={resource_id}, size={image_width}x{image_height}")

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # List partition table mode
    if args.partition:
        if not args.firmware:
            print("Error: -b/--partition requires -f/--firmware")
            return
        debug(f"Listing firmware partition table from: {args.firmware}")
        list_partition_entries(args.firmware)
        return

    # Load data from specified partition in firmware
    if args.firmware:
        partition = args.partition_num
        debug(f"Loading partition {partition} from firmware: {args.firmware}")
        partition_data = load_partition_data(args.firmware, partition, debug)
        if partition_data is None:
            print("Error: Failed to parse firmware")
            return
    else:
        debug(f"Loading from resources file: {args.resources}")
        with open(args.resources, "rb") as f:
            partition_data = f.read()

    print(f"Partition data: {len(partition_data)} bytes")
    output_dir = args.output
    image_width = args.width
    image_height = args.height
    resource_id = args.id

    # Create output directory
    os.makedirs(output_dir, exist_ok=True)

    # List mode
    if args.list:
        debug(f"Enumerating resources (filter: w<=4000, h<=4000, size<10MB, ID<100000)")
        resources = enumerate_all_resources(partition_data)
        debug(f"Found {len(resources)} valid resource entries")
        print(f"\nFound {len(resources)} resources:\n")
        print(f"{'Entry':<6} {'ID':<6} {'Width':<6} {'Height':<7} {'Size':<10} {'Offset':<10}")
        print("-" * 50)
        for entry_idx, res_id, rel_offset, w, h, size in resources:
            print(f"{entry_idx:<6} {res_id:<6} {w:<6} {h:<7} {size:<10} 0x{rel_offset:<8x}")
        return

    # Find image by ID or dimensions
    if resource_id is not None:
        debug(f"Searching for resource ID: {resource_id}")
        result = find_resource_entry_by_id(partition_data, resource_id)
        if result is None:
            print(f"Error: Could not find image with ID {resource_id}")
            return
    else:
        debug(f"Searching for resource by size: {image_width}x{image_height}")
        result = find_resource_entry_by_size(partition_data, image_width, image_height)
        if result is None:
            print(f"Error: Could not find {image_width}x{image_height} image")
            return

    entry_offset, data_offset, compressed_size, width, height = result
    debug(f"Selected entry at table offset 0x{entry_offset:x}")
    debug(f"Data at relative offset 0x{data_offset:x}, compressed size: {compressed_size} bytes")
    debug(f"Decompressing as {width}x{height}")

    # Extract compressed data
    compressed_data = extract_resource_data(
        partition_data, data_offset, compressed_size
    )
    print(f"\nExtracted {len(compressed_data)} bytes (with 20-byte header)")

    # Check compression flag in first byte of 20-byte resource header
    compression_flag = compressed_data[0]
    print(f"Compression flag: 0x{compression_flag:02X}")

    # Pass to decompress (it will strip the 20-byte header internally)
    print("Decompressing...")
    img = decompress_and_create_image(compressed_data, width, height)

    # Save output
    output_path = os.path.join(output_dir, f"image_{width}x{height}_id{resource_id if resource_id is not None else 'unknown'}.png")
    img.save(output_path)
    print(f"\nSaved: {output_path}")

    # Verify
    print(f"Image size: {img.size[0]}x{img.size[1]}")

    # Show sample pixels
    print("\nSample pixels:")
    print(f"  Top-left: {img.getpixel((0, 0))}")
    print(f"  Top-right: {img.getpixel((img.size[0] - 1, 0))}")
    print(f"  Bottom-left: {img.getpixel((0, img.size[1] - 1))}")
    print(f"  Bottom-right: {img.getpixel((img.size[0] - 1, img.size[1] - 1))}")


if __name__ == "__main__":
    main()

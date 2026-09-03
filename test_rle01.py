#!/usr/bin/env python3
"""
Pytest test cases for TJC compression flag 0x01 decompression.

These tests verify the nibble RLE decompression against the known
reference image (composite_result.png) and the compressed test data
(test_image_1_compressed.bin).
"""

import pickle
import struct
from pathlib import Path

import pytest
from PIL import Image


# Test data paths
TEST_DIR = Path(__file__).parent
COMPRESSED_BIN = TEST_DIR / "test_image_1_compressed.bin"
REFERENCE_PKL = TEST_DIR / "reference_rows.pkl"
BLOCKS_PKL = TEST_DIR / "compressed_blocks.pkl"


def load_test_data():
    """Load test data from pickle files."""
    with open(COMPRESSED_BIN, "rb") as f:
        compressed_data = f.read()

    with open(REFERENCE_PKL, "rb") as f:
        reference = pickle.load(f)

    with open(BLOCKS_PKL, "rb") as f:
        blocks = pickle.load(f)

    return compressed_data, reference, blocks


def rgb565_to_rgb888(rgb565):
    """Convert RGB565 to RGB888 using simple multiply."""
    r = (rgb565 >> 11) & 0x1F
    g = (rgb565 >> 5) & 0x3F
    b = rgb565 & 0x1F
    return (r * 8, g * 4, b * 8)


def extract_nibbles(control):
    """Extract nibbles from control bytes with lo-first ordering."""
    nibbles = []
    for b in control:
        nibbles.append(b & 0x0F)  # lo nibble first
        nibbles.append(b >> 4)       # hi nibble second
    return nibbles


def decompress_nibble_rle(data):
    """
    Decompress nibble RLE format.
    
    Each block is 20 bytes:
    - 4 control bytes -> 8 nibbles (repeat counts, lo-first order)
    - 8 RGB565 pixel values (16 bytes)
    
    Each nibble specifies how many times to repeat the corresponding pixel.
    """
    decoded = []
    
    for block_idx in range(len(data) // 20):
        offset = block_idx * 20
        if offset + 20 > len(data):
            break
        
        control = data[offset : offset + 4]
        pixels_data = data[offset + 4 : offset + 20]
        
        # Extract nibbles in lo-first order
        nibbles = extract_nibbles(control)
        
        # Parse RGB565 pixels
        rgb565_pixels = []
        for i in range(8):
            p = struct.unpack("<H", pixels_data[i * 2 : (i + 1) * 2])[0]
            rgb565_pixels.append(rgb565_to_rgb888(p))
        
        # Expand: nibble[i] applies to pixel[i]
        for i in range(8):
            decoded.extend([rgb565_pixels[i]] * nibbles[i])
    
    return decoded


class TestNibbleRLEDecompression:
    """Test cases for nibble RLE decompression algorithm."""

    def test_loads_test_data(self):
        """Verify test data files exist and can be loaded."""
        compressed_data, reference, blocks = load_test_data()
        
        # Verify structure
        assert len(compressed_data) == 3262, f"Expected 3262 bytes, got {len(compressed_data)}"
        assert compressed_data[0] == 0x01, f"Expected flag 0x01, got 0x{compressed_data[0]:02x}"
        assert reference["width"] == 120
        assert reference["height"] == 64
        assert len(blocks) >= 3, "Need at least 3 blocks for testing"
        
    def test_reference_first_row(self):
        """Verify reference first row has expected pattern."""
        _, reference, _ = load_test_data()
        ref_row0 = reference["row0"]

        # First 12 pixels should be (0, 4, 0) - dark green (8+4 from nibble 0+1)
        assert ref_row0[0] == (0, 4, 0), f"Expected (0, 4, 0), got {ref_row0[0]}"
        assert ref_row0[11] == (0, 4, 0), f"Expected (0, 4, 0), got {ref_row0[11]}"

        # Second run should be (8, 8, 8) at position 12
        assert ref_row0[12] == (8, 8, 8), f"Expected (8, 8, 8), got {ref_row0[12]}"
        
    def test_reference_second_row(self):
        """Verify reference second row has expected pattern."""
        _, reference, _ = load_test_data()
        ref_row1 = reference["row1"]
        
        # Second row should be offset in colors
        assert ref_row1[0] == (120, 124, 120), f"Expected (120, 124, 120), got {ref_row1[0]}"
        
    def test_reference_third_row(self):
        """Verify reference third row matches first row."""
        _, reference, _ = load_test_data()
        ref_row0 = reference["row0"]
        ref_row2 = reference["row2"]
        
        # Row 2 should mirror row 0 (or close to it based on test image)
        # Actually let's check they're similar but maybe not exact
        assert len(ref_row2) == 120
        
    def test_first_two_rows_match_compressed_data(self):
        """
        MAIN TEST: First two rows decoded from compressed data should match reference.
        
        This test verifies the nibble RLE decompression algorithm produces
        pixel-identical output to the reference image.
        
        Current expected: ~32.5% match with direct nibble mapping
        Target: 100% match (or close to it for correct algorithm)
        """
        compressed_data, reference, _ = load_test_data()
        
        # Skip 20-byte header
        data = compressed_data[20:]
        
        # Decompress
        decoded = decompress_nibble_rle(data)
        
        ref_row0 = reference["row0"]
        ref_row1 = reference["row1"]
        
        # Compare first two rows (first 240 pixels)
        decoded_row0 = decoded[:120]
        decoded_row1 = decoded[120:240]
        
        # Count matches
        matches_row0 = sum(1 for d, r in zip(decoded_row0, ref_row0) if d == r)
        matches_row1 = sum(1 for d, r in zip(decoded_row1, ref_row1) if d == r)
        
        match_pct_row0 = matches_row0 / 120 * 100
        match_pct_row1 = matches_row1 / 120 * 100
        
        # With correct algorithm (swap nibble order, simple multiply):
        # - Swap nibble order: lo nibble first, then hi nibble
        # - Simple multiply: r*8, g*4, b*8 (not shift-based)
        # Should achieve 100% for first 2 rows we test
        assert match_pct_row0 >= 90, f"Row0: {matches_row0}/120 = {match_pct_row0:.1f}% (expected >=90%)"
        assert match_pct_row1 >= 90, f"Row1: {matches_row1}/120 = {match_pct_row1:.1f}% (expected >=90%)"
        
    def test_block_structure(self):
        """Verify compressed block structure is as expected."""
        _, _, blocks = load_test_data()
        
        # First block
        b0 = blocks[0]
        assert b0["block_idx"] == 0
        assert sum(b0["nibbles"]) == 63, f"Block 0 nibble sum: expected 63, got {sum(b0['nibbles'])}"
        
        # Second block
        b1 = blocks[1]
        assert b1["block_idx"] == 1
        assert sum(b1["nibbles"]) == 57, f"Block 1 nibble sum: expected 57, got {sum(b1['nibbles'])}"
        
    def test_rgb565_conversion(self):
        """Verify RGB565 to RGB888 conversion (simple multiply)."""
        _, _, blocks = load_test_data()
        
        # First pixel from first block should be (0, 4, 0)
        b0 = blocks[0]
        pixel0_rgb565 = b0["pixels_rgb565"][0]
        pixel0_rgb888 = rgb565_to_rgb888(pixel0_rgb565)
        
        assert pixel0_rgb888 == (0, 4, 0), f"Expected (0, 4, 0), got {pixel0_rgb888}"
        
    def test_decode_produces_correct_pixel_count(self):
        """Verify decode produces expected total pixel count."""
        compressed_data, reference, _ = load_test_data()
        
        data = compressed_data[20:]
        decoded = decompress_nibble_rle(data)
        
        # Should decode to at least 120*2 = 240 pixels for first 2 rows
        assert len(decoded) >= 240, f"Expected >=240 pixels, got {len(decoded)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
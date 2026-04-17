#!/usr/bin/env python3
"""
Unit tests for TJC decompression module.
"""

import unittest
from tjc_decompress import control_to_nibbles, decompress_block
from collections import Counter

"""

# Byte sequence `FE FF FF FF E4 10 E4 10 E4 10 E4 10 E4 10 E4 10 E4 10 E4 10` has to be decompressed into `10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4`.

# Byte sequence `FE 1B 2F 11 E4 10 E4 10 E4 10 C3 10 A3 10 A3 10 C3 10 E3 10` decompresses into `10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10E4 10C3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10A3 10C3 10E3`.

# Byte sequence `1F 11 11 11 9B 45 6B 1A C8 19 C8 11 96 34 39 3D C3 10 04 11` decompresses into `459B 1A6B 19C8 11C8 3496 3D39 10C3 1104 1104 1104 1104 1104 1104 1104 1104 1104 1104 1104 1104 1104 1104 1104`. Make these tests pass.

"""
class TestControlToNibbles(unittest.TestCase):
    """Test control byte to nibble conversion."""

    def test_1f_11_11_11(self):
        ctrl = bytes.fromhex("1f111111")
        nibbles = control_to_nibbles(ctrl)
        self.assertEqual(nibbles, [1, 1, 1, 1, 1, 1, 1, 15])


class TestDecompressBlock(unittest.TestCase):
    """Test block decompression."""

    def test_fe_ffffff_fill(self):
        block = bytes.fromhex("feffffffe410e410e410e410e410e410e410e410e410")
        pixels = decompress_block(block)
        self.assertEqual(len(pixels), 119)
        self.assertEqual(pixels[0], 0x10E4)
        self.assertTrue(all(p == 0x10E4 for p in pixels))

    def test_fe_1b_2f_11_mixed(self):
        block = bytes.fromhex("fe1b2f11e410e410e410c310a310a310c310e310")
        pixels = decompress_block(block)
        self.assertEqual(len(pixels), 60)
        counts = Counter(pixels)
        self.assertEqual(counts[0x10E4], 40)
        self.assertEqual(counts[0x10C3], 2)
        self.assertEqual(counts[0x10A3], 17)
        self.assertEqual(counts[0x10E3], 1)

    def test_1f_11_11_11_mixed(self):
        block = bytes.fromhex("1f1111119b456b1ac819c8119634393dc3100411")
        pixels = decompress_block(block)
        self.assertEqual(len(pixels), 22)

        counts = Counter(pixels)
        self.assertEqual(counts[0x459B], 1)
        self.assertEqual(counts[0x1A6B], 1)
        self.assertEqual(counts[0x19C8], 1)
        self.assertEqual(counts[0x11C8], 1)
        self.assertEqual(counts[0x3496], 1)
        self.assertEqual(counts[0x3D39], 1)
        self.assertEqual(counts[0x10C3], 1)
        self.assertEqual(counts[0x1104], 15)

if __name__ == "__main__":
    unittest.main()

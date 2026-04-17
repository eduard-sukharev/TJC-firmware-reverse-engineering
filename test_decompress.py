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


class TestDecompressBlock(unittest.TestCase):
    def test_case_1(self):
        input_data = bytes(
            [
                0xFE,
                0xFF,
                0xFF,
                0xFF,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xE4,
                0x10,
            ]
        )
        expected = [0x10E4] * 51
        result = decompress_block(input_data)
        self.assertEqual(result, expected)

    def test_case_2(self):
        input_data = bytes(
            [
                0xFE,
                0x1B,
                0x2F,
                0x11,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xE4,
                0x10,
                0xC3,
                0x10,
                0xA3,
                0x10,
                0xA3,
                0x10,
                0xC3,
                0x10,
                0xE3,
                0x10,
            ]
        )
        expected = [0x10E4] * 21 + [0x10A3] * 14 + [0x10C3] + [0x10E3]
        result = decompress_block(input_data)
        self.assertEqual(result, expected)

    def test_case_3(self):
        input_data = bytes(
            [
                0x1F,
                0x11,
                0x11,
                0x11,
                0x9B,
                0x45,
                0x6B,
                0x1A,
                0xC8,
                0x19,
                0xC8,
                0x11,
                0x96,
                0x34,
                0x39,
                0x3D,
                0xC3,
                0x10,
                0x04,
                0x11,
            ]
        )
        expected = [0x459B, 0x1A6B, 0x19C8, 0x11C8, 0x3496, 0x3D39, 0x10C3, 0x1104] + [
            0x1104
        ] * 14
        result = decompress_block(input_data)
        self.assertEqual(result, expected)


if __name__ == "__main__":
    unittest.main()

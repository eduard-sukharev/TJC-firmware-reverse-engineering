#!/usr/bin/env python3
"""
Tests for the encoder (tjc_compress) and the firmware integrity values
(tjc_checksums).

The encoder is validated against the stock firmware in the strongest available
way: re-encoding every compressed resource must reproduce the original
encoder's output length and *every control byte*. Only the filler in unused
(count 0) pixel slots is allowed to differ, since the decoder never reads it.
"""

import struct
from pathlib import Path

import pytest

import tjc_checksums
from tjc_compress import MAX_FIRST_RUN, build_resource, compress_pixels
from tjc_decompress import (
    BLOCK_SIZE,
    LITERAL_CONTROL,
    RESOURCE_HEADER_SIZE,
    decompress_image_data,
    payload_length,
)

HERE = Path(__file__).parent
RESOURCES = HERE / "Resources.bin"
FIRMWARE = HERE / "tjc.tft"
ENTRY_SIZE = 24
MAGICS = (0x0301640A, 0x0301600A)


def compressed_entries(data):
    for i in range(len(data) // ENTRY_SIZE):
        o = i * ENTRY_SIZE
        magic, rid, rel, wh, alloc, _x = struct.unpack("<IIIIII", data[o : o + 24])
        if magic not in MAGICS:
            continue
        w, h = wh & 0xFFFF, (wh >> 16) & 0xFFFF
        if w == 0 or h == 0 or alloc == 0 or rel + alloc > len(data):
            continue
        if data[rel] != 0x04:
            continue
        yield rid, rel, w, h, alloc


@pytest.fixture(scope="module")
def resources():
    if not RESOURCES.exists():
        pytest.skip("Resources.bin not present")
    return RESOURCES.read_bytes()


@pytest.fixture(scope="module")
def firmware():
    if not FIRMWARE.exists():
        pytest.skip("tjc.tft not present")
    return FIRMWARE.read_bytes()


def test_encoder_reproduces_original_control_bytes(resources):
    """Length and every control byte must match the stock encoder exactly."""
    bad_len, bad_ctrl, total = [], [], 0
    for rid, rel, w, h, alloc in compressed_entries(resources):
        orig = resources[rel : rel + alloc]
        used = payload_length(orig)
        orig_payload = orig[RESOURCE_HEADER_SIZE : RESOURCE_HEADER_SIZE + used]
        pixels = decompress_image_data(orig)[: w * h]
        new_payload = compress_pixels(pixels, w, h)
        total += 1
        if len(new_payload) != len(orig_payload):
            bad_len.append(rid)
            continue
        for b in range(len(orig_payload) // BLOCK_SIZE):
            s = b * BLOCK_SIZE
            if orig_payload[s : s + 4] != new_payload[s : s + 4]:
                bad_ctrl.append(rid)
                break
    assert not bad_len, f"{len(bad_len)}/{total} wrong length: {bad_len[:5]}"
    assert not bad_ctrl, f"{len(bad_ctrl)}/{total} wrong control bytes: {bad_ctrl[:5]}"


def test_encoder_round_trips_pixels(resources):
    bad = []
    for rid, rel, w, h, alloc in compressed_entries(resources):
        pixels = decompress_image_data(resources[rel : rel + alloc])[: w * h]
        if decompress_image_data(build_resource(pixels, w, h))[: w * h] != pixels:
            bad.append(rid)
    assert not bad, f"round-trip failed for {len(bad)} resources: {bad[:5]}"


def test_encoder_output_fits_original_allocation(resources):
    bad = []
    for rid, rel, w, h, alloc in compressed_entries(resources):
        pixels = decompress_image_data(resources[rel : rel + alloc])[: w * h]
        if len(build_resource(pixels, w, h)) > alloc:
            bad.append(rid)
    assert not bad, f"{len(bad)} resources grew beyond their allocation: {bad[:5]}"


def test_encoder_never_emits_literal_signature_by_accident():
    """First run count is capped at 14 so 1F 11 11 11 can only be deliberate."""
    # 8 runs that would each want to be long; first must clamp to 14.
    pixels = [1] * 15 + [2] * 15 + [3] * 15
    payload = compress_pixels(pixels, len(pixels), 1)
    for b in range(len(payload) // BLOCK_SIZE):
        ctrl = payload[b * BLOCK_SIZE : b * BLOCK_SIZE + 4]
        first = ctrl[0] & 0x0F
        assert first <= MAX_FIRST_RUN, f"first run {first} exceeds cap"


def test_literal_block_used_for_eight_singles():
    pixels = list(range(1, 9))
    payload = compress_pixels(pixels, 8, 1)
    assert payload[:4] == LITERAL_CONTROL


def test_stock_firmware_passes_all_checksums(firmware):
    declared = struct.unpack("<I", firmware[0x3C:0x40])[0]
    assert declared == len(firmware), "header length field mismatch"
    for name, (ok, got, want) in tjc_checksums.verify(firmware).items():
        assert ok, f"{name}: stored 0x{got:08x} != computed 0x{want:08x}"


def test_reseal_is_a_noop_on_a_valid_file(firmware):
    assert tjc_checksums.reseal(firmware) == firmware


def test_reseal_repairs_a_modified_resource(firmware):
    buf = bytearray(firmware)
    # flip a byte deep inside the resources section
    buf[0x400000] ^= 0xFF
    broken = bytes(buf)
    assert not all(ok for ok, _g, _w in tjc_checksums.verify(broken).values())
    fixed = tjc_checksums.reseal(broken)
    assert all(ok for ok, _g, _w in tjc_checksums.verify(fixed).values())
    assert len(fixed) == len(firmware)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

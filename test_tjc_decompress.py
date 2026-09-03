#!/usr/bin/env python3
"""
Validation of the TJC image decoder against the whole stock firmware.

The decoder is checked with three independent invariants that a correct
implementation must satisfy for every compressed resource:

1. the decoded pixel count equals width * height
2. every 4-row stripe's run counts sum exactly (the encoder aligns each group
   of 4 output rows to a block boundary)
3. the number of payload bytes consumed equals the length recorded in the
   resource header at bytes 4-7

Any error in the block layout, the nibble order, the literal-block rule or the
run-length semantics breaks at least one of these on a large fraction of the
1994 compressed resources, so together they pin the format down tightly.
"""

import struct
from pathlib import Path

import pytest

from tjc_decompress import (
    BLOCK_SIZE,
    LITERAL_CONTROL,
    RESOURCE_HEADER_SIZE,
    control_to_counts,
    decompress_image_data,
    payload_length,
)

RESOURCES = Path(__file__).parent / "Resources.bin"
ENTRY_SIZE = 24
MAGICS = (0x0301640A, 0x0301600A)


def iter_resources(data):
    """Yield (resource_id, offset, width, height, size) for every table entry."""
    for i in range(len(data) // ENTRY_SIZE):
        o = i * ENTRY_SIZE
        magic, rid, rel, wh, size, _extra = struct.unpack("<IIIIII", data[o : o + 24])
        if magic not in MAGICS:
            continue
        w, h = wh & 0xFFFF, (wh >> 16) & 0xFFFF
        if w == 0 or h == 0 or size == 0 or rel + size > len(data):
            continue
        yield rid, rel, w, h, size


@pytest.fixture(scope="module")
def resources():
    if not RESOURCES.exists():
        pytest.skip(f"{RESOURCES.name} not present")
    data = RESOURCES.read_bytes()
    entries = [e for e in iter_resources(data) if data[e[1]] == 0x04]
    if not entries:
        pytest.skip("no compressed resources found")
    return data, entries


def block_output_size(ctrl):
    """Number of pixels a block with this control field emits."""
    if ctrl == LITERAL_CONTROL:
        return 8
    return sum(control_to_counts(ctrl))


def test_every_resource_decodes_to_exact_pixel_count(resources):
    data, entries = resources
    bad = []
    for rid, rel, w, h, size in entries:
        pixels = decompress_image_data(data[rel : rel + size])
        if len(pixels) != w * h:
            bad.append((rid, w, h, len(pixels)))
    assert not bad, f"{len(bad)} of {len(entries)} resources decoded to a wrong size: {bad[:5]}"


def test_four_row_stripes_align_to_block_boundaries(resources):
    """Each group of 4 output rows must end exactly on a 20-byte block boundary."""
    data, entries = resources
    bad = []
    for rid, rel, w, h, size in entries:
        res = data[rel : rel + size]
        payload = res[RESOURCE_HEADER_SIZE : RESOURCE_HEADER_SIZE + payload_length(res)]
        nblocks = len(payload) // BLOCK_SIZE
        unit, produced, bi, ok = 4 * w, 0, 0, True
        while bi < nblocks and produced < w * h:
            want, acc = min(unit, w * h - produced), 0
            while bi < nblocks and acc < want:
                acc += block_output_size(payload[bi * BLOCK_SIZE : bi * BLOCK_SIZE + 4])
                bi += 1
            if acc != want:
                ok = False
                break
            produced += want
        if not ok:
            bad.append((rid, w, h))
    assert not bad, f"{len(bad)} of {len(entries)} resources broke stripe alignment: {bad[:5]}"


def test_consumed_length_matches_header_field(resources):
    """Decoding must consume exactly the byte count recorded in the header."""
    data, entries = resources
    bad = []
    for rid, rel, w, h, size in entries:
        res = data[rel : rel + size]
        n = payload_length(res)
        payload = res[RESOURCE_HEADER_SIZE : RESOURCE_HEADER_SIZE + n]
        nblocks = len(payload) // BLOCK_SIZE
        total = sum(
            block_output_size(payload[i * BLOCK_SIZE : i * BLOCK_SIZE + 4])
            for i in range(nblocks)
        )
        if total != w * h or nblocks * BLOCK_SIZE != n:
            bad.append((rid, total, w * h, nblocks * BLOCK_SIZE, n))
    assert not bad, f"{len(bad)} of {len(entries)} resources mismatched header length: {bad[:5]}"


def test_literal_block_emits_eight_pixels():
    """The 1F 11 11 11 signature means 8 literal pixels, not 22 RLE pixels."""
    from tjc_decompress import decompress_block

    block = LITERAL_CONTROL + bytes(range(16))
    assert len(decompress_block(block)) == 8
    # A naive RLE reading of that control field would give 22.
    assert sum(control_to_counts(LITERAL_CONTROL)) == 22


def test_nibble_order_is_low_first():
    assert control_to_counts(b"\x21\x00\x00\x00")[:2] == [1, 2]


def test_placeholder_census():
    """Unassigned slots are solid-colour dummies, cleanly separable from real art."""
    if not RESOURCES.exists():
        pytest.skip(f"{RESOURCES.name} not present")
    data = RESOURCES.read_bytes()
    solid, real, dims = 0, 0, set()
    for _rid, rel, w, h, size in iter_resources(data):
        pixels = decompress_image_data(data[rel : rel + size])[: w * h]
        if len(set(pixels)) == 1:
            solid += 1
            dims.add((w, h))
        else:
            real += 1
    # every placeholder is the same 4x2 white dummy, and nothing else is solid
    assert dims == {(4, 2)}, f"unexpected solid-colour dimensions: {dims}"
    assert solid == 570, solid
    assert real == 2058, real


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

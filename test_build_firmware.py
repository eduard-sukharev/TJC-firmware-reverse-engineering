#!/usr/bin/env python3
"""
Tests for build_firmware.py - asset discovery, naming rules and a real
end-to-end build against the stock firmware.
"""

import struct
import subprocess
import sys
from pathlib import Path

import pytest

from build_firmware import encode_for_slot, resource_index, scan_assets
from tjc_checksums import verify
from tjc_decompress import decompress_image_data

HERE = Path(__file__).parent
FIRMWARE = HERE / "tjc.tft"


@pytest.fixture(scope="module")
def firmware():
    if not FIRMWARE.exists():
        pytest.skip("tjc.tft not present")
    return FIRMWARE.read_bytes()


def _png(path, size=(4, 4), colour=(10, 20, 30)):
    from PIL import Image

    Image.new("RGB", size, colour).save(path)


def test_asset_naming_variants(tmp_path):
    _png(tmp_path / "id0000_240x320.png")
    _png(tmp_path / "id0007.png")
    _png(tmp_path / "42.png")
    assets, ignored, duplicates = scan_assets(tmp_path)
    assert set(assets) == {0, 7, 42}
    assert assets[0][1] == (240, 320)      # dimensions parsed from the name
    assert assets[7][1] is None            # no dimensions in the name
    assert not ignored and not duplicates


def test_non_assets_are_ignored_not_guessed(tmp_path):
    (tmp_path / "notes.txt").write_text("hi")
    _png(tmp_path / "kitten.png")
    (tmp_path / "subdir").mkdir()
    assets, ignored, _dups = scan_assets(tmp_path)
    assert assets == {}
    reasons = {p.name: why for p, why in ignored}
    assert "notes.txt" in reasons and "kitten.png" in reasons and "subdir" in reasons


def test_duplicate_ids_are_reported(tmp_path):
    _png(tmp_path / "id0005.png")
    _png(tmp_path / "5.png")
    _assets, _ignored, duplicates = scan_assets(tmp_path)
    assert duplicates and duplicates[0][0] == 5


def test_encode_for_slot_rejects_when_over_budget():
    pixels = [(i * 2654435761) & 0xFFFF for i in range(64 * 64)]  # noisy
    blob, how = encode_for_slot(pixels, 64, 64, alloc=100)
    assert blob is None and "only 100 available" in how


def test_encode_for_slot_fits_flat_image():
    pixels = [0x1234] * (32 * 32)
    blob, how = encode_for_slot(pixels, 32, 32, alloc=8192)
    assert blob is not None and how == "compressed"


def test_end_to_end_build_patches_only_requested_asset(tmp_path, firmware):
    from PIL import Image

    index = resource_index(firmware)
    # pick a small compressed resource so the test stays quick
    rid, (off, w, h, alloc) = next(
        (r, v) for r, v in sorted(index.items())
        if v[1] * v[2] <= 400 and firmware[v[0]] == 0x04
    )

    assets = tmp_path / "assets"
    assets.mkdir()
    _png(assets / f"id{rid:04d}_{w}x{h}.png", size=(w, h), colour=(255, 0, 255))
    out = tmp_path / "out.tft"

    rc = subprocess.call(
        [sys.executable, str(HERE / "build_firmware.py"),
         "-a", str(assets), "-f", str(FIRMWARE), "-o", str(out)],
        cwd=str(HERE),
    )
    assert rc == 0
    patched = out.read_bytes()

    assert len(patched) == len(firmware)
    assert all(ok for ok, _g, _w in verify(patched).values())

    # the requested image really changed, to the colour we asked for
    px = decompress_image_data(patched[off : off + alloc])[: w * h]
    assert len(set(px)) == 1
    assert px[0] == ((255 >> 3) << 11) | ((0 >> 2) << 5) | (255 >> 3)

    # nothing outside that resource, header 1 and the tail CRC moved
    changed = [
        i for i in range(len(firmware))
        if firmware[i] != patched[i] and not (off <= i < off + alloc)
    ]
    assert changed == [0x44, 0x45, 0x46, 0x47, 0xC4, 0xC5, 0xC6, 0xC7,
                       len(firmware) - 4, len(firmware) - 3,
                       len(firmware) - 2, len(firmware) - 1], changed

    # header 2 and the resource table entry are untouched
    assert patched[0xC8:0x190] == firmware[0xC8:0x190]


def test_refuses_to_overwrite_original(tmp_path):
    if not FIRMWARE.exists():
        pytest.skip("tjc.tft not present")
    assets = tmp_path / "a"
    assets.mkdir()
    _png(assets / "id0000.png")
    rc = subprocess.call(
        [sys.executable, str(HERE / "build_firmware.py"),
         "-a", str(assets), "-f", str(FIRMWARE), "-o", str(FIRMWARE)],
        cwd=str(HERE), stdout=subprocess.DEVNULL,
    )
    assert rc == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

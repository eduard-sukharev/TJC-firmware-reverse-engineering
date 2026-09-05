"""Diagnostic probe (see AGENTS.md "Opportunity, tried once, hung the panel"):
corrupts ONLY the inner container CRC field of one leaf, leaving its code
bytes untouched, to find out whether the kernel validates every loaded
blob's CRC unconditionally on every boot (in which case this alone would
hang the panel, same symptom as the earlier content-patch experiment) or
only some/none of them (in which case boot should be unaffected).

Target: p6's QR-version-bucketing leaf (crc=0x1efe907d, the `strlen` +
version-1..8 threshold function from AGENTS.md) - chosen because it makes
zero calls into the kernel vtable, i.e. it looks like a pure, self-contained
algorithm helper with no plausible reason to run automatically at boot.
"""

import struct

import tjc_checksums as tc
from tjc_codeblobs import CODE_BLOB_PARTITIONS, PARTITION_TABLE_OFFSET, parse_container

TARGET_LEAF_CRC = 0x1EFE907D


def read_partitions(fw):
    for i in range(12):
        rel_off, size, _meta = struct.unpack_from("<III", fw, PARTITION_TABLE_OFFSET + i * 12)
        if size:
            file_off = PARTITION_TABLE_OFFSET + rel_off
            yield i, file_off, fw[file_off : file_off + size]


def walk_abs(data, base_abs, path=""):
    parsed = parse_container(bytes(data))
    if parsed is None:
        yield "leaf", path, base_abs, bytes(data)
        return
    variant, entries = parsed
    if variant == "outer":
        for k, (id_, off, size) in enumerate(entries):
            yield from walk_abs(data[off : off + size], base_abs + off, f"{path}.{k}_id{id_:08x}")
    else:
        for k, (off, size, crc_) in enumerate(entries):
            crc_field_off = base_abs + 8 + k * 12 + 8
            yield "crc_field", f"{path}.{k}", crc_field_off, crc_
            yield from walk_abs(
                data[off : off + size], base_abs + off, f"{path}.{k}_crc{crc_:08x}"
            )


def main():
    fw = bytearray(open("tjc.tft", "rb").read())

    hits = []
    for idx, file_off, data in read_partitions(fw):
        if idx not in CODE_BLOB_PARTITIONS:
            continue
        for kind, path, off, payload in walk_abs(data, file_off, f"p{idx}"):
            if kind == "crc_field" and payload == TARGET_LEAF_CRC:
                hits.append((path, off, payload))

    print(f"found {len(hits)} matching CRC field(s) for {TARGET_LEAF_CRC:#010x}")
    for path, off, old in hits:
        new = (old ^ 0xFFFFFFFF) & 0xFFFFFFFF  # deliberately wrong
        struct.pack_into("<I", fw, off, new)
        print(f"  corrupted {path} @ {off:#08x}: {old:#010x} -> {new:#010x} (code bytes untouched)")

    print("verify before top-level reseal:", tc.verify(bytes(fw)))
    resealed = tc.reseal(bytes(fw))
    print("verify after top-level reseal: ", tc.verify(resealed))

    out = "tjc_crcprobe_test.tft"
    with open(out, "wb") as f:
        f.write(resealed)
    print(f"wrote {out} ({len(resealed)} bytes)")


if __name__ == "__main__":
    main()

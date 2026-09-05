"""One-off proof-of-concept patch (see AGENTS.md "Opportunity, untested"):
flips the message code passed to the kernel's show-message call on the
flash-verify success path, in every physical copy of that routine inside
partitions 5 and 6, from 0x19 ("Update Successed!") to 0x1d ("Touch Screen
Adjust OK!"). Pure argument change, zero size delta, so no file-layout work
is needed -- only re-sealing the CRCs (including each leaf's own inner
container CRC, on the chance the kernel checks it before executing a blob).

This is a diagnostic experiment, not a feature: if flashing this firmware
makes a normal upload show "Touch Screen Adjust OK!" instead of "Update
Successed!", that is direct proof the kernel executes attacker-controlled
logic out of a loaded .tft plugin blob, with a controllable argument -- the
first hard evidence toward the "replace a blob with a real bitmap blit"
idea in AGENTS.md, rather than more static-analysis inference.
"""

import struct

import capstone as cs

import tjc_checksums as tc
from tjc_codeblobs import CODE_BLOB_PARTITIONS, PARTITION_TABLE_OFFSET, parse_container

OLD_CODE = 0x19  # "Update Successed!"
NEW_CODE = 0x1D  # "Touch Screen Adjust OK!" -- chosen only for being an
# unmistakably different full sentence, not for any functional reason.


def read_partitions(fw):
    for i in range(12):
        rel_off, size, _meta = struct.unpack_from("<III", fw, PARTITION_TABLE_OFFSET + i * 12)
        if size:
            file_off = PARTITION_TABLE_OFFSET + rel_off
            yield i, file_off, fw[file_off : file_off + size]


def walk_abs(data, base_abs, path=""):
    """Like tjc_codeblobs.walk, but yields true absolute file offsets for
    every leaf and every inner-container CRC field's own file offset."""
    parsed = parse_container(bytes(data))
    if parsed is None:
        yield "leaf", path, base_abs, bytes(data)
        return
    variant, entries = parsed
    if variant == "outer":
        header_end = 8 + len(entries) * 12
        for k, (id_, off, size) in enumerate(entries):
            yield from walk_abs(data[off : off + size], base_abs + off, f"{path}.{k}_id{id_:08x}")
    else:
        for k, (off, size, crc_) in enumerate(entries):
            crc_field_off = base_abs + 8 + k * 12 + 8  # offset,size,crc -> crc is 3rd u32
            yield "crc_field", f"{path}.{k}", crc_field_off, crc_
            yield from walk_abs(
                data[off : off + size], base_abs + off, f"{path}.{k}_crc{crc_:08x}"
            )


def main():
    fw = bytearray(open("tjc.tft", "rb").read())
    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_THUMB | cs.CS_MODE_MCLASS)

    patch_sites = []  # (abs_off,) for the movs immediate byte
    crc_fields = {}  # leaf_path -> (crc_field_abs_off, old_crc)
    leaves = {}  # leaf_path -> (leaf_abs_off, data)

    for idx, file_off, data in read_partitions(fw):
        if idx not in CODE_BLOB_PARTITIONS:
            continue
        for kind, path, off, payload in walk_abs(data, file_off, f"p{idx}"):
            if kind == "crc_field":
                crc_fields[path] = (off, payload)
            else:
                leaves[path] = (off, payload)

    for path, (abs_off, leaf) in leaves.items():
        ins_list = list(md.disasm(leaf, 0))
        for k, ins in enumerate(ins_list):
            if ins.mnemonic == "movs" and ins.op_str == f"r0, #{hex(OLD_CODE)}":
                nxt = ins_list[k + 1] if k + 1 < len(ins_list) else None
                if nxt and nxt.mnemonic == "blx":
                    patch_sites.append((path, abs_off + ins.address))

    print(f"found {len(patch_sites)} call sites to patch")
    for path, off in patch_sites:
        assert fw[off : off + 2] == bytes([OLD_CODE, 0x20]), (path, off, fw[off : off + 2].hex())
        fw[off] = NEW_CODE
        print(f"  patched {path} @ {off:#08x}: r0 immediate {OLD_CODE:#04x} -> {NEW_CODE:#04x}")

    # recompute each touched leaf's own inner-container CRC (see docstring:
    # unknown whether the kernel checks this before running a blob, but
    # keeping it consistent costs nothing and removes a variable from the
    # experiment).
    touched_leaf_paths = {path.rsplit(".", 0)[0] for path, _ in patch_sites}
    # crc_fields keys are like "p5.0_id000ef030.2" (container-relative path
    # without the "_crcXXXXXXXX" suffix); leaves keys have that suffix
    # appended. Match by prefix.
    for leaf_path, (leaf_off, _old_data) in leaves.items():
        prefix = leaf_path.rsplit("_crc", 1)[0]
        if prefix not in crc_fields:
            continue
        if not any(p == leaf_path for p, _ in patch_sites):
            continue
        crc_off, old_crc = crc_fields[prefix]
        new_data = bytes(fw[leaf_off : leaf_off + len(_old_data)])
        new_crc = tc.crc(new_data) & 0xFFFFFFFF
        struct.pack_into("<I", fw, crc_off, new_crc)
        print(
            f"  updated inner CRC for {leaf_path}: {old_crc:#010x} -> {new_crc:#010x} "
            f"(field @ {crc_off:#08x})"
        )

    print("verify before top-level reseal:", tc.verify(bytes(fw)))
    resealed = tc.reseal(bytes(fw))
    print("verify after top-level reseal: ", tc.verify(resealed))

    out = "tjc_qrpatch_test.tft"
    with open(out, "wb") as f:
        f.write(resealed)
    print(f"wrote {out} ({len(resealed)} bytes)")


if __name__ == "__main__":
    main()

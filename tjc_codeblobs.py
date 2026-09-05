"""Parser/dumper for the ARM Cortex-M code blobs embedded in tjc.tft
(firmware partitions 5 and 6 -- see AGENTS.md, "Parts 5 and 6: loadable
plugins with a kernel API vtable").

These are NOT the DWIN protocol parser (that is confirmed to live in the
panel's resident kernel, not the .tft -- see AGENTS.md). They are
position-independent Thumb/Thumb-2 plugins the kernel loads and calls into a
vtable it hands them, at least one identified as a QR code generator and one
as a flash verify/update routine.

Container format (recursive, two different field orders per level):

    outer:  magic(4) | count(4) | count x [ id(4)     | offset(4) | size(4) ] | chunks
    inner:  magic(4) | count(4) | count x [ offset(4) | size(4)   | crc(4)   ] | leaves

`offset` is relative to the start of the container that holds the table.
Each chunk's `offset + size` equals the next chunk's `offset`; the last one
ends exactly at the container's end (verified byte-exact on every level).
The inner `crc` field is this project's own Nextion/TJC byte-based CRC-32
(see tjc_checksums.crc) computed over the leaf bytes -- confirmed on all 25
leaves in the stock firmware, which means a modified leaf can be re-sealed
with tjc_checksums.crc rather than needing a new algorithm.

CLI:
    python3 tjc_codeblobs.py tjc.tft --list         # walk + verify CRCs
    python3 tjc_codeblobs.py tjc.tft --dump outdir  # write each leaf as .bin
    python3 tjc_codeblobs.py tjc.tft --disasm       # list push{lr}..pop{pc}
                                                     # functions per leaf and
                                                     # the kernel vtable calls
                                                     # they make (needs capstone)
"""

import argparse
import struct
import sys

from tjc_checksums import crc as tjc_crc

PARTITION_TABLE_OFFSET = 0x10000
CODE_BLOB_PARTITIONS = (5, 6)  # the two entries known to hold these plugins


def read_partitions(fw):
    """Yields (index, file_offset, data) for every non-empty partition-table
    entry, per the 12-entry x 12-byte table documented in AGENTS.md /
    CLAUDE.md ("Firmware layout")."""
    for i in range(12):
        rel_off, size, meta = struct.unpack_from(
            "<III", fw, PARTITION_TABLE_OFFSET + i * 12
        )
        if size:
            file_off = PARTITION_TABLE_OFFSET + rel_off
            yield i, file_off, fw[file_off : file_off + size]


def parse_container(data):
    """Try both known field orders. Returns (variant, entries) where variant
    is 'outer' (id, offset, size) or 'inner' (offset, size, crc), or None if
    `data` is not a chained container (i.e. it is a leaf)."""
    if len(data) < 12:
        return None
    _magic, count = struct.unpack_from("<II", data, 0)
    if not (1 <= count <= 64):
        return None
    header_end = 8 + count * 12
    if header_end > len(data):
        return None
    raw = [struct.unpack_from("<III", data, 8 + k * 12) for k in range(count)]

    def chains(offsets_sizes):
        if offsets_sizes[0][0] != header_end:
            return False
        for k in range(len(offsets_sizes) - 1):
            if offsets_sizes[k][0] + offsets_sizes[k][1] != offsets_sizes[k + 1][0]:
                return False
        last_off, last_size = offsets_sizes[-1]
        return last_off + last_size == len(data)

    outer = [(off, size) for (_id, off, size) in raw]
    if chains(outer):
        return "outer", [(id_, off, size) for (id_, off, size) in raw]

    inner = [(off, size) for (off, size, _crc) in raw]
    if chains(inner):
        return "inner", [(off, size, crc_) for (off, size, crc_) in raw]

    return None


def walk(data, path="", verify=True, on_leaf=None, on_mismatch=None):
    """Recursively descends the container structure, calling on_leaf(path,
    bytes) for every terminal (non-container) chunk. Returns (n_chunks,
    n_crc_ok) counted over 'inner' containers only (the level that carries a
    CRC)."""
    n_total = n_ok = 0
    parsed = parse_container(data)
    if parsed is None:
        if on_leaf:
            on_leaf(path, data)
        return n_total, n_ok

    variant, entries = parsed
    if variant == "outer":
        for k, (id_, off, size) in enumerate(entries):
            sub_path = f"{path}.{k}_id{id_:08x}"
            t, o = walk(data[off : off + size], sub_path, verify, on_leaf, on_mismatch)
            n_total += t
            n_ok += o
    else:  # inner
        for k, (off, size, crc_) in enumerate(entries):
            chunk = data[off : off + size]
            n_total += 1
            if verify:
                calc = tjc_crc(chunk) & 0xFFFFFFFF
                if calc == crc_:
                    n_ok += 1
                elif on_mismatch:
                    on_mismatch(f"{path}.{k}", crc_, calc)
            sub_path = f"{path}.{k}_crc{crc_:08x}"
            t, o = walk(chunk, sub_path, verify, on_leaf, on_mismatch)
            n_total += t
            n_ok += o

    return n_total, n_ok


def find_leaves(fw):
    """Convenience: returns {path: bytes} for every leaf under the known
    code-blob partitions."""
    leaves = {}
    for idx, _off, data in read_partitions(fw):
        if idx not in CODE_BLOB_PARTITIONS:
            continue
        walk(data, f"p{idx}", on_leaf=lambda p, b: leaves.__setitem__(p, b))
    return leaves


def cmd_list(fw):
    total = ok = 0
    for idx, file_off, data in read_partitions(fw):
        if idx not in CODE_BLOB_PARTITIONS:
            continue
        print(f"partition {idx}  file_off={file_off:#x}  size={len(data)}")
        mismatches = []
        t, o = walk(
            data,
            f"p{idx}",
            on_mismatch=lambda p, stored, calc: mismatches.append((p, stored, calc)),
        )
        total += t
        ok += o
        for p, stored, calc in mismatches:
            print(f"  MISMATCH {p}: stored={stored:#010x} calc={calc:#010x}")
    print(f"\nCRC verified: {ok}/{total} leaf chunks")


def cmd_dump(fw, outdir):
    import os

    leaves = find_leaves(fw)
    os.makedirs(outdir, exist_ok=True)
    for path, data in sorted(leaves.items()):
        fn = os.path.join(outdir, path + ".bin")
        with open(fn, "wb") as f:
            f.write(data)
        print(f"{fn}  {len(data)} bytes")


def cmd_disasm(fw):
    try:
        import capstone as cs
    except ImportError:
        print("pip install capstone", file=sys.stderr)
        sys.exit(1)

    import re

    md = cs.Cs(cs.CS_ARCH_ARM, cs.CS_MODE_THUMB | cs.CS_MODE_MCLASS)
    md.detail = True
    md.skipdata = True

    def functions_in(data):
        """Find push{...,lr} sites and walk forward to a matching
        pop{...,pc}/bx lr, the same validity test used to prove parts 2/5/6
        are code in AGENTS.md. Yields (start_offset, length)."""
        sites = [
            o
            for o in range(0, len(data) - 1, 2)
            if 0xB500 <= struct.unpack_from("<H", data, o)[0] <= 0xB5FF
        ]
        for start in sites:
            off = start
            n = 0
            while off < min(len(data), start + 2048):
                ins = list(md.disasm(data[off : off + 4], 0, count=1))
                if not ins:
                    break
                i = ins[0]
                n += 1
                if (i.mnemonic == "pop" and "pc" in i.op_str) or (
                    i.mnemonic == "bx" and i.op_str == "lr"
                ):
                    if n >= 8:
                        yield start, off + i.size - start
                    break
                off += i.size

    def vtable_calls(data):
        """Same heuristic as the AGENTS.md investigation: ldr rX,[rBASE,#imm]
        (or [rBASE]) shortly before blx rX is treated as a kernel API call
        through the context vtable in rBASE. Returns a Counter of (base,
        offset) -> call count."""
        import collections

        ins_list = list(md.disasm(data, 0))
        calls = collections.Counter()
        reg_src = {}
        for k, i in enumerate(ins_list):
            m = re.match(r"^(\w+), \[(\w+), #(0x[0-9a-f]+|\d+)\]$", i.op_str)
            if i.mnemonic == "ldr" and m:
                reg_src[m.group(1)] = (m.group(2), int(m.group(3), 0), k)
            else:
                m0 = re.match(r"^(\w+), \[(\w+)\]$", i.op_str)
                if i.mnemonic == "ldr" and m0:
                    reg_src[m0.group(1)] = (m0.group(2), 0, k)
            if i.mnemonic == "blx" and i.op_str in reg_src:
                base, imm, at = reg_src[i.op_str]
                if k - at <= 8:
                    calls[(base, imm)] += 1
        return calls

    leaves = find_leaves(fw)
    import collections

    all_calls = collections.Counter()
    for path, data in sorted(leaves.items()):
        funcs = list(functions_in(data))
        calls = vtable_calls(data)
        print(f"{path}  ({len(data)} bytes): {len(funcs)} functions")
        for start, length in funcs:
            print(f"    func @ {start:#06x}  len={length}")
        for (base, imm), n in sorted(calls.items(), key=lambda kv: kv[0][1]):
            print(f"    calls [{base}+{imm:#04x}]  x{n}")
        all_calls.update(calls)

    print("\n=== kernel vtable slot summary across all leaves ===")
    for (base, imm), n in sorted(all_calls.items(), key=lambda kv: kv[0][1]):
        print(f"  [{base}+{imm:#04x}]  total calls={n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("firmware", help="path to a .tft file")
    ap.add_argument(
        "--list",
        action="store_true",
        help="walk the containers and verify CRCs (default action)",
    )
    ap.add_argument(
        "--dump", metavar="DIR", help="write every leaf blob to DIR as .bin files"
    )
    ap.add_argument(
        "--disasm",
        action="store_true",
        help="disassemble each leaf (needs capstone): list functions and the "
        "kernel vtable slots they call",
    )
    args = ap.parse_args()

    with open(args.firmware, "rb") as f:
        fw = f.read()

    if args.dump:
        cmd_dump(fw, args.dump)
    elif args.disasm:
        cmd_disasm(fw)
    else:
        cmd_list(fw)


if __name__ == "__main__":
    main()

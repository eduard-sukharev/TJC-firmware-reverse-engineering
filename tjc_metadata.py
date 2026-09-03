import csv

# 1. Update this path to point to your firmware file:
FIRMWARE_PATH = "tjc.tft"

# 2. Set output CSV filename:
CSV_OUTPUT = "tjc_metadata_report.csv"

# 3. List of known icon sizes (width, height)
icon_dims = [
    (96, 14), (102, 115), (20, 20), (68, 64), (68, 68), (124, 124), (140, 140), (240, 320),
    (78, 78), (36, 36), (36, 21), (18, 18), (182, 22), (100, 18), (68, 18), (4, 2)
]
size_patterns = {bytes([w & 0xff, (w >> 8) & 0xff, h & 0xff, (h >> 8) & 0xff]): (w, h) for w, h in icon_dims}

# 4. Metadata scan parameters
START_OFFSET = 0x35BA0
METADATA_LEN = 26

def scan_firmware_metadata(filepath, out_csv):
    with open(filepath, "rb") as f:
        f.seek(0, 2)
        filesize = f.tell()
        f.seek(0)
        f.seek(START_OFFSET)
        data = f.read()

    results = []
    for ptr in range(0, len(data) - METADATA_LEN, 2):
        meta = data[ptr:ptr+METADATA_LEN]
        wh = meta[-4:]
        if wh in size_patterns:
            w, h = size_patterns[wh]
            icon_idx = int.from_bytes(meta[-12:-11], 'little')
            unknown_start_hex = meta[0:16].hex()
            unknown_marker_hex = meta[-16:-12].hex()
            unknown_hex = meta[-7:-4].hex()
            results.append({
                "metadata_offset": f"{START_OFFSET + ptr:08X}",
                "unknown_start_hex": unknown_start_hex,
                "unknown_marker_hex": unknown_marker_hex,
                "icon_index": icon_idx,
                "unknown_hex": unknown_hex,
                "width": w,
                "height": h,
                "metadata_full_hex": meta.hex()
            })

    with open(out_csv, "w", newline="") as csvfile:
        fieldnames = [
            "metadata_offset", "unknown_start_hex", "unknown_marker_hex", "icon_index", "unknown_hex", "width", "height", "metadata_full_hex"
        ]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(row)

    print(f"CSV report saved to {out_csv}")
    print(f"Total records found: {len(results)}")

if __name__ == "__main__":
    scan_firmware_metadata(FIRMWARE_PATH, CSV_OUTPUT)

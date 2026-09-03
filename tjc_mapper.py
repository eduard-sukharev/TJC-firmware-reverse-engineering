# ---- CONFIGURE THESE ----
FIRMWARE_PATH = "tjc.tft"  # path to your file
START_OFFSET = 0x35BA0

# Icon dimension table: {bytes: (w, h)}
icon_dims = [
    (96, 14), (102, 115), (20, 20), (68, 64), (68, 68), (124, 124), (140, 140),
    (78, 78), (36, 36), (36, 21), (18, 18), (182, 22), (100, 18), (68, 18), (240, 320)
]
icon_size_map = {w*h*2: f"{w}x{h}" for w, h in icon_dims}

PADDING = bytes([0x00]*20)

def format_offset(offset):
    return f"{offset//0x10000:04X}:{offset%0x10000:04X}"

with open(FIRMWARE_PATH, "rb") as f:
    f.seek(START_OFFSET)
    data = f.read()

# Scan for 20x0x00 paddings, collect offsets right after
padding_offsets = []
ptr = 0
while ptr < len(data) - 20:
    if data[ptr:ptr+20] == PADDING:
        padding_offsets.append(ptr+20)
        ptr += 20
    else:
        ptr += 1

# For each padding offset, calculate chunk size (distance to next padding)
for i in range(len(padding_offsets)-1):
    offset = padding_offsets[i]
    next_offset = padding_offsets[i+1]
    length = next_offset - offset

    if length < 600:
        continue

    # Find matching WxH if any
    match = icon_size_map.get(length, "")
    print(f"{format_offset(START_OFFSET+offset)}  {length:6d}  {match}")

# Optionally, print the last found offset (no following chunk)
if padding_offsets:
    print(f"{format_offset(START_OFFSET+padding_offsets[-1])}  (last chunk, size unknown)")

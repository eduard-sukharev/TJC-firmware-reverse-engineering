# Replacement assets

Drop images here that you want written into the firmware, then run:

```bash
python3 build_firmware.py            # assets/ -> tjc_custom.tft
```

Only the files present here are changed. Every other resource in the firmware
is left byte-for-byte alone.

## Naming

Files are matched to firmware resources by the id in the file name:

| File name | Resource |
|-----------|----------|
| `id0000_240x320.png` | 0, and the dimensions are checked against the resource table |
| `id0000.png` | 0 |
| `0.png` | 0 |

Anything whose name does not contain an id is reported and skipped, never
guessed at. Any format Pillow can read works.

## Getting a starting point

Extract the stock assets first, then copy in *only* the ones you intend to
change:

```bash
python3 extract_all.py -f tjc.tft -o extracted_all
cp extracted_all/id0000_240x320.png assets/
```

`extracted_all/` is the extractor's output and is deliberately kept separate
from this directory, so a build can never consume a whole extraction by
accident. `build_firmware.py` refuses to read directly from it.

## Size budget

A replacement has to fit the space the original image already occupies. Run
`python3 build_firmware.py --list` to see each asset's size against its budget
without writing anything. Flat UI artwork compresses well; busy photographic
images may not fit.

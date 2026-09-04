# TJC Display Thumbnail Rendering Benchmarks

**Date:** 2026-09-04  
**Hardware:** TJC3224T132_011N panel on Ender-3 V3 SE  
**Serial:** 115200 baud, 3ms/frame throttle (safe minimum from Phase 1 testing)  
**Test images:** 2 real G-code thumbnails (96×96 RGB565), decoded from Marlin's `E3V3SE_THUMB_RAW16` format  

## Results Summary

### thumbnail_1_thumb.png

- **Image content:** 9,216 px, 22.4% foreground (2,065 pixels), 69 distinct colors, 1,483 RLE runs
- **Naive (baseline):** 4,130 frames, 13.33s wall time
- **RLE (Phase 1):** 2,962 frames, 9.72s, **1.37× speedup** (28.3% frame reduction)
- **Bucket-sort (Phase 2):** 1,552 frames, 5.21s, **2.56× speedup** (62.4% frame reduction)
- **Key insight:** Palette switching on 1,479 of 1,483 runs (99.7%) — the bottleneck is not byte count, but palette set overhead. Bucket-sort eliminates this by grouping all runs of the same color, reducing to only 69 palette switches (one per distinct color).

### thumbnail_2_thumb.png

- **Image content:** 9,216 px, 20.7% foreground (1,905 pixels), 69 distinct colors, 1,212 RLE runs
- **Naive (baseline):** 3,810 frames, 12.60s wall time
- **RLE (Phase 1):** 2,420 frames, 7.96s, **1.58× speedup** (36.5% frame reduction)
- **Bucket-sort (Phase 2):** 1,281 frames, 4.33s, **2.91× speedup** (66.4% frame reduction)
- **Key insight:** More aggressive RLE compression here (fewer runs), so plain RLE does better (1.58× vs 1.37×). Bucket-sort still delivers 2.9× overall.

## Comparative Analysis

| Algorithm      | Avg speedup | Frame reduction | Why it works |
|---|---|---|---|
| **Naive**      | 1.00×       | baseline        | Per-pixel `0x40` set-palette + `0x5B` rect = 2 frames/px |
| **RLE**        | 1.47×       | 32% avg         | Collapses pixel runs into single `0x5B`; still palette-heavy (1 per run) |
| **Bucket-sort**| 2.74×       | 64% avg         | Groups all runs by color; `0x40` sent only 69 times total (once per color) |

## Wall Time Analysis

**Observed:** Wall times scale with frame count (not wire-bound).
- Naive: 3,810–4,130 frames × ~3.24ms/frame ≈ 12.3–13.4s  
- RLE: 2,420–2,962 frames × ~3.28ms/frame ≈ 7.9–9.7s  
- Bucket-sort: 1,281–1,552 frames × ~3.39ms/frame ≈ 4.3–5.3s  

The consistent ~3.3ms/frame (slightly higher than the 3ms throttle) accounts for serial transmission time (~24 bytes × frame at 115200 baud = ~2.1ms) + panel processing overhead.

## Design Validation

1. ✅ **Panel is not wire-bound at 115200 baud.** Reducing frame count by 62% directly reduced wall time by 62%, with no buffering or queueing artifacts. The panel processes drawing commands in real time, keeping up with the serial stream.

2. ✅ **Palette switching is the bottleneck.** Both thumbnails have ~69 distinct colors scattered across 1,200–1,500 RLE runs. RLE alone (28–37% reduction) underperforms bucket-sort (62–66% reduction) by nearly 2×, proving that one palette-set per run is the dominant cost, not pixel count or rect-fill throughput.

3. ✅ **3ms/frame is a safe, non-minimal delay.** Used conservatively after the overrun incident (unthrottled ~2000-command flood wedged the panel). This delay was not bisected downward; tighter timing may be possible but 3ms is proven safe on both real images.

4. ✅ **Real thumbnails are favorable for this optimization.** Smooth shading → many colors, but all used in long runs by color bucket. Worst case (flat-shaded silhouettes, 8 colors) would show even better reduction (~5×).

## Implications for Phase 3

**Port strategy: Use bucket-sort, not plain RLE.**

Bucket-sort costs ~6 KB RAM on a 96×96 image (holding the full run list before rendering), which is comfortable on the STM32F401 (256 KB SRAM). The speedup (2.7–2.9×) is worth the cost, and the memory is released immediately after rendering.

The algorithm:
1. Decode the thumbnail image line-by-line (unchanged).
2. Collect all runs (x0, x1, y) into color buckets as they're generated (new).
3. Render each bucket (one palette set, then all its runs) instead of row-by-row (new).
4. Keep the existing `color == 0` (transparent-black) skip (unchanged).
5. Apply 3ms/frame throttle in the DWIN frame-send helper, not per-call (new; matches Phase 1 finding).

## Files

- `tjc_dwin.py` — DWIN protocol client with throttling
- `dwin_blit.py` — Image encoders: naive, RLE, bucket-sort  
- `dwin_bench.py` — Hardware benchmark harness
- `thumb_raw16.py` — Decoder for G-code `E3V3SE_THUMB_RAW16` blocks
- `thumbnail_1_thumb.png`, `thumbnail_2_thumb.png` — Extracted real test images

All verified on real hardware, no corruption observed at 3ms/frame.

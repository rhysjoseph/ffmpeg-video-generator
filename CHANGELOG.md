# Changelog

## v1.0.0 — 25 November 2026

First tagged release of Pattern Studio. The generator, scaler, file verifier and Docker Desktop deployment are included. This release adds regression coverage and hardware playback measurements.

### Verification

- Added a 1080p50 regression test that renders a ten-second ProRes HQ MOV and checks the moving white patch on the bottom scan line of all 500 frames, including wraparound.
- Narrowed the Shogun Classic monitor pack to 21 Apple-encoded ProRes HQ profiles. All 8,310 frames were checked against the lossless source, and all 21 delivered files matched their read-back checksums. [Profile manifest and file checksums](docs/verification/shogun-classic-pack.json)
- Checked 40 generated MOVs and 40 scaler outputs. All 80 passed the measured picture and PCM loop checks. Four QHD/UHD deinterlacing cases showed small differences along a reconstructed edge before ProRes encoding. [File and format results](docs/verification/decklink-format-sweep.md)
- Tested 13 native SDI formats through the UltraStudio HD Mini and PRISM with DXD-8 reference. SDI error counters stayed flat over 56 measured joins after lock. The 1080p59.94 conversion also passed the referenced playout checks at all four dashboard durations. Three 720p rates carried an unexpected reserved bit in the SDI payload identifier. [Referenced playout results](docs/verification/decklink-reference-sweep.md)

### Known playback issue

- **Shogun Classic, AtomOS 10.45.01, 1080p50.** The updated Apple-encoded ProRes HQ file still showed bottom-edge corruption on SDI. A 36-second recording found 13 affected pictures at four source timecodes. All 1,800 pictures arrived in order. The embedded stereo tone dropped around each of the three loop joins. This playback path remains unqualified for critical-system testing. [Timecodes, comparison images and recordings](docs/verification/shogun-sdi-return-1080p50.md)

# DXD-8 referenced DeckLink and PRISM benchmark

25 November 2026. The UltraStudio HD Mini played 28 generated and scaled clip paths through PRISM SDI 2, across 13 native formats. The card reference input and PRISM video-to-PTP checks passed in 17 of 17 runs. The benchmark covered 56 internal loop joins. BNC outputs 3 and 4 on the Brainstorm DXD-8 were restored to 1080p50 tri-level sync. The final DXD readback matched the recorded configuration for all four output pairs. [Measurements by file and run](decklink-reference-sweep.json)

## Selecting the reference for 1080p59.94

With the UltraStudio outputting 1080p59.94, the driver reported an unknown reference format for 1080p59.94 tri-level sync. With 1080i59.94 it identified the reference but reported unlocked, and PRISM measured the phase changing. NTSC black burst gave hardware lock and a stable offset of about −191 µs in the short trial. **720p59.94 tri-level sync** gave hardware lock and a much smaller offset. Over the measured loops of the generated and scaled files, PRISM reported **Video/Ref Locked**, and the SDI phase measured +0.067 to +0.074 µs. The measured SDI payload was `89 CA 00 01`, 1080p59.94 Level A, 10-bit YCbCr 4:2:2. The file burn-in on the scaler picture identifies its 720p source. [PRISM screenshot at the reported corner-flash interval](decklink-reference-1080p5994.jpg)

The DXD-8 was the PTP grandmaster. PRISM reported its identity as the locked grandmaster on domain 127. The DXD-8 supplied analogue sync to the UltraStudio through BNC 3. At each measurement the bench read the DXD output selection and status, the card’s detected reference format and lock, its output-mode lock flags, and PRISM’s separate video-to-reference, PTP and phase measurements. The warm-up results distinguish a momentary lock indication from sustained phase stability. Phase is the offset PRISM displayed relative to PTP. It includes the equipment and signal path. [DXD-8 operation manual](https://brainstormtime.com/wp-content/uploads/2025/05/Brainstorm_DXD-8_Manual_rev4.00.pdf) · [DeckLink SDK manual](https://documents.blackmagicdesign.com/UserManuals/DeckLinkSDKManual.pdf)

## Native SDI formats

The published measurements identify the bench grandmaster as `bench-dxd8`. This label replaces its hardware clock identifier throughout the JSON.

Each run began with two 10-second warm-up cycles. Each test clip then played three consecutive times under one output clock. The checked interval begins at the sample immediately before its first measured join and continues through the final cycle. PRISM counted SDI framing and occasional CRC errors during format changes. The measurements preserve these acquisition deltas separately so a clean loop result cannot be mistaken for a glitch-free format switch. The deinterlacing rows give the source field rate in the run name and carried progressive SDI at that rate.

| Playout run | DXD reference | UltraStudio locked samples | PRISM Video/Ref samples | PTP phase range (µs) | Joins | New SDI errors | VPID (hex) |
| --- | --- | ---: | --- | ---: | ---: | ---: | --- |
| 1920x1080-59.94p | 720p59.94 | 16/16 | Locked ×16 | 0.067 to 0.074 | 4 | 0 | 89 CA 00 01 |
| 1280x720-50p | 720p50 | 16/16 | Locked ×16 | -0.983 to -0.970 | 4 | 0 | 84 C9 00 01 |
| 1280x720-59.94p | 720p59.94 | 16/16 | Locked ×16 | -0.998 to -0.984 | 4 | 0 | 84 CA 00 01 |
| 1280x720-60p | 720p60 | 16/16 | Locked ×16 | -0.997 to -0.983 | 4 | 0 | 84 CB 00 01 |
| 1280x720-deint-50i | 720p50 | 7/7 | Locked ×7 | -1.010 to -0.997 | 2 | 0 | 84 C9 00 01 |
| 1280x720-deint-59.94i | 720p59.94 | 7/7 | Locked ×7 | -1.025 to -1.011 | 2 | 0 | 84 CA 00 01 |
| 1920x1080-23.98p | 1080p23.98 | 16/16 | Locked ×16 | -1.065 to -1.038 | 4 | 0 | 85 C2 00 01 |
| 1920x1080-24p | 1080p24 | 16/16 | Locked ×16 | -1.051 to -1.037 | 4 | 0 | 85 C3 00 01 |
| 1920x1080-25p | 1080p25 | 16/16 | Locked ×16 | -1.104 to -1.091 | 4 | 0 | 85 C5 00 01 |
| 1920x1080-29.97p | 1080p29.97 | 16/16 | Locked ×16 | -1.011 to -0.998 | 4 | 0 | 85 C6 00 01 |
| 1920x1080-30p | 1080p30 | 16/16 | Locked ×16 | -1.064 to -1.064 | 4 | 0 | 85 C7 00 01 |
| 1920x1080-50i | 1080i50 | 7/7 | Locked ×7 | -1.037 to -1.024 | 2 | 0 | 85 05 00 01 |
| 1920x1080-50p | 720p50 | 16/16 | Locked ×16 | 0.101 to 0.114 | 4 | 0 | 89 C9 00 01 |
| 1920x1080-59.94i | 1080i59.94 | 7/7 | Locked ×7 | -1.011 to -1.011 | 2 | 0 | 85 06 00 01 |
| 1920x1080-60p | 720p60 | 16/16 | Locked ×16 | 0.081 to 0.094 | 4 | 0 | 89 CB 00 01 |
| 1920x1080-deint-50i | 720p50 | 7/7 | Locked ×7 | 0.088 to 0.094 | 2 | 0 | 89 C9 00 01 |
| 1920x1080-deint-59.94i | 720p59.94 | 7/7 | Locked ×7 | 0.088 to 0.094 | 2 | 0 | 89 CA 00 01 |

All steady-state error counters stayed flat and the luma and chroma CRC measurements remained active. Each playout sequence was assembled without re-encoding. Video packet hashes and exact presentation timestamps were verified before output. Each run used a continuous DeckLink schedule through both joins of each clip. PRISM pictures were compared against decoded source frames or their individual fields, including the lower-right corner. The bench recorded 73 picture samples. Across the 218 steady timing observations, the widest phase range in any single run was 0.027 µs. Continuous physical picture capture would be needed to inspect every on-wire frame.

At 720p50, 59.94 and 60, the VPID carried byte 2 values `C9`, `CA` and `CB`. The reserved high bit should be zero. A separate 720p59.94 native test pattern reproduced `84 CA 00 01` in the SDI output without using either MOV generation or scaling. Reference lock and the payload-identifier discrepancy can coexist. [SMPTE ST 292-1:2018, §9.4](https://pub.smpte.org/pub/st292-1/st292-1-2018.pdf#page=10)

## Four dashboard durations at 1080p59.94

The bench also played the complete H.264-to-ProRes HQ loop conversion for each supported length, followed by the first 120 frames of the same file. Fractional-rate fixtures contain 60 frames per nominal second. A nominal 120-second loop therefore lasts 120.120 seconds. The sequence used the 720p59.94 reference. Every compressed picture, timestamp and all eight PCM channels were checked against the source segments before playback. Measurements on each side of each wrap used the same uninterrupted SDI clock. The before and after PRISM screenshots were each compared with the first and last three seconds of the decoded file. The nearest frame numbers below are zero-based spot measurements.

In the initial 10-second trial, the card remained locked and the displayed phase was +0.067 µs at all four samples. PRISM still reported “Drifting” in the first two samples, then “Locked” before and after the wrap. The 10-second row below uses a repeat with 50.050 seconds of preroll. Both attempts are retained in the JSON. A temporary repeat-playout assembly failed its PCM identity check during preparation and was discarded. The sequence used on SDI passed the full video packet, timestamp and eight-channel PCM identity checks.

| Dashboard length | Full clip frames | PRISM samples | Nearest file frame before → after wrap | PTP phase range (µs) | Timing, SDI and wrap coverage |
| --- | ---: | ---: | ---: | ---: | --- |
| 10 s | 600 | 4 | 538 → 28 | 0.074 to 0.081 | Pass |
| 30 s | 1,800 | 8 | 1741 → 33 | 0.067 to 0.074 | Pass |
| 60 s | 3,600 | 14 | 3543 → 33 | 0.067 to 0.074 | Pass |
| 120 s | 7,200 | 26 | 7141 → 31 | 0.067 to 0.074 | Pass |

## File artefacts and loops

All 80 file SHA-256 digests matched the earlier benchmark. A fresh decode covered 30,840 pictures from the 40 generated 10-second MOVs and 40 scaler outputs. The test compared the predicted bar movement across the full-width lower scan line at each join, checked stereo PCM against a continuous 1 kHz tone and compared the lower-right region with the expected moving white patch during seconds 4–6. All 80 files passed the measured picture-motion and audio wraps. The burned-in clip timecode restarts on a loop.

The 4–6 second check covered 1,153,836,720 luma samples outside the edge guards. It reproduced the same 119 threshold differences in four high-resolution deinterlacing cases. QHD 50i and 59.94i source conversions had 22 and 6 differences, respectively. UHD had 44 and 47. The earlier lossless comparison located them on a reconstructed scan line at the moving edge before ProRes encoding. All 40 generated MOVs and the remaining 36 scaler cases passed the patch check. The HD Mini's physical sweep covers the 13 native 720- and 1080-line formats above. QHD, UHD and the remaining dashboard modes have file measurements. [Earlier full-frame comparisons and pixel coordinates](decklink-format-sweep.md)

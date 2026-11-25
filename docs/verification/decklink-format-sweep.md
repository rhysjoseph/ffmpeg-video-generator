# DeckLink and PRISM format sweep

On 25 November 2026, all 40 generated MOVs and all 40 scaler cases passed the picture and audio loop checks. All 40 generated files and 36 scaler outputs also passed the independent white-patch check. Four QHD/UHD deinterlacing cases showed small edge differences on reconstructed lines. Across the 13 native SDI formats shared by the generator and the UltraStudio HD Mini, the PRISM error counters stayed flat during the measured loop joins. All three 720p rates showed a reserved-bit discrepancy in the SDI payload identifier. [Per-file results, flagged pixel coordinates and PRISM measurements](decklink-format-sweep.json)

## 1080p59.94

The first run played the byte-matched monitor export and a 1280×720 to 1920×1080 scaler conversion. Each file held 600 progressive pictures at 60000/1001 fps, covering 10.010 seconds, with 480,480 samples per audio channel. The observed picture movement at each join agreed with the adjacent frames. The independent bottom-strip check found the white patch in the expected position, including the 4–6 second interval.

PRISM SDI 2 reported 1080p59.94, 3G Level A, YCbCr 4:2:2 10-bit and payload `89 CA 00 01` for both files. The smaller raster named in the second burned-in label identifies the scaler input. The PRISM format field shows the output raster. [PRISM comparison](decklink-format-sweep-5994.jpg)

## File coverage

Each raster (1280×720, 1920×1080, 2560×1440 and 3840×2160) had eight progressive monitor clips at 23.98, 24, 25, 29.97, 30, 50, 59.94 and 60 fps, plus top-field-first 50i and 59.94i. The test used the nominal 10-second monitor pack with moving bars, ball, logo, timecode and profile label. The burn-in counter restarts when each clip loops.

- **Generated files.** SGNCL was unmounted. All 40 recreated MOVs matched the SHA-256 hashes read back from the drive at delivery. Their delivery reports cover full-frame, two-half comparisons with lossless encoder-input references. This run also decoded each MOV to check motion and PCM independently.
- **Scaler files.** At each progressive rate the application upscaled 720 to 1080, downscaled 1080 to 720, and upscaled 1080 to QHD and UHD. For each of the eight interlaced source clips it used automatic deinterlacing at the source raster, producing 50p or 59.94p with one output frame per input field. These tests used the application's ProRes HQ preset and preserved stereo audio.
- **Picture.** The combined file records cover 30,840 decoded pictures. The scaler verification compared every frame with a separately constructed lossless target based on the source, Lanczos resize and, for interlaced sources, field-rate deinterlacing. The highest per-half mean difference from the applicable reference was 0.130 on an 8-bit RGB scale. No sampled flat reference patch contained a large error. An independent trajectory calculation tracked the moving white patch across the full width, including each end of the loop. Between 4 and 6 seconds we checked 1,153,836,720 lower-right luma samples outside the specified transition margins against the expected white mask. Woven source frames were checked by field.
- **Loop and audio.** Every file had the expected frame count, cadence and picture motion at the wrap. No consecutive identical decoded pictures or near-freezes were reported. Stereo PCM started and ended on the video boundaries, with a whole number of 1 kHz periods. Every sample was checked against the continuous calibrated tone to within one 24-bit code.

### Four deinterlacing findings

In the QHD 50i→50p and 59.94i→59.94p outputs, 22 and 6 pixel samples respectively fell on the dark side of the white-mask threshold. The UHD cases had 44 and 47. All 119 were on the first line of the bottom strip, 2.5–3.5 source pixels from the moving vertical edge, in fields where the deinterlacer had to reconstruct that line. All 119 were already below the threshold in the lossless deinterlacer output. ProRes encoding changed those samples by at most two 10-bit codes. These four files passed the loop checks and retain a picture-review finding for precision edge measurements. The machine-readable report includes each coordinate, frame, measured luma and corresponding pre-encode value.

## Physical SDI results

The local GStreamer DeckLink sink sent 10-bit v210 through the UltraStudio HD Mini to physical SDI 2. Each of 28 clip paths played three times, with one uninterrupted output clock per run. Every compressed video packet in each playback sequence matched its source and had the expected consecutive presentation timestamp. The input was already mapped to the second physical connector.

| Raster | On-wire rate | File path tested | Measured VPID | Signalling |
| --- | --- | --- | --- | --- |
| 1280x720 | 50p | Generated and scaled | `84 C9 00 01` | 720p reserved bit set |
| 1280x720 | 59.94p | Generated and scaled | `84 CA 00 01` | 720p reserved bit set |
| 1280x720 | 60p | Generated and scaled | `84 CB 00 01` | 720p reserved bit set |
| 1280x720 | 50p | Field-rate scaler output | `84 C9 00 01` | 720p reserved bit set |
| 1280x720 | 59.94p | Field-rate scaler output | `84 CA 00 01` | 720p reserved bit set |
| 1920x1080 | 23.98p | Generated and scaled | `85 C2 00 01` | Passed |
| 1920x1080 | 24p | Generated and scaled | `85 C3 00 01` | Passed |
| 1920x1080 | 25p | Generated and scaled | `85 C5 00 01` | Passed |
| 1920x1080 | 29.97p | Generated and scaled | `85 C6 00 01` | Passed |
| 1920x1080 | 30p | Generated and scaled | `85 C7 00 01` | Passed |
| 1920x1080 | 50i | Generated interlaced | `85 05 00 01` | Passed |
| 1920x1080 | 50p | Generated and scaled | `89 C9 00 01` | Passed |
| 1920x1080 | 59.94i | Generated interlaced | `85 06 00 01` | Passed |
| 1920x1080 | 59.94p | Generated and scaled | `89 CA 00 01` | Passed |
| 1920x1080 | 60p | Generated and scaled | `89 CB 00 01` | Passed |
| 1920x1080 | 50p | Field-rate scaler output | `89 C9 00 01` | Passed |
| 1920x1080 | 59.94p | Field-rate scaler output | `89 CA 00 01` | Passed |

The scaler produces progressive output. The two native 1080i runs used generated interlaced MOVs. The four field-rate scaler runs exercised conversions from 720- and 1080-line interlaced sources. The remaining application formats were checked in files. The HD Mini supports three native 720p rates and has no QHD or UHD output. [UltraStudio HD Mini technical specifications](https://www.blackmagicdesign.com/products/ultrastudio/techspecs)

**720p signalling.** For these 1.485 Gb/s payloads SMPTE ST 292-1:2018 reserves byte 2 bit 7 and requires zero. For 50, 59.94 and 60 fps the expected byte values are `49`, `4A` and `4B`. The measured values were `C9`, `CA` and `CB`. A separate GStreamer test pattern sent directly to the same card at 720p59.94 produced the same `84 CA 00 01` without a MOV or scaler. The result isolates this discrepancy to the SDI playout path. [SMPTE ST 292-1, §9.4.1](https://pub.smpte.org/pub/st292-1/st292-1-2018.pdf#page=10)

**1080i picture review.** Two 50i PRISM screenshots initially differed from the woven MOV by one display column along the moving white patch. Comparing the two source fields separately identified the top field of frame 116 as the displayed picture in both captures. With that field, the large-difference pixel count in the lower-right region fell from 45 to zero. The same field-aware comparison was used for both interlaced formats.

**Measurement limits.** Switching modes produced acquisition transients. The report retains acquisition counter changes separately and evaluates the locked interval beginning with the sample just before the first loop join. All 56 internal joins fell in these intervals, with no new SDI errors or inactive luma/chroma CRC seconds. All runs reached end of stream. We compared 73 sampled PRISM pictures to decoded file frames. The full frame-by-frame checks apply to the files. A continuous SDI return capture would be needed to count every physical picture independently. PRISM also reported video drifting relative to its locked PTP reference during the sweep. Facility genlock remains unqualified.

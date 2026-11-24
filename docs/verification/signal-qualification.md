# Signal and conversion qualification

Measured on 24 November 2026 with macOS FFmpeg 9.0.2 and the Docker Desktop arm64 image with FFmpeg 7.1.5. Each report records its tool versions and individual cases. The file checks apply to the specified fixtures and thresholds. The physical measurement covers one HD-SDI mode.

**427 supported qualification cases ran in each environment with zero failed cases.** On macOS, 275 passed without a finding and 152 had review findings. On Docker, 237 passed without a finding and 190 had review findings. Both builds also passed all 39 regression tests. The case reports distinguish expected static pictures, rate-conversion repeats, codec quantisation, missing metadata and AAC loop limitations.

## Coverage

| Suite | Cases per environment | Measurement | macOS | Docker |
| --- | ---: | --- | --- | --- |
| Codec by resolution | 277 supported | All four rasters, 224 generated files and 53 converted files. Eight decoded pictures per case. Three other raster requests are outside the DNxHD HQ preset. | [Results](native-bars-profile-matrix.json) | [Results](docker-bars-profile-matrix.json) |
| Custom encoding | 51 | A deterministic covering array of 735 feasible option-value pairs across raster, rate, depth, chroma, colour, range, codec selection, CRF, speed, container and field order. | [Results](signal-encoders.json) | [Results](docker-signal-encoders.json) |
| Editing encoders | 22 | Each of the eleven named generator editing profiles at two settings. Includes progressive DNxHR and both field dominances across ProRes cases. | [Results](signal-editing.json) | [Results](docker-signal-editing.json) |
| HD bar signal | 5 | Eight upper patches, five PLUGE samples, the luma ramp interior and one grey-to-white rise time. Measured before encoding and after decoding, including a 12-bit moving-marker case. | [Results](signal-bars.json) | [Results](docker-signal-bars.json) |
| SDR colour | 24 | Each of four profiles at both ranges and all three depths. Compares eight native Y′CbCr triplets against a separate numerical implementation of the scene-referred SDR transform. | [Results](signal-colour.json) | [Results](docker-signal-colour.json) |
| Conversion | 28 | Every converter preset with limited- and full-range moving-patch inputs. Varies source depth, chroma, matrix, size and cadence. Covers pad, crop, stretch, upscaling, downscaling and rate doubling. | [Results](signal-conversions.json) | [Results](docker-signal-conversions.json) |
| Proxy controls | 8 | Both HEVC proxy depths on the same moving source at CRF 35 Fast, CRF 28 Ultrafast, CRF 28 Fast and CRF 16 Slow. | [Results](signal-proxies.json) | [Results](docker-signal-proxies.json) |
| Full-length MOV loops | 4 pairs | Generate and convert complete 10-, 30-, 60- and 120-second selections. Decode the sound at both joins and compare each converted picture to its source. | [Results](signal-durations.json) | [Results](docker-signal-durations.json) |
| Full-length AAC loops | 8 | Four real durations in each of MP4 and MPEG-TS. Measures picture motion, stream start offsets and decoded audio sample counts. Includes 50i. | [Results](signal-aac.json) | [Results](docker-signal-aac.json) |

A pairwise case covers each feasible pair of selected options somewhere in the suite. Three-way and higher-order interactions can still be untested. Field order affects interlaced output. The eight-frame cases exercise encoder setup, file signalling and short decode paths. The full-length groups exercise motion, codec delay and file endings over the actual dashboard durations.

## Generation

The earlier FFmpeg HD bar source placed the 10-bit 75% green luma at 532, compared with the published 534. Its ramp originated in eight bits and extended beyond nominal black and white. The replacement plate uses the native patch codes, 75% white and black optional subpatterns, recommended bar widths and a linear nominal ramp. It shapes horizontal transitions with an integrated sine-squared function. QHD and UHD use scaled geometry. [SMPTE RP 219-2002, sections 2.1–2.2 and Annexes B–C](https://pub.smpte.org/doc/rp219/20020619-pub/Rp219-2002.pdf)

All five pre-encoder fixtures matched the thirteen sampled patch triplets exactly. The interior ramp agreed with its linear target to rounding precision. The tests also measure one luma transition, using interpolated 10% and 90% crossings at the HD sample clock. Codec quantisation can move the decoded values. The reports retain the actual deviations, including single-code changes on 12-bit exports. Rise time on every transition, all chroma transitions, analogue reconstruction and other editions of the practice are outside this measurement. [Measured HD bars](signal-bars.json)

The SDR colour check starts from the independently transcribed upper-patch codes. It decodes BT.709 Y′CbCr to R′G′B′, linearises the channels, changes D65 primaries and applies the target transfer, matrix and range. It uses a symmetric extension of the transfer for excursions outside the destination gamut. The pre-encoder and decoded limits are one and two 8-bit-equivalent codes respectively. Across the 24 cases on both builds, the largest observed discrepancy was 0.25 of an 8-bit code. This tests the generator's scene-referred conversion. A display-referred transform can produce different numbers. [ITU-R BT.709](https://www.itu.int/rec/R-REC-BT.709/en) · [ITU-R BT.601](https://www.itu.int/rec/R-REC-BT.601/en) · [ITU-R BT.2020](https://www.itu.int/rec/R-REC-BT.2020/en)

The custom encoder tests compare each output frame with a lossless recording of the signal supplied to its encoder. That comparison can detect encoding damage. The native bar and SDR colour groups provide independent checks on the source. Static fixtures can legitimately report repeated frames. FFmpeg 7 can leave ProRes range metadata unspecified, which remains visible as a review finding.

## Conversion and picture damage

The converter test creates eight planar frames with different upper and lower chips. The lower chips change position on every frame. A separate reference starts from expected limited-range samples and uses independently calculated geometry, cadence and bicubic resizing. The converter uses Lanczos. DNx references calculate the Y′CbCr matrix change from the component equations. The check compares every decoded frame at the output raster, measures both halves separately, and tests patch interiors for isolated large differences. The highest allowed per-half mean is 3 RGB codes. At most 0.5% of channel samples in either half may differ by more than 32 codes, and sampled flat reference patches allow zero such outliers. An additional native-level check measures the upper chips. These engineering limits are specific to these fixtures.

Two failures led to changes.

- **DNx matrix signalling.** A MOV advertised BT.601 while the decoded DNx picture header specified BT.709. DNx generation and conversion now encode component values for the BT.709 matrix used by this FFmpeg encoder. The chosen or source primaries and transfer are retained and reported separately in the conversion plan. Constant-luminance BT.2020 to DNx requires another transform and is rejected. Generation and conversion now check the stream contract, decoded field dominance, frame colour and presentation timestamps before publishing each file. Standalone uploads also report disagreements between stream and picture colour tags. [FFmpeg DNx decoder](https://github.com/FFmpeg/FFmpeg/blob/master/libavcodec/dnxhddec.c)
- **High-compression HEVC chroma.** At CRF 35 Ultrafast, the original 10-bit proxy exceeded the 3-code mean error threshold on both builds. The 8-bit proxy also exceeded it on Docker. A two-step reduction of each chroma QP offset brought both depths inside the same threshold while keeping the chosen luma CRF and speed. The follow-up runs use the shipping settings. The experiment records errors and output sizes for offsets 0, −2, −3, −4 and −6. [Before-and-after measurements](proxy-chroma-study.json) · [x265 chroma QP settings](https://x265.readthedocs.io/en/master/cli.html#cmdoption-cbqpoffs)

The clean short and full-length comparison fixtures produced zero large errors in the sampled flat patches. Regression controls deliberately insert a green lower half and a single grey pixel and require the verifier to identify the damaged frame. The original damaged file remains unavailable.

## Loop and SDI measurements

| Selected length | Generated MOV → converted MOV | Pictures per cycle | Actual cycle |
| --- | --- | ---: | ---: |
| 10 s | UHD 24p H.264 → ProRes Proxy | 240 | 10.000 s |
| 30 s | QHD 29.97p 10-bit HEVC → ProRes HQ | 900 | 30.030 s |
| 60 s | 1080p25 full-range 10-bit H.264 → DNxHR 444 | 1,500 | 60.000 s |
| 120 s | 720p23.98 H.264 → DNxHR SQ | 2,880 | 120.120 s |

The moving MOV clips had continuous picture transitions at the measured joins. Generated and converted PCM matched the video length sample-for-sample and wrapped the 1 kHz tone at the expected phase. AAC differed by player and container. Native FFmpeg trimmed the tested MP4 files to the picture span. Docker FFmpeg left trailing decoded samples. MPEG-TS carried AAC starting 1,024 samples before picture and retained extra decoded samples at all four durations. Use MOV with PCM when the loop requires sample-accurate audio. A player must also keep its output running across the file restart.

The corrected 1080p59.94 ProRes HQ clip played three cycles through the UltraStudio HD Mini to end of stream. PRISM showed SDR Rec.709, YCbCr 4:2:2 10-bit, SMPTE 425 Level A, green SDI-format and CRC indicators, and eight channels around −20 dBFS. PRISM also reported **Video/Ref Drifting**. The screenshot is a spot reading on this HD path. Genlocked timing, continuous SDI error logging, exhaustive pixel capture and UHD hardware qualification remain open. [PRISM display during playout](prism-native-bars.jpg)

## Reproduce

Open **Verify video → Test codec profiles and resolutions → Test suite**. Each fixed suite specifies its own rasters and durations. The original codec-by-resolution option also supports a selected raster and full-length tests. Download a previous dashboard report before starting a new run.

The same tests run locally or inside the Docker image.

```sh
python3 profile_matrix.py --report profiles.json
python3 signal_qualification.py generate --report encoders.json
python3 signal_qualification.py editing --report editing.json
python3 signal_qualification.py bars --report bars.json
python3 signal_qualification.py colour --report colour.json
python3 signal_qualification.py convert --report conversions.json
python3 signal_qualification.py proxy --report proxies.json
python3 signal_qualification.py duration --report mov-loops.json
python3 signal_qualification.py aac --report aac-loops.json
python3 -m unittest -q
```

Each suite saves completed cases as it runs and returns a nonzero exit code for a failed measurement. A review finding preserves the measurement and its reason. Critical-system acceptance also needs the specific delivery standard, codec and hardware path used by that system.

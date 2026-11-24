# File verification and scaler qualification

Open **Verify video** to check a completed export or upload a file. A completed export has a saved delivery specification, so the verifier can also compare the measured stream against the requested settings. **Download JSON** saves the measurements. A separate automatic check decodes the finished picture and all audio tracks and checks the length before the application makes an export available for download.

## Qualification results, 24 November 2026

| Environment | Supported cases | Checks passed | Review | Failed | Unsupported |
| --- | ---: | ---: | ---: | ---: | ---: |
| [macOS, FFmpeg 9.0.2](macos-matrix.json) | 277 | 158 | 119 | 0 | 3 |
| [Docker Desktop, Linux arm64, FFmpeg 7.1.5](docker-matrix.json) | 277 | 134 | 143 | 0 | 3 |

All 119 macOS reviews involved identical neighbouring pictures in deliberately static generator fixtures. Docker reported the same 119 static cases and also omitted colour-range metadata for 48 ProRes cases. Twenty-four cases had both findings. All decoded-picture comparisons passed, including the sampled flat patches. Both environments passed the 32-test regression suite, which includes deliberate damage and a separate UHD 60p 4:4:4 conversion.

**Historical 1080p59.94 scenario.** Two ten-second H.264 MOV clips were produced with the pre-QC generator from commit `9ef960b`, one at 8-bit 4:2:0 and one at 10-bit 4:2:2. Both included moving HD bars, overlays and four stereo audio tracks. The deployed converter exported each to ProRes 422 HQ. Every one of the 599 decoded frames per clip matched reference timing. The verifier found zero large errors in sampled flat patches in either clip. The largest fraction of channel samples differing by more than 32 in either half of any frame was 0.1711% for the 8-bit source and zero for the 10-bit source. The original recording with visible damage was unavailable. [Reference measurements](legacy-5994.json)

Three defects were reproducible during qualification.

- Converting a 50i moving sweep to 50p previously produced pairs of frames at the same position. Field-rate deinterlacing now yields 30 distinct consecutive target positions over the 0.6-second fixture.
- Negotiating 10-bit compositing changed bar boundaries relative to the 8-bit source. Selecting a common source sampling format before compositing aligned the bars across profiles.
- A generated 25p 10-bit H.264 MOV fixture failed strict decode on three consecutive Linux runs. Signalling AVC3 and repeating parameter sets for 10-bit AVC in MOV preserved decodability in the fixture. This guard also covers future exports through the dashboard. Decoder success alone cannot detect a validly encoded wrong picture.

## Reproduce the profile sweep

Open **Verify video → Test codec profiles and resolutions**, choose one resolution or all four, then select **Run profile tests**. Each run replaces the latest matrix report. Download the previous report first if you want to keep a history. The fixtures run in a separate temporary directory. Only the report and run log persist in the outputs volume.

The equivalent local command is:

```sh
python3 profile_matrix.py --report matrix.json
```

Use `--resolution 1920x1080` to narrow a run. The default is eight frames per fixture. Increase `--frames` to exercise longer GOPs and durations. The command returns a nonzero exit status for failed cases. A working copy of the report is updated after every case. Both suites can also run inside the deployed container.

```sh
docker compose exec studio python3 -m unittest -v
docker compose exec studio python3 profile_matrix.py --report /app/outputs/manual-matrix.json
docker compose cp studio:/app/outputs/manual-matrix.json ./manual-matrix.json
```

| Path | Coverage at each resolution | Reference |
| --- | --- | --- |
| Generator, custom encoding | H.264 at 8/10 bits and HEVC at 8/10/12 bits, each at 4:2:0, 4:2:2 and 4:4:4 in MOV, MP4 and MPEG-TS | Lossless FFV1 recording of FFmpeg's HD bars at the target raster, with explicit BT.709 tags |
| Generator, editing profiles | Six ProRes and five DNxHR MOV profiles | Same reference, compared across every frame |
| Converter | All 14 presets, including both HEVC proxies | Generated moving 1080p H.264 10-bit 4:2:2 source with timecode, moving marker and four stereo audio tracks |
| DNxHD HQ | 1080p25 in the sweep. Other supported 1080p rates have separate regression tests | Matching 25p moving source |

The four target sizes are 1280×720, 1920×1080, 2560×1440 and 3840×2160. The main sweep uses 60000/1001 progressive frames per second. It has 224 generator cases and 53 supported converter cases. Three other DNxHD raster combinations are recorded as unsupported. The codec sweep uses the default quality and speed, BT.709 and limited range. Separate tests exercise interlace, other rates, ranges, colour spaces, geometry and overlays. The generated reference and encoder both use FFmpeg's bar definitions. Their agreement tests preservation of those definitions and gives no independent certification of the pattern standard.

## Read a file report

| Measurement | How to interpret it |
| --- | --- |
| Inventory | ffprobe reports tracks, codec profile, pixel format, dimensions, frame rate, field order, colour tags, channel layout and any timecode tags. A timecode drawn into the picture is distinct from a timecode track. MediaInfo supplies a second inventory when installed. |
| Decode | Strict FFmpeg decode reads the primary picture and every audio track. Decoded frame counts and scan flags complement the container metadata. A playable header can coexist with damaged slices later in the file. |
| Repeats and freezes | Adjacent equal decoded-picture hashes identify exact repeats in the analysis format. The freeze detector reports near-static periods of at least two seconds at −60 dB. Fixed bars can correctly produce either finding. A moving overlay can conceal a freeze elsewhere in the picture. |
| Levels | The scan records per-plane minima and maxima across all frames in the analysis filter's YUV representation. HD bars include intentional excursions. Use the selected signal specification and a waveform for interpretation. |
| Payload | The report includes an initial packet sample with SHA-256 payload hashes and a sample of H.264/HEVC parameter-set fields when available. This is a diagnostic sample of the beginning of the stream. |
| Result | **Failed** identifies a decode, comparison or contract error. **Review** identifies a finding that needs interpretation, including intentional static pictures or an unreported ProRes range field. **Checks passed** applies to the checks performed. |

To compare picture content, supply a progressive SDR reference of the same shot, start frame, timing and display aspect. When resolutions differ, the verifier resizes the reference with bicubic interpolation for comparison against the converter's Lanczos result. Trimmed, cropped and retimed exports need an independently prepared reference for that edit. The report checks every decoded frame, compares relative timestamps within 1 ms, and measures the upper and lower halves separately. The RGB comparison uses 8-bit samples. Native signal measurements and encoded pixel-format checks provide separate evidence about precision.

The fixture limits are a worst-frame mean absolute channel error of 3 codes per half and at most 0.5% of channel samples differing by more than 32 codes per half. A separate check examines 32 patches distributed across the picture. Where each reference channel varies by at most 3 codes, any difference above 32 raises a finding and records the first affected frame and patch. This catches sparse speckles that a whole-picture mean could hide. These are project regression limits. Film grain, aggressive compression, intended grade changes, errors outside sampled flat patches and low-bit differences need separate evaluation.

## Tools and signal boundaries

| Resource | Use in this workflow |
| --- | --- |
| [ffprobe](https://ffmpeg.org/ffprobe.html) and [MediaInfo](https://mediaarea.net/en/MediaInfo/Download/Mac_OS) | Both CLIs are bundled in Docker. Native installations can use MediaInfo CLI as a second reader. A field missing in one reader stays unreported in its inventory. |
| [FFmpeg filters](https://ffmpeg.org/ffmpeg-filters.html#freezedetect), [frame hashes](https://ffmpeg.org/ffmpeg-formats.html#framemd5) and [trace_headers](https://ffmpeg.org/ffmpeg-bitstream-filters.html#trace_005fheaders) | Used by the verifier. For individual packet bytes, FFprobe also supports a bounded packet dump using `-read_intervals '%+#1' -show_packets -show_data`. |
| [QCTools](https://mediaarea.net/QCTools/How_To_Use) | Companion desktop tool for graph, waveform and vectorscope review at a flagged frame. The upstream [qcli instructions](https://github.com/bavc/qctools#using-qcli) describe generating a QCTools report with `qcli -i clip.mov`. Studio's JSON is a separate format. |
| [BMX](https://github.com/ebu/bmx) | Investigate an MXF containing an ST 436 ancillary essence track with the BMX tools and a known ANC reference. The generator currently writes MOV, MP4 and TS. |
| [TSDuck](https://tsduck.io/commands/) and [libklvanc](https://github.com/stoth68000/libklvanc) | For a TS carrying ST 2038, inspect program/PID mapping and transport continuity, then decode and compare ANC packets and checksums. File inventory alone cannot establish HANC/VANC preservation. Studio's converter maps picture and audio. Its QC report marks ANC checksums as untested. |

## ImagePRO-4K baseline

Barco specifies UHD/60 processing, 4:4:4 support and 10-bit signals, along with independent output sizing and colour correction. Its hardware also provides SDI/HDMI/DP interfaces, genlock and live switching. These establish separate file-processing and physical-signal acceptance criteria. [Barco ImagePRO-4K specifications](https://www.barco.com/en/product/imagepro-4k)

| Capability | Local evidence or remaining acceptance test |
| --- | --- |
| Raster, aspect and sampling conversion | The format sweep measures actual rasters and sample formats. An anamorphic fixture checks black padding, cropped edges and stretching using decoded pixel positions. |
| Scan and rate conversion | The moving-sweep regression requires distinct motion positions on successive 50p frames from a 50i input. The converter supports explicit field dominance for incorrectly flagged sources. Other rate changes use frame selection or repetition. |
| Dirty sources | Strict decode exposes damaged inputs. An intact reference is needed to diagnose validly encoded but wrong pictures. Automatic repair of missing source content would require an agreed concealment policy. |
| Colour performance | Studio checks codec settings, tags, signal statistics and SDR appearance. A 12-bit internal hardware pipeline, LUT behaviour and proprietary scaler response require reference measurements to establish equivalence. |
| Live signal performance | Genlock lock/relock, SDI timing, physical ANC carriage, switching latency and clock drift require measurements on the intended I/O chain. |

For critical-system qualification, specify the standard and edition for each test signal, obtain independent golden vectors, run long-duration and bad-input trials, and compare decoded results and device output on the target hardware. The file suite provides repeatable evidence for the covered cases.

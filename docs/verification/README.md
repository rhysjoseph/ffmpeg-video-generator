# File verification and scaler qualification

Open **Verify video** to check a completed export or upload a file. A completed export has a saved delivery specification, so the verifier can also compare the measured stream against the requested settings. **Download JSON** saves the measurements. A separate automatic check decodes the finished picture and all audio tracks and checks the length before the application makes an export available for download. Completed exports also pass a decoded-frame check for cadence, colour signalling and field dominance against the export settings.

## Signal and conversion qualification

The [Shogun Classic SDI return test](shogun-sdi-return-1080p50.md) captured 1,800 frames of the updated 1080p50 export. It identifies four bottom-edge artefact timecodes and measures a stereo tone interruption at all three loop joins. The [original flicker investigation](shogun-flicker.md) documents the earlier frame-43 failure and the local checks at all fifteen reported positions.

The [DXD-8 reference benchmark](decklink-reference-sweep.md) records which reference locked the UltraStudio for each SDI format, how PRISM measured its phase against PTP, and the results for generated and converted video at the loop joins.

The [DeckLink format sweep](decklink-format-sweep.md) covers all 40 monitor files, 40 ProRes HQ scaler outputs and the 13 native SDI formats shared by the dashboard and the UltraStudio HD Mini. It includes the 1080p59.94 loop measurements and a 720p payload-identifier finding.

The [1080p50 DeckLink benchmark](decklink-1080p50.md) compares SDI payload identifiers from the Shogun and UltraStudio and traces the lower-right white patch through encoding and physical playout.

The November follow-up measures native HD bar codes, independent SDR colour transforms, picture timestamps and decoded colour signalling. It covers all four lengths, the codec-by-resolution sweep and conversion from both limited- and full-range test sources. The measurements, exceptions and reproduction commands are in the [signal qualification report](signal-qualification.md).

## Earlier profile qualification, 24 November 2026

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

## Full-length exports and the SDI bench

The duration suite generates moving 1920×1080 H.264 10-bit 4:2:2 MOV at 60000/1001 fps, converts it to ProRes 422 HQ and compares every converted picture against its source. Both files carry four stereo PCM tracks. Each duration ran through the macOS and Docker builds. Neither build found decoder errors, repeated neighbouring frames or large sampled flat-patch errors in these moving-picture conversions. The regression suite passed 35 tests on each host. Docker flagged the unreported ProRes colour-range field at all four lengths. [macOS results](macos-durations.json) · [Docker results](docker-durations.json)

| Dashboard length | Normal export frames | Seamless loop frames | Loop duration at 59.94p | UltraStudio → PRISM |
| --- | ---: | ---: | ---: | --- |
| 10 s | 599 | 600 | 10.010 s | [10-second capture](sdi-10s.jpg) |
| 30 s | 1,798 | 1,800 | 30.030 s | [30-second capture](sdi-30s.jpg) |
| 60 s | 3,596 | 3,600 | 60.060 s | [60-second capture](sdi-60s.jpg) |
| 120 s | 7,193 | 7,200 | 120.120 s | [120-second capture](sdi-120s.jpg) |

The four SDI runs used separately labelled H.264-to-ProRes conversions at the ordinary durations. Each played to end of stream. In all four midpoint measurements PRISM reported 1080p59.94, SDR Rec.709, YCbCr 4:2:2 10-bit and SMPTE 425 Level A with green CRC status. Eight embedded channels metered approximately −20 dBFS. The captures are spot measurements. PRISM reported **Video/Ref Drifting** against its locked PTP reference. Desktop Video Setup showed no external reference at the UltraStudio. Facility genlock and a frame-by-frame capture of the physical output remain open qualifications.

**Device discovery.** macOS enumerated the UltraStudio HD Mini on Thunderbolt 3 at 40 Gb/s while Desktop Video 16.5 was waiting for extension approval. After the Blackmagic Network, Camera and BlackmagicIO extensions became active, Desktop Video Setup and the vendor's device list recognised the unit and the latter reported current firmware. Desktop Video initially selected dual-link output, and the single-cable receiver showed 1080i59.94. Selecting **Single Link** and **SMPTE Level A** delivered progressive 59.94 on SDI 1. The PRISM layout uses Video Session, Picture, Waveform and Audio. Its previous layout used IP Status, Picture, IP Session and Timing. [Blackmagic Desktop Video manual](https://documents.blackmagicdesign.com/UserManuals/DesktopVideoManual.pdf)

**Audio routing.** The generated file measured −20 dBFS on each of eight decoded channels. In this setup, Media Express sent tone on channels 1–2 with both four stereo tracks and a single interleaved eight-channel PCM track. Selecting channels 1–8 in the Media Express UI did not resolve it. The native GStreamer 1.28 DeckLink output delivered all eight from the interleaved version over the same cable. Identical tones establish level and presence. Identifying channel swaps would require distinct tones or identifiers. [Four-pair Media Express result](prism-1080p5994.jpg) · [Eight-channel Media Express control](prism-8ch.jpg) · [Direct DeckLink result](prism-decklink.jpg)

### Seamless loops

Select **Seamless loop** in the generator and choose a **MOV** output for PCM audio. Motion completes whole cycles over the selected duration. The running timecode is hidden so its displayed value cannot jump backwards at the join. At fractional rates the generator uses an integral number of nominal seconds of frames. This keeps the specified raster timing, 48 kHz sample rate and 1 kHz test tone exact. The dashboard shows the resulting wall-clock duration. The generated file repeats when the player loops it. A full-length conversion that retains timing can preserve the seam. Trims, frame-rate changes and arbitrary source cuts need a fresh check.

In **Verify video**, select **Check loop boundary** for an uploaded file or conversion. Saved loop-mode generator exports receive this check automatically when verified. The report compares the last-to-first picture difference with adjacent steps after scaling to 320×180 RGB. For each audio channel it measures the decoded sample step across the join and compares audio length with picture duration. An intentional lip-sync flash can trigger picture review. A small object jumping position can evade a whole-frame average. A regression test separately tracks marker and sweep positions. MP4 and TS exports use AAC, for which audible joins depend on how the player handles priming and padding. A separate ten-second sweep exercised all seven generator patterns. The intentional lip-sync flash triggered picture review, interlaced sweep motion passed, and the MPEG-TS/AAC case decoded with 1,824 extra audio samples (38 ms). The MP4/AAC case had aligned lengths in the tested decoder. [Pattern and container measurements](pattern-loops.json)

All four loop-mode durations passed the macOS H.264-to-ProRes comparison with zero repeated neighbouring pictures, zero large differences in sampled flat patches and zero audio-length error on every track. The deployed Docker dashboard also generated and verified a 23.98p H.264 MOV loop at the 10-second setting. It measured 240 pictures, 480,480 stereo PCM samples per channel and zero sample offset in both start and duration.

The hardware loop test repeated the same nominal 10-second ProRes MOV three times through one continuously open DeckLink output. The byte stream fed to the player contained 1,800 decoded pictures with exactly 1,001 ticks per step on a 60,000 Hz clock. Each 600-frame block had the same sequence of decoded hashes. All three eight-channel PCM blocks were byte-identical, with 480,480 samples per channel per block and continuous packet timestamps. The PRISM showed progressive video, green CRC status and eight active channels around the two joins. [Loop measurements](macos-loops.json) · [Three-cycle playout measurements](three-cycle-playout.json) · [PRISM after the second join](sdi-loop.jpg)

Run the full-length checks with:

```sh
python3 duration_tests.py --report durations.json
python3 duration_tests.py --loop --report loops.json --keep-dir outputs/loop-durations
```

For native hardware playback of a retained four-pair loop, interleave its PCM tracks and use the explicit 10-bit and eight-channel DeckLink sinks. The example plays three cycles and requires exclusive access to the selected output. Device 0 was the only Blackmagic video device on the qualification host. The Docker image handles file generation and verification. [GStreamer DeckLink audio sink](https://gstreamer.freedesktop.org/documentation/decklink/decklinkaudiosink.html) · [GStreamer DeckLink video sink](https://gstreamer.freedesktop.org/documentation/decklink/decklinkvideosink.html)

```sh
gstbin=/Library/Frameworks/GStreamer.framework/Versions/1.0/bin
ffmpeg -v error -stream_loop 2 -i outputs/loop-durations/prores-hq-10s.mov \
  -filter_complex '[0:a:0][0:a:1][0:a:2][0:a:3]join=inputs=4:channel_layout=7.1:map=0.0-FL|0.1-FR|1.0-FC|1.1-LFE|2.0-BL|2.1-BR|3.0-SL|3.1-SR[a]' \
  -map 0:V:0 -map '[a]' -c:v copy -c:a pcm_s24le -video_track_timescale 60000 \
  -movflags +empty_moov+default_base_moof+frag_keyframe -frag_duration 250000 -f mov pipe:1 | \
  "$gstbin/gst-launch-1.0" fdsrc fd=0 ! qtdemux name=d \
    d.video_0 ! queue ! avdec_prores ! videoconvert ! video/x-raw,format=v210 ! \
    decklinkvideosink device-number=0 mode=1080p5994 video-format=10bit-yuv mapping-format=level-a async=false \
    d.audio_0 ! queue ! audioconvert ! audio/x-raw,format=S32LE,channels=8,rate=48000 ! \
    decklinkaudiosink device-number=0 async=false
```

## Reproduce the profile sweep

Open **Verify video → Test codec profiles and resolutions**, choose a resolution and test length, then select **Run profile tests**. Each run replaces the latest matrix report. Download the previous report first if you want to keep a history. The fixtures run in a separate temporary directory. Only the report and run log persist in the outputs volume.

The equivalent local command is:

```sh
python3 profile_matrix.py --report matrix.json
```

Use `--resolution 1920x1080` to narrow a run. The default is eight frames per fixture. Use `--duration 10`, `30`, `60` or `120` for real-time lengths across all selected profiles, or use `--frames` to specify a frame count. The command returns a nonzero exit status for failed cases. A working copy of the report is updated after every case. Both suites can also run inside the deployed container.

```sh
docker compose exec studio python3 -m unittest -v
docker compose exec studio python3 profile_matrix.py --report /app/outputs/manual-matrix.json
docker compose cp studio:/app/outputs/manual-matrix.json ./manual-matrix.json
```

| Path | Coverage at each resolution | Reference |
| --- | --- | --- |
| Generator, custom encoding | H.264 at 8/10 bits and HEVC at 8/10/12 bits, each at 4:2:0, 4:2:2 and 4:4:4 in MOV, MP4 and MPEG-TS | Lossless FFV1 recording of the generator's HD plate at the target raster with explicit BT.709 tags. The original sweep used FFmpeg's HD bars |
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

To compare picture content, supply an SDR reference of the same shot, start frame, timing and display aspect. Woven interlaced comparisons require matching rasters and decoded field dominance. When resolutions differ, the verifier resizes the reference with bicubic interpolation for comparison against the converter's Lanczos result. Trimmed, cropped and retimed exports need an independently prepared reference for that edit. The report checks every decoded frame, compares relative timestamps within 1 ms, and measures the upper and lower halves separately. The RGB comparison uses 8-bit samples. Native signal measurements and encoded pixel-format checks provide separate evidence about precision.

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

# Pattern Studio

A local FFmpeg test-pattern generator and video converter for macOS, with a browser interface at **http://localhost:9191**. Videos and settings stay on your computer; no account or external services are needed.

## Start

Double-click **Start.command** in Finder, then open **http://localhost:9191**. Keep its Terminal window open while rendering. Press Control-C in that window to stop the server.

Alternatively, from this directory:

```sh
python3 app.py
```

Requirements: Python 3.10+, FFmpeg with libx264, ffprobe, and Pillow. They are already available on the Mac used to build this project. On another Mac:

```sh
brew install python ffmpeg
python3 -m venv .venv
.venv/bin/python3 -m pip install -r requirements.txt
.venv/bin/python3 app.py
```

The launcher uses an existing `.venv`, or the current Python if Pillow is available. Otherwise it creates `.venv` and installs Pillow. You can override the binaries using `FFMPEG_PATH` and `FFPROBE_PATH`. The server binds only to `127.0.0.1`, using port 9191 by default; use `--port` to change it.

## Use

1. Choose a pattern, resolution, rate and duration.
2. Toggle timecode and the moving freeze marker; optionally enter a label.
3. Choose audio channels, tone level and a **Container / output format**.
4. Use **Refresh frame** to see an actual FFmpeg-rendered first frame, then **Generate video**.
5. Download the finished video from Recent exports, or find it directly in `outputs/` beside this script.

One render runs at a time. The page shows progress and supports cancellation. Completed files have unique names and are never overwritten. A JSON sidecar records settings and ffprobe stream details. Recent exports survive a server restart. Closing the browser does not stop an active render. Large UHD renders may take a while; the H.264 encoder uses four threads and HEVC uses a four-thread worker pool to leave resources for the rest of your Mac.

## Generator output formats

The generator's **Audio & output → Container / output format** selector includes:

- MP4, MOV and MPEG-TS with custom H.264 / HEVC encoding.
- Apple ProRes Proxy, LT, 422, 422 HQ, 4444 and 4444 XQ in MOV.
- Avid DNxHR LB, SQ, HQ, HQX and 444 in MOV.

Editing profiles automatically set codec, bit depth, chroma and limited range, and use 48 kHz, 24-bit PCM audio. They retain the chosen stereo or four stereo tracks. Quality and encoding-speed controls apply to custom H.264 / HEVC exports; editing profiles use their own compression settings. Returning to custom encoding restores your previous settings. Profiles unavailable in the installed FFmpeg are disabled.

ProRes supports progressive and interlaced output with the selected field order. DNxHR requires a progressive frame rate. ProRes 422 profiles use 10-bit 4:2:2 input; 4444/XQ use 10-bit 4:4:4 input and decode as 12-bit, with an opaque picture. DNxHR LB/SQ/HQ use 8-bit 4:2:2; HQX uses 10-bit 4:2:2 and 444 uses 10-bit 4:4:4. These editing formats produce larger files. ProRes RAW encoding is unavailable.

## Logo overlays

In the generator's **Burn-in overlays → Logo overlay** controls, upload a PNG, JPEG, WebP, TIFF or BMP. PNG/WebP transparency is preserved. Set corner/centre placement, width (2–50% of video width), opacity and margin. Aspect ratio is retained and logo height is capped at half the frame. Margin is a percentage of the shorter frame edge. Refresh the preview to inspect placement. The freeze marker stays above the logo.

Uploads are limited to 25 MB and 20 megapixels; logos are orientation-corrected, normalised to RGBA PNG and capped at 4096 pixels on the longer side. Logos are treated as SDR artwork. Remove overlay disables it without deleting the saved local upload.

## Video converter

Choose the **Video converter** tab and upload a local video (up to 20 GB). The app displays its codec, dimensions, frame rate, duration and audio-track count, then prepares a validated conversion plan.

Available output presets:

- Apple ProRes Proxy, LT, 422, 422 HQ, 4444 and 4444 XQ → MOV.
- Avid DNxHD HQ → MOV, restricted to 1920×1080 at 23.98, 24, 25, 29.97 or 30p. Bitrate is selected automatically: 175, 185 or 220 Mbit/s as appropriate.
- Avid DNxHR LB, SQ, HQ, HQX and 444 → MOV, including UHD/custom dimensions.
- H.265/HEVC proxy at 8 or 10 bits → MP4, with CRF and speed controls.

**Apple ProRes RAW encoding is unavailable in FFmpeg and is not substituted with regular ProRes.** RAW inputs are rejected here; develop them in a compatible application first. Standard ProRes 4444/XQ use this encoder's 10-bit input and may decode as 12-bit; this is not native 12-bit source processing. Conversion currently flattens/discards source alpha, including in 4444 output.

Choose source size, a standard size or even custom dimensions from 128–8192 pixels (DNxHR needs width ≥256). Aspect handling offers fit with black bars, centre crop, or stretch. Source sample aspect ratio and rotation are accounted for, and output uses square pixels. Frame-rate conversion duplicates/drops frames, preserving playback speed and audio pitch; it does not use optical-flow interpolation. Match source rate uses the average rate to make a constant-frame-rate file. All converted output is progressive; automatic deinterlacing processes flagged interlaced frames, while Always handles sources with missing/incorrect flags.

Trim start/length are in seconds; length 0 means to the end. All audio tracks are retained by default: 48 kHz 24-bit PCM in MOV, 48 kHz AAC in proxies. Audio can be removed. Subtitles, chapters, data tracks and extra video streams are not copied. The first non-attached-picture video stream is used.

Output colour is limited-range YUV. Source colour primaries, matrix and transfer are retained where recognised; missing/unsupported tags use BT.709 defaults. HDR transfer tags are retained without tone mapping or a guarantee of preserving every HDR mastering metadata item. SDR logos are colour-converted for SDR source profiles. Logo compositing onto HDR footage is blocked to avoid inserting incorrectly mapped artwork; convert without a logo or use a separate colour-managed workflow.

To reuse the generator's logo, enable **Use uploaded logo** on the conversion tab. Its placement and size controls are shared with the generator. Source uploads are working copies: originals stay unchanged. Working copies and logo files remain in `uploads/`; outputs and metadata remain in `outputs/`. A refresh resets the current upload selection but retains local files. You can remove unused working copies from `uploads/` while the app is stopped. Large intermediate codecs need substantial output disk space.

Conversions and pattern generation share the same single-job queue, progress display, cancellation and recent exports. Neither overwrites a source file.

## Signal details

| Setting | Output |
| --- | --- |
| HD SMPTE Bars | FFmpeg `smptehdbars`, based on SMPTE RP 219-2002 |
| SMPTE Bars | FFmpeg `smptebars`, based on EG 1-1990 |
| PAL 75% / 100% | FFmpeg `pal75bars` / `pal100bars`, EBU PAL levels |
| Moving Colour Bars | HD bars, horizontal scroll with an eight-second cycle |
| Lip Sync | White flash and short 1 kHz beep at the same timestamps, repeating every nominal second |
| Side Sweep | White vertical bar moving left to right, with a two-second cycle |
| Resolutions | 3840×2160, 2560×1440, 1920×1080, 1280×720 |
| Progressive rates | 24000/1001 (23.98), 24, 25, 30000/1001 (29.97), 30, 50, 60000/1001 (59.94), 60 fps |
| Interlaced rates | 50i = 25 frames / 50 fields per second; 59.94i = 30000/1001 frames / 60000/1001 fields per second |
| Duration | 10, 30, 60 or 120 seconds; video duration rounds to a whole frame |
| Video encoding | H.264 or HEVC; Auto selects H.264 for 8/10-bit and HEVC for 12-bit |
| Pixel format | 8, 10 or 12-bit; 4:2:0, 4:2:2 or 4:4:4 |
| Colour | SDR BT.709, BT.2020, BT.601 PAL or BT.601 NTSC; limited or full range |
| Quality / speed | CRF 10 (Maximum), 16 (High), 23 (Compact); ultrafast, fast, medium or slow |
| MOV audio | 48 kHz, 24-bit PCM |
| MP4 / MPEG-TS audio | 48 kHz AAC, 256 kbit/s per stereo pair |

PAL and classic SMPTE source matrices are normalised to a BT.709 working space. The completed picture is converted to the selected output matrix, primaries, transfer and range, with matching metadata. Colour conversion uses FFmpeg’s `colorspace` filter. These are compressed diagnostic videos, not lossless reference masters or certified calibration signals. All profiles are SDR: selecting BT.2020 does not enable PQ, HLG or HDR mastering metadata.

Interlaced output weaves alternating scanlines from distinct source frames and supports top or bottom field first. Motion and compositing are calculated at field rate; the timecode holds the same frame number across both fields. Chroma sampling happens before weaving to avoid mixing distinct field times. Interlace is supported with H.264 at 8 or 10 bits. HEVC / 12-bit output requires a progressive frame rate; incompatible selections are blocked by both the page and the renderer. 1080 is the conventional interlaced HD delivery size; other requested resolutions remain available but may be rejected by broadcast equipment. Some players deinterlace automatically, while others display combing. The requested `69.94i` was corrected to `59.94i` with confirmation.

### Timecode and text

Drop-frame timecode starts at `00:00:00;00` for **29.97p, 59.94p and 59.94i**. It skips two frame numbers per minute at 29.97 fps, or four at 59.94 fps, except every tenth minute. Other rates use non-drop timecode starting at `00:00:00:00`; there is no standard drop-frame mode for those rates. The 59.94p counter runs 00–59; interlaced timecode counts complete frames. Timecode is burned into the picture, not provided as an ancillary or dedicated timecode track.

Pillow renders the text as a small video strip piped to FFmpeg, so FFmpeg's optional `drawtext` filter is not required. Labels are literal text, support Unicode where the installed font has glyphs, and shrink to fit. The freeze box moves diagonally and reflects off all four picture boundaries without wrapping. At Normal speed it traverses the width in three seconds and the height in two seconds; Slow halves the speed and Fast doubles it. A black outline keeps it visible against the bars. The marker is drawn above the text overlays, so it remains visible when crossing them.


### Bit depth, chroma and encoding

All nine depth/chroma combinations are available with HEVC in MP4, MOV and MPEG-TS. H.264 supports 8/10-bit at all three chroma settings. Auto chooses H.264 for 8/10-bit and HEVC for 12-bit. The app checks the installed encoder’s pixel-format support and probes the actual output; it rejects an unexpected downgrade. Old exports retain their original formats.

The FFmpeg bar sources and Pillow text originate at 8-bit precision. Higher-depth output is real 10/12-bit encoding and adds precision during colour conversion; it does not turn the built-in sources into native 10/12-bit calibration ramps. Compositing retains 4:4:4 chroma (10-bit working precision for higher-depth exports), then converts to the requested output format. The browser preview is an 8-bit SDR representation of the selected colour output.

Limited range uses nominal luma 16–235 and chroma 16–240 at 8-bit, scaled by 4 at 10-bit and 16 at 12-bit. Full range spans 0–255, 0–1023 or 0–4095. BT.2020 uses the SDR BT.2020-10 transfer flag at 8/10 bits and BT.2020-12 at 12 bits. PAL and NTSC profiles use their respective BT.601 matrix/primaries and SMPTE 170M transfer.

Maximum / High / Compact select CRF 10 / 16 / 23; lower CRF favours fidelity and larger files. These are lossy settings, and equal CRF values are not identical quality across codecs. Slower presets generally improve compression efficiency. Hardware players and QuickTime may not support high-depth or 4:2:2/4:4:4 profiles; use a compatible NLE or decoder.

### Audio

Every selected channel carries the same in-phase 1 kHz sine tone. The eight-channel option writes **four independent stereo audio tracks**, ordered 1–2, 3–4, 5–6 and 7–8. It is not a 7.1 surround track. A normal media player may play only its selected stereo track; an NLE or broadcast tool can access all four pairs.

Levels are sine-wave **sample peaks**, using amplitude `10^(dBFS/20)`. The mathematical RMS level is 3.01 dB lower. Choose MOV for uncompressed, precise audio levels: AAC encoding can change decoded sample peaks and introduces codec delay/padding. Silence retains all chosen channels with zero-valued source samples.

Lip Sync gates the tone to match the flash. Each pulse lasts approximately 80 ms, rounded to a whole output frame, starting at frame zero. The cycle is 24/25/30/50/60 frames depending on the rate; fractional-rate cycles last 1.001 seconds. The image and source audio start together; at interlaced rates the flash spans both fields. Silence disables the audible cue.

## Verification

```sh
python3 -m unittest -v
```

Tests render actual samples for all seven patterns, all ten rates, all three containers and all eleven generator editing profiles. They check all nine depth/chroma combinations in HEVC, all six in H.264, colour tags and actual limited/full-range sample values, decoded progressive/interlaced flags, top/bottom field order, four-edge marker positions, four stereo tracks, PCM tone frequency and peak levels, silence, drop-frame boundaries, lip-sync timing, labels and previews.

Pattern and interlace definitions follow the [official FFmpeg filter documentation](https://ffmpeg.org/ffmpeg-filters.html). FFmpeg and ffprobe must be in PATH or supplied via the environment variables above.

HEVC interlace restrictions follow the [x265 field-input documentation](https://x265.readthedocs.io/en/master/cli.html#cmdoption-interlace).

Media tests additionally cover every conversion preset, DNxHD rate constraints, audio-track retention, trimming, mute, aspect modes, transparent logos, and logo overlays on high-depth patterns.

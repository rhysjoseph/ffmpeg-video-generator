"""Exercise every named delivery profile at every generator resolution with decoded test pictures."""
import argparse
from dataclasses import replace
from fractions import Fraction
import json
from pathlib import Path
import subprocess
import tempfile

import assets
from delivery import PROBE_PROFILES, generation_profiles
from engine import DURATIONS, FFMPEG, RESOLUTIONS, Settings, render
from transcode import ConvertSettings, PRESETS, convert
from verification import verify


RATE = Fraction(60000, 1001)


def contract(codec, pixel, raster, fps, frames, container, profile):
    width, height = map(int, raster.split("x"))
    return {"codec_name": codec, "pix_fmt": pixel, "width": width, "height": height, "fps": str(fps),
            "field_order": "progressive", "color_space": "bt709", "color_range": "tv",
            "profile": profile, "frames": frames, "container": "mpegts" if container == "ts" else container,
            "audio_tracks": 4, "audio_channels": [2]*4,
            "audio_codecs": ["pcm_s24le" if container == "mov" else "aac"]*4}


def run_matrix(root, frames, rasters, output, duration=None):
    cases = []
    partial = output.with_suffix(".partial.json")
    def record(case):
        if duration is not None:
            case["duration_seconds"] = duration
        cases.append(case)
        # Keep completed evidence if the long run is interrupted.
        partial.write_text(json.dumps(cases, indent=2) + "\n")
        partial.replace(output)
        print(case["mode"], case["profile"], case["resolution"], case["status"], flush=True)

    def exercise(mode, key, raster, fn, expected, ref, extension):
        target = root / ("output." + extension)
        try:
            fn(target)
            report = verify(target, reference=ref, expected=expected, details=False)
            case = {k: report[k] for k in ("status","errors","review","scan","comparison") if k in report}
            if "inventory" in report:
                v = report["inventory"]["streams"][0]
                case["measured"] = {k: v.get(k) for k in ("codec_name","profile","pix_fmt","width","height","r_frame_rate")}
        except (ValueError, RuntimeError, OSError, subprocess.SubprocessError) as exc:
            case = {"status": "failed", "errors": [str(exc)]}
        record({"mode": mode, "profile": key, "resolution": raster, **case})

    base = Settings(audio="four_pairs", rate="59.94p", timecode=False, freeze_box=False,
                    duration=duration or 10)
    sources = {}
    for rate, fps in (("59.94p", RATE), ("25p", Fraction(25))):
        source = root / "legacy.mov"
        render(replace(base, rate=rate, pattern="scroll", timecode=True, freeze_box=True,
                       bit_depth=10, chroma="422", container="mov"), source,
               duration=None if duration else float(frames/fps))
        ident = ("a" if rate == "25p" else "b")*32
        assets.register_upload(source, ident, "video", "legacy-pattern.mov")
        sources[rate] = ident, assets.asset(ident, "video")[0]

    main_frames = round(duration * RATE) if duration else frames

    for raster in rasters:
        ref = root / "bars.mkv"
        subprocess.run([FFMPEG, "-v", "error", "-y", "-f", "lavfi", "-i", f"smptehdbars=size={raster}:rate={RATE},format=yuv444p,"
                        "setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709",
                        "-frames:v", str(main_frames), "-c:v", "ffv1", "-threads", "4", "-color_range", "tv",
                        "-colorspace", "bt709", "-color_trc", "bt709", "-color_primaries", "bt709", str(ref)], check=True)
        variants = []
        for codec in ("h264", "hevc"):
            for depth in ((8, 10) if codec == "h264" else (8, 10, 12)):
                for chroma in ("420", "422", "444"):
                    for ext in ("mp4", "mov", "ts"):
                        key = f"{codec}-{depth}bit-{chroma}-{ext}"
                        variants.append((key, replace(base, codec=codec, container=ext, bit_depth=depth, chroma=chroma)))
        for key, p in generation_profiles().items():
            variants.append((key, replace(base, delivery_profile=key, container="mov",
                                          bit_depth=p["bit_depth"], chroma=p["chroma"])))
        for key, settings in variants:
            settings = replace(settings, resolution=raster)
            codec = {"libx264":"h264","libx265":"hevc","prores_ks":"prores","dnxhd":"dnxhd"}[settings.encoder]
            pixel = "yuv444p12le" if key in ("prores_4444","prores_xq") else settings.pixel_format
            if codec == "h264":
                profile = {"444":"High 4:4:4 Predictive", "422":"High 4:2:2",
                           "420":"High 10" if settings.bit_depth == 10 else "High"}[settings.chroma]
            elif codec == "hevc":
                profile = {(8,"420"):"Main", (10,"420"):"Main 10"}.get((settings.bit_depth, settings.chroma), "Rext")
            else:
                profile = PROBE_PROFILES[key]
            expected = contract(codec, pixel, raster, RATE, main_frames, settings.container, profile)
            exercise("generate", key, raster, lambda p: render(settings, p, duration=None if duration else float(frames/RATE)),
                     expected, ref, settings.container)

        for key, (_, encoder, _, pixel, container) in PRESETS.items():
            if key == "dnxhd_hq" and raster != "1920x1080":
                record({"mode":"convert", "profile":key, "resolution":raster, "status":"unsupported",
                        "reason":"DNxHD HQ preset requires 1920x1080."})
                continue
            rate = "25p" if key == "dnxhd_hq" else "59.94p"
            ident, source = sources[rate]
            s = ConvertSettings(source_id=ident, profile=key, resolution=raster)
            codec = {"prores_ks":"prores","libx265":"hevc","dnxhd":"dnxhd"}[encoder]
            fps = 25 if rate == "25p" else RATE
            expected = contract(codec, "yuv444p12le" if key in ("prores_4444","prores_xq") else pixel,
                                raster, fps, round(duration * fps) if duration else frames, container, PROBE_PROFILES[key])
            exercise("convert", key, raster, lambda p: convert(s, p), expected, source, container)
    return cases


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    length = parser.add_mutually_exclusive_group()
    length.add_argument("--frames", type=int, default=8)
    length.add_argument("--duration", type=int, choices=DURATIONS, help="Use the full dashboard duration in seconds.")
    parser.add_argument("--resolution", action="append", choices=RESOLUTIONS)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    if args.frames < 4:
        parser.error("Use at least four frames per fixture.")
    with tempfile.TemporaryDirectory(prefix="profile-matrix-") as temp:
        assets.UPLOADS = Path(temp)  # The matrix runs in its own process.
        results = run_matrix(Path(temp), args.frames, args.resolution or list(RESOLUTIONS), args.report, args.duration)
    raise SystemExit(int(any(c["status"] == "failed" for c in results)))

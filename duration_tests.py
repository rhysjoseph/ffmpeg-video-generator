"""Qualify the 1080p59.94 H.264 to ProRes HQ path at every dashboard duration."""
import argparse
from dataclasses import asdict
from fractions import Fraction
import json
import shutil
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid

import assets
from engine import DURATIONS, Settings, probe, render
from transcode import ConvertSettings, convert, plan
from verification import check_contract, export_expectations, tool_versions, validate_export, verify


def audio_durations(info):
    return [float(int(s["duration_ts"]) * Fraction(s["time_base"]))
            for s in info["streams"] if s["codec_type"] == "audio"]


def exercise(seconds, directory, loop=False, keep=None):
    settings = Settings.parse(dict(duration=seconds, rate="59.94p", pattern="scroll", container="mov",
                                   bit_depth=10, chroma="422", audio="four_pairs", seamless_loop=loop))
    source = directory / "generated.mov"
    target = directory / "converted.mov"
    render(settings, source)
    info = probe(source)
    gate = validate_export(source, settings.runtime, settings.fps, lambda proc: None, threading.Event())
    frames = round(settings.runtime * settings.fps)
    expected = export_expectations({"settings": asdict(settings)})
    errors, review = check_contract(info, {**expected, "frames": frames}, gate["frames_decoded"])
    ident = uuid.uuid4().hex
    assets.register_upload(source, ident, "video", source.name)
    source, _ = assets.asset(ident, "video")
    preset = ConvertSettings.parse(dict(source_id=ident, profile="prores_hq"))
    expected = export_expectations({"kind": "conversion", "settings": asdict(preset), "conversion": plan(preset)})
    convert(preset, target)
    report = verify(target, reference=source, expected={**expected, "frames": frames}, details=False, loop=loop)
    audio = {"generated": audio_durations(info), "converted": audio_durations(probe(target))}
    for stage, lengths in audio.items():
        if any(abs(length - settings.runtime) > 1 / settings.fps for length in lengths):
            errors.append(f"{stage} audio duration differs from the selected length by more than one frame.")
    errors.extend(report["errors"])
    review.extend(report["review"])
    extra = {}
    if loop and "loop_boundary" in report:
        boundary = report["loop_boundary"]
        extra = {"loop_boundary": boundary, "cycle_seconds": settings.runtime}
        # A full cycle of the -20 dBFS, 1 kHz tone at 48 kHz wraps from -428 to 0 in s16.
        for track in boundary["audio"]:
            if track["offset_from_video_samples"] or any(abs(step-428)>2 for step in track["join_step_s16"]):
                errors.append(f"Track {track['stream']} did not wrap at the expected tone phase.")
    if keep is not None and not errors:
        keep.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(target, keep / f"prores-hq-{seconds}s.mov")
    return {**extra, "status": "failed" if errors else "review" if review else "checks passed",
            "errors": errors, "review": review, "expected_frames": frames, "generated": gate,
            "audio_seconds": audio, "converted": report.get("scan"), "comparison": report.get("comparison")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--loop", action="store_true", help="Test seamless motion and PCM tone cycles.")
    parser.add_argument("--keep-dir", type=Path, help="Keep the converted fixtures for hardware playout.")
    args = parser.parse_args()
    results = {"tools": tool_versions(), "cases": []}
    for seconds in DURATIONS:
        print(f"Testing {seconds} seconds", flush=True)
        with tempfile.TemporaryDirectory(prefix="pattern-duration-") as temp:
            assets.UPLOADS = Path(temp)
            try:
                case = exercise(seconds, Path(temp), args.loop, args.keep_dir)
            except (RuntimeError, ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
                case = {"status": "failed", "errors": [str(exc)]}
        results["cases"].append({"seconds": seconds, **case})
        args.report.write_text(json.dumps(results, indent=2) + "\n")
        print(seconds, case["status"], case["errors"], flush=True)
    raise SystemExit(int(any(case["status"] == "failed" for case in results["cases"])))

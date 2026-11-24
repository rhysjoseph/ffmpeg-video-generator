"""File QC for the dashboard and the profile matrix. All paths belong to the caller."""
import argparse
from contextlib import ExitStack
from fractions import Fraction
from functools import lru_cache
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading

from PIL import Image, ImageChops
from engine import FFMPEG, FFPROBE, probe
from delivery import PROBE_PROFILES


@lru_cache(maxsize=1)
def tool_versions():
    result = {}
    for name, command, flag in (("ffmpeg", FFMPEG, "-version"), ("ffprobe", FFPROBE, "-version"),
                                ("mediainfo", shutil.which("mediainfo"), "--Version")):
        if command:
            lines = subprocess.check_output([command, flag], text=True, timeout=10).strip().splitlines()
            result[name] = lines[-1] if name == "mediainfo" else lines[0]
    return result


def primary(info):
    for stream in info["streams"]:
        if stream["codec_type"] == "video" and not stream.get("disposition", {}).get("attached_pic"):
            return stream
    raise ValueError("No picture stream found.")


def decode_input(path):
    return [FFMPEG, "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-err_detect", "explode",
            "-threads", "4", "-filter_threads", "2", "-protocol_whitelist", "file,pipe", "-i", str(path)]


def validate_export(path, duration, fps, started, cancel):
    """Strictly decode the primary picture and every audio track before publication."""
    args = decode_input(path) + ["-map", "0:V:0", "-map", "0:a?", "-fps_mode", "passthrough",
                                 "-progress", "pipe:1", "-nostats", "-f", "null", "-"]
    with tempfile.TemporaryFile() as log:
        with subprocess.Popen(args, stdout=subprocess.PIPE, stderr=log, text=True) as proc:
            started(proc)
            count = 0
            for line in proc.stdout:
                if line.startswith("frame="):
                    count = int(line.partition("=")[2])
            code = proc.wait()
        if cancel.is_set():
            raise InterruptedError("Verification cancelled.")
        log.seek(0)
        error = log.read(2000).decode(errors="replace").strip()
        if code or error or count < 1:
            raise RuntimeError("Export failed strict decode. " + error)
        if abs(count - duration * float(fps)) > 1.01:
            raise RuntimeError(f"Unexpected decoded length: {count} frames at {fps} fps for {duration} seconds.")
        return {"frames_decoded": count, "audio_decode": "all mapped tracks", "decoder_errors": 0}


def scan(path, video, directory, has_audio):
    # Keep per-frame records on temporary disk and bound the dashboard response.
    filters = "freezedetect=n=-60dB:d=2,signalstats,metadata=print:file=levels"
    args = decode_input(path) + ["-map", f"0:{video['index']}", "-vf", filters, "-fps_mode", "passthrough",
                                 "-threads", "2", "-f", "framemd5", "hashes"]
    args += ["-map", "0:a", "-f", "null", "-"] if has_audio else []
    result = subprocess.run(args, cwd=directory, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=3600)
    if result.returncode or result.stderr.strip():
        raise ValueError("Decode/analysis failed: " + result.stderr.decode(errors="replace")[-1500:])
    previous = None
    frames = repeats = 0
    with (directory / "hashes").open() as hashes:
        for line in hashes:
            if not line.startswith("#"):
                digest = line.rsplit(",", 1)[-1].strip()
                repeats += digest == previous
                previous = digest
                frames += 1
    if not frames:
        raise ValueError("No decoded video frames.")
    levels = {}
    freezes = []
    count = 0
    with (directory / "levels").open() as stats:
        for line in stats:
            key, _, value = line.strip().partition("=")
            if key == "lavfi.freezedetect.freeze_start":
                count += 1
                if len(freezes) < 100:
                    freezes.append(float(value))
            name = key.removeprefix("lavfi.signalstats.")
            if name in ("YMIN", "UMIN", "VMIN", "YMAX", "UMAX", "VMAX"):
                op = min if name.endswith("MIN") else max
                levels[name] = op(levels.get(name, float(value)), float(value))
    # Some codecs omit field_order at stream level. Check flags on decoded frames.
    field_counts = {"progressive": 0, "tff": 0, "bff": 0}
    with tempfile.TemporaryFile(mode="w+") as flags:
        subprocess.run([FFPROBE, "-v", "error", "-protocol_whitelist", "file,pipe", "-select_streams",
                        str(video["index"]), "-show_frames", "-show_entries", "frame=interlaced_frame,top_field_first",
                        "-of", "compact=p=0:nk=0", str(path)], stdout=flags, check=True, timeout=3600)
        flags.seek(0)
        for line in flags:
            values = dict(part.split("=", 1) for part in line.strip().split("|") if "=" in part)
            if "interlaced_frame" in values:
                key = "progressive" if values["interlaced_frame"] == "0" else (
                    "tff" if values.get("top_field_first") == "1" else "bff")
                field_counts[key] += 1
    return {"decoded_frames": frames, "scan_counts": field_counts, "consecutive_identical": repeats, "near_freezes": count,
            "first_freeze_starts_seconds": freezes, "sample_extrema": levels}


def picture_reader(stack, path, stream, width, height, directory, name):
    # RGB is used only for the SDR appearance comparison, independently of native signal measurements.
    timeline = directory / (name + ".pts")
    filters = (f"scale={width}:{height}:flags=bicubic,format=rgb24,settb=AVTB,"
               f"metadata=add:key=qc:value=1,metadata=print:key=qc:file={timeline.name}")
    log = stack.enter_context(tempfile.TemporaryFile())
    proc = stack.enter_context(subprocess.Popen(decode_input(path) + [
        "-map", f"0:{stream['index']}", "-vf", filters, "-fps_mode", "passthrough", "-threads", "2",
        "-f", "rawvideo", "-"], cwd=directory, stderr=log, stdout=subprocess.PIPE))
    stack.callback(proc.kill)
    timer = threading.Timer(3600, proc.kill)
    timer.daemon = True
    timer.start()
    stack.callback(timer.cancel)
    return proc, timeline


def timestamps(path):
    with path.open() as source:
        for line in source:
            if line.startswith("frame:"):
                # Read integer PTS from metadata after explicitly setting a microsecond time base.
                yield int(line.split("pts:", 1)[1].split()[0])


def compare(path, video, reference, directory):
    ref = primary(probe(reference))
    width, height = video["width"], video["height"]
    for stream in (ref, video):
        if stream.get("field_order") not in ("progressive", None, "unknown"):
            raise ValueError("Reference comparison requires progressive pictures.")
        if stream.get("color_transfer") in ("smpte2084", "arib-std-b67"):
            raise ValueError("Reference comparison supports SDR pictures.")
    def dar(stream):
        sar = stream.get("sample_aspect_ratio")
        ratio = Fraction(sar.replace(":", "/")) if sar and sar not in ("N/A", "0:1") else 1
        return Fraction(stream["width"], stream["height"]) * ratio
    if dar(ref) != dar(video):
        raise ValueError("Reference comparison requires the same display aspect ratio.")
    halves = [(0, 0, width, height//2), (0, height//2, width, height)]
    worst = [{"mean_error": 0., "large_error_fraction": 0., "peak": 0} for box in halves]
    flat_samples = 0
    flat_outliers = 0
    first_flat_error = None
    count = 0
    with ExitStack() as stack:
        first, t1 = picture_reader(stack, path, video, width, height, directory, "output")
        second, t2 = picture_reader(stack, reference, ref, width, height, directory, "reference")
        size = width * height * 3
        while True:
            a, b = first.stdout.read(size), second.stdout.read(size)
            if not a and not b:
                break
            if len(a) != size or len(b) != size:
                raise ValueError("Reference and output frame counts differ.")
            reference_image = Image.frombytes("RGB", (width, height), b)
            diff = ImageChops.difference(Image.frombytes("RGB", (width, height), a), reference_image)
            # Check interiors separately so isolated sparkles cannot hide in a frame average.
            for row in range(4):
                for col in range(8):
                    box = ((4*col+1)*width//32, (4*row+1)*height//16,
                           (4*col+3)*width//32, (4*row+3)*height//16)
                    if any(high-low > 3 for low, high in reference_image.crop(box).getextrema()):
                        continue
                    hist = diff.crop(box).histogram()
                    flat_samples += sum(hist)
                    outliers = sum(n for i, n in enumerate(hist) if i % 256 > 32)
                    flat_outliers += outliers
                    if outliers and first_flat_error is None:
                        first_flat_error = {"frame": count, "box": list(box)}
            for box, metrics in zip(halves, worst):
                hist = diff.crop(box).histogram()
                samples = sum(hist)
                mean = sum((i % 256) * n for i, n in enumerate(hist)) / samples
                fraction = sum(n for i, n in enumerate(hist) if i % 256 > 32) / samples
                peak = max(i % 256 for i, n in enumerate(hist) if n)
                if fraction > metrics["large_error_fraction"]:
                    metrics["worst_fraction_frame"] = count
                metrics["mean_error"] = max(mean, metrics["mean_error"])
                metrics["large_error_fraction"] = max(fraction, metrics["large_error_fraction"])
                metrics["peak"] = max(peak, metrics["peak"])
            count += 1
        if first.wait() or second.wait() or not count:
            raise ValueError("Reference comparison decode failed.")
        start_a = start_b = None
        aligned = 0
        for a, b in zip(timestamps(t1), timestamps(t2), strict=True):
            if start_a is None:
                start_a, start_b = a, b
            if abs((a-start_a) - (b-start_b)) > 1000:
                raise ValueError("Reference frame timings differ by more than 1 ms.")
            aligned += 1
        if aligned != count:
            raise ValueError("Missing reference timestamps.")
    return {"frames": count, "top_half": worst[0], "bottom_half": worst[1],
            "flat_channel_samples": flat_samples, "flat_large_errors": flat_outliers,
            "first_flat_error": first_flat_error}


def export_expectations(job):
    from engine import Settings
    from transcode import PRESETS
    settings = job["settings"]
    if job.get("kind") == "conversion":
        plan = job["conversion"]
        profile = settings["profile"]
        _, encoder, _, pixel, container = PRESETS[profile]
        width, height = plan["width"], plan["height"]
        fps = Fraction(plan["fps"])
        expected = {"field_order": "progressive", "color_range": "tv"}
        if "audio_channels" in plan:
            channels = plan["audio_channels"]
            expected.update(audio_tracks=len(channels), audio_channels=channels,
                            audio_codecs=["pcm_s24le" if container == "mov" else "aac"] * len(channels))
        if settings["audio"] == "mute":
            expected["audio_tracks"] = 0
    else:
        s = Settings.parse(settings)
        profile, encoder, pixel, container = s.delivery_profile, s.encoder, s.pixel_format, s.container
        width, height = s.dimensions
        fps = s.fps
        expected = {"audio_tracks": s.pairs, "audio_channels": [2]*s.pairs,
                    "audio_codecs": ["pcm_s24le" if container == "mov" else "aac"]*s.pairs,
                    "color_space": s.colour_tags[0], "color_range": s.video_range}
        if s.interlaced:
            expected["decoded_dominance"] = s.field_order
        else:
            expected["field_order"] = "progressive"
    if profile in PROBE_PROFILES:
        expected["profile"] = PROBE_PROFILES[profile]
    codec = {"libx264":"h264", "libx265":"hevc", "prores_ks":"prores", "dnxhd":"dnxhd"}[encoder]
    return {**expected, "codec_name":codec, "pix_fmt":"yuv444p12le" if profile in ("prores_4444","prores_xq") else pixel,
            "width":width, "height":height, "fps":str(fps), "container":"mpegts" if container == "ts" else container}


def check_contract(info, expected, count, scan_counts=None):
    errors, review = [], []
    video = primary(info)
    audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
    actual = {**video, "frames": count, "audio_tracks": len(audio),
              "audio_codecs": [s["codec_name"] for s in audio],
              "audio_channels": [s["channels"] for s in audio],
              "fps": str(Fraction(video["r_frame_rate"])),
              "container": info["format"]["format_name"].split(",")}
    actual["pix_fmt"] = actual["pix_fmt"].replace("yuvj", "yuv")
    if scan_counts is not None and expected.get("field_order") == "progressive":
        if scan_counts["progressive"] == count:
            if actual.get("field_order") in (None, "unknown"):
                actual["field_order"] = "progressive"
        else:
            errors.append("Decoded frames do not all have progressive scan flags.")
    if "mov" in actual["container"]:
        brand = info["format"].get("tags", {}).get("major_brand", "").strip()
        actual["container"] = ["mov" if brand == "qt" else "mp4"] if brand else []
    for key, value in expected.items():
        if key == "decoded_dominance":
            if scan_counts is not None and scan_counts[value] != count:
                errors.append(f"Decoded field dominance differs from {value}.")
            continue
        matches = value in actual[key] if key == "container" else value == actual.get(key)
        if key == "color_range" and actual.get(key) is None and video["codec_name"] == "prores":
            review.append("ProRes colour range is unreported. Expected " + value +
                          ". Review the measured sample levels and reference comparison.")
        elif key == "field_order" and actual.get(key) in (None, "unknown") and scan_counts is None:
            review.append("Stream scan order is unreported.")
        elif not matches:
            errors.append(f"{key}: expected {value}, measured {actual.get(key)}")
    return errors, review


def verify(path, reference=None, expected=None, details=True):
    path = Path(path).resolve()
    report = {"status": "failed", "errors": [], "review": [], "anc_checksums": "not tested"}
    try:
        info = probe(path)
        video = primary(info)
        audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
        report["inventory"] = info
        info["format"].pop("filename", None)
        with tempfile.TemporaryDirectory(prefix="pattern-qc-") as temp:
            directory = Path(temp)
            report["scan"] = scan(path, video, directory, bool(audio))
            count = report["scan"]["decoded_frames"]
            if video.get("nb_frames", "").isdigit() and int(video["nb_frames"]) != count:
                report["errors"].append("Decoded count differs from the declared frame count.")
            if report["scan"]["consecutive_identical"] or report["scan"]["near_freezes"]:
                report["review"].append("Repeated or near-static pictures detected. Static patterns can be intentional.")
            if expected:
                errors, review = check_contract(info, expected, count, report["scan"]["scan_counts"])
                report["errors"].extend(errors)
                report["review"].extend(review)
            if reference:
                metrics = compare(path, video, Path(reference).resolve(), directory)
                report["comparison"] = metrics
                if metrics["flat_large_errors"]:
                    report["errors"].append("Large pixel differences in a sampled flat reference patch.")
                for half in ("top_half", "bottom_half"):
                    if metrics[half]["mean_error"] > 3 or metrics[half]["large_error_fraction"] > .005:
                        report["errors"].append(f"{half} exceeds the SDR fixture difference limits.")
            if details:
                report["tools"] = tool_versions()
                inspect_tools(path, video, report)
        report["status"] = "failed" if report["errors"] else "review" if report["review"] else "checks passed"
    except (ValueError, OSError, subprocess.SubprocessError, KeyError, ArithmeticError) as exc:
        report["errors"].append(str(exc))
    return report


def inspect_tools(path, video, report):
    if shutil.which("mediainfo"):
        raw = subprocess.check_output(["mediainfo", "--Output=JSON", str(path)], timeout=60)
        report["mediainfo"] = json.loads(raw).get("media", {}).get("track", [])
    else:
        report["mediainfo"] = "unavailable on this host"
    packets = subprocess.check_output([FFPROBE, "-v", "error", "-protocol_whitelist", "file,pipe",
        "-select_streams", str(video["index"]), "-read_intervals", "%+#4", "-show_packets",
        "-show_data_hash", "sha256", "-of", "json", str(path)], timeout=30)
    report["packet_sample"] = json.loads(packets).get("packets", [])
    if video["codec_name"] in ("hevc", "h264"):
        fields = ("chroma_format_idc", "bit_depth_luma_minus8", "bit_depth_chroma_minus8",
                  "frame_mbs_only_flag", "general_profile_idc", "profile_idc")
        with tempfile.TemporaryFile(mode="w+") as trace:
            result = subprocess.run([FFMPEG, "-hide_banner", "-loglevel", "info", "-protocol_whitelist", "file,pipe",
                "-i", str(path), "-map", f"0:{video['index']}", "-frames:v", "1", "-c:v", "copy",
                "-bsf:v", "trace_headers", "-f", "null", "-"], stderr=trace, timeout=30)
            trace.seek(0)
            values = {}
            for line in trace:
                if "[trace_headers" in line and " = " in line:
                    tokens = line.split()
                    for field in fields:
                        if field in tokens:
                            values[field] = tokens[-1]
            report["header_sample"] = values
            if result.returncode or not values:
                report["review"].append("Header sample unavailable.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file", type=Path)
    parser.add_argument("--reference", type=Path)
    args = parser.parse_args()
    result = verify(args.file, reference=args.reference)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["errors"] else 0)

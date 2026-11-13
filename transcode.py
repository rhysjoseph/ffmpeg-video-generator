"""File conversion presets with explicit codec and geometry validation."""
from dataclasses import asdict, dataclass
from fractions import Fraction
import math
from pathlib import Path
import subprocess

from assets import asset, validate_logo, logo_graph
from engine import FFMPEG, RATES, RESOLUTIONS, encoder_formats, probe
from delivery import EDITING_PROFILES

# id: label, encoder, encoder profile, pixel format, container
PRESETS = {
    **EDITING_PROFILES,
    "dnxhd_hq": ("Avid DNxHD HQ · 1080p", "dnxhd", "dnxhd", "yuv422p", "mov"),
    "hevc_proxy": ("H.265 Proxy · 8-bit", "libx265", "main", "yuv420p", "mp4"),
    "hevc_proxy10": ("H.265 Proxy · 10-bit", "libx265", "main10", "yuv420p10le", "mp4"),
}


@dataclass(frozen=True)
class ConvertSettings:
    source_id: str = ""
    profile: str = "prores_hq"
    resolution: str = "source"
    width: int = 1920
    height: int = 1080
    rate: str = "source"
    fit: str = "pad"
    deinterlace: str = "auto"
    audio: str = "keep"
    start: float = 0
    length: float = 0
    proxy_crf: int = 28
    speed: str = "fast"
    logo_id: str = ""
    logo_position: str = "top_right"
    logo_width: int = 15
    logo_margin: int = 3
    logo_opacity: int = 100

    @classmethod
    def parse(cls, values):
        if not isinstance(values, dict) or set(values) - set(cls.__dataclass_fields__):
            raise ValueError("Invalid conversion settings.")
        s = cls(**values)
        for key, allowed in {"profile": PRESETS, "resolution": ("source", "custom", *RESOLUTIONS),
                             "rate": ("source", *[r for r in RATES if r.endswith("p")]),
                             "fit": ("pad", "crop", "stretch"), "deinterlace": ("auto", "always"),
                             "audio": ("keep", "mute"), "speed": ("ultrafast", "fast", "medium", "slow")}.items():
            value = getattr(s, key)
            if not isinstance(value, str) or value not in allowed:
                raise ValueError(f"Invalid {key}.")
        for key in ("width", "height"):
            v = getattr(s, key)
            if type(v) is not int or not 128 <= v <= 8192 or v % 2:
                raise ValueError("Custom dimensions must be even numbers from 128 to 8192.")
        for key in ("start", "length"):
            v = getattr(s, key)
            if type(v) not in (float, int) or not math.isfinite(v) or v < 0:
                raise ValueError("Trim values must be non-negative seconds.")
        if type(s.proxy_crf) is not int or not 16 <= s.proxy_crf <= 35:
            raise ValueError("Proxy CRF must be between 16 and 35.")
        validate_logo(s)
        asset(s.source_id, "video")
        return s


def plan(s):
    s = ConvertSettings.parse(asdict(s))
    source, meta = asset(s.source_id, "video")
    video = meta["video"]
    fps = Fraction(video.get("avg_frame_rate") or "0/1")
    if fps <= 0:
        fps = Fraction(video.get("r_frame_rate") or "0/1")
    if s.rate != "source":
        fps = Fraction(RATES[s.rate])
    if not 1 <= fps <= 240:
        raise ValueError("Select an explicit frame rate; the source rate is not usable.")
    sar = Fraction(video.get("sample_aspect_ratio", "1:1").replace(":", "/")) if video.get("sample_aspect_ratio") not in (None, "N/A", "0:1") else Fraction(1)
    width, height = round(video["width"] * sar / 2) * 2, video["height"] // 2 * 2
    rotation = next((v.get("rotation", 0) for v in video.get("side_data_list", []) if "rotation" in v), 0)
    if abs(int(rotation)) % 180 == 90:
        width, height = height, width
    if s.resolution == "custom":
        width, height = s.width, s.height
    elif s.resolution != "source":
        width, height = map(int, s.resolution.split("x"))
    if not (128 <= width <= 8192 and 128 <= height <= 8192):
        raise ValueError("Choose output dimensions between 128 and 8192 pixels.")
    remaining = meta["duration"] - s.start
    duration = min(s.length, remaining) if s.length else remaining
    if duration <= 0:
        raise ValueError("Trim start must be before the end of the video.")
    label, encoder, profile, pix, container = PRESETS[s.profile]
    if pix not in encoder_formats(encoder):
        raise ValueError(f"This FFmpeg build does not support {label}.")
    bitrate = None
    if s.profile == "dnxhd_hq":
        rates = {Fraction(24000,1001):175, Fraction(24):175, Fraction(25):185, Fraction(30000,1001):220, Fraction(30):220}
        if (width, height) != (1920,1080) or fps not in rates:
            raise ValueError("DNxHD HQ requires 1920×1080 at 23.98, 24, 25, 29.97 or 30p. Use DNxHR for other formats.")
        bitrate = rates[fps]
    if encoder == "dnxhd" and (width < 256 or height < 120):
        raise ValueError("DNxHR requires at least 256×120 pixels.")
    hdr = video.get("color_transfer") in ("smpte2084", "arib-std-b67")
    if s.logo_id and hdr:
        raise ValueError("Logo overlays on HDR sources require tone mapping. Disable the conversion logo to preserve HDR without changing its transfer function.")
    return {"source": str(source), "name": meta["name"], "duration": duration, "width": width, "height": height,
            "fps": str(fps), "label": label, "encoder": encoder, "profile": profile, "pix_fmt": pix,
            "container": container, "bitrate": bitrate, "video": video, "hdr": hdr}


def build_conversion(s, output):
    p = plan(s)
    v, w, h = p["video"], p["width"], p["height"]
    args = [FFMPEG, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y", "-filter_complex_threads", "2",
            "-protocol_whitelist", "file,pipe", "-ss", str(s.start), "-i", p["source"]]
    # Untagged HD material is treated as BT.709. Existing source colour tags are retained.
    matrix = v.get("color_space") if v.get("color_space") in ("bt709", "bt470bg", "smpte170m", "bt2020nc", "bt2020c", "smpte240m") else "bt709"
    primaries = v.get("color_primaries") if v.get("color_primaries") in ("bt709", "bt470bg", "smpte170m", "bt2020", "smpte432", "smpte431", "smpte240m") else "bt709"
    transfer = v.get("color_transfer") if v.get("color_transfer") in ("bt709", "smpte170m", "bt2020-10", "bt2020-12", "smpte2084", "arib-std-b67", "iec61966-2-1", "linear", "gamma22", "gamma28", "smpte240m") else "bt709"
    in_range = "pc" if v.get("color_range") == "pc" else "tv"
    # All converter presets deliver legal-range YUV. Source colour primaries/transfer stay intact.
    filters = [f"bwdif=mode=send_frame:parity=auto:deint={'all' if s.deinterlace == 'always' else 'interlaced'}",
               f"setparams=colorspace={matrix}:color_primaries={primaries}:color_trc={transfer}:range={in_range}",
               "scale=w='max(2,trunc(iw*sar/2)*2)':h=ih,setsar=1"]
    mode = "decrease" if s.fit == "pad" else "increase"
    if s.fit == "stretch":
        filters.append(f"scale={w}:{h}:flags=lanczos:in_range={in_range}:out_range=tv")
    else:
        filters.append(f"scale={w}:{h}:force_original_aspect_ratio={mode}:force_divisible_by=2:flags=lanczos:in_range={in_range}:out_range=tv")
        filters.append(f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=black" if s.fit == "pad" else f"crop={w}:{h}:(iw-ow)/2:(ih-oh)/2")
    filters += ["setsar=1", f"fps={p['fps']}", "setfield=prog"]
    graph = [f"[0:{v['index']}]" + ",".join(filters) + "[scaled]"]
    current = "scaled"
    if s.logo_id:
        # Convert logo into the source's SDR colour profile before compositing.
        logo_args, logo_filter, x, y = logo_graph(s, 1, w, h, p["fps"])
        args += logo_args
        graph.append(logo_filter)
        graph.append("[logo]split[logo_colour][logo_alpha]")
        graph.append("[logo_alpha]alphaextract[alpha]")
        graph.append(f"[logo_colour]format=yuv444p10le,colorspace=iall=bt709:irange=tv:space={matrix}:primaries={primaries}:trc={transfer}:range=tv:format=yuv444p10[colour_logo]")
        graph.append("[colour_logo][alpha]alphamerge[converted_logo]")
        graph.append(f"[scaled][converted_logo]overlay=x='{x}':y='{y}':format=yuv444p10:shortest=1[branded]")
        current = "branded"
    graph.append(f"[{current}]format={p['pix_fmt']},setparams=range=tv:colorspace={matrix}:color_primaries={primaries}:color_trc={transfer}[out]")
    args += ["-filter_complex", ";".join(graph), "-map", "[out]"]
    if s.audio == "keep":
        args += ["-map", "0:a?"]
    args += ["-map_metadata", "0", "-map_chapters", "-1", "-metadata:s:v:0", "rotate=0", "-t", str(p["duration"]),
             "-c:v", p["encoder"], "-profile:v", p["profile"], "-pix_fmt", p["pix_fmt"], "-threads", "4",
             "-color_range", "tv", "-colorspace", matrix, "-color_primaries", primaries, "-color_trc", transfer]
    if p["encoder"] == "libx265":
        args += ["-preset", s.speed, "-crf", str(s.proxy_crf), "-x265-params", "pools=4:frame-threads=2:log-level=error", "-tag:v", "hvc1"]
    elif p["encoder"] == "prores_ks":
        args += ["-alpha_bits", "0"]
    if p["bitrate"]:
        args += ["-b:v", f"{p['bitrate']}M"]
    if s.audio == "keep":
        args += ["-c:a", "aac", "-b:a", "256k"] if p["container"] == "mp4" else ["-c:a", "pcm_s24le"]
        args += ["-ar", "48000"]
    args += ["-movflags", "+faststart", "-progress", "pipe:1", "-nostats", str(output)]
    return args, p


def convert(s, output, *, progress=None, started=None, cancel=None):
    args, p = build_conversion(s, output)
    log_path = Path(output).with_suffix(".log")
    with log_path.open("wb") as log:
        proc = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log)
        if started:
            started(proc)
        for line in proc.stdout:
            key, _, value = line.decode(errors="replace").strip().partition("=")
            if key == "out_time_us" and value.lstrip("-").isdigit() and progress:
                progress(min(.99, max(0, int(value) / 1e6 / p["duration"])))
        code = proc.wait()
        proc.stdout.close()
    if cancel and cancel.is_set():
        raise InterruptedError("Conversion cancelled.")
    if code:
        raise RuntimeError(log_path.read_text(errors="replace")[-5000:] or "FFmpeg conversion failed.")
    result = next(v for v in probe(output)["streams"] if v["codec_type"] == "video")
    if (result["width"], result["height"]) != (p["width"], p["height"]):
        raise RuntimeError("The encoder did not preserve the selected output dimensions.")
    if Fraction(result["r_frame_rate"]) != Fraction(p["fps"]):
        raise RuntimeError("The encoder did not preserve the selected frame rate.")
    return p

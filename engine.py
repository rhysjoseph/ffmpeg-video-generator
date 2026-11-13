"""Local FFmpeg test-pattern renderer. No shell commands or drawtext dependency."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import threading
from dataclasses import asdict, dataclass
from functools import lru_cache
from fractions import Fraction

from PIL import Image, ImageDraw, ImageFont
from assets import validate_logo, logo_graph
from delivery import EDITING_PROFILES

ROOT = Path(__file__).resolve().parent
FFMPEG = os.environ.get("FFMPEG_PATH") or shutil.which("ffmpeg")
FFPROBE = os.environ.get("FFPROBE_PATH") or shutil.which("ffprobe")
PATTERNS = {
    "smptehdbars": "HD SMPTE Bars", "smptebars": "SMPTE Bars",
    "pal75bars": "PAL 75%", "pal100bars": "PAL 100%",
    "scroll": "Moving Colour Bars", "lipsync": "Lip Sync", "sweep": "Side Sweep",
}
RESOLUTIONS = {"3840x2160": "UHD 4K", "2560x1440": "QHD", "1920x1080": "Full HD", "1280x720": "HD"}
RATES = {
    "23.98p": "24000/1001", "24p": "24", "25p": "25", "29.97p": "30000/1001",
    "30p": "30", "50p": "50", "59.94p": "60000/1001", "60p": "60",
    "50i": "25", "59.94i": "30000/1001",
}
COLOURS = {
    # matrix, primaries, transfer; all profiles are SDR.
    "bt709": ("bt709", "bt709", "bt709"),
    "bt2020": ("bt2020nc", "bt2020", "bt2020-10"),
    "bt601_pal": ("bt470bg", "bt470bg", "smpte170m"),
    "bt601_ntsc": ("smpte170m", "smpte170m", "smpte170m"),
}
QUALITY = {"maximum": "10", "high": "16", "compact": "23"}


@lru_cache(maxsize=4)
def encoder_formats(encoder):
    if not FFMPEG:
        return set()
    result = subprocess.run([FFMPEG, "-hide_banner", "-h", f"encoder={encoder}"],
                            capture_output=True, text=True, timeout=10)
    for line in result.stdout.splitlines():
        if "Supported pixel formats:" in line:
            return set(line.split(":", 1)[1].split())
    return set()


@dataclass(frozen=True)
class Settings:
    pattern: str = "smptehdbars"
    resolution: str = "1920x1080"
    rate: str = "25p"
    duration: int = 10
    timecode: bool = True
    freeze_box: bool = True
    label: str = ""
    audio: str = "stereo"
    level: str = "-20"
    container: str = "mp4"
    delivery_profile: str = "custom"
    bit_depth: int = 8
    chroma: str = "420"
    colour: str = "bt709"
    video_range: str = "tv"
    codec: str = "auto"
    quality: str = "high"
    preset: str = "fast"
    field_order: str = "tff"
    box_speed: str = "normal"
    logo_id: str = ""
    logo_position: str = "top_right"
    logo_width: int = 15
    logo_margin: int = 3
    logo_opacity: int = 100

    @classmethod
    def parse(cls, values):
        if not isinstance(values, dict):
            raise ValueError("Settings must be a JSON object.")
        if set(values) - set(cls.__dataclass_fields__):
            raise ValueError("Unknown setting.")
        s = cls(**values)
        for key, allowed in {
            "pattern": PATTERNS, "resolution": RESOLUTIONS, "rate": RATES,
            "duration": (10, 30, 60, 120), "audio": ("stereo", "four_pairs"),
            "level": ("-20", "-18", "-12", "silence"), "container": ("mp4", "mov", "ts"),
            "delivery_profile": ("custom", *EDITING_PROFILES),
            "bit_depth": (8, 10, 12), "chroma": ("420", "422", "444"),
            "colour": COLOURS, "video_range": ("tv", "pc"), "codec": ("auto", "h264", "hevc"),
            "quality": QUALITY, "preset": ("ultrafast", "fast", "medium", "slow"),
            "field_order": ("tff", "bff"), "box_speed": ("slow", "normal", "fast"),
        }.items():
            value = getattr(s, key)
            if isinstance(value, (dict, list, bool)) or value not in allowed:
                raise ValueError(f"Invalid {key}.")
        if type(s.duration) is not int:
            raise ValueError("Duration must be an integer.")
        if type(s.bit_depth) is not int:
            raise ValueError("Bit depth must be an integer.")
        if s.editing_profile:
            label, _, _, pixel, container = s.editing_profile
            if s.container != container or s.pixel_format != pixel or s.video_range != "tv" or s.codec != "auto":
                raise ValueError(f"{label} requires MOV, {pixel}, limited range and Auto codec.")
            if s.interlaced and s.encoder == "dnxhd":
                raise ValueError("DNxHR requires a progressive frame rate. Choose ProRes or H.264 for interlaced output.")
        if not s.editing_profile and s.codec == "h264" and s.bit_depth == 12:
            raise ValueError("12-bit video requires HEVC. Choose Auto or H.265 / HEVC.")
        if s.interlaced and s.encoder == "libx265":
            raise ValueError("Interlaced output requires H.264 at 8 or 10 bits. Select a progressive rate for HEVC / 12-bit.")
        if type(s.timecode) is not bool or type(s.freeze_box) is not bool:
            raise ValueError("Burn-in switches must be booleans.")
        if not isinstance(s.label, str) or len(s.label) > 120 or any(ord(c) < 32 for c in s.label):
            raise ValueError("Label must be a single line of at most 120 characters.")
        validate_logo(s)
        return s

    @property
    def fps(self):
        return Fraction(RATES[self.rate])

    @property
    def interlaced(self):
        return self.rate.endswith("i")

    @property
    def drop(self):
        return self.rate in ("29.97p", "59.94p", "59.94i")

    @property
    def dimensions(self):
        return tuple(map(int, self.resolution.split("x")))

    @property
    def pairs(self):
        return 4 if self.audio == "four_pairs" else 1

    @property
    def pixel_format(self):
        return f"yuv{self.chroma}p" + (f"{self.bit_depth}le" if self.bit_depth > 8 else "")

    @property
    def encoder(self):
        if self.editing_profile:
            return self.editing_profile[1]
        return "libx265" if self.codec == "hevc" or (self.codec == "auto" and self.bit_depth == 12) else "libx264"

    @property
    def editing_profile(self):
        return EDITING_PROFILES.get(self.delivery_profile)

    @property
    def colour_tags(self):
        matrix, primaries, transfer = COLOURS[self.colour]
        if self.colour == "bt2020" and self.bit_depth == 12:
            transfer = "bt2020-12"
        return matrix, primaries, transfer


def timecode(frame: int, fps: Fraction, drop: bool) -> str:
    """SMPTE count; skip 2/4 numbers each minute except every tenth minute."""
    nominal = round(fps)
    if drop:
        if fps not in (Fraction(30000, 1001), Fraction(60000, 1001)):
            raise ValueError("Drop-frame requires 29.97 or 59.94 fps.")
        skip = 2 if nominal == 30 else 4
        ten = nominal * 600 - skip * 9
        minute = nominal * 60 - skip
        blocks, rest = divmod(frame, ten)
        frame += skip * 9 * blocks + skip * max(0, (rest - skip) // minute)
    seconds, frames = divmod(frame, nominal)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours % 24:02}:{minutes:02}:{seconds:02}{';' if drop else ':'}{frames:02}"


def font(size, mono=False):
    candidates = (["/System/Library/Fonts/Menlo.ttc", "DejaVuSansMono.ttf"] if mono else [
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf", "DejaVuSans.ttf"])
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default(size=size)


class BurnIn:
    """Small RGB strip streamed to FFmpeg; labels are always literal text."""
    def __init__(self, s):
        self.s = s
        w, h = s.dimensions
        self.pad = max(8, round(h * .012))
        self.tc_font = font(round(h * .037), True)
        label_size = round(h * .029)
        self.label_font = font(label_size)
        max_width = round(w * .88)
        while s.label and self.label_font.getlength(s.label) > max_width - 2 * self.pad and label_size > 9:
            label_size -= 1
            self.label_font = font(label_size)
        text_width = max(self.tc_font.getlength("00:00:00;00") if s.timecode else 0,
                         self.label_font.getlength(s.label) if s.label else 0)
        self.width = math.ceil((text_width + self.pad * 2) / 2) * 2
        self.tc_height = round(h * .05) if s.timecode else 0
        self.label_height = label_size + self.pad if s.label else 0
        self.height = math.ceil((2 * self.pad + self.tc_height + self.label_height) / 2) * 2
        self.base = Image.new("RGB", (self.width, self.height), (12, 15, 20))
        if s.label:
            ImageDraw.Draw(self.base).text((self.width / 2, self.pad + self.tc_height), s.label,
                                        font=self.label_font, fill="white", anchor="mt")

    def frame(self, n):
        im = self.base.copy()
        if self.s.timecode:
            ImageDraw.Draw(im).text((self.width / 2, self.pad), timecode(n, self.s.fps, self.s.drop),
                                   font=self.tc_font, fill="white", anchor="mt")
        return im.tobytes()


def build_command(s, output, *, duration=None, preview=False):
    if not FFMPEG:
        raise RuntimeError("FFmpeg was not found. Install it with: brew install ffmpeg")
    # Direct Python callers get the same validation as the web API.
    s = Settings.parse(asdict(s))
    if not preview and s.pixel_format not in encoder_formats(s.encoder):
        raise ValueError(f"This FFmpeg build cannot encode {s.pixel_format} with {s.encoder}. Choose another codec or install a compatible FFmpeg build.")
    duration = s.duration if duration is None else duration
    w, h = s.dimensions
    source_rate = s.fps * (2 if s.interlaced else 1)
    rate = str(source_rate)
    work_format = "yuv444p10le" if s.bit_depth > 8 else "yuv444p"
    overlay_format = "yuv444p10" if s.bit_depth > 8 else "yuv444"
    matrix, primaries, transfer = s.colour_tags
    # For fractional rates, flash/beep repeat at an integer number of output frames.
    cycle = round(s.fps)
    pulse_frames = max(1, round(float(s.fps) * .08))
    period = float(Fraction(cycle, 1) / s.fps)
    pulse = float(Fraction(pulse_frames, 1) / s.fps)
    source = s.pattern if s.pattern in ("smptehdbars", "smptebars", "pal75bars", "pal100bars") else "smptehdbars"
    if s.pattern in ("lipsync", "sweep"):
        video = f"color=c=0x10141c:s={w}x{h}:r={rate}"
    else:
        video = f"{source}=s={w}x{h}:r={rate}"
    # Keep full chroma through compositing. Native FFmpeg bars have 8-bit levels;
    # higher-depth output preserves those sources and gains conversion precision.
    video += f",format={work_format}"
    # Normalise source matrices into the BT.709 working space.
    if source in ("smptebars", "pal75bars", "pal100bars"):
        video += f",scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=tv:out_range=tv,format={work_format}"
    elif s.pattern in ("lipsync", "sweep"):
        video += f",scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=tv:out_range=tv,format={work_format}"
    video += ",setparams=range=tv:colorspace=bt709:color_primaries=bt709:color_trc=bt709"
    if s.pattern == "scroll":
        video += f",scroll=horizontal={1 / (float(source_rate) * 8):.12f}"
    if s.pattern == "lipsync":
        field_multiplier = 2 if s.interlaced else 1
        video += (f",drawbox=x=iw*.30:y=ih*.22:w=iw*.40:h=ih*.44:color=white:t=fill:"
                  f"enable='lt(mod(n,{cycle * field_multiplier}),{pulse_frames * field_multiplier})'"
                  ",drawbox=x=iw*.30:y=ih*.22:w=iw*.40:h=ih*.44:color=0x6c7787:t=2")
    args = [FFMPEG, "-hide_banner", "-loglevel", "warning", "-nostdin", "-y",
            "-filter_complex_threads", "2", "-f", "lavfi", "-i", video]
    graph = []
    current = "0:v"
    if s.pattern == "sweep":
        graph.append(f"color=c=white:s={max(4, w // 80 // 2 * 2)}x{h}:r={rate},format={work_format},setparams=colorspace=bt709[sweep]")
        graph.append(f"[{current}][sweep]overlay=x='mod(t/2,1)*(W-w)':y=0:format={overlay_format}[swept]")
        current = "swept"
    overlay = BurnIn(s) if s.timecode or s.label else None
    if overlay:
        args += ["-thread_queue_size", "8", "-f", "rawvideo", "-pixel_format", "rgb24",
                 "-video_size", f"{overlay.width}x{overlay.height}", "-framerate", rate, "-i", "pipe:0"]
        graph.append(f"[1:v]scale=in_range=pc:out_range=tv:out_color_matrix=bt709,format={work_format},setparams=colorspace=bt709[caption]")
        graph.append(f"[{current}][caption]overlay=x='(W-w)/2':y='H-h-H*.055':eof_action=repeat:format={overlay_format}[burned]")
        current = "burned"
    if s.logo_id:
        logo_args, logo_filter, x, y = logo_graph(s, 2 if overlay else 1, w, h, source_rate, work_format)
        args += logo_args
        graph.append(logo_filter)
        graph.append(f"[{current}][logo]overlay=x='{x}':y='{y}':format={overlay_format}[branded]")
        current = "branded"
    if s.freeze_box:
        size = h // 18 // 2 * 2
        speed = {"slow": .5, "normal": 1, "fast": 2}[s.box_speed]
        graph.append(f"color=c=0x20e4b0:s={size}x{size}:r={rate},format={work_format},"
                     f"scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=tv:out_range=tv,"
                     f"drawbox=color=black:t=2,format={work_format},setparams=colorspace=bt709[box]")
        # Triangle waves reflect at all four boundaries without jumping or clipping.
        graph.append(f"[{current}][box]overlay=x='(W-w)*(1-abs(1-mod(t*{speed}/3,2)))':"
                     f"y='(H-h)*(1-abs(1-mod(t*{speed}/2,2)))':format={overlay_format}[moving]")
        current = "moving"
    conversion = (f"colorspace=iall=bt709:irange=tv:space={matrix}:primaries={primaries}:"
                  f"trc={transfer}:range={s.video_range}:format={s.pixel_format.replace('le', '')}")
    # Sample chroma before weaving, so 4:2:0 filtering never mixes temporal fields.
    graph.append(f"[{current}]{conversion},setsar=1[converted]")
    current = "converted"
    if s.interlaced:
        mode = "interleave_top" if s.field_order == "tff" else "interleave_bottom"
        graph.append(f"[{current}]tinterlace=mode={mode}[interlaced]")
        current = "interlaced"
    if preview:
        # A colour-managed SDR representation of the output, displayed as 8-bit RGB.
        graph.append(f"[{current}]colorspace=ispace={matrix}:iprimaries={primaries}:itrc={transfer}:"
                     f"irange={s.video_range}:all=bt709:range=tv:format=yuv444p,"
                     "scale=960:540:in_color_matrix=bt709:in_range=tv:out_range=pc,format=rgb24[v]")
    else:
        graph.append(f"[{current}]setparams=range={s.video_range}:color_primaries={primaries}:color_trc={transfer}:colorspace={matrix}[v]")
    if not preview:
        amplitude = 0 if s.level == "silence" else 10 ** (int(s.level) / 20)
        signal = f"{amplitude:.12f}*sin(2*PI*1000*t)"
        if s.pattern == "lipsync":
            signal += f"*lt(mod(t,{period:.12f}),{pulse:.12f})"
        graph.append(f"aevalsrc=exprs='{signal}|{signal}':s=48000:d={duration}:c=stereo[a]")
        if s.pairs > 1:
            graph.append("[a]asplit=4[a0][a1][a2][a3]")
    args += ["-filter_complex", ";".join(graph), "-map", "[v]"]
    if preview:
        args += ["-frames:v", "1", "-c:v", "png", "-update", "1", str(output)]
        return args, overlay
    for i in range(s.pairs):
        args += ["-map", f"[a{i}]" if s.pairs > 1 else "[a]"]
    args += ["-t", str(duration), "-c:v", s.encoder,
             "-threads", "4", "-pix_fmt", s.pixel_format, "-r", str(s.fps),
             "-color_range", s.video_range, "-colorspace", matrix,
             "-color_primaries", primaries, "-color_trc", transfer]
    if s.editing_profile:
        args += ["-profile:v", s.editing_profile[2]]
        if s.encoder == "prores_ks":
            args += ["-alpha_bits", "0"]
            if s.interlaced:
                args += ["-flags", "+ilme+ildct", "-field_order", "tt" if s.field_order == "tff" else "bb"]
    else:
        args += ["-preset", s.preset, "-crf", QUALITY[s.quality], "-g", str(round(s.fps) * 2)]
    if s.encoder == "libx265":
        params = "pools=4:frame-threads=2:log-level=error"
        args += ["-x265-params", params]
        if s.container in ("mp4", "mov"):
            args += ["-tag:v", "hvc1"]
    elif s.interlaced and s.encoder == "libx264":
        args += ["-flags", "+ilme+ildct", "-x264-params", f"{s.field_order}=1"]
    if s.container == "mov":
        args += ["-c:a", "pcm_s24le"]
    else:
        args += ["-c:a", "aac", "-b:a", "256k"]
    args += ["-ar", "48000"]
    for i in range(s.pairs):
        args += [f"-metadata:s:a:{i}", f"title=Stereo {i + 1} - Channels {i * 2 + 1}-{i * 2 + 2}",
                 f"-disposition:a:{i}", "default" if i == 0 else "0"]
    if s.container in ("mp4", "mov"):
        args += ["-movflags", "+faststart"]
    else:
        args += ["-mpegts_flags", "+resend_headers"]
    args += ["-progress", "pipe:1", "-nostats", "-f", {"ts": "mpegts"}.get(s.container, s.container), str(output)]
    return args, overlay


def render(s, output, *, duration=None, progress=None, started=None, cancel=None):
    duration = s.duration if duration is None else duration
    args, overlay = build_command(s, output, duration=duration)
    log_path = Path(output).with_suffix(".log")
    feeder_errors = []
    with log_path.open("wb") as log:
        proc = subprocess.Popen(args, stdin=subprocess.PIPE if overlay else subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=log)
        if started:
            started(proc)

        def feed():
            try:
                multiplier = 2 if s.interlaced else 1
                for n in range(math.ceil(duration * s.fps) * multiplier + 2):
                    if cancel and cancel.is_set():
                        break
                    proc.stdin.write(overlay.frame(n // multiplier))
            except (BrokenPipeError, OSError):
                pass
            except Exception as exc:
                feeder_errors.append(str(exc))
                proc.terminate()
            finally:
                try:
                    proc.stdin.close()
                except OSError:
                    pass

        feeder = threading.Thread(target=feed, daemon=True) if overlay else None
        if feeder:
            feeder.start()
        for line in proc.stdout:
            key, _, value = line.decode(errors="replace").strip().partition("=")
            if key == "out_time_us" and value.lstrip("-").isdigit() and progress:
                progress(min(.99, max(0, int(value) / 1_000_000 / duration)))
        code = proc.wait()
        proc.stdout.close()
        if feeder:
            feeder.join(timeout=5)
    if cancel and cancel.is_set():
        raise InterruptedError("Render cancelled.")
    if code or feeder_errors:
        raise RuntimeError("\n".join(feeder_errors) or log_path.read_text(errors="replace")[-5000:] or "FFmpeg render failed.")
    actual = next(stream for stream in probe(output)["streams"] if stream["codec_type"] == "video")
    # Some decoders call full-range 8-bit formats yuvj420p/yuvj422p/yuvj444p.
    expected_pixel = "yuv444p12le" if s.delivery_profile in ("prores_4444", "prores_xq") else s.pixel_format
    if actual["pix_fmt"].replace("yuvj", "yuv") != expected_pixel:
        raise RuntimeError(f"Encoder returned {actual['pix_fmt']} instead of requested {s.pixel_format}.")
    expected_codec = {"libx264": "h264", "libx265": "hevc", "prores_ks": "prores", "dnxhd": "dnxhd"}[s.encoder]
    if actual["codec_name"] != expected_codec:
        raise RuntimeError(f"Encoder returned {actual['codec_name']} instead of requested {expected_codec}.")
    return args


def probe(path):
    if not FFPROBE:
        raise RuntimeError("ffprobe was not found. Install it with: brew install ffmpeg")
    result = subprocess.run([FFPROBE, "-v", "error", "-protocol_whitelist", "file,pipe", "-show_streams", "-show_format", "-of", "json", str(path)],
                            capture_output=True, text=True, check=True, timeout=30)
    return json.loads(result.stdout)


def capabilities():
    if not FFMPEG:
        return {"ready": False, "error": "FFmpeg not found. Run brew install ffmpeg, then restart."}
    try:
        version = subprocess.check_output([FFMPEG, "-version"], text=True, timeout=10).splitlines()[0]
        filters = subprocess.check_output([FFMPEG, "-hide_banner", "-filters"], text=True, timeout=10)
        encoders = subprocess.check_output([FFMPEG, "-hide_banner", "-encoders"], text=True, timeout=10)
        required = ("smptehdbars", "smptebars", "pal75bars", "pal100bars", "scroll", "overlay", "tinterlace", "aevalsrc", "colorspace")
        missing = [name for name in required if name not in filters]
        missing += [name for name in ("libx264", "aac", "pcm_s24le", "png") if name not in encoders]
        if not FFPROBE:
            missing.append("ffprobe")
        return {"ready": not missing, "version": version, "path": FFMPEG,
                "encoder_formats": {key: sorted(encoder_formats(encoder)) for key, encoder in
                                    (("h264", "libx264"), ("hevc", "libx265"), ("prores_ks", "prores_ks"), ("dnxhd", "dnxhd"))},
                "error": "Missing FFmpeg components: " + ", ".join(missing) if missing else None}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ready": False, "error": str(exc)}

"""Validated local upload storage, shared by patterns and transcoding."""
import json
import math
from pathlib import Path
import re
import warnings

from PIL import Image, ImageOps

UPLOADS = Path(__file__).resolve().parent / "uploads"
LOGO_FIELDS = ("logo_id", "logo_position", "logo_width", "logo_margin", "logo_opacity")
POSITIONS = ("top_left", "top_right", "bottom_left", "bottom_right", "centre")


def asset(ident, kind):
    if not isinstance(ident, str) or not re.fullmatch(r"[0-9a-f]{32}", ident):
        raise ValueError("Invalid upload ID.")
    try:
        item = json.loads((UPLOADS / f"{ident}.json").read_text())
    except (OSError, ValueError):
        raise ValueError("Upload not found. Please upload the file again.") from None
    path = UPLOADS / (ident + (".png" if kind == "logo" else ".media"))
    if item.get("kind") != kind or not path.is_file():
        raise ValueError("Upload type does not match.")
    return path, item


def validate_logo(s):
    if not isinstance(s.logo_id, str) or (s.logo_id and not re.fullmatch(r"[0-9a-f]{32}", s.logo_id)):
        raise ValueError("Invalid logo upload ID.")
    if not isinstance(s.logo_position, str) or s.logo_position not in POSITIONS:
        raise ValueError("Invalid logo position.")
    for key, low, high in (("logo_width", 2, 50), ("logo_margin", 0, 15), ("logo_opacity", 0, 100)):
        value = getattr(s, key)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f"{key} must be between {low} and {high}.")


def register_upload(path, ident, kind, name):
    from engine import probe
    info = {"id": ident, "kind": kind, "name": name[:180], "bytes": path.stat().st_size}
    if kind == "logo":
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as source:
                    if source.format not in ("PNG", "JPEG", "WEBP", "TIFF", "BMP"):
                        raise ValueError("Use a PNG, JPEG, WebP, TIFF or BMP logo.")
                    if source.width * source.height > 20_000_000:
                        raise ValueError("Logo must be no larger than 20 megapixels.")
                    image = ImageOps.exif_transpose(source).convert("RGBA")
                    image.thumbnail((4096, 4096), Image.Resampling.LANCZOS)
                    image.save(UPLOADS / f"{ident}.png")
                    info.update(width=image.width, height=image.height)
        except (OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise ValueError("The logo could not be decoded or is too large.") from exc
        path.unlink(missing_ok=True)
    else:
        metadata = probe(path)
        videos = [v for v in metadata.get("streams", []) if v.get("codec_type") == "video" and not v.get("disposition", {}).get("attached_pic")]
        if not videos:
            raise ValueError("The upload contains no video stream.")
        video = videos[0]
        if video.get("codec_name") == "prores_raw":
            raise ValueError("ProRes RAW input is not supported by this converter. Develop it in a compatible editor first, then export standard ProRes.")
        duration = float(video.get("duration") or metadata.get("format", {}).get("duration", 0))
        if not math.isfinite(duration) or duration <= 0:
            raise ValueError("Could not determine the video duration.")
        if not 1 <= video.get("width", 0) <= 16384 or not 1 <= video.get("height", 0) <= 16384:
            raise ValueError("Unsupported source dimensions.")
        path.rename(UPLOADS / f"{ident}.media")
        info.update(duration=duration, video=video, audio=[a for a in metadata["streams"] if a.get("codec_type") == "audio"])
    (UPLOADS / f"{ident}.json").write_text(json.dumps(info, indent=2))
    return info


def logo_graph(s, index, width, height, rate, work_format="yuv444p10le", colour_matrix="bt709"):
    """Return an image input and filter fragments; preserve alpha and aspect ratio."""
    path, meta = asset(s.logo_id, "logo")
    factor = min(width * s.logo_width / 100 / meta["width"], height * .5 / meta["height"])
    lw = max(2, round(meta["width"] * factor / 2) * 2)
    lh = max(2, round(meta["height"] * factor / 2) * 2)
    margin = round(min(width, height) * s.logo_margin / 100)
    x = str(margin) if "left" in s.logo_position else f"W-w-{margin}"
    y = str(margin) if "top" in s.logo_position else f"H-h-{margin}"
    if s.logo_position == "centre":
        x, y = "(W-w)/2", "(H-h)/2"
    alpha_format = work_format.replace("yuv", "yuva")
    args = ["-loop", "1", "-framerate", str(rate), "-i", str(path)]
    filt = (f"[{index}:v]format=rgba,colorchannelmixer=aa={s.logo_opacity / 100},"
            f"scale={lw}:{lh}:out_color_matrix={colour_matrix}:out_range=tv,"
            f"format={alpha_format},setparams=colorspace={colour_matrix}[logo]")
    return args, filt, x, y

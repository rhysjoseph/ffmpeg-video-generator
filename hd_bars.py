"""Native planar HD bars. The twelve scan lines expand vertically without interpolation."""
from array import array
from functools import lru_cache
from math import ceil, pi, sin
from pathlib import Path
import sys
import tempfile


# SMPTE RP 219-2002 Annex B, in 8-, 10- and 12-bit Y', Cb, Cr code values.
PATCHES = {
    "grey": ((104,128,128), (414,512,512), (1658,2048,2048)),
    "white75": ((180,128,128), (721,512,512), (2884,2048,2048)),
    "yellow": ((168,44,136), (674,176,543), (2694,704,2171)),
    "cyan": ((145,147,44), (581,589,176), (2325,2356,704)),
    "green": ((133,63,52), (534,253,207), (2136,1012,827)),
    "magenta": ((63,193,204), (251,771,817), (1004,3084,3269)),
    "red": ((51,109,212), (204,435,848), (815,1740,3392)),
    "blue": ((28,212,120), (111,848,481), (446,3392,1925)),
    "cyan100": ((188,154,16), (754,615,64), (3015,2459,256)),
    "blue100": ((32,240,118), (127,960,471), (509,3840,1884)),
    "yellow100": ((219,16,138), (877,64,553), (3507,256,2212)),
    "red100": ((63,102,240), (250,409,960), (1001,1637,3840)),
    "black": ((16,128,128), (64,512,512), (256,2048,2048)),
    "white": ((235,128,128), (940,512,512), (3760,2048,2048)),
    "grey15": ((49,128,128), (195,512,512), (782,2048,2048)),
    "minus2": ((12,128,128), (46,512,512), (186,2048,2048)),
    "plus2": ((20,128,128), (82,512,512), (326,2048,2048)),
    "plus4": ((25,128,128), (99,512,512), (396,2048,2048)),
}
# Segment ends in 1920-sample coordinates (Annex C recommended widths).
ROWS = (
    ((240,"grey"), (446,"white75"), (652,"yellow"), (858,"cyan"), (1062,"green"),
     (1268,"magenta"), (1474,"red"), (1680,"blue"), (1920,"grey")),
    ((240,"cyan100"), (1680,"white75"), (1920,"blue100")),
    ((240,"yellow100"), (446,"black"), (1680,"ramp"), (1920,"red100")),
    ((240,"grey15"), (548,"black"), (960,"white"), (1130,"black"), (1198,"minus2"),
     (1268,"black"), (1336,"plus2"), (1406,"black"), (1474,"plus4"), (1680,"black"), (1920,"grey15")),
)


_STORAGE = tempfile.TemporaryDirectory(prefix="hd-bars-")


@lru_cache(maxsize=64)
def plate(width, depth, double_clock=False, fractional=False):
    # 55 ns from 10% to 90%. For an integrated sin² pulse that interval is
    # 0.482188 of the support. Scale the sampled width for the non-HD rasters.
    clock = 74.25e6 * (2 if double_clock else 1) / (1.001 if fractional else 1)
    support = 55e-9 * clock / 0.482188
    if width > 1920:
        support *= width / 1920
    values = {name: triplets[(depth-8)//2] for name, triplets in PATCHES.items()}
    data = array("B" if depth == 8 else "H")
    for component in range(3):
        for segments, height in zip(ROWS, (7,1,1,3)):
            row, start = [], 0
            joins = []
            for end, name in segments:
                stop = round(end * width / 1920)
                if name == "ramp":
                    black, white = values["black"][component], values["white"][component]
                    row.extend(black + (white-black)*i/(stop-start-1) for i in range(stop-start))
                else:
                    row.extend([values[name][component]] * (stop-start))
                if start:
                    joins.append(start)
                start = stop
            for boundary in joins:
                left, right = row[boundary-1], row[boundary]
                for x in range(ceil(boundary-.5-support/2), ceil(boundary-.5+support/2)):
                    t = (x+.5-boundary)/support + .5
                    weight = t - sin(2*pi*t)/(2*pi)
                    row[x] = left + (right-left)*weight
            data.extend([round(v) for v in row] * height)
    if depth > 8 and sys.byteorder == "big":
        data.byteswap()
    # Independent names also cover concurrent first use from multiple render jobs.
    with tempfile.NamedTemporaryFile(dir=_STORAGE.name, suffix=".yuv", delete=False) as f:
        data.tofile(f)
        return Path(f.name)


def source_args(width, height, depth, fps, interlaced=False):
    pixel = "yuv444p" + (f"{depth}le" if depth > 8 else "")
    path = plate(width, depth, height >= 1080 and fps > 30 and not interlaced, fps.denominator == 1001)
    return (["-f", "rawvideo", "-pixel_format", pixel, "-video_size", f"{width}x12",
             "-framerate", str(fps), "-i", str(path)],
            f"scale={width}:{height}:flags=neighbor,format={pixel},setsar=1,loop=loop=-1:size=1:start=0,setpts=N")

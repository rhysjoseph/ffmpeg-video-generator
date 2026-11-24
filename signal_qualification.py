"""Reproducible signal, encoding and conversion qualification for Pattern Studio."""
import argparse
from array import array
from dataclasses import asdict
from fractions import Fraction
from itertools import combinations, product
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import tempfile

import assets
from delivery import generation_profiles
from duration_tests import exercise
from engine import COLOURS, DURATIONS, FFMPEG, QUALITY, RATES, RESOLUTIONS, Settings, build_command, probe, render
from transcode import ConvertSettings, PRESETS, convert, plan
from verification import export_expectations, primary, tool_versions, verify


GROUPS = ("generate", "editing", "duration", "convert", "proxy", "bars", "aac", "colour")

FACTORS = {
    "resolution": tuple(RESOLUTIONS), "rate": tuple(RATES), "bit_depth": (8,10,12),
    "chroma": ("420","422","444"), "colour": tuple(COLOURS), "video_range": ("pc","tv"),
    "codec": ("auto","hevc","h264"), "quality": tuple(QUALITY), "preset": ("ultrafast","fast","medium","slow"),
    "container": ("mov","mp4","ts"), "field_order": ("tff","bff"),
}
FULL = (
    ("3840x2160","24p",8,"420","bt709","tv","h264","ultrafast","sweep","prores_proxy"),
    ("2560x1440","29.97p",10,"422","bt2020","tv","hevc","fast","scroll","prores_hq"),
    ("1920x1080","25p",10,"444","bt601_pal","pc","h264","fast","sweep","dnxhr_444"),
    ("1280x720","23.98p",8,"420","bt601_ntsc","tv","h264","ultrafast","scroll","dnxhr_sq"),
)


def setting_pairs(row):
    return set(combinations(row.items(), 2))


def design():
    # Cover every feasible pair, including rare pairs, independently of random candidate frequency.
    rng = random.Random(219)
    triples = []
    for rate, codec, depth in product(FACTORS["rate"], FACTORS["codec"], FACTORS["bit_depth"]):
        if codec == "h264" and depth == 12 or rate.endswith("i") and (codec == "hevc" or depth == 12):
            continue
        triples.append(dict(rate=rate, codec=codec, bit_depth=depth))
    pool = []
    for a,b in combinations(FACTORS,2):
        for av,bv in product(FACTORS[a],FACTORS[b]):
            pair = {a:av, b:bv}
            legal = [t for t in triples if all(t.get(k,v) == v for k,v in pair.items())]
            if legal:
                for _ in range(3):
                    row = {k:rng.choice(opts) for k,opts in FACTORS.items()}
                    row.update(rng.choice(legal))
                    row.update(pair)
                    pool.append((row, setting_pairs(row)))
    needed = set.union(*(pairs for _,pairs in pool))
    count = len(needed)
    selected = []
    while needed:
        row,pairs = max(pool,key=lambda candidate: len(candidate[1] & needed))
        selected.append(row)
        needed -= pairs
    return selected, count


def report_fields(report):
    result = {k:report[k] for k in ("status","errors","review","comparison","loop_boundary") if k in report}
    if "scan" in report:
        result["scan"] = report["scan"]
    if "inventory" in report:
        v = primary(report["inventory"])
        result["measured"] = {k:v.get(k) for k in ("codec_name","profile","pix_fmt","width","height",
                              "r_frame_rate","field_order","color_range","color_space","color_transfer","color_primaries")}
    return result


def master(settings, target, seconds):
    # Tap the pre-encoder signal. Independent native-level checks below test the source itself.
    args,_ = build_command(settings, target, duration=seconds)
    args = args[:args.index("-c:v")] + ["-c:v","ffv1","-threads","4","-pix_fmt",settings.pixel_format,
            "-color_range", settings.video_range, "-colorspace", settings.colour_tags[0],
            "-color_primaries", settings.colour_tags[1], "-color_trc",settings.colour_tags[2], "-c:a","pcm_s16le"]
    if settings.interlaced:
        args += ["-field_order","tt" if settings.field_order == "tff" else "bb"]
    subprocess.run([*args,str(target)],check=True,capture_output=True)


def read_patches(path, points):
    v = primary(probe(path))
    w,h,pixel = v["width"],v["height"],v["pix_fmt"]
    depth = 12 if "12le" in pixel else 10 if "10le" in pixel else 8
    sx = 1 if "444" in pixel else 2
    sy = 2 if "420" in pixel else 1
    raw = subprocess.check_output([FFMPEG,"-v","error","-i",str(path),"-map","0:V:0","-frames:v","1",
                                   "-pix_fmt",pixel,"-threads","1","-f","rawvideo","-"])
    samples = array("B" if depth == 8 else "H",raw)
    if depth > 8 and sys.byteorder == "big":
        samples.byteswap()
    plane_size = (w//sx)*(h//sy)
    result = []
    for px,py in points:
        x,y = int(w*px),int(h*py)
        chroma = (y//sy)*(w//sx)+x//sx
        result.append([samples[w*y+x], samples[w*h+chroma], samples[w*h+plane_size+chroma]])
    return depth,result


def neutral_checks(report, target, full):
    depth, samples = read_patches(target,[(.2,.9),(.4,.9)])
    scale = 1 << (depth-8)
    exp = [[0 if full else 16*scale,128*scale,128*scale],
           [(1<<depth)-1 if full else 235*scale,128*scale,128*scale]]
    delta = max(abs(a-b) for observed,expected in zip(samples,exp) for a,b in zip(observed,expected))
    report["black_white"] = {"observed":samples, "expected":exp, "max_code_error":delta}
    if delta > 2*scale:
        report["errors"].append("Black or white interior exceeds two 8-bit-equivalent codes.")


def generate_case(row, root):
    s = Settings.parse({**row,"timecode":False,"freeze_box":False})
    seconds = float(8/s.fps)
    target,ref = root/("generated."+s.container),root/"reference.mkv"
    render(s,target,duration=seconds)
    master(s,ref,seconds)
    expected = export_expectations({"settings":asdict(s)})
    report = report_fields(verify(target,ref,{**expected,"frames":8},details=False))
    neutral_checks(report,target,s.video_range == "pc")
    return report


def duration_case(index, root):
    raster,rate,depth,chroma,colour,rng,codec,preset,pattern,profile = FULL[index]
    seconds = DURATIONS[index]
    s = Settings.parse(dict(duration=seconds,resolution=raster,rate=rate,bit_depth=depth,chroma=chroma,
                            colour=colour,video_range=rng,codec=codec,preset=preset,pattern=pattern,
                            container="mov",seamless_loop=True))
    return {"settings":asdict(s),"profile":profile,**exercise(seconds,root,True,settings=s,profile=profile)}


# All colours are specified as normalised luma and signed, normalised chroma.
CHIPS = ((0,0,0), (.72,-.28,.12), (.28,.25,-.18), (1,0,0),
         (.43,.22,.29), (.61,-.22,-.24), (.34,-.12,.27), (.8,.06,-.17))


def chip_movie(path, width, height, depth, chroma, colour, full, fps, geometry=None, dnx=False):
    # Build eight frames with distinct upper and lower patterns. One chip moves each frame.
    tags = Settings(colour=colour,bit_depth=depth).colour_tags
    factor, top = 1 << (depth-8), (1 << depth)-1
    chips = CHIPS
    if dnx:
        # Decode normalised Y'CbCr to R'G'B' and independently encode the VC-3 matrix.
        kr,kb = {"bt709":(.2126,.0722),"bt2020nc":(.2627,.0593),
                 "smpte170m":(.299,.114),"bt470bg":(.299,.114)}[tags[0]]
        chips = []
        for y,cb,cr in CHIPS:
            red,blue = y+2*(1-kr)*cr,y+2*(1-kb)*cb
            green = (y-kr*red-kb*blue)/(1-kr-kb)
            luma = .2126*red+.7152*green+.0722*blue
            chips.append((luma,(blue-luma)/(2*(1-.0722)),(red-luma)/(2*(1-.2126))))
        tags = ("bt709",*tags[1:])
    rows = []
    for component in range(3):
        def code(chip):
            level = chip[component]
            if not component:
                return round(level*top) if full else round((16+219*level)*factor)
            return round(128*factor+level*(top if full else 224*factor))
        rows.append([array("B" if depth == 8 else "H", [code(chip)]) for chip in chips])
        if sys.byteorder == "big" and depth > 8:
            for value in rows[-1]:
                value.byteswap()
    raw_pixel = "yuv444p" + (f"{depth}le" if depth>8 else "")
    rng = "pc" if full else "tv"
    params = f"setparams=range={rng}:colorspace={tags[0]}:color_primaries={tags[1]}:color_trc={tags[2]}"
    pixel = raw_pixel.replace("444",chroma)
    filters = geometry or f"scale=in_range={rng}:out_range={rng}"
    args = [FFMPEG,"-v","error","-y","-f","rawvideo","-pixel_format",raw_pixel,"-video_size",f"{width}x{height}",
            "-framerate",str(fps),"-i","pipe:0","-vf",f"{params},{filters},format={pixel},{params}",
            "-c:v","ffv1","-threads","4","-pix_fmt",pixel,"-color_range",rng,"-colorspace",tags[0],
            "-color_primaries",tags[1],"-color_trc",tags[2],str(path)]
    with subprocess.Popen(args,stdin=subprocess.PIPE,stderr=subprocess.PIPE) as proc:
        try:
            with proc.stdin:
                for n in range(8):
                    for plane in rows:
                        upper = b"".join(plane[i].tobytes()*(width//4) for i in range(4))
                        lower = b"".join(plane[4+(i+n)%4].tobytes()*(width//4) for i in range(4))
                        proc.stdin.write(upper*(height//2) + lower*(height//2))
        except BrokenPipeError:
            pass
        message = proc.stderr.read().decode()
        if proc.wait():
            raise RuntimeError(message)


def convert_case(case, index, root, crf=None, speed=None):
    profile, full = case
    raster = tuple(reversed(RESOLUTIONS))[index//2 % 4]
    if profile == "dnxhd_hq":
        raster = "1920x1080"
    w,h = map(int,raster.split("x"))
    fit = ("pad","crop","stretch")[index%3]
    sw,sh = ((640,480),(1920,1080),(960,720),(1280,720))[index%4]
    depth = (8,10,12)[index%3]
    chroma = ("444","420","422")[index%3]
    colour = tuple(COLOURS)[(index//2 + index%2)%4]
    rate = Fraction(25) if index%4 < 2 or profile == "dnxhd_hq" else Fraction(30000,1001)
    double = bool(index%3 == 0 and profile != "dnxhd_hq")
    output_rate = 2*rate if double else rate
    ref, source = root/"reference.mkv", root/"source.mkv"
    chip_movie(source,sw,sh,depth,chroma,colour,full,rate)
    ident = "c"*32
    assets.register_upload(source,ident,"video","chips.mkv")
    container = PRESETS[profile][-1]
    settings = ConvertSettings(source_id=ident,profile=profile,resolution=raster,fit=fit,
                               rate=("50p" if rate == 25 else "59.94p") if double else "source",
                               proxy_crf=crf or (16 if full else 35),speed=speed or ("slow" if full else "ultrafast"))
    target = root/("output."+container)
    convert(settings,target)
    # The expected movie starts limited-range and is independently fitted using explicit geometry.
    if fit == "stretch":
        rw,rh = w,h
    else:
        ratio = (min if fit == "pad" else max)(Fraction(w,sw),Fraction(h,sh))
        rw,rh = round(sw*ratio/2)*2, round(sh*ratio/2)*2
    geom = f"scale={rw}:{rh}:flags=bicubic:in_range=tv:out_range=tv"
    if fit == "pad":
        geom += f",pad={w}:{h}:{(w-rw)//2}:{(h-rh)//2}"
    if fit == "crop":
        geom += f",crop={w}:{h}:{(rw-w)//2}:{(rh-h)//2}"
    geom += f",setsar=1,fps={output_rate}"
    dnx = PRESETS[profile][1] == "dnxhd"
    chip_movie(ref,sw,sh,depth,"444",colour,False,rate,geom,dnx)
    contract = export_expectations({"kind":"conversion","settings":asdict(settings),"conversion":plan(settings)})
    contract.update(zip(("color_space","color_primaries","color_transfer"),Settings(colour=colour,bit_depth=depth).colour_tags))
    if dnx:
        contract["color_space"] = "bt709"
    contract["frames"] = 16 if double else 8
    result = report_fields(verify(target,ref,contract,details=False))
    result["fixture"] = {"source_raster":[sw,sh],"source_fps":str(rate),"colour":colour,"depth":depth,
                         "full_range":full,"chroma":chroma,"fit":fit,"target":raster,"target_fps":str(output_rate),
                         "proxy_crf":settings.proxy_crf if container == "mp4" else None,
                         "speed":settings.speed if container == "mp4" else None}
    # Sample the centre of each of the four upper chips in actual output coordinates.
    points = [(((i+.5)*rw/4+(w-rw)/2)/w,(rh/4+(h-rh)/2)/h) for i in range(4)]
    points = [point for point in points if .01 < point[0] < .99]
    out_depth,observed = read_patches(target,points)
    ref_depth,expected = read_patches(ref,points)
    delta = max(abs(a/(1<<(out_depth-8))-b/(1<<(ref_depth-8)))
                for patch,ref_patch in zip(observed,expected) for a,b in zip(patch,ref_patch))
    result["chips"] = {"observed":observed,"expected":expected,"output_depth":out_depth,
                       "reference_depth":ref_depth,"max_8bit_equivalent_error":delta}
    if delta > 2:
        result["errors"].append("Interior chip level differs by more than two 8-bit-equivalent codes.")
    return result


# Published targets for decoded interiors, independent of the generator's plate data.
# RP 219-2002 Annex B, in screen order across the upper row.
UPPER = {
    8: ((104,180,168,145,133,63,51,28),(128,128,44,147,63,193,109,212),(128,128,136,44,52,204,212,120)),
    10: ((414,721,674,581,534,251,204,111),(512,512,176,589,253,771,435,848),(512,512,543,176,207,817,848,481)),
    12: ((1658,2884,2694,2325,2136,1004,815,446),(2048,2048,704,2356,1012,3084,1740,3392),
         (2048,2048,2171,704,827,3269,3392,1925)),
}
PLUGE = {8:(12,16,20,16,25),10:(46,64,82,64,99),12:(186,256,326,256,396)}
BARS = (
    ("1280x720","59.94p",8,False),("1920x1080","59.94i",10,False),
    ("1920x1080","50p",10,False),("1920x1080","59.94p",12,False),
    ("1920x1080","59.94p",12,True),
)


def bars_case(case, root):
    raster,rate,depth,marker = case
    s = Settings(resolution=raster,rate=rate,bit_depth=depth,chroma="444",timecode=False,freeze_box=marker,
                 quality="maximum",container="mov")
    w,h = s.dimensions
    clock = 74.25 * (2 if h==1080 and s.fps>30 else 1) / (1.001 if s.fps.denominator==1001 else 1)
    reference,target = root/"plate.mkv",root/"export.mov"
    seconds = float(8/s.fps)
    master(s,reference,seconds)
    render(s,target,duration=seconds)
    points = [(x/1920,.25) for x in (120,340,550,750,950,1160,1370,1560)]
    points += [(x/1920,.90) for x in (1160,1230,1300,1370,1440)]
    expected = list(zip(*UPPER[depth])) + [(y,1<<(depth-1),1<<(depth-1)) for y in PLUGE[depth]]
    result = {"errors":[],"review":[]}
    for stage,path in (("pre_encoder",reference),("decoded_export",target)):
        _,observed = read_patches(path,points)
        worst = max(abs(a-b) for patch,ref in zip(observed,expected) for a,b in zip(patch,ref))
        pixel = primary(probe(path))["pix_fmt"]
        def row_at(y):
            data = subprocess.check_output([FFMPEG,"-v","error","-i",str(path),"-map","0:V:0",
                    "-vf",f"crop=iw:2:0:{y}","-frames:v","1","-pix_fmt",pixel,"-f","rawvideo","-"])
            row = array("B" if depth == 8 else "H",data[:w*(1 if depth==8 else 2)])
            if depth>8 and sys.byteorder=="big":
                row.byteswap()
            return row
        ramp = row_at(h*17//24)
        a,b = round(w*446/1920), round(w*1680/1920)-1
        black,white = 16<<(depth-8),235<<(depth-8)
        margin = 16
        ramp_error = max(abs(ramp[x]-(black+(white-black)*(x-a)/(b-a))) for x in range(a+margin,b-margin))
        edge = row_at(h//4)
        lo,hi = UPPER[depth][0][:2]
        crossings = []
        for fraction in (.1,.9):
            level = lo+(hi-lo)*fraction
            for x in range(w//8-16,w//8+16):
                if edge[x] <= level < edge[x+1]:
                    crossings.append(x+(level-edge[x])/(edge[x+1]-edge[x]))
                    break
        rise_ns = (crossings[1]-crossings[0])*1000/clock if len(crossings)==2 else None
        result[stage] = {"patches":observed,"max_patch_error_codes":worst,"ramp_max_error_codes":round(ramp_error,3),
                         "ramp_distinct_interior_codes":len(set(ramp[a+margin:b-margin])),"luma_rise_ns":rise_ns}
        if stage=="pre_encoder" and (worst or ramp_error>.501):
            result["errors"].append("Pre-encoder patch or ramp differs from its native code target.")
        if rise_ns is None or not 49.5 <= rise_ns <= 60.5:
            result["review"].append(f"{stage} grey-to-white luma transition outside 55 ns ±10%.")
        if stage=="decoded_export" and (worst or ramp_error>.501):
            result["review"].append("Lossy decoding changes reference code values.")
    result["status"] = "failed" if result["errors"] else "review" if result["review"] else "checks passed"
    return result


# Linear-light BT.709 RGB to target RGB. Each matrix is M_target^-1 * M_709,
# where M maps the primary chromaticities to XYZ with a common D65 white.
GAMUT = {
    "bt709": ((1,0,0),(0,1,0),(0,0,1)),
    "bt2020": ((.62740390,.32928304,.04331307),(.06909729,.91954039,.01136232),
               (.01639144,.08801331,.89559525)),
    "bt601_pal": ((.95781476,.04218524,0),(0,1,0),(0,-.01193412,1.01193412)),
    "bt601_ntsc": ((1.06537903,-.05540087,-.00997816),(-.01963255,1.03636310,-.01673054),
                   (.00163205,.00441237,.99395558)),
}


def expected_colour(yuv, depth, colour, full):
    scale = 1 << (depth-8)
    y,cb,cr = ((v/scale-offset)/span for v,offset,span in zip(yuv,(16,128,128),(219,224,224)))
    red,blue = y+1.5748*cr, y+1.8556*cb
    green = (y-.2126*red-.0722*blue)/.7152
    linear = [math.copysign(((abs(v)+.099)/1.099)**(1/.45),v) if abs(v)>=.081 else v/4.5
              for v in (red,green,blue)]
    alpha,beta = (1.0993,.0181) if colour=="bt2020" and depth==12 else (1.099,.018)
    rgb = []
    for row in GAMUT[colour]:
        value = sum(k*v for k,v in zip(row,linear))
        # Extend the SDR transfer about zero for colours outside the target gamut.
        rgb.append(math.copysign(alpha*abs(value)**.45-(alpha-1),value) if abs(value)>=beta else 4.5*value)
    kr,kb = {"bt709":(.2126,.0722),"bt2020":(.2627,.0593)}.get(colour,(.299,.114))
    y = kr*rgb[0]+(1-kr-kb)*rgb[1]+kb*rgb[2]
    cb,cr = (rgb[2]-y)/(2*(1-kb)), (rgb[0]-y)/(2*(1-kr))
    top = (1<<depth)-1
    codes = [y*top if full else scale*(16+219*y)]
    codes.extend(128*scale+c*(top if full else 224*scale) for c in (cb,cr))
    return [max(0,min(top,round(v))) for v in codes]


def colour_case(case, root):
    colour,rng,depth = case
    settings = Settings(colour=colour,video_range=rng,bit_depth=depth,chroma="444",resolution="1280x720",
                        timecode=False,freeze_box=False,container="mov",quality="maximum")
    source,target = root/"master.mkv",root/"export.mov"
    master(settings,source,.32)
    render(settings,target,duration=.32)
    expected = [expected_colour(patch,depth,colour,rng=="pc") for patch in zip(*UPPER[depth])]
    points = [(x/1920,.25) for x in (120,340,550,750,950,1160,1370,1560)]
    result = {"expected":expected,"errors":[],"review":[]}
    for stage,path,limit in (("pre_encoder",source,1),("decoded_export",target,2)):
        _,observed = read_patches(path,points)
        largest = max(abs(a-b) for patch,ref in zip(observed,expected) for a,b in zip(patch,ref))
        result[stage] = {"observed":observed,"max_code_error":largest}
        if largest > limit*(1<<(depth-8)):
            result["errors"].append(f"{stage} differs from the independent SDR colour transform by more than {limit} 8-bit-equivalent code(s).")
    result["status"] = "failed" if result["errors"] else "checks passed"
    return result


def editing_rows():
    rows = []
    for i,(key,profile) in enumerate(generation_profiles().items()):
        for variant in range(2):
            interlace = key.startswith("prores") and variant
            rows.append(dict(delivery_profile=key,container="mov",bit_depth=profile["bit_depth"],chroma=profile["chroma"],
                             resolution=tuple(RESOLUTIONS)[(i+variant)%4],colour=tuple(COLOURS)[(i+variant)%4],
                             rate=("59.94i" if i%2 else "50i") if interlace else ("23.98p" if variant else "30p"),
                             field_order="bff" if i%2 else "tff"))
    return rows


def aac_case(case, index, root):
    seconds,container = case
    rate = ("24p","29.97p","50i","23.98p")[index//2]
    s = Settings.parse(dict(container=container,resolution="1920x1080" if rate.endswith("i") else "1280x720",
                            rate=rate,field_order="bff",duration=seconds,pattern="sweep",seamless_loop=True,
                            quality="high",preset="ultrafast"))
    target = root/("loop."+container)
    render(s,target)
    expected = export_expectations({"settings":asdict(s)})
    report = report_fields(verify(target,expected=expected,details=False,loop=True))
    report["settings"] = asdict(s)
    return report


def run(group,output):
    pairs = 0
    if group == "generate":
        inputs,pairs = design()
    elif group == "colour":
        inputs = list(product(COLOURS, ("tv", "pc"), (8,10,12)))
    elif group == "bars":
        inputs = BARS
    elif group == "editing":
        inputs = editing_rows()
    elif group == "duration":
        inputs = list(range(len(FULL)))
    elif group == "aac":
        inputs = list(product(DURATIONS,("mp4","ts")))
    elif group == "proxy":
        inputs = list(product(("hevc_proxy","hevc_proxy10"),((35,"fast"),(28,"ultrafast"),(28,"fast"),(16,"slow"))))
    else:
        inputs = list(product(PRESETS,(False,True)))
    results = {"tools":tool_versions(),"group":group,"planned":len(inputs),"cases":[]}
    if pairs:
        results["planned_distinct_pairs"] = pairs
    for index,case in enumerate(inputs):
        with tempfile.TemporaryDirectory(prefix="signal-qc-") as directory:
            root = Path(directory)
            assets.UPLOADS = root
            try:
                if group in ("generate","editing"):
                    result = generate_case(case,root)
                elif group == "duration":
                    result = duration_case(case,root)
                elif group == "aac":
                    result = aac_case(case,index,root)
                elif group == "proxy":
                    profile,(crf,speed) = case
                    result = convert_case((profile,False),26,root,crf,speed)
                elif group == "colour":
                    result = colour_case(case, root)
                elif group == "bars":
                    result = bars_case(case,root)
                else:
                    result = convert_case(case,index,root)
            except (RuntimeError,ValueError,OSError,subprocess.SubprocessError,KeyError,ArithmeticError) as exc:
                result = {"status":"failed","errors":[str(exc)]}
        if result.get("errors"):
            result["status"] = "failed"
        results["cases"].append({"case":case,**result})
        partial = output.with_suffix(".partial")
        partial.write_text(json.dumps(results,indent=2)+"\n")
        partial.replace(output)
        print(index+1,len(inputs),result["status"],result.get("errors"),flush=True)
    return any(case["status"] == "failed" for case in results["cases"])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("group",choices=GROUPS)
    parser.add_argument("--report",type=Path,required=True)
    args = parser.parse_args()
    raise SystemExit(int(run(args.group,args.report)))

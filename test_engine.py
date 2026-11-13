"""Run with python3 -m unittest -v. Integration checks use real FFmpeg renders."""
import array
import json
from dataclasses import replace
from fractions import Fraction
import math
from pathlib import Path
import subprocess
import tempfile
import unittest

from delivery import generation_profiles
from engine import FFMPEG, FFPROBE, PATTERNS, RATES, Settings, build_command, probe, render, timecode


class TimecodeTests(unittest.TestCase):
    def test_drop_frame_minute_and_tenth_minute(self):
        rate = Fraction(30000, 1001)
        expected = {0: "00:00:00;00", 1799: "00:00:59;29", 1800: "00:01:00;02",
                    17981: "00:09:59;29", 17982: "00:10:00;00", 107892: "01:00:00;00"}
        for frame, value in expected.items():
            self.assertEqual(timecode(frame, rate, True), value)
        self.assertEqual(timecode(3600, Fraction(60000, 1001), True), "00:01:00;04")
        self.assertEqual(timecode(35964, Fraction(60000, 1001), True), "00:10:00;00")

    def test_non_drop(self):
        self.assertEqual(timecode(1500, Fraction(25), False), "00:01:00:00")
        self.assertEqual(timecode(1440, Fraction(24000, 1001), False), "00:01:00:00")
        with self.assertRaises(ValueError):
            timecode(0, Fraction(25), True)

    def test_validation(self):
        for invalid in ({"duration": 999}, {"rate": "69.94i"}, {"container": "../../file"},
                        {"timecode": "yes"}, {"label": "a\nb"}, {"pattern": []}, {"unknown": True},
                        {"bit_depth": 16}, {"bit_depth": 10.0}, {"codec": "h264", "bit_depth": 12},
                        {"rate": "50i", "bit_depth": 12}, {"rate": "59.94i", "codec": "hevc"},
                        {"chroma": "411"}, {"colour": "pq"}, {"video_range": "unknown"}):
            with self.assertRaises((ValueError, TypeError)):
                Settings.parse(invalid)
        self.assertEqual(Settings.parse({"label": "100% : 'literal' 中文"}).label, "100% : 'literal' 中文")

    def test_editing_profile_validation(self):
        valid = {"delivery_profile": "prores_hq", "container": "mov", "bit_depth": 10, "chroma": "422"}
        self.assertEqual(Settings.parse(valid).encoder, "prores_ks")
        for invalid in ({"delivery_profile": "prores_raw"}, {**valid, "container": "mp4"},
                        {**valid, "bit_depth": 8}, {**valid, "chroma": "420"},
                        {**valid, "video_range": "pc"}, {**valid, "codec": "hevc"},
                        {**valid, "delivery_profile": "dnxhr_hqx", "rate": "50i"}):
            with self.subTest(settings=invalid), self.assertRaises(ValueError):
                Settings.parse(invalid)


@unittest.skipUnless(FFMPEG, "FFmpeg is required")
class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix="pattern-tests-")
        cls.root = Path(cls.temp.name)
        cls.base = Settings(resolution="1280x720", duration=10)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def make(self, name, settings, duration=.24):
        path = self.root / f"{name}.{settings.container}"
        render(settings, path, duration=duration)
        return path, probe(path)

    def pcm(self, path, stream="0:a:0"):
        raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-map", stream,
                                       "-f", "f32le", "-acodec", "pcm_f32le", "-"])
        samples = array.array("f")
        samples.frombytes(raw)
        return samples

    def test_all_patterns_render_with_overlays(self):
        for pattern in PATTERNS:
            with self.subTest(pattern=pattern):
                path, info = self.make(pattern, replace(self.base, pattern=pattern, label="100% : 'test' 中文"))
                self.assertGreater(path.stat().st_size, 1000)
                self.assertEqual(info["streams"][0]["width"], 1280)

    def test_all_frame_rates_and_interlace_flags(self):
        for rate, rational in RATES.items():
            with self.subTest(rate=rate):
                _, info = self.make(rate, replace(self.base, rate=rate, pattern="sweep"))
                video = info["streams"][0]
                self.assertEqual(Fraction(video["r_frame_rate"]), Fraction(rational))
                self.assertEqual(video["field_order"], "tt" if rate.endswith("i") else "progressive")
                self.assertEqual(video["color_space"], "bt709")

    def test_containers_and_four_discrete_stereo_tracks(self):
        for container in ("mp4", "mov", "ts"):
            with self.subTest(container=container):
                path, info = self.make(container, replace(self.base, container=container, audio="four_pairs"))
                audio = [s for s in info["streams"] if s["codec_type"] == "audio"]
                self.assertEqual(len(audio), 4)
                self.assertTrue(all(s["channels"] == 2 and s["sample_rate"] == "48000" for s in audio))
                self.assertTrue(all(s["codec_name"] == ("pcm_s24le" if container == "mov" else "aac") for s in audio))
                for i in range(4):
                    samples = self.pcm(path, f"0:a:{i}")
                    self.assertGreater(max(samples), .08)

    def test_tone_frequency_peak_and_silence(self):
        for level in ("-20", "-18", "-12", "silence"):
            with self.subTest(level=level):
                path, _ = self.make("tone" + level, replace(self.base, container="mov", level=level))
                pcm = self.pcm(path)
                left, right = pcm[::2], pcm[1::2]
                self.assertEqual(left, right)
                peak = max(abs(v) for v in left)
                if level == "silence":
                    self.assertEqual(peak, 0)
                else:
                    self.assertAlmostEqual(20 * math.log10(peak), int(level), places=3)
                    crossings = sum(a <= 0 < b for a, b in zip(left, left[1:]))
                    self.assertLess(abs(crossings * 48000 / len(left) - 1000), 5)

    def test_lipsync_audio_matches_flash_frames(self):
        s = replace(self.base, pattern="lipsync", container="mov", rate="29.97p", timecode=False, freeze_box=False)
        path, _ = self.make("sync", s, 1.2)
        pcm = self.pcm(path)[::2]
        self.assertGreater(max(pcm[:2000]), .09)
        self.assertEqual(max(pcm[10000:40000]), 0)
        self.assertGreater(max(pcm[48100:50000]), .09)
        raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-vf",
                                       "crop=2:2:640:360,format=gray", "-f", "rawvideo", "-"])
        luma = list(raw[::4])
        self.assertGreater(luma[0], 220)
        self.assertLess(luma[5], 40)
        self.assertGreater(luma[30], 220)

    def test_interlace_has_different_temporal_fields(self):
        path, _ = self.make("fields", replace(self.base, pattern="sweep", rate="50i", timecode=False, freeze_box=False))
        raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-frames:v", "1",
                                       "-pix_fmt", "gray", "-f", "rawvideo", "-"])
        top = raw[:1280]
        bottom = raw[1280:2560]
        top_white = [x for x, v in enumerate(top) if v > 200]
        bottom_white = [x for x, v in enumerate(bottom) if v > 200]
        self.assertTrue(top_white and bottom_white)
        self.assertGreater(min(bottom_white), min(top_white))

    def test_no_burnins_and_preview(self):
        s = replace(self.base, timecode=False, freeze_box=False)
        self.make("clean", s)
        target = self.root / "preview.png"
        command, overlay = build_command(replace(s, label="Preview"), target, preview=True)
        result = subprocess.run(command, input=overlay.frame(0), capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        from PIL import Image
        with Image.open(target) as im:
            self.assertEqual(im.size, (960, 540))

    def test_depth_chroma_and_codecs_are_preserved(self):
        for codec in ("h264", "hevc"):
            for depth in ((8, 10) if codec == "h264" else (8, 10, 12)):
                for chroma in ("420", "422", "444"):
                    with self.subTest(codec=codec, depth=depth, chroma=chroma):
                        s = replace(self.base, codec=codec, bit_depth=depth, chroma=chroma, label="Precision test")
                        _, info = self.make(f"{codec}-{depth}-{chroma}", s, .16)
                        video = info["streams"][0]
                        self.assertEqual(video["pix_fmt"], s.pixel_format)
                        self.assertEqual(video["codec_name"], "hevc" if codec == "hevc" else "h264")

    def test_colour_range_metadata_and_sample_conversion(self):
        white_levels = {}
        for colour in ("bt709", "bt2020", "bt601_pal", "bt601_ntsc"):
            for video_range in ("tv", "pc"):
                with self.subTest(colour=colour, video_range=video_range):
                    s = replace(self.base, bit_depth=12, chroma="444", colour=colour, video_range=video_range,
                                pattern="pal100bars", freeze_box=False, timecode=False, quality="maximum")
                    path, info = self.make(f"{colour}-{video_range}", s, .12)
                    v = info["streams"][0]
                    self.assertEqual((v["color_space"], v["color_primaries"], v["color_transfer"]), s.colour_tags)
                    self.assertEqual(v["color_range"], video_range)
                    raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-frames:v", "1",
                                                   "-vf", "crop=2:2:10:10", "-pix_fmt", "yuv444p12le", "-f", "rawvideo", "-"])
                    white_levels[colour, video_range] = int.from_bytes(raw[:2], "little")
        for colour in ("bt709", "bt2020", "bt601_pal", "bt601_ntsc"):
            self.assertAlmostEqual(white_levels[colour, "tv"], 235 * 16, delta=25)
            self.assertAlmostEqual(white_levels[colour, "pc"], 4095, delta=25)

    def test_hevc_containers_and_h264_interlace_orders(self):
        for container in ("mp4", "mov", "ts"):
            with self.subTest(container=container):
                s = replace(self.base, bit_depth=12, chroma="422", container=container)
                path, info = self.make(f"hevc-{container}", s, .24)
                v = info["streams"][0]
                self.assertEqual(v["codec_name"], "hevc")
                self.assertEqual(v["pix_fmt"], "yuv422p12le")
                # HEVC in TS may omit stream-level field_order; inspect decoded flags.
                from engine import FFPROBE
                import json
                frames = json.loads(subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v",
                    "-show_frames", "-show_entries", "frame=interlaced_frame", "-of", "json", str(path)]))["frames"]
                self.assertTrue(frames)
                self.assertTrue(all(not f["interlaced_frame"] for f in frames))
                self.assertEqual(Fraction(v["r_frame_rate"]), 25)
        for order in ("tff", "bff"):
            for chroma in ("420", "422", "444"):
                s = replace(self.base, rate="50i", field_order=order, bit_depth=10, chroma=chroma)
                _, info = self.make(f"avc-{order}-{chroma}", s)
                self.assertEqual(info["streams"][0]["field_order"], "tt" if order == "tff" else "bb")
                self.assertEqual(info["streams"][0]["pix_fmt"], s.pixel_format)

    def test_editing_profiles_and_pcm_tracks(self):
        for key, profile in generation_profiles().items():
            with self.subTest(profile=key):
                settings = replace(self.base, container="mov", delivery_profile=key,
                                   bit_depth=profile["bit_depth"], chroma=profile["chroma"],
                                   audio="four_pairs", label="Editing profile")
                _, info = self.make(key, settings, .16)
                video = info["streams"][0]
                self.assertEqual(video["codec_name"], "prores" if key.startswith("prores") else "dnxhd")
                expected_pixel = "yuv444p12le" if key in ("prores_4444", "prores_xq") else profile["pixel_format"]
                self.assertEqual(video["pix_fmt"], expected_pixel)
                self.assertEqual(Fraction(video["r_frame_rate"]), settings.fps)
                self.assertEqual(video["color_space"], "bt709")
                audio = [stream for stream in info["streams"] if stream["codec_type"] == "audio"]
                self.assertEqual(len(audio), 4)
                self.assertTrue(all(stream["codec_name"] == "pcm_s24le" and stream["channels"] == 2 for stream in audio))

    def test_prores_interlace_orders(self):
        for rate in ("50i", "59.94i"):
            for order in ("tff", "bff"):
                with self.subTest(rate=rate, order=order):
                    settings = replace(self.base, container="mov", delivery_profile="prores_hq",
                                       bit_depth=10, chroma="422", rate=rate, field_order=order)
                    path, info = self.make(f"prores-{rate}-{order}", settings)
                    self.assertEqual(info["streams"][0]["field_order"], "tb" if order == "tff" else "bt")
                    frames = json.loads(subprocess.check_output([FFPROBE, "-v", "error", "-select_streams", "v",
                        "-show_frames", "-show_entries", "frame=interlaced_frame,top_field_first", "-of", "json", str(path)]))["frames"]
                    self.assertTrue(frames)
                    self.assertTrue(all(frame["interlaced_frame"] == 1 and
                                        frame["top_field_first"] == (order == "tff") for frame in frames))

    def test_box_reflects_at_all_four_edges(self):
        s = replace(self.base, pattern="sweep", timecode=False, quality="maximum")
        path, _ = self.make("bounce", s, 6.08)
        raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-vf",
                                       "select='eq(n,0)+eq(n,50)+eq(n,75)+eq(n,100)+eq(n,150)',scale=320:180",
                                       "-fps_mode", "passthrough", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
        size = 320 * 180 * 3
        self.assertEqual(len(raw), 5 * size)
        positions = []
        for offset in range(0, len(raw), size):
            frame = raw[offset:offset + size]
            pixels = [i // 3 for i in range(0, size, 3)
                      if frame[i] < 90 and frame[i + 1] > 150 and 90 < frame[i + 2] < 230]
            self.assertTrue(pixels)
            positions.append((min(p % 320 for p in pixels), min(p // 320 for p in pixels)))
        for actual, expected in zip(positions, ((0, 0), (206, 170), (310, 85), (206, 0), (0, 170))):
            self.assertAlmostEqual(actual[0], expected[0], delta=3)
            self.assertAlmostEqual(actual[1], expected[1], delta=3)

    def test_high_depth_colour_preview(self):
        s = replace(self.base, bit_depth=12, chroma="444", colour="bt2020", video_range="pc")
        target = self.root / "colour-preview.png"
        command, overlay = build_command(s, target, preview=True)
        result = subprocess.run(command, input=overlay.frame(0), capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr.decode())


if __name__ == "__main__":
    unittest.main()

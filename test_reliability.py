"""Decoded-picture and cadence checks using synthetic signals with known content."""
from dataclasses import replace
from pathlib import Path

from PIL import Image, ImageDraw
from verification import loop_boundary, verify, validate_export
from threading import Event
from fractions import Fraction
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import assets
from engine import DURATIONS, FFMPEG, RATES, Settings, probe, render
from transcode import ConvertSettings, convert


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        patcher = patch.object(assets, "UPLOADS", self.root)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.ident = "c" * 32
        self.settings = ConvertSettings(source_id=self.ident, profile="prores_hq")

    def register(self, path):
        assets.register_upload(path, self.ident, "video", "fixture.mov")
        return self.root / (self.ident + ".media")

    def test_loop_schedule_closes_on_frames_samples_and_tone_cycles(self):
        for rate in RATES:
            for seconds in DURATIONS:
                s = Settings(duration=seconds, rate=rate, seamless_loop=True)
                span = Fraction(str(s.runtime))
                for frequency in (s.fps, 48000, 1000):
                    self.assertEqual((span * frequency).denominator, 1, (rate, seconds))

    def test_loop_mode_closes_moving_marker_and_sweep(self):
        s = Settings(resolution="1280x720", rate="25p", pattern="sweep", container="mov")
        for loop in (False, True):
            target = self.root / f"motion-{loop}.mov"
            render(replace(s, seamless_loop=loop, timecode=False), target)
            video, audio = probe(target)["streams"][:2]
            report, findings = loop_boundary(target, video, [audio], 250)
            # A small bar at opposite sides can produce the same mean RGB error
            # as a normal step. Compare actual positions for this known pattern.
            raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(target), "-map", "0:v:0",
                "-vf", "select='eq(n,0)+eq(n,249)',scale=320:180", "-pix_fmt", "rgb24",
                "-fps_mode", "passthrough", "-f", "rawvideo", "-"])
            frame_size = 320 * 180 * 3
            positions = []
            for offset in (0, frame_size):
                pixels = Image.frombytes("RGB", (320,180), raw[offset:offset+frame_size])
                sweep_x = next(x for x in range(320) if min(pixels.getpixel((x,90))) > 170)
                green = [(x,y) for y in range(180) for x in range(320)
                         if (rgb := pixels.getpixel((x,y)))[1] > 140 and rgb[0] < 90]
                positions.append((sweep_x,min(x for x,y in green),min(y for x,y in green)))
            largest_step = max(abs(a-b) for a,b in zip(*positions))
            self.assertEqual(largest_step < 16, loop, positions)
            if loop:
                self.assertFalse(findings, findings)
                self.assertEqual(report["audio"][0]["offset_from_video_samples"], 0)

    def test_loop_check_detects_a_visual_cut_and_audio_step(self):
        path = self.root / "cut.mov"
        subprocess.run([FFMPEG, "-v", "error", "-f", "lavfi", "-i",
            "color=c=black:s=160x90:r=25:d=1,drawbox=c=white:t=fill:enable='gte(t,0.5)'",
            "-f", "lavfi", "-i", "aevalsrc='if(lt(t,0.5),0.2,-0.2)':s=48000:d=1",
            "-c:v", "libx264", "-c:a", "pcm_s24le", str(path)], check=True)
        video, audio = probe(path)["streams"][:2]
        _, findings = loop_boundary(path, video, [audio], 25)
        self.assertTrue(any("picture transition" in f for f in findings))
        self.assertTrue(any("large step" in f for f in findings))

    def frames(self, path, width, height):
        raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(path), "-map", "0:v:0",
                                      "-pix_fmt", "gray", "-fps_mode", "passthrough", "-f", "rawvideo", "-"])
        size = width * height
        self.assertEqual(len(raw) % size, 0)
        return [raw[i:i+size] for i in range(0, len(raw), size)]

    def test_field_rate_motion(self):
        source = self.root / "interlaced.mov"
        render(Settings(resolution="1280x720", rate="50i", pattern="sweep", container="mov",
                        freeze_box=False, timecode=False), source, duration=.6)
        self.register(source)
        target = self.root / "50p.mov"
        convert(replace(self.settings, rate="50p"), target)
        frames = self.frames(target, 1280, 720)
        positions = [next(x for x, v in enumerate(f[360*1280:361*1280]) if v > 180) for f in frames]
        self.assertEqual(len(positions), 30)
        self.assertTrue(all(b > a for a, b in zip(positions, positions[1:])), positions)

    def test_anamorphic_fit_fill_and_stretch(self):
        # 320x240, SAR 2:1, displayed as 640x240. Coloured edge strips
        # make the difference between cropping and squashing measurable.
        img = Image.new("RGB", (320,240), (205,205,205))
        draw = ImageDraw.Draw(img)
        draw.rectangle((0,0,39,239), fill=(230,15,15))
        draw.rectangle((280,0,319,239), fill=(15,15,230))
        src = self.root / "wide.mkv"
        subprocess.run([FFMPEG, "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
                        "-video_size", "320x240", "-framerate", "25", "-i", "-", "-vf", "setsar=2",
                        "-c:v", "ffv1", str(src)], input=img.tobytes()*4, check=True)
        self.register(src)
        for fit in ("pad", "crop", "stretch"):
            with self.subTest(fit=fit):
                out = self.root / (fit + ".mov")
                convert(replace(self.settings, resolution="custom", width=320, height=240, fit=fit), out)
                raw = subprocess.check_output([FFMPEG, "-v", "error", "-i", str(out), "-frames:v", "1",
                                               "-pix_fmt", "rgb24", "-f", "rawvideo", "-"])
                frame = Image.frombytes("RGB", (320,240), raw)
                if fit == "pad":
                    self.assertLess(max(frame.getpixel((160, 45))), 8)
                    self.assertGreater(min(frame.getpixel((160, 70))), 180)
                else:
                    self.assertGreater(min(frame.getpixel((160, 45))), 180)
                left, right = frame.getpixel((5,120)), frame.getpixel((315,120))
                if fit == "crop":
                    self.assertGreater(min(left + right), 180)
                else:
                    self.assertGreater(left[0]-left[2], 150)
                    self.assertGreater(right[2]-right[0], 150)

    def test_ten_bit_avc_mov_decodes_before_conversion(self):
        path = self.root / "avc.mov"
        s = Settings(rate="25p", pattern="scroll", bit_depth=10, chroma="422",
                     container="mov", audio="four_pairs")
        render(s, path, duration=.32)
        report = verify(path, details=True)
        self.assertFalse(report["errors"], report)
        self.assertEqual(report["scan"]["decoded_frames"], 8)
        self.assertEqual(report["header_sample"]["bit_depth_luma_minus8"], "2")

    def test_green_half_and_sparse_grey_pixels_are_detected(self):
        source_image = Image.new("RGB", (320, 240), (25, 40, 170))
        reference = self.root / "reference.mkv"

        def encode(frames, path):
            subprocess.run([FFMPEG, "-v", "error", "-f", "rawvideo", "-pixel_format", "rgb24",
                            "-video_size", "320x240", "-framerate", "25", "-i", "pipe:0",
                            "-c:v", "ffv1", "-pix_fmt", "bgr0", str(path)],
                           input=b"".join(image.tobytes() for image in frames), check=True)

        encode([source_image]*4, reference)
        clean = verify(reference, reference, details=False)
        self.assertFalse(clean["errors"], clean)
        self.assertEqual(clean["scan"]["consecutive_identical"], 3)
        for defect in ("green", "speckles"):
            bad = source_image.copy()
            draw = ImageDraw.Draw(bad)
            if defect == "green":
                draw.rectangle((0,120,319,239), (0,255,0))
            else:
                draw.point((15,20), (140,140,140))
            path = self.root / (defect + ".mkv")
            encode([source_image, bad, source_image, source_image], path)
            result = verify(path, reference, details=False)
            self.assertEqual(result["status"], "failed")
            self.assertEqual(result["comparison"]["first_flat_error"]["frame"], 1)
            if defect == "green":
                self.assertGreater(result["comparison"]["bottom_half"]["mean_error"], 50)
                self.assertEqual(result["comparison"]["top_half"]["mean_error"], 0)

    def test_uhd_60p_444_conversion(self):
        source = self.root / "uhd.mov"
        render(Settings(resolution="3840x2160", rate="60p", container="mov", chroma="444", bit_depth=10,
                        delivery_profile="dnxhr_444"), source, duration=.1)
        original = self.register(source)
        target = self.root / "uhd-prores.mov"
        convert(replace(self.settings, profile="prores_4444"), target)
        report = verify(target, reference=original, expected={
            "width":3840, "height":2160, "fps":"60", "frames":6, "profile":"4444", "pix_fmt":"yuv444p12le",
            "field_order":"progressive"}, details=False)
        self.assertFalse(report["errors"], report)

    def test_gate_rejects_wrong_duration_and_truncated_media(self):
        path = self.root / "short.mov"
        s = Settings(resolution="1280x720", container="mov")
        render(s, path, duration=.4)
        result = validate_export(path, .4, Fraction(25), lambda p: None, Event())
        self.assertEqual(result["frames_decoded"], 10)
        with self.assertRaisesRegex(RuntimeError, "length"):
            validate_export(path, 2, Fraction(25), lambda p: None, Event())
        with path.open("r+b") as f:
            f.truncate(path.stat().st_size//2)
        with self.assertRaisesRegex(RuntimeError, "decode"):
            validate_export(path, .4, Fraction(25), lambda p: None, Event())

    def test_incomplete_file_fails(self):
        path = self.root / "incomplete.mp4"
        path.write_bytes(b"truncated")
        self.assertEqual(verify(path)["status"], "failed")

if __name__ == "__main__":
    unittest.main()

import json
from dataclasses import replace
from fractions import Fraction
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image, ImageDraw

import assets
from engine import FFMPEG, Settings, build_command, probe, render
from transcode import PRESETS, ConvertSettings, convert, plan


@unittest.skipUnless(FFMPEG, "FFmpeg required")
class MediaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix="studio-media-tests-")
        cls.root = Path(cls.tmp.name)
        cls.uploads = cls.root / "uploads"
        cls.uploads.mkdir()
        cls.patcher = patch.object(assets, "UPLOADS", cls.uploads)
        cls.patcher.start()
        cls.logo_id = "a" * 32
        cls.source_id = "b" * 32
        image = Image.new("RGBA", (200,100), (0,0,0,0))
        ImageDraw.Draw(image).rectangle((40,20,159,79), fill=(255,0,0,255))
        image.save(cls.uploads / "logo.upload", format="PNG")
        assets.register_upload(cls.uploads / "logo.upload", cls.logo_id, "logo", "Test logo.png")
        cls.source = cls.uploads / "source.mov"
        render(Settings(resolution="1280x720", container="mov", audio="four_pairs", timecode=False, freeze_box=False), cls.source, duration=1.2)
        assets.register_upload(cls.source, cls.source_id, "video", "Source.mov")
        cls.base = ConvertSettings(source_id=cls.source_id, resolution="custom", width=640, height=360, length=.24)

    @classmethod
    def tearDownClass(cls):
        cls.patcher.stop()
        cls.tmp.cleanup()

    def output(self, s, name="converted"):
        p = plan(s)
        path = self.root / f"{name}.{p['container']}"
        convert(s, path)
        return path, probe(path)

    def test_all_conversion_presets(self):
        for profile, preset in PRESETS.items():
            with self.subTest(profile=profile):
                s = replace(self.base, profile=profile, resolution="1920x1080" if profile=="dnxhd_hq" else "custom")
                _, meta = self.output(s, profile)
                video = meta["streams"][0]
                self.assertEqual(video["codec_name"], "prores" if preset[1]=="prores_ks" else "hevc" if preset[1]=="libx265" else "dnxhd")
                self.assertEqual(video["height"], 1080 if profile=="dnxhd_hq" else 360)
                audio = [v for v in meta["streams"] if v["codec_type"]=="audio"]
                self.assertEqual(len(audio), 4)
                self.assertTrue(all(v["channels"]==2 for v in audio))

    def test_dnxhd_rates(self):
        for rate in ("23.98p", "24p", "25p", "29.97p", "30p"):
            with self.subTest(rate=rate):
                s = replace(self.base, profile="dnxhd_hq", resolution="1920x1080", rate=rate, length=.12)
                self.output(s, "dnxhd-" + rate)

    def test_trim_rate_and_audio_removal(self):
        s = replace(self.base, profile="hevc_proxy", rate="50p", start=.2, length=.6, audio="mute")
        _, meta = self.output(s)
        self.assertEqual(len(meta["streams"]), 1)
        self.assertEqual(Fraction(meta["streams"][0]["r_frame_rate"]), 50)
        self.assertAlmostEqual(float(meta["format"]["duration"]), .6, delta=.05)

    def test_geometry_and_logos(self):
        for fit in ("pad", "crop", "stretch"):
            with self.subTest(fit=fit):
                s = replace(self.base, fit=fit, width=640, height=480, logo_id=self.logo_id, logo_position="bottom_right", logo_opacity=60)
                _, meta = self.output(s, fit)
                self.assertEqual((meta["streams"][0]["width"],meta["streams"][0]["height"]),(640,480))

    def test_generator_logo_with_and_without_text_and_high_depth(self):
        for tc, depth in ((False,8),(True,8),(True,12)):
            s=Settings(resolution="1280x720",timecode=tc,bit_depth=depth,logo_id=self.logo_id,logo_position="centre",label="Logo" if tc else "")
            path=self.root/f"logo-{tc}-{depth}.mp4"
            render(s,path,duration=.2)
            self.assertEqual(probe(path)["streams"][0]["pix_fmt"],s.pixel_format)

    def test_transparent_logo_pixels(self):
        s=Settings(resolution="1280x720",timecode=False,freeze_box=False,logo_position="top_left",logo_width=20,logo_margin=0)
        images=[]
        for ident in ("",self.logo_id):
            p=self.root/f"preview-{bool(ident)}.png"
            command,_=build_command(replace(s,logo_id=ident),p,preview=True)
            subprocess.run(command,check=True,capture_output=True)
            with Image.open(p) as im:images.append(im.convert("RGB"))
        self.assertEqual(images[0].getpixel((5,5)),images[1].getpixel((5,5)))
        red=images[1].getpixel((95,45))
        self.assertGreater(red[0],200)
        self.assertLess(red[1],50)

    def test_invalid_uploads_and_settings(self):
        for data in ({"source_id":self.source_id,"profile":"prores_raw"},
                     {"source_id":self.source_id,"width":641},
                     {"source_id":"../../file"},
                     {"source_id":self.source_id,"logo_width":101}):
            with self.assertRaises(ValueError):ConvertSettings.parse(data)
        with self.assertRaises(ValueError):plan(replace(self.base,profile="dnxhd_hq"))
        with self.assertRaises(ValueError):plan(replace(self.base,start=2))
        bad=self.uploads/"bad.upload"
        bad.write_bytes(b"not an image")
        with self.assertRaises(ValueError):assets.register_upload(bad,"c"*32,"logo","bad.png")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Tests for the .xavatar builder. Run: python3 -m unittest discover -s tests"""

from __future__ import annotations

import io
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.xavatar import core  # noqa: E402


class XAvatarTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls._tmpdir = tempfile.TemporaryDirectory()
        cls.tmp = Path(cls._tmpdir.name)
        cls.source = cls.tmp / "source.png"

        img = Image.new("RGBA", (640, 480))
        pixels = img.load()
        for y in range(480):
            for x in range(640):
                pixels[x, y] = (x % 256, y % 256, (x + y) % 256, 255)
        img.save(cls.source)

    @classmethod
    def tearDownClass(cls) -> None:
        cls._tmpdir.cleanup()

    def build(self, name: str, **kwargs) -> Path:
        return core.build_avatar(self.source, self.tmp / name, **kwargs)

    def test_offline_package(self) -> None:
        out = self.build("offline.xavatar")
        with zipfile.ZipFile(out) as zf:
            names = zf.namelist()
            self.assertEqual(
                set(names), set(core.AVATAR_NAMES + core.OFFLINE_NAMES)
            )
            self.assertEqual(zf.read("avatar.png"), zf.read("picture.png"))
            json.loads(zf.read("online.json"))
            self.check_dds(zf, [n for n in names if n.endswith(".dds")])

    def test_online_package(self) -> None:
        out = self.build("online.xavatar", offline=False)
        with zipfile.ZipFile(out) as zf:
            self.assertEqual(set(zf.namelist()), set(core.AVATAR_NAMES))

    def test_circle_alpha(self) -> None:
        out = self.build("circle.xavatar", circle=True, offline=False)
        with zipfile.ZipFile(out) as zf:
            img = Image.open(io.BytesIO(zf.read("avatar.png"))).convert("RGBA")
        self.assertEqual(img.size, (440, 440))
        self.assertEqual(img.getpixel((0, 0))[3], 0)
        self.assertEqual(img.getpixel((220, 220))[3], 255)

    def test_stretch(self) -> None:
        out = self.build("stretch.xavatar", crop=False, offline=False)
        with zipfile.ZipFile(out) as zf:
            img = Image.open(io.BytesIO(zf.read("avatar.png")))
        self.assertEqual(img.size, (440, 440))

    def test_missing_input(self) -> None:
        with self.assertRaises(core.XAvatarError):
            core.build_avatar(self.tmp / "nope.png", self.tmp / "x.xavatar")

    def test_build_bytes(self) -> None:
        raw = self.source.read_bytes()
        package = core.build_bytes(raw, crop=True, circle=False, offline=True)
        with zipfile.ZipFile(io.BytesIO(package)) as zf:
            self.assertEqual(
                set(zf.namelist()), set(core.AVATAR_NAMES + core.OFFLINE_NAMES)
            )

    def test_preview_is_png(self) -> None:
        png = core.preview_png(self.source.read_bytes(), crop=True, circle=True)
        self.assertEqual(png[:8], b"\x89PNG\r\n\x1a\n")
        with Image.open(io.BytesIO(png)) as img:
            self.assertLessEqual(max(img.size), 320)

    def check_dds(self, zf: zipfile.ZipFile, names: list[str]) -> None:
        for name in names:
            data = zf.read(name)
            self.assertEqual(data[:4], b"DDS ")
            width, height = struct.unpack_from("<II", data, 12)
            dimension = int("".join(c for c in Path(name).stem if c.isdigit()))
            self.assertEqual((width, height), (dimension, dimension), name)
            self.assertEqual(data[84:88], b"DXT5", name)
            self.assertEqual(struct.unpack_from("<I", data, 76)[0], 32, name)


if __name__ == "__main__":
    unittest.main()

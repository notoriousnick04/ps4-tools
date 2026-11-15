#!/usr/bin/env python3
"""HTTP tests for the local web UI. Run: python3 -m unittest discover -s tests"""

from __future__ import annotations

import base64
import io
import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import server  # noqa: E402
from tools.xavatar import core  # noqa: E402


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.httpd = server.create_server("127.0.0.1", 0)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

        img = Image.new("RGB", (300, 200), (120, 80, 200))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        cls.image_b64 = base64.b64encode(buf.getvalue()).decode()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.httpd.shutdown()
        cls.httpd.server_close()
        cls.thread.join(timeout=5)

    def get(self, path: str) -> urllib.response.addinfourl:
        return urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}", timeout=15)

    def post(self, path: str, payload: dict):
        data = json.dumps(payload).encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        return urllib.request.urlopen(request, timeout=30)

    def test_hub_lists_tools(self) -> None:
        with self.get("/") as response:
            self.assertEqual(response.status, 200)
            body = response.read().decode()
        self.assertIn("PS4", body)
        self.assertIn("XAVATAR Maker", body)
        self.assertIn('href="/xavatar"', body)

    def test_tool_page(self) -> None:
        with self.get("/xavatar") as response:
            body = response.read().decode()
        self.assertEqual(response.status, 200)
        self.assertIn("Create .xavatar", body)
        self.assertIn("/xavatar/static/app.js", body)

    def test_static_assets(self) -> None:
        with self.get("/static/style.css") as response:
            self.assertEqual(response.headers["Content-Type"], "text/css")
            self.assertIn("--accent", response.read().decode())
        with self.get("/xavatar/static/app.js") as response:
            self.assertIn("createPackage", response.read().decode())
        with self.get("/static/icon.svg") as response:
            self.assertEqual(response.headers["Content-Type"], "image/svg+xml")
            self.assertIn(b"<svg", response.read())
        with self.get("/static/logo.png") as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")

    def test_path_traversal_blocked(self) -> None:
        for path in ("/static/../server.py", "/static/%2e%2e/server.py"):
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.get(path)
            self.assertEqual(ctx.exception.code, 404)

    def test_preview(self) -> None:
        with self.post(
            "/api/xavatar/preview",
            {"image": f"data:image/png;base64,{self.image_b64}", "crop": True},
        ) as response:
            self.assertEqual(response.headers["Content-Type"], "image/png")
            data = response.read()
        self.assertEqual(data[:8], b"\x89PNG\r\n\x1a\n")

    def test_build(self) -> None:
        with self.post(
            "/api/xavatar/build",
            {
                "image": self.image_b64,
                "crop": True,
                "circle": False,
                "offline": True,
                "filename": "My Avatar.png",
            },
        ) as response:
            self.assertEqual(response.headers["Content-Type"], "application/zip")
            self.assertIn(
                'filename="My-Avatar.xavatar"',
                response.headers["Content-Disposition"],
            )
            data = response.read()

        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(
                set(zf.namelist()), set(core.AVATAR_NAMES + core.OFFLINE_NAMES)
            )

    def test_build_without_offline(self) -> None:
        with self.post(
            "/api/xavatar/build",
            {"image": self.image_b64, "offline": False, "filename": "online"},
        ) as response:
            data = response.read()
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            self.assertEqual(set(zf.namelist()), set(core.AVATAR_NAMES))

    def test_bad_requests(self) -> None:
        cases = [
            ("/api/xavatar/preview", {"image": "not base64!"}),
            ("/api/xavatar/nope", {"image": self.image_b64}),
            ("/api/unknown/preview", {"image": self.image_b64}),
        ]
        for path, payload in cases:
            with self.assertRaises(urllib.error.HTTPError) as ctx:
                self.post(path, payload)
            self.assertIn(ctx.exception.code, (400, 404))
            if ctx.exception.code == 400:
                body = json.loads(ctx.exception.read())
                self.assertIn("error", body)

    def test_not_found(self) -> None:
        with self.assertRaises(urllib.error.HTTPError) as ctx:
            self.get("/does-not-exist")
        self.assertEqual(ctx.exception.code, 404)


if __name__ == "__main__":
    unittest.main()

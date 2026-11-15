"""XAVATAR Maker: turn a picture into a PS4 .xavatar package."""

from __future__ import annotations

import base64
import binascii
import re
from pathlib import Path

from ..base import ToolError
from . import core

SLUG = "xavatar"
TITLE = "XAVATAR Maker"
SUMMARY = "Turn a picture into a PS4 .xavatar avatar package."
STATIC = Path(__file__).resolve().parent / "static"

MAX_UPLOAD = 25 * 1024 * 1024
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _decode_image(payload: dict) -> bytes:
    data = payload.get("image")
    if not isinstance(data, str) or not data:
        raise ToolError("No image received")
    if data.startswith("data:"):
        _, _, data = data.partition(",")
    try:
        raw = base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ToolError("Image data is not valid base64") from exc
    if not raw:
        raise ToolError("The image is empty")
    if len(raw) > MAX_UPLOAD:
        raise ToolError("Image is larger than 25 MB")
    return raw


def _filename(payload: dict) -> str:
    name = _UNSAFE.sub("-", str(payload.get("filename") or "avatar")).strip("-.")
    if not name:
        name = "avatar"
    if name.lower().endswith(".xavatar"):
        return name
    if "." in name:
        name = name.rsplit(".", 1)[0]
    return f"{name}.xavatar"


def handle(action: str, payload: dict) -> tuple[str, bytes, dict[str, str]]:
    """Return (content type, body, extra headers) for one API call."""
    if action == "preview":
        png = core.preview_png(
            _decode_image(payload),
            crop=bool(payload.get("crop", True)),
            circle=bool(payload.get("circle", False)),
        )
        return "image/png", png, {}

    if action == "build":
        try:
            package = core.build_bytes(
                _decode_image(payload),
                crop=bool(payload.get("crop", True)),
                circle=bool(payload.get("circle", False)),
                offline=bool(payload.get("offline", True)),
            )
        except core.XAvatarError as exc:
            raise ToolError(str(exc)) from exc
        name = _filename(payload)
        return (
            "application/zip",
            package,
            {"Content-Disposition": f'attachment; filename="{name}"'},
        )

    raise ToolError(f"Unknown action: {action}")

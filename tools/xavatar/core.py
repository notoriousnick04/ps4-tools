"""Build .xavatar packages for PS4 (offline-activated accounts).

A .xavatar file is a ZIP containing:
    avatar.png, avatar64.dds, avatar128.dds, avatar260.dds, avatar440.dds
and, for offline-activated profiles, also:
    picture.png, picture64.dds, picture128.dds, picture260.dds,
    picture440.dds, online.json
"""

from __future__ import annotations

import io
import shutil
import struct
import subprocess
import tempfile
import zipfile
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageOps
except ImportError as exc:  # pragma: no cover - launcher checks this first
    raise SystemExit("Pillow is required: sudo pacman -S python-pillow") from exc

SIZES = (440, 260, 128, 64)
AVATAR_NAMES = ["avatar.png"] + [f"avatar{s}.dds" for s in SIZES]
OFFLINE_NAMES = ["picture.png"] + [f"picture{s}.dds" for s in SIZES] + ["online.json"]

# Same metadata Lapy's "PS4 Avatar Maker 1.7" writes for offline-activated accounts.
OFFLINE_JSON = r'''{"avatarUrl":"http:\/\/static-resource.np.community.playstation.net\/avatar_xl\/WWS_E\/E0012_XL.png","firstName":"","lastName":"","pictureUrl":"https:\/\/image.api.np.km.playstation.net\/images\/?format=png&w=440&h=440&image=https%3A%2F%2Fkfscdn.api.np.km.playstation.net%2F00000000000008%2F000000000000003.png&sign=blablabla019501","trophySummary":"{\"level\":1,\"progress\":0,\"earnedTrophies\":{\"platinum\":0,\"gold\":0,\"silver\":0,\"bronze\":0}}","isOfficiallyVerified":"true"}'''

MAX_PNG = 2 * 1024 * 1024
MAX_PACKAGE = 4 * 1024 * 1024

# A path on disk or raw image bytes (as uploaded from the web UI).
Source = str | Path | bytes


class XAvatarError(Exception):
    pass


def _magick() -> str:
    for name in ("magick", "convert"):
        path = shutil.which(name)
        if path:
            return path
    raise XAvatarError("ImageMagick is required (magick/convert not found).")


def _open(source: Source) -> Image.Image:
    try:
        if isinstance(source, (bytes, bytearray)):
            handle = Image.open(io.BytesIO(bytes(source)))
        else:
            handle = Image.open(Path(source).expanduser())
        with handle:
            return ImageOps.exif_transpose(handle).convert("RGBA")
    except Exception as exc:
        raise XAvatarError(f"Cannot read image: {exc}") from exc


def load_square(source: Source, crop: bool = True, circle: bool = False) -> Image.Image:
    """Load an image, fit it to 440x440 RGBA, optionally center-crop and mask."""
    img = _open(source)

    if crop:
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))

    img = img.resize((440, 440), Image.Resampling.LANCZOS)

    if circle:
        # 4x supersampled mask for a smooth edge.
        mask = Image.new("L", (1760, 1760), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, 1759, 1759), fill=255)
        mask = mask.resize((440, 440), Image.Resampling.LANCZOS)
        masked = Image.new("RGBA", (440, 440), (0, 0, 0, 0))
        masked.paste(img, (0, 0), mask)
        img = masked

    return img


def preview_png(source: Source, crop: bool = True, circle: bool = False) -> bytes:
    """Small PNG preview, rendered by the same pipeline used for the package."""
    img = load_square(source, crop=crop, circle=circle)
    img.thumbnail((320, 320), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def build_dds(source_png: Path, size: int, dest: Path) -> None:
    cmd = [
        _magick(),
        str(source_png),
        "-filter", "Lanczos",
        "-resize", f"{size}x{size}!",
        "-alpha", "on",
        "-define", "dds:compression=dxt5",
        "-define", "dds:mipmaps=0",
        f"DDS:{dest}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0 or not dest.is_file():
        detail = (result.stderr or result.stdout).strip()
        raise XAvatarError(f"ImageMagick failed for {size}x{size}: {detail}")


def verify_dds(path: Path, dimension: int) -> None:
    """Validate the parts a PS4 payload checks, so we never emit a broken file."""
    data = path.read_bytes()
    name = path.name
    if len(data) < 128 or data[:4] != b"DDS ":
        raise XAvatarError(f"{name}: not a DDS file")
    if struct.unpack_from("<I", data, 4)[0] != 124:
        raise XAvatarError(f"{name}: bad DDS header size")
    height, width = struct.unpack_from("<II", data, 12)
    if (width, height) != (dimension, dimension):
        raise XAvatarError(f"{name}: expected {dimension}x{dimension}, got {width}x{height}")
    if struct.unpack_from("<I", data, 76)[0] != 32:
        raise XAvatarError(f"{name}: bad pixel format size")
    if not struct.unpack_from("<I", data, 80)[0] & 0x4:
        raise XAvatarError(f"{name}: missing FOURCC flag")
    fourcc = data[84:88]
    if fourcc not in (b"DXT1", b"DXT5"):
        raise XAvatarError(f"{name}: unsupported compression {fourcc!r}")
    if struct.unpack_from("<I", data, 112)[0] != 0:
        raise XAvatarError(f"{name}: cubemaps/volumes are not allowed")

    levels = struct.unpack_from("<I", data, 28)[0] or 1
    max_levels = 1
    v = dimension
    while v > 1:
        v >>= 1
        max_levels += 1
    if levels > max_levels:
        raise XAvatarError(f"{name}: too many mip levels ({levels})")

    block = 8 if fourcc == b"DXT1" else 16
    expected = 128
    w = h = dimension
    for _ in range(levels):
        expected += ((w + 3) // 4) * ((h + 3) // 4) * block
        w = max(1, w // 2)
        h = max(1, h // 2)
    if len(data) != expected:
        raise XAvatarError(f"{name}: size {len(data)} != expected {expected}")


def verify_png(path: Path) -> None:
    try:
        with Image.open(path) as img:
            if img.format != "PNG" or img.size != (440, 440):
                raise XAvatarError(f"{path.name}: expected a 440x440 PNG")
    except XAvatarError:
        raise
    except Exception as exc:
        raise XAvatarError(f"{path.name}: invalid PNG: {exc}") from exc
    if path.stat().st_size > MAX_PNG:
        raise XAvatarError(f"{path.name}: larger than 2 MiB")


def verify_package(path: Path, offline: bool) -> None:
    expected = AVATAR_NAMES + (OFFLINE_NAMES if offline else [])
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
            if sorted(names) != sorted(expected):
                raise XAvatarError("package contains unexpected or missing entries")
            if zf.testzip() is not None:
                raise XAvatarError("package failed CRC check")
            total = sum(info.file_size for info in zf.infolist())
            if total > MAX_PACKAGE:
                raise XAvatarError("package is larger than 4 MiB")
    except zipfile.BadZipFile as exc:
        raise XAvatarError(f"not a valid ZIP: {exc}") from exc


def build_avatar(
    source: Source,
    output: str | Path | None = None,
    *,
    crop: bool = True,
    circle: bool = False,
    offline: bool = True,
) -> Path:
    """Create a .xavatar file and return its path."""
    if isinstance(source, (bytes, bytearray)):
        raise TypeError("build_avatar() needs a path; use build_bytes() for raw data")

    source = Path(source).expanduser()
    if not source.is_file():
        raise XAvatarError(f"Image not found: {source}")

    if output is None:
        output = source.with_suffix(".xavatar")
    output = Path(output).expanduser()
    if output.suffix.lower() != ".xavatar":
        output = output.with_suffix(".xavatar")

    img = load_square(source, crop=crop, circle=circle)
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="xavatar-") as tmp:
        tmp = Path(tmp)
        avatar_png = tmp / "avatar.png"
        img.save(avatar_png, "PNG", optimize=True, compress_level=9)
        verify_png(avatar_png)

        entries: list[tuple[str, Path]] = [("avatar.png", avatar_png)]

        for size in SIZES:
            dds = tmp / f"avatar{size}.dds"
            build_dds(avatar_png, size, dds)
            verify_dds(dds, size)
            entries.append((dds.name, dds))

        if offline:
            picture_png = tmp / "picture.png"
            shutil.copyfile(avatar_png, picture_png)
            entries.append(("picture.png", picture_png))
            for size in SIZES:
                src_dds = tmp / f"avatar{size}.dds"
                dst_dds = tmp / f"picture{size}.dds"
                shutil.copyfile(src_dds, dst_dds)
                entries.append((dst_dds.name, dst_dds))
            online = tmp / "online.json"
            online.write_text(OFFLINE_JSON, encoding="utf-8")
            entries.append(("online.json", online))

        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for name, file_path in entries:
                zf.write(file_path, arcname=name)

    verify_package(output, offline)
    return output


def build_bytes(
    source: bytes,
    *,
    crop: bool = True,
    circle: bool = False,
    offline: bool = True,
) -> bytes:
    """Build a package from raw image bytes and return the .xavatar contents."""
    with tempfile.TemporaryDirectory(prefix="xavatar-") as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "input"
        src.write_bytes(source)
        out = build_avatar(src, tmp_path / "out.xavatar", crop=crop, circle=circle, offline=offline)
        return out.read_bytes()

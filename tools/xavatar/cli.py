#!/usr/bin/env python3
"""Command-line mode for XAVATAR Maker.

    python3 -m tools.xavatar.cli photo.png
    python3 -m tools.xavatar.cli photo.png Out.xavatar --stretch --circle --no-offline
"""

from __future__ import annotations

import argparse
import sys

from . import core


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="xavatar",
        description="Create .xavatar packages for PS4.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Copy the .xavatar to USB and install it with PS4-Xplorer,\n"
            "or put it in /data/AVATARS/ and use Avatar Changer."
        ),
    )
    parser.add_argument("image", help="input picture (PNG/JPG/WebP)")
    parser.add_argument("output", nargs="?", help="output .xavatar path")
    parser.add_argument(
        "--stretch", action="store_true", help="stretch instead of center-cropping"
    )
    parser.add_argument("--circle", action="store_true", help="transparent circle mask")
    parser.add_argument(
        "--no-offline",
        action="store_true",
        help="omit picture*.dds and online.json (online PSN account)",
    )
    args = parser.parse_args(argv)

    try:
        path = core.build_avatar(
            args.image,
            args.output,
            crop=not args.stretch,
            circle=args.circle,
            offline=not args.no_offline,
        )
    except core.XAvatarError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    count = len(core.AVATAR_NAMES) + (len(core.OFFLINE_NAMES) if not args.no_offline else 0)
    print(f"Created {path} ({count} files, {path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

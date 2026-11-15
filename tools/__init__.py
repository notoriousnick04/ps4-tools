"""Tool registry for the PS4 Tools web UI.

Adding a tool: create tools/<slug>/ with SLUG, TITLE, SUMMARY, STATIC and a
handle(action, payload) function, then append it to TOOLS below.
"""

from __future__ import annotations

from . import xavatar
from .base import ToolError

TOOLS = [xavatar]

__all__ = ["TOOLS", "ToolError"]

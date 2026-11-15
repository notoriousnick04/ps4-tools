"""Shared helpers for the tool registry."""

from __future__ import annotations


class ToolError(Exception):
    """A request the tool refused; the message is safe to show to the user."""

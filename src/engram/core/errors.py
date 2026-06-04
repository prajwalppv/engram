"""Typed, user-facing errors. Tools translate these into clean MCP errors."""
from __future__ import annotations


class CoreError(Exception):
    """Base for expected, user-facing errors."""


class StoreSafetyError(CoreError):
    """A path would escape the store, or an op is unsafe."""


class MemoryNotFoundError(CoreError):
    """No memory matched the given identifier."""

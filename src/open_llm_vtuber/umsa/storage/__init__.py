"""Storage backends for UMSA.

This package provides persistent storage implementations for the
Unified Memory System Architecture.
"""

from __future__ import annotations

try:
    from .sqlite_store import SQLiteStore

    __all__ = ["SQLiteStore"]
except ImportError:
    # aiosqlite not installed
    __all__ = []

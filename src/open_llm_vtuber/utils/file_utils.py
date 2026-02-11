"""File system utilities for Open-LLM-VTuber.

This module provides common file operations to reduce code duplication
across the codebase.
"""

from pathlib import Path


def ensure_directory_exists(path: str | Path) -> Path:
    """Ensure a directory exists, creating it if necessary.

    Args:
        path: Directory path (string or Path object)

    Returns:
        Path object of the directory

    Example:
        >>> ensure_directory_exists("cache")
        PosixPath('cache')
        >>> ensure_directory_exists(Path("models/tts"))
        PosixPath('models/tts')
    """
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path

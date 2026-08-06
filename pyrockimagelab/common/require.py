"""Required-argument helpers for pyrockimagelab public APIs.

Image folder roots and per-folder paths must be supplied by the caller
(typically a notebook or CLI). Package code must not assume CISR/CoreImages trees.
"""
from __future__ import annotations

from pathlib import Path


class MissingRequiredError(ValueError):
    """Raised when a required folder/root path argument is missing."""


def require_path(value, *, name: str) -> Path:
    """Return ``Path(value)`` or raise naming what is missing.

    Parameters
    ----------
    value :
        Filesystem path (str or Path). ``None`` / empty string is rejected.
    name :
        Argument name used in the error message (e.g. ``"folder"``, ``"core_images_dir"``).

    Returns
    -------
    pathlib.Path
    """
    if value is None or (isinstance(value, str) and not str(value).strip()):
        raise MissingRequiredError(
            f"{name} is required (filesystem path). "
            f"Pass {name}=... from your notebook/config or CLI; there is no package default."
        )
    return Path(value)


def require_existing_dir(value, *, name: str) -> Path:
    """Return an existing directory path or raise."""
    path = require_path(value, name=name)
    if not path.is_dir():
        raise MissingRequiredError(f"{name} not found or not a directory: {path}")
    return path

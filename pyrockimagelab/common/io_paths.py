"""Shared I/O, picks, path helpers, discovery, and progress assessment.

Folder / root paths are **required** — there is no package default for
``CoreImages`` or any CISR tree. Pass ``folder`` / ``core_images_dir`` from
your notebook or CLI.

>>> from pyrockimagelab.common import discover_depth_folders, load_picks
>>> folders = discover_depth_folders(core_images_dir="/path/to/CoreImages")
>>> picks = load_picks(folder="/path/to/CoreImages/UWI/2563-2572")
"""

from __future__ import annotations

import gc
import json
import os
import re
from pathlib import Path


import cv2
import numpy as np
from PIL import Image


from pyrockimagelab.common.require import require_existing_dir, require_path




try:
    import pillow_heif

    pillow_heif.register_heif_opener()
    HEIC_OK = True
except ImportError:
    HEIC_OK = False
    print("[warn] pillow_heif not installed; HEIC files will not load.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
VALID_EXTS = (".heic", ".heif", ".tif", ".tiff", ".jpg", ".jpeg", ".png")
PICKS_FILENAME = "_picks.json"
DISPLAY_LONG_SIDE = 1600
USE_HDR_GAINMAP = True
DEFAULT_SEG_LENGTH_FT = 3
N_SEGMENTS_DEFAULT = 3
DEFAULT_HR_PHOTO_RANGES = {1: (1, 7), 2: (7, 13), 3: (13, 19)}
THUMB_SELECT_LONG_SIDE = 100
THUMB_PREVIEW_LONG_SIDE = 72

_OUTPUT_PATTERN = re.compile(r"_lr_|_hr_|_lr\.|_hr\.")
_DEPTH_RANGE_STEM = re.compile(r"^\d+-\d+$")

cv2.setNumThreads(6)


def release_working_memory(quiet=False):
    """Close matplotlib figures (if matplotlib is in use) and collect large allocations."""
    import sys
    if "matplotlib.pyplot" in sys.modules:
        sys.modules["matplotlib.pyplot"].close("all")
    gc.collect()
    if not quiet:
        print("  Memory cleared.")


# ---------------------------------------------------------------------------
# Image I/O
# ---------------------------------------------------------------------------
def load_any_image(path):
    p = Path(path)
    ext = p.suffix.lower()
    if ext in (".heic", ".heif"):
        if not HEIC_OK:
            raise RuntimeError("pillow_heif missing; cannot read HEIC.")
        return np.asarray(Image.open(p).convert("RGB"))
    if ext in (".tif", ".tiff"):
        arr = cv2.imread(str(p), cv2.IMREAD_UNCHANGED)
        if arr is None:
            return np.asarray(Image.open(p).convert("RGB"))
        if arr.dtype != np.uint8:
            arr = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
        if arr.ndim == 2:
            return cv2.cvtColor(arr, cv2.COLOR_GRAY2RGB)
        if arr.shape[2] == 4:
            return cv2.cvtColor(arr, cv2.COLOR_BGRA2RGB)
        return cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    if ext in (".jpg", ".jpeg", ".png"):
        bgr = cv2.imread(str(p))
        if bgr is None:
            return np.asarray(Image.open(p).convert("RGB"))
        return cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    raise ValueError(f"Unsupported image format: {p.suffix}")


def save_at_dpi(rgb, out_path_no_ext, dpi=600):
    out = Path(out_path_no_ext)
    out.parent.mkdir(parents=True, exist_ok=True)
    pil = Image.fromarray(rgb)
    tif_path = out.with_suffix(".tif")
    png_path = out.with_suffix(".png")
    d = (int(dpi), int(dpi))
    pil.save(tif_path, format="TIFF", compression="tiff_lzw", dpi=d)
    pil.save(png_path, format="PNG", dpi=d)
    return tif_path, png_path


# ---------------------------------------------------------------------------
# Picks persistence
# ---------------------------------------------------------------------------
def load_picks(folder):
    """Load ``_picks.json`` from a depth-range image folder.

    Parameters
    ----------
    folder : str or pathlib.Path
        **Required.** Path to the depth-range folder that holds source photos
        and ``_picks.json``. No package default.
    """
    folder = require_path(folder, name="folder")
    path = folder / PICKS_FILENAME
    data = {}
    if path.exists():
        try:
            with open(path) as f:
                data = json.load(f)
        except Exception as e:
            print(f"[warn] could not parse {path}: {e}; starting fresh.")
            data = {}
    data.setdefault("box_quads", {})
    data.setdefault("detail_order", [])
    data.setdefault("mosaic_quad", None)
    data.setdefault("n_segments", N_SEGMENTS_DEFAULT)
    data.setdefault("lr_seg_lengths", data.get("seg_lengths", {}))
    data.setdefault("hr_seg_lengths", {})
    data.setdefault("lr_seg_names", {})
    data.setdefault("hr_seg_names", {})
    data.setdefault("hr_photo_quads", {})
    data.setdefault("hr_assignments", {})
    data.setdefault("lr_completed", False)
    data.setdefault("hr_completed", False)
    data.setdefault("lr_skipped_segs", [])
    data.setdefault("hr_skipped_segs", [])
    # Normalize legacy names that used _lr suffix on LR outputs
    lr_names = data.get("lr_seg_names", {})
    if lr_names:
        data["lr_seg_names"] = {k: normalize_lr_seg_name(v) for k, v in lr_names.items()}
    return data


def save_picks(folder, picks):
    """Write ``_picks.json`` into a depth-range image folder.

    Parameters
    ----------
    folder : str or pathlib.Path
        **Required.** Depth-range folder path. No package default.
    picks : dict
        Picks payload to serialize.
    """
    folder = require_path(folder, name="folder")
    path = folder / PICKS_FILENAME
    with open(path, "w") as f:
        json.dump(picks, f, indent=2)
    return path

# ---------------------------------------------------------------------------
# Path / name helpers and discovery
# ---------------------------------------------------------------------------
def parse_folder_depth_range(folder_name):
    m = re.match(r"^(\d+)-(\d+)$", folder_name)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _fmt_depth(v):
    return int(v) if v == int(v) else v


def strip_uwi_prefix(name, uwi):
    """Remove leading UWI_ from an output stem, if present."""
    name = (name or "").strip()
    uwi = str(uwi or "").strip()
    if not name or not uwi:
        return name
    prefix = f"{uwi}_"
    if name.startswith(prefix):
        return name[len(prefix) :]
    return name


def prefix_uwi_output_name(name, uwi):
    """Ensure output stem is {UWI}_{depth-range} or {UWI}_{depth-range}_hr."""
    name = (name or "").strip()
    uwi = str(uwi or "").strip()
    if not name:
        return name
    if not uwi:
        return name
    return f"{uwi}_{strip_uwi_prefix(name, uwi)}"


def normalize_lr_seg_name(name, uwi=None):
    """Strip legacy _lr suffix and optional UWI prefix so LR stem is {start}-{end}."""
    name = strip_uwi_prefix((name or "").strip(), uwi)
    if name.endswith("_lr"):
        return name[:-3]
    return name


def default_hr_name_from_lr(lr_name, uwi=None):
    """Build HR stem from LR name: {UWI}_2563-2566 -> {UWI}_2563-2566_hr."""
    base = normalize_lr_seg_name(lr_name, uwi=uwi)
    if base.endswith("_hr"):
        hr = base
    else:
        hr = f"{base}_hr" if base else ""
    return prefix_uwi_output_name(hr, uwi) if uwi else hr


def _is_source_image(path):
    if path.suffix.lower() not in VALID_EXTS:
        return False
    if _OUTPUT_PATTERN.search(path.name):
        return False
    if _DEPTH_RANGE_STEM.match(path.stem):
        return False
    return True


def list_source_images(folder):
    """List source photos in a depth-range folder (excludes outputs / HEIC-ok check via VALID_EXTS).

    Parameters
    ----------
    folder : str or pathlib.Path
        **Required.** Depth-range folder path. No package default.
    """
    folder = require_path(folder, name="folder")
    return sorted(p for p in folder.iterdir() if p.is_file() and _is_source_image(p))


def discover_depth_folders(core_images_dir):
    """Return sorted ``[(uwi, folder_path), ...]`` under ``{root}/{UWI}/{depth-range}/``.

    Parameters
    ----------
    core_images_dir : str or pathlib.Path
        **Required.** Root directory that contains UWI subfolders with
        depth-range image folders. No package default (do not hard-wire
        ``CoreImages`` or a CISR project path).

    Returns
    -------
    list[tuple[str, pathlib.Path]]
        Sorted ``(uwi, depth_folder)`` pairs. Empty list if the root has no
        matching children (root itself must exist).
    """
    root = require_existing_dir(core_images_dir, name="core_images_dir")
    results = []
    for uwi_dir in sorted(root.iterdir()):
        if not uwi_dir.is_dir():
            continue
        uwi = uwi_dir.name
        for depth_dir in sorted(uwi_dir.iterdir()):
            if not depth_dir.is_dir():
                continue
            if parse_folder_depth_range(depth_dir.name) is None:
                continue
            results.append((uwi, depth_dir))
    results.sort(key=lambda t: (t[0], parse_folder_depth_range(t[1].name)[0]))
    return results


def filter_folders(folders, uwi=None, folder_names=None):
    if uwi:
        folders = [(u, p) for u, p in folders if u == uwi]
    if folder_names:
        name_set = set(folder_names)
        folders = [(u, p) for u, p in folders if p.name in name_set]
        order = {name: i for i, name in enumerate(folder_names)}
        folders.sort(key=lambda t: order.get(t[1].name, len(folder_names)))
    return folders

# ---------------------------------------------------------------------------
# Progress assessment and resume
# ---------------------------------------------------------------------------
def assess_progress(folders, run_lr=True, run_hr=True):
    """Scan _picks.json for each folder. Returns (status_dict, summary).

    status_dict: {(uwi, folder_path): {"lr": bool, "hr": bool}}
    summary: dict with mode-aware counts:
      - n_total, n_done, n_pending (mode-specific)
      - n_both_done, n_lr_only, n_hr_only, n_not_started (detailed breakdown)
    """
    status = {}
    n_both = n_lr = n_hr = n_none = 0
    for uwi, folder_path in folders:
        picks_path = folder_path / PICKS_FILENAME
        lr_done = False
        hr_done = False
        if picks_path.exists():
            try:
                with open(picks_path) as f:
                    data = json.load(f)
                lr_done = data.get("lr_completed", False)
                hr_done = data.get("hr_completed", False)
            except Exception:
                pass
        status[(uwi, folder_path)] = {"lr": lr_done, "hr": hr_done}
        if lr_done and hr_done:
            n_both += 1
        elif lr_done:
            n_lr += 1
        elif hr_done:
            n_hr += 1
        else:
            n_none += 1

    # Mode-specific done/pending counts
    if run_lr and run_hr:
        n_done = n_both
        n_pending = n_lr + n_hr + n_none
    elif run_lr and not run_hr:
        n_done = n_both + n_lr
        n_pending = n_hr + n_none
    else:  # run_hr only
        n_done = n_both + n_hr
        n_pending = n_lr + n_none

    summary = {
        "n_total": len(folders),
        "n_done": n_done,
        "n_pending": n_pending,
        "n_both_done": n_both,
        "n_lr_only": n_lr,
        "n_hr_only": n_hr,
        "n_not_started": n_none,
    }
    return status, summary

def reset_completion(folder, lr=True, hr=True):
    """Clear completion flags and skip lists but preserve corner picks and names."""
    picks = load_picks(folder)
    if lr:
        picks["lr_completed"] = False
        picks["lr_skipped_segs"] = []
    if hr:
        picks["hr_completed"] = False
        picks["hr_skipped_segs"] = []
    save_picks(folder, picks)

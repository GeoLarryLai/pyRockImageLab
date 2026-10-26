"""Core photo batch processor (LR + HR) — pyrockimagelab.core_box.processing.

Sources layout (caller-supplied root)::

    {core_images_dir}/{UWI}/{depth-range}/
    Outputs: {core_images_dir}/{UWI}/{UWI}_{start}-{end}[_hr].png
    Picks:   {core_images_dir}/{UWI}/{depth-range}/_picks.json

``folder`` and batch ``--root`` / ``core_images_dir`` are **required**.
There is no package default for CoreImages or any CISR path.

Everything here is non-interactive (no GUI). Corners, names and lengths come from
``_picks.json``, which the browser app (``pyrockimagelab-app``) writes. The old matplotlib
pop-up pickers were removed in 0.1.0.

CLI (replays saved corners)::

    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --help
    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages
    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --lr-only
    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --uwi UWI --folder start-end

Library::

    from pyrockimagelab import process_folder
    process_folder(folder="/path/to/CoreImages/UWI/start-end", uwi="UWI", ...)
"""

import argparse
import gc
from pathlib import Path

from pyrockimagelab.common.require import require_existing_dir, require_path
from pyrockimagelab.common.io_paths import (
    DEFAULT_SEG_LENGTH_FT,
    N_SEGMENTS_DEFAULT,
    USE_HDR_GAINMAP,
    _fmt_depth,
    assess_progress,
    default_hr_name_from_lr,
    discover_depth_folders,
    filter_folders,
    load_any_image,
    load_picks,
    list_source_images,
    normalize_lr_seg_name,
    parse_folder_depth_range,
    prefix_uwi_output_name,
    release_working_memory,
    reset_completion,
    save_at_dpi,
    save_picks,
)
from pyrockimagelab.image_processing.stitch import (
    MATCH_RATIO,
    NFEATURES,
    RANSAC_REPROJ,
    WORK_MEGAPIX,
    stitch_chain,
)
from pyrockimagelab.image_processing.warp import _apply_hdr_enhancement, clamp_quad_to_image, ortho_warp_quad, trim_empty_rows


def _hr_segment_name(seg_num, n_segments, picks, folder, uwi):
    """Derive default HR output stem; inherits LR segment names when available."""
    saved_hr = picks.get("hr_seg_names", {}).get(f"seg{seg_num}", "")
    if saved_hr:
        return prefix_uwi_output_name(saved_hr, uwi)

    lr_name = picks.get("lr_seg_names", {}).get(f"seg{seg_num}", "")
    if lr_name:
        return default_hr_name_from_lr(lr_name, uwi=uwi)

    depth_range = parse_folder_depth_range(folder.name)
    if depth_range:
        is_last = seg_num == n_segments
        hr_seg_start = depth_range[0]
        for prev in range(1, seg_num):
            hr_seg_start += float(
                picks.get("hr_seg_lengths", {}).get(f"seg{prev}", "")
                or picks.get("lr_seg_lengths", {}).get(f"seg{prev}", "")
                or str(DEFAULT_SEG_LENGTH_FT)
            )
        length_val = float(
            picks.get("hr_seg_lengths", {}).get(f"seg{seg_num}", "")
            or picks.get("lr_seg_lengths", {}).get(f"seg{seg_num}", "")
            or str(DEFAULT_SEG_LENGTH_FT)
        )
        if is_last:
            stem = f"{_fmt_depth(depth_range[1] - length_val)}-{_fmt_depth(depth_range[1])}_hr"
        else:
            stem = f"{_fmt_depth(hr_seg_start)}-{_fmt_depth(hr_seg_start + length_val)}_hr"
        return prefix_uwi_output_name(stem, uwi)

    return prefix_uwi_output_name(f"{folder.name}_hr_{seg_num}", uwi)



# ---------------------------------------------------------------------------
# Building blocks (used by the app, the notebooks and the replay functions)
# ---------------------------------------------------------------------------
def lr_segment_defaults(folder, uwi, picks):
    """Default ``[{"seg", "length_ft", "output_name"}, ...]`` for every box-photo section.

    Same naming rules as the old interactive loop: saved name, else depth from the
    folder name (``start-end``) plus each section length, else ``{folder}_{i}``.
    """
    folder = Path(folder)
    n_segments = int(picks.get("n_segments", N_SEGMENTS_DEFAULT))
    depth_range = parse_folder_depth_range(folder.name)
    current = depth_range[0] if depth_range else None
    out = []
    for i in range(1, n_segments + 1):
        saved_length = picks.get("lr_seg_lengths", {}).get(f"seg{i}", "")
        length = saved_length if saved_length else str(DEFAULT_SEG_LENGTH_FT)
        saved_name = picks.get("lr_seg_names", {}).get(f"seg{i}", "")
        if saved_name:
            name = prefix_uwi_output_name(normalize_lr_seg_name(saved_name, uwi=uwi), uwi)
        elif depth_range:
            lv = float(length)
            if i == n_segments:
                s, e = depth_range[1] - lv, depth_range[1]
            else:
                s, e = current, current + lv
            name = prefix_uwi_output_name(f"{_fmt_depth(s)}-{_fmt_depth(e)}", uwi)
        else:
            name = prefix_uwi_output_name(f"{folder.name}_{i}", uwi)
        out.append({"seg": i, "length_ft": length, "output_name": name})
        if current is not None:
            try:
                current += float(length)
            except ValueError:
                current += DEFAULT_SEG_LENGTH_FT
    return out


def lr_name_for_length(folder, uwi, picks, seg, length):
    """Output name implied by a new section length (live update in the app)."""
    folder = Path(folder)
    dr = parse_folder_depth_range(folder.name)
    if not dr:
        return None
    n = int(picks.get("n_segments", N_SEGMENTS_DEFAULT))
    start = dr[0]
    for prev in range(1, seg):
        try:
            start += float(picks.get("lr_seg_lengths", {}).get(f"seg{prev}", "") or DEFAULT_SEG_LENGTH_FT)
        except ValueError:
            start += DEFAULT_SEG_LENGTH_FT
    length = float(length)
    s, e = (dr[1] - length, dr[1]) if seg == n else (start, start + length)
    return prefix_uwi_output_name(f"{_fmt_depth(s)}-{_fmt_depth(e)}", uwi)


def crop_lr_segment(box_img, quad):
    """Straighten one box-photo section from its 4 corners (+ contrast enhancement)."""
    seg = ortho_warp_quad(box_img, quad)
    if USE_HDR_GAINMAP:
        seg = _apply_hdr_enhancement(seg)
    return seg


def save_lr_segment(folder, uwi, picks, seg_num, quad, box_img, length_ft=None, output_name=None):
    """Record one section in ``picks``, write ``_picks.json`` and save ``../{name}.tif/.png`` (300 dpi)."""
    folder = require_path(folder, name="folder")
    key = f"{picks['box_photo']}::seg{seg_num}"
    if length_ft is not None and str(length_ft).strip():
        picks.setdefault("lr_seg_lengths", {})[f"seg{seg_num}"] = str(length_ft).strip()
    defaults = {d["seg"]: d for d in lr_segment_defaults(folder, uwi, picks)}
    default_name = defaults.get(seg_num, {}).get("output_name") or f"{folder.name}_{seg_num}"
    raw = (output_name or "").strip() or default_name
    name = prefix_uwi_output_name(normalize_lr_seg_name(raw, uwi=uwi), uwi)
    picks.setdefault("lr_seg_names", {})[f"seg{seg_num}"] = name
    picks["box_quads"][key] = [[float(x), float(y)] for x, y in quad]
    sk = picks.setdefault("lr_skipped_segs", [])
    if seg_num in sk:
        sk.remove(seg_num)
    save_picks(folder, picks)
    seg = crop_lr_segment(box_img, quad)
    paths = save_at_dpi(seg, folder.parent / name, dpi=300)
    return name, seg.shape, paths


def hr_default_name(folder, uwi, picks, seg_num):
    return _hr_segment_name(seg_num, int(picks.get("n_segments", N_SEGMENTS_DEFAULT)), picks, Path(folder), uwi)


def crop_hr_photo(img, quad):
    """Trim + straighten one close-up photo (``quad=None`` keeps the full photo)."""
    out = ortho_warp_quad(img, quad) if quad is not None else img
    if USE_HDR_GAINMAP:
        out = _apply_hdr_enhancement(out)
    return out


def stitch_params_for(picks, seg_num, overrides=None):
    sp = picks.get("hr_stitch_params", {}).get(f"seg{seg_num}", {})
    p = {
        "NFEATURES": sp.get("NFEATURES", NFEATURES),
        "MATCH_RATIO": sp.get("MATCH_RATIO", MATCH_RATIO),
        "RANSAC_REPROJ": sp.get("RANSAC_REPROJ", RANSAC_REPROJ),
        "WORK_MEGAPIX": sp.get("WORK_MEGAPIX", WORK_MEGAPIX),
    }
    if overrides:
        p.update({k: type(p[k])(v) if not isinstance(p[k], int) else int(float(v)) for k, v in overrides.items() if k in p})
    return p


def stitch_hr_segment(folder, picks, seg_num, photo_names=None, params=None):
    """Crop every assigned close-up with its saved corners and stitch them. Returns ``(mosaic, names)``."""
    folder = require_path(folder, name="folder")
    if photo_names is None:
        photo_names = [p.name for p in list_source_images(folder)]
    idx = picks.get("hr_assignments", {}).get(f"seg{seg_num}", [])
    names = [photo_names[i] for i in idx]
    if not names:
        return None, []
    quads = picks.get("hr_photo_quads", {})
    crops = []
    for n in names:
        img = load_any_image(folder / n)
        crops.append(crop_hr_photo(img, quads.get(n)))
        del img
    p = params or stitch_params_for(picks, seg_num)
    mosaic = stitch_chain(seg_num, crops, picks, params=p)
    del crops
    gc.collect()
    return mosaic, names


def finish_hr_segment(folder, uwi, picks, seg_num, mosaic, quad=None, output_name=None):
    """Straighten the joined image with its 4 corners, trim empty rows, save ``../{name}.tif/.png`` (600 dpi)."""
    folder = require_path(folder, name="folder")
    if quad is not None:
        picks[f"hr_mosaic_quad_seg{seg_num}"] = [[float(x), float(y)] for x, y in quad]
        mosaic = trim_empty_rows(ortho_warp_quad(mosaic, clamp_quad_to_image(quad, mosaic)))
    default = hr_default_name(folder, uwi, picks, seg_num)
    name = prefix_uwi_output_name((output_name or "").strip() or default, uwi)
    picks.setdefault("hr_seg_names", {})[f"seg{seg_num}"] = name
    save_picks(folder, picks)
    paths = save_at_dpi(mosaic, folder.parent / name, dpi=600)
    return name, mosaic.shape, paths


# ---------------------------------------------------------------------------
# Replay functions (same names as before 0.1.0; now use saved corners only)
# ---------------------------------------------------------------------------
def process_lr_segments(folder, box_path, uwi, folder_idx=1, total_folders=1, picks=None):
    """Save every box-photo section that has saved corners. Returns ``(saved, picks, False)``."""
    folder = require_path(folder, name="folder")
    picks = load_picks(folder) if picks is None else picks
    box_path = Path(box_path)
    picks["box_photo"] = box_path.name
    print(f"  [{folder_idx}/{total_folders}] {uwi}/{folder.name} — box photo {box_path.name}")
    box_img = load_any_image(box_path)
    saved = 0
    skipped = set(picks.get("lr_skipped_segs", []))
    for d in lr_segment_defaults(folder, uwi, picks):
        i = d["seg"]
        quad = picks["box_quads"].get(f"{box_path.name}::seg{i}")
        if quad is None or i in skipped:
            print(f"  Section {i}: no saved corners — skipped")
            continue
        name, shape, _ = save_lr_segment(folder, uwi, picks, i, quad, box_img, d["length_ft"], d["output_name"])
        print(f"  Section {i}: {shape[1]} x {shape[0]} px -> ../{name}.tif/.png")
        saved += 1
    del box_img
    release_working_memory(quiet=True)
    picks["lr_completed"] = True
    save_picks(folder, picks)
    return saved, picks, False


def process_hr_segment(folder, uwi, seg_num, n_segments=None, photo_names=None, segment_photo_indices=None, picks=None):
    """Stitch and save one close-up section from saved picks. Returns True/None."""
    folder = require_path(folder, name="folder")
    picks = load_picks(folder) if picks is None else picks
    if segment_photo_indices is not None:
        picks["hr_assignments"] = {f"seg{k}": list(v) for k, v in segment_photo_indices.items()}
    mosaic, names = stitch_hr_segment(folder, picks, seg_num, photo_names)
    if mosaic is None:
        print(f"  [skip] No photos assigned to section {seg_num}")
        return None
    name, shape, _ = finish_hr_segment(folder, uwi, picks, seg_num, mosaic, picks.get(f"hr_mosaic_quad_seg{seg_num}"))
    print(f"  Saved: ../{name}.tif/.png ({shape[1]} x {shape[0]} px)")
    del mosaic
    release_working_memory(quiet=True)
    return True


def process_hr_segments(folder, uwi, picks=None, segment_filter=None):
    """Replay every assigned close-up section. Returns ``(saved, False)``."""
    folder = require_path(folder, name="folder")
    picks = load_picks(folder) if picks is None else picks
    n = int(picks.get("n_segments", N_SEGMENTS_DEFAULT))
    photo_names = [p.name for p in list_source_images(folder)]
    saved = 0
    for s in ([segment_filter] if segment_filter else range(1, n + 1)):
        if s in picks.get("hr_skipped_segs", []):
            continue
        if process_hr_segment(folder, uwi, s, n, photo_names, None, picks):
            saved += 1
    picks["hr_completed"] = True
    save_picks(folder, picks)
    return saved, False


def process_folder(folder, uwi, folder_idx=1, total_folders=1, run_lr=True, run_hr=True, segment_filter=None):
    """Replay a whole depth folder from its ``_picks.json``. Returns ``(lr_saved, hr_saved, False)``."""
    folder = require_path(folder, name="folder")
    picks = load_picks(folder)
    lr = hr = 0
    if run_lr and picks.get("box_photo"):
        lr, picks, _ = process_lr_segments(folder, folder / picks["box_photo"], uwi, folder_idx, total_folders, picks)
    if run_hr:
        hr, _ = process_hr_segments(folder, uwi, picks, segment_filter)
    return lr, hr, False


def main(argv=None):
    """CLI: replay saved corners for every depth folder under ``--root``."""
    parser = argparse.ArgumentParser(
        description="Re-create core images from saved corners (_picks.json). "
        "Use pyrockimagelab-app to mark corners."
    )
    parser.add_argument("--root", required=True, help="Folder containing {UWI}/{depth-range}/ folders")
    parser.add_argument("--uwi", help="Only this UWI")
    parser.add_argument("--folder", action="append", dest="folders", metavar="DEPTH-RANGE")
    parser.add_argument("--lr-only", action="store_true", help="Box-photo sections only")
    parser.add_argument("--hr-only", action="store_true", help="Close-up stitching only")
    parser.add_argument("--segment", type=int, help="Only this section number (stitching)")
    a = parser.parse_args(argv)
    if a.lr_only and a.hr_only:
        parser.error("Cannot use --lr-only and --hr-only together")
    root = require_existing_dir(a.root, name="--root")
    folders = filter_folders(discover_depth_folders(root), uwi=a.uwi, folder_names=a.folders)
    tl = th = 0
    for i, (uwi, f) in enumerate(folders, 1):
        l, h, _ = process_folder(f, uwi, i, len(folders), not a.hr_only, not a.lr_only, a.segment)
        tl += l; th += h
    print(f"Done: {len(folders)} folder(s), {tl} box-photo section(s), {th} stitched image(s).")


if __name__ == "__main__":
    main()

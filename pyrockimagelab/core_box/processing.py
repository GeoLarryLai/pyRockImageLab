"""Core photo batch processor (LR + HR) — pyrockimagelab.core_box.processing.

Sources layout (caller-supplied root)::

    {core_images_dir}/{UWI}/{depth-range}/
    Outputs: {core_images_dir}/{UWI}/{UWI}_{start}-{end}[_hr].png
    Picks:   {core_images_dir}/{UWI}/{depth-range}/_picks.json

``folder`` and batch ``--root`` / ``core_images_dir`` are **required**.
There is no package default for CoreImages or any CISR path.

CLI (from project root; conda env ``work``; needs local GUI)::

    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --help
    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages
    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --lr-only
    python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --uwi 30015058530000 --folder 7168-7172

Library::

    from pyrockimagelab import process_folder
    process_folder(folder="/path/to/.../7168-7172", uwi="30015058530000", ...)
"""

import argparse
import gc

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
from pyrockimagelab.common.ui import (
    QuadPicker,
    _DialogResult,
    assign_hr_photos,
    confirm_folder,
    pick_box_photo,
    show_progress_and_ask,
)
from pyrockimagelab.image_processing.stitch import (
    MATCH_RATIO,
    NFEATURES,
    RANSAC_REPROJ,
    WORK_MEGAPIX,
    stitch_chain,
)
from pyrockimagelab.image_processing.warp import _apply_hdr_enhancement, ortho_warp_quad


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


def process_lr_segments(folder, box_path, uwi, folder_idx, total_folders, picks):
    """LR extraction loop. Returns ``(segments_saved, picks, quit_requested)``.

    Parameters
    ----------
    folder : str or pathlib.Path
        **Required.** Depth-range image folder. No package default.
    box_path : str or pathlib.Path
        Box photo path inside ``folder``.
    uwi : str
        Well UWI used in output naming.
    folder_idx, total_folders : int
        Progress labels for the picker UI.
    picks : dict
        Mutable picks payload (updated and saved in-place).
    """
    folder = require_path(folder, name="folder")
    print(f"\n{'=' * 65}")
    print(f"  [{folder_idx}/{total_folders}]  {uwi}/{folder.name}  —  LOW-RES")
    print(f"  Box photo: {box_path.name}")
    print(f"{'=' * 65}")

    print(f"  Loading {box_path.name} ...")
    box_img = load_any_image(box_path)
    print(f"  Full resolution: {box_img.shape[1]} x {box_img.shape[0]}")

    n_segments = picks.get("n_segments", N_SEGMENTS_DEFAULT)
    depth_range = parse_folder_depth_range(folder.name)
    current_depth = depth_range[0] if depth_range else None
    seg_idx = 0
    saved_count = 0

    while seg_idx < n_segments:
        i = seg_idx + 1
        key = f"{box_path.name}::seg{i}"
        prev_quad = picks["box_quads"].get(key)

        is_last = i == n_segments
        saved_length = picks.get("lr_seg_lengths", {}).get(f"seg{i}", "")
        default_length = saved_length if saved_length else str(DEFAULT_SEG_LENGTH_FT)
        saved_name = picks.get("lr_seg_names", {}).get(f"seg{i}", "")

        if saved_name:
            default_name = prefix_uwi_output_name(normalize_lr_seg_name(saved_name, uwi=uwi), uwi)
        elif depth_range:
            length_val = float(default_length)
            if is_last:
                seg_end = depth_range[1]
                seg_start = seg_end - length_val
            else:
                seg_start = current_depth
                seg_end = current_depth + length_val
            default_name = prefix_uwi_output_name(
                f"{_fmt_depth(seg_start)}-{_fmt_depth(seg_end)}", uwi
            )
        else:
            default_name = prefix_uwi_output_name(f"{folder.name}_{i}", uwi)

        def _make_lr_callback(_seg_start, _is_last, _dr, _uwi):
            def _on_change(field_key, value, metadata):
                if field_key != "length_ft" or not _dr:
                    return None
                try:
                    length = float(value)
                except ValueError:
                    return None
                if _is_last:
                    s, e = _dr[1] - length, _dr[1]
                else:
                    s, e = _seg_start, _seg_start + length
                stem = f"{_fmt_depth(s)}-{_fmt_depth(e)}"
                return {"output_name": prefix_uwi_output_name(stem, _uwi)}

            return _on_change

        lr_callback = (
            _make_lr_callback(current_depth, is_last, depth_range, uwi) if depth_range else None
        )

        fields = [
            {"key": "length_ft", "label": "Length (ft)", "default": default_length},
            {"key": "output_name", "label": "Output name", "default": default_name},
        ]
        if seg_idx == 0:
            fields.insert(0, {"key": "n_segments", "label": "N segments", "default": str(n_segments)})

        if prev_quad is not None:
            print(f"  Segment {i}: prefilled (drag to refine; Enter to keep).")
        else:
            print(f"  Segment {i}: click 4 corners (any order; Enter to confirm).")

        picker = QuadPicker(
            box_img,
            initial_quad=prev_quad,
            title=f"[{folder_idx}/{total_folders}] {folder.name}  —  LR Segment {i}/{n_segments}",
            metadata_fields=fields,
            on_field_change=lr_callback,
            segment_actions=True,
        )
        quad = picker.run()

        if picker.segment_action == QuadPicker.ACTION_QUIT:
            del box_img
            release_working_memory(quiet=True)
            return saved_count, picks, True
        if picker.segment_action == QuadPicker.ACTION_SKIP:
            print(f"  Segment {i}: skipped by user.")
            skipped = picks.setdefault("lr_skipped_segs", [])
            if i not in skipped:
                skipped.append(i)
            save_picks(folder, picks)
            if current_depth is not None:
                saved_length = picks.get("lr_seg_lengths", {}).get(f"seg{i}", "") or str(
                    DEFAULT_SEG_LENGTH_FT
                )
                try:
                    current_depth += float(saved_length)
                except ValueError:
                    current_depth += DEFAULT_SEG_LENGTH_FT
            seg_idx += 1
            continue

        if quad is None:
            print(f"  Segment {i}: cancelled. Aborting LR loop.")
            break

        meta = picker.metadata

        if seg_idx == 0 and "n_segments" in meta:
            try:
                new_n = int(meta["n_segments"])
                if new_n >= 1:
                    n_segments = new_n
                    picks["n_segments"] = n_segments
            except ValueError:
                pass

        if meta.get("length_ft", "").strip():
            picks.setdefault("lr_seg_lengths", {})[f"seg{i}"] = meta["length_ft"].strip()

        raw_name = meta.get("output_name", default_name).strip() or default_name
        seg_name = prefix_uwi_output_name(normalize_lr_seg_name(raw_name, uwi=uwi), uwi)
        picks.setdefault("lr_seg_names", {})[f"seg{i}"] = seg_name
        picks["box_quads"][key] = [[float(x), float(y)] for x, y in quad]
        save_picks(folder, picks)

        seg = ortho_warp_quad(box_img, quad)
        if USE_HDR_GAINMAP:
            seg = _apply_hdr_enhancement(seg)

        save_at_dpi(seg, folder.parent / seg_name, dpi=300)
        length_str = f"  ({meta['length_ft'].strip()} ft)" if meta.get("length_ft", "").strip() else ""
        print(f"  Segment {i}: {seg.shape[1]} x {seg.shape[0]} px{length_str} -> ../{seg_name}.tif/.png")
        saved_count += 1
        del seg

        if current_depth is not None:
            try:
                current_depth += float(meta.get("length_ft", default_length))
            except ValueError:
                current_depth += DEFAULT_SEG_LENGTH_FT

        seg_idx += 1

    del box_img
    release_working_memory(quiet=True)
    picks["lr_completed"] = True
    save_picks(folder, picks)
    return saved_count, picks, False


def process_hr_segment(folder, uwi, seg_num, n_segments, photo_names, segment_photo_indices, picks):
    """Crop, stitch, mosaic ortho, and save one HR segment.

    Parameters
    ----------
    folder : str or pathlib.Path
        **Required.** Depth-range image folder. No package default.
    """
    folder = require_path(folder, name="folder")
    print(f"\n{'=' * 60}")
    print(f"HR SEGMENT {seg_num}/{n_segments} — {uwi}/{folder.name}")
    print(f"{'=' * 60}")

    indices = list(segment_photo_indices.get(seg_num, []))
    if not indices:
        print(f"  [skip] No photos assigned to segment {seg_num}")
        return None

    names = [photo_names[i] for i in indices]
    paths = [folder / n for n in names]

    hr_photo_quads = picks.setdefault("hr_photo_quads", {})
    default_hr_name = _hr_segment_name(seg_num, n_segments, picks, folder, uwi)

    photos_skipped_this_run = False

    while True:
        print(f"\n  {len(names)} photos in this segment:")
        for idx, name in zip(indices, names):
            print(f"    [{idx}] {name}")

        processed_imgs = []
        skipped_in_pass = []

        photo_iter = list(enumerate(zip(names, paths)))
        for photo_idx, (name, path) in photo_iter:
            print(f"\n  Photo {photo_idx + 1}/{len(names)}: {name}")
            full_img = load_any_image(path)
            print(f"    Resolution: {full_img.shape[1]} x {full_img.shape[0]}")

            prev_quad = hr_photo_quads.get(name)
            if prev_quad:
                print("    Crop: prefilled (Enter to keep; Esc to skip cropping; x to skip photo)")
            else:
                print("    Crop: click 4 corners (Enter to confirm; Esc to skip cropping; x to skip photo)")

            picker = QuadPicker(
                full_img,
                initial_quad=prev_quad,
                title=f"Seg {seg_num} — {name}  ({photo_idx + 1}/{len(names)})\n"
                "Select core area (Esc=no crop | x=skip photo)",
                segment_actions=(photo_idx == 0),
                skip_photo_action=True,
            )
            quad = picker.run()

            if picker.segment_action == QuadPicker.ACTION_SKIP_PHOTO:
                print(f"    >>> Photo skipped: {name}")
                skipped_in_pass.append(photo_idx)
                del full_img
                continue

            if photo_idx == 0:
                if picker.segment_action == QuadPicker.ACTION_QUIT:
                    del full_img
                    release_working_memory(quiet=True)
                    return "quit"
                if picker.segment_action == QuadPicker.ACTION_SKIP:
                    del full_img
                    release_working_memory(quiet=True)
                    return "skip"

            if quad is not None:
                hr_photo_quads[name] = [[float(x), float(y)] for x, y in quad]
                save_picks(folder, picks)
                cropped = ortho_warp_quad(full_img, quad)
                print(f"    Cropped + ortho: {cropped.shape[1]} x {cropped.shape[0]}")
            else:
                print("    Skipped cropping (using full image)")
                cropped = full_img

            if USE_HDR_GAINMAP:
                cropped = _apply_hdr_enhancement(cropped)

            processed_imgs.append(cropped)
            del full_img

        if skipped_in_pass:
            photos_skipped_this_run = True
            for si in sorted(skipped_in_pass, reverse=True):
                removed_name = names.pop(si)
                removed_idx = indices.pop(si)
                paths.pop(si)
                print(f"    Removed [{removed_idx}] {removed_name} from segment {seg_num}")
            picks["hr_assignments"][f"seg{seg_num}"] = list(indices)
            save_picks(folder, picks)
            print(f"  Updated segment {seg_num}: {len(names)} photo(s) remaining")

        if not processed_imgs:
            print(f"  [skip] All photos skipped for segment {seg_num}")
            return None

        stitch_params = picks.get("hr_stitch_params", {}).get(f"seg{seg_num}", {})
        cur_params = {
            "NFEATURES": stitch_params.get("NFEATURES", NFEATURES),
            "MATCH_RATIO": stitch_params.get("MATCH_RATIO", MATCH_RATIO),
            "RANSAC_REPROJ": stitch_params.get("RANSAC_REPROJ", RANSAC_REPROJ),
            "WORK_MEGAPIX": stitch_params.get("WORK_MEGAPIX", WORK_MEGAPIX),
        }

        print(f"\n  Stitching {len(processed_imgs)} processed image(s)...")
        mosaic = stitch_chain(seg_num, processed_imgs, picks, params=cur_params)
        print(f"  Stitched mosaic: {mosaic.shape[1]} x {mosaic.shape[0]} px")

        while True:
            mosaic_quad_key = f"hr_mosaic_quad_seg{seg_num}"
            prev_mosaic_quad = picks.get(mosaic_quad_key)

            if prev_mosaic_quad:
                print("\n  Mosaic ortho: prefilled (Enter to keep; Esc to skip; d to redo crops; t to restitch)")
            else:
                print("\n  Mosaic ortho: click 4 corners (Enter to confirm; Esc to skip; d/t for redo/restitch)")

            name_label = "Output name"
            if photos_skipped_this_run:
                name_label = "*** Output name (photo(s) skipped — revise?)"

            picker = QuadPicker(
                mosaic,
                initial_quad=prev_mosaic_quad,
                title=f"Segment {seg_num} mosaic ortho  ({mosaic.shape[1]}x{mosaic.shape[0]})\n"
                "Select final rectangle (Esc to skip; d=[Redo crops]; t=[Restitch])",
                metadata_fields=[
                    {"key": "output_name",   "label": name_label,      "default": default_hr_name},
                    {"key": "NFEATURES",     "label": "NFEATURES",     "default": str(int(cur_params["NFEATURES"]))},
                    {"key": "MATCH_RATIO",   "label": "MATCH_RATIO",   "default": str(cur_params["MATCH_RATIO"])},
                    {"key": "RANSAC_REPROJ", "label": "RANSAC_REPROJ", "default": str(cur_params["RANSAC_REPROJ"])},
                    {"key": "WORK_MEGAPIX",  "label": "WORK_MEGAPIX",  "default": str(cur_params["WORK_MEGAPIX"])},
                ],
                redo_action=True,
                restitch_action=True,
                highlight_keys=["output_name"] if photos_skipped_this_run else None,
            )
            mosaic_quad = picker.run()

            if picker.segment_action == QuadPicker.ACTION_RESTITCH:
                try:
                    cur_params = {
                        "NFEATURES": int(picker.metadata.get("NFEATURES", cur_params["NFEATURES"])),
                        "MATCH_RATIO": float(picker.metadata.get("MATCH_RATIO", cur_params["MATCH_RATIO"])),
                        "RANSAC_REPROJ": float(picker.metadata.get("RANSAC_REPROJ", cur_params["RANSAC_REPROJ"])),
                        "WORK_MEGAPIX": float(picker.metadata.get("WORK_MEGAPIX", cur_params["WORK_MEGAPIX"])),
                    }
                except ValueError as e:
                    print(f"  [warn] Invalid parameter value ({e}), keeping previous.")
                picks.setdefault("hr_stitch_params", {})[f"seg{seg_num}"] = dict(cur_params)
                save_picks(folder, picks)
                print(f"\n  Re-stitching with: {cur_params}")
                del mosaic
                gc.collect()
                mosaic = stitch_chain(seg_num, processed_imgs, picks, params=cur_params)
                print(f"  Stitched mosaic: {mosaic.shape[1]} x {mosaic.shape[0]} px")
                continue

            break

        if picker.segment_action == QuadPicker.ACTION_REDO:
            print("\n  >>> Redoing photo crops for this segment...")
            del mosaic, processed_imgs
            gc.collect()
            continue

        del processed_imgs
        break

    if mosaic_quad is not None:
        picks[mosaic_quad_key] = [[float(x), float(y)] for x, y in mosaic_quad]
        save_picks(folder, picks)
        mosaic = ortho_warp_quad(mosaic, mosaic_quad)
        print(f"  Ortho-corrected mosaic: {mosaic.shape[1]} x {mosaic.shape[0]} px")
    else:
        print("  Skipped mosaic ortho (saving stitched mosaic as-is)")

    raw_hr_name = picker.metadata.get("output_name", default_hr_name).strip() or default_hr_name
    seg_name = prefix_uwi_output_name(raw_hr_name, uwi)
    picks.setdefault("hr_seg_names", {})[f"seg{seg_num}"] = seg_name
    save_picks(folder, picks)

    save_at_dpi(mosaic, folder.parent / seg_name, dpi=600)
    print(f"  Saved: ../{seg_name}.tif/.png ({mosaic.shape[1]} x {mosaic.shape[0]} px)")
    del mosaic
    release_working_memory()
    return True


def process_hr_segments(folder, uwi, picks, segment_filter=None):
    """HR workflow for one folder. Returns ``(segments_saved, quit_requested)``.

    Parameters
    ----------
    folder : str or pathlib.Path
        **Required.** Depth-range image folder. No package default.
    """
    folder = require_path(folder, name="folder")
    print(f"\n{'=' * 65}")
    print(f"  {uwi}/{folder.name}  —  HIGH-RES")
    print(f"{'=' * 65}")

    sources = list_source_images(folder)
    if not sources:
        print(f"  [skip] No source images in {folder.name}")
        return 0, False

    photo_names = [p.name for p in sources]
    n_segments = picks.get("n_segments", N_SEGMENTS_DEFAULT)

    prev_hr = picks.get("hr_assignments", {})
    assignments = assign_hr_photos(sources, n_segments, prev_assignments=prev_hr)
    if assignments is None:
        print("  [skip] HR photo assignment cancelled")
        return 0, False

    segment_photo_indices = {}
    print("\nConfirmed photo assignments:\n")
    for seg_num, indices in sorted(assignments.items()):
        segment_photo_indices[seg_num] = indices
        print(f"  Segment {seg_num}: {len(indices)} photos")
        for idx in indices:
            print(f"    [{idx}] {photo_names[idx]}")

    picks["hr_assignments"] = {f"seg{k}": v for k, v in segment_photo_indices.items()}
    save_picks(folder, picks)

    segments_to_run = (
        [segment_filter] if segment_filter is not None else list(range(1, n_segments + 1))
    )

    saved = 0
    for seg_num in segments_to_run:
        result = process_hr_segment(
            folder, uwi, seg_num, n_segments, photo_names, segment_photo_indices, picks
        )
        if result == "quit":
            return saved, True
        if result == "skip":
            print(f"  HR segment {seg_num}: skipped by user.")
            skipped = picks.setdefault("hr_skipped_segs", [])
            if seg_num not in skipped:
                skipped.append(seg_num)
            save_picks(folder, picks)
            release_working_memory(quiet=True)
            continue
        if result:
            saved += 1

    picks["hr_completed"] = True
    save_picks(folder, picks)
    release_working_memory(quiet=True)
    return saved, False


def process_folder(folder, uwi, folder_idx, total_folders, run_lr=True, run_hr=True, segment_filter=None):
    """Full LR + HR pipeline for one depth folder."""
    picks = load_picks(folder)
    lr_saved = 0
    hr_saved = 0

    if run_lr:
        sources = list_source_images(folder)
        if not sources:
            print(f"  [skip] {uwi}/{folder.name}: no source images for LR")
            return 0, 0, False

        box_path = pick_box_photo(sources, default_path=picks.get("box_photo"))
        if box_path is None:
            print(f"  [skip] {uwi}/{folder.name}: no box photo selected")
            return 0, 0, False
        picks["box_photo"] = box_path.name
        save_picks(folder, picks)

        lr_saved, picks, quit_req = process_lr_segments(
            folder, box_path, uwi, folder_idx, total_folders, picks
        )
        if quit_req:
            return lr_saved, hr_saved, True

    if run_hr:
        hr_saved, quit_req = process_hr_segments(folder, uwi, picks, segment_filter=segment_filter)
        if quit_req:
            return lr_saved, hr_saved, True

    release_working_memory(quiet=True)
    return lr_saved, hr_saved, False


def main(argv=None):
    """CLI batch driver. Requires ``--root`` (no package default for CoreImages)."""
    parser = argparse.ArgumentParser(
        description="Batch core photo processing (LR box extraction + HR mosaics)"
    )
    parser.add_argument(
        "--root",
        required=True,
        help="Required root directory containing {UWI}/{depth-range}/ folders",
    )
    parser.add_argument("--uwi", help="Process only this UWI under --root")
    parser.add_argument(
        "--folder",
        action="append",
        dest="folders",
        metavar="DEPTH-RANGE",
        help="Depth-range folder to process; repeat for multiple (e.g. --folder 2563-2572 --folder 2572-2581)",
    )
    parser.add_argument("--start-at", type=int, default=1, help="Resume from folder index (1-based)")
    parser.add_argument("--lr-only", action="store_true", help="Run low-res only")
    parser.add_argument("--hr-only", action="store_true", help="Run high-res only (uses existing picks)")
    parser.add_argument("--segment", type=int, help="Process only this HR segment number (1-based)")
    args = parser.parse_args(argv)

    if args.lr_only and args.hr_only:
        parser.error("Cannot use --lr-only and --hr-only together")

    run_lr = not args.hr_only
    run_hr = not args.lr_only

    core_images_dir = require_existing_dir(args.root, name="--root / core_images_dir")

    folders = filter_folders(
        discover_depth_folders(core_images_dir),
        uwi=args.uwi,
        folder_names=args.folders,
    )
    total = len(folders)
    mode = "LR+HR" if run_lr and run_hr else ("LR only" if run_lr else "HR only")
    print(f"\nFound {total} depth folder(s) under {core_images_dir} — mode: {mode}\n")

    if total == 0:
        print("Nothing to do.")
        return

    # --- Progress assessment and resume/restart popup ---
    status, summary = assess_progress(folders, run_lr=run_lr, run_hr=run_hr)
    choice = show_progress_and_ask(summary, mode, run_lr=run_lr, run_hr=run_hr)

    if choice == "quit":
        print("Quit by user.")
        return

    if choice == "restart_all":
        print("Restarting ALL — clearing completion flags (picks preserved)...")
        for uwi, folder in folders:
            reset_completion(folder, lr=run_lr, hr=run_hr)
    elif choice == "redo_last":
        # Find the last in-progress folder (has picks/partial work but not complete)
        last_in_progress = None
        for uwi, folder in folders:
            s = status[(uwi, folder)]
            is_complete = (s["lr"] and s["hr"]) if (run_lr and run_hr) else (
                s["lr"] if run_lr else s["hr"]
            )
            if is_complete:
                continue
            # Check if this folder has been touched (has picks file with data)
            picks = load_picks(folder)
            has_progress = (
                picks.get("box_photo")
                or picks.get("box_quads")
                or picks.get("lr_seg_names")
                or picks.get("hr_assignments")
                or s["lr"]  # LR done but HR not
                or s["hr"]  # HR done but LR not
            )
            if has_progress:
                last_in_progress = (uwi, folder)
        if last_in_progress is None:
            print("No in-progress folder found. Use Resume to start from the beginning.")
            return
        uwi, folder = last_in_progress
        print(f"Redoing last in-progress folder: {uwi}/{folder.name}")
        reset_completion(folder, lr=run_lr, hr=run_hr)
        folders = [last_in_progress]
        total = 1
    elif choice == "resume":
        remaining = []
        for uwi, folder in folders:
            s = status[(uwi, folder)]
            if run_lr and run_hr:
                if s["lr"] and s["hr"]:
                    print(f"  [done] {uwi}/{folder.name} — LR+HR complete, skipping")
                    continue
            elif run_lr and not run_hr:
                if s["lr"]:
                    print(f"  [done] {uwi}/{folder.name} — LR complete, skipping")
                    continue
            elif run_hr and not run_lr:
                if s["hr"]:
                    print(f"  [done] {uwi}/{folder.name} — HR complete, skipping")
                    continue
            remaining.append((uwi, folder))
        folders = remaining
        total = len(folders)
        print(f"\n{len(folders)} folder(s) remaining after skipping completed work.\n")
        if total == 0:
            print("All folders already complete. Nothing to do.")
            return

    if args.start_at > 1:
        folders = folders[args.start_at - 1 :]
        start_idx = args.start_at
    else:
        start_idx = 1

    total_lr = 0
    total_hr = 0
    folders_done = 0

    for offset, (uwi, folder) in enumerate(folders):
        idx = start_idx + offset

        # In resume mode for LR+HR, if LR done but HR pending, skip LR for this folder
        folder_run_lr = run_lr
        folder_run_hr = run_hr
        if choice == "resume" and run_lr and run_hr:
            s = status.get((uwi, folder), {"lr": False, "hr": False})
            if s["lr"] and not s["hr"]:
                folder_run_lr = False
                print(f"  [{idx}/{total}] {uwi}/{folder.name} — LR already done, running HR only")

        action = confirm_folder(uwi, folder, idx, total)
        if action == _DialogResult.QUIT:
            print("Quit by user.")
            break
        if action == _DialogResult.SKIP:
            print(f"  Skipped {uwi}/{folder.name}")
            continue

        release_working_memory(quiet=True)
        lr_saved, hr_saved, quit_req = process_folder(
            folder,
            uwi,
            idx,
            total,
            run_lr=folder_run_lr,
            run_hr=folder_run_hr,
            segment_filter=args.segment,
        )
        total_lr += lr_saved
        total_hr += hr_saved
        folders_done += 1
        release_working_memory(quiet=True)

        if quit_req:
            print("Quit by user.")
            break

    print(f"\n{'=' * 65}")
    print(f"  DONE — {folders_done} folder(s) processed")
    print(f"  LR segments saved: {total_lr}  |  HR segments saved: {total_hr}")
    print(f"  Outputs in each UWI folder under {core_images_dir}/")
    print(f"{'=' * 65}")


if __name__ == "__main__":
    main()

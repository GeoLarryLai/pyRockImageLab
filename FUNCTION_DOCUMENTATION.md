# Function documentation

Public functions and classes in `pyrockimagelab`, grouped by module. Each entry is the name, the file, and the first line of the docstring. If that line is missing, the entry says "No docstring."

## pyrockimagelab.common.io_paths

- `release_working_memory` (pyrockimagelab/common/io_paths.py): Close matplotlib figures and collect large numpy/OpenCV allocations.
- `load_any_image` (pyrockimagelab/common/io_paths.py): No docstring.
- `save_at_dpi` (pyrockimagelab/common/io_paths.py): No docstring.
- `load_picks` (pyrockimagelab/common/io_paths.py): Load ``_picks.json`` from a depth-range image folder.
- `save_picks` (pyrockimagelab/common/io_paths.py): Write ``_picks.json`` into a depth-range image folder.
- `parse_folder_depth_range` (pyrockimagelab/common/io_paths.py): No docstring.
- `strip_uwi_prefix` (pyrockimagelab/common/io_paths.py): Remove leading UWI_ from an output stem, if present.
- `prefix_uwi_output_name` (pyrockimagelab/common/io_paths.py): Ensure output stem is {UWI}_{depth-range} or {UWI}_{depth-range}_hr.
- `normalize_lr_seg_name` (pyrockimagelab/common/io_paths.py): Strip legacy _lr suffix and optional UWI prefix so LR stem is {start}-{end}.
- `default_hr_name_from_lr` (pyrockimagelab/common/io_paths.py): Build HR stem from LR name: {UWI}_2563-2566 -> {UWI}_2563-2566_hr.
- `list_source_images` (pyrockimagelab/common/io_paths.py): List source photos in a depth-range folder (excludes outputs / HEIC-ok check via VALID_EXTS).
- `discover_depth_folders` (pyrockimagelab/common/io_paths.py): Return sorted ``[(uwi, folder_path), ...]`` under ``{root}/{UWI}/{depth-range}/``.
- `filter_folders` (pyrockimagelab/common/io_paths.py): No docstring.
- `assess_progress` (pyrockimagelab/common/io_paths.py): Scan _picks.json for each folder. Returns (status_dict, summary).
- `reset_completion` (pyrockimagelab/common/io_paths.py): Clear completion flags and skip lists but preserve corner picks and names.

## pyrockimagelab.common.require

- `MissingRequiredError` (pyrockimagelab/common/require.py): Raised when a required folder/root path argument is missing.
- `require_path` (pyrockimagelab/common/require.py): Return ``Path(value)`` or raise naming what is missing.
- `require_existing_dir` (pyrockimagelab/common/require.py): Return an existing directory path or raise.

## pyrockimagelab.common.ui

- `QuadPicker` (pyrockimagelab/common/ui.py): Interactive 4-point picker with auto-sorted corners (TL, TR, BR, BL).
- `confirm_folder` (pyrockimagelab/common/ui.py): Yes / Skip / Quit dialog using matplotlib. Returns _DialogResult.
- `pick_box_photo` (pyrockimagelab/common/ui.py): Matplotlib-based box-photo selector with thumbnail grid.
- `assign_hr_photos` (pyrockimagelab/common/ui.py): Matplotlib thumbnail picker for photo-to-segment assignment.
- `show_progress_and_ask` (pyrockimagelab/common/ui.py): Matplotlib popup with progress counts and Resume/Restart/Quit buttons.

## pyrockimagelab.core_box.processing

- `process_lr_segments` (pyrockimagelab/core_box/processing.py): LR extraction loop. Returns ``(segments_saved, picks, quit_requested)``.
- `process_hr_segment` (pyrockimagelab/core_box/processing.py): Crop, stitch, mosaic ortho, and save one HR segment.
- `process_hr_segments` (pyrockimagelab/core_box/processing.py): HR workflow for one folder. Returns ``(segments_saved, quit_requested)``.
- `process_folder` (pyrockimagelab/core_box/processing.py): Full LR + HR pipeline for one depth folder.
- `main` (pyrockimagelab/core_box/processing.py): CLI batch driver. Requires ``--root`` (no package default for CoreImages).

## pyrockimagelab.image_processing.stitch

- `stitch_chain` (pyrockimagelab/image_processing/stitch.py): Sequentially stitch RGB images. Always produces output.

## pyrockimagelab.image_processing.warp

- `ortho_warp_quad` (pyrockimagelab/image_processing/warp.py): No docstring.

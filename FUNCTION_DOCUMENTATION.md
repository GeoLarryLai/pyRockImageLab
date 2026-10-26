# Function documentation

Public functions and classes in `pyrockimagelab`, grouped by module. Each entry is the name, the file, and the first line of the docstring. If that line is missing, the entry says "No docstring."

## pyrockimagelab.common.io_paths

- `release_working_memory` (pyrockimagelab/common/io_paths.py): Close matplotlib figures (if matplotlib is in use) and collect large allocations.
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

## pyrockimagelab.core_box.processing

- `lr_segment_defaults` (pyrockimagelab/core_box/processing.py): Default ``[{"seg", "length_ft", "output_name"}, ...]`` for every box-photo section.
- `lr_name_for_length` (pyrockimagelab/core_box/processing.py): Output name implied by a new section length (live update in the app).
- `crop_lr_segment` (pyrockimagelab/core_box/processing.py): Straighten one box-photo section from its 4 corners (+ contrast enhancement).
- `save_lr_segment` (pyrockimagelab/core_box/processing.py): Record one section in ``picks``, write ``_picks.json`` and save ``../{name}.tif/.png`` (300 dpi).
- `hr_default_name` (pyrockimagelab/core_box/processing.py): No docstring.
- `crop_hr_photo` (pyrockimagelab/core_box/processing.py): Trim + straighten one close-up photo (``quad=None`` keeps the full photo).
- `stitch_params_for` (pyrockimagelab/core_box/processing.py): No docstring.
- `stitch_hr_segment` (pyrockimagelab/core_box/processing.py): Crop every assigned close-up with its saved corners and stitch them. Returns ``(mosaic, names)``.
- `finish_hr_segment` (pyrockimagelab/core_box/processing.py): Straighten the joined image with its 4 corners, trim empty rows, save ``../{name}.tif/.png`` (600 dpi).
- `process_lr_segments` (pyrockimagelab/core_box/processing.py): Save every box-photo section that has saved corners. Returns ``(saved, picks, False)``.
- `process_hr_segment` (pyrockimagelab/core_box/processing.py): Stitch and save one close-up section from saved picks. Returns True/None.
- `process_hr_segments` (pyrockimagelab/core_box/processing.py): Replay every assigned close-up section. Returns ``(saved, False)``.
- `process_folder` (pyrockimagelab/core_box/processing.py): Replay a whole depth folder from its ``_picks.json``. Returns ``(lr_saved, hr_saved, False)``.
- `main` (pyrockimagelab/core_box/processing.py): CLI: replay saved corners for every depth folder under ``--root``.

## pyrockimagelab.image_processing.stitch

- `stitch_chain` (pyrockimagelab/image_processing/stitch.py): Sequentially stitch RGB images. Always produces output.

## pyrockimagelab.image_processing.warp

- `ortho_warp_quad` (pyrockimagelab/image_processing/warp.py): No docstring.
- `clamp_quad_to_image` (pyrockimagelab/image_processing/warp.py): Clip quad corners to the image bounds (avoids empty/black margins when a
- `trim_empty_rows` (pyrockimagelab/image_processing/warp.py): Drop top/bottom rows that are mostly empty (near-black) after warping.

## pyrockimagelab.webapp

- `main` (pyrockimagelab/webapp/__init__.py): No docstring.

## pyrockimagelab.webapp.routes

- `State` (pyrockimagelab/webapp/routes.py): No docstring.
- `create_app` (pyrockimagelab/webapp/routes.py): No docstring.

## pyrockimagelab.webapp.shell.jobs

- `Job` (pyrockimagelab/webapp/shell/jobs.py): Job(id: 'str', title: 'str', n: 'int' = 0, N: 'int' = 1, message: 'str' = '', state: 'str' = 'running', result: 'object' = None, error: 'str | None' = None, t0: 'float' = <factory>, t1: 'float | None' = None)
- `JobRunner` (pyrockimagelab/webapp/shell/jobs.py): ``submit(title, fn)`` runs ``fn(job)`` in a daemon thread; ``fn`` calls ``job.progress(n, N, msg)``

## pyrockimagelab.webapp.shell.server

- `free_port` (pyrockimagelab/webapp/shell/server.py): No docstring.
- `open_folder` (pyrockimagelab/webapp/shell/server.py): No docstring.
- `mount_shell` (pyrockimagelab/webapp/shell/server.py): Add /shell/static, GET /shell/api/jobs/{id}, POST /shell/api/quit and
- `serve` (pyrockimagelab/webapp/shell/server.py): Run ``app`` on http://127.0.0.1:<free port> until Ctrl+C or the Quit button.

The browser app is started with `pyrockimagelab-app` (`pyrockimagelab.webapp.main`).

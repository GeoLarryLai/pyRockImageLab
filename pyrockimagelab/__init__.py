"""pyRockImageLab — crop core-box photos and stitch close-up core photos (browser app: ``pyrockimagelab-app``).

Import
------
>>> import pyrockimagelab as pril
>>> help(pril.process_folder)  # required: folder, uwi, ...

Version: 0.1.0

Required caller inputs (no CISR/CoreImages path defaults)
---------------------------------------------------------
- ``folder``: depth-range image folder path for per-folder processing
- ``core_images_dir`` / ``--root``: root containing ``{UWI}/{depth-range}/`` trees
  for batch discovery

Method knobs (e.g. N_SEGMENTS, stitch params) may keep package defaults.
"""

from pyrockimagelab import common, core_box, image_processing
from pyrockimagelab.common.require import MissingRequiredError, require_existing_dir, require_path
from pyrockimagelab.core_box.processing import (
    main,
    process_folder,
    process_hr_segment,
    process_hr_segments,
    process_lr_segments,
    lr_segment_defaults,
    lr_name_for_length,
    crop_lr_segment,
    save_lr_segment,
    hr_default_name,
    crop_hr_photo,
    stitch_params_for,
    stitch_hr_segment,
    finish_hr_segment,
)
from pyrockimagelab.image_processing.warp import clamp_quad_to_image, trim_empty_rows
from pyrockimagelab.common import (
    DEFAULT_HR_PHOTO_RANGES,
    DEFAULT_SEG_LENGTH_FT,
    DISPLAY_LONG_SIDE,
    HEIC_OK,
    MATCH_RATIO,
    MAX_CANVAS_PIXELS,
    MAX_PERSPECT_DISTORT,
    N_SEGMENTS_DEFAULT,
    NFEATURES,
    PICKS_FILENAME,
    RANSAC_REPROJ,
    USE_HDR_GAINMAP,
    VALID_EXTS,
    WORK_MEGAPIX,
    assess_progress,
    default_hr_name_from_lr,
    discover_depth_folders,
    filter_folders,
    list_source_images,
    load_any_image,
    load_picks,
    normalize_lr_seg_name,
    ortho_warp_quad,
    parse_folder_depth_range,
    prefix_uwi_output_name,
    release_working_memory,
    reset_completion,
    save_at_dpi,
    save_picks,
    stitch_chain,
)

# Back-compat alias names used by old top-level __all__
require = common.require
processing = core_box.processing

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "common",
    "image_processing",
    "core_box",
    "processing",
    "require",
    "MissingRequiredError",
    "require_path",
    "require_existing_dir",
    "process_folder",
    "process_lr_segments",
    "process_hr_segments",
    "process_hr_segment",
    "lr_segment_defaults",
    "lr_name_for_length",
    "crop_lr_segment",
    "save_lr_segment",
    "hr_default_name",
    "crop_hr_photo",
    "stitch_params_for",
    "stitch_hr_segment",
    "finish_hr_segment",
    "clamp_quad_to_image",
    "trim_empty_rows",
    "main",
    "discover_depth_folders",
    "filter_folders",
    "list_source_images",
    "load_picks",
    "save_picks",
    "load_any_image",
    "save_at_dpi",
    "stitch_chain",
    "assess_progress",
    "reset_completion",
    "ortho_warp_quad",
    "parse_folder_depth_range",
    "normalize_lr_seg_name",
    "default_hr_name_from_lr",
    "prefix_uwi_output_name",
    "release_working_memory",
    "N_SEGMENTS_DEFAULT",
    "DEFAULT_SEG_LENGTH_FT",
    "DEFAULT_HR_PHOTO_RANGES",
    "NFEATURES",
    "MATCH_RATIO",
    "RANSAC_REPROJ",
    "WORK_MEGAPIX",
    "MAX_PERSPECT_DISTORT",
    "MAX_CANVAS_PIXELS",
    "USE_HDR_GAINMAP",
    "DISPLAY_LONG_SIDE",
    "VALID_EXTS",
    "PICKS_FILENAME",
    "HEIC_OK",
]

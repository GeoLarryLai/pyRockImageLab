"""Core-box LR/HR processing and CLI."""

from pyrockimagelab.core_box.processing import (
    main,
    process_folder,
    process_hr_segment,
    process_hr_segments,
    process_lr_segments,
)

__all__ = [
    "process_folder",
    "process_lr_segments",
    "process_hr_segments",
    "process_hr_segment",
    "main",
]

# pyRockImageLab

**pyRockImageLab** (`import pyrockimagelab`) provides interactive tools to crop,
ortho-warp, stitch, and mosaic geological **core photographs** — from low-res
box photos (LR segments) to high-res detail mosaics (HR).

| Package path | Role |
|--------------|------|
| `pyrockimagelab/common/` | Shared I/O, picks, `QuadPicker`, discovery helpers |
| `pyrockimagelab/image_processing/` | `ortho_warp_quad`, `stitch_chain` |
| `pyrockimagelab/core_box/` | Per-folder / batch LR+HR processing + CLI entry point |

**Version:** 0.0.1  
**License:** [AGPL-3.0-or-later](LICENSE)

> [!IMPORTANT]
> Filesystem paths are **required**. The package does **not** ship defaults for
> `CoreImages/`, CISR Dropbox trees, or any project-specific root. Pass
> `folder` / `core_images_dir` / `--root` from your notebook or CLI.

## Installation

### From source (this checkout)

```bash
cd pyrockimagelab
pip install -e .
# or: pip install -e ".[heic]"
```

### Conda env

```bash
conda env create -f environment.yml
conda activate pyrockimagelab
```

### Dependencies

- Python ≥ 3.9
- `numpy`, `opencv-python`, `Pillow`, `matplotlib`
- Optional: `pillow-heif` (HEIC/HEIF), `PyQt5` (GUI backend off macOS)

Interactive picking needs a local matplotlib GUI backend (macOS `MacOSX`, else Qt or Tk).

## Layout expected by the tools

Caller-supplied root:

```text
{core_images_dir}/{UWI}/{depth-range}/     # source photos + _picks.json
{core_images_dir}/{UWI}/{UWI}_{start}-{end}[_hr].png   # outputs
```

Example depth-range folder name: `7168-7172`.

## Library usage

```python
import pyrockimagelab as pril

# Required: folder path + UWI (and related kwargs as needed)
pril.process_folder(
    folder="/path/to/CoreImages/30015058530000/7168-7172",
    uwi="30015058530000",
)

# Building blocks
from pyrockimagelab import QuadPicker, stitch_chain, process_lr_segments, process_hr_segment
```

```python
from pyrockimagelab.common import discover_depth_folders, load_picks

folders = discover_depth_folders(core_images_dir="/path/to/CoreImages")
picks = load_picks(folder="/path/to/CoreImages/UWI/7168-7172")
```

## CLI

```bash
python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --help
python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages
python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --lr-only
python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --uwi 30015058530000 --folder 7168-7172
```

After install, the `pyrockimagelab` console script points at the same entry point.

## Typical interactive workflow

1. **LR (box photo)** — confirm folder → pick box photo → `QuadPicker` corners → extract LR segments  
2. **HR (detail photos)** — assign photo ranges per segment → crop/ortho each photo → `stitch_chain` → mosaic ortho  
3. Progress and corner picks are stored in `{folder}/_picks.json`

Method knobs (segment count, SIFT `NFEATURES`, RANSAC thresholds, work megapixels, etc.) may keep package defaults; override from the notebook or function kwargs.

## Example notebook

Project-root notebook (paths only in a config cell):

- `pyRockImageLab-01_core_photo_processing.ipynb`

## Packaging notes

Publish-ready files in this directory:

- `pyproject.toml` / `setup.py`
- `LICENSE` (AGPL-3.0-or-later)
- `README.md` (this file) / `README-pypi.md` (PyPI long description)
- `environment.yml`

No upload is performed by the package itself.

## Citation / contact

Larry Syu-Heng Lai  
larry.lai@beg.utexas.edu · larrysyuhenglai@gmail.com  
[Quantitative Clastics Laboratory](https://qcl.beg.utexas.edu), Bureau of Economic Geology, The University of Texas at Austin

## Related

- **pyLogCrafter** (`pylogcrafter`) — well-log QC, normalization, imputation, facies, and viz companion package

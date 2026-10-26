# pyRockImageLab

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23656974.svg)](https://doi.org/10.5281/zenodo.23656974) [![PyPI version](https://img.shields.io/pypi/v/pyrockimagelab.svg)](https://pypi.org/project/pyrockimagelab/) [![PyPI downloads](https://static.pepy.tech/badge/pyrockimagelab/month)](https://pepy.tech/project/pyrockimagelab)

v0.0.3

**pyRockImageLab** (`import pyrockimagelab`) provides interactive tools to crop, ortho-warp, stitch, and mosaic geological core photographs, from low-res box photos (LR segments) to high-res detail mosaics (HR).

> [!NOTE]
> Filesystem paths are required. The package does not ship defaults for a core-image root or any project-specific folder. Pass `folder`, `core_images_dir`, or `--root` from your notebook or CLI.

![QuadPicker interface for selecting a core-box segment](https://raw.githubusercontent.com/GeoLarryLai/pyRockImageLab/main/docs/media/quadpicker_ui.png)

*Picking the four corners of a core-box segment in QuadPicker (example core box from `example_data/ExampleCore`).*

Contact:

Larry Syu-Heng Lai (larrysyuhenglai@gmail.com)  
The project was initiated when Larry was affiliated at the [Quantitative Clastics Laboratory](https://qcl.beg.utexas.edu/), Bureau of Economic Geology, The University of Texas at Austin

## Installation

From [PyPI](https://pypi.org/project/pyrockimagelab/):

```bash
pip install pyrockimagelab
```

From this repo:

```bash
conda env create -f environment.yml
conda activate pyrockimagelab
pip install -e ".[heic,gui]"
```

Interactive picking needs a local matplotlib GUI backend (macOS `MacOSX`, otherwise Qt or Tk).

## Citation

Lai, L.S.-H. (2026) pyRockImageLab. *Zenodo*, https://doi.org/10.5281/zenodo.23656974

## Key Features

- Crop a box photo into depth segments with a four-corner ortho-warp (`QuadPicker`).
- Stitch high-res detail photos along a segment (`stitch_chain`) and build a mosaic.
- Save corner picks in `_picks.json` so a later run can start from the same corners.
- Command-line entry point: `pyrockimagelab`.

## Example notebooks

[`pyRockImageLab_1_ExampleCore.ipynb`](https://github.com/GeoLarryLai/pyRockImageLab/blob/main/pyRockImageLab_1_ExampleCore.ipynb) runs end to end on the small example set in `example_data/ExampleCore/` (one box photo, six close-up photos and saved corner picks, about 15 MB). It crops, stitches and ortho-corrects the close-ups into a high-resolution mosaic of the 2563–2566 ft segment and writes PNGs to `outputs/`. Set `INTERACTIVE = True` to re-pick corners in the Qt windows.

![Box-photo segment and high-resolution mosaic for 2563–2566 ft](https://raw.githubusercontent.com/GeoLarryLai/pyRockImageLab/main/figures/ExampleCore_2563-2566_hr.png)

*Segment 1 from the box photo (left) and the stitched high-resolution mosaic (right).*

[`pyRockImageLab_1_core_photo_processing.ipynb`](https://github.com/GeoLarryLai/pyRockImageLab/blob/main/pyRockImageLab_1_core_photo_processing.ipynb) is the full workflow notebook for your own data.

That notebook only sets the folder path, segment count, and high-res photo ranges, then calls the package. Put your own core photos outside this repo and pass that folder in.

Caller-supplied layout:

```text
{core_images_dir}/{UWI}/{depth-range}/          # source photos + _picks.json
{core_images_dir}/{UWI}/{UWI}_{start}-{end}[_hr].png
```

```python
import pyrockimagelab as pril

pril.process_folder(
    folder="/path/to/CoreImages/UWI/start-end",
    uwi="UWI",
)
```

```bash
python -m pyrockimagelab.core_box.processing --root /path/to/CoreImages --uwi UWI --folder start-end
```

## Package structure

```
README.md
README-pypi.md
FUNCTION_DOCUMENTATION.md
pyproject.toml
setup.py
environment.yml
example_data/ExampleCore/        # anonymized example photos + _picks.json
figures/
pyRockImageLab_1_ExampleCore.ipynb
pyrockimagelab/
    common/
    image_processing/
    core_box/
```

Function list: `FUNCTION_DOCUMENTATION.md`.

## Dependencies

Requires Python >=3.10.

Installed with the package: numpy (>=1.20), opencv-python (>=4.5), Pillow (>=8.3), matplotlib (>=3.5).

Optional extras:

- `heic`: pillow-heif >=0.13
- `gui`: PyQt5 >=5.15

## License

```text
Program: pyRockImageLab
Interactive tools for core and outcrop image processing, data
collection, and automated geological and geomorphic classification and
analysis
Copyright (C) 2026  Larry Syu-Heng Lai
```

pyRockImageLab is licensed under the GNU Affero General Public License 3.0 or later. See [LICENSE](https://github.com/GeoLarryLai/pyRockImageLab/blob/main/LICENSE).

## Related

- **pyLogCrafter** (`pylogcrafter`) — well-log QC, normalization, imputation, facies, and viz companion package

# pyRockImageLab browser app: plan (draft for Larry's approval)

## 1. What exists today (GitHub main 2016e8c, v0.0.3)
Package scope today: **core-box photos only.** You get low-res (LR) segments from the box photo and high-res (HR) mosaics from detail photos. There's no outcrop or classification code yet.

| Notebook | UI today |
|---|---|
| `pyRockImageLab_1_core_photo_processing.ipynb` | `%matplotlib qt`, which opens blocking matplotlib windows (Qt/MacOSX backend) from `common/ui.py`. Settings like FOLDER, N_SEGMENTS and HR_PHOTO_RANGES are edited in code cells. |
| `pyRockImageLab_1_ExampleCore.ipynb` | Replays the saved `_picks.json` without interaction (INTERACTIVE=False). Optionally it opens the same Qt pickers. |

The pop-ups, all matplotlib widgets in `common/ui.py`, are called by `core_box/processing.py`:
1. `confirm_folder`: Process / Skip / Quit for each depth folder.
2. `show_progress_and_ask`: Resume / Restart All / Redo Last / Quit.
3. `pick_box_photo`: click a thumbnail to choose the box photo.
4. `QuadPicker` (LR): drag the 4 corners (TL/TR/BR/BL, with snapping) for each segment. It has depth/name TextBoxes and Skip seg / Quit buttons. Keys: Enter, r, Esc, s, q.
5. `assign_hr_photos`: Seg N buttons plus clicking photos to assign them to segments, then OK / Cancel.
6. `QuadPicker` (HR crop, one per detail photo): adds Skip Photo / Redo crops.
7. `QuadPicker` (mosaic ortho quad): adds Restitch, with SIFT/RANSAC parameters.

The backend is already cleanly separated: `warp.py` (ortho_warp_quad, CLAHE enhance, clamp, trim), `stitch.py` (stitch_chain), and `io_paths.py` (picks JSON, folder discovery, naming, progress, save_at_dpi). However, `process_lr_segments`/`process_hr_segment` mix the UI calls with the processing, so they'll need to be split into "compute" and "pick" pieces.

## 2. Pain points
- Every pop-up is blocking, which is fragile in Jupyter: you need a GUI backend, it doesn't work on Colab or headless machines, and Qt pulls in about 200 MB.
- Settings live in code cells, with no undo or overview. It's hard to see which segments and folders are done.
- Restitch is a full re-run that blocks the UI. On the example data, stitching segment 1 took **12 s** for 6 photos into a 16k×1.6k px mosaic, with **~1.9 GB peak RAM** (box, Linux).
- The headless pipeline on the example data works (the crop, stitch and ortho steps run fine).
- Metadata: `pyproject.toml` `authors` contains the email address, which breaks the no-emails-in-metadata rule. This should be fixed in the same release.

## 3. Proposed app (FastAPI + uvicorn, same style as pyPetrograph)
`pyrockimagelab-app`: a local server that opens in the browser. It's a step-by-step flow with a left sidebar of steps and one canvas, all in the clean pyPetrograph look.

| Step | Controls |
|---|---|
| 1. Project | Root folder, UWI, a list of depth folders with status chips (todo / LR done / HR done), and Resume / Restart / Redo last. This replaces confirm_folder and show_progress. |
| 2. Box photo | A thumbnail grid where you click to choose; it also sets the segment count. |
| 3. LR segments | Canvas with draggable 4-corner quads, one per segment and all visible at once, with snapping and a live ortho preview. Has depth start/end and name fields, plus Skip / Save. |
| 4. Assign HR photos | Segment columns with drag-and-drop photo thumbnails, prefilled from the default ranges. |
| 5. HR crops | Per-photo quad editor with a filmstrip, and Skip photo / Redo. |
| 6. Stitch + ortho | A Stitch button that runs in the background with a progress log, SIFT/ratio/RANSAC sliders, a Restitch button, and a mosaic quad editor with a preview. |
| 7. Export | DPI and format (tif/png) settings, the output file list, and download. |

Everything is saved to the same `_picks.json`, so the app, the notebooks and the CLI stay interchangeable.

**Reused:** warp.py, stitch.py, io_paths.py, the naming rules, and picks.json.
**New:** `webapp/` (FastAPI routes plus one static HTML/JS page with a canvas quad editor), and non-UI `compute_lr_segment` / `compute_hr_segment` functions split out of processing.py. Images are served as downscaled previews; full resolution is used only for the final warp.
**Notebooks keep:** the headless example notebook (replaying picks) and a scripting/batch notebook. The interactive Qt cells are replaced by "launch the app".

## 4. Dependencies and size
- Base install now (numpy, opencv-python, Pillow, matplotlib): **368 MB** (clean venv, Py 3.13 on Linux; Py 3.12 is expected to be about the same).
- The current `[gui]` extra with PyQt5, which the notebooks need: **569 MB**.
- Proposed base: the same packages plus fastapi and uvicorn (about 10 MB), so **~380 MB**, with no Qt. matplotlib stays, for figures and the legacy pickers. PyQt5 becomes optional or is dropped. Optional: switch to `opencv-python-headless`, which saves a little and avoids clashing with Qt.

## 5. Risks
- Memory: HR mosaics are big (16k px, ~2 GB RAM). The app has to stream previews and avoid holding several folders in memory.
- Behaviour parity: corner snapping, auto-sorting the quad, and the depth/name rules all have to match. I'll check this by replaying `_picks.json` and comparing the outputs byte for byte against the current functions, as was done for pyPetrograph.
- HEIC support still depends on the optional pillow-heif.
- Refactoring processing.py touches public functions, so the old signatures need to stay as wrappers.

## 6. Build order
1. Split compute from UI in processing.py, and add tests that replay the example picks. Outputs must stay identical.
2. App skeleton: project/folder status, box photo, and LR quad editor.
3. HR assignment and crops.
4. Background stitching with params and the mosaic quad, then export.
5. Equivalence and speed checks against the notebook, then README and screenshots for your review, then a 0.1.0 release via Github Manager once you approve.

## 7. Decisions for Larry
1. **Scope:** core-box workflow only for now (it's the only one in the code), with outcrop and classification added later as more tabs in the **same app**? Or should those be planned in now?
2. **Qt:** remove the Qt pickers and PyQt5 entirely (as was done for pyPetrograph), or keep them as an optional legacy extra?
3. **Batch mode:** should the app handle a whole root with many UWIs and depth folders, which replaces the CLI loop? Or one depth folder at a time, which is simpler?

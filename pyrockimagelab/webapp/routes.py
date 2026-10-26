# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Larry Syu-Heng Lai
"""FastAPI routes. Two tools share one project: ``crop`` (core-box photo -> one straightened
image per core section) and ``stitch`` (close-up photos -> one long high-resolution image).
All science calls are the package's own (``pyrockimagelab.core_box.processing``); every
choice is written to the folder's ``_picks.json`` exactly as the notebooks/CLI expect."""
from __future__ import annotations

import gc
import io
import threading
from pathlib import Path

import cv2
import numpy as np
from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from pyrockimagelab.common.io_paths import (
    DISPLAY_LONG_SIDE, assess_progress, discover_depth_folders, list_source_images,
    load_any_image, load_picks, save_picks,
)
from pyrockimagelab.core_box import processing as P
from pyrockimagelab.webapp.shell import JobRunner, mount_shell

STATIC = Path(__file__).parent / "static"
PREVIEW_LONG = DISPLAY_LONG_SIDE          # 1600 px, as the old pickers
MOSAIC_PREVIEW_LONG = 4000                # joined images are very tall


def _jpeg(rgb, q=88) -> bytes:
    ok, buf = cv2.imencode(".jpg", cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, q])
    return buf.tobytes()


def _shrink(rgb, long_side):
    h, w = rgb.shape[:2]
    s = min(1.0, long_side / max(h, w))
    if s >= 1.0:
        return rgb, 1.0
    return cv2.resize(rgb, (max(1, round(w * s)), max(1, round(h * s))), interpolation=cv2.INTER_AREA), s


def _quad(q):
    if q is None:
        return None
    a = np.asarray(q, dtype=float)
    if a.shape != (4, 2):
        raise HTTPException(400, "Corners must be 4 points (x, y).")
    return a.tolist()


class State:
    def __init__(self, root=None):
        self.lock = threading.RLock()
        self.root = Path(root).expanduser().resolve() if root else None
        self.uwi = None
        self.folder: Path | None = None
        self.picks: dict | None = None
        self.sources: list[Path] = []
        self._img_cache: dict[str, np.ndarray] = {}
        self._prev_cache: dict[tuple, bytes] = {}
        self.mosaic: dict[int, np.ndarray] = {}

    # images ---------------------------------------------------------------
    def image(self, name):
        if name not in self._img_cache:
            if len(self._img_cache) >= 2:               # keep memory low: 2 full photos max
                self._img_cache.pop(next(iter(self._img_cache)))
            self._img_cache[name] = load_any_image(self.folder / name)
        return self._img_cache[name]

    def preview(self, name, long_side):
        k = (str(self.folder), name, long_side)
        if k not in self._prev_cache:
            small, _ = _shrink(self.image(name), long_side)
            self._prev_cache[k] = _jpeg(small)
        return self._prev_cache[k]

    def need(self):
        if self.folder is None:
            raise HTTPException(409, "Open a depth folder first.")

    def names(self):
        return [p.name for p in self.sources]


def _folder_rows(root: Path):
    rows = []
    folders = discover_depth_folders(root)
    status, _ = assess_progress(folders)
    for uwi, f in folders:
        pk = load_picks(f)
        n = int(pk.get("n_segments", 3))
        box = pk.get("box_photo") or ""
        crop_done = sum(1 for i in range(1, n + 1) if f"{box}::seg{i}" in pk.get("box_quads", {})
                        and (f.parent / f"{pk.get('lr_seg_names', {}).get(f'seg{i}', '#')}.png").exists())
        stitch_done = sum(1 for i in range(1, n + 1) if (f.parent / f"{pk.get('hr_seg_names', {}).get(f'seg{i}', '#')}.png").exists())
        rows.append(dict(uwi=uwi, folder=f.name, photos=len(list_source_images(f)), sections=n,
                         cropped=crop_done, stitched=stitch_done,
                         crop_complete=status[(uwi, f)]["lr"], stitch_complete=status[(uwi, f)]["hr"]))
    return rows


def create_app(root=None, testing=False) -> FastAPI:
    app = FastAPI(title="pyRockImageLab", docs_url=None, redoc_url=None)
    app.state.testing = testing
    st = State(root)
    app.state.st = st
    runner = JobRunner(error_types=(HTTPException, ValueError, FileNotFoundError))
    app.state.runner = runner
    mount_shell(app, runner)
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    # project ----------------------------------------------------------------
    @app.get("/api/project")
    def project():
        if st.root is None:
            return dict(root=None, folders=[])
        return dict(root=str(st.root), folders=_folder_rows(st.root))

    @app.post("/api/project")
    def set_project(body: dict = Body(...)):
        p = Path(str(body.get("root", "")).strip()).expanduser()
        if not p.is_dir():
            raise HTTPException(404, f"Folder not found: {p}")
        st.root = p.resolve()
        rows = _folder_rows(st.root)
        if not rows:
            raise HTTPException(400, "No photo folders found. Expected {well}/{start-end}/ inside this folder, e.g. MyWell/2563-2572/.")
        return dict(root=str(st.root), folders=rows)

    @app.post("/api/open")
    def open_folder(body: dict = Body(...)):
        if st.root is None:
            raise HTTPException(409, "Choose a project folder first.")
        f = st.root / str(body["uwi"]) / str(body["folder"])
        if not f.is_dir():
            raise HTTPException(404, f"Folder not found: {f}")
        with st.lock:
            st.uwi, st.folder = str(body["uwi"]), f
            st.picks = load_picks(f)
            st.sources = list_source_images(f)
            st._img_cache.clear(); st._prev_cache.clear(); st.mosaic.clear(); gc.collect()
        return folder_state()

    @app.get("/api/folder")
    def folder_state():
        st.need()
        pk = st.picks
        return dict(uwi=st.uwi, folder=st.folder.name, out_dir=str(st.folder.parent), photos=st.names(),
                    box_photo=pk.get("box_photo"), n_sections=int(pk.get("n_segments", 3)),
                    assignments={k: v for k, v in pk.get("hr_assignments", {}).items()})

    @app.get("/api/thumb/{i}")
    def thumb(i: int):
        st.need()
        name = st.names()[i]
        k = (str(st.folder), name, "t")
        if k not in st._prev_cache:
            img = load_any_image(st.folder / name)
            st._prev_cache[k] = _jpeg(_shrink(img, 220)[0], 80)
            del img
        return Response(st._prev_cache[k], media_type="image/jpeg")

    @app.get("/api/photo/{i}")
    def photo(i: int):
        st.need()
        name = st.names()[i]
        img = st.image(name)
        return Response(st.preview(name, PREVIEW_LONG), media_type="image/jpeg",
                        headers={"X-Full-Size": f"{img.shape[1]}x{img.shape[0]}"})

    # crop tool --------------------------------------------------------------
    def crop_state():
        pk = st.picks
        box = pk.get("box_photo")
        img = st.image(box)
        secs = P.lr_segment_defaults(st.folder, st.uwi, pk)
        names = pk.get("lr_seg_names", {})
        for s in secs:
            i = s["seg"]
            s["corners"] = pk["box_quads"].get(f"{box}::seg{i}")
            s["saved"] = (st.folder.parent / (names.get(f"seg{i}", "#") + ".png")).exists()
        return dict(box_photo=box, index=st.names().index(box), size=[img.shape[1], img.shape[0]], sections=secs)

    @app.post("/api/crop/box")
    def crop_box(body: dict = Body(...)):
        st.need()
        name = st.names()[int(body["index"])]
        with st.lock:
            st.picks["box_photo"] = name
            save_picks(st.folder, st.picks)
        return crop_state()

    @app.get("/api/crop")
    def crop_get():
        st.need()
        if not st.picks.get("box_photo"):
            raise HTTPException(409, "Choose the core-box photo first.")
        return crop_state()

    @app.post("/api/crop/sections")
    def crop_sections(body: dict = Body(...)):
        """Update section count / corners / lengths / names (no image written)."""
        st.need()
        pk = st.picks
        with st.lock:
            if "n_sections" in body:
                n = int(body["n_sections"])
                if not 1 <= n <= 20:
                    raise HTTPException(400, "Number of core sections must be 1–20.")
                pk["n_segments"] = n
            for s in body.get("sections", []):
                i = int(s["seg"])
                if s.get("clear"):
                    pk["box_quads"].pop(f"{pk['box_photo']}::seg{i}", None)
                elif s.get("corners") is not None:
                    pk["box_quads"][f"{pk['box_photo']}::seg{i}"] = _quad(s["corners"])
                if s.get("length_ft") not in (None, ""):
                    float(s["length_ft"])
                    pk.setdefault("lr_seg_lengths", {})[f"seg{i}"] = str(s["length_ft"]).strip()
                    if not s.get("output_name"):
                        pk.get("lr_seg_names", {}).pop(f"seg{i}", None)
                if s.get("output_name"):
                    pk.setdefault("lr_seg_names", {})[f"seg{i}"] = str(s["output_name"]).strip()
            save_picks(st.folder, pk)
        return crop_state()

    @app.post("/api/crop/preview")
    def crop_preview(body: dict = Body(...)):
        st.need()
        q = _quad(body["corners"])
        out = P.crop_lr_segment(st.image(st.picks["box_photo"]), q)
        return Response(_jpeg(_shrink(out, 900)[0]), media_type="image/jpeg")

    @app.post("/api/crop/save")
    def crop_save(body: dict = Body(default={})):
        st.need()
        pk = st.picks
        box = pk["box_photo"]
        todo = [s for s in P.lr_segment_defaults(st.folder, st.uwi, pk)
                if pk["box_quads"].get(f"{box}::seg{s['seg']}") is not None]
        if body.get("seg"):
            todo = [s for s in todo if s["seg"] == int(body["seg"])]
        if not todo:
            raise HTTPException(400, "Mark the corners of at least one core section first.")

        def work(job):
            files = []
            img = st.image(box)
            for k, s in enumerate(todo):
                job.progress(k, len(todo), f"saving section {s['seg']}")
                with st.lock:
                    name, shape, paths = P.save_lr_segment(st.folder, st.uwi, pk, s["seg"],
                                                           pk["box_quads"][f"{box}::seg{s['seg']}"], img,
                                                           s["length_ft"], s["output_name"])
                files.append(dict(seg=s["seg"], name=name, size=[shape[1], shape[0]], files=[p.name for p in paths]))
            n = int(pk.get("n_segments", 3))
            if all(pk["box_quads"].get(f"{box}::seg{i}") for i in range(1, n + 1)):
                pk["lr_completed"] = True
                save_picks(st.folder, pk)
            return dict(out_dir=str(st.folder.parent), saved=files)
        return dict(job=runner.submit("Saving section images", work, sync=testing).as_dict())

    # stitch tool -----------------------------------------------------------
    @app.post("/api/stitch/assign")
    def stitch_assign(body: dict = Body(...)):
        st.need()
        pk = st.picks
        with st.lock:
            if "n_sections" in body:
                pk["n_segments"] = int(body["n_sections"])
            seg = int(body["seg"])
            idx = [int(i) for i in body["indices"]]
            if any(not 0 <= i < len(st.sources) for i in idx):
                raise HTTPException(400, "Unknown photo number.")
            pk.setdefault("hr_assignments", {})[f"seg{seg}"] = idx
            save_picks(st.folder, pk)
            st.mosaic.pop(seg, None)
        return dict(assignments=pk["hr_assignments"])

    @app.get("/api/stitch/{seg}")
    def stitch_state(seg: int):
        st.need()
        pk = st.picks
        names = st.names()
        idx = pk.get("hr_assignments", {}).get(f"seg{seg}", [])
        photos = []
        for i in idx:
            photos.append(dict(index=i, name=names[i], corners=pk.get("hr_photo_quads", {}).get(names[i])))
        m = st.mosaic.get(seg)
        return dict(seg=seg, photos=photos, params=P.stitch_params_for(pk, seg),
                    output_name=P.hr_default_name(st.folder, st.uwi, pk, seg),
                    joined=None if m is None else [m.shape[1], m.shape[0]],
                    corners=pk.get(f"hr_mosaic_quad_seg{seg}"))

    @app.post("/api/stitch/trim")
    def stitch_trim(body: dict = Body(...)):
        """Save (or clear with null) the trim corners for one close-up photo."""
        st.need()
        name = st.names()[int(body["index"])]
        with st.lock:
            q = st.picks.setdefault("hr_photo_quads", {})
            if body.get("corners") is None:
                q.pop(name, None)
            else:
                q[name] = _quad(body["corners"])
            save_picks(st.folder, st.picks)
            for s in list(st.mosaic):
                st.mosaic.pop(s)
        return dict(ok=True)

    @app.post("/api/stitch/join")
    def stitch_join(body: dict = Body(...)):
        st.need()
        seg = int(body["seg"])
        pk = st.picks
        params = P.stitch_params_for(pk, seg, body.get("params"))
        if body.get("params"):
            pk.setdefault("hr_stitch_params", {})[f"seg{seg}"] = dict(params)
            save_picks(st.folder, pk)
        if not pk.get("hr_assignments", {}).get(f"seg{seg}"):
            raise HTTPException(400, "Choose the close-up photos for this section first.")

        def work(job):
            job.progress(0, 2, "trimming and joining photos")
            st._img_cache.clear(); st.mosaic.clear(); gc.collect()
            m, names = P.stitch_hr_segment(st.folder, pk, seg, st.names(), params)
            st.mosaic[seg] = m
            st._prev_cache.pop(("mosaic", seg), None)
            return dict(seg=seg, size=[m.shape[1], m.shape[0]], photos=len(names))
        return dict(job=runner.submit("Joining photos", work, sync=testing).as_dict())

    @app.get("/api/stitch/{seg}/joined.jpg")
    def joined(seg: int):
        m = st.mosaic.get(seg)
        if m is None:
            raise HTTPException(404, "Join the photos first.")
        k = ("mosaic", seg)
        if k not in st._prev_cache:
            st._prev_cache[k] = _jpeg(_shrink(m, MOSAIC_PREVIEW_LONG)[0])
        return Response(st._prev_cache[k], media_type="image/jpeg", headers={"X-Full-Size": f"{m.shape[1]}x{m.shape[0]}"})

    @app.post("/api/stitch/save")
    def stitch_save(body: dict = Body(...)):
        st.need()
        seg = int(body["seg"])
        m = st.mosaic.get(seg)
        if m is None:
            raise HTTPException(409, "Join the photos first.")
        q = _quad(body.get("corners"))

        def work(job):
            job.progress(0, 1, "saving the joined image")
            with st.lock:
                name, shape, paths = P.finish_hr_segment(st.folder, st.uwi, st.picks, seg, m, q, body.get("output_name"))
                n = int(st.picks.get("n_segments", 3))
                assigned = [i for i in range(1, n + 1) if st.picks.get("hr_assignments", {}).get(f"seg{i}")]
                if all(f"seg{i}" in st.picks.get("hr_seg_names", {}) for i in assigned):
                    st.picks["hr_completed"] = True
                    save_picks(st.folder, st.picks)
            return dict(out_dir=str(st.folder.parent), name=name, size=[shape[1], shape[0]], files=[p.name for p in paths])
        return dict(job=runner.submit("Saving joined image", work, sync=testing).as_dict())

    @app.get("/api/output/{name}")
    def output(name: str):
        st.need()
        p = (st.folder.parent / name).resolve()
        if p.parent != st.folder.parent.resolve() or not p.is_file():
            raise HTTPException(404, "No such output.")
        img = load_any_image(p)
        return Response(_jpeg(_shrink(img, 1600)[0]), media_type="image/jpeg")

    return app

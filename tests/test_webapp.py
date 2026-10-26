# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Larry Syu-Heng Lai
"""API-level tests for the pyRockImageLab app (both tools) on the bundled example data.
The app must write exactly the same files as the GUI-free package replay (``process_folder``)."""
import filecmp
import json
import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import pyrockimagelab as pril
from pyrockimagelab.webapp.routes import create_app

EX = Path(__file__).resolve().parents[1] / "example_data" / "ExampleCore" / "2563-2572"
pytestmark = pytest.mark.skipif(not EX.is_dir(), reason="example data not present")


def _project(tmp, name):
    f = tmp / name / "ExampleCore" / "2563-2572"
    shutil.copytree(EX, f)
    return f.parents[1], f


@pytest.fixture(scope="module")
def reference(tmp_path_factory):
    root, f = _project(tmp_path_factory.mktemp("ref"), "p")
    pril.process_folder(f, "ExampleCore")
    return f.parent


def _client(root):
    c = TestClient(create_app(root=root, testing=True))
    r = c.get("/api/project").json()
    assert r["folders"][0]["photos"] == 7
    assert c.post("/api/open", json={"uwi": "ExampleCore", "folder": "2563-2572"}).status_code == 200
    return c


def _job(r):
    j = r.json()["job"]
    assert j["state"] == "done", j["error"]
    return j["result"]


def test_start_page_and_static(tmp_path):
    root, _ = _project(tmp_path, "p")
    c = TestClient(create_app(root=root, testing=True))
    html = c.get("/").text
    assert "Crop core-box photo" in html and "Stitch close-up photos" in html
    assert c.get("/static/app.js").status_code == 200 and c.get("/shell/static/shell.js").status_code == 200
    assert c.post("/api/project", json={"root": str(tmp_path / "nope")}).status_code == 404


def test_crop_tool_matches_replay(tmp_path, reference):
    root, f = _project(tmp_path, "p")
    c = _client(root)
    st = c.post("/api/crop/box", json={"index": 0}).json()
    assert st["box_photo"] == "ExampleCore_00_box.jpg" and len(st["sections"]) == 3
    assert [s["output_name"] for s in st["sections"]] == [
        "ExampleCore_2563-2566", "ExampleCore_2566-2569", "ExampleCore_2569-2572"]
    assert all(s["corners"] for s in st["sections"])
    assert c.post("/api/crop/preview", json={"corners": st["sections"][0]["corners"]}).headers["content-type"] == "image/jpeg"
    # re-send the same corners as the browser does after a drag
    c.post("/api/crop/sections", json={"sections": [{"seg": 1, "corners": st["sections"][0]["corners"]}]})
    res = _job(c.post("/api/crop/save", json={}))
    assert [s["name"] for s in res["saved"]] == [s["output_name"] for s in st["sections"]]
    for s in res["saved"]:
        for ext in (".png", ".tif"):
            assert filecmp.cmp(f.parent / (s["name"] + ext), reference / (s["name"] + ext), shallow=False)
    assert json.loads((f / "_picks.json").read_text())["lr_completed"] is True


def test_crop_tool_edits(tmp_path):
    root, f = _project(tmp_path, "p")
    c = _client(root)
    c.post("/api/crop/box", json={"index": 0})
    r = c.post("/api/crop/sections", json={"sections": [{"seg": 1, "length_ft": "2.5"}]}).json()
    assert r["sections"][0]["output_name"] == "ExampleCore_2563-2565.5"
    assert r["sections"][1]["output_name"] == "ExampleCore_2566-2569"     # saved names are kept
    r = c.post("/api/crop/sections", json={"sections": [{"seg": 2, "clear": True}]}).json()
    assert r["sections"][1]["corners"] is None
    assert c.post("/api/crop/sections", json={"n_sections": 0}).status_code == 400
    pk = pril.load_picks(f)        # notebooks read the same file
    assert pk["lr_seg_lengths"]["seg1"] == "2.5" and "ExampleCore_00_box.jpg::seg2" not in pk["box_quads"]


def test_stitch_tool_matches_replay(tmp_path, reference):
    root, f = _project(tmp_path, "p")
    c = _client(root)
    st = c.get("/api/stitch/1").json()
    assert [p["index"] for p in st["photos"]] == [1, 2, 3, 4, 5, 6]
    assert st["output_name"] == "ExampleCore_2563-2566_hr" and st["corners"]
    assert c.post("/api/stitch/save", json={"seg": 1}).status_code == 409        # must join first
    j = _job(c.post("/api/stitch/join", json={"seg": 1}))
    assert j["photos"] == 6 and j["size"][1] > 10000
    assert c.get("/api/stitch/1/joined.jpg").status_code == 200
    res = _job(c.post("/api/stitch/save", json={"seg": 1, "corners": st["corners"], "output_name": st["output_name"]}))
    for ext in (".png", ".tif"):
        assert filecmp.cmp(f.parent / (res["name"] + ext), reference / (res["name"] + ext), shallow=False)


def test_stitch_tool_assign_and_trim(tmp_path):
    root, f = _project(tmp_path, "p")
    c = _client(root)
    c.post("/api/stitch/assign", json={"seg": 2, "indices": [3, 4]})
    c.post("/api/stitch/trim", json={"index": 3, "corners": None})
    assert c.post("/api/stitch/assign", json={"seg": 2, "indices": [99]}).status_code == 400
    pk = pril.load_picks(f)
    assert pk["hr_assignments"]["seg2"] == [3, 4] and "ExampleCore_03_detail.jpg" not in pk["hr_photo_quads"]


def test_no_gui_imports():
    import sys
    assert not any(m.startswith(("PyQt", "PySide", "matplotlib.pyplot")) for m in sys.modules)

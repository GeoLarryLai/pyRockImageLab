# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Larry Syu-Heng Lai
"""pyRockImageLab app (``pyrockimagelab-app``): crop core-box photos and stitch close-up
photos in any browser. Served by FastAPI on 127.0.0.1; no Qt needed."""
from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="pyrockimagelab-app", description="pyRockImageLab in the browser")
    ap.add_argument("root", nargs="?", default=None, help="project folder that holds {UWI}/{depth-range}/ photo folders")
    ap.add_argument("--port", type=int, default=None, help="port (default: first free from 8777)")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    a = ap.parse_args(argv)
    from pyrockimagelab.webapp.routes import create_app
    from pyrockimagelab.webapp.shell import serve

    serve(create_app(root=a.root), "pyRockImageLab", port=a.port or 8777, open_browser=not a.no_browser)
    return 0

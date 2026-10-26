# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Larry Syu-Heng Lai
"""server: /shell routes + local launcher (127.0.0.1, free port, browser, clean shutdown)."""
from __future__ import annotations
from pathlib import Path
import os, socket, subprocess, sys, threading, webbrowser

HOST = "127.0.0.1"
STATIC = Path(__file__).parent / "static"


def free_port(preferred: int = 8766) -> int:
    for port in (preferred, 0):
        with socket.socket() as s:
            try:
                s.bind((HOST, port)); return s.getsockname()[1]
            except OSError:
                continue
    raise OSError("no free port")


def open_folder(path: str | Path) -> None:
    p = str(path)
    if sys.platform == "darwin":
        subprocess.Popen(["open", p])
    elif os.name == "nt":
        os.startfile(p)          # noqa: S606 - local folder chosen by the user
    else:
        subprocess.Popen(["xdg-open", p])


def mount_shell(app, runner, guard_of=None) -> None:
    """Add /shell/static, GET /shell/api/jobs/{id}, POST /shell/api/quit and
    POST /shell/api/open_folder ({path}) to a FastAPI ``app``. ``guard_of(path)`` may veto folders."""
    from fastapi import HTTPException, Body
    from fastapi.staticfiles import StaticFiles
    app.mount("/shell/static", StaticFiles(directory=str(STATIC)), name="shell_static")

    @app.get("/shell/api/jobs/{jid}")
    def job(jid: str):
        j = runner.get(jid)
        if j is None:
            raise HTTPException(404, f"unknown job {jid}")
        return j.as_dict()

    @app.post("/shell/api/open_folder")
    def open_folder_route(body: dict = Body(...)):
        p = Path(body.get("path", "")).expanduser()
        if not p.is_dir():
            raise HTTPException(404, "nothing exported yet - the folder is created by the first export")
        if not getattr(app.state, "testing", False):
            open_folder(p)
        return dict(opened=str(p))

    @app.post("/shell/api/quit")
    def quit_():
        srv = getattr(app.state, "server", None)
        if srv is not None:
            srv.should_exit = True
        return dict(quitting=True)


def serve(app, name: str, port: int | None = None, open_browser: bool = True) -> None:
    """Run ``app`` on http://127.0.0.1:<free port> until Ctrl+C or the Quit button."""
    import uvicorn
    port = free_port(port or 8766)
    config = uvicorn.Config(app, host=HOST, port=port, log_level="warning")
    server = uvicorn.Server(config); app.state.server = server
    url = f"http://{HOST}:{port}/"
    print(f"{name}: {url}  (local only; Ctrl+C or the Quit button to stop)", flush=True)
    if open_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    try:
        server.run()
    except KeyboardInterrupt:
        pass
    print(f"{name}: stopped", flush=True)

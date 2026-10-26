# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Larry Syu-Heng Lai
"""jobs: run long tasks in background threads and report ``n / N (xx%)`` progress."""
from __future__ import annotations
import threading, time, traceback, uuid
from dataclasses import dataclass, field


@dataclass
class Job:
    id: str
    title: str
    n: int = 0
    N: int = 1
    message: str = ""
    state: str = "running"          # running | done | error
    result: object = None
    error: str | None = None
    t0: float = field(default_factory=time.time)
    t1: float | None = None

    def progress(self, n: int, N: int | None = None, message: str | None = None) -> None:
        self.n = int(n)
        if N is not None:
            self.N = max(1, int(N))
        if message is not None:
            self.message = message

    def as_dict(self) -> dict:
        pct = 100 if self.state == "done" else int(round(100 * min(self.n, self.N) / self.N))
        return dict(id=self.id, title=self.title, n=self.n, N=self.N, pct=pct, message=self.message,
                    state=self.state, error=self.error, result=self.result,
                    seconds=round((self.t1 or time.time()) - self.t0, 1))


class JobRunner:
    """``submit(title, fn)`` runs ``fn(job)`` in a daemon thread; ``fn`` calls ``job.progress(n, N, msg)``
    and returns a JSON-able result. Exceptions become ``state='error'`` with a one-line message
    (``error_types`` are shown without a traceback)."""

    def __init__(self, keep: int = 50, error_types: tuple = ()):
        self.jobs: dict[str, Job] = {}; self.keep = keep; self.error_types = error_types
        self._lock = threading.Lock()

    def submit(self, title: str, fn, sync: bool = False) -> Job:
        job = Job(uuid.uuid4().hex[:10], title)
        with self._lock:
            self.jobs[job.id] = job
            for k in list(self.jobs)[:-self.keep]:
                if self.jobs[k].state != "running":
                    self.jobs.pop(k)

        def body():
            try:
                job.result = fn(job); job.n = job.N; job.state = "done"
            except Exception as ex:          # reported to the page, never crashes the server
                job.error = f"{type(ex).__name__}: {ex}"; job.state = "error"
                if not isinstance(ex, self.error_types):
                    traceback.print_exc()
            finally:
                job.t1 = time.time()
        if sync:
            body()
        else:
            threading.Thread(target=body, daemon=True, name=f"job-{job.id}").start()
        return job

    def get(self, jid: str) -> Job | None:
        return self.jobs.get(jid)

    def wait(self, jid: str, timeout: float = 600.0) -> Job:
        """Block until the job ends (tests / headless use)."""
        t = time.time()
        while self.jobs[jid].state == "running":
            if time.time() - t > timeout:
                raise TimeoutError(jid)
            time.sleep(0.05)
        return self.jobs[jid]

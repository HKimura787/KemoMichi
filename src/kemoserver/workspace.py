"""The project currently open in this server, plus long-running jobs."""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from contextvars import copy_context
from dataclasses import dataclass, field
from pathlib import Path

from kemocore.sidecar import Sidecar
from kemocore.timelapse.project import TimelapseProject


class Workspace:
    def __init__(self):
        self.lock = threading.RLock()
        self.project: TimelapseProject | None = None
        self.sidecar: Sidecar | None = None

    def open(self, ddb: Path, read_only: bool = False) -> TimelapseProject:
        with self.lock:
            project = TimelapseProject(ddb, read_only=read_only)
            sidecar = Sidecar(project.path, read_only=project.read_only)
            self.close()
            self.project, self.sidecar = project, sidecar
            return project

    def close(self) -> None:
        with self.lock:
            if self.project:
                self.project.close()
            if self.sidecar:
                self.sidecar.close()
            self.project = self.sidecar = None


@dataclass
class Job:
    id: str
    kind: str
    status: str = "running"  # running | done | failed
    done: int = 0
    total: int = 0
    result: dict = field(default_factory=dict)
    error: dict | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "kind": self.kind, "status": self.status, "done": self.done, "total": self.total,
                "result": self.result, "error": self.error}


class Jobs:
    def __init__(self):
        self.jobs: dict[str, Job] = {}
        self.threads: list[threading.Thread] = []
        self.stopping = threading.Event()

    def start(self, kind: str, work) -> Job:
        if self.stopping.is_set():
            raise RuntimeError("KemoMichi is shutting down")
        job = Job(id=uuid.uuid4().hex, kind=kind)
        self.jobs[job.id] = job

        def progress(done: int, total: int) -> None:
            if self.stopping.is_set():
                raise InterruptedError("Project creation cancelled: KemoMichi is shutting down")
            job.done, job.total = done, total

        def run():
            try:
                progress(0, 0)
                job.result = work(progress) or {}
                job.status = "done"
            except Exception as exc:  # reported to the UI
                key = getattr(exc, "key", "error.unexpected")
                job.error = {"error": key, "params": getattr(exc, "params", {}), "detail": str(exc)}
                job.status = "failed"
                if not isinstance(exc, InterruptedError):
                    traceback.print_exc()

        thread = threading.Thread(target=copy_context().run, args=(run,), daemon=True)
        self.threads = [worker for worker in self.threads if worker.is_alive()]
        self.threads.append(thread)
        thread.start()
        return job

    def wait(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        for thread in self.threads:
            thread.join(max(0, deadline - time.monotonic()))
        return not any(thread.is_alive() for thread in self.threads)

    def get(self, job_id: str) -> Job | None:
        return self.jobs.get(job_id)

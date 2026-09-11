"""Local HTTP server and Server-Sent-Events stream for the live evolution UI.

The server is dependency-free (``http.server``) and intended for local use:

* ``GET  /``                         -> single-page UI
* ``GET  /api/catalog``              -> Hamiltonians, templates, protocol presets
* ``POST /api/runs``                 -> start an evolution run (JSON config)
* ``GET  /api/runs/<id>``            -> run status and current leaderboard
* ``GET  /api/runs/<id>/events``     -> SSE stream (replays history, then live)
* ``POST /api/runs/<id>/cancel``     -> cancel a run
* ``GET  /api/runs/<id>/candidates/<cid>`` -> canonical Candidate JSON
* ``GET  /api/runs/<id>/export``     -> JSON export of every evaluated circuit
* ``POST /api/runs/<id>/vqe``        -> start VQE validation on candidate ids
* ``GET  /api/vqe/<id>/events``      -> SSE stream of the VQE job
* ``POST /api/vqe/<id>/cancel``      -> cancel a VQE job
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from typing import Any
import uuid
import webbrowser

from verfeinert._version import __version__
from verfeinert.ansatz_analyzer.metrics.hamiltonians import hamiltonian_catalog
from verfeinert.ansatz_analyzer.metrics.protocol import PAPER_VQE, protocol_summary
from verfeinert.core.io.serialization import to_json_safe

from .engine import LiveEvolutionEngine, LiveRunConfig, template_catalog
from .vqe import VQECancelled, VQEConfig, optimizer_catalog, run_vqe


STATIC_ROOT = Path(__file__).resolve().parent / "static"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
SSE_KEEPALIVE_SECONDS = 15.0


class _EventLog:
    """Thread-safe append-only event log with blocking readers."""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []
        self._condition = threading.Condition()
        self.finished = False

    def append(self, event: Mapping[str, Any]) -> None:
        with self._condition:
            payload = dict(event)
            payload["sequence"] = len(self._events)
            payload.setdefault("timestamp", time.time())
            self._events.append(payload)
            self._condition.notify_all()

    def finish(self) -> None:
        with self._condition:
            self.finished = True
            self._condition.notify_all()

    def snapshot(self) -> list[dict[str, Any]]:
        with self._condition:
            return list(self._events)

    def wait_for(self, index: int, timeout: float) -> list[dict[str, Any]]:
        """Return events from ``index`` onwards, waiting up to ``timeout`` seconds."""
        with self._condition:
            if len(self._events) <= index and not self.finished:
                self._condition.wait(timeout=timeout)
            return self._events[index:]


@dataclass
class _Job:
    job_id: str
    kind: str
    log: _EventLog = field(default_factory=_EventLog)
    cancel_event: threading.Event = field(default_factory=threading.Event)
    status: str = "running"
    result: dict[str, Any] | None = None
    engine: LiveEvolutionEngine | None = None
    config: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    thread: threading.Thread | None = None


class LiveServerState:
    """Registry of evolution runs and VQE jobs."""

    def __init__(self) -> None:
        self._jobs: dict[str, _Job] = {}
        self._lock = threading.Lock()

    def job(self, job_id: str) -> _Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def jobs(self, kind: str | None = None) -> list[_Job]:
        with self._lock:
            return [job for job in self._jobs.values() if kind is None or job.kind == kind]

    def start_run(self, payload: Mapping[str, Any]) -> _Job:
        run_id = f"run-{uuid.uuid4().hex[:8]}"
        config = LiveRunConfig.from_mapping({**dict(payload), "run_id": run_id})
        job = _Job(job_id=run_id, kind="run", config=config.to_dict())
        engine = LiveEvolutionEngine(config, emit=job.log.append, should_cancel=job.cancel_event.is_set)
        job.engine = engine

        def target() -> None:
            try:
                job.result = engine.run()
                job.status = str(job.result.get("status", "completed"))
            except Exception as exc:  # pragma: no cover - engine already reports failures
                job.status = "failed"
                job.log.append({"event_type": "run_failed", "error": str(exc)})
            finally:
                job.log.finish()

        job.thread = threading.Thread(target=target, name=f"verfeinert-{run_id}", daemon=True)
        with self._lock:
            self._jobs[run_id] = job
        job.thread.start()
        return job

    def start_vqe(self, run_job: _Job, payload: Mapping[str, Any]) -> _Job:
        if run_job.engine is None:
            raise ValueError("run has no engine.")
        candidate_ids = [str(item) for item in payload.get("candidate_ids", [])]
        if not candidate_ids:
            top = int(payload.get("top", 3))
            candidate_ids = [row["candidate_id"] for row in run_job.engine.leaderboard(top)]
        documents = []
        for candidate_id in candidate_ids:
            document = run_job.engine.document(candidate_id)
            if document is None:
                raise ValueError(f"unknown candidate {candidate_id!r}.")
            documents.append(document)
        vqe_config = VQEConfig.from_mapping(payload.get("config") or payload)
        hamiltonian = run_job.engine.config.hamiltonian
        vqe_id = f"vqe-{uuid.uuid4().hex[:8]}"
        job = _Job(
            job_id=vqe_id,
            kind="vqe",
            config={"run_id": run_job.job_id, "candidate_ids": candidate_ids, "vqe": vqe_config.to_dict(), "hamiltonian": hamiltonian.to_dict()},
        )

        def target() -> None:
            results = []
            try:
                job.log.append({"event_type": "vqe_batch_started", "candidate_ids": candidate_ids, "config": vqe_config.to_dict(), "hamiltonian": hamiltonian.to_dict()})
                for document in documents:
                    if job.cancel_event.is_set():
                        raise VQECancelled("cancelled")
                    results.append(
                        run_vqe(
                            document,
                            hamiltonian,
                            config=vqe_config,
                            emit=job.log.append,
                            should_cancel=job.cancel_event.is_set,
                        ),
                    )
                job.result = {"status": "completed", "results": results}
                job.status = "completed"
                job.log.append({"event_type": "vqe_batch_completed", "results": [_strip_trajectories(item) for item in results]})
            except VQECancelled:
                job.status = "cancelled"
                job.result = {"status": "cancelled", "results": results}
                job.log.append({"event_type": "vqe_batch_cancelled", "results": [_strip_trajectories(item) for item in results]})
            except Exception as exc:
                job.status = "failed"
                job.result = {"status": "failed", "error": str(exc), "results": results}
                job.log.append({"event_type": "vqe_batch_failed", "error": f"{type(exc).__name__}: {exc}"})
            finally:
                job.log.finish()

        job.thread = threading.Thread(target=target, name=f"verfeinert-{vqe_id}", daemon=True)
        with self._lock:
            self._jobs[vqe_id] = job
        job.thread.start()
        return job


def _strip_trajectories(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(result)
    payload["restarts"] = [
        {key: value for key, value in restart.items() if key not in {"trajectory", "best_parameters"}}
        for restart in payload.get("restarts", [])
    ]
    return payload


def build_catalog() -> dict[str, Any]:
    """Return the static catalog used by the UI."""
    return to_json_safe(
        {
            "version": __version__,
            "hamiltonians": hamiltonian_catalog(),
            "templates": template_catalog(),
            "protocols": {name: protocol_summary(name) for name in ("paper", "fast")},
            "vqe_defaults": dict(PAPER_VQE),
            "vqe_optimizers": optimizer_catalog(),
            "cpu_count": os.cpu_count() or 1,
            "defaults": {
                "n_qubits": 4,
                "n_trials": 3,
                "protocol": "paper",
                "layers": [1],
                "max_generations": 5,
                "elite_size": 4,
                "children_per_parent": 3,
                "workers": max(1, min(4, (os.cpu_count() or 2) - 1)),
                "random_seed": 12345,
            },
        },
    )


class LiveRequestHandler(BaseHTTPRequestHandler):
    """HTTP handler bound to a :class:`LiveServerState` through the server."""

    server_version = f"verfeinert-live/{__version__}"

    @property
    def state(self) -> LiveServerState:
        return self.server.state  # type: ignore[attr-defined]

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - BaseHTTPRequestHandler API
        if getattr(self.server, "verbose", False):  # type: ignore[attr-defined]
            super().log_message(format, *args)

    # ------------------------------------------------------------------ routing
    def do_GET(self) -> None:  # noqa: N802 - http.server API
        path = self.path.split("?", 1)[0]
        parts = [part for part in path.split("/") if part]
        try:
            if not parts or path == "/index.html":
                return self._send_file(STATIC_ROOT / "index.html", "text/html; charset=utf-8")
            if parts == ["api", "catalog"]:
                return self._send_json(build_catalog())
            if parts[:1] == ["api"] and len(parts) >= 3 and parts[1] in {"runs", "vqe"}:
                job = self.state.job(parts[2])
                if job is None:
                    return self._send_json({"error": f"unknown job {parts[2]!r}"}, HTTPStatus.NOT_FOUND)
                if len(parts) == 3:
                    return self._send_json(_job_summary(job))
                if parts[3] == "events":
                    return self._stream_events(job)
                if parts[1] == "runs" and parts[3] == "candidates" and len(parts) == 5:
                    document = job.engine.document(parts[4]) if job.engine else None
                    if document is None:
                        return self._send_json({"error": f"unknown candidate {parts[4]!r}"}, HTTPStatus.NOT_FOUND)
                    return self._send_json(document)
                if parts[1] == "runs" and parts[3] == "export":
                    return self._send_json(_export_run(job))
                if parts[1] == "vqe" and parts[3] == "result":
                    return self._send_json(job.result or {"status": job.status})
            if parts == ["api", "jobs"]:
                return self._send_json({"jobs": [_job_summary(job) for job in self.state.jobs()]})
            if parts[:1] == ["static"] and len(parts) == 2:
                return self._send_file(STATIC_ROOT / parts[1], _content_type(parts[1]))
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except BrokenPipeError:  # pragma: no cover - client disconnected
            pass

    def do_POST(self) -> None:  # noqa: N802 - http.server API
        path = self.path.split("?", 1)[0]
        parts = [part for part in path.split("/") if part]
        try:
            payload = self._read_json()
            if parts == ["api", "runs"]:
                job = self.state.start_run(payload)
                return self._send_json({"run_id": job.job_id, "config": job.config}, HTTPStatus.CREATED)
            if parts[:2] == ["api", "runs"] and len(parts) == 4:
                job = self.state.job(parts[2])
                if job is None:
                    return self._send_json({"error": f"unknown run {parts[2]!r}"}, HTTPStatus.NOT_FOUND)
                if parts[3] == "cancel":
                    job.cancel_event.set()
                    return self._send_json({"run_id": job.job_id, "status": "cancelling"})
                if parts[3] == "vqe":
                    vqe_job = self.state.start_vqe(job, payload)
                    return self._send_json({"vqe_id": vqe_job.job_id, "config": vqe_job.config}, HTTPStatus.CREATED)
            if parts[:2] == ["api", "vqe"] and len(parts) == 4 and parts[3] == "cancel":
                job = self.state.job(parts[2])
                if job is None:
                    return self._send_json({"error": f"unknown vqe job {parts[2]!r}"}, HTTPStatus.NOT_FOUND)
                job.cancel_event.set()
                return self._send_json({"vqe_id": job.job_id, "status": "cancelling"})
            self._send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
        except (ValueError, TypeError, KeyError) as exc:
            self._send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        except BrokenPipeError:  # pragma: no cover - client disconnected
            pass

    # ------------------------------------------------------------------ helpers
    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("request body must be a JSON object.")
        return payload

    def _send_json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(to_json_safe(payload)).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path, content_type: str) -> None:
        if not path.is_file():
            return self._send_json({"error": f"missing static asset {path.name}"}, HTTPStatus.NOT_FOUND)
        body = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _stream_events(self, job: _Job) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        self.close_connection = True
        index = 0
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        for item in query.split("&"):
            if item.startswith("from="):
                try:
                    index = max(0, int(item[5:]))
                except ValueError:
                    index = 0
        last_keepalive = time.time()
        while True:
            events = job.log.wait_for(index, timeout=1.0)
            for event in events:
                self._write_sse(event)
                index = int(event["sequence"]) + 1
            if job.log.finished and index >= len(job.log.snapshot()):
                self.wfile.write(b"event: end\ndata: {}\n\n")
                self.wfile.flush()
                return
            if time.time() - last_keepalive > SSE_KEEPALIVE_SECONDS:
                self.wfile.write(b": keepalive\n\n")
                self.wfile.flush()
                last_keepalive = time.time()

    def _write_sse(self, event: Mapping[str, Any]) -> None:
        data = json.dumps(to_json_safe(event))
        self.wfile.write(f"id: {event['sequence']}\nevent: {event.get('event_type', 'message')}\ndata: {data}\n\n".encode("utf-8"))
        self.wfile.flush()


def _job_summary(job: _Job) -> dict[str, Any]:
    summary: dict[str, Any] = {
        "job_id": job.job_id,
        "kind": job.kind,
        "status": job.status,
        "created_at": job.created_at,
        "event_count": len(job.log.snapshot()),
        "config": job.config,
    }
    if job.engine is not None:
        summary["leaderboard"] = job.engine.leaderboard(25)
        summary["evaluated_count"] = len(job.engine.evaluated())
    if job.kind == "vqe" and job.result is not None:
        summary["results"] = [_strip_trajectories(item) for item in job.result.get("results", [])]
    return summary


def _export_run(job: _Job) -> dict[str, Any]:
    if job.engine is None:
        return {"run_id": job.job_id, "status": job.status}
    engine = job.engine
    return {
        "schema_version": "verfeinert.live_run_export.v1",
        "run_id": job.job_id,
        "status": job.status,
        "config": engine.config.to_dict(),
        "leaderboard": engine.leaderboard(),
        "candidates": {
            candidate_id: {
                "document": state.document,
                "generation": state.generation,
                "parent_id": state.parent_id,
                "label": state.label,
                "mutation": state.mutation,
                "evaluation": state.evaluation,
            }
            for candidate_id, state in engine.candidates.items()
        },
    }


def _content_type(name: str) -> str:
    if name.endswith(".html"):
        return "text/html; charset=utf-8"
    if name.endswith(".js"):
        return "application/javascript; charset=utf-8"
    if name.endswith(".css"):
        return "text/css; charset=utf-8"
    if name.endswith(".svg"):
        return "image/svg+xml"
    return "application/octet-stream"


class LiveServer(ThreadingHTTPServer):
    """Threading HTTP server carrying the shared job registry."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int], *, verbose: bool = False) -> None:
        super().__init__(address, LiveRequestHandler)
        self.state = LiveServerState()
        self.verbose = verbose

    @property
    def url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}/"


def create_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT, *, verbose: bool = False) -> LiveServer:
    """Create (but do not start) the live server."""
    return LiveServer((host, int(port)), verbose=verbose)


def serve(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    *,
    open_browser: bool = True,
    verbose: bool = False,
) -> int:
    """Serve the UI until interrupted; returns a process exit code."""
    server = create_server(host, port, verbose=verbose)
    url = server.url
    print(f"verfeinert live UI: {url}  (Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover - interactive
        print("\nverfeinert live UI stopped.", flush=True)
    finally:
        server.server_close()
    return 0


__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "LiveRequestHandler",
    "LiveServer",
    "LiveServerState",
    "build_catalog",
    "create_server",
    "serve",
]

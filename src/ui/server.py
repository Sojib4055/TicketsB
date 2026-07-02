from __future__ import annotations

from dataclasses import asdict
from functools import partial
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from typing import Any
from urllib.parse import unquote, urlparse

from src.reports.reporting import LATEST_UI_STATE_PATH
from src.trips import load_trip_request, save_trip_request, schedule_for_trip, trip_from_payload


class DashboardServer:
    def __init__(
        self,
        host: str,
        port: int,
        state_path: Path = LATEST_UI_STATE_PATH,
        static_dir: Path | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.state_path = state_path
        self.static_dir = static_dir or Path(__file__).with_name("static")
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"

    def start(self) -> str:
        handler = partial(
            DashboardRequestHandler,
            static_dir=self.static_dir,
            state_path=self.state_path,
        )
        last_error: OSError | None = None
        for candidate_port in range(self.port, self.port + 20):
            try:
                self._server = ThreadingHTTPServer((self.host, candidate_port), handler)
                self.port = candidate_port
                break
            except OSError as exc:
                last_error = exc
        if self._server is None:
            raise RuntimeError("Unable to start dashboard server") from last_error

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self.url

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


class DashboardRequestHandler(SimpleHTTPRequestHandler):
    def __init__(
        self,
        *args: Any,
        static_dir: Path,
        state_path: Path,
        **kwargs: Any,
    ) -> None:
        self.static_dir = static_dir
        self.state_path = state_path
        super().__init__(*args, directory=static_dir.as_posix(), **kwargs)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/state":
            self._send_state()
            return
        if path == "/api/trip":
            self._send_trip()
            return
        if path.startswith("/file/"):
            self._send_artifact(path.removeprefix("/file/"))
            return
        if path == "/":
            self.path = "/index.html"
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/trip":
            self._save_trip()
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        super().end_headers()

    def _send_state(self) -> None:
        if self.state_path.exists():
            payload = self.state_path.read_text(encoding="utf-8")
        else:
            payload = json.dumps({"state": "STARTING", "top_offers": [], "events": []})
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload.encode("utf-8"))

    def _send_trip(self) -> None:
        trip = load_trip_request()
        payload = {"trip": None, "schedule": None}
        if trip is not None:
            payload = {
                "trip": asdict(trip),
                "schedule": asdict(schedule_for_trip(trip)),
            }
        self._send_json(payload)

    def _save_trip(self) -> None:
        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise ValueError("Trip payload must be an object")
            trip = save_trip_request(trip_from_payload(payload))
            self._send_json({"ok": True, "trip": asdict(trip), "schedule": asdict(schedule_for_trip(trip))})
        except Exception as exc:
            self.send_response(HTTPStatus.BAD_REQUEST)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"ok": False, "error": str(exc)}).encode("utf-8"))

    def _send_json(self, payload: dict[str, Any]) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _send_artifact(self, raw_path: str) -> None:
        relative = Path(unquote(raw_path))
        if relative.is_absolute() or ".." in relative.parts:
            self.send_error(HTTPStatus.BAD_REQUEST)
            return

        path = Path.cwd() / relative
        allowed_roots = [
            Path.cwd() / "logs" / "screenshots",
            Path.cwd() / "logs" / "reports",
            Path.cwd() / "logs" / "tickets",
        ]
        try:
            resolved = path.resolve()
            if not any(resolved.is_relative_to(root.resolve()) for root in allowed_roots):
                self.send_error(HTTPStatus.FORBIDDEN)
                return
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        if not resolved.exists() or not resolved.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", _content_type_for(resolved))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(resolved.read_bytes())


def _content_type_for(path: Path) -> str:
    if path.suffix == ".png":
        return "image/png"
    if path.suffix == ".json":
        return "application/json; charset=utf-8"
    if path.suffix == ".txt":
        return "text/plain; charset=utf-8"
    if path.suffix == ".pdf":
        return "application/pdf"
    return "application/octet-stream"

#!/usr/bin/env python3
"""Start the local test-pattern studio: python3 app.py [--port 9191]."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import uuid
import shutil
from urllib.parse import urlsplit, unquote

from engine import ROOT, Settings, build_command, capabilities, probe, render
from assets import UPLOADS, asset, register_upload
from transcode import ConvertSettings, PRESETS, plan, convert
from delivery import generation_profiles

OUTPUTS = ROOT / "outputs"
STATIC = ROOT / "static"


class Studio:
    def __init__(self):
        OUTPUTS.mkdir(exist_ok=True)
        UPLOADS.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        self.process = None
        self.active = None
        self.cancel = threading.Event()
        self.preview_lock = threading.Lock()
        self.health = capabilities()
        for path in sorted(OUTPUTS.glob("*.json"), reverse=True)[:100]:
            try:
                job = json.loads(path.read_text())
                if job.get("status") == "complete" and (OUTPUTS / job["filename"]).is_file():
                    self.jobs[job["id"]] = job
            except (ValueError, KeyError, OSError):
                continue

    def snapshot(self):
        with self.lock:
            return json.loads(json.dumps(sorted(self.jobs.values(), key=lambda j: j["created"], reverse=True)))

    def start(self, settings, kind="pattern"):
        with self.lock:
            if self.active:
                raise ValueError("A render is already running. Wait for it or cancel it first.")
            if not self.health["ready"]:
                raise ValueError(self.health["error"])
            ident = uuid.uuid4().hex
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            if settings.logo_id:
                asset(settings.logo_id, "logo")
            if kind == "pattern":
                build_command(settings, OUTPUTS / "validation.mov")
            conversion = plan(settings) if kind == "conversion" else None
            filename = (f"{stamp}_{settings.profile}_{conversion['width']}x{conversion['height']}_{ident[:6]}.{conversion['container']}" if conversion else
                        f"{stamp}_{settings.pattern}_{settings.resolution}_{settings.rate}_{ident[:6]}.{settings.container}")
            job = {"id": ident, "filename": filename, "settings": asdict(settings), "status": "rendering",
                   "kind": kind, "progress": 0, "created": datetime.now(timezone.utc).isoformat(), "error": None}
            if conversion:
                job["conversion"] = {k: v for k, v in conversion.items() if k not in ("source", "video")}
            self.jobs[ident] = job
            self.active = ident
            self.cancel = threading.Event()
            threading.Thread(target=self.work, args=(job, settings, self.cancel), daemon=True).start()
            return dict(job)

    def work(self, job, settings, cancel):
        output = OUTPUTS / job["filename"]
        partial = output.with_name(output.stem + ".partial" + output.suffix)
        def progress(value):
            with self.lock:
                job["progress"] = value
        def started(proc):
            with self.lock:
                self.process = proc
                if cancel.is_set():
                    proc.terminate()
        try:
            runner = convert if job.get("kind") == "conversion" else render
            runner(settings, partial, progress=progress, started=started, cancel=cancel)
            metadata = probe(partial)
            with self.lock:
                if cancel.is_set():
                    raise InterruptedError("Render cancelled.")
                partial.rename(output)
                job.update(status="complete", progress=1, bytes=output.stat().st_size, metadata=metadata)
                (OUTPUTS / (output.stem + ".json")).write_text(json.dumps(job, indent=2))
        except InterruptedError:
            with self.lock:
                job.update(status="cancelled", error=None)
        except Exception as exc:
            with self.lock:
                job.update(status="failed", error=str(exc))
        finally:
            partial.unlink(missing_ok=True)
            partial.with_suffix(".log").unlink(missing_ok=True)
            with self.lock:
                self.process = None
                self.active = None

    def stop(self, ident):
        with self.lock:
            if ident != self.active:
                return
            self.cancel.set()
            proc = self.process
            if proc and proc.poll() is None:
                proc.terminate()
                def force_stop():
                    if proc.poll() is None:
                        proc.kill()
                timer = threading.Timer(3, force_stop)
                timer.daemon = True
                timer.start()


class Handler(BaseHTTPRequestHandler):
    server_version = "PatternStudio/1.0"

    def log_message(self, fmt, *args):
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(fmt, *args)

    def local_request(self):
        allowed = {f"localhost:{self.server.server_port}", f"127.0.0.1:{self.server.server_port}"}
        if self.headers.get("Host") not in allowed:
            self.send_error(403, "Local access only")
            return False
        origin = self.headers.get("Origin")
        if origin and origin not in {"http://" + host for host in allowed}:
            self.send_error(403, "Cross-origin requests are not allowed")
            return False
        return True

    def reply(self, value, status=200, content_type="application/json"):
        data = json.dumps(value).encode() if content_type == "application/json" else value
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_GET(self):
        if not self.local_request():
            return
        path = urlsplit(self.path).path
        if path == "/api/status":
            self.reply({"health": self.server.studio.health, "jobs": self.server.studio.snapshot(), "output_dir": str(OUTPUTS),
                        "generation_profiles": generation_profiles(),
                        "conversion_presets": {k: {"label":v[0], "container":v[4], "pixel_format":v[3]} for k,v in PRESETS.items()}})
        elif re.fullmatch(r"/logo/[0-9a-f]{32}", path):
            try:
                file, _ = asset(path.rsplit("/", 1)[-1], "logo")
                self.reply(file.read_bytes(), content_type="image/png")
            except ValueError:
                self.send_error(404)
        elif path.startswith("/download/"):
            self.download(path.rsplit("/", 1)[-1])
        elif path in ("/", "/style.css", "/app.js", "/convert.js"):
            filename = STATIC / ("index.html" if path == "/" else path[1:])
            self.reply(filename.read_bytes(), content_type=mimetypes.guess_type(str(filename))[0] + "; charset=utf-8")
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.local_request():
            return
        try:
            path = urlsplit(self.path).path
            if path in ("/api/upload/logo", "/api/upload/video"):
                self.upload(path.rsplit("/", 1)[-1])
                return
            if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                raise ValueError("Expected application/json.")
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            path = urlsplit(self.path).path
            if path == "/api/render":
                self.reply(self.server.studio.start(Settings.parse(data)), 202)
            elif path == "/api/convert":
                self.reply(self.server.studio.start(ConvertSettings.parse(data), "conversion"), 202)
            elif path == "/api/conversion-plan":
                result = plan(ConvertSettings.parse(data))
                self.reply({k: v for k, v in result.items() if k not in ("source", "video")})
            elif path == "/api/preview":
                settings = Settings.parse(data)
                if not self.server.studio.preview_lock.acquire(blocking=False):
                    self.reply({"error": "A preview is already being generated. Try again shortly."}, 409)
                    return
                try:
                    with tempfile.TemporaryDirectory(prefix="pattern-preview-") as temp:
                        output = Path(temp) / "preview.png"
                        command, overlay = build_command(settings, output, preview=True)
                        result = subprocess.run(command, input=overlay.frame(0) if overlay else b"", capture_output=True, timeout=30)
                        if result.returncode:
                            raise RuntimeError(result.stderr.decode(errors="replace")[-3000:])
                        self.reply(output.read_bytes(), content_type="image/png")
                finally:
                    self.server.studio.preview_lock.release()
            elif re.fullmatch(r"/api/cancel/[0-9a-f]{32}", path):
                self.server.studio.stop(path.rsplit("/", 1)[-1])
                self.reply({"ok": True})
            else:
                self.send_error(404)
        except (ValueError, TypeError) as exc:
            self.reply({"error": str(exc)}, 400)
        except Exception as exc:
            self.reply({"error": str(exc)}, 500)

    def upload(self, kind):
        if self.headers.get("Content-Type") != "application/octet-stream":
            raise ValueError("Upload the original file bytes as application/octet-stream.")
        length = int(self.headers.get("Content-Length", "0"))
        limit = 25 * 1024**2 if kind == "logo" else 20 * 1024**3
        if not 0 < length <= limit:
            self.close_connection = True
            raise ValueError("Logo uploads are limited to 25 MB; videos to 20 GB.")
        if shutil.disk_usage(UPLOADS).free < length + 512 * 1024**2:
            self.close_connection = True
            raise ValueError("There is not enough free disk space for this upload.")
        ident = uuid.uuid4().hex
        path = UPLOADS / f"{ident}.upload"
        name = Path(unquote(self.headers.get("X-Filename", "upload"))).name
        try:
            self.connection.settimeout(120)
            with path.open("xb") as out:
                remaining = length
                while remaining:
                    chunk = self.rfile.read(min(1024**2, remaining))
                    if not chunk:
                        raise ValueError("Upload was interrupted.")
                    out.write(chunk)
                    remaining -= len(chunk)
            item = register_upload(path, ident, kind, name)
            self.reply(item, 201)
        except Exception:
            for suffix in (".upload", ".media", ".png", ".json"):
                (UPLOADS / (ident + suffix)).unlink(missing_ok=True)
            raise

    def download(self, ident):
        with self.server.studio.lock:
            job = self.server.studio.jobs.get(ident)
            if not job or job["status"] != "complete":
                self.send_error(404)
                return
            path = OUTPUTS / job["filename"]
        if not path.is_file():
            self.send_error(404)
            return
        size = path.stat().st_size
        start, end = 0, size - 1
        byte_range = self.headers.get("Range")
        if byte_range:
            match = re.fullmatch(r"bytes=(\d+)-(\d*)", byte_range)
            if not match or int(match[1]) >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
            start = int(match[1])
            end = min(int(match[2]) if match[2] else size - 1, size - 1)
            if end < start:
                self.send_error(416)
                return
        self.send_response(206 if byte_range else 200)
        self.send_header("Content-Type", {".mov": "video/quicktime", ".ts": "video/mp2t"}.get(path.suffix, "video/mp4"))
        self.send_header("Content-Length", str(end - start + 1))
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
        if byte_range:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        try:
            with path.open("rb") as file:
                file.seek(start)
                remaining = end - start + 1
                while remaining:
                    chunk = file.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
        except (BrokenPipeError, ConnectionResetError):
            pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=9191)
    args = parser.parse_args()
    studio = Studio()
    try:
        server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError as exc:
        raise SystemExit(f"Could not start on port {args.port}: {exc}")
    server.studio = studio
    print(f"\nPattern Studio → http://localhost:{args.port}\nFiles → {OUTPUTS}\nPress Control-C to stop.\n", flush=True)
    if not studio.health["ready"]:
        print(studio.health["error"], flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if studio.active:
            studio.stop(studio.active)
        server.server_close()


if __name__ == "__main__":
    main()

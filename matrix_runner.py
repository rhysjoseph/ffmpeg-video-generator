"""Manage a single, isolated qualification run and retain its most recent report."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading

from engine import DURATIONS, RESOLUTIONS, ROOT
from verification import tool_versions
from datetime import datetime, timezone


class MatrixRunner:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.report = self.directory / "matrix.json"
        self.lock = threading.Lock()
        self.process = None

    def start(self, resolution, duration=None):
        if resolution != "all" and resolution not in RESOLUTIONS:
            raise ValueError("Choose a supported output resolution.")
        if duration is not None and (type(duration) is not int or duration not in DURATIONS):
            raise ValueError("Choose a supported test duration.")
        with self.lock:
            if self.process and self.process.poll() is None:
                raise ValueError("A profile matrix is already running.")
            self.directory.mkdir(parents=True, exist_ok=True)
            environment = {"started_utc": datetime.now(timezone.utc).isoformat(), "tools": tool_versions(),
                           "resolution": resolution}
            if duration is None:
                environment["frames_per_fixture"] = 8
            else:
                environment["duration_seconds"] = duration
            (self.directory / "environment.json").write_text(json.dumps(environment))
            self.report.unlink(missing_ok=True)
            args = [sys.executable, str(ROOT / "profile_matrix.py"), "--report", str(self.report)]
            if resolution != "all":
                args += ["--resolution", resolution]
            if duration is not None:
                args += ["--duration", str(duration)]
            with (self.directory / "matrix.log").open("w") as log:
                self.process = subprocess.Popen(args, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)

    def snapshot(self, full=False):
        with self.lock:
            code = self.process.poll() if self.process else None
            running = self.process is not None and code is None
            cases = json.loads(self.report.read_text()) if self.report.exists() else []
            if running:
                state = "running"
            elif self.process:
                state = "finished" if code == 0 else "failed"
            elif cases:
                state = "saved results"
            else:
                state = "idle"
            result = {"state":state, "tested":sum(c["status"] != "unsupported" for c in cases),
                      "failed":sum(c["status"] == "failed" for c in cases),
                      "review":sum(c["status"] == "review" for c in cases),
                      "unsupported":sum(c["status"] == "unsupported" for c in cases)}
            if cases:
                last = cases[-1]
                result["latest"] = " · ".join(last[k] for k in ("mode","profile","resolution","status"))
            if full:
                environment = self.directory / "environment.json"
                if environment.exists():
                    result["environment"] = json.loads(environment.read_text())
                result["cases"] = cases
                logfile = self.directory / "matrix.log"
                if state == "failed" and logfile.exists():
                    result["diagnostic"] = logfile.read_text(errors="replace")[-2000:]
            return result

    def close(self):
        with self.lock:
            if self.process and self.process.poll() is None:
                os.killpg(self.process.pid, signal.SIGTERM)
                self.process.wait()

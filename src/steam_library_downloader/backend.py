from __future__ import annotations

import json
import os
import queue
import re
import shutil
import signal
import subprocess
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Callable, Iterable

import qrcode

APP_NAME = "Steam Library Downloader"
APP_ID = "dev.alastorkaneki.steamlibrarydownloader"
VERSION = "0.1.0"
MARKER_QR = "@@STEAM_QR@@"
MARKER_ACCOUNT = "@@STEAM_ACCOUNT@@"
MARKER_LIBRARY = "@@OWNED_APPS@@"
MARKER_BACKEND = "@@SLD_BACKEND@@"
ANSI_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")

BG = "#050506"
PANEL = "#0d0d10"
PANEL_2 = "#15151a"
TEXT = "#f5f3ff"
MUTED = "#aaa5b7"
PURPLE = "#9c6cff"
RED = "#ff4868"
GREEN = "#71f7a7"
BORDER = "#2a2633"


def app_data_dir() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "steam-library-downloader"


def app_config_dir() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "steam-library-downloader"


def runtime_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def backend_candidates() -> Iterable[Path]:
    override = os.environ.get("STEAM_DL_BACKEND")
    if override:
        yield Path(override).expanduser()
    root = runtime_root()
    yield root / "libexec" / "depotdownloader" / "DepotDownloader"
    yield root / "libexec" / "DepotDownloader"
    yield app_data_dir() / "backend" / "DepotDownloader"
    found = shutil.which("DepotDownloader")
    if found:
        yield Path(found)


def find_backend() -> Path | None:
    for candidate in backend_candidates():
        try:
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return candidate
        except OSError:
            continue
    return None


def backend_state_root() -> Path:
    return app_data_dir() / "backend-home"


def backend_environment() -> dict[str, str]:
    state_root = backend_state_root()
    state_root.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HOME"] = str(state_root)
    env["XDG_DATA_HOME"] = str(state_root / ".local" / "share")
    env["XDG_CONFIG_HOME"] = str(state_root / ".config")
    env["DOTNET_CLI_HOME"] = str(state_root / ".dotnet")
    env["DOTNET_NOLOGO"] = "1"
    env["TERM"] = "dumb"
    env["STEAM_LIBRARY_DOWNLOADER_GUI"] = "1"
    return env


def verify_backend(backend: Path) -> tuple[bool, str]:
    try:
        result = subprocess.run(
            [str(backend), "--sld-version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
            env=backend_environment(),
            cwd=backend_state_root(),
            check=False,
        )
    except Exception as exc:
        return False, str(exc)
    output = ANSI_RE.sub("", result.stdout or "")
    if result.returncode == 0 and f"{MARKER_BACKEND}1" in output:
        return True, "1"
    return False, output.strip() or f"exit code {result.returncode}"


@dataclass(slots=True)
class OwnedApp:
    app_id: int
    name: str
    app_type: str

    @classmethod
    def from_json(cls, item: dict) -> "OwnedApp":
        app_id = item.get("AppId", item.get("appId", item.get("appid", 0)))
        return cls(
            int(app_id),
            str(item.get("Name", item.get("name", f"App {app_id}"))),
            str(item.get("Type", item.get("type", ""))),
        )


class BackendRunner:
    def __init__(self, emit: Callable[[str, object], None]) -> None:
        self.emit = emit
        self.process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def stop(self) -> None:
        with self._lock:
            process = self.process
        if not process or process.poll() is not None:
            return
        try:
            process.send_signal(signal.SIGINT)
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    def start(self, args: list[str], purpose: str) -> None:
        if self.running:
            raise RuntimeError("A Steam operation is already running")
        backend = find_backend()
        if backend is None:
            raise FileNotFoundError(
                "The patched DepotDownloader backend was not found. Install the AppImage build "
                "or set STEAM_DL_BACKEND to the bundled backend executable."
            )

        state_root = backend_state_root()
        env = backend_environment()

        command = [str(backend), *args]
        self.emit("log", "$ " + " ".join(_shell_quote(part) for part in command))
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            cwd=state_root,
        )
        with self._lock:
            self.process = process
        threading.Thread(target=self._read, args=(process, purpose), daemon=True).start()

    def _read(self, process: subprocess.Popen[str], purpose: str) -> None:
        assert process.stdout is not None
        try:
            for raw in process.stdout:
                line = ANSI_RE.sub("", raw.rstrip("\r\n"))
                if line.startswith(MARKER_QR):
                    self.emit("qr", line[len(MARKER_QR):].strip())
                elif line.startswith(MARKER_ACCOUNT):
                    self.emit("account", line[len(MARKER_ACCOUNT):].strip())
                elif line.startswith(MARKER_LIBRARY):
                    payload = line[len(MARKER_LIBRARY):].strip()
                    try:
                        data = json.loads(payload)
                        self.emit("library", [OwnedApp.from_json(x) for x in data])
                    except Exception as exc:
                        self.emit("error", f"Could not decode the Steam library: {exc}")
                elif line.startswith(MARKER_BACKEND):
                    self.emit("backend", line[len(MARKER_BACKEND):].strip())
                elif line:
                    self.emit("log", line)
                    percent = _extract_percent(line)
                    if percent is not None:
                        self.emit("progress", percent)
        finally:
            code = process.wait()
            with self._lock:
                if self.process is process:
                    self.process = None
            self.emit("done", (purpose, code))


def _extract_percent(line: str) -> float | None:
    match = re.search(r"(?<!\d)(100(?:\.0+)?|\d{1,2}(?:\.\d+)?)%", line)
    if not match:
        return None
    try:
        return max(0.0, min(100.0, float(match.group(1))))
    except ValueError:
        return None


def _shell_quote(value: str) -> str:
    if re.fullmatch(r"[A-Za-z0-9_./:@%+=,-]+", value):
        return value
    return "'" + value.replace("'", "'\\''") + "'"



def _safe_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\x00-\x1f]", "-", value).strip(" .")
    return cleaned[:120] or "Steam App"

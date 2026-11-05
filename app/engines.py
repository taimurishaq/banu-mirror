"""Find UxPlay / scrcpy, build their command lines, and read their output."""

import os
import re
import shutil
import sys
from pathlib import Path

APP_NAME = "Banu mirror"
MSYS2_BIN = Path(r"C:\msys64\ucrt64\bin")

# Status values shown in the window
STOPPED = "Stopped"
STARTING = "Starting…"
WAITING_IPAD = "Waiting for iPad"
CONNECTING = "Connecting…"
MIRRORING = "Mirroring"

# scrcpy settings for each Quality choice
QUALITY_PRESETS = {
    "Fast": ["--max-size=1024", "--video-bit-rate=4M", "--max-fps=60"],
    "Balanced": ["--max-size=1600", "--video-bit-rate=8M", "--max-fps=60"],
    "Sharp": ["--video-bit-rate=16M", "--max-fps=60"],
}

VIDEO_ENGINES = {
    "Direct3D 12 (recommended)": "d3d12videosink",
    "Direct3D 11 (older PCs)": "d3d11videosink",
}


def app_dir():
    """Folder of Banu mirror.exe when packaged, or the project folder in development."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def data_dir():
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


# ---------------------------------------------------------------- UxPlay

def find_uxplay():
    """Return (path_to_uxplay.exe, environment) or (None, reason)."""
    bundled = app_dir() / "engine" / "uxplay" / "uxplay.exe"
    if bundled.is_file():
        root = bundled.parent
        env = os.environ.copy()
        env["PATH"] = str(root) + os.pathsep + env.get("PATH", "")
        # Use only the GStreamer plugins shipped with the app.
        env["GST_PLUGIN_SYSTEM_PATH_1_0"] = str(root / "lib" / "gstreamer-1.0")
        env["GST_PLUGIN_SCANNER_1_0"] = str(root / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe")
        env["GST_REGISTRY_1_0"] = str(data_dir() / "gstreamer-registry.bin")
        for key in ("GST_PLUGIN_PATH", "GST_PLUGIN_PATH_1_0", "GST_PLUGIN_SYSTEM_PATH"):
            env.pop(key, None)
        return bundled, env

    dev = app_dir() / "uxplay" / "build" / "uxplay.exe"
    if dev.is_file():
        if not MSYS2_BIN.is_dir():
            return None, "uxplay.exe was found, but MSYS2 (C:\\msys64) is missing, so it can't run."
        env = os.environ.copy()
        env["PATH"] = str(MSYS2_BIN) + os.pathsep + env.get("PATH", "")
        return dev, env

    return None, (
        "uxplay.exe was not found.\n\nExpected it in:\n  %s\nor\n  %s"
        % (bundled, dev)
    )


def uxplay_args(exe, name, video_engine, fullscreen):
    sink = VIDEO_ENGINES.get(video_engine, "d3d12videosink")
    if fullscreen and sink == "d3d12videosink":
        # -fs alone would disable the Alt+Enter toggle, so set both options ourselves.
        vs = "d3d12videosink fullscreen=TRUE fullscreen-on-alt-enter=TRUE"
    elif fullscreen:
        vs = "d3d11videosink fullscreen-toggle-mode=alt-enter+property fullscreen=TRUE"
    else:
        vs = sink  # UxPlay adds the Alt+Enter toggle by itself
    return [str(exe), "-n", name, "-nh", "-p", "-vs", vs, "-as", "wasapisink"]


class UxPlayWatcher:
    """Turns UxPlay's console messages into a status."""

    RE_REQUEST = re.compile(r"connection request from (.+?) \((.+?)\)")

    def __init__(self):
        self.status = STARTING
        self.device = ""
        self.sockets = 0
        self.ready = False

    def feed(self, line):
        """Read one output line; return a new status or None if unchanged."""
        old = (self.status, self.device)
        if "Initialized server socket" in line:
            self.ready = True
            self.status = WAITING_IPAD
        elif "Accepted IPv4 client" in line or "Accepted IPv6 client" in line:
            self.sockets += 1
        elif "Connection closed on socket" in line:
            self.sockets = max(0, self.sockets - 1)
            if self.sockets == 0 and self.status in (CONNECTING, MIRRORING):
                self.status, self.device = WAITING_IPAD, ""
        elif "lost connection with client" in line:
            self.sockets = 0
            self.status, self.device = WAITING_IPAD, ""
        else:
            m = self.RE_REQUEST.search(line)
            if m:
                self.device = m.group(1).strip()
                if self.status != MIRRORING:
                    self.status = CONNECTING
            elif ("raop_rtp_mirror starting mirroring" in line
                  or "Begin streaming to GStreamer video pipeline" in line
                  or "raop_rtp starting audio" in line):
                self.status = MIRRORING
        return self.status if (self.status, self.device) != old else None

    def label(self):
        if self.status == MIRRORING and self.device:
            return "Mirroring %s" % self.device
        if self.status == CONNECTING and self.device:
            return "Connecting to %s…" % self.device
        return self.status


def explain_uxplay_problem(lines):
    text = "\n".join(lines)
    if "avdec_aac is missing" in text or "avdec_alac is missing" in text:
        return "The audio decoder (GStreamer libav plugin) is missing."
    if "gst_parse_launch failed" in text or "no element" in text.lower():
        return "A GStreamer video/audio part is missing or failed to load."
    if "ddress already in use" in text or "bind" in text.lower():
        return "Another program is already using UxPlay's network ports. Is UxPlay already running?"
    return ""


# ---------------------------------------------------------------- scrcpy / adb

def find_scrcpy():
    """Return (scrcpy.exe, adb.exe) or (None, reason)."""
    bundled = app_dir() / "engine" / "scrcpy" / "scrcpy.exe"
    candidates = [bundled]
    which = shutil.which("scrcpy")
    if which:
        candidates.append(Path(which))
    winget = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    if winget.is_dir():
        candidates.extend(sorted(winget.glob("Genymobile.scrcpy*/*/scrcpy.exe"), reverse=True))
    for exe in candidates:
        if exe.is_file():
            adb = exe.parent / "adb.exe"
            if adb.is_file():
                return exe, adb
    return None, "scrcpy.exe (and adb.exe) were not found.\n\nExpected them in:\n  %s" % bundled.parent


def scrcpy_args(exe, serial, quality, fullscreen, device_label):
    args = [str(exe), "--serial=%s" % serial]
    args += QUALITY_PRESETS.get(quality, QUALITY_PRESETS["Balanced"])
    args.append("--window-title=%s - %s" % (APP_NAME, device_label or "Android"))
    if fullscreen:
        args.append("--fullscreen")
    return args


class ScrcpyWatcher:
    RE_DEVICE = re.compile(r"INFO: Device: \[[^\]]*\]\s*(.+?)\s*(\(Android|$)")

    def __init__(self):
        self.status = CONNECTING
        self.device = ""

    def feed(self, line):
        m = self.RE_DEVICE.search(line)
        if m:
            self.device = m.group(1).strip()
            if self.device.lower().startswith("google "):
                self.device = self.device[7:]
            self.status = MIRRORING
            return self.status
        return None

    def label(self):
        if self.status == MIRRORING and self.device:
            return "Mirroring %s" % self.device
        return self.status

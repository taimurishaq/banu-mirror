"""Build the Banu mirror installer (dist/BanuMirror-Setup-<version>.exe).

Run from PowerShell in the project folder:
    py scripts\\package.py

Needs (on the build PC only):
  - MSYS2 at C:\\msys64 with the UxPlay packages (scripts/setup-dev.sh)
  - scrcpy from winget (Genymobile.scrcpy)
  - PyInstaller:  py -m pip install --user pyinstaller
  - Inno Setup 6: winget install JRSoftware.InnoSetup

Steps:
  1. Build UxPlay in portable mode (no -march=native), so it runs on any 64-bit PC.
  2. Copy uxplay.exe, the GStreamer plugins it uses, and every MSYS2 DLL they need.
  3. Copy scrcpy (with adb) for Android phones.
  4. Turn the Python app into "Banu mirror.exe" with PyInstaller.
  5. Wrap it all into one setup .exe with Inno Setup.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

APP_VERSION = "1.0.0"

ROOT = Path(__file__).resolve().parent.parent
MSYS2 = Path(r"C:\msys64")
UCRT64 = MSYS2 / "ucrt64"
OBJDUMP = UCRT64 / "bin" / "objdump.exe"

BUILD = ROOT / "build"
STAGE = BUILD / "stage" / "Banu mirror"  # becomes the installed folder
DIST = ROOT / "dist"

# GStreamer plugins UxPlay needs for screen mirroring + audio on Windows.
# decodebin picks the best H.264 decoder: hardware (D3D12/D3D11/NVIDIA/Intel/AMD)
# when the PC has one, otherwise the software decoder from libav.
GST_PLUGINS = [
    "coreelements", "app", "typefindfunctions", "playback", "autodetect",
    "videoparsersbad", "audioparsers", "libav",
    "videoconvertscale", "videofilter",
    "d3d11", "d3d12", "nvcodec", "qsv", "amfcodec", "mediafoundation",
    "audioconvert", "audioresample", "volume", "level",
    "wasapi", "wasapi2", "directsound",
]


def step(text):
    print("\n== %s ==" % text, flush=True)


def run(args, **kwargs):
    print("  >", " ".join(str(a) for a in args), flush=True)
    subprocess.run([str(a) for a in args], check=True, **kwargs)


def msys_bash(command, cwd):
    """Run a command in the MSYS2 UCRT64 environment, starting in cwd."""
    env = os.environ.copy()
    env.update(MSYSTEM="UCRT64", CHERE_INVOKING="1")
    run([MSYS2 / "usr" / "bin" / "bash.exe", "-lc", command], cwd=cwd, env=env)


# ---------------------------------------------------------------- 1. UxPlay

def build_uxplay():
    step("1/5 Building UxPlay (portable)")
    out = BUILD / "uxplay-portable"  # build/ is git-ignored; the uxplay folder stays untouched
    shutil.rmtree(out, ignore_errors=True)
    out.mkdir(parents=True)
    msys_bash("cmake -G Ninja -DNO_MARCH_NATIVE=ON ../../uxplay && ninja", cwd=out)
    exe = out / "uxplay.exe"
    if not exe.is_file():
        sys.exit("uxplay.exe was not built.")
    return exe


# ---------------------------------------------------------------- 2. engine

def dll_imports(path):
    out = subprocess.run([str(OBJDUMP), "-p", str(path)], capture_output=True, text=True, check=True).stdout
    return re.findall(r"DLL Name:\s*(\S+)", out)


def copy_with_dependencies(files, dest_bin):
    """Copy every MSYS2 DLL the given files need into dest_bin (recursively).

    DLLs that are not in MSYS2 (Windows' own, like kernel32.dll) are skipped.
    Returns the set of MSYS2 files that were used, for the license list.
    """
    msys_bin = UCRT64 / "bin"
    seen, used = set(), set(files)
    todo = list(files)
    while todo:
        for name in dll_imports(todo.pop()):
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            src = msys_bin / name
            if src.is_file():
                shutil.copy2(src, dest_bin / name)
                used.add(src)
                todo.append(src)
    return used


def copy_licenses(msys_files, dest):
    """Copy the license folders of the MSYS2 packages we ship."""
    # pacman only understands MSYS2-style paths, e.g. /ucrt64/bin/libglib-2.0-0.dll
    paths = ["/" + Path(f).relative_to(MSYS2).as_posix()
             for f in msys_files if Path(f).is_relative_to(MSYS2)]
    result = subprocess.run(
        [str(MSYS2 / "usr" / "bin" / "pacman.exe"), "-Qqo"] + paths,
        capture_output=True, text=True,
    )
    packages = sorted(set(result.stdout.split()))
    if not packages:
        sys.exit("Could not look up MSYS2 package names:\n" + result.stderr[-2000:])
    dest.mkdir(parents=True, exist_ok=True)
    lic_root = UCRT64 / "share" / "licenses"
    names = []
    for pkg in packages:
        short = pkg.replace("mingw-w64-ucrt-x86_64-", "")
        src = lic_root / short
        if src.is_dir():
            shutil.copytree(src, dest / short, dirs_exist_ok=True)
        names.append(short)
    (dest / "PACKAGES.txt").write_text(
        "Libraries from MSYS2 (https://www.msys2.org) shipped with Banu mirror:\n\n"
        + "\n".join(names) + "\n",
        encoding="utf-8",
    )


def stage_uxplay(uxplay_exe):
    step("2/5 Collecting UxPlay + GStreamer")
    dest = STAGE / "engine" / "uxplay"
    plugins_dest = dest / "lib" / "gstreamer-1.0"
    scanner_dest = dest / "libexec" / "gstreamer-1.0"
    for d in (plugins_dest, scanner_dest):
        d.mkdir(parents=True, exist_ok=True)

    shutil.copy2(uxplay_exe, dest / "uxplay.exe")
    roots = [dest / "uxplay.exe"]

    for name in GST_PLUGINS:
        src = UCRT64 / "lib" / "gstreamer-1.0" / ("libgst%s.dll" % name)
        if not src.is_file():
            sys.exit("GStreamer plugin missing in MSYS2: %s" % src)
        shutil.copy2(src, plugins_dest / src.name)
        roots.append(src)

    scanner = UCRT64 / "libexec" / "gstreamer-1.0" / "gst-plugin-scanner.exe"
    shutil.copy2(scanner, scanner_dest / scanner.name)
    roots.append(scanner)

    used = copy_with_dependencies(roots, dest)
    dlls = len(list(dest.glob("*.dll")))
    print("  %d plugins, %d DLLs" % (len(GST_PLUGINS), dlls))

    lic = STAGE / "licenses"
    lic.mkdir(parents=True, exist_ok=True)
    shutil.copy2(ROOT / "uxplay" / "LICENSE", lic / "UxPlay-LICENSE.txt")
    copy_licenses(used, lic / "msys2")


# ---------------------------------------------------------------- 3. scrcpy

def find_scrcpy_dir():
    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    found = sorted(packages.glob("Genymobile.scrcpy*/*/scrcpy.exe"), reverse=True)
    if not found:
        sys.exit("scrcpy not found. Install it with: winget install Genymobile.scrcpy")
    return found[0].parent


def stage_scrcpy():
    step("3/5 Collecting scrcpy")
    src = find_scrcpy_dir()
    dest = STAGE / "engine" / "scrcpy"
    skip = {"open_a_terminal_here.bat", "scrcpy-noconsole.vbs"}
    shutil.copytree(src, dest, ignore=lambda d, names: [n for n in names if n in skip])
    shutil.copy2(src / "LICENSE.txt", STAGE / "licenses" / "scrcpy-LICENSE.txt")
    print("  from", src)


# ---------------------------------------------------------------- 4. app

def build_app():
    step("4/5 Building Banu mirror.exe (PyInstaller)")
    work = BUILD / "pyinstaller"
    run([
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--clean", "--windowed",
        "--name", "Banu mirror",
        "--paths", ROOT / "app",
        "--distpath", BUILD / "pyinstaller-dist",
        "--workpath", work,
        "--specpath", work,
        ROOT / "app" / "main.py",
    ])
    built = BUILD / "pyinstaller-dist" / "Banu mirror"
    shutil.copytree(built, STAGE, dirs_exist_ok=True)
    shutil.copy2(ROOT / "README.md", STAGE / "README.md")


# ---------------------------------------------------------------- 5. installer

def find_iscc():
    for base in (os.environ.get("LOCALAPPDATA", "") + r"\Programs",
                 os.environ.get("ProgramFiles(x86)", ""), os.environ.get("ProgramFiles", "")):
        exe = Path(base) / "Inno Setup 6" / "ISCC.exe"
        if exe.is_file():
            return exe
    sys.exit("Inno Setup not found. Install it with: winget install JRSoftware.InnoSetup")


def build_installer():
    step("5/5 Building the installer (Inno Setup)")
    DIST.mkdir(exist_ok=True)
    run([
        find_iscc(), "/Q",
        "/DAppVersion=%s" % APP_VERSION,
        "/DStageDir=%s" % STAGE,
        "/DOutDir=%s" % DIST,
        ROOT / "installer" / "BanuMirror.iss",
    ])
    out = DIST / ("BanuMirror-Setup-%s.exe" % APP_VERSION)
    print("\nDone: %s (%.0f MB)" % (out, out.stat().st_size / 1e6))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--no-installer", action="store_true",
                        help="stop after building the app folder (build/stage/Banu mirror)")
    args = parser.parse_args()

    shutil.rmtree(STAGE, ignore_errors=True)
    STAGE.mkdir(parents=True)
    uxplay_exe = build_uxplay()
    stage_uxplay(uxplay_exe)
    stage_scrcpy()
    build_app()
    if args.no_installer:
        print("\nApp folder ready: %s" % STAGE)
        return
    build_installer()


if __name__ == "__main__":
    main()

#!/usr/bin/env bash
# Installs the MSYS2 packages UxPlay needs and builds uxplay.exe.
#
# Run it from the "MSYS2 UCRT64" terminal, inside the project folder:
#   bash scripts/setup-dev.sh             # build tuned for this PC (fastest)
#   bash scripts/setup-dev.sh --portable  # build that runs on any 64-bit PC
#
# If the terminal closes during step 1, MSYS2 updated itself.
# Open "MSYS2 UCRT64" again and re-run the same command.
set -euo pipefail

if [ "${MSYSTEM:-}" != "UCRT64" ]; then
  echo "Please run this from the 'MSYS2 UCRT64' terminal (current: ${MSYSTEM:-not MSYS2})." >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CMAKE_ARGS=()
if [ "${1:-}" = "--portable" ]; then
  CMAKE_ARGS+=(-DNO_MARCH_NATIVE=ON)
fi

echo "== 1/3 Updating MSYS2 =="
pacman -Syu --noconfirm --disable-download-timeout

echo "== 2/3 Installing build tools, libraries and GStreamer =="
pacman -S --needed --noconfirm --disable-download-timeout \
  mingw-w64-ucrt-x86_64-gcc \
  mingw-w64-ucrt-x86_64-cmake \
  mingw-w64-ucrt-x86_64-ninja \
  mingw-w64-ucrt-x86_64-libplist \
  mingw-w64-ucrt-x86_64-gstreamer \
  mingw-w64-ucrt-x86_64-gst-plugins-base \
  mingw-w64-ucrt-x86_64-gst-libav \
  mingw-w64-ucrt-x86_64-gst-plugins-good \
  mingw-w64-ucrt-x86_64-gst-plugins-bad

echo "== 3/3 Building UxPlay =="
if [ ! -f "$ROOT/uxplay/CMakeLists.txt" ]; then
  echo "The uxplay folder is empty. In Git Bash or PowerShell run:" >&2
  echo "  git submodule update --init" >&2
  exit 1
fi
# Start from a clean build folder so the --portable choice always applies.
rm -rf "$ROOT/uxplay/build"
mkdir -p "$ROOT/uxplay/build"
cd "$ROOT/uxplay/build"
cmake "${CMAKE_ARGS[@]}" ..
ninja

echo
./uxplay.exe -v
echo "Built: $ROOT/uxplay/build/uxplay.exe"

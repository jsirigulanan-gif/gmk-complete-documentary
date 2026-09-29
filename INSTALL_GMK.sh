#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

echo "============================================================"
echo " GMK P.T. Operator — Build 044 — CachyOS / Arch Linux Setup"
echo "============================================================"
echo

if ! command -v pacman >/dev/null 2>&1; then
  echo "[ERROR] pacman was not found. This installer is for CachyOS/Arch-based systems."
  echo "You can still run START_GMK.sh after manually installing Python 3.10+, Tk, ffmpeg, yt-dlp, jsonschema and PyYAML."
  exit 2
fi

PACKAGES=(python tk ffmpeg python-jsonschema python-yaml python-pytest)
MISSING=()
for pkg in "${PACKAGES[@]}"; do
  if ! pacman -Q "$pkg" >/dev/null 2>&1; then
    MISSING+=("$pkg")
  fi
done
if ! command -v yt-dlp >/dev/null 2>&1 && ! pacman -Q yt-dlp >/dev/null 2>&1; then
  MISSING+=(yt-dlp)
fi

if ((${#MISSING[@]})); then
  echo "[1/4] Installing required CachyOS/Arch packages: ${MISSING[*]}"
  sudo pacman -S --needed "${MISSING[@]}"
else
  echo "[1/4] Required system packages are already installed."
fi

echo "[2/4] Checking Python runtime and GMK dependencies..."
python - <<'PY'
import sys
if sys.version_info < (3,10):
    raise SystemExit("Python 3.10+ is required")
from importlib.metadata import version
import jsonschema, yaml, tkinter
print("Python", sys.version.split()[0], "OK")
print("jsonschema", version("jsonschema"))
print("PyYAML", yaml.__version__ if hasattr(yaml, '__version__') else "OK")
print("Tkinter OK")
PY
if ! command -v ffprobe >/dev/null 2>&1; then
  echo "[ERROR] ffprobe is still unavailable after installing ffmpeg."
  exit 2
fi
ffprobe -version | head -n 1

chmod +x START_GMK.sh INSTALL_GMK.sh

echo "[3/4] Installing user launcher..."
mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
LAUNCHER="$HOME/.local/bin/gmk-pt-operator"
cat > "$LAUNCHER" <<LAUNCH
#!/usr/bin/env bash
exec "${ROOT}/START_GMK.sh" "\$@"
LAUNCH
chmod +x "$LAUNCHER"

DESKTOP="$HOME/.local/share/applications/gmk-pt-operator.desktop"
cat > "$DESKTOP" <<DESKTOPFILE
[Desktop Entry]
Type=Application
Name=GMK P.T. Operator
Comment=Gamer Must Know P.T. production operator
Exec=${LAUNCHER}
Path=${ROOT}
Terminal=false
Categories=AudioVideo;Utility;
StartupNotify=true
DESKTOPFILE
chmod 644 "$DESKTOP"
if command -v update-desktop-database >/dev/null 2>&1; then
  update-desktop-database "$HOME/.local/share/applications" >/dev/null 2>&1 || true
fi

echo "[4/4] Running GMK system check..."
python -m gmk_operator --system-check

echo
echo "Setup complete."
echo "Open GMK from your app launcher: GMK P.T. Operator"
echo "or run: ./START_GMK.sh"

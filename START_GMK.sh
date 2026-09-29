#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON=""
if command -v python >/dev/null 2>&1; then
  PYTHON="$(command -v python)"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
fi

if [[ -z "$PYTHON" ]]; then
  echo "[GMK] Python 3 was not found."
  echo "On CachyOS run: ./INSTALL_GMK.sh"
  exit 2
fi

if ! "$PYTHON" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 2)' >/dev/null 2>&1; then
  echo "[GMK] Python 3.10 or newer is required."
  exit 2
fi

exec "$PYTHON" -m gmk_operator "$@"

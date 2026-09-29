from __future__ import annotations

from pathlib import Path
import os
import shutil


class MediaToolNotFound(RuntimeError):
    pass


def _existing(path: str | Path | None) -> str | None:
    if not path:
        return None
    p = Path(path).expanduser()
    if p.is_file():
        return str(p.resolve())
    return None


def _windows_candidates(tool: str) -> list[Path]:
    exe = f"{tool}.exe"
    env = os.environ
    roots: list[Path] = []
    for key in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA", "USERPROFILE"):
        raw = env.get(key)
        if raw:
            roots.append(Path(raw))
    out: list[Path] = []
    for root in roots:
        out.extend([
            root / "Shutter Encoder" / "Library" / exe,
            root / "Shutter Encoder" / exe,
            root / "ffmpeg" / "bin" / exe,
            root / "FFmpeg" / "bin" / exe,
        ])
    local = env.get("LOCALAPPDATA")
    if local:
        out.append(Path(local) / "Microsoft" / "WinGet" / "Links" / exe)
    chocolatey = env.get("ChocolateyInstall")
    if chocolatey:
        out.append(Path(chocolatey) / "bin" / exe)
    return out


def resolve_media_tool(tool: str) -> str:
    """Resolve ffprobe/ffmpeg without changing pipeline semantics.

    Resolution order:
    1) explicit GMK_<TOOL> environment variable,
    2) normal PATH,
    3) a small set of common Windows install locations.

    The GUI stores the user's selected executable and exports GMK_FFPROBE for
    the current process. Core runtimes call this helper, so GUI and CLI use the
    same executable and validation rules.
    """
    key = f"GMK_{tool.upper()}"
    explicit = _existing(os.environ.get(key))
    if explicit:
        return explicit
    found = shutil.which(tool)
    if found:
        return found
    if os.name == "nt":
        for candidate in _windows_candidates(tool):
            existing = _existing(candidate)
            if existing:
                return existing
    raise MediaToolNotFound(f"{tool} not found. Set {key} to the executable path or add {tool} to PATH.")


def resolve_ffprobe() -> str:
    return resolve_media_tool("ffprobe")


def resolve_ffmpeg() -> str:
    return resolve_media_tool("ffmpeg")

# GMK Schema v1 — Build 041 Changelog

## Focus
CachyOS / Arch Linux native operator release.

## Added
- `INSTALL_GMK.sh` using native `pacman` packages instead of editable pip installation.
- CachyOS-native `START_GMK.sh` using the repository source directly.
- Desktop application launcher installation under `~/.local/share/applications/`.
- User launcher under `~/.local/bin/gmk-pt-operator`.
- `QUICK_START_CACHYOS_TH.md`.
- Build 041 platform/launcher regression tests.

## Preserved
- Windows `.cmd` launcher support remains available.
- No Core Object, Project State, Gate ID or schema contract change.
- No media bytes added to the P.T. package.
- Authoritative media/source-lock/Gate behavior is unchanged.

## Dependency policy
On CachyOS/Arch the release uses native packages: `python`, `tk`, `ffmpeg`, `python-jsonschema`, and `python-yaml`. It does not require `pip install -e .`.

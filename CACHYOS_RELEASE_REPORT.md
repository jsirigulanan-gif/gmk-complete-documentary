# GMK Build 041 — CachyOS Native Release Report

Build 041 adapts the operator-facing release to the user's actual operating system: CachyOS, an Arch Linux-based distribution.

The Linux path runs GMK directly from the extracted package with the system Python and dependencies managed through pacman. `ffprobe` is supplied by the Arch/CachyOS `ffmpeg` package. Tkinter is supplied by `tk`.

The installer creates a user-local desktop entry and launcher. It does not modify the authoritative P.T. workspace except through the normal GMK operator actions after explicit user confirmation.

No schema or pipeline semantics changed in this build.

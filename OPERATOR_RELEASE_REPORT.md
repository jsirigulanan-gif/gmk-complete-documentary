# GMK P.T. Operator Release Candidate — Build 040

## Purpose
Build 040 turns the hardened GMK runtime into a practical operator-facing program without creating a second source of truth. The desktop app calls the same `PilotReadinessRuntime`, `PilotMediaProcessRuntime`, `AuditRuntime`, source-lock validator and durable workspace used by the CLI.

## Windows flow
1. Extract the Build 040 ZIP to a writable folder.
2. Run `INSTALL_GMK.cmd` once.
3. Run `START_GMK.cmd` whenever GMK is needed.
4. Use the Lisa and TGA tabs to select the two authorized videos and complete the human inspection fields.
5. Refresh readiness. Fix any blocker until the status is `READY_TO_EXECUTE`.
6. Run Preflight.
7. Use Execute Media only after reviewing the readiness/preflight result.

## Runtime dependencies
- Python 3.10+
- Tkinter (included in normal python.org Windows installers)
- `jsonschema` and `PyYAML` (installed into the local `.venv` by the setup script)
- `ffprobe`

The System tab can store an explicit `ffprobe.exe` path when it is not available on PATH. This setting is operator-local and not authoritative project state.

## Current real P.T. state
```text
Project State       ASSET_RECON
Manifest Version    104
Cataloged Assets    8 / 10
Verified Segments   8
Pending Videos      LISA_X_DIRECT_VERIFIED, TGA_VIDEO
Readiness           BLOCKED_MEDIA
```

## Boundary
The release candidate is ready to operate the real P.T. media boundary, but the package intentionally contains no Lisa/TGA media. The real project cannot advance until those exact files are supplied and inspected.

## Validation
- Build 040 operator tests: **4/4 PASS**.
- Affected backend regressions: **14 PASS** (Build 018/019/023/030).
- Quick Audit: **22 PASS / 0 FAIL / 0 TIMEOUT / 1 WARN**.
- Operator headless smoke: **PASS**.
- Schema/contracts: **80 PASS / unchanged**.

The single audit warning is the documented legacy Build 001 changelog gap.

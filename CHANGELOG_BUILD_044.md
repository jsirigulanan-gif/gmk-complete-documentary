# Build 044 — Reliable frame sampling and Git checkout audits

## Changes

- Stop frame sampling before the source duration, including the millisecond-rounded
  timestamp actually sent to ffmpeg. A 10-second source sampled every 5 seconds
  now yields frames at 0 and 5 seconds instead of failing at EOF.
- Preserve an explicitly requested end timestamp when it is before source EOF.
- Reject non-finite sampling intervals rather than silently returning partial evidence.
- Accept Git checkouts, worktrees, and release archives in the layout audit; keep
  the source-root runtime-manifest check.
- Add Build 044 regression tests to QUICK audits and include Build 043 in FULL
  partitions, which previously stopped at Build 042.
- Reconcile current README/build metadata and continuation instructions. Historical
  Build 040–043 reports remain preserved.
- Narrow the local input ignore rule to retain the handoff's packaged pilot
  research document in Git.

## Boundaries

No frozen Schema v1 contracts or pilot workspace data changed. This build does not
claim a completed real documentary, live acquisition, or validated Ollama inference.
The P.T. pilot remains at ASSET_RECON with two source-locked media inputs pending.

See `BUILD_044_VALIDATION.md` for measured results.

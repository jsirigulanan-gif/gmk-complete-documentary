# Build 044 validation and import record

Verified on CachyOS, Python 3.14, with local ffmpeg/ffprobe, on 2026-09-29.
Dependencies were installed in a separate virtualenv outside the repository.

## Import provenance

- Source: `GMK_Complete_Documentary_Maker_Build_043_WORK_HANDOFF.zip`
- ZIP SHA-256: `2addd98b26743894d87544aad886120224f259ff61cf2ad3488d2690e2963cf2`
- Initial source import: Git tag `build-043`, commit `ef746a0`.
- Source contents are at the repository root, without the ZIP's enclosing folder.
- Restore executable permissions for `INSTALL_GMK.sh` and `START_GMK.sh`.
- Build 044 narrows the top-level `inputs/` ignore rule so the handoff's packaged
  P.T. research DOCX is included in Git. The original import's ignore rule omitted
  that document; it is present in the current build with its original bytes.
- Generated `pilot/PT_OPERATOR_OUTPUT` snapshots remain excluded by the supplied
  ignore rules; authoritative pilot workspace files are preserved.
- Commit author is Codex; this does not assert human authorship of the supplied code.

## Measured results

| Verification | Result |
| --- | --- |
| Imported Build 042 + 043 footage tests | 32 passed, 75.02 seconds |
| Build 044 + 043 + Build 042 frame regression | 14 passed, 8.21 seconds |
| QUICK audit | 26 PASS, 0 FAIL, 0 TIMEOUT, 1 legacy WARN |
| Schema validator | 80 registered contracts validated |
| Pilot doctor | `ok: true` |
| Pilot status | `ASSET_RECON`, manifest version 104 |
| Pilot workspace, schema, contract bytes vs ZIP | Unchanged |

QUICK includes compileall, schema/semantic/gate/layout checks, Build 035 audit,
Build 040/041 operator tests, Build 042 fast footage tests, and Build 044 tests.
Detailed output: `BUILD_044_QUICK_AUDIT.json`.

The one warning is the historical missing `CHANGELOG_BUILD_001.md`; Build 001
history exists in README. The initial audit exposed stale README labels, the
obsolete no-Git requirement, and lost executable bits after ZIP extraction;
these were resolved before the final audit.

## Regression reproduced

Before the fix, a real generated 10-second video sampled at 0, 5, and 10 seconds
raised `FrameSamplingError` at `t=10.0`. After the fix, default, exact-duration,
and beyond-duration end ranges all produce JPEG evidence at 0 and 5 seconds.
An explicit end of 5 seconds still includes that valid frame. Invalid non-finite
intervals fail before extraction.

## Limits and next work

No real source media was acquired and no live Ollama model was invoked. Fixtures
test frame extraction and runtime wiring, not real-model semantic accuracy. No
full historical suite or completed real documentary is claimed.

The source-locked P.T. inputs `LISA_X_DIRECT_VERIFIED` and `TGA_VIDEO` remain
pending. `status` reports a possible next state, but does not prove that those
media bytes exist; do not treat it as a completed acquisition or human approval.

The next product gap is an operator/CLI entry point for the existing automatic
production runtime and explicitly configured vision provider. See
`GPT_WORK_HANDOFF.md`. Current continuation is in Codex; no separate GPT Work
job has been created.

# Build 045 — Clarify the Operator's purpose and P.T. pilot boundary

The former top-level “Lisa camera hack” and “TGA stage statement” tabs looked like
required product inputs. They are source-locked media slots for the bundled P.T.
example only. They now sit under **โครงการตัวอย่าง P.T.**, alongside that project's
readiness dashboard.

The Operator opens on a Thai overview explaining the documentary production goal,
what this GUI can do today, why the two P.T. videos are needed, and that the GUI
does not yet create an arbitrary new project or finish a film in one click. The
footage search tab says it produces a research report from P.T. Narration Beats.
The dashboard now uses clearer Thai labels and a plain next step when source
media is missing. The Quick Audit dialog reads the correct warning-count field.
Background task failures now show their real error instead of raising a second
Tk callback error when the exception variable has left scope.

The P.T. source locks, workspace state, frozen Schema v1 contracts, human approval
boundaries, and media execution behavior did not change. The pilot remains
`ASSET_RECON` / `BLOCKED_MEDIA` until the exact Lisa and TGA videos are supplied
and inspected.

Locally generated footage research reports stay in `pilot/PT_FOOTAGE_RESEARCH/`
and are excluded from Git; the existing local report is preserved.

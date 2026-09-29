# Build 047 validation

The complete user lifecycle and acceptance definition are recorded in PRODUCT_REQUIREMENTS.md. This build implements the first project-authority integration, not the finished documentary product.

- Targeted tests: 39 passed across production binding, Drive catalog/intake/voice, Operator compatibility and distribution checks.
- QUICK audit: 29 PASS, 0 FAIL, 0 TIMEOUT, 1 existing Build 001 changelog warning.
- New project creation produces a persistent core workspace; status/next-action reads use the existing StateEngine manifest.
- Repeated source import/migration retains one exact source registration and does not advance to Research Audited merely because an imported document says VERIFIED.
- Tests reject missing/corrupt production records, a different project's workspace even with matching titles/object IDs, altered research input bytes, and a core revision between checkpoint preparation and upload.
- Deterministic checkpoint tests restore the core records and verify the manifest hash. Storage success or an injected legacy completion label cannot override core state or claim a completed documentary.
- The existing real local project was connected, its original research registered, and its state read back as RESEARCH_INTAKE with SATISFY_GATE_REQUIREMENTS as the next action. A 50,566-byte production checkpoint was registered locally. Private source/project files remain outside Git.
- Live desktop verification displayed the connected research-intake status and hid the legacy migration button for an already connected project.

No real Drive upload or private TTS call was attempted for this build. The existing Drive quota problem and pending private-text TTS consent remain unresolved. General evidence/claim ingestion, canonical script/beat/media/voice adapters, integrated editing/rendering, and final Drive delivery verification still need implementation and real end-to-end acceptance.

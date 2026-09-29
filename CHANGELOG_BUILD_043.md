# Build 043 — Visual Semantic Footage Matcher

Build 043 closes the principal visual-only footage gap left by Build 042.

## Added

- `gmk_footage.visual_matcher` runtime.
- Pixel-grounded frame description provider interface.
- Local Ollama vision provider using explicit `GMK_VISION_MODEL` and localhost HTTP only.
- Deterministic frame-to-Narration-Beat semantic scoring.
- Visual timestamp nomination with evidence manifests and frame paths.
- Automatic production fallback order:
  1. transcript/caption timestamp evidence,
  2. visual-semantic evidence from sampled frames,
  3. unresolved — never metadata-only guessing.
- `BeatResearchResult` now carries its full `BeatSearchIntent` when produced by the live research runtime; old positional construction remains compatible.
- Auto-production manifests record `selection_mode` and visual-match evidence.

## Safety / provenance behavior retained

- YouTube remains first source priority, followed by web/archive video, real stills/documents, and AI last.
- Rights remain non-blocking workflow metadata and default to `PENDING_PERMISSION` unless verified elsewhere.
- Attribution/source URL/segment timestamps remain preserved into production manifests and credits.
- No cookies, credentials, DRM bypass, authentication bypass, or access-control bypass are added.
- Metadata relevance alone is not accepted as proof that a visual is present.

## Vision provider behavior

The default code does not silently install or guess a heavyweight local vision model. To use the included local provider, set `GMK_VISION_MODEL` to an Ollama vision-capable model available on the operator machine. If no vision matcher is configured, visual-only beats remain unresolved rather than being guessed.

## Validation

- Build 043 new tests: 2 PASS.
- Build 042 footage suite: 30 PASS when run in partitions (aggregate invocation still exceeds the surrounding harness wall-clock limit, consistent with Build 042 notes).
- Build 040 + 041 operator compatibility: 8 PASS.
- `compileall`: PASS.

## Schema

No Schema v1 contract or Gate ID changed. Frozen contract count remains 80.

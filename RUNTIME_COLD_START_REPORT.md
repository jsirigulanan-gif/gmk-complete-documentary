# GMK Runtime / Cold Start Report — Build 006

## Purpose
Build 006 closes the persistence boundary left intentionally open in Build 005. A fresh process can now reconstruct a GMK project from persisted state without relying on conversation memory.

## Persistent authority chain
```text
CURRENT_MANIFEST.json
  -> exact Project Manifest version + hash
  -> exact Core Registry snapshots
  -> exact Artifact Registry snapshot
  -> immutable Core Object records
  -> immutable Artifact records
  -> audit/gate history sidecars
  -> dependency recomputation
  -> Gate/Blocker/Next Legal Action derivation
```

## Artifact Registry
Artifact identity is now stable and versioned independently from Core Objects.

```text
artifact_id
artifact_type
HEAD version
  -> version locator
     -> logical URI
     -> ArtifactRef payload SHA-256
     -> complete record SHA-256
     -> schema ID
```

Creating Artifact v2 advances Artifact HEAD only. Existing exact ArtifactRefs remain pinned to their original version and checksum.

## Project Manifest
The runtime compiler creates a manifest conforming to `gmk://schema/v1/project-manifest` and pins:
- ACTIVE Project exact version
- Schema `1.0.0`
- `GMK_POLICY_BUNDLE` exact version + file SHA-256
- all standard Core Registry snapshots
- Artifact Registry snapshot
- current Narrative Spine / Voiceover / TTS / Master Voice when present
- current Design DNA when present
- latest Checkpoint pointer when present
- current RELEASED Release when present
- persisted Gate summaries with concrete evidence
- current derived blockers
- project state + entered-at timestamp

The Manifest remains a resume pointer, not a database.

## Cold Start fail-closed checks
Cold Start rejects reconstruction on:
- current Manifest checksum mismatch
- Project Manifest JSON Schema violation
- Schema version incompatibility
- Policy Bundle version/hash mismatch
- missing standard Registry pointer
- Registry snapshot version/hash mismatch
- object identity mismatch
- object full-record checksum mismatch
- artifact identity mismatch
- artifact full-record checksum mismatch
- managed artifact payload checksum mismatch
- unresolved current Manifest refs
- `current_release` not resolving to a `RELEASED` Release
- dependency projection integrity failure
- Registry drift during reconstruction

## Exact state preservation
Regression tests prove that a persisted project with:
```text
PROJECT HEAD   = v2
PROJECT ACTIVE = v1
Artifact HEAD  = v2
```
reopens with those exact values. Cold Start never promotes HEAD automatically.

## Test result
```text
validate_schemas.py            PASS — 68 schemas/contracts
validate_semantics.py          PASS
state_engine_smoke.py          PASS
dependency_engine_smoke.py     PASS
gate_engine_smoke.py           PASS
runtime_cold_start_smoke.py    PASS
pytest                          71 passed
```

# Build 042 Partitioned Validation

Build 042 validation is recorded partition-by-partition because the monolithic QUICK audit harness repeatedly exceeded its aggregate wall-clock limit in this container even though the same constituent checks passed when isolated.

## Core invariants

- Schema/contracts: **80 PASS**
- Semantic smoke: **PASS**
- Gate smoke: **PASS**
- Repository layout audit: **PASS**
- compileall: **PASS**
- STATIC Audit: **16 PASS / 0 FAIL / 0 TIMEOUT / 1 WARN**
  - WARN: legacy Build 001 has no standalone changelog.

## Build 042 footage partitions

- Query planner: 3 PASS
- YouTube discovery provider: 3 PASS
- Metadata ranker: 2 PASS
- YouTube subtitle fetcher: 2 PASS
- Transcript/timestamp finder: 2 PASS
- Source priority policy: 2 PASS
- Web source providers: 3 PASS
- Fallback research: 2 PASS
- Footage research orchestrator: 1 PASS
- Distribution/CLI/GUI integration: 4 PASS
- YouTube acquire + segment extraction: 1 PASS
- Frame sampler: 1 PASS
- Web/still material acquisition: 2 PASS
- Rough-cut assembly: 1 PASS
- Automatic YouTube production path: 1 PASS

**Build 042 total: 30 PASS (partitioned).**

## Compatibility partitions

- Build 035 audit tests: 3 PASS
- Build 040 operator tests: 4 PASS
- Build 041 CachyOS tests: 4 PASS

## Aggregate audit note

The monolithic QUICK audit invocation timed out in the surrounding execution environment. It is **not recorded as PASS**. The final package relies on the individually executed, passing constituent checks above.

## P.T. workspace non-mutation

- `pilot/PT_WORKSPACE/CURRENT_MANIFEST.json` SHA-256 remained:
  `c3bbb10d540ea0a5a9a621b80852322982113764f2277710eeb6530c66acc6a7`
- Manifest pointer remains v104.
- Real pilot remains `ASSET_RECON`.

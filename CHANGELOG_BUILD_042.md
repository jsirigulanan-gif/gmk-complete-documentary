# Build 042 — Complete Documentary Maker Footage Core

Build 042 restores the original GMK product requirement: footage research and automatic rough-cut production are core documentary-making capabilities, not an external manual step.

## Material priority

1. YouTube
2. Web / archive video
3. Real stills / documents
4. AI-generated visual only as last resort after configured search-again rounds

## Added

- `gmk_footage` runtime package.
- Deterministic Narration Beat → multi-family YouTube query planner.
- Read-only `yt-dlp` YouTube metadata discovery.
- Explainable candidate ranking.
- Caption / auto-caption retrieval and VTT timestamp nomination.
- Local-media frame sampling and inspection manifests for visual-only footage.
- Selected YouTube acquisition with provenance and `PENDING_PERMISSION` tracking.
- Exact segment extraction with ffmpeg and checksum receipts.
- Automatic rough-cut timeline assembly, optional voice-track replacement, MP4 export, timeline manifest and credits sidecar.
- Internet Archive / NASA video research providers.
- Wikimedia Commons / NASA still-image research providers.
- Web/archive video acquisition and still-image-to-video rendering.
- Source priority controller and fallback research runtime.
- CachyOS installer now includes `yt-dlp`.
- Operator GUI gains a Documentary Maker footage-research tab.
- CLI: `footage-plan` and `footage-research`.

## Rights workflow

Rights are tracked as production metadata (`PENDING_PERMISSION` by default) and attribution is preserved. Rights status does not masquerade as verified permission. The acquisition layer does not use cookies, credentials, DRM bypass, or access-control bypass flags.

## Boundary retained

Build 042 does not pretend that metadata or transcript relevance proves visual relevance. Clips without sufficient caption/timestamp evidence remain subject to frame/visual inspection. Automatic visual-semantic scoring is the next missing core capability.

## Schema

No Schema v1 contract or Gate ID is changed. Status remains `FROZEN_WITH_ERRATA_024_025_029_033` and contract count remains 80.

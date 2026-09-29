# GMK — Complete Documentary Production System

This is the user's product requirement. It governs the final product and takes precedence over historical descriptions of the P.T. pilot or claims that a component runtime is "complete". Implementation status is recorded separately; this document does not claim these capabilities already exist.

## Product outcome

GMK must carry one documentary project from a topic or brief to a completed, reviewed, exported documentary. Research assistance, script generation, shot-list generation, footage search, downloading, and editor/render integration are connected capabilities within that project.

The product must support this complete lifecycle:

**Topic / Brief → Research → Evidence / Claims → Narrative → Script → Narration Beats → Visual Requirements → Footage Research → Footage Selection → Footage Acquisition → Scene Planning → Shot Planning → Timeline / Edit Assembly → Voice / TTS → Design / Graphics → Render → Full-film QA → Delivery → Export → Completed Documentary.**

## Inputs and storage

- Accept a new topic/brief or an existing research/script document. The user's established source is Gemini output saved as `[LEMiNO Script]` Google Docs on Google Drive.
- Importing an existing script may supply draft material for several stages. It does not automatically verify its claims, sources, timings, or visual coverage.
- Keep every downloaded source-footage file in that project's Google Drive storage, including downloaded candidates subsequently rejected. Keep source URLs, attribution, selection decisions, scene usage, and acquired-byte hashes.
- Store script versions, voice, music, graphics, editing data, QA reports, final exports, and resumable production metadata under the same project. Use local working/cache files for processing on Linux.
- An offline/quota/authentication failure must preserve local work and show pending delivery. It must not be mistaken for a completed upload or completed documentary.
- Prefer free voice services/tools as requested by the user; never silently switch to a paid service. External-service permissions and credentials remain distinct from model capability.

## Required stage outcomes

| Stage | Required result and checks |
| --- | --- |
| Topic / Brief | Topic, audience, language, editorial question, target length, scope, and delivery settings are available to subsequent stages. Missing required values are visible. |
| Research | Research records preserve sources and capture dates, relevant excerpts, leads, gaps, and contradictions. |
| Evidence / Claims | Claims point to specific evidence. Support, uncertainty, conflicting evidence, and unsupported statements remain explicit. A source's own VERIFIED label is not independent verification. |
| Narrative | A coherent opening, central question, progression, turning points, and ending grounded in the supported material. |
| Script | An editable, versioned narration script linked to claims and narrative sections. |
| Narration Beats | Stable beat identities, spoken text, narrative purpose, and claim references. |
| Visual Requirements | What the audience must see for each beat, distinguishing evidence footage, illustrative material, graphics, and reconstruction. |
| Footage Research | Search queries, candidate sources, metadata, caption/frame observations, and coverage gaps. Metadata similarity alone does not establish a visual match. |
| Footage Selection | Selected candidate segments and the reason/evidence for their relevance to beats; unresolved coverage remains visible. |
| Footage Acquisition | Actual usable media bytes, duration/stream checks, provenance, checksums, and a Drive upload receipt or explicit pending/failed storage state. |
| Scene Planning | Ordered scenes with purpose, beats, available media, and transitions. |
| Shot Planning | Exact source clips/in-out points, composition, graphics/audio requirements, and scene/beat associations. |
| Timeline / Edit Assembly | A real editable timeline and preview assembled from project media; original source timecodes remain traceable. |
| Voice / TTS | Real narration audio, pronunciation review, and measured timing bound to the exact script version; interrupted generation resumes from valid cached scenes. |
| Design / Graphics | Consistent typography, graphics, maps/charts/titles where appropriate, music and sound design, and clearly distinguished illustrative material. |
| Render | A playable video rendered from the current approved timeline, narration, media, and design versions. |
| Full-film QA | Technical checks plus editorial review of facts, visual relevance, pacing, narration/picture synchronization, pronunciation, music balance, and credits over the whole film. |
| Delivery | An agreed delivery package containing the approved master, required accompanying files, and export profile. |
| Export | Actual export files with verified checksums and confirmed arrival in the project's Drive destination. Export can encode/package or copy a valid master, but must not substitute an untested placeholder. |
| Completed Documentary | The exact delivered/exported master passed full-film QA and its delivery has been verified. No unresolved blocking issue, stale required dependency, placeholder media, failed transfer, or missing required audio remains. |

## One coherent project

Use the existing StateEngine, versioned references, dependency invalidation, and production/release gates as the authoritative production record. The Drive asset catalog provides storage receipts; it must not be a second authority for production completion. The desktop UI and CLI expose the same project and operations.

Every stage consumes explicit upstream versions and emits real artifacts with provenance. Editing a claim, script, selected clip, narration, or timeline invalidates affected downstream results. Retry/resume reuses only artifacts whose dependencies still match. The UI must display the current task, actual outputs, blockers, and the next valid action, without requiring users to construct internal JSON by hand.

The lifecycle is not a one-pass chain: the initial timeline is a draft. Measured voice timing feeds back into the timeline/shot durations before render. Visual findings can trigger script/narrative revisions. A revised master requires new QA. Existing frozen runtime ordering can govern final locks while draft planning happens earlier; it must not silently erase a user-required stage.

## Acceptance

First demonstrate one real 2–3 minute documentary using a selected Drive document, sourced footage, Thai narration, music, editable preview, full-film checks, and a playable export verified on Drive. Repeat from a saved project after interruption and after a script edit to show resume and downstream invalidation. Then demonstrate the same workflow on a 30-minute project on the user's hardware or an explicitly chosen render worker.

Component tests, screenshots, populated manifests, synthetic media tests, and state labels are necessary development evidence but do not substitute for this real acceptance run. Public uploading/publishing is separate from exporting to the user's private project storage.

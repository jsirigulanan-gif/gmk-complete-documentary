# GMK P.T. Rough Narrative Report — Build 013

## Result
The durable P.T. pilot has moved from `RESEARCH_AUDITED` to `ROUGH_NARRATIVE_READY` using exact active audited Claims only.

```text
Project State                 ROUGH_NARRATIVE_READY
Manifest Version              7
Narrative Spine               NARRATIVE_SPINE_000001@1
Acts                           5
Scenes                         7
Active Narration Beats        10
Included audited Claims        9
Research-prohibited Claims     3
Editorially deferred theories  2
ROUGH_NARRATIVE Gate          PASS
VISUAL_REQUIREMENTS Gate      FAIL (expected; not built yet)
Cold-start drift roots         0
Cold-start invalidations       0
Cold-start changed records     0
```

## Narrative spine

**Core question**  
P.T. กลายจากเดโมปริศนาที่แทบไม่มีชื่อ ไปเป็นผลงานดิจิทัลที่ถูกถอดออกและดาวน์โหลดซ้ำไม่ได้ แต่ยังคงถูกศึกษาผ่านหลักฐานที่หลงเหลืออยู่ได้อย่างไร?

**Opening promise**  
เริ่มจากการปล่อยเดโมภายใต้ชื่อ `7780s Studio`, ตามไปถึงการถอดออกจาก Store / การบล็อก re-download และปิดด้วยสิ่งที่หลักฐานเชิงเทคนิคภายหลังยังตรวจพบจากสำเนาที่เหลืออยู่.

**Final synthesis**  
Research ที่ audit แล้วรองรับข้อสรุปเชิงโครงเรื่องว่า P.T. ไม่ได้ “หาย” ในเหตุการณ์เดียว: ช่องทางเข้าถึงถูกตัดลงเป็นลำดับ ขณะที่ installed copies, public records และ later technical inspection ยังทิ้งหลักฐานให้ตรวจสอบได้. นี่เป็น narrative synthesis ไม่ใช่ Claim ใหม่เรื่องอิทธิพลของ P.T. ต่อเกมอื่น.

## Acts / scenes / beats

| Act | Scene | Beat | Research binding |
|---|---|---|---|
| The Demo With No Name | 12 August 2014 | `NB_000001@2` Opening setup | `CLM_000001@2` |
|  |  | `NB_000002@1` 7780 meaning | `CLM_000003@2` |
|  | A Million Downloads | `NB_000003@1` early spread | `CLM_000002@2` (`QUALIFIED` ceiling) |
| The Ghost Behind the Camera | What the Camera Hack Showed | `NB_000004@2` Lisa finding | `CLM_000008@2` (`ATTRIBUTED`; no exact distance) |
| The Disappearing Download | 29 April — 6 May | `NB_000005@1` Store removal | `CLM_000005@2` |
|  |  | `NB_000006@2` re-download block | `CLM_000014@1` |
|  | The Installed Copy Becomes the Object | `NB_000007@1` PS4 resale consequence | `CLM_000006@2` |
| The Creator Outside the Door | A Statement on Stage | `NB_000008@1` TGA statement | `CLM_000007@2` (`ATTRIBUTED`) |
|  |  | `NB_000009@1` contract end | `CLM_000009@2` |
| The Digital Ghost | What Was Actually Erased? | `NB_000010@2` payoff synthesis | `CLM_000005@2`, `CLM_000014@1`, `CLM_000006@2`, `CLM_000008@2` |

Every active Beat is committed as `workflow_state: RESEARCH_BOUND`. Build 013 intentionally does **not** create final narration and does **not** create `visual_requirement` fields.

## Claims intentionally kept out of the spine

- `CLM_000004` (`204863`) — audit allows it only as `THEORY`, but it is editorially deferred because it is not needed for the documentary's core causal path.
- `CLM_000010` (Swedish-radio community theory) — also narratable only as `THEORY`, editorially deferred from the rough spine.
- `CLM_000011`, `CLM_000012`, `CLM_000013` — `INSUFFICIENT_EVIDENCE` + `PROHIBITED`; the runtime would fail closed if a plan attempted to bind them.

## Runtime guarantees added in Build 013

1. Rough Narrative can run only from `RESEARCH_AUDITED`.
2. Every Claim binding resolves the current exact ACTIVE Claim version before mutation begins.
3. Stale/blocked/archived/rejected or research-ineligible Claims are rejected.
4. `production_use.narration_allowed=false` / `PROHIBITED` fails closed.
5. `batch_id` is bound to SHA-256 of the complete plan; replay is idempotent and changed content with the same ID is rejected.
6. The runtime creates `ACT` → `SCENE` → `NARRATION_BEAT` through the State Engine and creates the immutable `NARRATIVE_SPINE` Artifact through the Artifact Registry.
7. Gate evaluation occurs after commit; state transition is performed in a separate transaction so `ROUGH_NARRATIVE_READY` is entered only from committed evidence.
8. Cold Start reconstructs the completed rough narrative with zero dependency drift.

## Next legal action

```text
ROUGH_NARRATIVE_READY
        ↓
VISUAL_REQUIREMENTS
        ↓
VISUAL_REQUIREMENTS_READY
```

The current missing requirement is `BEAT_VISUAL_REQUIREMENTS_READY`: Build 014 should create exact visual requirements for the 10 active Beats without writing final narration prematurely.

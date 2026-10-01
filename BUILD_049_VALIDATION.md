# Build 049 validation

Validated locally on CachyOS during 2026-09-30 / 2026-10-01. These results demonstrate the connected local editing workflow; they do not establish real documentary acceptance or final Drive delivery.

## Automated checks

- New editor/research/storage records: **13 passed** (`test_story_footage`, `test_evidence_review`, `test_edit_checkpoint`, `test_script_review`).
- Real-media/edit/render partition: **8 passed**, plus the subsequently added source-preserving trim/concurrent-range test: **1 passed**. Total new Build 049 cases: **22**.
- QUICK audit with a 240-second partition timeout: **31 PASS / 0 FAIL / 0 TIMEOUT / 1 WARN**. Its ten pytest partitions contain **84 passing cases**, including the 13 new record tests; do not add those 13 again when counting unique tests. The warning is the existing missing standalone Build 001 changelog.
- Operator compatibility after final UI changes: **5 passed** (Build 040 and Build 045), run alongside the new trim test.
- Python compilation and `git diff --check`: passed.
- Earlier affected research-audit compatibility: Build 012 **7 passed**; new evidence review **3 passed**. These overlap new-test counts above.

The media tests use actual FFmpeg-generated source video and tone audio. They exercise exact measured voice timing, frame/sample conform, explicit last-frame hold, music ducking, mixed Thai/Latin title overlays, subtitle export, full-file decode, local review and delivery ZIP creation. Their short synthetic output is **not** a 2–3 minute documentary and is not evidence of narrative quality, natural voice quality or footage relevance.

Failure tests cover altered media, out-of-bounds trims, stale editor revisions, stale AI story drafts, fabricated excerpts, incorrect source associations, retracted evidence, changed narration, sync checkpoint races and render/export invalidation after research or edit changes. Caption-free metadata never triggers automatic footage selection.

## Live local observations

- The existing private project opened in the editor with **13 scenes**, **13 claim review units**, and **7 source leads**. Editor, source review and scene-to-claim review dialogs were constructed using the actual desktop. No provider request or factual approval was made by that check.
- A rendered fixture frame was inspected. A Thai-only drawtext font initially caused missing Latin glyphs; libass font fallback now renders the mixed heading `ฉากแรก · First` correctly.
- Opening/saving an unchanged edit preserves its revision, so UI navigation does not invalidate a previously reviewed render.
- Private source documents and project assets remain outside the Git repository.

## Unverified / unfinished

- No live Codex story generation, private-project Edge narration, or new project YouTube download was performed. The provider adapters and acquisition orchestration were tested using controlled inputs. User provider choice and private-text TTS consent remain pending.
- A read-only rclone Drive check on 2026-09-30 still returned the shared OAuth client's quota **403**. No verified project upload or final Drive delivery is claimed.
- Caption nominations are proposed cuts; visual-semantic relevance needs review or a connected vision provider.
- Draft scene/shot/render objects still need the canonical final production/release adapters. The evidence-readiness report is derived from canonical claims, not a replacement completion authority.
- Local delivery ZIPs are explicitly `REVIEWED_LOCAL_DRAFT`; `documentary_completed` stays false. Real 2–3 minute and 30-minute acceptance remain pending.

# GMK Documentary Maker — Build 056 operator handoff

Start on Linux/CachyOS with `./START_GMK.sh` (run `./INSTALL_GMK.sh` for first setup). Windows uses `INSTALL_GMK.cmd` and `START_GMK.cmd`.

The desktop app has general documentary projects and setup. Create a topic or import a local/Drive LEMiNO Script, then open the documentary workspace. Research and every acquired source file remain in the project library; removing a selected cut does not delete its original.

The overview derives readiness for all 20 requested lifecycle stages and opens the next available action. Review claim evidence and scene wording before connecting the story. Select/download footage, inspect actual pictures, record exact visual reviews and listening decisions. Use **เชื่อมภาพที่ตรวจแล้วเข้าข้อมูลผลิต** to preview and register the current bytes and selected ranges. Changes require a fresh preview; relevant trims invalidate picture reviews.

Use **ตรวจความครอบคลุมภาพกับเสียง** to inspect measured narration, used ranges, missing/repeated pictures and explicit held frames, then save the coverage result. If selecting this reviewed library is complete, choose the initially unchecked stop option and provide a reason. PASS plus that decision advances the existing canonical visual-coverage gates. Relevant revisions require fresh assessment.

Use **เตรียมบทสุดท้ายและตรวจเสียงรวม** after coverage/library closure. Inspect, prepare exact ordered final narration and actual master audio, open the verified local WAV, then explicitly record a named whole-master listening decision. Per-scene reviews do not approve the master. Rejected voice requires explicit reopening and new assessment/preparation. Original files and history remain.

Use **ตรวจรูปแบบภาพและเชื่อมแผนฉากช็อต** after voice approval. Inspect actual design settings, prepare/open a verified PNG, then explicitly record a named design review. Only approved current design allows **เชื่อมแผนฉากและทุกช็อต**. All used cuts and held frames follow actual master timing; SUPPORTING stays contextual and rights remain UNKNOWN. Style reopening preserves current voice; upstream reopening retires owned design/plans/voice and retains history/media.

Add or explicitly omit music, inspect the measured-audio timeline, render MP4, review the entire film across the eight named checks, then create an exact local draft package. Drive delivery validates the stored package/master/manifest receipts. Failed transfer preserves local work and allows retry.

See [Thai startup](README_START_HERE_TH.md), [editor guide](EDITOR_GUIDE_TH.md), [current validation](BUILD_056_VALIDATION.md), [product requirements](PRODUCT_REQUIREMENTS.md) and [remaining integration](IMPLEMENTATION_ROADMAP.md).

## CLI

```bash
python -m gmk_operator --system-check
python -m gmk_operator --headless-status
python -m gmk_projects workflow /path/to/project
python -m gmk_projects production-inspect /path/to/project
python -m gmk_projects media-inspect /path/to/project
python -m gmk_projects media-connect /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
python -m gmk_projects coverage-inspect /path/to/project
python -m gmk_projects coverage-record /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
# Optional explicit reviewed-library selection closure:
python -m gmk_projects coverage-record /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash> --complete-library-selection --stop-reason "Reviewed library selection is sufficient for these scenes"
python -m gmk_projects final-inspect /path/to/project
python -m gmk_projects final-prepare /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
# After listening to the exact prepared master:
python -m gmk_projects final-voice-decide /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash> --master-sha256 <preview-master-hash> --decision APPROVED --actor-id <reviewer-name>
python -m gmk_projects final-reopen /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
python -m gmk_projects design-inspect /path/to/project
python -m gmk_projects design-prepare /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
python -m gmk_projects design-decide /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash> --decision APPROVED --actor-id <reviewer-name>
python -m gmk_projects plan-prepare /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
python -m gmk_projects design-reopen /path/to/project --edit-sha256 <preview-edit-hash> --manifest-sha256 <preview-core-hash>
python -m gmk_projects delivery-verify /path/to/project
```

Canonical media registration stops at ASSET_RECON. Current coverage PASS plus explicit library closure can reach VISUAL_COVERAGE_READY; it does not certify rights, exhaustive external search or full-film approval. Build 055 carries exact reviewed narration and real assembled audio through SCRIPT_READY/TTS_READY to explicit human VOICE_LOCKED. Build 056 also reaches SHOT_PLAN_READY. Canonical review/production lock/render/QA/final release are still pending, as are real short/long film acceptance and verified live Drive delivery. Synthetic tests never approve the real user's claims. Historical P.T. fixtures and CLI engines remain developer regression data outside the product UI; they are not the general project's next task.

Build 056 connects current design approval and exact used-cut plans to SHOT_PLAN_READY. Canonical review/production lock/render/full-film QA/final release and real short/long-film/Drive acceptance remain pending.

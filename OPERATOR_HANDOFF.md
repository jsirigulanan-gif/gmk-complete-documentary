# GMK Documentary Maker — Build 054 operator handoff

Start on Linux/CachyOS with `./START_GMK.sh` (run `./INSTALL_GMK.sh` for first setup). Windows uses `INSTALL_GMK.cmd` and `START_GMK.cmd`.

The desktop app has general documentary projects and setup. Create a topic or import a local/Drive LEMiNO Script, then open the documentary workspace. Research and every acquired source file remain in the project library; removing a selected cut does not delete its original.

The overview derives readiness for all 20 requested lifecycle stages and opens the next available action. Review claim evidence and scene wording before connecting the story. Select/download footage, inspect actual pictures, record exact visual reviews and listening decisions. Use **เชื่อมภาพที่ตรวจแล้วเข้าข้อมูลผลิต** to preview and register the current bytes and selected ranges. Changes require a fresh preview; relevant trims invalidate picture reviews.

Use **ตรวจความครอบคลุมภาพกับเสียง** to inspect measured narration, used ranges, missing/repeated pictures and explicit held frames, then save the coverage result. If selecting this reviewed library is complete, choose the initially unchecked stop option and provide a reason. PASS plus that decision advances the existing canonical visual-coverage gates. Relevant revisions require fresh assessment.

Add or explicitly omit music, inspect the measured-audio timeline, render MP4, review the entire film across the eight named checks, then create an exact local draft package. Drive delivery validates the stored package/master/manifest receipts. Failed transfer preserves local work and allows retry.

See [Thai startup](README_START_HERE_TH.md), [editor guide](EDITOR_GUIDE_TH.md), [current validation](BUILD_053_VALIDATION.md), [product requirements](PRODUCT_REQUIREMENTS.md) and [remaining integration](IMPLEMENTATION_ROADMAP.md).

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
python -m gmk_projects delivery-verify /path/to/project
```

Canonical media registration stops at ASSET_RECON. Current coverage PASS plus explicit library closure can reach VISUAL_COVERAGE_READY; it does not certify rights, exhaustive external search or full-film approval. Canonical downstream locks and final release are still pending, as are real short/long film acceptance and verified live Drive delivery. Synthetic tests never approve the real user's claims. Historical P.T. fixtures and CLI engines remain developer regression data outside the product UI; they are not the general project's next task.

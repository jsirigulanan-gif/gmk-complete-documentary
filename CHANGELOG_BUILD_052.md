# Build 052 — focused documentary workspace and guided production readiness

The desktop app previously mixed general documentary projects with a P.T. demonstration and fixed Lisa/TGA requirements. It now opens the user's documentary projects directly and exposes setup in one additional tab. Pilot UI, its path requirements, old execution controls, separate overview/log pages and duplicate general-project actions were removed. Historical core engines and fixtures remain outside the product UI; private projects and media were retained.

New topic briefs record audience, editorial question, scope, language and target duration. The editor derives readiness across all 20 product stages and directs the user to the next useful action. It checks actual registered media bytes, measures narration/timeline, identifies stale renders/packages, and leaves canonical completion pending where final integration is missing.

Shot review records visible content, match reason and evidence/support/context classification against exact current narration, visual requirements, claim refs and source in/out points. Listening review pins the current narration/audio bytes. Relevant edits require review again; missing files require recovery before readiness. Full-film approval in the UI records eight editorial checks against the current master and edit/research versions.

Early-stage research additions reopen research intake transactionally and preserve the working edit and old sources. Story and footage forms scroll so controls remain accessible on smaller displays. The installer includes rclone, desktop labels and startup docs use GMK Documentary Maker, and CLI/headless commands now inspect general projects.

Unstructured research can now be turned into explicit review units from selected original text. The UI and `research-add-claim` CLI preserve the exact source hash and excerpt in an immutable derivative without replacing the script. Identical submissions replay without duplicate claims. Assertions stay UNREVIEWED and in the same imported source-independence group; original research questions remain open. No external source verification is inferred from this extraction.

Research forms scroll while keeping save controls visible. Guided recovery targets the exact scene with missing audio/footage, including later scenes with previous approvals. Missing footage routes to acquisition before visual review.

Reimporting the exact original now restores a missing registered asset instead of returning a reference to an absent file. Existing catalog identity, sources, scene associations and timeline references survive. Changed existing bytes are rejected and retained for recovery rather than overwritten.

The audit runner now decodes byte output retained by timed-out subprocesses instead of crashing while formatting the result. Workflow/media and research-extraction checks run in separate bounded partitions; TIMEOUT remains an explicit non-pass result.

Automatic provider-backed production and canonical final asset/shot/render/release integration are still incomplete. This build verifies guided local production, not real Drive delivery or completed-documentary acceptance.

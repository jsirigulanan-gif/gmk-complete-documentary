# Build 046 — Documentary project intake and Drive storage

The application can create documentary projects from LEMiNO Script research rather than requiring the bundled P.T. slots. The new Drive tab imports research and manages registered files in each project's own Drive directory.

- Preserve original research, source hyperlinks, and parsed bilingual shot content. Source VERIFIED labels remain unverified claims and timestamps remain planning estimates.
- Freeze local asset copies, record SHA256/MD5 and source/scene references, verify remote byte size and MD5, and publish immutable manifest snapshots only after all registered assets pass verification.
- Keep files and upload failure state for retry. Never delete unrelated Drive files or change sharing. ProjectAcquirer archives each acquired candidate before it is returned to the footage matcher.
- Move P.T. footage search into the P.T. example section.
- Add optional free Edge TTS Thai narration (Niwat/Premwadee), per-scene cache/retry, actual audio duration measurement, subtitle files, and a narration timeline. Previewing one scene is not marked as a completed narration job.

Full automatic film production is still incomplete. Live Drive upload encountered the existing shared rclone client's Google API quota (403). An upload failure is not reported as completion.

# Build 046 validation

- Targeted regression: 32 passed (project storage/intake/voice, Operator, acquisition, and automatic-footage compatibility).
- QUICK audit: 28 PASS, 0 FAIL, 0 TIMEOUT, 1 existing Build 001 changelog warning.
- Live desktop construction: tabs are Start, Drive Projects, P.T. Example, System, Log; the new panel reads locally created projects successfully.
- Real Google Docs research import: 13 scenes, Thai narration in all 13 scenes, 7 retained hyperlinks. Source is private and remains outside Git.
- Live free Thai speech service: listed Niwat and Premwadee voices. Generated a new generic Thai test passage with Niwat; ffprobe measured 10.536 seconds, 63,216 bytes. This is a connectivity/audio-file test, not a listening-quality certification or a narration of the private research document.
- Storage tests cover failed upload and retry, immutable copies, multiple scene/source references, local corruption, remote checksum rejection, path traversal rejection, and per-candidate archival.
- Voice tests use actual generated test audio to check measured timing, cache corruption, partial-job recovery, and preview completion semantics. Synthetic test tones are not documentary deliverables.

## Live blockers

- Actual project upload was attempted and failed with Google Drive API quota error 403 on the pre-existing shared rclone OAuth client. Project state recorded the failure and local files remained. Successful real Drive upload is NOT claimed.
- Sending private project narration to Edge TTS was rejected by automatic approval review pending explicit user consent. Only an independently written generic sample was sent.
- No complete documentary was rendered. Automated factual review/story revision, project footage orchestration, music mixing, and an integrated video editor remain outstanding.

See DRIVE_PROJECTS.md for configuration and continuation. This build is a tested intake/storage/narration milestone, not the finished end-to-end product.

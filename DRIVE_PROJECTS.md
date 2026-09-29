# Documentary projects on Google Drive

## Scope

Projects are independent of the P.T. example but use the same existing production StateEngine and schema. The current milestone provides registered research intake, production state, file storage, and optional narration, not end-to-end documentary generation. The complete target is in PRODUCT_REQUIREMENTS.md.

Open **โปรเจกต์ Drive** in the Operator. Search the root of the configured `gdrive:` connection for `[LEMiNO Script]` Google Docs, select one, and create a project. Alternatively, import DOCX, plain text, or a Google Docs API JSON snapshot. Each project keeps the original source, extracted text and hyperlinks, and a working `script.json`.

Local projects live under `~/GMK Projects/project-<unique ID>/`. Registered files go to `gdrive:GMK Documentary Projects/project-<unique ID>/` in these categories:

- `research`: research sources and script versions
- `footage`: full downloaded source footage
- `voice`: narration audio
- `music`: music files
- `timeline`: editing data
- `exports`: finished video exports
- `manifests`: immutable project inventory snapshots

`production/CURRENT_MANIFEST.json` is the authoritative local production-state pointer. The Drive catalog no longer stores a hardcoded production-state label. Before sync, the core records and research inputs are frozen into a registered `production-checkpoint.zip` asset under `timeline`. Repeating sync without core changes reuses that checkpoint. This backup is not a complete restore UI or a final film export.

New projects are bound automatically. Existing Build 046 projects can be connected once with **เชื่อมโปรเจกต์รุ่นเดิม** or `python -m gmk_projects connect-production /path/to/project`. Migration preserves their registered media and is safe to repeat. Status reads do not silently migrate a project. Missing or corrupt core records fail rather than resetting the project's history.

The Drive directory is created by the first successful upload. Empty local folders are not claimed as existing remote folders. The directory ID is unique per project so duplicate documentary titles do not overwrite another project.

## Upload semantics

Register a file before upload. GMK freezes a copy, computes hashes in bounded memory, and records source URLs and scene references. It copies only registered assets, verifies size and MD5 returned from Drive, then uploads a manifest snapshot. A failed transfer or missing/mismatched checksum keeps the project in `UPLOAD_FAILED`; local media remains available and sync can be retried. A verified storage state does not mean the film is finished. There is no automatic local cleanup and no remote delete, public sharing, or destructive folder sync.

The existing Python footage runtime can use `ProjectAcquirer(project)` as its `acquirer` to archive every downloaded candidate, including clips later rejected by matching. The new project GUI does not yet invoke that footage-production runtime. Legacy P.T. commands retain their existing behavior; they are not silently redirected to Drive.

## CLI

```bash
python -m gmk_projects list-scripts
python -m gmk_projects create --title 'My documentary' --source research.docx
python -m gmk_projects add '/path/to/project' clip.mp4 --role footage --scene SHOT-001 --source-url https://example.com/source
python -m gmk_projects sync '/path/to/project'
python -m gmk_projects status '/path/to/project'
```

Dependencies: Python, rclone, and a Google Drive remote configured as `gdrive:`. Remote name and destination root can be set on CLI project creation. The application's rclone credentials are independent of the Codex Drive connector. Secrets stay in rclone's configuration, outside this repository.

## Current connection issue

On 2026-09-29 the local rclone connection listed root folders, but uploads failed with Google's 403 quota error for the shared rclone client. Existing local work is preserved. Rclone documents the retirement of its shared Google client during 2026 and recommends a personal OAuth client: https://rclone.org/drive/#making-your-own-client-id . Resolving this connection is required before claiming a successful real Drive upload.

## Thai narration

The project panel offers a first-scene preview and full narration using Niwat (male) or Premwadee (female) through the third-party `edge-tts` client. It uses Microsoft's online Edge speech service without an API key: https://github.com/rany2/edge-tts . Text is sent to that service; audio is generated online, not locally. Service availability/limits are outside GMK's control. There is no paid fallback. Review pronunciation and prosody before using the audio in a film.

Install `requirements-voice.txt` in a Python virtual environment; configure its `edge-tts` executable using `GMK_EDGE_TTS` or the local Operator configuration's `edge_tts_path`. ffprobe must be available. CLI: `python -m gmk_projects voice /path/to/project --limit 1`. Omit `--limit` to narrate all imported scenes.

Each scene's generated audio is measured with ffprobe, registered in the project, and referenced by a measured `voice_timeline.json`. Source document timings are not treated as spoken durations. Completed scenes are cached; failed later scenes can be retried. Voice generation can proceed while Drive is unavailable; use the upload button to send registered audio after connection recovery.

## Completion criteria and outstanding work

The product target is: select a research document, refine a sourced narrative, download relevant footage, generate Thai voice, time pictures to measured speech, mix music, allow review/edits, and export a playable MP4 back to the same project. First prove this with a 2–3 minute film, then scale to 30 minutes.

Outstanding: automatic research verification/story rewriting, project scene-to-footage orchestration, measured narration-to-picture assembly, music selection/mixing, integrated preview/editor, large interrupted transfer recovery, remote project restore, and an end-to-end real documentary acceptance run. Upload retry currently retries failed files; it does not guarantee byte-offset resume after a process restart. Original research and acquired media are private project data and must not be committed to Git.

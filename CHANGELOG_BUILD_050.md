# Build 050 — Verify the exact draft package before and after delivery

Previously a local export could rely on mutable summary JSON and a generic project upload without proving that the delivery ZIP matched the currently reviewed film. Delivery now validates the registered render snapshot, archived technical QA, editorial decision, research revision and every ZIP member before starting a transfer.

- Build deterministic ZIPs using fixed timestamps, stable entry order and bounded-memory streaming. Unchanged exports reuse the same immutable bytes.
- Register an immutable delivery record and its active reference in the project manifest so the uploaded snapshot identifies the selected package.
- Verify archived QA and render records rather than trusting only `last_render.json`; require the exact USER_APPROVED editorial decision.
- Reject incomplete, duplicate-entry, altered, stale or mismatched package contents. Compare individual member hashes without extracting archives.
- Expose local `delivery-verify` and explicit network `delivery-sync` commands plus editor actions.
- Validate file ID, size and MD5 from every Drive adapter receipt, including the project manifest snapshot. Invalid receipts keep storage failed rather than VERIFIED.
- Retry interrupted transfers using the same package, retain all project assets, and check again after transfer for concurrent changes before issuing a dated delivery-verification receipt.

The delivered product of this adapter is a **reviewed local draft package**. It does not advance canonical production gates or finalize a documentary. Live Drive still needs its account/quota problem resolved; this build's transfer tests use a controlled in-memory adapter. No private script was sent to a voice/model provider.

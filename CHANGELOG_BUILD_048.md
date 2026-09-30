# Build 048 — General documentary research intake

Importing DOCX, native Google Docs JSON, or text now creates canonical SOURCE, EVIDENCE, CLAIM, RESEARCH_GAP and RESEARCH_ATTEMPT_LOG records in the project's existing StateEngine workspace. New imports run intake automatically; existing projects have a repeatable intake action.

- Recognize LEMiNO SHOT narration and explicit CLAIM:/FACT: entries, including Thai labels. In bilingual scenes, use Thai narration once instead of importing its English alternative as corroboration.
- Retain exact extracted-text line/scene locators. Visual/audio cues and the source library are excluded from supported shot narration. Unstructured briefs produce an extraction gap, not invented assertions.
- Treat imported paragraphs as review units, which may need further splitting into individual claims. All start UNREVIEWED with narration prohibited for an approved production; document evidence proves only what the supplied document says.
- Preserve deduplicated hyperlinks as unfetched source leads. Do not invent links between a claim and the document's bibliography.
- Add a local, escaped HTML review and JSON companion showing current claims, locations, source leads and research gaps. GUI buttons and CLI expose intake/review, with counts from canonical records.
- Keep original P.T. parser behavior as the default legacy runtime. General intake uses its own versioned replay namespace. Imported packs share an unknown-independence group so multiple drafts do not count as independent corroboration.
- Validate frozen inputs on every attempt, including replay; serialize project writes and retain idempotent source/claim history across multiple packs.

This completes the general intake/review slice, not the external research assistant, atomic claim extraction, editorial decisions, narrative generation or film-production lifecycle. The review page is read-only. No private script was sent to TTS and no successful live Drive upload is claimed.

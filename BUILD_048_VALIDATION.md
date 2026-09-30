# Build 048 validation

Scope: general research intake and a read-only review surface over existing canonical records. This is not a complete documentary production acceptance run.

- Targeted coverage: 61 distinct tests passed across Build 011/012/013 research/narrative compatibility, Build 040/041/045 Operator compatibility, Build 042 distribution, and Build 046/047/048 projects. Executed in bounded partitions; changed research behavior was retested after final edits.
- QUICK audit: 30 PASS, 0 FAIL, 0 TIMEOUT, 1 documented legacy Build 001 changelog warning. The initial audit caught stale current-build documentation; it passed after the README and changelog were completed.
- Eight new regression tests cover selected-language narration and exact source locations; freeform briefs that cannot be automatically extracted; Google Docs text/hyperlinks; replay/cold-start/audit guard; multiple source packs without assumed independence; modified frozen-source rejection; HTML escaping; and source edits during import without diverging script/claim inputs.
- Legacy P.T. intake, research audit and narrative tests remain compatible. General intake does not inherit P.T. keyword-to-evidence-scope heuristics.
- Live local source: 13 selected narration paragraphs, 13 contextual document excerpts, 7 unfetched source links, and an unresolved audit gap were persisted. Replay retained 13 records with no duplicates. The actual production state remains RESEARCH_INTAKE.
- A new production checkpoint containing those records was registered locally (95,847 bytes at verification). It was not uploaded to Drive.
- Live desktop construction displayed the two research actions and actual project count: 13 unreviewed / 13 total. The test closed its own window.
- CLI entry points, Python compilation and whitespace checks passed.

The source document, project records, report and checkpoint remain outside Git. No external source URLs were fetched, private narration submitted to Edge TTS, or Drive upload attempted by this build. Remaining product gaps include evidence collection/review, atomic claim splitting, narrative generation, canonical beats/visuals, footage/timeline integration, full-film rendering/QA and verified Drive delivery. The existing Drive quota issue and pending consent for private project TTS remain unresolved.

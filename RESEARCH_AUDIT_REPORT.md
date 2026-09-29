# GMK P.T. Research Audit Report — Build 012

## Result
Independent Research Audit is complete for the P.T. intake claim set. The runtime created exact external `SOURCE` / `EVIDENCE` records, derived Claim dispositions from evidence relation + strength + source-independence groups, cleared the intake guard only after every intake Claim received an explicit disposition, and transitioned the durable pilot workspace to `RESEARCH_AUDITED`.

```text
Project State             RESEARCH_AUDITED
Manifest Version          5
External Sources Added    22
External Evidence Added   22
Active Claims             14
CORROBORATED               5
SOURCE_VERIFIED            6
INSUFFICIENT_EVIDENCE      3
Open Research Gaps         4
Resolved Research Gaps     2
Research Audit Gate        PASS
Cold-start Registry Drift  0
```

## Claim dispositions

| Claim | Type | Verification | Certainty | Narration mode | Audited wording |
|---|---|---|---|---|---|
| `CLM_000001` | FACTUAL_ASSERTION | CORROBORATED | HIGH | DIRECT | P.T. เปิดตัวและปล่อยให้ดาวน์โหลดบน PlayStation Network เมื่อวันที่ 12 สิงหาคม 2014 ในงาน Gamescom 2014 โดยใช้ชื่อสตูดิโอปลอมว่า "7780s Studio" |
| `CLM_000002` | FACTUAL_ASSERTION | SOURCE_VERIFIED | MEDIUM | QUALIFIED | ยอดดาวน์โหลดของ P.T. ทะลุ 1 ล้านครั้งภายในวันที่ 1 กันยายน 2014 ก่อนที่เกมจะถูกถอดจากสโตร์ |
| `CLM_000003` | FACTUAL_ASSERTION | SOURCE_VERIFIED | HIGH | DIRECT | รหัส "7780" อ้างอิงจากขนาดพื้นที่ของจังหวัดชิซูโอกะ (7,780 ตร.กม.) ซึ่งแปลความหมายได้ว่า "Silent Hill" |
| `CLM_000004` | COMMUNITY_THEORY | SOURCE_VERIFIED | MEDIUM | THEORY | มีทฤษฎีในชุมชนผู้เล่นว่าเลข “204863” สามารถอ่านเป็น 24/08/63 ซึ่งตรงกับวันเกิดของ Hideo Kojima แต่การตรวจรอบนี้ไม่พบหลักฐานจาก Kojima หรือ Konami ที่ยืนยันว่าเป็นเจตนาของตัวเลขนี้ |
| `CLM_000005` | FACTUAL_ASSERTION | CORROBORATED | HIGH | DIRECT | Konami ถอด P.T. ออกจาก PlayStation Store อย่างเป็นทางการเมื่อวันที่ 29 เมษายน 2015 |
| `CLM_000006` | FACTUAL_ASSERTION | CORROBORATED | HIGH | DIRECT | หลังการถอด P.T. มีการตั้งขาย PS4 ที่ติดตั้งเกมไว้ใน eBay โดยมีตัวอย่างประกาศในสหราชอาณาจักรที่ £1,000 (ประมาณ $1,500) และต่อมา eBay ลบประกาศลักษณะนี้จำนวนมากโดยอ้างข้อจำกัดเกี่ยวกับซอฟต์แวร์/ลิขสิทธิ์ |
| `CLM_000007` | REPORTED_ASSERTION | SOURCE_VERIFIED | MEDIUM | ATTRIBUTED | ในงาน The Game Awards 2015 Geoff Keighley กล่าวบนเวทีว่า Hideo Kojima ได้รับแจ้งจากทนายที่เป็นตัวแทนของ Konami ว่าเขาไม่ได้รับอนุญาตให้เดินทางมาร่วมงานเพื่อรับรางวัล |
| `CLM_000008` | TECHNICAL_FINDING | SOURCE_VERIFIED | HIGH | ATTRIBUTED | การแฮ็กมุมกล้องของ Lance McDonald ในปี 2019 แสดงให้เห็นว่า หลังผู้เล่นได้ไฟฉาย โมเดล Lisa จะติดตามอยู่ด้านหลังผู้เล่นและเคลื่อนตามไปด้วย; หลักฐานที่ตรวจรอบนี้ไม่ยืนยันระยะห่างเชิงตัวเลขที่แน่นอน |
| `CLM_000009` | FACTUAL_ASSERTION | CORROBORATED | HIGH | DIRECT | สัญญาจ้างงานของ Hideo Kojima กับ Konami สิ้นสุดลงอย่างเป็นทางการในวันที่ 15 ธันวาคม 2015 |
| `CLM_000010` | COMMUNITY_THEORY | SOURCE_VERIFIED | MEDIUM | THEORY | การถอดรหัสข้อความวิทยุภาษาสวีเดน ("Close your eyes..."): ชุมชนเชื่อว่าเป็นสัญลักษณ์เชื่อมโยงถึง The War of the Worlds (1938) และเป็นการส่งสัญญาณเตือนถึงการถูกจับตามอง (Surveillance) ขององค์กร |
| `CLM_000011` | COMMUNITY_THEORY | INSUFFICIENT_EVIDENCE | LOW | PROHIBITED | ถุงกระดาษเปื้อนเลือดที่พูดได้คือตัวแทนของ Hideo Kojima ที่กำลังถูกกดทับและขังอยู่ในห้องสี่เหลี่ยมแคบๆ ของ Konami |
| `CLM_000012` | RUMOR | INSUFFICIENT_EVIDENCE | LOW | PROHIBITED | ข่าวลือที่ว่า Kojima แอบใช้งบประมาณและทรัพยากรของ MGSV ในการพัฒนา P.T. โดยไม่ได้รับการอนุมัติอย่างเป็นทางการจากบอร์ดบริหารระดับสูงของ Konami จนกลายเป็นฟางเส้นสุดท้าย |
| `CLM_000013` | INTERPRETATION | INSUFFICIENT_EVIDENCE | LOW | PROHIBITED | ฉากห้องน้ำและทารกที่ผิดรูปในอ่างล้างหน้า สื่อถึง "การแท้งบุตร" ของโปรเจกต์เกมที่ถูกขัดขวางไม่ให้ลืมตาดูโลก |
| `CLM_000014` | FACTUAL_ASSERTION | CORROBORATED | HIGH | DIRECT | ภายในวันที่ 6 พฤษภาคม 2015 P.T. ไม่สามารถดาวน์โหลดซ้ำจาก PlayStation Network ได้ แม้บัญชีนั้นจะเคยเพิ่มหรือดาวน์โหลดเกมไว้ก่อนหน้า |

## Important corrections / constraints
- `FACT-004 / CLM_000004` is no longer treated as a verified factual claim. The birthday reading of `204863` is retained only as a **community theory**; the audit found community discussion but no Kojima/Konami evidence establishing creator intent.
- `CLM_000006` narrows the pack's mixed currency wording: verified examples include UK listings at **£1,000 (about $1,500)**; a separate source supports eBay later taking down such listings.
- `CLM_000007` is a `REPORTED_ASSERTION`: narration must attribute the restriction to **Geoff Keighley's live Game Awards statement**, rather than independently claiming Konami's motive.
- `CLM_000008` establishes the Lisa behind/follow relationship from the McDonald camera-hack finding, but **does not establish the pack's exact 0.5 m offset**. The numeric precision remains unknown and is recorded as an open MAJOR Research Gap.
- The pack narrative places the re-download lock in **December 2015**. Contemporaneous May 2015 evidence shows re-download was already blocked by **May 6, 2015**. This discrepancy is preserved explicitly as resolved `GAP_000005`; it was not silently edited. A separately supported factual Claim, `CLM_000014`, records the May 6 state.
- `CLM_000011`, `CLM_000012`, and `CLM_000013` remain `INSUFFICIENT_EVIDENCE` and `PROHIBITED` for narration as asserted interpretations/rumor.
- The original three Research Pack unresolved questions remain OPEN.

## Research truth boundary
`SOURCE_VERIFIED` does not mean every downstream interpretation is factual. It means the identified source group supports the scoped Claim. Community theories are narratable only as theories; reported statements/technical findings retain attribution where required.

## Runtime integrity
Build 012 also closes two runtime integrity gaps exposed by real Research Audit:
1. LIVE derived/operational changes can now be persisted as content-addressed exact records while the immutable decision version remains untouched.
2. Cold-start dependency recomputation is idempotent: lineage `SUPERSEDES` edges do not stale the new version, historical Dependency Impact Reports do not become live dependents, and equivalent stale state preserves prior timestamps/record hashes.
3. An unresolved Research Gap remains a blocker even when its exact dependencies are stale; staleness cannot make a critical unknown disappear.
4. Research Audit idempotency now binds `batch_id` to the exact batch SHA-256; reusing a batch ID with changed verification content fails closed.

## Next legal action
`RESEARCH_AUDITED → ROUGH_NARRATIVE_READY` is not yet legal because `NARRATIVE_SPINE` has not been created. The current derived action is `SATISFY_GATE_REQUIREMENTS` for the `ROUGH_NARRATIVE` gate.

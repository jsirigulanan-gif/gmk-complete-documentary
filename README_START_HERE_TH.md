# Current package: Build 043

# เริ่มใช้ GMK P.T. Operator — Build 045

Build 045 เป็น **CachyOS / Arch Linux native release + Windows-compatible release** ของ GMK Operator GUI โดย GUI เป็นเพียงหน้าควบคุม; source-lock, `ffprobe`, checksum, Gate และ workspace mutation ยังใช้ authoritative runtime ชุดเดียวกับ CLI

GMK มีเป้าหมายช่วยผลิตสารคดีตั้งแต่งานวิจัยจนถึงการส่งออกวิดีโอ แต่ GUI รุ่นนี้ทำงานกับโครงการตัวอย่าง **P.T.** ที่เตรียมไว้เท่านั้น แท็บ Lisa/TGA เป็นไฟล์วิดีโอสองแหล่งที่โครงการนี้ยังขาด ไม่ใช่ข้อกำหนดของสารคดีทุกเรื่อง ส่วนแท็บค้นฟุตเทจสร้างรายงานจาก Narration Beats ของ P.T.; ยังไม่มีปุ่มสร้างสารคดีเรื่องใหม่หรือเรนเดอร์ทั้งเรื่องในครั้งเดียว

## CachyOS / Arch Linux — แนะนำสำหรับเครื่องนี้

1. แตก ZIP ไปไว้ในโฟลเดอร์ที่เขียนไฟล์ได้ เช่น `~/GMK/`
2. เปิด Terminal ในโฟลเดอร์ repo `gmk-complete-documentary`
3. รัน `./INSTALL_GMK.sh`
4. หลังติดตั้ง เปิด **GMK P.T. Operator** จากเมนูแอป หรือรัน `./START_GMK.sh`

ตัว installer ใช้ `pacman` และติดตั้งเฉพาะ dependency ที่ขาด: `python`, `tk`, `ffmpeg`, `python-jsonschema`, `python-yaml` โดยไม่ใช้ `pip install -e .`

ดูขั้นตอนละเอียดที่ `QUICK_START_CACHYOS_TH.md`

## Windows

Windows launcher เดิมยังคงรองรับ:

1. `INSTALL_GMK.cmd` ครั้งแรก
2. `START_GMK.cmd` ครั้งต่อไป

## จากหน้าโปรแกรม

- ดู P.T. readiness และ manifest state
- เลือกวิดีโอ Lisa/TGA ให้โปรแกรม copy เข้า source-locked slot ที่ถูกต้อง
- กรอก human inspection โดยไม่แก้ JSON เอง
- รัน authoritative preflight
- Execute media เมื่อสถานะเป็น `READY_TO_EXECUTE`
- รัน Quick Audit / System Check

## ขอบเขตความปลอดภัย

- โปรแกรมไม่ดาวน์โหลด media ต้นทางเอง
- ชื่อไฟล์ไม่ถือเป็นหลักฐานว่า content ถูกต้อง
- Human inspection ยังจำเป็น
- `Execute Media` ต้องได้รับการยืนยันจากผู้ใช้ และหยุดที่ `VISUAL_COVERAGE_READY`
- Voice / Design / HTML / Production Lock / Delivery approvals ยังเป็น Human Approval แยกเหมือนเดิม

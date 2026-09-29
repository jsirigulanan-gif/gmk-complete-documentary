# GMK P.T. Operator — เริ่มใช้บน CachyOS

แพ็ก Build 044 รองรับ **CachyOS / Arch Linux แบบ native** ไม่ต้องใช้ `.cmd` และไม่ต้องติดตั้ง GMK ด้วย `pip install -e .`

## ครั้งแรก

1. แตก ZIP ไปไว้ในโฟลเดอร์ที่คุณเขียนไฟล์ได้ เช่น `~/GMK/`
2. เปิด Terminal ในโฟลเดอร์ repo `gmk-complete-documentary`
3. รัน:

```bash
chmod +x INSTALL_GMK.sh START_GMK.sh
./INSTALL_GMK.sh
```

ตัวติดตั้งจะใช้ `pacman` เพื่อตรวจ/ติดตั้ง:

- `python`
- `tk`
- `ffmpeg` (รวม `ffprobe`)
- `yt-dlp` (ค้น metadata/caption และ acquire footage ที่เข้าถึงได้)
- `python-jsonschema`
- `python-yaml`
- `python-pytest` (สำหรับ QUICK audit)

จากนั้นจะเพิ่ม **GMK P.T. Operator** เข้าเมนูแอปของ desktop environment และสร้าง launcher ที่ `~/.local/bin/gmk-pt-operator`

## เปิดครั้งต่อไป

เปิด **GMK P.T. Operator** จากเมนูแอป หรือรัน:

```bash
./START_GMK.sh
```

## ใส่วิดีโอ Lisa / TGA

ใช้ปุ่ม **เลือกวิดีโอ** ในแท็บ Lisa/TGA ของ GUI ได้เลย โปรแกรมจะ copy เข้า source-locked slot ที่ถูกต้องให้ ไม่จำเป็นต้องลากไฟล์เอง

จากนั้นกรอก human inspection ให้ครบ แล้วทำตามลำดับ:

`Refresh Readiness → Preflight → Execute Media`

ระบบจะไม่ mutate P.T. workspace จนกว่าคุณยืนยัน Execute และ preflight ผ่าน

## Documentary Maker — ค้นฟุตเทจอัตโนมัติ

ใน GUI เปิดแท็บ **Documentary Maker** แล้วใช้ตามลำดับ:

1. **สร้าง Footage Search Plan** — อ่าน Narration Beat และ Visual Requirement เพื่อสร้างคำค้น
2. **ค้น YouTube + Timestamp** — ค้น candidate, rank, อ่าน caption/auto-caption และเสนอช่วงเวลา
3. ระบบยึด priority: **YouTube → Web/Archive video → Still/Document → AI last**

ระบบจะไม่ใช้ metadata อย่างเดียวเป็นหลักฐานว่าภาพตรง ถ้าคลิปไม่มี transcript/visual evidence พอ จะคงสถานะ inspection-required ไว้ก่อน

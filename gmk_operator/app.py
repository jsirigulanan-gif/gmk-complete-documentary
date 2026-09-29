from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Callable
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import threading
import traceback

from gmk_pilot import PilotReadinessRuntime, PilotMediaProcessRuntime
from gmk_runtime.cold_start import ColdStartLoader
from gmk_runtime.media_tools import resolve_ffprobe, MediaToolNotFound
from gmk_audit import AuditRuntime
from gmk_footage.query_planner import FootageQueryPlanner
from gmk_footage.research import FootageResearchRuntime
from gmk_footage.fallback_research import MaterialFallbackResearchRuntime

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "pilot" / "PT_WORKSPACE"
INTAKE = ROOT / "pilot" / "PT_MEDIA_INTAKE"
WORKSHEET = INTAKE / "PT_MEDIA_INSPECTION_WORKSHEET.json"
OUTPUT_DIR = ROOT / "pilot" / "PT_OPERATOR_OUTPUT"
FOOTAGE_OUTPUT = ROOT / "pilot" / "PT_FOOTAGE_RESEARCH"
CONFIG_DIR = ROOT / "operator"
CONFIG_PATH = CONFIG_DIR / "GMK_OPERATOR_CONFIG.json"

CANDIDATES = ("LISA_X_DIRECT_VERIFIED", "TGA_VIDEO")


def _json_load(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Expected object JSON: {path}")
    return raw


def _json_write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_config() -> dict[str, Any]:
    if not CONFIG_PATH.is_file():
        return {}
    try:
        raw = _json_load(CONFIG_PATH)
        return raw
    except Exception:
        return {}


def _save_config(payload: dict[str, Any]) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _json_write(CONFIG_PATH, payload)


def apply_operator_config() -> dict[str, Any]:
    cfg = _load_config()
    ffprobe = str(cfg.get("ffprobe_path") or "").strip()
    if ffprobe:
        os.environ["GMK_FFPROBE"] = ffprobe
    return cfg


def system_check() -> dict[str, Any]:
    apply_operator_config()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = None) -> None:
        row = {"check": name, "ok": bool(ok)}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)

    py_ok = sys.version_info >= (3, 10)
    add("python_3_10_plus", py_ok, sys.version.split()[0])
    add("workspace_present", WORKSPACE.is_dir(), str(WORKSPACE))
    add("intake_present", INTAKE.is_dir(), str(INTAKE))
    add("worksheet_present", WORKSHEET.is_file(), str(WORKSHEET))
    try:
        tool = resolve_ffprobe()
        add("ffprobe", True, tool)
    except Exception as exc:
        add("ffprobe", False, str(exc))
    yt = shutil.which("yt-dlp")
    add("yt_dlp", bool(yt), yt or "not found — run INSTALL_GMK.sh")
    try:
        import tkinter  # noqa: F401
        add("tkinter", True, "available")
    except Exception as exc:
        add("tkinter", False, str(exc))
    return {
        "build": "042",
        "platform": platform.platform(),
        "ok": all(x["ok"] for x in checks),
        "checks": checks,
    }


def headless_status() -> dict[str, Any]:
    apply_operator_config()
    result = PilotReadinessRuntime(ROOT, WORKSPACE).inspect(INTAKE, OUTPUT_DIR)
    return result.to_dict()


def _open_path(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def _worksheet_items() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    raw = _json_load(WORKSHEET)
    by: dict[str, dict[str, Any]] = {}
    for item in raw.get("items") or []:
        key = str(item.get("candidate_key") or "")
        if key:
            by[key] = item
    return raw, by


class OperatorApp:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title("GMK Complete Documentary Maker — Build 042")
        self.root.geometry("980x720")
        self.root.minsize(860, 640)
        self.cfg = apply_operator_config()
        self._busy = False
        self.status_var = tk.StringVar(value="กำลังตรวจสถานะ…")
        self.state_var = tk.StringVar(value="-")
        self.version_var = tk.StringVar(value="-")
        self.next_var = tk.StringVar(value="-")
        self.slot_vars: dict[str, dict[str, Any]] = {}
        self._build_ui()
        self.root.after(150, self.refresh_readiness)

    def _build_ui(self) -> None:
        tk = self.tk
        ttk = self.ttk
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="GMK P.T. Operator", font=("Segoe UI", 18, "bold"))
        title.pack(anchor="w")
        ttk.Label(
            outer,
            text="Build 042 — Complete Documentary Maker / YouTube-first Footage Research / Auto Editing Core",
        ).pack(anchor="w", pady=(0, 10))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)

        self.dashboard = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(self.dashboard, text="สถานะ")
        self._build_dashboard(self.dashboard)

        documentary = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(documentary, text="Documentary Maker")
        self._build_documentary_tab(documentary)

        for key, label in (("LISA_X_DIRECT_VERIFIED", "Lisa camera hack"), ("TGA_VIDEO", "TGA stage statement")):
            frame = ttk.Frame(self.notebook, padding=12)
            self.notebook.add(frame, text=label)
            self._build_candidate_tab(frame, key)

        system = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(system, text="ระบบ")
        self._build_system_tab(system)

        logs = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(logs, text="Log")
        self.log = tk.Text(logs, wrap="word", height=20)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        self.footer = ttk.Label(outer, textvariable=self.status_var, anchor="w")
        self.footer.pack(fill="x", pady=(8, 0))

    def _build_dashboard(self, parent) -> None:
        ttk = self.ttk
        grid = ttk.Frame(parent)
        grid.pack(fill="x")
        rows = [
            ("Readiness", self.state_var),
            ("Manifest", self.version_var),
            ("ขั้นถัดไป", self.next_var),
        ]
        for r, (label, var) in enumerate(rows):
            ttk.Label(grid, text=label, font=("Segoe UI", 10, "bold")).grid(row=r, column=0, sticky="nw", padx=(0, 12), pady=4)
            ttk.Label(grid, textvariable=var, wraplength=730).grid(row=r, column=1, sticky="nw", pady=4)
        grid.columnconfigure(1, weight=1)

        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=12)
        ttk.Button(actions, text="Refresh readiness", command=self.refresh_readiness).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Preflight", command=self.run_preflight).pack(side="left", padx=6)
        ttk.Button(actions, text="Execute media", command=self.execute_media).pack(side="left", padx=6)
        ttk.Button(actions, text="เปิด intake folder", command=lambda: _open_path(INTAKE)).pack(side="left", padx=6)

        ttk.Separator(parent).pack(fill="x", pady=8)
        ttk.Label(parent, text="Media slots", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.slot_summary = ttk.Frame(parent)
        self.slot_summary.pack(fill="x", pady=6)

        ttk.Label(
            parent,
            text=(
                "Execute จะเปิดได้อย่างปลอดภัยเมื่อ readiness เป็น READY_TO_EXECUTE เท่านั้น "
                "และจะพา P.T. ไปถึง VISUAL_COVERAGE_READY โดยยังไม่ข้าม Human Approval ขั้นถัดไป"
            ),
            wraplength=820,
        ).pack(anchor="w", pady=(8, 0))

    def _build_candidate_tab(self, parent, key: str) -> None:
        tk = self.tk
        ttk = self.ttk
        raw, items = _worksheet_items()
        item = items.get(key, {})
        vars_: dict[str, Any] = {
            "operator": tk.StringVar(value=str(item.get("operator") or "")),
            "start_seconds": tk.StringVar(value="" if item.get("start_seconds") is None else str(item.get("start_seconds"))),
            "end_seconds": tk.StringVar(value="" if item.get("end_seconds") is None else str(item.get("end_seconds"))),
            "key_seconds": tk.StringVar(value="" if item.get("key_seconds") is None else str(item.get("key_seconds"))),
            "source_url": tk.StringVar(value=str(item.get("source_url") or "")),
        }
        self.slot_vars[key] = vars_

        ttk.Label(parent, text=key, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(parent, textvariable=vars_["source_url"], wraplength=760).grid(row=1, column=0, columnspan=3, sticky="w", pady=(2, 8))

        buttons = ttk.Frame(parent)
        buttons.grid(row=2, column=0, columnspan=3, sticky="w", pady=(0, 10))
        ttk.Button(buttons, text="เลือกวิดีโอ…", command=lambda k=key: self.select_video(k)).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="เปิดโฟลเดอร์", command=lambda k=key: _open_path(INTAKE / k)).pack(side="left", padx=6)
        ttk.Button(buttons, text="บันทึก inspection", command=lambda k=key: self.save_inspection(k)).pack(side="left", padx=6)

        fields = [
            ("Operator", "operator"),
            ("Start (sec)", "start_seconds"),
            ("End (sec)", "end_seconds"),
            ("Key (sec, optional)", "key_seconds"),
        ]
        row = 3
        for label, name in fields:
            ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Entry(parent, textvariable=vars_[name], width=36).grid(row=row, column=1, sticky="ew", pady=4)
            row += 1

        ttk.Label(parent, text="Visual content").grid(row=row, column=0, sticky="nw", pady=4)
        visual = tk.Text(parent, height=5, wrap="word")
        visual.insert("1.0", str(item.get("visual_content") or ""))
        visual.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=4)
        vars_["visual_content_widget"] = visual
        row += 1

        ttk.Label(parent, text="Match reason").grid(row=row, column=0, sticky="nw", pady=4)
        reason = tk.Text(parent, height=5, wrap="word")
        reason.insert("1.0", str(item.get("match_reason") or ""))
        reason.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=4)
        vars_["match_reason_widget"] = reason
        row += 1

        ttk.Label(parent, text="Inspection note").grid(row=row, column=0, sticky="nw", pady=4)
        note = tk.Text(parent, height=5, wrap="word")
        note.insert("1.0", str(item.get("inspection_note") or ""))
        note.grid(row=row, column=1, columnspan=2, sticky="nsew", pady=4)
        vars_["inspection_note_widget"] = note
        row += 1

        ttk.Label(
            parent,
            text="กรอกข้อมูลจากการดูไฟล์จริงเท่านั้น โดยเฉพาะช่วงเวลาและเหตุผลที่ยืนยันว่า media ตรงกับ source lock",
            wraplength=760,
        ).grid(row=row, column=0, columnspan=3, sticky="w", pady=(8, 0))
        parent.columnconfigure(1, weight=1)
        parent.rowconfigure(row - 3, weight=1)
        parent.rowconfigure(row - 2, weight=1)
        parent.rowconfigure(row - 1, weight=1)


    def _build_documentary_tab(self, parent) -> None:
        ttk=self.ttk
        ttk.Label(parent,text="Complete Documentary Maker — Footage Research",font=("Segoe UI",14,"bold")).pack(anchor="w")
        ttk.Label(parent,text="ลำดับวัตถุดิบ: YouTube → Web/Archive Video → Still/Document → AI (last resort)",wraplength=800).pack(anchor="w",pady=(2,10))
        actions=ttk.Frame(parent);actions.pack(fill="x",pady=(0,10))
        ttk.Button(actions,text="1. สร้าง Footage Search Plan",command=self.generate_footage_plan).pack(side="left",padx=(0,6))
        ttk.Button(actions,text="2. ค้น YouTube + Timestamp",command=self.run_footage_research).pack(side="left",padx=6)
        ttk.Button(actions,text="3. ค้นต่อ Web / Still",command=self.run_material_research).pack(side="left",padx=6)
        ttk.Button(actions,text="เปิดโฟลเดอร์ผลลัพธ์",command=lambda:_open_path(FOOTAGE_OUTPUT)).pack(side="left",padx=6)
        self.footage_text=self.tk.Text(parent,height=24,wrap="word");self.footage_text.pack(fill="both",expand=True)
        self.footage_text.insert("1.0","ยังไม่ได้รัน Footage Research\n")
        self.footage_text.configure(state="disabled")

    def _show_footage_result(self, payload) -> None:
        if hasattr(payload,'to_dict'): payload=payload.to_dict()
        self.footage_text.configure(state="normal");self.footage_text.delete("1.0","end")
        self.footage_text.insert("1.0",json.dumps(payload,ensure_ascii=False,indent=2,sort_keys=True))
        self.footage_text.configure(state="disabled")

    def generate_footage_plan(self) -> None:
        def run():
            FOOTAGE_OUTPUT.mkdir(parents=True,exist_ok=True)
            payload=FootageQueryPlanner(ROOT,WORKSPACE).build().to_dict()
            _json_write(FOOTAGE_OUTPUT/'FOOTAGE_QUERY_PLAN.json',payload)
            return payload
        self._async("กำลังสร้าง Footage Search Plan…",run,self._show_footage_result)

    def run_footage_research(self) -> None:
        def run():
            FOOTAGE_OUTPUT.mkdir(parents=True,exist_ok=True)
            report=FootageResearchRuntime(ROOT,WORKSPACE).run(per_query=5,inspect_top=3,timestamp_top=3).to_dict()
            _json_write(FOOTAGE_OUTPUT/'FOOTAGE_RESEARCH_REPORT.json',report)
            return report
        self._async("กำลังค้น YouTube และวิเคราะห์ timestamp…",run,self._show_footage_result)

    def run_material_research(self) -> None:
        def run():
            FOOTAGE_OUTPUT.mkdir(parents=True,exist_ok=True)
            youtube=FootageResearchRuntime(ROOT,WORKSPACE).run(per_query=5,inspect_top=3,timestamp_top=3)
            material=MaterialFallbackResearchRuntime(ROOT,WORKSPACE).run(youtube,per_query=5)
            payload={'youtube':youtube.to_dict(),'material_fallback':material.to_dict()}
            _json_write(FOOTAGE_OUTPUT/'MATERIAL_RESEARCH_REPORT.json',payload)
            return payload
        self._async("กำลังค้น YouTube → Web/Archive → Still/Document…",run,self._show_footage_result)

    def _build_system_tab(self, parent) -> None:
        ttk = self.ttk
        self.system_text = self.tk.Text(parent, height=18, wrap="word")
        self.system_text.pack(fill="both", expand=True)
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="System check", command=self.refresh_system_check).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="เลือก ffprobe.exe…", command=self.choose_ffprobe).pack(side="left", padx=6)
        ttk.Button(actions, text="Quick Audit", command=self.run_audit).pack(side="left", padx=6)
        self.refresh_system_check()

    def log_line(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_busy(self, busy: bool, message: str = "") -> None:
        self._busy = busy
        self.status_var.set(message if message else ("กำลังทำงาน…" if busy else "พร้อม"))

    def _async(self, label: str, fn: Callable[[], Any], done: Callable[[Any], None] | None = None) -> None:
        from tkinter import messagebox
        if self._busy:
            messagebox.showinfo("GMK", "มีงานกำลังทำอยู่ กรุณารอให้งานปัจจุบันจบก่อน")
            return
        self._set_busy(True, label)
        self.log_line(f"> {label}")

        def worker() -> None:
            try:
                result = fn()
            except Exception as exc:
                tb = traceback.format_exc()
                self.root.after(0, lambda: self._async_error(label, exc, tb))
                return
            self.root.after(0, lambda: self._async_done(label, result, done))

        threading.Thread(target=worker, daemon=True).start()

    def _async_error(self, label: str, exc: Exception, tb: str) -> None:
        from tkinter import messagebox
        self._set_busy(False, "เกิดข้อผิดพลาด")
        self.log_line(tb)
        messagebox.showerror("GMK", f"{label}\n\n{type(exc).__name__}: {exc}")

    def _async_done(self, label: str, result: Any, done: Callable[[Any], None] | None) -> None:
        self._set_busy(False, "พร้อม")
        if hasattr(result, "to_dict"):
            payload = result.to_dict()
        elif isinstance(result, dict):
            payload = result
        else:
            payload = {"result": str(result)}
        self.log_line(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        if done:
            done(result)

    def refresh_readiness(self) -> None:
        def run():
            return PilotReadinessRuntime(ROOT, WORKSPACE).inspect(INTAKE, OUTPUT_DIR)
        self._async("กำลังตรวจ readiness…", run, self._display_readiness)

    def _display_readiness(self, result) -> None:
        self.state_var.set(result.readiness)
        self.version_var.set(f"{result.project_state} / manifest v{result.manifest_version}")
        self.next_var.set(result.next_action)
        for w in self.slot_summary.winfo_children():
            w.destroy()
        for idx, slot in enumerate(result.slots):
            key = slot["candidate_key"]
            text = f"{key}: media={slot['media_state']} | inspection={'OK' if slot['inspection_complete'] else 'INCOMPLETE'}"
            self.ttk.Label(self.slot_summary, text=text).grid(row=idx, column=0, sticky="w", pady=2)

    def select_video(self, key: str) -> None:
        from tkinter import filedialog, messagebox
        selected = filedialog.askopenfilename(
            title=f"เลือกวิดีโอสำหรับ {key}",
            filetypes=[("Video files", "*.mp4 *.mov *.mkv *.webm *.m4v *.avi"), ("All files", "*.*")],
        )
        if not selected:
            return
        src = Path(selected)
        slot = INTAKE / key
        slot.mkdir(parents=True, exist_ok=True)
        existing = [p for p in slot.iterdir() if p.is_file() and p.name not in {"README.txt", ".DS_Store", "Thumbs.db"} and not p.name.startswith(".")]
        if existing:
            if not messagebox.askyesno("แทนที่ไฟล์?", f"slot นี้มี {existing[0].name} อยู่แล้ว\nต้องการแทนที่ด้วย {src.name} หรือไม่?"):
                return
            for p in existing:
                p.unlink()
        dest = slot / src.name
        shutil.copy2(src, dest)
        self.log_line(f"Copied {src} -> {dest}")
        messagebox.showinfo("GMK", f"ใส่ไฟล์ใน slot แล้ว:\n{dest.name}")
        self.refresh_readiness()

    @staticmethod
    def _float_or_none(text: str) -> float | None:
        text = text.strip()
        if not text:
            return None
        return float(text)

    def save_inspection(self, key: str) -> None:
        from tkinter import messagebox
        raw, items = _worksheet_items()
        if key not in items:
            messagebox.showerror("GMK", f"ไม่พบ inspection entry: {key}")
            return
        item = items[key]
        v = self.slot_vars[key]
        try:
            item["operator"] = v["operator"].get().strip()
            item["start_seconds"] = self._float_or_none(v["start_seconds"].get())
            item["end_seconds"] = self._float_or_none(v["end_seconds"].get())
            item["key_seconds"] = self._float_or_none(v["key_seconds"].get())
        except ValueError:
            messagebox.showerror("GMK", "Start / End / Key ต้องเป็นตัวเลขวินาที")
            return
        item["visual_content"] = v["visual_content_widget"].get("1.0", "end").strip()
        item["match_reason"] = v["match_reason_widget"].get("1.0", "end").strip()
        item["inspection_note"] = v["inspection_note_widget"].get("1.0", "end").strip()
        _json_write(WORKSHEET, raw)
        self.log_line(f"Saved inspection: {key}")
        messagebox.showinfo("GMK", "บันทึก inspection แล้ว")
        self.refresh_readiness()

    def run_preflight(self) -> None:
        from tkinter import messagebox
        def run():
            inspection = _json_load(WORKSHEET)
            return PilotMediaProcessRuntime(ROOT, WORKSPACE).run(INTAKE, inspection, execute=False, output_dir=OUTPUT_DIR)
        def done(result):
            messagebox.showinfo("GMK", "Preflight ผ่าน" if result.ready else "Preflight ยังไม่พร้อม")
            self.refresh_readiness()
        self._async("กำลังรัน preflight…", run, done)

    def execute_media(self) -> None:
        from tkinter import messagebox
        try:
            readiness = PilotReadinessRuntime(ROOT, WORKSPACE).inspect(INTAKE, OUTPUT_DIR)
        except Exception as exc:
            messagebox.showerror("GMK", str(exc))
            return
        if readiness.readiness == "ALREADY_ADVANCED":
            messagebox.showinfo("GMK", "P.T. ผ่าน media stage แล้ว ไม่ต้อง import ซ้ำ")
            return
        if not readiness.ready_to_execute:
            messagebox.showwarning("GMK", f"ยัง Execute ไม่ได้\n\nสถานะ: {readiness.readiness}\n{readiness.next_action}")
            return
        if not messagebox.askyesno(
            "ยืนยัน Execute",
            "ไฟล์และ inspection ผ่าน authoritative preflight แล้ว\n\n"
            "Execute จะ mutate PT_WORKSPACE และพาโปรเจกต์ผ่าน Asset Catalog / Visual Coverage\n"
            "โดยจะหยุดก่อน Human Approval ขั้นถัดไป\n\nยืนยันหรือไม่?",
        ):
            return
        def run():
            inspection = _json_load(WORKSHEET)
            return PilotMediaProcessRuntime(ROOT, WORKSPACE).run(INTAKE, inspection, execute=True, output_dir=OUTPUT_DIR)
        def done(result):
            messagebox.showinfo("GMK", f"Execute เสร็จ\nProject state: {result.project_state}")
            self.refresh_readiness()
        self._async("กำลัง Execute P.T. media…", run, done)

    def refresh_system_check(self) -> None:
        payload = system_check()
        self.system_text.configure(state="normal")
        self.system_text.delete("1.0", "end")
        self.system_text.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2))
        self.system_text.configure(state="disabled")

    def choose_ffprobe(self) -> None:
        from tkinter import filedialog, messagebox
        selected = filedialog.askopenfilename(
            title="เลือก ffprobe executable",
            filetypes=[("ffprobe", "ffprobe.exe" if os.name == "nt" else "ffprobe"), ("All files", "*.*")],
        )
        if not selected:
            return
        cfg = _load_config()
        cfg["ffprobe_path"] = str(Path(selected).resolve())
        _save_config(cfg)
        os.environ["GMK_FFPROBE"] = cfg["ffprobe_path"]
        try:
            resolved = resolve_ffprobe()
        except Exception as exc:
            messagebox.showerror("GMK", f"ใช้ ffprobe ไม่ได้: {exc}")
        else:
            messagebox.showinfo("GMK", f"ตั้งค่า ffprobe แล้ว:\n{resolved}")
        self.refresh_system_check()

    def run_audit(self) -> None:
        from tkinter import messagebox
        def run():
            return AuditRuntime(ROOT).run(profile="QUICK", timeout_seconds=120)
        def done(result):
            messagebox.showinfo("GMK", f"Quick Audit\nPASS={result.pass_count} FAIL={result.fail_count} TIMEOUT={result.timeout_count} WARN={result.warn_count}")
        self._async("กำลังรัน Quick Audit…", run, done)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gmk-operator", description="GMK P.T. desktop operator surface")
    p.add_argument("--headless-status", action="store_true", help="Print readiness JSON without opening a GUI.")
    p.add_argument("--system-check", action="store_true", help="Print Windows/runtime dependency check JSON.")
    p.add_argument("--json", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if args.system_check:
        payload = system_check()
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if payload["ok"] else 2
    if args.headless_status:
        try:
            payload = headless_status()
        except Exception as exc:
            print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if payload.get("ready_to_execute") or payload.get("readiness") == "ALREADY_ADVANCED" else 2
    check = system_check()
    if not check["ok"]:
        # A GUI can still launch so the operator can select ffprobe from the System tab,
        # but missing Python/Tk/workspace is fatal.
        fatal = [x for x in check["checks"] if not x["ok"] and x["check"] != "ffprobe"]
        if fatal:
            print(json.dumps(check, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
    return OperatorApp().run()

from __future__ import annotations

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

from gmk_runtime.media_tools import resolve_ffprobe
from gmk_audit import AuditRuntime

ROOT = Path(__file__).resolve().parents[1]
BUILD = json.loads((ROOT / "BUILD_STATUS.json").read_text(encoding="utf-8"))["build"]
CONFIG_DIR = ROOT / "operator"
CONFIG_PATH = CONFIG_DIR / "GMK_OPERATOR_CONFIG.json"


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
    edge_tts = str(cfg.get('edge_tts_path') or '').strip()
    if edge_tts:
        os.environ['GMK_EDGE_TTS'] = edge_tts
    return cfg


def system_check() -> dict[str, Any]:
    apply_operator_config()
    checks: list[dict[str, Any]] = []

    def add(name: str, ok: bool, detail: Any = None, *, required=True) -> None:
        row = {"check": name, "ok": bool(ok), "required": required}
        if detail is not None:
            row["detail"] = detail
        checks.append(row)

    py_ok = sys.version_info >= (3, 10)
    add("python_3_10_plus", py_ok, sys.version.split()[0])
    add("ffmpeg", bool(shutil.which('ffmpeg')), shutil.which('ffmpeg'))
    try:
        tool = resolve_ffprobe()
        add("ffprobe", True, tool)
    except Exception as exc:
        add("ffprobe", False, str(exc))
    yt = shutil.which("yt-dlp")
    add("yt_dlp", bool(yt), yt or "not found — run INSTALL_GMK.sh", required=False)
    for name, executable in (('drive_sync', 'rclone'), ('story_ai', 'codex'), ('online_voice', 'edge-tts')):
        found = shutil.which(executable)
        add(name, bool(found), found or 'not installed', required=False)
    try:
        import tkinter  # noqa: F401
        add("tkinter", True, "available")
    except Exception as exc:
        add("tkinter", False, str(exc))
    return {
        "build": BUILD,
        "platform": platform.platform(),
        "ok": all(x["ok"] for x in checks if x['required']),
        "checks": checks,
    }


def headless_status(project: Path | None = None, *, base: Path | None = None) -> dict[str, Any]:
    apply_operator_config()
    from gmk_projects.storage import Project
    from gmk_projects.production import ProductionProject
    if project is not None:
        return ProductionProject(Project(project)).status()
    base = base or Path.home() / 'GMK Projects'
    return {'projects': [{'path': str(p.parent), 'title': Project(p.parent).read()['title']}
                         for p in sorted(base.glob('project-*/project.json'))], 'workspace_mutated': False}


class OperatorApp:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title(f"GMK Complete Documentary Maker — Build {BUILD}")
        self.root.geometry("980x720")
        self.root.minsize(860, 640)
        self.cfg = apply_operator_config()
        self._busy = False
        self.status_var = tk.StringVar(value="กำลังตรวจสถานะ…")
        self._build_ui()
        self.status_var.set('พร้อม — เลือกโปรเจกต์และเปิดโต๊ะตัดต่อเพื่อทำงานต่อ')

    def _build_ui(self) -> None:
        tk = self.tk
        ttk = self.ttk
        outer = ttk.Frame(self.root, padding=14)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="GMK Documentary Maker", font=("Segoe UI", 18, "bold"))
        title.pack(anchor="w")
        ttk.Label(
            outer,
            text=f"Build {BUILD} — รีเสิร์ช บท ภาพ เสียง ตัดต่อ และวิดีโอสารคดี",
        ).pack(anchor="w", pady=(0, 10))

        self.notebook = ttk.Notebook(outer)
        self.notebook.pack(fill="both", expand=True)

        projects = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(projects, text="โปรเจกต์สารคดี")
        from .projects import ProjectsPanel
        self.projects_panel = ProjectsPanel(self, projects)

        system = ttk.Frame(self.notebook, padding=12)
        self.notebook.add(system, text="ตั้งค่าและตรวจระบบ")
        self._build_system_tab(system)

        self.footer = ttk.Label(outer, textvariable=self.status_var, anchor="w")
        self.footer.pack(fill="x", pady=(8, 0))


    def _build_system_tab(self, parent) -> None:
        ttk = self.ttk
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="ตรวจเครื่องมือ", command=self.refresh_system_check).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="เลือก ffprobe…", command=self.choose_ffprobe).pack(side="left", padx=6)
        ttk.Button(actions, text="ตรวจโปรแกรม", command=self.run_audit).pack(side="left", padx=6)
        self.system_text = self.tk.Text(parent, height=12, wrap="word")
        self.system_text.pack(fill="both", expand=True, pady=8)
        ttk.Label(parent, text='รายละเอียดเมื่อเกิดข้อผิดพลาด').pack(anchor='w')
        self.log = self.tk.Text(parent, wrap='word', height=7, state='disabled')
        self.log.pack(fill='both', expand=True)
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
                self.root.after(0, lambda error=exc, detail=tb: self._async_error(label, error, detail))
                return
            self.root.after(0, lambda: self._async_done(label, result, done))

        threading.Thread(target=worker, daemon=True).start()

    def _async_error(self, label: str, exc: Exception, tb: str) -> None:
        from tkinter import messagebox
        self._set_busy(False, "เกิดข้อผิดพลาด")
        self.log_line(tb)
        if hasattr(self, 'projects_panel') and self.projects_panel.selection.current() >= 0:
            self.projects_panel.show()
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


    def refresh_system_check(self) -> None:
        payload = system_check()
        names = {'python_3_10_plus': 'Python', 'ffmpeg': 'ประกอบและเรนเดอร์วิดีโอ', 'ffprobe': 'อ่านข้อมูลภาพและเสียง',
                 'yt_dlp': 'ค้นและดาวน์โหลดฟุตเทจ', 'drive_sync': 'ส่งไฟล์ไป Google Drive',
                 'story_ai': 'สร้างโครงเรื่องด้วยบัญชี Codex', 'online_voice': 'สร้างเสียงฟรีผ่าน Edge TTS',
                 'tkinter': 'หน้าจอโปรแกรม'}
        lines = ['เครื่องมือสำหรับโปรเจกต์สารคดี', '']
        for row in payload['checks']:
            lines.append(('✓ พร้อม · ' if row['ok'] else 'ต้องติดตั้ง · ')+names[row['check']])
            if not row['ok']: lines.append('  '+str(row.get('detail') or 'ใช้ INSTALL_GMK เพื่อเตรียมเครื่องมือ'))
        lines += ['', 'เครื่องมือออนไลน์ที่ติดตั้งแล้ว ยังต้องเชื่อมบัญชีและมีโควตาที่ใช้ได้']
        self.system_text.configure(state="normal")
        self.system_text.delete("1.0", "end")
        self.system_text.insert("1.0", '\n'.join(lines))
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
            messagebox.showinfo("GMK", f"Quick Audit\nPASS={result.pass_count} FAIL={result.fail_count} TIMEOUT={result.timeout_count} WARN={result.warning_count}")
        self._async("กำลังรัน Quick Audit…", run, done)

    def run(self) -> int:
        self.root.mainloop()
        return 0


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="gmk-operator", description="GMK documentary project workspace")
    p.add_argument("--headless-status", action="store_true", help="List user projects or inspect --project without opening a GUI.")
    p.add_argument("--project", type=Path, help="Project directory for --headless-status.")
    p.add_argument("--system-check", action="store_true", help="Print local production-tool checks.")
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
            payload = headless_status(args.project)
        except Exception as exc:
            print(json.dumps({"error": type(exc).__name__, "message": str(exc)}, ensure_ascii=False, indent=2))
            return 2
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    check = system_check()
    if not check["ok"]:
        # Tool setup is available in the GUI; only Python/Tk are needed to open it.
        fatal = [x for x in check["checks"] if not x["ok"] and x['check'] in {'python_3_10_plus', 'tkinter'}]
        if fatal:
            print(json.dumps(check, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
    return OperatorApp().run()

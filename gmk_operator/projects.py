from pathlib import Path
import tempfile
from tkinter import filedialog, messagebox

from gmk_projects.intake import import_research, read_source
from gmk_projects.storage import Project, RcloneDrive


class ProjectsPanel:
    def __init__(self, app, parent):
        self.app, self.base = app, Path.home() / 'GMK Projects'
        self.scripts, self.projects = [], []
        tk, ttk = app.tk, app.ttk
        ttk.Label(parent, text='โปรเจกต์สารคดีบน Google Drive', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(parent, text='นำเข้ารีเสิร์ช แล้วเปิดโต๊ะตัดต่อเพื่อสร้างเรื่อง แก้บท ค้นภาพ ใส่เสียงและดนตรี เรนเดอร์ และส่งออก',
                  wraplength=800).pack(anchor='w', pady=6)
        ttk.Button(parent, text='ค้นเอกสาร LEMiNO Script ใน Drive', command=self.search).pack(anchor='w')
        self.sources = ttk.Combobox(parent, state='readonly', width=95)
        self.sources.pack(fill='x', pady=6)
        row = ttk.Frame(parent)
        row.pack(fill='x')
        ttk.Button(row, text='สร้างโปรเจกต์จากเอกสารที่เลือก', command=self.import_drive).pack(side='left')
        ttk.Button(row, text='นำเข้าไฟล์บทจากเครื่อง', command=self.import_local).pack(side='left', padx=6)
        ttk.Separator(parent).pack(fill='x', pady=12)
        ttk.Label(parent, text='โปรเจกต์ของคุณ').pack(anchor='w')
        self.selection = ttk.Combobox(parent, state='readonly', width=95)
        self.selection.pack(fill='x', pady=6)
        self.selection.bind('<<ComboboxSelected>>', lambda event: self.show())
        row = ttk.Frame(parent)
        row.pack(fill='x')
        self.roles = {'ฟุตเทจต้นฉบับ': 'footage', 'เสียงพากย์': 'voice', 'ดนตรี': 'music',
                      'บทและรีเสิร์ช': 'research', 'ไฟล์ตัดต่อ': 'timeline', 'วิดีโอส่งออก': 'exports'}
        self.role = ttk.Combobox(row, state='readonly', values=list(self.roles), width=18)
        self.role.current(0)
        self.role.pack(side='left')
        ttk.Button(row, text='เพิ่มไฟล์', command=self.add_file).pack(side='left', padx=6)
        ttk.Button(row, text='ส่งไฟล์และตรวจสอบบน Drive', command=self.sync).pack(side='left')
        ttk.Button(row, text='รีเฟรช', command=self.reload).pack(side='left', padx=6)
        self.connect_button = ttk.Button(row, text='เชื่อมโปรเจกต์รุ่นเดิม', command=self.connect_production)
        research_row = ttk.Frame(parent)
        research_row.pack(fill='x', pady=6)
        ttk.Button(research_row, text='แยกข้อกล่าวอ้างจากรีเสิร์ช', command=self.analyze_research).pack(side='left')
        ttk.Button(research_row, text='เปิดรายการตรวจรีเสิร์ช', command=self.review_research).pack(side='left', padx=6)
        ttk.Button(research_row, text='เปิดโต๊ะตัดต่อสารคดี', command=self.open_editor).pack(side='left')
        self.details = tk.Text(parent, height=12, wrap='word', state='disabled')
        self.details.pack(fill='both', expand=True, pady=10)
        self.reload()

    def reload(self, selected=None):
        self.projects = [Project(p.parent) for p in sorted(self.base.glob('project-*/project.json'))]
        self.selection['values'] = [p.read()['title'] for p in self.projects]
        if self.projects:
            index = next((i for i, p in enumerate(self.projects) if selected and p.root == selected.root), 0)
            self.selection.current(index)
            self.show()

    def current(self):
        index = self.selection.current()
        if index < 0:
            messagebox.showinfo('GMK', 'เลือกหรือสร้างโปรเจกต์ก่อนครับ')
            return None
        return self.projects[index]

    def show(self):
        p = self.current()
        if p is None:
            return
        data = p.read()
        research_label = 'ยังไม่มีข้อมูลตรวจรีเสิร์ช'
        from gmk_projects.production import ProductionProject
        try:
            production = ProductionProject(p).status()
            if production['connected']:
                self.connect_button.pack_forget()
            else:
                self.connect_button.pack(side='left')
            state_labels = {'NOT_CONNECTED': 'โปรเจกต์รุ่นเดิม — กดเชื่อมโปรเจกต์รุ่นเดิมเพื่อทำงานต่อ',
                            'BOOTSTRAPPED': 'ตั้งโปรเจกต์แล้ว — รอนำเข้ารีเสิร์ช',
                            'RESEARCH_INTAKE': 'รับรีเสิร์ชแล้ว — ขั้นถัดไปคือตรวจหลักฐานและข้อกล่าวอ้าง'}
            production_label = state_labels.get(production['production_state'], production['production_state'])
            if production['connected']:
                research_label = f'ข้อความรอตรวจ {production["unreviewed_claim_count"]} / ทั้งหมด {production["claim_count"]} รายการ'
        except Exception:
            production_label = 'อ่านสถานะการผลิตไม่ได้ — ต้องตรวจหรือกู้คืนข้อมูลก่อนทำงานต่อ'
        statuses = {'LOCAL_ONLY': 'ยังอยู่ในเครื่อง', 'PENDING_UPLOAD': 'มีไฟล์รอส่ง',
                    'UPLOADING': 'กำลังส่ง', 'UPLOAD_FAILED': 'ส่งไม่สำเร็จ — ไฟล์ยังอยู่ในเครื่อง กดส่งซ้ำได้',
                    'VERIFIED': 'ส่งและตรวจไฟล์ครบแล้ว'}
        lines = [data['title'], 'สถานะ Drive: ' + statuses.get(data['storage_status'], data['storage_status']),
                 'โฟลเดอร์ Drive: ' + data['drive']['root'] + '/' + data['project_id'],
                 'ในเครื่อง: ' + str(p.root),
                 'สถานะการผลิต: ' + production_label,
                 'รีเสิร์ช: ' + research_label,
                 'การส่งออกสารคดีครบกระบวนการ: ยังไม่ได้ยืนยัน', '']
        lines += [('✓ ' if a['upload_status'] == 'VERIFIED' else 'รอส่ง: ') + a['original_name'] for a in data['assets']]
        self.details.configure(state='normal')
        self.details.delete('1.0', 'end')
        self.details.insert('1.0', '\n'.join(lines))
        self.details.configure(state='disabled')

    def search(self):
        def done(rows):
            self.scripts = rows
            self.sources['values'] = [r['Name'] for r in rows]
            if rows:
                self.sources.current(0)
            else:
                messagebox.showinfo('GMK', 'ไม่พบเอกสาร LEMiNO Script ที่ราก Drive ในการเชื่อมต่อนี้')
        self.app._async('กำลังค้นเอกสารใน Drive…', RcloneDrive().list_scripts, done)

    def import_drive(self):
        index = self.sources.current()
        if index < 0:
            messagebox.showinfo('GMK', 'ค้นหาและเลือกเอกสารก่อนครับ')
            return
        source = self.scripts[index]
        def run():
            with tempfile.TemporaryDirectory(prefix='gmk-research-') as folder:
                doc = Path(folder) / 'research.docx'
                RcloneDrive().fetch_script(source['ID'], doc)
                read_source(doc)  # Reject failed/empty exports before creating a project.
                p = Project.create(self.base, source['Name'].removesuffix('.docx'),
                                   source_url='https://docs.google.com/document/d/' + source['ID'] + '/edit')
                import_research(p, doc)
                return p
        self.app._async('กำลังนำเข้าบท…', run, self.reload)

    def import_local(self):
        chosen = filedialog.askopenfilename(title='เลือกบทหรือรีเสิร์ช', filetypes=[('Research', '*.docx *.txt *.json')])
        if not chosen:
            return
        def run():
            text, _ = read_source(Path(chosen))
            p = Project.create(self.base, text.strip().splitlines()[0])
            import_research(p, Path(chosen))
            return p
        self.app._async('กำลังนำเข้าบท…', run, self.reload)

    def add_file(self):
        project = self.current()
        if not project:
            return
        chosen = filedialog.askopenfilename(title='เพิ่มไฟล์เข้าคลังโปรเจกต์')
        if chosen:
            role = self.roles[self.role.get()]
            self.app._async('กำลังเก็บไฟล์ในโปรเจกต์…', lambda: project.add_file(Path(chosen), role), lambda _: self.show())

    def sync(self):
        project = self.current()
        if project:
            self.app._async('กำลังส่งและตรวจไฟล์บน Drive…', project.sync, lambda _: self.show())

    def connect_production(self):
        from gmk_projects.production import ProductionProject
        project = self.current()
        if project:
            self.app._async('กำลังเชื่อมสถานะการผลิต…', ProductionProject(project).connect_existing, lambda _: self.show())

    def analyze_research(self):
        from gmk_projects.research import analyze_research
        project = self.current()
        if project:
            def done(result):
                self.show()
                messagebox.showinfo('GMK', f'มีข้อความรอตรวจ {result["claims_for_review"]} รายการ และลิงก์อ้างอิง {result["source_leads"]} แหล่ง\nกดเปิดรายการตรวจรีเสิร์ชเพื่อดูตำแหน่งต้นฉบับ ยังไม่ได้ตรวจข้อเท็จจริง')
            self.app._async('กำลังแยกข้อความและแหล่งอ้างอิง…', lambda: analyze_research(project), done)

    def review_research(self):
        import webbrowser
        from gmk_projects.research import research_review
        project = self.current()
        if project:
            self.app._async('กำลังเปิดรายการตรวจรีเสิร์ช…', lambda: research_review(project),
                            lambda result: webbrowser.open(Path(result['review_path']).as_uri()))

    def open_editor(self):
        project = self.current()
        if project:
            from .editor import EditorWindow
            try:
                EditorWindow(self.app, project)
            except Exception as exc:
                messagebox.showerror('GMK', str(exc))

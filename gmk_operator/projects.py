from pathlib import Path
import tempfile
from tkinter import filedialog, messagebox, simpledialog

from gmk_projects.intake import import_research, read_source
from gmk_projects.storage import Project, RcloneDrive


class ProjectsPanel:
    def __init__(self, app, parent):
        self.app, self.base = app, Path.home() / 'GMK Projects'
        self.scripts, self.projects = [], []
        tk, ttk = app.tk, app.ttk
        ttk.Label(parent, text='สร้างสารคดีจากหัวเรื่องและรีเสิร์ช', font=('Segoe UI', 14, 'bold')).pack(anchor='w')
        ttk.Label(parent, text='สร้างโปรเจกต์หรือนำเข้าเอกสาร แล้วเปิดพื้นที่ทำสารคดีเพื่อตรวจงานถัดไป ค้นภาพ ใส่เสียง ตัดต่อ และส่งออก',
                  wraplength=800).pack(anchor='w', pady=6)
        ttk.Button(parent, text='ค้นเอกสาร LEMiNO Script ใน Drive', command=self.search).pack(anchor='w')
        self.sources = ttk.Combobox(parent, state='readonly', width=95)
        self.sources.pack(fill='x', pady=6)
        row = ttk.Frame(parent)
        row.pack(fill='x')
        ttk.Button(row, text='เริ่มจากหัวเรื่องใหม่', command=self.new_topic).pack(side='left', padx=(0,6))
        ttk.Button(row, text='สร้างโปรเจกต์จากเอกสารที่เลือก', command=self.import_drive).pack(side='left')
        ttk.Button(row, text='นำเข้าไฟล์บทจากเครื่อง', command=self.import_local).pack(side='left', padx=6)
        ttk.Separator(parent).pack(fill='x', pady=12)
        ttk.Label(parent, text='โปรเจกต์ของคุณ').pack(anchor='w')
        self.selection = ttk.Combobox(parent, state='readonly', width=95)
        self.selection.pack(fill='x', pady=6)
        self.selection.bind('<<ComboboxSelected>>', lambda event: self.show())
        row = ttk.Frame(parent)
        row.pack(fill='x')
        ttk.Button(row, text='เปิดพื้นที่ทำสารคดี', command=self.open_editor).pack(side='left', padx=(0,6))
        ttk.Button(row, text='ส่งไฟล์และตรวจสอบบน Drive', command=self.sync).pack(side='left')
        ttk.Button(row, text='รีเฟรช', command=self.reload).pack(side='left', padx=6)
        self.connect_button = ttk.Button(row, text='เชื่อมโปรเจกต์รุ่นเดิม', command=self.connect_production)
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
        story_label = 'ยังไม่ได้เชื่อมบทเข้าระบบผลิต'
        media_label = 'ยังไม่ได้เชื่อมฟุตเทจเข้าข้อมูลผลิต'
        from gmk_projects.production import ProductionProject
        try:
            production = ProductionProject(p).status()
            if production['connected']:
                self.connect_button.pack_forget()
            else:
                self.connect_button.pack(side='left')
            state_labels = {'NOT_CONNECTED': 'โปรเจกต์รุ่นเดิม — กดเชื่อมโปรเจกต์รุ่นเดิมเพื่อทำงานต่อ',
                            'BOOTSTRAPPED': 'ตั้งโปรเจกต์แล้ว — รอนำเข้ารีเสิร์ช',
                            'RESEARCH_INTAKE': 'รับรีเสิร์ชแล้ว — ขั้นถัดไปคือตรวจหลักฐานและข้อกล่าวอ้าง',
                            'RESEARCH_AUDITED': 'ตรวจรีเสิร์ชแล้ว — รอเชื่อมโครงเรื่อง',
                            'ROUGH_NARRATIVE_READY': 'มีโครงเรื่องและฉากแล้ว — รอกำหนดภาพ',
                            'VISUAL_REQUIREMENTS_READY': 'กำหนดภาพแต่ละฉากแล้ว — ขั้นถัดไปคือค้นและตรวจฟุตเทจ',
                            'ASSET_RECON': 'ลงทะเบียนฟุตเทจแล้ว — ตรวจภาพและจัดช็อตต่อ',
                            'ASSET_CATALOG_READY': 'เลือกคลังภาพแล้ว — รอตรวจความครอบคลุมภาพ',
                            'VISUAL_COVERAGE_READY': 'ภาพครอบคลุมฉากแล้ว — เตรียมบทและงานผลิตต่อ'}
            production_label = state_labels.get(production['production_state'], production['production_state'])
            story_label = production.get('story_binding', {}).get('reason', story_label)
            media_label = production.get('media_binding', {}).get('reason', media_label)
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
                 'บทและฉาก: ' + story_label,
                 'ฟุตเทจและช่วงตัด: ' + media_label,
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

    def new_topic(self):
        topic = simpledialog.askstring('เริ่มสารคดี', 'หัวเรื่องสารคดี:', parent=self.app.root)
        if not topic or not topic.strip(): return
        def done(project):
            self.reload(project)
            from .editor import EditorWindow
            EditorWindow(self.app, project).edit_brief()
        self.app._async('กำลังสร้างโปรเจกต์สารคดี', lambda: Project.create(self.base, topic), done)

    def sync(self):
        project = self.current()
        if project:
            self.app._async('กำลังส่งและตรวจไฟล์บน Drive…', project.sync, lambda _: self.show())

    def connect_production(self):
        from gmk_projects.production import ProductionProject
        project = self.current()
        if project:
            self.app._async('กำลังเชื่อมสถานะการผลิต…', ProductionProject(project).connect_existing, lambda _: self.show())

    def open_editor(self):
        project = self.current()
        if project:
            from .editor import EditorWindow
            try:
                EditorWindow(self.app, project)
            except Exception as exc:
                messagebox.showerror('GMK', str(exc))

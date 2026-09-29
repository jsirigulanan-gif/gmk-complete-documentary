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
        ttk.Label(parent, text='นำเข้าบท สร้างเสียงไทย และจัดเก็บไฟล์ — การเลือกภาพและตัดต่ออัตโนมัติยังไม่เชื่อมครบ',
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
        voice_row = ttk.Frame(parent)
        voice_row.pack(fill='x', pady=6)
        self.voice = ttk.Combobox(voice_row, state='readonly', values=['เสียงชาย · Niwat', 'เสียงหญิง · Premwadee'], width=23)
        self.voice.current(0)
        self.voice.pack(side='left')
        ttk.Button(voice_row, text='ทดลองเสียงฉากแรก (ฟรี)', command=lambda: self.narrate(1)).pack(side='left', padx=6)
        ttk.Button(voice_row, text='สร้างเสียงทุกฉาก (ฟรี)', command=lambda: self.narrate(None)).pack(side='left')
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
        statuses = {'LOCAL_ONLY': 'ยังอยู่ในเครื่อง', 'PENDING_UPLOAD': 'มีไฟล์รอส่ง',
                    'UPLOADING': 'กำลังส่ง', 'UPLOAD_FAILED': 'ส่งไม่สำเร็จ — ไฟล์ยังอยู่ในเครื่อง กดส่งซ้ำได้',
                    'VERIFIED': 'ส่งและตรวจไฟล์ครบแล้ว'}
        lines = [data['title'], 'สถานะ Drive: ' + statuses.get(data['storage_status'], data['storage_status']),
                 'โฟลเดอร์ Drive: ' + data['drive']['root'] + '/' + data['project_id'],
                 'ในเครื่อง: ' + str(p.root),
                 'สถานะการผลิต: รับข้อมูลแล้ว — ยังไม่ใช่วิดีโอสำเร็จรูป', '']
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

    def narrate(self, limit):
        from gmk_projects.voice import EdgeVoice, generate_voice
        project = self.current()
        if not project:
            return
        provider = EdgeVoice('th-TH-NiwatNeural' if self.voice.current() == 0 else 'th-TH-PremwadeeNeural')
        def done(result):
            self.show()
            messagebox.showinfo('GMK', f'สร้างเสียงแล้ว {len(result["scenes"])} ฉาก รวม {result["duration_seconds"]:.1f} วินาที\nไฟล์อยู่ในโฟลเดอร์ voice ของโปรเจกต์ กรุณาฟังก่อนตัดต่อ')
        self.app._async('กำลังสร้างเสียงภาษาไทยผ่านบริการออนไลน์ฟรี…', lambda: generate_voice(project, provider, limit=limit), done)

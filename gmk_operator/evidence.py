"""Explicit evidence review backed by archived bytes and core claim versions."""
import json
from tkinter import messagebox

from gmk_projects.evidence import collect_source, review_claim
from gmk_projects.research import research_review
from gmk_projects.edit import asset_file


class ResearchWindow:
    def __init__(self,app,project):
        self.app,self.project=app,project
        tk,ttk=app.tk,app.ttk
        self.window=tk.Toplevel(app.root);self.window.title('GMK · ตรวจหลักฐาน')
        self.window.geometry(f'{min(1150,self.window.winfo_screenwidth()-60)}x{min(830,self.window.winfo_screenheight()-80)}')
        self.claims=[];self.sources=[];self.claim_index=0
        self.selection=ttk.Combobox(self.window,state='readonly',width=110)
        self.selection.pack(fill='x',padx=10,pady=6);self.selection.bind('<<ComboboxSelected>>',lambda _:self.show_claim())
        ttk.Label(self.window,text='ข้อกล่าวอ้างที่ต้องตรวจ — แก้ให้เหลือประเด็นชัดเจนได้ ก่อนยืนยันกับข้อความหลักฐาน').pack(anchor='w',padx=10)
        self.claim=tk.Text(self.window,height=4,wrap='word');self.claim.pack(fill='x',padx=10,pady=5)
        self.status=tk.StringVar();ttk.Label(self.window,textvariable=self.status).pack(anchor='w',padx=10)
        row=ttk.Frame(self.window);row.pack(fill='x',padx=10,pady=5)
        self.url=tk.StringVar();self.url_box=ttk.Combobox(row,textvariable=self.url,width=90);self.url_box.pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='อ่านและเก็บหน้าเว็บ',command=self.fetch).pack(side='left',padx=5)
        self.source_choice=ttk.Combobox(self.window,state='readonly');self.source_choice.pack(fill='x',padx=10,pady=5)
        self.source_choice.bind('<<ComboboxSelected>>',lambda _:self.show_source())
        ttk.Label(self.window,text='ข้อความจากหน้าเว็บที่เก็บไว้ — ลากเลือกข้อความที่เกี่ยวข้อง แล้วกดใช้เป็นหลักฐาน').pack(anchor='w',padx=10)
        self.source_text=tk.Text(self.window,height=13,wrap='word',state='disabled');self.source_text.pack(fill='both',expand=True,padx=10,pady=5)
        ttk.Button(self.window,text='ใช้ข้อความที่เลือกเป็นหลักฐาน',command=self.use_excerpt).pack(anchor='w',padx=10)
        self.excerpt=tk.Text(self.window,height=4,wrap='word');self.excerpt.pack(fill='x',padx=10,pady=5)
        row=ttk.Frame(self.window);row.pack(fill='x',padx=10,pady=5)
        self.disposition=ttk.Combobox(row,state='readonly',values=['หลักฐานยังไม่พอ — ห้ามใช้ในบทจริง','ข้อความนี้สนับสนุนข้อกล่าวอ้าง','พบข้อมูลขัดแย้ง — ห้ามใช้ในบทจริง'],width=45)
        self.disposition.current(0);self.disposition.pack(side='left')
        self.confirmed=tk.BooleanVar()
        ttk.Checkbutton(row,text='ฉันอ่านและเทียบข้อความกับข้อกล่าวอ้างแล้ว',variable=self.confirmed).pack(side='left',padx=8)
        ttk.Button(self.window,text='บันทึกผลตรวจข้อกล่าวอ้าง',command=self.save).pack(anchor='w',padx=10,pady=6)
        ttk.Label(self.window,text='การดาวน์โหลดหน้าเว็บไม่ทำให้ข้อกล่าวอ้างผ่านโดยอัตโนมัติ แหล่งต่างเว็บยังไม่ถือว่าเป็นหลักฐานอิสระจนกว่าจะตรวจที่มา',wraplength=1100).pack(anchor='w',padx=10,pady=5)
        self.reload()

    def reload(self):
        report=research_review(self.project);self.claims=report['claims']
        self.selection['values']=[c['id']+' · '+c['verification_state']+' · '+c['text'][:80] for c in self.claims]
        if self.claims:
            self.selection.current(min(self.claim_index,len(self.claims)-1));self.show_claim()
        self.url_box['values']=[s['url'] for s in report['source_leads']]
        self.load_sources()

    def load_sources(self):
        self.sources=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((self.project.root/'external_sources').glob('*.json'))]
        self.source_choice['values']=[s['title']+' · '+s['url'] for s in self.sources]
        if self.sources:
            self.source_choice.current(len(self.sources)-1);self.show_source()

    def show_claim(self):
        self.claim_index=self.selection.current()
        if self.claim_index<0:return
        claim=self.claims[self.claim_index]
        self.claim.delete('1.0','end');self.claim.insert('1.0',claim['text'])
        self.status.set(f'{claim["id"]} รุ่น {claim["version"]} · {claim["verification_state"]} · อนุญาตใช้ในบท: {claim["narration_allowed"]}')
        self.excerpt.delete('1.0','end');self.confirmed.set(False)

    def show_source(self):
        index=self.source_choice.current()
        if index<0:return
        self.excerpt.delete('1.0','end');self.confirmed.set(False)
        try:
            text=asset_file(self.project,self.sources[index]['text'],'research').read_text(encoding='utf-8')
            self.source_text.configure(state='normal');self.source_text.delete('1.0','end');self.source_text.insert('1.0',text);self.source_text.configure(state='disabled')
        except Exception as exc:messagebox.showerror('GMK',str(exc),parent=self.window)

    def fetch(self):
        url=self.url.get().strip()
        self.app._async('กำลังอ่านและเก็บแหล่งข้อมูล',lambda:collect_source(self.project,url),lambda _:self.load_sources() if self.window.winfo_exists() else None)

    def use_excerpt(self):
        try:text=self.source_text.get('sel.first','sel.last')
        except self.app.tk.TclError:return messagebox.showinfo('GMK','ลากเลือกข้อความในแหล่งข้อมูลก่อน',parent=self.window)
        self.excerpt.delete('1.0','end');self.excerpt.insert('1.0',text)

    def save(self):
        if not self.claims:return
        if not self.confirmed.get():return messagebox.showinfo('GMK','อ่านและยืนยันการเทียบหลักฐานก่อนบันทึก',parent=self.window)
        claim=self.claims[self.claim_index]
        index=self.source_choice.current();source=self.sources[index] if index>=0 else None
        text=self.claim.get('1.0','end-1c');excerpt=self.excerpt.get('1.0','end-1c')
        disposition=['INSUFFICIENT','SUPPORTED','CONTRADICTED'][self.disposition.current()]
        self.app._async('กำลังบันทึกผลตรวจหลักฐาน',lambda:review_claim(self.project,claim['id'],claim['version'],text,source=source,excerpt=excerpt,disposition=disposition),lambda _:self.reload() if self.window.winfo_exists() else None)

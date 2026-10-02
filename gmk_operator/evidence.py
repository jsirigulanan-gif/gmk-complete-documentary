"""Explicit evidence review backed by archived bytes and core claim versions."""
import json
from tkinter import messagebox

from gmk_projects.evidence import collect_source, review_claim
from gmk_projects.research import research_review
from gmk_projects.research_draft import add_review_claim, research_inputs
from gmk_projects.intake import read_source
from gmk_projects.edit import asset_file


class ResearchWindow:
    def __init__(self,app,project):
        self.app,self.project=app,project
        tk,ttk=app.tk,app.ttk
        self.window=tk.Toplevel(app.root);self.window.title('GMK · ตรวจหลักฐาน')
        self.window.geometry(f'{min(1150,self.window.winfo_screenwidth()-60)}x{min(830,self.window.winfo_screenheight()-80)}')
        self.claims=[];self.sources=[];self.claim_index=0
        footer=ttk.Frame(self.window);footer.pack(side='bottom',fill='x',padx=10,pady=5)
        ttk.Button(footer,text='บันทึกผลตรวจข้อกล่าวอ้าง',command=self.save).pack(anchor='w',pady=6)
        ttk.Label(footer,text='การดาวน์โหลดหน้าเว็บไม่ทำให้ข้อกล่าวอ้างผ่านโดยอัตโนมัติ แหล่งต่างเว็บยังไม่ถือว่าเป็นหลักฐานอิสระจนกว่าจะตรวจที่มา',wraplength=1000).pack(anchor='w')
        toolbar=ttk.Frame(self.window);toolbar.pack(fill='x',padx=10,pady=6)
        self.selection=ttk.Combobox(toolbar,state='readonly',width=80)
        self.selection.pack(side='left',fill='x',expand=True);self.selection.bind('<<ComboboxSelected>>',lambda _:self.show_claim())
        ttk.Button(toolbar,text='เพิ่มประเด็นจากรีเสิร์ช',command=self.add_claim).pack(side='left',padx=6)
        container=ttk.Frame(self.window);container.pack(fill='both',expand=True)
        canvas=tk.Canvas(container,highlightthickness=0)
        scrollbar=ttk.Scrollbar(container,orient='vertical',command=canvas.yview)
        scrollbar.pack(side='right',fill='y');canvas.pack(side='left',fill='both',expand=True)
        canvas.configure(yscrollcommand=scrollbar.set)
        body=ttk.Frame(canvas);item=canvas.create_window((0,0),window=body,anchor='nw')
        body.bind('<Configure>',lambda _:canvas.configure(scrollregion=canvas.bbox('all')))
        canvas.bind('<Configure>',lambda event:canvas.itemconfigure(item,width=event.width))
        ttk.Label(body,text='ข้อกล่าวอ้างที่ต้องตรวจ — แก้ให้เหลือประเด็นชัดเจนได้ ก่อนยืนยันกับข้อความหลักฐาน',wraplength=1000).pack(anchor='w',padx=10)
        self.claim=tk.Text(body,height=4,wrap='word');self.claim.pack(fill='x',padx=10,pady=5)
        self.status=tk.StringVar();ttk.Label(body,textvariable=self.status,wraplength=1000).pack(anchor='w',padx=10)
        row=ttk.Frame(body);row.pack(fill='x',padx=10,pady=5)
        self.url=tk.StringVar();self.url_box=ttk.Combobox(row,textvariable=self.url,width=90);self.url_box.pack(side='left',fill='x',expand=True)
        ttk.Button(row,text='อ่านและเก็บหน้าเว็บ',command=self.fetch).pack(side='left',padx=5)
        self.source_choice=ttk.Combobox(body,state='readonly');self.source_choice.pack(fill='x',padx=10,pady=5)
        self.source_choice.bind('<<ComboboxSelected>>',lambda _:self.show_source())
        ttk.Label(body,text='ข้อความจากหน้าเว็บที่เก็บไว้ — ลากเลือกข้อความที่เกี่ยวข้อง แล้วกดใช้เป็นหลักฐาน',wraplength=1000).pack(anchor='w',padx=10)
        self.source_text=tk.Text(body,height=13,wrap='word',state='disabled');self.source_text.pack(fill='both',expand=True,padx=10,pady=5)
        ttk.Button(body,text='ใช้ข้อความที่เลือกเป็นหลักฐาน',command=self.use_excerpt).pack(anchor='w',padx=10)
        self.excerpt=tk.Text(body,height=4,wrap='word');self.excerpt.pack(fill='x',padx=10,pady=5)
        row=ttk.Frame(body);row.pack(fill='x',padx=10,pady=5)
        self.disposition=ttk.Combobox(row,state='readonly',values=['หลักฐานยังไม่พอ — ห้ามใช้ในบทจริง','ข้อความนี้สนับสนุนข้อกล่าวอ้าง','พบข้อมูลขัดแย้ง — ห้ามใช้ในบทจริง'],width=45)
        self.disposition.current(0);self.disposition.pack(side='left')
        self.confirmed=tk.BooleanVar()
        ttk.Checkbutton(row,text='ฉันอ่านและเทียบข้อความกับข้อกล่าวอ้างแล้ว',variable=self.confirmed).pack(side='left',padx=8)
        self.reload()

    def reload(self):
        report=research_review(self.project);self.claims=report['claims']
        self.selection['values']=[c['id']+' · '+c['verification_state']+' · '+c['text'][:80] for c in self.claims]
        if self.claims:
            self.selection.current(min(self.claim_index,len(self.claims)-1));self.show_claim()
        else:
            self.status.set('ยังไม่มีข้อกล่าวอ้าง — กดเพิ่มประเด็นจากรีเสิร์ช แล้วเลือกข้อความต้นฉบับ')
        self.url_box['values']=[s['url'] for s in report['source_leads']]
        self.load_sources()

    def add_claim(self):
        tk,ttk=self.app.tk,self.app.ttk
        try:inputs=research_inputs(self.project)
        except Exception as exc:return messagebox.showerror('GMK',str(exc),parent=self.window)
        if not inputs:return messagebox.showinfo('GMK','นำเข้าเอกสารรีเสิร์ชก่อนเพิ่มประเด็น',parent=self.window)
        dialog=tk.Toplevel(self.window);dialog.title('GMK · เพิ่มประเด็นจากต้นฉบับ')
        dialog.geometry(f'{min(980,dialog.winfo_screenwidth()-80)}x{min(730,dialog.winfo_screenheight()-100)}')
        footer=ttk.Frame(dialog);footer.pack(side='bottom',fill='x',padx=12,pady=8)
        ttk.Label(footer,text='สร้างรายการ UNREVIEWED เท่านั้น ต้องตรวจแหล่งหลักฐานก่อนนำไปใช้ในบทจริง',wraplength=850).pack(anchor='w')
        selection=ttk.Combobox(dialog,state='readonly',values=[a['original_name'] for a in inputs]);selection.pack(fill='x',padx=12,pady=8)
        ttk.Label(dialog,text='ลากเลือกข้อความที่เกี่ยวข้องจากเอกสาร แล้วกดใช้ข้อความที่เลือก').pack(anchor='w',padx=12)
        original=tk.Text(dialog,height=12,wrap='word',state='disabled');original.pack(fill='both',expand=True,padx=12,pady=6)
        selected=tk.Text(dialog,height=3,wrap='word',state='disabled')
        assertion=tk.Text(dialog,height=3,wrap='word')
        def show(_=None):
            try:
                content,_=read_source(asset_file(self.project,inputs[selection.current()],'research'))
                original.configure(state='normal');original.delete('1.0','end');original.insert('1.0',content);original.configure(state='disabled')
                selected.configure(state='normal');selected.delete('1.0','end');selected.configure(state='disabled')
                assertion.delete('1.0','end')
            except Exception as exc:messagebox.showerror('GMK',str(exc),parent=dialog)
        def use():
            try:value=original.get('sel.first','sel.last')
            except tk.TclError:return messagebox.showinfo('GMK','เลือกข้อความในเอกสารก่อน',parent=dialog)
            selected.configure(state='normal');selected.delete('1.0','end');selected.insert('1.0',value);selected.configure(state='disabled')
            assertion.delete('1.0','end');assertion.insert('1.0',value)
        ttk.Button(dialog,text='ใช้ข้อความที่เลือก',command=use).pack(anchor='w',padx=12)
        ttk.Label(dialog,text='ข้อความต้นฉบับที่เลือก').pack(anchor='w',padx=12)
        selected.pack(fill='x',padx=12,pady=4)
        ttk.Label(dialog,text='ข้อกล่าวอ้างหนึ่งประเด็นที่ต้องตรวจ — ปรับข้อความให้ชัดเจนได้').pack(anchor='w',padx=12)
        assertion.pack(fill='x',padx=12,pady=4)
        def save():
            source=inputs[selection.current()]['path'];excerpt=selected.get('1.0','end-1c');claim=assertion.get('1.0','end-1c')
            def done(_):
                if dialog.winfo_exists():dialog.destroy()
                if self.window.winfo_exists():
                    self.reload()
                    index=next((i for i,c in enumerate(self.claims) if c['text']==' '.join(claim.split())),None)
                    if index is not None:self.selection.current(index);self.show_claim()
            self.app._async('กำลังเพิ่มประเด็นรอตรวจจากต้นฉบับ',lambda:add_review_claim(self.project,source,excerpt,claim),done)
        ttk.Button(footer,text='สร้างประเด็นรอตรวจ',command=save).pack(anchor='w',pady=6)
        selection.bind('<<ComboboxSelected>>',show);selection.current(0);show()

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

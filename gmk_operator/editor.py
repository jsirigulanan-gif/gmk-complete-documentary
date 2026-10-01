"""Project editing desk: one working draft from script through local delivery."""
import json
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
import webbrowser

from gmk_projects.edit import EditSession, media_ref, probe
from gmk_projects.storage import atomic_json


class EditorWindow:
    def __init__(self, app, project):
        self.app, self.project = app, project
        self.session = EditSession(project)
        self.data = self.session.load()
        self.index = 0
        self.candidates = []
        self.disabled_widgets = []
        tk, ttk = app.tk, app.ttk
        self.window = tk.Toplevel(app.root)
        self.window.title('GMK · '+project.read()['title'])
        self.window.geometry(f'{min(1140,self.window.winfo_screenwidth()-60)}x{min(820,self.window.winfo_screenheight()-80)}')
        self.window.minsize(900, 620)
        self.status = tk.StringVar(value='แก้บท → เพิ่มภาพและเสียง → ตรวจไทม์ไลน์ → เรนเดอร์ → ตรวจทั้งเรื่อง → ส่งออก')
        ttk.Label(self.window, textvariable=self.status, wraplength=1080).pack(fill='x', padx=12, pady=8)
        self.book = ttk.Notebook(self.window)
        self.book.pack(fill='both', expand=True, padx=12, pady=8)
        story = ttk.Frame(self.book, padding=10)
        footage = ttk.Frame(self.book, padding=10)
        finish = ttk.Frame(self.book, padding=10)
        self.book.add(story, text='1 · บท ฉาก และเสียง')
        self.book.add(footage, text='2 · ค้นภาพและตัดช็อต')
        self.book.add(finish, text='3 · ไทม์ไลน์และส่งออก')
        left = ttk.Frame(story)
        left.pack(side='left', fill='y', padx=(0,12))
        self.scenes = tk.Listbox(left, width=27, exportselection=False)
        self.scenes.pack(fill='both', expand=True)
        self.scenes.bind('<<ListboxSelect>>', self.select_scene)
        for label, action in [('เพิ่มฉาก', self.add_scene), ('เลื่อนขึ้น', lambda: self.move_scene(-1)), ('เลื่อนลง', lambda: self.move_scene(1))]:
            ttk.Button(left, text=label, command=action).pack(fill='x', pady=3)
        ttk.Button(left, text='ให้ AI สร้างโครงเรื่อง', command=self.generate_story).pack(fill='x', pady=8)
        right = ttk.Frame(story)
        right.pack(fill='both', expand=True)
        self.title = tk.StringVar()
        self.included = tk.BooleanVar(value=True)
        self.hold = tk.BooleanVar()
        self.overlay = tk.BooleanVar()
        ttk.Label(right, text='ชื่อฉาก').pack(anchor='w')
        ttk.Entry(right, textvariable=self.title).pack(fill='x')
        ttk.Checkbutton(right, text='รวมฉากนี้ในวิดีโอ', variable=self.included).pack(anchor='w')
        ttk.Label(right, text='บทพากย์ภาษาไทย (แก้บทแล้วต้องสร้างเสียงใหม่)').pack(anchor='w')
        self.narration = tk.Text(right, height=8, wrap='word')
        self.narration.pack(fill='both', expand=True)
        ttk.Label(right, text='ภาพที่ต้องการ').pack(anchor='w', pady=(6,0))
        self.visual = tk.Text(right, height=3, wrap='word')
        self.visual.pack(fill='x')
        ttk.Checkbutton(right, text='อนุญาตค้างเฟรมท้ายเมื่อภาพสั้นกว่าเสียง', variable=self.hold).pack(anchor='w')
        ttk.Checkbutton(right, text='แสดงชื่อฉากช่วงต้นภาพ', variable=self.overlay).pack(anchor='w')
        voice_row = ttk.Frame(right)
        voice_row.pack(fill='x', pady=8)
        self.voice_choice = ttk.Combobox(voice_row, state='readonly', values=['Niwat · ชาย', 'Premwadee · หญิง'], width=20)
        self.voice_choice.current(0)
        self.voice_choice.pack(side='left')
        ttk.Button(voice_row, text='บันทึกฉาก', command=self.save).pack(side='left', padx=4)
        ttk.Button(voice_row, text='นำเข้าเสียงฉากนี้', command=self.import_voice).pack(side='left')
        ttk.Button(voice_row, text='ฟังเสียงฉากนี้', command=self.play_voice).pack(side='left', padx=4)
        row = ttk.Frame(right)
        row.pack(fill='x')
        ttk.Button(row, text='สร้างเสียงฉากนี้ · Edge ออนไลน์', command=lambda: self.synthesize(False)).pack(side='left')
        ttk.Button(row, text='สร้างเสียงฉากที่เลือกทั้งหมด', command=lambda: self.synthesize(True)).pack(side='left', padx=4)
        ttk.Button(right, text='นำเสียงที่เคยสร้างในโปรเจกต์มาใช้', command=self.import_old_voice).pack(anchor='w', pady=5)
        ttk.Button(right, text='เปิดรีเสิร์ชและแหล่งอ้างอิง', command=self.open_research).pack(anchor='w')
        ttk.Button(right, text='ตรวจบทฉากนี้กับหลักฐาน', command=self.review_claims).pack(anchor='w', pady=3)
        self.voice_status = tk.StringVar()
        ttk.Label(right, textvariable=self.voice_status, wraplength=700).pack(anchor='w', pady=6)

        ttk.Label(footage, text='ค้นจากคำอธิบายภาพ แล้วเปิดตรวจเนื้อหาก่อนเลือกช่วงตัด ผลค้นหายังไม่ยืนยันว่าภาพตรงบท').pack(anchor='w')
        self.query = tk.StringVar()
        ttk.Entry(footage, textvariable=self.query).pack(fill='x', pady=6)
        row = ttk.Frame(footage)
        row.pack(fill='x')
        ttk.Button(row, text='ค้น YouTube', command=self.search).pack(side='left')
        ttk.Button(row, text='เปิดวิดีโอที่เลือก', command=self.open_candidate).pack(side='left', padx=5)
        ttk.Button(row, text='ดาวน์โหลดเข้าคลังโปรเจกต์', command=self.download).pack(side='left')
        ttk.Button(row, text='ดาวน์โหลดจาก URL', command=self.download_url).pack(side='left', padx=5)
        ttk.Button(row, text='เตรียมช็อตฉากนี้อัตโนมัติ', command=self.auto_footage).pack(side='left')
        self.results = tk.Listbox(footage, height=7, exportselection=False)
        self.results.pack(fill='x', pady=6)
        ttk.Button(footage,text='เตรียมภาพอัตโนมัติทุกฉากที่ยังว่าง',command=self.auto_all_footage).pack(anchor='w',pady=4)
        self.active_scene = tk.StringVar()
        ttk.Label(footage, textvariable=self.active_scene).pack(anchor='w')
        ttk.Label(footage, text='เลือกฉากที่แท็บ 1 แล้วเพิ่มไฟล์/ช่วงภาพลงฉากนั้น (หน่วยวินาที)').pack(anchor='w')
        row = ttk.Frame(footage)
        row.pack(fill='x', pady=6)
        self.start, self.end = tk.StringVar(value='0'), tk.StringVar(value='10')
        ttk.Label(row, text='เริ่ม').pack(side='left')
        ttk.Entry(row, textvariable=self.start, width=10).pack(side='left')
        ttk.Label(row, text='จบ').pack(side='left')
        ttk.Entry(row, textvariable=self.end, width=10).pack(side='left')
        ttk.Button(row, text='เลือกวิดีโอและเพิ่มช็อต', command=self.add_shot).pack(side='left', padx=6)
        self.shots = tk.Listbox(footage, height=8, exportselection=False)
        self.shots.pack(fill='both', expand=True)
        self.shots.bind('<<ListboxSelect>>', self.select_shot)
        row = ttk.Frame(footage)
        row.pack(fill='x', pady=6)
        ttk.Button(row, text='เปิดไฟล์ช็อต', command=self.open_shot).pack(side='left')
        ttk.Button(row, text='บันทึกเวลาเริ่ม/จบช็อตที่เลือก', command=self.trim_shot).pack(side='left', padx=5)
        ttk.Button(row, text='เลื่อนขึ้น', command=lambda: self.move_shot(-1)).pack(side='left', padx=5)
        ttk.Button(row, text='เลื่อนลง', command=lambda: self.move_shot(1)).pack(side='left')
        ttk.Button(row, text='เอาช็อตออกจากฉาก', command=self.remove_shot).pack(side='left', padx=5)
        ttk.Label(footage, text='ไฟล์ที่เอาออกจากฉากยังอยู่ในคลัง และรออัปโหลดไปโฟลเดอร์ Drive ของโปรเจกต์').pack(anchor='w')

        row = ttk.Frame(finish)
        row.pack(fill='x')
        self.resolution = ttk.Combobox(row, state='readonly', values=['640 × 360', '1280 × 720', '1920 × 1080'], width=16)
        self.resolution.current({640:0,1280:1,1920:2}[self.data['width']])
        self.resolution.pack(side='left')
        ttk.Button(row, text='เพิ่มดนตรี', command=self.add_music).pack(side='left', padx=5)
        ttk.Button(row, text='เอาดนตรีออก', command=self.remove_music).pack(side='left')
        self.gain = tk.DoubleVar(value=self.data['music_gain'])
        ttk.Label(row, text='ระดับดนตรี').pack(side='left', padx=5)
        ttk.Scale(row, from_=0, to=.4, variable=self.gain).pack(side='left', fill='x', expand=True)
        self.music_status = tk.StringVar()
        ttk.Label(finish, textvariable=self.music_status).pack(anchor='w', pady=6)
        self.timeline = tk.Text(finish, height=19, wrap='word', state='disabled')
        self.timeline.pack(fill='both', expand=True)
        row = ttk.Frame(finish)
        row.pack(fill='x', pady=6)
        for label, action in [('ตรวจไทม์ไลน์', self.preflight), ('เรนเดอร์ MP4 ตัวอย่าง', self.render), ('เปิดวิดีโอล่าสุด', self.play_render)]:
            ttk.Button(row, text=label, command=action).pack(side='left', padx=3)
        row = ttk.Frame(finish)
        row.pack(fill='x')
        ttk.Button(row, text='ยืนยันว่าดูและฟังทั้งเรื่องแล้ว', command=self.approve).pack(side='left')
        ttk.Button(row, text='สร้างชุดส่งออกฉบับร่าง', command=self.export).pack(side='left', padx=5)
        ttk.Button(row, text='อัปโหลดและตรวจไฟล์บน Drive', command=self.sync).pack(side='left')
        row = ttk.Frame(finish)
        row.pack(fill='x', pady=4)
        ttk.Button(row, text='ตรวจชุดส่งออกกับงานรุ่นปัจจุบัน', command=self.verify_delivery).pack(side='left')
        ttk.Button(row, text='ส่งชุดฉบับร่างและตรวจสำเนาบน Drive', command=self.deliver).pack(side='left', padx=5)
        ttk.Label(finish, text='การตรวจไฟล์ทางเทคนิคไม่ใช่การตรวจข้อเท็จจริง ต้องตรวจภาพ เสียง คำบรรยาย และแหล่งอ้างอิงก่อนส่งมอบ', wraplength=1000).pack(anchor='w', pady=8)
        self.window.protocol('WM_DELETE_WINDOW', self.close)
        self.reload()

    def run(self, label, operation, done=None):
        if self.app._busy:
            messagebox.showinfo('GMK','มีงานกำลังทำอยู่ กรุณารอก่อน',parent=self.window)
            return
        if not self.save():
            return
        def disable(widget):
            for child in widget.winfo_children():
                disable(child)
            try:
                state = widget.cget('state')
                widget.configure(state='disabled')
                self.disabled_widgets.append((widget,state))
            except self.app.tk.TclError:
                pass
        disable(self.book)
        def finished(result):
            if self.window.winfo_exists():
                self.restore_widgets()
                self.reload()
                if done:
                    done(result)
                self.status.set(label+' — เสร็จแล้ว')
        self.app._async(label, operation, finished)
        def restore_after_error():
            if self.window.winfo_exists() and self.disabled_widgets:
                if self.app._busy:
                    self.window.after(150,restore_after_error)
                else:
                    self.restore_widgets()
                    self.reload()
        self.window.after(150,restore_after_error)

    def restore_widgets(self):
        for widget,state in self.disabled_widgets:
            if widget.winfo_exists():
                widget.configure(state=state)
        self.disabled_widgets = []

    def capture(self):
        scene = self.data['scenes'][self.index]
        scene.update(title=self.title.get(), narration=self.narration.get('1.0','end-1c'),
                     visual=self.visual.get('1.0','end-1c'), included=self.included.get(),
                     hold_last_frame=self.hold.get(), show_title=self.overlay.get())
        self.data['music_gain'] = self.gain.get()
        self.data['width'], self.data['height'] = [(640,360),(1280,720),(1920,1080)][self.resolution.current()]

    def save(self):
        try:
            self.capture()
            self.data = self.session.save(self.data, expected_revision=self.data['revision'])
            self.reload()
            return True
        except Exception as exc:
            messagebox.showerror('GMK', str(exc), parent=self.window)
            return False

    def reload(self):
        self.data = self.session.load()
        self.index = min(self.index, len(self.data['scenes'])-1)
        self.scenes.delete(0,'end')
        for scene in self.data['scenes']:
            self.scenes.insert('end', ('✓ ' if scene['included'] else '— ')+scene['title'])
        self.scenes.selection_set(self.index)
        self.show_scene()
        self.music_status.set('ดนตรี: '+(self.data['music']['path'] if self.data.get('music') else 'ยังไม่ได้เลือก'))

    def show_scene(self):
        scene = self.data['scenes'][self.index]
        self.title.set(scene['title'])
        self.narration.delete('1.0','end'); self.narration.insert('1.0',scene['narration'])
        self.visual.delete('1.0','end'); self.visual.insert('1.0',scene['visual'])
        self.included.set(scene['included']); self.hold.set(scene['hold_last_frame']); self.overlay.set(scene['show_title'])
        self.query.set(scene['visual'][:200] or scene['title'])
        self.active_scene.set('ฉากปัจจุบัน: '+scene['title'])
        voice = scene.get('voice')
        self.voice_status.set('เสียง: '+(f'{voice["duration_seconds"]:.2f} วินาที · ต้องฟังตรวจ' if voice else 'ยังไม่มีเสียงตรงบท'))
        self.shots.delete(0,'end')
        for shot in scene['shots']:
            self.shots.insert('end', f'{shot["in_seconds"]:.2f}–{shot["out_seconds"]:.2f}s · {shot["original_name"]}')

    def select_scene(self, event=None):
        selection = self.scenes.curselection()
        if selection and selection[0] != self.index:
            new = selection[0]
            if self.save():
                self.index = new
                self.reload()

    def add_scene(self):
        if self.save():
            self.data['scenes'].append(self.session.new_scene())
            self.data = self.session.save(self.data, expected_revision=self.data['revision'])
            self.index = len(self.data['scenes'])-1
            self.reload()

    def move_scene(self, step):
        if not self.save(): return
        target = self.index+step
        if 0 <= target < len(self.data['scenes']):
            self.data['scenes'][self.index], self.data['scenes'][target] = self.data['scenes'][target], self.data['scenes'][self.index]
            self.data = self.session.save(self.data, expected_revision=self.data['revision'])
            self.index = target; self.reload()

    def import_voice(self):
        if not self.save(): return
        path = filedialog.askopenfilename(parent=self.window, title='เลือกเสียงฉากปัจจุบัน', filetypes=[('Audio','*.wav *.mp3 *.m4a *.flac *.ogg')])
        if path:
            scene_id, revision = self.data['scenes'][self.index]['id'], self.data['revision']
            self.run('กำลังนำเข้าเสียง', lambda: self.session.attach_voice(scene_id, Path(path), expected_revision=revision))

    def synthesize(self, all_scenes):
        if not self.save(): return
        consent = self.project.root/'edge_tts_consent.json'
        if not self.has_consent(consent):
            if not messagebox.askyesno('Microsoft Edge TTS', 'ระบบจะส่งข้อความบทพากย์ของโปรเจกต์นี้ไปยังบริการ Microsoft Edge TTS เพื่อสร้างเสียงฟรี อนุญาตหรือไม่?', parent=self.window):
                return
            atomic_json(consent, {'provider':'Microsoft Edge TTS','project_id':self.project.read()['project_id'],'allowed':True})
        from gmk_projects.voice import EdgeVoice
        provider = EdgeVoice('th-TH-NiwatNeural' if self.voice_choice.current()==0 else 'th-TH-PremwadeeNeural')
        ids = None if all_scenes else [self.data['scenes'][self.index]['id']]
        self.run('กำลังสร้างเสียงออนไลน์', lambda: self.session.synthesize(provider, scene_ids=ids))

    def import_old_voice(self):
        if self.save(): self.run('กำลังเชื่อมเสียงเดิม', self.session.import_existing_voice)

    def open_research(self):
        from .evidence import ResearchWindow
        if self.save():
            ResearchWindow(self.app,self.project)

    def search(self):
        from gmk_projects.footage import search_footage
        query = self.query.get().strip()
        def done(rows):
            self.candidates = rows; self.results.delete(0,'end')
            for row in rows: self.results.insert('end', row['title']+' · '+row['channel'])
        self.run('กำลังค้นฟุตเทจ', lambda: search_footage(self.project,query),done)

    def chosen(self):
        selection = self.results.curselection()
        return self.candidates[selection[0]] if selection else None

    def open_candidate(self):
        row = self.chosen()
        if row: webbrowser.open(row['webpage_url'])

    def download(self):
        row = self.chosen()
        if row: self.acquire(row)

    def download_url(self):
        from gmk_projects.footage import candidate_from_url
        url = simpledialog.askstring('YouTube','ลิงก์วิดีโอสาธารณะ:',parent=self.window)
        if url:
            try: self.acquire(candidate_from_url(url))
            except Exception as exc: messagebox.showerror('GMK',str(exc),parent=self.window)

    def acquire(self, candidate):
        from gmk_projects.footage import acquire_footage
        def done(result):
            messagebox.showinfo('GMK','เก็บฟุตเทจแล้ว เลือกไฟล์นี้เพื่อเพิ่มช่วงตัด:\n'+result['local_path']+'\nไฟล์ยังรออัปโหลด Drive',parent=self.window)
        self.run('กำลังดาวน์โหลดฟุตเทจ',lambda: acquire_footage(self.project,candidate),done)

    def auto_footage(self):
        if not self.save():return
        from gmk_projects.footage import prepare_scene_footage
        scene_id=self.data['scenes'][self.index]['id']
        def progress(message):self.app.root.after(0,lambda:self.status.set(message))
        def done(result):
            detail=(f'เตรียม {result["cuts"]} ช็อตแล้ว ภาพยังขาด {result["uncovered_seconds"]:.2f} วินาที\nต้องเปิดตรวจว่าภาพตรงกับบทก่อนส่งมอบ' if result['prepared'] else result['reason'])
            messagebox.showinfo('GMK',detail,parent=self.window)
        self.run('กำลังเตรียมช่วงภาพจากคำบรรยาย',lambda:prepare_scene_footage(self.project,scene_id,progress=progress),done)

    def auto_all_footage(self):
        if not self.save():return
        from gmk_projects.footage import prepare_project_footage
        def progress(message):self.app.root.after(0,lambda:self.status.set(message))
        def done(result):
            self.show_plan(result['preflight']);self.book.select(2)
            failed=[row.get('reason','') for row in result['scenes'] if not row['prepared']]
            if failed:messagebox.showinfo('GMK','บางฉากต้องค้นหรือเลือกภาพเพิ่ม:\n'+'\n'.join(failed)[:1600],parent=self.window)
        self.run('กำลังเตรียมภาพทุกฉาก',lambda:prepare_project_footage(self.project,progress=progress),done)

    def add_shot(self):
        if not self.save(): return
        path = filedialog.askopenfilename(parent=self.window, title='เลือกวิดีโอ', initialdir=self.project.root/'footage', filetypes=[('Video','*.mp4 *.mkv *.webm *.mov')])
        if path:
            try: start,end = float(self.start.get()),float(self.end.get())
            except ValueError: return messagebox.showerror('GMK','เวลาเริ่มและจบต้องเป็นตัวเลข',parent=self.window)
            scene_id,revision = self.data['scenes'][self.index]['id'],self.data['revision']
            self.run('กำลังเพิ่มช็อต',lambda: self.session.add_shot(scene_id,Path(path),start,end,expected_revision=revision))

    def open_shot(self):
        selection = self.shots.curselection()
        if selection:
            webbrowser.open((self.project.root/self.data['scenes'][self.index]['shots'][selection[0]]['path']).as_uri())

    def play_voice(self):
        if not self.save(): return
        voice = self.data['scenes'][self.index].get('voice')
        if not voice:
            return messagebox.showinfo('GMK', 'ยังไม่มีเสียงที่ตรงกับบทฉากนี้', parent=self.window)
        from gmk_projects.edit import asset_file
        try:
            webbrowser.open(asset_file(self.project, voice, 'voice').as_uri())
        except Exception as exc:
            messagebox.showerror('GMK', str(exc), parent=self.window)

    def select_shot(self, event=None):
        selected = self.shots.curselection()
        if selected:
            shot = self.data['scenes'][self.index]['shots'][selected[0]]
            self.start.set(str(shot['in_seconds']))
            self.end.set(str(shot['out_seconds']))

    def trim_shot(self):
        selected = self.shots.curselection()
        if not selected: return
        scene = self.data['scenes'][self.index]
        shot_id = scene['shots'][selected[0]]['id']
        try:
            start, end = float(self.start.get()), float(self.end.get())
        except ValueError:
            return messagebox.showerror('GMK', 'เวลาเริ่มและจบต้องเป็นตัวเลข', parent=self.window)
        if not self.save(): return
        revision = self.data['revision']
        self.run('กำลังปรับช่วงภาพ', lambda: self.session.trim_shot(
            scene['id'], shot_id, start, end, expected_revision=revision))

    def move_shot(self,step):
        selected = self.shots.curselection()
        if not selected: return
        cuts = self.data['scenes'][self.index]['shots']; index = selected[0]; target = index+step
        if 0 <= target < len(cuts):
            cuts[index],cuts[target] = cuts[target],cuts[index]; self.save()

    def remove_shot(self):
        selected = self.shots.curselection()
        if selected:
            self.data['scenes'][self.index]['shots'].pop(selected[0]); self.save()

    def add_music(self):
        if not self.save(): return
        path = filedialog.askopenfilename(parent=self.window,title='เลือกดนตรี',filetypes=[('Audio','*.wav *.mp3 *.m4a *.flac *.ogg')])
        if path:
            def run():
                info=probe(Path(path))
                if not any(s['codec_type']=='audio' for s in info['streams']): raise ValueError('ไฟล์นี้ไม่มีเสียง')
                data=self.session.load(); data['music']=media_ref(self.project.add_file(Path(path),'music'))
                return self.session.save(data,expected_revision=data['revision'])
            self.run('กำลังเพิ่มดนตรี',run)

    def remove_music(self):
        self.data['music']=None; self.save()

    def show_plan(self,result):
        lines=[f'ความยาว {result["duration_seconds"]:.2f} วินาที · พร้อมเรนเดอร์: {result["ready_to_render"]}']
        lines += ['บทผ่านการเทียบหลักฐานทุกฉาก: '+str(result['script_review']['ready'])]
        lines += [f'{s["start_frame"]/result["fps"]:.2f}s · {s["scene_id"]} · {s["duration_seconds"]:.2f}s · {len(s["cuts"])} ช็อต' for s in result['timeline']]
        lines += ['ต้องแก้: '+str(i['scene_id'])+' '+i['detail'] for i in result['issues']]
        lines += ['รอตรวจ: '+w for w in result['warnings']]
        self.timeline.configure(state='normal'); self.timeline.delete('1.0','end'); self.timeline.insert('1.0','\n'.join(lines)); self.timeline.configure(state='disabled')

    def preflight(self):
        if self.save(): self.run('กำลังตรวจไทม์ไลน์',self.session.preflight,self.show_plan)

    def render(self):
        if not self.save(): return
        from gmk_projects.render import render_project
        def progress(message):
            self.app.root.after(0,lambda: self.status.set(message))
        self.run('กำลังเรนเดอร์',lambda: render_project(self.project,progress=progress),lambda r: messagebox.showinfo('GMK',f'สร้างไฟล์แล้ว\n{r["master_path"]}\nตรวจเทคนิค: {r["technical_qa"]["passed"]}\nกรุณาดูและฟังทั้งเรื่องก่อนส่งออก',parent=self.window))

    def play_render(self):
        path=self.project.root/'last_render.json'
        if path.exists():
            result=json.loads(path.read_text()); webbrowser.open(Path(result['master_path']).as_uri())

    def approve(self):
        if not self.save(): return
        from gmk_projects.render import approve_editorial_review
        path=self.project.root/'last_render.json'
        if not path.exists(): return messagebox.showinfo('GMK','เรนเดอร์ก่อนครับ',parent=self.window)
        result=json.loads(path.read_text())
        if messagebox.askyesno('ตรวจทั้งเรื่อง','คุณดูและฟังวิดีโอรุ่นนี้ครบแล้ว และตรวจภาพ เสียง คำบรรยาย รวมถึงเนื้อหาแล้วใช่หรือไม่?',parent=self.window):
            self.run('กำลังบันทึกผลตรวจ',lambda: approve_editorial_review(self.project,expected_master_sha256=result['technical_qa']['sha256']))

    def export(self):
        if not self.save(): return
        from gmk_projects.render import export_delivery
        self.run('กำลังสร้างชุดส่งออก',lambda: export_delivery(self.project),lambda r: messagebox.showinfo('GMK','สร้างชุดส่งออกฉบับร่างแล้ว:\n'+str(self.project.root/r['package']['path'])+'\nบทผ่านการเทียบหลักฐานทุกฉาก: '+str(r['script_review_ready'])+'\nยังไม่ได้ผ่านการส่งมอบขั้นสุดท้ายและตรวจสำเนาบน Drive',parent=self.window))

    def sync(self):
        self.run('กำลังอัปโหลดและตรวจ Drive',self.project.sync)

    def show_delivery(self, result):
        lines = ['ตรวจชุดส่งออกฉบับร่างผ่านแล้ว',
                 'ไฟล์ ZIP, MP4, บท และผลตรวจเป็นรุ่นเดียวกัน',
                 'บทผ่านการเทียบหลักฐานทุกฉาก: '+str(result['script_review_ready']),
                 'ชุดไฟล์: '+str(self.project.root/result['package']['path'])]
        if result.get('drive_receipts'):
            lines += ['ส่งและตรวจเลขไฟล์ ขนาด และ checksum บน Drive สำเร็จในการส่งครั้งนี้']
        else:
            lines += ['การตรวจครั้งนี้ตรวจไฟล์ในเครื่อง ยังไม่ได้ตรวจ Drive สด']
        lines += ['ชุดนี้เป็นฉบับร่าง ยังไม่ใช่การอนุมัติส่งมอบสารคดีขั้นสุดท้าย']
        self.timeline.configure(state='normal')
        self.timeline.delete('1.0', 'end')
        self.timeline.insert('1.0', '\n'.join(lines))
        self.timeline.configure(state='disabled')

    def verify_delivery(self):
        from gmk_projects.delivery import verify_delivery
        self.run('กำลังตรวจชุดส่งออก', lambda: verify_delivery(self.project), self.show_delivery)

    def deliver(self):
        from gmk_projects.delivery import deliver_project
        self.run('กำลังส่งชุดฉบับร่างและตรวจ Drive', lambda: deliver_project(self.project), self.show_delivery)

    def close(self):
        if self.app._busy:
            messagebox.showinfo('GMK','รอให้งานที่กำลังทำเสร็จก่อนปิดหน้าต่าง',parent=self.window)
        elif self.save(): self.window.destroy()

    def generate_story(self):
        if not self.save(): return
        brief=simpledialog.askstring('โจทย์สารคดี','อยากเล่าเรื่องนี้ในมุมใด และอยากให้คนดูเข้าใจอะไร?',parent=self.window)
        if not brief: return
        seconds=simpledialog.askinteger('ความยาว','ความยาวเป้าหมายเป็นวินาที (เช่น 180 = 3 นาที):',initialvalue=180,minvalue=30,maxvalue=3600,parent=self.window)
        if seconds is None: return
        consent=self.project.root/'codex_story_consent.json'
        if not self.has_consent(consent):
            if not messagebox.askyesno('Codex AI','ส่งข้อความรีเสิร์ชและโจทย์ของโปรเจกต์นี้ไปยัง Codex ที่ล็อกอินในเครื่องเพื่อสร้างร่างเรื่องหรือไม่? ใช้สิทธิ์และโควตาของบัญชี Codex ร่างเดิมจะยังอยู่จนกว่าจะกดใช้ร่างใหม่',parent=self.window): return
            atomic_json(consent,{'provider':'Codex CLI','project_id':self.project.read()['project_id'],'allowed':True})
        from gmk_projects.story import generate_story,apply_story,CodexStoryProvider
        def done(result):
            dialog=self.app.tk.Toplevel(self.window);dialog.title('ตรวจโครงเรื่องจาก AI');dialog.geometry('850x680')
            preview=self.app.tk.Text(dialog,wrap='word');preview.pack(fill='both',expand=True,padx=10,pady=10)
            draft=result['draft']
            lines=[draft['title'],draft['central_question'],draft['narrative_arc'],'']
            for scene in draft['scenes']:
                lines += [scene['story_role']+' · '+scene['title'],scene['narration'],'ภาพ: '+scene['visual'],'อ้างรายการ: '+', '.join(scene['claim_ids']),'']
            lines += ['ประเด็นที่ยังต้องตรวจ:']+draft['research_warnings']
            preview.insert('1.0','\n'.join(lines));preview.configure(state='disabled')
            def apply():
                if not self.save(): return
                self.run('กำลังนำร่างเรื่องมาใช้',lambda:apply_story(self.project,result),lambda _:dialog.destroy())
            self.app.ttk.Button(dialog,text='ใช้ร่างนี้และเก็บฉบับเดิมไว้',command=apply).pack(pady=10)
        self.run('กำลังให้ Codex สร้างโครงเรื่อง',lambda:generate_story(self.project,brief,seconds,provider=CodexStoryProvider(model=self.app.cfg.get('story_model'))),done)

    def has_consent(self,path):
        try:
            consent=json.loads(path.read_text(encoding='utf-8'))
            return consent.get('allowed') is True and consent.get('project_id')==self.project.read()['project_id']
        except (OSError,ValueError,AttributeError):
            return False

    def review_claims(self):
        if not self.save(): return
        from gmk_projects.research import research_review
        from gmk_projects.script_review import review_scene_claims
        report = research_review(self.project)
        scene = self.data['scenes'][self.index]
        revision, scene_id = self.data['revision'], scene['id']
        dialog = self.app.tk.Toplevel(self.window)
        dialog.title('เทียบบทกับหลักฐาน · '+scene['title'])
        dialog.geometry('850x600')
        self.app.ttk.Label(dialog, text=scene['narration'], wraplength=810).pack(fill='x', padx=10, pady=10)
        self.app.ttk.Label(dialog, text='เลือกข้อกล่าวอ้างที่รองรับบทฉากนี้ (เลือกได้หลายรายการ)').pack(anchor='w', padx=10)
        choices = self.app.tk.Listbox(dialog, selectmode='multiple', exportselection=False)
        choices.pack(fill='both', expand=True, padx=10, pady=8)
        for i, claim in enumerate(report['claims']):
            choices.insert('end', ('✓ ' if claim['narration_allowed'] else 'รอตรวจ · ')+claim['id']+' · '+claim['text'])
            if any(r['id'] == claim['id'] for r in scene.get('claim_refs', [])):
                choices.selection_set(i)
        self.app.ttk.Label(dialog, text='หลักฐานรองรับถ้อยคำในบทนี้อย่างไร รวมถึงข้อจำกัดหรือการระบุว่าเป็นคำบอกเล่า').pack(anchor='w', padx=10)
        note = self.app.tk.Text(dialog, height=4, wrap='word')
        note.pack(fill='x', padx=10, pady=8)
        def confirm():
            selected = [report['claims'][i]['id'] for i in choices.curselection()]
            explanation = note.get('1.0', 'end-1c')
            self.run('กำลังผูกบทกับหลักฐาน', lambda: review_scene_claims(
                self.project, scene_id, selected, expected_revision=revision,
                expected_manifest_sha256=report['manifest_sha256'], editorial_note=explanation),
                lambda _: dialog.destroy())
        self.app.ttk.Button(dialog, text='บันทึกผลการเทียบบทกับหลักฐาน', command=confirm).pack(pady=10)

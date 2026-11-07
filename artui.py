"""AI 그림 설명서 창 / 그림 한꺼번에 적용 창."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import artguide as AG
from winpos import center_window

FONT = ("Malgun Gothic", 10)


def _requests_dir(app):
    base = getattr(app, "app_dir", "") or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                                                       "sts2_mod_maker")
    return os.path.join(base, "ai_requests")


def _open_folder(path):
    try:
        os.startfile(path)      # 윈도 탐색기로 연다 (끌어다 첨부하기 좋게)
    except (OSError, AttributeError):
        pass


def quick_copy(app):
    """버튼 한 번: 저장된 선택으로 설명서를 바로 복사. 참고 그림이 있으면 첨부할 폴더도 연다. -> 안내 글"""
    guide = AG.quick_guide(app.project, getattr(app, "app_dir", "") or "")
    app.clipboard_clear()
    app.clipboard_append(guide)
    refs = AG.style_refs(app.project)
    n = len(AG.chosen_slots(app.project))
    if refs:
        folder, _z = AG.make_bundle(app.project, guide, refs, _requests_dir(app))
        _open_folder(folder)
        return f"그림 설명서({n}장)를 복사했습니다. 열린 폴더의 참고 그림 {len(refs)}장을 함께 첨부하세요."
    return f"그림 설명서({n}장)를 복사했습니다. 채팅 AI 에 붙여 넣으세요."


class ArtGuideDialog(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("🖼 AI 그림 설명서 만들기")
        self.transient(app)
        self.geometry("1100x760")
        p = app.project
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Label(top, text="채팅 AI (ChatGPT·Claude·Gemini 등) 에 아래 설명서를 그대로 붙여 넣으면, 모드에 필요한 그림을 "
                            "파일 이름까지 맞춰 만들어 줍니다.\n카드 삽화에는 '카드 원화 구도 설계 스킬' 이 들어갑니다. "
                            "다 만든 그림은 'AI → 🖼 그림 한꺼번에 적용' 으로 한 번에 넣으세요.",
                  justify="left").pack(anchor="w")
        opt = ttk.Frame(self, padding=(8, 0))
        opt.pack(fill="x")
        ttk.Label(opt, text="포함할 그림").grid(row=0, column=0, sticky="w")
        self.groups = {}
        gf = ttk.Frame(opt)
        gf.grid(row=0, column=1, sticky="w")
        saved = AG.guide_options(p)
        for key, label in AG.GROUPS:
            v = tk.BooleanVar(value=key in saved["groups"])
            self.groups[key] = v
            ttk.Checkbutton(gf, text=label, variable=v, command=self._opts_changed).pack(side="left", padx=3)
        self.only_missing = tk.BooleanVar(value=saved["only_missing"])
        ttk.Checkbutton(opt, text="그림이 아직 없는 칸만", variable=self.only_missing,
                        command=self._opts_changed).grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(opt, text="화풍 (모든 그림 공통)").grid(row=2, column=0, sticky="nw", pady=4)
        self.style = tk.Text(opt, height=3, width=100, font=FONT, wrap="word")
        self.style.grid(row=2, column=1, sticky="we", pady=4)
        self.style.insert("1.0", p.get("art_style", ""))
        self.style.bind("<KeyRelease>", lambda _e: self._style_changed())
        # 그림체 참고 그림 (첨부)
        ttk.Label(opt, text="그림체 참고 그림\n(AI 에 첨부)").grid(row=3, column=0, sticky="nw", pady=4)
        rf = ttk.Frame(opt)
        rf.grid(row=3, column=1, sticky="we", pady=4)
        self.ref_strip = tk.Frame(rf, background="#f1f1f4", height=78)
        self.ref_strip.pack(side="left", fill="x", expand=True)
        rb = ttk.Frame(rf)
        rb.pack(side="left", padx=6)
        ttk.Button(rb, text="➕ 그림 추가…", command=self.add_refs).pack(fill="x")
        ttk.Button(rb, text="모두 빼기", command=self.clear_refs).pack(fill="x", pady=2)
        self._ref_photos = []
        opt.columnconfigure(1, weight=1)
        crow = ttk.Frame(self, padding=(8, 0))
        crow.pack(fill="x")
        self.count = ttk.Label(crow, text="", foreground="#555")
        self.count.pack(side="left")
        self.copied = ttk.Label(crow, text="", foreground="#2e7d32", font=("Malgun Gothic", 10, "bold"))
        self.copied.pack(side="left", padx=16)
        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        self.text = tk.Text(body, font=("Malgun Gothic", 9), wrap="word")
        sb = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(fill="both", expand=True)
        bt = ttk.Frame(self, padding=8)
        bt.pack(fill="x")
        ttk.Button(bt, text="📋 설명서 복사", command=self.copy).pack(side="left", padx=2)
        ttk.Button(bt, text="📦 AI에게 보낼 묶음 (설명서 + 참고 그림)", command=self.bundle).pack(side="left", padx=2)
        ttk.Button(bt, text="💾 .md 파일로 저장…", command=self.save).pack(side="left", padx=2)
        ttk.Button(bt, text="🖼 그림 한꺼번에 적용…", command=lambda: (self.destroy(), ArtApplyDialog(self.app))
                   ).pack(side="left", padx=12)
        ttk.Button(bt, text="닫기", command=self.destroy).pack(side="right")
        self.auto_copy = tk.BooleanVar(value=bool(app.settings.get("art_auto_copy", True)))
        ttk.Checkbutton(bt, text="창을 열면 자동으로 복사", variable=self.auto_copy,
                        command=lambda: app.settings.__setitem__("art_auto_copy", bool(self.auto_copy.get()))
                        ).pack(side="right", padx=10)
        self._job = None
        self.show_refs()
        self.rebuild()
        center_window(self)
        if self.auto_copy.get():
            self.copy(quiet=True)

    # ---- 그림체 참고 그림 ----
    def refs(self):
        return AG.style_refs(self.app.project)

    def show_refs(self):
        from PIL import Image, ImageTk
        for w in self.ref_strip.winfo_children():
            w.destroy()
        self._ref_photos = []
        refs = self.refs()
        if not refs:
            tk.Label(self.ref_strip, text="(없음) 원하는 그림체의 그림을 올리면, 설명서가 'AI 에 같이 첨부하라' 고 알려 주고\n"
                                          "그 그림의 선·채색·명암·색감을 따르게 합니다.",
                     background="#f1f1f4", foreground="#777", justify="left").pack(side="left", padx=6, pady=8)
            return
        for i, path in enumerate(refs):
            cell = tk.Frame(self.ref_strip, background="#f1f1f4")
            cell.pack(side="left", padx=3, pady=3)
            try:
                im = Image.open(path)
                im.thumbnail((64, 64))
                ph = ImageTk.PhotoImage(im)
                self._ref_photos.append(ph)
                tk.Label(cell, image=ph, background="#f1f1f4").pack()
            except Exception:
                tk.Label(cell, text="?", width=8, height=4).pack()
            row = tk.Frame(cell, background="#f1f1f4")
            row.pack()
            tk.Label(row, text=AG.ref_names(refs)[i], font=("Malgun Gothic", 7), background="#f1f1f4").pack(side="left")
            tk.Button(row, text="✕", font=("Malgun Gothic", 7), relief="flat", padx=1, pady=0,
                      command=lambda p=path: self.remove_ref(p)).pack(side="left")

    def add_refs(self):
        fs = filedialog.askopenfilenames(parent=self, title="원하는 그림체의 그림",
                                         filetypes=[("그림", "*.png *.jpg *.jpeg *.webp")])
        if not fs:
            return
        cur = list(self.app.project.get("art_style_refs") or [])
        cur += [f for f in fs if f not in cur]
        self.app.project["art_style_refs"] = cur[:10]
        self.app.mark_dirty()
        self.show_refs()
        self.rebuild()

    def remove_ref(self, path):
        self.app.project["art_style_refs"] = [p for p in self.app.project.get("art_style_refs") or [] if p != path]
        self.app.mark_dirty()
        self.show_refs()
        self.rebuild()

    def clear_refs(self):
        if self.app.project.get("art_style_refs"):
            self.app.project["art_style_refs"] = []
            self.app.mark_dirty()
            self.show_refs()
            self.rebuild()

    def _opts_changed(self):
        self.app.project["art_guide"] = {"groups": [k for k, v in self.groups.items() if v.get()],
                                         "only_missing": bool(self.only_missing.get())}
        self.app.mark_dirty()
        self.rebuild()

    def bundle(self):
        folder, zpath = AG.make_bundle(self.app.project, self.guide(), self.refs(), _requests_dir(self.app))
        self.copy(quiet=True)
        _open_folder(folder)
        messagebox.showinfo("AI에게 보낼 묶음", "설명서를 복사했고, 아래 폴더를 열었습니다.\n"
                                           f"{folder}\n\n채팅 AI 에 설명서를 붙여 넣고, 폴더의 style_ref 그림들을 끌어다 함께 첨부하세요.\n"
                                           f"(zip 하나로 올리려면: {os.path.basename(zpath)})", parent=self)

    def _style_changed(self):
        val = self.style.get("1.0", "end").strip()
        if self.app.project.get("art_style", "") != val:
            self.app.project["art_style"] = val
            self.app.mark_dirty()
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(400, self.rebuild)

    def chosen(self):
        return AG.chosen_slots(self.app.project, {"groups": [k for k, v in self.groups.items() if v.get()],
                                                  "only_missing": bool(self.only_missing.get())})

    def guide(self):
        app_dir = getattr(self.app, "app_dir", "") or ""
        return AG.build_guide(self.app.project, self.chosen(), self.style.get("1.0", "end"), app_dir, self.refs())

    def rebuild(self):
        self._job = None
        ch = self.chosen()
        self.count.configure(text=f"그림 {len(ch)}장  (" + ", ".join(
            f"{lab} {sum(1 for s in ch if s['group'] == g)}" for g, lab in AG.GROUPS if any(s['group'] == g for s in ch)) + ")")
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.guide())

    def copy(self, quiet=False):
        self.clipboard_clear()
        self.clipboard_append(self.guide())
        n = len(self.refs())
        self.copied.configure(text="✔ 설명서를 복사했습니다" + (f" · 참고 그림 {n}장은 '📦 묶음' 으로 첨부" if n else ""))
        if not quiet:
            messagebox.showinfo("그림 설명서", "복사했습니다. 채팅 AI 에 붙여 넣으세요.\n"
                                           "(그림을 만들 수 있는 AI 여야 합니다: ChatGPT 이미지 생성, Gemini 등)" +
                                ("\n\n그림체 참고 그림이 있으니 '📦 AI에게 보낼 묶음' 으로 폴더를 열어 함께 첨부하세요." if n else ""),
                                parent=self)

    def save(self):
        path = filedialog.asksaveasfilename(parent=self, defaultextension=".md", filetypes=[("Markdown", "*.md")],
                                            initialfile=f"{self.app.project['mod'].get('id', 'mod')}_그림설명서.md")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.guide())


class ArtApplyDialog(tk.Toplevel):
    def __init__(self, app, files=None):
        super().__init__(app)
        self.app = app
        self.title("🖼 그림 한꺼번에 적용")
        self.transient(app)
        self.geometry("1180x720")
        self.slot_list = AG.slots(app.project)
        self.files = []
        self.assign = {}
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="📦 zip 고르기…", command=self.pick_zip).pack(side="left", padx=2)
        ttk.Button(top, text="📁 폴더 고르기…", command=self.pick_folder).pack(side="left", padx=2)
        ttk.Button(top, text="그림 파일 고르기…", command=self.pick_files).pack(side="left", padx=2)
        self.src_label = ttk.Label(top, text="AI 가 준 zip 이나 그림 폴더를 고르세요. 파일 이름(card_strike.png) 또는 "
                                             "#번호(3.png)로 칸을 찾습니다.", foreground="#555")
        self.src_label.pack(side="left", padx=10)
        opt = ttk.Frame(self, padding=(8, 0))
        opt.pack(fill="x")
        self.remove_bg = tk.BooleanVar(value=True)
        ttk.Checkbutton(opt, text="투명 배경 칸은 단색 배경을 자동으로 지우기", variable=self.remove_bg,
                        command=self.show_preview).pack(side="left")
        ttk.Label(opt, text="   크기는 게임 크기로 자동 맞춤 (카드 1000×760 · 아이콘 256 · 초상화 132×195 · 지도 49×64 …)",
                  foreground="#777").pack(side="left")
        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=6)
        left = ttk.Frame(main)
        main.add(left, weight=3)
        cols = ("num", "slot", "file", "now")
        self.tree = ttk.Treeview(left, columns=cols, show="headings", selectmode="browse")
        for c, t, w in (("num", "#", 44), ("slot", "칸", 300), ("file", "넣을 그림", 260), ("now", "지금", 90)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w", stretch=c in ("slot", "file"))
        sb = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        right = ttk.Frame(main, padding=6)
        main.add(right, weight=2)
        self.pv_title = ttk.Label(right, text="", font=("Malgun Gothic", 10, "bold"), wraplength=420)
        self.pv_title.pack(anchor="w")
        row = ttk.Frame(right)
        row.pack(fill="x", pady=4)
        ttk.Label(row, text="그림:").pack(side="left")
        self.file_combo = ttk.Combobox(row, state="readonly", width=44)
        self.file_combo.pack(side="left", padx=4)
        self.file_combo.bind("<<ComboboxSelected>>", lambda _e: self.choose_file())
        ttk.Button(row, text="비우기", command=self.clear_one).pack(side="left")
        self.canvas = tk.Canvas(right, width=440, height=440, background="#2a2a32", highlightthickness=0)
        self.canvas.pack(pady=4)
        self.pv_note = ttk.Label(right, text="", foreground="#666", wraplength=430, justify="left")
        self.pv_note.pack(anchor="w")
        bt = ttk.Frame(self, padding=8)
        bt.pack(fill="x")
        self.summary = ttk.Label(bt, text="")
        self.summary.pack(side="left")
        ttk.Button(bt, text="취소", command=self.destroy).pack(side="right", padx=2)
        self.apply_btn = ttk.Button(bt, text="✔ 적용", command=self.do_apply)
        self.apply_btn.pack(side="right", padx=2)
        self._photo = None
        self.refresh()
        center_window(self)
        if files:
            self.load_files(files)

    # ---- 고르기 ----
    def pick_zip(self):
        z = filedialog.askopenfilename(parent=self, title="AI 가 준 그림 zip", filetypes=[("zip", "*.zip")])
        if not z:
            return
        try:
            files = AG.extract_zip(z)
        except Exception as exc:
            messagebox.showerror("zip 열기", f"zip 을 풀지 못했습니다: {exc}", parent=self)
            return
        if not files:
            messagebox.showinfo("zip 열기", "zip 안에 그림(png·jpg·webp)이 없습니다.", parent=self)
            return
        self.load_files(files)

    def pick_folder(self):
        d = filedialog.askdirectory(parent=self, title="AI 가 만든 그림 폴더")
        if d:
            self.load_files(AG.list_images(d))

    def pick_files(self):
        fs = filedialog.askopenfilenames(parent=self, filetypes=[("그림", "*.png *.jpg *.jpeg *.webp")])
        if fs:
            self.load_files(list(fs))

    def load_files(self, files):
        files = [f for f in files if "_적용됨" not in f.replace("\\", "/").split("/")]
        self.files = files
        self.assign = AG.match_files(self.slot_list, files)
        self.src_label.configure(text=f"그림 {len(files)}개 · 짝지어진 칸 {len(self.assign)}개"
                                      + (f" · 남은 그림 {len(files) - len(self.assign)}개 (칸을 골라 직접 지정)" if len(files) > len(self.assign) else ""))
        self.file_combo.configure(values=["(없음)"] + [os.path.basename(f) for f in files])
        self.refresh()

    def refresh(self):
        sel = self.tree.selection()
        self.tree.delete(*self.tree.get_children())
        for s in self.slot_list:
            f = self.assign.get(s["key"])
            now = "있음" if s["current"] and os.path.isfile(s["current"]) else "-"
            self.tree.insert("", "end", iid=s["key"], values=(s["num"], f"{s['title']} · {s['name']}  [{s['key']}]",
                                                             os.path.basename(f) if f else "", now))
        if sel and self.tree.exists(sel[0]):
            self.tree.selection_set(sel[0])
        self.summary.configure(text=f"적용할 그림 {len(self.assign)}장 / 칸 {len(self.slot_list)}개")

    def cur_slot(self):
        sel = self.tree.selection()
        return next((s for s in self.slot_list if sel and s["key"] == sel[0]), None)

    def on_select(self):
        s = self.cur_slot()
        if not s:
            return
        self.pv_title.configure(text=f"#{s['num']} {s['title']} — {s['name']}")
        f = self.assign.get(s["key"])
        self.file_combo.set(os.path.basename(f) if f else "(없음)")
        self.show_preview()

    def choose_file(self):
        s = self.cur_slot()
        if not s:
            return
        i = self.file_combo.current()
        if i <= 0:
            self.assign.pop(s["key"], None)
        else:
            f = self.files[i - 1]
            for k, v in list(self.assign.items()):     # 한 그림은 한 칸에만
                if v == f and k != s["key"]:
                    self.assign.pop(k)
            self.assign[s["key"]] = f
        self.refresh()
        self.show_preview()

    def clear_one(self):
        s = self.cur_slot()
        if s:
            self.assign.pop(s["key"], None)
            self.refresh()
            self.show_preview()

    def show_preview(self):
        from PIL import Image, ImageTk
        s = self.cur_slot()
        self.canvas.delete("all")
        if not s:
            return
        w, h, mode, tr, label = AG.SPECS[s["kind"]]
        src = self.assign.get(s["key"]) or (s["current"] if s["current"] and os.path.isfile(s["current"]) else "")
        note = f"{label}: " + (f"{w}×{h} " if w else "") + {"cover": "꽉 채우고 가운데 자르기", "contain": "비율 유지해 맞춤",
                                                          "sprite": "크기 유지"}[mode] + (" · 투명 배경" if tr else "")
        if not src:
            self.pv_note.configure(text=note + "\n(그림 없음)")
            return
        try:
            im = AG.process(src, s["kind"], self.remove_bg.get()) if self.assign.get(s["key"]) else Image.open(src).convert("RGBA")
        except Exception as exc:
            self.pv_note.configure(text=f"그림을 읽지 못했습니다: {exc}")
            return
        # 투명 부분이 보이게 체크무늬 위에
        bg = Image.new("RGBA", im.size, (60, 60, 70, 255))
        tile = 16
        from PIL import ImageDraw
        d = ImageDraw.Draw(bg)
        for y in range(0, im.size[1], tile):
            for x in range((y // tile) % 2 * tile, im.size[0], tile * 2):
                d.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(80, 80, 92, 255))
        bg.alpha_composite(im)
        r = min(430 / bg.size[0], 430 / bg.size[1], 4.0)
        show = bg.resize((max(1, int(bg.size[0] * r)), max(1, int(bg.size[1] * r))),
                         Image.NEAREST if r > 1.5 else Image.LANCZOS)
        self._photo = ImageTk.PhotoImage(show)
        self.canvas.create_image(220, 220, image=self._photo)
        self.pv_note.configure(text=note + f"\n결과 {im.size[0]}×{im.size[1]}" +
                               ("" if self.assign.get(s["key"]) else "  (지금 들어 있는 그림)"))

    def do_apply(self):
        if not self.assign:
            messagebox.showinfo("그림 적용", "적용할 그림이 없습니다. 폴더를 고르세요.", parent=self)
            return
        out = AG.out_dir_for(self.assign.values())
        replaced = sum(1 for s in self.slot_list if s["key"] in self.assign and s["current"])
        if replaced and not messagebox.askyesno("그림 적용", f"{len(self.assign)}장을 적용합니다. 이미 그림이 있는 칸 {replaced}개는 "
                                                       "새 그림으로 바뀝니다 (Ctrl+Z 로 되돌릴 수 있음).\n계속할까요?", parent=self):
            return
        if getattr(self, "_busy", False):
            return
        self._busy = True
        self.apply_btn.configure(state="disabled")
        self.grab_set()           # 적용하는 동안 다른 곳을 누르지 않게

        def progress(i, n, s):
            # 그림마다 화면을 돌려 준다 (오래 멈추면 윈도가 '응답 없음' 창으로 바꿔 Tk 가 깨질 수 있음)
            self.summary.configure(text=f"적용 중… {i}/{n}  {s['title']} · {s['name']}")
            self.update()
        try:
            done = AG.apply(self.app.project, self.slot_list, self.assign, out, self.remove_bg.get(),
                            log=self.app.log, progress=progress)
        except Exception as exc:
            self._busy = False
            self.grab_release()
            self.apply_btn.configure(state="normal")
            messagebox.showerror("그림 적용", f"적용하지 못했습니다: {exc}", parent=self)
            return
        app = self.app
        self._photo = None
        self.destroy()           # 창을 먼저 닫고 나서 앱 화면을 다시 그린다
        app.mark_dirty()
        app.load_all()
        try:
            app.commit_snapshot()
        except Exception:
            pass
        app.status(f"✔ 그림 {len(done)}장을 적용했습니다", 6000)
        messagebox.showinfo("그림 적용", f"{len(done)}장을 적용했습니다.\n다듬은 그림은 '{out}' 에 저장했습니다.", parent=app)

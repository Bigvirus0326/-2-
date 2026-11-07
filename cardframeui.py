"""카드 테두리 디자인 편집 창 — 스타일 목록 + 부위별(틀·그림 테두리·제목 띠) 설정 + 실시간 미리보기 3장."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, ttk

import cardframe as CF
from winpos import center_window

TITLE = "카드 테두리 디자인"
KEY_LABEL = {"all": "공통", "Attack": "공격", "Skill": "스킬", "Power": "파워"}
SAMPLE = {"Attack": ("타격", "피해를 6 줍니다."), "Skill": ("수비", "방어도를 5 얻습니다."),
          "Power": ("각성", "힘을 2 얻습니다.")}


class FrameStyleDialog(tk.Toplevel):
    def __init__(self, app, select=None, on_close=None):
        super().__init__(app)
        self.app, self.on_close = app, on_close
        self.title(TITLE)
        self.transient(app)
        self.configure(padx=10, pady=10)
        self.cur = None
        self._loading = False
        self._job = None
        self._photos = []
        self._base = {}
        assets = app.game_assets()
        for part in CF.PARTS:
            self._base[part] = CF.base_rgb_from(assets, part) if assets is not None else CF.BASE_RGB[part]

        top = ttk.Frame(self)
        top.pack(fill="both", expand=True)
        # ---- 왼쪽: 스타일 목록 ----
        left = ttk.Frame(top)
        left.pack(side="left", fill="y", padx=(0, 10))
        ttk.Label(left, text="테두리 디자인", style="Head.TLabel").pack(anchor="w")
        self.lst = tk.Listbox(left, width=24, height=14, exportselection=False, activestyle="none")
        self.lst.pack(fill="y", expand=True, pady=4)
        self.lst.bind("<<ListboxSelect>>", lambda _e: self._select())
        bf = ttk.Frame(left)
        bf.pack(fill="x")
        ttk.Button(bf, text="＋ 새로", style="Accent.TButton", command=self.add).pack(side="left", expand=True, fill="x")
        ttk.Button(bf, text="복제", command=self.duplicate).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(bf, text="삭제", command=self.delete).pack(side="left", expand=True, fill="x")
        ttk.Button(left, text="예시 추가 (청동빛)", command=self.add_example).pack(fill="x", pady=(4, 0))
        ttk.Separator(left).pack(fill="x", pady=8)
        ttk.Button(left, text="게임 원본 틀 PNG로 저장…", command=self.export).pack(fill="x")
        ttk.Label(left, text="원본 틀·테두리·띠를 꺼내\n그 위에 그려 '내 그림'으로\n쓰면 크기가 딱 맞습니다.",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(4, 0))

        # ---- 가운데: 설정 ----
        mid = ttk.Frame(top)
        mid.pack(side="left", fill="both", expand=True)
        nf = ttk.Frame(mid)
        nf.pack(fill="x")
        self.name = tk.StringVar()
        self.sid = tk.StringVar()
        ttk.Label(nf, text="이름").pack(side="left")
        ttk.Entry(nf, textvariable=self.name, width=18).pack(side="left", padx=(4, 12))
        ttk.Label(nf, text="ID").pack(side="left")
        ttk.Entry(nf, textvariable=self.sid, width=16).pack(side="left", padx=4)
        self.name.trace_add("write", lambda *_: self.changed())
        self.sid.trace_add("write", lambda *_: self.changed())
        self.ui = {}
        for part in CF.PARTS:
            self.ui[part] = self._part_box(mid, part)
        self.plaque = tk.BooleanVar(value=True)
        ttk.Checkbutton(mid, text="종류 명패(공격·스킬·파워)도 제목 띠 색으로 (제목 띠가 '색 바꾸기'일 때)",
                        variable=self.plaque, command=self.changed).pack(anchor="w", pady=(4, 0))
        self.warn = ttk.Label(mid, text="", foreground="#b4572f", wraplength=470, justify="left")
        self.warn.pack(anchor="w", pady=(4, 0))

        # ---- 오른쪽: 미리보기 ----
        right = ttk.Frame(top)
        right.pack(side="left", fill="both", padx=(10, 0))
        pv = ttk.Frame(right)
        pv.pack(fill="x")
        ttk.Label(pv, text="미리보기", style="Head.TLabel").pack(side="left")
        self.rarity = ttk.Combobox(pv, state="readonly", width=8, values=["일반", "특별", "희귀"])
        self.rarity.current(0)
        self.rarity.pack(side="right")
        self.rarity.bind("<<ComboboxSelected>>", lambda _e: self.schedule())
        ttk.Label(pv, text="희귀도").pack(side="right", padx=4)
        self.canvas = tk.Canvas(right, width=int(560 * app.ui), height=int(270 * app.ui), background="#1d1f24",
                                highlightthickness=0)
        self.canvas.pack(pady=4)
        ttk.Label(right, text="게임과 같은 계산(색 = 게임 hsv 셰이더, 그림 = 그대로)으로 그립니다.",
                  style="Muted.TLabel").pack(anchor="w")

        bot = ttk.Frame(self)
        bot.pack(fill="x", pady=(8, 0))
        ttk.Label(bot, text="쓰는 곳: 캐릭터 탭 '카드 테두리'(모든 카드 기본) · 카드 탭 '테두리 디자인'(카드마다)",
                  style="Muted.TLabel").pack(side="left")
        ttk.Button(bot, text="닫기", command=self.close).pack(side="right")
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.bind("<Escape>", lambda _e: self.close())
        self.refresh_list(select)
        center_window(self, app)
        self.grab_set()

    # ---- 부위 설정 상자 ----
    def _part_box(self, parent, part):
        box = ttk.LabelFrame(parent, text=f"{CF.PART_LABEL[part]}  (권장 {CF.SIZES[part][0]}×{CF.SIZES[part][1]})", padding=6)
        box.pack(fill="x", pady=(8, 0))
        w = {"mode": tk.StringVar(value="game")}
        mf = ttk.Frame(box)
        mf.pack(fill="x")
        for val, lab in CF.MODES[part]:
            ttk.Radiobutton(mf, text=lab, value=val, variable=w["mode"],
                            command=lambda p=part: (self._mode_ui(p), self.changed())).pack(side="left", padx=(0, 10))
        # 색
        cf = ttk.Frame(box)
        w["color_frame"] = cf
        w["swatch"] = tk.Label(cf, width=4, relief="groove", background="#888888")
        w["swatch"].pack(side="left")
        ttk.Button(cf, text="색 고르기…", command=lambda p=part: self.pick_color(p)).pack(side="left", padx=4)
        w["color"] = tk.StringVar()
        ttk.Entry(cf, textvariable=w["color"], width=9).pack(side="left")
        w["color"].trace_add("write", lambda *_, p=part: self.color_typed(p))
        ttk.Label(cf, text="   셰이더 H S V").pack(side="left")
        w["hsv"] = []
        for i, (lo, hi) in enumerate(((0, 1), (0, 5), (0, 5))):
            v = tk.StringVar()
            ttk.Spinbox(cf, from_=lo, to=hi, increment=0.01 if i == 0 else 0.05, textvariable=v, width=6).pack(side="left", padx=1)
            v.trace_add("write", lambda *_: self.changed())
            w["hsv"].append(v)
        # 그림
        imf = ttk.Frame(box)
        w["image_frame"] = imf
        w["images"] = {}
        for r, key in enumerate(CF.IMAGE_KEYS[part]):
            ttk.Label(imf, text=KEY_LABEL[key] + (" (비우면 공통)" if key != "all" else "")).grid(row=r, column=0, sticky="w")
            v = tk.StringVar()
            ttk.Entry(imf, textvariable=v, width=38).grid(row=r, column=1, sticky="we", padx=4, pady=1)
            ttk.Button(imf, text="찾기…", style="Small.TButton",
                       command=lambda v=v: self.browse(v)).grid(row=r, column=2)
            ttk.Button(imf, text="지우기", style="Small.TButton", command=lambda v=v: v.set("")).grid(row=r, column=3, padx=2)
            v.trace_add("write", lambda *_: self.changed())
            w["images"][key] = v
        imf.columnconfigure(1, weight=1)
        return w

    def _mode_ui(self, part):
        w = self.ui[part]
        m = w["mode"].get()
        w["color_frame"].pack_forget()
        w["image_frame"].pack_forget()
        if m == "color":
            w["color_frame"].pack(fill="x", pady=(6, 0))
        elif m == "image":
            w["image_frame"].pack(fill="x", pady=(6, 0))

    # ---- 목록 ----
    @property
    def styles(self):
        return CF.styles(self.app.project)

    def refresh_list(self, select=None):
        self.lst.delete(0, "end")
        for s in self.styles:
            self.lst.insert("end", f"▣ {s.get('name') or s['id']}  ({s['id']})")
        if self.styles:
            idx = next((i for i, s in enumerate(self.styles) if s["id"] == select), None)
            if idx is None:
                idx = min(self.cur or 0, len(self.styles) - 1)
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(idx)
            self.load(idx)
        else:
            self.cur = None
            self._enable(False)
            self.draw()

    def _enable(self, on):
        for part in CF.PARTS:
            self.ui[part]["mode"].set(self.ui[part]["mode"].get() if on else "game")
            self._mode_ui(part)

    def _select(self):
        s = self.lst.curselection()
        if s:
            self.load(s[0])

    def _unique(self, base):
        used = {s["id"] for s in self.styles}
        if base not in used:
            return base
        i = 0
        while True:
            cand = f"{base}_{'abcdefghijklmnopqrstuvwxyz'[i % 26] * (1 + i // 26)}"
            if cand not in used:
                return cand
            i += 1

    def add(self):
        st = CF.new_style(self._unique("frame"), "새 테두리")
        st["frame"].update(mode="color", color="#3a6fb0", hsv=CF.hsv_for("#3a6fb0", "frame", self._base["frame"]))
        self.styles.append(st)
        self.app.mark_dirty()
        self.refresh_list(st["id"])

    def add_example(self):
        st = CF.new_style(self._unique("bronze"), "청동빛 테두리")
        st["frame"].update(mode="color", color="#8c6420", hsv=CF.hsv_for("#8c6420", "frame", self._base["frame"]))
        st["banner"].update(mode="color", color="#9c2a32", hsv=CF.hsv_for("#9c2a32", "banner", self._base["banner"]))
        self.styles.append(st)
        self.app.mark_dirty()
        self.refresh_list(st["id"])

    def duplicate(self):
        if self.cur is None:
            return
        st = CF.clone_style(self.styles[self.cur], self._unique(self.styles[self.cur]["id"]))
        self.styles.insert(self.cur + 1, st)
        self.app.mark_dirty()
        self.refresh_list(st["id"])

    def delete(self):
        if self.cur is None:
            return
        st = self.styles[self.cur]
        if not messagebox.askyesno(TITLE, f"'{st.get('name') or st['id']}' 테두리를 지울까요?\n"
                                          "이 테두리를 쓰던 카드는 게임 원래 테두리로 돌아갑니다.", parent=self):
            return
        CF.rename(self.app.project, st["id"], None)
        del self.styles[self.cur]
        self.app.mark_dirty()
        self.refresh_list()

    # ---- 불러오기 / 저장 ----
    def load(self, idx):
        self.cur = idx
        st = self.styles[idx]
        self._loading = True
        try:
            self.name.set(st.get("name", ""))
            self.sid.set(st["id"])
            self.plaque.set(bool(st.get("plaque_follows", True)))
            for part in CF.PARTS:
                w, p = self.ui[part], st[part]
                w["mode"].set(p.get("mode", "game"))
                w["color"].set(p.get("color", ""))
                for v, x in zip(w["hsv"], p.get("hsv", [1, 1, 1])):
                    v.set(f"{float(x):.4g}")
                for key, v in w["images"].items():
                    v.set((p.get("images") or {}).get(key, ""))
                self._mode_ui(part)
                self._swatch(part)
        finally:
            self._loading = False
        self._warn()
        self.draw()

    def changed(self):
        if self._loading or self.cur is None:
            return
        st = self.styles[self.cur]
        old = st["id"]
        st["name"] = self.name.get().strip()
        new = self.sid.get().strip()
        if new and new != old:
            st["id"] = new
            CF.rename(self.app.project, old, new)
        st["plaque_follows"] = bool(self.plaque.get())
        for part in CF.PARTS:
            w, p = self.ui[part], st[part]
            p["mode"] = w["mode"].get()
            p["color"] = w["color"].get().strip()
            hsv = []
            for v, d in zip(w["hsv"], p.get("hsv", [1, 1, 1])):
                try:
                    hsv.append(float(v.get()))
                except ValueError:
                    hsv.append(float(d))
            p["hsv"] = hsv
            p["images"] = {k: v.get().strip().strip('"') for k, v in w["images"].items()}
        self.lst.delete(self.cur)
        self.lst.insert(self.cur, f"▣ {st.get('name') or st['id']}  ({st['id']})")
        self.lst.selection_set(self.cur)
        self.app.mark_dirty()
        self._warn()
        self.schedule()

    # ---- 색 ----
    def _swatch(self, part):
        w = self.ui[part]
        col = w["color"].get().strip()
        try:
            w["swatch"].configure(background=col if col.startswith("#") and len(col) == 7 else "#888888")
        except tk.TclError:
            w["swatch"].configure(background="#888888")

    def pick_color(self, part):
        w = self.ui[part]
        res = colorchooser.askcolor(color=w["color"].get() or "#888888", parent=self, title=f"{CF.PART_LABEL[part]} 색")
        if res and res[1]:
            w["color"].set(res[1])

    def color_typed(self, part):
        """색을 정하면 게임 셰이더 H S V 를 계산해 채운다."""
        if self._loading:
            return
        w = self.ui[part]
        col = w["color"].get().strip()
        self._swatch(part)
        if len(col) == 7 and col.startswith("#"):
            h, s, v = CF.hsv_for(col, part, self._base[part])
            self._loading = True
            try:
                for var, x in zip(w["hsv"], (h, s, v)):
                    var.set(f"{x:.4g}")
            finally:
                self._loading = False
        self.changed()

    def _warn(self):
        if self.cur is None:
            self.warn.configure(text="")
            return
        st = self.styles[self.cur]
        msgs = []
        fr = st["frame"]
        if fr.get("mode") == "color" and float((fr.get("hsv") or [1, 1, 1])[2]) > 1.8:
            msgs.append("⚠ 카드 틀 색이 밝아 설명 칸도 밝아집니다 (게임에서도 같음). 글자가 잘 보이게 조금 어두운 색을 권합니다.")
        for part in CF.PARTS:
            p = st[part]
            if p.get("mode") == "image" and not any((p.get("images") or {}).values()):
                msgs.append(f"{CF.PART_LABEL[part]}: 그림을 고르지 않아 게임 그림을 씁니다.")
        if any(st[p].get("mode") == "image" for p in CF.PARTS):
            msgs.append("내 그림은 ④ 게시(dll+pck)로 담아야 게임에 보입니다.")
        self.warn.configure(text="\n".join(msgs))

    def browse(self, var):
        p = filedialog.askopenfilename(parent=self, filetypes=[("PNG 이미지", "*.png"), ("모든 파일", "*.*")])
        if p:
            var.set(p)

    def export(self):
        assets = self.app.game_assets()
        if assets is None:
            messagebox.showerror(TITLE, "게임 파일을 찾지 못했습니다. '모드 / 빌드' 탭에서 슬더스2 설치 폴더를 정하세요.", parent=self)
            return
        folder = filedialog.askdirectory(parent=self, title="원본 틀을 저장할 폴더")
        if not folder:
            return
        try:
            names = CF.export_templates(assets, folder)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(TITLE, f"저장하지 못했습니다:\n{e}", parent=self)
            return
        messagebox.showinfo(TITLE, f"{len(names)}개를 저장했습니다:\n" + "\n".join(names) +
                            "\n\n틀 598×844 · 그림 테두리 551×420 · 제목 띠 655×170", parent=self)

    # ---- 미리보기 ----
    def schedule(self):
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(200, self.draw)

    def draw(self):
        self._job = None
        c = self.canvas
        c.delete("all")
        self._photos = []
        assets = self.app.game_assets()
        if assets is None:
            c.create_text(10, 10, anchor="nw", fill="#ccc", text="게임 파일이 있어야 미리보기를 그릴 수 있습니다.")
            return
        try:
            import ingame
            from PIL import ImageTk
        except ImportError:
            return
        st = self.styles[self.cur] if self.cur is not None else None
        rarity = ("Common", "Uncommon", "Rare")[max(0, self.rarity.current())]
        lang = "ko"
        cw = int(c.cget("width"))
        tw = (cw - 40) // 3
        for i, t in enumerate(CF.TYPES):
            name, desc = SAMPLE[t]
            card = {"id": f"sample_{t.lower()}", "type": t, "rarity": rarity, "cost": 1, "upgrade_cost": 1,
                    "name_ko": name, "name_en": t, "desc_ko": desc, "effects": [], "keywords": [], "image": "",
                    "_frame_style": st}
            try:
                im = ingame.compose(assets, self.app.project, "card", card, lang)
            except Exception as e:  # noqa: BLE001
                c.create_text(10 + i * (tw + 10), 10, anchor="nw", fill="#f88", text=str(e)[:60], width=tw)
                continue
            k = tw / im.width
            im = im.resize((tw, int(im.height * k)))
            ph = ImageTk.PhotoImage(im)
            self._photos.append(ph)
            c.create_image(10 + i * (tw + 10), 6, image=ph, anchor="nw")

    def close(self):
        try:
            self.grab_release()
        except tk.TclError:
            pass
        self.destroy()
        if self.on_close:
            self.on_close()

"""
'🎨 이펙트 · 버튼' 탭.

  * 이펙트 그리기: 붓·직선·원·고리·사각형·다각형·그림으로 직접 그리고, 도형마다 움직임(이동·크기·회전·사라짐·복제)을 정한다.
                   ▶ 재생으로 게임과 같은 계산으로 바로 미리보기 (전투 화면 모형 위).
  * 전투 버튼:     카스토리스 '숨결' 같은 버튼을 만든다. 오른쪽 시험장에서 눌러 보며 비용·횟수 제한·이펙트를 확인한다.
  * 게임 안 시험:  빌드한 모드에서 개발자 콘솔 '<모드id>fx 이펙트id' / '<모드id>btn 버튼id' 로 바로 확인.
"""
from __future__ import annotations

import copy
import math
import time
import tkinter as tk
import types
from tkinter import colorchooser, filedialog, messagebox, ttk

import fxbtn as FX
from docking import DockPanedWindow

APP_TITLE = "StS2 모드 메이커"
CW, CH = 900, 520                     # 무대 크기 (게임 좌표 1:1)
W_GAME, H_GAME = 1920, 1080
PLAYER_FEET = (250, 450)
ENEMY_FEET = (660, 450)
TOOLS = [("select", "↖ 선택·이동"), ("stroke", "🖌 붓"), ("line", "／ 직선"), ("circle", "● 원"), ("ring", "◯ 고리"),
         ("rect", "▭ 사각형"), ("poly", "⬠ 다각형"), ("image", "🖼 그림")]


# ---------------------------------------------------------------------------
# 무대 배경 (전투 화면 모형)
# ---------------------------------------------------------------------------
_STAGE = {}
_ASSETS = {"get": None}


def _assets():
    try:
        return _ASSETS["get"]() if _ASSETS["get"] else None
    except Exception:  # noqa: BLE001
        return None


def stage_image(show_grid=True, enemy=False, project=None):
    ch = (project or {}).get("character") or {}
    key = (show_grid, enemy, ch.get("combat_image"), ch.get("combat_scale"), ch.get("combat_flip"), ch.get("combat_lift"))
    if key in _STAGE:
        return _STAGE[key].copy()
    from PIL import Image, ImageDraw
    a = _assets()
    if a is not None:
        import gamescene as GS
        full = GS.scene(a, {"character": ch, "gimmicks": {}}, {"hp": 75, "maxhp": 75, "ehp": 60, "emaxhp": 60}, ui=False)
        cx, cy = (GS.ENEMY[0] - ENEMY_FEET[0], GS.ENEMY[1] - ENEMY_FEET[1]) if enemy else \
            (GS.PLAYER[0] - PLAYER_FEET[0], GS.PLAYER[1] - PLAYER_FEET[1])
        im = full.crop((cx, cy, cx + CW, cy + CH))
        if show_grid:
            ov = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for x in range(0, CW, 50):
                od.line([(x, 0), (x, CH)], fill=(255, 255, 255, 22))
            for y in range(0, CH, 50):
                od.line([(0, y), (CW, y)], fill=(255, 255, 255, 22))
            im.alpha_composite(ov)
        _STAGE[key] = im
        return im.copy()
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    for y in range(CH):
        k = y / CH
        d.line([(0, y), (CW, y)], fill=(int(28 + 20 * k), int(24 + 14 * k), int(44 + 10 * k), 255))
    d.rectangle((0, 455, CW, CH), fill=(36, 30, 40, 255))
    d.line([(0, 455), (CW, 455)], fill=(70, 60, 74, 255), width=2)
    if show_grid:
        ov = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for x in range(0, CW, 50):
            od.line([(x, 0), (x, CH)], fill=(255, 255, 255, 18))
        for y in range(0, CH, 50):
            od.line([(0, y), (CW, y)], fill=(255, 255, 255, 18))
        im.alpha_composite(ov)
        d = ImageDraw.Draw(im)

    def body(fx, fy, col, flip=False):
        d.ellipse((fx - 55, fy - 12, fx + 55, fy + 8), fill=(0, 0, 0, 90))
        d.rounded_rectangle((fx - 38, fy - 190, fx + 38, fy - 40), 26, fill=col)
        d.ellipse((fx - 30, fy - 250, fx + 30, fy - 190), fill=col)
        d.rectangle((fx - 30, fy - 45, fx - 10, fy), fill=col)
        d.rectangle((fx + 10, fy - 45, fx + 30, fy), fill=col)
    body(*PLAYER_FEET, (92, 110, 160, 255))
    body(*ENEMY_FEET, (150, 80, 80, 255))
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("malgun.ttf", 16)
    except OSError:
        font = None
    d.text((PLAYER_FEET[0] - 8, PLAYER_FEET[1] + 14), "나", fill=(200, 210, 240, 255), font=font)
    d.text((ENEMY_FEET[0] - 8, ENEMY_FEET[1] + 14), "적", fill=(240, 200, 200, 255), font=font)
    _STAGE[key] = im
    return im.copy()


def _font_for(size):
    return ("Malgun Gothic", size)


# ---------------------------------------------------------------------------
# 탭
# ---------------------------------------------------------------------------
class FxTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.z = max(1.0, min(1.6, getattr(app, "ui", 1.0)))
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True)
        _ASSETS["get"] = app.game_assets
        self.painter = EffectPainter(nb, self)
        self.buttons = ButtonDesigner(nb, self)
        nb.add(self.painter, text="  🎨 이펙트 그리기  ")
        nb.add(self.buttons, text="  🔘 전투 버튼  ")
        self.nb = nb

    @property
    def project(self):
        return self.app.project

    @property
    def g(self):
        # 정규화는 비어 있을 때만 (매번 하면 dict 가 새로 만들어져 편집 중인 참조가 끊긴다)
        g = self.app.project.get("gimmicks")
        if not isinstance(g, dict) or "effects" not in g or "buttons" not in g:
            import gimmick as G
            G.normalize(self.app.project)
        return self.app.project["gimmicks"]

    def load(self):
        self.painter.load()
        self.buttons.load()

    def dirty(self):
        self.app.mark_dirty()

    def unique(self, base):
        used = self.app.all_ids()
        if base not in used:
            return base
        import gimmick as G
        i = 1
        while f"{base}_{G.letters(i).lower()}" in used:
            i += 1
        return f"{base}_{G.letters(i).lower()}"


# ---------------------------------------------------------------------------
# 이펙트 그리기
# ---------------------------------------------------------------------------
class EffectPainter(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.z = tab.z
        self.cur = None          # 이펙트 번호
        self.sel = None          # 도형 번호
        self.tool = tk.StringVar(value="stroke")
        self.color = "#b48cff"
        self.width = tk.StringVar(value="4")
        self.alpha = tk.StringVar(value="1.0")
        self.fill = tk.BooleanVar(value=True)
        self.grid_on = tk.BooleanVar(value=True)
        self.at_enemy = tk.BooleanVar(value=False)
        self.loop = tk.BooleanVar(value=True)
        self.speed = tk.StringVar(value="1")
        self.fast = tk.BooleanVar(value=False)
        self.playing = False
        self.t = 0.0
        self.drawing = None
        self.history = []
        self._loading = False
        self._photo = None
        self._after = None

        panels = DockPanedWindow(self, title="이펙트 그리기", orient="horizontal")
        panels.pack(fill="both", expand=True)
        # ---- 왼쪽: 이펙트 목록 ----
        left = panels.add_panel(lambda parent:ttk.Frame(parent, padding=6), "이펙트 목록", weight=0)
        ttk.Label(left, text="이펙트", font=("Malgun Gothic", 10, "bold")).pack(anchor="w")
        self.lst = tk.Listbox(left, width=26, height=12, exportselection=False, activestyle="none")
        self.lst.pack(fill="y")
        self.lst.bind("<<ListboxSelect>>", lambda _e: self.select_effect())
        bf = ttk.Frame(left)
        bf.pack(fill="x", pady=4)
        ttk.Button(bf, text="새로", width=6, command=self.add_effect).pack(side="left")
        ttk.Button(bf, text="복제", width=6, command=self.dup_effect).pack(side="left", padx=2)
        ttk.Button(bf, text="삭제", width=6, command=self.del_effect).pack(side="left")
        self.ev = {}
        for k, label in (("id", "ID"), ("name", "이름"), ("x", "기준점 X"), ("y", "기준점 Y"), ("z", "앞뒤 (Z)")):
            f = ttk.Frame(left)
            f.pack(fill="x", pady=1)
            ttk.Label(f, text=label, width=8).pack(side="left")
            v = tk.StringVar()
            ttk.Entry(f, textvariable=v, width=16).pack(side="left", fill="x", expand=True)
            v.trace_add("write", lambda *_: self.effect_changed())
            self.ev[k] = v
        ttk.Label(left, text="기준점: 캐릭터 발밑에서의 위치.\n(0, -120) = 몸통 가운데.\n블록 '이펙트 재생'에서\n'모든 적'을 고르면 적마다 재생.",
                  foreground="#777", justify="left").pack(anchor="w", pady=6)
        ttk.Label(left, text="게임 안에서 시험:\n개발자 콘솔에\n  <모드id 소문자>fx 이펙트id\n  …fx 이펙트id enemy",
                  foreground="#555", justify="left").pack(anchor="w")

        # ---- 가운데: 도구 + 무대 + 재생 ----
        mid = panels.add_panel(lambda parent:ttk.Frame(parent, padding=6), "그리기 작업 공간", weight=1)
        tb = ttk.Frame(mid)
        tb.pack(fill="x")
        for val, label in TOOLS:
            ttk.Radiobutton(tb, text=label, value=val, variable=self.tool, command=self.tool_changed).pack(side="left", padx=2)
        sb = ttk.Frame(mid)
        sb.pack(fill="x", pady=(4, 2))
        ttk.Label(sb, text="색").pack(side="left")
        self.swatch = tk.Label(sb, width=3, background=self.color, relief="groove")
        self.swatch.pack(side="left", padx=2)
        self.swatch.bind("<Button-1>", lambda _e: self.pick_color())
        ttk.Button(sb, text="고르기", width=6, command=self.pick_color).pack(side="left")
        ttk.Label(sb, text="  굵기").pack(side="left")
        ttk.Spinbox(sb, from_=1, to=60, textvariable=self.width, width=4, command=self.style_to_sel).pack(side="left")
        ttk.Label(sb, text="  불투명").pack(side="left")
        ttk.Spinbox(sb, from_=0.05, to=1.0, increment=0.05, textvariable=self.alpha, width=5, command=self.style_to_sel).pack(side="left")
        ttk.Checkbutton(sb, text="채우기", variable=self.fill, command=self.style_to_sel).pack(side="left", padx=6)
        ttk.Checkbutton(sb, text="격자", variable=self.grid_on, command=self.redraw).pack(side="left", padx=6)
        ttk.Checkbutton(sb, text="적 위치에서 보기", variable=self.at_enemy, command=self.redraw).pack(side="left")
        ttk.Label(sb, text="   되돌리기: Ctrl+Z", foreground="#777").pack(side="left")
        self.canvas = tk.Canvas(mid, width=int(CW * self.z), height=int(CH * self.z), background="#111", highlightthickness=0,
                                cursor="crosshair")
        self.canvas.pack(pady=4)
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Double-Button-1>", self.on_double)
        self.canvas.bind("<Button-3>", self.on_double)
        # Ctrl+Z 는 앱이 받아서, 이 화면이 보일 때 _undo_key 를 부른다 (sts2_mod_maker.App._key_undo)
        pb = ttk.Frame(mid)
        pb.pack(fill="x")
        self.play_btn = ttk.Button(pb, text="▶ 재생", width=9, command=self.toggle_play)
        self.play_btn.pack(side="left")
        ttk.Button(pb, text="⏮ 처음", width=7, command=lambda: self.seek(0)).pack(side="left", padx=2)
        ttk.Checkbutton(pb, text="반복", variable=self.loop).pack(side="left", padx=4)
        ttk.Label(pb, text="속도").pack(side="left")
        ttk.Combobox(pb, values=["1", "0.5", "0.25"], textvariable=self.speed, width=5, state="readonly").pack(side="left", padx=2)
        ttk.Checkbutton(pb, text="게임 '빠르게' 설정으로", variable=self.fast).pack(side="left", padx=6)
        self.tvar = tk.DoubleVar(value=0)
        self.scale = ttk.Scale(pb, from_=0, to=1, variable=self.tvar, command=lambda _v: self.seek(self.tvar.get(), from_scale=True))
        self.scale.pack(side="left", fill="x", expand=True, padx=8)
        self.tlabel = ttk.Label(pb, text="0.00 / 0.00초", width=16)
        self.tlabel.pack(side="left")
        self.hint = ttk.Label(mid, text="", foreground="#555")
        self.hint.pack(anchor="w")

        # ---- 오른쪽: 도형 목록 + 움직임 ----
        right = panels.add_panel(lambda parent:ttk.Frame(parent, padding=6), "도형·움직임", weight=0)
        ttk.Label(right, text="도형", font=("Malgun Gothic", 10, "bold")).pack(anchor="w")
        self.shapes = tk.Listbox(right, width=30, height=9, exportselection=False, activestyle="none")
        self.shapes.pack(fill="x")
        self.shapes.bind("<<ListboxSelect>>", lambda _e: self.select_shape(self.shapes.curselection()[0] if self.shapes.curselection() else None))
        sf = ttk.Frame(right)
        sf.pack(fill="x", pady=3)
        for txt, cmd in (("▲", lambda: self.move_shape(-1)), ("▼", lambda: self.move_shape(1)), ("복제", self.dup_shape),
                         ("삭제", self.del_shape)):
            ttk.Button(sf, text=txt, width=5, command=cmd).pack(side="left", padx=1)
        af = ttk.LabelFrame(right, text="움직임 (고른 도형)", padding=6)
        af.pack(fill="x", pady=6)
        self.av = {}
        rows = (("start", "시작 (초)", 0, 5, 0.05), ("dur", "길이 (초)", 0.05, 5, 0.05), ("mx", "이동 X", -900, 900, 10),
                ("my", "이동 Y", -600, 600, 10), ("scale", "크기 (배)", 0, 10, 0.1), ("rot", "회전 (도)", -1440, 1440, 15),
                ("fade", "끝 불투명", 0, 1, 0.1), ("copies", "복제 수", 1, 60, 1), ("spread", "퍼짐 (px)", 0, 900, 10))
        for r, (k, label, lo, hi, inc) in enumerate(rows):
            ttk.Label(af, text=label).grid(row=r, column=0, sticky="w", pady=1)
            v = tk.StringVar()
            sp = ttk.Spinbox(af, from_=lo, to=hi, increment=inc, textvariable=v, width=8)
            sp.grid(row=r, column=1, sticky="w")
            v.trace_add("write", lambda *_: self.anim_changed())
            self.av[k] = v
        ttk.Label(af, text="가속").grid(row=len(rows), column=0, sticky="w")
        self.ease = ttk.Combobox(af, values=[l for _, l in FX.EASES], state="readonly", width=12)
        self.ease.grid(row=len(rows), column=1, sticky="w")
        self.ease.bind("<<ComboboxSelected>>", lambda _e: self.anim_changed())
        ttk.Label(af, text="복제 수 > 1 이면 사방으로 '퍼짐'만큼\n흩어집니다 (나비 떼, 파편).",
                  foreground="#777", justify="left").grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=4)
        self.info = ttk.Label(right, text="", foreground="#2d4f6a", wraplength=260, justify="left")
        self.info.pack(anchor="w")
        self.load()

    # ---- 데이터 ----
    @property
    def fxs(self):
        return self.tab.g["effects"]

    @property
    def fx(self):
        return self.fxs[self.cur] if self.cur is not None and self.cur < len(self.fxs) else None

    def load(self):
        self.lst.delete(0, "end")
        for e in self.fxs:
            self.lst.insert("end", f"✦ {e.get('name') or e['id']}  ({e['id']})")
        if self.fxs:
            i = min(self.cur or 0, len(self.fxs) - 1)
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(i)
            self.select_effect(i)
        else:
            self.cur = None
            self.redraw()

    def select_effect(self, i=None):
        if i is None:
            s = self.lst.curselection()
            if not s:
                return
            i = s[0]
        self.cur = i
        self.sel = None
        self.history = []
        self._loading = True
        try:
            for k, v in self.ev.items():
                v.set(str(self.fx.get(k, "")))
        finally:
            self._loading = False
        self.refresh_shapes()
        self.seek(0)

    def effect_changed(self):
        if self._loading or self.fx is None:
            return
        e = self.fx
        old = e["id"]
        for k, v in self.ev.items():
            val = v.get().strip()
            if k in ("x", "y", "z"):
                try:
                    e[k] = float(val) if k != "z" else int(float(val))
                except ValueError:
                    continue
            else:
                e[k] = val
        if e["id"] != old and e["id"]:
            _rename(self.tab.project, "fx", old, e["id"])
        self.lst.delete(self.cur)
        self.lst.insert(self.cur, f"✦ {e.get('name') or e['id']}  ({e['id']})")
        self.lst.selection_set(self.cur)
        self.tab.dirty()
        self.redraw()

    def add_effect(self):
        e = FX.new_effect(self.tab.unique("new_fx"))
        self.fxs.append(e)
        self.cur = len(self.fxs) - 1
        self.tab.dirty()
        self.load()

    def dup_effect(self):
        if self.fx is None:
            return
        e = copy.deepcopy(self.fx)
        e["id"] = self.tab.unique(e["id"])
        e["name"] = (e.get("name") or "") + " (복사)"
        self.fxs.insert(self.cur + 1, e)
        self.cur += 1
        self.tab.dirty()
        self.load()

    def del_effect(self):
        if self.fx is None:
            return
        if not messagebox.askyesno(APP_TITLE, f"이펙트 '{self.fx.get('name')}'를 삭제할까요?", parent=self):
            return
        _rename(self.tab.project, "fx", self.fx["id"], None)
        del self.fxs[self.cur]
        self.cur = max(0, self.cur - 1)
        self.tab.dirty()
        self.load()

    # ---- 도형 목록 ----
    def refresh_shapes(self):
        self.shapes.delete(0, "end")
        if self.fx is None:
            return
        names = dict(FX.SHAPE_TYPES)
        for i, s in enumerate(self.fx["shapes"]):
            a = s.get("anim") or {}
            extra = f" ×{a.get('copies')}" if int(a.get("copies", 1) or 1) > 1 else ""
            self.shapes.insert("end", f"{i + 1}. {names.get(s['type'], s['type'])}{extra}  {a.get('start', 0)}~{float(a.get('start', 0) or 0) + float(a.get('dur', 0.5) or 0.5):.2f}s")
        if self.sel is not None and self.sel < len(self.fx["shapes"]):
            self.shapes.selection_set(self.sel)
        self.info.configure(text=f"도형 {len(self.fx['shapes'])}개 · 전체 {FX.total_time(self.fx):.2f}초")

    def select_shape(self, i):
        self.sel = i
        if i is None or self.fx is None or i >= len(self.fx["shapes"]):
            self.sel = None
            self.redraw()
            return
        s = self.fx["shapes"][i]
        a = s.get("anim") or FX.new_anim()
        self._loading = True
        try:
            self.av["start"].set(str(a.get("start", 0)))
            self.av["dur"].set(str(a.get("dur", 0.5)))
            mv = a.get("move") or [0, 0]
            self.av["mx"].set(str(mv[0]))
            self.av["my"].set(str(mv[1]))
            for k in ("scale", "rot", "fade", "copies", "spread"):
                self.av[k].set(str(a.get(k, "")))
            self.ease.set(dict(FX.EASES).get(a.get("ease", "out"), "점점 느리게"))
            self.color = s.get("color") or self.color
            self.swatch.configure(background=self.color)
            self.width.set(str(s.get("width", 4)))
            self.alpha.set(str(s.get("alpha", 1)))
            self.fill.set(bool(s.get("fill")))
        finally:
            self._loading = False
        self.shapes.selection_clear(0, "end")
        self.shapes.selection_set(i)
        self.redraw()

    def anim_changed(self):
        if self._loading or self.fx is None or self.sel is None:
            return
        s = self.fx["shapes"][self.sel]
        a = s.setdefault("anim", FX.new_anim())

        def num(k, cast=float):
            try:
                return cast(float(self.av[k].get()))
            except ValueError:
                return None
        for k, cast in (("start", float), ("dur", float), ("scale", float), ("rot", float), ("fade", float),
                        ("copies", int), ("spread", float)):
            v = num(k, cast)
            if v is not None:
                a[k] = v
        mx, my = num("mx"), num("my")
        if mx is not None and my is not None:
            a["move"] = [mx, my]
        lab = self.ease.get()
        a["ease"] = next((k for k, l in FX.EASES if l == lab), a.get("ease", "out"))
        self.tab.dirty()
        self.refresh_shapes()
        self.redraw()

    def style_to_sel(self):
        if self._loading or self.fx is None or self.sel is None:
            return
        s = self.fx["shapes"][self.sel]
        self.push()
        s["color"] = self.color
        try:
            s["width"] = float(self.width.get())
            s["alpha"] = max(0.0, min(1.0, float(self.alpha.get())))
        except ValueError:
            pass
        s["fill"] = bool(self.fill.get())
        self.tab.dirty()
        self.redraw()

    def pick_color(self):
        res = colorchooser.askcolor(color=self.color, parent=self)
        if res and res[1]:
            self.color = res[1]
            self.swatch.configure(background=self.color)
            self.style_to_sel()

    def move_shape(self, d):
        if self.fx is None or self.sel is None:
            return
        sh = self.fx["shapes"]
        j = self.sel + d
        if 0 <= j < len(sh):
            self.push()
            sh[self.sel], sh[j] = sh[j], sh[self.sel]
            self.sel = j
            self.tab.dirty()
            self.refresh_shapes()
            self.redraw()

    def dup_shape(self):
        if self.fx is None or self.sel is None:
            return
        self.push()
        s = copy.deepcopy(self.fx["shapes"][self.sel])
        _offset(s, 20, 20)
        self.fx["shapes"].insert(self.sel + 1, s)
        self.sel += 1
        self.tab.dirty()
        self.refresh_shapes()
        self.redraw()

    def del_shape(self):
        if self.fx is None or self.sel is None:
            return
        self.push()
        del self.fx["shapes"][self.sel]
        self.sel = None
        self.tab.dirty()
        self.refresh_shapes()
        self.redraw()

    def push(self):
        if self.fx is not None:
            self.history.append(copy.deepcopy(self.fx["shapes"]))
            self.history = self.history[-60:]

    def _undo_key(self, _e):
        if self.winfo_ismapped() and self.history and self.fx is not None:
            self.fx["shapes"] = self.history.pop()
            self.sel = None
            self.tab.dirty()
            self.refresh_shapes()
            self.redraw()

    # ---- 좌표 ----
    def origin(self):
        feet = ENEMY_FEET if self.at_enemy.get() else PLAYER_FEET
        e = self.fx or {"x": 0, "y": -120}
        return feet[0] + float(e.get("x", 0)), feet[1] + float(e.get("y", -120))

    def to_local(self, ev):
        ox, oy = self.origin()
        return round(ev.x / self.z - ox, 1), round(ev.y / self.z - oy, 1)

    def to_screen(self, x, y):
        ox, oy = self.origin()
        return (x + ox) * self.z, (y + oy) * self.z

    # ---- 그리기 ----
    def tool_changed(self):
        hints = {"select": "도형을 눌러 고르고 끌어서 옮깁니다.", "stroke": "누른 채로 끌어서 자유롭게 그립니다.",
                 "line": "끌어서 직선을 긋습니다.", "circle": "가운데를 누르고 끌어서 크기를 정합니다.",
                 "ring": "가운데를 누르고 끌어서 크기를 정합니다.", "rect": "모서리에서 끌어 사각형을 그립니다.",
                 "poly": "점을 하나씩 찍고, 더블클릭(또는 오른쪽 클릭)으로 마칩니다.",
                 "image": "넣을 곳을 누르면 PNG 를 고릅니다 (불꽃·칼날 그림 등)."}
        self.hint.configure(text=hints.get(self.tool.get(), ""))
        self.drawing = None
        self.canvas.delete("temp")

    def _style(self):
        try:
            w = float(self.width.get())
        except ValueError:
            w = 4
        try:
            al = max(0.05, min(1.0, float(self.alpha.get())))
        except ValueError:
            al = 1.0
        return {"color": self.color, "width": w, "alpha": al}

    def on_press(self, ev):
        if self.fx is None:
            self.add_effect()
        self.stop()
        x, y = self.to_local(ev)
        tool = self.tool.get()
        if tool == "select":
            i = self.hit(x, y)
            self.select_shape(i)
            if i is not None:
                self.push()
                self.drawing = {"kind": "move", "last": (x, y)}
            return
        if tool == "poly":
            if not self.drawing or self.drawing.get("kind") != "poly":
                self.drawing = {"kind": "poly", "pts": []}
            self.drawing["pts"].append([x, y])
            self.temp_poly()
            return
        if tool == "image":
            p = filedialog.askopenfilename(filetypes=[("PNG 이미지", "*.png"), ("모든 파일", "*.*")], parent=self)
            if not p:
                return
            im = FX._load_img(p)
            w, h = (im.size if im else (80, 80))
            k = 120 / max(w, h)
            self.add_shape(FX.new_shape("image", cx=x, cy=y, w=round(w * k), h=round(h * k), image=p, **self._style()))
            return
        self.drawing = {"kind": tool, "p0": (x, y), "pts": [[x, y]]}

    def on_drag(self, ev):
        d = self.drawing
        if not d:
            return
        x, y = self.to_local(ev)
        if d["kind"] == "move":
            lx, ly = d["last"]
            _offset(self.fx["shapes"][self.sel], x - lx, y - ly)
            d["last"] = (x, y)
            self.redraw()
            return
        if d["kind"] == "stroke":
            lx, ly = d["pts"][-1]
            if math.hypot(x - lx, y - ly) >= 3:
                d["pts"].append([x, y])
        else:
            d["p1"] = (x, y)
        self.temp_draw()

    def on_release(self, ev):
        d = self.drawing
        if not d or d["kind"] == "poly":
            return
        self.drawing = None
        self.canvas.delete("temp")
        if d["kind"] == "move":
            self.tab.dirty()
            self.refresh_shapes()
            return
        x0, y0 = d["p0"]
        x1, y1 = d.get("p1", d["p0"])
        st = self._style()
        k = d["kind"]
        if k == "stroke" and len(d["pts"]) >= 2:
            self.add_shape(FX.new_shape("stroke", points=_simplify(d["pts"]), fill=False, **st))
        elif k == "line" and (x0, y0) != (x1, y1):
            self.add_shape(FX.new_shape("line", points=[[x0, y0], [x1, y1]], fill=False, **st))
        elif k in ("circle", "ring"):
            r = max(4.0, round(math.hypot(x1 - x0, y1 - y0), 1))
            self.add_shape(FX.new_shape(k, cx=x0, cy=y0, r=r, fill=(k == "circle"), **st))
        elif k == "rect" and abs(x1 - x0) > 2 and abs(y1 - y0) > 2:
            self.add_shape(FX.new_shape("rect", cx=(x0 + x1) / 2, cy=(y0 + y1) / 2, w=abs(x1 - x0), h=abs(y1 - y0),
                                        fill=bool(self.fill.get()), **st))

    def on_double(self, _ev):
        d = self.drawing
        if d and d.get("kind") == "poly":
            self.drawing = None
            self.canvas.delete("temp")
            pts = d["pts"]
            if len(pts) >= 3:
                self.add_shape(FX.new_shape("poly", points=pts, fill=bool(self.fill.get()), **self._style()))

    def add_shape(self, s):
        self.push()
        self.fx["shapes"].append(s)
        self.sel = len(self.fx["shapes"]) - 1
        self.tab.dirty()
        self.refresh_shapes()
        self.select_shape(self.sel)

    def temp_draw(self):
        d = self.drawing
        self.canvas.delete("temp")
        col = self.color
        try:
            w = max(1, float(self.width.get()) * self.z)
        except ValueError:
            w = 4
        if d["kind"] == "stroke":
            pts = [c for p in d["pts"] for c in self.to_screen(*p)]
            if len(pts) >= 4:
                self.canvas.create_line(*pts, fill=col, width=w, capstyle="round", joinstyle="round", smooth=True, tags="temp")
            return
        x0, y0 = self.to_screen(*d["p0"])
        x1, y1 = self.to_screen(*d.get("p1", d["p0"]))
        if d["kind"] == "line":
            self.canvas.create_line(x0, y0, x1, y1, fill=col, width=w, capstyle="round", tags="temp")
        elif d["kind"] in ("circle", "ring"):
            r = math.hypot(x1 - x0, y1 - y0)
            if d["kind"] == "circle":
                self.canvas.create_oval(x0 - r, y0 - r, x0 + r, y0 + r, fill=col, outline="", tags="temp")
            else:
                self.canvas.create_oval(x0 - r, y0 - r, x0 + r, y0 + r, outline=col, width=w, tags="temp")
        elif d["kind"] == "rect":
            self.canvas.create_rectangle(x0, y0, x1, y1, outline=col, width=2, fill=col if self.fill.get() else "", tags="temp")

    def temp_poly(self):
        self.canvas.delete("temp")
        pts = [c for p in self.drawing["pts"] for c in self.to_screen(*p)]
        for i in range(0, len(pts), 2):
            self.canvas.create_oval(pts[i] - 3, pts[i + 1] - 3, pts[i] + 3, pts[i + 1] + 3, fill=self.color, outline="white", tags="temp")
        if len(pts) >= 4:
            self.canvas.create_line(*pts, fill=self.color, width=2, dash=(4, 2), tags="temp")

    def hit(self, x, y):
        if self.fx is None:
            return None
        for i in range(len(self.fx["shapes"]) - 1, -1, -1):
            x1, y1, x2, y2 = _bbox(self.fx["shapes"][i])
            if x1 - 6 <= x <= x2 + 6 and y1 - 6 <= y <= y2 + 6:
                return i
        return None

    # ---- 화면 ----
    def redraw(self, t=None):
        from PIL import ImageTk
        base = stage_image(self.grid_on.get(), self.at_enemy.get(), self.tab.project)
        if self.fx is not None:
            still = t is None
            img = FX.render(self.fx, t or 0.0, (CW, CH), (self.origin()[0] - float(self.fx.get("x", 0)),
                                                         self.origin()[1] - float(self.fx.get("y", -120))),
                            img=base, still=still, ss=1 if (self.playing and not still) else 2)
        else:
            img = base
        if self.z != 1:
            from PIL import Image
            img = img.resize((int(CW * self.z), int(CH * self.z)), Image.BILINEAR)
        self._photo = ImageTk.PhotoImage(img)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, anchor="nw", image=self._photo)
        if self.fx is not None:
            ox, oy = self.to_screen(0, 0)
            self.canvas.create_line(ox - 8, oy, ox + 8, oy, fill="#ffcc33")
            self.canvas.create_line(ox, oy - 8, ox, oy + 8, fill="#ffcc33")
            if t is None and self.sel is not None and self.sel < len(self.fx["shapes"]):
                x1, y1, x2, y2 = _bbox(self.fx["shapes"][self.sel])
                a, b = self.to_screen(x1, y1)
                c, d = self.to_screen(x2, y2)
                self.canvas.create_rectangle(a - 4, b - 4, c + 4, d + 4, outline="#33d6ff", dash=(4, 3))
        if t is None:
            self.canvas.create_text(10, 10, anchor="nw", fill="#9aa", font=_font_for(9),
                                    text="편집 화면: 모든 도형을 처음 모습으로 보여 줍니다. ▶ 재생으로 움직임 확인.")

    # ---- 재생 ----
    def toggle_play(self):
        if self.playing:
            self.stop()
        else:
            self.play()

    def play(self):
        if self.fx is None or not self.fx.get("shapes"):
            return
        self.playing = True
        self.play_btn.configure(text="■ 정지")
        if self.t >= FX.total_time(self.fx) - 1e-3:
            self.t = 0.0
        self._t0 = time.perf_counter() - self.t / self._rate()
        self._tick()

    def _rate(self):
        try:
            r = float(self.speed.get())
        except ValueError:
            r = 1.0
        return r * (2.0 if self.fast.get() else 1.0)   # 게임 '빠르게' = 시간 0.5배

    def _tick(self):
        if not self.playing or self.fx is None:
            return
        total = FX.total_time(self.fx)
        self.t = (time.perf_counter() - self._t0) * self._rate()
        if self.t > total + 0.25:
            if self.loop.get():
                self._t0 = time.perf_counter()
                self.t = 0.0
            else:
                self.stop()
                return
        self.show_time(min(self.t, total))
        self._after = self.after(33, self._tick)

    def stop(self):
        self.playing = False
        self.play_btn.configure(text="▶ 재생")
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        self.redraw()

    def seek(self, t, from_scale=False):
        if self.fx is None:
            self.redraw()
            return
        total = FX.total_time(self.fx)
        if from_scale:
            t = float(t) * total
        self.t = t
        if t <= 0 and not from_scale:
            self.redraw()
            self.tlabel.configure(text=f"0.00 / {total:.2f}초")
            self.tvar.set(0)
            return
        self.show_time(t)

    def show_time(self, t):
        total = FX.total_time(self.fx)
        self.redraw(t)
        self.tlabel.configure(text=f"{t:.2f} / {total:.2f}초")
        self.tvar.set(t / total if total else 0)


def _offset(s, dx, dy):
    if s["type"] in ("circle", "ring", "rect", "image"):
        s["cx"] = round(float(s.get("cx", 0)) + dx, 1)
        s["cy"] = round(float(s.get("cy", 0)) + dy, 1)
    else:
        s["points"] = [[round(p[0] + dx, 1), round(p[1] + dy, 1)] for p in s.get("points") or []]


def _bbox(s):
    t = s["type"]
    if t in ("circle", "ring"):
        r = float(s.get("r", 20))
        return s["cx"] - r, s["cy"] - r, s["cx"] + r, s["cy"] + r
    if t in ("rect", "image"):
        w2, h2 = float(s.get("w", 40)) / 2, float(s.get("h", 40)) / 2
        return s["cx"] - w2, s["cy"] - h2, s["cx"] + w2, s["cy"] + h2
    pts = s.get("points") or [[0, 0]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _simplify(pts, tol=1.6):
    """붓 선 점을 줄인다 (Ramer-Douglas-Peucker)."""
    if len(pts) < 3:
        return pts

    def rdp(a, b, seg):
        (x1, y1), (x2, y2) = a, b
        best, idx = 0.0, -1
        L = math.hypot(x2 - x1, y2 - y1) or 1e-9
        for i, (x, y) in enumerate(seg):
            d = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / L
            if d > best:
                best, idx = d, i
        if best > tol:
            m = seg[idx]
            return rdp(a, m, seg[:idx]) + [m] + rdp(m, b, seg[idx + 1:])
        return []
    return [pts[0]] + rdp(pts[0], pts[-1], pts[1:-1]) + [pts[-1]]


def _rename(project, kind, old, new):
    """이펙트/버튼 ID 변경을 블록·버튼 참조에 반영."""
    key = "fx" if kind == "fx" else "button"

    def fix(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if k == key and v == old and (kind == "fx" or "label_ko" not in o):
                    o[k] = new or ""
                else:
                    fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    for k in ("cards", "relics", "potions", "powers"):
        fix(project.get(k, []))
    g = project.get("gimmicks") or {}
    for k in ("summons", "orbs"):
        fix(g.get(k, []))
    for b in g.get("buttons", []):
        if kind == "fx" and b.get("fx") == old:
            b["fx"] = new or ""
        fix(b.get("blocks", []))


# ---------------------------------------------------------------------------
# 전투 버튼
# ---------------------------------------------------------------------------
class ButtonDesigner(ttk.Frame):
    def __init__(self, master, tab):
        super().__init__(master)
        self.tab = tab
        self.z = tab.z
        self.cur = None
        self._loading = False
        self.hover = False
        self.fx_play = []          # [(fx, origin, t0)]
        self._photo = None
        self._after = None

        panels = DockPanedWindow(self, title="전투 버튼", orient="horizontal")
        panels.pack(fill="both", expand=True)
        left = panels.add_panel(lambda parent:ttk.Frame(parent, padding=6), "버튼 목록", weight=0)
        ttk.Label(left, text="버튼", font=("Malgun Gothic", 10, "bold")).pack(anchor="w")
        self.lst = tk.Listbox(left, width=26, height=8, exportselection=False, activestyle="none")
        self.lst.pack(fill="x")
        self.lst.bind("<<ListboxSelect>>", lambda _e: self.select())
        bf = ttk.Frame(left)
        bf.pack(fill="x", pady=4)
        ttk.Button(bf, text="새로", width=6, command=self.add).pack(side="left")
        ttk.Button(bf, text="삭제", width=6, command=self.delete).pack(side="left", padx=2)

        form = panels.add_panel(lambda parent:ttk.Frame(parent, padding=6), "버튼 편집기", weight=0)
        self.v = {}
        r = 0

        def ent(label, key, width=24, hint=""):
            nonlocal r
            ttk.Label(form, text=label).grid(row=r, column=0, sticky="w", pady=1)
            var = tk.StringVar()
            ttk.Entry(form, textvariable=var, width=width).grid(row=r, column=1, columnspan=3, sticky="w", pady=1)
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var
            if hint:
                ttk.Label(form, text=hint, foreground="#777").grid(row=r, column=4, sticky="w")
            r += 1
        ent("ID", "id")
        ent("이름 (한국어)", "label_ko")
        ent("이름 (영어)", "label_en")
        ent("이름 (중국어 간체)", "label_zh", hint="비우면 영어")
        ent("둘째 줄 (한국어)", "sub_ko", hint="# = 표시 값")
        ent("둘째 줄 (영어)", "sub_en")
        ent("둘째 줄 (중국어 간체)", "sub_zh")
        ttk.Label(form, text="표시 값 (#)").grid(row=r, column=0, sticky="w")
        self.val_btn = ttk.Button(form, text="", width=30, command=lambda: self.edit_slot("value"))
        self.val_btn.grid(row=r, column=1, columnspan=3, sticky="w")
        r += 1
        ent("툴팁 (한국어)", "tip_ko", 40)
        ent("툴팁 (영어)", "tip_en", 40)
        ent("툴팁 (중국어 간체)", "tip_zh", 40)
        for key, label in (("bg", "바탕색"), ("border", "테두리색"), ("text", "글자색")):
            ttk.Label(form, text=label).grid(row=r, column=0, sticky="w")
            var = tk.StringVar()
            e = ttk.Entry(form, textvariable=var, width=9)
            e.grid(row=r, column=1, sticky="w")
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var
            ttk.Button(form, text="고르기", width=6, command=lambda k=key: self.pick(k)).grid(row=r, column=2, sticky="w")
            r += 1
        ttk.Label(form, text="위치 기준").grid(row=r, column=0, sticky="w")
        self.anchor_opts = FX.anchor_options(self.tab.project)
        self.anchor = ttk.Combobox(form, state="readonly", width=40, values=[l for _k, l in self.anchor_opts])
        self.anchor.grid(row=r, column=1, columnspan=3, sticky="w")
        self.anchor.bind("<<ComboboxSelected>>", lambda _e: (self.changed(), self._anchor_ui()))
        r += 1
        sz = ttk.Frame(form)
        sz.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        for key, label in (("w", "너비"), ("h", "높이")):
            ttk.Label(sz, text=label).pack(side="left")
            var = tk.StringVar()
            ttk.Spinbox(sz, from_=20, to=1200, increment=5, textvariable=var, width=6).pack(side="left", padx=(2, 8))
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var
        ttk.Label(sz, text="(기준 1920×1080 화면에서의 px, 화면 크기에 맞춰 같이 커지고 작아짐)", foreground="#777").pack(side="left")
        r += 1
        self.pos_screen = ttk.Frame(form)
        self.pos_screen.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        for key, label in (("rx", "가로 위치 %"), ("ry", "세로 위치 %")):
            ttk.Label(self.pos_screen, text=label).pack(side="left")
            var = tk.StringVar()
            ttk.Spinbox(self.pos_screen, from_=0, to=100, increment=0.5, textvariable=var, width=6).pack(side="left", padx=(2, 8))
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var
        ttk.Label(self.pos_screen, text="버튼 가운데가 놓일 화면 위치 (0 = 왼쪽/위, 100 = 오른쪽/아래)", foreground="#777").pack(side="left")
        self.pos_creature = ttk.Frame(form)
        self.pos_creature.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        for key, label in (("x", "위치 X"), ("y", "위치 Y")):
            ttk.Label(self.pos_creature, text=label).pack(side="left")
            var = tk.StringVar()
            ttk.Spinbox(self.pos_creature, from_=-1200, to=1200, increment=5, textvariable=var, width=6).pack(side="left", padx=(2, 8))
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var
        ttk.Label(self.pos_creature, text="캐릭터 발밑 기준 px (기본 -95, -470 = 머리 위)", foreground="#777").pack(side="left")
        r += 1
        ttk.Label(form, text="오른쪽 시험장에서 Ctrl+끌기로 옮길 수 있고, '화면 비율'을 바꿔 가며 다른 모니터에서의 자리를 확인하세요.",
                  foreground="#777", wraplength=430, justify="left").grid(row=r, column=0, columnspan=4, sticky="w")
        r += 1
        cf = ttk.Frame(form)
        cf.grid(row=r, column=0, columnspan=4, sticky="w", pady=2)
        for key, label in (("energy_cost", "에너지 비용"), ("per_turn", "턴당 횟수(0=무제한)"), ("per_combat", "전투당 횟수")):
            ttk.Label(cf, text=label).pack(side="left")
            var = tk.StringVar()
            ttk.Spinbox(cf, from_=0, to=99, textvariable=var, width=4).pack(side="left", padx=(2, 8))
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var
        r += 1
        ttk.Label(form, text="자원 비용").grid(row=r, column=0, sticky="w")
        self.res = ttk.Combobox(form, state="readonly", width=26)
        self.res.grid(row=r, column=1, columnspan=2, sticky="w")
        self.res.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        var = tk.StringVar()
        ttk.Spinbox(form, from_=0, to=99, textvariable=var, width=4).grid(row=r, column=3, sticky="w")
        var.trace_add("write", lambda *_: self.changed())
        self.v["res_cost"] = var
        r += 1
        ttk.Label(form, text="쓸 수 있는 조건").grid(row=r, column=0, sticky="w")
        self.cond_btn = ttk.Button(form, text="", width=30, command=lambda: self.edit_slot("cond"))
        self.cond_btn.grid(row=r, column=1, columnspan=2, sticky="w")
        ttk.Button(form, text="없애기", width=6, command=lambda: self.clear_slot("cond")).grid(row=r, column=3, sticky="w")
        r += 1
        ttk.Label(form, text="누를 때 이펙트").grid(row=r, column=0, sticky="w")
        self.fx = ttk.Combobox(form, state="readonly", width=26)
        self.fx.grid(row=r, column=1, columnspan=3, sticky="w")
        self.fx.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        r += 1
        ttk.Label(form, text="켜는 유물").grid(row=r, column=0, sticky="w")
        self.relic = ttk.Combobox(form, state="readonly", width=26)
        self.relic.grid(row=r, column=1, columnspan=3, sticky="w")
        self.relic.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        r += 1
        ttk.Label(form, text="이 유물을 가지고 전투를 시작하면 버튼이 생깁니다 (시작 유물 권장).\n"
                             "아니면 카드·파워 블록 '버튼 켜기'로 켭니다.", foreground="#777", justify="left").grid(
            row=r, column=0, columnspan=4, sticky="w")
        r += 1
        ttk.Button(form, text="🧩 눌렀을 때 실행할 블록…", command=self.edit_blocks).grid(row=r, column=0, columnspan=2, sticky="w", pady=6)
        r += 1
        self.desc = ttk.Label(form, text="", foreground="#2d4f6a", wraplength=440, justify="left")
        self.desc.grid(row=r, column=0, columnspan=4, sticky="w")

        # ---- 시험장 (게임 전투 화면) ----
        right = panels.add_panel(lambda parent:ttk.Frame(parent, padding=6), "전투 시험장", weight=1)
        top = ttk.Frame(right)
        top.pack(fill="x")
        ttk.Label(top, text="시험장 — 게임 전투 화면 그대로. 버튼을 눌러 보세요", font=("Malgun Gothic", 10, "bold")).pack(side="left")
        self.lang = tk.StringVar(value="ko")
        for val, lab in (("zh", "简体中文"), ("en", "English"), ("ko", "한국어")):
            ttk.Radiobutton(top, text=lab, value=val, variable=self.lang, command=self.redraw_all).pack(side="right", padx=4)
        import gamescene as GS
        self.aspect = ttk.Combobox(top, state="readonly", width=24,
                                   values=[f"{n}  (게임 화면 {w}×{h})" for n, w, h in GS.ASPECTS])
        self.aspect.current(0)
        self.aspect.pack(side="right", padx=8)
        self.aspect.bind("<<ComboboxSelected>>", lambda _e: self._aspect_changed())
        ttk.Label(top, text="모니터 화면 비율").pack(side="right")
        self.vw, self.vh = W_GAME, H_GAME
        self.canvas = tk.Canvas(right, width=int(W_GAME * 0.4 * self.z), height=int(H_GAME * 0.4 * self.z),
                                background="#111", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, pady=4)
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<Motion>", self.on_motion)
        self.canvas.bind("<ButtonPress-1>", self.on_click)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: setattr(self, "_drag", None))
        stf = ttk.Frame(right)
        stf.pack(fill="x")
        self.e_var, self.r_var, self.p_var, self.s_var = (tk.StringVar(value=v) for v in ("3", "5", "0", "0"))
        self.res_lbl = ttk.Label(stf, text="자원")
        for label, var, lab_widget in (("에너지", self.e_var, None), (None, self.r_var, self.res_lbl),
                                       ("이번 턴 사용한 카드", self.p_var, None), ("별", self.s_var, None)):
            (lab_widget or ttk.Label(stf, text=label)).pack(side="left")
            ttk.Spinbox(stf, from_=0, to=99, textvariable=var, width=4, command=self._vars_changed).pack(side="left", padx=(2, 10))
            var.trace_add("write", lambda *_: self._vars_changed())
        ttk.Button(stf, text="⏭ 턴 넘기기", command=self.next_turn).pack(side="left", padx=6)
        ttk.Button(stf, text="↺ 전투 다시", command=self.reset_sim).pack(side="left")
        self.log = tk.Text(right, height=7, font=("Malgun Gothic", 9), wrap="word", background="#f7f7fa")
        self.log.pack(fill="x", pady=4)
        self.ds = 0.4 * self.z
        self.popups = []
        self._base = None
        self._base_key = None
        self._drag = None
        self.st = {}
        self.load()

    # ---- 데이터 ----
    @property
    def items(self):
        return self.tab.g["buttons"]

    @property
    def b(self):
        return self.items[self.cur] if self.cur is not None and self.cur < len(self.items) else None

    def load(self):
        import modgen as M
        self.lst.delete(0, "end")
        for b in self.items:
            self.lst.insert("end", f"🔘 {b.get('label_ko') or '?'}  ({b['id']})")
        self.res_opts = [("", "없음")] + M.power_options(self.tab.project)
        self.res["values"] = [l for _, l in self.res_opts]
        self.fx_opts = [("", "없음")] + [(e["id"], e.get("name") or e["id"]) for e in FX.effects(self.tab.project)]
        self.fx["values"] = [l for _, l in self.fx_opts]
        self.relic_opts = [("", "없음 (블록으로 켜기)")] + [(r["id"], r.get("name_ko") or r["id"]) for r in self.tab.project.get("relics", [])]
        self.relic["values"] = [l for _, l in self.relic_opts]
        if self.items:
            i = min(self.cur or 0, len(self.items) - 1)
            self.lst.selection_clear(0, "end")
            self.lst.selection_set(i)
            self.select(i)
        else:
            self.cur = None
            self.draw()

    def select(self, i=None):
        if i is None:
            s = self.lst.curselection()
            if not s:
                return
            i = s[0]
        self.cur = i
        b = self.b
        self._loading = True
        try:
            for k, var in self.v.items():
                var.set(str(b.get(k, "")))
            self.res.set(dict(self.res_opts).get(b.get("res_power", ""), "없음"))
            self.fx.set(dict(self.fx_opts).get(b.get("fx", ""), "없음"))
            self.relic.set(dict(self.relic_opts).get(b.get("auto_relic", ""), "없음 (블록으로 켜기)"))
            self.anchor_opts = FX.anchor_options(self.tab.project)
            self.anchor.configure(values=[l for _k, l in self.anchor_opts])
            keys = [k for k, _l in self.anchor_opts]
            cur = b.get("anchor", "creature")
            if cur not in keys:          # 지워진 동료 등: 목록에 보이게 남겨 둔다
                self.anchor_opts.append((cur, f"(없는 기준: {cur})"))
                self.anchor.configure(values=[l for _k, l in self.anchor_opts])
                keys.append(cur)
            self.anchor.current(keys.index(cur))
        finally:
            self._loading = False
        self._anchor_ui()
        self.refresh_labels()
        self.reset_sim()

    def changed(self):
        if self._loading or self.b is None:
            return
        b = self.b
        old = b["id"]
        for k, var in self.v.items():
            val = var.get().strip()
            if k in ("w", "h", "x", "y", "energy_cost", "per_turn", "per_combat", "res_cost"):
                try:
                    b[k] = int(float(val))
                except ValueError:
                    pass
            elif k in ("rx", "ry"):
                try:
                    b[k] = round(max(0.0, min(100.0, float(val))), 2)
                except ValueError:
                    pass
            else:
                b[k] = val
        i_a = self.anchor.current()
        b["anchor"] = self.anchor_opts[i_a][0] if 0 <= i_a < len(self.anchor_opts) else "creature"
        b["res_power"] = next((k for k, l in self.res_opts if l == self.res.get()), "")
        b["fx"] = next((k for k, l in self.fx_opts if l == self.fx.get()), "")
        b["auto_relic"] = next((k for k, l in self.relic_opts if l == self.relic.get()), "")
        if b["id"] != old and b["id"]:
            _rename(self.tab.project, "button", old, b["id"])
        self.lst.delete(self.cur)
        self.lst.insert(self.cur, f"🔘 {b.get('label_ko') or '?'}  ({b['id']})")
        self.lst.selection_set(self.cur)
        self.tab.dirty()
        self.refresh_labels()
        self.draw()

    def _anchor_ui(self):
        i_a = self.anchor.current()
        if 0 <= i_a < len(getattr(self, "anchor_opts", [])) and self.anchor_opts[i_a][0] != "screen":
            self.pos_screen.grid_remove()
            self.pos_creature.grid()
        else:
            self.pos_creature.grid_remove()
            self.pos_screen.grid()

    def refresh_labels(self):
        import blockcode as B
        import blockui
        b = self.b
        if b is None:
            return
        P = self.tab.project
        self.val_btn.configure(text=(blockui._plain(B.value_label(b["value"], P)) if isinstance(b.get("value"), dict) else "(없음)") + " ✎")
        self.cond_btn.configure(text=(blockui._plain(B.cond_label(b["cond"], P)) if isinstance(b.get("cond"), dict) else "(항상)") + " ✎")
        d = blockui._plain(B.describe(b.get("blocks"), P, "power", "ko")) or "(블록 없음)"
        self.desc.configure(text="누르면: " + d)

    def edit_slot(self, key):
        if self.b is None:
            return
        import blockui
        ed = types.SimpleNamespace(project=self.tab.project, owner_kind="button", allow_event=False)
        cur = self.b.get(key) or ({"t": "num", "v": 0} if key == "value" else {"t": "cmp", "a": {"t": "stars"}, "op": ">=", "b": {"t": "num", "v": 1}})
        d = blockui.SlotDialog(self, ed, key if key == "cond" else "value", cur)
        self.wait_window(d)
        if d.result is not None:
            self.b[key] = d.result
            self.tab.dirty()
            self.refresh_labels()

    def clear_slot(self, key):
        if self.b is not None:
            self.b[key] = None
            self.tab.dirty()
            self.refresh_labels()

    def pick(self, key):
        if self.b is None:
            return
        res = colorchooser.askcolor(color=self.v[key].get() or "#ffffff", parent=self)
        if res and res[1]:
            self.v[key].set(res[1])

    def edit_blocks(self):
        if self.b is None:
            return
        import blockui
        b = self.b
        ed = blockui.BlockEditor(self, self.tab.project, "button", {"id": b["id"], "trigger": "none", "enemy_mode": "all"},
                                 b.get("blocks") or [], where=f"버튼 '{b.get('label_ko')}'을 눌렀을 때")
        self.wait_window(ed)
        if ed.result is not None:
            b["blocks"] = ed.result["blocks"]
            self.tab.dirty()
            self.refresh_labels()

    def add(self):
        self.items.append(FX.new_button(self.tab.unique("new_button")))
        self.cur = len(self.items) - 1
        self.tab.dirty()
        self.load()

    def delete(self):
        if self.b is None:
            return
        if not messagebox.askyesno(APP_TITLE, f"버튼 '{self.b.get('label_ko')}'를 삭제할까요?", parent=self):
            return
        _rename(self.tab.project, "button", self.b["id"], None)
        del self.items[self.cur]
        self.cur = max(0, self.cur - 1)
        self.tab.dirty()
        self.load()

    # ---- 시험장 ----
    def assets(self):
        return _assets()

    def _resize(self, ev):
        self._cw, self._ch = ev.width, ev.height
        self.ds = max(0.1, min(ev.width / self.vw, ev.height / self.vh))
        self._base_key = None
        self.draw()

    def _aspect_changed(self):
        import gamescene as GS
        _n, self.vw, self.vh = GS.ASPECTS[max(0, self.aspect.current())]
        cw, ch = getattr(self, "_cw", self.canvas.winfo_width()), getattr(self, "_ch", self.canvas.winfo_height())
        self.ds = max(0.1, min(cw / self.vw, ch / self.vh))
        self._base_key = None
        self.fx_play, self.popups = [], []
        self.draw()

    def feet(self, enemy=False):
        import gamescene as GS
        return GS.view_pos(GS.ENEMY if enemy else GS.PLAYER, self.vw, self.vh)

    def redraw_all(self):
        self._base_key = None
        self.draw()

    def reset_sim(self):
        if not hasattr(self, "e_var"):
            return
        ch = self.tab.project.get("character") or {}
        hp = int(ch.get("hp", 75) or 75)
        self.st = {"hp": hp, "maxhp": hp, "block": 0, "ehp": 60, "emaxhp": 60, "eblock": 0, "energy": 3, "maxenergy": 3,
                   "stars": 0, "res": {}, "played": 0, "turn": 1, "intent": 9, "turn_uses": 0, "combat_uses": 0}
        self._busy = True
        try:
            self.e_var.set("3")
            self.p_var.set("0")
            self.s_var.set("0")
        finally:
            self._busy = False
        self._vars_changed()
        self.log.delete("1.0", "end")
        self.write("전투 시작 — 버튼이 켜졌습니다." + (f" (유물 '{self.b.get('auto_relic')}')" if self.b and self.b.get("auto_relic") else ""))
        self.fx_play, self.popups = [], []
        self.draw()

    def _vars_changed(self):
        if getattr(self, "_busy", False) or not self.st:
            return
        def num(v, d=0):
            try:
                return max(0, int(float(v.get())))
            except (ValueError, tk.TclError):
                return d
        b = self.b
        self.st["energy"] = num(self.e_var, 3)
        self.st["played"] = num(self.p_var)
        self.st["stars"] = num(self.s_var)
        self.st["res"] = {}
        if b and b.get("res_power"):
            self.st["res"][b["res_power"]] = num(self.r_var, 5)
            import gamescene as GS
            self.res_lbl.configure(text=GS._pname(self.tab.project, b["res_power"]))
        else:
            self.res_lbl.configure(text="자원 (없음)")
        self._base_key = None
        self.draw()

    def _push_vars(self):
        self._busy = True
        try:
            self.e_var.set(str(self.st["energy"]))
            self.s_var.set(str(self.st.get("stars", 0)))
            b = self.b
            if b and b.get("res_power"):
                self.r_var.set(str(self.st["res"].get(b["res_power"], 0)))
        finally:
            self._busy = False

    def next_turn(self):
        st = self.st
        st["turn"] = st.get("turn", 1) + 1
        st["turn_uses"] = 0
        st["energy"] = st.get("maxenergy", 3)
        st["block"] = 0
        st["played"] = 0
        dmg = st.get("intent", 9)
        st["hp"] = max(0, st["hp"] - dmg)
        self.popups.append(("self", dmg, time.perf_counter()))
        self._busy = True
        try:
            self.p_var.set("0")
        finally:
            self._busy = False
        self._push_vars()
        self.write(f"— {st['turn']}턴: 적이 {dmg} 피해로 공격, 에너지 {st['energy']}, 방어도 초기화, 턴당 횟수 초기화 —")
        self._base_key = None
        self._anim()

    def write(self, s):
        self.log.insert("end", s + "\n")
        self.log.see("end")

    def rect(self):
        """버튼 자리 (게임 화면 좌표). 게임 코드와 같은 계산."""
        import gamescene as GS
        b = self.b
        w, h = float(b.get("w", 190)), float(b.get("h", 70))
        if b.get("anchor", "creature") == "screen":
            s = GS.ui_scale(self.vw, self.vh)
            cx, cy = self.vw * float(b.get("rx", 50)) / 100, self.vh * float(b.get("ry", 30)) / 100
            return cx - w * s / 2, cy - h * s / 2, cx + w * s / 2, cy + h * s / 2
        feet = self.anchor_feet()
        if feet is None:        # 따라갈 동료가 없음: 게임처럼 숨김
            return -9999, -9999, -9999 + w, -9999 + h
        fx, fy = feet
        x, y = fx + float(b.get("x", -95)), fy + float(b.get("y", -470))
        return x, y, x + w, y + h

    def anchor_feet(self):
        """버튼이 따라다니는 개체의 발밑 (시험장 좌표). 없으면 None."""
        import gamescene as GS
        a = str((self.b or {}).get("anchor", "creature") or "creature")
        if a in ("enemy_each", "enemy_first", "enemy_last"):     # 시험장에는 적이 하나
            return self.feet(enemy=True) if (self.st or {}).get("ehp", 1) > 0 else None
        if a.startswith("pet:"):
            pets = list(((self.st or {}).get("pets") or {}).items())
            for i, (pid, (hp, _mx)) in enumerate(pets):
                if pid == a[4:] and hp > 0:
                    return GS.view_pos(GS.pet_feet(i), self.vw, self.vh)
            return None
        return self.feet()

    def _sim(self, log=None):
        import gamescene as GS
        return GS.Sim(self.tab.project, self.st, log or (lambda _s: None))

    def value_text(self):
        b = self.b
        if b and isinstance(b.get("value"), dict):
            import copy as _c
            st = _c.deepcopy(self.st)
            import gamescene as GS
            return str(int(GS.Sim(self.tab.project, st, lambda _s: None).val(b["value"])))
        return ""

    def why_not(self):
        b = self.b
        st = self.st
        if not st:
            return ""
        if int(b.get("per_turn") or 0) and st["turn_uses"] >= int(b["per_turn"]):
            return f"이번 턴에 이미 {st['turn_uses']}번 썼습니다 (턴당 {b['per_turn']}번)."
        if int(b.get("per_combat") or 0) and st["combat_uses"] >= int(b["per_combat"]):
            return f"이번 전투에 이미 {st['combat_uses']}번 썼습니다."
        if st["energy"] < int(b.get("energy_cost") or 0):
            return f"에너지가 부족합니다 ({st['energy']} < {b['energy_cost']})."
        if b.get("res_power") and int(b.get("res_cost") or 0) > st["res"].get(b["res_power"], 0):
            return f"자원이 부족합니다 ({st['res'].get(b['res_power'], 0)} < {b['res_cost']})."
        if isinstance(b.get("cond"), dict):
            import copy as _c
            import gamescene as GS
            if not GS.Sim(self.tab.project, _c.deepcopy(st), lambda _s: None).cond(b["cond"]):
                return "쓸 수 있는 조건을 만족하지 않습니다."
        if st["hp"] <= 0:
            return "쓰러졌습니다 ('전투 다시')."
        return ""

    def _world(self, ev):
        return ev.x / self.ds, ev.y / self.ds

    def on_motion(self, ev):
        if self.b is None:
            return
        x, y = self._world(ev)
        x1, y1, x2, y2 = self.rect()
        h = x1 <= x <= x2 and y1 <= y <= y2
        if h != self.hover:
            self.hover = h
            self.draw()

    def on_click(self, ev):
        if self.b is None:
            return
        x, y = self._world(ev)
        x1, y1, x2, y2 = self.rect()
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            return
        if ev.state & 0x4:     # Ctrl+끌기 = 위치 옮기기
            self._drag = (x, y)
            return
        self.press()

    def on_drag(self, ev):
        if not self._drag or self.b is None:
            return
        x, y = self._world(ev)
        dx, dy = x - self._drag[0], y - self._drag[1]
        self._drag = (x, y)
        if self.b.get("anchor", "creature") == "screen":
            self.v["rx"].set(str(round(float(self.b.get("rx", 50)) + dx / self.vw * 100, 1)))
            self.v["ry"].set(str(round(float(self.b.get("ry", 30)) + dy / self.vh * 100, 1)))
        else:
            self.v["x"].set(str(int(float(self.b.get("x", 0)) + dx)))
            self.v["y"].set(str(int(float(self.b.get("y", 0)) + dy)))

    def press(self):
        import gamescene as GS
        b = self.b
        reason = self.why_not()
        if reason:
            self.write("✖ 누를 수 없음: " + reason)
            return
        st = self.st
        st["turn_uses"] += 1
        st["combat_uses"] += 1
        msg = [f"✔ '{b.get('label_ko')}' 사용"]
        if int(b.get("energy_cost") or 0):
            st["energy"] -= int(b["energy_cost"])
            msg.append(f"에너지 -{b['energy_cost']} → {st['energy']}")
        if b.get("res_power") and int(b.get("res_cost") or 0):
            st["res"][b["res_power"]] = st["res"].get(b["res_power"], 0) - int(b["res_cost"])
            msg.append(f"자원 -{b['res_cost']} → {st['res'][b['res_power']]}")
        if int(b.get("per_turn") or 0):
            msg.append(f"이번 턴 {st['turn_uses']}/{b['per_turn']}회")
        self.write(" · ".join(msg))
        now = time.perf_counter()
        fx = FX.find_effect(self.tab.project, b.get("fx"))
        if fx:
            self.fx_play.append((fx, self.feet(), now))
        sim = GS.Sim(self.tab.project, st, self.write)
        sim.run(b.get("blocks") or [])
        for ev in sim.events:
            if ev[0] == "dmg":
                self.popups.append((ev[1], ev[2], now))
            elif ev[0] == "fx":
                f2 = FX.find_effect(self.tab.project, ev[1])
                if f2:
                    self.fx_play.append((f2, self.feet(ev[2] == "enemy"), now))
        if st["ehp"] <= 0:
            self.write("★ 적을 쓰러뜨렸습니다! ('전투 다시'로 처음부터)")
        self._push_vars()
        self._base_key = None
        self._anim()

    def _anim(self):
        if self._after:
            self.after_cancel(self._after)
            self._after = None
        now = time.perf_counter()
        self.fx_play = [(f, o, t0) for f, o, t0 in self.fx_play if now - t0 <= FX.total_time(f) + 0.2]
        self.popups = [p for p in self.popups if now - p[2] <= 1.1]
        self.draw(now)
        if self.fx_play or self.popups:
            self._after = self.after(33, self._anim)

    def draw(self, now=None):
        from PIL import Image, ImageDraw, ImageTk
        import gamescene as GS
        c = self.canvas
        if not hasattr(self, "lang"):
            return
        a = self.assets()
        ds = self.ds
        size = (max(1, int(self.vw * ds)), max(1, int(self.vh * ds)))
        lang = self.lang.get()
        key = (repr(sorted((k, repr(v)) for k, v in self.st.items())), lang, size, id(a),
               repr(self.tab.project.get("character")))
        if key != self._base_key or self._base is None:
            if a is not None:
                base = GS.scene(a, self.tab.project, self.st or {"hp": 75, "maxhp": 75}, lang, vw=self.vw, vh=self.vh)
            else:
                base = Image.new("RGBA", (self.vw, self.vh), (24, 22, 34, 255))
                ImageDraw.Draw(base).text((40, 40), "게임 폴더(모드/빌드 탭)를 정하면 실제 전투 화면으로 보입니다.",
                                          fill=(220, 220, 230, 255))
            self._base = base.resize(size, Image.BILINEAR)
            self._base_key = key
        img = self._base.copy()
        now = now or time.perf_counter()
        for f, feet, t0 in self.fx_play:
            img = FX.render(f, now - t0, size, feet, img=img, ss=1, zoom=ds)
        if self.popups and a is not None:
            d = ImageDraw.Draw(img)
            for who, n, t0 in self.popups:
                age = now - t0
                fx_, fy_ = self.feet(who == "enemy")
                al = int(255 * max(0.0, 1 - age / 1.1))
                try:
                    font = a.font("bold", max(10, int(64 * ds)))
                except Exception:  # noqa: BLE001
                    font = None
                d.text(((fx_ + 30) * ds, (fy_ - 300 - age * 120) * ds), str(n), font=font, anchor="mm",
                       fill=(255, 236, 200, al), stroke_width=max(1, int(6 * ds)), stroke_fill=(120, 20, 20, al))
        b = self.b
        reason = ""
        if b is not None and a is not None:
            reason = self.why_not()
            state = "disabled" if reason else ("hover" if self.hover else "normal")
            bi = GS.button_image(a, b, state, self.value_text(), lang)
            x1, y1, x2, y2 = self.rect()
            bs = (x2 - x1) / max(1.0, float(b.get("w", 190)))   # 화면 비율 기준이면 화면 크기에 따른 배율
            bi = bi.resize((max(1, int(bi.width * ds * bs)), max(1, int(bi.height * ds * bs))), Image.LANCZOS)
            img.alpha_composite(bi, (int((x1 - 2 * bs) * ds), int((y1 - 2 * bs) * ds)))
            tip_text = GS.btn_text(b, "tip", lang)
            if self.hover and tip_text:
                tip = GS.tip_image(a, GS.btn_text(b, "label", lang), tip_text, lang)
                if tip is not None:
                    tip = tip.resize((max(1, int(tip.width * ds)), max(1, int(tip.height * ds))), Image.LANCZOS)
                    img.alpha_composite(tip, (int((x2 + 12) * ds), int(y1 * ds)))
        self.last_frame = img      # 시험용 (화면을 찍지 않고 결과 확인)
        self._photo = ImageTk.PhotoImage(img)
        c.delete("all")
        c.create_image(0, 0, anchor="nw", image=self._photo)
        if b is None:
            c.create_text(20, 20, anchor="nw", fill="#ddd", text="왼쪽에서 '새로'를 눌러 버튼을 만드세요.", font=_font_for(11))
            return
        if reason:
            x1, y1, x2, y2 = self.rect()
            c.create_text((x1 + x2) / 2 * ds, (y2 + 14) * ds, text=reason, fill="#ff9b9b",
                          font=("Malgun Gothic", max(7, int(18 * ds)), "bold"))
        c.create_text(8, size[1] - 6, anchor="sw", fill="#ddd", font=("Malgun Gothic", 8),
                      text="클릭 = 누르기 · Ctrl+끌기 = 위치 옮기기 · 캐릭터·몬스터 몸은 실루엣(게임은 Spine 애니메이션)")

def _mix(a, b, k):
    def rgb(h):
        h = (h or "#000000").lstrip("#")
        try:
            return [int(h[i:i + 2], 16) for i in (0, 2, 4)]
        except ValueError:
            return [0, 0, 0]
    x, y = rgb(a), rgb(b)
    return "#%02x%02x%02x" % tuple(int(x[i] + (y[i] - x[i]) * k) for i in range(3))


def _round_rect(c, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2, x1, y2, x1, y2 - r,
           x1, y1 + r, x1, y1]
    try:
        return c.create_polygon(pts, smooth=True, **kw)
    except tk.TclError:
        kw.pop("fill", None)
        return c.create_polygon(pts, smooth=True, fill="#222", **kw)

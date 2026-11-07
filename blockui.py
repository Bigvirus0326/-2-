"""
블록 코딩 편집기 (tkinter).

왼쪽 블록 모음에서 가운데 작업 공간으로 끌어다 놓고, 만약/반복 블록 안에 넣어 새 능력을 만든다.
값·조건 칸은 눌러서 고른다 (계산·조건 안에 다시 값·조건을 넣을 수 있다).
아래에 만들어지는 C# 코드와 자동 설명이 바로 보인다.
"""
from __future__ import annotations

import copy
import re
import tkinter as tk
from tkinter import messagebox, ttk

import blockcode as B
from winpos import center_window
import modgen as M

TITLE = "블록 코딩"
FONT = ("Malgun Gothic", 10)
FONT_B = ("Malgun Gothic", 10, "bold")


def _plain(s):
    s = re.sub(r"\{IfUpgraded:show:([^|}]*)\|([^}]*)\}", r"\2(강화 \1)", s or "")
    s = s.replace("{Passive}", "지속 수치").replace("{Evoke}", "발현 수치").replace("{Amount}", "스택")
    return re.sub(r"\[/?[a-z_]+\]", "", s)


def _darker(hexcol, k=0.75):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


# ---------------------------------------------------------------------------
# 값 / 조건 고르기 창
# ---------------------------------------------------------------------------
VALUE_TYPES = [("num", "숫자"), ("stack", "파워 수"), ("stat", "체력 / 방어도"), ("count", "카드 수 / 적 수"),
               ("energy", "남은 에너지"), ("amount", "이 파워의 스택 수 (파워 전용)"), ("round", "현재 턴 수"),
               ("rand", "무작위 범위 (최소~최대)"), ("var", "변수"), ("op", "계산 (값 ○ 값)"),
               ("played", "사용한 카드 수 (이번 턴/전투 · 종류·태그별) — 연계"), ("summons", "소환수 수"),
               ("event", "그 수치 (넘친 양 / 기준치 도달 때의 스택)"),
               ("orbs", "구체 수 / 구체 슬롯 수"), ("orb_passive", "이 구체의 지속 수치 (구체 전용, 밀집 적용)"),
               ("orb_evoke", "이 구체의 발현 수치 (구체 전용, 밀집 적용)"), ("stars", "별 수"),
               ("energy_x", "X (이 카드에 쓴 에너지, X 비용 카드 전용)"),
               ("star_x", "X (이 카드에 쓴 별, 별 X 카드 전용)"), ("osty", "골골이 체력"), ("pet", "동료(골골이형) 체력")]
COND_TYPES = [("cmp", "비교 (값 ○ 값)"), ("chance", "확률 %"), ("has", "파워를 가지고 있음"),
              ("and", "그리고 (둘 다)"), ("or", "또는 (하나라도)"), ("not", "아니다"),
              ("osty_alive", "골골이가 살아 있음"), ("pet_alive", "동료(골골이형)가 살아 있음")]


class _Combo(ttk.Combobox):
    def __init__(self, master, options, value, width=14, command=None):
        self.opts = list(options)
        super().__init__(master, values=[l for _, l in self.opts], state="readonly", width=width, font=FONT)
        self.set_value(value)
        if command:
            self.bind("<<ComboboxSelected>>", lambda _e: command(self.get_value()))

    def get_value(self):
        i = self.current()
        return self.opts[i][0] if 0 <= i < len(self.opts) else (self.opts[0][0] if self.opts else "")

    def set_value(self, v):
        for i, (val, _l) in enumerate(self.opts):
            if val == v:
                self.current(i)
                return
        if self.opts:
            self.current(0)


class SlotDialog(tk.Toplevel):
    """값(value) 또는 조건(cond) 하나를 고르는 창."""

    def __init__(self, master, editor, kind, current):
        super().__init__(master)
        self.editor, self.kind = editor, kind
        self.title("값 고르기" if kind == "value" else "조건 고르기")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.result = None
        self.data = copy.deepcopy(current) if isinstance(current, dict) else (
            {"t": "num", "v": 0} if kind == "value" else {"t": "chance", "pct": {"t": "num", "v": 50}})
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)
        types = VALUE_TYPES if kind == "value" else COND_TYPES
        if kind == "value" and editor.owner_kind not in ("power", "summon"):
            types = [t for t in types if t[0] != "amount"]
        if kind == "value" and not getattr(editor, "allow_event", False):
            types = [t for t in types if t[0] != "event"]
        if kind == "value" and editor.owner_kind != "orb":
            types = [t for t in types if t[0] not in ("orb_passive", "orb_evoke")]
        if kind == "value" and editor.owner_kind != "card":
            types = [t for t in types if t[0] not in ("star_x", "energy_x")]
        ttk.Label(outer, text="종류").grid(row=0, column=0, sticky="w")
        self.type = _Combo(outer, types, self.data.get("t"), width=28, command=self._type_changed)
        self.type.grid(row=0, column=1, sticky="w", pady=4)
        self.fields = ttk.Frame(outer)
        self.fields.grid(row=1, column=0, columnspan=2, sticky="we", pady=6)
        self.preview = ttk.Label(outer, text="", foreground="#555", wraplength=420)
        self.preview.grid(row=2, column=0, columnspan=2, sticky="w")
        b = ttk.Frame(outer)
        b.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(b, text="확인", command=self.ok).pack(side="left", padx=4)
        ttk.Button(b, text="취소", command=self.destroy).pack(side="left")
        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self)
        self.grab_set()
        self.wait_visibility()

    # ---- 칸 만들기 ----
    def _type_changed(self, t):
        old = self.data
        self.data = {"t": t}
        defaults = {
            "num": {"v": 0}, "stack": {"who": "self", "power": "Strength"}, "stat": {"who": "self", "stat": "hp"},
            "count": {"what": "hand"}, "rand": {"min": {"t": "num", "v": 1}, "max": {"t": "num", "v": 3}},
            "var": {"name": "a"}, "played": {"scope": "turn", "filter": "Any"},
            "orbs": {"what": "count", "orb": ""}, "osty": {"what": "hp"},
            "pet": {"pet": _first_pet(self.editor.project), "what": "hp"}, "pet_alive": {"pet": _first_pet(self.editor.project)},
            "op": {"op": "+", "a": old if self.kind == "value" else {"t": "num", "v": 0},
                                         "b": {"t": "num", "v": 1}},
            "cmp": {"a": {"t": "stat", "who": "self", "stat": "hp"}, "op": "<=", "b": {"t": "num", "v": 30}},
            "chance": {"pct": {"t": "num", "v": 50}}, "has": {"who": "self", "power": "Strength"},
            "and": {"a": old, "b": {"t": "chance", "pct": {"t": "num", "v": 50}}},
            "or": {"a": old, "b": {"t": "chance", "pct": {"t": "num", "v": 50}}}, "not": {"a": old},
        }
        self.data.update(copy.deepcopy(defaults.get(t, {})))
        self._build()

    def _build(self):
        for w in self.fields.winfo_children():
            w.destroy()
        d, f, t = self.data, self.fields, self.data.get("t")
        ed = self.editor
        who_opts = [x for x in B.who_options(ed.owner_kind, multi=False)]

        def row(r, label, widget):
            ttk.Label(f, text=label).grid(row=r, column=0, sticky="w", padx=(0, 8), pady=3)
            widget.grid(row=r, column=1, sticky="w", pady=3)

        def entry(key, width=8, num=True):
            v = tk.StringVar(value=str(d.get(key, "")))

            def upd(*_):
                txt = v.get().strip()
                if num:
                    try:
                        d[key] = float(txt) if "." in txt else int(txt or 0)
                    except ValueError:
                        return
                else:
                    d[key] = txt or "a"
                self._update_preview()
            v.trace_add("write", upd)
            return ttk.Entry(f, textvariable=v, width=width, font=FONT)

        def combo(key, options, width=16):
            return _Combo(f, options, d.get(key), width=width,
                          command=lambda val, k=key: (d.__setitem__(k, val), self._update_preview()))

        def slot(key, kind):
            btn = ttk.Button(f, width=34)

            def refresh():
                lab = B.value_label(d.get(key), ed.project, card=ed.owner_kind == "card") if kind == "value" else B.cond_label(d.get(key), ed.project, card=ed.owner_kind == "card")
                btn.configure(text=_plain(lab) + "  ✎")

            def edit():
                dlg = SlotDialog(self, ed, kind, d.get(key))
                self.wait_window(dlg)
                if dlg.result is not None:
                    d[key] = dlg.result
                    refresh()
                    self._update_preview()
            btn.configure(command=edit)
            refresh()
            return btn

        if t == "num":
            row(0, "수치", entry("v"))
            if ed.owner_kind == "card":
                row(1, "강화 시 +", entry("up"))
        elif t == "stack":
            row(0, "누구의", combo("who", who_opts))
            row(1, "파워", combo("power", M.power_options(ed.project), 30))
        elif t == "stat":
            row(0, "누구의", combo("who", who_opts))
            row(1, "무엇", combo("stat", B.STATS))
        elif t == "count":
            row(0, "무엇", combo("what", B.COUNTS, 20))
        elif t == "rand":
            row(0, "최소", slot("min", "value"))
            row(1, "최대", slot("max", "value"))
        elif t == "var":
            row(0, "변수 이름", entry("name", 10, num=False))
        elif t == "op":
            row(0, "값 A", slot("a", "value"))
            row(1, "계산", combo("op", B.ARITH, 6))
            row(2, "값 B", slot("b", "value"))
        elif t == "cmp":
            row(0, "값 A", slot("a", "value"))
            row(1, "비교", combo("op", B.CMP_OPS, 6))
            row(2, "값 B", slot("b", "value"))
        elif t == "chance":
            row(0, "확률 (%)", slot("pct", "value"))
        elif t == "has":
            row(0, "누가", combo("who", who_opts))
            row(1, "파워", combo("power", M.power_options(ed.project), 30))
        elif t in ("and", "or"):
            row(0, "조건 A", slot("a", "cond"))
            row(1, "조건 B", slot("b", "cond"))
        elif t == "not":
            row(0, "조건", slot("a", "cond"))
        elif t == "played":
            import gimmick as G
            row(0, "언제", combo("scope", B.PLAYED_SCOPES, 14))
            row(1, "어떤 카드", combo("filter", G.card_filters(ed.project), 22))
            ttk.Label(f, text="지금 쓰고 있는 카드는 세지 않습니다 (연계: '이번 턴 격투 카드 수 ≥ 2').",
                      foreground="#777").grid(row=2, column=0, columnspan=2, sticky="w")
        elif t == "orbs":
            import gimmick as G
            row(0, "무엇", combo("what", B.ORB_COUNTS, 18))
            row(1, "어떤 구체 (구체 수일 때)", combo("orb", [("", "모든 구체")] + G.orb_options(ed.project), 24))
        elif t in ("pet", "pet_alive"):
            import pets as PT
            opts = [(p["id"], p.get("name_ko") or p["id"]) for p in PT.pets(ed.project)] or [("", "('🎲 기믹' 탭에서 동료를 만드세요)")]
            row(0, "동료", combo("pet", opts, 18))
            if t == "pet":
                row(1, "무엇", combo("what", [("hp", "현재 체력"), ("maxhp", "최대 체력")], 12))
        elif t == "osty":
            row(0, "무엇", combo("what", B.OSTY_STATS, 18))
            ttk.Label(f, text="골골이가 없으면 0입니다.", foreground="#777").grid(row=1, column=0, columnspan=2, sticky="w")
        elif t in ("energy", "amount", "round", "summons", "event", "orb_passive", "orb_evoke", "stars", "star_x", "energy_x",
                   "osty_alive"):
            note = {"amount": "소환수에서는 '단계', 파워에서는 '스택 수'입니다.",
                    "event": "'넘칠 때'에는 넘친 양, '기준치 도달 시'에는 그때의 스택 수입니다."}.get(t, "(설정할 것 없음)")
            ttk.Label(f, text=note, foreground="#777").grid(row=0, column=0)
        self._update_preview()

    def _update_preview(self):
        lab = B.value_label(self.data, self.editor.project, card=self.editor.owner_kind == "card") if self.kind == "value" else \
            B.cond_label(self.data, self.editor.project, card=self.editor.owner_kind == "card")
        self.preview.configure(text="→ " + _plain(lab))

    def ok(self):
        self.result = self.data
        self.destroy()


def _first_pet(project):
    import pets as PT
    p = PT.pets(project or {})
    return p[0]["id"] if p else ""


class LabelDialog(tk.Toplevel):
    """선택지 이름 (한국어 / 영어 / 중국어 간체)."""

    def __init__(self, master, value):
        super().__init__(master)
        self.title("선택지 이름")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.result = None
        f = ttk.Frame(self, padding=10)
        f.pack()
        self.ko = tk.StringVar(value=value.get("ko", ""))
        self.en = tk.StringVar(value=value.get("en", ""))
        ttk.Label(f, text="한국어").grid(row=0, column=0, sticky="w", pady=3)
        e = ttk.Entry(f, textvariable=self.ko, width=28, font=FONT)
        e.grid(row=0, column=1, pady=3)
        ttk.Label(f, text="영어").grid(row=1, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.en, width=28, font=FONT).grid(row=1, column=1, pady=3)
        self.zh = tk.StringVar(value=value.get("zh", ""))
        ttk.Label(f, text="중국어 간체").grid(row=2, column=0, sticky="w", pady=3)
        ttk.Entry(f, textvariable=self.zh, width=28, font=FONT).grid(row=2, column=1, pady=3)
        ttk.Label(f, text="고르기 화면에 카드 이름으로 나옵니다. 비우면 그 선택지는 없습니다.\n"
                          "영어·중국어를 비우면 한국어 이름을 씁니다.",
                  foreground="#777", justify="left").grid(row=3, column=0, columnspan=2, sticky="w", pady=4)
        b = ttk.Frame(f)
        b.grid(row=4, column=0, columnspan=2, sticky="e")
        ttk.Button(b, text="확인", command=self.ok).pack(side="left", padx=4)
        ttk.Button(b, text="취소", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self)
        self.grab_set()
        e.focus_set()

    def ok(self):
        self.result = {"ko": self.ko.get().strip(), "en": self.en.get().strip(), "zh": self.zh.get().strip()}
        self.destroy()


# ---------------------------------------------------------------------------
# 편집기
# ---------------------------------------------------------------------------
class BlockEditor(tk.Toplevel):
    def __init__(self, master, project, owner_kind, item, blocks, text_ko="", text_en="", auto_text=True,
                 where=None, allow_event=False, show_text=True, text_zh=""):
        super().__init__(master)
        self.title(f"{TITLE} — 새 능력 만들기")
        self.project, self.owner_kind, self.item = project, owner_kind, item or {}
        self.allow_event = allow_event
        B.set_project_hint(project)
        self.blocks = copy.deepcopy(blocks or [])
        self.result = None
        self.slots = []
        self.frames = []
        self.drag = None
        self.history = []
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{min(1500, sw - 80)}x{min(980, sh - 120)}")
        except tk.TclError:
            pass
        self.transient(master.winfo_toplevel())

        top = ttk.Frame(self, padding=(8, 6))
        top.pack(fill="x")
        where = where or {"card": "카드를 낼 때", "relic": "유물이 발동할 때", "potion": "물약을 쓸 때",
                          "power": "파워가 발동할 때", "summon": "소환수가 행동할 때",
                          "orb": "구체가 발동할 때", "button": "버튼을 눌렀을 때",
                          "pet": "동료가 행동할 때"}[owner_kind]
        ttk.Label(top, text=f"{where} 위에서부터 차례로 실행됩니다. 왼쪽 블록을 끌어다 놓으세요.",
                  font=FONT_B).pack(side="left")
        ttk.Button(top, text="되돌리기 (Ctrl+Z)", command=self.undo).pack(side="right", padx=2)
        ttk.Button(top, text="모두 지우기", command=self.clear_all).pack(side="right", padx=2)

        main = ttk.PanedWindow(self, orient="vertical")
        main.pack(fill="both", expand=True)
        upper = ttk.PanedWindow(main, orient="horizontal")
        main.add(upper, weight=4)

        # ---- 블록 모음 ----
        pal_outer = ttk.Frame(upper, padding=4)
        upper.add(pal_outer, weight=0)
        self.pal_canvas = tk.Canvas(pal_outer, width=290, background="#f4f4f6", highlightthickness=0)
        psb = ttk.Scrollbar(pal_outer, orient="vertical", command=self.pal_canvas.yview)
        self.pal_canvas.configure(yscrollcommand=psb.set)
        self.pal_canvas.pack(side="left", fill="both", expand=True)
        psb.pack(side="right", fill="y")
        self.palette = tk.Frame(self.pal_canvas, background="#f4f4f6")
        self.pal_canvas.create_window(0, 0, window=self.palette, anchor="nw")
        self.palette.bind("<Configure>", lambda _e: self.pal_canvas.configure(scrollregion=self.pal_canvas.bbox("all")))
        self._build_palette()

        # ---- 작업 공간 ----
        ws = ttk.Frame(upper)
        upper.add(ws, weight=1)
        self.canvas = tk.Canvas(ws, background="#fbfbfd", highlightthickness=0)
        vsb = ttk.Scrollbar(ws, orient="vertical", command=self.canvas.yview)
        hsb = ttk.Scrollbar(ws, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)

        # ---- 아래: 코드 / 설명 ----
        lower = ttk.Frame(main, padding=6)
        main.add(lower, weight=2)
        lower.columnconfigure(0, weight=3)
        lower.columnconfigure(1, weight=2)
        ttk.Label(lower, text="만들어지는 C# 코드 (자동)", font=FONT_B).grid(row=0, column=0, sticky="w")
        self.code = tk.Text(lower, height=10, font=("Consolas", 9), wrap="none", background="#1e1f26",
                            foreground="#d7dae0", state="disabled")
        self.code.grid(row=1, column=0, rowspan=4, sticky="nsew", padx=(0, 8))
        self.err = ttk.Label(lower, text="", foreground="#c0392b", wraplength=520, justify="left")
        self.err.grid(row=5, column=0, sticky="w")
        ttk.Label(lower, text="카드에 보일 설명", font=FONT_B).grid(row=0, column=1, sticky="w")
        self.auto = tk.BooleanVar(value=auto_text)
        ttk.Checkbutton(lower, text="블록에서 자동으로 만들기", variable=self.auto,
                        command=self.refresh_outputs).grid(row=1, column=1, sticky="w")
        def desc_box(row, tag, height):
            fr = ttk.Frame(lower)
            fr.grid(row=row, column=1, sticky="nsew", pady=2)
            ttk.Label(fr, text=tag, width=7, foreground="#6b7280").pack(side="left", anchor="n", pady=2)
            t = tk.Text(fr, height=height, font=FONT, wrap="word")
            t.pack(side="left", fill="both", expand=True)
            return t
        self.desc_ko = desc_box(2, "한국어", 4)
        self.desc_en = desc_box(3, "English", 3)
        self.desc_zh = desc_box(4, "中文", 3)
        self.desc_ko.insert("1.0", text_ko or "")
        self.desc_en.insert("1.0", text_en or "")
        self.desc_zh.insert("1.0", text_zh or "")
        def typed(e):
            # 글자를 실제로 고칠 때만 자동 설명을 끕니다 (화살표·Ctrl 키는 무시)
            if (e.char and e.char.isprintable() and not (e.state & 0x4)) or e.keysym in ("BackSpace", "Delete"):
                self.auto.set(False)
        for t in (self.desc_ko, self.desc_en, self.desc_zh):
            t.bind("<Key>", typed)
        ttk.Label(lower, text="[gold]글자[/gold] = 금색 강조,  {IfUpgraded:show:5|3} = 강화하면 5, 아니면 3",
                  foreground="#777", font=("Malgun Gothic", 8)).grid(row=5, column=1, sticky="w")
        btns = ttk.Frame(lower)
        btns.grid(row=6, column=1, sticky="e", pady=(6, 0))
        ttk.Button(btns, text="확인", command=self.ok).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=self.destroy).pack(side="left")
        self.bind("<Control-z>", lambda _e: self.undo())
        self.canvas.bind("<Configure>", lambda _e: None)
        self.render()
        center_window(self)
        self.grab_set()

    # ---------------- 블록 모음 ----------------
    def _build_palette(self):
        for cat, ops in B.PALETTE:
            name, color = B.CATS[cat]
            tk.Label(self.palette, text=name, font=FONT_B, background="#f4f4f6", foreground=_darker(color, 0.8),
                     anchor="w").pack(fill="x", padx=6, pady=(10, 2))
            for op in ops:
                spec = B.SPECS[op]
                if op == "flash" and self.owner_kind not in ("relic", "power", "summon", "button", "pet"):
                    continue
                if op == "orb_grow" and self.owner_kind != "orb":
                    continue
                text = re.sub(r"\{\w+\}", "▢", spec["ko"])
                lab = tk.Label(self.palette, text=("⊓ " if spec.get("body") else "") + text, font=FONT,
                               background=color, foreground="white", anchor="w", padx=8, pady=5, cursor="hand2",
                               wraplength=260, justify="left")
                lab.pack(fill="x", padx=6, pady=2)
                lab.bind("<ButtonPress-1>", lambda e, o=op: self.start_drag(e, new=o))
                lab.bind("<B1-Motion>", self.on_drag)
                lab.bind("<ButtonRelease-1>", self.end_drag)
        tk.Label(self.palette, text="\n블록을 여기로 다시 끌어오면 지워집니다.\n오른쪽 클릭: 복제 / 삭제",
                 font=("Malgun Gothic", 9), background="#f4f4f6", foreground="#888", justify="left").pack(fill="x", padx=6)

    # ---------------- 그리기 ----------------
    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def render(self):
        for f in self.frames:
            f.destroy()
        self.frames = []
        self.canvas.delete("all")
        self.slots = []
        y = self._layout_list(self.blocks, 16, 16, top=True)
        w = max([f.winfo_reqwidth() + 80 for f in self.frames] + [400])
        self.canvas.configure(scrollregion=(0, 0, w + 200, y + 200))
        self.refresh_outputs()

    def _layout_list(self, lst, x, y, top=False):
        if not lst:
            self.slots.append((lst, 0, x, y))
            if top:
                self.canvas.create_text(x + 6, y + 10, anchor="nw", fill="#9aa0aa", font=FONT,
                                        text="← 왼쪽에서 블록을 끌어다 여기에 놓으세요")
                return y + 60
            self.canvas.create_rectangle(x, y + 2, x + 220, y + 26, outline="#c8ccd6", dash=(4, 3))
            self.canvas.create_text(x + 8, y + 14, anchor="w", fill="#a0a6b0", font=("Malgun Gothic", 9),
                                    text="여기에 블록 넣기")
            return y + 32
        for i, b in enumerate(lst):
            self.slots.append((lst, i, x, y))
            y = self._layout_block(b, lst, i, x, y)
        self.slots.append((lst, len(lst), x, y))
        return y

    def _layout_block(self, b, lst, idx, x, y):
        spec = B.SPECS.get(b["op"])
        if not spec:
            return y
        color = B.CATS[spec["cat"]][1]
        frame = self._block_frame(b, spec, color)
        self.canvas.create_window(x, y, window=frame, anchor="nw")
        frame.update_idletasks()
        h = frame.winfo_reqheight()
        self._bind_drag(frame, b, lst)
        y2 = y + h
        if spec.get("body"):
            inner_top = y2
            y2 = self._layout_list(b.setdefault("body", []), x + 22, y2 + 4)
            for key, label in spec.get("sections", []):
                self.canvas.create_rectangle(x, inner_top, x + 14, y2, fill=color, outline="")
                ef = self._section_frame(b, spec, label, color)
                self.canvas.create_window(x, y2, window=ef, anchor="nw")
                ef.update_idletasks()
                self._bind_drag(ef, b, lst)
                inner_top = y2 + ef.winfo_reqheight()
                y2 = self._layout_list(b.setdefault(key, []), x + 22, inner_top + 4)
            self.canvas.create_rectangle(x, inner_top, x + 14, y2 + 2, fill=color, outline="")
            self.canvas.create_rectangle(x, y2 + 2, x + 120, y2 + 14, fill=color, outline="")
            y2 += 14
        return y2 + 4

    def _section_frame(self, b, spec, template, color):
        ef = tk.Frame(self.canvas, background=color)
        self.frames.append(ef)
        inner = tk.Frame(ef, background=color)
        inner.pack(padx=6, pady=3)
        for part in re.split(r"(\{\w+\})", template):
            if not part:
                continue
            m = re.match(r"\{(\w+)\}", part)
            if m:
                key = m.group(1)
                self._arg_widget(inner, b, key, spec["args"][key][0]).pack(side="left", padx=2)
            else:
                tk.Label(inner, text=part, font=FONT_B, background=color, foreground="white").pack(side="left")
        return ef

    def _block_frame(self, b, spec, color):
        frame = tk.Frame(self.canvas, background=color, highlightthickness=1, highlightbackground=_darker(color))
        self.frames.append(frame)
        inner = tk.Frame(frame, background=color)
        inner.pack(padx=6, pady=4)
        parts = re.split(r"(\{\w+\})", spec["ko"])
        for part in parts:
            if not part:
                continue
            m = re.match(r"\{(\w+)\}", part)
            if m:
                key = m.group(1)
                w = self._arg_widget(inner, b, key, spec["args"][key][0])
                w.pack(side="left", padx=2)
            else:
                lab = tk.Label(inner, text=part, font=FONT_B, background=color, foreground="white")
                lab.pack(side="left")
        return frame

    def _arg_widget(self, parent, b, key, kind):
        a = b["args"]
        changed = self._changed

        def set_(v):
            a[key] = v
            changed()
        if kind in ("who_multi", "who_one"):
            return _Combo(parent, B.who_options(self.owner_kind, kind == "who_multi"), a.get(key), 15, set_)
        if kind == "power":
            return _Combo(parent, M.power_options(self.project), a.get(key), 18, set_)
        if kind == "card":
            opts = ([("this", "이 카드의 복사본")] if self.owner_kind == "card" else []) + \
                   [(c["id"], c.get("name_ko") or c["id"]) for c in self.project.get("cards", [])]
            return _Combo(parent, opts, a.get(key), 16, set_)
        if kind == "pile":
            return _Combo(parent, B.PILES, a.get(key), 12, set_)
        if kind == "hand_action":
            return _Combo(parent, B.HAND_ACTIONS, a.get(key), 7, set_)
        if kind == "keyword":
            return _Combo(parent, M.CARD_KEYWORDS, a.get(key), 8, set_)
        if kind == "kw_action":
            return _Combo(parent, B.KW_ACTIONS, a.get(key), 5, set_)
        if kind == "kw_where":
            return _Combo(parent, B.KW_WHERE, a.get(key), 12, set_)
        if kind == "which":
            return _Combo(parent, B.WHICH, a.get(key), 8, set_)
        if kind == "card_type":
            return _Combo(parent, B.CARD_TYPES, a.get(key), 6, set_)
        if kind == "card_filter":
            import gimmick as G
            return _Combo(parent, G.card_filters(self.project), a.get(key) or "Any", 12, set_)
        if kind in ("summon", "summon_any"):
            import gimmick as G
            opts = ([("*", "모든 소환수")] if kind == "summon_any" else []) + \
                [(x["id"], x.get("name_ko") or x["id"]) for x in G.summons(self.project)]
            if not opts:
                opts = [("", "(기믹 탭에서 소환수를 만드세요)")]
            return _Combo(parent, opts, a.get(key), 14, set_)
        if kind == "pet":
            import pets as PT
            opts = [(p["id"], p.get("name_ko") or p["id"]) for p in PT.pets(self.project)] or \
                [("", "('🎲 기믹' 탭에서 동료를 만드세요)")]
            return _Combo(parent, opts, a.get(key), 12, set_)
        if kind in ("fx", "button"):
            import fxbtn
            items = fxbtn.effects(self.project) if kind == "fx" else fxbtn.buttons(self.project)
            opts = [(x["id"], x.get("name") or x.get("label_ko") or x["id"]) for x in items] or \
                [("", "('🎨 이펙트·버튼' 탭에서 만드세요)")]
            return _Combo(parent, opts, a.get(key), 14, set_)
        if kind == "orb":
            import gimmick as G
            return _Combo(parent, G.orb_options(self.project), a.get(key), 14, set_)
        if kind == "evoke_which":
            return _Combo(parent, B.EVOKE_WHICH, a.get(key), 6, set_)
        if kind == "pick_pile":
            return _Combo(parent, B.PICK_PILES, a.get(key), 12, set_)
        if kind == "pick_action":
            return _Combo(parent, B.PICK_ACTIONS, a.get(key), 16, set_)
        if kind == "delay_when":
            return _Combo(parent, B.DELAY_WHEN, a.get(key), 14, set_)
        if kind == "label":
            def label_text():
                v = a.get(key) or {}
                return f" {v.get('ko') or '(비어 있음)'} / {v.get('en') or '-'} ✎ "
            btn = tk.Button(parent, text=label_text(), font=FONT, relief="flat", background="white", foreground="#333",
                            activebackground="#eef", cursor="hand2", padx=4, pady=0)

            def edit_label():
                dlg = LabelDialog(self, a.get(key) or {})
                self.wait_window(dlg)
                if dlg.result is not None:
                    self._push_history()
                    a[key] = dlg.result
                    btn.configure(text=label_text())
                    changed()
            btn.configure(command=edit_label)
            return btn
        if kind == "int":
            v = tk.StringVar(value=str(a.get(key, 1)))

            def upd(*_):
                try:
                    a[key] = max(1, int(v.get()))
                    changed()
                except ValueError:
                    pass
            v.trace_add("write", upd)
            return ttk.Spinbox(parent, from_=1, to=50, textvariable=v, width=4, font=FONT)
        if kind == "bool":
            v = tk.BooleanVar(value=bool(a.get(key, True)))
            return tk.Checkbutton(parent, variable=v, background=parent["background"], activebackground=parent["background"],
                                  command=lambda: set_(bool(v.get())))
        if kind == "varname":
            v = tk.StringVar(value=str(a.get(key, "a")))
            v.trace_add("write", lambda *_: (a.__setitem__(key, v.get().strip() or "a"), changed()))
            return ttk.Entry(parent, textvariable=v, width=6, font=FONT)
        if kind in ("value", "cond"):
            def label():
                lab = B.value_label(a.get(key), self.project, card=self.owner_kind == "card") if kind == "value" else B.cond_label(a.get(key), self.project, card=self.owner_kind == "card")
                return " " + _plain(lab) + " ✎ "
            btn = tk.Button(parent, text=label(), font=FONT, relief="flat", background="white", foreground="#333",
                            activebackground="#eef", cursor="hand2", padx=4, pady=0)

            def edit():
                dlg = SlotDialog(self, self, kind, a.get(key))
                self.wait_window(dlg)
                if dlg.result is not None:
                    self._push_history()
                    a[key] = dlg.result
                    btn.configure(text=label())
                    changed()
            btn.configure(command=edit)
            return btn
        return tk.Label(parent, text="?")

    # ---------------- 끌어서 옮기기 ----------------
    def _bind_drag(self, frame, b, lst):
        widgets = [frame] + [w for w in frame.winfo_children()]
        for w in list(widgets):
            widgets += [c for c in w.winfo_children() if isinstance(c, tk.Label)]
        for w in widgets:
            if isinstance(w, (tk.Label, tk.Frame)):
                w.bind("<ButtonPress-1>", lambda e, b_=b, l_=lst: self.start_drag(e, block=b_, src=l_))
                w.bind("<B1-Motion>", self.on_drag)
                w.bind("<ButtonRelease-1>", self.end_drag)
                w.bind("<Button-3>", lambda e, b_=b, l_=lst: self.context_menu(e, b_, l_))

    def start_drag(self, e, new=None, block=None, src=None):
        self.drag = {"new": new, "block": block, "src": src, "x0": e.x_root, "y0": e.y_root, "moved": False}

    def _canvas_xy(self, e):
        return (self.canvas.canvasx(e.x_root - self.canvas.winfo_rootx()),
                self.canvas.canvasy(e.y_root - self.canvas.winfo_rooty()))

    def on_drag(self, e):
        d = self.drag
        if not d:
            return
        if not d["moved"] and abs(e.x_root - d["x0"]) + abs(e.y_root - d["y0"]) < 6:
            return
        d["moved"] = True
        x, y = self._canvas_xy(e)
        self.canvas.delete("drag")
        name = B.SPECS[d["new"] or d["block"]["op"]]["ko"]
        self.canvas.create_text(x + 14, y + 10, anchor="nw", text="✥ " + re.sub(r"\{\w+\}", "▢", name)[:30],
                                font=FONT_B, fill="#555", tags="drag")
        slot = self._nearest_slot(x, y, d)
        if slot:
            _l, _i, sx, sy = slot
            self.canvas.create_line(sx - 4, sy, sx + 260, sy, fill="#ff5a36", width=4, tags="drag")

    def _nearest_slot(self, x, y, d):
        best, bd = None, 1e9
        moving = d.get("block")
        banned = set()
        if moving is not None:
            banned = {id(b.get("body")) for b in B.walk([moving]) if b.get("body") is not None} | \
                     {id(b.get("else")) for b in B.walk([moving]) if b.get("else") is not None}
        for s in self.slots:
            lst, _i, sx, sy = s
            if id(lst) in banned:
                continue
            dist = abs(sy - y) + 0.6 * abs(sx - (x - 30))
            if dist < bd:
                best, bd = s, dist
        return best

    def end_drag(self, e):
        d, self.drag = self.drag, None
        self.canvas.delete("drag")
        if not d or not d["moved"]:
            return
        # 블록 모음 위에 놓으면 삭제
        target = self.winfo_containing(e.x_root, e.y_root)
        over_palette = target is not None and str(target).startswith(str(self.pal_canvas))
        if over_palette:
            if d["block"] is not None:
                self._push_history()
                d["src"].remove(d["block"])
                self.render()
            return
        x, y = self._canvas_xy(e)
        if not (0 <= e.x_root - self.canvas.winfo_rootx() <= self.canvas.winfo_width()):
            return
        slot = self._nearest_slot(x, y, d)
        if not slot:
            return
        lst, idx, _sx, _sy = slot
        self._push_history()
        if d["new"]:
            lst.insert(idx, B.new_block(d["new"]))
        else:
            blk, src = d["block"], d["src"]
            old = next((k for k, v in enumerate(src) if v is blk), None)
            if old is None:
                return
            src.pop(old)
            if src is lst and old < idx:
                idx -= 1
            lst.insert(idx, blk)
        self.render()

    def context_menu(self, e, b, lst):
        m = tk.Menu(self, tearoff=0)
        m.add_command(label="복제", command=lambda: self._dup(b, lst))
        m.add_command(label="삭제", command=lambda: self._del(b, lst))
        m.tk_popup(e.x_root, e.y_root)

    def _dup(self, b, lst):
        self._push_history()
        i = next(k for k, v in enumerate(lst) if v is b)
        lst.insert(i + 1, copy.deepcopy(b))
        self.render()

    def _del(self, b, lst):
        self._push_history()
        i = next(k for k, v in enumerate(lst) if v is b)
        lst.pop(i)
        self.render()

    # ---------------- 되돌리기 ----------------
    def _push_history(self):
        self.history.append(copy.deepcopy(self.blocks))
        if len(self.history) > 50:
            self.history.pop(0)

    def undo(self):
        if self.history:
            self.blocks = self.history.pop()
            self.render()

    def clear_all(self):
        if self.blocks and messagebox.askyesno(TITLE, "블록을 모두 지울까요?", parent=self):
            self._push_history()
            self.blocks = []
            self.render()

    # ---------------- 결과 ----------------
    def _changed(self):
        self.refresh_outputs()

    def refresh_outputs(self):
        C = M._Ctx(self.owner_kind, self.item)
        lines, errs = B.compile_blocks(self.blocks, self.project, C, "", allow_event=self.allow_event)
        self.code.configure(state="normal")
        self.code.delete("1.0", "end")
        self.code.insert("1.0", "\n".join(lines))
        self.code.configure(state="disabled")
        self.err.configure(text="\n".join("⚠ " + x for x in dict.fromkeys(errs)))
        if self.auto.get():
            for t, lang in ((self.desc_ko, "ko"), (self.desc_en, "en"), (self.desc_zh, "zh")):
                t.delete("1.0", "end")
                t.insert("1.0", B.describe(self.blocks, self.project, "power" if self.owner_kind == "summon" else self.owner_kind, lang))

    def ok(self):
        C = M._Ctx(self.owner_kind, self.item)
        lines, errs = B.compile_blocks(self.blocks, self.project, C, "", allow_event=self.allow_event)
        if errs and not messagebox.askyesno(TITLE, "블록에 문제가 있습니다:\n\n" + "\n".join(dict.fromkeys(errs)) +
                                            "\n\n그래도 저장할까요?", parent=self):
            return
        self.result = {"blocks": self.blocks, "code": "\n".join(lines), "auto_text": bool(self.auto.get()),
                       "text_ko": self.desc_ko.get("1.0", "end").strip(),
                       "text_en": self.desc_en.get("1.0", "end").strip(),
                       "text_zh": self.desc_zh.get("1.0", "end").strip()}
        self.destroy()

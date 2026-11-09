"""
블록 코딩 편집기 (tkinter).

왼쪽 블록 모음에서 가운데 작업 공간으로 끌어다 놓고, 만약/반복 블록 안에 넣어 새 능력을 만든다.
값·조건 칸은 눌러서 고른다 (계산·조건 안에 다시 값·조건을 넣을 수 있다).
아래에 만들어지는 C# 코드와 자동 설명이 바로 보인다.
"""
from __future__ import annotations

from uxkit import buffered_canvas
import copy
import hashlib
import os
import json
from pathlib import Path
import re
import traceback
import tkinter as tk
from tkinter import simpledialog, filedialog, messagebox, ttk

from uxkit import C, Tooltip, DockPanedWindow, install_panel_menu, scroll_command
import blockcode as B
from winpos import center_window
import modgen as M

TITLE = "블록 코딩"
FONT = ("Malgun Gothic", 10)
FONT_B = ("Malgun Gothic", 10, "bold")


# Short names in the picker; the workspace shows the editable arguments.
PALETTE_NAMES = {
    "damage": "피해 주기 · 대상과 횟수 선택",
    "block": "방어도 얻기", "draw": "카드 뽑기", "energy": "에너지 얻기",
    "apply_power": "파워 부여하기", "remove_power": "파워 제거하기",
    "heal": "체력 회복하기", "lose_hp": "방어도를 무시하고 체력 잃기",
    "pick": "카드 골라서 한 가지 동작 실행",
    "pick_each": "카드 골라서 한 장마다 여러 동작 실행",
    "picked_action": "고른 카드에 동작 추가 · ‘한 장마다 실행’ 안에서 사용",
    "pick_transform": "고른 카드를 지정한 카드로 변화시키기",
    "if": "조건을 만족하면 실행", "if_else": "조건에 따라 두 갈래로 실행",
    "repeat": "안에 넣은 블록 반복하기",
}


def _advanced_palette_block(op, spec):
    return (spec["cat"] == "mod_api" or op in ("original_play", "source_step")
            or any(kind == "code" for kind, _ in spec.get("args", {}).values()))


def _plain(s):
    s = re.sub(r"\{IfUpgraded:show:([^|}]*)\|([^}]*)\}", r"\2(강화 \1)", s or "")
    s = s.replace("{Passive}", "지속 수치").replace("{Evoke}", "발현 수치").replace("{Amount}", "스택")
    return re.sub(r"\[/?[a-z_]+\]", "", s)


def _darker(hexcol, k=0.75):
    h = hexcol.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))

def _block_color(category):
    color = B.CATS[category][1]
    def luminance(value):
        channels = [int(value[i:i+2],16)/255 for i in (1,3,5)]
        linear = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
        return sum(v*k for v,k in zip(linear,(.2126,.7152,.0722)))
    while 1.05/(luminance(color)+.05)<4.5:
        color = _darker(color,.92)
    return color



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
               ("star_x", "X (이 카드에 쓴 별, 별 X 카드 전용)"), ("osty", "골골이 체력"), ("pet", "동료(골골이형) 체력"),
               ("card_state", "카드 변수 값 (이 카드 / 고른 카드 한 장마다 따로)")]
COND_TYPES = [("cmp", "비교 (값 ○ 값)"), ("chance", "확률 %"), ("has", "파워를 가지고 있음"),
              ("and", "그리고 (둘 다)"), ("or", "또는 (하나라도)"), ("not", "아니다"),
              ("osty_alive", "골골이가 살아 있음"), ("pet_alive", "동료(골골이형)가 살아 있음"),
              ("card_var_has", "카드에 변수가 있음 (그 한 장)"), ("card_is", "카드가 ~이다 (키워드·태그·종류·인챈트)")]


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
        is_clone = editor.owner_kind == "card" and bool((getattr(editor,"item",None) or {}).get("clone"))
        if is_clone:
            # 가져온 효과 칸: 원본 변수 / 직접 수식을 그대로 쓸 수 있다
            types = ([("dynvar", "원본 변수 (DynamicVars · 강화 수치 포함)")] if kind == "value" and
                     (editor.item or {}).get("raw_vars") else []) + \
                [("src", "직접 수식 입력" if kind == "value" else "직접 조건 입력")] + list(types)
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
        if kind == "cond":
            for op, label in (("and","그리고 조건 추가"), ("or","또는 조건 추가")):
                ttk.Button(b, text=label, command=lambda op=op: self.append_clause(op)).pack(side="left")
        self._build()
        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self)
        self.grab_set()
        self.wait_visibility()

    # ---- 칸 만들기 ----
    def append_clause(self, op):
        dialog = SlotDialog(self, self.editor, "cond", None)
        self.wait_window(dialog)
        self.grab_set()
        if dialog.result:
            self.data = {"t":op, "a":self.data, "b":dialog.result}
            self.type.set_value(op)
            self._build()

    def _type_changed(self, t):
        old = self.data
        self.data = {"t": t}
        defaults = {
            "num": {"v": 0}, "stack": {"who": "self", "power": "Strength"}, "stat": {"who": "self", "stat": "hp"},
            "count": {"what": "hand"}, "rand": {"min": {"t": "num", "v": 1}, "max": {"t": "num", "v": 3}},
            "var": {"name": "a"}, "played": {"scope": "turn", "filter": "Any"},
            "card_state": {"card": "this" if self.editor.owner_kind == "card" else "picked", "key": "count"},
            "card_var_has": {"card": "this" if self.editor.owner_kind == "card" else "picked", "key": "count"},
            "card_is": {"card": "this" if self.editor.owner_kind == "card" else "picked", "filter": "kw:Retain"},
            "orbs": {"what": "count", "orb": ""}, "osty": {"what": "hp"},
            "pet": {"pet": _first_pet(self.editor.project), "what": "hp"}, "pet_alive": {"pet": _first_pet(self.editor.project)},
            "op": {"op": "+", "a": old if self.kind == "value" else {"t": "num", "v": 0},
                                         "b": {"t": "num", "v": 1}},
            "cmp": {"a": {"t": "stat", "who": "self", "stat": "hp"}, "op": "<=", "b": {"t": "num", "v": 30}},
            "chance": {"pct": {"t": "num", "v": 50}}, "has": {"who": "self", "power": "Strength"},
            "and": {"a": old, "b": {"t": "chance", "pct": {"t": "num", "v": 50}}},
            "or": {"a": old, "b": {"t": "chance", "pct": {"t": "num", "v": 50}}}, "not": {"a": old},
            "src": {"code": old.get("code", "") if old.get("t") == "src" else ""},
            "dynvar": {"name": next((v["name"] for v in (getattr(self.editor,"item",None) or {}).get("raw_vars", [])), ""),
                       "prop": "BaseValue"},
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

        if t == "src":
            v = tk.StringVar(value=str(d.get("code", "")))

            def upd_src(*_):
                d["code"] = v.get()
                self._update_preview()
            v.trace_add("write", upd_src)
            row(0, "직접 수식", ttk.Entry(f, textvariable=v, width=56, font=("Consolas", 10)))
            ttk.Label(f, text="가져온 효과에 쓰인 이름 (t, Me, DynamicVars[\"V0\"].IntValue 등)을 그대로 쓸 수 있습니다.",
                      foreground="#777").grid(row=1, column=0, columnspan=2, sticky="w")
        elif t == "dynvar":
            raw = (ed.item or {}).get("raw_vars", [])
            names = [(x["name"], x["name"]) for x in raw]
            box = ttk.Frame(f)

            def show_var(name=None):
                for w in box.winfo_children():
                    w.destroy()
                rv = next((x for x in raw if x["name"] == (name or d.get("name"))), None)
                if rv is None:
                    return
                for col, (field, label) in enumerate((("value", "값"), ("upgrade", "강화 시 +"))):
                    ttk.Label(box, text=label).grid(row=0, column=col * 2, padx=(0 if col == 0 else 10, 4))
                    sv = tk.StringVar(value=str(rv.get(field, 0) or 0))

                    def upd_rv(*_, sv=sv, field=field, rv=rv):
                        try:
                            rv[field] = int(sv.get())
                        except ValueError:
                            try:
                                rv[field] = float(sv.get())
                            except ValueError:
                                return
                        self._update_preview()
                    sv.trace_add("write", upd_rv)
                    ttk.Entry(box, textvariable=sv, width=6, font=FONT).grid(row=0, column=col * 2 + 1)

            def pick(val):
                d["name"] = val
                show_var(val)
                self._update_preview()
            row(0, "변수", _Combo(f, names, d.get("name"), 12, pick))
            row(1, "수치 (카드 전체에 적용)", box)
            show_var()
            ttk.Label(f, text="같은 변수를 쓰는 다른 칸·카드 설명의 숫자도 함께 바뀝니다.",
                      foreground="#777").grid(row=2, column=0, columnspan=2, sticky="w")
        elif t == "num":
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
        elif t == "card_is":
            row(0, "어느 카드", combo("card", B.CARD_REFS, 26))
            row(1, "무엇", combo("filter", B.card_is_filters(ed.project), 24))
        elif t in ("card_state", "card_var_has"):
            row(0, "어느 카드", combo("card", B.CARD_REFS, 26))
            kv = tk.StringVar(value=str(d.get("key", "count")))

            def upd_key(*_):
                d["key"] = kv.get().strip() or "count"
                self._update_preview()
            kv.trace_add("write", upd_key)
            row(1, "상태 이름", ttk.Entry(f, textvariable=kv, width=12))
            ttk.Label(f, text="같은 카드가 여러 장이어도 한 장마다 따로 저장됩니다 (처음엔 0).", foreground="#777").grid(
                row=2, column=0, columnspan=2, sticky="w")
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


def _source_call_slots(block):
    """Recover argument positions for imported call slots, including older saved blocks."""
    slots = {s.get("key"): s for s in block.get("slots", [])}
    if block.get("call_signature") and all(s.get("source_segment") is not None and s.get("source_arg") is not None
                                           for s in slots.values() if s.get("kind") in ("value", "code")):
        return block.get("call_signature"), list(slots.values())
    try:
        import csblocks
        parts = block.get("parts") or []
        stitched, original = [], []
        placeholders = {}
        for index, part in enumerate(parts):
            if index % 2:
                key = part
                token = f"__STS2_SLOT_{key}__"
                placeholders[token] = key
                stitched.append(token)
                original.append(str(slots.get(key, {}).get("orig", token)))
            else:
                stitched.append(str(part))
                original.append(str(part))
        statement = "".join(stitched).strip().rstrip(";").strip()
        original_statement = "".join(original).strip().rstrip(";").strip()
        assign = re.match(r"^(?:(?:var|[\w.?<>\[\],]+)\s+)?[A-Za-z_]\w*(?:\.\w+|\[[^\]]*\])*\s*(?:\+=|-=|\*=|/=|=(?!=))\s*", statement)
        rhs = statement[assign.end():] if assign else statement
        original_assign = re.match(r"^(?:(?:var|[\w.?<>\[\],]+)\s+)?[A-Za-z_]\w*(?:\.\w+|\[[^\]]*\])*\s*(?:\+=|-=|\*=|/=|=(?!=))\s*", original_statement)
        original_rhs = original_statement[original_assign.end():] if original_assign else original_statement
        parsed = csblocks.Decomposer.__new__(csblocks.Decomposer).chain_parts(rhs)
        if not parsed:
            return block.get("call_signature"), list(slots.values())
        sig_parsed = csblocks.Decomposer.__new__(csblocks.Decomposer).chain_parts(original_rhs) or parsed
        sig_segs, sig_aw = sig_parsed
        signature = csblocks.call_signature(sig_segs, original_rhs if sig_parsed is not parsed else rhs, sig_aw)
        segs, _aw = parsed
        for si, seg in enumerate(segs):
            if seg.get("args") is None:
                continue
            a, b = seg["args"]
            raw = rhs[a:b]
            for ai, (x, y) in enumerate(csblocks.split_args(raw)):
                arg = raw[x:y]
                for token, key in placeholders.items():
                    if token in arg:
                        slots[key].update(source_segment=si, source_arg=ai)
        block["call_signature"] = signature
        return signature, list(slots.values())
    except Exception:
        return block.get("call_signature"), list(slots.values())


class CallMappingDialog(tk.Toplevel):
    """Connect an imported call to a native effect block, optionally saving an exact-call rule."""

    def __init__(self, master, editor, block):
        super().__init__(master)
        self.editor, self.block = editor, block
        self.title("가져온 호출을 블록에 연결")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.result = None
        self.signature, self.source_slots = _source_call_slots(block)
        self.source_slots = [s for s in self.source_slots if s.get("source_segment") is not None and
                             s.get("source_arg") is not None and s.get("kind") in ("value", "code")]
        self.values = {}
        self.widgets = {}
        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=(block.get("label") or "가져온 호출"), font=FONT_B,
                  wraplength=520).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(outer, text="이 호출을 어떤 공용 효과 블록으로 바꿀지 정하세요. 수치와 코드 칸을 원본 인수에 연결하거나 직접 지정할 수 있습니다.",
                  foreground="#555", wraplength=520).grid(row=1, column=0, columnspan=2, sticky="w", pady=(3, 8))
        options = [(op, f"{B.CATS[B.SPECS[op]['cat']][0]} · {B.SPECS[op]['ko']}") for op in B.MANUAL_MAP_OPS
                   if op != "flash" or editor.owner_kind in ("relic", "power", "summon", "button", "pet")]
        ttk.Label(outer, text="연결할 블록").grid(row=2, column=0, sticky="w", padx=(0, 8))
        self.op = _Combo(outer, options, "damage", width=42, command=self._build_fields)
        self.op.grid(row=2, column=1, sticky="w")
        self.fields = ttk.Frame(outer)
        self.fields.grid(row=3, column=0, columnspan=2, sticky="we", pady=(8, 2))
        self.keep = tk.BooleanVar(value=True)
        ttk.Checkbutton(outer, text="이 모드에서 같은 호출을 계속 이 블록에 연결", variable=self.keep).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(8, 2))
        ttk.Label(outer, text="규칙은 호출 형태가 정확히 같은 경우에만 다시 적용됩니다.", foreground="#777").grid(
            row=5, column=0, columnspan=2, sticky="w")
        buttons = ttk.Frame(outer)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(buttons, text="확인", command=self.ok).pack(side="left", padx=4)
        ttk.Button(buttons, text="취소", command=self.destroy).pack(side="left")
        self._build_fields()
        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self)
        self.grab_set()
        self.wait_visibility()

    def _build_fields(self, _op=None):
        for child in self.fields.winfo_children():
            child.destroy()
        self.widgets = {}
        op = self.op.get_value()
        spec = B.SPECS[op].get("args", {})
        who_opts = [x for x in B.who_options(self.editor.owner_kind, multi=True) if x[0] != "it"]
        power_opts = M.power_options(self.editor.project)
        source_opts = []
        for source in self.source_slots:
            key = source["key"]
            shown = self.block.get("args", {}).get(key, source.get("orig", ""))
            if source.get("kind") == "value" and isinstance(shown, dict):
                description = B.value_label(shown, self.editor.project, card=self.editor.owner_kind == "card")
            else:
                description = str(shown or source.get("orig", ""))
            source_opts.append((f"arg:{key}", f"원본 인수 · {source.get('name', key)} ({_plain(description)[:45]})"))
        value_opts = [("fixed", "고정 수치 입력")] + source_opts
        code_opts = [("fixed", "고정 코드 식 입력")] + source_opts

        def row(r, label, widget):
            ttk.Label(self.fields, text=label).grid(row=r, column=0, sticky="w", padx=(0, 10), pady=3)
            widget.grid(row=r, column=1, sticky="w", pady=3)

        field_labels = {"who": "대상", "amount": "수치", "hits": "타격 횟수", "powered": "힘·약화 적용",
                        "power": "파워", "keyword": "키워드", "action": "동작"}
        for r, (field, (kind, default)) in enumerate(spec.items()):
            if kind == "value":
                default_num = default.get("v", 1) if isinstance(default, dict) and default.get("t") == "num" else 1
                box = ttk.Frame(self.fields)
                choice = _Combo(box, value_opts, "fixed", width=39)
                choice.pack(side="left")
                value = tk.StringVar(value=str(default_num))
                entry = ttk.Entry(box, textvariable=value, width=9, font=FONT)
                entry.pack(side="left", padx=(6, 0))

                def changed(_event=None, c=choice, e=entry):
                    e.configure(state="normal" if c.get_value() == "fixed" else "disabled")
                choice.bind("<<ComboboxSelected>>", changed)
                self.widgets[field] = {"kind": kind, "choice": choice, "value": value}
                row(r, field_labels.get(field, field), box)
            elif kind == "code":
                box = ttk.Frame(self.fields)
                choice = _Combo(box, code_opts, "fixed", width=39)
                choice.pack(side="left")
                value = tk.StringVar(value=str(default or ""))
                entry = ttk.Entry(box, textvariable=value, width=24, font=FONT)
                entry.pack(side="left", padx=(6, 0))

                def changed(_event=None, c=choice, e=entry):
                    e.configure(state="normal" if c.get_value() == "fixed" else "disabled")
                choice.bind("<<ComboboxSelected>>", changed)
                self.widgets[field] = {"kind": kind, "choice": choice, "value": value}
                row(r, field_labels.get(field, field), box)
            elif kind in ("who_multi", "power"):
                opts = who_opts if kind == "who_multi" else power_opts
                combo = _Combo(self.fields, opts, default, width=32 if kind == "power" else 20)
                self.widgets[field] = {"kind": kind, "combo": combo}
                row(r, field_labels.get(field, "대상" if kind == "who_multi" else "파워"), combo)
            elif kind == "keyword":
                combo = _Combo(self.fields, M.CARD_KEYWORDS, default, width=24)
                self.widgets[field] = {"kind": kind, "combo": combo}
                row(r, field_labels.get(field, field), combo)
            elif kind == "kw_action":
                combo = _Combo(self.fields, B.KW_ACTIONS, default, width=18)
                self.widgets[field] = {"kind": kind, "combo": combo}
                row(r, field_labels.get(field, field), combo)
            elif kind == "bool":
                combo = _Combo(self.fields, [(True, "적용"), (False, "적용 안 함")], bool(default), width=18)
                self.widgets[field] = {"kind": kind, "combo": combo}
                row(r, field_labels.get(field, field), combo)
            elif kind == "int":
                value = tk.StringVar(value=str(default))
                entry = ttk.Entry(self.fields, textvariable=value, width=9, font=FONT)
                self.widgets[field] = {"kind": kind, "value": value}
                row(r, field_labels.get(field, field), entry)

    def ok(self):
        op = self.op.get_value()
        block = B.new_block(op)
        bindings = {}
        for field, widget in self.widgets.items():
            kind = widget["kind"]
            if kind in ("value", "code"):
                selected = widget["choice"].get_value()
                if selected.startswith("arg:"):
                    key = selected[4:]
                    source = next((s for s in self.source_slots if s.get("key") == key), None)
                    if not source:
                        messagebox.showerror("호출 연결", "선택한 원본 인수를 찾을 수 없습니다.", parent=self)
                        return
                    current = self.block.get("args", {}).get(key, source.get("orig", ""))
                    if kind == "code":
                        if isinstance(current, dict) and current.get("t") == "src":
                            code = current.get("code") or source.get("orig", "")
                        elif isinstance(current, dict):
                            try:
                                code = B._Gen(self.editor.project, M._Ctx(self.editor.owner_kind, self.editor.item)).val(current)
                            except Exception:
                                code = source.get("orig", "")
                        else:
                            code = current or source.get("orig", "")
                        block["args"][field] = str(code).strip()
                    elif source.get("kind") == "value" and isinstance(current, dict):
                        block["args"][field] = copy.deepcopy(current)
                    else:
                        block["args"][field] = {"t": "src", "code": str(current or source.get("orig", ""))}
                    bindings[field] = {"kind": "arg", "segment": source["source_segment"], "index": source["source_arg"],
                                       "initial_value": copy.deepcopy(block["args"][field])}
                else:
                    raw = widget["value"].get().strip()
                    if kind == "code":
                        value = raw
                    else:
                        try:
                            number = float(raw) if "." in raw else int(raw)
                        except ValueError:
                            messagebox.showerror("호출 연결", f"{field}에 숫자를 입력해 주세요.", parent=self)
                            return
                        value = {"t": "num", "v": number}
                    block["args"][field] = copy.deepcopy(value)
                    bindings[field] = {"kind": "fixed", "value": value}
            elif kind == "int":
                try:
                    value = max(1, int(widget["value"].get()))
                except ValueError:
                    messagebox.showerror("호출 연결", "타격 횟수는 정수로 입력해 주세요.", parent=self)
                    return
                block["args"][field] = value
                bindings[field] = {"kind": "fixed", "value": value}
            else:
                value = widget["combo"].get_value()
                block["args"][field] = value
                bindings[field] = {"kind": "fixed", "value": value}
        rule = {"signature": self.signature, "op": op, "bindings": bindings}
        self.result = {"block": block, "rule": rule if self.keep.get() and self.signature else None}
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
                 where=None, allow_event=False, show_text=True, text_zh="", on_decompose=None, upgraded_text=None, card_event=None):
        super().__init__(master)
        self.title(f"{TITLE} — 새 능력 만들기")
        self.project, self.owner_kind, self.item = project, owner_kind, item or {}
        self.app = getattr(master, "app", None)
        self.card_event = card_event
        self.allow_event = allow_event
        self.on_decompose = on_decompose
        B.set_project_hint(project)
        B.set_item_hint(self.item)
        self.blocks = copy.deepcopy(blocks or [])
        self.result = None
        self.slots = []
        self.frames = []
        self.drag = None
        self._drag_window_owners = {}
        self._drag_feedback = None
        self.history = []
        self.pending_call_mappings = []
        try:
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            self.geometry(f"{min(1500, sw - 80)}x{min(980, sh - 120)}")
        except tk.TclError:
            pass
        self.transient(master.winfo_toplevel())
        self.minsize(760,480)

        top = ttk.Frame(self, padding=(12, 10))
        top.pack(fill="x")
        where = where or {"card": "카드를 낼 때", "relic": "유물이 발동할 때", "potion": "물약을 쓸 때",
                          "power": "파워가 발동할 때", "summon": "소환수가 행동할 때",
                          "orb": "구체가 발동할 때", "button": "버튼을 눌렀을 때",
                          "pet": "동료가 행동할 때"}[owner_kind]
        self.mode_hint = ttk.Label(self, text="왼쪽 블록을 작업 공간으로 끌어다 놓으세요.", style="Footer.TLabel")
        self.mode_hint.pack(side="bottom",fill="x",padx=12,pady=(0,6))
        self.bind("<Configure>",lambda e:self.mode_hint.configure(wraplength=max(200,e.width-24))
                  if e.widget is self else None,add="+")
        ttk.Label(top, text=where, style="Brand.TLabel").pack(side="left")
        ttk.Button(top, text="되돌리기 (Ctrl+Z)", command=self.undo).pack(side="right", padx=2)
        ttk.Button(top, text="모두 지우기", style="Danger.TButton", command=self.clear_all).pack(side="right", padx=2)
        if on_decompose:
            original = ttk.Menubutton(top,text="원본 효과 ▾")
            original.pack(side="right",padx=2)
            original_menu = tk.Menu(original,tearoff=False)
            original_menu.add_command(label="다시 분석해 블록으로 풀기",command=self.redecompose)
            original_menu.add_command(label="가져온 효과 하나로 접기",command=self.collapse_original)
            original.configure(menu=original_menu)

        main = ttk.PanedWindow(self, orient="vertical")
        main.pack(fill="both", expand=True)
        upper = DockPanedWindow(main, title="블록 코딩", orient="horizontal")
        self.block_panes = upper
        main.add(upper, weight=4)

        # ---- 블록 모음 ----
        pal_outer = upper.add_panel(lambda parent:ttk.Frame(parent, padding=10), "블록 라이브러리", weight=0)
        self.library_panel = pal_outer
        self.browse_saved = tk.BooleanVar(self,False)
        routes = ttk.Frame(pal_outer)
        routes.pack(fill="x")
        for saved,label in ((False,"개별 블록"), (True,"저장한 묶음")):
            ttk.Radiobutton(routes,text=label,style="Segment.TRadiobutton",variable=self.browse_saved,value=saved,
                            command=self._build_palette).pack(side="left",expand=True,fill="x")
        tools = ttk.Frame(pal_outer)
        tools.pack(fill="x", pady=4)
        ttk.Button(tools,text="문장으로 만들기…",command=self.open_recipes).pack(side="left")
        library_tools = ttk.Menubutton(tools,text="도구 ▾",style="Small.TButton")
        library_tools.pack(side="right")
        library_menu = tk.Menu(library_tools,tearoff=False)
        library_menu.add_command(label="공유 블록 정의…",command=self.define_shared)
        library_tools.configure(menu=library_menu)
        search_row = ttk.Frame(pal_outer)
        search_row.pack(fill="x",pady=(6,4),before=tools)
        ttk.Label(search_row, text="블록 검색").pack(side="left")
        self.palette_query = tk.StringVar(self)
        search = ttk.Entry(search_row, textvariable=self.palette_query, width=18)
        search.pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(search_row, text="지우기", width=6, command=lambda: self.palette_query.set("")).pack(side="right")
        search.bind("<Escape>", lambda _: (self.palette_query.set(""), "break")[1])
        self.show_advanced = tk.BooleanVar(self, True)
        ttk.Checkbutton(pal_outer, text="다른 효과도 모두 보기",
                        variable=self.show_advanced, command=self._apply_palette_visibility).pack(anchor="w")
        self.pal_canvas = tk.Canvas(pal_outer, width=300, background=C["surface"], highlightthickness=0)
        psb = ttk.Scrollbar(pal_outer, orient="vertical", command=scroll_command(self.pal_canvas))
        self.pal_canvas.configure(yscrollcommand=psb.set)
        self.pal_canvas.pack(side="left", fill="both", expand=True)
        psb.pack(side="right", fill="y")
        self.palette = tk.Frame(self.pal_canvas, background=C["surface"])
        palette_window = self.pal_canvas.create_window(0, 0, window=self.palette, anchor="nw")
        self.pal_canvas.bind("<Configure>", lambda e: self.pal_canvas.itemconfigure(
            palette_window, width=max(1, e.width)))
        self.palette.bind("<Configure>", lambda _e: self.pal_canvas.configure(scrollregion=self.pal_canvas.bbox("all")))
        self.palette_query.trace_add("write", lambda *_: self._build_palette())
        self.preset_dir = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "sts2_mod_maker" / "block_presets"
        self.favorite_file = self.preset_dir.parent / "favorite_blocks.json"
        saved = []
        try:
            saved = json.loads(self.favorite_file.read_text("utf8"))
            self.favorites = {op for op in saved if isinstance(op,str) and op in B.SPECS} if isinstance(saved,list) else set()
        except (ValueError,OSError):
            self.favorites = set()
        self.favorite_order = list(dict.fromkeys(op for op in saved if isinstance(op,str) and op in self.favorites)) if isinstance(saved, list) else []
        self.saved_presets = {}
        for preset_file in sorted(self.preset_dir.glob("*.json")):
            try:
                record = json.loads(preset_file.read_text(encoding="utf8"))
                if isinstance(record["name"], str) and isinstance(record["blocks"], list) and all(
                        isinstance(b, dict) and b.get("op") in B.SPECS for b in B.walk(record["blocks"])):
                    self.saved_presets[preset_file.stem] = record
            except (OSError, ValueError, KeyError, TypeError, AttributeError):
                continue
        self._build_palette()

        # ---- 작업 공간 ----
        ws = upper.add_panel(lambda parent:ttk.Frame(parent), "블록 작업 공간", weight=1)
        self.workspace_panel = ws
        self.canvas = tk.Canvas(ws, background=C["workspace"], highlightthickness=0)
        vsb = ttk.Scrollbar(ws, orient="vertical", command=scroll_command(self.canvas))
        hsb = ttk.Scrollbar(ws, orient="horizontal", command=scroll_command(self.canvas, True))
        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")
        self.canvas.pack(fill="both", expand=True)

        menu = tk.Menu(self)
        views = tk.Menu(menu, tearoff=False)
        menu.add_cascade(label="보기", menu=views)
        self.configure(menu=menu)
        install_panel_menu(views, self._root(), scope=self)
        def output_window(title, size):
            window = tk.Toplevel(self)
            window.withdraw()
            window.title(title)
            window.transient(self)
            window.geometry(size)
            def close():
                window.withdraw()
                self.focus_set()
            window.protocol("WM_DELETE_WINDOW", close)
            window.bind("<Escape>", lambda _: close())
            def show():
                if not window.winfo_viewable():
                    center_window(window, self)
                window.lift()
                window.focus_set()
            views.add_command(label=title, command=show)
            return window

        code_win = output_window("생성된 C# 코드", "760x460")
        code_win.columnconfigure(0, weight=1)
        code_win.rowconfigure(0, weight=1)
        self.code = tk.Text(code_win, font=("Consolas", 10), wrap="none", background="#1e1f26",
                            foreground="#d7dae0", state="disabled")
        self.code.grid(row=0,column=0,sticky="nsew")
        for orient, row, column, sticky, command in (("vertical",0,1,"ns",self.code.yview),
                                                    ("horizontal",1,0,"ew",self.code.xview)):
            bar = ttk.Scrollbar(code_win, orient=orient, command=command)
            bar.grid(row=row,column=column,sticky=sticky)
            self.code.configure(**{("yscrollcommand" if row==0 else "xscrollcommand"):bar.set})
        self.err = ttk.Label(code_win, foreground="#c0392b", wraplength=660, justify="left")
        self.err.grid(row=2,column=0,sticky="w")

        from uxkit import AutoScroll
        description_window = output_window("카드 설명", "720x650")
        description_scroll = AutoScroll(description_window)
        description_scroll.pack(fill="both", expand=True)
        lower = description_scroll.inner
        lower.columnconfigure(1, weight=1)
        for row in (2,3,4):
            lower.rowconfigure(row,weight=1)
        ttk.Label(lower, text="카드에 보일 설명", font=FONT_B).grid(row=0, column=1, sticky="w")
        self.auto = tk.BooleanVar(value=auto_text)
        ttk.Checkbutton(lower, text="블록에서 자동으로 만들기", variable=self.auto,
                        command=self.refresh_outputs).grid(row=1, column=1, sticky="w")
        def desc_box(row, tag, height):
            fr = ttk.Frame(lower)
            fr.grid(row=row, column=1, sticky="nsew", pady=2)
            ttk.Label(fr, text=tag, width=7, foreground="#6b7280").pack(side="left", anchor="n", pady=2)
            from descriptionui import DescriptionText, GameColorBar
            content = ttk.Frame(fr)
            content.pack(side="left", fill="both", expand=True)
            lang = {2:"ko", 3:"en", 4:"zh", 6:"ko", 7:"en", 8:"zh"}[row]
            t = DescriptionText(content, lambda:(self.project, self.item, lang, row >= 6),
                                height=height, font=FONT, wrap="word", exportselection=False,
                                background="white", padx=8, pady=6)
            t.pack(fill="both", expand=True)
            GameColorBar(content, t, lambda:self.auto.set(False)).pack(fill="x", pady=(3, 0))
            return t
        self.desc_ko = desc_box(2, "한국어", 4)
        self.desc_en = desc_box(3, "English", 3)
        self.desc_zh = desc_box(4, "中文", 3)
        self.desc_ko.set_source(text_ko or "")
        self.desc_en.set_source(text_en or "")
        self.desc_zh.set_source(text_zh or "")
        self.upgraded_desc = {}
        for row, lang in enumerate(("ko", "en", "zh"), 6):
            field = desc_box(row, {"ko":"한국어 +", "en":"English +", "zh":"中文 +"}[lang], 2)
            field.set_source((upgraded_text or {}).get(lang, ""))
            self.upgraded_desc[lang] = field
        ttk.Label(lower, text="강화 설명을 비워 두면 기본 설명을 사용합니다.").grid(row=9, column=1, sticky="w")
        def typed(e):
            # 글자를 실제로 고칠 때만 자동 설명을 끕니다 (화살표·Ctrl 키는 무시)
            if (e.char and e.char.isprintable() and not (e.state & 0x4)) or e.keysym in ("BackSpace", "Delete"):
                self.auto.set(False)
        for t in (self.desc_ko, self.desc_en, self.desc_zh, *self.upgraded_desc.values()):
            t.bind("<Key>", typed)
        ttk.Label(lower, text="글자를 선택하고 게임 기본 색을 누르세요. 다른 색은 직접 선택할 수 있습니다.",
                  foreground="#777", font=("Malgun Gothic", 8)).grid(row=5, column=1, sticky="w")
        if not show_text:
            # 원본 카드: 설명은 원본 문구를 그대로 쓰므로 자동 설명 칸을 숨긴다
            self.auto.set(False)
            for w in lower.grid_slaves(column=1):
                if int(w.grid_info().get("row", 0)) in (1, 2, 3, 4, 5, 6, 7, 8, 9):
                    w.grid_remove()
            ttk.Label(lower, text="원본 카드의 설명 문구를 그대로 씁니다.\n수치는 원본 변수(V0 등)를 바꾸면 설명 숫자도 함께 바뀝니다.\n"
                                  "블록 위 이름에 마우스를 올리면 그 블록의 C# 이 보입니다.",
                      foreground="#555", justify="left").grid(row=1, column=1, rowspan=3, sticky="nw", pady=4)
        self.group_moving = False
        self.selection_origin = None
        self.group_blocks = []
        self.block_headers = []
        self.select_bindtag = "GroupSelection" + str(id(self))
        for sequence, handler in (("<ButtonPress-1>", self._group_start),
                                  ("<B1-Motion>", self._group_motion),
                                  ("<ButtonRelease-1>", self._group_end)):
            command = self.register(handler, self._substitute)
            self.tk.call("bind", self.select_bindtag, sequence,
                         f'if {{"[{command} {self._subst_format_str}]" == "break"}} break')
        footer = ttk.Frame(self, padding=(10,8))
        footer.pack(side="bottom", fill="x", before=main)
        presets = ttk.Frame(footer)
        presets.pack(side="left")
        self.group_delete = ttk.Button(presets, text="선택 삭제 (Del)", style="Danger.TButton", command=self._delete_group, state="disabled")
        self.group_delete.pack(side="left")
        self.group_save = ttk.Button(presets, text="라이브러리에 저장", state="disabled", command=self._save_group)
        self.group_save.pack(side="left", padx=3)
        ttk.Button(presets, text="파일 가져오기…", command=self.load_blocks).pack(side="left")
        btns = ttk.Frame(footer)
        btns.pack(side="right")
        ttk.Button(btns, text="효과 적용", style="Accent.TButton", command=self.ok).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=self.destroy).pack(side="left")
        self.canvas.bind("<Delete>", self._delete_selection_key)
        self.bind("<Control-z>", lambda _e: self.undo())
        self.bind("<Escape>", self._cancel_block_drag)
        self.bind("<Destroy>", self._cleanup_drag_on_destroy, add="+")
        self.canvas.bind("<Configure>", lambda _e: None)
        self.render()
        center_window(self)
        self.grab_set()

    def destroy(self):
        if getattr(self,"_closing",False) or not self.winfo_exists():
            return
        self._closing = True
        if self.grab_current() is self:
            self.grab_release()
        self.configure(menu="")
        self.transient("")
        self.withdraw()
        # Break Canvas window-item links before Tk destroys embedded controls.
        # After wm manage/forget, pending geometry work can otherwise outlive
        # those controls on Windows. Settle it while the whole editor is alive.
        if hasattr(self,"canvas"):
            self._clear_drag_feedback()
            self._restore_drag_windows()
            self.canvas.delete("all")
            # Process pending native reparent/unmap messages while all controls
            # still exist. The withdrawn editor cannot receive new edits.
            self.update()
        super().destroy()

    # ---------------- 블록 모음 ----------------
    def define_shared(self):
        if not self.blocks:
            return
        name = simpledialog.askstring("내 블록 정의", "이름을 입력하세요. 값 칸에서 변수 input1, input2를 선택하면 호출할 때 입력받습니다.", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        defs = self.project.setdefault("shared_blocks", {})
        def uses(node, seen):
            if isinstance(node,list):
                return any(uses(child,seen) for child in node)
            if isinstance(node,dict):
                if node.get("op")=="shared_call":
                    ref = node.get("args",{}).get("name","")
                    if ref==name or (ref in defs and ref not in seen and uses(defs[ref],seen|{ref})):
                        return True
                return any(uses(child,seen) for child in node.values())
            return False
        count = sum(uses(card,set()) for card in self.project.get("cards",[]))
        if name in defs and not messagebox.askyesno("내 블록 수정", f"이 정의를 사용하는 카드 {count}장에 변경이 적용됩니다. 바꿀까요?", parent=self):
            return
        defs[name] = copy.deepcopy(self.blocks)
        if self.app:
            self.app.mark_dirty()
        self.render()

    def open_recipes(self):
        import gimmick as G
        win = tk.Toplevel(self)
        win.title("효과 레시피")
        win.transient(self)
        tabs = ttk.Notebook(win)
        tabs.pack(fill="both", expand=True, padx=8, pady=8)
        transform, threshold = ttk.Frame(tabs, padding=8), ttk.Frame(tabs, padding=8)
        tabs.add(transform, text="조건에 맞는 카드로 변화")
        tabs.add(threshold, text="파워 수치에 따라 효과 실행")
        def line(parent):
            row = ttk.Frame(parent)
            row.pack(anchor="w", pady=4)
            return row
        def words(row, text):
            ttk.Label(row, text=text).pack(side="left", padx=2)
        def choice(row, opts, width=16):
            field = _Combo(row, opts, opts[0][0], width)
            field.pack(side="left")
            return field
        def number(row, default):
            field = ttk.Spinbox(row, from_=1, to=999, width=4)
            field.set(default)
            field.pack(side="left")
            return field
        row = line(transform)
        pile = choice(row, B.PICK_PILES)
        words(row, "에서")
        source = choice(row, G.card_filters(self.project))
        words(row, "중 무작위")
        count = number(row, 2)
        words(row, "장을 골라")
        row = line(transform)
        pool_choice = choice(row, [(k,v[0]) for k,v in M.transform_pools(self.project).items()])
        words(row, "에서")
        result = choice(row, G.card_filters(self.project) +
                        [("kw:"+k, label+" 키워드 카드") for k,label in M.CARD_KEYWORDS], 22)
        words(row, "중 하나로 각각 변화시켜요.")
        row = line(threshold)
        words(row, "나에게")
        power = choice(row, M.power_options(self.project))
        words(row, "파워가")
        stacks = number(row, 3)
        words(row, "이상 있으면")
        row = line(threshold)
        action = choice(row, [("draw","카드 뽑기"), ("block","방어도 얻기"), ("energy","에너지 얻기")])
        words(row, "효과를 수치")
        amount = number(row, 1)
        words(row, "만큼 적용해요.")
        def value(field):
            n = int(field.get())
            if not 1 <= n <= 999:
                raise ValueError()
            return {"t":"num", "v":n}
        def insert():
            try:
                if tabs.select() == str(transform):
                    block = B.new_block("random_transform")
                    block["args"].update(pile=pile.get_value(), ctype=source.get_value(), count=value(count), result_pool=pool_choice.get_value(), result_filter=result.get_value())
                else:
                    block = B.new_block("if")
                    block["args"]["cond"] = {"t":"cmp", "op":">=", "a":{"t":"stack", "who":"self", "power":power.get_value()}, "b":value(stacks)}
                    effect = B.new_block(action.get_value())
                    effect["args"]["amount"] = value(amount)
                    block["body"] = [effect]
            except ValueError:
                messagebox.showwarning("효과 레시피", "1부터 999 사이의 정수를 입력하세요.", parent=win)
                return
            self._push_history()
            self.blocks.append(block)
            self.render()
            win.destroy()
        ttk.Button(win, text="작업 공간에 추가", command=insert).pack(pady=6)
        center_window(win)
        win.grab_set()
        self.wait_window(win)
        self.grab_set()

    def _save_favorites(self, order):
        order = list(dict.fromkeys(order))
        try:
            self.favorite_file.parent.mkdir(parents=True,exist_ok=True)
            tmp = self.favorite_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(order),encoding="utf8")
            tmp.replace(self.favorite_file)
        except OSError as exc:
            messagebox.showerror("즐겨찾기 저장 실패",str(exc),parent=self)
            return False
        self.favorite_order = order
        self.favorites = set(order)
        return True

    def _toggle_favorite(self, op):
        order = [key for key in self.favorite_order if key in self.favorites and key != op]
        order += sorted(self.favorites - set(order) - {op})
        if op not in self.favorites:
            order.append(op)
        if not self._save_favorites(order):
            return
        # Keep the category widgets and scroll position intact when pinning.
        for block_op, star in self._palette_stars:
            if star.winfo_exists():
                pinned = block_op in self.favorites
                star.configure(text="★" if pinned else "☆",
                               foreground="#895000" if pinned else "#4c5665")
        self._refresh_favorites()

    def _refresh_favorites(self):
        candidates = {op:(caption,color) for op,caption,color in self._favorite_candidates}
        order = [op for op in self.favorite_order + sorted(self.favorites-set(self.favorite_order))
                 if op in self.favorites and op in candidates]
        previous = getattr(self, "_favorite_rows", {})
        rows = {op:row for op,row in previous.items()
                if op in order and row.winfo_exists() and row.master == self._favorites_frame}
        for widget in self._favorites_frame.winfo_children():
            if widget not in rows.values():
                widget.destroy()
        self._palette_stars = [(op,star) for op,star in self._palette_stars if star.winfo_exists()]
        self._favorite_rows = {}
        for op in order:
            caption,color = candidates[op]
            row = rows.get(op)
            if row is None:
                row = self._palette_block(self._favorites_frame,op,caption,color)
            self._favorite_rows[op] = row
        for row in self._favorite_rows.values():
            row.pack_forget()
        for row in self._favorite_rows.values():
            row.pack(fill="x",padx=5,pady=2)
        if not order:
            ttk.Label(self._favorites_frame, text="☆를 눌러 즐겨찾기에 추가하세요.",
                      padding=5, wraplength=170).pack(anchor="w")

    def _palette_block(self, parent, op, caption, color):
        row = ttk.Frame(parent)
        row.pack(fill="x", padx=5, pady=2)
        pinned = op in self.favorites
        star = tk.Button(row,text="★" if pinned else "☆",width=2,relief="flat",cursor="hand2",
                         foreground="#895000" if pinned else "#4c5665",command=lambda:self._toggle_favorite(op))
        star.pack(side="left",fill="y")
        self._palette_stars.append((op, star))
        Tooltip(star,lambda: "즐겨찾기 해제" if op in self.favorites else "즐겨찾기 추가")
        lab = tk.Label(row,text=caption,font=FONT,background=color,foreground="white",anchor="w",
                       padx=8,pady=5,cursor="hand2",wraplength=225,justify="left")
        lab.pack(fill="x",expand=True)
        lab.bind("<Configure>", lambda e: lab.configure(wraplength=max(1,e.width-16)))
        def begin(e):
            self.start_drag(e,new=op)
            self.drag["favorite"] = parent == self._favorites_frame
        lab.bind("<ButtonPress-1>",begin)
        lab.bind("<B1-Motion>",self.on_drag)
        lab.bind("<ButtonRelease-1>",self.end_drag)
        return row

    def _apply_palette_visibility(self):
        # Reuse widgets and preserve the viewport; Tk paints after this batch.
        for widget, advanced in self._palette_visibility:
            widget.pack_forget()
        for widget, advanced in self._palette_visibility:
            if not advanced or self.show_advanced.get() or self.palette_query.get().strip():
                widget.pack(**widget._palette_pack)

    def _build_palette(self):
        for widget in self.palette.winfo_children():
            widget.destroy()
        self._palette_stars = []
        self._palette_visibility = []
        self._favorite_candidates = []
        terms = self.palette_query.get().casefold().split()
        matches = 0
        self.pal_canvas.yview_moveto(0)
        is_manosaba = (self.project.get("takeover") or {}).get("mod", "").casefold() == "manosaba"
        favorites = ttk.LabelFrame(self.palette,text="★ 즐겨찾기")
        self._favorites_frame = favorites
        if not self.browse_saved.get():
            favorites.pack(fill="x",padx=4,pady=4)
        for key, preset in sorted(self.saved_presets.items(), key=lambda pair: pair[1]["name"].casefold()):
            if not self.browse_saved.get() and not terms:
                continue
            keywords = " ".join(["저장한 블록 모음", preset["name"],
                                 *(B.SPECS[b["op"]]["ko"] for b in B.walk(preset["blocks"]))]).casefold()
            if not all(term in keywords for term in terms):
                continue
            if not matches:
                ttk.Label(self.palette, text="저장한 블록 모음", font=FONT_B).pack(anchor="w", padx=6)
            matches += 1
            row = ttk.Frame(self.palette)
            row.pack(fill="x", padx=6, pady=2)
            ttk.Button(row,text="×",width=3, command=lambda k=key:self._delete_preset(k)).pack(side="right")
            label = ttk.Label(row, text=preset["name"], padding=5, relief="ridge", cursor="hand2")
            label.pack(side="left",fill="x",expand=True)
            Tooltip(label, lambda p=preset:self._preset_summary(p), delay=300, wrap=520)
            label.bind("<Button-3>", lambda e,k=key:self._rename_preset(k))
            label.bind("<ButtonPress-1>", lambda e, p=preset: self.start_drag(e, preset=p))
            label.bind("<B1-Motion>", self.on_drag)
            label.bind("<ButtonRelease-1>", self.end_drag)
        if self.browse_saved.get():
            if not matches:
                ttk.Label(self.palette,text="표시할 묶음이 없습니다. 블록을 왼쪽으로 끌어 저장하세요.").pack()
            return
        for cat, ops in B.PALETTE:
            if cat == "mod_api" and not is_manosaba:
                continue
            name, _ = B.CATS[cat]
            color = _block_color(cat)
            show_heading = True
            category_rows = []
            for op in ops:
                spec = B.SPECS[op]
                if op == "kotodama_gain" and self.owner_kind not in ("card", "relic", "potion", "power"):
                    continue
                if op in ("manosaba_ema_summon", "manosaba_novel_summon", "manosaba_ignite",
                          "manosaba_attach_combust", "manosaba_gun_attack") and self.owner_kind != "card":
                    continue
                if op == "original_play" and not (self.owner_kind == "card" and (self.item.get("clone") or {}).get("editable_play")):
                    continue
                if op == "source_step" and not (self.owner_kind == "card" and self.item.get("clone")):
                    continue
                if op == "flash" and self.owner_kind not in ("relic", "power", "summon", "button", "pet"):
                    continue
                if op == "orb_grow" and self.owner_kind != "orb":
                    continue
                if op == "card_attack" and self.owner_kind != "card":
                    continue
                text = re.sub(r"\{\w+\}", "▢", spec["ko"])
                caption = PALETTE_NAMES.get(op, text)
                keywords = " ".join((name, text, caption, PALETTE_NAMES.get(op, ""), op, *(label for _, label in B.PICK_ACTIONS
                                                    if op in ("pick", "picked_action")))).casefold()
                if not all(term in keywords for term in terms):
                    continue
                caption = ("⊓ " if spec.get("body") else "") + caption
                self._favorite_candidates.append((op, caption, color))
                matches += 1
                if show_heading:
                    heading = tk.Label(self.palette, text=name, font=FONT_B, background=C["surface"], foreground=_darker(color, 0.8),
                             anchor="w")
                    heading.pack(fill="x", padx=6, pady=(10, 2))
                    show_heading = False
                row = self._palette_block(self.palette, op, caption, color)
                category_rows.append((row, _advanced_palette_block(op, spec)))
            if category_rows:
                self._palette_visibility.append((heading, all(advanced for _, advanced in category_rows)))
                self._palette_visibility.extend(category_rows)
        self._refresh_favorites()
        if terms and not matches:
            ttk.Label(self.palette, text="검색 결과가 없습니다." if self.show_advanced.get() else "검색 결과가 없습니다. 고급 블록도 확인해 보세요.").pack(padx=8, pady=12)
            return
        tk.Label(self.palette, text="\n블록을 여기로 끌어오면 라이브러리에 복사합니다.\n오른쪽 클릭: 연결(가져온 호출) / 복제 / 삭제",
                 font=("Malgun Gothic", 9), background=C["surface"], foreground=C["muted"], justify="left").pack(fill="x", padx=6)
        flags = dict(self._palette_visibility)
        self._palette_visibility = [(w,flags.get(w,False)) for w in self.palette.pack_slaves()]
        for widget, _ in self._palette_visibility:
            widget._palette_pack = widget.pack_info()
            widget._palette_pack.pop("in", None)
        self._apply_palette_visibility()


    # ---------------- 그리기 ----------------
    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    @buffered_canvas("canvas", defer_new=True)
    def render(self):
        self.block_headers = []
        self.group_blocks = []
        self.selection_origin = None
        self.group_delete.configure(state="disabled")
        self.group_save.configure(state="disabled")
        self.mode_hint.configure(text="왼쪽 블록을 작업 공간으로 끌어다 놓으세요.")
        old_frames = self.frames
        self.frames = []
        self.canvas.delete("all")
        self.slots = []
        self._pending_block_windows = []
        y = self._layout_list(self.blocks, 16, 16, top=True)
        w = max([f.winfo_reqwidth() + 80 for f in self.frames] + [400])
        self.canvas.configure(scrollregion=(0, 0, w + 200, y + 200))
        for x, y, frame in self._pending_block_windows:
            self.canvas.create_window(x,y,window=frame,anchor="nw")
        self._pending_block_windows = []
        def bind_selection(widget):
            if self.select_bindtag not in widget.bindtags():
                widget.bindtags((self.select_bindtag,) + widget.bindtags())
            for child in widget.winfo_children():
                bind_selection(child)
        bind_selection(self.canvas)
        self.refresh_outputs()
        for frame in old_frames:
            frame.destroy()

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
        color = _block_color(spec["cat"])
        frame = self._block_frame(b, spec, color)
        self._pending_block_windows.append((x,y,frame))
        frame.update_idletasks()
        h = frame.winfo_reqheight()
        self._bind_drag(frame, b, lst)
        self.block_headers.append((b, lst, frame, (x, y, x + frame.winfo_reqwidth(), y + h)))
        y2 = y + h
        if spec.get("body"):
            inner_top = y2
            y2 = self._layout_list(b.setdefault("body", []), x + 22, y2 + 4)
            for key, label in spec.get("sections", []):
                self.canvas.create_rectangle(x, inner_top, x + 14, y2, fill=color, outline="")
                ef = self._section_frame(b, spec, label, color)
                self._pending_block_windows.append((x,y2,ef))
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
        caption = B.block_caption(b)
        parts = re.split(r"(\{\w+\})", caption)
        row = inner
        if b["op"] == "src_call" and len(b.get("slots", [])) > 3:
            row = tk.Frame(inner, background=color)
            row.pack(anchor="w")
        elif len(spec.get("args", {})) > 4:
            row = tk.Frame(inner, background=color)
            row.pack(anchor="w")
        count = 0
        for part in parts:
            if not part:
                continue
            m = re.match(r"\{(\w+)\}", part)
            if m:
                key = m.group(1)
                w = self._arg_widget(row, b, key, B.arg_kind(b, key))
                w.pack(side="left", padx=2)
                count += 1
                if row is not inner and count % 3 == 0:     # 칸이 많으면 줄을 바꿔 너무 넓어지지 않게
                    row = tk.Frame(inner, background=color)
                    row.pack(anchor="w")
            else:
                lab = tk.Label(row, text=part, font=FONT_B, background=color, foreground="white")
                lab.pack(side="left")
                if b["op"] == "src_call" and part.strip() == (b.get("label") or "").strip():
                    try:
                        import uxkit
                        uxkit.tip(lab, "현재 코드 결과:\n" + self._src_preview(b))
                    except Exception:
                        pass
        if b["op"] in ("src_call", "source_step", "src_loop"):
            frame.configure(highlightbackground="#1f2a44", highlightthickness=2)
        return frame

    def _src_preview(self, b):
        try:
            g = B._Gen(self.project, M._Ctx("card", self.item))
            return "\n".join(l.strip() for l in g.stmt(dict(b, body=[], **({"else": []} if "else" in b else {})), ""))[:600]
        except Exception as exc:     # 미리보기는 실패해도 편집에는 지장 없음
            return f"(미리보기 실패: {exc})"

    def _code_choices(self, op, key):
        if op not in B.SPECS or op in ("src_call", "src_loop"):
            return {}
        ctx = M._Ctx(self.owner_kind, self.item)
        if key in ("creature", "target", "attacker", "applier"):
            choices = {"자신": ctx.me, "무작위 적 한 명": "@random_enemy"}
            if ctx.single:
                choices["선택한 대상"] = ctx.single
            return choices
        if key == "card_type":
            return {f"{M.text(c, 'name', 'ko')} ({c['id']})": M.item_cls(self.project, "card", c)
                    for c in self.project.get("cards", [])}
        if key == "card":
            choices = {"방금 변화한 카드":"@replacement", "손패에서 무작위 한 장": "@random_hand"}
            if self.owner_kind == "card":
                choices["이 카드"] = "this"
            return choices
        if key == "power_type":
            return {label: meta["cls"] for pid, label in M.power_options(self.project)
                    if (meta := M.power_meta(self.project, pid))}
        if key == "player":
            return {"소유 플레이어": ctx.player}
        if key == "pile":
            return {label: "PileType." + pile for pile, label in B.PILES}
        if key == "position" and B.SPECS[op]["args"][key][1].startswith("CardPilePosition."):
            return {"맨 위": "CardPilePosition.Top", "맨 아래": "CardPilePosition.Bottom", "무작위 위치": "CardPilePosition.Random"}
        if key == "keyword":
            return {label: "CardKeyword." + code for code, label in M.CARD_KEYWORDS}
        return {}

    def _arg_widget(self, parent, b, key, kind):
        a = b["args"]
        changed = self._changed

        def set_(v):
            a[key] = v
            changed()
        if kind in ("who_multi", "who_one"):
            options = B.who_options(self.owner_kind, kind == "who_multi")
            if self.card_event:
                target = self.item.get("event_targets", {}).get(self.card_event, "random")
                target_label = dict(M.CARD_EVENT_TARGETS).get(target, target)
                if target == "choose":
                    target_label = f"직접 고른 적 최대 {M.card_event_target_count(self.item, self.card_event)}명"
                options = [(code, "이벤트 대상 · " + target_label if code == "target" else label) for code, label in options]
            return _Combo(parent, options, a.get(key), 15, set_)
        if kind == "choice":
            s = B.slot_info(b, key)
            opts = [tuple(o) for o in s.get("options", [])] or [(a.get(key, ""), a.get(key, ""))]
            return _Combo(parent, opts, a.get(key), max(10, min(22, max(len(l) for _c, l in opts))), set_)
        if kind == "manosaba_monster":
            takeover = self.project.get("takeover") or {}
            monsters = takeover.get("novel_monsters", []) or []
            opts = [(x, x.rsplit(".", 1)[-1]) for x in monsters]
            current = str(a.get(key) or "")
            if current and all(code != current for code, _label in opts):
                opts.insert(0, (current, current.rsplit(".", 1)[-1]))
            if not opts:
                opts = [("", "(가져온 몬스터를 불러올 수 없습니다)")]
            return _Combo(parent, opts, current, 18, set_)
        if kind == "code":
            # 원본 식을 그대로 고쳐 쓰는 칸 (목록에서 자주 쓰는 값을 고를 수도 있음)
            s = B.slot_info(b, key)
            cur = str(a.get(key, "") or "")
            opts = list(dict.fromkeys([cur] + list(s.get("options", []) or []) + ([s["orig"]] if s.get("orig") else [])))
            choices = self._code_choices(b["op"], key)
            if B.SPECS.get(b["op"], {}).get("args", {}).get(key, (None, None))[1] in ("true", "false"):
                choices.update({"예": "true", "아니오": "false"})
            labels = {code: label for label, code in choices.items()}
            options = list(choices) + [code for code in opts if code not in labels]
            display = labels.get(cur, cur)
            v = tk.StringVar(value=display)
            w = ttk.Combobox(parent, textvariable=v, values=options, width=max(14, min(30, len(display) + 2)), font=FONT)
            state = {"pushed": False}

            def upd(*_):
                if not state["pushed"]:
                    self._push_history()
                    state["pushed"] = True
                a[key] = choices.get(v.get(), v.get())
                changed()
            v.trace_add("write", upd)
            return w
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
        if kind == "shared_name":
            names = self.project.get("shared_blocks", {})
            return _Combo(parent, [(n,n) for n in names], a.get(key), 18, set_)
        if kind == "result_pool":
            options = [(k,v[0]) for k,v in M.transform_pools(self.project).items()]
            current = a.get(key, "")
            if current not in dict(options):
                options.append((current, "찾을 수 없는 카드 풀"))
            def select_pool(value):
                set_(value)
                self.render()
            return _Combo(parent, options, current, 16, select_pool)
        if kind == "result_filter":
            import gimmick as G
            options = G.card_filters(self.project) + [("kw:" + code, label + " 키워드 카드") for code, label in M.CARD_KEYWORDS]
            frame = ttk.Frame(parent)
            def candidates():
                f = a.get(key, "Any")
                pool_key = a.get("result_pool", "")
                target = M.transform_pools(self.project).get(pool_key, ("",""))[1]
                return [c for c in self.project.get("cards", []) if (not pool_key or M.effective_card_pool(self.project,c) == target) and (f == "Any" or c.get("type") == f
                        or (f.startswith("tag:") and f[4:] in c.get("gtags", []))
                        or (f.startswith("kw:") and f[3:] in c.get("keywords", [])))]
            def show_candidates():
                rows = candidates()
                names = "\n".join(f"{M.text(c, 'name', 'ko')} ({c['id']})" for c in rows)
                messagebox.showinfo("현재 프로젝트의 변화 후보", names or "현재 프로젝트에 이 조건을 만족하는 카드가 없습니다.", parent=self)
            def select(value):
                set_(value)
                button.configure(text=f"후보 {len(candidates())}장")
            _Combo(frame, options, a.get(key, "Any"), 20, select).pack(side="left")
            button = ttk.Button(frame, text=f"후보 {len(candidates())}장", command=show_candidates)
            button.pack(side="left")
            return frame
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
        if kind == "card_ref":
            return _Combo(parent, B.CARD_REFS, a.get(key), 22, set_)
        if kind == "clone_policy":
            return _Combo(parent, B.CLONE_POLICIES, a.get(key), 12, set_)
        if kind == "end_policy":
            return _Combo(parent, B.END_POLICIES, a.get(key), 18, set_)
        if kind == "draw_pos":
            return _Combo(parent, B.DRAW_POS, a.get(key), 10, set_)
        if kind == "enchant":
            return _Combo(parent, B.ENCHANTS, a.get(key), 20, set_)
        if kind == "gtag":
            import gimmick as G
            opts = [(t["id"], "#" + (t.get("name_ko") or t["id"])) for t in G.tags(self.project)] or \
                [("", "('🎲 기믹' 탭에서 태그를 만드세요)")]
            return _Combo(parent, opts, a.get(key), 16, set_)
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
        if kind == "source":
            summary = tk.StringVar(value=a.get(key, "").strip().split("\n")[0][:64] or "편집")
            def edit_source():
                window = tk.Toplevel(self)
                window.title("직접 코드 단계 편집")
                t = tk.Text(window, width=80, height=12, undo=True)
                t.pack(fill="both", expand=True)
                t.insert("1.0", a.get(key, ""))
                def save():
                    self._push_history()
                    a[key] = t.get("1.0", "end-1c")
                    summary.set(a[key].strip().split("\n")[0][:64] or "편집")
                    window.destroy()
                    changed()
                ttk.Button(window, text="적용", command=save).pack()
                window.transient(self)
                window.grab_set()
            return ttk.Button(parent, textvariable=summary, command=edit_source)
        if kind == "raw_stat":
            var = next((v for v in self.item.get("raw_vars", []) if v["name"] == a.get(key)), {})
            frame = ttk.Frame(parent)
            for field, label in (("value", ""), ("upgrade", "강화 +")):
                ttk.Label(frame, text=label).pack(side="left")
                state = tk.StringVar(value=str(var.get(field, 0)))
                entry = ttk.Entry(frame, width=5, textvariable=state)
                entry.pack(side="left")
                entry.raw_state = state
                def update(*_, v=state, f=field):
                    try:
                        var[f] = int(v.get())
                    except ValueError:
                        return
                    changed()
                state.trace_add("write", update)
            return frame
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
            default = B.SPECS.get(b.get("op"), {}).get("args", {}).get(key, ("bool", False))[1]
            v = tk.BooleanVar(value=bool(a.get(key, default)))
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

    def _cleanup_drag_on_destroy(self, event):
        if event.widget is self:
            self._clear_drag_feedback()
            self._restore_drag_windows()

    def _clear_drag_feedback(self):
        feedback, self._drag_feedback = self._drag_feedback, None
        if feedback:
            for widget in [feedback["window"], *feedback["marks"]]:
                try:
                    widget.destroy()
                except tk.TclError:
                    pass
        try:
            self.canvas.delete("drag_origin")
        except tk.TclError:
            pass

    def _show_drag_feedback(self, event, title, count, action, target=None):
        colors = {"save": ("#15803d", "#ecfdf3", "＋ 묶음으로 저장"),
                  "move": ("#175ac1", "#eef5ff", "↕ 여기에 이동"),
                  "add": ("#175ac1", "#eef5ff", "＋ 여기에 추가"),
                  "invalid": ("#b43b37", "#fff1f0", "× 여기에 놓을 수 없습니다")}
        color, background, caption = colors[action]
        feedback = self._drag_feedback
        if feedback is None:
            window = tk.Toplevel(self)
            window.withdraw()
            window.overrideredirect(True)
            window.attributes("-topmost", True)
            frame = tk.Frame(window, background=background, highlightthickness=2, highlightbackground=color)
            frame.pack(fill="both", expand=True)
            badge = tk.Label(frame, font=FONT_B, anchor="w", background=background, foreground=color, padx=10, pady=4)
            badge.pack(fill="x")
            detail = tk.Label(frame, font=FONT, anchor="w", justify="left", wraplength=260, background=background, foreground="#253345", padx=10, pady=4)
            detail.pack(fill="x")
            feedback = self._drag_feedback = dict(window=window, frame=frame, badge=badge, detail=detail, target=None, marks=[])
        feedback["frame"].configure(background=background, highlightbackground=color)
        feedback["badge"].configure(text=f"{caption} · {count}개", background=background, foreground=color)
        feedback["detail"].configure(text=title, background=background)
        feedback["window"].geometry(f"+{max(0,event.x_root+18)}+{max(0,event.y_root+18)}")
        feedback["window"].deiconify()
        feedback["window"].lift()
        if feedback["target"] is not target:
            for widget in feedback["marks"]:
                widget.destroy()
            feedback["marks"] = []
            feedback["target"] = target
            if target is not None:
                for position in ("top", "bottom", "left", "right"):
                    edge = tk.Frame(target, background=color)
                    if position in ("top", "bottom"):
                        edge.place(relx=0, rely=0 if position=="top" else 1, relwidth=1, height=4, anchor="nw" if position=="top" else "sw")
                    else:
                        edge.place(relx=0 if position=="left" else 1, rely=0, relheight=1, width=4, anchor="nw" if position=="left" else "ne")
                    feedback["marks"].append(edge)
                banner = tk.Label(target, font=FONT_B, background=background, foreground=color, padx=12, pady=7, relief="solid", borderwidth=1)
                banner.place(relx=.5, y=7, anchor="n")
                feedback["marks"].append(banner)
        if target is not None:
            for edge in feedback["marks"][:-1]:
                edge.configure(background=color)
                edge.lift()
            feedback["marks"][-1].configure(text=f"{caption} · 블록 {count}개", background=background, foreground=color)
            feedback["marks"][-1].lift()
        self.mode_hint.configure(text=caption + f" · 블록 {count}개" + (" (원본은 유지됩니다)" if action=="save" else ""))

    def _over_workspace(self, event):
        x,y = event.x_root-self.canvas.winfo_rootx(),event.y_root-self.canvas.winfo_rooty()
        if not (0 <= x < self.canvas.winfo_width() and 0 <= y < self.canvas.winfo_height()):
            return False
        widget = self.winfo_containing(event.x_root,event.y_root)
        feedback = self._drag_feedback
        if feedback and feedback["target"] is self.workspace_panel and widget in feedback["marks"]:
            return True
        while widget is not None:
            if widget is self.canvas:
                return True
            widget = widget.master
        return False

    def _drag_title(self, blocks):
        import preview as PV
        names = []
        for block in blocks[:3]:
            text = B.describe([block], self.project, self.owner_kind, "ko", self.item)
            text = PV.fill_values(self.project, text, self.item)
            plain = "".join(part for part, _ in PV.parse_bbcode(text))
            names.append(plain[:90] or re.sub(r"\{\w+\}", "▢", B.block_caption(block)))
        return "\n".join(names) + (f"\n외 {len(blocks)-3}개" if len(blocks)>3 else "")

    def _keep_drop_window_visible(self, event, to_library):
        target = self.library_panel if to_library else self.workspace_panel
        window = self.block_panes.floating_window(target)
        if window is None:
            return
        try:
            source = event.widget.winfo_toplevel()
            if window is source:
                return
            if window not in self._drag_window_owners:
                self._drag_window_owners[window] = window.transient()
                # Owned palettes stay above the drag source without taking keyboard focus
                # or making the palette globally topmost over other applications.
                window.transient(source)
            window.lift()
        except (AttributeError, tk.TclError):
            pass

    def _restore_drag_windows(self):
        owners, self._drag_window_owners = self._drag_window_owners, {}
        for window, owner in owners.items():
            try:
                if window.winfo_exists():
                    if owner and not self.tk.getboolean(self.tk.call("winfo", "exists", owner)):
                        owner = ""
                    window.transient(owner)
            except tk.TclError:
                pass

    def _cancel_block_drag(self, event=None):
        self.drag = None
        self.group_moving = False
        self.selection_origin = None
        self.canvas.delete("drag", "group_box")
        self._clear_drag_feedback()
        self._restore_drag_windows()
        self.mode_hint.configure(text="드래그를 취소했습니다.")
        return "break"

    def start_drag(self, e, new=None, block=None, src=None, preset=None):
        self._clear_drag_feedback()
        self._restore_drag_windows()
        self.drag = {"preset": preset, "new": new, "block": block, "src": src, "x0": e.x_root, "y0": e.y_root, "moved": False}

    def _canvas_xy(self, e):
        return (self.canvas.canvasx(e.x_root - self.canvas.winfo_rootx()),
                self.canvas.canvasy(e.y_root - self.canvas.winfo_rooty()))

    def on_drag(self, e):
        d = self.drag
        if not d:
            return
        if not d["moved"] and abs(e.x_root-d["x0"])+abs(e.y_root-d["y0"]) < 6:
            return
        d["moved"] = True
        self._keep_drop_window_visible(e, to_library=d["block"] is not None)
        x,y = self._canvas_xy(e)
        self.canvas.delete("drag", "drag_origin")
        blocks = d["preset"]["blocks"] if d["preset"] else [d["block"]] if d["block"] is not None else [B.new_block(d["new"])]
        title = d["preset"]["name"] + "\n" + self._drag_title(blocks) if d["preset"] else self._drag_title(blocks)
        count = len(blocks)
        if d["block"] is not None:
            for block,_,_,(left,top,right,bottom) in self.block_headers:
                if block is d["block"]:
                    self.canvas.create_rectangle(left-3,top-3,right+3,bottom+3,outline="#175ac1",width=3,dash=(5,3),tags="drag_origin")
        if d.get("favorite") and self._favorite_drop_index(e) is not None:
            self._show_drag_feedback(e,"즐겨찾기 순서 변경",1,"move",self._favorites_frame)
            return
        if d["block"] is not None and self._over_library(e):
            self._show_drag_feedback(e,title,count,"save",self.library_panel)
            return
        slot = self._nearest_slot(x,y,d) if self._over_workspace(e) else None
        if slot:
            _,_,sx,sy = slot
            action = "move" if d["block"] is not None else "add"
            self._show_drag_feedback(e,title,count,action,self.workspace_panel)
            self.canvas.create_text(sx,sy-3,anchor="sw",text=f"여기에 블록 {count}개 " + ("이동" if action=="move" else "추가"),fill="#175ac1",tags="drag")
            self.canvas.create_line(sx-4,sy,sx+260,sy,fill="#175ac1",width=5,tags="drag")
        else:
            self._show_drag_feedback(e,title,count,"invalid")

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

    def _favorite_drop_index(self, e):
        frame = self._favorites_frame
        if not frame.winfo_ismapped():
            return None
        x,y = e.x_root-frame.winfo_rootx(), e.y_root-frame.winfo_rooty()
        if not (0 <= x < frame.winfo_width() and 0 <= y < frame.winfo_height()):
            return None
        rows = list(self._favorite_rows.values())
        return sum(e.y_root >= row.winfo_rooty()+row.winfo_height()/2 for row in rows)

    def _move_favorite(self, op, index):
        visible = list(self._favorite_rows)
        if op not in visible:
            return
        old = visible.index(op)
        visible.remove(op)
        visible.insert(max(0,index-(old<index)),op)
        # Preserve positions of favorites hidden by search/context filters.
        sequence = iter(visible)
        order = [next(sequence) if key in visible else key for key in self.favorite_order]
        if not self._save_favorites(order):
            return
        self._favorite_rows = {key:self._favorite_rows[key] for key in visible}
        for row in self._favorite_rows.values():
            row.pack_forget()
        for row in self._favorite_rows.values():
            row.pack(fill="x",padx=5,pady=2)
        self.mode_hint.configure(text="즐겨찾기 순서를 저장했습니다.")

    def end_drag(self, e):
        d, self.drag = self.drag, None
        over_library = self._over_library(e)
        over_workspace = self._over_workspace(e)
        self._clear_drag_feedback()
        self._restore_drag_windows()
        self.canvas.delete("drag")
        if not d or not d["moved"]:
            return
        if d.get("favorite") and self._favorite_drop_index(e) is not None:
            self._move_favorite(d["new"], self._favorite_drop_index(e))
            return
        if over_library:
            if d["block"] is not None:
                self._save_group([d["block"]])
            else:
                self.mode_hint.configure(text="라이브러리의 블록은 작업 공간에 놓으세요.")
            return
        if not over_workspace:
            self.mode_hint.configure(text="드래그를 취소했습니다. 놓을 수 있는 영역을 선택하세요.")
            return
        x, y = self._canvas_xy(e)
        slot = self._nearest_slot(x, y, d)
        if not slot:
            return
        lst, idx, _sx, _sy = slot
        if d["preset"]:
            resolved = self._resolve_preset(d["preset"]["blocks"])
            if resolved is None:
                return
        self._push_history()
        if d["preset"]:
            lst[idx:idx] = resolved
        elif d["new"]:
            block = B.new_block(d["new"])
            if d["new"] == "shared_call":
                block["args"]["name"] = next(iter(self.project.get("shared_blocks", {})), "")
            lst.insert(idx, block)
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
        count = len(d["preset"]["blocks"]) if d["preset"] else 1
        self.mode_hint.configure(text=f"블록 {count}개를 " + ("이동했습니다." if d["block"] is not None else "추가했습니다."))

    def context_menu(self, e, b, lst):
        m = tk.Menu(self, tearoff=0)
        if b.get("op") == "src_call":
            m.add_command(label="효과 블록으로 연결…", command=lambda: self._map_call(b, lst))
            m.add_separator()
        m.add_command(label="복제", command=lambda: self._dup(b, lst))
        m.add_command(label="삭제", command=lambda: self._del(b, lst))
        m.tk_popup(e.x_root, e.y_root)

    def _map_call(self, block, lst):
        _source_call_slots(block)
        dialog = CallMappingDialog(self, self, block)
        self.wait_window(dialog)
        if not dialog.result:
            return
        self._push_history()
        index = next((i for i, value in enumerate(lst) if value is block), None)
        if index is None:
            return
        replacement = dialog.result["block"]
        if dialog.result.get("rule"):
            replacement["mapped_signature"] = dialog.result["rule"]["signature"]
            replacement["mapped_rule"] = copy.deepcopy(dialog.result["rule"])
            self.pending_call_mappings.append(copy.deepcopy(dialog.result["rule"]))
        lst[index] = replacement
        self.render()
        self._changed()

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
    def _resolve_preset(self, source):
        blocks = copy.deepcopy(source)
        groups = {"카드": self.project.get("cards", []),
                  "태그": self.project.get("gimmicks", {}).get("tags", [])}
        ids = {kind: {row["id"] for row in rows} for kind, rows in groups.items()}
        missing = {}

        def collect(node, key, kind, prefix=""):
            value = node.get(key)
            if isinstance(value, str) and value.startswith(prefix):
                ident = value[len(prefix):]
                if ident and ident not in ids[kind]:
                    missing.setdefault((kind, ident), []).append((node, key, prefix))

        def filters(node):
            if isinstance(node, list):
                for child in node:
                    filters(child)
            elif isinstance(node, dict):
                for key, value in node.items():
                    if key in ("filter", "ctype", "result_filter", "played_filter"):
                        collect(node, key, "태그", "tag:")
                    else:
                        filters(value)

        for block in B.walk(blocks):
            args = block.get("args", {})
            for key in args:
                if B.SPECS[block["op"]].get("args", {}).get(key, (None,))[0] == "card" and args[key] != "this":
                    collect(args, key, "카드")
            filters(args)

        for (kind, old), slots in missing.items():
            rows = groups[kind]
            if not rows:
                messagebox.showwarning("블록 모음 연결", f"이 프로젝트에는 '{old}' 대신 연결할 {kind}가 없습니다. 먼저 {kind}를 추가하세요.", parent=self)
                return None
            dialog = tk.Toplevel(self)
            dialog.title("블록 모음 연결")
            dialog.transient(self)
            ttk.Label(dialog, text=f"찾을 수 없는 {kind} ID '{old}' 대신 사용할 {kind}를 선택하세요.", padding=8).pack()
            picker = ttk.Combobox(dialog, state="readonly", width=44,
                                  values=[f"{M.text(row, 'name', 'ko')} ({row['id']})" for row in rows])
            picker.pack(fill="x", padx=8)
            chosen = []
            def accept():
                if picker.current() >= 0:
                    chosen.append(rows[picker.current()]["id"])
                    dialog.destroy()
            buttons = ttk.Frame(dialog, padding=8)
            buttons.pack()
            ttk.Button(buttons, text="연결", command=accept).pack(side="left")
            ttk.Button(buttons, text="취소", command=dialog.destroy).pack(side="left")
            dialog.bind("<Escape>", lambda _: dialog.destroy())
            center_window(dialog)
            dialog.grab_set()
            self.wait_window(dialog)
            self.grab_set()
            if not chosen:
                return None
            for node, key, prefix in slots:
                node[key] = prefix + chosen[0]
        return blocks

    def _preset_summary(self, preset):
        lines = [preset["name"]]
        def show(rows, depth):
            for block in rows:
                caption = B.block_caption(block)
                args = block.get("args", {})
                def field(match):
                    k = match.group(1)
                    v = args.get(k,"")
                    if isinstance(v,dict):
                        return (B.cond_label(v,self.project) if k=="cond" else B.value_label(v,self.project))
                    return str(v)
                lines.append("  "*depth + "• " + re.sub(r"\{(\w+)\}",field,caption))
                for branch in B.BODY_KEYS:
                    if block.get(branch):
                        if branch != "body":
                            lines.append("  "*depth + ("아니면" if branch=="else" else "세 번째 갈래"))
                        show(block[branch],depth+1)
        show(preset["blocks"],0)
        return "\n".join(lines)

    def _rename_preset(self, key):
        preset = self.saved_presets[key]
        name = simpledialog.askstring("이름 변경", "새 이름", initialvalue=preset["name"], parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if any(k!=key and v["name"].casefold()==name.casefold() for k,v in self.saved_presets.items()):
            messagebox.showwarning("이름 변경","이미 사용 중인 이름입니다.",parent=self)
            return
        try:
            self._store_preset(key,name,preset["blocks"])
        except OSError as exc:
            messagebox.showerror("이름 변경",str(exc),parent=self)
            return
        self.palette_query.set(name)

    def _delete_preset(self, key):
        name = self.saved_presets[key]["name"]
        if not messagebox.askyesno("라이브러리에서 삭제",f"‘{name}’ 묶음을 삭제할까요?",parent=self):
            return
        try:
            (self.preset_dir/(key+".json")).unlink(missing_ok=True)
        except OSError as exc:
            messagebox.showerror("삭제 실패",str(exc),parent=self)
            return
        del self.saved_presets[key]
        self._build_palette()

    def _delete_group(self):
        if self.group_blocks:
            self._push_history()
            selected = {id(b) for b in self.group_blocks}
            self.group_source[:] = [b for b in self.group_source if id(b) not in selected]
            self.render()

    def _delete_selection_key(self, event):
        if self.group_blocks:
            self._delete_group()
            return "break"

    def _over_library(self, event):
        widget = self.winfo_containing(event.x_root, event.y_root)
        floating = self.block_panes.floating_window(self.library_panel)
        while widget is not None:
            if widget is self.library_panel or widget is floating:
                return True
            widget = widget.master
        return False

    def _group_start(self, event):
        if event.widget != self.canvas and not isinstance(event.widget,(tk.Frame,tk.Label)):
            return
        x,y = self._canvas_xy(event)
        for block,_,_,(a,b,c,d) in self.block_headers:
            if a <= x <= c and b <= y <= d and any(v is block for v in self.group_blocks):
                self.canvas.focus_set()
                self.group_moving = True
                self.group_anchor = (x,y)
                return "break"
        if event.widget == self.canvas:
            self.canvas.focus_set()
            self.selection_origin = (x,y)
            self._group_motion(event)
            return "break"

    def _group_slot(self, event):
        x,y = self._canvas_xy(event)
        banned = {id(b[k]) for b in B.walk(self.group_blocks) for k in B.BODY_KEYS if k in b}
        slots = [slot for slot in self.slots if id(slot[0]) not in banned]
        return min(slots,key=lambda s:abs(s[3]-y)+0.6*abs(s[2]-x),default=None)

    def _group_motion(self, event):
        if self.group_moving:
            x,y = self._canvas_xy(event)
            if abs(x-self.group_anchor[0])+abs(y-self.group_anchor[1]) < 6:
                return "break"
            self._keep_drop_window_visible(event, to_library=True)
            self.canvas.delete("group_box")
            title,count = self._drag_title(self.group_blocks),len(self.group_blocks)
            if self._over_library(event):
                self._show_drag_feedback(event,title,count,"save",self.library_panel)
                return "break"
            slot = self._group_slot(event) if self._over_workspace(event) else None
            if slot:
                _,_,x,y = slot
                self._show_drag_feedback(event,title,count,"move",self.workspace_panel)
                self.canvas.create_text(x,y-3,anchor="sw",text=f"여기에 블록 {count}개 이동",fill="#175ac1",tags="group_box")
                self.canvas.create_line(x,y,x+260,y,fill="#175ac1",width=5,tags="group_box")
            else:
                self._show_drag_feedback(event,title,count,"invalid")
            return "break"
        if self.selection_origin is None:
            return
        x, y = self._canvas_xy(event)
        x0, y0 = self.selection_origin
        left, right = sorted((x0,x))
        top, bottom = sorted((y0,y))
        self.canvas.delete("group_box")
        self.canvas.create_rectangle(left,top,right,bottom,outline="#215fb4",dash=(4,2),tags="group_box")
        covered = set()
        selected = []
        for block, siblings, frame, (a,b,c,d) in self.block_headers:
            hit = a <= right and left <= c and b <= bottom and top <= d
            if hit and id(block) not in covered:
                selected.append((siblings,block))
                covered.update(id(child) for child in B.walk([block]))
        compatible = len({id(siblings) for siblings,_ in selected}) <= 1
        self.canvas.delete("selection_marks")
        for block, _, frame, (a,b,c,d) in self.block_headers:
            color = _block_color(B.SPECS[block["op"]]["cat"])
            active = id(block) in covered
            accent = "#064eb5" if compatible else "#9b4411"
            fill = accent if active else color
            def tint(widget):
                if isinstance(widget, (tk.Frame,tk.Label)) and widget.cget("background") in (color,"#064eb5","#9b4411"):
                    widget.configure(background=fill)
                for child in widget.winfo_children():
                    tint(child)
            tint(frame)
            frame.configure(highlightbackground=accent if active else _darker(color))
            if active:
                self.canvas.create_rectangle(a-3,b-2,c+3,d+2,outline=accent,width=3,tags="selection_marks")
                self.canvas.create_text(a-9,(b+d)/2,text="✓" if compatible else "!",fill=accent,font=FONT_B,tags="selection_marks")
        self.group_source = selected[0][0] if selected and compatible else None
        self.group_blocks = [block for _,block in selected] if compatible else []
        self.group_delete.configure(state="normal" if self.group_blocks else "disabled")
        hint = f"선택한 묶음: 블록 {len(self.group_blocks)}개" if compatible else "서로 다른 갈래입니다. 공통 조건 블록도 선택하세요."
        self.mode_hint.configure(text=hint)
        self.group_save.configure(state="normal" if self.group_blocks else "disabled")
        return "break"

    def _group_end(self, event):
        if self.group_moving:
            over_library = self._over_library(event)
            over_workspace = self._over_workspace(event)
            self._clear_drag_feedback()
            self._restore_drag_windows()
            self.group_moving = False
            self.canvas.delete("group_box")
            x,y = self._canvas_xy(event)
            if over_library:
                self.mode_hint.configure(text=f"선택한 묶음: 블록 {len(self.group_blocks)}개")
                self._save_group()
                return "break"
            slot = self._group_slot(event)
            if (slot and over_workspace and abs(x-self.group_anchor[0])+abs(y-self.group_anchor[1]) > 5):
                dest,index,_,_ = slot
                src = self.group_source
                ids = {id(b) for b in self.group_blocks}
                if dest is src:
                    index -= sum(id(b) in ids for b in src[:index])
                moved_count = len(self.group_blocks)
                self._push_history()
                src[:] = [b for b in src if id(b) not in ids]
                dest[index:index] = self.group_blocks
                self.render()
                self.mode_hint.configure(text=f"블록 {moved_count}개를 이동했습니다.")
            else:
                self.mode_hint.configure(text="이동을 취소했습니다. 블록은 원래 위치에 있습니다.")
            return "break"
        if self.selection_origin is not None:
            self._group_motion(event)
            self.selection_origin = None
            self.canvas.delete("group_box")
            return "break"

    def _save_group(self, blocks=None):
        blocks = self.group_blocks if blocks is None else blocks
        if not blocks:
            return
        name = simpledialog.askstring("라이브러리에 저장", "블록 묶음 이름", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        import uuid
        key = next((k for k,v in self.saved_presets.items() if v["name"].casefold()==name.casefold()), uuid.uuid4().hex)
        if key in self.saved_presets and not messagebox.askyesno("라이브러리", f"‘{name}’ 묶음을 바꿀까요?", parent=self):
            return
        try:
            self._store_preset(key, name, blocks)
        except OSError as exc:
            messagebox.showerror("라이브러리 저장 실패", str(exc), parent=self)
            return
        self.render()
        self.browse_saved.set(True)
        self.palette_query.set(name)
        self.mode_hint.configure(text=f"‘{name}’ 묶음을 라이브러리에 저장했습니다.")

    def _register_preset(self, path, blocks):
        source = Path(path).resolve()
        key = hashlib.sha256(os.path.normcase(str(source)).encode("utf8")).hexdigest()
        self._store_preset(key, source.stem, blocks)

    def _store_preset(self, key, name, blocks):
        record = {"name": name, "blocks": copy.deepcopy(blocks)}
        self.preset_dir.mkdir(parents=True, exist_ok=True)
        dest = self.preset_dir / (key + ".json")
        temp = dest.with_suffix(".tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf8")
        temp.replace(dest)
        self.saved_presets[key] = record
        self._build_palette()

    def save_blocks(self):
        if not self.blocks:
            messagebox.showinfo(TITLE, "저장할 블록이 없습니다.", parent=self)
            return
        path = filedialog.asksaveasfilename(parent=self, title="블록 모음 저장",
            defaultextension=".sts2blocks", filetypes=[("블록 모음", "*.sts2blocks")])
        if path:
            try:
                data = {"format": "sts2blocks-1", "blocks": self.blocks}
                Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")
                self._register_preset(path, self.blocks)
            except OSError as exc:
                messagebox.showerror(TITLE, str(exc), parent=self)

    def load_blocks(self):
        path = filedialog.askopenfilename(parent=self, title="블록 모음 불러오기",
            filetypes=[("블록 모음", "*.sts2blocks")])
        if not path:
            return
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
            if not isinstance(data, dict) or data.get("format") != "sts2blocks-1":
                raise ValueError("모드 메이커에서 저장한 블록 모음을 선택하세요.")
            blocks = data.get("blocks")
            if not isinstance(blocks, list) or not blocks:
                raise ValueError("저장된 블록 목록이 비어 있거나 손상되었습니다.")
            for block in B.walk(blocks):
                if (not isinstance(block, dict) or block.get("op") not in B.SPECS
                        or not isinstance(block.get("args", {}), dict)
                        or any(not isinstance(block[k], list) for k in B.BODY_KEYS if k in block)):
                    raise ValueError("지원하지 않는 블록이 포함되어 있습니다.")
            resolved = self._resolve_preset(blocks)
            if resolved is None:
                return
            self._push_history()
            self.blocks.extend(resolved)
            try:
                self.render()
                self._register_preset(path, blocks)
            except Exception:
                self.undo()
                raise
        except Exception as exc:
            messagebox.showerror("블록 모음 불러오기", str(exc) or repr(exc), parent=self)

    def _push_history(self):
        self.history.append(copy.deepcopy(self.blocks))
        if len(self.history) > 50:
            self.history.pop(0)

    def undo(self):
        if self.history:
            self.blocks = self.history.pop()
            self.render()

    def redecompose(self):
        """원본 OnPlay 를 다시 읽어 블록 하나하나로 푼다 (지금 블록은 되돌리기로 돌아올 수 있음)."""
        previous_mappings = self.project.get("call_mappings")
        had_mappings = "call_mappings" in self.project
        if self.pending_call_mappings:
            self.project["call_mappings"] = copy.deepcopy(previous_mappings or []) + copy.deepcopy(self.pending_call_mappings)
        try:
            blocks, info = self.on_decompose()
        except Exception as exc:
            detail = str(exc).strip() or repr(exc).strip() or type(exc).__name__
            trace = traceback.format_exc()
            if self.app is not None:
                self.app.log(f"[오류] 원본 코드 재분석 실패 ({type(exc).__name__}): {detail}\n{trace}")
            messagebox.showerror("원본 코드 분석 실패", "원본 코드를 블록으로 풀지 못했습니다.\n\n"
                                 f"{type(exc).__name__}: {detail}\n\n"
                                 "현재 효과는 유지됩니다. 도움말 → 건의 / 오류 보내기에서 오류 로그를 확인할 수 있습니다.",
                                 parent=self)
            return
        finally:
            if had_mappings:
                self.project["call_mappings"] = previous_mappings
            else:
                self.project.pop("call_mappings", None)
        if not blocks:
            reason = str(info or "").strip() or "변환할 수 있는 코드가 없습니다. 원본 DLL과 카드 클래스를 확인해 주세요."
            if self.app is not None:
                self.app.log(f"[오류] 원본 코드 블록 변환 실패: {reason}")
            messagebox.showwarning("원본 코드 분석 결과", "원본 코드를 블록으로 풀지 못했습니다.\n\n"
                                   f"{reason}\n\n현재 효과 블록은 그대로 유지됩니다.", parent=self)
            return
        self._push_history()
        self.blocks = blocks
        self.render()
        self._changed()

    def collapse_original(self):
        self._push_history()
        self.blocks = [{"op": "original_play", "args": {}}]
        self.render()
        self._changed()

    def clear_all(self):
        if self.blocks and messagebox.askyesno(TITLE, "블록을 모두 지울까요?", parent=self):
            self._push_history()
            self.blocks = []
            self.render()

    # ---------------- 결과 ----------------
    def _changed(self):
        self.refresh_outputs()

    def refresh_outputs(self):
        C = M.card_event_context(self.item, self.card_event) if self.card_event else M._Ctx(self.owner_kind, self.item)
        lines, errs = B.compile_blocks(self.blocks, self.project, C, "", allow_event=self.allow_event)
        code = "\n".join(lines)
        if self.code.get("1.0", "end-1c") != code:
            view = self.code.yview()
            self.code.configure(state="normal")
            self.code.delete("1.0", "end")
            self.code.insert("1.0", code)
            self.code.configure(state="disabled")
            self.code.yview_moveto(view[0])
        self.err.configure(text="\n".join("⚠ " + x for x in dict.fromkeys(errs)))
        if self.auto.get():
            for t, lang in ((self.desc_ko, "ko"), (self.desc_en, "en"), (self.desc_zh, "zh")):
                t.set_source(B.describe(self.blocks, self.project, "power" if self.owner_kind == "summon" else self.owner_kind, lang))

    def ok(self):
        C = M.card_event_context(self.item, self.card_event) if self.card_event else M._Ctx(self.owner_kind, self.item)
        lines, errs = B.compile_blocks(self.blocks, self.project, C, "", allow_event=self.allow_event)
        if errs and not messagebox.askyesno(TITLE, "블록에 문제가 있습니다:\n\n" + "\n".join(dict.fromkeys(errs)) +
                                            "\n\n그래도 저장할까요?", parent=self):
            return
        active_rules = {}
        known_rules = list(self.project.get("call_mappings") or []) + self.pending_call_mappings
        for block in B.walk(self.blocks):
            signature = block.get("mapped_signature")
            if not signature:
                continue
            rule = copy.deepcopy(block.get("mapped_rule") or next(
                (r for r in reversed(known_rules) if isinstance(r, dict) and r.get("signature") == signature and
                 r.get("op") == block.get("op")), None))
            if not rule:
                continue
            for field, binding in (rule.get("bindings") or {}).items():
                if field not in (block.get("args") or {}):
                    continue
                current = copy.deepcopy(block["args"][field])
                if binding.get("kind") == "arg" and current == binding.get("initial_value"):
                    binding.pop("initial_value", None)
                else:
                    rule["bindings"][field] = {"kind": "fixed", "value": current}
            active_rules[signature] = rule
        if active_rules:
            rules = self.project.setdefault("call_mappings", [])
            if not isinstance(rules, list):
                rules = self.project["call_mappings"] = []
            for rule in active_rules.values():
                rules[:] = [old for old in rules if not isinstance(old, dict) or old.get("signature") != rule.get("signature")]
                rules.append(rule)
        self.result = {"blocks": self.blocks, "code": "\n".join(lines), "auto_text": bool(self.auto.get()),
                       "upgraded_text": {lang: field.source().strip() for lang, field in self.upgraded_desc.items()},
                       "text_ko": self.desc_ko.source().strip(),
                       "text_en": self.desc_en.source().strip(),
                       "text_zh": self.desc_zh.source().strip()}
        self.destroy()

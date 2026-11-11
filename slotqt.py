"""값 고르기 · 조건 고르기 창 (Qt 版). Tk 의 blockui.SlotDialog 와 같은 종류 목록·기본값·칸을 쓴다.

editor 는 project, owner_kind, item, allow_event (그 밖에 condition_scope) 를 가진 물건이면 된다 (블록 편집기가 넘긴다).
"""
import copy

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
                               QListWidget, QPushButton, QVBoxLayout, QWidget)

import blockcode as B
import blockhelp as BH
import gimmick as G
import gimmickrules as GR
import modgen as M
import pets as PT
import qtkit as Q

CONDITION_SCOPE_DEFAULT = ""


def _first_pet(project):
    pets = PT.pets(project)
    return pets[0]["id"] if pets else ""


def _plain(text):
    return GR.plain(text)


class SlotDialogQt(QDialog):
    def __init__(self, parent, editor, kind, current):
        super().__init__(parent)
        self.editor, self.kind = editor, kind
        self.condition_scope = (current or {}).get("scope", getattr(editor, "condition_scope", CONDITION_SCOPE_DEFAULT)) \
            if isinstance(current, dict) else getattr(editor, "condition_scope", CONDITION_SCOPE_DEFAULT)
        self.setWindowTitle("값 고르기" if kind == "value" else "조건 고르기")
        self.result = None
        self.data = copy.deepcopy(current) if isinstance(current, dict) else (
            {"t": "num", "v": 0} if kind == "value" else {"t": "chance", "pct": {"t": "num", "v": 50}})
        root = QVBoxLayout(self)
        types = B.VALUE_TYPES if kind == "value" else B.COND_TYPES
        owner = editor.owner_kind
        if kind == "value" and owner not in ("power", "summon"):
            types = [t for t in types if t[0] != "amount"]
        if kind == "value" and not getattr(editor, "allow_event", False):
            types = [t for t in types if t[0] != "event"]
        if kind == "value" and owner != "orb":
            types = [t for t in types if t[0] not in ("orb_passive", "orb_evoke")]
        if kind == "value" and owner != "card":
            types = [t for t in types if t[0] not in ("star_x", "energy_x")]
        item = getattr(editor, "item", None) or {}
        if owner == "card" and item.get("clone"):
            # 가져온 효과 칸: 원본 변수 / 직접 수식을 그대로 쓸 수 있다
            head = [("dynvar", "가져온 카드의 원래 수치 (강화 포함)")] if kind == "value" and item.get("raw_vars") else []
            types = head + [("src", "직접 수식 입력" if kind == "value" else "직접 조건 입력")] + list(types)
        row = QHBoxLayout()
        row.addWidget(QLabel("종류"))
        self.type = QComboBox()
        for value, text in types:
            self.type.addItem(text, value)
        index = self.type.findData(self.data.get("t"))
        self.type.setCurrentIndex(index if index >= 0 else 0)
        self.type.currentIndexChanged.connect(lambda _i: self._type_changed(self.type.currentData()))
        self.type.setToolTip(BH.slot_help(self.kind, self.data.get("t")))
        row.addWidget(self.type, 1)
        root.addLayout(row)
        self.fields = _Fields()
        root.addWidget(self.fields)
        self.preview = QLabel("")
        self.preview.setWordWrap(True)
        self.preview.setStyleSheet(f"color: {Q.C['secondary']};")
        root.addWidget(self.preview)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.ok)
        buttons.rejected.connect(self.reject)
        if kind == "cond":
            extra = QHBoxLayout()
            for op, label in (("and", "그리고 조건 추가"), ("or", "또는 조건 추가")):
                button = QPushButton(label)
                button.clicked.connect(lambda _=False, o=op: self.append_clause(o))
                extra.addWidget(button)
            extra.addStretch(1)
            root.addLayout(extra)
        root.addWidget(buttons)
        self._build()
        self.resize(560, 360)

    # ---- 칸 도우미 ----
    def _grid(self):
        return self.fields.grid

    def _clear(self):
        while self._grid().count():
            item = self._grid().takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()

    def _row(self, r, label, widget):
        self._grid().addWidget(QLabel(label), r, 0)
        self._grid().addWidget(widget, r, 1)

    def _note(self, r, text):
        note = QLabel(text)
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Q.C['muted']};")
        self._grid().addWidget(note, r, 0, 1, 2)

    def _combo(self, r, label, key, options):
        box = QComboBox()
        for value, text in options:
            box.addItem(text, value)
        current = self.data.get(key)
        index = box.findData(current)
        if index < 0 and current is not None:
            box.addItem(f"(없는 항목: {current})", current)
            index = box.count() - 1
        box.setCurrentIndex(max(0, index))
        box.currentIndexChanged.connect(lambda _i, b=box, k=key: (self.data.__setitem__(k, b.currentData()), self._update_preview()))
        self._row(r, label, box)

    def _num(self, r, label, key, default=0):
        edit = QLineEdit(str(self.data.get(key, default)))

        def upd(text, k=key):
            text = text.strip()
            try:
                self.data[k] = float(text) if "." in text else int(text or 0)
            except ValueError:
                return
            self._update_preview()
        edit.textChanged.connect(upd)
        self._row(r, label, edit)

    def _text(self, r, label, key, default="a"):
        edit = QLineEdit(str(self.data.get(key, "")))

        def upd(text, k=key):
            self.data[k] = text.strip() or default
            self._update_preview()
        edit.textChanged.connect(upd)
        self._row(r, label, edit)

    def _slot(self, r, label, key, kind):
        button = QPushButton("")

        def refresh():
            lab = B.value_label(self.data.get(key), self.editor.project, card=self.editor.owner_kind == "card") \
                if kind == "value" else B.cond_label(self.data.get(key), self.editor.project, card=self.editor.owner_kind == "card")
            button.setText(_plain(lab) + "  ✎")

        def edit():
            dialog = SlotDialogQt(self, self.editor, kind, self.data.get(key))
            if dialog.exec() and dialog.result is not None:
                self.data[key] = dialog.result
                refresh()
                self._update_preview()
        button.clicked.connect(lambda _=False: edit())
        refresh()
        self._row(r, label, button)

    # ---- 종류별 칸 ----
    def _build(self):
        self._clear()
        d, t, ed = self.data, self.data.get("t"), self.editor
        who_opts = list(B.who_options(ed.owner_kind, multi=False))
        scope = self.condition_scope
        if t == "group":
            self._combo(0, "조건 연결", "mode", [("all", "모든 조건 만족 (그리고)"), ("any", "하나 이상 만족 (또는)")])
            items = d.setdefault("items", [])
            listing = QListWidget()
            for item in items:
                listing.addItem(_plain(B.cond_label(item, ed.project, card=ed.owner_kind == "card")))
            self._row(1, "조건 목록", listing)
            actions = QHBoxLayout()
            add = QPushButton("+ 조건 추가")
            edit = QPushButton("수정")
            remove = QPushButton("삭제")
            initial = ({"t": "card_is", "card": "picked", "filter": "Attack"} if scope == "card"
                       else {"t": "has", "who": "it" if scope == "creature" else "self", "power": "Weak"})

            def add_item():
                dialog = SlotDialogQt(self, ed, "cond", initial)
                if dialog.exec() and dialog.result is not None:
                    items.append(dialog.result)
                    self._build()

            def edit_item():
                row = listing.currentRow()
                if row < 0:
                    return
                dialog = SlotDialogQt(self, ed, "cond", items[row])
                if dialog.exec() and dialog.result is not None:
                    items[row] = dialog.result
                    self._build()

            def remove_item():
                row = listing.currentRow()
                if row >= 0:
                    del items[row]
                    self._build()
            add.clicked.connect(lambda _=False: add_item())
            edit.clicked.connect(lambda _=False: edit_item())
            remove.clicked.connect(lambda _=False: remove_item())
            listing.itemDoubleClicked.connect(lambda _it: edit_item())
            for b in (add, edit, remove):
                actions.addWidget(b)
            actions.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(actions)
            self._grid().addWidget(wrap, 2, 0, 1, 2)
        elif t == "hp_percent":
            self._combo(0, "누구의", "who", who_opts)
            self._combo(1, "비교", "op", B.CMP_OPS)
            self._slot(2, "최대 체력 대비 (%)", "value", "value")
        elif t in ("pile_count", "card_identity"):
            cards = [("", "종류·태그 조건으로 찾기")] + [(c["id"], f"{c.get('name_ko') or c['id']} ({c['id']})")
                                                       for c in ed.project.get("cards", [])]
            self._combo(0, "지정 카드", "card_id", cards)
            if t == "pile_count":
                self._combo(1, "누구의", "who", who_opts)
                self._combo(2, "어느 곳", "pile", [("Deck", "전체 덱 (전투 전 원본)")] + B.PILES)
                self._combo(3, "지정 카드를 비웠을 때 조건", "filter", B.card_is_filters(ed.project))
                self._combo(4, "비교", "op", B.CMP_OPS)
                self._slot(5, "장수", "count", "value")
        elif t == "src":
            self._text(0, "직접 수식", "code", default="")
            self._note(1, "가져온 효과에 쓰인 이름 (t, Me, DynamicVars[\"V0\"].IntValue 등)을 그대로 쓸 수 있습니다.")
        elif t == "dynvar":
            raw = (ed.item or {}).get("raw_vars", [])
            self._combo(0, "변수", "name", [(x["name"], x["name"]) for x in raw])
            self._note(1, "같은 변수를 쓰는 다른 칸·카드 설명의 숫자도 함께 바뀝니다.")
            current = next((x for x in raw if x["name"] == d.get("name")), None)
            if current is not None:
                for r, (field, label) in enumerate((("value", "수치 (카드 전체에 적용)"), ("upgrade", "강화 시 +")), 2):
                    edit = QLineEdit(str(current.get(field, 0) or 0))

                    def upd(text, rv=current, f=field):
                        try:
                            rv[f] = int(text)
                        except ValueError:
                            try:
                                rv[f] = float(text)
                            except ValueError:
                                return
                        self._update_preview()
                    edit.textChanged.connect(upd)
                    self._row(r, label, edit)
        elif t == "num":
            self._num(0, "수치", "v")
            if ed.owner_kind == "card":
                self._num(1, "강화 시 +", "up")
        elif t == "stack":
            self._combo(0, "누구의", "who", who_opts)
            self._combo(1, "파워", "power", M.power_options(ed.project))
        elif t == "stat":
            self._combo(0, "누구의", "who", who_opts)
            self._combo(1, "무엇", "stat", B.STATS)
        elif t == "count":
            self._combo(0, "무엇", "what", B.COUNTS)
        elif t == "rand":
            self._slot(0, "최소", "min", "value")
            self._slot(1, "최대", "max", "value")
        elif t == "var":
            self._text(0, "변수 이름", "name")
        elif t == "op":
            self._slot(0, "값 A", "a", "value")
            self._combo(1, "계산", "op", B.ARITH)
            self._slot(2, "값 B", "b", "value")
        elif t == "cmp":
            self._slot(0, "값 A", "a", "value")
            self._combo(1, "비교", "op", B.CMP_OPS)
            self._slot(2, "값 B", "b", "value")
        elif t == "chance":
            self._slot(0, "확률 (%)", "pct", "value")
        elif t == "has":
            self._combo(0, "누가", "who", who_opts)
            self._combo(1, "파워", "power", M.power_options(ed.project))
        elif t in ("and", "or"):
            self._slot(0, "조건 A", "a", "cond")
            self._slot(1, "조건 B", "b", "cond")
        elif t == "not":
            self._slot(0, "조건", "a", "cond")
        elif t == "played":
            self._combo(0, "언제", "scope", B.PLAYED_SCOPES)
            self._combo(1, "어떤 카드", "filter", G.card_filters(ed.project))
            self._note(2, "지금 쓰고 있는 카드는 세지 않습니다 (연계: '이번 턴 격투 카드 수 ≥ 2').")
        elif t == "orbs":
            self._combo(0, "무엇", "what", B.ORB_COUNTS)
            self._combo(1, "어떤 구체 (구체 수일 때)", "orb", [("", "모든 구체")] + G.orb_options(ed.project))
        elif t in ("pet", "pet_alive"):
            opts = [(p["id"], p.get("name_ko") or p["id"]) for p in PT.pets(ed.project)] or \
                [("", "('기믹' 탭에서 동료를 만드세요)")]
            self._combo(0, "동료", "pet", opts)
            if t == "pet":
                self._combo(1, "무엇", "what", [("hp", "현재 체력"), ("maxhp", "최대 체력")])
        elif t == "card_is":
            d["card"], d["card_n"] = B.pos_n(d.get("card", "this"), d.get("card_n"))
            self._combo(0, "어느 카드", "card", B.CARD_REFS)
            self._combo(1, "무엇", "filter", B.card_is_filters(ed.project))
            self._num(2, "N번째 (뽑을 더미 · 1=맨 위, -1=맨 아래)", "card_n")
        elif t in ("card_state", "card_var_has"):
            d["card"], d["card_n"] = B.pos_n(d.get("card", "this"), d.get("card_n"))
            self._combo(0, "어느 카드", "card", B.CARD_REFS)
            self._text(1, "상태 이름", "key", default="count")
            self._num(2, "N번째 (뽑을 더미 · 1=맨 위, -1=맨 아래)", "card_n")
            self._note(3, "같은 카드가 여러 장이어도 한 장마다 따로 저장됩니다 (처음엔 0).")
        elif t == "osty":
            self._combo(0, "무엇", "what", B.OSTY_STATS)
            self._note(1, "골골이가 없으면 0입니다.")
        elif t in ("energy", "amount", "round", "summons", "event", "orb_passive", "orb_evoke", "stars", "star_x",
                   "energy_x", "osty_alive"):
            notes = {"amount": "소환수에서는 '단계', 파워에서는 '스택 수'입니다.",
                     "event": "'넘칠 때'에는 넘친 양, '기준치 도달 시'에는 그때의 스택 수입니다."}
            self._note(0, notes.get(t, "(설정할 것 없음)"))
        self._update_preview()

    def _type_changed(self, t):
        old = self.data
        self.data = {"t": t}
        scope = self.condition_scope
        owner, project = self.editor.owner_kind, self.editor.project
        pet = _first_pet(project)
        defaults = {
            "group": {"mode": "all", "items": [old] if old and old.get("t") != "group" else [], "scope": scope},
            "hp_percent": {"who": "it" if scope == "creature" else "self", "op": "<=", "value": {"t": "num", "v": 50}},
            "pile_count": {"who": "it" if scope == "creature" else "self", "pile": "Deck", "filter": "Any", "card_id": "",
                           "op": ">=", "count": {"t": "num", "v": 1}},
            "card_identity": {"card_id": next((x["id"] for x in project.get("cards", [])), "")},
            "num": {"v": 0}, "stack": {"who": "self", "power": "Strength"}, "stat": {"who": "self", "stat": "hp"},
            "count": {"what": "hand"}, "rand": {"min": {"t": "num", "v": 1}, "max": {"t": "num", "v": 3}},
            "var": {"name": "a"}, "played": {"scope": "turn", "filter": "Any"},
            "card_state": {"card": "this" if owner == "card" else "picked", "key": "count"},
            "card_var_has": {"card": "this" if owner == "card" else "picked", "key": "count"},
            "card_is": {"card": "picked" if scope == "card" else "this" if owner == "card" else "picked",
                        "filter": "kw:Retain"},
            "orbs": {"what": "count", "orb": ""}, "osty": {"what": "hp"},
            "pet": {"pet": pet, "what": "hp"}, "pet_alive": {"pet": pet},
            "op": {"op": "+", "a": old if self.kind == "value" else {"t": "num", "v": 0}, "b": {"t": "num", "v": 1}},
            "cmp": {"a": {"t": "stat", "who": "self", "stat": "hp"}, "op": "<=", "b": {"t": "num", "v": 30}},
            "chance": {"pct": {"t": "num", "v": 50}},
            "has": {"who": "it" if scope == "creature" else "self", "power": "Weak"},
            "and": {"a": old, "b": {"t": "chance", "pct": {"t": "num", "v": 50}}},
            "or": {"a": old, "b": {"t": "chance", "pct": {"t": "num", "v": 50}}},
            "not": {"a": old},
            "src": {"code": old.get("code", "") if old.get("t") == "src" else ""},
            "dynvar": {"name": next((v["name"] for v in (getattr(self.editor, "item", None) or {}).get("raw_vars", [])), ""),
                       "prop": "BaseValue"},
        }
        self.data.update(copy.deepcopy(defaults.get(t, {})))
        self._build()

    def append_clause(self, op):
        dialog = SlotDialogQt(self, self.editor, "cond", None)
        if dialog.exec() and dialog.result:
            self.data = {"t": op, "a": self.data, "b": dialog.result}
            index = self.type.findData(op)
            self.type.blockSignals(True)
            self.type.setCurrentIndex(index)
            self.type.blockSignals(False)
            self._build()

    def _update_preview(self):
        lab = B.value_label(self.data, self.editor.project, card=self.editor.owner_kind == "card") \
            if self.kind == "value" else B.cond_label(self.data, self.editor.project, card=self.editor.owner_kind == "card")
        self.preview.setText("→ " + _plain(lab))

    def ok(self):
        self.result = self.data
        self.accept()


class _Fields(QWidget):
    """칸을 격자로 담는 상자 (SlotDialogQt 의 칸 영역)."""

    def __init__(self):
        super().__init__()
        self.grid = QGridLayout(self)
        self.grid.setColumnStretch(1, 1)

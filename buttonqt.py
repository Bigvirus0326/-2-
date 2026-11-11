"""'전투 버튼' 탭의 Qt 版: 버튼 목록 · 버튼 편집 칸 · 전투 시험장 (Tk 의 ButtonDesigner 와 같은 규칙).

값·조건 칸과 '눌렀을 때 블록' 편집은 블록 편집기가 필요해서 아직 Tk 앱에서 합니다 (칸은 보이지만 누를 수 없다).
"""
import copy
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QColorDialog, QComboBox, QGridLayout, QHBoxLayout, QLineEdit,
                               QListWidget, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QSplitter,
                               QVBoxLayout, QWidget)

import blockcode as B
import fxbtn as FX
import fxrules as R
import gamescene as GS
import gimmickrules as GR
from fxqt import _Stage, _ask, _bold, _button, _dspin, _pil_pixmap, _spin
from formqt import label
from types import SimpleNamespace
from blockqt import edit_blocks
from slotqt import SlotDialogQt
from itemtabqt import unique_id
import qtkit as Q

CHOICE_LANGS = (("zh", "简体中文"), ("en", "English"), ("ko", "한국어"))


def _slot_button(designer, key):
    button = QPushButton("")
    button.clicked.connect(lambda _=False: designer.edit_slot_key(key))
    return button


def _set_choice(box, value):
    """콤보 상자를 값에 맞춘다. 목록에 없는 값(지워진 항목 등)은 '(없는 항목)'으로 보이게 남긴다."""
    index = box.findData(value)
    if index < 0:
        box.addItem(f"(없는 항목: {value})", value)
        index = box.count() - 1
    box.blockSignals(True)
    box.setCurrentIndex(index)
    box.blockSignals(False)


class ButtonDesignerQt(QWidget):
    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.tab = tab
        self.z = tab.z
        self.cur = None
        self._loading = False
        self._busy = False
        self.hover = False
        self._drag = None
        self.fx_play = []
        self.popups = []
        self.st = {}
        self._base = None
        self._base_key = None
        self.v = {}
        self.lang = "ko"
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._anim)

        split = QSplitter(Qt.Orientation.Horizontal)
        root = QHBoxLayout(self)
        root.addWidget(split)

        # ---- 왼쪽: 버튼 목록 ----
        left = QWidget()
        lc = QVBoxLayout(left)
        lc.addWidget(_bold("버튼"))
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lst.currentRowChanged.connect(self._row)
        lc.addWidget(self.lst, 1)
        bar = QHBoxLayout()
        bar.addWidget(_button("새로", self.add))
        bar.addWidget(_button("삭제", self.delete))
        lc.addLayout(bar)
        split.addWidget(left)

        # ---- 가운데: 버튼 편집 칸 ----
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        self.form = QGridLayout(body)
        self.form.setColumnStretch(1, 1)
        self._build_form(self.form)
        scroll.setWidget(body)
        split.addWidget(scroll)

        # ---- 오른쪽: 전투 시험장 ----
        right = QWidget()
        rc = QVBoxLayout(right)
        top = QHBoxLayout()
        top.addWidget(_bold("시험장 — 게임 전투 화면 그대로. 버튼을 눌러 보세요"))
        top.addStretch(1)
        top.addWidget(label("모니터 화면 비율"))
        self.aspect = QComboBox()
        for name, w, h in GS.ASPECTS:
            self.aspect.addItem(f"{name}  (게임 화면 {w}×{h})")
        self.aspect.currentIndexChanged.connect(lambda _i: self._aspect_changed())
        top.addWidget(self.aspect)
        for val, text in CHOICE_LANGS:
            button = QRadioButton(text)
            button.setChecked(val == "ko")
            button.toggled.connect(lambda on, v=val: on and self.set_lang(v))
            top.addWidget(button)
        rc.addLayout(top)
        self.vw, self.vh = R.W_GAME, R.H_GAME
        self.stage_w, self.stage_h = int(R.W_GAME * 0.4 * self.z), int(R.H_GAME * 0.4 * self.z)
        self.stage = _Stage(self)
        self.stage.setFixedSize(self.stage_w, self.stage_h)
        self.stage.setStyleSheet(f"background: {Q.C['stage']};")
        rc.addWidget(self.stage, 0, Qt.AlignmentFlag.AlignHCenter)
        self.ds = min(self.stage_w / self.vw, self.stage_h / self.vh)
        stf = QHBoxLayout()
        self.e_box = _spin(3, 0, 99)
        self.r_box = _spin(5, 0, 99)
        self.p_box = _spin(0, 0, 99)
        self.s_box = _spin(0, 0, 99)
        self.res_lbl = label("자원")
        stf.addWidget(label("에너지"))
        stf.addWidget(self.e_box)
        stf.addWidget(self.res_lbl)
        stf.addWidget(self.r_box)
        stf.addWidget(label("이번 턴 사용한 카드"))
        stf.addWidget(self.p_box)
        stf.addWidget(label("별"))
        stf.addWidget(self.s_box)
        for box in (self.e_box, self.r_box, self.p_box, self.s_box):
            box.valueChanged.connect(lambda _v: self._vars_changed())
        stf.addWidget(_button("⏭ 턴 넘기기", self.next_turn))
        stf.addWidget(_button("↺ 전투 다시", self.reset_sim))
        stf.addStretch(1)
        rc.addLayout(stf)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setFixedHeight(120)
        rc.addWidget(self.log)
        split.addWidget(right)
        split.setStretchFactor(2, 1)
        split.setSizes([240, 380, 640])
        self.load()

    # ---- 칸 ----
    def _build_form(self, g):
        r = 0

        def row(text, widget, span=3):
            nonlocal r
            g.addWidget(label(text), r, 0)
            g.addWidget(widget, r, 1, 1, span)
            r += 1

        def text_field(key, text):
            edit = QLineEdit()
            edit.textChanged.connect(self.changed)
            self.v[key] = ("str", edit)
            row(text, edit)

        for key, text in (("id", "ID"), ("label_ko", "이름 (한국어)"), ("label_en", "이름 (영어)"),
                          ("label_zh", "이름 (중국어 간체, 비우면 영어)"), ("sub_ko", "둘째 줄 (한국어, # = 표시 값)"),
                          ("sub_en", "둘째 줄 (영어)"), ("sub_zh", "둘째 줄 (중국어 간체)")):
            text_field(key, text)
        self.val_btn = _slot_button(self, "value")
        row("표시 값 (#)", self.val_btn)
        for key, text in (("tip_ko", "툴팁 (한국어)"), ("tip_en", "툴팁 (영어)"), ("tip_zh", "툴팁 (중국어 간체)")):
            text_field(key, text)
        for key, text in (("bg", "바탕색"), ("border", "테두리색"), ("text", "글자색")):
            edit = QLineEdit()
            edit.setMaximumWidth(120)
            edit.textChanged.connect(self.changed)
            self.v[key] = ("str", edit)
            holder = QHBoxLayout()
            holder.addWidget(edit)
            holder.addWidget(_button("고르기", lambda _=False, k=key: self.pick(k)))
            holder.addStretch(1)
            wrap = QWidget()
            wrap.setLayout(holder)
            row(text, wrap)
        self.anchor = QComboBox()
        self.anchor.currentIndexChanged.connect(lambda _i: self.changed())
        row("위치 기준", self.anchor)
        sizes = QHBoxLayout()
        for key, text, default in (("w", "너비", 190), ("h", "높이", 70)):
            sizes.addWidget(label(text))
            box = _spin(default, -9999, 9999)
            box.setMinimum(20)
            box.setMaximum(1200)
            box.valueChanged.connect(lambda _v: self.changed())
            self.v[key] = ("int", box)
            sizes.addWidget(box)
        sizes.addWidget(label("(기준 1920×1080 화면에서의 px)"))
        sizes.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(sizes)
        g.addWidget(wrap, r, 0, 1, 4)
        r += 1
        self.pos_screen = QWidget()
        ps = QHBoxLayout(self.pos_screen)
        ps.setContentsMargins(0, 0, 0, 0)
        for key, text, default in (("rx", "가로 위치 %", 50), ("ry", "세로 위치 %", 30)):
            ps.addWidget(label(text))
            box = _dspin(default, 0, 100, 0.5)
            box.valueChanged.connect(lambda _v: self.changed())
            self.v[key] = ("float", box)
            ps.addWidget(box)
        ps.addWidget(label("(버튼 가운데가 놓일 화면 위치)"))
        ps.addStretch(1)
        g.addWidget(self.pos_screen, r, 0, 1, 4)
        r += 1
        self.pos_creature = QWidget()
        pc = QHBoxLayout(self.pos_creature)
        pc.setContentsMargins(0, 0, 0, 0)
        for key, text, default in (("x", "위치 X", -95), ("y", "위치 Y", -470)):
            pc.addWidget(label(text))
            box = _spin(default, -1200, 1200)
            box.valueChanged.connect(lambda _v: self.changed())
            self.v[key] = ("int", box)
            pc.addWidget(box)
        pc.addWidget(label("(캐릭터 발밑 기준 px, 기본 -95, -470 = 머리 위)"))
        pc.addStretch(1)
        g.addWidget(self.pos_creature, r, 0, 1, 4)
        r += 1
        g.addWidget(label("오른쪽 시험장에서 Ctrl+끌기로 옮길 수 있습니다."), r, 0, 1, 4)
        r += 1
        costs = QHBoxLayout()
        for key, text in (("energy_cost", "에너지 비용"), ("per_turn", "턴당 횟수 (0 = 무제한)"), ("per_combat", "전투당 횟수")):
            costs.addWidget(label(text))
            box = _spin(0, 0, 99)
            box.valueChanged.connect(lambda _v: self.changed())
            self.v[key] = ("int", box)
            costs.addWidget(box)
        costs.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(costs)
        g.addWidget(wrap, r, 0, 1, 4)
        r += 1
        self.res = QComboBox()
        self.res.currentIndexChanged.connect(lambda _i: self.changed())
        g.addWidget(label("자원 비용 (파워)"), r, 0)
        g.addWidget(self.res, r, 1)
        self.res_cost = _spin(0, 0, 99)
        self.res_cost.valueChanged.connect(lambda _v: self.changed())
        self.v["res_cost"] = ("int", self.res_cost)
        g.addWidget(self.res_cost, r, 2)
        r += 1
        self.cond_btn = _slot_button(self, "cond")
        row("쓸 수 있는 조건", self.cond_btn)
        self.fx = QComboBox()
        self.fx.currentIndexChanged.connect(lambda _i: self.changed())
        row("누를 때 이펙트", self.fx)
        self.relic = QComboBox()
        self.relic.currentIndexChanged.connect(lambda _i: self.changed())
        row("켜는 유물", self.relic)
        g.addWidget(label("이 유물을 가지고 전투를 시작하면 버튼이 생깁니다 (시작 유물 권장). "
                          "아니면 카드·파워 블록 '버튼 켜기'로 켭니다."), r, 0, 1, 4)
        r += 1
        self.block_btn = QPushButton("🧩 눌렀을 때 실행할 블록…")
        self.block_btn.clicked.connect(lambda _=False: self.edit_press_blocks())
        g.addWidget(self.block_btn, r, 0, 1, 2)
        r += 1
        self.desc = label("")
        self.desc.setStyleSheet(f"color: {Q.C['secondary']};")
        g.addWidget(self.desc, r, 0, 1, 4)
        g.setRowStretch(r + 1, 1)

    def edit_press_blocks(self):
        """눌렀을 때 실행할 블록 (Tk 의 edit_blocks 와 같다)."""
        if self.b is None:
            return
        b = self.b
        result = edit_blocks(self, self.tab.project, "button", b, b.get("blocks") or [],
                             where=f"버튼 '{b.get('label_ko')}'을 눌렀을 때")
        if result is not None:
            b["blocks"] = result["blocks"]
            self.tab.dirty()
            self.refresh_labels()

    def edit_slot_key(self, key):
        """표시 값 또는 쓸 수 있는 조건 하나를 고친다."""
        if self.b is None:
            return
        b = self.b
        context = SimpleNamespace(project=self.tab.project, owner_kind="button", item=b, allow_event=False)
        dialog = SlotDialogQt(self, context, "value" if key == "value" else "cond", b.get(key))
        if dialog.exec() and dialog.result is not None:
            b[key] = dialog.result
            self.tab.dirty()
            self.refresh_labels()

    # ---- 데이터 ----
    @property
    def items(self):
        return self.tab.g["buttons"]

    @property
    def b(self):
        return self.items[self.cur] if self.cur is not None and self.cur < len(self.items) else None

    def load(self):
        import modgen as Mg
        self.lst.blockSignals(True)
        self.lst.clear()
        for b in self.items:
            self.lst.addItem(f"🔘 {b.get('label_ko') or '?'}  ({b['id']})")
        self.lst.blockSignals(False)
        self._fill(self.res, [("", "없음")] + Mg.power_options(self.tab.project))
        self._fill(self.fx, [("", "없음")] + [(e["id"], e.get("name") or e["id"]) for e in FX.effects(self.tab.project)])
        self._fill(self.relic, [("", "없음 (블록으로 켜기)")] +
                   [(r["id"], r.get("name_ko") or r["id"]) for r in self.tab.project.get("relics", [])])
        if self.items:
            i = min(self.cur or 0, len(self.items) - 1)
            self.lst.setCurrentRow(i)
            self.select(i)
        else:
            self.cur = None
            self.draw()

    @staticmethod
    def _fill(box, options):
        box.blockSignals(True)
        box.clear()
        for value, text in options:
            box.addItem(text, value)
        box.blockSignals(False)

    def _row(self, row):
        if row >= 0 and row != self.cur:
            self.select(row)

    def select(self, i):
        self.cur = i
        b = self.b
        self._loading = True
        try:
            for k, (typ, w) in self.v.items():
                val = b.get(k, "")
                if typ == "str":
                    w.setText(str(val))
                elif typ == "int":
                    w.setValue(int(val) if isinstance(val, (int, float)) else 0)
                elif typ == "float":
                    w.setValue(float(val) if isinstance(val, (int, float)) else 0.0)
            _set_choice(self.res, b.get("res_power", ""))
            _set_choice(self.fx, b.get("fx", ""))
            _set_choice(self.relic, b.get("auto_relic", ""))
            self._fill(self.anchor, FX.anchor_options(self.tab.project))
            _set_choice(self.anchor, b.get("anchor", "creature"))
        finally:
            self._loading = False
        self._anchor_ui()
        self.refresh_labels()
        self.reset_sim()

    def changed(self, *_):
        if self._loading or self.b is None:
            return
        b = self.b
        old = b["id"]
        for k, (typ, w) in self.v.items():
            if typ == "str":
                b[k] = w.text().strip()
            elif typ == "int":
                b[k] = int(w.value())
            elif typ == "float":
                b[k] = round(max(0.0, min(100.0, float(w.value()))), 2)
        b["anchor"] = self.anchor.currentData() or "creature"
        b["res_power"] = self.res.currentData() or ""
        b["fx"] = self.fx.currentData() or ""
        b["auto_relic"] = self.relic.currentData() or ""
        if b["id"] != old and b["id"]:
            R._rename(self.tab.project, "button", old, b["id"])
        self.lst.blockSignals(True)
        item = self.lst.item(self.cur)
        if item is not None:
            item.setText(f"🔘 {b.get('label_ko') or '?'}  ({b['id']})")
        self.lst.blockSignals(False)
        self.tab.dirty()
        self._anchor_ui()
        self.refresh_labels()
        self.draw()

    def _anchor_ui(self):
        creature = self.anchor.currentData() != "screen"
        self.pos_creature.setVisible(creature)
        self.pos_screen.setVisible(not creature)

    def refresh_labels(self):
        b = self.b
        if b is None:
            return
        P = self.tab.project
        self.val_btn.setText((GR.plain(B.value_label(b["value"], P)) if isinstance(b.get("value"), dict) else "(없음)") + " ✎")
        self.cond_btn.setText((GR.plain(B.cond_label(b["cond"], P)) if isinstance(b.get("cond"), dict) else "(항상)") + " ✎")
        d = GR.plain(B.describe(b.get("blocks"), P, "power", "ko")) or "(블록 없음)"
        self.desc.setText("누르면: " + d)

    def set_lang(self, lang):
        self.lang = lang
        self.redraw_all()

    def add(self):
        self.items.append(FX.new_button(unique_id(self.tab.project, "new_button")))
        self.cur = len(self.items) - 1
        self.tab.dirty()
        self.load()

    def delete(self):
        if self.b is None:
            return
        if not _ask(self, f"버튼 '{self.b.get('label_ko')}'를 삭제할까요?"):
            return
        R._rename(self.tab.project, "button", self.b["id"], None)
        del self.items[self.cur]
        self.cur = max(0, self.cur - 1)
        self.tab.dirty()
        self.load()

    def pick(self, key):
        if self.b is None:
            return
        _typ, edit = self.v[key]
        chosen = QColorDialog.getColor(QColor(edit.text().strip() or "#ffffff"), self, "색 고르기")
        if chosen.isValid():
            edit.setText(chosen.name())

    # ---- 시험장 ----
    def _aspect_changed(self):
        _n, self.vw, self.vh = GS.ASPECTS[max(0, self.aspect.currentIndex())]
        self.ds = max(0.1, min(self.stage_w / self.vw, self.stage_h / self.vh))
        self._base_key = None
        self.fx_play, self.popups = [], []
        self.draw()

    def feet(self, enemy=False):
        return GS.view_pos(GS.ENEMY if enemy else GS.PLAYER, self.vw, self.vh)

    def redraw_all(self):
        self._base_key = None
        self.draw()

    def reset_sim(self):
        if not hasattr(self, "e_box"):
            return
        ch = self.tab.project.get("character") or {}
        hp = int(ch.get("hp", 75) or 75)
        self.st = {"hp": hp, "maxhp": hp, "block": 0, "ehp": 60, "emaxhp": 60, "eblock": 0, "energy": 3, "maxenergy": 3,
                   "stars": 0, "res": {}, "played": 0, "turn": 1, "intent": 9, "turn_uses": 0, "combat_uses": 0}
        self._busy = True
        try:
            self.e_box.setValue(3)
            self.p_box.setValue(0)
            self.s_box.setValue(0)
        finally:
            self._busy = False
        self._vars_changed()
        self.log.clear()
        b = self.b
        self.write("전투 시작 — 버튼이 켜졌습니다." + (f" (유물 '{b.get('auto_relic')}')" if b and b.get("auto_relic") else ""))
        self.fx_play, self.popups = [], []
        self.draw()

    def _vars_changed(self):
        if self._busy or not self.st:
            return
        b = self.b
        self.st["energy"] = max(0, int(self.e_box.value()))
        self.st["played"] = max(0, int(self.p_box.value()))
        self.st["stars"] = max(0, int(self.s_box.value()))
        self.st["res"] = {}
        if b and b.get("res_power"):
            self.st["res"][b["res_power"]] = max(0, int(self.r_box.value()))
            self.res_lbl.setText(GS._pname(self.tab.project, b["res_power"]))
        else:
            self.res_lbl.setText("자원 (없음)")
        self._base_key = None
        self.draw()

    def _push_vars(self):
        self._busy = True
        try:
            self.e_box.setValue(int(self.st["energy"]))
            self.s_box.setValue(int(self.st.get("stars", 0)))
            b = self.b
            if b and b.get("res_power"):
                self.r_box.setValue(int(self.st["res"].get(b["res_power"], 0)))
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
            self.p_box.setValue(0)
        finally:
            self._busy = False
        self._push_vars()
        self.write(f"— {st['turn']}턴: 적이 {dmg} 피해로 공격, 에너지 {st['energy']}, 방어도 초기화, 턴당 횟수 초기화 —")
        self._base_key = None
        self._anim()

    def write(self, s):
        self.log.appendPlainText(s)

    def rect(self):
        """버튼 자리 (게임 화면 좌표). 게임 코드와 같은 계산."""
        b = self.b
        w, h = float(b.get("w", 190)), float(b.get("h", 70))
        if b.get("anchor", "creature") == "screen":
            s = GS.ui_scale(self.vw, self.vh)
            cx, cy = self.vw * float(b.get("rx", 50)) / 100, self.vh * float(b.get("ry", 30)) / 100
            return cx - w * s / 2, cy - h * s / 2, cx + w * s / 2, cy + h * s / 2
        feet = self.anchor_feet()
        if feet is None:             # 따라갈 동료가 없음: 게임처럼 숨김
            return -9999, -9999, -9999 + w, -9999 + h
        fx, fy = feet
        x, y = fx + float(b.get("x", -95)), fy + float(b.get("y", -470))
        return x, y, x + w, y + h

    def anchor_feet(self):
        a = str((self.b or {}).get("anchor", "creature") or "creature")
        if a in ("enemy_each", "enemy_first", "enemy_last"):
            return self.feet(enemy=True) if (self.st or {}).get("ehp", 1) > 0 else None
        if a.startswith("pet:"):
            pets = list(((self.st or {}).get("pets") or {}).items())
            for i, (pid, (hp, _mx)) in enumerate(pets):
                if pid == a[4:] and hp > 0:
                    return GS.view_pos(GS.pet_feet(i), self.vw, self.vh)
            return None
        return self.feet()

    def value_text(self):
        b = self.b
        if b and isinstance(b.get("value"), dict):
            return str(int(GS.Sim(self.tab.project, copy.deepcopy(self.st), lambda _s: None).val(b["value"])))
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
            if not GS.Sim(self.tab.project, copy.deepcopy(st), lambda _s: None).cond(b["cond"]):
                return "쓸 수 있는 조건을 만족하지 않습니다."
        if st["hp"] <= 0:
            return "쓰러졌습니다 ('전투 다시')."
        return ""

    def _world(self, pos):
        return pos.x() / self.ds, pos.y() / self.ds

    def stage_move(self, e):
        if self.b is None:
            return
        if self._drag is not None:
            x, y = self._world(e.position())
            dx, dy = x - self._drag[0], y - self._drag[1]
            self._drag = (x, y)
            if self.b.get("anchor", "creature") == "screen":
                self.v["rx"][1].setValue(round(float(self.b.get("rx", 50)) + dx / self.vw * 100, 1))
                self.v["ry"][1].setValue(round(float(self.b.get("ry", 30)) + dy / self.vh * 100, 1))
            else:
                self.v["x"][1].setValue(int(float(self.b.get("x", 0)) + dx))
                self.v["y"][1].setValue(int(float(self.b.get("y", 0)) + dy))
            return
        x, y = self._world(e.position())
        x1, y1, x2, y2 = self.rect()
        hovered = x1 <= x <= x2 and y1 <= y <= y2
        if hovered != self.hover:
            self.hover = hovered
            self.draw()

    def stage_press(self, e):
        if self.b is None or e.button() != Qt.MouseButton.LeftButton:
            return
        x, y = self._world(e.position())
        x1, y1, x2, y2 = self.rect()
        if not (x1 <= x <= x2 and y1 <= y <= y2):
            return
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:     # Ctrl+끌기 = 위치 옮기기
            self._drag = (x, y)
            return
        self.press()

    def stage_release(self, _e):
        self._drag = None

    def stage_double(self, _e):
        pass

    def press(self):
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
        now = time.perf_counter()
        self.fx_play = [(f, o, t0) for f, o, t0 in self.fx_play if now - t0 <= FX.total_time(f) + 0.2]
        self.popups = [p for p in self.popups if now - p[2] <= 1.1]
        self.draw(now)
        if self.fx_play or self.popups:
            self._timer.start()
        else:
            self._timer.stop()

    def draw(self, now=None):
        from PIL import Image, ImageDraw
        a = R._assets()
        ds = self.ds
        size = (max(1, int(self.vw * ds)), max(1, int(self.vh * ds)))
        key = (repr(sorted((k, repr(v)) for k, v in self.st.items())), self.lang, size, id(a),
               repr(self.tab.project.get("character")))
        if key != self._base_key or self._base is None:
            if a is not None:
                base = GS.scene(a, self.tab.project, self.st or {"hp": 75, "maxhp": 75}, self.lang, vw=self.vw, vh=self.vh)
            else:
                base = Image.new("RGBA", (self.vw, self.vh), (24, 22, 34, 255))
                ImageDraw.Draw(base).text((40, 40), "게임 폴더를 정하면 실제 전투 화면으로 보입니다 (설정 → 게임 경로).",
                                          fill=(220, 220, 230, 255))
            self._base = base.resize(size, Image.BILINEAR)
            self._base_key = key
        img = self._base.copy()
        now = now or time.perf_counter()
        for f, feet, t0 in self.fx_play:
            img = FX.render(f, now - t0, size, feet, img=img, ss=1, zoom=ds)
        b = self.b
        reason = ""
        if b is not None and a is not None:
            reason = self.why_not()
            state = "disabled" if reason else ("hover" if self.hover else "normal")
            bi = GS.button_image(a, b, state, self.value_text(), self.lang)
            x1, y1, x2, y2 = self.rect()
            bs = (x2 - x1) / max(1.0, float(b.get("w", 190)))
            bi = bi.resize((max(1, int(bi.width * ds * bs)), max(1, int(bi.height * ds * bs))), Image.LANCZOS)
            img.alpha_composite(bi, (int((x1 - 2 * bs) * ds), int((y1 - 2 * bs) * ds)))
            tip_text = GS.btn_text(b, "tip", self.lang)
            if self.hover and tip_text:
                tip = GS.tip_image(a, GS.btn_text(b, "label", self.lang), tip_text, self.lang)
                if tip is not None:
                    tip = tip.resize((max(1, int(tip.width * ds)), max(1, int(tip.height * ds))), Image.LANCZOS)
                    img.alpha_composite(tip, (int((x2 + 12) * ds), int(y1 * ds)))
        self.last_frame = img                 # 시험용 (화면을 찍지 않고 결과 확인)
        pm = _pil_pixmap(img)
        canvas = QPainter(pm)
        try:
            if b is None:
                canvas.setPen(QColor("#dddddd"))
                canvas.drawText(20, 30, "왼쪽에서 '새로'를 눌러 버튼을 만드세요.")
            else:
                if reason:
                    x1, y1, x2, y2 = self.rect()
                    canvas.setPen(QColor("#ff9b9b"))
                    canvas.drawText(int((x1 + x2) / 2 * ds) - 160, int((y2 + 14) * ds), 320, 30,
                                    Qt.AlignmentFlag.AlignHCenter, reason)
                canvas.setPen(QColor("#dddddd"))
                canvas.drawText(8, size[1] - 6, "클릭 = 누르기 · Ctrl+끌기 = 위치 옮기기 · 캐릭터·몬스터 몸은 실루엣(게임은 Spine 애니메이션)")
        finally:
            canvas.end()
        self.stage.setPixmap(pm)

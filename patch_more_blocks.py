import io


def patch(path, pairs):
    s = io.open(path, encoding="utf-8").read()
    for old, new in pairs:
        assert s.count(old) == 1, (path, old[:70], s.count(old))
        s = s.replace(old, new)
    io.open(path, "w", encoding="utf-8").write(s)
    print("patched", path)


patch("itemtabqt.py", [
    ('''from clonepanelqt import ClonePanelQt\n''', '''from clonepanelqt import ClonePanelQt
from types import SimpleNamespace
from slotqt import SlotDialogQt\n'''),
    # 항목 공통: 블록 목록 편집 · 조건 칸 편집
    ('''    def _current_item(self):''', '''    def _editor_for(self, item):
        """칸 편집 창이 항목의 종류·이름을 알 수 있도록 넘기는 작은 물건."""
        return SimpleNamespace(project=self.project, owner_kind=self.kind, item=item, allow_event=False,
                               condition_scope="")

    def edit_block_list(self, key, where, **extra):
        """항목의 블록 목록(key)을 블록 편집 창으로 고친다."""
        from blockqt import edit_blocks
        if self.cur is None:
            return
        it = self.items[self.cur]
        result = edit_blocks(self, self.project, self.kind, it, it.get(key) or [], where=where, **extra)
        if result is not None:
            it[key] = result["blocks"]
            self._effects_changed()

    def _current_item(self):'''),
    # 파워: 넘칠 때 · 기준치 도달 블록 단추
    ('''        g.addWidget(_label("상시 효과"), 8, 0, Qt.AlignmentFlag.AlignTop)
        self.modifiers = ModifierListQt(lambda: self.project, self._notify)
        g.addWidget(self.modifiers, 8, 1, 1, 3)
        self._common(g, 9)''', '''        g.addWidget(_label("상시 효과"), 8, 0, Qt.AlignmentFlag.AlignTop)
        self.modifiers = ModifierListQt(lambda: self.project, self._notify)
        g.addWidget(self.modifiers, 8, 1, 1, 3)
        progress = QHBoxLayout()
        over = QPushButton("🧩 넘칠 때 블록…")
        over.clicked.connect(lambda _=False: self.edit_block_list(
            "overflow_blocks", "최대 스택을 넘칠 때 (넘친 만큼은 버려지고)", allow_event=True))
        reach = QPushButton("🧩 기준치 도달 시 블록…")
        reach.clicked.connect(lambda _=False: self.edit_block_list(
            "threshold_blocks", "기준치 이상이 될 때", allow_event=True))
        progress.addWidget(over)
        progress.addWidget(reach)
        progress.addStretch(1)
        wrap = QWidget()
        wrap.setLayout(progress)
        g.addWidget(wrap, 9, 1, 1, 3)
        self._common(g, 10)'''),
    # 카드: 사용 조건 · 금색 테두리 칸을 고친다
    ('''            button = _small_button("(없음) ✎", None)
            button.setEnabled(False)
            button.setToolTip("조건 편집기는 아직 Tk 앱에서 합니다.")
            self._cond_btns[key] = button''', '''            button = _small_button("(없음) ✎", lambda _=False, k=key: self.edit_cond(k))
            self._cond_btns[key] = button'''),
    ('''    def _cond_text(self, it, key):''', '''    def edit_cond(self, key):
        """사용 조건 · 금색 테두리 조건 하나를 고친다 (Tk 의 edit_cond 와 같다)."""
        if self.cur is None:
            return
        it = self.items[self.cur]
        dialog = SlotDialogQt(self, self._editor_for(it), "cond", it.get(key) or {
            "t": "cmp", "a": {"t": "played", "scope": "turn", "filter": "Any"}, "op": ">=", "b": {"t": "num", "v": 2}})
        if dialog.exec() and dialog.result is not None:
            it[key] = dialog.result
            self._cond_btns[key].setText(self._cond_text(it, key))
            self.write_item()
            self._notify()

    def _cond_text(self, it, key):'''),
])

patch("buttonqt.py", [
    ('''from formqt import label
''', '''from formqt import label
from blockqt import edit_blocks
from slotqt import SlotDialogQt
'''),
    ('''        self.val_btn = _disabled(BLOCK_NOTE)
        row("표시 값 (#)", self.val_btn)''', '''        self.val_btn = _slot_button(self, "value")
        row("표시 값 (#)", self.val_btn)'''),
    ('''        self.cond_btn = _disabled(BLOCK_NOTE)
        row("쓸 수 있는 조건", self.cond_btn)''', '''        self.cond_btn = _slot_button(self, "cond")
        row("쓸 수 있는 조건", self.cond_btn)'''),
    ('''        self.block_btn = _disabled(BLOCK_NOTE)
        self.block_btn.setText("🧩 눌렀을 때 실행할 블록… (Tk 앱에서)")''', '''        self.block_btn = QPushButton("🧩 눌렀을 때 실행할 블록…")
        self.block_btn.clicked.connect(lambda _=False: self.edit_press_blocks())'''),
    ('''    # ---- 데이터 ----
    @property
    def items(self):
        return self.tab.g["buttons"]''', '''    def edit_press_blocks(self):
        """눌렀을 때 실행할 블록 (Tk 의 edit_blocks 와 같다)."""
        if self.b is None:
            return
        b = self.b
        result = edit_blocks(self, self.tab.project, "button", {"id": b["id"], "trigger": "none", "enemy_mode": "all"},
                             b.get("blocks") or [], where=f"버튼 '{b.get('label_ko')}'을 눌렀을 때")
        if result is not None:
            b["blocks"] = result["blocks"]
            self.tab.dirty()
            self.refresh_labels()

    def edit_slot_key(self, key):
        """표시 값 또는 쓸 수 있는 조건 하나를 고친다."""
        if self.b is None:
            return
        b = self.b
        context = SimpleNamespace(project=self.tab.project, owner_kind="button", item=b, allow_event=False,
                                  condition_scope="")
        current = b.get(key) or ({"t": "num", "v": 0} if key == "value" else
                                 {"t": "cmp", "a": {"t": "stacks"}, "op": ">=", "b": {"t": "num", "v": 1}})
        dialog = SlotDialogQt(self, context, "value" if key == "value" else "cond", current)
        if dialog.exec() and dialog.result is not None:
            b[key] = dialog.result
            self.tab.dirty()
            self.refresh_labels()

    # ---- 데이터 ----
    @property
    def items(self):
        return self.tab.g["buttons"]'''),
    ('''def _set_choice(box, value):''', '''def _slot_button(designer, key):
    button = QPushButton("")
    button.clicked.connect(lambda _=False: designer.edit_slot_key(key))
    return button


def _set_choice(box, value):'''),
    ('''import copy
import time
''', '''import copy
import time
from types import SimpleNamespace
'''),
    ('''        d = B.describe''', '''        d = B.describe'''),
])

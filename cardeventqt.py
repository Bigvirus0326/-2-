"""카드의 '뽑을 · 버릴 · 소멸할 때' 효과 칸 (Tk 의 CardEventEffects 와 같은 규칙).

탭마다 블록 목록 하나, 강화 후 따로 설정, 강화 후 효과 편집, 강화 전 효과 복사, 이벤트 대상과 선택 수.
블록 저장소는 카드 안에 그대로 둔다: event_blocks / upgrade_event_blocks, event_targets, event_target_counts.
"""
import copy

from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QHBoxLayout, QLabel, QListWidget,
                               QMessageBox, QPushButton, QSpinBox, QVBoxLayout, QWidget)

import blockcode as B
from flowlayout import FlowLayout
import gimmickrules as GR
import modgen as M
import previewcore as PV
import projectio as IO

EVENTS = (("draw", "뽑을 때"), ("discard", "버릴 때"), ("exhaust", "소멸할 때"))


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


class CardEventPanelQt(QWidget):
    def __init__(self, tab, event, label, parent=None):
        super().__init__(parent)
        self.tab, self.ev, self.label = tab, event, label
        self._loading = False

        root = QVBoxLayout(self)
        self.hint = QLabel()
        self.hint.setWordWrap(True)
        root.addWidget(self.hint)

        body = QHBoxLayout()
        self.listing = QListWidget()
        self.listing.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.listing.itemDoubleClicked.connect(lambda _i: self.edit())
        body.addWidget(self.listing, 1)
        side = QVBoxLayout()
        self.buttons = []
        for text, slot in (("블록 편집", self.edit), ("삭제", self.remove),
                           ("▲", lambda: self.move(-1)), ("▼", lambda: self.move(1))):
            button = QPushButton(text)
            button.clicked.connect(slot)
            side.addWidget(button)
            self.buttons.append(button)
        side.addStretch(1)
        body.addLayout(side)
        root.addLayout(body)

        target_row = QHBoxLayout()
        target_row.addWidget(QLabel("이벤트 대상"))
        self.target = QComboBox()
        for value, text in M.CARD_EVENT_TARGETS:
            self.target.addItem(text, value)
        self.target.currentIndexChanged.connect(lambda _i: self._target_changed())
        target_row.addWidget(self.target)
        target_row.addWidget(QLabel("선택 수"))
        self.count = QSpinBox()
        self.count.setRange(1, 99)
        self.count.valueChanged.connect(self._count_changed)
        target_row.addWidget(self.count)
        note = QLabel("명 · 블록에서 '대상'을 고르면 이 설정을 사용합니다.")
        note.setWordWrap(True)                  # 긴 설명은 줄을 바꾼다 (창을 넓히지 않게)
        note.setMinimumWidth(0)
        target_row.addWidget(note)
        target_row.addStretch(1)
        root.addLayout(target_row)

        variants = FlowLayout(spacing=8)        # 칸이 좁으면 버튼이 다음 줄로 넘어간다
        self.separate = QCheckBox("강화 후 따로 설정")
        self.separate.toggled.connect(self._variant_changed)
        self.upgraded = QCheckBox("강화 후 효과 편집")
        self.upgraded.toggled.connect(lambda _c: self._reload())
        self.copy_button = QPushButton("강화 전 효과 복사")
        self.copy_button.clicked.connect(self.copy_base)
        for widget in (self.separate, self.upgraded, self.copy_button):
            variants.addWidget(widget)
        root.addLayout(variants)
        root.addStretch(1)
        self.refresh()

    # ---- 읽기 ----
    def card(self):
        cur = getattr(self.tab, "cur", None)
        items = self.tab.items
        return items[cur] if cur is not None and cur < len(items) else None

    def _key(self, card):
        return "upgrade_event_blocks" if card and M.event_separate(card, self.ev) and self.upgraded.isChecked() else "event_blocks"

    def blocks(self):
        card = self.card()
        return card.get(self._key(card), {}).get(self.ev, []) if card else []

    def _text(self, card, block):
        description = B.describe([block], self.tab.project, "card", "ko")
        description = PV.fill_values(self.tab.project, description, card, upgraded=self.upgraded.isChecked())
        return GR.plain(description) or B.SPECS.get(block.get("op"), {}).get("ko", "효과")

    def _reload(self):
        if not self._loading:
            self.refresh(self.listing.currentRow())

    def refresh(self, select=None):
        self._loading = True
        try:
            card = self.card()
            separate = bool(card and M.event_separate(card, self.ev))
            self.separate.setChecked(separate)
            if not separate:
                self.upgraded.setChecked(False)
            self.listing.clear()
            blocks = self.blocks()
            for block in blocks:
                self.listing.addItem(self._text(card, block))
            if blocks and select is not None and select >= 0:
                self.listing.setCurrentRow(min(select, len(blocks) - 1))
            enabled = card is not None and not card.get("clone")
            self.separate.setEnabled(enabled)
            self.upgraded.setEnabled(enabled and separate)
            self.copy_button.setEnabled(enabled)
            self.target.setEnabled(enabled)
            for button in self.buttons:
                button.setEnabled(enabled)
            target = card.get("event_targets", {}).get(self.ev, "random") if card else "random"
            self.target.setCurrentIndex(max(0, self.target.findData(target)))
            self.count.setValue(int(card.get("event_target_counts", {}).get(self.ev, 1)) if card else 1)
            self.count.setEnabled(enabled and target == "choose")
            self._update_hint(card, target)
            index = self.tab.event_tabs.indexOf(self) if getattr(self.tab, "event_tabs", None) else -1
            if index >= 0:
                self.tab.event_tabs.setTabText(index, self.label + (f" ({len(blocks)})" if blocks else ""))
        finally:
            self._loading = False

    def _update_hint(self, card, target):
        if card and card.get("clone"):
            text = "가져온 원본 카드는 이 시점의 효과 편집을 지원하지 않습니다."
        elif target == "choose":
            text = (f"적을 최대 {self.count.value()}명 차례로 선택하세요. 중복 선택은 불가하며, "
                    "취소하면 선택한 적까지만 적용합니다.")
        else:
            text = "블록 편집을 눌러 효과를 추가하거나 수정하세요."
        self.hint.setText(text)

    # ---- 고치기 ----
    def edit(self):
        from blockqt import edit_blocks
        card = self.card()
        if not card or card.get("clone"):
            return
        upgraded = M.event_separate(card, self.ev) and self.upgraded.isChecked()
        key = "upgrade_event_blocks" if upgraded else "event_blocks"
        result = edit_blocks(self, self.tab.project, "card", card, card.get(key, {}).get(self.ev, []),
                             where=self.label + (" · 강화 후" if upgraded else " · 강화 전"),
                             show_text=False, card_event=self.ev)
        if result is not None:
            card.setdefault(key, {})[self.ev] = result["blocks"]
            self.refresh()
            self.tab._effects_changed()

    def remove(self):
        card = self.card()
        row = self.listing.currentRow()
        if row < 0 or not card or card.get("clone"):
            return
        del self.blocks()[row]
        self.refresh(row)
        self.tab._effects_changed()

    def move(self, direction):
        card = self.card()
        blocks = self.blocks()
        row = self.listing.currentRow()
        dest = row + direction
        if row < 0 or not card or card.get("clone") or not 0 <= dest < len(blocks):
            return
        blocks[row], blocks[dest] = blocks[dest], blocks[row]
        self.refresh(dest)
        self.tab._effects_changed()

    def _variant_changed(self, checked):
        card = self.card()
        if self._loading or not card or card.get("clone"):
            return
        card.setdefault("separate_upgrade_events", {})[self.ev] = checked
        if checked:
            card.setdefault("upgrade_event_blocks", {}).setdefault(
                self.ev, copy.deepcopy(card.get("event_blocks", {}).get(self.ev, [])))
        self.upgraded.setChecked(checked)
        self.refresh()
        self.tab._effects_changed()

    def copy_base(self):
        card = self.card()
        if not card or card.get("clone"):
            return
        if card.get("upgrade_event_blocks", {}).get(self.ev) and not _ask(
                self, "저장된 강화 후 효과를 강화 전 효과의 복사본으로 바꿀까요?"):
            return
        card.setdefault("upgrade_event_blocks", {})[self.ev] = copy.deepcopy(card.get("event_blocks", {}).get(self.ev, []))
        card.setdefault("separate_upgrade_events", {})[self.ev] = True
        self.refresh()
        self.tab._effects_changed()

    def _target_changed(self):
        card = self.card()
        if self._loading or not card or card.get("clone"):
            return
        card.setdefault("event_targets", {})[self.ev] = self.target.currentData()
        self.refresh()
        self.tab._effects_changed()

    def _count_changed(self, value):
        card = self.card()
        if self._loading or not card or card.get("clone") or self.target.currentData() != "choose":
            return
        card.setdefault("event_target_counts", {})[self.ev] = value
        self._update_hint(card, "choose")
        self.tab._effects_changed()

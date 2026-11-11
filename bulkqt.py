"""한꺼번에 바꾸기 (Qt 版): 고른 여러 항목의 공통 칸(종류·희귀도·비용 등)을 한 번에 바꾼다. 체크한 칸만 바뀐다.

Tk 의 uxkit.BulkEditDialog 와 같은 규칙. 바꾸기 전에 바뀔 내용을 보여 주고 확인을 받는다.
"""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QSpinBox, QVBoxLayout)

import gimmick as GM
import projectio as IO


class BulkEditDialogQt(QDialog):
    def __init__(self, tab, indices, parent=None):
        super().__init__(parent or tab)
        self.tab = tab
        self.indices = list(indices)
        self.setWindowTitle(f"{tab.noun} {len(self.indices)}개 한꺼번에 바꾸기")
        first = tab.items[self.indices[0]]
        root = QVBoxLayout(self)
        root.addWidget(QLabel("바꿀 칸만 체크하세요. 체크하지 않은 칸은 그대로 둡니다."))
        grid = QGridLayout()
        self.rows = []                              # (키, 체크 상자, 값 가져오는 함수)
        labels = getattr(tab, "field_labels", {})
        r = 0
        for key, (typ, w) in tab._fields.items():
            if typ not in ("combo", "int", "bool") or key == "id":
                continue
            on = QCheckBox()
            grid.addWidget(on, r, 0)
            grid.addWidget(QLabel(labels.get(key, key)), r, 1)
            if typ == "combo":
                options = [(w.itemData(i), w.itemText(i)) for i in range(w.count())]
                box = QComboBox()
                for value, text in options:
                    box.addItem(text, value)
                current = first.get(key)
                index = box.findData(current)
                box.setCurrentIndex(index if index >= 0 else 0)
                box.currentIndexChanged.connect(lambda _i, c=on: c.setChecked(True))
                getter = (lambda b=box: b.currentData())
                grid.addWidget(box, r, 2)
            elif typ == "int":
                spin = QSpinBox()
                spin.setRange(-9999, 9999)
                spin.setValue(int(first.get(key, 0) or 0))
                spin.valueChanged.connect(lambda _v, c=on: c.setChecked(True))
                getter = (lambda s=spin: int(s.value()))
                grid.addWidget(spin, r, 2)
            else:
                box = QCheckBox("켜기")
                box.setChecked(bool(first.get(key)))
                box.toggled.connect(lambda _v, c=on: c.setChecked(True))
                getter = (lambda b=box: b.isChecked())
                grid.addWidget(box, r, 2)
            self.rows.append((key, on, getter))
            r += 1
        self.tags = [t for t in GM.tags(tab.project)] if tab.kind == "card" else []
        self.tag_box = QComboBox()
        self.tag_box.addItem("태그 추가 안 함", "")
        for t in self.tags:
            self.tag_box.addItem(t.get("name_ko") or t["id"], t["id"])
        if self.tags:
            grid.addWidget(QLabel("기믹 태그 추가"), r, 1)
            grid.addWidget(self.tag_box, r, 2)
            r += 1
        if not self.rows:
            grid.addWidget(QLabel("한꺼번에 바꿀 수 있는 칸이 없습니다."), r, 0, 1, 3)
            r += 1
        root.addLayout(grid)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        go = QPushButton("바꾸기")
        go.clicked.connect(self.ok)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        buttons.addWidget(go)
        buttons.addWidget(cancel)
        root.addLayout(buttons)

    def ok(self):
        changes = {}
        for key, on, getter in self.rows:
            if on.isChecked():
                value = getter()
                if value is not None:
                    changes[key] = value
        tag = self.tag_box.currentData() if self.tags else ""
        updates = []
        for i in self.indices:
            card = self.tab.items[i]
            diff = {k: v for k, v in changes.items() if card.get(k) != v}
            if tag and tag not in card.get("gtags", []):
                diff["gtags"] = card.get("gtags", []) + [tag]
            if diff:
                updates.append((i, diff))
        if not updates:
            self.reject()
            return
        labels = getattr(self.tab, "field_labels", {})
        preview = "\n".join(
            (self.tab.items[i].get("name_ko") or self.tab.items[i]["id"]) + ": " +
            ", ".join(f"{labels.get(k, k)} {self.tab.items[i].get(k, '')} → {v}" for k, v in diff.items())
            for i, diff in updates)
        if QMessageBox.question(self, IO.APP_TITLE, "일괄 변경 미리보기\n\n" + preview + "\n\n적용할까요?") \
                != QMessageBox.StandardButton.Yes:
            return
        for i, diff in updates:
            self.tab.items[i].update(diff)
        self.tab._notify()
        self.tab.refresh_list(self.indices[0])
        self.accept()

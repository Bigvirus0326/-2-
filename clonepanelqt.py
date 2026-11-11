"""복제한 항목 패널 (Qt 版): 원본 정보 · 원본 수치 표 · 원본 수치 편집 · 원본 풀 · 원본 코드 보기.

Tk 의 ClonePanel 과 같은 규칙. 보이는 조건과 칸의 동작은 원본을 따른다.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QHBoxLayout, QHeaderView, QLabel, QPushButton,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from dialogsqt import RawVarDialogQt
from qtkit import code_window as _code_window
import qtkit as Q


class ClonePanelQt(QWidget):
    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.tab = tab
        self.item = None
        self._code_dialogs = []
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 4, 0, 4)
        self.info = QLabel("")
        self.info.setStyleSheet(f"color: {Q.C['warn']};")
        self.info.setWordWrap(True)
        root.addWidget(self.info)
        row = QHBoxLayout()
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["원본 값 이름", "종류", "수치", "강화 시 +"])
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setMaximumHeight(130)
        self.table.itemDoubleClicked.connect(lambda _it: self.edit())
        row.addWidget(self.table, 1)
        side = QVBoxLayout()
        edit = QPushButton("수치 편집")
        edit.clicked.connect(self.edit)
        side.addWidget(edit)
        code = QPushButton("원본 코드 보기")
        code.clicked.connect(self.show_code)
        side.addWidget(code)
        self.pool = QComboBox()
        self.pool.addItem("내 카드/유물 풀", "mine")
        self.pool.addItem("원본 캐릭터 풀", "theirs")
        self.pool.currentIndexChanged.connect(lambda _i: self._pool_changed())
        side.addWidget(self.pool)
        side.addStretch(1)
        row.addLayout(side)
        root.addLayout(row)
        self.hide()

    def set(self, item, inside_editor=False):
        """항목이 바뀌었을 때 부른다. 보여야 할 때만 보인다 (Tk 와 같은 조건)."""
        self.item = item
        cl = item.get("clone") if item else None
        hidden = ((cl and cl.get("editable_play") and any(e.get("original_effect") for e in item.get("effects", []))
                   and not inside_editor) or (not cl and not (item and item.get("raw_vars"))))
        if not item or hidden:
            self.hide()
            return
        self.show()
        if cl:
            self.info.setText(f"원본 효과 · {cl.get('orig_class')} ({cl.get('mod')})")
            self.pool.blockSignals(True)
            index = self.pool.findData(cl.get("pool", "mine"))
            self.pool.setCurrentIndex(index if index >= 0 else 0)
            self.pool.blockSignals(False)
            self.pool.setVisible(not (self.tab.kind == "card" and item.get("pool_character")))
        else:
            self.info.setText("불러온 항목 (코드 없음): 원본 텍스트를 그대로 씁니다.")
            self.pool.setVisible(False)
        rows = item.get("raw_vars", []) or []
        self.table.setRowCount(0)
        for v in rows:
            r = self.table.rowCount()
            self.table.insertRow(r)
            for col, value in enumerate((v.get("name"), v.get("type"), v.get("value"), v.get("upgrade"))):
                self.table.setItem(r, col, QTableWidgetItem("" if value is None else str(value)))

    def edit(self):
        r = self.table.currentRow()
        if r < 0 or not self.item or r >= len(self.item.get("raw_vars", [])):
            return
        v = self.item["raw_vars"][r]
        dialog = RawVarDialogQt(self, v)
        if dialog.exec() and dialog.result:
            v["value"], v["upgrade"] = dialog.result
            self.set(self.item)
            self.tab._notify()

    def _pool_changed(self):
        if self.item and self.item.get("clone"):
            index = self.tab.cur
            self.item["clone"]["pool"] = self.pool.currentData()
            if self.tab.kind == "card":
                self.item["pool_character"] = ""
            self.tab._notify()
            if self.tab.kind == "card" and index is not None:
                self.tab.refresh_list(index)

    def show_code(self):
        if self.item and self.item.get("clone"):
            cl = self.item["clone"]
            self._code_dialogs.append(_code_window(self, f"원본 코드 - {cl.get('orig_class')}", cl.get("body", "")))

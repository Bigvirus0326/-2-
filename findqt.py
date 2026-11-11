"""전체에서 찾기 창 (Qt 版). 이름·ID·설명으로 찾고, 고르면 그 항목 편집 화면으로 간다 (Tk 의 FindPalette 와 같다)."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout

import findcore as FC

LIMIT = 300


class FindPaletteQt(QDialog):
    def __init__(self, app, query="", parent=None):
        super().__init__(parent or app)
        self.app = app
        self.setWindowTitle("전체에서 찾기")
        self.resize(560, 440)
        self.rows = []
        root = QVBoxLayout(self)
        root.addWidget(QLabel("이름·ID·설명으로 찾기 (초성도 됩니다: ㅅㅂ → 수비)"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("찾을 말")
        self.search.textChanged.connect(self.refresh)
        self.search.returnPressed.connect(self.go)
        root.addWidget(self.search)
        self.listing = QListWidget()
        self.listing.itemDoubleClicked.connect(lambda _i: self.go())
        root.addWidget(self.listing, 1)
        self.count = QLabel("")
        root.addWidget(self.count)
        if query:
            self.search.setText(query)
        self.refresh(self.search.text())
        self.search.setFocus()

    def refresh(self, query):
        self.listing.clear()
        self.rows = []
        for kind, iid, name, extra, _item in FC.all_entries(self.app.project):
            if not FC.matches(query, name, iid, extra, FC.KIND_LABEL.get(kind, "")):
                continue
            row = QListWidgetItem(f"{name}    [{FC.KIND_LABEL.get(kind, kind)}]  {iid}")
            self.listing.addItem(row)
            self.rows.append((kind, iid))
            if len(self.rows) >= LIMIT:
                break
        if self.rows:
            self.listing.setCurrentRow(0)
        more = " (처음 300개만 보여 줍니다)" if len(self.rows) >= LIMIT else ""
        self.count.setText(f"{len(self.rows)}개{more}")

    def go(self):
        row = self.listing.currentRow()
        if row < 0 or row >= len(self.rows):
            return
        kind, iid = self.rows[row]
        self.accept()
        self.app.goto_any(kind, iid)

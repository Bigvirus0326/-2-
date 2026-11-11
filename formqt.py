"""칸 만들기 도우미 (Qt). 아이템 탭(itemtabqt)과 기믹 탭(gimmickqt)이 같이 쓴다.

등록한 칸은 self._fields 에 (종류, 위젯) 으로 들어간다. 종류: str · int · combo · text · bool.
값을 프로젝트에 쓰는 것(fields_to_item)과 프로젝트에서 읽는 것(item_to_fields)도 여기서 한다.
쓰는 쪽은 칸이 바뀌면 self._edited() 를 부르고, 읽는 쪽은 self._loading 을 켠 채로 부른다.
"""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QLabel, QLineEdit, QPlainTextEdit,
                               QPushButton, QSizePolicy, QSpinBox)
import os

import qtkit as Q
import fieldhelp as FH

INT_RANGE = (-9999, 9999)     # 기존 값을 위젯이 고쳐 쓰지 않도록 넓게 둔다 (Tk 는 입력한 값을 그대로 둔다)


def label(text="", help_text=""):
    """긴 설명이 칸을 밀어내지 않도록 줄을 바꾼다 (창이 좁을 때 가로 스크롤이 생기지 않게).
    help_text 가 있으면 마우스를 올렸을 때 말풍선을 띄운다."""
    text_label = QLabel(text)
    text_label.setWordWrap(True)
    text_label.setContentsMargins(0, 0, 14, 0)      # 칸 이름과 입력 칸 사이를 띄운다 (붙어 보이지 않게)
    if help_text:
        Q.tip(text_label, help_text)
        text_label.setCursor(Qt.CursorShape.WhatsThisCursor)
    return text_label


def shrink(widget):
    """칸이 창 너비에 맞게 줄어들도록 한다 (글자 길이 때문에 칸이 잘리지 않게)."""
    widget.setMinimumWidth(0)
    widget.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    if isinstance(widget, QComboBox):
        widget.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        widget.setMinimumContentsLength(4)
    return widget


def fill(box, options):
    box.clear()
    for value, text in options:
        box.addItem(text, value)


class FieldsMixin:
    image_hint = ""

    def _label_of(self, key, text):
        """칸의 이름을 기억한다 (한꺼번에 바꾸기 창에 쓴다)."""
        if not hasattr(self, "field_labels"):
            self.field_labels = {}
        self.field_labels[key] = text.replace("\n", " ")

    def _help_label(self, text, key):
        """칸 이름. 설명이 있으면 ⓘ 를 붙이고 마우스를 올리면 말풍선을 띄운다 (Tk 의 _field_label 과 같다)."""
        help_text = FH.field_help(getattr(self, "kind", ""), key)
        return label(text + ("  ⓘ" if help_text else ""), help_text)

    def _str(self, g, row, col, text, key):
        edit = shrink(QLineEdit())
        edit.textChanged.connect(self._edited)
        g.addWidget(self._help_label(text, key), row, col)
        g.addWidget(edit, row, col + 1)
        self._fields[key] = ("str", edit)
        return edit

    def _int(self, g, row, col, text, key):
        self._label_of(key, text)
        spin = shrink(QSpinBox())
        spin.setRange(*INT_RANGE)
        spin.valueChanged.connect(self._edited)
        g.addWidget(self._help_label(text, key), row, col)
        g.addWidget(spin, row, col + 1)
        self._fields[key] = ("int", spin)
        return spin

    def _combo(self, g, row, col, text, key, options):
        self._label_of(key, text)
        box = shrink(QComboBox())
        fill(box, options)
        box.currentIndexChanged.connect(self._edited)
        g.addWidget(self._help_label(text, key), row, col)
        g.addWidget(box, row, col + 1)
        self._fields[key] = ("combo", box)
        return box

    def _check(self, key, text):
        self._label_of(key, text)
        box = QCheckBox(text)
        Q.tip(box, FH.field_help(getattr(self, "kind", ""), key))
        box.toggled.connect(self._edited)
        self._fields[key] = ("bool", box)
        return box

    def _text(self, g, row, text, key, height=3, mono=False):
        g.addWidget(self._help_label(text, key), row, 0, Qt.AlignmentFlag.AlignTop)
        edit = QPlainTextEdit()
        edit.setFixedHeight(height * 22 + 10)
        if mono:
            edit.setStyleSheet("font-family: Consolas;")
        edit.textChanged.connect(self._edited)
        g.addWidget(edit, row, 1, 1, 3)
        self._fields[key] = ("text", edit)
        return edit

    def _image(self, g, row, key="image"):
        edit = QLineEdit()
        edit.textChanged.connect(self._edited)
        browse = QPushButton("찾기…")
        browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
        g.addWidget(self._help_label("그림 (PNG)", key), row, 0)
        g.addWidget(edit, row, 1)
        g.addWidget(browse, row, 2)
        g.addWidget(label(self.image_hint), row, 3)
        self._fields[key] = ("str", edit)
        return edit

    def _browse(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "그림 고르기", "", "PNG 이미지 (*.png);;모든 파일 (*.*)")
        if path:
            edit.setText(os.path.normpath(path))

    def _box(self, key):
        return self._fields[key][1]

    def _set_checked(self, key, value):
        box = self._box(key)
        box.blockSignals(True)
        box.setChecked(value)
        box.blockSignals(False)

    def fields_to_item(self, it):
        """등록된 칸의 값을 항목에 쓴다 (Tk 앱의 changed() 와 같은 규칙: 문자열은 앞뒤 공백을 자른다)."""
        for key, (typ, w) in self._fields.items():
            if typ == "str":
                val = w.text().strip()
                it[key] = val.strip('"') if key == "image" else val
            elif typ == "int":
                it[key] = int(w.value())
            elif typ == "combo":
                it[key] = w.currentData()
            elif typ == "text":
                it[key] = w.toPlainText().strip()
            elif typ == "rich":
                it[key] = w.source().strip()
            elif typ == "bool":
                it[key] = bool(w.isChecked())

    def item_to_fields(self, it):
        """항목의 값을 칸에 넣는다. 호출하는 쪽이 self._loading 을 켜 둔다."""
        for key, (typ, w) in self._fields.items():
            val = it.get(key, "")
            if typ == "str":
                w.setText(str(val))
            elif typ == "int":
                w.setValue(int(val) if isinstance(val, (int, float)) else 0)
            elif typ == "combo":
                Q.set_combo_value(w, val)
            elif typ == "text":
                w.setPlainText(val or "")
            elif typ == "rich":
                w.set_source(val or "")
            elif typ == "bool":
                w.setChecked(bool(val))

"""설명 글 편집 칸 (Qt 版): 색·굵게·기울임과 '연결 수치·태그·파워·기믹' 칩을 글로 저장한다.

Tk 의 DescriptionText 와 같은 글(source)을 주고받는다. 칩은 Tk 처럼 창 위젯이 아니라, 칩 자리에 표시 글과
토큰을 함께 담은 글자로 그린다. 게임 색 막대(GameColorBar)와 '수치 넣기' · '태그·파워·기믹 넣기' 창도 여기 있다.
"""
import re
import uuid

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPushButton, QTextEdit, QVBoxLayout, QWidget)

import modgen as M
import previewcore as PV
import projectio as IO
import qtkit as Q
from flowlayout import FlowLayout

GAME_COLOR_LABELS = [("gold", "금색"), ("blue", "파랑"), ("green", "초록"), ("red", "빨강"),
                     ("orange", "주황"), ("purple", "보라"), ("aqua", "청록"), ("pink", "분홍")]
CHIP_BG, CHIP_FG = "#e8f1ff", "#185197"
PROP_TAGS, PROP_CHIP = 0x100001, 0x100002      # QTextFormat 사용자 속성 번호 (글자마다 붙인다)
ENERGY_COLOR = "#9a6500"
_CHIP_SERIAL = [0]


def _closing(opening):
    """'[color=#ff0000]' -> '[/color]', '[b]' -> '[/b]'."""
    name = opening[1:].split("=", 1)[0].split("]", 1)[0]
    return f"[/{name}]"


def _tag_format(tag):
    """여는 태그 하나를 글자 모양으로 바꾼다."""
    fmt = QTextCharFormat()
    raw = tag.lower()
    if raw.startswith("[color=") and raw.endswith("]"):
        fmt.setForeground(QColor(raw[7:-1]))
    elif raw in ("[b]",):
        fmt.setFontWeight(QFont.Weight.Bold)
    elif raw in ("[i]",):
        fmt.setFontItalic(True)
    elif raw == "[energy]":
        fmt.setForeground(QColor(ENERGY_COLOR))
    else:
        name = raw[1:-1]
        if name in PV.TEXT_COLORS:
            fmt.setForeground(QColor(PV.TEXT_COLORS[name]))
    return fmt


def _apply_tags(fmt, tags):
    for tag in tags:
        extra = _tag_format(tag)
        if extra.hasProperty(QTextCharFormat.Property.ForegroundBrush):
            fmt.setForeground(extra.foreground())
        if extra.fontWeight() == QFont.Weight.Bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if extra.fontItalic():
            fmt.setFontItalic(True)
    fmt.setProperty(PROP_TAGS, tuple(tags))
    return fmt


def _is_color_tag(opening):
    raw = opening.lower()
    if raw.startswith("[color="):
        return True
    return raw[1:-1] in PV.TEXT_COLORS


class DescriptionEditQt(QTextEdit):
    """설명 글 한 칸. context() 는 (프로젝트, 항목, 언어, 강화 여부) 를 돌려 준다 (칩 글을 채우는 데 쓴다)."""

    _clipboard_plain = None
    _clipboard_source = None

    def __init__(self, context, parent=None):
        super().__init__(parent)
        self.context = context
        self._chips = {}                 # chip id -> 토큰
        self.setAcceptRichText(False)
        self.setMinimumHeight(80)

    # ---- 글 ↔ 칸 ----
    def insert_source(self, source, cursor=None):
        """글(source)을 칸에 넣는다. 색·굵게·기울임 태그는 글자 모양으로, {…} 는 칩으로 바꾼다."""
        cur = cursor or self.textCursor()
        active = []
        pos = 0
        while pos < len(source):
            if source[pos] == "[":
                match = re.match(r"\[(/?)([a-z_]+)(=#[a-fA-F0-9]{6})?\]", source[pos:])
                if match:
                    closing, tag, arg = match.groups()
                    if closing:
                        hit = next((i for i in range(len(active) - 1, -1, -1) if active[i][0] == tag), None)
                        if hit is not None:
                            active.pop(hit)
                            pos += len(match[0])
                            continue
                    elif tag in ("b", "i", "energy") or tag in PV.TEXT_COLORS or (tag == "color" and arg):
                        opening = "[" + tag + (arg or "") + "]"
                        active.append((tag, opening))
                        pos += len(match[0])
                        continue
            tags = tuple(opening for _tag, opening in active)
            if source[pos] == "{":
                depth, end = 1, pos + 1
                while end < len(source) and depth:
                    depth += (source[end] == "{") - (source[end] == "}")
                    end += 1
                if depth == 0:
                    self._insert_chip(cur, source[pos:end], tags)
                    pos = end
                    continue
            fmt = _apply_tags(QTextCharFormat(), tags)
            cur.insertText(source[pos], fmt)
            pos += 1
        self.setTextCursor(cur)
        self.refresh_labels()

    def _insert_chip(self, cur, token, tags):
        _CHIP_SERIAL[0] += 1
        chip_id = _CHIP_SERIAL[0]
        self._chips[chip_id] = token
        fmt = _apply_tags(QTextCharFormat(), tags)
        fmt.setBackground(QColor(CHIP_BG))
        fmt.setForeground(QColor(CHIP_FG))
        fmt.setProperty(PROP_CHIP, chip_id)
        cur.insertText(self._label(token), fmt)

    def _label(self, token):
        project, item, lang, upgraded = self.context()
        rendered = M.resolve_description_references(M.resolve_block_description(token, item), project, lang)
        rendered = PV.fill_values(project, rendered, item, upgraded)
        plain = "".join(text for text, _ in PV.parse_bbcode(rendered)).strip()
        return plain if plain and plain != "?" else "연결 수치"

    def fragments(self):
        """(글자, 글자 모양) 조각을 차례대로 돌려 준다."""
        block = self.document().begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid():
                    yield frag.text(), frag.charFormat()
                it += 1
            block = block.next()
            if block.isValid():
                yield "\n", QTextCharFormat()

    def source(self):
        """칸의 내용을 글(source)로 바꾼다. set_source 와 짝을 이룬다."""
        segments = []                    # (태그 묶음, 글)
        chip_seen = None
        for text, fmt in self.fragments():
            chip = fmt.property(PROP_CHIP)
            if chip:
                if chip == chip_seen:
                    continue             # 같은 칩의 나머지 글자
                chip_seen = chip
                value = self._chips.get(chip, text)
                tags = tuple(fmt.property(PROP_TAGS) or ())
                segments.append((tags, value, True))
                continue
            chip_seen = None
            tags = tuple(fmt.property(PROP_TAGS) or ())
            if segments and not segments[-1][2] and segments[-1][0] == tags:
                segments[-1] = (tags, segments[-1][1] + text, False)
            else:
                segments.append((tags, text, False))
        out = []
        for tags, value, is_chip in segments:
            if is_chip:
                out.append("".join(tags) + value + "".join(_closing(t) for t in reversed(tags)))
            else:
                out.append("".join(tags) + value + "".join(_closing(t) for t in reversed(tags)))
        return "".join(out)

    def set_source(self, source):
        self.blockSignals(True)
        try:
            self.clear()
            self._chips = {}
            self.insert_source(source or "", QTextCursor(self.document()))
        finally:
            self.blockSignals(False)
        self.textChanged.emit()

    def refresh_labels(self):
        """칩의 글(연결 수치 값)을 다시 쓴다 (값이 바뀌었을 때)."""
        spans = []
        chip_now = None
        start = 0
        index = 0
        for text, fmt in self.fragments():
            chip = fmt.property(PROP_CHIP)
            for _ in text:
                if chip != chip_now:
                    if chip_now:
                        spans.append((chip_now, start, index))
                    chip_now, start = chip, index
                index += 1
        if chip_now:
            spans.append((chip_now, start, index))
        for chip, a, b in reversed(spans):
            token = self._chips.get(chip)
            if token is None:
                continue
            cur = QTextCursor(self.document())
            cur.setPosition(a)
            cur.setPosition(b, QTextCursor.MoveMode.KeepAnchor)
            fmt = cur.charFormat()
            new = self._label(token)
            if cur.selectedText() != new:
                cur.insertText(new, fmt)

    # ---- 색 ----
    def selection_range(self):
        cur = self.textCursor()
        if not cur.hasSelection():
            return None
        return cur.selectionStart(), cur.selectionEnd()

    def _edit_tags(self, start, end, change):
        """start..end 안의 글을 묶음마다 change(태그 묶음) 로 바꾼다. 칩은 건드리지 않는다."""
        doc = self.document()
        pieces = []
        block = doc.begin()
        while block.isValid():
            it = block.begin()
            while not it.atEnd():
                frag = it.fragment()
                if frag.isValid() and not frag.charFormat().property(PROP_CHIP):
                    a_, b_ = frag.position(), frag.position() + frag.length()
                    lo, hi = max(a_, start), min(b_, end)
                    if lo < hi:
                        pieces.append((lo, hi, tuple(frag.charFormat().property(PROP_TAGS) or ())))
                it += 1
            block = block.next()
        for lo, hi, tags in reversed(pieces):
            cur = QTextCursor(doc)
            cur.setPosition(lo)
            cur.setPosition(hi, QTextCursor.MoveMode.KeepAnchor)
            cur.setCharFormat(_apply_tags(QTextCharFormat(), change(tags)))
        self.textChanged.emit()

    def apply_color(self, start, end, color):
        opening = f"[color={color}]"
        self._edit_tags(start, end, lambda tags: tuple(t for t in tags if not _is_color_tag(t)) + (opening,))

    def apply_game_color(self, start, end, name):
        if name not in PV.TEXT_COLORS:
            raise ValueError("지원하지 않는 게임 색상입니다.")
        opening = f"[{name}]"
        self._edit_tags(start, end, lambda tags: tuple(t for t in tags if not _is_color_tag(t)) + (opening,))

    def reset_color(self, start, end):
        self._edit_tags(start, end, lambda tags: tuple(t for t in tags if not _is_color_tag(t)))

    def insert_token(self, token):
        cur = self.textCursor()
        self.insert_source(token, cur)
        self.textChanged.emit()


class GameColorBar(QWidget):
    """게임 기본 색 여덟 가지 + 기본색 + 직접 고르기 (Tk 의 GameColorBar 와 같다)."""

    def __init__(self, field, on_change, parent=None):
        super().__init__(parent)
        self.field = field
        self.on_change = on_change
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(QLabel("게임 기본 색"))
        grid = FlowLayout(spacing=4)            # 색 단추는 칸이 좁으면 다음 줄로 넘어간다
        for name, label in GAME_COLOR_LABELS:
            button = QPushButton(label)
            button.setStyleSheet(f"background: {PV.TEXT_COLORS[name]}; color: {Q.C['text']};")
            button.setToolTip("선택한 글자를 게임의 " + label + "으로 표시합니다.")
            button.clicked.connect(lambda _=False, n=name: self.apply(n))
            grid.addWidget(button)
        root.addLayout(grid)
        actions = FlowLayout(spacing=6)
        reset = QPushButton("기본색으로")
        reset.clicked.connect(lambda: self.apply(None))
        actions.addWidget(reset)
        custom = QPushButton("다른 색 직접 선택…")
        custom.clicked.connect(self.custom)
        actions.addWidget(custom)
        root.addLayout(actions)

    def _selection(self):
        span = self.field.selection_range()
        if span is None:
            QMessageBox.information(self.window(), IO.APP_TITLE, "색을 바꿀 글자를 먼저 드래그해서 선택하세요.")
        return span

    def apply(self, name):
        span = self._selection()
        if span is None:
            return
        if name is None:
            self.field.reset_color(*span)
        else:
            self.field.apply_game_color(*span, name)
        self.on_change()

    def custom(self):
        from PySide6.QtWidgets import QColorDialog
        span = self._selection()
        if span is None:
            return
        chosen = QColorDialog.getColor(QColor("#ffffff"), self, "설명 글자 색 선택")
        if chosen.isValid():
            self.field.apply_color(*span, chosen.name())
            self.on_change()


class InsertReferenceDialogQt(QDialog):
    """태그·파워·기믹 항목을 글에 넣는다 (Tk 의 insert_description_reference 와 같다)."""

    def __init__(self, parent, project):
        super().__init__(parent)
        self.setWindowTitle("태그·파워·기믹 넣기")
        self.token = None
        self.rows = M.description_reference_options(project)
        root = QVBoxLayout(self)
        self.query = QLineEdit()
        self.query.setPlaceholderText("찾기")
        self.query.textChanged.connect(lambda _t: self.refresh())
        root.addWidget(self.query)
        self.listing = QListWidget()
        self.listing.itemDoubleClicked.connect(lambda _it: self.accept_choice())
        root.addWidget(self.listing, 1)
        button = QPushButton("커서 위치에 넣기")
        button.clicked.connect(self.accept_choice)
        root.addWidget(button)
        self.visible = []
        self.refresh()

    def refresh(self):
        q = self.query.text().casefold()
        self.visible = [r for r in self.rows if q in r[0].casefold()]
        self.listing.clear()
        for label, _kind, _ident in self.visible:
            self.listing.addItem(label)
        if self.visible:
            self.listing.setCurrentRow(0)

    def accept_choice(self):
        row = self.listing.currentRow()
        if row < 0:
            return
        _label, kind, ident = self.visible[row]
        self.token = "{MakerName:" + kind + ":" + ident.encode("utf8").hex() + "}"
        self.accept()


class InsertNumberDialogQt(QDialog):
    """효과·원본·블록의 수치를 글에 넣는다 (Tk 의 insert_description_number 와 같다)."""

    def __init__(self, parent, project, item):
        super().__init__(parent)
        self.setWindowTitle("설명에 수치 넣기")
        self.token = None
        self.project = project
        self.item = item
        self.options = {"직접 입력한 기본·강화 수치": None}
        for effect in item.get("effects", []):
            kind = effect.get("kind")
            name = M.VAR_NAME.get(kind)
            if kind == "power":
                name = M.power_meta(project, effect.get("power"))["var"]
            if name:
                self.options[f"효과 수치: {name} ({effect.get('amount', 0)} → {effect.get('amount', 0) + effect.get('upgrade', 0)})"] = \
                    "{" + name + ":diff()}"
        for value in item.get("raw_vars", []):
            name = value.get("name", "")
            if name:
                self.options["원본 수치: " + name] = "{" + name + ":diff()}"
        for label, block, path in M.block_description_values(item):
            self.options["블록 수치: " + label] = (block, path)
        root = QVBoxLayout(self)
        self.picker = QComboBox()
        self.picker.addItems(list(self.options))
        root.addWidget(self.picker)
        grid = QHBoxLayout()
        self.base = QLineEdit("0")
        self.upgraded = QLineEdit("0")
        for text, box in (("기본 수치", self.base), ("강화 수치", self.upgraded)):
            grid.addWidget(QLabel(text))
            grid.addWidget(box)
        root.addLayout(grid)
        root.addWidget(QLabel("직접 입력한 수치는 설명에만 표시됩니다. 실제 효과는 효과/블록에서 수정하세요."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept_choice)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    def accept_choice(self):
        token = self.options[self.picker.currentText()]
        if token is None:
            try:
                base, upgraded = (self._number(box.text()) for box in (self.base, self.upgraded))
            except ValueError:
                QMessageBox.warning(self, IO.APP_TITLE, "숫자를 입력하세요.")
                return
            token = "{IfUpgraded:show:" + upgraded + "|" + base + "}"
        if isinstance(token, tuple):
            block, path = token
            ident = block.setdefault("description_id", uuid.uuid4().hex)
            token = "{BlockValue:" + ident + ":" + ".".join(path) + "}"
        self.token = token
        self.accept()

    @staticmethod
    def _number(text):
        text = text.strip()
        return str(float(text)) if "." in text else str(int(text))

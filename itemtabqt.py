"""'카드 · 유물 · 물약 · 파워' 탭의 Qt 版. 목록(찾기·새로 만들기·복제·삭제), 기본 칸, 설명·그림·추가 C# 코드, 미리보기.

종류마다 칸만 다르고 나머지는 같다. 효과 목록, 블록, 사용 조건도 여기서 편집한다.
여기서 고친 값은 그대로 저장되고, 이 칸들의 값은 건드리지 않는다.
"""
import copy
import os

from PySide6.QtCore import QMimeData, QRect, QSize, Qt
from PySide6.QtGui import QColor, QDrag, QFont, QImage, QKeySequence, QPainter, QPixmap, QShortcut
from PySide6.QtWidgets import QStyle, QStyledItemDelegate
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QComboBox, QDialog, QFileDialog, QGridLayout, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QRadioButton, QButtonGroup, QScrollArea, QSpinBox, QSplitter,
                               QVBoxLayout, QWidget)

import blockcode as B
import cardframe as CF
import cardkind as CK
import gimmick as GM
import gimmickrules as GR
import modgen as M
import preview_qt as PQ
import projectio as IO
from effectqt import EffectListQt
from modifierqt import ModifierListQt
from bulkqt import BulkEditDialogQt
from clonepanelqt import ClonePanelQt
from cardeventqt import CardEventPanelQt, EVENTS
import previewcore as PV
from PySide6.QtWidgets import QButtonGroup, QHBoxLayout, QPushButton, QRadioButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget
from slotqt import SlotDialogQt
from types import SimpleNamespace
from descriptionqt import DescriptionEditQt, GameColorBar, InsertNumberDialogQt, InsertReferenceDialogQt
from formqt import FieldsMixin, fill, label as _label
import qtkit as Q
from flowlayout import FlowLayout

LANGS = [("ko", "한국어"), ("en", "영어"), ("zh", "중국어 간체")]
INT_RANGE = (-9999, 9999)     # 프로젝트 값을 위젯이 고쳐 쓰지 않도록 넓게 둔다 (Tk 는 입력한 값을 그대로 둔다)
PREVIEW_W, PREVIEW_H = 320, 460


# ---------------------------------------------------------------------------
# 화면과 무관한 규칙 (Tk 앱의 App.all_ids · rename_ref 와 같다)
# ---------------------------------------------------------------------------
def all_ids(project):
    ids = {c["id"] for k in ("cards", "relics", "potions", "powers") for c in project[k]}
    g = project.get("gimmicks") or {}
    for group in ("tags", "summons", "orbs", "effects", "buttons", "pets"):
        ids |= {x["id"] for x in g.get(group, [])}
    ids.add(project["character"]["id"])
    return ids


def unique_id(project, base):
    """이미 있으면 _b, _c ... 를 붙인다 (ID 에는 숫자를 쓸 수 없으므로 영문 접미사)."""
    used = all_ids(project)
    if base not in used:
        return base
    letters = "abcdefghijklmnopqrstuvwxyz"
    i = 2
    while True:
        suffix, n = "", i
        while n:
            n, r = divmod(n - 1, 26)
            suffix = letters[r] + suffix
        candidate = f"{base}_{suffix}"
        if candidate not in used:
            return candidate
        i += 1


def rename_ref(project, kind, old, new):
    """ID 가 바뀌거나 항목이 지워졌을 때 다른 곳의 참조를 맞춘다.

    파워를 지울 때는 아무것도 바꾸지 않고, 그 파워를 쓰는 효과 수를 돌려준다 (0이면 안전).
    """
    M.rename_description_references(project, kind, old, new)
    for ch in [project["character"]] + M.imported_characters(project):
        if kind == "card":
            if new is None:
                ch["deck"] = [d for d in ch.get("deck", []) if d["card"] != old]
            else:
                for d in ch.get("deck", []):
                    if d["card"] == old:
                        d["card"] = new
        elif kind == "relic":
            ch["relics"] = [new if r == old else r for r in ch.get("relics", []) if not (new is None and r == old)]
    if kind == "relic":
        for r in project["relics"]:
            if r.get("upgrade_relic") == old:
                r["upgrade_relic"] = new or ""
    elif kind == "power":
        keys = ("power", "cond_power", "scale_power")
        if new is None:
            return sum(1 for k in ("cards", "relics", "potions", "powers") for it in project[k]
                       for e in it.get("effects", []) if f"c:{old}" in (e.get(f) for f in keys))
        for k in ("cards", "relics", "potions", "powers"):
            for it in project[k]:
                for e in it.get("effects", []):
                    for f in keys:
                        if e.get(f) == f"c:{old}":
                            e[f] = f"c:{new}"
    return 0


def ask_yes_no(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


def show_warning(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


def drop_order(count, selected, row):
    """고른 줄(selected)들을 row 자리 앞으로 한꺼번에 옮긴 새 순서 (옛 줄 번호의 목록).

    row 는 놓은 자리의 줄 번호 (count 면 맨 끝). 고른 줄은 원래 순서대로 함께 간다.
    """
    chosen = sorted(set(selected))
    rest = [r for r in range(count) if r not in chosen]
    before = sum(1 for r in chosen if r < row)
    cut = row - before
    return rest[:cut] + chosen + rest[cut:]


CARD_ROWS_MIME = "application/x-sts2-card-rows"   # 이 목록에서 끈 카드들이라는 표시


class _ReorderList(Q.BandSelectMixin, QListWidget):
    """카드 목록. 고른 여러 장을 한꺼번에 끌어 옮긴다.

    Qt 기본 끌기(InternalMove)는 고른 줄을 옮긴 뒤 원래 줄을 지워서, 여러 장을 끌면 장수가 줄거나
    한 장만 옮겨진 것처럼 보였다. 그래서 기본 끌기를 끄고 끌기를 직접 시작한다.
    놓을 때는 자리를 계산해 on_drop(rows, selected_rows) 로 넘긴다 (rows: 새 순서의 줄 번호).
    """

    def __init__(self, on_drop, parent=None):
        super().__init__(parent)
        self.on_drop = on_drop
        self._press = None
        self._line = Q.DropLine(self.viewport())                          # 놓을 자리 줄
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)   # 끌기는 아래에서 직접 시작한다

    def _band_items(self):
        return [self.item(i) for i in range(self.count())]

    def mousePressEvent(self, event):
        self._press = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None and event.buttons() & Qt.MouseButton.LeftButton:
            moved = (event.position().toPoint() - self._press).manhattanLength()
            index = self.indexAt(self._press)
            if (moved >= QApplication.startDragDistance() and index.isValid()
                    and self.item(index.row()).isSelected()):
                self._press = None
                self._start_drag()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        mime = QMimeData()
        mime.setData(CARD_ROWS_MIME, b"1")
        drag = QDrag(self)
        drag.setMimeData(mime)
        rects = [self.visualItemRect(self.item(r)) for r in range(self.count()) if self.item(r).isSelected()]
        picture, grab_at = Q.drag_picture(self, rects)
        if picture is not None:
            drag.setPixmap(picture)
            drag.setHotSpot(grab_at)
        drag.exec(Qt.DropAction.CopyAction)      # 옮기는 일은 놓을 때 on_drop 에서 한다 (줄을 지우는 일은 없다)
        self._line.clear()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(CARD_ROWS_MIME):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
        else:
            super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(CARD_ROWS_MIME):
            event.setDropAction(Qt.DropAction.CopyAction)
            event.accept()
            self._show_drop_line(event.position().toPoint())
        else:
            super().dragMoveEvent(event)

    def dragLeaveEvent(self, event):
        self._line.clear()
        super().dragLeaveEvent(event)

    def _show_drop_line(self, pos):
        """놓으면 들어갈 자리에 얇은 줄을 긋는다 (dropEvent 와 같은 규칙)."""
        target = self.indexAt(pos)
        if target.isValid():
            rect = self.visualRect(target)
            y = rect.bottom() if pos.y() > rect.center().y() else rect.top()
            self._line.show_at(QRect(rect.left(), y - 2, rect.width(), 4))
        elif self.count():
            rect = self.visualItemRect(self.item(self.count() - 1))
            self._line.show_at(QRect(rect.left(), rect.bottom() - 1, rect.width(), 4))
        else:
            self._line.clear()

    def dropEvent(self, event):
        self._line.clear()
        if not event.mimeData().hasFormat(CARD_ROWS_MIME):
            return super().dropEvent(event)
        pos = event.position().toPoint()
        target = self.indexAt(pos)
        if target.isValid():
            center = self.visualRect(target).center().y()
            row = target.row() + (1 if pos.y() > center else 0)
        else:
            row = self.count()
        selected = [r for r in range(self.count()) if self.item(r).isSelected()]
        event.setDropAction(Qt.DropAction.CopyAction)    # 옮기는 일은 아래에서 한다 (Qt 가 줄을 지우지 않게)
        event.accept()
        if selected:
            self.on_drop(drop_order(self.count(), selected, row), selected)


# ---------------------------------------------------------------------------
# 화면
# ---------------------------------------------------------------------------
class _CardRowDelegate(QStyledItemDelegate):
    """카드 목록 한 줄: 비용 원 · 이름 · 종류. 줄 밑에 희귀도 색 밑줄."""
    ROW_H = 32                   # 한 줄 28 + 밑줄 4
    COST_D = 20
    UNDERLINE_H = 4

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, painter, option, index):
        i = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(i, int) or not (0 <= i < len(self.tab.items)):
            return super().paint(painter, option, index)
        card = self.tab.items[i]
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect
        ink = QColor(option.palette.highlightedText().color() if selected else Q.C["text"])
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if selected:
            painter.fillRect(rect, option.palette.highlight())
        text_h = rect.height() - self.UNDERLINE_H
        mid = rect.top() + text_h // 2
        x, d = rect.left() + 8, self.COST_D
        if card.get("no_cost"):
            cost = "-"
        elif card.get("x_cost"):
            cost = "X"
        else:
            cost = str(int(card.get("cost", 0) or 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#c8553d"))
        painter.drawEllipse(QRect(x, mid - d // 2, d, d))
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(QRect(x, mid - d // 2, d, d), int(Qt.AlignmentFlag.AlignCenter), cost)
        name = card.get("name_ko") or card.get("name_en") or "?"
        kind = M.label_of(M.CARD_TYPES, card.get("type"))
        metrics = painter.fontMetrics()
        tx = x + d + 8
        name_w = metrics.horizontalAdvance(name)
        painter.setPen(ink)
        painter.drawText(QRect(tx, rect.top(), name_w + 4, text_h), int(Qt.AlignmentFlag.AlignVCenter), name)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(Q.C["muted"]) if not selected else ink)
        painter.drawText(QRect(tx + name_w + 12, rect.top(), max(0, rect.right() - tx - name_w - 20), text_h),
                         int(Qt.AlignmentFlag.AlignVCenter), kind)
        rarity = card.get("rarity")
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PV.RARITY_COLORS.get(rarity, "#5d5d5d")))
        painter.drawRect(QRect(rect.left() + 8, rect.bottom() - self.UNDERLINE_H + 1, rect.width() - 16, self.UNDERLINE_H))
        painter.restore()


class _RelicRowDelegate(QStyledItemDelegate):
    """유물 목록 한 줄: 이름 · 희귀도 글, 줄 밑에 희귀도 색 밑줄 (카드 목록과 같은 규칙)."""
    ROW_H = 32                   # 한 줄 28 + 밑줄 4
    UNDERLINE_H = 4

    def __init__(self, tab):
        super().__init__(tab)
        self.tab = tab

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, painter, option, index):
        i = index.data(Qt.ItemDataRole.UserRole)
        if not isinstance(i, int) or not (0 <= i < len(self.tab.items)):
            return super().paint(painter, option, index)
        relic = self.tab.items[i]
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        rect = option.rect
        ink = QColor(option.palette.highlightedText().color() if selected else Q.C["text"])
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        if selected:
            painter.fillRect(rect, option.palette.highlight())
        text_h = rect.height() - self.UNDERLINE_H
        x = rect.left() + 10
        font = painter.font()
        font.setBold(True)
        painter.setFont(font)
        name = relic.get("name_ko") or relic.get("name_en") or "?"
        name_w = painter.fontMetrics().horizontalAdvance(name)
        painter.setPen(ink)
        painter.drawText(QRect(x, rect.top(), name_w + 4, text_h), int(Qt.AlignmentFlag.AlignVCenter), name)
        font.setBold(False)
        painter.setFont(font)
        painter.setPen(QColor(Q.C["muted"]) if not selected else ink)
        label = M.label_of(M.RELIC_RARITIES, relic.get("rarity"))
        painter.drawText(QRect(x + name_w + 12, rect.top(), max(0, rect.right() - x - name_w - 20), text_h),
                         int(Qt.AlignmentFlag.AlignVCenter), label)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(PV.RARITY_COLORS.get(relic.get("rarity"), "#5d5d5d")))
        painter.drawRect(QRect(rect.left() + 8, rect.bottom() - self.UNDERLINE_H + 1, rect.width() - 16, self.UNDERLINE_H))
        painter.restore()


class ItemTabQt(FieldsMixin, QWidget):
    assets_fn = None       # 게임 그림을 읽는 함수 (app 이 넣는다). 없으면 기본 색으로 그린다
    views = None           # 게임 화면 그림 설정 (gameviewqt.GameViews, app 이 넣는다). 없으면 간단한 그림만
    _preview_stale = False # 화면에 없을 때 설정이 바뀌면 보일 때 다시 그린다
    library_fn = None      # 카드 라이브러리 창을 여는 함수 (카드 탭만 쓴다)
    kind = "card"          # card / relic / potion / power
    key = "cards"          # 프로젝트 안의 목록 이름
    noun = "카드"
    image_hint = ""
    note = ""              # 이 탭에서 아직 Tk 앱으로 가야 하는 것 (화면에 그대로 보인다)

    def __init__(self, project, on_change=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.on_change = on_change
        self.cur = None
        self.query = ""
        self._loading = False
        self._fields = {}      # 키 -> (종류, 위젯). 종류: str / int / combo / text / bool

        split = self.split = QSplitter(Qt.Orientation.Horizontal)
        root = QHBoxLayout(self)
        root.addWidget(split)
        split.addWidget(self._list_panel())
        split.addWidget(self._editor_panel())
        preview = self._preview_panel()
        preview.setMaximumWidth(380)               # 미리보기는 적당한 폭, 남는 너비는 편집 칸이 쓴다
        split.addWidget(preview)
        split.setStretchFactor(1, 1)
        split.setSizes([260, 560, 340])
        self.load_project(project)

    # ---- 화면 구성 ----
    def _list_panel(self):
        box = QWidget()
        col = QVBoxLayout(box)
        head = QHBoxLayout()
        title = _label(f"{self.noun} 목록")
        title.setStyleSheet("font-weight: bold;")
        head.addWidget(title)
        self.count_lbl = _label()
        head.addWidget(self.count_lbl)
        head.addStretch(1)
        col.addLayout(head)
        self.build_list_filters(col)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"{self.noun} 찾기 (이름·ID)")
        self.search.textChanged.connect(self.set_query)
        col.addWidget(self.search)
        self.listing = _ReorderList(self._list_dropped)
        if self.kind == "card":
            self.listing.setItemDelegate(_CardRowDelegate(self))   # 카드 줄: 비용 · 이름 · 종류 · 희귀도
        elif self.kind == "relic":
            self.listing.setItemDelegate(_RelicRowDelegate(self))  # 유물 줄: 이름 · 희귀도 · 밑줄
        self.listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)   # Ctrl/Shift 로 여러 장
        self.listing.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)          # 끌어서 순서 바꾸기
        self.listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listing.currentRowChanged.connect(self._row_changed)
        self.listing.model().rowsMoved.connect(lambda *_a: self._list_reordered())
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.listing, self.delete)
        col.addWidget(self.listing, 1)
        buttons = FlowLayout(spacing=6)        # 목록 단추는 칸이 좁으면 다음 줄로 넘어간다
        for text, slot in (("＋ 새로 만들기", self.add), ("복제", self.duplicate), ("삭제", self.delete),
                           ("한꺼번에…", self.bulk_edit)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        col.addLayout(buttons)
        return box

    def _editor_panel(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)   # 칸이 창보다 넓으면 가로 스크롤 (잘리지 않게)
        body = QWidget()
        col = QVBoxLayout(body)
        self.editor_title = _label(self.noun + " 편집")
        self.editor_title.setStyleSheet("font-weight: bold; font-size: 14px;")
        col.addWidget(self.editor_title)
        if self.note:
            note = _label(self.note)
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {Q.C['muted']};")
            col.addWidget(note)
        self.form = QWidget()
        grid = QGridLayout(self.form)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.build_form(grid)
        col.addWidget(self.form)
        col.addStretch(1)
        scroll.setWidget(body)
        return scroll

    def _preview_panel(self):
        box = QWidget()
        col = QVBoxLayout(box)
        top = QHBoxLayout()
        top.addWidget(_label("미리보기"))
        self._lang_group = QButtonGroup(self)
        self.preview_lang = "ko"
        for i, (value, label) in enumerate(LANGS):
            button = QRadioButton(label)
            button.setChecked(value == "ko")
            button.toggled.connect(lambda on, v=value: on and self.set_preview_lang(v))
            self._lang_group.addButton(button, i)
            top.addWidget(button)
        top.addStretch(1)
        col.addLayout(top)
        self.upgraded = QCheckBox("강화 후 (+)")
        self.upgraded.setVisible(self.kind == "card")
        self.upgraded.toggled.connect(lambda _c: self.update_preview())
        col.addWidget(self.upgraded)
        mode_row = QHBoxLayout()
        self._mode_group = QButtonGroup(self)
        self.mode_game = QRadioButton("게임 화면")
        self.mode_simple = QRadioButton("간단히")
        for i, (button, value) in enumerate(((self.mode_game, "game"), (self.mode_simple, "simple"))):
            button.toggled.connect(lambda on, v=value: on and self._pick_mode(v))
            self._mode_group.addButton(button, i)
            mode_row.addWidget(button)
        self.stacks_label = _label("스택 수")
        self.stacks_spin = QSpinBox()
        self.stacks_spin.setRange(1, 99)
        self.stacks_spin.valueChanged.connect(self._pick_stacks)
        mode_row.addWidget(self.stacks_label)
        mode_row.addWidget(self.stacks_spin)
        self.stacks_label.setVisible(self.kind == "power")
        self.stacks_spin.setVisible(self.kind == "power")
        mode_row.addStretch(1)
        col.addLayout(mode_row)
        self.preview_note = _label("")
        self.preview_note.setWordWrap(True)
        col.addWidget(self.preview_note)
        self.preview = _label()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.preview)
        col.addStretch(1)
        return box

    def _common(self, g, row):
        """효과 목록, 설명 직접 입력(3개 언어), 그림, 추가 C# 코드: 네 탭이 같다."""
        self.effects = EffectListQt(self.kind, lambda: self.project, self._current_item, self._effects_changed)
        self.effects.on_original = self.edit_original
        g.addWidget(_label("효과"), row, 0, Qt.AlignmentFlag.AlignTop)
        if self.kind == "card":
            g.addWidget(self._card_effect_tabs(), row, 1, 1, 3)
        else:
            g.addWidget(self.effects, row, 1, 1, 3)
        row += 1
        self.clone = ClonePanelQt(self)
        g.addWidget(self.clone, row, 0, 1, 4)
        row += 1
        g.addWidget(_label("설명은 효과에서 자동으로 만들어집니다. 직접 쓰고 싶을 때만 채우세요."), row, 0, 1, 4)
        row += 1
        for lang, text in LANGS:
            self._rich(g, row, f"설명 직접 입력 ({text})", "desc_" + lang, lang, False)
            row += 2                          # 글 한 줄 + 도구 줄
            if self.kind == "card":
                self._rich(g, row, f"강화 설명 직접 입력 ({text})", "upgrade_desc_" + lang, lang, True)
                row += 2
        self._image(g, row)
        row += 1
        self._text(g, row, "고급: 추가 C# 코드", "extra_code", height=6, mono=True)

    # ---- 목록 ----
    @property
    def items(self):
        return self.project[self.key]

    def row_text(self, it):
        return f"{it.get('name_ko') or it.get('name_en') or '?'}  ({it.get('id', '')})"

    def search_fields(self, it):
        return (it.get("name_ko"), it.get("name_en"), it.get("name_zh"), it.get("id"), it.get("desc_ko"))

    def _visible(self):
        q = self.query.casefold().strip()
        return [i for i, it in enumerate(self.items)
                if self._extra_ok(it) and (not q or any(q in str(v or "").casefold() for v in self.search_fields(it)))]

    def _extra_ok(self, it):
        return True

    def _scoped(self):
        return bool(self.query)

    def build_list_filters(self, col):
        pass

    def load_project(self, project):
        """프로젝트를 바꿔 끼운다 (열기·되돌리기). 바뀐 것으로 치지 않는다."""
        self.project = project
        self.cur = None
        self.refresh_list(0)

    def refresh_list(self, select=None):
        vis = self._visible()
        self.listing.blockSignals(True)
        try:
            self.listing.clear()
            for i in vis:
                row = QListWidgetItem(self.row_text(self.items[i]))
                row.setData(Qt.ItemDataRole.UserRole, i)
                self.listing.addItem(row)
        finally:
            self.listing.blockSignals(False)
        total = len(self.items)
        self.count_lbl.setText(f"{len(vis)} / {total}" if self._scoped() else f"{total}개")
        if not vis:
            self.cur = None
            self.form.setEnabled(False)
            self.effects.set([])
            self.update_preview()
            return
        want = select if select is not None else (self.cur if self.cur is not None else 0)
        target = want if want in vis else min(vis, key=lambda v: abs(v - want))
        self.listing.blockSignals(True)
        self.listing.setCurrentRow(vis.index(target))
        self.listing.blockSignals(False)
        self._load_item(target)

    def set_query(self, text):
        self.query = text
        self.refresh_list(self.cur)

    def _row_changed(self, row):
        if row < 0:
            return
        idx = self.listing.item(row).data(Qt.ItemDataRole.UserRole)
        if idx != self.cur:
            self._load_item(idx)

    def _leave_search(self):
        """새 항목이 검색에 안 걸릴 수 있으니 검색을 지운다."""
        if self.query:
            self.search.setText("")

    def _refresh_row(self):
        for r in range(self.listing.count()):
            row = self.listing.item(r)
            if row.data(Qt.ItemDataRole.UserRole) == self.cur:
                row.setText(self.row_text(self.items[self.cur]))
                return

    # ---- 편집 ----
    def _load_item(self, idx):
        self.cur = idx
        it = self.items[idx]
        self.editor_title.setText(it.get("name_ko") or it.get("id") or self.noun + " 편집")
        self.form.setEnabled(True)
        self._loading = True
        try:
            self.load_extra(it)              # 고를 목록을 먼저 채운 뒤에 값을 넣는다
            self.item_to_fields(it)
            self.effects.set(it["effects"])     # 목록은 항목의 효과 리스트를 직접 고친다 (Tk 와 같다)
            self.clone.set(it)
        finally:
            self._loading = False
        self._sync_controls(it)
        self.update_preview()

    def _rich(self, g, row, text, key, lang, upgraded):
        """설명 글 한 칸 (row) + 도구 줄 (row + 1): 수치 넣기 · 태그·파워·기믹 넣기 · 게임 색."""
        g.addWidget(_label(text), row, 0, Qt.AlignmentFlag.AlignTop)
        editor = DescriptionEditQt(lambda: (self.project, self._current_item(), lang, upgraded))
        editor.textChanged.connect(self._edited)
        g.addWidget(editor, row, 1, 1, 3)
        self._fields[key] = ("rich", editor)
        tools = QWidget()
        bar = QHBoxLayout(tools)
        bar.setContentsMargins(0, 0, 0, 0)
        if self.kind == "card" or upgraded:
            number = QPushButton("수치 넣기…")
            number.clicked.connect(lambda _=False, e=editor: self._insert_number(e))
            bar.addWidget(number)
        reference = QPushButton("태그·파워·기믹 넣기…")
        reference.clicked.connect(lambda _=False, e=editor: self._insert_reference(e))
        bar.addWidget(reference)
        bar.addWidget(GameColorBar(editor, self._edited))
        bar.addStretch(1)
        g.addWidget(tools, row + 1, 1, 1, 3)
        return editor

    def _insert_number(self, editor):
        if self.cur is None:
            return
        dialog = InsertNumberDialogQt(self, self.project, self.items[self.cur])
        if dialog.exec() and dialog.token:
            editor.insert_token(dialog.token)

    def _insert_reference(self, editor):
        dialog = InsertReferenceDialogQt(self, self.project)
        if dialog.exec() and dialog.token:
            editor.insert_token(dialog.token)

    def edit_original(self, index, reanalyze=False):
        """원본 효과(가져온 항목의 원본 코드)를 블록으로 고친다. '다시 분석'은 원본 DLL 을 다시 읽는다 (Tk 와 같다)."""
        from blockqt import edit_blocks
        from originalqt import decompose_original
        if self.cur is None or not self.items[self.cur].get("clone"):
            return
        item = self.items[self.cur]
        app = self.window()
        settings = getattr(app, "settings", None) or {}
        log = getattr(app, "log", print)
        draft = copy.deepcopy(item)
        effect = item["effects"][index]
        blocks = effect.get("blocks", [])

        def decompose():
            return decompose_original(self.project, settings, draft, log=log)

        if reanalyze or [b.get("op") for b in blocks] == ["original_play"]:
            try:
                got, info = decompose()
            except Exception as exc:  # noqa: BLE001 - 못 풀면 원본 실행 블록 그대로 연다
                show_warning(self, f"원본 코드를 읽지 못했습니다.\n\n{type(exc).__name__}: {exc}\n\n현재 효과는 유지됩니다.")
            else:
                if got:
                    blocks = got
                else:
                    reason = str(info or "").strip() or "변환 이유가 제공되지 않았습니다."
                    show_warning(self, f"원본 효과를 블록으로 풀지 못했습니다.\n\n{reason}\n\n원래 효과 블록은 유지됩니다.")
        host = SimpleNamespace(kind=self.kind, cur=self.cur, _notify=lambda: None, refresh_list=lambda _i: None)
        panel = ClonePanelQt(host)
        panel.set(draft, inside_editor=True)
        result = edit_blocks(self, self.project, self.kind, draft, blocks, show_text=False, on_decompose=decompose,
                             top_widget=panel)
        if result is None:
            return
        item["raw_vars"] = draft.get("raw_vars", [])
        clone, dclone = item["clone"], draft["clone"]
        clone["pool"] = dclone.get("pool", "mine")
        item["pool_character"] = draft.get("pool_character", item.get("pool_character", ""))
        clone["usings"] = dclone.get("usings", clone.get("usings", []))
        clone["body"] = dclone.get("body", clone.get("body", ""))
        clone["upgrade_body"] = dclone.get("upgrade_body", clone.get("upgrade_body", ""))
        effect["blocks"] = result["blocks"]
        effect["code"] = result["code"] or "// 실행할 블록 없음"
        self.effects.refresh(index)
        self._effects_changed()

    def _editor_for(self, item):
        """칸 편집 창이 항목의 종류·이름을 알 수 있도록 넘기는 작은 물건."""
        return SimpleNamespace(project=self.project, owner_kind=self.kind, item=item, allow_event=False)

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

    def _current_item(self):
        return self.items[self.cur] if self.cur is not None and self.cur < len(self.items) else {}

    def _effects_changed(self):
        self._refresh_row()
        self.update_preview()
        self._notify()

    def _edited(self, *_):
        if self._loading or self.cur is None:
            return
        self.write_item()
        self._refresh_row()
        self.update_preview()
        self._notify()

    def write_item(self):
        """화면의 값을 프로젝트에 쓴다 (Tk 앱의 ItemTab.changed 와 같은 순서)."""
        it = self.items[self.cur]
        old_id = it["id"]
        self.fields_to_item(it)
        self.dump_extra(it)
        if old_id != it["id"]:
            rename_ref(self.project, self.kind, old_id, it["id"])

    def _notify(self):
        if self.on_change:
            self.on_change()

    def update_preview(self):
        if self.cur is None or self.cur >= len(self.items):
            self.preview.clear()
            self.preview_note.setText("")
            return
        if self.views is not None and self.views.mode == "game":
            img, err = self.views.image(self.kind, self.items[self.cur], self.preview_lang,
                                        self.upgraded.isChecked(), self.views.stacks)
            if img is not None:
                pixmap = self.views.pixmap(img).scaled(PREVIEW_W, PREVIEW_H, Qt.AspectRatioMode.KeepAspectRatio,
                                                       Qt.TransformationMode.SmoothTransformation)
                self.preview.setPixmap(pixmap)
                self.preview_note.setText(f"게임 파일({self.views.version()})의 실제 틀·글꼴로 합성한 화면입니다.")
                return
            self.preview_note.setText(f"게임 화면을 만들 수 없어 간단히 표시합니다: {err}")
        else:
            self.preview_note.setText("")
        image = QImage(PREVIEW_W, PREVIEW_H, QImage.Format.Format_ARGB32)
        image.fill(QColor("#121318"))
        painter = QPainter(image)
        try:
            PQ.render_item(painter, self.project, self.kind, self.items[self.cur], 10, 10, 1.0,
                           self.preview_lang, upgraded=self.upgraded.isChecked(), stacks=self._stacks())
        except Exception as e:  # noqa: BLE001 - 미리보기가 실패해도 편집은 계속된다
            painter.setPen(QColor("#ff6666"))
            painter.drawText(image.rect(), int(Qt.AlignmentFlag.AlignCenter), f"미리보기 오류:\n{e}")
        finally:
            painter.end()
        self.preview.setPixmap(QPixmap.fromImage(image))

    def set_views(self, views):
        """게임 화면 설정을 붙인다: 모드·스택 수가 바뀌면 이 탭의 그림도 다시 그린다."""
        if self.views is not None:
            self.views.changed.disconnect(self._views_changed)
        self.views = views
        views.changed.connect(self._views_changed)
        self._sync_mode_radios()
        self.update_preview()

    def _stacks(self):
        return self.views.stacks if self.views is not None else 3

    def _sync_mode_radios(self):
        mode = self.views.mode if self.views is not None else "simple"
        _check_quiet(self.mode_game, mode == "game")
        _check_quiet(self.mode_simple, mode != "game")
        self.stacks_spin.blockSignals(True)
        self.stacks_spin.setValue(self._stacks())
        self.stacks_spin.blockSignals(False)

    def _pick_mode(self, mode):
        if self.views is not None:
            self.views.set_mode(mode)
        self._sync_mode_radios()
        self.update_preview()

    def _pick_stacks(self, value):
        if self.views is not None:
            self.views.set_stacks(value)
        self.update_preview()

    def _views_changed(self):
        self._sync_mode_radios()
        if self.isVisible():
            self._preview_stale = False
            self.update_preview()
        else:
            self._preview_stale = True

    def showEvent(self, event):
        super().showEvent(event)
        if self._preview_stale:
            self._preview_stale = False
            self.update_preview()

    def set_focus_layout(self, focused):
        """편집에 집중: 목록과 미리보기를 숨기고 편집 칸만 보인다 (Tk 의 set_editor_layout 과 같다)."""
        self.split.widget(0).setVisible(not focused)
        self.split.widget(2).setVisible(not focused)

    def set_preview_lang(self, lang):
        self.preview_lang = lang
        self.update_preview()

    # ---- 추가 · 복제 · 삭제 ----
    def new_item(self, iid):
        raise NotImplementedError

    def add(self):
        self._leave_search()
        self.items.append(self.new_item(unique_id(self.project, "new_" + self.kind)))
        self.refresh_list(len(self.items) - 1)
        self._notify()

    def duplicate(self):
        if self.cur is None:
            return
        it = copy.deepcopy(self.items[self.cur])
        it["id"] = unique_id(self.project, it["id"])
        it["name_ko"] = (it.get("name_ko") or "") + " (복사)"
        pos = self.cur + 1
        self.items.insert(pos, it)
        self._leave_search()
        self.refresh_list(pos)
        self._notify()

    def selected_indices(self):
        """고른 항목들의 번호 (목록에서 고른 것 전부, 없으면 현재 항목)."""
        picked = sorted({item.data(Qt.ItemDataRole.UserRole) for item in self.listing.selectedItems()})
        if picked:
            return picked
        return [self.cur] if self.cur is not None else []

    def bulk_edit(self):
        picked = self.selected_indices()
        if picked:
            BulkEditDialogQt(self, picked, self).exec()

    def _list_reordered(self):
        """Qt 가 목록 안에서 줄을 옮겼을 때 (코드에서 옮길 때 포함). 끌어 옮긴 순서를 그대로 프로젝트에 반영한다."""
        rows = range(self.listing.count())
        picked = [self.listing.item(r).data(Qt.ItemDataRole.UserRole) for r in rows if self.listing.item(r).isSelected()]
        self._apply_order([self.listing.item(r).data(Qt.ItemDataRole.UserRole) for r in rows], picked)

    def _list_dropped(self, rows, selected_rows):
        """사용자가 끌어 놓았을 때: rows 는 새 순서(지금 줄 번호), selected_rows 는 고른 줄 번호."""
        if self._scoped():           # 검색·필터가 걸려 있으면 옮기지 않는다 (목록은 그대로 둔다)
            return
        picked = [self.listing.item(r).data(Qt.ItemDataRole.UserRole) for r in selected_rows]
        self._apply_order([self.listing.item(r).data(Qt.ItemDataRole.UserRole) for r in rows], picked)

    def _apply_order(self, order, picked):
        """order: 새 순서 (옛 번호 목록). picked: 옮긴 뒤에도 고른 상태로 둘 옛 번호들. 검색 중이면 옮기지 않는다."""
        if self._scoped():
            self.refresh_list(self.cur)
            return
        n = len(self.items)
        if sorted(order) != list(range(n)):
            self.refresh_list(self.cur)
            return
        if order == list(range(n)):
            return
        old = list(self.items)
        self.items[:] = [old[i] for i in order]
        self._notify()
        self.refresh_list(order.index(self.cur) if self.cur in order else None)
        for new_row in (order.index(i) for i in picked):   # 목록을 다시 채우면서 지워진 선택을 되살린다
            self.listing.item(new_row).setSelected(True)

    def delete(self):
        picked = self.selected_indices()
        if not picked:
            return
        if len(picked) == 1:
            name = self.items[picked[0]].get("name_ko") or self.items[picked[0]]["id"]
            question = f"{self.noun} '{name}'을(를) 삭제할까요?\n(Ctrl+Z 로 되돌릴 수 있습니다)"
        else:
            question = f"{self.noun} {len(picked)}개를 삭제할까요?\n(Ctrl+Z 로 되돌릴 수 있습니다)"
        if not ask_yes_no(self, question):
            return
        in_use = 0
        for i in picked:
            in_use += rename_ref(self.project, self.kind, self.items[i]["id"], None)
        if in_use:
            show_warning(self, f"이 파워를 쓰는 효과가 {in_use}개 있습니다. 검사에서 위치를 확인해 고치세요.")
        for i in reversed(picked):
            del self.items[i]
        self.refresh_list(min(picked[0], len(self.items) - 1))
        self._notify()

    # ---- 종류별 훅 ----
    def build_form(self, g):
        raise NotImplementedError

    def load_extra(self, it):
        pass

    def dump_extra(self, it):
        pass

    def _sync_controls(self, it):
        pass


class CardTabQt(ItemTabQt):
    kind, key, noun = "card", "cards", "카드"
    image_hint = "250×190 권장"
    note = "블록이 있는 효과는 블록이 만든 결과를 보여 줍니다. 효과는 블록 편집에서 고칩니다."

    def row_text(self, it):
        """목록에서 바로 보이는 것: 이름 아래에 비용 · 종류 · 희귀도."""
        name = it.get("name_ko") or it.get("name_en") or "?"
        cost = "없음" if it.get("no_cost") else ("X" if it.get("x_cost") else int(it.get("cost", 0) or 0))
        kind = M.label_of(M.CARD_TYPES, it.get("type"))
        rarity = M.label_of(M.CARD_RARITIES, it.get("rarity"))
        return f"{name}  ({it.get('id', '')})\n비용 {cost} · {kind} · {rarity}"

    def build_form(self, g):
        self._kw = {}
        self._tag_box = {}
        self._tag_sig = None
        self._cond_btns = {}
        self._str(g, 0, 0, "ID (영문 소문자_)", "id")
        self._str(g, 0, 2, "이름 (한국어)", "name_ko")
        self._str(g, 1, 0, "이름 (영어)", "name_en")
        self._str(g, 1, 2, "이름 (중국어 간체)", "name_zh")
        self._kind_box = QComboBox()
        self._kind_box.currentIndexChanged.connect(self._kind_edited)
        kind_row = QHBoxLayout()
        kind_row.addWidget(self._kind_box, 1)
        kind_row.addWidget(_small_button("+ 종류 만들기", self.create_card_kind))
        kind_holder = QWidget()
        kind_holder.setLayout(kind_row)
        g.addWidget(_label("종류"), 2, 0)
        g.addWidget(kind_holder, 2, 1)
        self._combo(g, 2, 2, "희귀도", "rarity", M.CARD_RARITIES)
        self._int(g, 3, 0, "비용", "cost")
        self._int(g, 3, 2, "강화 후 비용", "upgrade_cost")
        self._combo(g, 4, 0, "대상", "target", M.CARD_TARGETS)
        self._combo(g, 4, 2, "태그", "tag", M.CARD_TAGS)
        self._combo(g, 5, 0, "강화 시 키워드 추가", "upgrade_add_keyword", [("", "없음")] + M.CARD_KEYWORDS)
        self._combo(g, 5, 2, "강화 시 키워드 제거", "upgrade_remove_keyword", [("", "없음")] + M.CARD_KEYWORDS)
        keywords = QGridLayout()          # 가로로 길면 창이 좁을 때 밀려 나므로 4칸씩 나눈다
        for n, (key, text) in enumerate(M.CARD_KEYWORDS):
            box = QCheckBox(text)
            box.toggled.connect(self._edited)
            keywords.addWidget(box, n // 4, n % 4)
            self._kw[key] = box
        g.addWidget(_label("키워드"), 6, 0, Qt.AlignmentFlag.AlignTop)
        g.addLayout(keywords, 6, 1, 1, 3)
        flags = QGridLayout()
        flags.addWidget(self._check("no_cost", "비용 없음 · 사용 불가"), 0, 0)
        flags.addWidget(self._check("x_cost", "X 비용"), 0, 1)
        flags.addWidget(self._check("x_plus_up", "강화하면 X+1"), 0, 2)
        g.addWidget(_label("특수"), 7, 0, Qt.AlignmentFlag.AlignTop)
        g.addLayout(flags, 7, 1, 1, 3)
        # 카드 전용 캐릭터 · 카드 틀
        self._pool_box = QComboBox()
        self._pool_box.currentIndexChanged.connect(self._edited)
        self._fields["pool_character"] = ("combo", self._pool_box)
        g.addWidget(_label("카드 전용 캐릭터"), 8, 0)
        g.addWidget(self._pool_box, 8, 1)
        self._frame_box = QComboBox()
        self._frame_box.currentIndexChanged.connect(self._edited)
        self._fields["frame_style"] = ("combo", self._frame_box)
        frame_row = QHBoxLayout()
        frame_row.addWidget(self._frame_box, 1)
        frame_edit = _small_button("편집…", self.edit_frames)
        frame_row.addWidget(frame_edit)
        frame_holder = QWidget()
        frame_holder.setLayout(frame_row)
        g.addWidget(_label("테두리 디자인"), 8, 2)
        g.addWidget(frame_holder, 8, 3)
        # 자원 · 별 비용
        self._res_box = QComboBox()
        self._res_box.currentIndexChanged.connect(self._edited)
        self._fields["res_power"] = ("combo", self._res_box)
        g.addWidget(_label("자원 비용 (파워)"), 9, 0)
        g.addWidget(self._res_box, 9, 1)
        self._int(g, 9, 2, "자원 비용 수치", "res_cost")
        self._int(g, 10, 0, "별 비용", "star_cost")
        self._int(g, 10, 2, "강화 시 별 비용 ±", "star_cost_up")
        g.addWidget(self._check("star_x", "별 X (가진 별 전부 → 블록 값 'X')"), 11, 0, 1, 4)
        # 태그 (기믹 탭에서 만든 것)
        self._tag_holder = QWidget()
        self._tag_layout = QHBoxLayout(self._tag_holder)
        self._tag_layout.setContentsMargins(0, 0, 0, 0)
        g.addWidget(_label("키워드 태그 (기믹)"), 12, 0, Qt.AlignmentFlag.AlignTop)
        g.addWidget(self._tag_holder, 12, 1, 1, 3)
        # 사용 조건 · 금색 테두리 (조건 편집기는 Tk 앱)
        for row, key, text in ((13, "play_cond", "사용 조건"), (14, "glow_cond", "금색 테두리 조건")):
            button = _small_button("(없음) ✎", lambda _=False, k=key: self.edit_cond(k))
            self._cond_btns[key] = button
            g.addWidget(_label(text), row, 0)
            g.addWidget(button, row, 1, 1, 2)
        self._common(g, 15)

    # ---- 목록 칸 (카드 전용 캐릭터 고르기) ----
    def build_list_filters(self, col):
        library = _small_button("카드 라이브러리…", lambda: self.library_fn() if self.library_fn else None)
        library.setToolTip("원작·참고 프로젝트에서 카드를 골라 가져오거나 이 카드에 적용합니다.")
        col.addWidget(library)
        self._pool_filter = QComboBox()
        self._pool_filter.currentIndexChanged.connect(lambda _i: self.refresh_list(self.cur))
        col.addWidget(self._pool_filter)

    def _sync_characters(self):
        """캐릭터 목록을 다시 채운다 (Tk 의 _sync_character_controls 와 같다). 고른 값은 그대로 둔다."""
        chars = M.card_characters(self.project)
        self._card_chars = chars
        main = self.project["character"]
        default_label = (f"메인 캐릭터 · {M.text(main, 'name', 'ko')}" if main.get("enabled")
                         else "공용 풀 (캐릭터 미지정)")
        self._default_label = default_label
        filters = [("__all__", "모든 카드"), ("", default_label)] + \
                  [(c["class"], f"{c['name']} ({c['class']})") for c in chars]
        _refill(self._pool_filter, filters, self._pool_filter.currentData() or "__all__")
        targets = [("", default_label)] + [(c["class"], f"{c['name']} ({c['class']})") for c in chars if c.get("card_pool_full")]
        current = self.items[self.cur].get("pool_character", "") if self.cur is not None and self.cur < len(self.items) else ""
        if current and current not in {v for v, _t in targets}:
            targets.append((current, f"{current} (원래 카드 풀을 찾을 수 없음)"))
        _refill(self._pool_box, targets, current)

    def _extra_ok(self, it):
        owner = self._pool_filter.currentData()
        return owner in (None, "__all__") or it.get("pool_character", "") == owner

    def _scoped(self):
        return bool(self.query) or self._pool_filter.currentData() not in (None, "__all__")

    def refresh_list(self, select=None):
        self._sync_characters()
        super().refresh_list(select)

    def load_project(self, project):
        self.project = project
        self._sync_characters()
        super().load_project(project)

    def new_item(self, iid):
        it = M.new_card(iid)
        owner = self._pool_filter.currentData()
        if owner not in (None, "__all__", "") and M.card_pool_for_character(self.project, owner):
            it["pool_character"] = owner
        return it

    # ---- 종류 ----
    def _kind_edited(self, *_):
        if self._loading or self.cur is None:
            return
        it = self.items[self.cur]
        self.write_item()
        if not str(self._kind_box.currentData()).startswith("kind:"):
            CK.defaults_for_type(it)     # 직접 고른 종류만 기본값을 바꾼다 (Tk 앱과 같다)
        self._load_item(self.cur)
        self._notify()

    def create_card_kind(self):
        """'+ 종류 만들기': 새 카드 종류를 만들고 이 카드에 바로 적용한다 (Tk 의 create_card_kind 와 같다)."""
        if self.cur is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("카드 종류 만들기")
        col = QVBoxLayout(dialog)
        name = QLineEdit()
        base = QComboBox()
        for value, text in M.CARD_TYPES:
            base.addItem(text, value)
        Q.set_combo_value(base, self.items[self.cur].get("type", "Skill"))
        description = QLineEdit()
        grid = QGridLayout()
        for row, (text, widget) in enumerate((("종류 이름", name), ("외형 참고 종류", base), ("설명 (게임 툴팁)", description))):
            grid.addWidget(_label(text), row, 0)
            grid.addWidget(widget, row, 1)
        col.addLayout(grid)
        col.addWidget(_label("게임에 독립된 카드 종류를 등록하고 카드 하단에 이름을 표시합니다.\n"
                             "외형 참고 종류는 카드 틀만 정합니다. 기믹 탭에서 이름·설명·발동 블록을 수정할 수 있습니다."))
        ok = _small_button("만들고 이 카드에 적용", None)

        def save():
            try:
                value = CK.create(self.project, name.text(), base.currentData(), description.text())
            except ValueError as exc:
                QMessageBox.warning(dialog, IO.APP_TITLE, str(exc))
                return
            self._loading = True
            try:
                _refill(self._kind_box, CK.options(self.project), value)
            finally:
                self._loading = False
            self._kind_edited()
            if self.on_change:
                self.on_change()
            dialog.accept()
        ok.clicked.connect(save)
        col.addWidget(ok)
        dialog.exec()

    # ---- 불러오기 · 쓰기 ----
    def load_extra(self, it):
        _fill_options(self._kind_box, CK.options(self.project))
        Q.set_combo_value(self._kind_box, CK.selected(self.project, it))
        for key, box in self._kw.items():
            box.blockSignals(True)
            box.setChecked(key in it.get("keywords", []))
            box.blockSignals(False)
        self._sync_characters()
        _fill_options(self._res_box, [("", "없음")] + M.power_options(self.project))
        _fill_options(self._frame_box, CF.options(self.project))
        self._rebuild_tags(it)
        for key, button in self._cond_btns.items():
            button.setText(self._cond_text(it, key))
        self._pool_before = it.get("pool_character", "")

    def _card_effect_tabs(self):
        """카드 효과 칸: '사용할 때'(강화 후 따로 설정 포함) + 뽑을·버릴·소멸할 때 탭 (Tk 의 common_bottom 과 같다)."""
        tabs = QTabWidget()
        page = QWidget()
        col = QVBoxLayout(page)
        bar = FlowLayout(spacing=8)                    # 칸이 좁으면 버튼이 다음 줄로 넘어간다
        self.sep_check = QCheckBox("강화 후 따로 설정")
        self.sep_check.toggled.connect(self._change_play_variant)
        self.play_variant = QCheckBox("강화 후 효과 편집")
        self.play_variant.toggled.connect(lambda _c: self._reload_play_list())
        copy_button = QPushButton("강화 전 효과 복사")
        copy_button.clicked.connect(self.copy_play_effects)
        for widget in (self.sep_check, self.play_variant, copy_button):
            bar.addWidget(widget)
        col.addLayout(bar)
        self.upgrade_summary = _label("")
        self.upgrade_summary.setWordWrap(True)
        col.addWidget(self.upgrade_summary)
        col.addWidget(self.effects, 1)
        tabs.addTab(page, "사용할 때")
        self.event_tabs = tabs
        self.event_panels = {}
        for event, text in EVENTS:
            panel = CardEventPanelQt(self, event, text)
            tabs.addTab(panel, text)
            self.event_panels[event] = panel
        return tabs

    def _load_item(self, idx):
        super()._load_item(idx)
        self._sync_play_effect_list(self.items[self.cur])
        for panel in self.event_panels.values():
            panel.refresh()

    def _reload_play_list(self):
        if self.cur is not None and not self._loading:
            self._sync_play_effect_list(self.items[self.cur])

    def _sync_play_effect_list(self, it):
        separate = bool(it.get("separate_upgrade_effect"))
        _check_quiet(self.sep_check, separate)
        self.play_variant.setEnabled(separate)
        if not separate:
            _check_quiet(self.play_variant, False)
        upgraded = separate and self.play_variant.isChecked()
        if upgraded:
            it.setdefault("upgrade_effects", copy.deepcopy(M.upgrade_effects(it)))
        self.effects.set(it["upgrade_effects"] if upgraded else it["effects"])
        self._refresh_upgrade_summary(it)

    def _refresh_upgrade_summary(self, it):
        if it.get("separate_upgrade_effect") and self.play_variant.isChecked():
            text = ("강화 후 효과를 편집 중입니다. 추가·편집·삭제로 강화 전과 다르게 바꾸세요. " +
                    PV.fill_values(self.project, M.upgraded_effect_description(self.project, it, "ko"), it, upgraded=True))
        else:
            text = "강화 전 효과를 편집 중입니다. '강화 후 따로 설정'을 켜면 현재 효과를 복사해 수정할 수 있습니다."
        self.upgrade_summary.setText(text)

    def _change_play_variant(self, enabled):
        if self._loading or self.cur is None:
            return
        card = self.items[self.cur]
        if enabled and not card.get("separate_upgrade_effect"):
            if "upgrade_effects" not in card and not card.get("upgrade_effect_blocks"):
                card["upgrade_effects"] = copy.deepcopy(card["effects"])
            _check_quiet(self.play_variant, True)
        card["separate_upgrade_effect"] = enabled
        self._sync_play_effect_list(card)
        self._effects_changed()

    def copy_play_effects(self):
        if self.cur is None:
            return
        card = self.items[self.cur]
        if M.upgrade_effects(card) and not ask_yes_no(self, "저장된 강화 후 효과를 현재 강화 전 효과의 복사본으로 바꿀까요?"):
            return
        card["upgrade_effects"] = copy.deepcopy(card["effects"])
        card["separate_upgrade_effect"] = True
        _check_quiet(self.sep_check, True)
        _check_quiet(self.play_variant, True)
        self._sync_play_effect_list(card)
        self._effects_changed()

    def _rebuild_tags(self, it):
        tags = [t for t in GM.tags(self.project) if not t.get("card_kind")]
        signature = tuple((t["id"], t.get("name_ko") or t["id"]) for t in tags)
        if signature != self._tag_sig:
            layout = self._tag_layout
            while layout.count():
                child = layout.takeAt(0).widget()
                if child is not None:
                    child.deleteLater()
            self._tag_box = {}
            if not tags:
                layout.addWidget(_label("(없음)"))
            for t in tags:
                box = QCheckBox(t.get("name_ko") or t["id"])
                box.toggled.connect(self._edited)
                layout.addWidget(box)
                self._tag_box[t["id"]] = box
            layout.addStretch(1)
            self._tag_sig = signature
        selected = set(it.get("gtags") or [])
        for key, box in self._tag_box.items():
            box.blockSignals(True)
            box.setChecked(key in selected)
            box.blockSignals(False)

    def edit_cond(self, key):
        """사용 조건 · 금색 테두리 조건 하나를 고친다 (Tk 의 edit_cond 와 같다)."""
        if self.cur is None:
            return
        it = self.items[self.cur]
        dialog = SlotDialogQt(self, self._editor_for(it), "cond", it.get(key))
        if dialog.exec() and dialog.result is not None:
            it[key] = dialog.result
            self._cond_btns[key].setText(self._cond_text(it, key))
            self._effects_changed()

    def _cond_text(self, it, key):
        c = it.get(key)
        if not isinstance(c, dict):
            return "(없음) ✎"
        return GR.plain(B.cond_label(c, self.project, card=True))[:60] + "  ✎"

    def dump_extra(self, it):
        it["keywords"] = [k for k, box in self._kw.items() if box.isChecked()]
        if it.get("no_cost"):
            it["x_cost"] = False
            it["x_plus_up"] = False
            self._set_checked("x_cost", False)
            self._set_checked("x_plus_up", False)
        it["gtags"] = [k for k, box in self._tag_box.items() if box.isChecked()]
        self._sync_controls(it)
        try:
            CK.apply(self.project, it, self._kind_box.currentData())
        except ValueError:
            pass                          # 종류가 목록에 없으면 그대로 둔다
        before = getattr(self, "_pool_before", "")
        now = it.get("pool_character", "")
        if before != now:                 # Tk 와 같다: 캐릭터 전용 풀을 떼면 원래 카드는 내 풀로
            if not now and before and it.get("clone"):
                it["clone"]["pool"] = "mine"
            self._pool_before = now

    def _sync_controls(self, it):
        for key in ("cost", "upgrade_cost"):
            self._box(key).setEnabled(not it.get("no_cost"))

    def edit_frames(self):
        """카드 테두리 디자인 편집 창 (Tk 의 edit_frames 와 같다). 닫으면 테두리 목록을 다시 채운다."""
        from cardframeqt import FrameStyleDialogQt
        it = self._current_item()
        sel = it.get("frame_style") or (self.project["character"].get("frame_style") or None)
        dialog = FrameStyleDialogQt(self, self.project, self.assets_fn,
                                    select=sel if sel not in ("", CF.GAME) else None, on_change=self._frames_changed)
        dialog.exec()

    def _frames_changed(self):
        self._notify()
        if self.cur is not None:
            self._load_item(self.cur)


def _check_quiet(box, value):
    """신호 없이 체크 상자 값만 맞춘다 (화면을 맞출 때 다시 쓰기 신호가 돌지 않게)."""
    box.blockSignals(True)
    box.setChecked(value)
    box.blockSignals(False)


def _refill(box, options, value):
    box.blockSignals(True)
    box.clear()
    for v, text in options:
        box.addItem(text, v)
    index = box.findData(value)
    box.setCurrentIndex(index if index >= 0 else 0)
    box.blockSignals(False)


def _fill_options(box, options):
    box.clear()
    for v, text in options:
        box.addItem(text, v)


def _small_button(text, slot):
    button = QPushButton(text)
    if slot is not None:
        button.clicked.connect(slot)
    return button


class RelicTabQt(ItemTabQt):
    kind, key, noun = "relic", "relics", "유물"
    image_hint = "256×256 권장"
    note = "효과는 효과 칸과 블록 편집에서 고칩니다."

    def build_form(self, g):
        self._str(g, 0, 0, "ID (영문 소문자_)", "id")
        self._str(g, 0, 2, "이름 (한국어)", "name_ko")
        self._str(g, 1, 0, "이름 (영어)", "name_en")
        self._str(g, 1, 2, "이름 (중국어 간체)", "name_zh")
        self._combo(g, 2, 0, "희귀도", "rarity", M.RELIC_RARITIES)
        self._combo(g, 2, 2, "발동 시점", "trigger", M.RELIC_TRIGGERS)
        self._combo(g, 3, 0, "사용한 카드 종류", "played_filter", [])
        self._int(g, 3, 2, "몇 장마다", "played_every")
        self._combo(g, 4, 0, "적 대상", "enemy_mode", M.RELIC_ENEMY_MODES)
        self._combo(g, 4, 2, "강화 버전 (고대의 존재가 교체)", "upgrade_relic", [])
        button = QPushButton("＋ 강화 버전 만들기")
        button.clicked.connect(self.make_upgrade)
        g.addWidget(button, 5, 1, 1, 3)
        self._str(g, 6, 0, "플레이버 (한국어)", "flavor_ko")
        self._str(g, 6, 2, "플레이버 (영어)", "flavor_en")
        self._str(g, 7, 0, "플레이버 (중국어 간체)", "flavor_zh")
        self._common(g, 8)

    def new_item(self, iid):
        return M.new_relic(iid)

    def load_extra(self, it):
        fill(self._box("played_filter"), GM.card_filters(self.project))
        fill(self._box("upgrade_relic"), [("", "없음 (게임 기본: 서클릿)")] +
              [(r["id"], f"{r.get('name_ko') or r['id']} ({r['id']})")
               for r in self.project["relics"] if r["id"] != it.get("id")])

    def make_upgrade(self):
        """이 유물을 복사해 '+' 강화 버전을 만들고 바로 연결한다 (Tk 앱과 같다)."""
        if self.cur is None:
            return
        base = self.items[self.cur]
        it = copy.deepcopy(base)
        it["id"] = unique_id(self.project, base["id"] + "_plus")
        for lang in ("ko", "en", "zh"):
            if base.get(f"name_{lang}"):
                it[f"name_{lang}"] = base[f"name_{lang}"] + "+"
        it["rarity"] = "Starter"        # 강화 시작 유물은 무작위 보상에 나오지 않는다
        it["upgrade_relic"] = ""
        base["upgrade_relic"] = it["id"]
        pos = self.cur + 1
        self.items.insert(pos, it)
        self._leave_search()
        self.refresh_list(pos)
        self._notify()


class PotionTabQt(ItemTabQt):
    kind, key, noun = "potion", "potions", "물약"
    image_hint = "256×256 권장"
    note = "효과는 효과 칸과 블록 편집에서 고칩니다. 물약은 전투 중에만 사용합니다."

    def build_form(self, g):
        self._str(g, 0, 0, "ID (영문 소문자_)", "id")
        self._str(g, 0, 2, "이름 (한국어)", "name_ko")
        self._str(g, 1, 0, "이름 (영어)", "name_en")
        self._str(g, 1, 2, "이름 (중국어 간체)", "name_zh")
        self._combo(g, 2, 0, "희귀도", "rarity", M.POTION_RARITIES)
        self._combo(g, 2, 2, "대상", "target", M.POTION_TARGETS)
        self._common(g, 3)

    def new_item(self, iid):
        return M.new_potion(iid)


class PowerTabQt(ItemTabQt):
    kind, key, noun = "power", "powers", "파워"
    image_hint = "64×64 권장 (큰 그림 256×256)"
    note = "넘칠 때·기준치 블록은 아래 버튼으로, 상시 효과는 목록에서 편집합니다."

    def build_form(self, g):
        self._str(g, 0, 0, "ID (영문 소문자_)", "id")
        self._str(g, 0, 2, "이름 (한국어)", "name_ko")
        self._str(g, 1, 0, "이름 (영어)", "name_en")
        self._str(g, 1, 2, "이름 (중국어 간체)", "name_zh")
        self._combo(g, 2, 0, "종류", "type", M.POWER_TYPES)
        self._combo(g, 2, 2, "중첩 방식", "stack", M.POWER_STACKS)
        self._combo(g, 3, 0, "발동 시점", "trigger", M.POWER_TRIGGERS)
        self._combo(g, 3, 2, "줄어드는 방식", "decay", M.POWER_DECAY)
        self._combo(g, 4, 0, "카드 종류", "played_filter", [])
        self._combo(g, 4, 2, "누가 사용", "played_by", M.POWER_PLAYED_BY)
        self._combo(g, 5, 0, "적 대상", "enemy_mode", M.RELIC_ENEMY_MODES)
        self._int(g, 5, 2, "최대 스택 (0 = 없음)", "cap")
        self._int(g, 6, 0, "기준치 (0 = 없음)", "threshold")
        self._combo(g, 6, 2, "기준치 도달 후", "threshold_mode", GM.THRESHOLD_MODES)
        self._str(g, 7, 0, "그룹 (같은 그룹은 하나만)", "group")
        g.addWidget(self._check("hidden", "숨김 (아이콘 없이 내부 카운터로만 사용)"), 7, 2, 1, 2)
        g.addWidget(_label("상시 효과"), 8, 0, Qt.AlignmentFlag.AlignTop)
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
        self._common(g, 10)

    def new_item(self, iid):
        return M.new_power(iid)

    def load_extra(self, it):
        fill(self._box("played_filter"), GM.card_filters(self.project))
        self.modifiers.set(it.setdefault("modifiers", []))

"""블록 코딩 편집기 (Qt 版) — 핵심 편집: 블록 고르기 · 작업 공간 · 칸 고치기 · 코드·설명 미리보기 · 저장.

Tk 의 blockui.BlockEditor 와 같은 결과(blocks · code · 설명)를 낸다. 아직 Qt 에 없는 것 (Tk 앱에서 한다):
끌어서 놓기, 즐겨찾기·저장한 묶음·문장으로 만들기, 반복 사용할 블록 만들기, 원본 호출 연결, 원본 효과 다시 풀기.
블록은 단추(추가 · 위 · 아래 · 복제 · 삭제 · 감싸기)로 옮긴다.
"""
import copy
import re

from PySide6.QtCore import QByteArray, QMimeData, QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QCursor, QDrag, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QShortcut
from PySide6.QtWidgets import QFileDialog, QInputDialog, QMenu
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSpinBox, QSplitter,
                               QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem, QTreeWidgetItemIterator, QVBoxLayout, QWidget,
                               QHeaderView, QRubberBand)

import blockchoices as BC
import blocklibqt
import blockcode as B
import blockfamilies as F
from flowlayout import FlowLayout
import blockhelp as BH
import gimmickrules as GR
import modgen as M
from descriptionqt import DescriptionEditQt
from slotqt import SlotDialogQt
import qtkit as Q

TITLE = "블록 코딩"
HISTORY_LIMIT = 100
CONTAINER_KEYS = ("body", "else", "third")
VALUE_KINDS = ("value",)
COND_KINDS = ("cond",)
TEXT_KINDS = ("code", "source", "raw_stat", "varname", "label")
WHO_KINDS = {"who_multi": True, "who_one": False}
PILE_KINDS = ("pile", "aura_pile", "aura_target_pile")


def _plain(text):
    return GR.plain(text)


def _ask(parent, text):
    return QMessageBox.question(parent, TITLE, text) == QMessageBox.StandardButton.Yes


def _warn(parent, text):
    QMessageBox.warning(parent, TITLE, text)


def _caption_text(editor, b):
    """블록의 한 줄 글: 칸 자리({키})에 현재 값을 넣는다."""
    template = B.block_caption(b)
    spec_args = _arg_specs(b)

    def fill(match):
        key = match.group(1)
        if key not in b.get("args", {}) and key not in spec_args:
            return match.group(0)
        return _value_text(editor, b, key)
    return re.sub(r"\{([a-zA-Z_]+)\}", fill, template)


def _category_color(op):
    """블록 종류의 기능 색 (blockcode.CATS). 모르는 블록이면 None."""
    try:
        cat = B.SPECS[op]["cat"]
    except (KeyError, TypeError):
        return None
    return B.CATS.get(cat, (None, None))[1]


def _tint(color, share=0.14):
    """기능 색을 흰 바탕에 옅게 섞는다 (글자가 잘 읽히도록)."""
    c = QColor(color)
    red = round(255 + (c.red() - 255) * share)
    green = round(255 + (c.green() - 255) * share)
    blue = round(255 + (c.blue() - 255) * share)
    return f"#{red:02x}{green:02x}{blue:02x}"


def _ink_for(color):
    """글자 색: 바탕이 밝으면 짙은 글씨, 어두우면 흰 글씨."""
    c = QColor(color)
    light = 0.299 * c.red() + 0.587 * c.green() + 0.114 * c.blue() > 170
    return Q.C["text"] if light else "#ffffff"


def _shade(color, share=0.18):
    """테두리 색: 기능 색을 조금 어둡게."""
    c = QColor(color)
    return QColor(round(c.red() * (1 - share)), round(c.green() * (1 - share)),
                  round(c.blue() * (1 - share))).name()


def _arg_specs(b):
    """블록의 칸 목록 {이름: 종류}. 원본에서 풀어낸 호출은 블록 안의 슬롯을 쓴다."""
    if b.get("op") == "src_call":
        return {s["key"]: s.get("kind", "code") for s in b.get("slots", [])}
    try:
        args = B.block_spec(b).get("args", {})
    except (KeyError, TypeError):
        return {}
    return {k: v[0] for k, v in args.items()}


def _value_text(editor, b, key):
    value = (b.get("args") or {}).get(key)
    kind = _arg_specs(b).get(key, "code")
    if kind in VALUE_KINDS and isinstance(value, dict):
        return _plain(B.value_label(value, editor.project, card=editor.owner_kind == "card"))
    if kind in COND_KINDS and isinstance(value, dict):
        return _plain(B.cond_label(value, editor.project, card=editor.owner_kind == "card"))
    if isinstance(value, bool):
        return "예" if value else "아니오"
    options = _options(editor, b, key, kind)
    label = next((text for v, text in options if v == value), None)
    if label is not None:
        return label
    text = str(value if value is not None else "")
    if B.HIDE_CODE and text and kind == "source":   # 코드 대신 줄 수만 보인다 (칸을 누르면 볼 수 있음)
        return f"원본 코드 {sum(1 for line in text.splitlines() if line.strip())}줄"
    if B.HIDE_CODE and text and kind == "code":
        return B.friendly_code(text, "원본 식")
    return text if text else "(비어 있음)"


def _options(editor, b, key, kind):
    """칸의 선택지 [(값, 글)]. 목록이 없는 칸은 빈 목록 (글로 고친다)."""
    if kind in WHO_KINDS:
        return list(B.who_options(editor.owner_kind, multi=WHO_KINDS[kind]))
    if kind in PILE_KINDS:
        return [("Deck", "전체 덱 (전투 전 원본)")] + list(B.PILES)
    if kind == "pick_pile":
        return list(B.PICK_PILES)
    if kind == "card_filter":
        return list(B.card_is_filters(editor.project))
    if kind == "keyword":
        return [("CardKeyword." + code, label) for code, label in M.CARD_KEYWORDS]
    if kind == "family_mode":
        return list(F.modes(b, editor.owner_kind))
    if kind == "preview_style":
        value = B.preview_style_expr(b.get("args", {}).get(key))
        options = list(B.preview_style_options(F.variant(b, B.SPECS)))
        if value not in dict(options):
            options.append((value, "가져온 표시 설정 유지"))
        return options
    if kind == "choice":
        slot = B.slot_info(b, key)
        return [tuple(o) for o in slot.get("options", [])]
    if kind == "card_type":
        return list(B.CARD_TYPES)
    if kind == "shared_name":
        return [(name, name) for name in editor.project.get("shared_blocks", {})]
    if kind == "switch_state":
        return [("on", "켜기"), ("off", "끄기")]
    if kind in ("code", "card", "card_ref", "power", "orb", "potion", "pet", "summon", "button", "fx", "gtag",
                "card_stat", "enemy_mode", "which", "enchant", "evoke_which", "clone_policy", "end_policy",
                "cost_duration", "delay_when", "result_pool", "result_filter", "enemy_filter", "aura_filter",
                "aura_power_filter", "aura_stat", "summon_any", "hand_action", "kw_where", "kw_action", "pick_action",
                "number_edit", "aura_pile", "family_mode", "varname"):
        try:
            choices = BC.code_choices(editor.project, editor.owner_kind, editor.item, b.get("op"), key)
        except (KeyError, TypeError, AttributeError):
            choices = {}
        return [(code, label) for label, code in choices.items()]
    return []


class _ArgRow:
    """칸 하나: 종류에 맞는 입력 상자와 값을 가져오는 함수."""

    def __init__(self, editor, b, key, kind, on_change):
        self.editor, self.b, self.key, self.kind = editor, b, key, kind
        self.on_change = on_change
        self.widget = None
        value = (b.get("args") or {}).get(key)
        if kind in VALUE_KINDS or kind in COND_KINDS:
            self.widget = QPushButton("")
            self._refresh_slot()
            self.widget.clicked.connect(lambda _=False: self._edit_slot())
        elif kind == "bool":
            self.widget = QCheckBox()
            self.widget.setChecked(bool(value))
            self.widget.toggled.connect(lambda v: self._set(bool(v)))
        elif kind == "family_mode":
            self.widget = QComboBox()
            for v, text in _options(editor, b, key, kind):
                self.widget.addItem(text, v)
            index = self.widget.findData(value)
            self.widget.setCurrentIndex(max(0, index))
            self.widget.currentIndexChanged.connect(lambda _i: self.editor._switch_mode(self.b, self.widget.currentData()))
        elif kind == "int":
            self.widget = QSpinBox()
            self.widget.setRange(-9999, 9999)
            self.widget.setValue(int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0)
            self.widget.valueChanged.connect(lambda v: self._set(int(v)))
        else:
            options = _options(editor, b, key, kind)
            if options and kind not in TEXT_KINDS:
                self.widget = QComboBox()
                for v, text in options:
                    self.widget.addItem(text, v)
                index = self.widget.findData(value)
                if index < 0 and value is not None:
                    self.widget.addItem(f"(직접 입력: {value})", value)
                    index = self.widget.count() - 1
                self.widget.setCurrentIndex(max(0, index))
                self.widget.currentIndexChanged.connect(lambda _i: self._set(self.widget.currentData()))
            else:
                self.widget = QLineEdit("" if value is None else str(value))
                self.widget.textChanged.connect(lambda t: self._set(t))

    def _set(self, value):
        self.b.setdefault("args", {})[self.key] = value
        if self.kind in VALUE_KINDS or self.kind in COND_KINDS:
            return
        self.on_change()

    def _refresh_slot(self):
        value = (self.b.get("args") or {}).get(self.key)
        if self.kind in VALUE_KINDS:
            text = _plain(B.value_label(value, self.editor.project, card=self.editor.owner_kind == "card")) \
                if isinstance(value, dict) else "(없음)"
        else:
            text = _plain(B.cond_label(value, self.editor.project, card=self.editor.owner_kind == "card")) \
                if isinstance(value, dict) else "(없음)"
        self.widget.setText(text + "  ✎")

    def _edit_slot(self):
        current = (self.b.get("args") or {}).get(self.key)
        dialog = SlotDialogQt(self.editor.window(), self.editor, "value" if self.kind in VALUE_KINDS else "cond", current)
        if dialog.exec() and dialog.result is not None:
            self.b.setdefault("args", {})[self.key] = dialog.result
            self._refresh_slot()
            self.on_change()


PALETTE_MIME = "application/x-sts2-block"    # 끌기 내용: "block:<번호>" (작업 공간) · 블록 종류 · "preset:<키>" (보관함)


def _drag_picture(view, items):
    """끌 때 커서를 따라가는 그림 (qtkit.drag_picture 와 같다)."""
    return Q.drag_picture(view, [view.visualItemRect(it) for it in items])


def _start_drag(view):
    """끌기는 직접 시작한다: Qt 기본 끌기는 옮긴 항목을 목록에서 지워 버린다. 끄는 줄들이 커서를 따라간다."""
    items = view.selectedItems()
    data = view.mimeData(items) if items else None
    if data is None:
        return
    drag = QDrag(view)
    drag.setMimeData(data)
    picture, grab_at = _drag_picture(view, items)
    if picture is not None:
        drag.setPixmap(picture)
        drag.setHotSpot(grab_at)
    drag.exec(Qt.DropAction.CopyAction)


class _PaletteTree(QTreeWidget):
    """블록 라이브러리: 항목을 끌어서 작업 공간에 놓을 수 있다."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setHeaderHidden(True)
        self.setWordWrap(True)                   # 블록 이름을 자르지 않고 줄을 바꾼다
        self.setDragEnabled(True)
        self.setAcceptDrops(True)                # 작업 공간의 블록을 여기 놓으면 지운다

    def mimeData(self, items):
        key = items[0].data(0, Qt.ItemDataRole.UserRole) if items else None
        if not key:
            return None
        data = QMimeData()
        data.setData(PALETTE_MIME, QByteArray(str(key).encode("utf8")))
        return data

    def startDrag(self, supported_actions):
        _start_drag(self)

    def _block_payload(self, event):
        if not event.mimeData().hasFormat(PALETTE_MIME):
            return None
        payload = bytes(event.mimeData().data(PALETTE_MIME)).decode("utf8")
        return payload if payload.startswith(("block:", "blocks:")) else None

    def dragEnterEvent(self, event):
        if self._block_payload(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if self._block_payload(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        payload = self._block_payload(event)
        if payload and self.editor._remove_blocks(payload):
            event.acceptProposedAction()
        else:
            event.ignore()


class _HintOverlay(QWidget):
    """끌 때 보여 줄 자리를 그리는 투명한 덮개 (목록 그림 위에 얹힌다, 마우스는 통과)."""

    def __init__(self, parent):
        super().__init__(parent)
        self.hint = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        if self.hint is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)                  # 놓으면 여기 들어간다: 얇은 강조 줄
        painter.setBrush(QColor(Q.C["accent"]))
        painter.drawRoundedRect(QRectF(self.hint), 2, 2)
        painter.end()


class _WorkTree(Q.BandSelectMixin, QTreeWidget):
    """작업 공간: 블록을 끌어서 옮기고, 팔레트·보관함에서 끌어서 넣는다."""

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.setHeaderHidden(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)   # 빈 곳을 끌어 여러 블록을 고른다
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setIndentation(0)                    # 조건 블록의 벽은 블록 안에서 그린다 (들여쓰기 없이 이어지게)
        self._overlay = _HintOverlay(self.viewport())   # 끌 때 보여 줄 자리 (줄)
        self._slot_target = None                  # 끌 때 골린 빈 칸
        self._band = None                         # 빈 곳을 끌어 고르는 사각형
        self._band_origin = None
        self._band_keep = False
        self.setRootIsDecorated(False)
        self.setStyleSheet("QTreeWidget::item:selected { background: transparent; } "
                           "QTreeWidget::branch { image: none; border-image: none; }")   # 선택은 블록 테두리로, 화살표는 감춘다

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._overlay.setGeometry(self.viewport().rect())
        self.editor._refresh_row_heights()        # 너비가 바뀌면 칸이 줄을 다시 넘긴다

    def _band_items(self):
        out, it = [], QTreeWidgetItemIterator(self)
        while it.value() is not None:
            if it.value().data(0, Qt.ItemDataRole.UserRole) is not None:
                out.append(it.value())
            it += 1
        return out

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:      # Delete: 고른 블록 지우기 (확인을 받는다)
            self.editor._delete()
            return
        super().keyPressEvent(event)

    def mimeData(self, items):
        picked = {it.data(0, Qt.ItemDataRole.UserRole) for it in items}
        picked.discard(None)
        if not picked:
            return None
        order, it = [], QTreeWidgetItemIterator(self)       # 끌 때는 작업 공간의 순서대로
        while it.value() is not None:
            block_id = it.value().data(0, Qt.ItemDataRole.UserRole)
            if block_id in picked and block_id not in order:
                order.append(block_id)
            it += 1
        kind = "block" if len(order) == 1 else "blocks"
        data = QMimeData()
        data.setData(PALETTE_MIME, QByteArray(f"{kind}:{','.join(str(i) for i in order)}".encode("utf8")))
        return data

    def startDrag(self, supported_actions):
        _start_drag(self)
        self._show_hint(None)

    def _show_hint(self, hint):
        if self._slot_target is not None:
            self._slot_target.set_target(False)
            self._slot_target = None
        if hint is not None and hint[0] == "slot":
            self._slot_target = hint[1]
            self._slot_target.set_target(True)
            hint = None
        self._overlay.hint = hint[1] if hint is not None else None
        self._overlay.setGeometry(self.viewport().rect())
        self._overlay.update()

    def dragLeaveEvent(self, event):
        self._show_hint(None)
        super().dragLeaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(PALETTE_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasFormat(PALETTE_MIME):
            event.acceptProposedAction()
            point = event.position().toPoint()
            dest, index = self.editor._drop_place(self.itemAt(point), self._where_at(point))
            self._show_hint(self.editor._drop_hint(dest, index))
        else:
            event.ignore()

    def _where_at(self, point):
        """놓은 자리: 항목의 위쪽 4분의 1 = 앞, 아래쪽 4분의 1 = 뒤, 가운데 = 안. 항목 밖 = 맨 끝.
        (직접 처리하므로 Qt 의 끌기 표시(dropIndicatorPosition)에 기대지 않는다.)"""
        item = self.itemAt(point)
        if item is None:
            return QAbstractItemView.DropIndicatorPosition.OnViewport
        rect = self.visualItemRect(item)
        if point.y() < rect.top() + rect.height() * 0.25:
            return QAbstractItemView.DropIndicatorPosition.AboveItem
        if point.y() > rect.bottom() - rect.height() * 0.25:
            return QAbstractItemView.DropIndicatorPosition.BelowItem
        return QAbstractItemView.DropIndicatorPosition.OnItem

    def dropEvent(self, event):
        self._show_hint(None)
        payload = bytes(event.mimeData().data(PALETTE_MIME)).decode("utf8")
        point = event.position().toPoint()
        if self.editor._drop(payload, self.itemAt(point), self._where_at(point)):
            event.acceptProposedAction()
        else:
            event.ignore()


def _payload_ids(payload):
    """끌어 놓을 블록 번호들: 'block:3' 또는 'blocks:3,5'."""
    return [int(x) for x in payload.split(":", 1)[1].split(",") if x]


def _top_only(blocks):
    """고른 블록 중 다른 고른 블록 안에 든 것은 뺀다 (안쪽은 바깥을 옮길 때 같이 간다)."""
    out = []
    for block in blocks:
        inside = any(any(x is block for x in lst)
                     for other in blocks if other is not block for lst in _lists_inside(other))
        if not inside and not any(x is block for x in out):
            out.append(block)
    return out


def _lists_inside(block):
    """블록 안에 든 목록들 (반복 · 만약 · 아니면 …)."""
    for key in CONTAINER_KEYS:
        if isinstance(block.get(key), list):
            yield block[key]
            for child in block[key]:
                yield from _lists_inside(child)


def _locate(blocks, target):
    """블록이 든 목록과 번호. 없으면 (None, None)."""
    for index, block in enumerate(blocks):
        if block is target:
            return blocks, index
        for key in CONTAINER_KEYS:
            if isinstance(block.get(key), list):
                found = _locate(block[key], target)
                if found[0] is not None:
                    return found
    return None, None


def _add_action(menu, text, slot):
    action = menu.addAction(text)
    action.triggered.connect(lambda _=False: slot())


class RecipeDialogQt(QDialog):
    """문장으로 만들기: 두 가지 효과 레시피 (Tk 의 효과 레시피 창과 같다)."""

    def __init__(self, parent, project):
        super().__init__(parent)
        self.setWindowTitle("효과 레시피")
        self.project = project
        self.result = None
        choices = blocklibqt.recipe_choices(project)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)

        transform = QWidget()
        col = QVBoxLayout(transform)
        row = QHBoxLayout()
        self.pile = self._combo(row, choices["piles"])
        row.addWidget(QLabel("에서"))
        self.source = self._combo(row, choices["sources"])
        row.addWidget(QLabel("중 무작위"))
        self.count = self._spin(row, 2)
        row.addWidget(QLabel("장을 골라"))
        row.addStretch(1)
        col.addLayout(row)
        row = QHBoxLayout()
        self.pool = self._combo(row, choices["pools"])
        row.addWidget(QLabel("에서"))
        self.result_filter = self._combo(row, choices["results"])
        row.addWidget(QLabel("중 하나로 각각 변화시켜요."))
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(1)
        self.tabs.addTab(transform, "조건에 맞는 카드로 변화")

        threshold = QWidget()
        col = QVBoxLayout(threshold)
        row = QHBoxLayout()
        row.addWidget(QLabel("나에게"))
        self.power = self._combo(row, choices["powers"])
        row.addWidget(QLabel("파워가"))
        self.stacks = self._spin(row, 3)
        row.addWidget(QLabel("이상 있으면"))
        row.addStretch(1)
        col.addLayout(row)
        row = QHBoxLayout()
        self.action = self._combo(row, choices["actions"])
        row.addWidget(QLabel("효과를 수치"))
        self.amount = self._spin(row, 1)
        row.addWidget(QLabel("만큼 적용해요."))
        row.addStretch(1)
        col.addLayout(row)
        col.addStretch(1)
        self.tabs.addTab(threshold, "파워 수치에 따라 효과 실행")

        add = QPushButton("작업 공간에 추가")
        add.clicked.connect(self._insert)
        root.addWidget(add)

    def _combo(self, row, options):
        box = QComboBox()
        for value, text in options:
            box.addItem(text, value)
        row.addWidget(box)
        return box

    def _spin(self, row, default):
        box = QSpinBox()
        box.setRange(1, 999)
        box.setValue(default)
        row.addWidget(box)
        return box

    def _insert(self):
        if self.tabs.currentIndex() == 0:
            self.result = blocklibqt.transform_recipe(self.project, self.pile.currentData(), self.source.currentData(),
                                                      self.count.value(), self.pool.currentData(),
                                                      self.result_filter.currentData())
        else:
            self.result = blocklibqt.threshold_recipe(self.power.currentData(), self.stacks.value(),
                                                      self.action.currentData(), self.amount.value())
        self.accept()


class _BlockRow(QWidget):
    """작업 공간의 블록 한 칸: 퍼즐 조각 모양 (위에 홈, 아래에 촉). 글과 칸은 안에 든다. 빈 곳을 누르면 그 블록을 고른다."""

    WALL = 16                                             # 조건 블록의 왼쪽 벽 너비 (픽셀)
    NOTCH_X, NOTCH_W, NOTCH_D, RADIUS = 18, 22, 0, 8     # 홈·촉은 쓰지 않는다 (블록끼리 틈 없이 붙이려고), 모서리 둥글기 (픽셀)
    SEAM = 4                                             # 블록 사이 이음새 높이 (조건 블록 색으로 채운다)
    SLOT = 40                                            # 빈 조건 칸: 블록 한 줄만큼 비워 두고 끌어 넣게 한다

    def __init__(self, on_press, parent=None):
        super().__init__(parent)
        self.on_press = on_press
        self.fill = QColor("#eef2f7")
        self.edge = QColor("#7d8898")
        self.walls = []                          # 바깥 조건 블록들의 색 (가장 바깥 것부터, 왼쪽 벽)
        self.selected = False
        self.outline = True                      # 빈 이음새 칸은 윤곽 없이 띠만 그린다
        self.square_left = False                 # 벽에 닿는 왼쪽 모서리를 곧게 (조건 블록 안·머리·띠)
        self.target = False                      # 끌 때 놓을 자리로 골렸다: 점선 상자

    def set_colors(self, fill, edge):
        self.fill, self.edge = QColor(fill), QColor(edge)
        self.update()

    def set_walls(self, colors):
        """이 블록이 든 조건 블록들의 색: 가장 바깥 것부터 왼쪽에 벽을 긋고, 블록은 그 오른쪽에 그린다."""
        self.walls = [QColor(c) for c in colors]
        self.update()

    def offset(self):
        return len(self.walls) * self.WALL

    def set_target(self, on):
        self.target = bool(on)
        self.update()

    def set_selected(self, on):
        self.selected = bool(on)
        self.update()

    def mousePressEvent(self, event):
        self.on_press()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for depth, wall in enumerate(self.walls):
            painter.fillRect(QRectF(depth * self.WALL, 0, self.WALL, self.height()), wall)
        if not self.outline:                     # 이음새: 벽 오른쪽도 조건 블록 색으로 채워 틈이 없게 한다
            painter.fillRect(QRectF(self.offset(), 0, self.width() - self.offset(), self.height()), self.fill)
        if self.target:
            painter.setPen(QPen(QColor(Q.C["accent"]), 2, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(self.offset() + 2, 2, self.width() - self.offset() - 4, self.height() - 4), 6, 6)
        if self.outline:
            painter.setPen(QPen(self.edge, 1))
            painter.setBrush(self.fill.darker(135) if self.selected else self.fill)     # 고른 블록은 바탕을 진하게
            painter.drawPath(self._outline())
        painter.end()

    def _outline(self):
        """블록 윤곽: 둥근 사각형. 조건 블록의 벽에 닿는 왼쪽 모서리는 곧게 해서 벽과 이어지게 한다."""
        r = self.RADIUS
        rl = 0 if self.square_left else r
        left, top = self.offset() + 0.5, 0.5
        right, bottom = self.width() - 1.5, self.height() - 1.5
        path = QPainterPath()
        path.moveTo(left + rl, top)
        path.lineTo(right - r, top)
        path.arcTo(QRectF(right - 2 * r, top, 2 * r, 2 * r), 90, -90)
        path.lineTo(right, bottom - r)
        path.arcTo(QRectF(right - 2 * r, bottom - 2 * r, 2 * r, 2 * r), 0, -90)
        path.lineTo(left + rl, bottom)
        if rl:
            path.arcTo(QRectF(left, bottom - 2 * rl, 2 * rl, 2 * rl), -90, -90)
            path.lineTo(left, top + rl)
            path.arcTo(QRectF(left, top, 2 * rl, 2 * rl), 180, -90)
        path.closeSubpath()
        return path


class BlockEditorQt(QDialog):
    def __init__(self, parent, project, owner_kind, item, blocks, where=None, allow_event=False, show_text=True,
                 text_ko="", text_en="", auto_text=True, text_zh="", upgraded_text=None, card_event=None,
                 on_decompose=None, top_widget=None):
        super().__init__(parent)
        self.setWindowTitle(f"{TITLE} — 새 능력 만들기")
        self.project, self.owner_kind, self.item = project, owner_kind, item or {}
        self.allow_event = allow_event
        self.card_event = card_event
        self.on_decompose = on_decompose      # 원본 효과일 때만: 원본 코드를 다시 블록으로 푼다
        self.show_text = show_text
        self.blocks = B.fix_unknown_blocks(copy.deepcopy(blocks or []))   # 지워진 블록은 직접 코드 블록으로 바꾼다
        self.result = None
        self._by_id = {}
        self.history = []
        self._last = copy.deepcopy(self.blocks)      # 바로 앞 모습 (칸을 고치기 전에 되돌리기로 넣는다)
        self.resize(1400, 900)
        B.set_project_hint(project)
        B.set_item_hint(self.item)
        where = where or {"card": "카드를 낼 때", "relic": "유물이 발동할 때", "potion": "물약을 쓸 때",
                          "power": "파워가 발동할 때", "summon": "소환수가 행동할 때", "orb": "구체가 발동할 때",
                          "button": "버튼을 눌렀을 때", "pet": "동료가 행동할 때"}.get(owner_kind, "")

        root = QVBoxLayout(self)
        top = QHBoxLayout()
        head = QLabel(where)
        head.setStyleSheet("font-weight: bold; font-size: 14px;")
        top.addWidget(head)
        top.addStretch(1)
        undo = QPushButton("되돌리기 (Ctrl+Z)")
        undo.clicked.connect(self.undo)
        top.addWidget(undo)
        clear = QPushButton("모두 지우기")
        clear.clicked.connect(self.clear_all)
        top.addWidget(clear)
        root.addLayout(top)
        if top_widget is not None:           # 원본 효과: 복제 패널(원본 수치 칸)을 창 위쪽에 둔다
            root.addWidget(top_widget)
        QShortcut(QKeySequence("Ctrl+Z"), self, self.undo)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # ---- 블록 고르기 ----
        left = QWidget()
        lc = QVBoxLayout(left)
        lc.addWidget(QLabel("블록 라이브러리 (더블클릭 = 넣기)"))
        self.query = QLineEdit()
        self.query.setPlaceholderText("블록 검색")
        self.query.textChanged.connect(lambda _t: self._build_palette())
        lc.addWidget(self.query)
        self.show_advanced = QCheckBox("다른 효과도 모두 보기")
        self.show_advanced.setChecked(True)
        self.show_advanced.toggled.connect(lambda _c: self._build_palette())
        lc.addWidget(self.show_advanced)
        self.palette = _PaletteTree(self)
        self.palette.itemDoubleClicked.connect(lambda it, _c: self._palette_add(it))
        self.palette.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.palette.customContextMenuRequested.connect(self._palette_menu)
        lc.addWidget(self.palette, 1)
        add = QPushButton("선택한 블록 넣기")
        add.clicked.connect(lambda _=False: self._palette_add(self.palette.currentItem()))
        lc.addWidget(add)
        split.addWidget(left)

        # ---- 작업 공간 ----
        middle = QWidget()
        mc = QVBoxLayout(middle)
        mc.addWidget(QLabel("작업 공간 (위에서 아래로 실행)"))
        self.tree = _WorkTree(self)
        self.tree.itemSelectionChanged.connect(self._mark_selected)
        self.tree.currentItemChanged.connect(self._mark_selected)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._workspace_menu)
        mc.addWidget(self.tree, 1)
        bar = QHBoxLayout()
        for text, slot in (("▲ 위로", lambda: self._move(-1)), ("▼ 아래로", lambda: self._move(1)),
                           ("복제", self._duplicate), ("삭제", self._delete), ("감싸기: 반복", lambda: self._wrap("repeat")),
                           ("감싸기: 만약", lambda: self._wrap("if"))):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, s=slot: s())
            bar.addWidget(button)
        mc.addLayout(bar)
        kit = QHBoxLayout()
        for text, slot in (("블록 불러오기…", self._load_file), ("블록 저장…", self._save_file),
                           ("내 블록으로 정의…", self._define_shared), ("문장으로 만들기…", self._open_recipes)):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, s=slot: s())
            kit.addWidget(button)
        for text, slot in (("원본 다시 분석", self._redecompose), ("원본 실행 블록으로 접기", self._collapse_original)):
            button = QPushButton(text)
            button.clicked.connect(lambda _=False, s=slot: s())
            button.setVisible(self.on_decompose is not None)
            kit.addWidget(button)
        mc.addLayout(kit)
        split.addWidget(middle)

        split.setSizes([360, 720])
        split.setStretchFactor(1, 1)

        # ---- 결과: 코드 · 설명 ----
        self.tabs = QTabWidget()
        self.tabs.setMaximumHeight(260)   # 코드·설명은 아래 자리만 차지하고, 높이는 위의 블록 편집 영역이 가져간다
        self.code_view = QPlainTextEdit()
        self.code_view.setReadOnly(True)
        self.code_view.setStyleSheet("font-family: Consolas;")
        self.code_view.setMaximumHeight(200)
        self.tabs.addTab(self.code_view, "C# 코드 (자동)")
        self.tabs.setTabVisible(self.tabs.indexOf(self.code_view), not B.HIDE_CODE)   # 기본은 숨김 (보기 › C# 코드 보기)
        desc_page = QWidget()
        dc = QVBoxLayout(desc_page)
        self.auto = QCheckBox("설명은 블록에서 자동으로 만들기")
        self.auto.setChecked(bool(auto_text))
        self.auto.toggled.connect(lambda _c: self._refresh_outputs())
        dc.addWidget(self.auto)
        self.desc = {}
        for lang, text in (("ko", text_ko), ("en", text_en), ("zh", text_zh)):
            box = DescriptionEditQt(lambda lang=lang: (self.project, self.item, lang, False))
            box.set_source(text or "")
            self.desc[lang] = box
            dc.addWidget(QLabel({"ko": "설명 (한국어)", "en": "설명 (영어)", "zh": "설명 (중국어 간체)"}[lang]))
            dc.addWidget(box)
        self.upgraded = {}
        for lang in ("ko", "en", "zh"):
            box = DescriptionEditQt(lambda lang=lang: (self.project, self.item, lang, True))
            box.set_source((upgraded_text or {}).get(lang, ""))
            self.upgraded[lang] = box
        self.tabs.addTab(desc_page, "설명")
        self.tabs.setVisible(bool(show_text))
        root.addWidget(self.tabs)
        self.error_label = QLabel("")
        self.error_label.setWordWrap(True)
        self.error_label.setStyleSheet(f"color: {Q.C['danger']};")
        root.addWidget(self.error_label)
        note = QLabel("블록은 끌어서 옮기고, 칸은 블록 안에서 바로 고칩니다. 원본 효과는 '다시 분석'과 '접기'로 고칩니다.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Q.C['muted']};")
        root.addWidget(note)
        bottom = QHBoxLayout()
        bottom.addStretch(1)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        ok = QPushButton("저장")
        ok.clicked.connect(self.ok)
        bottom.addWidget(ok)
        root.addLayout(bottom)

        self.favorite_order = blocklibqt.load_favorites()
        self.presets = blocklibqt.load_presets()
        self._build_palette()
        self._render()

    # ---- 블록 고르기 ----
    def _build_palette(self):
        self.palette.clear()
        self.palette.setColumnCount(2)                     # 0: 블록 이름, 1: ☆ 즐겨찾기 단추
        self.palette.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.palette.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)   # ☆ 칸은 30px 고정
        self.palette.header().setStretchLastSection(False)
        self.palette.header().resizeSection(1, 30)
        query = self.query.text().strip().casefold()

        def matches(label, key):
            return not query or query in label.casefold() or query in key

        favorites = [op for op in self.favorite_order if op in B.SPECS and matches(palette_name(op), op)]
        if favorites or not query:
            head = QTreeWidgetItem(["★ 즐겨찾기"])
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.palette.addTopLevelItem(head)
            for op in favorites:
                head.addChild(self._palette_child(op, palette_name(op)))
            if not favorites:                              # 아직 없으면 쓰는 법을 보여 준다
                hint = QTreeWidgetItem(["블록 오른쪽의 ☆ 를 누르면 여기에 모입니다"])
                hint.setFlags(Qt.ItemFlag.NoItemFlags)
                head.addChild(hint)
            head.setExpanded(True)
        library = []
        for key, preset in sorted(self.presets.items(), key=lambda pair: pair[1]["name"].casefold()):
            keywords = " ".join([preset["name"], *(B.block_caption(b) for b in B.walk(preset["blocks"]))])
            if matches(keywords, ""):
                library.append((key, preset))
        if library:
            head = QTreeWidgetItem(["저장한 블록 모음"])
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.palette.addTopLevelItem(head)
            for key, preset in library:
                child = QTreeWidgetItem([preset["name"]])
                child.setData(0, Qt.ItemDataRole.UserRole, "preset:" + key)
                child.setToolTip(0, blocklibqt.preset_summary(self.project, preset))
                head.addChild(child)
            head.setExpanded(True)
        for category, ops in B.PALETTE:
            names = []
            for op in ops:
                if op not in B.SPECS:
                    continue
                label = palette_name(op)
                if query and query not in label.casefold() and query not in op:
                    continue
                names.append((op, label))
            if not names:
                continue
            head = QTreeWidgetItem([B.CATS[category][0]])
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.palette.addTopLevelItem(head)
            for op, label in names:
                head.addChild(self._palette_child(op, label))
            head.setExpanded(True)
        self._attach_stars()

    def _attach_stars(self):
        """블록마다 ☆/★ 단추를 붙인다. 누르면 즐겨찾기에 넣거나 뺀다."""
        iterator = QTreeWidgetItemIterator(self.palette)
        while iterator.value() is not None:
            item = iterator.value()
            op = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(op, str) and op in B.SPECS:
                on = op in self.favorite_order
                star = QToolButton()
                star.setText("★" if on else "☆")
                star.setToolTip("즐겨찾기에서 빼기" if on else "즐겨찾기에 넣기")
                star.setAutoRaise(True)
                star.setCursor(Qt.CursorShape.PointingHandCursor)
                star.clicked.connect(lambda _checked=False, key=op: self._toggle_favorite(key))
                self.palette.setItemWidget(item, 1, star)
            iterator += 1

    def _palette_child(self, key, label):
        child = QTreeWidgetItem([label])
        child.setData(0, Qt.ItemDataRole.UserRole, key)
        color = _category_color(key)
        if color:
            child.setBackground(0, QBrush(QColor(color)))
            child.setForeground(0, QBrush(QColor(_ink_for(color))))
        return child

    def _palette_add(self, item):
        if item is None:
            return
        key = item.data(0, Qt.ItemDataRole.UserRole)
        if not key:
            return
        target = self._selected_list()
        if str(key).startswith("preset:"):
            blocks = self._resolved_preset(str(key)[7:])
            if not blocks:
                return
            self._push()
            target.extend(blocks)
            self._render(select=blocks[0])
            return
        self._push()
        block = _new_block(key)
        target.append(block)
        self._render(select=block)

    # ---- 끌어서 놓기 ----
    def _drop_place(self, target, where):
        """놓은 자리 -> (목록, 번호). 놓을 수 없으면 (None, None)."""
        if target is None:
            return self.blocks, len(self.blocks)
        if target.data(0, Qt.ItemDataRole.UserRole) is None:      # '안에서 실행' · '아니면' 머리글
            container = self._by_id.get(target.data(0, Qt.ItemDataRole.UserRole + 1))
            key = target.data(0, Qt.ItemDataRole.UserRole + 2)
            if container is None or key is None:
                return None, None
            dest = container.setdefault(key, [])
            return dest, len(dest)
        block = self._by_id.get(target.data(0, Qt.ItemDataRole.UserRole))
        owner = self._by_id.get(target.data(0, Qt.ItemDataRole.UserRole + 1))
        if block is None or owner is None:
            return None, None
        if where == QAbstractItemView.DropIndicatorPosition.OnItem and _is_container(block):
            dest = block.setdefault("body", [])
            return dest, len(dest)
        index = next(i for i, x in enumerate(owner) if x is block)
        if where == QAbstractItemView.DropIndicatorPosition.AboveItem:
            return owner, index
        return owner, index + 1

    def _drop_hint(self, dest, index):
        """끌 때 보여 줄 자리: 놓으면 들어갈 줄, 또는 빈 칸 상자. 놓을 수 없으면 None."""
        if dest is None:
            return None
        if dest:
            if index < len(dest):
                node = self._row_items.get(id(dest[index]), (None, None))[0]
                if node is None:
                    return None
                rect = self.tree.visualItemRect(node)
                return ("line", QRect(rect.left(), rect.top() - 2, rect.width(), 4))
            node = self._row_items.get(id(dest[-1]), (None, None))[0]
            if node is None:
                return None
            rect = self.tree.visualItemRect(node)
            return ("line", QRect(rect.left(), rect.bottom() - 1, rect.width(), 4))
        entry = self._list_items.get(id(dest))
        if entry is None:
            return None
        return ("slot", entry[1])

    def _drop(self, payload, target, where):
        """팔레트 블록(종류), 보관함 묶음(preset:키), 작업 공간 블록(block:번호)을 놓은 자리에 넣거나 옮긴다."""
        dest, index = self._drop_place(target, where)
        if dest is None:
            return False
        if payload.startswith(("block:", "blocks:")):
            moved = _top_only([b for b in (self._by_id.get(i) for i in _payload_ids(payload)) if b is not None])
            if not moved or any(lst is dest for block in moved for lst in _lists_inside(block)):
                return False                       # 자기 안으로는 넣을 수 없다
            self._push()
            for block in moved:
                source, source_index = _locate(self.blocks, block)
                if source is None:
                    continue
                if source is dest and source_index < index:
                    index -= 1
                del source[source_index]
            dest[index:index] = moved
            self._render(select=moved[0])
            return True
        if payload.startswith("preset:"):
            blocks = self._resolved_preset(payload[7:])
            if not blocks:
                return False
            self._push()
            dest[index:index] = blocks
            self._render(select=blocks[0])
            return True
        if payload not in B.SPECS:
            return False
        self._push()
        block = _new_block(payload)
        dest.insert(index, block)
        self._render(select=block)
        return True

    # ---- 즐겨찾기 · 보관함 ----
    def _resolved_preset(self, key):
        preset = self.presets.get(key)
        if preset is None:
            return None
        try:
            return blocklibqt.resolve_preset(preset["blocks"], self.project, self._pick_replacement)
        except LookupError as error:
            _warn(self, str(error))
            return None

    def _pick_replacement(self, kind, old, rows):
        labels = [f"{M.text(row, 'name', 'ko') or row['id']} ({row['id']})" for row in rows]
        choice, ok = QInputDialog.getItem(self, "블록 모음 연결",
                                          f"찾을 수 없는 {kind} ID '{old}' 대신 사용할 {kind}를 선택하세요.",
                                          labels, 0, False)
        if not ok:
            return None
        return rows[labels.index(choice)]["id"]

    def _toggle_favorite(self, op):
        try:
            self.favorite_order = blocklibqt.save_favorites(blocklibqt.toggle_favorite(self.favorite_order, op))
        except OSError as error:
            _warn(self, f"즐겨찾기 저장 실패: {error}")
            return
        self._build_palette()

    def _store_preset(self, key, name, blocks):
        try:
            blocklibqt.store_preset(key, name, blocks)
        except OSError as error:
            _warn(self, str(error))
            return False
        self.presets = blocklibqt.load_presets()
        self._build_palette()
        return True

    def _rename_preset(self, key):
        preset = self.presets[key]
        name, ok = QInputDialog.getText(self, "이름 변경", "새 이름", text=preset["name"])
        name = name.strip()
        if not ok or not name:
            return
        if any(k != key and v["name"].casefold() == name.casefold() for k, v in self.presets.items()):
            _warn(self, "이미 사용 중인 이름입니다.")
            return
        self._store_preset(key, name, preset["blocks"])

    def _delete_preset(self, key):
        name = self.presets[key]["name"]
        if not _ask(self, f"‘{name}’ 묶음을 삭제할까요?"):
            return
        try:
            blocklibqt.delete_preset(key)
        except OSError as error:
            _warn(self, str(error))
            return
        self.presets = blocklibqt.load_presets()
        self._build_palette()

    def _save_to_library(self, blocks):
        name, ok = QInputDialog.getText(self, "라이브러리에 저장", "블록 묶음 이름")
        name = name.strip()
        if not ok or not name:
            return
        key = blocklibqt.new_preset_key(name, self.presets)
        if key in self.presets and not _ask(self, f"‘{name}’ 묶음을 바꿀까요?"):
            return
        self._store_preset(key, name, blocks)

    def _palette_menu(self, pos):
        item = self.palette.itemAt(pos)
        key = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not key:
            return
        menu = QMenu(self)
        if str(key).startswith("preset:"):
            preset_key = str(key)[7:]
            _add_action(menu, "이름 바꾸기…", lambda: self._rename_preset(preset_key))
            _add_action(menu, "삭제", lambda: self._delete_preset(preset_key))
        else:
            text = "★ 즐겨찾기에서 빼기" if key in self.favorite_order else "☆ 즐겨찾기에 넣기"
            _add_action(menu, text, lambda: self._toggle_favorite(key))
        menu.exec(self.palette.viewport().mapToGlobal(pos))

    def _workspace_menu(self, pos):
        item = self.tree.itemAt(pos)
        if item is None or item.data(0, Qt.ItemDataRole.UserRole) is None:
            return
        self.tree.setCurrentItem(item)
        block, owner = self._selected_block_context()
        if block is None:
            return
        menu = QMenu(self)
        _add_action(menu, "▲ 위로", lambda: self._move(-1))
        _add_action(menu, "▼ 아래로", lambda: self._move(1))
        _add_action(menu, "복제", self._duplicate)
        _add_action(menu, "삭제", self._delete)
        menu.addSeparator()
        _add_action(menu, "라이브러리에 저장…", lambda: self._save_to_library([copy.deepcopy(block)]))
        if block.get("op") == "src_call":
            _add_action(menu, "효과 블록으로 연결…", lambda: self._map_call(block, owner))
        menu.exec(self.tree.viewport().mapToGlobal(pos))

    def _map_call(self, block, owner):
        from types import SimpleNamespace
        from callmapqt import CallMappingDialogQt
        dialog = CallMappingDialogQt(self, SimpleNamespace(project=self.project, owner_kind=self.owner_kind,
                                                           item=self.item), block)
        if not dialog.exec() or not dialog.result:
            return
        index = next(i for i, x in enumerate(owner) if x is block)
        self._push()
        owner[index] = dialog.result["block"]
        rule = dialog.result.get("rule")
        if rule:
            self.project.setdefault("call_mappings", []).append(rule)
            self._mark_dirty()
        self._render(select=owner[index])

    # ---- 원본 효과 ----
    def _redecompose(self):
        """원본 코드를 다시 읽어 블록으로 푼다 (지금 블록은 되돌리기로 돌아올 수 있다)."""
        if self.on_decompose is None:
            return
        try:
            blocks, info = self.on_decompose()
        except Exception as exc:  # noqa: BLE001 - 실패해도 현재 효과는 그대로 둔다
            _warn(self, f"원본 코드를 블록으로 풀지 못했습니다.\n\n{type(exc).__name__}: {str(exc).strip() or repr(exc)}\n\n현재 효과는 유지됩니다.")
            return
        if not blocks:
            reason = str(info or "").strip() or "변환할 수 있는 코드가 없습니다. 원본 DLL과 카드 클래스를 확인해 주세요."
            _warn(self, f"원본 코드를 블록으로 풀지 못했습니다.\n\n{reason}\n\n현재 효과 블록은 그대로 유지됩니다.")
            return
        self._push()
        self.blocks[:] = blocks
        self._render()

    def _collapse_original(self):
        self._push()
        self.blocks[:] = [{"op": "original_play", "args": {}}]
        self._render()

    # ---- 파일 · 정의 · 레시피 ----
    def _save_file(self):
        if not self.blocks:
            QMessageBox.information(self, "블록 코딩", "저장할 블록이 없습니다.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "블록 모음 저장", "", "블록 모음 (*.sts2blocks)")
        if not path:
            return
        try:
            blocklibqt.save_blocks_file(path, self.blocks)
            blocklibqt.register_file_preset(path, self.blocks)
        except OSError as error:
            _warn(self, str(error))
            return
        self.presets = blocklibqt.load_presets()
        self._build_palette()

    def _load_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "블록 모음 불러오기", "", "블록 모음 (*.sts2blocks)")
        if not path:
            return
        try:
            blocks = blocklibqt.load_blocks_file(path)
            resolved = blocklibqt.resolve_preset(blocks, self.project, self._pick_replacement)
        except (OSError, ValueError, LookupError) as error:
            _warn(self, str(error) or repr(error))
            return
        if resolved is None:
            return
        self._push()
        self.blocks.extend(resolved)
        self._render(select=resolved[0])
        try:
            blocklibqt.register_file_preset(path, blocks)
        except OSError:
            return
        self.presets = blocklibqt.load_presets()
        self._build_palette()

    def _define_shared(self):
        if not self.blocks:
            return
        name, ok = QInputDialog.getText(self, "내 블록 정의",
                                        "이름을 입력하세요. 값 칸에서 변수 input1, input2를 선택하면 호출할 때 입력받습니다.")
        name = name.strip()
        if not ok or not name:
            return
        if name in self.project.get("shared_blocks", {}):
            count = blocklibqt.shared_uses(self.project, name)
            if not _ask(self, f"이 정의를 사용하는 카드 {count}장에 변경이 적용됩니다. 바꿀까요?"):
                return
        blocklibqt.define_shared(self.project, name, self.blocks)
        self._mark_dirty()

    def _open_recipes(self):
        dialog = RecipeDialogQt(self, self.project)
        if not dialog.exec() or not dialog.result:
            return
        self._push()
        self.blocks.append(dialog.result)
        self._render(select=dialog.result)

    def _mark_dirty(self):
        """이 창을 연 화면(프로그램 창)에 바뀌었다고 알린다."""
        widget = self.parentWidget()
        while widget is not None:
            if hasattr(widget, "mark_dirty"):
                widget.mark_dirty()
                return
            widget = widget.parentWidget()

    # ---- 작업 공간 ----
    def _selected_block_context(self):
        """고른 블록과 그 블록이 든 목록: (블록, 목록). Qt 는 dict 를 복사하므로 번호(id)로 찾는다."""
        item = self.tree.currentItem()
        if item is None:
            return None, None
        block = self._by_id.get(item.data(0, Qt.ItemDataRole.UserRole))
        owner = self._by_id.get(item.data(0, Qt.ItemDataRole.UserRole + 1))
        return block, owner

    def _selected_list(self):
        """새 블록을 넣을 목록: 고른 블록이 반복·만약이면 그 안, 아니면 고른 블록 뒤."""
        block, owner = self._selected_block_context()
        if block is None:
            return self.blocks
        if any(k in block for k in CONTAINER_KEYS) and _is_container(block):
            return block.setdefault("body", [])
        return owner

    def _render(self, select=None):
        self._last = copy.deepcopy(self.blocks)
        current = select
        self.tree.blockSignals(True)
        self.tree.clear()
        self._by_id = {id(self.blocks): self.blocks}
        self._arg_rows = []
        self._row_items = {}
        self._list_items = {}
        self._fill(self.tree.invisibleRootItem(), self.blocks)
        self.tree.blockSignals(False)
        if current is not None:
            item = self._find_item(current)
            if item is not None:
                self.tree.setCurrentItem(item)
        self._refresh_outputs()

    def _attach_row(self, node, b, walls=()):
        """블록 한 줄을 문장처럼 놓는다: 글과 칸이 이어지고, 칸은 그 자리에서 고친다. 기능 색으로 채운다."""
        box = _BlockRow(lambda: None)
        color = _category_color(b.get("op"))
        box.set_walls(walls)
        box.square_left = bool(walls) or any(k in b for k in CONTAINER_KEYS)
        if color:
            box.set_colors(color, _shade(color))
        flow = FlowLayout(box, spacing=6)
        # 여백: 왼쪽은 벽 오른쪽부터, 아래는 촉이 나오는 자리만큼 더 둔다
        flow.setContentsMargins(box.offset() + 10, 8, 10, 8 + _BlockRow.NOTCH_D)
        widgets = {}
        for key, kind in _arg_specs(b).items():
            widgets[key] = _ArgRow(self, b, key, kind, lambda block=b: self._changed(block))
            self._arg_rows.append(widgets[key])
        try:
            template = B.block_caption(b)
        except (KeyError, TypeError):
            template = str(b.get("op"))
        for piece in re.split(r"(\{[^{}]+\})", template):
            if not piece or piece.isspace():
                continue
            if piece.startswith("{") and piece[1:-1] in widgets:
                flow.addWidget(widgets[piece[1:-1]].widget)
                continue
            text = QLabel(piece.strip())
            text.setStyleSheet(f"color: {_ink_for(color) if color else Q.C['text']}; font-weight: 600;")
            flow.addWidget(text)
        try:
            help_text = BH.block_help(b) or ""
        except (KeyError, TypeError, AttributeError):
            help_text = ""
        if help_text:
            box.setToolTip(help_text)
        self._row_items[id(b)] = (node, box)
        self.tree.setItemWidget(node, 0, box)
        self._refresh_row_heights()

    def _refresh_row_heights(self):
        """칸이 줄을 넘기면 행이 높아진다. 중첩 깊이만큼 들여쓴 실제 너비로 행 높이를 다시 잡는다."""
        view = self.tree.viewport().width()
        for node, box in list(self._row_items.values()):
            if node is None or box is None:
                continue
            width = max(200, view - 8)
            node.setSizeHint(0, QSize(width, box.heightForWidth(width)))
        self.tree.scheduleDelayedItemsLayout()

    def _mark_selected(self, *_args):
        for node, box in list(self._row_items.values()):
            if box is not None:
                box.set_selected(node.isSelected())

    def _attach_bar(self, item, color, text, walls=()):
        """조건 블록의 안쪽 구분: '아니면' · '그 밖에' 와 C 자의 아랫변. 블록과 같은 퍼즐 모양·색으로, 벽 오른쪽에서 시작한다."""
        box = _BlockRow(lambda: None)
        box.set_walls(walls)
        box.square_left = True
        box.set_colors(color, _shade(color))
        flow = FlowLayout(box, spacing=6)
        if text:
            flow.setContentsMargins(box.offset() + 10, 4, 10, 4 + _BlockRow.NOTCH_D)
            label = QLabel(text)
            label.setStyleSheet(f"color: {_ink_for(color)}; font-weight: 600;")
            flow.addWidget(label)
        else:                                       # 아랫변: '아니면' 띠와 같은 높이로 맞춘다
            flow.setContentsMargins(box.offset() + 10, 8, 10, 8 + _BlockRow.NOTCH_D)
        self._row_items[("bar", id(box))] = (item, box)
        self.tree.setItemWidget(item, 0, box)
        self._refresh_row_heights()

    def _fill(self, parent, blocks, walls=()):
        self._by_id[id(blocks)] = blocks
        for b in blocks:
            self._by_id[id(b)] = b
            node = QTreeWidgetItem([""])            # 글은 행 위젯이 그린다
            node.setData(0, Qt.ItemDataRole.UserRole, id(b))
            node.setData(0, Qt.ItemDataRole.UserRole + 1, id(blocks))
            parent.addChild(node)
            self._attach_row(node, b, walls)
            keys = [k for k in CONTAINER_KEYS if k in b]
            color = _category_color(b.get("op")) if keys else None
            for key in keys:
                if key != "body":                     # '아니면' · '그 밖에' 는 구분 띠로 나눈다
                    divider = QTreeWidgetItem([""])
                    divider.setFlags(Qt.ItemFlag.NoItemFlags)
                    node.addChild(divider)
                    self._attach_bar(divider, color or "#888888", {"else": "아니면", "third": "그 밖에"}[key], walls)
                sub = QTreeWidgetItem([""])            # 안쪽 칸 (끌어 넣을 자리이기도 하다)
                # 이음새: 위 블록의 촉이 여기 들어가고, 조건 블록의 왼쪽 띠가 이어진다
                seam = _BlockRow(lambda: None)
                seam.outline = False
                seam.set_walls(list(walls) + [color or "#888888"])
                empty = not b[key]
                seam.set_colors(_tint(color or "#888888", 0.25) if empty else (color or "#888888"),
                                color or "#888888")
                height = _BlockRow.SLOT if empty else _BlockRow.SEAM
                seam.setFixedHeight(height)
                sub.setSizeHint(0, QSize(0, height))
                if empty:
                    seam.setToolTip("여기에 블록을 끌어 넣습니다")
                sub.setData(0, Qt.ItemDataRole.UserRole + 1, id(b))
                sub.setData(0, Qt.ItemDataRole.UserRole + 2, key)
                node.addChild(sub)
                self.tree.setItemWidget(sub, 0, seam)     # 트리에 붙인 뒤에 위젯을 붙여야 보인다
                sub.setExpanded(True)                  # 안쪽 블록은 항상 펼쳐서 감싸는 모양이 보이게 한다
                self._list_items[id(b[key])] = (sub, seam)
                self._fill(sub, b[key], list(walls) + [color or "#888888"])
            if keys:                                   # C 자의 아랫변
                arm = QTreeWidgetItem([""])
                arm.setFlags(Qt.ItemFlag.NoItemFlags)
                node.addChild(arm)
                self._attach_bar(arm, color or "#888888", "", walls)
                node.setExpanded(True)

    def _find_item(self, block):
        it = QTreeWidgetItemIterator(self.tree)
        while it.value() is not None:
            node = it.value()
            if node.data(0, Qt.ItemDataRole.UserRole) == id(block):
                return node
            it += 1
        return None

    def _switch_mode(self, block, mode):
        """실행 방식(묶음 안의 변형)을 바꾼다. 바꾼 방식에 맞는 칸을 다시 만든다."""
        if not mode or mode == (block.get("args") or {}).get("mode"):
            return
        self._push()
        try:
            F.switch(block, mode, B.SPECS)
        except (ValueError, KeyError) as error:
            self.history.pop()
            _warn(self, str(error))
            return
        self._render(select=block)

    def _changed(self, block=None):
        """칸 하나를 고쳤다: 되돌리기 기록을 남기고, 그 블록의 글과 결과만 새로 쓴다 (입력 중에 칸을 다시 만들지 않는다)."""
        self.history.append(self._last)
        self.history = self.history[-HISTORY_LIMIT:]
        self._last = copy.deepcopy(self.blocks)
        if block is None:
            block, _owner = self._selected_block_context()
        self._refresh_row_heights()
        self._refresh_outputs()

    # ---- 위치 바꾸기 · 복제 · 삭제 · 감싸기 ----
    def _move(self, delta):
        block, owner = self._selected_block_context()
        if block is None:
            return
        index = next(i for i, x in enumerate(owner) if x is block)
        j = index + delta
        if not 0 <= j < len(owner):
            return
        self._push()
        owner[index], owner[j] = owner[j], owner[index]
        self._render(select=block)

    def _duplicate(self):
        block, owner = self._selected_block_context()
        if block is None:
            return
        self._push()
        index = next(i for i, x in enumerate(owner) if x is block)
        copy_block = copy.deepcopy(block)
        owner.insert(index + 1, copy_block)
        self._render(select=copy_block)

    def _selected_blocks(self):
        """작업 공간에서 고른 블록들 (안에 든 블록은 바깥 블록과 함께 간다). 고른 것이 없으면 현재 블록."""
        items = self.tree.selectedItems()
        if not items and self.tree.currentItem() is not None:
            items = [self.tree.currentItem()]
        picked = [self._by_id.get(it.data(0, Qt.ItemDataRole.UserRole)) for it in items]
        return _top_only([b for b in picked if b is not None])

    def _take_out(self, blocks):
        for block in blocks:
            source, index = _locate(self.blocks, block)
            if source is not None:
                del source[index]

    def _remove_blocks(self, payload):
        """작업 공간의 블록을 라이브러리에 놓으면 지운다 (되돌리기로 되돌릴 수 있다)."""
        moved = _top_only([b for b in (self._by_id.get(i) for i in _payload_ids(payload)) if b is not None])
        if not moved:
            return False
        self._push()
        self._take_out(moved)
        self._render()
        return True

    def _delete(self):
        blocks = self._selected_blocks()
        if not blocks:
            return
        text = ("이 블록을 지울까요? (안에 든 블록도 함께 지워집니다)" if len(blocks) == 1
                else f"고른 블록 {len(blocks)}개를 지울까요? (안에 든 블록도 함께 지워집니다)")
        if not _ask(self, text):
            return
        self._push()
        self._take_out(blocks)
        self._render()

    def _wrap(self, kind):
        block, owner = self._selected_block_context()
        if block is None:
            return
        self._push()
        index = next(i for i, x in enumerate(owner) if x is block)
        wrapper = _new_block("repeat" if kind == "repeat" else "condition_branch")
        if kind == "repeat":
            wrapper.setdefault("body", [])
        wrapper.setdefault("body", []).append(block)
        owner[index] = wrapper
        self._render(select=wrapper)

    def clear_all(self):
        if not self.blocks:
            return
        if not _ask(self, "블록을 모두 지울까요? (되돌리기로 되돌릴 수 있습니다)"):
            return
        self._push()
        self.blocks.clear()
        self._render()

    # ---- 되돌리기 ----
    def _push(self):
        self.history.append(copy.deepcopy(self.blocks))
        self.history = self.history[-HISTORY_LIMIT:]

    def undo(self):
        if not self.history:
            return
        self.blocks[:] = self.history.pop()
        self._render()

    # ---- 결과 ----
    def _refresh_outputs(self):
        lines, errs = B.compile_blocks(self.blocks, self.project,
                                       M.card_event_context(self.item, self.card_event) if self.card_event
                                       else M._Ctx(self.owner_kind, self.item), "", allow_event=self.allow_event)
        self.code_view.setPlainText("\n".join(lines))
        self.error_label.setText("\n".join("⚠ " + x for x in dict.fromkeys(errs)))
        if self.auto.isChecked():
            for lang, box in self.desc.items():
                box.set_source(B.describe(self.blocks, self.project,
                                          "power" if self.owner_kind == "summon" else self.owner_kind, lang))

    def ok(self):
        C = M.card_event_context(self.item, self.card_event) if self.card_event else M._Ctx(self.owner_kind, self.item)
        lines, errs = B.compile_blocks(self.blocks, self.project, C, "", allow_event=self.allow_event)
        if errs and not _ask(self, "블록에 문제가 있습니다:\n\n" + "\n".join(dict.fromkeys(errs)) + "\n\n그래도 저장할까요?"):
            return
        self.result = {"blocks": self.blocks, "code": "\n".join(lines), "auto_text": bool(self.auto.isChecked()),
                       "upgraded_text": {lang: box.source().strip() for lang, box in self.upgraded.items()},
                       "text_ko": self.desc["ko"].source().strip(),
                       "text_en": self.desc["en"].source().strip(),
                       "text_zh": self.desc["zh"].source().strip()}
        self.accept()


def edit_blocks(parent, project, owner_kind, item, blocks, **kwargs):
    """블록 편집 창을 연다. 저장하면 결과(dict), 취소하면 None."""
    dialog = BlockEditorQt(parent, project, owner_kind, item, blocks, **kwargs)
    if dialog.exec() and dialog.result is not None:
        return dialog.result
    return None


def _is_container(block):
    try:
        spec = B.block_spec(block)
    except (KeyError, TypeError):
        return False
    return bool(spec.get("body") or spec.get("else") or block.get("body") is not None)


def _new_block(op):
    """새 블록: 칸마다 기본값을 넣는다."""
    block = {"op": op, "args": {}}
    try:
        spec = B.block_spec(block)
        for key, (kind, default) in spec.get("args", {}).items():
            block["args"][key] = copy.deepcopy(default)
        if spec.get("body"):
            block["body"] = []
    except (KeyError, TypeError):
        pass
    return block


def palette_name(op):
    """팔레트에 보이는 이름 (없으면 블록 글을 쓴다)."""
    return B.PALETTE_NAMES.get(op) or (B.SPECS.get(op) or {}).get("ko", op or "")

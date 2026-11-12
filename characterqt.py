"""'캐릭터' 탭의 Qt 版: 내 캐릭터 · 가져온 캐릭터 편집 (이름·소개·체력·골드·덱·유물·그림·전투 모습·모션·미리보기).

가져온 캐릭터는 원래 모드의 것이라 색·카드 풀·테두리·구체 칸은 숨기고, 나머지는 바꿀 수 있다 (Tk 와 같다).
카드 테두리 편집기·아키텍트 대사 편집은 대화상자로 연다.
"""
import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QPushButton,
                               QRadioButton, QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget, QButtonGroup)

import cardframe as CF
from cardlibqt import CARD_MIME
from itemtabqt import _CardRowDelegate
import modgen as M
import preview_qt as PQ
import qtkit as Q
from combatqt import combat_pixmap
from pets import frame_ms

LANGS = [("ko", "한국어"), ("en", "영어"), ("zh", "중국어 간체")]
ART_FIELDS = [
    ("energy_icon_image", "카드 에너지 구슬", "74×74 (비우면 임시 외형 캐릭터 것)"),
    ("energy_text_icon_image", "설명용 에너지 아이콘", "24×24"),
    ("icon_image", "아이콘", "88×88"),
    ("select_image", "선택 화면 초상화", "132×195"),
    ("select_locked_image", "선택 화면 (잠김)", "132×195"),
    ("map_marker_image", "지도 표시", "49×64"),
    ("select_bg_image", "선택 화면 전체 배경", "1920×1080 (캐릭터를 고르면 화면 전체를 채움)"),
]
ENERGY_KEYS = ("energy_icon_image", "energy_text_icon_image")
MOTIONS = (("attack_frames", "공격 모션"), ("hit_frames", "피격 모션"))
MINE_ONLY = {"id", "color", "card_h", "card_s", "card_v", *ENERGY_KEYS}              # 가져온 캐릭터는 원래 코드가 정한다
MINE_FLAGS = ("enabled", "placeholder", "frame_style", "orb_slots", "show_stars")
IMPORTED_ONLY = {"gold"}                                                 # 시작 골드: 비우면 원래대로


def _set_combo(combo, value):
    Q.set_combo_value(combo, value)


def _set_drop_hover(widget, cls_name, on):
    """라이브러리 항목이 끌려 들어왔을 때 놓을 수 있는 목록에 강조 테두리를 보인다."""
    if getattr(widget, "_drop_hover", False) == on:
        return
    widget._drop_hover = on
    widget.setStyleSheet(f"{cls_name} {{ border: 2px solid {Q.C['accent']}; }}" if on else "")


class _DeckTable(QTableWidget):
    """시작 덱 목록: 카드 라이브러리의 카드를 끌어 놓으면 dropped 신호를 보낸다."""
    dropped = Signal()

    def dragEnterEvent(self, event):
        _set_drop_hover(self, "QTableWidget", self._take(event))

    def dragMoveEvent(self, event):
        self._take(event)

    def dragLeaveEvent(self, event):
        _set_drop_hover(self, "QTableWidget", False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        _set_drop_hover(self, "QTableWidget", False)
        if self._take(event):
            self.dropped.emit()

    def _take(self, event):
        if event.mimeData().hasFormat(CARD_MIME):
            event.acceptProposedAction()
            return True
        event.ignore()
        return False


class _RelicList(QListWidget):
    """시작 유물 목록: 라이브러리의 항목을 끌어 놓으면 dropped 신호를 보낸다."""
    dropped = Signal()

    def dragEnterEvent(self, event):
        _set_drop_hover(self, "QListWidget", self._take(event))

    def dragMoveEvent(self, event):
        self._take(event)

    def dragLeaveEvent(self, event):
        _set_drop_hover(self, "QListWidget", False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        _set_drop_hover(self, "QListWidget", False)
        if self._take(event):
            self.dropped.emit()

    def _take(self, event):
        if event.mimeData().hasFormat(CARD_MIME):
            event.acceptProposedAction()
            return True
        event.ignore()
        return False


class _DeckRowDelegate(_CardRowDelegate):
    """시작 덱 한 줄: 카드 목록과 같은 모양, 오른쪽 끝에 장수. 원작·없는 카드는 이름 글만 보인다."""

    def _entry(self, index):
        deck = self.tab.ch().get("deck", [])
        return deck[index.row()] if 0 <= index.row() < len(deck) else None

    def _card_at(self, index):
        entry = self._entry(index)
        if entry is None:
            return None
        card = next((c for c in self.tab.project["cards"] if c["id"] == entry["card"]), None)
        if card is None:                          # 원작·원래 코드 카드: 목록 글을 이름으로 쓴다
            label = index.data(Qt.ItemDataRole.DisplayRole) or entry["card"]
            return {"name_ko": label, "no_cost": True, "type": "", "rarity": ""}
        return card

    def _extra_text(self, index):
        entry = self._entry(index)
        return f"× {entry['count']}" if entry else ""


class _HeightGrip(QWidget):
    """목록 바로 아래의 손잡이: 끌면 목록(target)의 높이가 바뀐다. 고정 높이라 아래 칸이 목록을 눌러 줄이지 않는다."""

    def __init__(self, target, height):
        super().__init__()
        self.target = target
        self._drag = None
        target.setFixedHeight(height)
        self.setFixedHeight(10)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("위아래로 끌어서 목록 높이를 바꿉니다")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(Q.C["line2"]))
        painter.drawRoundedRect(self.width() // 2 - 24, 3, 48, 4, 2, 2)

    def mousePressEvent(self, event):
        self._drag = (event.globalPosition().y(), self.target.height())

    def mouseMoveEvent(self, event):
        if self._drag:
            y0, h0 = self._drag
            self.target.setFixedHeight(max(60, int(h0 + event.globalPosition().y() - y0)))

    def mouseReleaseEvent(self, _event):
        self._drag = None


class CharacterPanelQt(QWidget):
    def __init__(self, project, on_change=None, ui=1.0, parent=None):
        super().__init__(parent)
        self.project = project
        self.on_change = on_change
        self.ui = ui
        self.assets_fn = None      # 게임 그림을 읽는 함수 (app 이 넣는다)
        self.cur = None            # None = 내 캐릭터, 숫자 = 가져온 캐릭터 순번
        self._loading = False
        self._fields = {}
        self._mine = []            # 가져온 캐릭터일 때 숨기는 칸
        self._gold = []            # 가져온 캐릭터일 때만 보이는 칸
        self.card_drop_fn = None   # 라이브러리에서 끌어 놓은 카드를 가져온다 (app 이 넣는다, done(카드 id) 로 알림)
        self.relic_drop_fn = None  # 라이브러리에서 끌어 놓은 유물을 가져온다 (app 이 넣는다, done(유물 id) 로 알림)
        self.motion_lists = {}
        self.motion_times = {}
        self._motion_token = 0     # 모션 재생을 멈추는 번호 (바뀌면 이전 재생은 멈춘다)

        root = QHBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        form = QVBoxLayout(body)
        root.addWidget(scroll, 1)

        form.addWidget(self._selector_bar())

        self.enabled = QCheckBox("새 캐릭터 만들기  (끄면 카드는 무색, 유물/물약은 공용 풀에 추가됩니다)")
        self.enabled.toggled.connect(self.changed)
        form.addWidget(self.enabled)
        self._mine.append(self.enabled)

        basics = QGridLayout()
        self._text(basics, 0, 0, "캐릭터 ID (영문 소문자_)", "id", mine=True)
        self._text(basics, 0, 2, "시작 체력", "hp")
        gold_label = QLabel("시작 골드 (비우면 원래대로)")
        gold = QLineEdit()
        gold.textChanged.connect(lambda _t: self.changed())
        basics.addWidget(gold_label, 1, 0)
        basics.addWidget(gold, 1, 1)
        self._fields["gold"] = gold
        self._gold += [gold_label, gold]
        form.addLayout(basics)

        names = QGridLayout()
        for row, (lang, label) in enumerate(LANGS):
            self._text(names, row, 0, f"이름 ({label})", f"name_{lang}")
            self._text(names, row, 2, f"소개 ({label})", f"desc_{lang}")
        form.addLayout(names)

        look = QGridLayout()
        color_label = QLabel("대표 색상")
        look.addWidget(color_label, 0, 0)
        color = QLineEdit()
        color.textChanged.connect(lambda _t: self.changed())
        look.addWidget(color, 0, 1)
        self._fields["color"] = color
        self.swatch = QLabel()
        self.swatch.setFixedSize(40, 20)
        look.addWidget(self.swatch, 0, 2)
        pick = QPushButton("고르기…")
        pick.clicked.connect(self.pick_color)
        look.addWidget(pick, 0, 3)
        look.addWidget(QLabel("임시 외형 (애니메이션)"), 1, 0)
        self.placeholder = QComboBox()
        for value, label in M.PLACEHOLDER_CHARS:
            self.placeholder.addItem(label, value)
        self.placeholder.currentIndexChanged.connect(lambda _i: self.changed())
        look.addWidget(self.placeholder, 1, 1)
        look.addWidget(QLabel("카드 테두리"), 1, 2)
        self.frame_combo = QComboBox()
        self.frame_combo.currentIndexChanged.connect(lambda _i: self.changed())
        look.addWidget(self.frame_combo, 1, 3)
        frame_edit = QPushButton("테두리 편집…")
        frame_edit.clicked.connect(self.edit_frames)
        look.addWidget(frame_edit, 1, 4)
        look_box = QWidget()
        look_box.setLayout(look)
        form.addWidget(look_box)
        self._mine.append(look_box)

        hsv = QHBoxLayout()
        hsv.addWidget(QLabel("카드 뒷면 HSV (0~1)"))
        for key, label in (("card_h", "H"), ("card_s", "S"), ("card_v", "V")):
            hsv.addWidget(QLabel(label))
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.valueChanged.connect(lambda _v: self.changed())
            hsv.addWidget(spin)
            self._fields[key] = spin
        hsv.addWidget(QLabel("1 / 1 / 1 이 기본"))
        hsv.addStretch(1)
        hsv_box = QWidget()
        hsv_box.setLayout(hsv)
        form.addWidget(hsv_box)
        self._mine.append(hsv_box)

        counts = QHBoxLayout()
        counts.addWidget(QLabel("구체 슬롯 수"))
        self.orb_slots = QSpinBox()
        self.orb_slots.setRange(0, 10)
        self.orb_slots.valueChanged.connect(lambda _v: self.changed())
        counts.addWidget(self.orb_slots)
        self.show_stars = QCheckBox("별 카운터 항상 표시 (리젠트처럼 별을 쓰는 캐릭터)")
        self.show_stars.toggled.connect(self.changed)
        counts.addWidget(self.show_stars)
        counts.addStretch(1)
        counts_box = QWidget()
        counts_box.setLayout(counts)
        form.addWidget(counts_box)
        self._mine.append(counts_box)

        form.addWidget(self._deck_box())
        form.addWidget(self._relic_box())
        architect = QPushButton("아키텍트 대사 편집…")
        architect.clicked.connect(self.edit_architect)
        form.addWidget(architect)
        form.addWidget(self._art_box())
        form.addWidget(self._combat_box())
        form.addStretch(1)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {Q.C['danger']};")
        form.addWidget(self.status)

        side = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("미리보기"))
        self._lang_group = QButtonGroup(self)
        for i, (value, label) in enumerate(LANGS):
            button = QRadioButton(label)
            button.setChecked(value == "ko")
            button.toggled.connect(lambda on, v=value: on and self.set_preview_lang(v))
            self._lang_group.addButton(button, i)
            top.addWidget(button)
        side.addLayout(top)
        self.preview_lang = "ko"
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview.setStyleSheet(f"border: 1px solid {Q.C['line2']}; padding: 6px; background: {Q.C['stage']};")
        side.addWidget(self.preview, 0, Qt.AlignmentFlag.AlignTop)
        self.preview_icons = QLabel()                    # 선택 화면 아래에 따로 보이는 작은 그림들
        self.preview_icons.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_icons.setStyleSheet(f"border: 1px solid {Q.C['line2']}; padding: 6px; background: {Q.C['stage']};")
        side.addWidget(self.preview_icons, 0, Qt.AlignmentFlag.AlignTop)
        side.addStretch(1)
        root.addLayout(side)

        self.load(project)

    # ---- 칸 만들기 ----
    def _selector_bar(self):
        box = QWidget()
        row = QVBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        top = QHBoxLayout()
        top.addWidget(QLabel("편집할 캐릭터"))
        self.char_combo = QComboBox()
        self.char_combo.setMinimumWidth(320)
        self.char_combo.currentIndexChanged.connect(lambda _i: self._picked_char())
        top.addWidget(self.char_combo)
        top.addStretch(1)
        row.addLayout(top)
        self.sel_note = QLabel("")
        self.sel_note.setWordWrap(True)
        row.addWidget(self.sel_note)
        self.selbar = box
        return box

    def _picked_char(self):
        if not self._loading:
            self.select_char(self.char_combo.currentData())

    def _text(self, grid, row, col, label, key, mine=False):
        label_widget = None
        if label:
            label_widget = QLabel(label)
            grid.addWidget(label_widget, row, col)
        edit = QLineEdit()
        edit.textChanged.connect(lambda _t: self.changed())
        grid.addWidget(edit, row, col + 1)
        self._fields[key] = edit
        if mine:
            self._mine += [w for w in (label_widget, edit) if w is not None]
        return edit

    def _deck_box(self):
        box = QGroupBox("시작 덱")
        layout = QVBoxLayout(box)
        self.deck_table = _DeckTable(0, 1)
        self.deck_table.horizontalHeader().setVisible(False)          # 카드 목록처럼 머리글 없이 줄만 보인다
        self.deck_table.horizontalHeader().setStretchLastSection(True)
        self.deck_table.verticalHeader().setVisible(False)
        self.deck_table.verticalHeader().setDefaultSectionSize(_DeckRowDelegate.ROW_H)
        self.deck_table.setItemDelegate(_DeckRowDelegate(self))
        self.deck_table.setShowGrid(False)
        self.deck_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deck_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.deck_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.deck_table.setAcceptDrops(True)
        self.deck_table.setToolTip("카드 라이브러리의 카드를 여기로 끌어 놓으면 한 장 들어갑니다")
        self.deck_table.dropped.connect(self.deck_drop)
        layout.addWidget(self.deck_table)
        layout.addWidget(_HeightGrip(self.deck_table, 150))
        row = QHBoxLayout()
        self.deck_card = QComboBox()
        self.deck_card.setMinimumWidth(260)
        self.deck_count = QSpinBox()
        self.deck_count.setRange(1, 20)
        add = QPushButton("추가 / 장수 변경")
        add.clicked.connect(self.deck_add)
        remove = QPushButton("선택 삭제")
        remove.clicked.connect(self.deck_remove)
        self.deck_total = QLabel("")
        for w in (self.deck_card, self.deck_count, add, remove, self.deck_total):
            row.addWidget(w)
        layout.addLayout(row)
        return box

    def _relic_box(self):
        box = QGroupBox("시작 유물")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.relic_combo = QComboBox()
        self.relic_combo.setMinimumWidth(320)
        add = QPushButton("유물 추가")
        add.clicked.connect(self.relic_add)
        row.addWidget(self.relic_combo, 1)
        row.addWidget(add)
        layout.addLayout(row)
        self.relic_list = _RelicList()
        self.relic_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.relic_list.setAcceptDrops(True)
        self.relic_list.setToolTip("라이브러리의 유물을 여기로 끌어 놓으면 시작 유물에 들어갑니다")
        self.relic_list.dropped.connect(self.relic_drop)
        layout.addWidget(self.relic_list)
        layout.addWidget(_HeightGrip(self.relic_list, 120))
        remove = QPushButton("선택 삭제")
        remove.clicked.connect(self.relic_remove)
        layout.addWidget(remove)
        layout.addWidget(QLabel("시작 시 지급할 유물을 고르세요. 여러 개를 추가할 수 있습니다. (희귀도 '시작' 권장)"))
        return box

    def _thumb_label(self):
        """그림 미리보기 칸: 고른 PNG 를 작게 보인다 (없으면 '없음')."""
        thumb = QLabel()
        thumb.setFixedSize(76, 76)
        thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        thumb.setStyleSheet(f"border: 1px solid {Q.C['line2']}; background: {Q.C['surface']}; color: {Q.C['muted']};")
        thumb.setText("없음")
        return thumb

    def _show_thumb(self, thumb, path):
        path = (path or "").strip().strip('"')
        if not path:
            thumb.setPixmap(QPixmap())
            thumb.setText("없음")
            return
        pix = QPixmap(path) if os.path.isfile(path) else QPixmap()
        if pix.isNull():
            thumb.setPixmap(QPixmap())
            thumb.setText("못 읽음")
            return
        thumb.setPixmap(pix.scaled(70, 70, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))

    def _art_box(self):
        box = QGroupBox("캐릭터 그림 (선택 사항, 비우면 임시 외형 캐릭터의 그림을 씀)")
        grid = QGridLayout(box)
        for row, (key, label, hint) in enumerate(ART_FIELDS):
            thumb = self._thumb_label()
            grid.addWidget(thumb, row, 0)
            name = QLabel(label)
            grid.addWidget(name, row, 1)
            edit = QLineEdit()
            edit.textChanged.connect(lambda _t, e=edit, th=thumb: (self._show_thumb(th, e.text()), self.changed()))
            grid.addWidget(edit, row, 2)
            browse = QPushButton("찾기…")
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            grid.addWidget(browse, row, 3)
            hint_label = QLabel(hint)
            grid.addWidget(hint_label, row, 4)
            self._fields[key] = edit
            if key in ENERGY_KEYS:            # 에너지 아이콘은 원래 코드가 정한다 (가져온 캐릭터에서 숨긴다)
                self._mine += [name, edit, browse, hint_label, thumb]
        return box

    def _combat_box(self):
        box = QGroupBox("전투 모습")
        col = QVBoxLayout(box)
        grid = QGridLayout()
        combat_thumb = self._thumb_label()
        grid.addWidget(combat_thumb, 0, 0)
        grid.addWidget(QLabel("전투 그림 (PNG)"), 0, 1)
        combat = QLineEdit()
        combat.textChanged.connect(lambda _t, e=combat, th=combat_thumb: (self._show_thumb(th, e.text()), self.changed()))
        grid.addWidget(combat, 0, 2)
        browse = QPushButton("찾기…")
        browse.clicked.connect(lambda _=False: self._browse(combat))
        grid.addWidget(browse, 0, 3)
        grid.addWidget(QLabel("비우면 가져온 캐릭터는 원래 모습, 새 캐릭터는 임시 외형을 씁니다"), 0, 4)
        self._fields["combat_image"] = combat
        col.addLayout(grid)
        tune = QHBoxLayout()
        tune.addWidget(QLabel("크기 %"))
        self.combat_scale = QSpinBox()
        self.combat_scale.setRange(10, 400)
        self.combat_scale.setSingleStep(5)
        self.combat_scale.valueChanged.connect(lambda _v: self.changed())
        tune.addWidget(self.combat_scale)
        tune.addWidget(QLabel("띄우기(px)"))
        self.combat_lift = QSpinBox()
        self.combat_lift.setRange(-200, 300)
        self.combat_lift.setSingleStep(5)
        self.combat_lift.valueChanged.connect(lambda _v: self.changed())
        tune.addWidget(self.combat_lift)
        self.combat_flip = QCheckBox("좌우 반전 (캐릭터는 오른쪽을 봐야 함)")
        self.combat_flip.toggled.connect(self.changed)
        tune.addWidget(self.combat_flip)
        tune.addStretch(1)
        col.addLayout(tune)
        self.combat_canvas = QLabel()
        self.combat_canvas.setFixedSize(300, 320)
        self.combat_canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.combat_canvas)
        col.addWidget(QLabel("기본 전투 그림을 지정한 뒤 모션에 사용할 PNG를 재생 순서대로 추가하세요."))
        for key, title in MOTIONS:
            motion = QGroupBox(title)
            layout = QVBoxLayout(motion)
            listing = QListWidget()
            listing.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            listing.setMaximumHeight(90)
            layout.addWidget(listing)
            self.motion_lists[key] = listing
            row = QHBoxLayout()
            row.addWidget(QLabel("프레임당 ms"))
            timing = QSpinBox()
            timing.setRange(16, 5000)
            timing.setSingleStep(10)
            timing.valueChanged.connect(lambda _v, k=key: self.motion_speed_changed(k))
            row.addWidget(timing)
            self.motion_times[key] = timing
            for label, action in (("PNG 추가", "add"), ("선택 제거", "remove"), ("재생", "play")):
                button = QPushButton(label)
                button.clicked.connect(lambda _=False, k=key, a=action: self.edit_motion(k, a))
                row.addWidget(button)
            row.addStretch(1)
            layout.addLayout(row)
            col.addWidget(motion)
        return box

    # ---- 읽기 · 쓰기 ----
    def ch(self):
        imp = M.imported_characters(self.project)
        if self.cur is not None and 0 <= self.cur < len(imp):
            return imp[self.cur]
        return self.project["character"]

    def imported(self):
        return self.cur is not None and self.ch() is not self.project["character"]

    def assets(self):
        return self.assets_fn() if self.assets_fn else None

    def select_char(self, value):
        self.cur = None if value in ("", "mine", None) else int(value)
        self.load(self.project)

    def load(self, project):
        """프로젝트를 바꿔 끼운다(열기·되돌리기). 칸을 다시 채우되 바뀐 것으로 치지 않는다."""
        self.project = project
        if self.cur is not None and self.cur >= len(M.imported_characters(project)):
            self.cur = None
        ch = self.ch()
        self._loading = True
        try:
            self._fill_char_choices()
            self.enabled.setChecked(bool(ch.get("enabled")))
            for key, widget in self._fields.items():
                if isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(ch.get(key, 1.0)))
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(ch.get(key, "")))
            _set_combo(self.placeholder, ch.get("placeholder", "ironclad"))
            self.frame_combo.clear()
            for value, label in CF.options(self.project, for_card=False):
                self.frame_combo.addItem(label, value)
            _set_combo(self.frame_combo, ch.get("frame_style", ""))
            self.orb_slots.setValue(int(ch.get("orb_slots", 0) or 0))
            self.show_stars.setChecked(bool(ch.get("show_stars")))
            self.combat_scale.setValue(int(ch.get("combat_scale", 100) or 100))
            self.combat_lift.setValue(int(ch.get("combat_lift", 0) or 0))
            self.combat_flip.setChecked(bool(ch.get("combat_flip")))
            for key, spin in self.motion_times.items():
                spin.setValue(frame_ms(ch, key))
            self._refresh_deck_and_relic_choices()
            self.refresh_deck()
            self.refresh_relics()
        finally:
            self._loading = False
        self._apply_kind_visibility()
        self.update_swatch()
        self.update_preview()
        self.refresh_motion_lists()
        self.update_combat_preview()

    def _fill_char_choices(self):
        imp = M.imported_characters(self.project)
        self.selbar.setVisible(bool(imp))
        self.char_combo.blockSignals(True)
        self.char_combo.clear()
        mine_label = "내 캐릭터 (새로 만들기)" + ("" if self.project["character"].get("enabled") else " — 꺼짐")
        self.char_combo.addItem(mine_label, "mine")
        for i, c in enumerate(imp):
            self.char_combo.addItem(f"가져온 캐릭터: {M.text(c, 'name', 'ko') or c['class']} ({c['class']})", str(i))
        self.char_combo.setCurrentIndex(self.char_combo.findData("mine" if not self.imported() else str(self.cur)))
        self.char_combo.blockSignals(False)
        if imp:
            self.sel_note.setText(
                ("원래 모드의 캐릭터입니다. 이름·소개·체력·골드·시작 덱·시작 유물·선택 화면 그림·아이콘·전투 모습·모션·아키텍트 대사를 바꿀 수 있습니다. "
                 "전투 그림을 비우면 원래 모습이 유지됩니다. 색·카드 풀은 원래 설정을 씁니다.")
                if self.imported() else f"이 모드에는 가져온 캐릭터가 {len(imp)}명 있습니다. 위에서 골라 편집하세요.")

    def _apply_kind_visibility(self):
        imported = self.imported()
        for widget in self._mine:
            widget.setVisible(not imported)
        for widget in self._gold:
            widget.setVisible(imported)

    def changed(self, *_):
        if self._loading:
            return
        ch = self.ch()
        imported = self.imported()
        for key, widget in self._fields.items():
            if imported and key in MINE_ONLY:
                continue
            if not imported and key in IMPORTED_ONLY:
                continue
            if isinstance(widget, QDoubleSpinBox):
                ch[key] = float(widget.value())
                continue
            val = widget.text().strip()
            if key == "hp":
                try:
                    ch[key] = int(val)
                except ValueError:
                    pass
            elif key == "gold":
                if not val:
                    ch.pop("gold", None)
                else:
                    try:
                        ch[key] = int(val)
                    except ValueError:
                        pass
            elif key.endswith("_image"):
                ch[key] = val.strip('"')
            else:
                ch[key] = val
        if not imported:
            ch["enabled"] = self.enabled.isChecked()
            ch["placeholder"] = self.placeholder.currentData()
            ch["frame_style"] = self.frame_combo.currentData()
            ch["orb_slots"] = int(self.orb_slots.value())
            ch["show_stars"] = bool(self.show_stars.isChecked())
        ch["combat_scale"] = int(self.combat_scale.value())
        ch["combat_lift"] = int(self.combat_lift.value())
        ch["combat_flip"] = bool(self.combat_flip.isChecked())
        self.update_swatch()
        self.update_preview()
        self.update_combat_preview()
        if self.on_change:
            self.on_change()

    def _notify(self):
        if self.on_change:
            self.on_change()

    def edit_frames(self):
        from cardframeqt import FrameStyleDialogQt
        sel = self.ch().get("frame_style") or None
        dialog = FrameStyleDialogQt(self, self.project, self.assets_fn,
                                    select=sel if sel not in ("", CF.GAME) else None, on_change=self._frames_changed)
        dialog.exec()

    def _frames_changed(self):
        self.load(self.project)
        self._notify()

    def edit_architect(self):
        from dialogsqt import ArchitectDialogQt
        if ArchitectDialogQt(self, self.project, self.ch()).exec():
            self._notify()

    def refresh_choices(self):
        """카드·유물 목록이 바뀌면 덱·유물 고르기 목록을 다시 채운다."""
        self._refresh_deck_and_relic_choices()
        self.refresh_deck()
        self.refresh_relics()

    # ---- 색 · 그림 ----
    def update_swatch(self):
        c = self._fields["color"].text().strip()
        color = c if M.HEX_RE.match(c) and c.startswith("#") else "#" + c.lstrip("#")
        self.swatch.setStyleSheet(f"background: {color if M.HEX_RE.match(color) else Q.C['muted']};")

    def pick_color(self):
        current = self._fields["color"].text().strip()
        start = QColor(current if M.HEX_RE.match(current) else "#ffffff")
        chosen = QColorDialog.getColor(start, self, "대표 색상 고르기")
        if chosen.isValid():
            self._fields["color"].setText(chosen.name())

    def _browse(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "그림 고르기", "", "PNG 이미지 (*.png);;모든 파일 (*.*)")
        if path:
            edit.setText(os.path.normpath(path))

    # ---- 덱 · 유물 ----
    def _card_choices(self):
        cards = list(self.project["cards"])
        cards.extend({"id": "game:" + entry, "name_ko": label + " · 원작"}
                     for entry, label in self.ch().get("game_cards", {}).items())
        return cards

    def _refresh_deck_and_relic_choices(self):
        self.deck_card.clear()
        for c in self._card_choices():
            self.deck_card.addItem(f"{c.get('name_ko') or c['id']} ({c['id']})", c["id"])
        self.relic_combo.clear()
        for r in self.project["relics"]:
            self.relic_combo.addItem(
                f"{r.get('name_ko') or r['id']} ({r['id']}) - {M.label_of(M.RELIC_RARITIES, r['rarity'])}", r["id"])
        for key, label in self.ch().get("game_relics", {}).items():
            self.relic_combo.addItem(label + " · 원작", "game:" + key)

    def refresh_deck(self):
        names = {c["id"]: c.get("name_ko") or c["id"] for c in self._card_choices()}
        deck = self.ch().get("deck", [])
        self.deck_table.setRowCount(0)
        total = 0
        for d in deck:
            row = self.deck_table.rowCount()
            self.deck_table.insertRow(row)
            if d["card"].startswith("raw:"):
                label = f"원래 코드: {d['card'][4:].split('.')[-1]}"
            else:
                label = f"{names.get(d['card'], '⚠ 없음')} ({d['card']})"
            self.deck_table.setItem(row, 0, QTableWidgetItem(label))
            total += int(d["count"])
        self.deck_total.setText(f"총 {total}장")

    def deck_add(self):
        cid = self.deck_card.currentData()
        if cid:
            self._put_in_deck(cid, max(1, int(self.deck_count.value())))

    def deck_drop(self):
        """카드 라이브러리에서 끌어 놓은 카드: 가져온 뒤 덱에 한 장 넣는다."""
        if self.card_drop_fn is not None:
            self.card_drop_fn(lambda cid: self._put_in_deck(cid, 1, add=True))

    def _put_in_deck(self, cid, n, add=False):
        deck = self.ch().setdefault("deck", [])
        for d in deck:
            if d["card"] == cid:
                d["count"] = d["count"] + n if add else n
                break
        else:
            deck.append({"card": cid, "count": n})
        self.refresh_deck()
        self._notify()

    def deck_remove(self):
        row = self.deck_table.currentRow()
        if row < 0:
            return
        del self.ch()["deck"][row]
        self.refresh_deck()
        self._notify()

    def refresh_relics(self):
        relics = {r["id"]: r for r in self.project["relics"]}
        self.relic_list.clear()
        for relic_id in self.ch().get("relics", []):
            relic = relics.get(relic_id)
            if relic is None:
                if relic_id.startswith("raw:"):
                    label = f"원래 코드: {relic_id[4:].split('.')[-1]}"
                elif relic_id.startswith("game:"):
                    label = self.ch().get("game_relics", {}).get(relic_id[5:], f"⚠ 없음 ({relic_id})")
                else:
                    label = f"⚠ 없음 ({relic_id})"
            else:
                label = f"{relic.get('name_ko') or relic_id} ({relic_id})"
            self.relic_list.addItem(label)

    def relic_add(self):
        relic_id = self.relic_combo.currentData()
        if relic_id:
            self._put_relic(relic_id)

    def relic_drop(self):
        """라이브러리에서 끌어 놓은 유물: 가져온 뒤 시작 유물에 넣는다."""
        if self.relic_drop_fn is not None:
            self.relic_drop_fn(self._put_relic)

    def _put_relic(self, relic_id):
        ids = self.ch().setdefault("relics", [])
        if relic_id not in ids:
            ids.append(relic_id)
            self.refresh_relics()
            self._notify()

    def relic_remove(self):
        selected = {self.relic_list.row(item) for item in self.relic_list.selectedItems()}
        if not selected:
            return
        self.ch()["relics"] = [r for i, r in enumerate(self.ch().get("relics", [])) if i not in selected]
        self.refresh_relics()
        self._notify()

    # ---- 전투 모습 · 모션 ----
    def motion_speed_changed(self, key):
        if self._loading:
            return
        value = int(self.motion_times[key].value())
        character = self.ch()
        if frame_ms(character, key) != value:
            character[key + "_ms"] = value
            self._notify()

    def refresh_motion_lists(self):
        for key, listing in self.motion_lists.items():
            listing.clear()
            for i, frame in enumerate(self.ch().get(key, []), 1):
                listing.addItem(f"{i}. {os.path.basename(frame['image'])}")

    def edit_motion(self, key, action):
        ch = self.ch()
        frames = ch.get(key, [])
        if action == "play":
            self._play_motion(key)
            return
        if action == "add":
            paths, _ = QFileDialog.getOpenFileNames(self, "모션 그림 고르기", "", "PNG 이미지 (*.png)")
            if not paths:
                return
            ch[key] = frames + [{"image": path} for path in paths]
        else:
            row = self.motion_lists[key].currentRow()
            if row < 0:
                return
            ch[key] = [frame for i, frame in enumerate(frames) if i != row]
        self._notify()
        self.refresh_motion_lists()
        self.update_combat_preview()

    def _play_motion(self, key):
        ch = self.ch()
        frames = list(ch.get(key, []))
        if not frames:
            return
        self._motion_token += 1
        token = self._motion_token

        def show(index):
            if token != self._motion_token:
                return
            if index == len(frames):
                self.update_combat_preview()
                return
            self.combat_canvas.setPixmap(combat_pixmap(self.assets(), frames[index]["image"], ch.get("combat_scale"),
                                                       ch.get("combat_flip"), ch.get("combat_lift"), ""))
            QTimer.singleShot(frame_ms(ch, key), lambda: show(index + 1))
        show(0)

    def update_combat_preview(self):
        self._motion_token += 1          # 그림을 새로 그리면 재생 중인 모션은 멈춘다
        ch = self.ch()
        if ch.get("combat_image"):
            self.combat_canvas.setPixmap(combat_pixmap(self.assets(), ch.get("combat_image"), ch.get("combat_scale"),
                                                       ch.get("combat_flip"), ch.get("combat_lift"),
                                                       M.text(ch, "name", "ko")))
        else:
            self.combat_canvas.clear()
            self.combat_canvas.setText("(그림 없음 — 임시 외형\n캐릭터의 애니메이션)")

    # ---- 미리보기 ----
    def set_preview_lang(self, lang):
        self.preview_lang = lang
        self.update_preview()

    def update_preview(self):
        u = self.ui
        P = self.project
        if self.imported():
            ich = self.ch()
            fake = dict(P["character"])
            fake.update({k: v for k, v in ich.items() if k.startswith(("name_", "desc_")) or k in ("hp", "deck", "relics")})
            fake.update({"enabled": True, "color": "#8a8a8a",
                         "select_image": ich.get("select_image") or ich.get("orig_select_image") or ""})
            fake["deck"] = [d for d in ich.get("deck", []) if not d["card"].startswith("raw:")]
            fake["relics"] = [r for r in ich.get("relics", []) if not r.startswith("raw:")]
            P = dict(P, character=fake)
        dpr = self.preview.devicePixelRatioF()           # 화면 배율대로 크게 만들어 글자와 테두리가 흐리지 않게

        def draw(width, height, render):
            image = QImage(round(width * dpr), round(height * dpr), QImage.Format.Format_ARGB32)
            image.setDevicePixelRatio(dpr)
            image.fill(QColor("#121318"))
            painter = QPainter(image)
            try:
                render(painter)
            except Exception as e:  # noqa: BLE001
                painter.setPen(QColor("#ff6666"))
                painter.drawText(0, 0, width, height, int(Qt.AlignmentFlag.AlignCenter), f"미리보기 오류:\n{e}")
            painter.end()
            return QPixmap.fromImage(image)

        lang = self.preview_lang
        self.preview.setPixmap(draw(int(PQ.SELECT_W * u), int(PQ.SELECT_H * u),
                                    lambda pt: PQ.render_select_screen(pt, P, 0, 0, lang, u)))
        self.preview_icons.setPixmap(draw(int(PQ.SELECT_W * u), int(104 * u),
                                          lambda pt: PQ.render_character_icons(pt, P, 0, 0, lang, u)))

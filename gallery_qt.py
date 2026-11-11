"""'도감' 탭의 Qt 版. 필터·크기·언어·칸 배치·클릭해서 편집 화면으로 가기는 Tk 와 같다.

칸 그림은 '게임 화면'(gameviewqt, 백그라운드에서 만든다)이나 간단한 그림(preview_qt.render_item)으로 그린다.
"""
from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QHBoxLayout, QRadioButton, QScrollArea,
                               QVBoxLayout, QWidget)

import copy
import json

import preview_qt as PQ
import qtkit as Q
from gameviewqt import GameModeBar

SIZES = [("small", "작게", 0.5), ("medium", "보통", 0.65), ("large", "크게", 0.85)]
FILTERS = [("all", "전체"), ("card", "카드"), ("relic", "유물"), ("potion", "물약"), ("power", "파워")]
# (종류, 프로젝트 키, 제목, 기본 높이)
SECTIONS = [("card", "cards", "카드", 420), ("relic", "relics", "유물", 400),
            ("potion", "potions", "물약", 400), ("power", "powers", "파워", 400)]
GAP, PAD = 14, 16


class _Grid(QWidget):
    """칸을 그리고 클릭을 받는 면. 칸 배치는 GalleryQt 가 계산해 넣어 준다."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.tiles = []        # (QRect, kind, index, item)
        self.titles = []       # (x, y, 글)
        self.setStyleSheet(f"background: {Q.C['stage']};")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#121318"))
        painter.setPen(QColor("#e8e2d0"))
        painter.setFont(QFont(Q.FONT, 13, QFont.Weight.Bold))
        for x, y, text in self.titles:
            painter.drawText(x, y, text)
        for rect, kind, _index, item in self.tiles:
            self.owner.draw_tile(painter, rect, kind, item)
        painter.end()

    def mouseReleaseEvent(self, event):
        point = event.position().toPoint()
        for rect, kind, index, _item in self.tiles:
            if rect.contains(point):
                self.owner.open_requested.emit(kind, index)
                return


class GalleryQt(QWidget):
    open_requested = Signal(str, int)   # (종류, 번호): 편집 화면으로 가라는 요청

    def __init__(self, project, scale_ui=1.0, parent=None, views=None):
        super().__init__(parent)
        self.project = project
        self.scale_ui = scale_ui
        self.views = views          # 게임 화면 설정 (gameviewqt.GameViews). 없으면 간단한 그림만
        self._pix = {}              # 게임 화면 그림을 칸 크기에 맞춘 것 (QPixmap)
        self._filter = "all"
        self._size = "medium"
        self.lang = "ko"
        self.upgraded = False

        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self._filter_group = QButtonGroup(self)
        for val, label in FILTERS:
            button = QRadioButton(label)
            button.setChecked(val == "all")
            button.toggled.connect(lambda on, v=val: on and self.set_filter(v))
            self._filter_group.addButton(button)
            bar.addWidget(button)
        bar.addSpacing(12)
        self.size_box = QComboBox()
        for val, label, _ in SIZES:
            self.size_box.addItem(label, val)
        self.size_box.setCurrentIndex(1)
        self.size_box.currentIndexChanged.connect(lambda _i: self.set_size(self.size_box.currentData()))
        bar.addWidget(self.size_box)
        bar.addSpacing(12)
        self.lang_box = QComboBox()
        for val, label in (("ko", "한국어"), ("en", "English"), ("zh", "简体中文")):
            self.lang_box.addItem(label, val)
        self.lang_box.currentIndexChanged.connect(lambda _i: self.set_lang(self.lang_box.currentData()))
        bar.addWidget(self.lang_box)
        upgraded = QCheckBox("카드 강화(+)")
        upgraded.toggled.connect(self.set_upgraded)
        bar.addWidget(upgraded)
        if views is not None:
            bar.addSpacing(12)
            bar.addWidget(GameModeBar(views))
        bar.addStretch(1)
        root.addLayout(bar)

        self.grid = _Grid(self)
        if views is not None:
            views.changed.connect(self.grid.update)
            views.ready.connect(self.grid.update)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(False)
        self.scroll.setWidget(self.grid)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        root.addWidget(self.scroll, 1)
        # 칸이 늘어나 세로 스크롤바가 생기면 너비가 줄어든다: 그때도 다시 배치한다
        self.scroll.verticalScrollBar().rangeChanged.connect(lambda *_: self.refresh())
        self.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self.refresh)   # 레이아웃이 끝난 뒤 너비를 읽는다 (칸 수가 너비에 따라 달라진다)

    # ---- 설정 ----
    def set_project(self, project):
        self.project = project
        self.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()          # 도감은 보일 때 다시 채운다 (Tk 와 같다)

    def set_filter(self, value):
        self._filter = value
        self.refresh()

    def set_size(self, value):
        self._size = value
        self.refresh()

    def set_lang(self, value):
        self.lang = value
        self.grid.update()

    def set_upgraded(self, value):
        self.upgraded = bool(value)
        self.grid.update()

    def _scale(self):
        base = {v: s for v, _l, s in SIZES}.get(self._size, 0.65)
        return base * self.scale_ui

    def draw_tile(self, painter, rect, kind, item):
        """칸 하나: 미리보기 그림 + 아래에 번호. 그리기에 실패하면 오류 글만 쓴다 (나머지 칸은 계속 그린다)."""
        try:
            pixmap = self._game_pixmap(kind, item, rect) if self._game_on() else None
            if pixmap is not None:
                logical_w = pixmap.width() / pixmap.devicePixelRatio()    # 화면 배율(125%·150%)에 맞춘 그림의 실제 칸 너비
                painter.drawPixmap(rect.x() + int((rect.width() - logical_w) // 2), rect.y(), pixmap)
            else:
                PQ.render_item(painter, self.project, kind, item, rect.x(), rect.y(), self._scale(),
                               self.lang, self.upgraded, stacks=self._stacks())
        except Exception as e:  # noqa: BLE001
            painter.setPen(QColor("#ff6666"))
            painter.setFont(QFont(Q.FONT, 9))
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter) | int(Qt.TextFlag.TextWordWrap), f"오류: {e}")
        painter.setPen(QColor("#777777"))
        painter.setFont(QFont("Consolas", 8))
        painter.drawText(QRect(rect.left(), rect.bottom() + 2, rect.width(), 16),
                         int(Qt.AlignmentFlag.AlignHCenter), str(item.get("id", "")))

    def _stacks(self):
        return self.views.stacks if self.views is not None else 3

    def _game_on(self):
        return self.views is not None and self.views.available()

    def _game_pixmap(self, kind, item, rect):
        """게임 화면 그림을 칸 크기에 맞춰 돌려 준다. 아직 만드는 중이면 None (간단한 그림을 그린다)."""
        P = self.project
        shared = json.dumps([P.get("character", {}), P.get("powers", []), P.get("card_frames", [])],
                            sort_keys=True, ensure_ascii=False, default=str)
        key = (json.dumps(item, sort_keys=True, ensure_ascii=False, default=str), shared)
        dpr = self.grid.devicePixelRatioF()        # 화면 배율만큼 크게 만들어야 흐려지지 않는다
        size = (round(rect.width() * dpr), round(rect.height() * dpr))
        pkey = (key, kind, self.lang, self.upgraded, self._stacks(), dpr) + size
        pixmap = self._pix.get(pkey)
        if pixmap is not None:
            return pixmap
        snap = copy.deepcopy(item)          # 백그라운드 스레드가 읽는 복사본
        img = self.views.thumb(key, lambda: snap, kind, self.lang, self.upgraded, self._stacks(), *size)
        if img is None:
            return None
        if len(self._pix) > 1500:
            self._pix.clear()
        pixmap = self.views.pixmap(img)
        pixmap.setDevicePixelRatio(dpr)
        self._pix[pkey] = pixmap
        return pixmap

    # ---- 배치 ----
    def compute(self, width):
        """칸 위치, 제목 위치, 전체 높이를 계산한다 (그리지는 않는다)."""
        s = self._scale()
        width = max(300, width)
        tw = 300 * s
        tiles, titles = [], []
        y = 10
        for kind, key, title, base_h in SECTIONS:
            if self._filter not in ("all", kind):
                continue
            items = self.project.get(key, [])
            titles.append((PAD, y + 22, f"{title}  ({len(items)})"))
            y += 34
            th = base_h * s
            cols = max(1, int((width - PAD * 2 + GAP) // (tw + GAP)))
            for i, item in enumerate(items):
                col, row = i % cols, i // cols
                rect = QRect(int(PAD + col * (tw + GAP)), int(y + row * (th + GAP + 18)), int(tw), int(th))
                tiles.append((rect, kind, i, item))
            rows = (len(items) + cols - 1) // cols
            y += rows * (th + GAP + 18) + 20
            if not items:
                titles.append((PAD, y, "(없음)"))
                y += 20
        return tiles, titles, int(y + 20), width

    def refresh(self):
        tiles, titles, height, width = self.compute(self.scroll.viewport().width())
        self.grid.tiles, self.grid.titles = tiles, titles
        self.grid.setFixedSize(width, height)
        self.grid.update()

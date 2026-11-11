"""'도감' 탭의 Qt 뼈대. 필터·크기·칸 배치·클릭해서 편집 화면으로 가기는 Tk 와 같다.

아직 옮기지 않은 것: 칸 안의 그림. Tk 에서는 preview.py(캔버스 그리기 644줄)가 그린다.
그 그리기 부분을 QPainter 로 옮기기 전까지는 이름과 번호만 적은 칸을 그린다 (draw_tile 을 바꾸면 된다).
"""
from PySide6.QtCore import QRect, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QRadioButton, QScrollArea, QVBoxLayout,
                               QWidget)

import qtkit as Q

SIZES = [("small", "작게", 0.5), ("medium", "보통", 0.65), ("large", "크게", 0.85)]
FILTERS = [("all", "전체"), ("card", "카드"), ("relic", "유물"), ("potion", "물약"), ("power", "파워")]
# (종류, 프로젝트 키, 제목, 기본 높이)
SECTIONS = [("card", "cards", "카드", 420), ("relic", "relics", "유물", 400),
            ("potion", "potions", "물약", 400), ("power", "powers", "파워", 400)]
GAP, PAD = 14, 16


def draw_tile(painter, rect, item):
    """칸 하나 그리기 (자리 표시: 어두운 바탕, 이름, 번호)."""
    painter.setPen(QPen(QColor("#3a3f4b")))
    painter.setBrush(QColor("#1d2027"))
    painter.drawRoundedRect(rect, 10, 10)
    painter.setPen(QColor("#e8e2d0"))
    painter.setFont(QFont(Q.FONT, 10, QFont.Weight.Bold))
    painter.drawText(rect.adjusted(8, 8, -8, -8), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter),
                     str(item.get("name_ko") or item.get("id", "")))
    painter.setPen(QColor("#777777"))
    painter.setFont(QFont("Consolas", 8))
    painter.drawText(QRect(rect.left(), rect.bottom() + 2, rect.width(), 16),
                     int(Qt.AlignmentFlag.AlignHCenter), str(item.get("id", "")))


class _Grid(QWidget):
    """칸을 그리고 클릭을 받는 면. 칸 배치는 GalleryQt 가 계산해 넣어 준다."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.tiles = []        # (QRect, kind, index, item)
        self.titles = []       # (x, y, 글)
        self.setStyleSheet("background: #121318;")

    def paintEvent(self, _event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#121318"))
        painter.setPen(QColor("#e8e2d0"))
        painter.setFont(QFont(Q.FONT, 13, QFont.Weight.Bold))
        for x, y, text in self.titles:
            painter.drawText(x, y, text)
        for rect, _kind, _index, item in self.tiles:
            draw_tile(painter, rect, item)
        painter.end()

    def mouseReleaseEvent(self, event):
        point = event.position().toPoint()
        for rect, kind, index, _item in self.tiles:
            if rect.contains(point):
                self.owner.open_requested.emit(kind, index)
                return


class GalleryQt(QWidget):
    open_requested = Signal(str, int)   # (종류, 번호): 편집 화면으로 가라는 요청

    def __init__(self, project, scale_ui=1.0, parent=None):
        super().__init__(parent)
        self.project = project
        self.scale_ui = scale_ui
        self._filter = "all"
        self._size = "medium"

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
        bar.addStretch(1)
        root.addLayout(bar)

        self.grid = _Grid(self)
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
    def set_filter(self, value):
        self._filter = value
        self.refresh()

    def set_size(self, value):
        self._size = value
        self.refresh()

    def _scale(self):
        base = {v: s for v, _l, s in SIZES}.get(self._size, 0.65)
        return base * self.scale_ui

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

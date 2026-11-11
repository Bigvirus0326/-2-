"""PySide6 (Qt) 쪽 공용 부품. uxkit.py(Tk)와 같은 색·글꼴을 쓴다.

DockWorkspace: 탭 끌어서 분리·결합, 숨기기, 배치 저장을 QDockWidget 으로 한다. 실제 앱에는 아직 붙이지 않았다.
"""
import base64
import html

from PySide6.QtCore import QPoint, QRect, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPixmap
from PySide6.QtWidgets import (QDialog, QDockWidget, QFrame, QMainWindow, QPlainTextEdit, QRubberBand, QScrollArea,
                               QTabWidget, QVBoxLayout, QWidget)

# 색. 바탕·면·글자는 따뜻한 무채색 (카드 게임의 종이·잉크 느낌), 강조는 불씨색 한 가지만 쓴다.
# 긴 작업 화면에서 눈이 편하도록 채도는 아주 낮게 둔다.
C = {
    "bg": "#f6f5f2", "surface": "#fffffe", "line": "#e6e3dc", "line2": "#cdc8be",
    "text": "#1f1d1a", "muted": "#6b655b", "secondary": "#4f4a42",
    "accent": "#b4502a", "accent_hi": "#94401f", "accent_soft": "#f6e7de",
    "hover": "#efece6", "warn": "#8f5410", "danger": "#a8303f",
    "success": "#2b7456", "workspace": "#fbfaf7", "panel": "#ebe8e1",
    "console": "#2a2622", "console_fg": "#e9e4da",
    "stage": "#1f1c18",    # 그림·미리보기가 놓이는 어두운 무대 (게임 카드가 돋보이게)
}

FONT = "Malgun Gothic"


def apply_theme(app, size=10):
    """앱 전체의 글꼴과 평면 스타일 (Qt 스타일시트)."""
    app.setStyle("Fusion")
    app.setFont(QFont(FONT, size))
    app.setStyleSheet(f"""
        QWidget {{ color: {C['text']}; }}
        QMenuBar {{ background: {C['bg']}; color: {C['secondary']}; }}
        QMenuBar::item:selected {{ background: {C['hover']}; color: {C['text']}; }}
        QMenu {{ background: {C['surface']}; border: 1px solid {C['line']}; padding: 4px; }}
        QMenu::item {{ padding: 5px 24px 5px 12px; border-radius: 4px; }}
        QMenu::item:selected {{ background: {C['accent_soft']}; color: {C['text']}; }}
        QToolBar {{ background: {C['surface']}; border: none; border-bottom: 1px solid {C['line']};
                    spacing: 2px; padding: 4px 8px; }}
        QToolBar QToolButton {{ color: {C['secondary']}; padding: 4px 8px; border-radius: 6px; border: 1px solid transparent; }}
        QToolBar QToolButton:hover {{ background: {C['hover']}; color: {C['text']}; }}
        QToolBar QToolButton:pressed {{ background: {C['accent_soft']}; }}
        QTabBar::tab {{ background: transparent; color: {C['muted']}; padding: 8px 14px 7px 14px;
                        border: none; border-bottom: 2px solid transparent; }}
        QTabBar::tab:selected {{ color: {C['text']}; border-bottom: 2px solid {C['accent']}; }}
        QTabBar::tab:hover:!selected {{ color: {C['text']}; }}
        QTabBar::tab:disabled {{ color: {C['line2']}; }}
        QTabWidget::pane {{ border: none; }}
        QDockWidget {{ color: {C['secondary']}; }}
        QDockWidget::title {{ background: {C['panel']}; padding: 6px 10px; text-align: left; color: {C['secondary']}; }}
        QGroupBox {{ background: {C['surface']}; border: 1px solid {C['line']}; border-radius: 10px;
                     margin-top: 30px; padding: 10px 12px 10px 12px; }}
        QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; left: 12px; top: 4px;
                            color: {C['text']}; padding: 0 4px; background: transparent; }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
            background: {C['surface']}; border: 1px solid {C['line2']}; border-radius: 6px; padding: 4px 8px;
            selection-background-color: {C['accent_soft']}; selection-color: {C['text']}; }}
        QLineEdit:hover, QComboBox:hover, QSpinBox:hover {{ border: 1px solid {C['muted']}; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QPlainTextEdit:focus {{ border: 1px solid {C['accent']}; }}
        QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{ color: {C['muted']}; background: {C['bg']}; }}
        QPushButton {{ background: {C['surface']}; color: {C['text']}; border: 1px solid {C['line2']};
                       border-radius: 8px; padding: 5px 14px; }}
        QPushButton:hover {{ background: {C['hover']}; border: 1px solid {C['muted']}; }}
        QPushButton:pressed {{ background: {C['accent_soft']}; }}
        QPushButton:focus {{ border: 2px solid {C['accent']}; }}
        QPushButton:disabled {{ color: {C['muted']}; background: {C['bg']}; border: 1px solid {C['line']}; }}
        QPushButton[primary="true"] {{ background: {C['accent']}; color: #ffffff; border: 1px solid {C['accent']}; font-weight: 600; }}
        QPushButton[primary="true"]:hover {{ background: {C['accent_hi']}; border: 1px solid {C['accent_hi']}; }}
        QCheckBox, QRadioButton {{ color: {C['secondary']}; spacing: 6px; }}
        QCheckBox:focus, QRadioButton:focus {{ color: {C['text']}; }}
        QListWidget, QTreeWidget, QTableWidget {{ background: {C['surface']}; border: 1px solid {C['line']};
                                                   border-radius: 8px; outline: none; }}
        QListWidget::item {{ padding: 6px 8px; border-radius: 4px; }}
        QListWidget::item:hover {{ background: {C['hover']}; }}
        QListWidget::item:selected {{ background: {C['accent_soft']}; color: {C['text']}; }}
        QHeaderView::section {{ background: {C['bg']}; color: {C['muted']}; border: none;
                                border-bottom: 1px solid {C['line']}; padding: 4px 8px; }}
        QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
        QScrollBar::handle:vertical {{ background: {C['line2']}; border-radius: 5px; min-height: 24px; }}
        QScrollBar::handle:vertical:hover {{ background: {C['muted']}; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
        QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 0; }}
        QScrollBar::handle:horizontal {{ background: {C['line2']}; border-radius: 5px; min-width: 24px; }}
        QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; }}
        QStatusBar {{ background: {C['bg']}; color: {C['muted']}; border-top: 1px solid {C['line']}; }}
        QToolTip {{ background: {C['console']}; color: {C['console_fg']}; border: none; padding: 5px 7px; }}
    """)


def tip(widget, text):
    """말풍선 설명 (Tk 의 uxkit.tip 과 같다). 글자 서식으로 넣어 긴 문장은 Qt 가 줄을 바꾼다."""
    if text:
        widget.setToolTip("<qt>" + html.escape(text).replace("\n", "<br>") + "</qt>")
    return widget


def set_combo_value(combo, value):
    """콤보 상자를 값에 맞춘다. 목록에 없는 값은 지우지 않도록 '(목록에 없음)' 항목으로 남긴다.

    그렇지 않으면 다른 칸을 고칠 때 첫 항목 값으로 바뀌어 버린다 (Tk 앱은 값을 그대로 둔다).
    """
    index = combo.findData(value)
    if index < 0:
        combo.addItem(f"{value} (목록에 없음)", value)
        index = combo.count() - 1
    combo.setCurrentIndex(index)


class ScrollPage(QScrollArea):
    """내용이 창보다 크면 가로·세로 스크롤바가 나온다 (uxkit.AutoScroll 과 같은 역할).

    내용 위젯은 set_content() 로 넣는다. 스크롤만 해도 내용을 다시 만들지 않는다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._content = None

    def set_content(self, widget: QWidget):
        self.setWidget(widget)
        self._content = widget
        return widget

    def content(self):
        return self._content


class TabHost(QTabWidget):
    """작업 탭 묶음. 탭을 숨기고 다시 보이게 할 수 있다 (uxkit.ScrollNotebook 의 기본 기능)."""

    def add_page(self, page: QWidget, title: str) -> QWidget:
        self.addTab(page, title)
        return page

    def page_index(self, page: QWidget) -> int:
        return self.indexOf(page)

    def select(self, page: QWidget):
        i = self.indexOf(page)
        if i >= 0:
            self.setCurrentIndex(i)

    def set_visible(self, page: QWidget, show: bool):
        i = self.indexOf(page)
        if i >= 0:
            self.setTabVisible(i, show)


class DockWorkspace(QMainWindow):
    """작업 탭을 도킹 창으로 묶는다: 탭을 끌어 옮기거나, 밖으로 떼어 내거나, 숨길 수 있다.

    각 페이지는 QDockWidget 이 되고, 처음에는 한 탭 묶음으로 쌓인다. 배치는 save_layout()/restore_layout() 으로 보관한다.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowTabbedDocks |
                            QMainWindow.DockOption.AllowNestedDocks)
        self.setTabPosition(Qt.DockWidgetArea.AllDockWidgetAreas, QTabWidget.TabPosition.North)
        self._docks = {}   # 페이지 위젯 -> QDockWidget
        self._first = None

    def add_page(self, page: QWidget, title: str) -> QWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(title)
        dock.setWidget(page)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, dock)
        if self._first is None:
            self._first = dock
        else:
            self.tabifyDockWidget(self._first, dock)
        self._docks[page] = dock
        return page

    def dock_of(self, page: QWidget) -> QDockWidget:
        return self._docks[page]

    def select(self, page: QWidget):
        self._docks[page].raise_()

    def set_visible(self, page: QWidget, show: bool):
        self._docks[page].setVisible(show)

    def view_menu_actions(self):
        """보기 메뉴에 넣을 항목 (체크하면 보이고 끄면 숨긴다)."""
        return [dock.toggleViewAction() for dock in self._docks.values()]

    def save_layout(self) -> bytes:
        return bytes(self.saveState())

    def restore_layout(self, state: bytes) -> bool:
        return self.restoreState(state)

    def floating_docks(self):
        return [dock for dock in self._docks.values() if dock.isFloating()]

    def dock_all(self):
        """떨어진 탭을 모두 제자리로 되돌려 한 탭 묶음에 넣는다 (숨긴 탭은 그대로 둔다)."""
        if self._first is None:
            return
        for dock in self._docks.values():
            if dock.isFloating():
                dock.setFloating(False)
        for dock in self._docks.values():
            if dock is not self._first and dock not in self.tabifiedDockWidgets(self._first):
                self.tabifyDockWidget(self._first, dock)

    def reset_layout(self):
        """배치 초기화: 모든 탭을 보이게 하고 한 탭 묶음으로 모은다."""
        for dock in self._docks.values():
            dock.setVisible(True)
        self.dock_all()

    def layout_text(self) -> str:
        """설정 파일에 넣을 수 있는 글자(base64)로 된 배치."""
        return base64.b64encode(self.save_layout()).decode("ascii")

    def restore_layout_text(self, text: str) -> bool:
        try:
            state = base64.b64decode(text.encode("ascii"), validate=True)
        except (ValueError, AttributeError):
            return False
        return bool(state) and self.restore_layout(state)


def code_window(parent, title, code):
    """원본 코드를 읽기 전용 창에 보여 준다 (Tk 의 show_code_window 와 같다). 창을 돌려 준다."""
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(900, 700)
    layout = QVBoxLayout(dialog)
    text = QPlainTextEdit()
    text.setReadOnly(True)
    text.setStyleSheet("font-family: Consolas;")
    text.setPlainText(code)
    layout.addWidget(text)
    dialog.show()
    return dialog


# ---------------------------------------------------------------------------
# 끌기 피드백: 빈 곳을 끌어 고르기 · 끄는 그림 · 놓을 자리 줄 (블록 편집·카드 목록이 같이 쓴다)
# ---------------------------------------------------------------------------
BAND_STYLE = "QRubberBand { background: rgba(180, 80, 42, 45); border: 1px solid #b4502a; }"


def drag_picture(view, rects):
    """끌 때 커서를 따라갈 그림: 끄는 줄들의 자리를 모아 반투명하게 그린다. (그림, 커서가 잡은 자리)."""
    rects = [r for r in rects if r.isValid() and r.height() > 0]
    if not rects:
        return None, QPoint(0, 0)
    union = rects[0]
    for rect in rects[1:]:
        union = union.united(rect)
    shot = view.viewport().grab(union)
    picture = QPixmap(shot.size())
    picture.fill(Qt.GlobalColor.transparent)
    painter = QPainter(picture)
    painter.setOpacity(0.85)
    painter.drawPixmap(0, 0, shot)
    painter.end()
    grab_at = view.viewport().mapFromGlobal(QCursor.pos()) - union.topLeft()
    grab_at.setX(min(max(grab_at.x(), 0), picture.width() - 1))
    grab_at.setY(min(max(grab_at.y(), 0), picture.height() - 1))
    return picture, grab_at


class BandSelectMixin:
    """빈 곳을 끌면 사각형이 나타나고, 사각형에 닿는 줄이 고른다. Ctrl·Shift 를 누르면 고른 것을 그대로 둔다.
    쓰는 쪽은 _band_items() (고를 수 있는 줄들)를 준다. QListWidget · QTreeWidget 에 앞쪽 부모로 섞어 쓴다."""

    def _band_items(self):
        return []

    def _band_hit(self, item, rect):
        return self.visualItemRect(item).intersects(rect)

    def mousePressEvent(self, event):
        point = event.position().toPoint()
        if event.button() == Qt.MouseButton.LeftButton and self.itemAt(point) is None:
            self._band_keep = bool(event.modifiers() & (Qt.KeyboardModifier.ControlModifier
                                                        | Qt.KeyboardModifier.ShiftModifier))
            self._band_origin = point
            self._band = QRubberBand(QRubberBand.Shape.Rectangle, self.viewport())
            self._band.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self._band.setStyleSheet(BAND_STYLE)
            self._band.setGeometry(QRect(point, QSize()))
            self._band.show()
            if not self._band_keep:
                self.clearSelection()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if getattr(self, "_band", None) is not None:
            rect = QRect(self._band_origin, event.position().toPoint()).normalized()
            self._band.setGeometry(rect)
            for item in self._band_items():
                if self._band_hit(item, rect):
                    item.setSelected(True)
                elif not self._band_keep:
                    item.setSelected(False)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if getattr(self, "_band", None) is not None:
            self._band.hide()
            self._band.deleteLater()
            self._band = None
            return
        super().mouseReleaseEvent(event)


class DropLine(QWidget):
    """놓을 자리를 알려 주는 얇은 강조 줄 (목록 그림 위에 얹힌다, 마우스는 통과)."""

    def __init__(self, parent):
        super().__init__(parent)
        self._line = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def show_at(self, rect):
        self._line = rect
        self.setGeometry(self.parentWidget().rect())
        self.update()

    def clear(self):
        self._line = None
        self.update()

    def paintEvent(self, event):
        if self._line is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#b4502a"))
        painter.drawRoundedRect(QRectF(self._line), 2, 2)
        painter.end()

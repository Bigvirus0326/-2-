"""PySide6 (Qt) 쪽 공용 부품. uxkit.py(Tk)와 같은 색·글꼴을 쓴다.

DockWorkspace: 탭 끌어서 분리·결합, 숨기기, 배치 저장을 QDockWidget 으로 한다. 실제 앱에는 아직 붙이지 않았다.
"""
import base64

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QScrollArea, QTabWidget, QWidget, QFrame, QMainWindow, QDockWidget

# uxkit.C 와 같은 값 (색 이름도 같게 둔다)
C = {
    "bg": "#eef2f8", "surface": "#ffffff", "line": "#dfe5ef", "line2": "#ccd5e4",
    "text": "#24324b", "muted": "#66758c", "accent": "#365ee8", "accent_hi": "#2949bd",
    "accent_soft": "#e9eeff", "hover": "#f2f5ff", "warn": "#a46615", "danger": "#b8364b",
    "success": "#237b62", "workspace": "#f7f9fd", "panel": "#e8edf6",
    "console": "#262a31", "console_fg": "#d9dde4",
}

FONT = "Malgun Gothic"


def apply_theme(app, size=10):
    """앱 전체의 글꼴과 평면 스타일 (Qt 스타일시트)."""
    app.setStyle("Fusion")
    app.setFont(QFont(FONT, size))
    app.setStyleSheet(f"""
        QWidget {{ color: {C['text']}; }}
        QTabBar::tab {{ background: {C['bg']}; color: {C['muted']}; padding: 6px 12px;
                        border: 1px solid {C['line']}; border-bottom: none; }}
        QTabBar::tab:selected {{ background: {C['surface']}; color: {C['text']}; }}
        QTabBar::tab:hover {{ background: {C['hover']}; }}
        QTabBar::tab:disabled {{ color: {C['line2']}; }}
        QLineEdit, QComboBox, QSpinBox, QPlainTextEdit, QTextEdit {{
            background: {C['surface']}; border: 1px solid {C['line2']}; padding: 2px 4px; }}
        QLineEdit:focus, QComboBox:focus, QSpinBox:focus {{ border: 1px solid {C['accent']}; }}
        QPushButton {{ background: {C['surface']}; border: 1px solid {C['line2']}; padding: 4px 10px; }}
        QPushButton:hover {{ background: {C['hover']}; }}
        QPushButton:pressed {{ background: {C['accent_soft']}; }}
        QPushButton:disabled {{ color: {C['line2']}; }}
        QToolTip {{ background: {C['console']}; color: {C['console_fg']}; border: none; padding: 4px; }}
    """)


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

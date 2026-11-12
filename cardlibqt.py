"""라이브러리 (Qt 版): 원작 · 참고 프로젝트 · 원작 키워드에서 카드·유물·물약·파워·키워드를 골라 가져오거나 적용한다.

Tk 의 card_library.py 와 같은 규칙. 목록의 카드는 캐릭터 탭 '시작 덱', 유물은 '시작 유물'로 끌어 놓을 수 있다 (버튼과 같은 가져오기).
원작 코드 읽기(디컴파일)는 백그라운드에서 하고 끝나면 화면 스레드에서 보여 준다.
"""
import copy
import json
import os
import re
import threading
from pathlib import Path
from types import SimpleNamespace

from PySide6.QtCore import QMimeData, QPoint, QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QCursor, QDrag, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout, QLabel, QListWidget, QMessageBox, QTabBar,
                               QMenuBar, QPlainTextEdit, QPushButton, QSplitter, QStyledItemDelegate, QVBoxLayout, QWidget,
                               QCheckBox, QLineEdit)

import modgen as M
import modimport as MI
import preview_qt as PQ
import projectio as IO
import card_library_rules as CLR
import qtkit as Q
import gimmick as G
import previewcore as PV
from itemtabqt import PREVIEW_H, PREVIEW_W, _CardRowDelegate, _RelicRowDelegate, all_ids, item_preview

def keyword_tags(project):
    """키워드 목록에 나오는 것: 프로젝트의 태그 전부 (카드 종류로 쓰는 태그는 뺀다)."""
    return [t for t in G.tags(project) if not t.get("card_kind")]


IMAGE_BOX = (235, 165)
CARD_MIME = "application/x-modmaker-card"     # 라이브러리 항목 끌어 놓기 (카드 → 시작 덱, 유물 → 시작 유물; 값은 쓰지 않는다)
KINDS = (("cards", "카드"), ("relics", "유물"), ("potions", "물약"), ("powers", "파워"), ("card_keywords", "키워드"))
PROJECT_KEY = {"cards": "cards", "relics": "relics", "potions": "potions", "powers": "powers"}   # 키워드는 프로젝트에 따로 없다
PAGE_OF = {"cards": 0, "relics": 1, "potions": 2, "powers": 3, "card_keywords": 0}            # 키워드는 카드 탭에 적용한다
DESC_KIND = {"cards": "card", "relics": "relic", "potions": "potion", "powers": "power", "card_keywords": "card"}


PREVIEW_KINDS = ("cards", "relics", "potions", "powers")   # 카드 탭 미리보기를 그릴 수 있는 종류


class _LibraryCardRows(_CardRowDelegate):
    """카드 목록 줄 (카드 종류일 때만). 원작 카드는 비용·종류 정보가 없어 이름만 보인다."""

    def _card_at(self, index):
        lib = self.tab
        if lib.kind != "cards" or not (0 <= index.row() < len(lib.rows)):
            return None
        card = lib.rows[index.row()]
        if lib.source().get("game"):
            return {"name_ko": M.text(card, "name", "ko") or card["id"], "no_cost": True, "type": "", "rarity": ""}
        return card


class _LibraryRelicRows(_RelicRowDelegate):
    """유물 목록 줄 (유물 종류일 때만). 원작 유물은 희귀도 정보가 없어 이름만 보인다."""

    def _item_at(self, index):
        lib = self.tab
        if lib.kind != "relics" or not (0 <= index.row() < len(lib.rows)):
            return None
        relic = lib.rows[index.row()]
        if lib.source().get("game"):
            return {"name_ko": M.text(relic, "name", "ko") or relic["id"], "rarity": ""}
        return relic


class _LibraryRowDelegate(QStyledItemDelegate):
    """라이브러리 목록 한 줄: 카드·유물은 목록과 같은 모양, 물약·파워·키워드는 기본 글 그대로."""

    def __init__(self, lib):
        super().__init__(lib)
        self.cards = _LibraryCardRows(lib)
        self.relics = _LibraryRelicRows(lib)

    def _picked(self):
        return {"cards": self.cards, "relics": self.relics}.get(self.parent().kind)

    def sizeHint(self, option, index):
        picked = self._picked()
        return picked.sizeHint(option, index) if picked else super().sizeHint(option, index)

    def paint(self, painter, option, index):
        picked = self._picked()
        if picked is None:
            return super().paint(painter, option, index)
        return picked.paint(painter, option, index)


ACTIVE_DRAG = {"lib": None}          # 지금 끌고 있는 목록의 라이브러리 창 (여러 창일 때 끌어 놓기가 어느 창 것인지 안다)


def _menu_action(menu, text, slot):
    """메뉴 항목 하나: 고르면 slot 을 부른다 (체크 상태는 쓰지 않는다)."""
    action = menu.addAction(text)
    action.triggered.connect(lambda _checked=False: slot())
    return action


class _HoverPreview(QFrame):
    """마우스를 올린 항목의 미리보기: 카드 탭 미리보기와 같은 그림 (클릭하지 않는다)."""

    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.ToolTip | Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet(f"QFrame {{ background: {Q.C['stage']}; border: 1px solid {Q.C['line2']}; }}")
        col = QVBoxLayout(self)
        col.setContentsMargins(4, 4, 4, 4)
        self.art = QLabel()
        self.art.setFixedSize(PREVIEW_W, PREVIEW_H)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        col.addWidget(self.art)

    def show_item(self, pixmap, pos):
        if pixmap is None:
            self.art.clear()
        else:
            self.art.setPixmap(pixmap)
        self.adjustSize()
        self.move(pos)
        self.show()


class _CardDragList(QListWidget):
    """라이브러리 목록: 항목을 끌면 CARD_MIME 을 싣는다. 실제로 끌어 놓은 항목은 라이브러리의 선택이 정한다."""
    owner = None

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        item = self.itemAt(event.position().toPoint())
        self.owner.hover_row(self.row(item) if item is not None else None)

    def leaveEvent(self, event):
        self.owner.hover_row(None)
        super().leaveEvent(event)

    def startDrag(self, _actions):
        if self.currentItem() is None:
            return
        ACTIVE_DRAG["lib"] = self.owner
        mime = QMimeData()
        mime.setData(CARD_MIME, b"1")
        drag = QDrag(self)
        drag.setMimeData(mime)
        rect = self.visualRect(self.currentIndex())
        drag.setPixmap(self.viewport().grab(rect))     # 끌고 가는 줄의 모양
        drag.setHotSpot(QPoint(16, rect.height() // 2))
        drag.exec(Qt.DropAction.CopyAction)


def _warn(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


def _info(parent, text):
    QMessageBox.information(parent, IO.APP_TITLE, text)


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


def _library_tab_at(app, pos, exclude=None):
    """전역 좌표 pos 가 보이는 라이브러리 종류 탭 줄 위인지 (exclude 창은 뺀다).
    끌고 있는 창이 탭 줄을 가려도 자리로 찾는다 (가리는 창이 무엇인지와 상관없다)."""
    for window in list(app._library_windows) + [app._card_library]:
        if window is None or window is exclude or not window.isVisible():
            continue
        bar = window.tabs
        if bar.isVisible() and QRect(bar.mapToGlobal(QPoint(0, 0)), bar.size()).contains(pos):
            return bar
    return None


class _KindTabBar(QTabBar):
    """라이브러리 종류 탭 (포토샵 문서 탭처럼). 탭을 끌면 바로 새 창으로 떨어져 나와 커서를 따라간다.
    놓을 때 다른 라이브러리의 탭 줄 위면 그 창으로 옮기고, 아니면 떨어진 채로 둔다.
    끄는 동안 놓을 수 있는 탭 줄은 강조되고, 마지막 탭 뒤에 들어갈 자리가 보인다."""

    def __init__(self, owner):
        super().__init__(owner)
        self.owner = owner
        self._press = None          # (탭 자리, 누른 자리, 탭 사각형)
        self._dragged = None        # 끌리고 있는 떨어진 창
        self._grab = QPoint()       # 그 창 안에서 커서가 잡은 자리
        self._target = None         # 지금 놓을 수 있는 탭 줄
        self._hover = False
        self._last = QPoint()       # 마지막으로 창을 옮긴 커서 자리 (같으면 다시 옮기지 않는다)
        self._timer = QTimer(self)  # 끄는 동안 커서를 따라간다 (탭 줄이 가려져도 계속 된다)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        self.setExpanding(False)
        self.setMovable(False)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            index = self.tabAt(pos)
            self._press = (index, pos, self.tabRect(index)) if index >= 0 else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press is not None:
            index, press, rect = self._press
            pos = event.position().toPoint()
            if (pos - press).manhattanLength() >= QApplication.startDragDistance() and not self.rect().contains(pos):
                self._press = None
                self._grab = QPoint(min(max(press.x() - rect.left(), 16), 160), 12)
                self._last = QCursor.pos()
                self._dragged = self.owner.detach_kind(self.tabData(index), self._last - self._grab)
                self._timer.start()
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._press = None
        super().mouseReleaseEvent(event)

    def _tick(self):
        window = self._dragged
        if window is None:
            self._timer.stop()
            return
        if not (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self._finish()
            return
        pos = QCursor.pos()
        if pos != self._last:
            self._last = pos
            window.move(pos - self._grab)
        target = _library_tab_at(self.owner.app, pos, exclude=window)
        if target is not self._target:
            if self._target is not None:
                self._target._set_hover(False)
            if target is not None:
                target._set_hover(True)
            self._target = target

    def _finish(self):
        self._timer.stop()
        window, self._dragged = self._dragged, None
        target, self._target = self._target, None
        if target is not None:
            target._set_hover(False)
        if window is None:
            return
        destination = _library_tab_at(self.owner.app, QCursor.pos(), exclude=window)
        if destination is None:                  # 어느 라이브러리 탭 줄에도 놓지 않았다: 떨어진 채로 둔다
            return
        for kind in window.kinds:
            destination.owner.add_kind(kind)
        self.owner.app.discard_library_window(window)

    def _set_hover(self, on):
        if self._hover != on:
            self._hover = on
            self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._hover:
            return
        painter = QPainter(self)
        frame = QPen(QColor(Q.C["accent"]))
        frame.setWidth(2)
        painter.setPen(frame)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.rect().adjusted(1, 1, -2, -2))
        if self.count():                                 # 놓으면 들어갈 자리: 마지막 탭 뒤의 세로 줄
            x = self.tabRect(self.count() - 1).right() + 4
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(Q.C["accent_hi"]))
            painter.drawRect(x, 4, 3, self.height() - 8)
        painter.end()


class CardLibraryQt(QWidget):
    run_on_ui = Signal(object)          # 백그라운드 작업이 끝난 뒤 화면 스레드에서 실행할 일

    @property
    def sources(self):
        return self._state.sources

    @property
    def assets(self):
        return self._state.assets

    @assets.setter
    def assets(self, value):
        self._state.assets = value

    def __init__(self, app, card_page, parent=None, kinds=None, state=None):
        super().__init__(parent)
        self.app = app
        self.card_page = card_page
        self.kind = None                    # 지금 고른 종류 탭 (카드·유물·물약·파워·키워드)
        self.dock = None                    # 메인 창에 붙은 도킹 패널 (떨어진 창은 None)
        self._state = state or SimpleNamespace(sources={}, assets=None)   # 원작·파일 목록은 라이브러리 창끼리 같이 쓴다
        self.rows = []
        self.reading = False
        self.run_on_ui.connect(lambda fn: fn())
        self.resize(640, 620)

        root = QVBoxLayout(self)
        menus = QMenuBar()
        file_menu = menus.addMenu("파일")
        _menu_action(file_menu, "원작 캐릭터 열기", self.open_game)
        _menu_action(file_menu, "프로젝트 파일 열기…", self.open_projects)
        file_menu.addSeparator()
        _menu_action(file_menu, "닫기", self.hide_window)
        item_menu = menus.addMenu("항목")
        self.add_act = _menu_action(item_menu, "선택한 항목 가져오기", lambda: self.add())
        self.apply_act = _menu_action(item_menu, "편집 중인 카드에 적용", lambda: self.apply_selected())
        self.code_act = _menu_action(item_menu, "원작 코드·수치 보기", self.show_code)
        self.remove_act = _menu_action(item_menu, "내 풀에서 제거", self.remove)
        view_menu = menus.addMenu("보기")
        _menu_action(view_menu, "선택한 항목 보기", self.show_detail)
        _menu_action(view_menu, "왼쪽에 붙이기", lambda: self.dock_to(Qt.DockWidgetArea.LeftDockWidgetArea))
        _menu_action(view_menu, "오른쪽에 붙이기", lambda: self.dock_to(Qt.DockWidgetArea.RightDockWidgetArea))
        _menu_action(view_menu, "아래에 붙이기", lambda: self.dock_to(Qt.DockWidgetArea.BottomDockWidgetArea))
        root.addWidget(menus)
        self.tabs = _KindTabBar(self)
        for kind, label in KINDS:
            if kinds is None or kind in kinds:
                self.tabs.setTabData(self.tabs.addTab(label), kind)
        root.addWidget(self.tabs)
        search_row = QHBoxLayout()                   # 검색은 한 줄을 온전히 쓴다
        search_row.addWidget(QLabel("항목 검색"))
        self.search = QLineEdit()
        self.search.textChanged.connect(lambda _t: self.refresh_cards())
        search_row.addWidget(self.search, 1)
        self.upgraded = QCheckBox("강화(+)")
        self.upgraded.toggled.connect(lambda _c: self.show_card())
        search_row.addWidget(self.upgraded)
        root.addLayout(search_row)

        middle = QWidget()
        mc = QVBoxLayout(middle)
        mc.addWidget(QLabel("열린 캐릭터 · 프로젝트"))
        self.groups = QComboBox()
        self.groups.currentIndexChanged.connect(lambda _i: self.refresh_cards())
        mc.addWidget(self.groups)
        mc.addWidget(QLabel("항목"))
        self.cards = _CardDragList()
        self.cards.owner = self
        self.cards.setDragEnabled(True)
        self.cards.setMouseTracking(True)
        self._hover_row = None
        self._preview = _HoverPreview(self)
        self.cards.setItemDelegate(_LibraryRowDelegate(self))
        self.cards.currentRowChanged.connect(lambda _r: self._card_picked())
        self.cards.itemDoubleClicked.connect(lambda _i: self.show_detail())
        mc.addWidget(self.cards, 1)
        root.addWidget(middle, 1)
        self.detail = QDialog(self)                  # 선택한 항목의 그림·설명은 따로 여는 팝업에 보인다
        self.detail.setWindowTitle("선택한 항목")
        self.detail.resize(420, 560)
        dc = QVBoxLayout(self.detail)
        self.art = QLabel()
        self.art.setFixedSize(*IMAGE_BOX)
        self.art.setAlignment(Qt.AlignmentFlag.AlignCenter)
        dc.addWidget(self.art)
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        dc.addWidget(self.info, 1)

        self.status = QLabel("원작 또는 프로젝트 파일을 열고 항목을 선택하세요.")
        root.addWidget(self.status)
        self.tabs.currentChanged.connect(lambda _i: self._kind_changed())
        self._kind_changed()

    @property
    def kinds(self):
        return [self.tabs.tabData(i) for i in range(self.tabs.count())]

    def _kind_changed(self):
        index = self.tabs.currentIndex()
        self.kind = self.tabs.tabData(index) if index >= 0 else None
        self.upgraded.setVisible(self.kind == "cards")
        self.setWindowTitle("라이브러리 · " + dict(KINDS)[self.kind] if self.kind else "라이브러리")
        self.refresh_groups("current")

    def add_kind(self, kind):
        """종류 탭을 이 창에 붙인다 (다른 창에서 옮겨 온 것). 숨은 창이면 다시 보인다."""
        if kind in self.kinds:
            return
        index = self.tabs.addTab(dict(KINDS)[kind])
        self.tabs.setTabData(index, kind)
        self.tabs.setCurrentIndex(index)
        self.show()
        self.raise_()

    def remove_kind(self, kind):
        index = next((i for i in range(self.tabs.count()) if self.tabs.tabData(i) == kind), None)
        if index is None:
            return
        self.tabs.removeTab(index)
        if self.tabs.count() == 0:
            self.hide()

    def detach_kind(self, kind, pos):
        """종류 탭을 떼어 새 창으로 연다. 새 창을 돌려 준다."""
        self.remove_kind(kind)
        return self.app.open_library_window(kind, pos)

    def set_kind(self, kind):
        """종류 탭을 고른다 (이 창에 없으면 붙인다)."""
        self.add_kind(kind)
        index = next(i for i in range(self.tabs.count()) if self.tabs.tabData(i) == kind)
        self.tabs.setCurrentIndex(index)

    # ---- 원본 · 프로젝트 열기 ----
    def open_game(self):
        import ingame
        folder = self.app.settings.get("sts2_path")
        if not folder or not (Path(folder) / "SlayTheSpire2.pck").is_file():
            folder = QFileDialog.getExistingDirectory(self, "SlayTheSpire2.pck가 있는 설치 폴더")
        if not folder:
            return
        try:
            self.assets = ingame.GameAssets(folder)
            groups = CLR.original_sources(self.assets)
            groups.update(CLR.item_sources(self.assets))
            if not groups:
                raise ValueError("원작 카드 목록을 찾을 수 없습니다.")
            for key, source in groups.items():
                self.sources["game:" + key] = source
            self.refresh_groups("game:" + ("ironclad" if "ironclad" in groups else next(iter(groups))))
        except Exception as exc:  # noqa: BLE001 - 사용자에게 그대로 보여 준다
            _warn(self, str(exc))

    def open_projects(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "참고할 캐릭터 프로젝트 선택", "",
                                                "모드 메이커 프로젝트 (*.sts2mod.json *.json)")
        for path in paths:
            try:
                raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                if not isinstance(raw, dict) or not isinstance(raw.get("cards"), list):
                    raise ValueError("카드 목록이 있는 모드 메이커 프로젝트를 선택하세요.")
                project = IO._resolve_project_image_paths(M.normalize(raw), os.path.dirname(path))
                self.sources[path] = {"title": M.text(project["character"], "name", "ko") + " · " + Path(path).name,
                                      "project": project}
                self.refresh_groups(path)
            except Exception as exc:  # noqa: BLE001
                _warn(self, f"{path}\n{exc}")

    # ---- 묶음 · 항목 ----
    def _items(self, src):
        """묶음 안에서 지금 종류의 항목들. 프로젝트 묶음은 프로젝트를 그때그때 읽는다 (바뀐 것이 바로 보인다)."""
        if "project" in src:
            if self.kind == "card_keywords":          # 프로젝트 키워드는 기믹의 태그 중 키워드로 만든 것
                return keyword_tags(src["project"])
            key = PROJECT_KEY.get(self.kind)
            return src["project"].get(key, []) if key else []
        return src.get("cards", []) if src.get("kind", "cards") == self.kind else []

    def _sources(self):
        """목록의 묶음: 맨 앞은 지금 열린 프로젝트, 뒤는 이 종류의 항목이 있는 원작·참고 파일."""
        project = self.app.project
        out = {"current": {"title": "현재 프로젝트 · " + M.text(project["character"], "name", "ko"),
                           "project": project, "current": True}}
        for key, src in self.sources.items():
            if "project" in src:
                if self._items(src):
                    out[key] = src
            elif src.get("kind", "cards") == self.kind:
                out[key] = src
        return out

    def refresh_groups(self, selected=None):
        sources = self._sources()
        keys = list(sources)
        if selected is None:                       # 다시 그릴 때는 고른 묶음을 그대로 둔다
            row = self.groups.currentIndex()
            selected = keys[row] if 0 <= row < len(keys) else "current"
        if selected not in keys:                   # 이 종류에 항목이 없는 묶음은 고를 수 없다
            selected = "current"
        self.groups.blockSignals(True)
        self.groups.clear()
        for key in keys:
            self.groups.addItem(sources[key]["title"])
        self.groups.setCurrentIndex(keys.index(selected))
        self.groups.blockSignals(False)
        self.refresh_cards()

    def source(self):
        row = self.groups.currentIndex()
        values = list(self._sources().values())
        return values[row] if 0 <= row < len(values) else {}

    def _page(self):
        """지금 종류의 편집 탭 (키워드는 카드 탭에 적용한다)."""
        return self.app.item_pages[PAGE_OF.get(self.kind, 0)]

    def _current_item(self):
        tab = self._page()
        return tab.items[tab.cur] if tab.cur is not None and tab.cur < len(tab.items) else None

    def _current_card(self):
        tab = self.card_page
        return tab.items[tab.cur] if tab.cur is not None and tab.cur < len(tab.items) else None

    def refresh_cards(self):
        self.hover_row(None)
        query = self.search.text().strip().casefold()
        self.rows = [c for c in self._items(self.source())
                     if any(query in str(c.get(k, "")).casefold() for k in ("id", "name_ko", "name_en", "name_zh"))]
        self.cards.blockSignals(True)
        self.cards.clear()
        for item in self.rows:
            self.cards.addItem(M.text(item, "name", "ko") or item["id"])
        row = 0
        if self.source().get("current") and self._page().cur is not None:
            row = next((i for i, c in enumerate(self.rows) if c is self._current_item()), 0)
        if self.rows:
            self.cards.setCurrentRow(row)
        self.cards.blockSignals(False)
        self.show_card()

    def _card_picked(self):
        """지금 프로젝트의 항목을 고르면 같은 종류의 편집 탭도 그 항목을 연다 (목록을 하나로 쓴다)."""
        item = self.selection()
        if item is not None and self.source().get("current"):
            page = self._page()
            index = next((i for i, c in enumerate(page.items) if c is item), None)
            if index is not None and index != page.cur:
                page.search.setText("")       # 탭 검색이 걸려 있으면 그 항목이 안 보이므로 지운다
                page.refresh_list(index)
        self.show_card()

    def hover_row(self, row):
        """마우스가 올라간 줄의 미리보기를 보인다 (None 이면 숨긴다)."""
        if row is None or not (0 <= row < len(self.rows)):
            self._hover_row = None
            self._preview.hide()
            return
        cursor = QCursor.pos() + QPoint(18, 18)
        if row == self._hover_row and self._preview.isVisible():
            self._preview.move(cursor)
            return
        self._hover_row = row
        self._preview.show_item(self._hover_pixmap(self.rows[row], self.source()), cursor)

    def _hover_pixmap(self, card, source):
        """카드 탭 미리보기와 같은 그림. 원작 항목은 게임 그림을 그대로 쓴다."""
        if source.get("game") or self.kind not in PREVIEW_KINDS:
            return self._pixmap_for(card, source)
        pixmap, _note = item_preview(DESC_KIND[self.kind], source["project"], card, self.card_page.preview_lang,
                                     self.upgraded.isChecked(), self.card_page.views, self.card_page._stacks())
        return pixmap

    def dock_to(self, area):
        """라이브러리를 메인 창의 왼쪽·오른쪽·아래 중 area 에 붙인다 (떨어져 있었어도 붙는다)."""
        if self.dock is None:
            return
        self.dock.setFloating(False)
        self.app.addDockWidget(area, self.dock)
        self.dock.show()

    def hide_window(self):
        """닫기: 도킹 패널이면 패널을 숨기고, 떨어진 창이면 창을 닫는다."""
        if self.dock is not None:
            self.dock.hide()
        else:
            self.close()

    def show_detail(self):
        """선택한 항목의 그림·설명을 팝업으로 보인다 (목록 옆 공간을 차지하지 않게). 고르는 것을 따라 바뀐다."""
        self.detail.show()
        self.detail.raise_()

    def selection(self):
        row = self.cards.currentRow()
        return self.rows[row] if 0 <= row < len(self.rows) else None

    def show_card(self):
        card, source, kind = self.selection(), self.source(), self.kind
        lines = []
        imported = False
        self.art.clear()
        if card:
            lines = [M.text(card, "name", "ko") + "  ·  " + card["id"]]
            for lang in ("ko", "en", "zh"):
                lines.append(f"{M.text(card, 'name', lang)}\n{self._description(card, source, lang)}")
            self._show_art(card, source)
            imported = bool(source.get("game")) and card["id"] in \
                self.app.project["character"].get("game_" + kind, {})
        self.info.setPlainText("\n\n".join(lines))
        is_current = bool(source.get("current"))         # 지금 열린 프로젝트의 항목: 가져올 것이 없다
        project_keyword = kind == "card_keywords" and not source.get("game")   # 이미 있는 키워드는 가져올 것이 없다
        self.add_act.setEnabled(bool(card) and not is_current and not project_keyword
                                and (not imported or kind == "cards"))
        if is_current:
            self.add_act.setText("이 프로젝트에 있음")
        elif kind == "cards":
            self.add_act.setText("＋ 새 카드로 가져오기")
        elif source.get("game"):
            self.add_act.setText("＋ 풀에 추가")
        else:
            self.add_act.setText("＋ 프로젝트에 추가")
        current = self._current_card()
        name = M.text(current, "name", "ko") if current else ""
        locked = bool(current) and self.card_page._locked(current)
        can_apply = (kind in ("cards", "card_keywords") and bool(card) and bool(current) and not locked
                     and not is_current and (not source.get("game") or kind == "card_keywords"))
        self.apply_act.setEnabled(can_apply)
        if kind == "card_keywords":
            self.apply_act.setText(f"‘{name}’에 키워드 적용")
        elif kind == "cards":
            self.apply_act.setText(f"‘{name}’에 덮어쓰기…" if name else "덮어쓸 카드를 선택하세요")
        else:
            self.apply_act.setText("이 종류는 덮어쓸 수 없습니다")
        self.code_act.setEnabled(bool(card) and bool(source.get("game")) and kind == "cards" and not self.reading)
        self.remove_act.setEnabled(imported)

    def _description(self, card, source, lang):
        if source.get("game"):
            desc = card.get("desc_" + lang, "")
            if "raw_vars" in card:
                desc = PV.fill_values({}, desc, card, self.upgraded.isChecked())
            return desc
        if self.kind == "card_keywords":          # 프로젝트 키워드: 적어 둔 설명을 그대로 보인다
            return card.get("desc_" + lang, "")
        p = source["project"]
        return PV.fill_values(p, M.description(p, card, DESC_KIND.get(self.kind, "card"), lang), card,
                              self.upgraded.isChecked())

    def _pixmap_for(self, card, source):
        try:
            pm = None
            if source.get("game") and card.get("portrait") and self.assets is not None:
                pic = self.assets.texture(card["portrait"]).copy()
                pic.thumbnail(IMAGE_BOX)
                pm = PQ._qpixmap(pic)
            elif card.get("image"):
                pm = PQ.pixmap(card["image"], IMAGE_BOX[0], IMAGE_BOX[1], "contain")
            return pm if isinstance(pm, QPixmap) and not pm.isNull() else None
        except (ImportError, OSError, ValueError, KeyError, AttributeError):
            return None

    def _show_art(self, card, source):
        pm = self._pixmap_for(card, source)
        if pm is not None:
            self.art.setPixmap(pm)

    # ---- 가져오기 · 적용 · 제거 ----
    def apply_keyword(self, selected):
        tab = self.card_page
        card = self._current_card()
        if card is None or not selected:
            _info(self, "카드 탭에서 적용할 카드를 먼저 선택하세요.")
            return
        keyword = M.pascal(selected["id"].lower())
        if keyword not in card["keywords"]:
            card["keywords"].append(keyword)
            self.app.mark_dirty()
            tab.refresh_list(tab.cur)
        self.status.setText(f"{M.text(card, 'name', 'ko')}에 적용됨")

    def apply_tag(self, selected):
        """프로젝트의 태그(키워드): 편집 중인 카드의 태그 목록에 넣는다."""
        tab = self.card_page
        card = self._current_card()
        if card is None or not selected:
            _info(self, "카드 탭에서 적용할 카드를 먼저 선택하세요.")
            return
        if selected["id"] not in card.get("gtags", []):
            card.setdefault("gtags", []).append(selected["id"])
            self.app.mark_dirty()
            tab.refresh_list(tab.cur)
        self.status.setText(f"{M.text(card, 'name', 'ko')}에 적용됨")

    def apply_selected(self, card=None, source=None):
        card = card or self.selection()
        source = source or self.source()
        tab = self.card_page
        if not card or self.kind not in ("cards", "card_keywords"):
            return False
        if source.get("game") and self.kind == "cards":
            return self.add(card, source)
        if tab.cur is None or tab.cur >= len(tab.items):
            _info(self, "카드 탭에서 적용할 카드를 먼저 선택하세요.")
            return False
        if tab._locked(tab.items[tab.cur]):
            _info(self, "원작 카드는 고칠 수 없습니다. 카드 탭에서 복제한 뒤 복사본을 고치세요.")
            return False
        if self.kind == "card_keywords":
            if source.get("game"):
                self.apply_keyword(card)
            else:
                self.apply_tag(card)
            return True
        if source.get("game"):
            return False
        if not _ask(self, "현재 카드의 내용과 효과를 선택한 카드로 바꿀까요?\n카드 ID와 전용 캐릭터 설정은 유지됩니다."):
            return False
        index = tab.cur
        old = tab.items[index]
        try:
            project = CLR.import_project_card(self.app.project, source["project"], card, all_ids(self.app.project))
        except ValueError as exc:
            _warn(self, str(exc))
            return False
        replacement = project["cards"].pop()
        imported_id = replacement["id"]
        CLR.rename_refs(replacement, imported_id, old["id"])
        replacement["id"] = old["id"]
        replacement["pool_character"] = old.get("pool_character", "")
        project["cards"][index] = replacement
        self.app.project = project
        self.app.mark_dirty()
        self.app.load_all()
        tab.refresh_list(index)
        self.status.setText(f"{M.text(replacement, 'name', 'ko')}을(를) 편집 중인 카드에 적용했습니다.")
        return True

    def add_to_deck(self, done):
        """끌어 놓은 카드를 가져온 뒤 done(프로젝트 카드 id) 을 부른다 (원작 카드는 코드를 읽은 뒤에 부른다)."""
        card, source = self.selection(), self.source()
        if not card or self.kind != "cards":
            self.status.setText("덱에는 카드 목록의 카드만 넣을 수 있습니다.")
            return False
        if source.get("current"):                  # 이미 이 프로젝트에 있는 카드는 가져오지 않고 그대로 넣는다
            done(card["id"])
            return True
        return self.add(card, source, done)

    def add_to_relics(self, done):
        """끌어 놓은 유물을 가져온 뒤 done(유물 id, 원작 유물은 'game:' 붙은 id) 을 부른다."""
        item, source = self.selection(), self.source()
        if not item or self.kind != "relics":
            self.status.setText("시작 유물에는 유물 목록의 항목만 넣을 수 있습니다.")
            return False
        if source.get("current"):
            done(item["id"])
            return True
        return self.add(item, source, done)

    def add(self, card=None, source=None, done=None):
        card, source = card or self.selection(), source or self.source()
        if not card:
            return False
        kind = self.kind
        if source.get("game") and kind == "cards":
            return self.import_game_copy(card, done)
        ref = None
        if source.get("game"):
            ch = self.app.project["character"]
            if kind in ("cards", "relics", "potions") and not ch.get("enabled"):
                _info(self, "캐릭터 탭에서 새 캐릭터 만들기를 켜면 원작 카드를 풀에 추가할 수 있습니다.")
                return False
            ch.setdefault("game_" + kind, {})[card["id"]] = dict(card) if kind in ("powers", "card_keywords") \
                else M.text(card, "name", "ko")
            ref = "game:" + card["id"]
        else:
            try:
                if kind == "cards":
                    self.app.project = CLR.import_project_card(self.app.project, source["project"], card,
                                                               all_ids(self.app.project))
                else:
                    self.app.project = CLR.import_project_item(self.app.project, card, PROJECT_KEY[kind],
                                                               all_ids(self.app.project))
            except ValueError as exc:
                _warn(self, str(exc))
                return False
        self.app.mark_dirty()
        self.app.load_all()
        if not source.get("game"):
            page = self._page()
            key = PROJECT_KEY[kind]
            index = len(self.app.project[key]) - 1
            page.search.setText("")
            page.refresh_list(index)
            ref = self.app.project[key][-1]["id"]
        self.status.setText(f"{M.text(card, 'name', 'ko')} 추가됨")
        self.show_card()
        if done and ref:
            done(ref)
        return True

    def import_game_copy(self, card, done=None):
        if self.reading:
            self.status.setText("원작 코드를 읽는 중입니다.")
            return False
        project = self.app.project
        folder = self.assets.sts2_path
        self.reading = True
        self.status.setText("원작 카드 효과를 가져오는 중…")

        def work():
            try:
                code, _ = CLR.read_original_code(folder, card["id"])
                self.run_on_ui.emit(lambda: self._finish_game_copy(project, card, code, None, done))
            except Exception as exc:  # noqa: BLE001
                self.run_on_ui.emit(lambda: self._finish_game_copy(project, card, None, exc, done))
        threading.Thread(target=work, daemon=True).start()
        return True

    def _finish_game_copy(self, project, card, code, exc, done=None):
        self.reading = False
        if exc is not None:
            self._original_error(card, exc)
            return
        try:
            if self.app.project is not project:
                raise ValueError("프로젝트가 변경되었습니다. 카드를 다시 가져오세요.")
            em = MI.ExtMod()
            em.classes = {c.name: c for c in MI.parse_cs(code)}
            MI._extract_items(em)
            item = next((it for it in em.items["card"] if it["class"] == M.pascal(card["id"].lower())), None)
            if item is None:
                raise ValueError("원작 카드의 기본 클래스와 효과를 확인할 수 없습니다.")
            item.update({k: v for k, v in card.items() if k.startswith(("name_", "desc_"))})
            copy_card = MI.clone_item(em, item, project)
            copy_card["clone"]["game_original"] = True
            self.add(copy_card, {"project": {"cards": [copy_card]}}, done)
        except Exception as e:  # noqa: BLE001
            self._original_error(card, e)

    def remove(self):
        card = self.selection()
        if not card or not self.source().get("game"):
            return
        ch = self.app.project["character"]
        key = "game:" + card["id"]
        kind = self.kind
        if kind == "powers" and any(key == val for val in CLR._strings(self.app.project)):
            _info(self, "이 파워를 사용하는 효과를 먼저 변경하세요.")
            return
        if kind == "relics" and key in ch["relics"]:
            if not _ask(self, "시작 유물에서도 제거할까요?"):
                return
            ch["relics"] = [v for v in ch["relics"] if v != key]
        if kind == "cards" and any(row["card"] == key for row in ch["deck"]):
            if not _ask(self, "시작 덱에서도 이 카드를 제거할까요?"):
                return
            ch["deck"] = [row for row in ch["deck"] if row["card"] != key]
        ch.get("game_" + kind, {}).pop(card["id"], None)
        self.app.mark_dirty()
        self.app.load_all()
        self.status.setText("내 풀에서 제거했습니다.")
        self.show_card()

    # ---- 원작 코드 ----
    def _original_error(self, card, exc):
        detail = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(exc)).strip()
        if not detail:
            detail = "실패한 도구가 오류 설명을 반환하지 않았습니다. .NET SDK와 게임 설치 경로를 확인해 주세요."
        title = f"원작 카드 {card['id']} 읽기 실패"
        self.status.setText(f"{title} · {detail.splitlines()[0][:80]}")
        self.app.log(f"[오류] {title} ({type(exc).__name__})\n{detail}")
        _warn(self, f"{title}\n\n{type(exc).__name__}\n{detail}")

    def show_code(self):
        card = self.selection()
        if not card or not self.source().get("game") or self.reading:
            return
        if "_source" in card:
            self._display_code(card)
            return
        self.reading = True
        self.status.setText("원작 카드 코드를 읽는 중…")
        folder = self.assets.sts2_path

        def work():
            try:
                code, raw = CLR.read_original_code(folder, card["id"], self.app.log)
                self.run_on_ui.emit(lambda: self._code_ready(card, code, raw, None))
            except Exception as exc:  # noqa: BLE001
                self.run_on_ui.emit(lambda: self._code_ready(card, None, None, exc))
        threading.Thread(target=work, daemon=True).start()

    def _code_ready(self, card, code, raw, exc):
        self.reading = False
        if exc is not None:
            self._original_error(card, exc)
        else:
            card["_source"], card["raw_vars"] = code, raw
            self._display_code(card)
            self.status.setText("원작 수치를 설명에 반영했습니다.")
        self.show_card()

    def _display_code(self, card):
        dialog = QDialog(self)
        dialog.setWindowTitle((M.text(card, "name", "ko") or card["id"]) + " · 원작 코드")
        dialog.resize(900, 640)
        col = QVBoxLayout(dialog)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setStyleSheet("font-family: Consolas;")
        view.setPlainText(card["_source"])
        col.addWidget(view)
        dialog.show()
        self._code_dialogs = getattr(self, "_code_dialogs", []) + [dialog]

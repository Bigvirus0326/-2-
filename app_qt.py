"""Qt 앱 껍데기: 메인 창, 메뉴, 설정, 프로젝트 열기·저장·되돌리기.

올라간 탭: 모드 / 빌드, 캐릭터, 카드·유물·물약·파워. 나머지는 자리 표시이며 Tk 앱(sts2_mod_maker.py)에서 쓴다.
실행: python app_qt.py
"""
import json
import os
import sys
import threading

from PySide6.QtCore import QRect, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QIcon, QKeySequence, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QLabel, QMessageBox,
                               QPlainTextEdit, QSplashScreen)

import buildrun as BR
import artuiqt
import webbrowser
import findcore
import helptext
import projectops as PO
import updaterqt as UQ
from findqt import FindPaletteQt
import modimport as MI
import ingame
from characterqt import CharacterPanelQt
from cardlibqt import CardLibraryQt
from aiqt import AIWorkflowQt
from artuiqt import ArtApplyDialogQt, ArtGuideDialogQt
from feedbackqt import FeedbackDialogQt
from externalqt import ExternalTabQt
from gameviewqt import GameViews
from gallery_qt import GalleryQt
from projectreviewqt import ImportResultsDialogQt, UnresolvedDialogQt, show_balance
from fxtabqt import FxTabQt
from gimmickqt import GimmickQt
from itemtabqt import CardTabQt, PotionTabQt, PowerTabQt, RelicTabQt
import modgen as M
import projectio as IO
import qtkit as Q
import updater as UP
from modtab_qt import ModTabQt

SNAPSHOT_DELAY_MS = 500          # 입력이 이만큼 멈추면 한 단계로 기록 (Tk 앱과 같다)
PROJECT_FILTER = "모드 메이커 프로젝트 (*.sts2mod.json *.json);;모든 파일 (*.*)"
SAVE_FILTER = "모드 메이커 프로젝트 (*.sts2mod.json)"
LOAD_ERRORS = (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError)
# Tk 앱의 작업 탭과 같은 순서·이름
TAB_TITLES = ["모드 / 빌드", "캐릭터", "카드", "유물", "물약", "파워", "기믹", "이펙트·버튼", "도감", "다른 모드"]


UI_SCALES = [0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6]


def _icon_dir():
    """도구 막대 그림 폴더. 개발 중에는 이 파일 옆, 배포본에서는 PyInstaller 가 풀어 둔 곳."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "ui_icons")


class QtApp(Q.DockWorkspace):
    log_line = Signal(str)   # 빌드 스레드에서 보낸 줄을 화면 스레드에서 받는다
    takeover_done = Signal(object, object)   # (프로젝트, 모드) - 화면 스레드에서 연다
    takeover_failed = Signal(str)

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else IO.load_settings()
        self.views = GameViews(self.game_assets, lambda: self.project, self)   # '게임 화면' 설정 (모든 그림 칸이 같이 쓴다)
        self.project = M.default_project()
        self.project_path = ""
        self.dirty = False
        self.history = IO.History()
        self._saved_state = ""
        self._restoring = False
        self._snap_timer = QTimer(self)
        self._snap_timer.setSingleShot(True)
        self._snap_timer.setInterval(SNAPSHOT_DELAY_MS)
        self._snap_timer.timeout.connect(self.commit_snapshot)

        self.busy = False
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(f"QPlainTextEdit {{ border: 1px solid {Q.C['line']}; border-radius: 6px; }}")   # 읽기 전용: 입력 강조 띠를 쓰지 않는다
        self.log_view.setMaximumBlockCount(3000)
        self.log_dock = QDockWidget("실행 기록", self)
        self.log_dock.setObjectName("실행 기록")
        self.log_dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_line.connect(self._append_log)
        self.takeover_done.connect(self._finish_takeover)
        self._card_library = None
        self._art_guide = None
        self.app_dir = IO.APP_DIR
        self.takeover_failed.connect(lambda msg: (self.status("[오류] 통째로 열기 실패: " + msg, 8000),
                                                 QMessageBox.critical(self, IO.APP_TITLE, f"이 모드를 통째로 열지 못했습니다:\n{msg}")))

        actions = [self.do_validate, lambda: self.do_generate(), lambda: self.do_build(False),
                   lambda: self.do_build(True)]
        self.mod_page = ModTabQt(self.project["mod"], self.settings, actions=actions,
                                 on_settings_change=self._settings_changed, on_mod_change=self._mod_changed)
        page = Q.ScrollPage()
        page.set_content(self.mod_page)
        self.add_page(page, TAB_TITLES[0])
        self.char_page = CharacterPanelQt(self.project, on_change=self._char_changed)
        self.add_page(self.char_page, TAB_TITLES[1])
        self.char_page.assets_fn = self.game_assets
        self.item_pages = [CardTabQt(self.project, on_change=self._items_changed),
                           RelicTabQt(self.project, on_change=self._items_changed),
                           PotionTabQt(self.project, on_change=self._items_changed),
                           PowerTabQt(self.project, on_change=self._items_changed)]
        for item_page, title in zip(self.item_pages, TAB_TITLES[2:6]):
            item_page.assets_fn = self.game_assets
            item_page.set_views(self.views)
            self.add_page(item_page, title)
        self.gimmick_page = GimmickQt(self.project, on_change=self.mark_dirty, on_reload=self.load_all)
        self.add_page(self.gimmick_page, TAB_TITLES[6])
        self.item_pages[0].library_fn = self.open_card_library
        self.fx_page = FxTabQt(self)
        self.add_page(self.fx_page, TAB_TITLES[7])
        self.gallery_page = GalleryQt(self.project, views=self.views)
        self.gallery_page.open_requested.connect(self._open_gallery)
        self.add_page(self.gallery_page, TAB_TITLES[8])
        self.ext_page = ExternalTabQt(self)
        self.add_page(self.ext_page, TAB_TITLES[9])

        self._build_menu()
        self._build_toolbar()
        saved = self.settings.get("dock_layout", "")
        if not (saved and self.restore_layout_text(saved)):   # 실패하면 기본 배치(한 탭 묶음)를 쓴다
            self._select_on_show = page   # 처음 열 때는 '모드 / 빌드' 탭이 보이게 (Tk 앱과 같다). 보인 뒤에 골라야 남는다
        self.log_dock.hide()   # 실행 기록은 기본으로 꺼 둔다 (보기 메뉴에서 켠다)
        self.resize(1100, 780)
        self._default_width_pending = not saved   # 처음 실행이면 작업 영역을 넉넉하게 연다 (showEvent 에서)
        self.update_title()
        last = self.settings.get("last_project", "")
        if last and os.path.isfile(last):
            self.open_project(last, quiet=True)
        else:
            self.new_project(confirm=False)
        QTimer.singleShot(1500, lambda: UQ.auto_check(self))

    # ---- 도구 막대 ----
    def _build_toolbar(self):
        """위쪽 도구 막대 (Tk 앱의 단추 줄과 같다). 그림·글자·말풍선 설명이 있어 메뉴를 몰라도 찾을 수 있다."""
        bar = self.addToolBar("도구")
        bar.setObjectName("main_toolbar")
        bar.setMovable(False)
        bar.setIconSize(QSize(24, 24))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)

        def button(icon, text, slot, tip_text):
            action = QAction(QIcon(os.path.join(_icon_dir(), icon + ".png")), text, self)
            Q.tip(action, tip_text)
            action.setStatusTip(tip_text)
            action.triggered.connect(slot)
            bar.addAction(action)

        button("save", "저장", self.save, "저장 (Ctrl+S)")
        button("undo", "되돌리기", self.undo, "되돌리기 (Ctrl+Z)")
        button("redo", "다시", self.redo, "다시 실행 (Ctrl+Y)")
        bar.addSeparator()
        button("validate", "① 검사", self.do_validate, "만든 것에 빠진 칸이나 잘못된 값이 없는지 확인합니다.")
        button("generate", "② 생성", lambda: self.do_generate(), "C# 프로젝트 파일을 만듭니다.")
        button("build", "③ 빌드 (dll)", lambda: self.do_build(False),
               "카드 효과가 실행되는 기능 파일(DLL)을 만들어 이 컴퓨터의 게임 모드 폴더에 넣습니다. 그림과 글 파일은 ④에서 함께 만듭니다.")
        button("publish", "④ 게시 (dll+pck)", lambda: self.do_build(True),
               "기능 파일(DLL)과 그림·글 파일(PCK)을 함께 만들어 이 컴퓨터의 게임 모드 폴더에 넣습니다.")
        bar.addSeparator()
        button("ai_make", "AI로 만들기", self.open_ai,
               "ChatGPT·Claude 같은 채팅 AI에게 카드·유물·물약·파워를 만들게 합니다.\n"
               "설명서를 복사해 AI에게 보내고, AI 의 답을 붙여 넣으면 검사·미리보기 후 들어갑니다.")
        button("ai_art", "AI 그림", self.open_art_guide,
               "모드에 필요한 모든 그림을 채팅 AI 에게 만들게 하는 설명서를 만듭니다.\n"
               "받은 그림을 한 번에 모든 칸에 넣을 수 있습니다.")
        button("copy_art", "그림 설명서 복사", self.quick_copy_art,
               "누르면 바로 그림 설명서를 복사합니다 (AI 그림 창에서 고른 그림·화풍 그대로).")

    # ---- 메뉴 ----
    def _build_menu(self):
        def add(menu, text, slot, shortcut=None):
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            menu.addAction(action)
            return action

        def check(menu, text, checked, slot):
            action = QAction(text, self)
            action.setCheckable(True)
            action.setChecked(bool(checked))
            action.toggled.connect(slot)
            menu.addAction(action)
            return action

        file_menu = self.menuBar().addMenu("파일")
        add(file_menu, "새로 만들기", lambda: self.new_project(), "Ctrl+N")
        add(file_menu, "열기…", self.open_dialog, "Ctrl+O")
        add(file_menu, "저장", self.save, "Ctrl+S")
        add(file_menu, "다른 이름으로 저장…", self.save_as, "Ctrl+Shift+S")
        add(file_menu, "캐릭터 카드 라이브러리…", self.open_card_library)
        add(file_menu, "프로젝트 자산 모으기…", self.pack_project_assets)
        file_menu.addSeparator()
        add(file_menu, "📂 다른 모드를 통째로 열기 (바로 작업)…", self.open_external_tab)
        add(file_menu, "다른 모드 불러오기 (dll/pck/소스)…", self.open_external_tab)
        add(file_menu, "다른 프로젝트 합치기…", self.merge_dialog)
        add(file_menu, "예시 기믹 추가 (해적·마법사 스타일)…", lambda: self.gimmick_page.add_examples())
        file_menu.addSeparator()
        add(file_menu, "종료", self.close, "Ctrl+Q")

        edit_menu = self.menuBar().addMenu("편집")
        self.undo_action = add(edit_menu, "실행 취소", self.undo, "Ctrl+Z")
        self.redo_action = add(edit_menu, "다시 실행", self.redo, "Ctrl+Y")
        self._update_undo_actions()
        edit_menu.addSeparator()
        add(edit_menu, "목록에서 찾기", self.focus_list_search, "Ctrl+F")
        add(edit_menu, "전체에서 찾기…", self.open_find, "Ctrl+P")
        edit_menu.addSeparator()
        add(edit_menu, "카드 풀 밸런스 · 설명 검사…", self.show_balance)
        add(edit_menu, "가져온 모드 미연결 호출…", self.show_unresolved)

        ai_menu = self.menuBar().addMenu("AI")
        add(ai_menu, "AI로 만들기 (요청 복사 · 결과 붙여넣기)…", self.open_ai)
        add(ai_menu, "AI 그림 설명서 만들기…", self.open_art_guide)
        add(ai_menu, "📋 그림 설명서 바로 복사", self.quick_copy_art)
        add(ai_menu, "그림 한꺼번에 적용…", self.open_art_apply)

        view_menu = self.menuBar().addMenu("보기")
        for action in self.view_menu_actions():
            view_menu.addAction(action)
        view_menu.addSeparator()
        add(view_menu, "떨어진 탭 되돌리기", self.dock_all)
        add(view_menu, "배치 초기화", self.reset_layout)
        view_menu.addSeparator()
        self.focus_action = check(view_menu, "편집에 집중", False, self.set_editor_layout)
        add(view_menu, "크게", lambda: self.zoom_step(1), "Ctrl+=")
        add(view_menu, "작게", lambda: self.zoom_step(-1), "Ctrl+-")
        add(view_menu, "기본 크기 (100%)", lambda: self.set_ui_scale(1.0), "Ctrl+0")

        help_menu = self.menuBar().addMenu("도움말")
        add(help_menu, "사용 방법", self.show_help)
        add(help_menu, "건의 / 오류 보고…", self.open_feedback)
        add(help_menu, "로그 / 보고서 폴더 열기", self.open_feedback_folder)
        add(help_menu, "BaseLib (GitHub)", lambda: webbrowser.open(IO.BASELIB_URL))
        add(help_menu, "StS2 모딩 튜토리얼", lambda: webbrowser.open("https://tutorials.sts2modding.com/en/"))
        help_menu.addSeparator()
        add(help_menu, "🔔 업데이트 확인…", lambda: UQ.check(self, manual=True))
        check(help_menu, "켤 때 새 버전 알려 주기", self.settings.get("update_check", True),
              lambda on: self._set_update_option("update_check", on))
        check(help_menu, "시험판(Pre-release)도 받기", self.settings.get("update_prerelease", False),
              lambda on: self._set_update_option("update_prerelease", on))
        add(help_menu, "모드 메이커 깃허브 (릴리스)", lambda: webbrowser.open(UP.RELEASES_PAGE))
        disabled = QAction(f"버전 v{UP.VERSION}", self)
        disabled.setEnabled(False)
        help_menu.addAction(disabled)

    def _update_undo_actions(self):
        self.undo_action.setEnabled(self.history.can_undo() or self._snap_timer.isActive())
        self.redo_action.setEnabled(self.history.can_redo())

    # ---- 설정 · 배율 · 도움말 ----
    def persist_settings(self):
        IO.save_settings(self.settings)

    def _set_update_option(self, key, on):
        self.settings[key] = bool(on)
        self.persist_settings()

    def set_ui_scale(self, value):
        """화면 배율: 글꼴 크기를 바꾼다 (Tk 의 set_scale 과 같은 단계)."""
        value = min(max(float(value), UI_SCALES[0]), UI_SCALES[-1])
        self.settings["ui_scale"] = round(value, 2)
        Q.apply_theme(QApplication.instance(), max(7, round(10 * value)))
        self.persist_settings()
        self.status(f"화면 배율 {round(value * 100)}%", 2500)

    def zoom_step(self, step):
        current = float(self.settings.get("ui_scale", 1.0) or 1.0)
        i = min(range(len(UI_SCALES)), key=lambda k: abs(UI_SCALES[k] - current))
        self.set_ui_scale(UI_SCALES[max(0, min(len(UI_SCALES) - 1, i + step))])

    def set_editor_layout(self, focused):
        """편집에 집중: 항목 탭에서 목록과 미리보기를 숨기고 편집 칸만 보인다 (Tk 의 set_editor_layout 과 같다)."""
        for page in self.item_pages:
            page.set_focus_layout(bool(focused))

    def focus_list_search(self):
        for page in self.item_pages:
            if page.isVisible():
                page.search.setFocus()
                page.search.selectAll()
                return
        self.open_find()

    def open_find(self, query=""):
        FindPaletteQt(self, query, self).exec()

    def open_external_tab(self):
        self.select(self.ext_page)

    def quick_copy_art(self):
        try:
            message = artuiqt.quick_copy(self)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, IO.APP_TITLE, f"그림 설명서를 만들지 못했습니다: {exc}")
            return
        self.status("✔ " + message, 6000)

    def show_help(self):
        QMessageBox.information(self, IO.APP_TITLE, helptext.HELP_TEXT)

    def open_feedback_folder(self):
        import feedback as FB
        path = FB.log_dir(IO.APP_DIR)
        os.makedirs(path, exist_ok=True)
        try:
            os.startfile(path)
        except (OSError, AttributeError):
            pass

    # ---- 프로젝트 자산 · 합치기 ----
    def pack_project_assets(self):
        if self.busy:
            QMessageBox.information(self, IO.APP_TITLE, "빌드 중에는 프로젝트 자산을 모을 수 없습니다.")
            return
        if not self.project_path and not self.save_as():
            return
        sources, missing = PO.pack_plan(self.project)
        if not sources:
            QMessageBox.information(self, IO.APP_TITLE, "모을 그림 파일이 없습니다.")
            return
        if missing:
            QMessageBox.warning(self, IO.APP_TITLE,
                                "그림 파일을 찾지 못했습니다. 경로를 수정한 뒤 다시 시도하세요:\n\n" +
                                "\n".join(missing[:12]) +
                                (f"\n… 외 {len(missing) - 12}개" if len(missing) > 12 else ""))
            return
        try:
            packed, count, created = PO.pack_assets(self.project, self.project_path, sources)
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, IO.APP_TITLE, f"자산을 복사하지 못했습니다:\n{e}")
            return
        old_project, old_dirty = self.project, self.dirty
        self.project = packed
        self.mark_dirty()
        if not self.save():
            self.project, self.dirty = old_project, old_dirty
            PO.remove_files(created)
            self.load_all()
            return
        self.load_all()
        QMessageBox.information(self, IO.APP_TITLE,
                                f"그림 {count}개를 프로젝트의 assets 폴더에 모았습니다.\n"
                                "프로젝트 파일에는 상대 경로로 저장했습니다.")

    def merge_dialog(self):
        path, _ = QFileDialog.getOpenFileName(self, "합칠 프로젝트", "",
                                              "모드 메이커 프로젝트 (*.sts2mod.json *.json);;모든 파일 (*.*)")
        if not path:
            return
        try:
            other = PO.load_project_file(path)
        except (OSError, ValueError, KeyError, TypeError) as e:
            QMessageBox.critical(self, IO.APP_TITLE, f"프로젝트를 읽을 수 없습니다:\n{e}")
            return
        counts, renamed = PO.merge_into(self.project, other)
        self.mark_dirty()
        self.load_all()
        QMessageBox.information(self, IO.APP_TITLE, PO.merge_summary(counts, renamed))

    # ---- 상태 ----
    def status(self, text, ms=4000):
        self.statusBar().showMessage(text, ms)

    def update_title(self):
        name = os.path.basename(self.project_path) if self.project_path else "새 프로젝트"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} - {IO.APP_TITLE} v{UP.VERSION}")

    def load_all(self):
        self.mod_page.load(self.project["mod"])
        self.char_page.load(self.project)
        for page in self.item_pages:
            page.load_project(self.project)
        self.gimmick_page.load_project(self.project)
        self.fx_page.load_project()
        self.gallery_page.set_project(self.project)
        self.update_title()

    def open_card_library(self):
        """카드 라이브러리 창 (한 번 만들면 계속 쓴다)."""
        if self._card_library is None:
            self._card_library = CardLibraryQt(self, self.item_pages[0], self)
        self._card_library.show()
        self._card_library.raise_()

    def open_ai(self):
        AIWorkflowQt(self, paste=False).exec()

    def _open_gallery(self, kind, index):
        """도감에서 칸을 누르면 그 항목의 편집 화면을 연다."""
        key = {"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}[kind]
        self.goto_any(kind, self.project[key][index]["id"])

    def goto_any(self, kind, ident):
        """kind·ID 가 있는 탭과 줄을 고른다 (AI 로 넣은 항목을 바로 보여 준다)."""
        items_pages = {"card": 0, "relic": 1, "potion": 2, "power": 3}
        if kind in items_pages:
            page = self.item_pages[items_pages[kind]]
            index = next((i for i, it in enumerate(page.items) if it["id"] == ident), None)
            if index is not None:
                page.refresh_list(index)
            self.select(page)
            return
        gimmick_panels = {"tag": "tags", "summon": "summons", "orb": "orbs", "pet": "pets"}
        if kind in gimmick_panels:
            panel = self.gimmick_page.panels[gimmick_panels[kind]]
            index = next((i for i, it in enumerate(panel.items) if it["id"] == ident), None)
            if index is not None:
                panel.refresh_list(index)
            self.gimmick_page.tabs.setCurrentWidget(panel)
            self.select(self.gimmick_page)
            return
        if kind == "fx":
            index = next((i for i, e in enumerate(self.fx_page.painter.fxs) if e["id"] == ident), None)
            if index is not None:
                self.fx_page.painter.select_effect(index)
            self.fx_page.setCurrentWidget(self.fx_page.painter)
            self.select(self.fx_page)
        elif kind == "button":
            index = next((i for i, b in enumerate(self.fx_page.buttons.items) if b["id"] == ident), None)
            if index is not None:
                self.fx_page.buttons.select(index)
            self.fx_page.setCurrentWidget(self.fx_page.buttons)
            self.select(self.fx_page)

    def open_art_guide(self):
        if self._art_guide is None:
            self._art_guide = ArtGuideDialogQt(self, self)
        self._art_guide.show()
        self._art_guide.raise_()

    def open_art_apply(self):
        dialog = ArtApplyDialogQt(self, parent=self)
        dialog.show()

    def open_feedback(self, initial_kind="건의", initial_title="", initial_description=""):
        FeedbackDialogQt(IO.APP_DIR, self, initial_kind, initial_title, initial_description).exec()

    def show_balance(self):
        show_balance(self, self.project)

    def show_unresolved(self):
        def changed():
            self.mark_dirty()
            self.load_all()
        UnresolvedDialogQt(self, self.project, changed).exec()

    def reload_items(self):
        """카드·유물·물약·파워 목록이 바뀌었을 때 (복제 등): 목록과 캐릭터의 덱·유물 고르기를 다시 채운다."""
        for page in self.item_pages:
            page.refresh_list(None)
        self.char_page.refresh_choices()

    def open_mod_as_project(self, path):
        """다른 모드를 같은 ID 의 새 프로젝트로 연다 (백그라운드에서 읽고 푼다)."""
        if self.busy:
            QMessageBox.information(self, IO.APP_TITLE, "빌드 중에는 열 수 없습니다.")
            return
        if not self.confirm_discard():
            return
        sts2 = self.settings.get("sts2_path", "")
        self.status(f"다른 모드를 통째로 여는 중: {os.path.basename(path)} …", 60000)

        def work():
            try:
                em = MI.load_mod(path, sts2, log=self.log)
                project = MI.takeover(em, sts2, log=self.log)
                self.takeover_done.emit(project, em)
            except Exception as e:  # noqa: BLE001
                self.takeover_failed.emit(str(e) or type(e).__name__)
        threading.Thread(target=work, daemon=True).start()

    def _finish_takeover(self, project, em):
        project = M.normalize(project)
        self.project = project
        self.project_path = ""
        self.dirty = True
        self.load_all()
        self.reset_history()
        self.update_title()
        n = {k: len(project[k]) for k in ("cards", "relics", "potions", "powers")}
        self.log(f"통째로 열었습니다: {em.name} ({em.id}) — 카드 {n['cards']} · 유물 {n['relics']} · 물약 {n['potions']} · 파워 {n['powers']}")
        ImportResultsDialogQt(self, project, self._takeover_notes(project, em, n), self._open_import_card,
                              analyze_card=self._analyze_import_card, show_unresolved=self.show_unresolved).exec()

    def _takeover_notes(self, project, em, n):
        """가져오기 결과 창의 안내 줄 (Tk 의 _finish_takeover 와 같은 내용)."""
        t = project.get("takeover") or {}
        lines = [f"'{em.name}' ({em.id}) 을(를) 새 프로젝트로 열었습니다.",
                 f"카드 {n['cards']} · 유물 {n['relics']} · 물약 {n['potions']} · 파워 {n['powers']} 를 여기서 고칠 수 있습니다."]
        if t.get("kept"):
            lines.append(f"그 밖에 {len(t['kept'])}개 항목은 파일 구조 때문에 원래 코드 그대로 둡니다 (동작은 같음).")
        ichs = M.imported_characters(project)
        if ichs:
            lines.append(f"캐릭터 {len(ichs)}명(" + ", ".join(M.text(c, "name", "ko") or c["class"] for c in ichs) +
                         ")도 가져왔습니다 — '캐릭터' 탭 위쪽에서 골라 이름·체력·시작 덱·유물·그림·대사를 고치고, "
                         "'카드' 탭에서 캐릭터별 카드 목록과 전용 풀을 설정할 수 있습니다.")
        if t.get("characters"):
            lines.append("캐릭터(" + ", ".join(c["class"] for c in t["characters"]) + ")는 원래 코드 그대로 씁니다.")
        backup = os.path.join(t.get("dir", ""), "backup")
        lines += ["",
                  f"• 모드 ID 가 원래와 같은 '{em.id}' 라서, 빌드하면 게임 mods 폴더의 원래 모드를 이 버전으로 바꿉니다.",
                  f"  원래 모드 파일은 따로 백업해 두었습니다: {backup}" if os.path.isdir(backup) else
                  "  원래 모드가 필요하면 빌드 전에 따로 복사해 두세요.",
                  "• 원래 코드·그림·번역은 이 컴퓨터의 작업 폴더에 보관됩니다. 지우지 마세요.",
                  "• 먼저 '파일 → 다른 이름으로 저장' 으로 프로젝트를 저장하세요."]
        return lines

    def _open_import_card(self, card_id):
        self.goto_any("card", card_id)

    def _analyze_import_card(self, card_id):
        """결과 창의 '다시 분석': 카드를 열고 원본 효과를 다시 블록으로 푼다."""
        self.goto_any("card", card_id)
        page = self.item_pages[0]
        card = next((c for c in page.items if c["id"] == card_id), None)
        index = next((i for i, e in enumerate(card.get("effects", [])) if e.get("original_effect")), None) if card else None
        if index is not None:
            page.edit_original(index, reanalyze=True)

    def game_assets(self):
        """게임 폴더의 그림 (전투 화면 모형용). 게임 폴더가 없으면 None."""
        return ingame.get_assets(self.settings.get("sts2_path", ""))

    def _char_changed(self):
        self.mark_dirty()

    def _items_changed(self):
        self.char_page.refresh_choices()   # 카드·유물 이름이 캐릭터의 덱·유물 목록에도 보인다
        self.mark_dirty()

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.update_title()
        if not self._restoring:
            self._snap_timer.start()
        self._update_undo_actions()

    def _mod_changed(self, _mod):
        self.mark_dirty()

    def _settings_changed(self, settings):
        if not IO.save_settings(settings):
            self.status("[경고] 앱 설정을 저장하지 못했습니다.", 8000)

    # ---- 되돌리기 ----
    def commit_snapshot(self):
        try:
            state = IO.snapshot(self.project)
        except (TypeError, ValueError):
            return
        self.history.push(state, {"tab": "모드 / 빌드"})
        self._update_undo_actions()

    def reset_history(self):
        self._snap_timer.stop()
        try:
            state = IO.snapshot(self.project)
        except (TypeError, ValueError):
            state = ""
        self.history.reset(state)
        self._saved_state = state
        self._update_undo_actions()

    def undo(self):
        self._flush_snapshot()
        if not self.history.can_undo():
            self.status("더 되돌릴 것이 없습니다")
            return
        state, _loc = self.history.undo()
        self._restore(state, "되돌렸습니다")

    def redo(self):
        self._flush_snapshot()
        if not self.history.can_redo():
            self.status("다시 실행할 것이 없습니다")
            return
        state, _loc = self.history.redo()
        self._restore(state, "다시 실행했습니다")

    def _flush_snapshot(self):
        if self._snap_timer.isActive():   # 아직 기록 안 된 입력부터 기록
            self._snap_timer.stop()
            self.commit_snapshot()

    def _restore(self, state, msg):
        self._restoring = True
        try:
            self.project = json.loads(state)
            self.dirty = state != self._saved_state
            self.load_all()
        finally:
            self._restoring = False
        self._update_undo_actions()
        self.status(msg)

    # ---- 모드 / 빌드 ----
    def log(self, msg):
        """어느 스레드에서 불러도 된다: 실제 쓰기는 화면 스레드에서 한다."""
        self.log_line.emit(str(msg))

    def _append_log(self, msg):
        self.log_view.appendPlainText(msg.rstrip())

    def do_validate(self):
        errors, warnings = BR.validate(self.project)
        for w in warnings:
            self.log("[경고] " + w)
        for e in errors:
            self.log("[오류] " + e)
        if errors or warnings:
            text = "\n".join((["오류:"] + errors if errors else []) + (["경고:"] + warnings if warnings else []))
            (QMessageBox.warning if errors else QMessageBox.information)(self, IO.APP_TITLE, text)
        if errors:
            return False
        self.log(f"검사 통과 (경고 {len(warnings)}개).")
        if not warnings:
            QMessageBox.information(self, IO.APP_TITLE, "문제가 없습니다.")
        return True

    def do_generate(self, quiet=False):
        if self.busy:
            if not quiet:
                QMessageBox.information(self, IO.APP_TITLE, "빌드 중에는 프로젝트를 다시 생성할 수 없습니다.")
            return None
        errors, _ = BR.validate(self.project)
        if errors:
            self.do_validate()
            return None
        try:
            root = BR.generate(self.project, self.settings, log=self.log)
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여 준다
            self.log(f"[오류] 생성 실패: {e}")
            QMessageBox.critical(self, IO.APP_TITLE, f"생성 실패:\n{e}")
            return None
        if not quiet:
            QMessageBox.information(self, IO.APP_TITLE, f"프로젝트를 만들었습니다:\n{root}")
        return root

    def do_build(self, publish):
        if self.busy:
            QMessageBox.information(self, IO.APP_TITLE, "이미 빌드 중입니다.")
            return
        problem = BR.check_build_prereqs(self.settings, publish)
        if problem:
            QMessageBox.critical(self, IO.APP_TITLE, problem)
            return
        root = self.do_generate(quiet=True)
        if not root:
            return
        sts2_path = self.settings.get("sts2_path", "")
        mod_id = self.project["mod"]["id"]
        cmd = BR.build_command(publish, sts2_path)
        self.busy = True
        self.log(f"$ {' '.join(cmd)}   (폴더: {root})")

        def run():
            try:
                code = BR.run_build(cmd, root, self.log)
                if code == 0:
                    self.log(f"✔ {'게시' if publish else '빌드'} 성공! → {os.path.join(sts2_path, 'mods', mod_id)}")
                    if not publish:
                        self.log("  (그림·텍스트가 들어 있는 .pck는 ④ 게시에서 만들어집니다.)")
                else:
                    self.log(f"✘ 실패 (종료 코드 {code}). 위 로그의 error 줄을 확인하세요.")
            finally:
                self.busy = False

        threading.Thread(target=run, daemon=True).start()

    # ---- 파일 ----
    def confirm_discard(self):
        """저장하지 않은 변경이 있으면 묻는다. 계속해도 되면 True."""
        if not self.dirty:
            return True
        answer = QMessageBox.question(self, IO.APP_TITLE, "저장하지 않은 변경 사항이 있습니다. 저장할까요?",
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No |
                                      QMessageBox.StandardButton.Cancel)
        if answer == QMessageBox.StandardButton.Cancel:
            return False
        if answer == QMessageBox.StandardButton.Yes:
            return self.save()
        return True

    def new_project(self, confirm=True):
        if confirm and not self.confirm_discard():
            return
        self.project = M.default_project()
        self.project_path = ""
        self.dirty = False
        self.load_all()
        self.reset_history()
        self.status("새 프로젝트를 만들었습니다")

    def open_dialog(self):
        if not self.confirm_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, "프로젝트 열기", "", PROJECT_FILTER)
        if path:
            self.open_project(path)

    def open_project(self, path, quiet=False):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            project = M.normalize(loaded)
            project = IO._resolve_project_image_paths(project, os.path.dirname(os.path.abspath(path)))
        except LOAD_ERRORS as e:
            if quiet:
                self.status(f"[오류] 마지막 프로젝트를 열지 못했습니다 ({path}): {e}. 기본 프로젝트로 시작합니다.", 8000)
                self.settings["last_project"] = ""
                IO.save_settings(self.settings)
                self.new_project(confirm=False)
            else:
                QMessageBox.critical(self, IO.APP_TITLE, f"프로젝트를 열 수 없습니다:\n{e}")
            return False
        self.project = project
        self.project_path = path
        self.dirty = False
        self.settings["last_project"] = path
        if not IO.save_settings(self.settings):
            self.status("[경고] 앱 설정을 저장하지 못했습니다.", 8000)
        self.load_all()
        self.reset_history()
        self.status(f"열었습니다: {path}")
        return True

    def save(self):
        if not self.project_path:
            return self.save_as()
        try:
            IO._atomic_write_json(self.project_path, IO._project_data_for_save(self.project, self.project_path))
        except (OSError, TypeError, ValueError) as e:
            QMessageBox.critical(self, IO.APP_TITLE, f"저장 실패:\n{e}")
            return False
        self.dirty = False
        self.update_title()
        if self._snap_timer.isActive():
            self._flush_snapshot()
        self._saved_state = self.history.cur
        self.settings["last_project"] = self.project_path
        if not IO.save_settings(self.settings):
            self.status("[경고] 프로젝트는 저장했지만 앱 설정은 저장하지 못했습니다.", 8000)
        self.status(f"저장했습니다: {self.project_path}")
        return True

    def save_as(self):
        default = f"{self.project['mod']['id']}.sts2mod.json"
        path, _ = QFileDialog.getSaveFileName(self, "다른 이름으로 저장", default, SAVE_FILTER)
        if not path:
            return False
        old_path = self.project_path
        self.project_path = path
        if not self.save():
            self.project_path = old_path
            self.update_title()
            return False
        return True

    def show(self):
        super().show()
        # 보이기 전에 고른 탭은 배치가 끝난 뒤에야 남는다 (showEvent 안에서는 무시된다)
        page = getattr(self, "_select_on_show", None)
        if page is not None:
            self._select_on_show = None
            self.select(page)

    def showEvent(self, event):
        super().showEvent(event)
        if getattr(self, "_default_width_pending", False):
            self._default_width_pending = False
            # 독은 내용의 크기로 정해지므로, 보이기 시작한 뒤에 작업 영역 너비를 직접 정한다
            self.resizeDocks([self.dock_of(self.char_page)], [900], Qt.Orientation.Horizontal)

    def closeEvent(self, event):
        if self.confirm_discard():
            self.settings["dock_layout"] = self.layout_text()   # 탭 배치는 프로젝트가 아니라 앱 설정에 둔다
            IO.save_settings(self.settings)
            event.accept()
        else:
            event.ignore()


def _app_icon_path():
    """프로그램 아이콘(mod-maker-taskbar-icon.ico): 개발할 때는 이 파일 옆, 배포본에서는 실행 파일이 푸는 곳."""
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, "mod-maker-taskbar-icon.ico")


def _loading_splash(app):
    """실행할 때 보이는 로딩창: 그림(ui_icons/loading.png) 위에 제목과 '불러오는 중'. 창이 준비되면 닫는다 (main 에서)."""
    picture = QPixmap(os.path.join(_icon_dir(), "loading.png"))
    width, height = 600, 337
    canvas = QPixmap(width, height)
    canvas.fill(QColor(Q.C["stage"]))
    painter = QPainter(canvas)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    if not picture.isNull():
        scaled = picture.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                Qt.TransformationMode.SmoothTransformation)
        painter.drawPixmap((width - scaled.width()) // 2, (height - scaled.height()) // 2, scaled)
    painter.fillRect(QRect(0, height - 84, width, 84), QColor(20, 18, 15, 205))   # 글을 읽을 어두운 띠
    font = QFont(Q.FONT, 16)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("#fbfaf7"))
    painter.drawText(QRect(24, height - 76, width - 48, 36), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                     "슬더스2 모드 메이커")
    font.setPointSize(10)
    font.setBold(False)
    painter.setFont(font)
    painter.setPen(QColor("#e9e4da"))
    painter.drawText(QRect(24, height - 40, width - 48, 24), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                     "모드를 불러오는 중입니다…")
    right = int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    font.setPointSize(9)
    painter.setFont(font)
    painter.setPen(QColor("#e9e4da"))
    painter.drawText(QRect(width - 324, height - 64, 300, 22), right, f"패치 v{UP.VERSION}")
    painter.drawText(QRect(width - 324, height - 40, 300, 22), right, "슬레이 더 스파이어 갤러리 - 데이타")
    painter.end()
    splash = QSplashScreen(canvas, Qt.WindowType.WindowStaysOnTopHint)
    splash.show()
    app.processEvents()                              # 창을 만드는 동안에도 로딩창이 그려지게 한다
    return splash


def main():
    import feedback as FB
    import selftestqt
    app = QApplication.instance() or QApplication(sys.argv)
    FB.install_exception_hooks(IO.APP_DIR)
    scale = float(IO.load_settings().get("ui_scale", 1.0) or 1.0)
    Q.apply_theme(app, max(7, round(10 * scale)))
    report = selftestqt.report_path_from_args(sys.argv)
    if report is not None:                       # 배포본 점검: 창을 열지 않고 결과만 쓴다
        return selftestqt.run(report)
    if sys.platform == "win32":                      # 작업표시줄이 python 아이콘 대신 이 프로그램 아이콘을 쓰게 한다
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("StS2ModMaker")
        except (AttributeError, OSError):
            pass
    app.setWindowIcon(QIcon(_app_icon_path()))
    splash = _loading_splash(app)
    win = QtApp()
    win.show()
    splash.finish(win)                               # 창이 나타나면 로딩창을 닫는다
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

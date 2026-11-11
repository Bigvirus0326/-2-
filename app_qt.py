"""Qt 앱 껍데기: 메인 창, 메뉴, 설정, 프로젝트 열기·저장·되돌리기.

지금은 '모드 / 빌드' 탭만 올라가 있다. 나머지 탭은 3단계에서 붙인다.
검사·생성·빌드·게시 단계 버튼은 아직 Tk 앱(sts2_mod_maker.py)에서만 동작한다.
실행: python app_qt.py
"""
import json
import os
import sys
import threading

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (QApplication, QDockWidget, QFileDialog, QLabel, QMessageBox,
                               QPlainTextEdit)

import buildrun as BR
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


def _placeholder(title):
    message = (f"'{title}' 탭은 아직 Qt 앱으로 옮기지 않았습니다.\n"
               "이 탭은 Tk 앱(sts2_mod_maker.py)에서 사용하세요.")
    label = QLabel(message)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setWordWrap(True)
    return label


class QtApp(Q.DockWorkspace):
    log_line = Signal(str)   # 빌드 스레드에서 보낸 줄을 화면 스레드에서 받는다

    def __init__(self, settings=None, parent=None):
        super().__init__(parent)
        self.settings = settings if settings is not None else IO.load_settings()
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
        self.log_view.setMaximumBlockCount(3000)
        self.log_dock = QDockWidget("실행 기록", self)
        self.log_dock.setObjectName("실행 기록")
        self.log_dock.setWidget(self.log_view)
        self.addDockWidget(Qt.DockWidgetArea.BottomDockWidgetArea, self.log_dock)
        self.log_line.connect(self._append_log)

        actions = [self.do_validate, lambda: self.do_generate(), lambda: self.do_build(False),
                   lambda: self.do_build(True)]
        self.mod_page = ModTabQt(self.project["mod"], self.settings, actions=actions,
                                 on_settings_change=self._settings_changed, on_mod_change=self._mod_changed)
        page = Q.ScrollPage()
        page.set_content(self.mod_page)
        self.add_page(page, TAB_TITLES[0])
        for title in TAB_TITLES[1:]:
            self.add_page(_placeholder(title), title)

        self._build_menu()
        saved = self.settings.get("dock_layout", "")
        if not (saved and self.restore_layout_text(saved)):   # 실패하면 기본 배치(한 탭 묶음)를 쓴다
            self.select(page)   # 처음 열 때는 '모드 / 빌드' 탭이 보이게 (Tk 앱과 같다)
        self.resize(1100, 780)
        self.update_title()
        last = self.settings.get("last_project", "")
        if last and os.path.isfile(last):
            self.open_project(last, quiet=True)
        else:
            self.new_project(confirm=False)

    # ---- 메뉴 ----
    def _build_menu(self):
        def add(menu, text, slot, shortcut=None):
            action = QAction(text, self)
            if shortcut:
                action.setShortcut(QKeySequence(shortcut))
            action.triggered.connect(slot)
            menu.addAction(action)
            return action

        file_menu = self.menuBar().addMenu("파일")
        add(file_menu, "새로 만들기", lambda: self.new_project(), "Ctrl+N")
        add(file_menu, "열기…", self.open_dialog, "Ctrl+O")
        add(file_menu, "저장", self.save, "Ctrl+S")
        add(file_menu, "다른 이름으로 저장…", self.save_as, "Ctrl+Shift+S")
        file_menu.addSeparator()
        add(file_menu, "종료", self.close, "Ctrl+Q")

        edit_menu = self.menuBar().addMenu("편집")
        self.undo_action = add(edit_menu, "실행 취소", self.undo, "Ctrl+Z")
        self.redo_action = add(edit_menu, "다시 실행", self.redo, "Ctrl+Y")
        self._update_undo_actions()

        view_menu = self.menuBar().addMenu("보기")
        for action in self.view_menu_actions():
            view_menu.addAction(action)
        view_menu.addSeparator()
        add(view_menu, "떨어진 탭 되돌리기", self.dock_all)
        add(view_menu, "배치 초기화", self.reset_layout)

    def _update_undo_actions(self):
        self.undo_action.setEnabled(self.history.can_undo() or self._snap_timer.isActive())
        self.redo_action.setEnabled(self.history.can_redo())

    # ---- 상태 ----
    def status(self, text, ms=4000):
        self.statusBar().showMessage(text, ms)

    def update_title(self):
        name = os.path.basename(self.project_path) if self.project_path else "새 프로젝트"
        self.setWindowTitle(f"{'*' if self.dirty else ''}{name} - {IO.APP_TITLE} v{UP.VERSION}")

    def load_all(self):
        self.mod_page.load(self.project["mod"])
        self.update_title()

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

    def closeEvent(self, event):
        if self.confirm_discard():
            self.settings["dock_layout"] = self.layout_text()   # 탭 배치는 프로젝트가 아니라 앱 설정에 둔다
            IO.save_settings(self.settings)
            event.accept()
        else:
            event.ignore()


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    Q.apply_theme(app)
    win = QtApp()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

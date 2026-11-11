import json
import os
import sys
import tempfile
import time
from unittest import TestCase, skipUnless
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QEvent
    from PySide6.QtGui import QCloseEvent
    from PySide6.QtWidgets import QApplication, QMessageBox, QTabBar
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import app_qt as A
    import projectio as IO


def _pump(seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        _app.processEvents()
        time.sleep(0.01)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class AppQtTests(TestCase):
    def setUp(self):
        # 설정 파일을 건드리지 않는다
        self._patches = [patch.object(IO, "save_settings", return_value=True)]
        for p in self._patches:
            p.start()
        self.tmp = tempfile.mkdtemp()
        self.app = A.QtApp(settings={"last_project": "", "sts2_path": "", "out_dir": self.tmp, "godot_path": ""})
        self.app.show()

    def tearDown(self):
        self.app._snap_timer.stop()
        self.app.dirty = False
        self.app.close()
        for p in self._patches:
            p.stop()

    def test_opens_on_the_first_tab_with_all_ten_tabs(self):
        bars = [b for b in self.app.findChildren(QTabBar) if b.count() > 1]
        self.assertEqual(len(bars), 1)
        self.assertEqual(bars[0].count(), len(A.TAB_TITLES))
        self.assertEqual(bars[0].tabText(bars[0].currentIndex()), A.TAB_TITLES[0])

    def test_starts_with_a_clean_new_project(self):
        self.assertEqual(self.app.project_path, "")
        self.assertFalse(self.app.dirty)
        self.assertIn("새 프로젝트", self.app.windowTitle())
        self.assertNotIn("*", self.app.windowTitle())

    def test_edit_marks_dirty_and_undo_returns_to_saved_state(self):
        before = self.app.mod_page._inputs["name"].text()
        self.app.mod_page._inputs["name"].setText("바뀐 이름")
        self.assertTrue(self.app.dirty)
        self.assertTrue(self.app.windowTitle().startswith("*"))
        _pump(0.7)                      # 입력이 멈추면 한 단계로 기록
        self.assertTrue(self.app.history.can_undo())
        self.app.undo()
        self.assertEqual(self.app.project["mod"]["name"], before)
        self.assertEqual(self.app.mod_page._inputs["name"].text(), before)
        self.assertFalse(self.app.dirty)

    def test_save_as_then_open_gives_the_same_project(self):
        self.app.mod_page._inputs["id"].setText("TestMod")
        path = os.path.join(self.tmp, "TestMod.sts2mod.json")
        with patch.object(A.QFileDialog, "getSaveFileName", return_value=(path, "")):
            self.assertTrue(self.app.save_as())
        self.assertTrue(os.path.isfile(path))
        self.assertFalse(self.app.dirty)
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["mod"]["id"], "TestMod")
        other = A.QtApp(settings={"last_project": "", "sts2_path": "", "out_dir": self.tmp, "godot_path": ""})
        try:
            self.assertTrue(other.open_project(path))
            self.assertEqual(other.project["mod"]["id"], "TestMod")
            self.assertEqual(other.mod_page._inputs["id"].text(), "TestMod")
        finally:
            other._snap_timer.stop()
            other.dirty = False
            other.close()

    def test_broken_project_file_does_not_crash_when_quiet(self):
        bad = os.path.join(self.tmp, "broken.sts2mod.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{ 망가진 파일")
        self.assertFalse(self.app.open_project(bad, quiet=True))
        self.assertEqual(self.app.project_path, "")

    def test_cancel_in_discard_prompt_keeps_the_window_open(self):
        self.app.mod_page._inputs["name"].setText("저장 안 함")
        event = QCloseEvent()
        with patch.object(A.QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel):
            self.app.closeEvent(event)
        self.assertFalse(event.isAccepted())

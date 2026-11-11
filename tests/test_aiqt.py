import os
import sys
import tempfile
from unittest import TestCase, skipUnless
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import app_qt as A
    import aiqt as AQ
    import projectio as IO


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class AIWorkflowQtTests(TestCase):
    def setUp(self):
        self._patches = [patch.object(IO, "save_settings", return_value=True), patch.object(AQ, "_info"),
                         patch.object(AQ, "_warn")]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        self.app = A.QtApp(settings={"last_project": "", "sts2_path": "", "out_dir": tempfile.mkdtemp(),
                                     "godot_path": ""})
        self.addCleanup(self._close)
        self.dialog = AQ.AIWorkflowQt(self.app, paste=False)
        self.addCleanup(self.dialog.close)

    def _close(self):
        self.app._snap_timer.stop()
        self.app.dirty = False
        self.app.deleteLater()

    def test_the_guide_contains_the_request_text(self):
        self.dialog.guide_page.req.setPlainText("불씨 카드 하나")
        self.assertIn("불씨 카드 하나", self.dialog.guide_page.prompt())

    def test_copying_the_guide_puts_it_on_the_clipboard(self):
        self.dialog.guide_page.copy()
        self.assertEqual(AQ.QApplication.clipboard().text(), self.dialog.guide_page.prompt())
        self.assertIn("복사했습니다", self.dialog.guide_page.status.text())

    def test_unreadable_answer_blocks_saving(self):
        page = self.dialog.paste_page
        page.src.setPlainText("이건 JSON 이 아닙니다")
        page.read()
        self.assertFalse(page.ok_btn.isEnabled())
        page.commit()                                       # 아무 일도 없어야 한다
        self.assertFalse(self.app.dirty)

    def test_paste_mode_opens_on_the_second_page(self):
        paste = AQ.AIWorkflowQt(self.app, paste=True)
        self.addCleanup(paste.close)
        self.assertIs(paste.tabs.currentWidget(), paste.paste_page)

    def test_going_to_a_card_selects_its_row(self):
        card_id = self.app.project["cards"][1]["id"]
        self.app.goto_any("card", card_id)
        tab = self.app.item_pages[0]
        self.assertEqual(tab.items[tab.cur]["id"], card_id)

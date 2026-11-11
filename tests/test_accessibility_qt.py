"""접근성 (말풍선 설명 · 도구 막대 · 포커스 표시). Tk 앱의 UX.field_help / UX.tip 과 같은 동작을 Qt 에서도 한다."""
import os
import sys
import tempfile
from unittest import TestCase, skipUnless
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QLabel, QToolBar
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

import fieldhelp as FH

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import app_qt as A
    import itemtabqt as IT
    import projectio as IO
    import modgen as M


class FieldHelpTableTests(TestCase):
    def test_the_card_cost_has_its_explanation(self):
        self.assertIn("에너지", FH.field_help("card", "cost"))

    def test_a_kind_specific_entry_wins_and_unknown_keys_are_empty(self):
        self.assertEqual(FH.field_help("card", "nope"), "")
        self.assertTrue(FH.field_help("power", "stack").strip())


@skipUnless(HAVE_QT, "PySide6 not installed")
class FieldLabelTests(TestCase):
    def test_a_card_field_with_help_shows_the_marker_and_a_tooltip(self):
        tab = IT.CardTabQt(M.default_project())
        labels = [w for w in tab.findChildren(QLabel) if w.text().startswith("비용")]
        self.assertTrue(labels, "비용 칸의 이름이 있어야 한다")
        self.assertIn("ⓘ", labels[0].text())
        self.assertIn("에너지", labels[0].toolTip())


@skipUnless(HAVE_QT, "PySide6 not installed")
class ToolBarTests(TestCase):
    def setUp(self):
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

    def test_the_main_buttons_are_on_a_toolbar_with_tooltips(self):
        bar = self.app.findChild(QToolBar, "main_toolbar")
        self.assertIsNotNone(bar)
        texts = [a.text() for a in bar.actions() if a.text()]
        self.assertIn("저장", texts)
        self.assertIn("④ 게시 (dll+pck)", texts)
        save = next(a for a in bar.actions() if a.text() == "저장")
        self.assertIn("Ctrl+S", save.toolTip())

    def test_every_toolbar_button_has_its_picture(self):
        bar = self.app.findChild(QToolBar, "main_toolbar")
        buttons = [a for a in bar.actions() if a.text()]
        self.assertEqual(len(buttons), 10)
        self.assertTrue(all(not a.icon().isNull() for a in buttons))

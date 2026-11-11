import os
import sys
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import modgen as M
    import dialogsqt as D


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ArchitectDialogQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.ch = self.project["character"]

    def test_default_text_is_written_as_empty_so_the_default_stays(self):
        d = D.ArchitectDialogQt(None, self.project, self.ch)
        self.addCleanup(d.close)
        d.ok()
        self.assertEqual(self.ch["architect_ko"], "")
        self.assertEqual(self.ch["architect_en"], "")

    def test_custom_text_is_saved_per_language(self):
        d = D.ArchitectDialogQt(None, self.project, self.ch)
        self.addCleanup(d.close)
        d.texts["ko"].setPlainText("아키텍트: 잘했다.\n나: 고마워.")
        d.ok()
        self.assertIn("잘했다", self.ch["architect_ko"])

    def test_status_says_when_no_line_is_readable(self):
        d = D.ArchitectDialogQt(None, self.project, self.ch)
        self.addCleanup(d.close)
        d.texts["en"].setPlainText("")
        self.assertIn("읽을 수 있는 줄이 없습니다", d.status["en"].text())

    def test_reset_puts_the_default_back_for_the_current_tab(self):
        d = D.ArchitectDialogQt(None, self.project, self.ch)
        self.addCleanup(d.close)
        d.texts["ko"].setPlainText("바꾼 대사")
        d.tabs.setCurrentIndex(0)
        d.reset()
        self.assertNotIn("바꾼 대사", d.texts["ko"].toPlainText())


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class RawVarDialogQtTests(TestCase):
    def test_numbers_come_back_as_int_when_whole(self):
        d = D.RawVarDialogQt(None, {"name": "Damage", "type": "decimal", "value": 6, "upgrade": 3})
        self.addCleanup(d.close)
        d.value.setText("7.0")
        d.up.setText("2")
        d.ok()
        self.assertEqual(d.result, (7, 2))

    def test_a_fraction_stays_a_float(self):
        d = D.RawVarDialogQt(None, {"name": "Damage", "type": "decimal", "value": 6, "upgrade": 0})
        self.addCleanup(d.close)
        d.value.setText("2.5")
        d.ok()
        self.assertEqual(d.result, (2.5, 0))

    def test_not_a_number_keeps_the_dialog_open(self):
        d = D.RawVarDialogQt(None, {"name": "Damage", "type": "decimal", "value": 6, "upgrade": 0})
        self.addCleanup(d.close)
        d.value.setText("많이")
        from unittest import mock
        with mock.patch.object(D, "_warn") as warn:
            d.ok()
        warn.assert_called_once()
        self.assertIsNone(d.result)

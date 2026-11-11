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
    import modtab_qt as MQ


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ModTabQtTests(TestCase):
    def test_missing_game_path_is_reported_as_bad(self):
        states = dict((text.split()[0], state) for state, text in MQ.check_lines({"sts2_path": ""}))
        self.assertEqual(states["슬더스2"], "bad")
        self.assertEqual(states["MegaDot"], "warn")

    def test_editing_fields_writes_back_to_the_dicts(self):
        mod, settings = {"id": "A"}, {"sts2_path": ""}
        tab = MQ.ModTabQt(mod, settings)
        tab._inputs["name"].setText("새 이름")
        tab._inputs["env:sts2_path"].setText(" C:/game ")
        self.assertEqual(mod["name"], "새 이름")
        self.assertEqual(settings["sts2_path"], "C:/game")
        tab.close()

    def test_loading_another_mod_does_not_write_back(self):
        first, second = {"id": "A"}, {"id": "B", "name": "비"}
        tab = MQ.ModTabQt(first, {})
        tab.load(second)
        self.assertEqual(first, {"id": "A"})
        self.assertEqual(tab._inputs["id"].text(), "B")
        tab.close()

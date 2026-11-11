import os
import sys
from unittest import TestCase, skipUnless, mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import clonepanelqt as CP
    import itemtabqt as IT
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ClonePanelTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.card["clone"] = {"orig_class": "Strike", "mod": "other", "pool": "mine", "body": "class X {}"}
        self.card["raw_vars"] = [{"name": "Damage", "type": "decimal", "value": 6, "upgrade": 3}]
        self.tab = IT.CardTabQt(self.project)
        self.addCleanup(self.tab.close)
        self.panel = self.tab.clone

    def test_a_copied_card_shows_its_original_values(self):
        self.tab.refresh_list(0)
        self.assertFalse(self.panel.isHidden())
        self.assertEqual(self.panel.table.rowCount(), 1)
        self.assertEqual(self.panel.table.item(0, 0).text(), "Damage")

    def test_an_ordinary_card_without_original_values_hides_the_panel(self):
        self.project["cards"][1].pop("clone", None)
        self.project["cards"][1].pop("raw_vars", None)
        self.tab.refresh_list(1)
        self.assertTrue(self.panel.isHidden())

    def test_editing_a_raw_value_writes_it_back(self):
        self.tab.refresh_list(0)
        self.panel.table.setCurrentCell(0, 0)
        fake = mock.Mock()
        fake.exec.return_value = 1
        fake.result = (9, 4)
        with mock.patch.object(CP, "RawVarDialogQt", return_value=fake):
            self.panel.edit()
        self.assertEqual(self.card["raw_vars"][0]["value"], 9)
        self.assertEqual(self.card["raw_vars"][0]["upgrade"], 4)

    def test_choosing_the_other_pool_clears_the_card_character(self):
        self.card["pool_character"] = "X"
        self.tab.refresh_list(0)
        self.panel.pool.setCurrentIndex(self.panel.pool.findData("theirs"))
        self.assertEqual(self.card["clone"]["pool"], "theirs")
        self.assertEqual(self.card["pool_character"], "")

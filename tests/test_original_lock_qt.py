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
    import cardlibqt as CL
    import itemtabqt as IT
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class OriginalCardLockTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.card["clone"] = {"orig_class": "Strike", "mod": "", "pool": "mine", "game_original": True}
        self.tab = IT.CardTabQt(self.project)
        self.addCleanup(self.tab.close)

    def test_an_original_card_is_read_only_in_the_editor(self):
        self.tab.refresh_list(0)
        self.assertFalse(self.tab.form.isEnabled())
        self.assertIn("읽기 전용", self.tab.editor_title.text())

    def test_a_normal_card_stays_editable(self):
        self.tab.refresh_list(1)
        self.assertTrue(self.tab.form.isEnabled())

    def test_bulk_edit_skips_original_cards(self):
        self.tab.refresh_list(0)
        self.tab.listing.item(0).setSelected(True)
        with mock.patch.object(IT, "BulkEditDialogQt") as dialog:
            self.tab.bulk_edit()
        dialog.assert_not_called()

    def test_duplicating_an_original_card_gives_an_editable_copy(self):
        self.tab.refresh_list(0)
        self.tab.duplicate()
        copy = self.project["cards"][1]
        self.assertFalse(copy["clone"].get("game_original"))
        self.assertTrue(self.card["clone"].get("game_original"))
        self.tab.refresh_list(1)
        self.assertTrue(self.tab.form.isEnabled())

    def test_the_library_refuses_to_overwrite_an_original_card(self):
        with mock.patch.object(CL, "_info") as info, mock.patch.object(CL, "_ask", return_value=True):
            lib = mock.Mock()
            lib.card_page = self.tab
            lib.kind = "cards"
            lib.source = mock.Mock(return_value={"project": {"cards": []}, "kind": "cards"})
            lib.selection = mock.Mock(return_value=self.project["cards"][1])
            lib.apply_keyword = mock.Mock()
            self.tab.refresh_list(0)
            self.assertFalse(CL.CardLibraryQt.apply_selected(lib, self.project["cards"][1], {"project": {"cards": []}}))
            info.assert_called_once()
            lib.apply_keyword.assert_not_called()

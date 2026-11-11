import json
import os
import sys
import tempfile
from unittest import TestCase, skipUnless, mock
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
    import cardlibqt as CL
    import modgen as M
    import projectio as IO


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class CardLibraryQtTests(TestCase):
    def setUp(self):
        self._patches = [patch.object(IO, "save_settings", return_value=True),
                         patch.object(CL, "_warn"), patch.object(CL, "_info")]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.mkdtemp()
        self.app = A.QtApp(settings={"last_project": "", "sts2_path": "", "out_dir": self.tmp, "godot_path": ""})
        self.addCleanup(self._close)
        self.app.show()
        # 참고할 프로젝트 파일 하나 (기본 프로젝트를 저장한 것)
        self.source_path = os.path.join(self.tmp, "reference.sts2mod.json")
        reference = M.default_project()
        reference["cards"][0]["name_ko"] = "참고 카드"
        with open(self.source_path, "w", encoding="utf-8") as f:
            json.dump(reference, f, ensure_ascii=False)

    def _close(self):
        self.app._snap_timer.stop()
        self.app.dirty = False
        self.app.close = lambda: True
        self.app.deleteLater()

    def _library(self):
        self.app.open_card_library()
        lib = self.app._card_library
        self.addCleanup(lib.close)
        return lib

    def _open_reference(self, lib):
        with patch.object(CL, "QFileDialog") as dialog:
            dialog.getOpenFileNames.return_value = ([self.source_path], "")
            lib.open_projects()

    def test_the_card_tab_button_opens_the_library(self):
        self.assertIsNotNone(self.app.item_pages[0].library_fn)
        self.app.item_pages[0].library_fn()
        self.assertIsNotNone(self.app._card_library)
        self.addCleanup(self.app._card_library.close)

    def test_opening_a_project_file_lists_its_cards(self):
        lib = self._library()
        self._open_reference(lib)
        self.assertEqual(lib.groups.count(), 1)
        self.assertGreater(lib.cards.count(), 0)
        self.assertIn("참고 카드", lib.cards.item(0).text())

    def test_adding_a_card_from_a_project_gives_it_a_new_id(self):
        lib = self._library()
        self._open_reference(lib)
        before = len(self.app.project["cards"])
        lib.cards.setCurrentRow(0)
        lib.add()
        cards = self.app.project["cards"]
        self.assertEqual(len(cards), before + 1)
        self.assertEqual(len({c["id"] for c in cards}), len(cards))
        self.assertTrue(self.app.dirty)

    def test_applying_overwrites_the_current_card_but_keeps_its_id(self):
        lib = self._library()
        self._open_reference(lib)
        card_tab = self.app.item_pages[0]
        card_tab.refresh_list(0)
        old_id = card_tab.items[0]["id"]
        lib.cards.setCurrentRow(0)
        with patch.object(CL, "_ask", return_value=True):
            self.assertTrue(lib.apply_selected())
        self.assertEqual(self.app.project["cards"][0]["id"], old_id)
        self.assertEqual(self.app.project["cards"][0]["name_ko"], "참고 카드")

    def test_applying_is_refused_when_the_user_says_no(self):
        lib = self._library()
        self._open_reference(lib)
        self.app.item_pages[0].refresh_list(0)
        lib.cards.setCurrentRow(0)
        before = self.app.project["cards"][0]["name_ko"]
        with patch.object(CL, "_ask", return_value=False):
            self.assertFalse(lib.apply_selected())
        self.assertEqual(self.app.project["cards"][0]["name_ko"], before)

    def test_game_cards_are_not_applied_without_the_game_files(self):
        lib = self._library()
        self.assertEqual(lib.source(), {})
        self.assertFalse(lib.apply_btn.isEnabled())

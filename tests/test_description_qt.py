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
    import modgen as M
    import descriptionqt as D
    import itemtabqt as IT


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class DescriptionEditQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.ed = D.DescriptionEditQt(lambda: (self.project, self.card, "ko", False))
        self.addCleanup(self.ed.close)

    def test_plain_text_round_trips(self):
        self.ed.set_source("피해를 줍니다.")
        self.assertEqual(self.ed.source(), "피해를 줍니다.")

    def test_bold_and_colours_round_trip(self):
        for src in ("[b]굵게[/b] 피해", "[color=#ff0000]빨강[/color] 끝", "[gold]금[/gold] 과 [red]빨강[/red]"):
            self.ed.set_source(src)
            self.assertEqual(self.ed.source(), src)

    def test_a_reference_token_is_kept_as_a_chip(self):
        src = "앞 {IfUpgraded:show:5|3} 뒤"
        self.ed.set_source(src)
        self.assertEqual(self.ed.source(), src)

    def test_game_colour_is_applied_to_the_selection_and_saved(self):
        self.ed.set_source("abc")
        self.ed.selectAll()
        span = self.ed.selection_range()
        self.ed.apply_game_color(*span, "gold")
        self.assertEqual(self.ed.source(), "[gold]abc[/gold]")

    def test_reset_colour_removes_the_tag_from_the_saved_text(self):
        self.ed.set_source("[red]abc[/red]")
        self.ed.selectAll()
        self.ed.reset_color(*self.ed.selection_range())
        self.assertEqual(self.ed.source(), "abc")

    def test_unknown_game_colour_is_refused(self):
        self.ed.set_source("abc")
        with self.assertRaises(ValueError):
            self.ed.apply_game_color(0, 1, "nope")

    def test_inserting_a_token_puts_it_into_the_saved_text(self):
        self.ed.set_source("앞 ")
        from PySide6.QtGui import QTextCursor
        self.ed.moveCursor(QTextCursor.MoveOperation.End)
        self.ed.insert_token("{IfUpgraded:show:9|4}")
        self.assertEqual(self.ed.source(), "앞 {IfUpgraded:show:9|4}")

    def test_edits_emit_text_changed(self):
        seen = []
        self.ed.textChanged.connect(lambda: seen.append(1))
        self.ed.set_source("x")
        self.assertTrue(seen)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ItemRichFieldTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.tab = IT.CardTabQt(self.project)
        self.addCleanup(self.tab.close)
        self.tab.refresh_list(0)

    def test_description_editor_writes_the_source_into_the_card(self):
        editor = self.tab._fields["desc_ko"][1]
        editor.set_source("[b]강한[/b] 타격")
        self.tab.write_item()
        self.assertEqual(self.project["cards"][self.tab.cur]["desc_ko"], "[b]강한[/b] 타격")

    def test_selecting_a_card_loads_its_description_into_the_editor(self):
        self.project["cards"][0]["desc_en"] = "[i]Hit[/i] hard"
        self.tab.refresh_list(0)
        self.assertEqual(self.tab._fields["desc_en"][1].source(), "[i]Hit[/i] hard")

    def test_number_dialog_result_is_inserted(self):
        editor = self.tab._fields["desc_ko"][1]
        editor.set_source("")
        fake = mock.Mock()
        fake.exec.return_value = 1
        fake.token = "{IfUpgraded:show:2|1}"
        with mock.patch.object(IT, "InsertNumberDialogQt", return_value=fake):
            self.tab._insert_number(editor)
        self.assertEqual(editor.source(), "{IfUpgraded:show:2|1}")

    def test_reference_dialog_cancel_inserts_nothing(self):
        editor = self.tab._fields["desc_ko"][1]
        editor.set_source("그대로")
        fake = mock.Mock()
        fake.exec.return_value = 0
        fake.token = None
        with mock.patch.object(IT, "InsertReferenceDialogQt", return_value=fake):
            self.tab._insert_reference(editor)
        self.assertEqual(editor.source(), "그대로")

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
    import artguide as AG
    import artuiqt as AQ
    import app_qt as A
    import projectio as IO
    import modgen as M


def _png(path, size=(40, 40)):
    from PIL import Image
    Image.new("RGBA", size, (200, 80, 60, 255)).save(path)
    return path


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ArtGuideDialogQtTests(TestCase):
    def setUp(self):
        self._patches = [patch.object(IO, "save_settings", return_value=True), patch.object(AQ, "_info")]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.mkdtemp()
        self.app = A.QtApp(settings={"last_project": "", "sts2_path": "", "out_dir": self.tmp, "godot_path": "",
                                     "art_auto_copy": False})
        self.addCleanup(self._close)
        self.dialog = AQ.ArtGuideDialogQt(self.app, self.app)
        self.addCleanup(self.dialog.close)

    def _close(self):
        self.app._snap_timer.stop()
        self.app.dirty = False
        self.app.deleteLater()

    def test_the_guide_text_is_filled_in(self):
        self.assertIn("그림", self.dialog.text.toPlainText())
        self.assertIn("그림", self.dialog.count.text())

    def test_unticking_a_group_changes_the_count_and_is_saved(self):
        first = self.dialog.groups[AG.GROUPS[0][0]]
        before = len(self.dialog.chosen())
        first.setChecked(not first.isChecked())
        self.assertNotEqual(len(self.dialog.chosen()), before)
        self.assertIn("art_guide", self.app.project)

    def test_style_text_is_saved_to_the_project(self):
        self.dialog.style.setPlainText("수채화 느낌")
        self.assertEqual(self.app.project["art_style"], "수채화 느낌")

    def test_copy_puts_the_guide_on_the_clipboard(self):
        self.dialog.copy(quiet=True)
        self.assertIn("그림", AQ.QApplication.clipboard().text())
        self.assertIn("설명서를 복사했습니다", self.dialog.copied.text())

    def test_adding_a_reference_picture_lists_it(self):
        ref = _png(os.path.join(self.tmp, "ref.png"))
        with patch.object(AQ, "QFileDialog") as dialog:
            dialog.getOpenFileNames.return_value = ([ref], "")
            self.dialog.add_refs()
        self.assertEqual(self.app.project["art_style_refs"], [ref])
        self.assertEqual(len(self.dialog.refs()), 1)

    def test_removing_a_reference_picture(self):
        ref = _png(os.path.join(self.tmp, "ref.png"))
        self.app.project["art_style_refs"] = [ref]
        self.dialog.remove_ref(ref)
        self.assertEqual(self.dialog.refs(), [])


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ArtApplyDialogQtTests(TestCase):
    def setUp(self):
        self._patches = [patch.object(IO, "save_settings", return_value=True), patch.object(AQ, "_info"),
                         patch.object(AQ, "_warn")]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.mkdtemp()
        self.app = A.QtApp(settings={"last_project": "", "sts2_path": "", "out_dir": self.tmp, "godot_path": ""})
        self.addCleanup(self._close)
        self.dialog = AQ.ArtApplyDialogQt(self.app, parent=self.app)
        self.addCleanup(self.dialog.close)

    def _close(self):
        self.app._snap_timer.stop()
        self.app.dirty = False
        self.app.deleteLater()

    def test_slots_are_listed_one_per_row(self):
        self.assertEqual(self.dialog.table.rowCount(), len(self.dialog.slot_list))

    def test_files_are_matched_the_same_way_as_the_engine_does(self):
        slot = next(s for s in self.dialog.slot_list if s["kind"] == "card")
        path = _png(os.path.join(self.tmp, f"card_{slot['key'].split('_', 1)[-1]}.png"))
        self.dialog.load_files([path])
        self.assertEqual(self.dialog.assign, AG.match_files(self.dialog.slot_list, [path]))

    def test_clearing_a_slot_drops_its_file(self):
        slot = self.dialog.slot_list[0]
        self.dialog.assign[slot["key"]] = _png(os.path.join(self.tmp, "x.png"))
        self.dialog.table.selectRow(0)
        self.dialog.clear_one()
        self.assertNotIn(slot["key"], self.dialog.assign)

    def test_applying_with_nothing_chosen_only_says_so(self):
        self.dialog.assign = {}
        self.dialog.do_apply()
        AQ._info.assert_called_once()

    def test_applying_calls_the_engine_and_reloads_the_project(self):
        slot = self.dialog.slot_list[0]
        self.dialog.assign = {slot["key"]: _png(os.path.join(self.tmp, "a.png"))}
        with patch.object(AQ, "AG") as ag, patch.object(AQ, "_ask", return_value=True):
            ag.out_dir_for.return_value = self.tmp
            ag.apply.return_value = [slot["key"]]
            ag.SPECS = AG.SPECS
            with patch.object(self.app, "load_all") as load:
                self.dialog.do_apply()
        load.assert_called_once()

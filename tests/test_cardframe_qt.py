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
    import cardframe as CF
    import cardframeqt as CQ
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class FrameStyleDialogQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.changes = 0
        self.dialog = CQ.FrameStyleDialogQt(None, self.project, None, on_change=self._count)
        self.addCleanup(self.dialog.close)

    def _count(self):
        self.changes += 1

    def test_add_creates_a_style_and_selects_it(self):
        before = len(CF.styles(self.project))
        self.dialog.add()
        self.assertEqual(len(CF.styles(self.project)), before + 1)
        self.assertEqual(self.dialog.cur, before)
        self.assertGreater(self.changes, 0)

    def test_name_and_mode_are_written_into_the_style(self):
        self.dialog.add()
        self.dialog.name.setText("내 테두리")
        self.dialog._set_mode("frame", "image")
        st = CF.styles(self.project)[self.dialog.cur]
        self.assertEqual(st["name"], "내 테두리")
        self.assertEqual(st["frame"]["mode"], "image")

    def test_mode_shows_only_the_matching_panel(self):
        self.dialog.add()
        self.dialog._set_mode("frame", "color")
        self.assertFalse(self.dialog.ui["frame"]["color_frame"].isHidden())
        self.assertTrue(self.dialog.ui["frame"]["image_frame"].isHidden())
        self.dialog._set_mode("frame", "image")
        self.assertTrue(self.dialog.ui["frame"]["color_frame"].isHidden())
        self.assertFalse(self.dialog.ui["frame"]["image_frame"].isHidden())

    def test_typing_a_color_fills_the_shader_values(self):
        self.dialog.add()
        self.dialog.ui["frame"]["color"].setText("#3a6fb0")
        h, s, v = CF.hsv_for("#3a6fb0", "frame", self.dialog._base["frame"])
        got = [spin.value() for spin in self.dialog.ui["frame"]["hsv"]]
        self.assertAlmostEqual(got[0], h, places=3)
        self.assertAlmostEqual(got[1], s, places=3)
        self.assertAlmostEqual(got[2], v, places=3)

    def test_duplicate_gives_a_new_id(self):
        self.dialog.add()
        first = CF.styles(self.project)[self.dialog.cur]["id"]
        self.dialog.duplicate()
        ids = [s["id"] for s in CF.styles(self.project)]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn(first, ids)

    def test_delete_is_refused_when_the_user_says_no(self):
        self.dialog.add()
        before = len(CF.styles(self.project))
        with mock.patch.object(CQ, "_ask", return_value=False):
            self.dialog.delete()
        self.assertEqual(len(CF.styles(self.project)), before)
        with mock.patch.object(CQ, "_ask", return_value=True):
            self.dialog.delete()
        self.assertEqual(len(CF.styles(self.project)), before - 1)

    def test_preview_says_it_needs_the_game_files_when_there_are_none(self):
        self.dialog.add()
        self.dialog.draw()
        self.assertIn("게임 파일", self.dialog.preview_labels[0].text())

    def test_bright_frame_colour_gets_a_warning(self):
        self.dialog.add()
        self.dialog._set_mode("frame", "color")
        self.dialog.ui["frame"]["hsv"][2].setValue(2.0)
        self.assertIn("밝아", self.dialog.warn.text())

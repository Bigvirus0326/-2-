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
    import gameviewqt as GV
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class GameViewsTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.views = GV.GameViews(lambda: None, lambda: self.project)
        self.addCleanup(self.views.deleteLater)

    def test_switching_to_simple_tells_every_picture_to_redraw(self):
        seen = []
        self.views.mode = "game"
        self.views.changed.connect(lambda: seen.append(self.views.mode))
        self.views.set_mode("simple")
        self.assertEqual(seen, ["simple"])
        self.assertFalse(self.views.available())

    def test_the_stack_count_only_signals_when_it_changes(self):
        seen = []
        self.views.changed.connect(lambda: seen.append(self.views.stacks))
        self.views.set_stacks(5)
        self.views.set_stacks(5)
        self.assertEqual(seen, [5])

    def test_a_missing_game_folder_gives_a_reason_instead_of_a_picture(self):
        if GV.ingame is None:
            self.skipTest("Pillow 가 없어 게임 화면 자체를 쓸 수 없습니다")
        img, err = self.views.image("card", self.project["cards"][0], "ko", False, 3)
        self.assertIsNone(img)
        self.assertTrue(err)

    def test_without_pillow_the_game_picture_is_refused_with_a_reason(self):
        with mock.patch.object(GV, "ingame", None):
            img, err = self.views.image("card", self.project["cards"][0], "ko", False, 3)
        self.assertIsNone(img)
        self.assertIn("Pillow", err)

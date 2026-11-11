"""블록 편집: 즐겨찾기 ☆/★ 단추 (파일에 쓰지 않도록 저장 함수를 가짜로 바꾼다)."""
import os
import sys
from unittest import TestCase, mock, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QToolButton
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import blockqt as BQ
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class FavoriteStarTests(TestCase):
    def setUp(self):
        self.saved = []
        self.patch = mock.patch.object(BQ.blocklibqt, "load_favorites", return_value=[])
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.save_patch = mock.patch.object(BQ.blocklibqt, "save_favorites",
                                            side_effect=lambda order: self.saved.append(list(order)) or list(order))
        self.save_patch.start()
        self.addCleanup(self.save_patch.stop)
        self.dialog = BQ.BlockEditorQt(None, M.default_project(), "card", M.default_project()["cards"][0], [])
        self.addCleanup(self.dialog.close)

    def test_every_block_has_a_star_and_the_favorites_section_is_shown_first(self):
        self.assertEqual(self.dialog.palette.topLevelItem(0).text(0), "★ 즐겨찾기")
        self.assertGreater(len(self.dialog.palette.findChildren(QToolButton)), 20)

    def test_pressing_a_star_adds_the_block_to_the_favorites(self):
        self.dialog._toggle_favorite("damage")
        self.assertEqual(self.saved[-1], [BQ.B.compact_op("damage")])
        head = self.dialog.palette.topLevelItem(0)
        self.assertEqual(head.childCount(), 1)

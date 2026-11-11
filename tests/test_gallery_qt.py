import os
import sys
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QPoint
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import gallery_qt as G

PROJECT = {"cards": [{"id": "A"}, {"id": "B"}, {"id": "C"}], "relics": [{"id": "R"}],
           "potions": [], "powers": [{"id": "P"}]}


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class GalleryQtTests(TestCase):
    def setUp(self):
        self.g = G.GalleryQt(PROJECT)
        self.g.resize(900, 700)
        self.g.show()
        _app.processEvents()

    def tearDown(self):
        self.g.close()

    def test_all_filter_shows_every_section(self):
        self.g.set_filter("all")
        tiles, titles, _h, _w = self.g.compute(900)
        self.assertEqual([k for _r, k, _i, _it in tiles], ["card"] * 3 + ["relic", "power"])
        self.assertIn("(없음)", [t for _x, _y, t in titles])   # 물약은 비어 있다

    def test_filter_limits_tiles_to_one_kind(self):
        self.g.set_filter("card")
        tiles, _t, _h, _w = self.g.compute(900)
        self.assertEqual({k for _r, k, _i, _it in tiles}, {"card"})

    def test_size_changes_tile_width(self):
        self.g.set_size("small")
        small = self.g.compute(900)[0][0][0].width()
        self.g.set_size("large")
        large = self.g.compute(900)[0][0][0].width()
        self.assertLess(small, large)

    def test_click_on_tile_asks_to_open_it(self):
        seen = []
        self.g.open_requested.connect(lambda kind, index: seen.append((kind, index)))
        self.g.set_filter("card")
        rect = self.g.grid.tiles[1][0]
        self.g.grid.mouseReleaseEvent(_Event(rect.center()))
        self.assertEqual(seen, [("card", 1)])


class _Event:
    def __init__(self, pt):
        self._pt = pt

    def position(self):
        return _Pos(self._pt)


class _Pos:
    def __init__(self, pt):
        self._pt = pt

    def toPoint(self):
        return self._pt

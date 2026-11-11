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
    import modgen as M
    import gallery_qt as G


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class GalleryRenderTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.project["cards"] = [M.new_card("C_ONE"), M.new_card("C_TWO")]
        self.project["relics"] = [M.new_relic("R_ONE")]
        self.project["potions"] = [M.new_potion("P_ONE")]
        self.project["powers"] = [M.new_power("W_ONE")]
        self.g = G.GalleryQt(self.project)
        self.g.resize(900, 700)
        self.g.show()
        _app.processEvents()

    def tearDown(self):
        self.g.close()

    def _painted_pixels(self):
        image = self.g.grid.grab().toImage()
        return sum(1 for y in range(0, image.height(), 7) for x in range(0, image.width(), 7)
                   if image.pixelColor(x, y).name() != "#121318")

    def test_every_kind_paints_real_content_in_each_language(self):
        for lang in ("ko", "en", "zh"):
            for upgraded in (False, True):
                self.g.set_lang(lang)
                self.g.set_upgraded(upgraded)
                _app.processEvents()
                self.assertGreater(self._painted_pixels(), 500, f"lang={lang} upgraded={upgraded}")

    def test_a_broken_item_shows_an_error_but_does_not_stop_the_others(self):
        self.project["relics"].append({"id": "BROKEN"})   # 필수 항목이 없는 유물
        self.g.refresh()
        _app.processEvents()
        self.assertGreater(self._painted_pixels(), 500)

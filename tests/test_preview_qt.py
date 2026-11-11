import os
import sys
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QImage, QPainter, QColor
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import modgen as M
    import preview_qt as P


def _canvas(w=320, h=420):
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor("#111318"))
    return img


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class PreviewQtTests(TestCase):
    def test_relic_and_potion_return_panel_size(self):
        project = M.default_project()
        relic = M.new_relic("T_RELIC")
        potion = M.new_potion("T_POTION")
        img = _canvas()
        p = QPainter(img)
        self.assertEqual(P.render_relic(p, project, relic, 0, 0, 1.0, "ko"), (300, 400))
        self.assertEqual(P.render_potion(p, project, potion, 0, 0, 1.0, "ko"), (300, 400))
        self.assertEqual(P.render_relic(p, project, relic, 0, 0, 0.5, "en"), (150, 200))
        p.end()

    def test_rich_text_wraps_into_more_lines_when_narrower(self):
        img = _canvas()
        p = QPainter(img)
        text = "매 턴 시작할 때 블록을 얻고 카드를 한 장 뽑습니다 " * 3
        wide = P.draw_rich(p, 0, 0, 400, text, 10, measure_only=True)
        narrow = P.draw_rich(p, 0, 0, 120, text, 10, measure_only=True)
        p.end()
        self.assertGreater(narrow, wide)

    def test_missing_image_falls_back_to_drawn_shapes(self):
        self.assertIsNone(P.pixmap("", 100, 100))
        self.assertIsNone(P.pixmap("C:/no/such/file.png", 100, 100))

    def test_card_power_and_character_render_in_every_language(self):
        project = M.default_project()
        card = M.new_card("T_CARD")
        power = M.new_power("T_POWER")
        img = _canvas(320, 600)
        p = QPainter(img)
        for lang in ("ko", "en", "zh"):
            self.assertEqual(P.render_card(p, project, card, 0, 0, 1.0, lang), (300, 420))
            self.assertEqual(P.render_power(p, project, power, 0, 0, 1.0, lang, 3), (300, 400))
            P.render_character(p, project, 0, 0, lang, 1.0)   # 반환 값 없음
        card["no_cost"] = True
        self.assertEqual(P.render_card(p, project, card, 0, 0, 0.5, "ko"), (150, 210))
        p.end()

    def test_missing_card_art_uses_stripe_placeholder_when_pillow_present(self):
        pm = P.placeholder(120, 80, "round", "#3a3f4a")
        self.assertTrue(pm is None or (pm.width() == 120 and pm.height() == 80))

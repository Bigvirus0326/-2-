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
    import characterqt as C


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class CharacterPanelQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.calls = 0
        self.panel = C.CharacterPanelQt(self.project, on_change=self._count)
        self.panel.resize(1000, 800)
        self.panel.show()

    def tearDown(self):
        self.panel.close()

    def _count(self):
        self.calls += 1

    def test_text_fields_write_into_the_character(self):
        f = self.panel._fields
        f["id"].setText("MY_HERO")
        f["hp"].setText("82")
        f["name_ko"].setText("내 영웅")
        f["color"].setText("#ff8800")
        ch = self.project["character"]
        self.assertEqual(ch["id"], "MY_HERO")
        self.assertEqual(ch["hp"], 82)
        self.assertEqual(ch["name_ko"], "내 영웅")
        self.assertEqual(ch["color"], "#ff8800")
        self.assertGreater(self.calls, 0)

    def test_hp_that_is_not_a_number_keeps_the_old_value(self):
        before = self.project["character"].get("hp")
        self.panel._fields["hp"].setText("많이")
        self.assertEqual(self.project["character"].get("hp"), before)

    def test_enabled_checkbox_and_hsv_are_stored(self):
        self.panel.enabled.setChecked(True)
        self.assertTrue(self.project["character"]["enabled"])
        self.panel._fields["card_h"].setValue(0.25)
        self.assertEqual(self.project["character"]["card_h"], 0.25)

    def test_deck_add_change_and_remove(self):
        self.project["character"]["deck"] = []             # 기본 프로젝트의 덱과 섞이지 않게 비운다
        self.project["cards"] = [{"id": "C_ONE", "name_ko": "하나"}]
        self.panel.load(self.project)
        self.panel.deck_card.setCurrentIndex(self.panel.deck_card.findData("C_ONE"))
        self.panel.deck_count.setValue(3)
        self.panel.deck_add()
        self.assertEqual(self.project["character"]["deck"], [{"card": "C_ONE", "count": 3}])
        self.assertEqual(self.panel.deck_total.text(), "총 3장")
        self.panel.deck_count.setValue(5)
        self.panel.deck_add()                                   # 같은 카드는 장수만 바뀐다
        self.assertEqual(self.project["character"]["deck"], [{"card": "C_ONE", "count": 5}])
        self.panel.deck_table.selectRow(0)
        self.panel.deck_remove()
        self.assertEqual(self.project["character"]["deck"], [])

    def test_relic_add_and_remove(self):
        self.project["character"]["relics"] = []          # 기본 프로젝트의 시작 유물과 섞이지 않게 비운다
        self.project["relics"] = [{"id": "R_ONE", "name_ko": "유물", "rarity": "Starter"}]
        self.panel.load(self.project)
        self.panel.relic_combo.setCurrentIndex(self.panel.relic_combo.findData("R_ONE"))
        self.panel.relic_add()
        self.panel.relic_add()                                  # 두 번 추가해도 한 번만 들어간다
        self.assertEqual(self.project["character"]["relics"], ["R_ONE"])
        self.panel.relic_list.item(0).setSelected(True)
        self.panel.relic_remove()
        self.assertEqual(self.project["character"]["relics"], [])

    def test_loading_another_project_does_not_count_as_an_edit(self):
        other = M.default_project()
        other["character"]["name_ko"] = "다른 캐릭터"
        before = self.calls
        self.panel.load(other)
        self.assertEqual(self.calls, before)
        self.assertEqual(self.panel._fields["name_ko"].text(), "다른 캐릭터")

    def test_preview_draws_an_image_in_each_language(self):
        for lang in ("ko", "en", "zh"):
            self.panel.set_preview_lang(lang)
            pixmap = self.panel.preview.pixmap()
            self.assertIsNotNone(pixmap)
            self.assertFalse(pixmap.isNull())

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


def _imported(name="가져온 영웅"):
    return {"class": "ImportedHero", "name_ko": name, "hp": 70, "deck": [], "relics": [],
            "attack_frames": [{"image": "a.png"}, {"image": "b.png"}]}


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ImportedCharacterTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.project["imported_characters"] = [_imported()]
        self.mine_before = dict(self.project["character"])
        self.panel = C.CharacterPanelQt(self.project)
        self.addCleanup(self.panel.close)
        self.panel.select_char("0")

    def test_choosing_an_imported_character_hides_the_mine_only_fields(self):
        self.assertTrue(self.panel.imported())
        self.assertFalse(self.panel._fields["color"].isVisibleTo(self.panel))
        self.assertTrue(self.panel.enabled.isHidden())
        self.assertTrue(self.panel._fields["name_ko"].isVisibleTo(self.panel))

    def test_name_and_hp_are_written_into_the_imported_character_only(self):
        self.panel._fields["name_ko"].setText("새 이름")
        self.panel._fields["hp"].setText("88")
        imported = self.project["imported_characters"][0]
        self.assertEqual(imported["name_ko"], "새 이름")
        self.assertEqual(imported["hp"], 88)
        self.assertEqual(self.project["character"], self.mine_before)

    def test_a_blank_gold_removes_the_override(self):
        self.panel._fields["gold"].setText("40")
        self.assertEqual(self.project["imported_characters"][0]["gold"], 40)
        self.panel._fields["gold"].setText("")
        self.assertNotIn("gold", self.project["imported_characters"][0])

    def test_motion_speed_is_saved_on_the_imported_character(self):
        self.panel.motion_times["attack_frames"].setValue(200)
        self.assertEqual(self.project["imported_characters"][0]["attack_frames_ms"], 200)

    def test_removing_a_motion_frame_keeps_the_others(self):
        self.panel.refresh_motion_lists()
        self.panel.motion_lists["attack_frames"].setCurrentRow(0)
        self.panel.edit_motion("attack_frames", "remove")
        self.assertEqual(self.project["imported_characters"][0]["attack_frames"], [{"image": "b.png"}])
        self.assertEqual(self.panel.motion_lists["attack_frames"].count(), 1)

    def test_going_back_to_my_character_shows_the_mine_only_fields_again(self):
        self.panel.select_char("mine")
        self.assertFalse(self.panel.imported())
        self.assertTrue(self.panel._fields["color"].isVisibleTo(self.panel))
        self.assertFalse(self.panel._fields["gold"].isVisibleTo(self.panel))

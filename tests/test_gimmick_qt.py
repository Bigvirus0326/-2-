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
    import gimmick as GM
    import gimmickqt as G
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class GimmickQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        GM.normalize(self.project)
        self.changes = 0
        self.page = G.GimmickQt(self.project, on_change=self._count)
        self.page.resize(1100, 800)
        self.page.show()
        self.addCleanup(self.page.close)

    def _count(self):
        self.changes += 1

    def test_adding_a_tag_gives_it_a_unique_id(self):
        tags = self.page.panels["tags"]
        tags.add()
        tags.add()
        ids = [t["id"] for t in self.project["gimmicks"]["tags"]]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(ids[0], "new_tag")
        self.assertGreater(self.changes, 0)

    def test_tag_id_change_renames_card_tags(self):
        tags = self.project["gimmicks"]["tags"]
        tags.append(GM.new_tag("fire"))
        self.project["cards"][0]["gtags"] = ["fire"]
        self.page.panels["tags"].refresh_list(len(tags) - 1)
        self.page.panels["tags"]._fields["id"][1].setText("flame")
        self.assertEqual(self.project["cards"][0]["gtags"], ["flame"])

    def test_deleting_a_tag_removes_it_from_cards(self):
        tags = self.project["gimmicks"]["tags"]
        tags.append(GM.new_tag("fire"))
        self.project["cards"][0]["gtags"] = ["fire", "other"]
        self.page.panels["tags"].refresh_list(len(tags) - 1)
        with mock.patch.object(G, "_ask", return_value=True):
            self.page.panels["tags"].delete()
        self.assertEqual(self.project["cards"][0]["gtags"], ["other"])
        self.assertFalse(any(t["id"] == "fire" for t in tags))

    def test_summon_slots_and_max_rank_are_written(self):
        summons = self.page.panels["summons"]
        self.project["gimmicks"]["summons"].append(GM.new_summon("ice"))
        summons.refresh_list(0)
        summons.slots.setValue(7)
        self.assertEqual(self.project["gimmicks"]["summon_slots"], 7)
        summons._fields["max_rank"][1].setValue(0)
        self.assertEqual(self.project["gimmicks"]["summons"][0]["max_rank"], 1)   # 최소 1단계

    def test_orb_passive_and_evoke_values(self):
        orbs = self.page.panels["orbs"]
        self.project["gimmicks"]["orbs"].append(GM.new_orb("ice"))
        orbs.refresh_list(0)
        orbs._fields["passive"][1].setValue(4)
        orbs._fields["evoke"][1].setValue(11)
        orb = self.project["gimmicks"]["orbs"][0]
        self.assertEqual((orb["passive"], orb["evoke"]), (4, 11))
        self.assertIn("4", orbs.desc.text())

    def test_pet_gets_its_own_id_in_its_blocks(self):
        pets = self.page.panels["pets"]
        pets.add()
        pet = self.project["gimmicks"]["pets"][-1]
        self.assertTrue(all(b["args"]["pet"] == pet["id"] for b in pet["blocks"]))

    def test_pet_preview_is_drawn(self):
        pets = self.page.panels["pets"]
        self.project["gimmicks"]["pets"].append(__import__("pets").new_pet("gol"))
        pets.refresh_list(0)
        self.assertFalse(pets.canvas.pixmap().isNull())

    def test_tag_timing_enables_the_hand_play_options_only(self):
        tags = self.page.panels["tags"]
        self.project["gimmicks"]["tags"].append(GM.new_tag("fire"))
        tags.refresh_list(0)
        tags.timing.setCurrentIndex(tags.timing.findData("play"))
        self.assertFalse(tags._box("played_every").isEnabled())
        tags.timing.setCurrentIndex(tags.timing.findData("hand_play"))
        self.assertTrue(tags._box("played_every").isEnabled())

    def test_examples_are_added_and_the_tabs_reload(self):
        reload = mock.Mock()
        page = G.GimmickQt(self.project, on_change=self._count, on_reload=reload)
        self.addCleanup(page.close)
        with mock.patch.object(G, "_ask", return_value=True), mock.patch.object(G, "_info") as info, \
                mock.patch.object(G.GM, "add_examples", return_value=["예시 A"]) as add:
            page.add_examples()
        add.assert_called_once()
        reload.assert_called_once()
        info.assert_called_once()


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class TagBlockTests(TestCase):
    def test_tag_blocks_are_saved_for_the_chosen_timing(self):
        project = M.default_project()
        GM.normalize(project)
        page = G.GimmickQt(project, on_change=lambda: None)
        self.addCleanup(page.close)
        tags = page.panels["tags"]
        tags.add()
        tag = project["gimmicks"]["tags"][tags.cur]
        for i in range(tags.timing.count()):
            tags.timing.setCurrentIndex(i)
            timing = tags.timing.currentData()
            blocks = [{"op": "block_action", "args": {"amount": {"t": "num", "v": i + 1}}}]
            with mock.patch("blockqt.edit_blocks", return_value={"blocks": blocks}):
                tags.edit_tag_blocks()
            self.assertEqual(GM.tag_blocks(tag, timing), blocks, timing)

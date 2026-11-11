import os
import sys
from unittest import TestCase, mock, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import modgen as M
    import itemtabqt as IT


def _row_of(tab, item_id):
    return next(i for i, it in enumerate(tab.items) if it["id"] == item_id)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class CardTabQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.calls = 0
        self.tab = IT.CardTabQt(self.project, on_change=self._count)
        self.tab.resize(1200, 800)
        self.tab.show()

    def tearDown(self):
        self.tab.close()

    def _count(self):
        self.calls += 1

    def _select(self, item_id):
        self.tab.refresh_list(_row_of(self.tab, item_id))
        return self.project["cards"][_row_of(self.tab, item_id)]

    def test_name_edit_writes_into_the_card_and_updates_the_row(self):
        card = self._select("strike")
        self.tab._fields["name_ko"][1].setText("강한 타격")
        self.assertEqual(card["name_ko"], "강한 타격")
        self.assertGreater(self.calls, 0)
        self.assertIn("강한 타격", self.tab.listing.currentItem().text())

    def test_id_change_renames_the_deck_entry(self):
        self.project["character"]["deck"] = [{"card": "strike", "count": 2}]
        self._select("strike")
        self.tab._fields["id"][1].setText("strike_v2")
        self.assertEqual(self.project["character"]["deck"], [{"card": "strike_v2", "count": 2}])

    def test_numbers_outside_the_spin_range_are_not_rewritten(self):
        self.project["cards"][_row_of(self.tab, "strike")]["cost"] = 12               # 기존 프로젝트의 값 (선택하기 전에 넣는다)
        card = self._select("strike")
        self.tab._fields["name_en"][1].setText("Strike!")
        self.assertEqual(card["cost"], 12)

    def test_unknown_rarity_is_kept_when_another_field_changes(self):
        self.project["cards"][_row_of(self.tab, "strike")]["rarity"] = "Mythic"       # 목록에 없는 값 (선택하기 전에 넣는다)
        card = self._select("strike")
        self.tab._fields["name_ko"][1].setText("다른 이름")
        self.assertEqual(card["rarity"], "Mythic")

    def test_cost_keywords_and_no_cost_rules(self):
        card = self._select("strike")
        self.tab._fields["cost"][1].setValue(3)
        self.assertEqual(card["cost"], 3)
        self.tab._kw["Exhaust"].setChecked(True)
        self.assertIn("Exhaust", card["keywords"])
        self.tab._set_checked("x_cost", True)
        self.tab._fields["no_cost"][1].setChecked(True)
        self.assertTrue(card["no_cost"])
        self.assertFalse(card["x_cost"])                    # 비용 없음이면 X 비용은 꺼진다
        self.assertFalse(self.tab._fields["cost"][1].isEnabled())

    def test_choosing_a_type_writes_it(self):
        card = self._select("strike")
        index = self.tab._kind_box.findData("Skill")
        self.tab._kind_box.setCurrentIndex(index)
        self.assertEqual(card["type"], "Skill")

    def test_add_then_duplicate_use_unique_ids(self):
        self.tab.add()
        new = self.project["cards"][-1]
        self.assertEqual(new["id"], "new_card")
        self.tab.duplicate()
        copy_ = self.project["cards"][self.tab.cur]
        self.assertNotEqual(copy_["id"], new["id"])
        self.assertTrue(copy_["name_ko"].endswith(" (복사)"))

    def test_delete_removes_card_and_its_deck_entry(self):
        self.project["character"]["deck"] = [{"card": "strike", "count": 2}]
        self._select("strike")
        with mock.patch.object(IT, "ask_yes_no", return_value=True):
            self.tab.delete()
        self.assertFalse(any(c["id"] == "strike" for c in self.project["cards"]))
        self.assertEqual(self.project["character"]["deck"], [])

    def test_delete_that_is_cancelled_keeps_the_card(self):
        before = len(self.project["cards"])
        self._select("strike")
        with mock.patch.object(IT, "ask_yes_no", return_value=False):
            self.tab.delete()
        self.assertEqual(len(self.project["cards"]), before)

    def test_search_filters_the_list(self):
        self.tab.search.setText("타격")
        self.assertEqual(self.tab.listing.count(), 1)
        self.assertIn("1 / ", self.tab.count_lbl.text())

    def test_loading_another_project_does_not_count_as_an_edit(self):
        other = M.default_project()
        other["cards"][0]["name_ko"] = "다른 카드"
        before = self.calls
        self.tab.load_project(other)
        self.assertEqual(self.calls, before)
        self.assertEqual(self.tab._fields["name_ko"][1].text(), "다른 카드")

    def test_preview_draws_for_the_selected_card(self):
        self._select("strike")
        self.assertFalse(self.tab.preview.pixmap().isNull())


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class OtherItemTabsQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.calls = 0

    def _tab(self, cls):
        tab = cls(self.project, on_change=self._count)
        tab.resize(1200, 800)
        tab.show()
        self.addCleanup(tab.close)
        return tab

    def _count(self):
        self.calls += 1

    def test_relic_upgrade_link_and_unknown_upgrade_value_is_kept(self):
        tab = self._tab(IT.RelicTabQt)
        base = self.project["relics"][0]
        base["upgrade_relic"] = "missing_relic"
        tab.refresh_list(0)
        tab._fields["name_en"][1].setText("Renamed")
        self.assertEqual(base["upgrade_relic"], "missing_relic")
        tab.make_upgrade()
        new = self.project["relics"][1]
        self.assertEqual(base["upgrade_relic"], new["id"])
        self.assertEqual(new["rarity"], "Starter")
        self.assertEqual(new["upgrade_relic"], "")
        self.assertTrue(new["name_ko"].endswith("+"))

    def test_potion_fields_write_into_the_potion(self):
        tab = self._tab(IT.PotionTabQt)
        potion = self.project["potions"][0]
        tab.refresh_list(0)
        tab._fields["name_zh"][1].setText("药水")
        tab._fields["target"][1].setCurrentIndex(tab._fields["target"][1].findData("Self"))
        self.assertEqual(potion["name_zh"], "药水")
        self.assertEqual(potion["target"], "Self")

    def test_power_in_use_is_reported_and_reference_is_renamed(self):
        tab = self._tab(IT.PowerTabQt)
        power = self.project["powers"][0]
        pid = power["id"]
        before = IT.rename_ref(self.project, "power", pid, None)     # 기본 프로젝트에도 이 파워를 쓰는 효과가 있다
        self.project["cards"][0]["effects"][0]["power"] = "c:" + pid
        self.assertEqual(IT.rename_ref(self.project, "power", pid, None), before + 1)
        self.assertEqual(IT.rename_ref(self.project, "power", pid, "renamed_pow"), 0)
        self.assertEqual(self.project["cards"][0]["effects"][0]["power"], "c:renamed_pow")
        tab.refresh_list(0)
        tab._fields["cap"][1].setValue(6)
        self.assertEqual(self.project["powers"][0]["cap"], 6)

    def test_every_item_tab_draws_its_first_item(self):
        for cls in (IT.CardTabQt, IT.RelicTabQt, IT.PotionTabQt, IT.PowerTabQt):
            tab = self._tab(cls)
            tab.refresh_list(0)
            for lang in ("ko", "en", "zh"):
                tab.set_preview_lang(lang)
                self.assertFalse(tab.preview.pixmap().isNull(), cls.__name__)

    def test_unique_id_skips_used_ids(self):
        self.assertEqual(IT.unique_id(self.project, "strike"), "strike_b")
        self.assertEqual(IT.unique_id(self.project, "brand_new"), "brand_new")


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class BlockButtonTests(TestCase):
    def setUp(self):
        self.project = M.default_project()

    def test_a_play_condition_is_written_from_the_slot_dialog(self):
        tab = IT.CardTabQt(self.project, on_change=lambda: None)
        self.addCleanup(tab.close)
        tab.refresh_list(_row_of(tab, "strike"))
        card = self.project["cards"][_row_of(tab, "strike")]
        cond = {"t": "cmp", "a": {"t": "num", "v": 1}, "op": ">=", "b": {"t": "num", "v": 2}}
        dialog = mock.Mock(result=cond)
        dialog.exec.return_value = 1
        with mock.patch.object(IT, "SlotDialogQt", return_value=dialog) as slot:
            tab.edit_cond("play_cond")
        self.assertEqual(slot.call_args[0][2], "cond")
        self.assertEqual(card["play_cond"], cond)

    def test_overflow_blocks_are_edited_with_events_allowed(self):
        tab = IT.PowerTabQt(self.project, on_change=lambda: None)
        self.addCleanup(tab.close)
        tab.refresh_list(0)
        power = tab.items[0]
        blocks = [{"op": "block_action", "args": {"amount": {"t": "num", "v": 2}}}]
        with mock.patch("blockqt.edit_blocks", return_value={"blocks": blocks}) as editor:
            tab.edit_block_list("overflow_blocks", "overflow", allow_event=True)
        self.assertTrue(editor.call_args.kwargs["allow_event"])
        self.assertEqual(power["overflow_blocks"], blocks)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class CardEventTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.tab = IT.CardTabQt(self.project, on_change=lambda: None)
        self.addCleanup(self.tab.close)
        self.tab.refresh_list(_row_of(self.tab, "strike"))
        self.card = self.project["cards"][_row_of(self.tab, "strike")]

    def test_the_upgraded_play_variant_copies_the_base_effects(self):
        self.tab.sep_check.setChecked(True)
        self.assertTrue(self.card["separate_upgrade_effect"])
        self.assertIsNot(self.card["upgrade_effects"], self.card["effects"])
        self.assertIs(self.tab.effects.effects, self.card["upgrade_effects"])

    def test_leaving_the_upgraded_variant_shows_the_base_effects_again(self):
        self.tab.sep_check.setChecked(True)
        self.tab.play_variant.setChecked(True)
        self.assertIs(self.tab.effects.effects, self.card["upgrade_effects"])
        self.tab.sep_check.setChecked(False)
        self.assertIs(self.tab.effects.effects, self.card["effects"])

    def test_an_event_block_is_edited_through_the_block_editor(self):
        panel = self.tab.event_panels["draw"]
        blocks = [{"op": "draw_action", "args": {"amount": {"t": "num", "v": 1}}}]
        with mock.patch("blockqt.edit_blocks", return_value={"blocks": blocks}) as editor:
            panel.edit()
        self.assertEqual(editor.call_args.kwargs["card_event"], "draw")
        self.assertEqual(self.card["event_blocks"]["draw"], blocks)
        self.assertEqual(panel.listing.count(), 1)

    def test_separate_event_variant_copies_the_base_blocks(self):
        panel = self.tab.event_panels["exhaust"]
        self.card["event_blocks"] = {"exhaust": [{"op": "draw_action", "args": {}}]}
        panel.separate.setChecked(True)
        self.assertTrue(self.card["separate_upgrade_events"]["exhaust"])
        self.assertEqual(self.card["upgrade_event_blocks"]["exhaust"], self.card["event_blocks"]["exhaust"])
        self.assertIsNot(self.card["upgrade_event_blocks"]["exhaust"], self.card["event_blocks"]["exhaust"])

    def test_the_event_target_count_is_saved_only_for_choose(self):
        panel = self.tab.event_panels["discard"]
        panel.target.setCurrentIndex(panel.target.findData("choose"))
        panel.count.setValue(3)
        self.assertEqual(self.card["event_targets"]["discard"], "choose")
        self.assertEqual(self.card["event_target_counts"]["discard"], 3)

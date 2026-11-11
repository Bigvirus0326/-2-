import copy
import unittest
import blockcode as B
import gimmick as G
import modgen as M

class TagBlockTests(unittest.TestCase):
    def setUp(self):
        self.project = G.normalize(M.default_project())
        self.card = self.project["cards"][0]
        self.tag = G.new_tag("burst")
        self.tag["blocks"] = [B.new_block("energy")]
        self.project["gimmicks"]["tags"] = [self.tag]
        self.card["gtags"] = ["burst", "burst"]

    def test_keyword_runs_once_after_card_effects_and_is_not_copied_into_project(self):
        before = copy.deepcopy(self.project)
        code = M.gen_card(self.project, self.card)
        self.assertEqual(code.count('.HasTag(this, "burst")'), 1)
        self.assertIn("PlayerCmd.GainEnergy", code)
        self.assertLess(code.index("CommonActions.CardAttack"), code.index('.HasTag(this, "burst")'))
        self.assertEqual(self.project, before)

    def test_untagged_cards_check_runtime_tags_and_empty_tags_add_nothing(self):
        self.card["gtags"] = []
        self.assertIn('.HasTag(this, "burst")', M.gen_card(self.project, self.card))
        self.tag["blocks"] = []
        self.assertNotIn('.HasTag(this, "burst")', M.gen_card(self.project, self.card))

    def test_keyword_tooltip_includes_actions_in_each_language(self):
        for lang in ("ko", "en", "zh"):
            files = M.gen_localization(self.project, lang)
            lid = M.loc_id(self.project, "burst_tag_power")
            self.assertTrue(files["powers"][lid + ".description"])

    def test_invalid_keyword_blocks_are_reported(self):
        child = B.new_block("card_upgrade")
        child["args"]["card"] = "@picked_card"
        self.tag["blocks"] = [child]
        errors, _ = G.validate(self.project)
        self.assertTrue(any("키워드" in e for e in errors))
        with self.assertRaises(ValueError):
            M.gen_card(self.project, self.card)

    def test_editor_saves_shared_blocks_without_editing_example_card(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        import sts2_mod_maker as S
        before = copy.deepcopy(self.card)
        result = [B.new_block("draw")]
        tab = SimpleNamespace(tag_cur=0, g=self.project["gimmicks"],
                              app=SimpleNamespace(project=self.project, mark_dirty=Mock()),
                              wait_window=Mock(), show_tag_blocks=Mock())
        with patch("blockui.BlockEditor", return_value=SimpleNamespace(result={"blocks": result})) as editor:
            S.GimmickTab.edit_tag_blocks(tab)
        self.assertEqual(self.tag["blocks"], result)
        self.assertEqual(self.card, before)
        self.assertEqual(editor.call_args.args[2], "card")
        tab.app.mark_dirty.assert_called_once()

    def test_all_timings_merge_with_card_hooks_and_check_hand(self):
        self.tag["event_blocks"] = {key: [B.new_block("hand_aura_stat" if key == "hand_aura" else "damage")] for key, _ in G.TAG_TIMINGS if key != "play"}
        self.card["event_blocks"] = {"draw": [B.new_block("energy")]}
        code = M.gen_card(self.project, self.card)
        for method in (*M.CARD_EVENTS.values(), "AfterPlayerTurnStart", "BeforeSideTurnEnd"):
            self.assertEqual(code.count("Task " + method + "("), 1)
        self.assertEqual(code.count("Hand.Cards.Contains(this)"), 3)
        self.assertEqual(code.count("if (card != this) return;"), 4)
        self.assertIn("eventTarget", code)
        self.assertNotIn("cardPlay.Target", code[code.index("Task AfterCardDrawn("):code.index("Task AfterCardPlayed(")])
        for key, _ in G.TAG_TIMINGS:
            self.assertTrue(G.tag_blocks(self.tag, key))

    def test_imported_hook_is_preserved_and_wrapped(self):
        self.tag["event_blocks"] = {"draw": [B.new_block("energy")]}
        body = "public override async Task AfterCardDrawn(PlayerChoiceContext ctx, CardModel drawn, bool automatic) { await Task.CompletedTask; }"
        hooks, preserved = M.keyword_card_hooks(self.project, self.card, body)
        self.assertIn("MakerOriginalAfterCardDrawn", preserved)
        self.assertIn("await MakerOriginalAfterCardDrawn(choiceContext, card, flag)", "\n".join(hooks))

    def test_event_editor_saves_only_selected_timing(self):
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        import sts2_mod_maker as S
        original = copy.deepcopy(self.tag["blocks"])
        result = [B.new_block("draw")]
        tab = SimpleNamespace(tag_cur=0, g=self.project["gimmicks"],
                              tag_timing=SimpleNamespace(get_value=lambda: "exhaust"),
                              app=SimpleNamespace(project=self.project, mark_dirty=Mock()),
                              wait_window=Mock(), show_tag_blocks=Mock())
        with patch("blockui.BlockEditor", return_value=SimpleNamespace(result={"blocks": result})) as editor:
            S.GimmickTab.edit_tag_blocks(tab)
        self.assertEqual(self.tag["blocks"], original)
        self.assertEqual(G.tag_blocks(self.tag, "exhaust"), result)
        self.assertEqual(editor.call_args.kwargs["card_event"], "exhaust")

    def test_hand_play_filters_owner_self_and_matching_keyword(self):
        self.tag["event_blocks"]["hand_play"] = [B.new_block("damage")]
        other = G.new_tag("explosion")
        other["name_ko"] = "폭발"
        self.project["gimmicks"]["tags"].append(other)
        for selected, expected in (("Any", "true"), ("tag:explosion", '.HasTag(cardPlay.Card, "explosion")'),
                                   ("kw:Exhaust", "cardPlay.Card.Keywords.Contains(CardKeyword.Exhaust)")):
            self.tag["played_filter"] = selected
            code = M.gen_card(self.project, self.card)
            section = code[code.index("Task AfterCardPlayed("):]
            self.assertIn("cardPlay.Card == this || cardPlay.Card.Owner != Owner", section)
            self.assertIn("Hand.Cards.Contains(this)", section)
            self.assertIn(expected, section)
            self.assertIn("cardPlay.Target", section)
            self.assertNotIn("eventTarget", section)
        files = M.gen_localization(self.project, "ko")
        self.assertIn("소멸", files["powers"][M.loc_id(self.project, "burst_tag_power") + ".description"])

    def test_missing_hand_play_filter_is_reported(self):
        self.tag["played_filter"] = "tag:missing"
        errors, _ = G.validate(self.project)
        self.assertTrue(any("조건" in error for error in errors))

    def test_keyword_condition_tracks_renamed_or_deleted_keyword(self):
        import sts2_mod_maker as S
        self.tag["played_filter"] = "tag:old_tag"
        S.rename_gimmick_ref(self.project, "tag", "old_tag", "new_tag")
        self.assertEqual(self.tag["played_filter"], "tag:new_tag")
        S.rename_gimmick_ref(self.project, "tag", "new_tag", None)
        self.assertEqual(self.tag["played_filter"], "Any")

    def test_filter_selection_is_saved_on_the_selected_keyword(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        import sts2_mod_maker as S
        tab = SimpleNamespace(_loading=False, tag_cur=0, g=self.project["gimmicks"],
                              tag_play_filter=SimpleNamespace(get_value=lambda: "kw:Exhaust"),
                              app=SimpleNamespace(mark_dirty=Mock()), show_tag_blocks=Mock())
        S.GimmickTab.tag_filter_changed(tab)
        self.assertEqual(self.tag["played_filter"], "kw:Exhaust")
        tab.app.mark_dirty.assert_called_once()
        tab.show_tag_blocks.assert_called_once_with(self.tag)

    def test_count_threshold_scope_and_aura_codegen(self):
        self.tag.update(event_blocks={"hand_play": [B.new_block("energy")]}, played_every=3,
                        played_scope="turn", hand_cost_enabled=True, hand_cost_amount=2,
                        hand_cost_filter="kw:Exhaust")
        code = M.gen_card(self.project, self.card)
        self.assertIn("_makerTagCount0 >= 3", code)
        self.assertIn("_makerTagCount0Round !=", code)
        self.assertIn("_makerTagCount0Combat !=", code)
        self.assertIn("reduction -= (-2m)", code)
        self.assertIn("cardSource.Keywords.Contains(CardKeyword.Exhaust)", code)
        self.assertIn("Math.Max(0m, originalCost - reduction)", code)
        self.assertIn("!card.EnergyCost.CostsX", code)
        self.assertIn("InvokeEnergyCostChanged", code)
        self.tag["played_scope"] = "combat"
        combat_code = M.gen_card(self.project, self.card)
        self.assertNotIn("_makerTagCount0Round !=", combat_code)
        self.assertIn("_makerTagCount0Combat !=", combat_code)
        self.tag["played_every"] = 0
        errors, _ = G.validate(self.project)
        self.assertTrue(any("집계" in error for error in errors))

    def test_old_tags_get_independent_empty_blocks(self):
        self.project["gimmicks"]["tags"] = [{"id": "a"}, {"id": "b"}]
        G.normalize(self.project)
        a, b = G.tags(self.project)
        a["blocks"].append(B.new_block("draw"))
        self.assertEqual(b["blocks"], [])

if __name__ == "__main__":
    unittest.main()


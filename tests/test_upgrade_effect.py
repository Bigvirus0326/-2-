import copy
import unittest

import blockcode as B
import gimmick as G
import modgen as M
import previewcore as P


class UpgradeEffectTests(unittest.TestCase):
    def setUp(self):
        self.project = G.normalize(M.default_project())
        self.card = self.project["cards"][0]
        draw = B.new_block("draw")
        draw["args"]["amount"] = {"t": "num", "v": 2}
        self.card.update(separate_upgrade_effect=True, upgrade_effect_blocks=[draw])

    def test_effect_branch_and_description_follow_upgrade_state(self):
        before = copy.deepcopy(self.card)
        body = "\n".join(M._effects_body(self.project, self.card, M._Ctx("card", self.card)))
        self.assertIn("if (IsUpgraded)", body)
        upgraded, base = body.split("else", 1)
        self.assertIn("CardPileCmd.Draw", upgraded)
        self.assertNotIn("CommonActions.CardAttack", upgraded)
        self.assertIn("CommonActions.CardAttack", base)
        desc = M.description(self.project, self.card, "card", "ko")
        normal = P.fill_values(self.project, desc, self.card, upgraded=False)
        upgraded = P.fill_values(self.project, desc, self.card, upgraded=True)
        self.assertIn("피해", normal)
        self.assertNotIn("피해", upgraded)
        self.assertIn("2", upgraded)
        self.assertIn("뽑", upgraded)
        self.assertEqual(self.card, before)

    def test_numeric_variables_and_shared_keyword_effect_are_kept(self):
        tag = G.new_tag("common")
        tag["blocks"] = [B.new_block("energy")]
        self.project["gimmicks"]["tags"] = [tag]
        self.card["gtags"] = ["common"]
        code = M.gen_card(self.project, self.card)
        self.assertIn('new CardsVar("MakerBlockCards1", (int)(2m))', code)
        body = "\n".join(M._effects_body(self.project, self.card, M._Ctx("card", self.card)))
        self.assertGreater(body.index('.HasTag(this, "common")'), body.index("else"))
        self.assertEqual(body.count("CardPileCmd.Draw"), 1)

    def test_disabled_retains_saved_blocks_but_uses_old_behavior(self):
        self.card["separate_upgrade_effect"] = False
        code = M.gen_card(self.project, self.card)
        self.assertNotIn("if (IsUpgraded)", code)
        self.assertNotIn("CardPileCmd.Draw", code)
        self.assertNotIn("{IfUpgraded:show:", M.description(self.project, self.card, "card", "ko"))
        self.assertTrue(self.card["upgrade_effect_blocks"])

    def test_empty_upgraded_effect_and_invalid_blocks(self):
        self.card["upgrade_effect_blocks"] = []
        self.assertIn("if (IsUpgraded)", M.gen_card(self.project, self.card))
        block = B.new_block("card_upgrade")
        block["args"]["card"] = "@picked_card"
        self.card["upgrade_effect_blocks"] = [block]
        self.assertTrue(any("강화 후 효과" in error for error in M.validate(self.project)[0]))
        with self.assertRaises(ValueError):
            M.gen_card(self.project, self.card)

    def test_cloned_original_onplay_only_runs_before_upgrade(self):
        self.card["clone"] = {"body": "protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay) { await Task.CompletedTask; }"}
        self.assertIn("if (!IsUpgraded) await OriginalOnPlay", M.gen_card(self.project, self.card))

    def test_custom_base_description_and_explicit_upgraded_description(self):
        self.card["desc_ko"] = "강화 전 설명"
        desc = M.description(self.project, self.card, "card", "ko")
        self.assertIn("뽑", P.fill_values(self.project, desc, self.card, upgraded=True))
        self.assertEqual(P.fill_values(self.project, desc, self.card), "강화 전 설명")
        self.card["upgrade_desc_ko"] = "직접 쓴 강화 설명"
        desc = M.description(self.project, self.card, "card", "ko")
        self.assertEqual(P.fill_values(self.project, desc, self.card, upgraded=True), "직접 쓴 강화 설명")

    def test_each_event_has_independent_upgraded_branch_and_description(self):
        self.card["separate_upgrade_effect"] = False
        self.card["effects"] = []
        for event in ("draw", "discard", "exhaust"):
            self.card["event_blocks"] = {event: [B.new_block("energy")]}
            self.card["separate_upgrade_events"] = {event: True}
            self.card["upgrade_event_blocks"] = {event: [B.new_block("block")]}
            code = M.gen_card(self.project, self.card)
            self.assertIn("if (IsUpgraded)", code)
            branch = code[code.index("if (IsUpgraded)"):]
            self.assertIn("CreatureCmd.GainBlock", branch.split("else", 1)[0])
            self.assertIn("PlayerCmd.GainEnergy", branch.split("else", 1)[1])
            desc = M.description(self.project, self.card, "card", "ko")
            self.assertIn("에너지", P.fill_values(self.project, desc, self.card))
            up = P.fill_values(self.project, desc, self.card, upgraded=True)
            self.assertIn("방어도", up)
            self.assertNotIn("에너지", up)
            self.card["separate_upgrade_events"][event] = False
            self.assertNotIn("if (IsUpgraded)", M.gen_card(self.project, self.card))

    def test_copied_traditional_effects_have_independent_numbers(self):
        self.card["upgrade_effects"] = [M.new_effect("damage", 25, 2), M.new_effect("block", 11, 1), M.new_effect("draw", 4, 0)]
        code = M.gen_card(self.project, self.card)
        self.assertIn('new DamageVar("MakerUpDamage", 25m, ValueProp.Move)', code)
        self.assertIn('DynamicVars["MakerUpDamage"].UpgradeValueBy(2m)', code)
        self.assertIn('DynamicVars["MakerUpBlock"].BaseValue', code)
        desc = M.description(self.project, self.card, "card", "ko")
        up = P.fill_values(self.project, desc, self.card, upgraded=True)
        self.assertIn("27", up)
        self.assertIn("12", up)
        self.assertIn("4", up)
        self.assertNotIn("MakerUp", up)


if __name__ == "__main__":
    unittest.main()

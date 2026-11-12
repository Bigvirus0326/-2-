import unittest

import csblocks
import modgen as M

RAW_VARS = [{"name": "Block", "value": 5, "upgrade": 0}, {"name": "Cards", "value": 2, "upgrade": 0}]


def ops_of(stmt):
    body = "protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)\n{\n" + stmt + "\n}"
    card = {"clone": {"body": body, "base": "", "orig_class": "X", "namespace": "N", "usings": []}, "raw_vars": RAW_VARS}
    blocks, _ = csblocks.decompose(card, [], {}, M.default_project())
    out = []
    for b in blocks or []:
        out.append(b["op"])
    return out


class CommonRewriteTests(unittest.TestCase):
    def test_card_block_becomes_block_of_owner(self):
        self.assertEqual(ops_of("await CommonActions.CardBlock(this, cardPlay);"), ["block"])

    def test_draw_becomes_draw(self):
        self.assertEqual(ops_of("await CommonActions.Draw(this, choiceContext);"), ["draw"])

    def test_other_common_calls_are_untouched(self):
        self.assertEqual(csblocks._common_rewrite("await CommonActions.Apply<X>(c, t, this, 1m)"),
                         "await CommonActions.Apply<X>(c, t, this, 1m)")

    def test_upgrade_end_turn_and_sound_forms(self):
        self.assertEqual(ops_of("CardCmd.Upgrade(this);"), ["card_upgrade"])
        self.assertEqual(ops_of("CardCmd.Upgrade(new[] { cardPlay.Card }, CardPreviewStyle.HorizontalLayout);"), ["card_upgrade"])
        self.assertEqual(ops_of('PlayerCmd.EndTurn(Owner, canBackOut: false);'), ["end_turn"])
        self.assertEqual(ops_of('SfxCmd.Play("event:/sfx/x");'), ["sfx"])
        self.assertEqual(ops_of('SfxCmd.Play("event:/sfx/x", 0.8f);'), ["sfx"])


if __name__ == "__main__":
    unittest.main()

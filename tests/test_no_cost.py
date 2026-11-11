import copy
import unittest

import gimmick as G
import modgen as M


class NoCostTests(unittest.TestCase):
    def test_no_cost_hides_energy_and_stays_unplayable_after_upgrade(self):
        project = G.normalize(M.default_project())
        card = project["cards"][0]
        card.update(no_cost=True, cost=3, upgrade_cost=0, x_cost=True,
                    keywords=["Unplayable"], upgrade_remove_keyword="Unplayable")
        before = copy.deepcopy(card)
        code = M.gen_card(project, card)
        self.assertIn("Card(-1, CardType.", code)
        self.assertIn("CardKeyword.Unplayable", code)
        self.assertNotIn("HasEnergyCostX => true", code)
        self.assertNotIn("EnergyCost.UpgradeBy", code)
        self.assertNotIn("RemoveKeyword(CardKeyword.Unplayable)", code)
        self.assertIn("Unplayable", M.card_keywords(card, True))
        self.assertEqual(card, before)

    def test_zero_cost_is_playable_and_existing_projects_keep_their_costs(self):
        project = G.normalize(M.default_project())
        card = project["cards"][0]
        card.update(cost=0, upgrade_cost=0, keywords=[])
        self.assertFalse(card["no_cost"])
        self.assertEqual(M.card_energy_cost(card), 0)
        self.assertNotIn("Unplayable", M.card_keywords(card))
        card.update(x_cost=True)
        self.assertIn("HasEnergyCostX => true", M.gen_card(project, card))

    def test_imported_cards_get_no_cost_and_disable_original_x(self):
        project = G.normalize(M.default_project())
        card = project["cards"][0]
        card.update(no_cost=True, cost=2, upgrade_cost=0,
                    clone={"body": "protected override bool HasEnergyCostX => true;",
                           "upgrade_body": "protected override void OnUpgrade() { RemoveKeyword(CardKeyword.Unplayable); EnergyCost.UpgradeBy(-2); }"})
        code = M.gen_card(project, card)
        self.assertIn(": base(-1, CardType.", code)
        self.assertIn("HasEnergyCostX => false", code)
        self.assertNotIn("protected override bool HasEnergyCostX => true", code)
        self.assertNotIn("RemoveKeyword(CardKeyword.Unplayable)", code)
        self.assertNotIn("EnergyCost.UpgradeBy", code)


if __name__ == "__main__":
    unittest.main()

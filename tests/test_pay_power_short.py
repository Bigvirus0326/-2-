import unittest

import blockcode as B
import modgen as M


def _project():
    p = M.default_project()
    p["powers"].append(M.new_power("bomb"))
    p["powers"][-1]["name_ko"] = "포격"
    return p


def _pay_if(need=2, pay=2, first_op="power_action", power="c:bomb"):
    pay_block = ({"op": "power_action", "args": {"mode": "remove_power", "who": "self", "power": power,
                                                  "amount": {"t": "num", "v": pay}}}
                 if first_op == "power_action" else
                 {"op": "damage_action", "args": {"mode": "damage", "who": "target", "amount": {"t": "num", "v": 1}}})
    return {"op": "if", "args": {"cond": {"t": "cmp", "a": {"t": "stack", "who": "self", "power": "c:bomb"},
                                          "op": ">=", "b": {"t": "num", "v": need}}},
            "body": [pay_block, {"op": "damage_action", "args": {"mode": "damage", "who": "target",
                                                                 "amount": {"t": "num", "v": 8}}}]}


class PayPowerShortTests(unittest.TestCase):
    def test_pay_then_effect_is_short(self):
        text = B.describe([_pay_if()], _project(), "card", "ko")
        self.assertEqual(text, "[gold]포격[/gold] 2: 피해를 8 줍니다.")

    def test_amount_different_from_need_keeps_long_text(self):
        text = B.describe([_pay_if(need=2, pay=1)], _project(), "card", "ko")
        self.assertIn("이상이면", text)

    def test_first_block_not_a_payment_keeps_long_text(self):
        text = B.describe([_pay_if(first_op="damage")], _project(), "card", "ko")
        self.assertIn("이상이면", text)

    def test_payment_of_another_power_keeps_long_text(self):
        text = B.describe([_pay_if(power="c:other")], _project(), "card", "ko")
        self.assertIn("이상이면", text)

    def test_english_text_is_unchanged(self):
        text = B.describe([_pay_if()], _project(), "card", "en")
        self.assertNotIn("포격", text)

    def test_card_description_uses_the_short_text(self):
        project = _project()
        card = M.new_card("bomb_card")
        card["effects"] = [dict(M.new_effect("code"), auto_text=True, blocks=[_pay_if()])]
        project["cards"].append(card)
        M.normalize(project)
        self.assertIn("포격", M.description(project, card, "card", "ko"))
        self.assertIn("[gold]포격[/gold] 2: 피해를", M.description(project, card, "card", "ko"))   # 피해 수치는 게임에서 채운다


if __name__ == "__main__":
    unittest.main()

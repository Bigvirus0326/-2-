import unittest

import csblocks
import modgen as M


class ValueMappingTests(unittest.TestCase):
    def setUp(self):
        self.d = csblocks.Decomposer({}, csblocks.ClassChain("", []), (), project=M.default_project())
        self.d.own_power = "c:gain"

    def test_split_keeps_precedence_and_skips_division(self):
        self.assertEqual(csblocks._split_arith("a + b * c"), ("a", "+", "b * c"))
        self.assertEqual(csblocks._split_arith("a - b + c"), ("a - b", "+", "c"))
        self.assertIsNone(csblocks._split_arith("a / b"))
        self.assertIsNone(csblocks._split_arith("x ? 1 : 2"))
        self.assertIsNone(csblocks._split_arith("-5"))

    def test_own_amount_times_number_is_a_value_block(self):
        v = self.d.resolve("2 * Amount")
        self.assertEqual(v["t"], "op")
        self.assertEqual(v["a"], {"t": "num", "v": 2})
        self.assertEqual(v["b"], {"t": "stack", "power": "c:gain", "who": "self"})

    def test_game_power_amount_lookup(self):
        v = self.d.resolve("Me.GetPowerAmount<StrengthPower>()")
        self.assertEqual(v, {"t": "stack", "power": "Strength", "who": "self"})
        self.assertIsNone(self.d.resolve("Me.GetPowerAmount<SomeModPower>()"))


if __name__ == "__main__":
    unittest.main()

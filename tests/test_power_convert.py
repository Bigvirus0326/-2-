import unittest

import modgen as M
import modimport as MI
import powerconv

GAIN = """using System.Threading.Tasks;
namespace Mod.Powers;
public sealed class GainPower : CustomPowerModel
{
    public override PowerType Type => PowerType.Buff;
    public override PowerStackType StackType => PowerStackType.Counter;
    public override async Task AfterPlayerTurnStart(PlayerChoiceContext ctx, Player player)
    {
        if (player.Creature == Owner)
        {
            await PlayerCmd.GainEnergy(Amount, player);
        }
    }
}
"""

HELPER = GAIN.replace("GainPower", "HelperPower").replace(
    "    public override async Task AfterPlayerTurnStart",
    "    private int Helper() => 1;\n    public override async Task AfterPlayerTurnStart")


class PowerConvertTests(unittest.TestCase):
    def convert_text(self, text, cls_name):
        em = MI.ExtMod()
        classes = MI.parse_cs(text)
        em.classes = {c.name: c for c in classes}
        c = em.classes[cls_name]
        project = M.default_project()
        new = M.new_power("gain")
        ok = powerconv.convert(em, c, new, project)
        return ok, new, project

    def test_turn_start_hook_becomes_native_trigger(self):
        ok, new, project = self.convert_text(GAIN, "GainPower")
        self.assertTrue(ok)
        self.assertEqual(new["trigger"], "turn_start")
        self.assertNotIn("clone", new)
        self.assertTrue(new["effects"][0]["blocks"])
        project["powers"] = [new]
        code = M.gen_power(project, new)
        self.assertIn("AfterPlayerTurnStart", code)
        self.assertIn("Trigger", code)

    def test_helper_method_keeps_original_csharp(self):
        ok, _new, _ = self.convert_text(HELPER, "HelperPower")
        self.assertFalse(ok)   # 도우미 메서드가 있으면 원본 C# 을 그대로 둔다


REMOVE = """using System.Threading.Tasks;
namespace Mod.Powers;
public sealed class OncePower : CustomPowerModel
{
    public override PowerType Type => PowerType.Buff;
    public override PowerStackType StackType => PowerStackType.Single;
    public override bool ShouldPlayVfx => false;
    public override Task AfterCardPlayed(PlayerChoiceContext ctx, CardPlay p)
    {
        if (p.Card.Owner.Creature != Owner || p.Card.Type != CardType.Attack)
        {
            return Task.CompletedTask;
        }
        return PowerCmd.Remove(this);
    }
}
"""


class RemoveOnPlayTests(unittest.TestCase):
    def test_remove_after_attack_is_card_played_power(self):
        ok, new, _ = PowerConvertTests().convert_text(REMOVE, "OncePower")
        self.assertTrue(ok)
        self.assertEqual(new["trigger"], "card_played")
        self.assertEqual(new["played_filter"], "Attack")
        self.assertEqual(new["played_by"], "owner")
        self.assertEqual(new["effects"][0]["blocks"][0]["op"], "remove_power_model")


if __name__ == "__main__":
    unittest.main()

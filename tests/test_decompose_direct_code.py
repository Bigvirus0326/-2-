import unittest
import blockcode as B
import csblocks
import modgen as M

BODY = """    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        int c = 2 + 1;
        Pile.Count++;
        if (c == 3) return;
        c += 2;
        await Task.CompletedTask;
        return;
    }"""


class DecomposeDirectCodeTests(unittest.TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.card["clone"] = {"body": BODY, "base": "", "orig_class": "X", "namespace": "N", "usings": []}
        self.blocks, _ = csblocks.decompose(self.card, [], {}, self.project)

    def ops(self, seq=None):
        out = []
        for b in seq or []:
            out.append(b["op"])
            for k in ("body", "else", "third"):
                out += self.ops(b.get(k))
        return out

    def test_early_return_becomes_block_not_raw_code(self):
        self.assertIsNotNone(self.blocks)
        self.assertIn("early_return", self.ops(self.blocks))
        self.assertNotIn("source_step", self.ops(self.blocks))

    def test_increment_and_plain_local_use_value_block(self):
        self.assertTrue(any(b.get("label", "").startswith("값 넣기") for b in self.blocks))

    def test_early_return_compiles_to_return(self):
        lines, errors = B.compile_blocks(self.blocks, self.project, M._Ctx("card", self.card))
        self.assertEqual(errors, [])
        code = "\n".join(lines)
        self.assertIn("return;", code)
        self.assertIn("c += 2;", code)
        self.assertIn("Pile.Count += 1;", code)


if __name__ == "__main__":
    unittest.main()


LOOP = """    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        foreach (Creature item in Enemies)
        {
            if (item == null) continue;
            if (item.IsDead) break;
        }
    }"""

LAMBDA = """    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)
    {
        Creature t = cardPlay.Target;
        var list = Enemies.Where(t => t.IsAlive).ToList();
        await CreatureCmd.Kill(t);
    }"""


class LoopAndAliasTests(unittest.TestCase):
    def decompose(self, body):
        project = M.default_project()
        card = project["cards"][0]
        card["clone"] = {"body": body, "base": "", "orig_class": "X", "namespace": "N", "usings": []}
        blocks, _ = csblocks.decompose(card, [], {}, project)
        return blocks

    def test_break_and_continue_become_blocks(self):
        ops = [b["op"] for b in csblocks._walk_blocks(self.decompose(LOOP))]
        self.assertIn("loop_break", ops)
        self.assertIn("loop_continue", ops)

    def test_alias_reused_as_lambda_parameter_is_not_replaced(self):
        text = " ".join(x for b in csblocks._walk_blocks(self.decompose(LAMBDA)) for x in csblocks._strings(b.get("args", {})))
        self.assertNotIn("cardPlay.Target =>", text)   # 람다의 t 를 원래 값으로 바꾸면 안 된다

import unittest
import blockcode as B
import modgen as M


class RandomCardBlockTests(unittest.TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]

    def compile(self, block):
        lines, errors = B.compile_blocks([block], self.project, M._Ctx("card", self.card))
        self.assertEqual(errors, [])
        return "\n".join(lines)

    def test_selection_is_distinct_and_completed_before_actions(self):
        block = B.new_block("random_each")
        block["args"]["count"] = {"t": "num", "v": 3}
        block["body"] = [B.new_block("picked_action"), B.new_block("picked_action")]
        block["body"][1]["args"]["action"] = "discard"
        code = self.compile(block)
        self.assertIn("CombatCardSelection.NextItem", code)
        self.assertIn(".Remove(", code)
        self.assertIn(".Count > 0", code)
        self.assertIn("!= this", code)
        self.assertNotIn(".Pick(", code)
        self.assertLess(code.index(".Add("), code.index("foreach"))
        self.assertLess(code.index("foreach"), code.index("CardCmd.Upgrade"))
        self.assertIn("CardCmd.Discard", code)
        self.assertIn("무작위 3장", B.describe([block], self.project, "card", "ko", self.card))

    def test_nested_selection_keeps_selected_card_scope(self):
        block = B.new_block("random_each")
        inner = B.new_block("random_each")
        inner["args"]["pile"] = "Discard"
        inner["body"] = [B.new_block("picked_action")]
        block["body"] = [inner, B.new_block("picked_action")]
        code = self.compile(block)
        self.assertEqual(code.count("CombatCardSelection.NextItem"), 2)
        self.assertEqual(code.count("CardCmd.Upgrade"), 2)
        self.assertIn("PileType.Discard", code)

    def test_zero_negative_counts_and_filter_are_preserved(self):
        for count in (0, -2, 20):
            block = B.new_block("random_each")
            block["args"]["ctype"] = "Attack"
            block["args"]["count"] = {"t": "num", "v": count}
            code = self.compile(block)
            self.assertIn("CardType.Attack", code)
            self.assertIn("-- > 0", code)
            self.assertIn("if (", code)

    def test_selected_cost_set_add_and_expirations(self):
        for mode in ("add", "set"):
            for duration, suffix in (("turn", "ThisTurn"), ("combat", "ThisCombat"), ("played", "UntilPlayed")):
                block = B.new_block("random_each")
                edit = B.new_block("card_cost_edit")
                edit["args"].update(edit_mode=mode, cost_duration=duration)
                block["body"] = [edit]
                code = self.compile(block)
                self.assertIn(".EnergyCost." + ("Add" if mode == "add" else "Set") + suffix, code)
                self.assertIn(".InvokeEnergyCostChanged()", code)
                self.assertIn(".EnergyCost.CostsX", code)
                self.assertIn(".EnergyCost.Canonical >= 0", code)
                self.assertIn("고른 카드", B.describe([block], self.project, "card", "ko", self.card))

    def test_selected_damage_changes_real_values_and_clamps(self):
        block = B.new_block("random_each")
        block["body"] = [B.new_block("card_cost_edit"), B.new_block("card_damage_edit")]
        code = self.compile(block)
        self.assertIn(".DynamicVars.Values.OfType<", code)
        self.assertIn("DynamicVars.DamageVar>", code)
        self.assertIn(".BaseValue + (3m)", code)
        self.assertIn("System.Math.Max(0m", code)
        self.assertNotIn(".PreviewValue =", code)
        block["body"][1]["args"]["edit_mode"] = "set"
        code = self.compile(block)
        self.assertIn(".BaseValue = System.Math.Max(0m, 3m)", code)

    def test_selected_numeric_change_requires_selection_scope(self):
        for op in ("card_cost_edit", "card_damage_edit"):
            _, errors = B.compile_blocks([B.new_block(op)], self.project, M._Ctx("card", self.card))
            self.assertTrue(errors)
            edit = B.new_block(op)
            edit["args"]["card"] = "this"
            self.compile(edit)

    def test_numeric_edits_work_in_manual_and_nested_selection(self):
        outer = B.new_block("pick_each")
        inner = B.new_block("random_each")
        edit = B.new_block("card_damage_edit")
        inner["body"] = [edit]
        outer["body"] = [inner, B.new_block("card_cost_edit")]
        self.compile(outer)

    def test_numeric_edits_reject_unknown_modes(self):
        for key, value in (("edit_mode", "invalid"), ("cost_duration", "invalid")):
            edit = B.new_block("card_cost_edit")
            edit["args"].update(card="this")
            edit["args"][key] = value
            _, errors = B.compile_blocks([edit], self.project, M._Ctx("card", self.card))
            self.assertTrue(errors)

    def test_unified_block_covers_all_numeric_choices(self):
        for stat in ("cost", "damage"):
            for mode in ("add", "set"):
                for duration in ("turn", "combat", "played"):
                    block = B.new_block("random_each")
                    edit = B.new_block("card_number_edit")
                    edit["args"].update(stat=stat,edit_mode=mode,duration=duration)
                    block["body"] = [edit]
                    code = self.compile(block)
                    if stat == "damage":
                        self.assertIn(".EditCardDamage(",code)
                        self.assertIn('"' + duration + '"',code)
                    else:
                        self.assertIn(".EnergyCost.",code)
                    text = B.describe([block],self.project,"card","ko",self.card)
                    self.assertIn("비용" if stat == "cost" else "피해",text)
                    self.assertIn(dict(B.COST_DURATIONS)[duration],text)

    def test_legacy_blocks_migrate_without_losing_settings(self):
        outer = B.new_block("random_each")
        cost,damage = B.new_block("card_cost_edit"),B.new_block("card_damage_edit")
        cost["args"].update(cost_duration="played",amount={"t":"num","v":-2},edit_mode="set")
        outer["body"] = [cost,damage]
        B.upgrade_numeric_blocks([outer])
        self.assertEqual(cost["op"],"card_number_edit")
        self.assertEqual(cost["args"]["duration"],"played")
        self.assertEqual(cost["args"]["amount"]["v"],-2)
        self.assertEqual(cost["args"]["edit_mode"],"set")
        self.assertEqual(damage["args"]["stat"],"damage")
        self.assertEqual(damage["args"]["duration"],"combat")
        palette = [op for _,ops in B.PALETTE for op in ops]
        self.assertIn("card_number_edit",palette)
        self.assertNotIn("card_cost_edit",palette)
        self.assertNotIn("card_damage_edit",palette)
        self.compile(outer)

    def test_all_card_stats_compile_and_describe(self):
        for stat,label in B.CARD_STATS:
            for duration in ("turn", "played", "combat"):
                block = B.new_block("random_each")
                edit = B.new_block("card_number_edit")
                edit["args"].update(stat=stat,duration=duration)
                block["body"] = [edit]
                code = self.compile(block)
                if stat not in ("cost", "damage"):
                    self.assertIn('.EditCardNumber(',code)
                    self.assertIn('"'+stat+'"',code)
                self.assertIn(label,B.describe([block],self.project,"card","ko",self.card))

    def test_block_numbers_feed_execution_description_and_upgrades(self):
        blocks = [B.new_block(op) for op in ("block","draw","energy","heal","lose_hp","max_hp","gold")]
        for block in blocks:
            block["args"]["amount"] = {"t":"num","v":2,"up":1}
        card = M.new_card("numeric_test")
        card["effects"] = [{"kind":"custom","amount":0,"blocks":blocks}]
        variables=M.block_number_vars(card)
        self.assertEqual(len(variables),7)
        for block,name,_ in variables:
            self.assertEqual(M.block_number_name(card,block),name)
            code,errors=B.compile_blocks([block],self.project,M._Ctx("card",card))
            self.assertEqual(errors,[])
            self.assertIn('DynamicVars["'+name+'"].BaseValue',"\n".join(code))
            self.assertIn('{'+name+':diff()}',B.describe([block],self.project,"card","ko",card))
        canonical="\n".join(M._canonical_vars(self.project,card,"card"))
        self.assertIn('new CardsVar("MakerBlockCards1", (int)(2m))',canonical)
        self.assertEqual(len(M.block_damage_upgrades(card)),7)

    def test_compact_pairs_preserve_old_behavior_and_migrate(self):
        import copy
        for legacy,(compact,key,value) in B.COMPACT_ALIASES.items():
            old=B.new_block(legacy)
            migrated=copy.deepcopy(old)
            B.upgrade_numeric_blocks([migrated])
            self.assertEqual(migrated["op"],B.compact_op(compact))
            self.assertEqual(migrated["args"][key],value)
            if legacy.startswith("button_"):
                import fxbtn
                self.project.setdefault("gimmicks",{})["buttons"]=[fxbtn.new_button("test_button")]
                old["args"]["button"]=migrated["args"]["button"]="test_button"
            self.assertEqual(self.compile(old),self.compile(migrated))
            self.assertEqual(B.describe([old],self.project,"card"),B.describe([migrated],self.project,"card"))
            self.assertEqual(B.describe([old],self.project,"card","zh"),B.describe([migrated],self.project,"card","zh"))
            palette=[op for _,ops in B.PALETTE for op in ops]
            self.assertIn(B.compact_op(compact),palette)
            self.assertNotIn(legacy,palette)


if __name__ == "__main__":
    unittest.main()

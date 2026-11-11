import copy
import unittest
from types import SimpleNamespace
import blockcode as B
import modgen as M
import gimmick as G
import aipaste
import aiguide


class BlockFamilyTests(unittest.TestCase):
    def setUp(self):
        self.project=M.default_project()
        G.normalize(self.project)
        self.card=self.project["cards"][0]

    def compile(self,blocks,card=None):
        return B.compile_blocks(blocks,self.project,M._Ctx("card",card or self.card))

    def test_every_legacy_variant_compiles_and_describes_identically(self):
        for family,_title,variants in B.F.GROUPS:
            for old,_label in variants:
                with self.subTest(family=family,old=old):
                    block=B.new_block(old)
                    if B.SPECS[old].get("body"):
                        block["body"]=[B.new_block("energy")]
                    if B.SPECS[old].get("else"):
                        block["else"]=[B.new_block("gold")]
                    before=self.compile([block])
                    texts=[B.describe([block],self.project,"card",lang,self.card) for lang in ("ko","en","zh")]
                    migrated=copy.deepcopy(block)
                    B.upgrade_numeric_blocks([migrated])
                    self.assertEqual(migrated["op"],family)
                    self.assertEqual(self.compile([migrated]),before)
                    self.assertEqual([B.describe([migrated],self.project,"card",lang,self.card) for lang in ("ko","en","zh")],texts)

    def test_card_selection_switch_preserves_conditions_and_children(self):
        block=B.new_block("select_cards")
        block["args"].update(pile="Discard",ctype="Attack",count={"t":"num","v":3,"up":1})
        edit=B.new_block("card_number_edit")
        block["body"]=[edit]
        for mode in ("random_each","pick_each","random_each"):
            B.F.switch(block,mode,B.SPECS)
            self.assertIs(block["body"][0],edit)
            self.assertEqual(block["args"]["pile"],"Discard")
            self.assertEqual(block["args"]["count"],{"t":"num","v":3,"up":1})
            lines,errors=self.compile([block])
            self.assertEqual(errors,[])
            code="\n".join(lines)
            self.assertIn("CombatCardSelection.NextItem" if mode=="random_each" else ".Pick(",code)
            self.assertIn(".EnergyCost.AddThisCombat",code)

    def test_variant_fields_and_branch_bodies_survive_round_trip(self):
        block=B.new_block("condition_branch")
        B.F.switch(block,"if_else",B.SPECS)
        effect=B.new_block("gold")
        block["else"]=[effect]
        B.F.switch(block,"if",B.SPECS)
        self.assertFalse(B.block_spec(block).get("else"))
        B.F.switch(block,"if_else",B.SPECS)
        self.assertIs(block["else"][0],effect)
        block=B.new_block("wait_action")
        block["args"]["duration"]={"t":"num","v":7}
        B.F.switch(block,"wait_scaled",B.SPECS)
        self.assertNotIn("duration",B.block_spec(block)["args"])
        block["args"]["minimum"]="0.7f"
        B.F.switch(block,"wait",B.SPECS)
        self.assertEqual(block["args"]["duration"]["v"],7)
        B.F.switch(block,"wait_scaled",B.SPECS)
        self.assertEqual(block["args"]["minimum"],"0.7f")

    def test_merged_numeric_blocks_keep_runtime_variables(self):
        card=M.new_card("family_numbers")
        blocks=[B.new_block(op) for op in ("damage","block","draw","energy","heal","lose_hp","max_hp","gold")]
        card["effects"]=[M.new_effect("code")]
        card["effects"][0]["blocks"]=blocks
        before=self.compile(blocks,card)
        canonical=M._canonical_vars(self.project,card,"card")
        names=[name for _,name,_ in M.block_number_vars(card)]
        B.upgrade_numeric_blocks(blocks)
        self.assertEqual(self.compile(blocks,card),before)
        self.assertEqual(M._canonical_vars(self.project,card,"card"),canonical)
        self.assertEqual([name for _,name,_ in M.block_number_vars(card)],names)
        self.assertTrue(all('DynamicVars["'+name+'"].BaseValue' in "\n".join(before[0]) for name in names))

    def test_palette_has_each_family_once_and_search_keeps_old_names(self):
        ops=[op for _,group in B.PALETTE for op in group]
        for family,_title,variants in B.F.GROUPS:
            self.assertEqual(ops.count(family),1)
            for old,_label in variants:
                self.assertNotIn(old,ops)
                self.assertIn(old,B.F.keywords(family,B.SPECS))
                self.assertEqual(B.compact_op(old),family)

    def test_invalid_modes_report_errors_instead_of_executing_a_default(self):
        for mode in ("missing",{},None):
            block=B.new_block("select_cards")
            block["args"]["mode"]=mode
            _,errors=self.compile([block])
            self.assertTrue(errors)

    def test_ai_import_uses_selected_variant_schema_and_body(self):
        ctx={"project_view":self.project,"powers":set(),"power_names":{},"summons":set(),"orbs":set()}
        patch=aipaste.Patch()
        source=[{"op":"condition_branch","args":{"mode":"if_else","cond":{"t":"chance","pct":{"t":"num","v":50}}},
                 "else":[{"op":"draw_action","args":{"mode":"draw_bottom","pos":-1,"count":2}}]}]
        result=aipaste._fix_blocks(source,ctx,"test",patch)
        self.assertEqual(patch.errors,[])
        self.assertEqual(patch.fixes,[])
        self.assertEqual(result[0]["else"][0]["args"]["count"]["v"],2)
        self.assertIn("draw_bottom",aiguide._blocks_reference())
        self.assertIn("random_each",aiguide._blocks_reference())

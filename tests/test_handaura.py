import copy
import unittest
import blockcode as B
import gimmick as G
import handaura as H
import modgen as M

class HandAuraTests(unittest.TestCase):
    def setUp(self):
        self.p=G.normalize(M.default_project())
        self.card=self.p["cards"][0]
        self.tag=G.new_tag("burst")
        self.p["gimmicks"]["tags"]=[self.tag]

    def test_all_stats_keyword_filter_and_conditions(self):
        blocks=[]
        for stat in ("cost","damage","block"):
            b=B.new_block("hand_aura_stat")
            b["args"].update(stat=stat,filter="kw:Exhaust",amount={"t":"num","v":-1 if stat=="cost" else 3})
            blocks.append(b)
        condition=B.new_block("if")
        condition["args"]["cond"]={"t":"cmp","a":{"t":"num","v":1},"op":">=","b":{"t":"num","v":1}}
        condition["body"]=blocks
        self.tag["event_blocks"]["hand_aura"]=[condition]
        original=copy.deepcopy(self.p)
        code=M.gen_card(self.p,self.card)
        for method in ("TryModifyEnergyCostInCombat","ModifyDamageAdditive","ModifyBlockAdditive"):
            self.assertIn(method,code)
        self.assertIn("cardSource.Keywords.Contains(CardKeyword.Exhaust)",code)
        self.assertIn("r += (3m)",code)
        self.assertEqual(self.p,original)

    def test_legacy_cost_setting_migrates_exactly_once(self):
        self.tag.update(hand_cost_enabled=True,hand_cost_amount=2,hand_cost_filter="kw:Retain")
        G.normalize(self.p)
        tag=G.tags(self.p)[0]
        self.assertFalse(tag["hand_cost_enabled"])
        self.assertEqual(len(H.blocks(tag)),1)
        self.assertEqual(H.blocks(tag)[0]["args"]["amount"]["v"],-2)
        G.normalize(self.p)
        self.assertEqual(len(H.blocks(G.tags(self.p)[0])),1)

    def test_imperative_and_unstable_actions_rejected(self):
        for block in (B.new_block("draw"), {"op":"hand_aura_stat","args":{"amount":{"t":"rand","min":0,"max":4}}}):
            self.tag["event_blocks"]["hand_aura"]=[block]
            with self.assertRaises(ValueError): H.rules(self.p,self.card,self.tag)
        _, errors=B.compile_blocks([B.new_block("hand_aura_stat")], self.p,M._Ctx("card",self.card))
        self.assertTrue(errors)

    def test_pile_defaults_and_invalid_selection(self):
        block=B.new_block("hand_aura_stat")
        self.assertEqual(block["args"]["active_pile"],"Hand")
        self.tag["event_blocks"]["hand_aura"]=[block]
        for pile in ("Hand","Draw","Discard"):
            block["args"]["active_pile"]=pile
            code=M.gen_card(self.p,self.card)
            self.assertIn("PileType."+pile+".GetPile(Owner).Cards.Contains(this)",code)
        del block["args"]["active_pile"]
        self.assertIn("PileType.Hand.GetPile(Owner)",M.gen_card(self.p,self.card))
        block["args"]["active_pile"]="Invalid"
        with self.assertRaises(ValueError): H.rules(self.p,self.card,self.tag)

    def test_target_pile_and_stored_power_effect(self):
        block=B.new_block("hand_aura_stat")
        block["args"].update(active_pile="Discard",target_pile="Hand",stat="damage",filter="kw:Exhaust")
        grant=B.new_block("aura_card_effect")
        grant["args"].update(active_pile="Discard",target_pile="Hand",filter="kw:Exhaust")
        power=B.new_block("apply_power")
        power["args"].update(who="self",power="Strength",amount={"t":"num","v":2})
        grant["body"]=[power]
        self.tag["event_blocks"]["hand_aura"]=[block,grant]
        code=M.gen_card(self.p,self.card)
        self.assertIn("MakerAuraMatchesPile(cardSource, PileType.Hand)",code)
        self.assertIn("MakerAuraMatchesPlayedPile(cardPlay.Card, PileType.Hand)",code)
        self.assertIn("StrengthPower>(choiceContext, Owner.Creature, this, 2m)",code)
        block["args"]["target_pile"]="Invalid"
        with self.assertRaises(ValueError): H.rules(self.p,self.card,self.tag)

    def test_existing_power_amount_has_typed_filter(self):
        boost=B.new_block("aura_power_amount")
        boost["args"].update(active_pile="Discard",target_pile="Hand",filter="kw:Exhaust",power_filter="Strength")
        self.tag["event_blocks"]["hand_aura"]=[boost]
        code=M.gen_card(self.p,self.card)
        self.assertIn("ModifyPowerAmountGivenAdditive",code)
        self.assertIn("power is global::MegaCrit.Sts2.Core.Models.Powers.StrengthPower",code)
        self.assertIn("giver == Owner.Creature && amount > 0",code)
        self.assertIn("r += (2m)",code)
        boost["args"]["power_filter"]="missing"
        with self.assertRaises(ValueError): H.rules(self.p,self.card,self.tag)

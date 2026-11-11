import unittest
import blockcode as B
import blockhelp as H
import modgen as M


class BeginnerHelpTests(unittest.TestCase):
    def test_every_visible_block_and_slot_has_help(self):
        for _,ops in B.PALETTE:
            for op in ops:
                block=B.new_block(op)
                variants=B.F.FAMILIES[op][1] if op in B.F.FAMILIES else [(op,op)]
                for mode,_ in variants:
                    if op in B.F.FAMILIES:
                        B.F.switch(block,mode,B.SPECS)
                    with self.subTest(op=op,mode=mode):
                        self.assertTrue(H.block_help(block).strip())
                        for key,(kind,_) in B.block_spec(block)["args"].items():
                            self.assertIn(kind,H.TERMS)
                            self.assertTrue(H.field_help(block,key).strip())

    def test_number_and_condition_choices_have_explanations(self):
        for kind,choices in (("value",B.VALUE_TYPES),("cond",B.COND_TYPES)):
            for code,_label in choices:
                self.assertIn(code,H.SLOT_HELP)
                self.assertTrue(H.slot_help(kind,code))

    def test_preview_labels_and_explanations_distinguish_actual_effects(self):
        for op in ("card_preview","card_preview_cards"):
            block=B.new_block(op)
            self.assertIn("표시 시간",B.block_caption(block))
            self.assertNotIn("크기",B.block_caption(block))
            self.assertIn("초",H.field_help(block,"scale"))
            self.assertIn("크기를 바꾸는 값이 아닙니다",H.field_help(block,"scale"))
        block=B.new_block("upgrade_card_action")
        self.assertIn("실제로 강화",H.block_help(block))
        self.assertIn("기본 배치",H.field_help(block,"style"))
        B.F.switch(block,"card_finalize_upgrade_internal",B.SPECS)
        self.assertIn("이 동작만으로 카드를 강화하지는",H.block_help(block))

    def test_preview_styles_keep_legacy_input_and_use_real_enum_names(self):
        project=M.default_project()
        for value,_label in B.PREVIEW_STYLES:
            block=B.new_block("card_upgrade")
            block["args"].update(card="this",style=value)
            lines,errors=B.compile_blocks([block],project,M._Ctx("card",project["cards"][0]))
            self.assertEqual(errors,[])
            self.assertIn("CardCmd.Upgrade", "\n".join(lines))
        self.assertEqual(B.preview_style_expr("CardPreviewStyle.Default"),"")
        self.assertTrue(B.preview_style_expr("CardPreviewStyle.GridLayout").startswith("global::"))
        self.assertEqual(B.preview_style_expr("customStyle"),"customStyle")
        block=B.new_block("card_preview")
        block["args"]["style"]="CardPreviewStyle.Default"
        code,_=B.compile_blocks([block],project,M._Ctx("card",project["cards"][0]))
        self.assertNotIn("CardPreviewStyle.Default","\n".join(code))
        self.assertIn("CardPreviewStyle.HorizontalLayout","\n".join(code))
        self.assertIn("card_upgrade",B.MANUAL_MAP_OPS)

    def test_preview_choices_avoid_invalid_combat_layouts_and_none_skips_display(self):
        options=dict(B.preview_style_options("card_preview"))
        self.assertFalse(any(value.endswith(("GridLayout","EventLayout")) for value in options))
        self.assertTrue(any(value.endswith("GridLayout") for value,_ in B.preview_style_options("card_upgrade")))
        project=M.default_project()
        block=B.new_block("card_preview")
        block["args"]["style"]="CardPreviewStyle.None"
        lines,errors=B.compile_blocks([block],project,M._Ctx("card",project["cards"][0]))
        self.assertEqual(errors,[])
        self.assertNotIn("PreviewCardPileAdd","\n".join(lines))

    def test_common_terms_have_beginner_examples(self):
        for kind,word in (("number_edit","-1"),("card_ref","고른 카드"),("gtag","폭발"),("clone_policy","복사"),("power","중첩")):
            self.assertIn(word,H.TERMS[kind])

import unittest
from types import SimpleNamespace
import blockcode as B
import blockui
import modgen as M

class CodeChoiceTests(unittest.TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.editor = SimpleNamespace(project=self.project, item=self.card, owner_kind="card")

    def choices(self, op, key):
        return blockui.BlockEditor._code_choices(self.editor, op, key)

    def compile(self, blocks):
        lines, errors = B.compile_blocks(blocks, self.project, M._Ctx("card", self.card))
        self.assertEqual(errors, [])
        return "\n".join(lines)

    def test_project_types_and_plain_choices(self):
        for op, key in (("card_transform_to", "card_type"), ("orb_channel_type", "orb_type"),
                        ("apply_power_type", "power_type"), ("potion_add_type", "potion_type")):
            choices = self.choices(op, key)
            if key != "potion_type" or self.project.get("potions"):
                self.assertTrue(choices)
        self.assertIn("이 카드", self.choices("card_upgrade", "card"))
        self.assertIn("자신", self.choices("damage_to", "creature"))
        self.assertIn("공격 동작", self.choices("trigger_creature_anim", "animation"))

    def test_picked_card_resolves_inside_selection_only(self):
        child = B.new_block("card_upgrade")
        child["args"]["card"] = "@picked_card"
        parent = B.new_block("random_each")
        parent["body"] = [child]
        code = self.compile([parent])
        self.assertIn("CardCmd.Upgrade", code)
        self.assertNotIn("@picked", code)
        _, errors = B.compile_blocks([child], self.project, M._Ctx("card", self.card))
        self.assertTrue(errors)

    def test_code_field_is_readonly_and_preserves_imported_expression(self):
        import tkinter as tk
        from tkinter import ttk
        root = tk.Tk()
        root.withdraw()
        self.editor._changed = lambda: None
        self.editor._code_choices = self.choices
        block = B.new_block("card_upgrade")
        block["args"]["card"] = "originalImportedCard"
        try:
            widget = blockui.BlockEditor._make_arg_widget(self.editor, root, block, "card", "code")
            combo = next(w for w in widget.winfo_children() if isinstance(w, ttk.Combobox))
            self.assertEqual(str(combo.cget("state")), "readonly")
            self.assertEqual(combo.get_value(), "originalImportedCard")
            self.assertNotIn("originalImportedCard", combo.get())
            combo.set_value("this")
            combo.event_generate("<<ComboboxSelected>>")
            self.assertEqual(block["args"]["card"], "this")
        finally:
            root.destroy()

    def test_power_instance_choices_skip_missing_power(self):
        choices = self.choices("remove_power_model", "power")
        for prefix in ("@own_power:", "@target_power:"):
            value = next(v for v in choices.values() if v.startswith(prefix))
            block = B.new_block("remove_power_model")
            block["args"]["power"] = value
            code = self.compile([block])
            self.assertIn("?.GetPower<", code)
            self.assertIn("!= null", code)
            self.assertIn("PowerCmd.Remove", code)
            self.assertNotIn(prefix, code)

if __name__ == "__main__":
    unittest.main()

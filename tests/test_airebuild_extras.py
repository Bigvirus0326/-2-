import json
import os
import sys
from unittest import TestCase, skipUnless

import airebuild as AR
import modgen as M

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False


def _card_with_raw():
    project = M.default_project()
    card = project["cards"][0]
    card["effects"] = [dict(M.new_effect("code"), blocks=[
        {"op": "source_step", "args": {"source": "List<CardModel> list = PileType.Hand.GetPile(Owner).Cards.ToList();"}},
        {"op": "draw", "args": {"amount": {"t": "num", "v": 1}}}])]
    return project, card


def _ans(obj):
    return "```json\n" + json.dumps(dict({"format": "sts2mod-patch"}, **obj), ensure_ascii=False) + "\n```"


def _power_effect(power_id):
    return dict(M.new_effect("power"), power=f"c:{power_id}", amount=1, target="self")


class PlanTests(TestCase):
    def test_new_power_and_gimmick_are_added_with_the_card(self):
        project, card = _card_with_raw()
        answer = _ans({
            "cards": [{"id": card["id"], "effects": [_power_effect("frost")]}],
            "powers": [{"id": "frost", "name_ko": "서리", "name_en": "Frost", "type": "Buff"}],
            "gimmicks": {"tags": [{"id": "ice", "name_ko": "얼음"}]}})
        plan, notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertIsNotNone(plan)
        self.assertCountEqual([(x["kind"], x["item"]["id"]) for x in plan["adds"]], [("power", "frost"), ("tag", "ice")])
        self.assertEqual(AR.plan_errors(project, plan), [])
        AR.apply_plan(project, plan)
        self.assertIn("frost", [p["id"] for p in project["powers"]])
        self.assertEqual([t["id"] for t in project["gimmicks"]["tags"]], ["ice"])
        self.assertEqual(card["effects"][0]["power"], "c:frost")

    def test_unused_power_can_be_removed(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("old_power"))
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}]}],
                       "remove": [{"kind": "power", "id": "old_power"}]})
        plan, notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertEqual(plan["removes"], [("power", "old_power")])
        self.assertEqual(AR.plan_errors(project, plan), [])
        AR.apply_plan(project, plan)
        self.assertNotIn("old_power", [p["id"] for p in project["powers"]])

    def test_removing_a_power_another_card_uses_is_refused(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("kindling"))
        project["cards"][1]["effects"] = [_power_effect("kindling")]
        before = len(project["powers"])
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}]}],
                       "remove": [{"kind": "power", "id": "kindling"}]})
        plan, _notes = AR.plan_answer(project, [("card", card)], answer)
        errors = AR.plan_errors(project, plan)
        self.assertTrue(any("kindling" in e for e in errors))
        self.assertEqual(len(project["powers"]), before)   # 검사 중에는 프로젝트를 건드리지 않는다

    def test_remove_of_unknown_or_bad_entries_is_reported(self):
        project, card = _card_with_raw()
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}]}],
                       "remove": [{"kind": "power", "id": "nope"}, {"kind": "card", "id": card["id"]}]})
        plan, notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertEqual(plan["removes"], [])
        self.assertTrue(any("프로젝트에 없어" in n for n in notes))
        self.assertTrue(any("알 수 없습니다" in n for n in notes))

    def test_existing_power_in_answer_is_kept_not_edited(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("kindling"))
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}]}],
                       "powers": [{"id": "kindling", "name_ko": "바뀜"}]})
        plan, notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertEqual(plan["adds"], [])
        self.assertTrue(any("바꾸지 않습니다" in n for n in notes))

    def test_answer_without_extras_has_no_check_cost(self):
        project, card = _card_with_raw()
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 2}]}]})
        plan, _notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertEqual(AR.plan_errors(project, plan), [])
        self.assertEqual(AR.plan_lines(plan), [])

    def test_card_resource_and_play_condition_come_from_the_answer(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("kindling"))
        cond = {"t": "cmp", "a": {"t": "energy"}, "op": ">=", "b": {"t": "num", "v": 1}}
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}],
                                  "res_power": "c:kindling", "res_cost": 3, "play_cond": cond}]})
        plan, _notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertEqual(plan["cardfields"][("card", card["id"])]["res_cost"], 3)
        self.assertEqual(AR.plan_errors(project, plan), [])
        AR.apply_plan(project, plan)
        self.assertEqual((card["res_power"], card["res_cost"]), ("c:kindling", 3))
        self.assertEqual(card["play_cond"]["op"], ">=")

    def test_card_resource_pointing_at_a_missing_power_is_refused(self):
        project, card = _card_with_raw()
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}],
                                  "res_power": "c:nope", "res_cost": 2}]})
        plan, notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertIsNone(plan)
        self.assertTrue(any("nope" in n for n in notes))

    def test_card_without_resource_keys_keeps_its_values(self):
        project, card = _card_with_raw()
        card["star_cost"] = 2
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}]}]})
        plan, _notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertEqual(plan["cardfields"], {})
        AR.apply_plan(project, plan)
        self.assertEqual(card["star_cost"], 2)

    def test_answer_that_drops_an_original_if_gets_a_warning(self):
        project, card = _card_with_raw()
        card["effects"] = [dict(M.new_effect("code"), blocks=[
            {"op": "source_step", "args": {"source": "if (Owner.Creature.CurrentHp > 5) {"}},
            {"op": "source_step", "args": {"source": "Foo();"}}])]
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "code", "auto_text": True, "blocks": [
            {"op": "draw", "args": {"amount": {"t": "num", "v": 1}}}]}]}]})
        plan, notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertIn(("card", card["id"]), plan["effects"])
        self.assertTrue(any("조건문(if)이 1개" in n for n in notes))

    def test_answer_that_keeps_the_if_has_no_warning(self):
        project, card = _card_with_raw()
        card["effects"] = [dict(M.new_effect("code"), blocks=[
            {"op": "source_step", "args": {"source": "if (Owner.Creature.CurrentHp > 5) {"}}])]
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "code", "auto_text": True, "blocks": [
            {"op": "if", "args": {"cond": {"t": "cmp", "a": {"t": "energy"}, "op": ">=", "b": {"t": "num", "v": 1}}},
             "body": [{"op": "draw", "args": {"amount": {"t": "num", "v": 1}}}]}]}]}]})
        plan, notes = AR.plan_answer(project, [("card", card)], answer)
        self.assertIn(("card", card["id"]), plan["effects"])
        self.assertFalse(any("조건문" in n for n in notes))

    def test_request_asks_to_keep_if_conditions(self):
        project, card = _card_with_raw()
        card["effects"][0]["blocks"][0]["args"]["source"] = "if (Owner.Creature.CurrentHp > 5) {"
        text = AR.request_text(project, "card", card)
        self.assertIn("조건문(if)이 1곳", text)
        self.assertIn("if 블록", text)

    def test_short_text_from_the_answer_becomes_the_card_description(self):
        project, card = _card_with_raw()
        answer = _ans({"cards": [{"id": card["id"], "effects": [{"kind": "code", "auto_text": False,
                                                                  "text_ko": "포격 2: 피해를 8 줍니다",
                                                                  "blocks": [{"op": "draw", "args": {"amount": {"t": "num", "v": 1}}}]}]}]})
        plan, _notes = AR.plan_answer(project, [("card", card)], answer)
        AR.apply_plan(project, plan)
        self.assertIn("포격 2: 피해를 8 줍니다", M.description(project, card, "card", "ko"))

    def test_prompt_documents_the_short_text_fields(self):
        import aiguide as AG
        self.assertIn("text_ko", AG.build_prompt(M.default_project(), ""))
        project, card = _card_with_raw()
        self.assertIn("짧은 설명", AR.request_text(project, "card", card))

    def test_payment_code_is_explained_as_resource_cost(self):
        self.assertIn("자원", AR.explain("if (!await H.Pay<KindlingPower>(choiceContext, Owner, 3m, this)) return;"))

    def test_request_tells_the_ai_about_adds_and_removes(self):
        project, card = _card_with_raw()
        text = AR.request_text(project, "card", card)
        self.assertIn('"remove"', text)
        self.assertIn("새 ID", text)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class DialogExtrasTests(TestCase):
    def setUp(self):
        self.app = QApplication.instance() or QApplication(sys.argv)
        import airebuildqt as R
        self.R = R
        self._orig_confirm = R._confirm_removes
        R._confirm_removes = lambda parent, plan: True   # 지우기 확인 창을 자동으로 '예'
        self.addCleanup(setattr, R, "_confirm_removes", self._orig_confirm)

    def test_single_dialog_adds_and_removes_on_take(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("old_power"))
        dialog = self.R.RebuildDialogQt(None, project, "card", card)
        self.addCleanup(dialog.close)
        dialog.answer.setPlainText(_ans({
            "cards": [{"id": card["id"], "effects": [_power_effect("frost")]}],
            "powers": [{"id": "frost", "name_ko": "서리"}],
            "remove": [{"kind": "power", "id": "old_power"}]}))
        dialog.read()
        self.assertTrue(dialog.take.isEnabled())
        dialog.take_changes()
        self.assertIn("frost", [p["id"] for p in project["powers"]])
        self.assertNotIn("old_power", [p["id"] for p in project["powers"]])
        self.assertEqual(dialog.effects[0]["power"], "c:frost")

    def test_single_dialog_blocks_take_when_removal_breaks_a_reference(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("kindling"))
        project["cards"][1]["effects"] = [_power_effect("kindling")]
        dialog = self.R.RebuildDialogQt(None, project, "card", card)
        self.addCleanup(dialog.close)
        dialog.answer.setPlainText(_ans({
            "cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}]}],
            "remove": [{"kind": "power", "id": "kindling"}]}))
        dialog.read()
        self.assertFalse(dialog.take.isEnabled())
        self.assertIn("kindling", dialog.result.text())

    def test_batch_dialog_applies_adds_and_removes_for_its_group(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("old_power"))
        dialog = self.R.BatchRebuildDialogQt(None, project, AR.targets(project))
        self.addCleanup(dialog.close)
        dialog.answer.setPlainText(_ans({
            "cards": [{"id": card["id"], "effects": [_power_effect("frost")]}],
            "powers": [{"id": "frost", "name_ko": "서리"}],
            "gimmicks": {"tags": [{"id": "ice", "name_ko": "얼음"}]},
            "remove": [{"kind": "power", "id": "old_power"}]}))
        dialog.apply()
        self.assertEqual(dialog.changed, 1)
        self.assertIn("frost", [p["id"] for p in project["powers"]])
        self.assertNotIn("old_power", [p["id"] for p in project["powers"]])
        self.assertEqual([t["id"] for t in project["gimmicks"]["tags"]], ["ice"])
        self.assertEqual(card["effects"][0]["power"], "c:frost")

    def test_batch_dialog_refuses_group_that_would_break_references(self):
        project, card = _card_with_raw()
        project["powers"].append(M.new_power("kindling"))
        project["cards"][1]["effects"] = [_power_effect("kindling")]
        dialog = self.R.BatchRebuildDialogQt(None, project, AR.targets(project, [card]))
        self.addCleanup(dialog.close)
        before = [dict(e) for e in card["effects"]]
        powers_before = len(project["powers"])
        dialog.answer.setPlainText(_ans({
            "cards": [{"id": card["id"], "effects": [{"kind": "draw", "amount": 1}]}],
            "remove": [{"kind": "power", "id": "kindling"}]}))
        dialog.apply()
        self.assertEqual(dialog.changed, 0)
        self.assertEqual(card["effects"], before)
        self.assertEqual(len(project["powers"]), powers_before)

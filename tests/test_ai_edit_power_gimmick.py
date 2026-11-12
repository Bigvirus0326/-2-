import copy
import json
import unittest

import aiguide as AG
import aipaste as AP
import modgen as M


def _answer(obj):
    return "```json\n" + json.dumps(obj, ensure_ascii=False) + "\n```"


def _project():
    p = M.default_project()
    power = M.new_power("kindling")
    power["name_ko"] = "불쏘시개"
    power["effects"] = [{"kind": "block", "amount": 2, "per_stack": True}]
    p["powers"].append(power)
    p["gimmicks"] = {"tags": [{"id": "fire", "name_ko": "불", "name_en": "Fire", "desc_ko": "불 태그"}]}
    return p


class PartialPowerEditTests(unittest.TestCase):
    def test_partial_power_edit_keeps_unlisted_fields(self):
        p = _project()
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG, "powers": [{"id": "kindling", "stack": "Single"}]}), p)
        self.assertEqual(patch.errors, [])
        item = patch.items[0]["item"]
        self.assertTrue(patch.items[0]["exists"])
        self.assertEqual(item["stack"], "Single")
        self.assertEqual(item["name_ko"], "불쏘시개")
        self.assertEqual(item["effects"][0]["amount"], 2)

    def test_power_effects_are_replaced_only_when_given(self):
        p = _project()
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG,
                                       "powers": [{"id": "kindling", "effects": [{"kind": "block", "amount": 5}]}]}), p)
        self.assertEqual(patch.errors, [])
        self.assertEqual(patch.items[0]["item"]["effects"][0]["amount"], 5)

    def test_new_power_still_uses_defaults(self):
        p = _project()
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG, "powers": [{"id": "frost", "name_ko": "서리"}]}), p)
        item = patch.items[0]["item"]
        self.assertFalse(patch.items[0]["exists"])
        self.assertEqual(item["name_ko"], "서리")
        self.assertEqual(item["type"], "Buff")

    def test_card_partial_edit_still_builds_fresh_item(self):
        p = _project()
        p["cards"].append(M.new_card("slash"))
        p["cards"][-1]["name_ko"] = "베기"
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG, "cards": [{"id": "slash", "cost": 2}]}), p)
        self.assertEqual(patch.items[0]["item"]["cost"], 2)
        self.assertEqual(patch.items[0]["item"]["name_ko"], "새 카드")


class GimmickEditCreateTests(unittest.TestCase):
    def test_partial_gimmick_edit_keeps_other_fields(self):
        p = _project()
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG, "gimmicks": {"tags": [{"id": "fire", "name_ko": "화염"}]}}), p)
        self.assertEqual(patch.errors, [])
        item = patch.items[0]["item"]
        self.assertTrue(patch.items[0]["exists"])
        self.assertEqual(item["name_ko"], "화염")
        self.assertEqual(item["desc_ko"], "불 태그")

    def test_new_gimmick_is_added_on_apply(self):
        p = _project()
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG,
                                       "gimmicks": {"summons": [{"id": "ember_imp", "name_ko": "불씨 악마"}]}}), p)
        self.assertEqual(patch.errors, [])
        self.assertFalse(patch.items[0]["exists"])
        added = AP.apply(p, patch)
        self.assertEqual(added, [("summon", "ember_imp")])
        self.assertEqual([s["name_ko"] for s in p["gimmicks"]["summons"]], ["불씨 악마"])

    def test_edit_applies_in_place_and_keeps_image(self):
        p = _project()
        p["gimmicks"]["tags"][0]["image"] = "keep.png"
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG, "gimmicks": {"tags": [{"id": "fire", "name_ko": "화염"}]}}), p)
        AP.apply(p, patch)
        self.assertEqual(len(p["gimmicks"]["tags"]), 1)
        self.assertEqual(p["gimmicks"]["tags"][0]["name_ko"], "화염")
        self.assertEqual(p["gimmicks"]["tags"][0]["image"], "keep.png")

    def test_gimmick_group_error_still_reported(self):
        p = _project()
        patch = AP.read_patch(_answer({"format": AG.FORMAT_TAG, "gimmicks": {"unknown": []}}), p)
        self.assertTrue(any("지원하지 않는 기믹 종류" in e for e in patch.errors))


class PromptTests(unittest.TestCase):
    def test_prompt_includes_current_power_and_gimmick_contents(self):
        prompt = AG.build_prompt(_project(), "불쏘시개 고쳐줘")
        self.assertIn("## 지금 있는 파워·기믹 전체 내용", prompt)
        self.assertIn('"kindling"', prompt)
        self.assertIn('"불 태그"', prompt)
        self.assertNotIn('"image"', AG.current_items_json(_project()))

    def test_prompt_documents_gimmick_creation_in_format_section(self):
        prompt = AG.build_prompt(_project(), "")
        self.assertIn("## 기믹 (gimmicks)", prompt)
        self.assertLess(prompt.index("## 기믹 (gimmicks)"), prompt.index("## 사용자의 요청"))

    def test_prompt_without_project_has_no_current_section(self):
        prompt = AG.build_prompt(_project(), "", include_project=False)
        self.assertNotIn("## 지금 있는 파워·기믹 전체 내용", prompt)

    def test_current_items_json_empty_for_plain_project(self):
        p = M.default_project()
        p["powers"] = []
        self.assertEqual(AG.current_items_json(p), "")


if __name__ == "__main__":
    unittest.main()

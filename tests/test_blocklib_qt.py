import os
import sys
import tempfile
from pathlib import Path
from unittest import TestCase, skipUnless, mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QAbstractItemView, QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

import blocklibqt as L
import blockcode as B
import modgen as M

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import blockqt as BQ


def _card_block():
    """카드를 고르는 칸이 있는 블록 하나와 그 칸 이름."""
    op = next(op for op in B.SPECS if any(v[0] == "card" for v in B.SPECS[op].get("args", {}).values()))
    block = B.new_block(op)
    card = next(k for k, v in B.SPECS[op]["args"].items() if v[0] == "card")
    return block, card


class LibraryRulesTests(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def test_favorites_keep_their_order_and_toggle_off(self):
        order = L.save_favorites(["draw_action", "block_action", "draw_action"], self.dir / "fav.json")
        self.assertEqual(order, ["draw_action", "block_action"])
        self.assertEqual(L.toggle_favorite(order, "draw_action"), ["block_action"])
        self.assertEqual(L.load_favorites(self.dir / "fav.json"), ["draw_action", "block_action"])

    def test_a_broken_preset_file_is_skipped(self):
        L.store_preset("good", "좋은 묶음", [B.new_block("draw_action")], self.dir)
        (self.dir / "bad.json").write_text("{not json", encoding="utf8")
        presets = L.load_presets(self.dir)
        self.assertEqual(list(presets), ["good"])
        self.assertIn("좋은 묶음", L.preset_summary(M.default_project(), presets["good"]))

    def test_a_missing_card_asks_for_a_replacement(self):
        project = M.default_project()
        block, card = _card_block()
        block["args"][card] = "NO_SUCH_CARD"
        chosen = project["cards"][0]["id"]
        resolved = L.resolve_preset([block], project, lambda kind, old, rows: chosen)
        self.assertEqual(resolved[0]["args"][card], chosen)
        self.assertEqual(block["args"][card], "NO_SUCH_CARD")          # 원래 묶음은 바꾸지 않는다

    def test_a_missing_card_with_nothing_to_pick_is_refused(self):
        project = M.default_project()
        project["cards"] = []
        block, card = _card_block()
        block["args"][card] = "NO_SUCH_CARD"
        with self.assertRaises(LookupError):
            L.resolve_preset([block], project, lambda *_: None)

    def test_a_block_file_must_come_from_this_program(self):
        path = self.dir / "x.sts2blocks"
        L.save_blocks_file(path, [B.new_block("draw_action")])
        self.assertEqual(L.load_blocks_file(path)[0]["op"], "draw_action")
        path.write_text('{"format": "other"}', encoding="utf8")
        with self.assertRaises(ValueError):
            L.load_blocks_file(path)

    def test_shared_definitions_count_the_cards_that_call_them(self):
        project = M.default_project()
        L.define_shared(project, "내 블록", [B.new_block("draw_action")])
        self.assertEqual(L.shared_uses(project, "내 블록"), 0)
        project["cards"][0]["effects"] = [{"kind": "code", "blocks": [
            {"op": "shared_call", "args": {"name": "내 블록"}}]}]
        self.assertEqual(L.shared_uses(project, "내 블록"), 1)

    def test_the_recipes_build_the_same_blocks_as_the_old_window(self):
        transform = L.transform_recipe(M.default_project(), "Hand", "Any", 2, "pool", "kw:Retain")
        self.assertEqual(transform["op"], "random_transform")
        self.assertEqual(transform["args"]["count"], {"t": "num", "v": 2})
        threshold = L.threshold_recipe("c:strength", 3, "draw", 1)
        self.assertEqual(threshold["op"], "if")
        self.assertEqual(threshold["body"][0]["op"], "draw")
        self.assertEqual(threshold["args"]["cond"]["b"], {"t": "num", "v": 3})


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class DragAndDropTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.editor = BQ.BlockEditorQt(None, self.project, "card", self.card, [])
        self.addCleanup(self.editor.close)

    def _item(self, block):
        self.editor._render(select=block)
        return self.editor._find_item(block)

    def test_dropping_a_block_above_another_moves_it_there(self):
        first, second = B.new_block("draw_action"), B.new_block("block_action")
        self.editor.blocks[:] = [first, second]
        self.editor._render()
        moved = self.editor._drop("block:%d" % id(second), self._item(first), QAbstractItemView.DropIndicatorPosition.AboveItem)
        self.assertTrue(moved)
        self.assertEqual([b["op"] for b in self.editor.blocks], ["block_action", "draw_action"])

    def test_a_block_cannot_be_dropped_inside_itself(self):
        rep = B.new_block("repeat")
        rep["body"] = [B.new_block("draw_action")]
        self.editor.blocks[:] = [rep]
        self.editor._render()
        accepted = self.editor._drop("block:%d" % id(rep), self._item(rep["body"][0]),
                                     QAbstractItemView.DropIndicatorPosition.OnItem)
        self.assertFalse(accepted)
        self.assertEqual(self.editor.blocks[0], rep)

    def test_a_palette_block_dropped_on_a_repeat_goes_into_it(self):
        rep = B.new_block("repeat")
        self.editor.blocks[:] = [rep]
        self.editor._render()
        self.assertTrue(self.editor._drop("draw_action", self._item(rep),
                                          QAbstractItemView.DropIndicatorPosition.OnItem))
        self.assertEqual(rep["body"][0]["op"], "draw_action")

    def test_a_library_group_dropped_on_the_empty_area_is_added_at_the_end(self):
        self.editor.presets = {"k": {"name": "묶음", "blocks": [B.new_block("draw_action")]}}
        self.assertTrue(self.editor._drop("preset:k", None, QAbstractItemView.DropIndicatorPosition.OnViewport))
        self.assertEqual(self.editor.blocks[-1]["op"], "draw_action")

    def test_favorites_are_shown_first_in_the_palette(self):
        self.editor.favorite_order = ["draw_action"]
        self.editor._build_palette()
        self.assertEqual(self.editor.palette.topLevelItem(0).text(0), "★ 즐겨찾기")
        self.assertEqual(self.editor.palette.topLevelItem(0).child(0).data(0, Qt.ItemDataRole.UserRole), "draw_action")


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class OriginalEffectTests(TestCase):
    def setUp(self):
        import itemtabqt as IT
        self.project = M.default_project()
        card = self.project["cards"][0]
        card["clone"] = {"orig_class": "X.Strike", "mod": "m", "body": "", "usings": []}
        card["effects"] = [{"kind": "code", "blocks": [{"op": "original_play", "args": {}}],
                            "original_effect": True, "code": ""}]
        self.card = card
        self.tab = IT.CardTabQt(self.project, on_change=lambda: None)
        self.addCleanup(self.tab.close)
        self.tab.refresh_list(0)

    def test_opening_an_original_effect_reanalyses_it_first(self):
        found = [{"op": "draw_action", "args": {}}]
        result = {"blocks": found, "code": "x"}
        with mock.patch("originalqt.decompose_original", return_value=(found, "")), \
                mock.patch("blockqt.edit_blocks", return_value=result) as editor:
            self.tab.edit_original(0)
        self.assertEqual(editor.call_args[0][4], found)
        self.assertIn("on_decompose", editor.call_args.kwargs)
        self.assertEqual(self.card["effects"][0]["blocks"], found)
        self.assertEqual(self.card["effects"][0]["code"], "x")

    def test_a_cancelled_original_edit_keeps_the_effect(self):
        with mock.patch("originalqt.decompose_original", return_value=([], "")), \
                mock.patch("itemtabqt.show_warning"), mock.patch("blockqt.edit_blocks", return_value=None):
            self.tab.edit_original(0)
        self.assertEqual(self.card["effects"][0]["blocks"], [{"op": "original_play", "args": {}}])


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class RedecomposeTests(TestCase):
    def test_redecompose_replaces_the_blocks_and_collapse_puts_the_original_back(self):
        project = M.default_project()
        original = [{"op": "original_play", "args": {}}]
        editor = BQ.BlockEditorQt(None, project, "card", project["cards"][0], original,
                                  on_decompose=lambda: ([B.new_block("draw_action")], ""))
        self.addCleanup(editor.close)
        editor._redecompose()
        self.assertEqual(editor.blocks[0]["op"], "draw_action")
        editor.undo()
        self.assertEqual(editor.blocks[0]["op"], "original_play")
        editor._collapse_original()
        self.assertEqual([b["op"] for b in editor.blocks], ["original_play"])

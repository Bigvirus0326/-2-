import os
import sys
from unittest import TestCase, skipUnless, mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import blockqt as BQ
    import modgen as M


def _palette_item(editor, op):
    for i in range(editor.palette.topLevelItemCount()):
        head = editor.palette.topLevelItem(i)
        for j in range(head.childCount()):
            child = head.child(j)
            if child.data(0, Qt.ItemDataRole.UserRole) == op:
                return child
    raise AssertionError(op)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class BlockEditorQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.editor = BQ.BlockEditorQt(None, self.project, "card", self.card, [])
        self.addCleanup(self.editor.close)

    def _add(self, op):
        self.editor.palette.setCurrentItem(_palette_item(self.editor, op))
        self.editor._palette_add(_palette_item(self.editor, op))

    def test_the_palette_lists_the_block_categories(self):
        self.assertGreater(self.editor.palette.topLevelItemCount(), 3)

    def test_adding_a_block_puts_it_in_the_workspace_with_default_values(self):
        self._add("block_action")
        self.assertEqual(len(self.editor.blocks), 1)
        self.assertEqual(self.editor.blocks[0]["op"], "block_action")
        self.assertIn("amount", self.editor.blocks[0]["args"])

    def test_moving_a_block_reorders_the_list(self):
        self._add("block_action")
        self._add("draw_action")
        first, second = self.editor.blocks
        self.editor.tree.setCurrentItem(self.editor._find_item(second))
        self.editor._move(-1)
        self.assertEqual(self.editor.blocks, [second, first])

    def test_duplicate_and_delete(self):
        self._add("energy_action")
        block = self.editor.blocks[0]
        self.editor.tree.setCurrentItem(self.editor._find_item(block))
        self.editor._duplicate()
        self.assertEqual(len(self.editor.blocks), 2)
        self.assertIsNot(self.editor.blocks[0], self.editor.blocks[1])
        with mock.patch.object(BQ, "_ask", return_value=True):
            self.editor.tree.setCurrentItem(self.editor._find_item(self.editor.blocks[1]))
            self.editor._delete()
        self.assertEqual(len(self.editor.blocks), 1)

    def test_wrapping_in_a_repeat_keeps_the_block_inside(self):
        self._add("draw_action")
        block = self.editor.blocks[0]
        self.editor.tree.setCurrentItem(self.editor._find_item(block))
        self.editor._wrap("repeat")
        self.assertEqual(self.editor.blocks[0]["op"], "repeat")
        self.assertIs(self.editor.blocks[0]["body"][0], block)

    def test_an_int_argument_is_written_into_the_block(self):
        self._add("damage_action")
        block = self.editor.blocks[0]
        self.editor.tree.setCurrentItem(self.editor._find_item(block))
        row = next(r for r in self.editor._arg_rows if r.key == "hits" and r.b is block)   # 칸은 블록 안에 있다
        row.widget.setValue(3)
        self.assertEqual(block["args"]["hits"], 3)

    def test_undo_brings_back_the_block_list(self):
        self._add("block_action")
        self._add("draw_action")
        self.editor.undo()
        self.assertEqual([b["op"] for b in self.editor.blocks], ["block_action"])

    def test_saving_gives_blocks_code_and_text(self):
        self._add("block_action")
        self.editor.ok()
        result = self.editor.result
        self.assertIsNotNone(result)
        self.assertEqual(result["blocks"][0]["op"], "block_action")
        self.assertIn("text_ko", result)
        self.assertIn("upgraded_text", result)

    def test_a_block_with_problems_asks_before_saving(self):
        self._add("block_action")
        with mock.patch.object(BQ.B, "compile_blocks", return_value=(["x"], ["문제"])), \
                mock.patch.object(BQ, "_ask", return_value=False):
            self.editor.ok()
        self.assertIsNone(self.editor.result)

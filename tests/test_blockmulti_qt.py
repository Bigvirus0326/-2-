"""블록 편집: 여러 블록을 고른 뒤 옮기거나 지운다 (라이브러리로 끌어 놓으면 지워진다). 라이브러리 색은 작업 공간과 같다."""
import os
import sys
from unittest import TestCase, mock, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtGui import QColor
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import blockqt as BQ
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class MultiBlockTests(TestCase):
    def setUp(self):
        project = M.default_project()
        blocks = [{"op": "damage_action", "args": {}}, {"op": "block_action", "args": {}},
                  {"op": "draw_action", "args": {}}]
        self.dialog = BQ.BlockEditorQt(None, project, "card", project["cards"][0], blocks)
        self.addCleanup(self.dialog.close)

    def _payload(self, *indexes):
        return "blocks:" + ",".join(str(id(self.dialog.blocks[i])) for i in indexes)

    def _ops(self, blocks=None):
        return [b["op"] for b in (self.dialog.blocks if blocks is None else blocks)]

    def test_blocks_dropped_on_the_library_are_removed(self):
        self.assertTrue(self.dialog._remove_blocks(self._payload(0, 2)))
        self.assertEqual(self._ops(), ["block_action"])

    def test_several_blocks_move_together_in_their_order(self):
        self.assertTrue(self.dialog._drop(self._payload(0, 2), None, None))
        self.assertEqual(self._ops(), ["block_action", "damage_action", "draw_action"])

    def test_delete_removes_every_selected_block(self):
        self.dialog.tree.clearSelection()
        for index in (0, 1):
            self.dialog._find_item(self.dialog.blocks[index]).setSelected(True)
        with mock.patch.object(BQ, "_ask", return_value=True):
            self.dialog._delete()
        self.assertEqual(self._ops(), ["draw_action"])

    def test_library_items_use_the_workspace_color(self):
        child = self.dialog._palette_child("damage_action", "피해 주기")
        self.assertEqual(child.background(0).color().name(), QColor(BQ._category_color("damage_action")).name())

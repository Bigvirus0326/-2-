import os
import sys
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QByteArray, QMimeData, QPointF, Qt
    from PySide6.QtGui import QDropEvent
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import blockcode as B
    import blockqt as BQ
    import modgen as M


def _mime(payload):
    data = QMimeData()
    data.setData(BQ.PALETTE_MIME, QByteArray(payload.encode("utf8")))
    return data


def _drop_at(tree, payload, item):
    """실제 끌어 놓기와 같은 경로: 자리(항목 가운데)에 놓은 이벤트를 작업 공간에 준다."""
    rect = tree.visualItemRect(item) if item is not None else tree.viewport().rect()
    point = QPointF(rect.center())
    mime = _mime(payload)                      # 이벤트가 끝날 때까지 살아 있어야 한다
    event = QDropEvent(point, Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton,
                       Qt.KeyboardModifier.NoModifier)
    tree.dropEvent(event)
    return event.isAccepted()


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class DropEventTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.editor = BQ.BlockEditorQt(None, self.project, "card", self.project["cards"][0], [])
        self.editor.resize(1200, 800)
        self.editor.show()
        self.addCleanup(self.editor.close)

    def test_a_palette_block_dropped_on_the_workspace_is_added(self):
        accepted = _drop_at(self.editor.tree, "draw_action", None)
        self.assertTrue(accepted)
        self.assertEqual([b["op"] for b in self.editor.blocks], ["draw_action"])

    def test_a_workspace_block_dropped_on_a_container_moves_into_it(self):
        rep = B.new_block("repeat")
        rep["body"] = []
        first = B.new_block("block_action")
        self.editor.blocks[:] = [rep, first]
        self.editor._render()
        item = self.editor._find_item(rep)
        accepted = _drop_at(self.editor.tree, "block:%d" % id(first), item)
        self.assertTrue(accepted)
        self.assertEqual(self.editor.blocks, [rep])
        self.assertEqual(rep["body"], [first])

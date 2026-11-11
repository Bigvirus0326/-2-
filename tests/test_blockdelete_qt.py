"""블록 편집: Delete 키로 고른 블록 지우기 (작업 공간에 포커스가 있을 때만)."""
import os
import sys
from unittest import TestCase, mock, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import blockqt as BQ
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class DeleteKeyTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.blocks = [{"op": "damage", "args": {}}, {"op": "damage", "args": {}}]
        self.dialog = BQ.BlockEditorQt(None, self.project, "card", self.card, [dict(b) for b in self.blocks])
        self.addCleanup(self.dialog.close)
        self.dialog.show()
        self.tree = self.dialog.tree
        self.tree.setFocus()
        self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self.tree.topLevelItem(0).setSelected(True)

    def test_delete_key_removes_the_selected_block_after_confirming(self):
        with mock.patch.object(BQ, "_ask", return_value=True):
            QTest.keyClick(self.tree, Qt.Key.Key_Delete)
        self.assertEqual(len(self.dialog.blocks), 1)

    def test_delete_key_does_nothing_when_the_user_says_no(self):
        with mock.patch.object(BQ, "_ask", return_value=False):
            QTest.keyClick(self.tree, Qt.Key.Key_Delete)
        self.assertEqual(len(self.dialog.blocks), 2)

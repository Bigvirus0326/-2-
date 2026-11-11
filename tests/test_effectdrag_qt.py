"""효과 목록: 여러 줄을 고르고, 끌어서 순서를 바꾸고, 끌어 놓아 지운다."""
import os
import sys
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import effectqt as EQ
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class EffectDragTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.effects = [{"kind": "damage", "amount": 1, "upgrade": 0},
                        {"kind": "block", "amount": 2, "upgrade": 0},
                        {"kind": "draw", "amount": 3, "upgrade": 0}]
        self.list = EQ.EffectListQt("card", lambda: self.project, lambda: {}, lambda: None)
        self.addCleanup(self.list.close)
        self.list.set(self.effects)

    def _kinds(self):
        return [e["kind"] for e in self.list.effects]

    def test_picked_rows_move_together_and_stay_selected(self):
        self.list._move_rows([0, 2], 3)
        self.assertEqual(self._kinds(), ["block", "damage", "draw"])
        self.assertEqual(sorted(self.list._picked_rows()), [1, 2])

    def test_remove_picked_deletes_every_selected_row(self):
        self.list.tree.clearSelection()
        for row in (0, 2):
            self.list.tree.topLevelItem(row).setSelected(True)
        self.list.remove_picked()
        self.assertEqual(self._kinds(), ["block"])

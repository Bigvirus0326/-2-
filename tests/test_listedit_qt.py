import os
import sys
from unittest import TestCase, skipUnless, mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import QModelIndex, QPoint, QPointF, Qt
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import itemtabqt as IT
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ListEditTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.changes = 0
        self.tab = IT.CardTabQt(self.project, on_change=self._count)
        self.addCleanup(self.tab.close)
        self.tab.resize(1200, 800)
        self.tab.show()
        for _ in range(2):
            self.project["cards"].append(M.new_card(f"extra_{_}"))
        self.tab.refresh_list(0)

    def _count(self):
        self.changes += 1

    def test_several_cards_can_be_deleted_at_once(self):
        ids = [c["id"] for c in self.project["cards"]]
        self.tab.listing.clearSelection()
        for row in (1, 2):
            self.tab.listing.item(row).setSelected(True)
        with mock.patch.object(IT, "ask_yes_no", return_value=True):
            self.tab.delete()
        left = [c["id"] for c in self.project["cards"]]
        self.assertEqual(left, [i for i in ids if i not in (ids[1], ids[2])])

    def test_deleting_with_no_selection_does_nothing(self):
        before = len(self.project["cards"])
        self.tab.listing.clearSelection()
        self.tab.cur = None
        self.tab.delete()
        self.assertEqual(len(self.project["cards"]), before)

    def test_dragging_a_row_reorders_the_project(self):
        ids = [c["id"] for c in self.project["cards"]]
        model = self.tab.listing.model()
        model.moveRows(QModelIndex(), 0, 1, QModelIndex(), len(ids))
        new_ids = [c["id"] for c in self.project["cards"]]
        self.assertEqual(new_ids, ids[1:] + ids[:1])
        self.assertGreater(self.changes, 0)

    def test_after_a_multi_card_drag_the_moved_cards_stay_selected(self):
        ids = [c["id"] for c in self.project["cards"]]
        self.tab.listing.clearSelection()
        for row in (0, 1):
            self.tab.listing.item(row).setSelected(True)
        model = self.tab.listing.model()
        model.moveRows(QModelIndex(), 0, 2, QModelIndex(), len(ids))
        self.assertEqual([c["id"] for c in self.project["cards"]], ids[2:] + ids[:2])
        selected = sorted(self.tab.listing.item(r).data(Qt.ItemDataRole.UserRole)
                          for r in range(self.tab.listing.count()) if self.tab.listing.item(r).isSelected())
        self.assertEqual(selected, [len(ids) - 2, len(ids) - 1])

    def test_a_drop_moves_all_selected_cards_together_and_keeps_them_selected(self):
        ids = [c["id"] for c in self.project["cards"]]
        n = len(ids)
        self.tab.listing.clearSelection()
        for row in (0, 1):
            self.tab.listing.item(row).setSelected(True)
        self.tab._list_dropped(IT.drop_order(n, [0, 1], n), [0, 1])
        self.assertEqual([c["id"] for c in self.project["cards"]], ids[2:] + ids[:2])
        selected = sorted(self.tab.listing.item(r).data(Qt.ItemDataRole.UserRole)
                          for r in range(self.tab.listing.count()) if self.tab.listing.item(r).isSelected())
        self.assertEqual(selected, [n - 2, n - 1])

    def test_a_real_drop_on_the_empty_space_below_moves_the_selected_cards(self):
        from PySide6.QtCore import QPointF
        ids = [c["id"] for c in self.project["cards"]]
        n = len(ids)
        self.tab.listing.clearSelection()
        for row in (0, 1):
            self.tab.listing.item(row).setSelected(True)
        event = mock.Mock()
        event.position.return_value = QPointF(5, 5000)      # 줄 밖 (맨 끝에 놓은 것)
        event.mimeData.return_value.hasFormat.return_value = True   # 카드 목록에서 끈 끌기
        self.tab.listing.dropEvent(event)
        self.assertEqual([c["id"] for c in self.project["cards"]], ids[2:] + ids[:2])

    def test_a_drag_from_a_selected_card_starts_one_drag_and_a_small_move_does_not(self):
        from PySide6.QtCore import QEvent
        from PySide6.QtGui import QMouseEvent
        lst = self.tab.listing
        lst.clearSelection()
        for row in (0, 1):
            lst.item(row).setSelected(True)
        p = lst.visualRect(lst.model().index(0, 0)).center()

        def mouse(kind, point, buttons):
            return QMouseEvent(kind, QPointF(point), QPointF(point), Qt.MouseButton.LeftButton, buttons,
                               Qt.KeyboardModifier.NoModifier)

        with mock.patch.object(lst, "_start_drag") as start:
            lst.mousePressEvent(mouse(QEvent.Type.MouseButtonPress, p, Qt.MouseButton.LeftButton))
            lst.mouseMoveEvent(mouse(QEvent.Type.MouseMove, p + QPoint(0, 2), Qt.MouseButton.LeftButton))
            self.assertFalse(start.called)
            lst.mouseMoveEvent(mouse(QEvent.Type.MouseMove, p + QPoint(0, 60), Qt.MouseButton.LeftButton))
            self.assertEqual(start.call_count, 1)

    def test_drop_order_puts_the_chosen_rows_in_front_of_the_drop_row(self):
        self.assertEqual(IT.drop_order(5, [0, 1], 4), [2, 3, 0, 1, 4])
        self.assertEqual(IT.drop_order(5, [0, 1], 0), [0, 1, 2, 3, 4])
        self.assertEqual(IT.drop_order(5, [1, 3], 5), [0, 2, 4, 1, 3])
        self.assertEqual(sorted(IT.drop_order(5, [1, 3], 2)), [0, 1, 2, 3, 4])

    def test_reordering_is_not_allowed_while_a_search_filters_the_list(self):
        ids = [c["id"] for c in self.project["cards"]]
        self.tab.search.setText(self.project["cards"][0]["name_ko"])
        model = self.tab.listing.model()
        model.moveRows(QModelIndex(), 0, 1, QModelIndex(), 2)
        self.assertEqual([c["id"] for c in self.project["cards"]], ids)

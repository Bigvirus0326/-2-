import os
import sys
from unittest import TestCase, skipUnless, mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QMessageBox
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import bulkqt as BQ
    import itemtabqt as IT
    import modgen as M


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class BulkEditTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.tab = IT.CardTabQt(self.project)
        self.addCleanup(self.tab.close)
        self.tab.refresh_list(0)

    def _dialog(self, indices):
        d = BQ.BulkEditDialogQt(self.tab, indices, self.tab)
        self.addCleanup(d.close)
        return d

    def _tick_and_set(self, d, key, value):
        """그 칸을 체크하고 값을 정한다 (화면 조작 대신 가져오는 함수를 바꾼다)."""
        rows = []
        for k, on, getter in d.rows:
            if k == key:
                on.setChecked(True)
                rows.append((k, on, lambda v=value: v))
            else:
                rows.append((k, on, getter))
        d.rows = rows

    def test_only_checked_fields_change(self):
        for c in self.project["cards"][:2]:
            c["cost"] = 1
            c["rarity"] = "Common"
        d = self._dialog([0, 1])
        self._tick_and_set(d, "cost", 3)
        with mock.patch.object(BQ.QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
            d.ok()
        self.assertEqual(self.project["cards"][0]["cost"], 3)
        self.assertEqual(self.project["cards"][1]["cost"], 3)
        self.assertEqual(self.project["cards"][0]["rarity"], "Common")

    def test_cancelling_the_preview_changes_nothing(self):
        d = self._dialog([0])
        self._tick_and_set(d, "cost", 9)
        before = self.project["cards"][0]["cost"]
        with mock.patch.object(BQ.QMessageBox, "question", return_value=QMessageBox.StandardButton.No):
            d.ok()
        self.assertEqual(self.project["cards"][0]["cost"], before)

    def test_nothing_checked_only_closes(self):
        d = self._dialog([0])
        before = dict(self.project["cards"][0])
        d.ok()
        self.assertEqual(self.project["cards"][0], before)

    def test_bulk_button_opens_the_dialog_for_the_selection(self):
        self.tab.listing.clearSelection()
        self.tab.listing.item(0).setSelected(True)
        with mock.patch.object(IT, "BulkEditDialogQt") as dialog:
            self.tab.bulk_edit()
        dialog.assert_called_once()

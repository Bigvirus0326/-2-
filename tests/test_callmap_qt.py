import os
import sys
from types import SimpleNamespace
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import blockcode as B
    import callmap
    import modgen as M
    from callmapqt import CallMappingDialogQt
    from projectreviewqt import UnresolvedDialogQt


def _imported_call():
    return {"op": "src_call", "label": "가져온 호출", "args": {}, "slots": []}


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class CallMapTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]

    def test_a_project_without_imported_calls_has_no_groups(self):
        self.assertEqual(callmap.scan_calls(self.project), {})

    def test_an_imported_call_is_listed_in_the_review(self):
        self.card["effects"] = [{"kind": "code", "blocks": [_imported_call()]}]
        review = UnresolvedDialogQt(None, self.project, lambda: None)
        self.addCleanup(review.close)
        self.assertEqual(len(review.groups), 1)
        self.assertNotEqual(review.listing.item(0).text(), "연결할 항목이 없습니다.")

    def test_connecting_without_a_rule_replaces_only_the_first_call(self):
        parent = [_imported_call(), _imported_call()]
        block = B.new_block("damage")
        updates = callmap.apply_connection(self.project, "card", [(parent, 0, self.card)], block, None)
        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0][2]["op"], "damage")
        self.assertIsNot(updates[0][2], block)

    def test_the_dialog_saves_the_chosen_block_without_a_rule_for_unknown_calls(self):
        editor = SimpleNamespace(project=self.project, owner_kind="card", item=self.card)
        dialog = CallMappingDialogQt(None, editor, _imported_call())
        self.addCleanup(dialog.close)
        dialog.op.setCurrentIndex(dialog.op.findData("damage"))
        dialog.ok()
        self.assertEqual(dialog.result["block"]["op"], "damage")
        self.assertIsNone(dialog.result["rule"])

import os
import sys
from unittest import TestCase, skipUnless, mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import modgen as M
    import projectreviewqt as R


class ReviewRulesTests(TestCase):
    def setUp(self):
        self.project = M.default_project()

    def test_balance_report_lists_every_pool_and_card_count(self):
        text = R.balance_text(self.project)
        self.assertIn("기본 풀", text)
        self.assertIn(f"{len(self.project['cards'])}장", text)

    def test_balance_report_flags_a_damage_number_that_disagrees_with_the_effect(self):
        card = self.project["cards"][0]
        card["desc_ko"] = "피해를 99 줍니다."
        card["effects"] = [M.new_effect("damage", 6, 3)]
        text = R.balance_text(self.project)
        self.assertIn("설명 확인", text)
        self.assertIn("설명 99 / 기본 효과 6", text)

    def test_an_empty_project_says_there_are_no_cards(self):
        self.project["cards"] = []
        self.assertIn("카드가 없습니다", R.balance_text(self.project))

    def test_a_reference_to_a_missing_power_is_found(self):
        self.project["cards"][0]["effects"] = [M.new_effect("block", 3, 0, power="c:nope")]
        self.project["cards"][0]["effects"][0]["cond_power"] = "c:nope"
        found = R.missing_refs(self.project)
        self.assertIn(("power", "c:nope"), found)

    def test_a_default_project_has_no_missing_references(self):
        self.assertEqual(R.missing_refs(self.project), {})

    def test_import_groups_split_cards_into_three_rows(self):
        groups = R.import_groups(self.project)
        self.assertEqual(sum(len(g) for g in groups), len(self.project["cards"]))


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ReviewDialogTests(TestCase):
    def test_connecting_a_missing_power_rewrites_the_reference(self):
        project = M.default_project()
        card = project["cards"][0]
        card["effects"] = [M.new_effect("block", 3, 0, power="c:nope")]
        changes = []
        dialog = R.UnresolvedDialogQt(None, project, lambda: changes.append(1))
        self.addCleanup(dialog.close)
        target = project["powers"][0]["id"]
        dialog.listing.setCurrentRow(list(dialog.missing).index(("power", "c:nope")))
        with mock.patch.object(dialog, "_pick_target", return_value=target):
            dialog.connect()
        self.assertEqual(card["effects"][0]["power"], "c:" + target)
        self.assertEqual(changes, [1])

    def test_import_results_dialog_opens_the_chosen_card(self):
        project = M.default_project()
        opened = []
        dialog = R.ImportResultsDialogQt(None, project, ["알림"], opened.append)
        self.addCleanup(dialog.close)
        self.assertEqual(dialog.windowTitle(), "다른 모드 가져오기 결과")

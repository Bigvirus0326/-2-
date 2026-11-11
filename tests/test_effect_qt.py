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
    import effectqt as E
    import itemtabqt as IT


def _visible(widget):
    return not widget.isHidden()


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class EffectDialogQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]

    def _dialog(self, effect=None, owner="card", item=None):
        d = E.EffectDialogQt(None, effect, owner, self.project, self.card if item is None else item)
        self.addCleanup(d.close)
        return d

    def test_accepting_a_damage_effect_writes_its_values(self):
        d = self._dialog(None, "card")
        d.kind.setCurrentIndex(d.kind.findData("damage"))
        d.amount.setValue(7)
        d.hits.setValue(2)
        d.upgrade.setValue(3)
        d._accept()
        r = d.result
        self.assertEqual((r["kind"], r["amount"], r["hits"], r["upgrade"]), ("damage", 7, 2, 3))
        self.assertEqual(r["target"], "enemy")         # 카드 피해는 항상 적을 향한다
        self.assertEqual(r["blocks"], [])
        self.assertFalse(r["auto_text"])

    def test_power_owner_gets_a_per_stack_checkbox_and_no_upgrade(self):
        power = self.project["powers"][0]
        d = self._dialog(None, "power", power)
        d.kind.setCurrentIndex(d.kind.findData("block"))
        self.assertTrue(_visible(d.per_stack))
        self.assertFalse(_visible(d.upgrade))
        d.per_stack.setChecked(True)
        d._accept()
        self.assertTrue(d.result["per_stack"])

    def test_other_target_appears_only_for_triggers_with_another_party(self):
        power = dict(self.project["powers"][0], trigger="damage_received")
        d = self._dialog(None, "power", power)
        self.assertGreaterEqual(d.target.findData("other"), 0)
        power["trigger"] = "turn_start"
        d2 = self._dialog(None, "power", power)
        self.assertEqual(d2.target.findData("other"), -1)

    def test_remove_power_shows_the_power_row_and_hides_the_scale_box(self):
        d = self._dialog(None, "card")
        d.kind.setCurrentIndex(d.kind.findData("remove_power"))
        self.assertTrue(_visible(d.power))
        self.assertFalse(_visible(d.scale_box))
        self.assertEqual(d.amount_lbl.text(), "제거량 (0 = 전부)")

    def test_code_effect_without_code_is_refused(self):
        d = self._dialog(None, "card")
        d.kind.setCurrentIndex(d.kind.findData("code"))
        d.code.setPlainText("   ")
        with mock.patch.object(E, "_warn") as warn:
            d._accept()
        warn.assert_called_once()
        self.assertIsNone(d.result)

    def test_code_effect_keeps_typed_text_and_upgrade_text(self):
        d = self._dialog(None, "card")
        d.kind.setCurrentIndex(d.kind.findData("code"))
        d.code.setPlainText("await Foo();")
        d._text_boxes["ko"].setText("한국어 설명")
        d._upgrade_boxes["en"].setText("Stronger")
        d._accept()
        self.assertEqual(d.result["code"], "await Foo();")
        self.assertEqual(d.result["text_ko"], "한국어 설명")
        self.assertEqual(d.result["upgraded_text"]["en"], "Stronger")

    def test_release_is_only_offered_when_there_are_blocks(self):
        d = self._dialog(None, "card")
        self.assertFalse(d.unblock_btn.isEnabled())

    def test_x_use_only_for_x_cost_cards(self):
        card = dict(self.card, x_cost=True)
        d = self._dialog(None, "card", card)
        self.assertTrue(_visible(d.x_use))
        card["x_cost"] = False
        d2 = self._dialog(None, "card", card)
        self.assertFalse(_visible(d2.x_use))


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class EffectListQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.changes = 0
        self.card = self.project["cards"][0]
        self.effects = self.card["effects"]
        self.lst = E.EffectListQt("card", lambda: self.project, lambda: self.card, self._count)
        self.addCleanup(self.lst.close)
        self.lst.set(self.effects)

    def _count(self):
        self.changes += 1

    def _pick(self, row):
        self.lst.tree.setCurrentItem(self.lst.tree.topLevelItem(row))

    def test_list_shows_one_row_per_effect(self):
        self.assertEqual(self.lst.tree.topLevelItemCount(), len(self.effects))
        self.assertIs(self.lst.effects, self.effects)     # 항목의 리스트를 직접 고친다

    def test_add_appends_the_dialog_result(self):
        new = M.new_effect("block", 4, 0)
        with mock.patch.object(self.lst, "_dialog", return_value=new):
            self.lst.add()
        self.assertIs(self.effects[-1], new)
        self.assertEqual(self.changes, 1)

    def test_cancelled_edit_changes_nothing(self):
        before = dict(self.effects[0])
        self._pick(0)
        with mock.patch.object(self.lst, "_dialog", return_value=None):
            self.lst.edit()
        self.assertEqual(self.effects[0], before)
        self.assertEqual(self.changes, 0)

    def test_edit_replaces_the_selected_effect(self):
        new = M.new_effect("block", 9, 0)
        self._pick(0)
        with mock.patch.object(self.lst, "_dialog", return_value=new):
            self.lst.edit()
        self.assertIs(self.effects[0], new)
        self.assertEqual(self.lst.tree.topLevelItem(0).text(1), "9")

    def test_move_and_remove(self):
        first, second = self.effects[0], M.new_effect("block", 2, 0)
        self.effects.append(second)
        self.lst.refresh()
        self._pick(0)
        self.lst.move(1)
        self.assertIs(self.effects[1], first)
        self.lst.move(1)                                  # 맨 아래에서는 아무 일도 없다
        self.assertIs(self.effects[1], first)
        self._pick(1)
        self.lst.remove()
        self.assertNotIn(first, self.effects)

    def test_original_effect_row_is_read_only_here(self):
        self.effects[0] = dict(self.effects[0], original_effect=True)
        self.lst.refresh()
        self.assertEqual(self.lst.tree.topLevelItem(0).text(0), "원본 효과 · 블록 편집")
        self._pick(0)
        with mock.patch.object(self.lst, "_dialog") as dialog, mock.patch.object(E, "_info"):
            self.lst.edit()
        dialog.assert_not_called()


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ItemTabEffectsQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.changes = 0
        self.tab = IT.CardTabQt(self.project, on_change=self._count)
        self.addCleanup(self.tab.close)
        self.tab.resize(1200, 800)
        self.tab.show()

    def _count(self):
        self.changes += 1

    def test_selecting_a_card_shows_its_effects(self):
        row = next(i for i, c in enumerate(self.project["cards"]) if c["id"] == "strike")
        self.tab.refresh_list(row)
        self.assertIs(self.tab.effects.effects, self.project["cards"][row]["effects"])

    def test_effect_edit_marks_the_project_changed_and_updates_the_row(self):
        row = next(i for i, c in enumerate(self.project["cards"]) if c["id"] == "strike")
        self.tab.refresh_list(row)
        new = M.new_effect("damage", 12, 0)
        self.tab.effects.tree.setCurrentItem(self.tab.effects.tree.topLevelItem(0))
        with mock.patch.object(self.tab.effects, "_dialog", return_value=new):
            self.tab.effects.edit()
        self.assertIs(self.project["cards"][row]["effects"][0], new)
        self.assertGreater(self.changes, 0)
        self.assertIn("(strike)", self.tab.listing.currentItem().text())

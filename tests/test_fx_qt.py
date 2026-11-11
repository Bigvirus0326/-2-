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
    import fxbtn as FX
    import modgen as M
    import fxtabqt as T
    import fxqt as FQ


class _Host:
    """FxTabQt 이 app 에게 바라는 것만 가진 가짜 앱."""

    def __init__(self):
        self.project = M.default_project()
        self.dirty = 0

    def mark_dirty(self):
        self.dirty += 1

    def game_assets(self):
        return None


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class EffectPainterQtTests(TestCase):
    def setUp(self):
        self.host = _Host()
        self.tab = T.FxTabQt(self.host)
        self.addCleanup(self.tab.close)
        self.p = self.tab.painter
        self.p.add_effect()

    def test_adding_an_effect_selects_it_and_marks_dirty(self):
        self.assertEqual(self.p.fx["id"], "new_fx")
        self.assertGreater(self.host.dirty, 0)

    def test_a_drawn_shape_is_selected_and_drawn(self):
        before = len(self.p.fx["shapes"])          # 새 이펙트에는 기본 도형이 하나 있다
        self.p.add_shape(FX.new_shape("circle", cx=0, cy=0, r=30, fill=True, color="#ff0000", width=4, alpha=1.0))
        self.assertEqual(len(self.p.fx["shapes"]), before + 1)
        self.assertEqual(self.p.sel, before)
        self.assertFalse(self.p.stage.pixmap().isNull())

    def test_animation_fields_write_into_the_selected_shape(self):
        self.p.add_shape(FX.new_shape("ring", cx=0, cy=0, r=20, fill=False, color="#ffffff", width=4, alpha=1.0))
        self.p.av["dur"].setValue(2.5)
        self.p.av["copies"].setValue(3)
        anim = self.p.fx["shapes"][self.p.sel]["anim"]
        self.assertEqual(anim["dur"], 2.5)
        self.assertEqual(anim["copies"], 3)

    def test_undo_brings_back_the_previous_shapes(self):
        self.p.fx["shapes"] = []
        self.p.add_shape(FX.new_shape("line", points=[[0, 0], [10, 10]], fill=False, color="#fff", width=2, alpha=1))
        self.p.push()
        self.p.del_shape()
        self.assertEqual(self.p.fx["shapes"], [])
        self.p.undo()
        self.assertEqual(len(self.p.fx["shapes"]), 1)

    def test_renaming_the_effect_id_updates_the_list(self):
        self.p.ev["id"].setText("flare_one")
        self.assertEqual(self.p.fx["id"], "flare_one")
        self.assertIn("flare_one", self.p.lst.item(self.p.cur).text())

    def test_deleting_an_effect_asks_first(self):
        self.p.add_effect()
        before = len(self.p.fxs)
        with mock.patch.object(FQ, "_ask", return_value=False):
            self.p.del_effect()
        self.assertEqual(len(self.p.fxs), before)
        with mock.patch.object(FQ, "_ask", return_value=True):
            self.p.del_effect()
        self.assertEqual(len(self.p.fxs), before - 1)

    def test_seeking_draws_a_playback_frame(self):
        self.p.add_shape(FX.new_shape("circle", cx=0, cy=0, r=30, fill=True, color="#ff0000", width=4, alpha=1.0))
        self.p.show_time(0.2)
        self.assertIn("0.20", self.p.tlabel.text())


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ButtonDesignerQtTests(TestCase):
    def setUp(self):
        self.host = _Host()
        self.tab = T.FxTabQt(self.host)
        self.addCleanup(self.tab.close)
        self.b = self.tab.buttons
        self.b.add()

    def test_adding_a_button_gives_it_a_unique_id_and_selects_it(self):
        self.assertEqual(self.b.b["id"], "new_button")
        self.b.add()
        self.assertEqual(self.b.b["id"], "new_button_b")

    def test_text_and_cost_fields_write_into_the_button(self):
        self.b.v["label_ko"][1].setText("숨결")
        self.b.v["energy_cost"][1].setValue(2)
        self.assertEqual(self.b.b["label_ko"], "숨결")
        self.assertEqual(self.b.b["energy_cost"], 2)

    def test_screen_anchor_shows_the_screen_position_fields(self):
        self.b.anchor.setCurrentIndex(self.b.anchor.findData("screen"))
        self.assertEqual(self.b.b["anchor"], "screen")
        self.assertFalse(self.b.pos_screen.isHidden())
        self.assertTrue(self.b.pos_creature.isHidden())

    def test_not_enough_energy_is_refused_and_says_why(self):
        self.b.v["energy_cost"][1].setValue(9)
        self.b.press()
        self.assertIn("에너지가 부족합니다", self.b.log.toPlainText())
        self.assertEqual(self.b.st["turn_uses"], 0)

    def test_a_press_spends_energy_and_the_turn_limit_stops_a_second_press(self):
        self.b.v["energy_cost"][1].setValue(1)
        self.b.v["per_turn"][1].setValue(1)
        self.b.press()
        self.assertEqual(self.b.st["energy"], 2)
        self.b.press()
        self.assertEqual(self.b.st["energy"], 2)
        self.assertIn("이번 턴에 이미", self.b.log.toPlainText())

    def test_next_turn_resets_the_turn_counter(self):
        self.b.v["per_turn"][1].setValue(1)
        self.b.press()
        self.b.next_turn()
        self.assertEqual(self.b.st["turn_uses"], 0)
        self.assertEqual(self.b.st["turn"], 2)

    def test_language_switch_redraws_the_test_bench(self):
        self.b.set_lang("en")
        self.assertFalse(self.b.stage.pixmap().isNull())

    def test_deleting_a_button_asks_first(self):
        n = len(self.b.items)
        import buttonqt as BQ
        with mock.patch.object(BQ, "_ask", return_value=False):
            self.b.delete()
        self.assertEqual(len(self.b.items), n)
        with mock.patch.object(BQ, "_ask", return_value=True):
            self.b.delete()
        self.assertEqual(len(self.b.items), n - 1)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ButtonSlotTests(TestCase):
    def test_a_value_slot_is_written_into_the_button(self):
        from unittest import mock
        import buttonqt
        host = _Host()
        tab = T.FxTabQt(host)
        self.addCleanup(tab.close)
        designer = tab.buttons
        designer.add()
        dialog = mock.Mock(result={"t": "num", "v": 3})
        dialog.exec.return_value = 1
        with mock.patch.object(buttonqt, "SlotDialogQt", return_value=dialog):
            designer.edit_slot_key("value")
        self.assertEqual(designer.b["value"], {"t": "num", "v": 3})

import os
import sys
import types
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import modgen as M
    import slotqt as SQ


def _editor(owner="card", item=None, allow_event=False):
    return types.SimpleNamespace(project=M.default_project(), owner_kind=owner, item=item or {},
                                 allow_event=allow_event)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class SlotDialogQtTests(TestCase):
    def _dialog(self, kind, current, editor=None):
        d = SQ.SlotDialogQt(None, editor or _editor(), kind, current)
        self.addCleanup(d.close)
        return d

    def test_a_number_value_keeps_its_number(self):
        d = self._dialog("value", {"t": "num", "v": 7})
        self.assertEqual(d.type.currentData(), "num")
        d.ok()
        self.assertEqual(d.result, {"t": "num", "v": 7})

    def test_changing_the_type_uses_its_defaults(self):
        d = self._dialog("value", {"t": "num", "v": 7})
        index = d.type.findData("stat")
        d.type.setCurrentIndex(index)
        self.assertEqual(d.data["t"], "stat")
        self.assertEqual(d.data["stat"], "hp")

    def test_the_amount_type_is_only_offered_to_powers(self):
        card = self._dialog("value", None, _editor("card"))
        power = self._dialog("value", None, _editor("power"))
        self.assertEqual(card.type.findData("amount"), -1)
        self.assertGreaterEqual(power.type.findData("amount"), 0)

    def test_event_values_need_the_event_flag(self):
        plain = self._dialog("value", None, _editor("power", allow_event=False))
        event = self._dialog("value", None, _editor("power", allow_event=True))
        self.assertEqual(plain.type.findData("event"), -1)
        self.assertGreaterEqual(event.type.findData("event"), 0)

    def test_a_condition_comparison_has_a_preview(self):
        d = self._dialog("cond", {"t": "cmp", "a": {"t": "num", "v": 1}, "op": ">=", "b": {"t": "num", "v": 2}})
        self.assertTrue(d.preview.text().startswith("→"))

    def test_the_clone_source_type_is_offered_for_copied_cards(self):
        item = {"clone": {"orig_class": "X"}, "raw_vars": [{"name": "Damage", "value": 6, "upgrade": 3}]}
        d = self._dialog("value", None, _editor("card", item))
        self.assertGreaterEqual(d.type.findData("src"), 0)
        self.assertGreaterEqual(d.type.findData("dynvar"), 0)

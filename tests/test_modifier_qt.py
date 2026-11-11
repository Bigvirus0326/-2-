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
    import modifierqt as MQ


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ModifierDialogQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()

    def _dialog(self, mod=None):
        d = MQ.ModifierDialogQt(None, mod, self.project)
        self.addCleanup(d.close)
        return d

    def test_a_plain_modifier_has_no_reference_box(self):
        d = self._dialog()
        d.kind.setCurrentIndex(d.kind.findData("dmg_dealt_add"))
        d._kind_changed()
        self.assertTrue(d.filter.isEnabled())
        d._accept()
        self.assertEqual(d.result["kind"], "dmg_dealt_add")
        self.assertEqual(d.result["ref"], "")

    def test_a_reference_is_required_when_the_kind_needs_one(self):
        d = self._dialog()
        d.kind.setCurrentIndex(d.kind.findData("res_cap"))
        d._kind_changed()
        self.assertEqual(d.ref.findData("") >= 0, True)
        with mock.patch.object(MQ, "_warn") as warn:
            d._accept()
        if M.MODIFIER_REF["res_cap"][1]:
            self.assertIsNotNone(d.result)
        else:
            warn.assert_called_once()
            self.assertIsNone(d.result)

    def test_value_is_read_as_an_integer(self):
        d = self._dialog({"kind": "dmg_dealt_add", "value": 2, "per_stack": True, "filter": "Any", "ref": ""})
        d.value.setText("-5")
        d._accept()
        self.assertEqual(d.result["value"], -5)
        self.assertTrue(d.result["per_stack"])

    def test_not_a_number_is_refused(self):
        d = self._dialog()
        d.value.setText("많이")
        with mock.patch.object(MQ, "_warn") as warn:
            d._accept()
        warn.assert_called_once()
        self.assertIsNone(d.result)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ModifierListQtTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.changes = 0
        self.mods = []
        self.lst = MQ.ModifierListQt(lambda: self.project, self._count)
        self.addCleanup(self.lst.close)
        self.lst.set(self.mods)

    def _count(self):
        self.changes += 1

    def test_add_appends_the_dialog_result(self):
        new = {"kind": "dmg_dealt_add", "value": 3, "per_stack": False, "filter": "Any", "ref": ""}
        fake = mock.Mock()
        fake.result = new
        with mock.patch.object(MQ, "ModifierDialogQt", return_value=fake):
            self.lst.add()
        self.assertEqual(self.mods, [new])
        self.assertEqual(self.changes, 1)

    def test_remove_drops_the_selected_row(self):
        self.mods.append({"kind": "dmg_dealt_add", "value": 1, "per_stack": False, "filter": "Any", "ref": ""})
        self.lst.refresh()
        self.lst.lst.setCurrentRow(0)
        self.lst.remove()
        self.assertEqual(self.mods, [])

    def test_percent_kind_shows_a_percent_sign(self):
        label, value, stack = self.lst._describe({"kind": "dmg_dealt_pct", "value": 50, "per_stack": False,
                                                  "filter": "Any", "ref": ""})
        self.assertTrue(value.endswith("%"))
        self.assertEqual(stack, "-")

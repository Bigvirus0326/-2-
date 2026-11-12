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
    import blockcode as B
    import blockqt as BQ
    import effectqt as E
    import modgen as M


def _palette_ops(editor):
    out = []
    stack = [editor.palette.topLevelItem(i) for i in range(editor.palette.topLevelItemCount())]
    while stack:
        it = stack.pop()
        out.append(str(it.data(0, 0x0100)))   # Qt.UserRole
        stack += [it.child(i) for i in range(it.childCount())]
    return out


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class HideCodeTests(TestCase):
    def setUp(self):
        self._old = B.HIDE_CODE
        B.HIDE_CODE = True
        self.addCleanup(setattr, B, "HIDE_CODE", self._old)
        self.project = M.default_project()
        self.card = self.project["cards"][0]

    def test_labels_use_words_instead_of_code(self):
        self.assertEqual(B.value_label({"t": "src", "code": "cardPlay.Target"}), "카드의 대상")
        self.assertEqual(B.value_label({"t": "src", "code": "a.B(c) + 2"}), "원본 수식")
        self.assertEqual(B.cond_label({"t": "src", "code": "x > 1"}), "원본 조건")

    def test_raw_code_ability_shows_a_note_not_the_code(self):
        effect = dict(M.new_effect("code"), code="await Foo();\nawait Bar();")
        d = E.EffectDialogQt(None, effect, "card", self.project, self.card)
        self.addCleanup(d.close)
        self.assertTrue(d.code.isHidden())
        self.assertTrue(d.unblock_btn.isHidden())
        self.assertFalse(d.code_note.isHidden())
        self.assertIn("원본 코드 2줄", d.code_note.text())
        self.assertEqual(d.code.toPlainText(), "await Foo();\nawait Bar();")   # 저장되는 코드는 그대로

    def test_block_editor_hides_code_tab_but_keeps_raw_block(self):
        editor = BQ.BlockEditorQt(None, self.project, "card", self.card, [])
        self.addCleanup(editor.close)
        self.assertFalse(editor.tabs.isTabVisible(editor.tabs.indexOf(editor.code_view)))
        self.assertIn("source_step", _palette_ops(editor))   # 직접 코드 블록은 늘 쓸 수 있다

    def test_showing_code_restores_the_code_box(self):
        B.HIDE_CODE = False
        effect = dict(M.new_effect("code"), code="await Foo();")
        d = E.EffectDialogQt(None, effect, "card", self.project, self.card)
        self.addCleanup(d.close)
        self.assertFalse(d.code.isHidden())
        self.assertTrue(d.code_note.isHidden())
        editor = BQ.BlockEditorQt(None, self.project, "card", self.card, [])
        self.addCleanup(editor.close)
        self.assertIn("source_step", _palette_ops(editor))   # 숨김 테스트가 실제로 블록 이름을 보는지 확인

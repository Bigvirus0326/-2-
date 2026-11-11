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
    import itemtabqt as IT
    import modgen as M
    from clonepanelqt import ClonePanelQt


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class OriginalEditorClonePanelTests(TestCase):
    def setUp(self):
        self.project = M.default_project()
        self.card = self.project["cards"][0]
        self.card["clone"] = {"orig_class": "X.Strike", "mod": "m", "body": "", "usings": []}
        self.card["raw_vars"] = [{"name": "Damage", "value": 6, "upgrade": 3}]
        self.card["effects"] = [{"kind": "code", "blocks": [{"op": "original_play", "args": {}}],
                                 "original_effect": True, "code": ""}]
        self.tab = IT.CardTabQt(self.project, on_change=lambda: None)
        self.addCleanup(self.tab.close)
        self.tab.refresh_list(0)

    def test_the_original_editor_shows_the_clone_panel_with_the_raw_values(self):
        with mock.patch("originalqt.decompose_original", return_value=([], "")), \
                mock.patch("itemtabqt.show_warning"), mock.patch("blockqt.edit_blocks", return_value=None) as editor:
            self.tab.edit_original(0)
        panel = editor.call_args.kwargs["top_widget"]
        self.assertIsInstance(panel, ClonePanelQt)
        self.assertEqual(panel.table.rowCount(), 1)
        self.assertEqual(panel.table.item(0, 0).text(), "Damage")

    def test_raw_value_edits_in_the_editor_are_kept_when_saved(self):
        def fake_edit(parent, project, kind, draft, blocks, **kwargs):
            panel = kwargs["top_widget"]
            draft["raw_vars"][0]["value"] = 9          # 같은 칸에서 수치를 바꾼 것과 같다
            return {"blocks": [{"op": "block_action", "args": {}}], "code": "c"}
        with mock.patch("originalqt.decompose_original", return_value=([], "")), \
                mock.patch("itemtabqt.show_warning"), mock.patch("blockqt.edit_blocks", side_effect=fake_edit):
            self.tab.edit_original(0)
        self.assertEqual(self.card["raw_vars"][0]["value"], 9)
        self.assertEqual(self.card["effects"][0]["blocks"][0]["op"], "block_action")

import os
import sys
import tempfile
from unittest import TestCase, skipUnless, mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import feedbackqt as F


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class FeedbackDialogQtTests(TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.dialog = F.FeedbackDialogQt(self.dir, None)
        self.addCleanup(self.dialog.close)

    def test_a_title_is_required(self):
        self.dialog.description.setPlainText("내용")
        with mock.patch.object(F, "_warn") as warn:
            self.assertIsNone(self.dialog._collect())
        warn.assert_called_once()

    def test_a_description_is_required(self):
        self.dialog.title_edit.setText("제목")
        with mock.patch.object(F, "_warn") as warn:
            self.assertIsNone(self.dialog._collect())
        warn.assert_called_once()

    def test_collected_report_is_redacted_and_keeps_the_kind(self):
        self.dialog.kind.setCurrentText("오류")
        self.dialog.title_edit.setText("제목입니다")
        self.dialog.description.setPlainText("내용입니다")
        report = self.dialog._collect()
        self.assertEqual(report["kind"], "오류")
        self.assertEqual(report["title"], F.FB.redact("제목입니다"))

    def test_logs_are_on_by_default_and_the_preview_says_so(self):
        self.assertTrue(self.dialog.include_logs.isChecked())
        self.dialog.title_edit.setText("제목")
        self.dialog.description.setPlainText("내용")
        report = self.dialog._collect()
        self.assertIn("[로그 포함]", self.dialog._payload_preview(report))

    def test_saving_a_report_writes_a_file_in_the_app_folder(self):
        self.dialog.title_edit.setText("제목")
        self.dialog.description.setPlainText("내용")
        with mock.patch.object(F, "_info") as info:
            self.dialog.save_bundle()
        info.assert_called_once()
        self.assertIn("보고서를 저장했습니다", info.call_args[0][1])

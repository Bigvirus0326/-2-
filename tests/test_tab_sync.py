import os
import subprocess
import sys
from unittest import TestCase

# sts2_mod_maker.App 은 프로세스마다 한 번만 만든다: 다른 테스트가 남긴 Tk 상태와 섞이지 않도록 따로 실행한다
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TabSyncTests(TestCase):
    def _run_app_check(self, name):
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", f"tests.tab_sync_app_checks.TabSyncTests.{name}"],
            cwd=ROOT, capture_output=True, text=True, timeout=170)
        self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])

    def test_plain_tab_switch_does_not_reread_tabs(self):
        self._run_app_check("test_plain_tab_switch_does_not_reread_tabs")

    def test_edit_rereads_other_tabs_in_background_not_on_switch(self):
        self._run_app_check("test_edit_rereads_other_tabs_in_background_not_on_switch")

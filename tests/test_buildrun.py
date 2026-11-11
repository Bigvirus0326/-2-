import os
import sys
from unittest import TestCase
from unittest.mock import patch

import buildrun as BR


class BuildRunTests(TestCase):
    def test_build_and_publish_commands(self):
        self.assertEqual(BR.build_command(False, ""), ["dotnet", "build", "-nologo"])
        self.assertEqual(BR.build_command(True, "C:/game"), ["dotnet", "publish", "-nologo", "-p:Sts2Path=C:/game"])

    def test_prerequisites_report_missing_dotnet_and_godot(self):
        settings = {"godot_path": ""}
        with patch.object(BR.shutil, "which", return_value=None):
            self.assertIn("dotnet", BR.check_build_prereqs(settings, False))
        with patch.object(BR.shutil, "which", return_value="C:/dotnet.exe"):
            self.assertIsNone(BR.check_build_prereqs(settings, False))       # 빌드는 MegaDot 없이도 된다
            self.assertIn("MegaDot", BR.check_build_prereqs(settings, True))  # 게시는 필요하다

    def test_run_build_streams_output_and_returns_exit_code(self):
        lines = []
        code = BR.run_build([sys.executable, "-c", "print('안녕 빌드')"], os.getcwd(), lines.append)
        self.assertEqual(code, 0)
        self.assertIn("안녕 빌드", "\n".join(lines))

    def test_run_build_reports_a_missing_program(self):
        lines = []
        code = BR.run_build(["no-such-program-xyz"], os.getcwd(), lines.append)
        self.assertEqual(code, -1)
        self.assertTrue(any("실행 실패" in line for line in lines))

    def test_validate_returns_two_lists_and_does_not_change_the_project(self):
        import modgen as M
        project = M.default_project()
        before = repr(project)
        errors, warnings = BR.validate(project)
        self.assertIsInstance(errors, list)
        self.assertIsInstance(warnings, list)
        self.assertEqual(repr(project), before)

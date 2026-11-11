import os
import random
import sys
from unittest import TestCase, skipUnless
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication, QLabel
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import app_qt as A
    import projectio as IO
    import qtkit as Q

TITLES = [f"탭{i}" for i in range(10)]
OPERATIONS = ["float", "dock", "hide", "show", "select", "dock_all", "reset", "snapshot", "restore"]


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class DockingQtTests(TestCase):
    def setUp(self):
        self.ws = Q.DockWorkspace()
        self.ws.resize(1000, 700)
        self.pages = {t: self.ws.add_page(QLabel(t), t) for t in TITLES}
        self.ws.show()
        self._settle()

    def tearDown(self):
        self.ws.close()

    def _settle(self):
        for _ in range(3):
            _app.processEvents()

    def _floating(self):
        return {t for t in TITLES if self.ws.dock_of(self.pages[t]).isFloating()}

    def _hidden(self):
        return {t for t in TITLES if self.ws.dock_of(self.pages[t]).isHidden()}

    def test_starts_as_one_tab_group(self):
        first = self.ws.dock_of(self.pages[TITLES[0]])
        self.assertEqual(len(self.ws.tabifiedDockWidgets(first)), 9)
        self.assertEqual(self._floating(), set())

    def test_random_operations_keep_the_invariants(self):
        rnd = random.Random(20261111)
        hidden_model = set()
        saved = None
        ran = {op: 0 for op in OPERATIONS}
        for step in range(300):
            title = rnd.choice(TITLES)
            page = self.pages[title]
            dock = self.ws.dock_of(page)
            op = rnd.choice(OPERATIONS)
            ran[op] += 1
            if op == "float":
                dock.setFloating(True)
            elif op == "dock":
                dock.setFloating(False)
            elif op == "hide":
                self.ws.set_visible(page, False)
                hidden_model.add(title)
            elif op == "show":
                self.ws.set_visible(page, True)
                hidden_model.discard(title)
            elif op == "select":
                self.ws.select(page)
            elif op == "dock_all":
                self.ws.dock_all()
            elif op == "reset":
                self.ws.reset_layout()
                hidden_model.clear()
            elif op == "snapshot":
                saved = (self.ws.layout_text(), self._floating(), self._hidden())
            elif op == "restore" and saved is not None:
                text, floating, hidden = saved
                self.assertTrue(self.ws.restore_layout_text(text), f"step {step}")
                self._settle()
                self.assertEqual(self._floating(), floating, f"step {step} floating after restore")
                self.assertEqual(self._hidden(), hidden, f"step {step} hidden after restore")
                hidden_model = set(hidden)
            self._settle()
            self.assertEqual(self._hidden(), hidden_model, f"step {step} op {op} hidden")
            if op in ("dock_all", "reset"):
                self.assertEqual(self._floating(), set(), f"step {step} op {op} floating")
        # 무작위 순서가 실제로 여러 가지 조작을 골고루 거쳤는지 확인 (아무 일도 안 하고 통과하지 않도록)
        self.assertGreater(ran["float"], 20)
        self.assertGreater(ran["hide"], 20)
        self.assertGreater(ran["snapshot"], 5)
        self.assertGreater(ran["restore"], 5)

    def test_layout_text_round_trip_across_app_instances(self):
        settings = {"last_project": "", "sts2_path": "", "out_dir": "", "godot_path": ""}
        with patch.object(IO, "save_settings", return_value=True):
            first = A.QtApp(settings=settings)
            first.show()
            list(first._docks.values())[2].setFloating(True)   # 셋째 탭(카드)을 떼어 낸다
            _app.processEvents()
            first.closeEvent(_CloseEvent())
            self.assertIn("dock_layout", settings)
            second = A.QtApp(settings=settings)
            second.show()
            _app.processEvents()
            self.assertEqual(len(second.floating_docks()), 1)
            second._snap_timer.stop()
            second.dirty = False
            second.close()
            first._snap_timer.stop()
            first.dirty = False
            first.close()


class _CloseEvent:
    def __init__(self):
        self._accepted = None

    def accept(self):
        self._accepted = True

    def ignore(self):
        self._accepted = False

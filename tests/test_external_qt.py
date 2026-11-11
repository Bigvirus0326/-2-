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
    import externalqt as E


class _Mod:
    """ExtMod 가 탭에 보이는 만큼만 흉내 낸다."""

    def __init__(self, dll=True):
        self.id, self.name, self.version, self.author = "other_mod", "다른 모드", "1.0", "x"
        self.root, self.kind, self.dll = "C:/mods/other", "installed", "x.dll" if dll else ""
        self.characters, self.notes = [], []
        self.items = {"card": [{"id": "x", "name_ko": "가", "name_en": "A", "class": "CardA", "_cls": None}],
                      "relic": [], "potion": [], "power": []}

    def summary(self):
        return "카드 1"


class _Host:
    def __init__(self):
        self.project = M.default_project()
        self.settings = {"sts2_path": ""}
        self.dirty = 0
        self.logs = []
        self.loads = 0
        self.reloads = 0

    def mark_dirty(self):
        self.dirty += 1

    def log(self, msg):
        self.logs.append(msg)

    def load_all(self):
        self.loads += 1

    def reload_items(self):
        self.reloads += 1

    def open_mod_as_project(self, path):
        self.opened = path


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class ExternalTabQtTests(TestCase):
    def setUp(self):
        self.host = _Host()
        self.tab = E.ExternalTabQt(self.host)
        self.addCleanup(self.tab.close)
        self.tab.resize(1100, 800)
        self.tab.show()

    def _add_mod(self, dll=True):
        m = _Mod(dll)
        self.tab._loaded(m)
        return m

    def test_empty_tab_asks_for_a_mod(self):
        self.assertIn("불러오세요", self.tab.detail.text())
        self.assertEqual(self.tab.listbox.count(), 0)

    def test_loaded_mod_is_listed_and_selected(self):
        m = self._add_mod()
        self.assertEqual(self.tab.listbox.count(), 1)
        self.assertIs(self.tab.cur, m)
        self.assertTrue(self.tab.dep_btn.isEnabled())

    def test_mod_without_dll_cannot_be_referenced_or_cloned(self):
        self._add_mod(dll=False)
        self.assertFalse(self.tab.dep_btn.isEnabled())

    def test_clicking_a_tile_toggles_its_selection(self):
        self._add_mod()
        self.tab.toggle("card", 0)
        self.assertIn(("card", 0), self.tab.selected)
        self.tab.toggle("card", 0)
        self.assertNotIn(("card", 0), self.tab.selected)

    def test_search_filters_the_visible_items(self):
        self._add_mod()
        self.tab.search.setText("nothing-matches")
        self.assertEqual(self.tab.visible_items(), [])
        self.tab.search.setText("CardA")
        self.assertEqual(len(self.tab.visible_items()), 1)

    def test_clone_copies_the_selected_item_with_a_fresh_id(self):
        m = self._add_mod()
        self.tab.toggle("card", 0)
        new = {"id": "x", "name_ko": "가", "effects": []}
        with mock.patch.object(E.MI, "clone_item", return_value=new), mock.patch.object(E, "_info"):
            self.tab.clone_selected()
        self.assertEqual(self.host.project["cards"][-1]["id"], "x")
        self.assertEqual(self.host.reloads, 1)
        self.assertGreater(self.host.dirty, 0)

    def test_clone_without_selection_only_explains(self):
        self._add_mod()
        before = len(self.host.project["cards"])
        with mock.patch.object(E, "_info") as info:
            self.tab.clone_selected()
        info.assert_called_once()
        self.assertEqual(len(self.host.project["cards"]), before)

    def test_take_over_goes_through_the_app(self):
        m = self._add_mod()
        self.tab.take_over()
        self.assertEqual(self.host.opened, m.root)

    def test_closing_a_mod_removes_it_from_the_list(self):
        self._add_mod()
        self.tab.close_mod()
        self.assertEqual(self.tab.listbox.count(), 0)

    def test_a_failed_load_is_reported_in_the_log(self):
        with mock.patch.object(E, "_warn") as warn:
            self.tab._show_load_error("고장", "trace", "ValueError")
        warn.assert_called_once()
        self.assertTrue(any("고장" in line for line in self.host.logs))

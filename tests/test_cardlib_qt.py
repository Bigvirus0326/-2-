import json
import os
import sys
import tempfile
from unittest import TestCase, skipUnless, mock
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
    HAVE_QT = True
except ImportError:
    HAVE_QT = False

if HAVE_QT:
    _app = QApplication.instance() or QApplication(sys.argv)
    import app_qt as A
    import cardlibqt as CL
    import modgen as M
    import projectio as IO


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class CardLibraryQtTests(TestCase):
    def setUp(self):
        self._patches = [patch.object(IO, "save_settings", return_value=True),
                         patch.object(CL, "_warn"), patch.object(CL, "_info")]
        for p in self._patches:
            p.start()
            self.addCleanup(p.stop)
        self.tmp = tempfile.mkdtemp()
        self.app = A.QtApp(settings={"last_project": "", "sts2_path": "", "out_dir": self.tmp, "godot_path": ""})
        self.addCleanup(self._close)
        self.app.show()
        # 참고할 프로젝트 파일 하나 (기본 프로젝트를 저장한 것)
        self.source_path = os.path.join(self.tmp, "reference.sts2mod.json")
        reference = M.default_project()
        reference["cards"][0]["name_ko"] = "참고 카드"
        with open(self.source_path, "w", encoding="utf-8") as f:
            json.dump(reference, f, ensure_ascii=False)

    def _close(self):
        self.app._snap_timer.stop()
        self.app.dirty = False
        self.app.close = lambda: True
        self.app.deleteLater()

    def _library(self):
        self.app.open_card_library()
        lib = self.app._card_library
        self.addCleanup(lib.close)
        return lib

    def _open_reference(self, lib):
        with patch.object(CL, "QFileDialog") as dialog:
            dialog.getOpenFileNames.return_value = ([self.source_path], "")
            lib.open_projects()

    def test_the_card_tab_button_opens_the_library(self):
        self.assertIsNotNone(self.app.item_pages[0].library_fn)
        self.app.item_pages[0].library_fn()
        self.assertIsNotNone(self.app._card_library)
        self.addCleanup(self.app._card_library.close)

    def test_opening_a_project_file_lists_its_cards(self):
        lib = self._library()
        self._open_reference(lib)
        self.assertEqual(lib.groups.count(), 2)          # 현재 프로젝트 + 참고 파일
        self.assertGreater(lib.cards.count(), 0)
        self.assertIn("참고 카드", lib.cards.item(0).text())

    def test_adding_a_card_from_a_project_gives_it_a_new_id(self):
        lib = self._library()
        self._open_reference(lib)
        before = len(self.app.project["cards"])
        lib.cards.setCurrentRow(0)
        lib.add()
        cards = self.app.project["cards"]
        self.assertEqual(len(cards), before + 1)
        self.assertEqual(len({c["id"] for c in cards}), len(cards))
        self.assertTrue(self.app.dirty)

    def test_applying_overwrites_the_current_card_but_keeps_its_id(self):
        lib = self._library()
        self._open_reference(lib)
        card_tab = self.app.item_pages[0]
        card_tab.refresh_list(0)
        old_id = card_tab.items[0]["id"]
        lib.cards.setCurrentRow(0)
        with patch.object(CL, "_ask", return_value=True):
            self.assertTrue(lib.apply_selected())
        self.assertEqual(self.app.project["cards"][0]["id"], old_id)
        self.assertEqual(self.app.project["cards"][0]["name_ko"], "참고 카드")

    def test_applying_is_refused_when_the_user_says_no(self):
        lib = self._library()
        self._open_reference(lib)
        self.app.item_pages[0].refresh_list(0)
        lib.cards.setCurrentRow(0)
        before = self.app.project["cards"][0]["name_ko"]
        with patch.object(CL, "_ask", return_value=False):
            self.assertFalse(lib.apply_selected())
        self.assertEqual(self.app.project["cards"][0]["name_ko"], before)

    def test_game_cards_are_not_applied_without_the_game_files(self):
        lib = self._library()
        self.assertTrue(lib.source().get("current"))     # 맨 앞은 지금 프로젝트
        self.assertFalse(lib.apply_act.isEnabled())

    def test_dropping_a_project_card_imports_it_and_reports_its_new_id(self):
        lib = self._library()
        self._open_reference(lib)
        lib.cards.setCurrentRow(0)
        before = len(self.app.project["cards"])
        done = mock.Mock()
        self.assertTrue(lib.add_to_deck(done))
        self.assertEqual(len(self.app.project["cards"]), before + 1)
        done.assert_called_once_with(self.app.project["cards"][-1]["id"])

    def test_dropping_a_relic_is_refused_for_the_deck(self):
        lib = self._library()
        self._open_reference(lib)
        lib.cards.setCurrentRow(0)
        lib.set_kind("relics")
        done = mock.Mock()
        self.assertFalse(lib.add_to_deck(done))
        done.assert_not_called()

    def test_dragging_a_card_from_the_list_carries_the_card_mime(self):
        from PySide6.QtCore import Qt
        lib = self._library()
        self._open_reference(lib)
        lib.cards.setCurrentRow(0)
        with patch.object(CL, "QDrag") as drag:
            lib.cards.startDrag(Qt.DropAction.CopyAction)
        mime = drag.return_value.setMimeData.call_args[0][0]
        self.assertTrue(mime.hasFormat(CL.CARD_MIME))
        drag.return_value.exec.assert_called_once()

    def test_picking_a_card_of_the_open_project_opens_it_in_the_card_tab(self):
        lib = self._library()
        tab = self.app.item_pages[0]
        self.assertGreater(len(self.app.project["cards"]), 1)
        lib.cards.setCurrentRow(1)
        self.assertEqual(tab.cur, 1)

    def test_dropping_a_card_of_the_open_project_does_not_import_a_copy(self):
        lib = self._library()
        before = len(self.app.project["cards"])
        lib.cards.setCurrentRow(1)
        done = mock.Mock()
        self.assertTrue(lib.add_to_deck(done))
        done.assert_called_once_with(self.app.project["cards"][1]["id"])
        self.assertEqual(len(self.app.project["cards"]), before)

    def test_the_library_list_draws_cards_as_card_rows_only(self):
        lib = self._library()
        delegate = lib.cards.itemDelegate()
        index = lib.cards.model().index(0, 0)
        self.assertIs(delegate.cards._card_at(index), lib.rows[0])
        self.assertIsNone(delegate.relics._item_at(index))
        self.app.project["relics"] = [M.new_relic("R_ONE")]
        lib.set_kind("relics")
        index = lib.cards.model().index(0, 0)
        self.assertIs(delegate.relics._item_at(index), lib.rows[0])
        self.assertIsNone(delegate.cards._card_at(index))

    def test_relics_of_the_open_project_are_listed_and_drop_to_the_relic_list(self):
        self.app.project["relics"] = [M.new_relic("R_ONE")]
        lib = self._library()
        lib.set_kind("relics")
        lib.cards.setCurrentRow(0)
        self.assertEqual(lib.rows[0]["id"], "R_ONE")
        done = mock.Mock()
        self.assertTrue(lib.add_to_relics(done))
        done.assert_called_once_with("R_ONE")

    def test_a_card_is_refused_as_a_relic(self):
        lib = self._library()
        lib.cards.setCurrentRow(0)
        done = mock.Mock()
        self.assertFalse(lib.add_to_relics(done))
        done.assert_not_called()

    def test_adding_a_project_relic_copies_it_with_a_new_id(self):
        self.app.project["relics"] = [M.new_relic("R_ONE")]
        lib = self._library()
        self._open_reference(lib)
        lib.set_kind("relics")
        # 참고 파일의 유물은 같은 ID 라서 복사본은 새 ID 를 받는다
        reference = [g for k, g in lib.sources.items()][0]["project"]
        reference["relics"] = [M.new_relic("R_ONE")]
        lib.refresh_groups(self.source_path)
        lib.cards.setCurrentRow(0)
        done = mock.Mock()
        self.assertTrue(lib.add(lib.selection(), lib.source(), done))
        self.assertEqual([r["id"] for r in self.app.project["relics"]], ["R_ONE", "R_ONE_2"])
        done.assert_called_once_with("R_ONE_2")

    def test_project_keywords_are_listed_and_applied_as_card_tags(self):
        tid = "kw_flame"
        self.app.project.setdefault("gimmicks", {}).setdefault("tags", []).append(
            {"id": tid, "name_ko": "불꽃", "desc_ko": "설명"})
        lib = self._library()
        lib.set_kind("card_keywords")
        self.assertIn(tid, [r["id"] for r in lib.rows])
        card = self.app.project["cards"][0]
        card["gtags"] = []
        self.app.item_pages[0].refresh_list(0)
        lib.cards.setCurrentRow(lib.rows.index(next(r for r in lib.rows if r["id"] == tid)))
        lib.apply_selected()
        self.assertIn(tid, card["gtags"])

    def test_tags_made_in_the_gimmick_tab_appear_in_the_keyword_list(self):
        self.app.project.setdefault("gimmicks", {}).setdefault("tags", []).append(
            {"id": "gimmick_tag", "name_ko": "기믹 태그", "desc_ko": "설명"})
        lib = self._library()
        lib.set_kind("card_keywords")
        self.assertIn("gimmick_tag", [r["id"] for r in lib.rows])

    def test_a_library_window_opens_on_its_kind_and_shares_the_sources(self):
        lib = self._library()
        self._open_reference(lib)
        window = self.app.open_library_window("relics")
        self.addCleanup(window.close)
        self.assertEqual(window.kind, "relics")
        self.assertIn("유물", window.windowTitle())
        self.assertIs(window.sources, lib.sources)
        self.assertIn(self.source_path, window.sources)

    def test_a_drop_goes_to_the_window_that_started_the_drag(self):
        from unittest import mock as _mock
        window = self.app.open_library_window("cards")
        self.addCleanup(window.close)
        done = _mock.Mock()
        with _mock.patch.object(window, "add_to_deck", return_value=True) as add:
            CL.ACTIVE_DRAG["lib"] = window
            try:
                self.app.drop_card_to_deck(done)
            finally:
                CL.ACTIVE_DRAG["lib"] = None
        add.assert_called_once()

    def test_a_kind_tab_can_be_moved_out_and_back(self):
        lib = self._library()
        self.assertIn("relics", lib.kinds)
        lib.remove_kind("relics")
        self.assertNotIn("relics", lib.kinds)
        window = self.app.open_library_window("relics")
        self.addCleanup(window.close)
        self.assertEqual(window.kinds, ["relics"])
        self.assertEqual(window.kind, "relics")
        lib.add_kind("relics")
        window.remove_kind("relics")
        self.assertIn("relics", lib.kinds)
        self.assertEqual(window.kinds, [])
        self.assertFalse(window.isVisible())

    def test_dragging_a_kind_tab_out_detaches_it_and_releasing_on_a_tab_bar_merges_it_back(self):
        from unittest import mock
        from PySide6.QtCore import QEvent, QPointF, QPoint, Qt
        from PySide6.QtGui import QMouseEvent
        lib = self._library()
        bar = lib.tabs
        index = next(i for i in range(bar.count()) if bar.tabData(i) == "relics")
        tab = bar.tabRect(index)
        bar._press = (index, tab.center(), tab)
        far = QPoint(tab.center().x(), 400)                   # 탭 줄 밖으로 끌었다
        move = QMouseEvent(QEvent.Type.MouseMove, QPointF(far), QPointF(far),
                           Qt.MouseButton.LeftButton, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        with mock.patch.object(CL, "QCursor") as cursor:
            cursor.pos.return_value = bar.mapToGlobal(far)
            bar.mouseMoveEvent(move)
        window = bar._dragged
        self.assertIsNotNone(window)
        self.assertEqual(window.kinds, ["relics"])
        self.assertNotIn("relics", lib.kinds)
        window.move(bar.mapToGlobal(QPoint(0, 0)))            # 끌고 있는 창이 원래 탭 줄을 덮었다
        with mock.patch.object(CL, "QCursor") as cursor:      # 원래 탭 줄 위에서 놓았다
            cursor.pos.return_value = bar.mapToGlobal(tab.center())
            bar._tick()                                       # 버튼이 떼어졌으니 여기서 끝난다
        bar._timer.stop()
        self.assertIn("relics", lib.kinds)
        self.assertIsNone(bar._dragged)
        self.assertNotIn(window, self.app._library_windows)


    def test_the_selected_item_detail_opens_as_a_popup(self):
        lib = self._library()
        self.assertFalse(lib.detail.isVisible())
        lib.show_detail()
        self.assertTrue(lib.detail.isVisible())
        self.assertIsNot(lib.detail.parentWidget(), None)

    def test_hovering_an_item_shows_its_preview_and_leaving_hides_it(self):
        lib = self._library()
        lib.hover_row(0)
        self.assertTrue(lib._preview.isVisible())
        self.assertFalse(lib._preview.art.pixmap().isNull())
        lib.hover_row(None)
        self.assertFalse(lib._preview.isVisible())

    def test_the_library_has_menus_and_the_search_has_its_own_row(self):
        from PySide6.QtWidgets import QMenuBar
        lib = self._library()
        for _ in range(2):
            _app.processEvents()
        titles = [a.text() for a in lib.findChild(QMenuBar).actions()]
        self.assertEqual(titles, ["파일", "항목", "보기"])
        self.assertTrue(lib.search.isVisible())
        self.assertGreater(lib.search.width(), 100)      # 검색 칸은 한 줄을 쓴다 (도킹 패널은 창 폭에 따라 줄 수 있다)

    def test_the_library_window_is_narrow(self):
        lib = self._library()
        self.assertLessEqual(lib.width(), 700)

    def test_the_hover_preview_asks_the_game_renderer_for_the_card_kind(self):
        class FakeViews:
            mode = "game"
            stacks = 3

            def __init__(self):
                self.kinds = []

            def image(self, kind, item, lang, upgraded, stacks):
                self.kinds.append(kind)
                return None, "game files missing"

        lib = self._library()
        fake = FakeViews()
        lib.card_page.views = fake
        lib.hover_row(0)
        self.assertEqual(fake.kinds, ["card"])

    def test_the_library_is_a_dock_panel_that_can_sit_left_right_or_bottom(self):
        from PySide6.QtWidgets import QDockWidget
        from PySide6.QtCore import Qt
        lib = self._library()
        dock = self.app._library_dock
        self.assertIsInstance(dock, QDockWidget)
        self.assertTrue(dock.allowedAreas() & Qt.DockWidgetArea.LeftDockWidgetArea)
        self.assertTrue(dock.allowedAreas() & Qt.DockWidgetArea.RightDockWidgetArea)
        self.assertTrue(dock.allowedAreas() & Qt.DockWidgetArea.BottomDockWidgetArea)
        self.assertIs(lib.dock, dock)
        self.assertTrue(lib.isVisible())

    def test_a_detached_library_window_is_its_own_top_level_window(self):
        window = self.app.open_library_window("potions")
        self.addCleanup(window.close)
        self.assertTrue(window.isWindow())
        self.assertIsNone(window.dock)

    def test_the_library_docks_to_the_left_right_or_bottom_of_the_main_window(self):
        from PySide6.QtCore import Qt
        lib = self._library()
        for area in (Qt.DockWidgetArea.LeftDockWidgetArea, Qt.DockWidgetArea.BottomDockWidgetArea,
                     Qt.DockWidgetArea.RightDockWidgetArea):
            lib.dock.setFloating(True)
            lib.dock_to(area)
            self.assertFalse(lib.dock.isFloating())
            self.assertEqual(self.app.dockWidgetArea(lib.dock), area)
            self.assertTrue(lib.dock.isVisible())

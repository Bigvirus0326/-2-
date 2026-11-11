import os
import sys
from unittest import TestCase, skipUnless

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # 화면 없이 돌린다

try:
    from PySide6.QtWidgets import QApplication, QWidget, QLabel
    HAVE_QT = True
except ImportError:   # PySide6 가 없으면 건너뛴다
    HAVE_QT = False

if HAVE_QT:
    import qtkit as Q
    _app = QApplication.instance() or QApplication(sys.argv)


@skipUnless(HAVE_QT, "PySide6 가 설치되어 있지 않습니다")
class QtKitTests(TestCase):
    def test_theme_sets_font_and_palette_colors(self):
        Q.apply_theme(_app)
        self.assertIn(Q.C["accent"], _app.styleSheet())
        self.assertEqual(_app.font().family(), Q.FONT)

    def test_scroll_page_scrolls_tall_content(self):
        page = Q.ScrollPage()
        page.resize(300, 200)
        body = QWidget()
        body.setMinimumHeight(1000)
        page.set_content(body)
        page.show()
        _app.processEvents()
        self.assertIs(page.content(), body)
        self.assertGreater(page.verticalScrollBar().maximum(), 0)
        page.close()

    def test_tab_host_select_and_hide(self):
        host = Q.TabHost()
        pages = [host.add_page(QLabel(t), t) for t in ("a", "b", "c")]
        host.select(pages[1])
        self.assertEqual(host.currentIndex(), 1)
        host.set_visible(pages[1], False)
        self.assertFalse(host.isTabVisible(1))
        host.set_visible(pages[1], True)
        self.assertTrue(host.isTabVisible(1))
        host.close()

    def test_workspace_tabs_hides_floats_and_restores_layout(self):
        ws = Q.DockWorkspace()
        ws.resize(800, 600)
        pages = [ws.add_page(QLabel(name), name) for name in ("a", "b", "c")]
        ws.show()
        _app.processEvents()
        titles = [d.windowTitle() for d in ws.tabifiedDockWidgets(ws.dock_of(pages[0]))]
        self.assertEqual(titles, ["b", "c"])          # 처음에는 한 탭 묶음
        ws.set_visible(pages[1], False)
        _app.processEvents()
        self.assertTrue(ws.dock_of(pages[1]).isHidden())
        self.assertEqual(len(ws.view_menu_actions()), 3)
        ws.dock_of(pages[2]).setFloating(True)
        _app.processEvents()
        self.assertTrue(ws.dock_of(pages[2]).isFloating())
        state = ws.save_layout()
        self.assertTrue(ws.restore_layout(state))
        ws.close()

import time
from unittest import TestCase
from unittest.mock import patch

import sts2_mod_maker as M
import uxkit as U


def _settle(app, seconds):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        app.update()
        time.sleep(0.01)


class TabSyncTests(TestCase):
    def setUp(self):
        U._ICONS.clear()   # 이전 테스트의 Tk 창에 묶인 아이콘 이미지를 버린다
        self.app = M.App()
        self.app.withdraw()
        _settle(self.app, 0.6)   # 시작 때 미리 읽기(warm-up)가 끝날 때까지

    def tearDown(self):
        for job in self.app.tk.splitlist(self.app.tk.call("after", "info")):
            self.app.after_cancel(job)   # 앱의 주기 작업(로그 등)이 파괴 뒤에 실행되지 않게
        self.app.destroy()

    def test_plain_tab_switch_does_not_reread_tabs(self):
        app = self.app
        with patch.object(app.gallery_tab, "refresh") as refresh:
            for tab in (app.gallery_tab, app.mod_tab, app.gallery_tab):
                app.nb.select(tab)
                app.update()
        refresh.assert_not_called()

    def test_edit_rereads_other_tabs_in_background_not_on_switch(self):
        app = self.app
        with patch.object(app.gallery_tab, "refresh") as refresh:
            app.nb.select(app.mod_tab)
            app.mark_dirty()
            _settle(app, 0.6)   # 디바운스(300ms) 뒤 보이지 않는 탭 갱신
            self.assertEqual(refresh.call_count, 1)
            app.nb.select(app.gallery_tab)
            app.update()
            self.assertEqual(refresh.call_count, 1)   # 전환 때는 다시 읽지 않는다

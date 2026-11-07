"""새 창을 부모 창 가운데에 띄우는 도우미 (왼쪽 위에 깜빡 나타났다 옮겨지는 일 없이)."""
from __future__ import annotations

import re
import sys


def _work_area(x, y):
    """(x, y) 점이 있는 모니터의 작업 영역 (작업 표시줄 제외). 실패하면 None."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        class MONITORINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                        ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.restype = wintypes.HMONITOR
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        mon = user32.MonitorFromPoint(wintypes.POINT(int(x), int(y)), 2)  # MONITOR_DEFAULTTONEAREST
        mi = MONITORINFO()
        mi.cbSize = ctypes.sizeof(MONITORINFO)
        if not user32.GetMonitorInfoW(mon, ctypes.byref(mi)):
            return None
        r = mi.rcWork
        return r.left, r.top, r.right, r.bottom
    except Exception:
        return None


_DECO = None  # 실제로 잰 (왼쪽 테두리, 제목 표시줄+위 테두리) 두께. 첫 창을 띄울 때 잽니다.


def center_window(win, parent=None):
    """win 을 parent(없으면 win 의 부모 창, 그것도 없으면 화면) 가운데에 놓습니다.
    창 내용을 다 만든 뒤, grab_set() 전에 부르세요."""
    global _DECO
    placed = None
    try:
        win.withdraw()
        win.update_idletasks()
        m = re.match(r"(\d+)x(\d+)", win.geometry())
        w, h = (int(m.group(1)), int(m.group(2))) if m else (0, 0)
        if w <= 1 or h <= 1:
            w, h = win.winfo_reqwidth(), win.winfo_reqheight()
        if parent is None and win.master is not None:
            parent = win.master.winfo_toplevel()
        if parent is not None and parent.winfo_ismapped():
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
        else:
            px, py, pw, ph = 0, 0, win.winfo_screenwidth(), win.winfo_screenheight()
        # geometry("+x+y") 는 테두리·제목 표시줄을 포함한 바깥 위치라서 그만큼 빼 줍니다
        if _DECO:
            dx, dy = _DECO
        else:
            k = max(1.0, win.winfo_fpixels("1i") / 96)
            dx, dy = round(7 * k), round(30 * k)
        cx, cy = px + pw // 2, py + ph // 2
        area = _work_area(cx, cy) or (0, 0, win.winfo_screenwidth(), win.winfo_screenheight())
        placed = (cx, cy, w, h, area)
        win.geometry(_pos(cx, cy, w, h, area, dx, dy))
    except Exception:
        pass
    finally:
        try:
            win.deiconify()
        except Exception:
            pass
    if placed and not _DECO:
        # 첫 창: 실제 테두리 두께를 재서 기억하고, 어긋났으면 바로 고칩니다
        try:
            win.update_idletasks()
            bx, by = win.winfo_rootx() - win.winfo_x(), win.winfo_rooty() - win.winfo_y()
            if 0 <= bx <= 60 and 0 < by <= 120:
                _DECO = (bx, by)
                win.geometry(_pos(*placed, bx, by))
        except Exception:
            pass


def _pos(cx, cy, w, h, area, dx, dy):
    left, top, right, bottom = area
    x, y = cx - w // 2 - dx, cy - h // 2 - dy
    x = max(left, min(x, right - w - 2 * dx))
    y = max(top, min(y, bottom - h - dy - dx))
    return f"+{x}+{y}"

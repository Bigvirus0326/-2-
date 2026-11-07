# -*- coding: utf-8 -*-
"""버전 번호와 업데이트 알림.

새 버전을 배포할 때:
  1) 아래 VERSION 을 올린다 (예: "0.3" → "0.4")
  2) 빌드.bat 으로 zip 을 만든다
  3) 깃허브 Releases 에 태그 v0.4 로 올리고 zip 을 첨부한다
그러면 이전 버전 사용자가 프로그램을 켤 때 알림 창이 뜬다.
"""
import json
import os
import re
import threading
import urllib.request
import webbrowser

VERSION = "0.3"
REPO = "Bigvirus0326/-2-"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"

_auto_done = False


def parse_version(text):
    """'v0.4', '갤산0.2V', '0.10.1' → (0, 4) 같은 숫자 묶음. 숫자가 없으면 None."""
    m = re.search(r"\d+(?:\.\d+)*", text or "")
    if not m:
        return None
    return tuple(int(x) for x in m.group(0).split("."))


def _norm(v):
    v = list(v)
    while len(v) > 1 and v[-1] == 0:
        v.pop()
    return tuple(v)


def is_newer(remote, local=VERSION):
    r = remote if isinstance(remote, tuple) else parse_version(remote)
    loc = local if isinstance(local, tuple) else parse_version(local)
    if r is None or loc is None:
        return False
    return _norm(r) > _norm(loc)


def release_version(rel):
    """릴리스의 태그에서 먼저, 없으면 제목에서 버전을 읽는다."""
    for key in ("tag_name", "name"):
        v = parse_version(rel.get(key) or "")
        if v:
            return v
    return None


def fetch_latest(timeout=6):
    req = urllib.request.Request(LATEST_API, headers={
        "User-Agent": "StS2ModMaker-UpdateCheck",
        "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        rel = json.loads(r.read().decode("utf-8"))
    v = release_version(rel)
    return {
        "version": v,
        "version_text": ".".join(map(str, v)) if v else "",
        "tag": rel.get("tag_name") or "",
        "name": rel.get("name") or rel.get("tag_name") or "",
        "url": rel.get("html_url") or RELEASES_PAGE,
        "body": rel.get("body") or "",
        "assets": [a.get("name", "") for a in rel.get("assets") or []],
    }


# ---------------------------------------------------------------------------
# 화면 (tkinter 는 여기서만)

def check(app, manual=False):
    """뒤에서 최신 릴리스를 확인하고, 새 버전이면 알림 창. manual=True 면 결과를 항상 알려 준다."""
    box = {}

    def work():
        try:
            box["rel"] = fetch_latest()
        except Exception as e:  # noqa: BLE001 — 인터넷 없음·차단 등은 조용히 넘어간다
            box["err"] = e

    th = threading.Thread(target=work, daemon=True)
    th.start()

    def poll():
        try:
            if not app.winfo_exists():
                return
        except Exception:  # noqa: BLE001
            return
        if th.is_alive():
            app.after(200, poll)
            return
        _done(app, box, manual)

    app.after(200, poll)


def auto_check(app):
    """프로그램을 켤 때 한 번만 (화면 배율을 바꿔 창을 다시 만들어도 다시 묻지 않음)."""
    global _auto_done
    if _auto_done or os.environ.get("STS2MM_NO_UPDATE"):
        return
    _auto_done = True
    if not app.settings.get("update_check", True):
        return
    check(app, manual=False)


def _done(app, box, manual):
    from tkinter import messagebox
    rel = box.get("rel")
    if rel is None:
        if manual:
            messagebox.showwarning("업데이트 확인", "깃허브에 연결하지 못했습니다.\n인터넷 연결을 확인하거나 나중에 다시 해 보세요.\n\n"
                                   f"({box.get('err')})", parent=app)
        return
    if not rel["version"] or not is_newer(rel["version"]):
        if manual:
            messagebox.showinfo("업데이트 확인", f"지금 최신 버전입니다 (v{VERSION}).", parent=app)
        return
    if not manual and app.settings.get("update_skip") == rel["version_text"]:
        return
    UpdateDialog(app, rel)


class UpdateDialog:
    def __init__(self, app, rel):
        import tkinter as tk
        from tkinter import ttk
        self.app, self.rel = app, rel
        w = self.win = tk.Toplevel(app)
        w.title("업데이트 알림")
        w.transient(app)
        w.resizable(True, True)
        f = ttk.Frame(w, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"새 버전 v{rel['version_text']} 이 나왔습니다", font=("", 13, "bold")).pack(anchor="w")
        ttk.Label(f, text=f"지금 쓰는 버전: v{VERSION}    ·    {rel['name']}", foreground="#666").pack(anchor="w", pady=(2, 8))
        body = rel["body"].strip()
        if body:
            ttk.Label(f, text="바뀐 내용").pack(anchor="w")
            tf = ttk.Frame(f)
            tf.pack(fill="both", expand=True, pady=(2, 8))
            t = tk.Text(tf, height=min(14, max(4, body.count("\n") + 2)), width=64, wrap="word", relief="solid", bd=1)
            sb = ttk.Scrollbar(tf, orient="vertical", command=t.yview)
            t.configure(yscrollcommand=sb.set)
            t.insert("1.0", body[:6000])
            t.configure(state="disabled")
            t.pack(side="left", fill="both", expand=True)
            sb.pack(side="right", fill="y")
        ttk.Label(f, text="다운로드 페이지에서 zip 을 받아 새 폴더에 풀어 쓰세요.\n"
                          "만들던 모드 프로젝트(.json)는 그대로 열 수 있습니다.", foreground="#666").pack(anchor="w")
        bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(10, 0))
        ttk.Button(bf, text="⬇ 다운로드 페이지 열기", command=self.open_page).pack(side="left")
        ttk.Button(bf, text="나중에", command=w.destroy).pack(side="right")
        ttk.Button(bf, text="이 버전은 다시 알리지 않기", command=self.skip).pack(side="right", padx=6)
        w.bind("<Escape>", lambda _e: w.destroy())
        w.update_idletasks()
        try:
            x = app.winfo_rootx() + max(0, (app.winfo_width() - w.winfo_width()) // 2)
            y = app.winfo_rooty() + max(0, (app.winfo_height() - w.winfo_height()) // 3)
            w.geometry(f"+{x}+{y}")
        except Exception:  # noqa: BLE001
            pass
        w.lift()
        w.focus_set()

    def open_page(self):
        webbrowser.open(self.rel["url"])
        self.win.destroy()

    def skip(self):
        self.app.settings["update_skip"] = self.rel["version_text"]
        getattr(self.app, "persist_settings", lambda: None)()
        self.win.destroy()

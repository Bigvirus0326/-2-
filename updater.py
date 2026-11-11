# -*- coding: utf-8 -*-
"""버전 번호, 업데이트 알림, 자동 업데이트.

새 버전을 배포할 때:
  1) 아래 VERSION 을 올린다 (예: "0.4" → "0.5")
  2) 빌드.bat 으로 zip 을 만든다
  3) 깃허브 Releases 에 태그 v0.5 로 올리고 exe 판 zip 을 첨부한다
그러면 이전 버전 사용자가 프로그램을 켤 때 알림 창이 뜨고, [지금 업데이트] 한 번으로
새 zip 을 받아 프로그램 파일을 바꾸고 다시 켠다 (설정·출력 폴더는 그대로).
"""
import release_signature
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
import webbrowser
import zipfile

VERSION = "0.12"
REPO = "Bigvirus0326/-2-"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
LATEST_API = f"https://api.github.com/repos/{REPO}/releases/latest"
UA = "StS2ModMaker-UpdateCheck"
EXE_NAME = "StS2ModMaker.exe"
MAIN_PY = "sts2_mod_maker.py"
# 업데이트할 때 건드리지 않는 것 (사용자 파일)
KEEP_FILES = ("settings.json", "selftest.json")
KEEP_DIRS = ("output", "ai_requests", "logs", ".git", ".build_env", ".build_tmp", "배포")
LOG_PATH = os.path.join(tempfile.gettempdir(), "sts2mm_update.log")

_auto_done = False


# ---------------------------------------------------------------------------
# 버전

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


def _get_json(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_latest(timeout=6, prerelease=False):
    """최신 릴리스. prerelease=True 면 깃허브에서 'Pre-release' 로 표시한 시험판까지 포함해 가장 높은 버전."""
    if prerelease:
        rels = [x for x in _get_json(LATEST_API.rsplit("/", 1)[0] + "?per_page=20", timeout)
                if not x.get("draft") and release_version(x)]
        if not rels:
            raise OSError("릴리스가 없습니다.")
        rel = max(rels, key=lambda x: _norm(release_version(x)))
    else:
        rel = _get_json(LATEST_API, timeout)
    v = release_version(rel)
    return {
        "version": v,
        "version_text": ".".join(map(str, v)) if v else "",
        "tag": rel.get("tag_name") or "",
        "name": rel.get("name") or rel.get("tag_name") or "",
        "url": rel.get("html_url") or RELEASES_PAGE,
        "prerelease": bool(rel.get("prerelease")),
        "body": rel.get("body") or "",
        "assets": [{"name": a.get("name", ""), "url": a.get("browser_download_url", ""),
                    "digest": a.get("digest"), "size": int(a.get("size") or 0)} for a in rel.get("assets") or []],
    }


# ---------------------------------------------------------------------------
# 자동 업데이트 (화면과 무관한 부분)

def is_frozen():
    return bool(getattr(sys, "frozen", False))


def install_dir():
    if is_frozen():
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def self_update_block_reason(dst=None):
    """자동 업데이트를 할 수 없으면 그 이유, 할 수 있으면 ''."""
    dst = dst or install_dir()
    if sys.platform != "win32":
        return "자동 업데이트는 Windows 에서만 됩니다."
    if not is_frozen():
        return "소스(실행.bat)로 실행 중이라 자동 업데이트를 하지 않습니다 (exe 판에서만 됩니다)."
    try:
        probe = os.path.join(dst, ".update_write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
    except OSError:
        return "프로그램 폴더에 쓸 수 없습니다 (Program Files 같은 곳이면 다른 폴더로 옮겨 주세요)."
    return ""


def _is_source_zip(name):
    n = name.lower()
    return "source" in n or "소스" in n or "src" in n


def pick_asset(assets, frozen=None):
    """exe 판이면 소스판이 아닌 zip 중 가장 큰 것, 소스판이면 이름에 source/소스 가 든 zip."""
    frozen = is_frozen() if frozen is None else frozen
    zips = [a for a in assets if a.get("name", "").lower().endswith(".zip") and a.get("url")]
    if frozen:
        cands = [a for a in zips if not _is_source_zip(a["name"])]
        return max(cands, key=lambda a: a.get("size", 0)) if cands else None
    cands = [a for a in zips if _is_source_zip(a["name"])]
    return cands[0] if cands else None


def download(url, dest, expected=0, progress=None, cancel=None, timeout=20, *, digest=None):
    if not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest or ""):
        raise ValueError("릴리스에 유효한 SHA-256 검증값이 없어 자동 업데이트를 중단했습니다.")
    checksum = hashlib.sha256()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    done = 0
    with urllib.request.urlopen(req, timeout=timeout) as r, open(dest, "wb") as f:
        total = int(r.headers.get("Content-Length") or expected or 0)
        while True:
            if cancel is not None and cancel.is_set():
                raise InterruptedError("취소했습니다.")
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            checksum.update(chunk)
            f.write(chunk)
            done += len(chunk)
            if progress:
                progress(done, total)
    if expected and done != expected:
        raise OSError(f"받은 크기가 다릅니다 ({done} / {expected} 바이트). 다시 시도해 주세요.")
    if checksum.hexdigest() != digest[7:].lower():
        raise ValueError("업데이트 파일의 SHA-256이 릴리스와 일치하지 않습니다.")
    return dest


def stage(zip_path, work, frozen=None):
    """zip 을 풀고, 새 프로그램 파일이 든 폴더(exe 또는 sts2_mod_maker.py 가 있는 곳)를 돌려준다."""
    frozen = is_frozen() if frozen is None else frozen
    marker = EXE_NAME if frozen else MAIN_PY
    out = os.path.join(work, "new")
    os.makedirs(out, exist_ok=True)
    base = os.path.realpath(out)
    with zipfile.ZipFile(zip_path) as z:
        bad = z.testzip()
        if bad:
            raise OSError(f"zip 파일이 깨졌습니다: {bad}")
        for m in z.namelist():
            target = os.path.realpath(os.path.join(out, m))
            if not (target == base or target.startswith(base + os.sep)):
                raise OSError(f"zip 안의 경로가 이상합니다: {m}")
        z.extractall(out)
    found = []
    for root, _dirs, files in os.walk(out):
        if marker in files:
            found.append(root)
    if not found:
        raise OSError(f"받은 zip 에 {marker} 가 없습니다. 다운로드 페이지에서 직접 받아 주세요.")
    return min(found, key=lambda p: p.count(os.sep))


def relaunch_command(dst=None):
    dst = dst or install_dir()
    if is_frozen():
        return [os.path.join(dst, EXE_NAME)]
    pyw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    return [pyw if os.path.exists(pyw) else sys.executable, os.path.join(dst, MAIN_PY)]


def _ps(s):
    return "'" + str(s).replace("'", "''") + "'"


def write_swap_script(src, dst, pid, relaunch, work, version_text=""):
    """프로그램이 꺼지길 기다렸다가 파일을 바꾸고 다시 켜는 PowerShell 스크립트."""
    keep_d = " ".join(_ps(d) for d in KEEP_DIRS + ("_internal",))
    keep_f = " ".join(_ps(f) for f in KEEP_FILES)
    args = ", ".join(_ps('"' + a + '"') for a in relaunch[1:])
    arglist = f" -ArgumentList @({args})" if args else ""
    msg = ("자동 업데이트 중 파일을 바꾸지 못했습니다.\n"
           "깃허브 다운로드 페이지에서 새 버전을 직접 받아 주세요.\n\n"
           f"기록: {LOG_PATH}")
    text = f"""# 슬더스2 모드 메이커 자동 업데이트 (v{version_text})
$ErrorActionPreference = 'Continue'
$log = {_ps(LOG_PATH)}
function L($m) {{ Add-Content -LiteralPath $log -Value ("[{{0}}] {{1}}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $m) -Encoding UTF8 }}
L 'start v{version_text}'
try {{ Wait-Process -Id {int(pid)} -Timeout 120 -ErrorAction SilentlyContinue }} catch {{}}
Start-Sleep -Milliseconds 800
$src = {_ps(src)}
$dst = {_ps(dst)}
$ok = $true
$si = Join-Path $src '_internal'
if (Test-Path -LiteralPath $si) {{
    robocopy $si (Join-Path $dst '_internal') /MIR /R:30 /W:1 /NP /NFL /NDL /NJH /NJS | Out-Null
    L ("_internal rc=" + $LASTEXITCODE)
    if ($LASTEXITCODE -ge 8) {{ $ok = $false }}
}}
robocopy $src $dst /E /XD {keep_d} /XF {keep_f} /R:30 /W:1 /NP /NFL /NDL /NJH /NJS | Out-Null
L ("files rc=" + $LASTEXITCODE)
if ($LASTEXITCODE -ge 8) {{ $ok = $false }}
if (-not $ok) {{
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show({_ps(msg)}, '슬더스2 모드 메이커') | Out-Null
}}
Start-Process -FilePath {_ps(relaunch[0])}{arglist} -WorkingDirectory $dst
L ('done ok=' + $ok)
Start-Sleep -Seconds 2
Remove-Item -LiteralPath {_ps(work)} -Recurse -Force -ErrorAction SilentlyContinue
"""
    path = os.path.join(work, "swap.ps1")
    with open(path, "w", encoding="utf-8-sig") as f:
        f.write(text)
    return path


def launch_swap(script):
    # NEW_PROCESS_GROUP | NO_WINDOW  (DETACHED_PROCESS 를 쓰면 PowerShell 이 콘솔이 없어 바로 꺼진다)
    flags = 0x00000200 | 0x08000000
    return subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
                             "-File", script], creationflags=flags, close_fds=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# ---------------------------------------------------------------------------
# 화면 (tkinter 는 여기서만)

def check(app, manual=False):
    """뒤에서 최신 릴리스를 확인하고, 새 버전이면 알림 창. manual=True 면 결과를 항상 알려 준다."""
    box = {}

    def work():
        try:
            box["rel"] = fetch_latest(prerelease=bool(app.settings.get("update_prerelease")))
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
    last = app.settings.get("last_version")
    if last != VERSION:
        if last and is_newer(VERSION, last):
            st = getattr(app, "status", None)
            if callable(st):
                st(f"v{VERSION} 로 업데이트되었습니다.", 8000)
        app.settings["last_version"] = VERSION
        getattr(app, "persist_settings", lambda: None)()
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
        self.asset = pick_asset(rel.get("assets") or [])
        self.block = self_update_block_reason()
        if not self.block and not self.asset:
            self.block = "이 릴리스에 맞는 zip 파일이 없어 자동 업데이트를 할 수 없습니다."
        self.cancel_ev = threading.Event()
        self.running = False
        w = self.win = tk.Toplevel(app)
        w.title("업데이트 알림")
        w.transient(app)
        w.resizable(True, True)
        w.protocol("WM_DELETE_WINDOW", self.close)
        f = ttk.Frame(w, padding=14)
        f.pack(fill="both", expand=True)
        ttk.Label(f, text=f"새 {'시험판' if rel.get('prerelease') else '버전'} v{rel['version_text']} 이 나왔습니다", font=("", 13, "bold")).pack(anchor="w")
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
        if self.block:
            note = self.block + "\n다운로드 페이지에서 zip 을 받아 새 폴더에 풀어 쓰세요."
        else:
            note = ("[지금 업데이트] 를 누르면 새 버전을 받아 프로그램을 바꾸고 다시 켭니다.\n"
                    "설정·출력 폴더와 모드 프로젝트(.json)는 그대로 남습니다.")
        self.note = ttk.Label(f, text=note, foreground="#666", justify="left")
        self.note.pack(anchor="w")
        self.prog_var = tk.DoubleVar(value=0)
        self.prog = ttk.Progressbar(f, variable=self.prog_var, maximum=100)
        self.bf = bf = ttk.Frame(f)
        bf.pack(fill="x", pady=(10, 0))
        if not self.block:
            self.go_btn = ttk.Button(bf, text="⟳ 지금 업데이트", command=self.start)
            self.go_btn.pack(side="left")
            ttk.Button(bf, text="다운로드 페이지", command=self.open_page).pack(side="left", padx=6)
        else:
            ttk.Button(bf, text="⬇ 다운로드 페이지 열기", command=self.open_page).pack(side="left")
        self.later_btn = ttk.Button(bf, text="나중에", command=self.close)
        self.later_btn.pack(side="right")
        self.skip_btn = ttk.Button(bf, text="이 버전은 다시 알리지 않기", command=self.skip)
        self.skip_btn.pack(side="right", padx=6)
        w.bind("<Escape>", lambda _e: self.close())
        w.update_idletasks()
        try:
            x = app.winfo_rootx() + max(0, (app.winfo_width() - w.winfo_width()) // 2)
            y = app.winfo_rooty() + max(0, (app.winfo_height() - w.winfo_height()) // 3)
            w.geometry(f"+{x}+{y}")
        except Exception:  # noqa: BLE001
            pass
        w.lift()
        w.focus_set()

    # -- 버튼
    def open_page(self):
        webbrowser.open(self.rel["url"])
        if not self.running:
            self.win.destroy()

    def skip(self):
        self.app.settings["update_skip"] = self.rel["version_text"]
        getattr(self.app, "persist_settings", lambda: None)()
        self.win.destroy()

    def close(self):
        if self.running:
            self.cancel_ev.set()
            return
        self.win.destroy()

    # -- 자동 업데이트
    def start(self):
        from tkinter import messagebox
        app = self.app
        if getattr(app, "busy", False):
            messagebox.showinfo("업데이트", "빌드 중에는 업데이트할 수 없습니다. 빌드가 끝난 뒤 다시 눌러 주세요.", parent=self.win)
            return
        confirm = getattr(app, "confirm_discard", None)
        if callable(confirm) and not confirm():
            return
        self.running = True
        for b in (self.go_btn, self.skip_btn):
            b.configure(state="disabled")
        self.later_btn.configure(text="취소")
        self.prog.pack(fill="x", pady=(8, 0), before=self.bf)
        self.note.configure(text="새 버전 받는 중…")
        st = self.state = {"done": 0, "total": self.asset.get("size", 0), "phase": "download"}
        self.work = tempfile.mkdtemp(prefix="sts2mm_update_")

        def run():
            try:
                zp = os.path.join(self.work, "update.zip")
                name = self.asset["name"] + ".sig"
                signatures = [a for a in self.rel["assets"] if a["name"] == name]
                if len(signatures) != 1 or signatures[0]["size"] != 384:
                    raise ValueError("이 업데이트의 배포자 서명 파일이 없거나 올바르지 않습니다.")
                req = urllib.request.Request(signatures[0]["url"], headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=20) as response:
                    signature = response.read(385)
                download(self.asset["url"], zp, self.asset.get("size", 0),
                         progress=lambda d, t: st.update(done=d, total=t), cancel=self.cancel_ev, digest=self.asset.get("digest"))
                release_signature.verify(zp, signature)
                st["phase"] = "stage"
                st["src"] = stage(zp, self.work)
                os.remove(zp)
                st["phase"] = "ready"
            except Exception as e:  # noqa: BLE001
                st["phase"] = "error"
                st["err"] = e

        self.th = threading.Thread(target=run, daemon=True)
        self.th.start()
        self.win.after(150, self._poll)

    def _poll(self):
        from tkinter import messagebox
        try:
            if not self.win.winfo_exists():
                return
        except Exception:  # noqa: BLE001
            return
        st = self.state
        if st["phase"] == "download":
            tot = st["total"] or 1
            self.prog_var.set(min(100, st["done"] * 100 / tot))
            self.note.configure(text=f"새 버전 받는 중… {st['done'] / 1e6:.1f} / {st['total'] / 1e6:.1f} MB")
        elif st["phase"] == "stage":
            self.prog_var.set(100)
            self.note.configure(text="압축 푸는 중…")
        if self.th.is_alive():
            self.win.after(150, self._poll)
            return
        if st["phase"] == "error":
            shutil.rmtree(self.work, ignore_errors=True)
            self.running = False
            if isinstance(st.get("err"), InterruptedError):
                self.win.destroy()
                return
            messagebox.showerror("업데이트 실패", f"자동 업데이트를 하지 못했습니다.\n{st['err']}\n\n"
                                 "[다운로드 페이지] 에서 직접 받을 수 있습니다.", parent=self.win)
            self.go_btn.configure(state="normal")
            self.skip_btn.configure(state="normal")
            self.later_btn.configure(text="나중에")
            self.prog.pack_forget()
            self.note.configure(text="자동 업데이트에 실패했습니다. 다시 누르거나 다운로드 페이지에서 받아 주세요.")
            return
        self.note.configure(text="새 버전으로 바꾸고 다시 켭니다…")
        self.win.update_idletasks()
        try:
            dst = install_dir()
            script = write_swap_script(st["src"], dst, os.getpid(), relaunch_command(dst), self.work,
                                       self.rel["version_text"])
            launch_swap(script)
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(self.work, ignore_errors=True)
            self.running = False
            messagebox.showerror("업데이트 실패", f"업데이트 도우미를 실행하지 못했습니다:\n{e}", parent=self.win)
            self.win.destroy()
            return
        self.app.after(400, self._quit_app)

    def _quit_app(self):
        app = self.app
        app.dirty = False
        app._restart_state = None
        app.destroy()

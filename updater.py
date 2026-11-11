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

"""
다른 모드 불러오기.

지원하는 형태
  - 설치된 모드 폴더 (모드ID.json + .dll + .pck)          dll 은 ilspycmd 로 C# 코드로 되돌려 읽는다
  - C# 소스 프로젝트 폴더 (.csproj, .cs, 모드ID/localization)
  - .pck 파일 하나 (안에 든 현지화·그림, 소스가 들어 있으면 소스도)
  - .dll 파일 하나, 모드 manifest(.json)

읽은 결과(ExtMod)는
  - 도감/게임 화면 미리보기
  - 내 프로젝트로 복제 (원본 클래스를 상속해서 원래 동작을 유지)
  - 내 모드에서 참조 (의존성 + 그 모드의 파워 사용)
에 쓰인다.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading

import ingame
import modgen as M

ROOTS = {
    "card": {"CustomCardModel", "CardModel"},
    "relic": {"CustomRelicModel", "RelicModel"},
    "potion": {"CustomPotionModel", "PotionModel"},
    "power": {"CustomPowerModel", "PowerModel"},
    "card_pool": {"CustomCardPoolModel", "CardPoolModel"},
    "character": {"CustomCharacterModel", "PlaceholderCharacterModel", "CharacterModel"},
}
LOC_FILE = {"card": "cards", "relic": "relics", "potion": "potions", "power": "powers", "character": "characters"}
DEFAULT_VAR_NAME = {
    "DamageVar": "Damage", "BlockVar": "Block", "CardsVar": "Cards", "EnergyVar": "Energy", "HealVar": "Heal",
    "HpLossVar": "HpLoss", "MaxHpVar": "MaxHp", "GoldVar": "Gold", "RepeatVar": "Repeat", "StarsVar": "Stars",
    "ForgeVar": "Forge", "SummonVar": "Summon", "CalculationBaseVar": "CalculationBase",
    "ExtraDamageVar": "ExtraDamage", "CalculatedDamageVar": "CalculatedDamage",
    "CalculatedBlockVar": "CalculatedBlock",
}
ACCESSOR_VAR = {"Damage": "Damage", "Block": "Block", "Cards": "Cards", "Energy": "Energy", "Heal": "Heal",
                "HpLoss": "HpLoss", "MaxHp": "MaxHp", "Gold": "Gold", "Repeat": "Repeat"}


def cache_root():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    return os.path.join(base, "sts2_mod_maker")


# ---------------------------------------------------------------------------
# 이름 규칙 (게임과 같음: 첫 글자 빼고 대문자 앞에 _ , 전부 대문자)
# ---------------------------------------------------------------------------
def game_snake(name):
    return M.game_snake(name)


def class_to_id(cls):
    """클래스명 -> 이 프로그램의 ID (pascal(ID) 로 다시 같은 클래스명이 나온다)."""
    return game_snake(cls).lower()


# ---------------------------------------------------------------------------
# 디컴파일 (ilspycmd)
# ---------------------------------------------------------------------------
_DECOMPILE_LOCK = threading.RLock()
_DECOMPILE_MARKER = ".sts2mm-decompile.json"


def _ilspy_cmd():
    tools = os.path.join(cache_root(), "tools")
    exe = os.path.join(tools, "ilspycmd.exe" if sys.platform == "win32" else "ilspycmd")
    if not os.path.isfile(exe):
        alt = os.path.join(tools, "ilspycmd.cmd")
        if os.path.isfile(alt):
            return alt
    return exe


def _run_capture(cmd, env=None):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              creationflags=_NOWIN, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        detail = str(exc).strip() or repr(exc).strip() or type(exc).__name__
        raise RuntimeError(f"명령을 실행하지 못했습니다: {' '.join(map(str, cmd))}\n{detail}") from exc


def _process_failure(label, cmd, result):
    lines = [label, f"명령: {' '.join(map(str, cmd))}", f"종료 코드: {result.returncode}"]
    has_output = False
    for name, value in (("표준 오류", result.stderr), ("표준 출력", result.stdout)):
        value = (value or "").strip()
        if value:
            has_output = True
            lines.extend([f"{name}:", value[-3000:]])
    if not has_output:
        lines.append("프로그램이 오류 세부 내용을 출력하지 않았습니다. .NET SDK 또는 디컴파일러 설치를 확인해 주세요.")
    return "\n".join(lines)


def _dotnet_exe():
    dotnet = shutil.which("dotnet")
    if not dotnet:
        raise RuntimeError(".NET SDK(dotnet)를 찾지 못했습니다. SDK 9 이상을 설치한 뒤 앱을 다시 실행해 주세요.")
    cmd = [dotnet, "--version"]
    result = _run_capture(cmd)
    if result.returncode != 0:
        raise RuntimeError(_process_failure(".NET SDK 확인에 실패했습니다.", cmd, result))
    return dotnet


def _remove_decompiler_install(tools):
    for name in ("ilspycmd.exe", "ilspycmd.cmd"):
        path = os.path.join(tools, name)
        try:
            if os.path.isfile(path):
                os.remove(path)
        except OSError as exc:
            detail = str(exc).strip() or repr(exc).strip() or type(exc).__name__
            raise RuntimeError(f"손상된 디컴파일러 파일을 지우지 못했습니다.\n{path}\n{detail}") from exc
    shutil.rmtree(os.path.join(tools, ".store", "ilspycmd"), ignore_errors=True)


def _install_decompiler(tools, dotnet, log, previous_error=""):
    log("dll 을 읽기 위한 디컴파일러(ilspycmd)를 설치합니다...")
    cmd = [dotnet, "tool", "install", "ilspycmd", "--tool-path", tools]
    result = _run_capture(cmd)
    if result.returncode != 0:
        detail = _process_failure("ilspycmd 설치에 실패했습니다.", cmd, result)
        if previous_error:
            detail = f"기존 설치 확인 결과:\n{previous_error}\n\n{detail}"
        raise RuntimeError(detail)
    exe = _ilspy_cmd()
    if not os.path.isfile(exe):
        raise RuntimeError(f"ilspycmd 설치 명령은 끝났지만 실행 파일을 찾지 못했습니다.\n예상 경로: {exe}\n"
                           "앱 폴더의 쓰기 권한과 .NET SDK 설치를 확인해 주세요.")
    env = dict(os.environ, DOTNET_ROLL_FORWARD="Major")
    probe_cmd = [exe, "--version"]
    probe = _run_capture(probe_cmd, env=env)
    if probe.returncode != 0:
        detail = _process_failure("설치한 ilspycmd가 실행되지 않습니다.", probe_cmd, probe)
        if previous_error:
            detail = f"기존 설치 확인 결과:\n{previous_error}\n\n{detail}"
        raise RuntimeError(detail)
    return exe


def ensure_decompiler(log=print):
    exe = _ilspy_cmd()
    if os.path.isfile(exe):
        probe_cmd = [exe, "--version"]
        try:
            probe = _run_capture(probe_cmd, env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
            if probe.returncode == 0:
                return exe
            previous_error = _process_failure("저장된 ilspycmd가 정상 실행되지 않습니다.", probe_cmd, probe)
        except Exception as exc:  # noqa: BLE001 — 중단된 설치를 자동 복구한다
            previous_error = str(exc).strip() or repr(exc).strip() or type(exc).__name__
        log("저장된 디컴파일러가 실행되지 않아 설치를 복구합니다...")
    else:
        previous_error = ""
    tools = os.path.join(cache_root(), "tools")
    os.makedirs(tools, exist_ok=True)
    dotnet = _dotnet_exe()
    if previous_error or os.path.isdir(os.path.join(tools, ".store", "ilspycmd")):
        _remove_decompiler_install(tools)
    return _install_decompiler(tools, dotnet, log, previous_error)


_NOWIN = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def _source_files(folder):
    return glob.glob(os.path.join(folder, "**", "*.cs"), recursive=True)


def _source_stats(folder):
    files = _source_files(folder)
    try:
        return len(files), sum(os.path.getsize(path) for path in files)
    except OSError:
        return 0, 0


def _valid_decompile_cache(folder, dll, st):
    marker_path = os.path.join(folder, _DECOMPILE_MARKER)
    try:
        with open(marker_path, encoding="utf-8") as stream:
            marker = json.load(stream)
        count, size = _source_stats(folder)
        return bool(count and marker.get("dll") == os.path.abspath(dll) and
                    marker.get("dll_size") == st.st_size and
                    marker.get("dll_mtime_ns") == getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)) and
                    marker.get("source_count") == count and marker.get("source_bytes") == size)
    except (OSError, ValueError, TypeError, AttributeError):
        return False


def decompile(dll, sts2_path="", extra_refs=(), log=print, force=False):
    """dll -> C# 소스 폴더 (캐시). 실패하면 예외."""
    st = os.stat(dll)
    key = hashlib.sha1(f"{os.path.abspath(dll)}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]
    out = os.path.join(cache_root(), "decompiled", f"{os.path.splitext(os.path.basename(dll))[0]}-{key}")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with _DECOMPILE_LOCK:
        backup = out + ".previous"
        if os.path.isdir(backup):
            if not os.path.exists(out):
                try:
                    os.replace(backup, out)
                except OSError:
                    pass
            elif _valid_decompile_cache(out, dll, st):
                shutil.rmtree(backup, ignore_errors=True)
            elif _valid_decompile_cache(backup, dll, st):
                shutil.rmtree(out, ignore_errors=True)
                try:
                    os.replace(backup, out)
                except OSError:
                    pass
            else:
                shutil.rmtree(backup, ignore_errors=True)
        if not force and _valid_decompile_cache(out, dll, st):
            return out
        if os.path.isdir(out):
            log("기존 원본 코드 캐시가 불완전하거나 이전 형식이라 다시 읽습니다...")
        exe = ensure_decompiler(log)
        temp_out = f"{out}.tmp-{os.getpid()}-{threading.get_ident()}"
        shutil.rmtree(temp_out, ignore_errors=True)
        os.makedirs(temp_out, exist_ok=True)
        cmd = [exe, "-p", "-o", temp_out]
        refs = list(extra_refs)
        if sts2_path:
            refs.append(os.path.join(sts2_path, "data_sts2_windows_x86_64"))
            for sub in ("mods", "mods.disabled"):
                for d in glob.glob(os.path.join(sts2_path, sub, "*")):
                    if os.path.isdir(d):
                        refs.append(d)
        for ref in refs:
            if os.path.isdir(ref):
                cmd += ["-r", ref]
        cmd.append(dll)
        log(f"dll 읽는 중: {os.path.basename(dll)}")
        try:
            result = _run_capture(cmd, env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
            if result.returncode != 0:
                raise RuntimeError(_process_failure("원본 DLL 디컴파일에 실패했습니다.", cmd, result))
            count, size = _source_stats(temp_out)
            if not count:
                raise RuntimeError(_process_failure("디컴파일은 종료됐지만 C# 파일이 생성되지 않았습니다.", cmd, result))
            marker = {
                "dll": os.path.abspath(dll), "dll_size": st.st_size,
                "dll_mtime_ns": getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)),
                "source_count": count, "source_bytes": size,
            }
            marker_tmp = os.path.join(temp_out, _DECOMPILE_MARKER + ".tmp")
            with open(marker_tmp, "w", encoding="utf-8") as stream:
                json.dump(marker, stream, ensure_ascii=False)
            os.replace(marker_tmp, os.path.join(temp_out, _DECOMPILE_MARKER))

            shutil.rmtree(backup, ignore_errors=True)
            if os.path.isdir(out):
                os.replace(out, backup)
            try:
                os.replace(temp_out, out)
            except OSError:
                if os.path.isdir(backup) and not os.path.exists(out):
                    os.replace(backup, out)
                raise
            shutil.rmtree(backup, ignore_errors=True)
        except Exception as exc:
            shutil.rmtree(temp_out, ignore_errors=True)
            log(f"[오류] 원본 DLL을 읽지 못했습니다: {str(exc).strip() or repr(exc).strip() or type(exc).__name__}")
            raise
        return out


# ---------------------------------------------------------------------------
# C# 간단 파서
# ---------------------------------------------------------------------------
def strip_comments(src):
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if src.startswith("//", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            seg = src[i:(n if j < 0 else j + 2)]
            out.append(re.sub(r"[^\n]", " ", seg))
            i = n if j < 0 else j + 2
            continue
        if c == '"' or (c == "@" and i + 1 < n and src[i + 1] == '"') or (c == "$" and i + 1 < n and src[i + 1] == '"'):
            j = i + (2 if c in "@$" else 1)
            verbatim = c == "@"
            while j < n:
                if src[j] == "\\" and not verbatim:
                    j += 2
                    continue
                if src[j] == '"':
                    if verbatim and j + 1 < n and src[j + 1] == '"':
                        j += 2
                        continue
                    break
                j += 1
            out.append(src[i:j + 1])
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            while j < n and src[j] != "'":
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1])
            i = j + 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def match_bracket(s, i, open_c="{", close_c="}"):
    """s[i] 가 여는 괄호일 때 짝이 맞는 닫는 괄호 위치. 문자열 안은 건너뛴다."""
    depth, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == '"':
            j = i + 1
            while j < n and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            i = j + 1
            continue
        if c == "'":
            j = i + 1
            while j < n and s[j] != "'":
                j += 2 if s[j] == "\\" else 1
            i = j + 1
            continue
        if c == open_c:
            depth += 1
        elif c == close_c:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def split_args(s):
    out, depth, cur, i = [], 0, [], 0
    while i < len(s):
        c = s[i]
        if c == '"':
            j = i + 1
            while j < len(s) and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            cur.append(s[i:j + 1])
            i = j + 1
            continue
        if c in "([{<":
            depth += 1
        elif c in ")]}>":
            depth -= 1
        if c == "," and depth == 0:
            out.append("".join(cur).strip())
            cur = []
        else:
            cur.append(c)
        i += 1
    if "".join(cur).strip():
        out.append("".join(cur).strip())
    return out


class CsClass:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def __repr__(self):
        return f"<{self.full} : {self.base}>"


_CLASS_RE = re.compile(
    r"((?:\[[^\[\]]*(?:\[[^\[\]]*\][^\[\]]*)*\]\s*)*)"            # 속성
    r"((?:(?:public|internal|private|protected|sealed|abstract|static|partial|file|unsafe|new)\s+)*)"
    r"(class|record)\s+(\w+)\s*(<[^>{(]*>)?\s*(\((?:[^()]|\([^()]*\))*\))?\s*(?::\s*([^{;]+?))?\s*(?:where\s[^{]*)?\{")


def parse_cs(text, path=""):
    src = strip_comments(text)
    usings = [u.strip() for u in re.findall(r"^\s*(using\s+(?!\()[^;=]+(?:=[^;]+)?;)", src, re.M)
              if not u.strip().startswith("using var")]
    ns_marks = [(m.start(), m.group(1)) for m in re.finditer(r"\bnamespace\s+([\w.]+)\s*[;{]", src)]
    classes, taken = [], []
    for m in _CLASS_RE.finditer(src):
        start = m.start(3)
        if any(a <= start <= b for a, b in taken):
            continue  # 중첩 클래스는 건너뜀
        ob = m.end() - 1
        cb = match_bracket(src, ob)
        if cb < 0:
            continue
        taken.append((ob, cb))
        ns = ""
        for pos, name in ns_marks:
            if pos < m.start():
                ns = name
        bases = split_args(m.group(7) or "")
        base, base_args = "", None
        if bases:
            b0 = bases[0]
            mm = re.match(r"\s*(?:global::)?([\w.]+)\s*(<[^(]*>)?\s*(\((.*)\))?\s*$", b0, re.S)
            if mm:
                base = mm.group(1).split(".")[-1]
                base_args = mm.group(4)
        classes.append(CsClass(
            name=m.group(4), namespace=ns, full=f"{ns}.{m.group(4)}" if ns else m.group(4),
            attrs=m.group(1) or "", mods=m.group(2) or "", primary=m.group(6), base=base, base_args=base_args,
            base_full=(bases[0].split("(")[0].strip().replace("global::", "") if bases else ""),
            body=src[ob + 1:cb], usings=usings, path=path))
    return classes


def find_member(body, name):
    """멤버 선언 (속성/메서드/식 본문) 의 (시작, 끝) — 없으면 None."""
    for m in re.finditer(r"(?m)^[ \t]*((?:\[[^\]]*\]\s*)*)((?:(?:public|protected|private|internal|override|virtual|"
                         r"sealed|static|async|new|abstract|readonly|unsafe)\s+)+)([\w<>\[\],.?\s]+?\s+)?" + re.escape(name)
                         + r"\b\s*(\(|=>|\{)", body):
        i = m.end() - 1
        tok = m.group(4)
        if tok == "(":
            j = match_bracket(body, i, "(", ")")
            k = j + 1
            rest = body[k:]
            mm = re.match(r"\s*(?::\s*(?:base|this)\s*\()", rest)
            if mm:
                k2 = k + mm.end() - 1
                k = match_bracket(body, k2, "(", ")") + 1
                rest = body[k:]
            mm = re.match(r"\s*(=>|\{|;)", rest)
            if not mm:
                continue
            p = k + mm.end() - 1
            if mm.group(1) == "{":
                e = match_bracket(body, p)
            elif mm.group(1) == "=>":
                e = _expr_end(body, p + 2)
            else:
                e = p
        elif tok == "=>":
            e = _expr_end(body, i + 2)
        else:
            e = match_bracket(body, i)
            mm = re.match(r"\s*=[^;]*;", body[e + 1:])   # 자동 속성 초기값
            if mm:
                e += mm.end()
        return m.start(), e + 1
    return None


def _expr_end(s, i):
    depth = 0
    while i < len(s):
        c = s[i]
        if c == '"':
            j = i + 1
            while j < len(s) and s[j] != '"':
                j += 2 if s[j] == "\\" else 1
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == ";" and depth == 0:
            return i
        i += 1
    return len(s) - 1


def member_text(body, name):
    span = find_member(body, name)
    return body[span[0]:span[1]] if span else ""


def remove_members(body, names):
    for n in names:
        while True:
            span = find_member(body, n)
            if not span:
                break
            body = body[:span[0]] + body[span[1]:]
    return body


def fix_decompiled(code):
    """ILSpy 가 남기는 컴파일러 전용 형식을 보통 C# 로 바꾼다."""
    out = code
    pat = r"new\s+(?:global::)?(?:_003C_003Ez__|<>z__)(\w+)<[^>]*>\("
    while True:
        m = re.search(pat, out)
        if not m:
            break
        o = m.end() - 1
        c = match_bracket(out, o, "(", ")")
        inner = out[o + 1:c].strip()
        mm = re.match(r"new\s+[\w.<>]+\[\d*\]\s*\{(.*)\}\s*$", inner, re.S)
        if mm:
            rep_ = "[" + mm.group(1).strip() + "]"
        elif "SingleElement" in m.group(1):
            rep_ = "[" + inner + "]"
        else:
            rep_ = "[.. " + inner + "]"
        out = out[:m.start()] + rep_ + out[c + 1:]
    return fix_out_ref(out)


def fix_out_ref(code):
    """ILSpy 가 out 매개변수를 'ref T x = ref outParam;' 로 받아 두는 코드는 그대로 컴파일되지 않는다 (CS0269).
    그 앞에서 out 매개변수를 기본값으로 먼저 채운다 (out 은 원래 읽기 전에 반드시 채우므로 동작은 같다)."""
    outs = set(re.findall(r"\bout\s+[\w.<>\[\]?,\s]+?\s+(\w+)\s*[,)]", code))
    if not outs:
        return code

    def rep(m):
        if m.group(4) not in outs:
            return m.group(0)
        return f"{m.group(1)}{m.group(4)} = default!;{m.group(1)}{m.group(2)}"
    return re.sub(r"(\n[ \t]*)(ref\s+([\w.<>\[\]?]+)\s+\w+\s*=\s*ref\s+(\w+)\s*;)", rep, code)


# ---------------------------------------------------------------------------
# 값 읽기
# ---------------------------------------------------------------------------
_NUM = re.compile(r"^-?\d+(?:\.\d+)?[mMfFdD]?$")


def parse_vars(expr):
    """CanonicalVars 식 -> [{type, name, value, expr(템플릿)}]"""
    out = []
    for m in re.finditer(r"new\s+((?:[\w]+\.)*(\w+Var))\s*(<\s*([\w.:]+)\s*>)?\s*\(", expr):
        o = m.end() - 1
        c = match_bracket(expr, o, "(", ")")
        if c < 0:
            continue
        args = split_args(expr[o + 1:c])
        typ = m.group(2)
        gen = (m.group(4) or "").split(".")[-1].replace("global::", "")
        name = None
        if args and re.match(r'^"[^"]*"$', args[0]):
            name = args[0][1:-1]
        elif typ == "PowerVar" and gen:
            name = gen
        else:
            name = DEFAULT_VAR_NAME.get(typ, typ.replace("Var", ""))
        value, vi, suffix = None, None, "m"
        for idx, a in enumerate(args):
            if _NUM.match(a):
                value = float(re.sub(r"[mMfFdD]$", "", a))
                vi = idx
                suffix = a[-1] if a[-1] in "mMfFdD" else ""
                break
        tmpl = None
        if vi is not None:
            args2 = list(args)
            args2[vi] = "{VALUE}"
            tmpl = expr[m.start():o + 1] + ", ".join(args2) + ")"
        else:
            tmpl = expr[m.start():c + 1]
        out.append({"type": typ, "name": name, "value": value, "expr": tmpl, "suffix": suffix,
                    "power": gen if typ == "PowerVar" else ""})
    return out


def parse_upgrades(body):
    ups, cost_delta, add_kw = {}, 0, []
    for m in re.finditer(r'DynamicVars\s*\[\s*"(\w+)"\s*\]\s*\.UpgradeValueBy\(\s*(-?[\d.]+)[mMfF]?\s*\)', body):
        ups[m.group(1)] = ups.get(m.group(1), 0) + float(m.group(2))
    for m in re.finditer(r"DynamicVars\.(\w+)\.UpgradeValueBy\(\s*(-?[\d.]+)[mMfF]?\s*\)", body):
        name = ACCESSOR_VAR.get(m.group(1), m.group(1))
        ups[name] = ups.get(name, 0) + float(m.group(2))
    for m in re.finditer(r"DynamicVars\.Power<(?:[\w.]+\.)?(\w+)>\(\)\.UpgradeValueBy\(\s*(-?[\d.]+)[mMfF]?\s*\)", body):
        ups[m.group(1)] = ups.get(m.group(1), 0) + float(m.group(2))
    for m in re.finditer(r"EnergyCost\.UpgradeBy\(\s*(-?\d+)\s*\)", body):
        cost_delta += int(m.group(1))
    add_kw = re.findall(r"AddKeyword\(\s*CardKeyword\.(\w+)\s*\)", body)
    return ups, cost_delta, add_kw


def _enum(text, enum):
    m = re.search(enum + r"\.(\w+)", text or "")
    return m.group(1) if m else None


def _prop_value(body, name):
    t = member_text(body, name)
    if not t:
        return ""
    m = re.search(r"=>\s*(.*?);\s*$", t, re.S) or re.search(r"return\s+(.*?);", t, re.S)
    return m.group(1).strip() if m else t


def _fmt_num(v):
    if v is None:
        return 0
    return int(v) if float(v).is_integer() else float(v)


# ---------------------------------------------------------------------------
# 모드 읽기
# ---------------------------------------------------------------------------
class ExtMod:
    def __init__(self):
        self.id = self.name = self.author = self.version = ""
        self.kind = ""            # installed / source / pck / dll
        self.root = ""
        self.dll = self.pck_path = ""
        self.pck = None
        self.manifest = {}
        self.classes = {}
        self.loc = {"en": {}, "ko": {}, "zh": {}}
        self.images = {}          # 정규화 이름 -> [경로(res 상대 또는 파일)]
        self.items = {"card": [], "relic": [], "potion": [], "power": []}
        self.pools = {}
        self.characters = []
        self.notes = []
        self.src_dir = ""
        self.cache = ""

    # ---- 요약 ----
    def summary(self):
        c = {k: len(v) for k, v in self.items.items()}
        return f"카드 {c['card']} · 유물 {c['relic']} · 물약 {c['potion']} · 파워 {c['power']}"

    # ---- 그림 ----
    def image_file(self, ref):
        """그림 참조(pck 경로 또는 파일 경로) -> 로컬 PNG 경로 (pck 는 꺼내서 캐시)."""
        if not ref:
            return ""
        if self.pck is None:
            return ref if os.path.isfile(ref) else ""
        # Archive entry names never become local path components.
        import ntpath
        parts = ref.replace("\\", "/").split("/")
        if ntpath.splitdrive(ref)[0] or any(part in ("", ".", "..") or ":" in part for part in parts):
            return ""
        root = os.path.realpath(os.path.join(cache_root(), "imports"))
        folder = os.path.realpath(os.path.join(self.cache, "images"))
        if not folder.startswith(root + os.sep):
            return ""
        ext = os.path.splitext(ref)[1].lower()
        ext = ext if ext in (".png", ".jpg", ".jpeg", ".webp") else ".png"
        out = os.path.join(folder, hashlib.sha256(ref.encode("utf8")).hexdigest() + ext)
        if os.path.realpath(out) != out:
            return ""
        if os.path.isfile(out):
            return out
        try:
            if ref.endswith(".res") and ref in self.pck:
                img = decode_res_image(ingame.rscc_decompress(self.pck.read(ref)))
                if img is None:
                    return ""
                os.makedirs(os.path.dirname(out), exist_ok=True)
                img.save(out)
                return out
            if ref + ".import" in self.pck:
                imp = self.pck.text(ref + ".import")
                mm = re.search(r'path(?:\.bptc|\.s3tc)?="res://([^"]+\.ctex)"', imp)
                img = ingame.decode_ctex(self.pck.read(mm.group(1)))
            elif ref in self.pck:
                from PIL import Image
                import io
                img = Image.open(io.BytesIO(self.pck.read(ref))).convert("RGBA")
            else:
                return ""
            os.makedirs(os.path.dirname(out), exist_ok=True)
            img.save(out)
            return out
        except Exception:  # noqa: BLE001
            return ""


def decode_res_image(d):
    """Godot 바이너리 ImageTexture(.res) 안의 그림 -> PIL (RGBA8/RGB8/PNG/WebP)."""
    import struct
    from PIL import Image
    import io
    for sig in (b"\x89PNG", b"RIFF"):
        i = d.find(sig)
        if i >= 0:
            try:
                return Image.open(io.BytesIO(d[i:])).convert("RGBA")
            except Exception:  # noqa: BLE001
                pass

    def int_after(key):
        i = d.find(key + b"\x00")
        if i < 0:
            return None
        j = i + len(key) + 1
        j = (j + 3) // 4 * 4 if (j % 4) else j
        for jj in (i + len(key) + 1, j):
            t, v = struct.unpack_from("<Ii", d, jj)
            if t in (2, 3):
                return v
        return None
    w, h = int_after(b"width"), int_after(b"height")
    fi = d.find(b"format\x00")
    fmt = ""
    if fi >= 0:
        mm = re.search(rb"(RGBA8|RGB8|LA8|L8)", d[fi:fi + 40])
        fmt = mm.group(1).decode() if mm else ""
    di = d.rfind(b"data\x00")
    if not (w and h and di >= 0):
        return None
    j = di + 5
    for jj in (j, (j + 3) // 4 * 4):
        t, n = struct.unpack_from("<II", d, jj)
        if t == 0x1F and n <= len(d):
            raw = d[jj + 8:jj + 8 + n]
            mode = {"RGBA8": "RGBA", "RGB8": "RGB", "LA8": "LA", "L8": "L"}.get(fmt, "RGBA")
            bpp = {"RGBA": 4, "RGB": 3, "LA": 2, "L": 1}[mode]
            if len(raw) >= w * h * bpp:
                return Image.frombytes(mode, (w, h), raw[:w * h * bpp]).convert("RGBA")
    return None


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def list_installed(sts2_path):
    """게임 mods / mods.disabled 의 모드 목록 [(이름, 경로, 켜짐 여부)]"""
    out = []
    for sub, on in (("mods", True), ("mods.disabled", False)):
        base = os.path.join(sts2_path or "", sub)
        if not os.path.isdir(base):
            continue
        for d in sorted(os.listdir(base)):
            p = os.path.join(base, d)
            if os.path.isdir(p) and glob.glob(os.path.join(p, "*.json")):
                out.append((d, p, on))
            elif d.lower().endswith(".pck"):
                out.append((d, p, on))
    return out


def load_mod(path, sts2_path="", log=print):
    em = ExtMod()
    path = os.path.abspath(path)
    em.root = path
    sources = []      # (텍스트, 경로)
    # ---- 무엇을 받았는지 ----
    if os.path.isdir(path):
        jsons = [j for j in glob.glob(os.path.join(path, "*.json")) if _is_manifest(j)]
        csproj = glob.glob(os.path.join(path, "*.csproj"))
        if jsons:
            em.manifest = _read_json(jsons[0])
        mid = em.manifest.get("id") or (os.path.splitext(os.path.basename(csproj[0]))[0] if csproj else os.path.basename(path))
        dll = os.path.join(path, f"{mid}.dll")
        pck = os.path.join(path, f"{mid}.pck")
        if csproj or glob.glob(os.path.join(path, "**", "*.cs"), recursive=True):
            em.kind = "source"
            em.src_dir = path
            for f in glob.glob(os.path.join(path, "**", "*.cs"), recursive=True):
                if re.search(r"[\\/](bin|obj|\.godot)[\\/]", f):
                    continue
                sources.append((_read_text(f), f))
            builds = glob.glob(os.path.join(path, ".godot", "mono", "temp", "bin", "*", f"{mid}.dll")) + \
                glob.glob(os.path.join(path, "bin", "**", f"{mid}.dll"), recursive=True)
            if os.path.isfile(dll):
                em.dll = dll
            elif builds:
                em.dll = builds[0]
            elif sts2_path:
                for sub in ("mods", "mods.disabled"):
                    p = os.path.join(sts2_path, sub, mid, f"{mid}.dll")
                    if os.path.isfile(p):
                        em.dll = p
                        break
        else:
            em.kind = "installed"
            if os.path.isfile(dll):
                em.dll = dll
            else:
                dlls = glob.glob(os.path.join(path, "*.dll"))
                em.dll = dlls[0] if dlls else ""
        if os.path.isfile(pck):
            em.pck_path = pck
        else:
            pcks = glob.glob(os.path.join(path, "*.pck"))
            em.pck_path = pcks[0] if pcks else ""
        em.id = mid
    elif path.lower().endswith(".pck"):
        em.kind = "pck"
        em.pck_path = path
        em.id = os.path.splitext(os.path.basename(path))[0]
    elif path.lower().endswith(".dll"):
        em.kind = "dll"
        em.dll = path
        em.id = os.path.splitext(os.path.basename(path))[0]
        man = os.path.splitext(path)[0] + ".json"
        if os.path.isfile(man):
            em.manifest = _read_json(man)
        p2 = os.path.splitext(path)[0] + ".pck"
        if os.path.isfile(p2):
            em.pck_path = p2
    elif path.lower().endswith(".json"):
        return load_mod(os.path.dirname(path), sts2_path, log)
    else:
        raise ValueError("모드 폴더, .dll, .pck, .json 중 하나를 고르세요.")

    cache_key = hashlib.sha256((em.id or "mod").encode("utf8")).hexdigest()
    em.cache = os.path.join(cache_root(), "imports", cache_key)
    if em.pck_path:
        em.pck = ingame.Pck(em.pck_path)
        names = list(em.pck.files)
        if not em.manifest:
            mf = [n for n in names if "/" not in n and n.endswith(".json")]
            for n in mf:
                try:
                    d = json.loads(em.pck.read(n))
                    if "id" in d:
                        em.manifest = d
                        break
                except ValueError:
                    pass
        if not sources:
            for n in names:
                if n.endswith(".cs") and em.pck.files[n][1] > 16:
                    sources.append((em.pck.text(n), "pck:" + n))
            stubs = [n for n in names if n.endswith(".cs") and em.pck.files[n][1] <= 16]
            if stubs and not sources:
                em.stub_paths = stubs
    if not sources and em.dll:
        try:
            out = decompile(em.dll, sts2_path, log=log)
            em.src_dir = out
            for f in glob.glob(os.path.join(out, "**", "*.cs"), recursive=True):
                sources.append((_read_text(f), f))
        except Exception as e:  # noqa: BLE001
            em.notes.append(f"dll 을 읽지 못해 수치·동작 없이 텍스트와 그림만 불러옵니다: {e}")
    m = em.manifest
    em.id = m.get("id") or em.id
    em.name = m.get("name") or em.id
    em.author = m.get("author", "")
    em.version = m.get("version", "")

    _load_loc(em)
    _index_images(em)
    for text, p in sources:
        for c in parse_cs(text, p):
            em.classes.setdefault(c.name, c)
    _extract_items(em)
    if not any(em.items.values()):
        _items_from_loc(em)
        if any(em.items.values()):
            em.notes.append("코드가 없어 종류·비용·동작은 알 수 없습니다 (텍스트와 그림만 불러왔습니다).")
    return em


def _is_manifest(p):
    d = _read_json(p)
    return isinstance(d, dict) and "id" in d and ("has_dll" in d or "has_pck" in d or "dependencies" in d)


def _read_json(p):
    try:
        with open(p, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _read_text(p):
    try:
        with open(p, encoding="utf-8-sig", errors="replace") as f:
            return f.read()
    except OSError:
        return ""


def _load_loc(em):
    def add(lang, fname, data):
        if isinstance(data, dict):
            em.loc[lang].setdefault(fname, {}).update(data)
    pat = re.compile(r"localization/(eng|kor|zhs)/(\w+)\.json$")
    code = {"eng": "en", "kor": "ko", "zhs": "zh"}
    if em.pck is not None:
        for n in em.pck.files:
            mm = pat.search(n)
            if mm:
                try:
                    add(code[mm.group(1)], mm.group(2), json.loads(em.pck.read(n).decode("utf-8-sig")))
                except ValueError:
                    pass
    if em.kind == "source":
        for f in glob.glob(os.path.join(em.root, "**", "localization", "*", "*.json"), recursive=True):
            mm = pat.search(f.replace("\\", "/"))
            if mm and not re.search(r"[\\/](bin|obj|\.godot)[\\/]", f):
                add(code[mm.group(1)], mm.group(2), _read_json(f))


def _index_images(em):
    def add(key_path, ref):
        stem = os.path.splitext(os.path.basename(key_path))[0]
        em.images.setdefault(_norm(stem), []).append(ref)
    if em.pck is not None:
        for n in em.pck.files:
            if n.endswith(".png.import"):
                add(n[:-7], n[:-7])
            elif n.endswith(".png") and not n.startswith(".godot"):
                add(n, n)
    if em.kind == "source":
        for f in glob.glob(os.path.join(em.root, "**", "*.png"), recursive=True):
            if not re.search(r"[\\/](bin|obj|\.godot)[\\/]", f):
                add(f, f)


PATH_PROPS = {"card": ["PortraitPath", "CustomPortraitPath"], "relic": ["BigIconPath", "PackedIconPath"],
              "potion": ["CustomPackedImagePath"], "power": ["CustomBigIconPath", "CustomPackedIconPath"]}


def _consts(em):
    if getattr(em, "_const_cache", None) is None:
        tab = {}
        for c in em.classes.values():
            for m in re.finditer(r"const\s+string\s+(\w+)\s*=\s*([^;]+);", c.body):
                tab[m.group(1)] = m.group(2)
                tab[c.name + "." + m.group(1)] = m.group(2)
            for m in re.finditer(r"static\s+(?:readonly\s+)?string\s+(\w+)\s*(?:=>|=)\s*([^;]+);", c.body):
                tab.setdefault(m.group(1), m.group(2))
                tab.setdefault(c.name + "." + m.group(1), m.group(2))
        exts = {}
        for c in em.classes.values():
            for m in re.finditer(r"static\s+string\s+(\w+)\s*\(\s*this\s+string\s+(\w+)[^)]*\)", c.body):
                rest = c.body[m.end():]
                mm = re.match(r"\s*=>\s*([^;]+);", rest)
                if mm:
                    exts[m.group(1)] = (m.group(2), mm.group(1))
                    continue
                o = rest.find("{")
                if o >= 0:
                    blk = rest[o:match_bracket(rest, o) + 1]
                    r = re.findall(r"return\s+([^;]+);", blk)
                    if r:
                        exts[m.group(1)] = (m.group(2), r[-1])
        em._const_cache = (tab, exts)
    return em._const_cache


def eval_path(em, expr, cls, entry, env=None, depth=0):
    """그림 경로를 만드는 간단한 식을 계산 (문자열 + GetType().Name + Id.Entry + 상수 + 확장 메서드)."""
    if depth > 6 or not expr:
        return None
    env = env or {}
    tab, exts = _consts(em)
    e = expr.strip().rstrip(";").strip()
    if e.startswith("=>"):
        e = e[2:].strip()
    while e.startswith("(") and match_bracket(e, 0, "(", ")") == len(e) - 1:
        e = e[1:-1].strip()
    parts = _split_plus(e)
    if len(parts) > 1:
        vals = [eval_path(em, p_, cls, entry, env, depth + 1) for p_ in parts]
        return None if any(v is None for v in vals) else "".join(vals)
    m = re.match(r'^@?"((?:[^"\\]|\\.)*)"$', e)
    if m:
        return m.group(1).replace("\\\\", "\\")
    m = re.match(r'^\$"((?:[^"\\]|\\.)*)"$', e)
    if m:
        out, txt, i = [], m.group(1), 0
        while i < len(txt):
            if txt[i] == "{":
                j = match_bracket(txt, i)
                v = eval_path(em, txt[i + 1:j].split(":")[0], cls, entry, env, depth + 1)
                if v is None:
                    return None
                out.append(v)
                i = j + 1
            else:
                out.append(txt[i])
                i += 1
        return "".join(out)
    if e in env:
        return env[e]
    if e in ("GetType().Name", "base.GetType().Name", f"nameof({cls})", "Name"):
        return cls
    mm = re.match(r"^(.*)\.(ToLowerInvariant|ToLower|ToUpperInvariant|ToUpper)\(\)$", e, re.S)
    if mm:
        v = eval_path(em, mm.group(1), cls, entry, env, depth + 1)
        return None if v is None else (v.lower() if "Lower" in mm.group(2) else v.upper())
    mm = re.match(r"^(.*)\.RemovePrefix\(\)$", e, re.S)
    if mm:
        v = eval_path(em, mm.group(1), cls, entry, env, depth + 1)
        return None if v is None else v.split("-", 1)[-1]
    if e in ("Id.Entry", "base.Id.Entry", "this.Id.Entry"):
        return entry
    mm = re.match(r"^(?:System\.IO\.)?Path\.(?:Join|Combine)\((.*)\)$", e, re.S)
    if mm:
        vals = [eval_path(em, a, cls, entry, env, depth + 1) for a in split_args(mm.group(1))]
        return None if any(v is None for v in vals) else "/".join(v.strip("/") if i else v.rstrip("/") for i, v in enumerate(vals))
    mm = re.match(r"^(.*)\.(\w+)\(\)$", e, re.S)
    if mm and mm.group(2) in exts:
        pname, body = exts[mm.group(2)]
        v = eval_path(em, mm.group(1), cls, entry, env, depth + 1)
        if v is None:
            return None
        return eval_path(em, body, cls, entry, dict(env, **{pname: v}), depth + 1)
    key = e.replace("global::", "")
    for k in (key, key.split(".")[-1], ".".join(key.split(".")[-2:])):
        if k in tab:
            return eval_path(em, tab[k], cls, entry, env, depth + 1)
    return None


def _split_plus(e):
    out, depth, cur, i = [], 0, [], 0
    while i < len(e):
        c = e[i]
        if c == '"':
            j = i + 1
            while j < len(e) and e[j] != '"':
                j += 2 if e[j] == "\\" else 1
            cur.append(e[i:j + 1])
            i = j + 1
            continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        if c == "+" and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    out.append("".join(cur))
    return [x.strip() for x in out if x.strip()]


def _resolve_ref(em, res):
    """계산된 res 경로 -> 모드 안 그림 참조 (pck 경로 또는 파일)."""
    if not res:
        return ""
    rel = res.replace("res://", "")
    if em.pck is not None:
        for cand in (rel, rel.replace(".png.res", ".png")):
            if cand.endswith(".res") and cand in em.pck:
                return cand
            if cand + ".import" in em.pck or cand in em.pck:
                return cand
    if em.kind == "source":
        f = os.path.join(em.root, rel.replace("/", os.sep))
        if os.path.isfile(f):
            return f
    return ""


def _find_image(em, kind, cls, item_id, c=None, entry=""):
    if c is not None:
        for prop in PATH_PROPS[kind]:
            t, _owner = _inherited_member(em, c, prop)
            if not t:
                continue
            mm = re.search(r"=>\s*(.*?);\s*$", t, re.S) or re.search(r"return\s+(.*?);", t, re.S)
            if not mm:
                continue
            ref = _resolve_ref(em, eval_path(em, mm.group(1), cls, entry))
            if ref:
                return ref
    return _find_image_by_name(em, kind, cls, item_id)


def _find_image_by_name(em, kind, cls, item_id):
    keys = [_norm(cls), _norm(item_id), _norm(game_snake(cls))]
    if kind == "power":
        keys += [_norm(cls[:-5]) if cls.endswith("Power") else ""]
    want = {"card": ("card",), "relic": ("relic",), "potion": ("potion",), "power": ("power", "buff", "debuff")}[kind]
    cands = []
    for k in keys:
        cands += em.images.get(k, [])
    if not cands:
        return ""

    def score(ref):
        low = ref.lower().replace("\\", "/")
        s = 0
        if any(w in low for w in want):
            s += 10
        if "outline" in low:
            s -= 20
        if "/big/" in low or "_big" in low:
            s += 2
        if "beta" in low:
            s -= 5
        return s
    return max(cands, key=score)


def _category(em, c, seen=None):
    seen = seen or set()
    for k, roots in ROOTS.items():
        if c.base in roots:
            return k
    if c.base in em.classes and c.base not in seen:
        seen.add(c.base)
        return _category(em, em.classes[c.base], seen)
    return None


def _inherited_attr(em, c, pattern):
    cur, guard = c, 0
    while cur and guard < 10:
        m = re.search(pattern, cur.attrs)
        if m:
            return m.group(1)
        cur = em.classes.get(cur.base)
        guard += 1
    return ""


def _inherited_member(em, c, name):
    cur, guard = c, 0
    while cur and guard < 10:
        t = member_text(cur.body, name)
        if t:
            return t, cur
        cur = em.classes.get(cur.base)
        guard += 1
    return "", None


def _loc_lookup(em, kind, cls):
    fname = LOC_FILE[kind]
    prefix = None
    keys = {}
    for lang in ("ko", "en", "zh"):
        for k in em.loc[lang].get(fname, {}):
            ident = k.rsplit(".", 1)[0]
            keys.setdefault(ident, set()).add(lang)
    want = game_snake(cls)
    for ident in keys:
        if "-" in ident and ident.split("-", 1)[1] == want:
            prefix = ident
            break
    if prefix is None:
        nc = _norm(cls)
        for ident in keys:
            if _norm(ident.split("-", 1)[-1]) == nc:
                prefix = ident
                break
    if prefix is None:
        return None, {}
    texts = {}
    for lang in ("ko", "en", "zh"):
        d = em.loc[lang].get(fname, {})
        texts[lang] = {k[len(prefix) + 1:]: v for k, v in d.items() if k.startswith(prefix + ".")}
    return prefix, texts


def _base_item(em, kind, c):
    iid = class_to_id(c.name if kind != "power" else (c.name[:-5] if c.name.endswith("Power") and len(c.name) > 5 else c.name))
    locid, texts = _loc_lookup(em, kind, c.name)
    ko, en, zh = texts.get("ko", {}), texts.get("en", {}), texts.get("zh", {})
    item = {"id": iid, "class": c.name, "full": c.full, "loc_id": locid or "",
            "name_ko": ko.get("title", "") or en.get("title", "") or c.name,
            "name_en": en.get("title", "") or ko.get("title", "") or c.name,
            "name_zh": zh.get("title", ""),
            "desc_ko": ko.get("smartDescription", ko.get("description", "")),
            "desc_en": en.get("smartDescription", en.get("description", "")),
            "desc_zh": zh.get("smartDescription", zh.get("description", "")),
            "effects": [], "extra_code": "", "_texts": texts, "_ext": em.id,
            "image_ref": _find_image(em, kind, c.name, iid, c, locid or ""), "image": ""}
    return item


def _extract_items(em):
    for c in em.classes.values():
        kind = _category(em, c)
        if kind in ("card_pool",):
            em.pools[c.name] = {
                "full": c.full,
                "h": _num_or(_prop_value(c.body, "H"), 1.0), "s": _num_or(_prop_value(c.body, "S"), 1.0),
                "v": _num_or(_prop_value(c.body, "V"), 1.0),
                "energy_big": _str_lit(_prop_value(c.body, "BigEnergyIconPath")),
                "energy_small": _str_lit(_prop_value(c.body, "TextEnergyIconPath")),
                "colorless": "true" in _prop_value(c.body, "IsColorless"),
            }
            continue
        if kind == "character":
            if "abstract" not in c.mods:
                hp = re.search(r"(\d+)", _prop_value(c.body, "StartingHp") or "")
                pool_text, _pool_owner = _inherited_member(em, c, "CardPool")
                pool = re.search(r"CardPool<(?:[\w.]+\.)?(\w+)>|CardPool<(?:global::)?(?:[\w.]+\.)?(\w+)>\s*\(", pool_text)
                pool_class = next((name for name in pool.groups() if name), "") if pool else ""
                em.characters.append({"class": c.name, "full": c.full, "hp": int(hp.group(1)) if hp else 0,
                                      "pool": pool_class,
                                      "pool_full": em.classes[pool_class].full if pool_class in em.classes else ""})
            continue
        if kind not in ("card", "relic", "potion", "power") or "abstract" in c.mods or "static" in c.mods:
            continue
        item = _base_item(em, kind, c)
        vars_text, _owner = _inherited_member(em, c, "CanonicalVars")
        rv = parse_vars(fix_decompiled(vars_text))
        up_body = member_text(c.body, "OnUpgrade")
        ups, cost_delta, add_kw = parse_upgrades(up_body)
        for v in rv:
            v["upgrade"] = ups.get(v["name"], 0)
            v["value"] = _fmt_num(v["value"])
            v["upgrade"] = _fmt_num(v["upgrade"])
        item["raw_vars"] = rv
        pool = _inherited_attr(em, c, r"Pool\s*\(\s*typeof\s*\(\s*(?:global::)?(?:[\w.]+\.)?(\w+)\s*\)")
        item["pool_class"] = pool
        if kind == "card":
            args = None
            if c.base_args is not None:
                args = split_args(c.base_args)
            else:
                ctor = find_member(c.body, c.name)
                if ctor:
                    t = c.body[ctor[0]:ctor[1]]
                    mm = re.search(r":\s*base\s*\(", t)
                    if mm:
                        o = mm.end() - 1
                        args = split_args(t[o + 1:match_bracket(t, o, "(", ")")])
            cost = None
            if args:
                mm = re.match(r"^-?\d+$", args[0].strip())
                cost = int(args[0]) if mm else None
            joined = ", ".join(args or [])
            kws = re.findall(r"CardKeyword\.(\w+)", _inherited_member(em, c, "CanonicalKeywords")[0])
            tags = re.findall(r"CardTag\.(\w+)", _inherited_member(em, c, "CanonicalTags")[0])
            item.update({
                "type": _enum(joined, "CardType") or "Skill", "rarity": _enum(joined, "CardRarity") or "Common",
                "target": _enum(joined, "TargetType") or "Self",
                "cost": cost if cost is not None else 0, "upgrade_cost": (cost or 0) + cost_delta,
                "cost_unknown": cost is None,
                "keywords": [k for k in kws if k in dict(M.CARD_KEYWORDS)],
                "upgrade_add_keyword": next((k for k in add_kw if k in dict(M.CARD_KEYWORDS)), ""),
                "tag": next((t for t in tags if t in ("Strike", "Defend")), ""),
            })
            if item["type"] not in dict(M.CARD_TYPES):
                item["type"] = "Skill"
            if item["rarity"] not in dict(M.CARD_RARITIES):
                item["rarity_orig"] = item["rarity"]
                item["rarity"] = "Rare" if item["rarity"] == "Ancient" else "Common"
            if item["target"] not in dict(M.CARD_TARGETS):
                item["target_orig"] = item["target"]
                item["target"] = "AnyEnemy" if "Enemy" in item["target"] else "Self"
        elif kind == "relic":
            r = _enum(_inherited_member(em, c, "Rarity")[0], "RelicRarity") or "Common"
            item.update({"rarity": r if r in dict(M.RELIC_RARITIES) else "Common", "trigger": "turn_start",
                         "played_filter": "Any", "played_every": 1, "enemy_mode": "all",
                         "flavor_ko": item["_texts"].get("ko", {}).get("flavor", ""),
                         "flavor_en": item["_texts"].get("en", {}).get("flavor", ""),
                         "flavor_zh": item["_texts"].get("zh", {}).get("flavor", "")})
        elif kind == "potion":
            r = _enum(_inherited_member(em, c, "Rarity")[0], "PotionRarity") or "Common"
            t = _enum(_inherited_member(em, c, "TargetType")[0], "TargetType") or "Self"
            item.update({"rarity": r if r in dict(M.POTION_RARITIES) else "Common",
                         "target": t if t in dict(M.POTION_TARGETS) else "Self"})
        elif kind == "power":
            item.update({"type": _enum(_inherited_member(em, c, "Type")[0], "PowerType") or "Buff",
                         "stack": _enum(_inherited_member(em, c, "StackType")[0], "PowerStackType") or "Counter",
                         "trigger": "none", "played_filter": "Any", "played_by": "owner", "enemy_mode": "all",
                         "decay": "none", "modifiers": []})
            if item["type"] not in ("Buff", "Debuff"):
                item["type"] = "Buff"
            if item["stack"] not in ("Counter", "Single"):
                item["stack"] = "Counter"
        item["_kind"] = kind
        item["_cls"] = c
        em.items[kind].append(item)
    for k in em.items:
        em.items[k].sort(key=lambda it: it["class"])


def _items_from_loc(em):
    """코드가 없을 때: 현지화 키만으로 항목을 만든다."""
    for kind in ("card", "relic", "potion", "power"):
        fname = LOC_FILE[kind]
        idents = set()
        for lang in ("ko", "en", "zh"):
            idents |= {k.rsplit(".", 1)[0] for k in em.loc[lang].get(fname, {}) if k.endswith(".title")}
        for ident in sorted(idents):
            raw = ident.split("-", 1)[-1]
            cls = "".join(p[:1] + p[1:].lower() for p in raw.split("_"))
            texts = {lang: {k[len(ident) + 1:]: v for k, v in em.loc[lang].get(fname, {}).items()
                            if k.startswith(ident + ".")} for lang in ("ko", "en", "zh")}
            ko, en, zh = texts["ko"], texts["en"], texts["zh"]
            iid = raw.lower()
            if kind == "power" and iid.endswith("_power"):
                iid = iid[:-6]
            item = {"id": iid, "class": cls, "full": cls, "loc_id": ident, "_texts": texts, "_ext": em.id,
                    "name_ko": ko.get("title", "") or en.get("title", ""), "name_en": en.get("title", "") or ko.get("title", ""),
                    "name_zh": zh.get("title", ""),
                    "desc_ko": ko.get("smartDescription", ko.get("description", "")),
                    "desc_en": en.get("smartDescription", en.get("description", "")),
                    "desc_zh": zh.get("smartDescription", zh.get("description", "")),
                    "effects": [], "extra_code": "", "raw_vars": [], "_kind": kind, "_cls": None,
                    "image_ref": _find_image_by_name(em, kind, cls, iid), "image": ""}
            base = {"card": M.new_card, "relic": M.new_relic, "potion": M.new_potion, "power": M.new_power}[kind](iid)
            base.update(item)
            base["effects"] = []
            if kind == "card":
                base["cost_unknown"] = True
            em.items[kind].append(base)


def _num_or(s, d):
    m = re.search(r"-?\d+(?:\.\d+)?", s or "")
    return float(m.group(0)) if m else d


def _str_lit(s):
    m = re.search(r'"([^"]*)"', s or "")
    return m.group(1) if m else ""


# ---------------------------------------------------------------------------
# 미리보기용 데이터
# ---------------------------------------------------------------------------
def preview_item(em, item):
    """미리보기(ingame/preview)에 넘길 항목 사본: 그림 경로·카드 틀 색·에너지 아이콘을 채운다."""
    it = {k: v for k, v in item.items() if not k.startswith("_")}
    it["raw_desc_only"] = True
    it["image"] = em.image_file(item.get("image_ref", ""))
    pool = em.pools.get(item.get("pool_class", ""))
    if pool:
        it["_hsv"] = (pool["h"], pool["s"], pool["v"]) if not pool["colorless"] else None
        for key in ("energy_big", "energy_small"):
            ref = pool.get(key, "")
            it["_" + key] = em.image_file(ref.replace("res://", "")) if ref else ""
    it["_colorless"] = bool(pool and pool["colorless"]) or not pool
    return it


# ---------------------------------------------------------------------------
# 복제 / 참조
# ---------------------------------------------------------------------------
REGENERATED = {
    "card": ["CanonicalVars", "CanonicalKeywords", "CanonicalTags", "PortraitPath", "CustomPortraitPath",
             "BetaPortraitPath", "OnUpgrade"],
    "relic": ["CanonicalVars", "Rarity", "PackedIconPath", "PackedIconOutlinePath", "BigIconPath"],
    "potion": ["CanonicalVars", "Rarity", "TargetType", "CustomPackedImagePath", "CustomPackedOutlinePath"],
    "power": ["CanonicalVars", "Type", "StackType", "CustomPackedIconPath", "CustomBigIconPath"],
}


def clone_item(em, item, project, target_pool="mine"):
    """외부 항목 -> 내 프로젝트 항목 (원본 클래스를 상속해 원래 동작 유지). 그림은 로컬 파일로 꺼낸다."""
    kind = item["_kind"]
    c = item.get("_cls")
    new = {"card": M.new_card, "relic": M.new_relic, "potion": M.new_potion, "power": M.new_power}[kind](item["id"])
    for k, v in item.items():
        if not k.startswith("_") and k not in ("class", "full", "loc_id", "image_ref", "pool_class", "cost_unknown"):
            new[k] = v
    new["effects"] = []
    new["raw_desc_only"] = True
    new["image"] = em.image_file(item.get("image_ref", ""))
    # 원본 텍스트의 추가 키(선택 화면 문구 등)도 새 ID 로 옮긴다
    extra = {}
    for lang in ("ko", "en", "zh"):
        for k, v in item.get("_texts", {}).get(lang, {}).items():
            if k not in ("title", "description", "smartDescription", "flavor"):
                extra.setdefault(lang, {})[k] = v
    new["extra_loc"] = extra
    if kind == "power":
        new["desc_ko"] = item["_texts"].get("ko", {}).get("smartDescription", item.get("desc_ko", ""))
        new["desc_en"] = item["_texts"].get("en", {}).get("smartDescription", item.get("desc_en", ""))
        new["static_desc_ko"] = item["_texts"].get("ko", {}).get("description", "")
        new["static_desc_en"] = item["_texts"].get("en", {}).get("description", "")
        new["desc_zh"] = item["_texts"].get("zh", {}).get("smartDescription", item.get("desc_zh", ""))
        new["static_desc_zh"] = item["_texts"].get("zh", {}).get("description", "")
    if c is None:
        new["raw_vars"] = []
        return new
    base_cls = em.classes.get(c.base)
    abstract_base = base_cls is not None and "abstract" in base_cls.mods
    body = fix_decompiled(c.body)
    upgrade_body = member_text(body, "OnUpgrade") if kind == "card" else ""
    ctor_args = []
    if kind == "card":
        if c.base_args is not None:
            ctor_args = split_args(c.base_args)
        else:
            ctor = find_member(body, c.name)
            if ctor:
                t = body[ctor[0]:ctor[1]]
                mm = re.search(r":\s*base\s*\(", t)
                if mm:
                    o = mm.end() - 1
                    ctor_args = split_args(t[o + 1:match_bracket(t, o, "(", ")")])
    body = remove_members(body, REGENERATED[kind] + [c.name])
    pool_full = ""
    if item.get("pool_class") and item["pool_class"] in em.classes:
        pool_full = em.classes[item["pool_class"]].full
    new["clone"] = {
        "mod": em.id, "orig_class": c.full, "orig_loc_id": item.get("loc_id", ""),
        "base": base_cls.full if abstract_base else "",       # 비어 있으면 내 기본 클래스를 상속
        "namespace": c.namespace, "ctor_args": ctor_args, "upgrade_body": upgrade_body,
        "usings": [u for u in c.usings if not u.startswith("using static") or True],
        "body": body.strip("\n"), "pool": target_pool, "their_pool": pool_full,
    }
    if kind == "card":
        M.expose_clone_play(new)
        if new["effects"] and new["effects"][0].get("original_effect"):
            # 원본 OnPlay 를 블록 하나하나로 풀어 둔다 (도우미 메서드·부모 클래스까지 펼침). 실패하면 '원본 실행' 블록 하나.
            import csblocks
            try:
                expanded, _info = csblocks.decompose_with_classes(new, em.classes, project)
            except Exception as exc:   # 풀기 실패는 가져오기를 막지 않는다
                expanded = None
                log_fn = getattr(em, "log", None)
                if callable(log_fn):
                    log_fn(f"원본 코드 블록 풀기 실패 ({item.get('id')}): {exc}")
            if expanded:
                new["effects"][0]["blocks"] = expanded
                new["effects"][0]["decomposed"] = True
                csblocks.merge_usings(new, _info.get("usings"))
    return new


def external_keywords(em):
    """Match localized entries to public CardKeyword fields only when unambiguous."""
    fields = {}
    for c in em.classes.values():
        for name in re.findall(r"\bpublic\s+static\s+(?:readonly\s+)?(?:[\w.]+\.)?CardKeyword\s+(\w+)\s*[;=]", c.body):
            fields.setdefault(re.sub(r"[^a-z0-9]", "", name.lower()), []).append(c.full + "." + name)
    rows = []
    for table in ("card_keywords", "static_hover_tips"):
        keys = sorted({k[:-6] for tables in em.loc.values() for k in tables.get(table, {}) if k.endswith(".title")})
        for key in keys:
            row = {"source_keyword": [em.id, table, key]}
            for lang in ("ko", "en", "zh"):
                values = em.loc.get(lang, {}).get(table, {})
                row["name_" + lang] = values.get(key + ".title", "")
                row["desc_" + lang] = values.get(key + ".description", "")
            local = re.sub(r"[^a-z0-9]", "", key.split("-")[-1].lower())
            candidates = fields.get(local, [])
            if table == "card_keywords" and len(candidates) == 1 and em.dll:
                row["keyword_member"] = candidates[0]
            rows.append(row)
    return rows


# ---------------------------------------------------------------------------
# 모드를 통째로 내 프로젝트로 (원래 코드·리소스는 그대로 두고, 카드·유물·물약·파워를 편집 가능하게)
# ---------------------------------------------------------------------------
TAKEOVER_ORIG_NS = "Orig"       # 원본 코드가 {id}.{id}Code 를 쓰면 {id}.{id}Orig 로 옮겨 생성 코드와 겹치지 않게


def _top_level_types(text):
    """파일 안의 최상위 형식 이름들 (class/record/struct/interface/enum/delegate)."""
    src = strip_comments(text)
    src = re.sub(r'@?"(?:[^"\\\n]|\\.)*"', '""', src)          # 문자열 안의 { } 는 세지 않는다
    block_ns = re.search(r"\bnamespace\s+[\w.]+\s*\{", src)
    top = 1 if block_ns else 0
    names, depth = [], 0
    for m in re.finditer(r"[{}]|\b(class|record|struct|interface|enum|delegate)\s+(?:\w+\s+)?(\w+)", src):
        tok = m.group(0)
        if tok == "{":
            depth += 1
        elif tok == "}":
            depth -= 1
        elif depth == top:
            names.append(m.group(2))
    return names


def _dep_entries(em, sts2_path):
    """원본 매니페스트의 필수 모드 (BaseLib 제외) → 참조 항목."""
    out = []
    for d in em.manifest.get("dependencies") or []:
        did = d.get("id") if isinstance(d, dict) else str(d)
        if not did or did.lower() == "baselib" or did == em.id:
            continue
        dll = ""
        for sub in ("mods", "mods.disabled"):
            for cand in (os.path.join(sts2_path or "", sub, did, f"{did}.dll"),):
                if os.path.isfile(cand):
                    dll = cand
        out.append({"id": did, "name": did, "version": (d.get("min_version") if isinstance(d, dict) else "") or "",
                    "dll": dll, "powers": []})
    return out


CHAR_IMAGE_PROPS = {     # 내 그림 칸 -> 원래 클래스에서 바꿀 속성
    "select_image": ["CustomCharacterSelectIconPath"],
    "select_locked_image": ["CustomCharacterSelectLockedIconPath"],
    "icon_image": ["CustomIconTexturePath", "CustomIconOutlineTexturePath", "CustomIcon", "CustomIconPath"],
    "map_marker_image": ["CustomMapMarkerPath"],
    "select_bg_image": ["CustomCharacterSelectBg"],
    "combat_image": ["CreateCustomVisuals"],
}
CHAR_REGEN = ["StartingHp", "StartingGold", "StartingDeck", "StartingRelics"]


def _model_list(text, kind):
    """'ModelDb.Card<X>()' 들 → [(형식 이름, 개수)] (순서 유지). 목록 식이 아니면 None."""
    found = re.findall(r"ModelDb\s*\.\s*" + kind + r"\s*<\s*(?:global::)?([\w.]+)\s*>\s*\(\s*\)", text)
    if not found:
        return None
    if re.search(r"\b(for|foreach|while|if|switch|Enumerable\.Repeat|Concat|Select)\b", text):
        return None        # 반복·조건으로 만드는 목록은 그대로 둔다
    out = []
    for name in found:
        if out and out[-1][0] == name:
            out[-1] = (name, out[-1][1] + 1)
        else:
            out.append((name, 1))
    return out


def import_character(em, c, project, lid):
    """원래 캐릭터 클래스 → 편집할 수 있는 캐릭터 항목. 고친 값만 다시 만들고 나머지는 원래 코드 그대로."""
    body = c.body
    pool_text, _pool_owner = _inherited_member(em, c, "CardPool")
    pool_match = re.search(r"CardPool<(?:[\w.]+\.)?(\w+)>|CardPool<(?:global::)?(?:[\w.]+\.)?(\w+)>\s*\(", pool_text)
    pool_class = next((name for name in pool_match.groups() if name), "") if pool_match else ""
    pool_info = em.classes.get(pool_class)
    by_class = {}
    for kind, key in (("card", "cards"), ("relic", "relics")):
        for it in project[key]:
            cl = it.get("clone") or {}
            if cl.get("keep_name"):
                by_class[(kind, cl["class_name"])] = it["id"]
                if cl.get("namespace"):
                    by_class[(kind, cl["namespace"] + "." + cl["class_name"])] = it["id"]

    def ref(kind, name):
        if (kind, name) in by_class:
            return by_class[(kind, name)]
        short = name.split(".")[-1]
        if (kind, short) in by_class:
            return by_class[(kind, short)]
        # 이 모드의 다른 클래스는 전체 이름, 게임·다른 모드의 것은 원래 코드에 쓰인 그대로 (원래 using 으로 찾음)
        return "raw:" + ("global::" + em.classes[short].full if short in em.classes else name)
    hp_m = re.search(r"(\d+)", _prop_value(body, "StartingHp") or "")
    gold_m = re.search(r"(\d+)", _prop_value(body, "StartingGold") or "")
    deck_l = _model_list(member_text(body, "StartingDeck"), "Card")
    relic_l = _model_list(member_text(body, "StartingRelics"), "Relic")
    texts = {lg: em.loc[lg].get("characters", {}) for lg in ("ko", "en", "zh")}
    bases = ""
    try:
        src = strip_comments(_read_text(c.path))
        mm = re.search(r"\bclass\s+" + re.escape(c.name) + r"\b\s*(?:<[^>{]*>)?\s*(?::\s*([^{]+?))?\s*(?:where\s[^{]*)?\{", src)
        bases = re.sub(r"\s+", " ", mm.group(1)).strip() if mm and mm.group(1) else ""
    except (OSError, TypeError):
        pass
    ich = {
        "class": c.name, "namespace": c.namespace, "loc_id": lid, "base": c.base_full or c.base, "bases": bases,
        "card_pool_class": pool_class, "card_pool_full": pool_info.full if pool_info else "",
        "mods": c.mods, "attrs": c.attrs.strip(), "usings": c.usings, "body": body.strip("\n"),
        "hp": int(hp_m.group(1)) if hp_m else 0, "gold": int(gold_m.group(1)) if gold_m else "",
        "deck": [{"card": ref("card", n), "count": k} for n, k in (deck_l or [])],
        "relics": [ref("relic", n) for n, _k in (relic_l or [])],
        "deck_fixed": deck_l is None and bool(find_member(body, "StartingDeck")),
        "relics_fixed": relic_l is None and bool(find_member(body, "StartingRelics")),
        "architect_ko": "", "architect_en": "", "architect_zh": "",
    }
    for lg in ("ko", "en", "zh"):
        ich[f"name_{lg}"] = texts[lg].get(f"{lid}.title", "")
        ich[f"desc_{lg}"] = texts[lg].get(f"{lid}.description", "")
    ich["orig"] = {k: ich[k] for k in ("hp", "gold", "name_ko", "name_en", "name_zh", "desc_ko", "desc_en", "desc_zh")}
    ich["orig"]["deck"] = [dict(d) for d in ich["deck"]]
    ich["orig"]["relics"] = list(ich["relics"])
    for key in CHAR_IMAGE_PROPS:
        ich[key] = ""
    ich.update(combat_scale=100, combat_lift=0, combat_flip=False,
               attack_frames=[], hit_frames=[], attack_frames_ms=120, hit_frames_ms=120)
    # 미리보기용 원래 그림 (선택 화면 초상화)
    sel = _str_lit(_prop_value(body, "CustomCharacterSelectIconPath"))
    ich["orig_select_image"] = em.image_file(sel.replace("res://", "")) if sel else ""
    return ich


def takeover(em, sts2_path="", log=print, progress=None):
    """불러온 모드 → 새 프로젝트 dict. 같은 모드 ID 로 만들어서 빌드하면 원래 모드를 대체한다.

    - 원래 C# 코드는 그대로 포함하고(카드·유물·물약·파워 파일만 빼고), 원래 .pck 는 '<ID>_original.pck' 로 함께 넣는다.
    - 카드·유물·물약·파워는 원래 클래스 이름 그대로 프로젝트 항목이 되어 이 프로그램에서 고칠 수 있다.
    """
    if not em.dll and em.kind != "source":
        raise ValueError("이 모드는 dll 이 없어 통째로 가져올 수 없습니다 (코드가 필요합니다).")
    if (not em.src_dir or not os.path.isdir(em.src_dir)) and em.dll:
        # pck 안의 .cs 로 읽은 모드: 실제 빌드된 dll 과 다를 수 있으니 dll 을 풀어서 쓴다
        em.src_dir = decompile(em.dll, sts2_path, log=log)
    if not em.src_dir or not os.path.isdir(em.src_dir):
        raise ValueError("이 모드의 C# 코드를 읽지 못했습니다.")
    mid = em.id
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", mid or ""):
        raise ValueError(f"모드 ID '{mid}' 는 C# 이름으로 쓸 수 없어 통째로 가져올 수 없습니다.")
    srcp = os.path.normcase(os.path.abspath(em.dll or em.src_dir))
    key = hashlib.sha1(f"{srcp}|{os.path.getmtime(srcp)}".encode()).hexdigest()[:8]
    base = os.path.join(cache_root(), "takeover", f"{mid}-{key}")
    src_out = os.path.join(base, "src")
    shutil.rmtree(src_out, ignore_errors=True)
    os.makedirs(src_out, exist_ok=True)

    # ---- 원래 코드 복사 (네임스페이스가 생성 코드와 겹치면 옮긴다) ----
    clash = f"{mid}.{mid}Code"
    moved = f"{mid}.{mid}{TAKEOVER_ORIG_NS}"
    files = []
    for f in glob.glob(os.path.join(em.src_dir, "**", "*.cs"), recursive=True):
        rel = os.path.relpath(f, em.src_dir)
        if re.search(r"(^|[\\/])(bin|obj|\.godot|Properties)[\\/]", rel) or rel.lower().endswith("assemblyinfo.cs"):
            continue
        text = _read_text(f)
        if em.kind == "source" and "<auto-generated" in text[:400]:
            continue
        if em.kind != "source":       # 디컴파일 결과의 컴파일 안 되는 모양 고치기
            text = fix_out_ref(text)
            # [GeneratedRegex] 가 만든 코드는 이미 풀려 있다 → 속성만 남으면 정규식 생성기가 다시 만들려다 오류
            text = re.sub(r"(?m)^[ \t]*\[GeneratedRegex\(.*\)\][ \t]*\r?\n", "", text)
        files.append((rel, text))
    renamed = any(re.search(r"\bnamespace\s+" + re.escape(clash) + r"\b", t) for _r, t in files)
    if renamed:
        pat = re.compile(r"\b" + re.escape(clash) + r"\b")
        files = [(r, pat.sub(moved, t)) for r, t in files]
    for rel, text in files:
        dst = os.path.join(src_out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "w", encoding="utf-8") as fh:
            fh.write(text)

    # 바뀐 코드로 다시 읽는다 (클래스 이름·네임스페이스·부모가 생성 코드와 맞도록)
    em.classes = {}
    for rel, text in files:
        for c in parse_cs(text, os.path.join(src_out, rel)):
            em.classes.setdefault(c.name, c)
    em.items = {"card": [], "relic": [], "potion": [], "power": []}
    em.pools, em.characters = {}, []
    _extract_items(em)

    # ---- 리소스 ----
    pck_copy = ""
    if em.pck_path and os.path.isfile(em.pck_path):
        pck_copy = os.path.join(base, "original.pck")
        shutil.copy2(em.pck_path, pck_copy)
    res_dir = ""
    if em.kind == "source":
        cand = os.path.join(em.root, mid)
        if os.path.isdir(cand):
            res_dir = cand
    backup = os.path.join(base, "backup")
    if em.kind == "installed" and os.path.isdir(em.root) and not os.path.isdir(backup):
        shutil.copytree(em.root, backup, ignore=shutil.ignore_patterns("*.pdb"))
    with open(os.path.join(base, "loc.json"), "w", encoding="utf-8") as fh:
        json.dump(em.loc, fh, ensure_ascii=False)

    # ---- 프로젝트 ----
    P = M.default_project()
    m = em.manifest
    P["mod"].update({"id": mid, "name": em.name or mid, "author": em.author or P["mod"]["author"],
                     "description": m.get("description", "") or P["mod"]["description"],
                     "version": em.version or P["mod"]["version"]})
    if m.get("min_game_version"):
        P["mod"]["min_game_version"] = m["min_game_version"]
    P["character"]["enabled"] = False
    P["character"]["deck"], P["character"]["relics"] = [], []
    P["cards"], P["relics"], P["potions"], P["powers"] = [], [], [], []
    P["dependencies"] = _dep_entries(em, sts2_path)

    # 파일 하나에 형식이 하나뿐인 항목만 가져온다 (나머지는 원래 코드로 남는다)
    by_file = {}
    for rel, text in files:
        by_file[os.path.join(src_out, rel)] = (rel, _top_level_types(text))
    exclude, kept = [], []
    used = set()
    total = sum(len(v) for v in em.items.values())
    done = 0
    for kind, key in (("power", "powers"), ("card", "cards"), ("relic", "relics"), ("potion", "potions")):
        if kind == "card":
            generated_power_classes = {it.get("class") for it in P["powers"]}
            kept_power_classes = {entry.split(":", 1)[1] for entry in kept if entry.startswith("power:")}
            P["takeover"] = {"mod": mid, "extra_powers": [
                {"class": it.get("class"), "full": em.classes[it["class"]].full,
                 "name_ko": it.get("name_ko", ""), "name_en": it.get("name_en", ""),
                 "name_zh": it.get("name_zh", ""), "type": it.get("type", "Buff")}
                for it in em.items.get("power", []) if it.get("class") in kept_power_classes and
                it.get("class") not in generated_power_classes and it.get("class") in em.classes]}
        for it in em.items[kind]:
            done += 1
            if progress:
                progress(done, total, it.get("name_ko") or it["id"])
            c = it.get("_cls")
            info = by_file.get(getattr(c, "path", ""))
            if c is None or info is None or info[1] != [c.name]:
                kept.append(f"{kind}:{it['class']}")
                continue
            try:
                new = clone_item(em, it, P, "theirs")
            except Exception as exc:  # noqa: BLE001
                log(f"  가져오지 못해 원래 코드로 둡니다: {it['class']} ({exc})")
                kept.append(f"{kind}:{it['class']}")
                continue
            cl = new["clone"]
            cl["keep_name"] = True
            cl["class_name"] = c.name
            cl["namespace"] = c.namespace
            cl["src_file"] = info[0]
            parent = em.classes.get(c.base)
            if parent is not None and not cl.get("base"):
                cl["base"] = parent.full
            nid, n = new["id"], 2
            while nid in used:
                nid = f"{new['id']}_{n}"
                n += 1
            new["id"] = nid
            used.add(nid)
            P[key].append(new)
            exclude.append(info[0])
    # ---- 캐릭터 (여러 명이어도 전부) ----
    imported_chars, kept_chars = [], []
    for ec in em.characters:
        c = em.classes.get(ec["class"])
        info = by_file.get(getattr(c, "path", "")) if c else None
        lid = f"{mid.upper()}-{M.game_snake(ec['class'])}"
        names = {f"name_{lg}": em.loc[lg].get("characters", {}).get(f"{lid}.title", "") for lg in ("ko", "en", "zh")}
        if c is None or info is None or info[1] != [c.name]:
            kept_chars.append({"class": ec["class"], "loc_id": lid,
                               "card_pool_class": ec.get("pool", ""), "card_pool_full": ec.get("pool_full", ""), **names})
            continue
        ich = import_character(em, c, P, lid)
        ich["src_file"] = info[0]
        imported_chars.append(ich)
        exclude.append(info[0])
    P["imported_characters"] = imported_chars
    pool_owners = {}
    for character in imported_chars + kept_chars:
        pool_full = character.get("card_pool_full", "")
        if pool_full:
            pool_owners.setdefault(pool_full, character["class"])
    for card in P["cards"]:
        original_pool = (card.get("clone") or {}).get("their_pool", "")
        if original_pool in pool_owners:
            card["pool_character"] = pool_owners[original_pool]
    def all_effect_blocks(blocks):
        for block in blocks or []:
            if not isinstance(block, dict):
                continue
            yield block
            for key in ("body", "else", "third"):
                yield from all_effect_blocks(block.get(key))

    novel_monsters = sorted({str(b.get("args", {}).get("monster")) for it in P["cards"]
                             for e in it.get("effects", []) if e.get("kind") == "code"
                             for b in all_effect_blocks(e.get("blocks"))
                             if b.get("op") == "manosaba_novel_summon" and
                             isinstance(b.get("args", {}).get("monster"), str)})
    generated_power_classes = {it.get("class") for it in P["powers"]}
    kept_power_classes = {entry.split(":", 1)[1] for entry in kept if entry.startswith("power:")}
    extra_powers = []
    for it in em.items.get("power", []):
        cls = it.get("class")
        c = em.classes.get(cls)
        if cls not in kept_power_classes or cls in generated_power_classes or c is None:
            continue
        extra_powers.append({"class": cls, "full": c.full,
                             "name_ko": it.get("name_ko", ""), "name_en": it.get("name_en", ""),
                             "name_zh": it.get("name_zh", ""), "type": it.get("type", "Buff")})
    P["takeover"] = {"mod": mid, "dir": base, "src": src_out, "pck": pck_copy, "res_dir": res_dir,
                     "loc": os.path.join(base, "loc.json"), "exclude": sorted(set(exclude)),
                     "renamed_ns": moved if renamed else "", "kept": kept,
                     "novel_monsters": novel_monsters,
                     "extra_powers": extra_powers,
                     "patches_all": any(re.search(r"\.PatchAll\s*\(", t) for _r, t in files),
                     "characters": kept_chars,       # 원래 코드 그대로 둔 캐릭터 (아키텍트 기본 대사만 채움)
                     "source": em.root, "kind": em.kind}
    return P


def dependency_entry(em):
    powers = []
    for it in em.items["power"]:
        c = it.get("_cls")
        if c is None:
            continue
        powers.append({"class": c.name, "full": c.full, "name_ko": it.get("name_ko", ""),
                       "name_en": it.get("name_en", ""), "type": it.get("type", "Buff")})
    return {"id": em.id, "name": em.name, "version": em.version, "dll": em.dll, "powers": powers}

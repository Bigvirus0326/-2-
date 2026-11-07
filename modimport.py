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
def _ilspy_cmd():
    tools = os.path.join(cache_root(), "tools")
    exe = os.path.join(tools, "ilspycmd.exe" if sys.platform == "win32" else "ilspycmd")
    if not os.path.isfile(exe):
        alt = os.path.join(tools, "ilspycmd.cmd")
        if os.path.isfile(alt):
            return alt
    return exe


def ensure_decompiler(log=print):
    exe = _ilspy_cmd()
    if os.path.isfile(exe):
        return exe
    if not shutil.which("dotnet"):
        raise RuntimeError(".NET SDK(dotnet)가 없어 dll 을 읽을 수 없습니다.")
    log("dll 을 읽기 위한 디컴파일러(ilspycmd)를 처음 한 번 설치합니다...")
    tools = os.path.join(cache_root(), "tools")
    os.makedirs(tools, exist_ok=True)
    r = subprocess.run(["dotnet", "tool", "install", "ilspycmd", "--tool-path", tools],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=_NOWIN)
    if r.returncode != 0 and "already installed" not in (r.stdout + r.stderr):
        raise RuntimeError("ilspycmd 설치 실패:\n" + (r.stderr or r.stdout)[-800:])
    exe = _ilspy_cmd()
    if not os.path.isfile(exe):
        raise RuntimeError("ilspycmd 를 찾을 수 없습니다.")
    return exe


_NOWIN = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0


def decompile(dll, sts2_path="", extra_refs=(), log=print):
    """dll -> C# 소스 폴더 (캐시). 실패하면 예외."""
    st = os.stat(dll)
    key = hashlib.sha1(f"{os.path.abspath(dll)}|{st.st_size}|{st.st_mtime}".encode()).hexdigest()[:16]
    out = os.path.join(cache_root(), "decompiled", f"{os.path.splitext(os.path.basename(dll))[0]}-{key}")
    if os.path.isdir(out) and glob.glob(os.path.join(out, "**", "*.cs"), recursive=True):
        return out
    exe = ensure_decompiler(log)
    cmd = [exe, "-p", "-o", out]
    refs = list(extra_refs)
    if sts2_path:
        refs.append(os.path.join(sts2_path, "data_sts2_windows_x86_64"))
        for sub in ("mods", "mods.disabled"):
            for d in glob.glob(os.path.join(sts2_path, sub, "*")):
                if os.path.isdir(d):
                    refs.append(d)
    for r in refs:
        if os.path.isdir(r):
            cmd += ["-r", r]
    cmd.append(dll)
    log(f"dll 읽는 중: {os.path.basename(dll)}")
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", creationflags=_NOWIN,
                       env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
    if r.returncode != 0 or not glob.glob(os.path.join(out, "**", "*.cs"), recursive=True):
        shutil.rmtree(out, ignore_errors=True)
        raise RuntimeError("디컴파일 실패:\n" + (r.stderr or r.stdout)[-800:])
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
    return out


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
        if os.path.isfile(ref):
            return ref
        if self.pck is None:
            return ""
        out = os.path.join(self.cache, "images", ref)
        if os.path.isfile(out):
            return out
        if os.path.isfile(out + ".png"):
            return out + ".png"
        try:
            if ref.endswith(".res") and ref in self.pck:
                img = decode_res_image(ingame.rscc_decompress(self.pck.read(ref)))
                if img is None:
                    return ""
                os.makedirs(os.path.dirname(out), exist_ok=True)
                out = out + ".png"
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

    em.cache = os.path.join(cache_root(), "imports", re.sub(r"[^\w.-]", "_", em.id or "mod"))
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
                pool = re.search(r"CardPool<(?:[\w.]+\.)?(\w+)>", member_text(c.body, "CardPool"))
                em.characters.append({"class": c.name, "full": c.full, "hp": int(hp.group(1)) if hp else 0,
                                      "pool": pool.group(1) if pool else ""})
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
    return new


def dependency_entry(em):
    powers = []
    for it in em.items["power"]:
        c = it.get("_cls")
        if c is None:
            continue
        powers.append({"class": c.name, "full": c.full, "name_ko": it.get("name_ko", ""),
                       "name_en": it.get("name_en", ""), "type": it.get("type", "Buff")})
    return {"id": em.id, "name": em.name, "version": em.version, "dll": em.dll, "powers": powers}

"""
원본 모드의 C# (디컴파일한 OnPlay) -> 하나하나 고칠 수 있는 블록.

- C# 문장을 읽어 if / 반복 / switch / 묶음 구조를 그대로 블록으로 옮긴다.
- 같은 카드나 부모 클래스의 도우미 메서드 (예: BishopPlay -> Hit) 는 안으로 펼친다.
  상수로 고르는 switch (BishopSpell.Strike) 는 그 갈래만 남긴다.
- 함수 호출 한 줄은 '호출 블록' 하나가 되고, 인수 하나하나가 따로 고칠 수 있는 칸이 된다.
  수치 칸은 원본 변수 (DynamicVars) / 강화 수치 / 직접 입력한 수식으로 알아본다.
- 지원하지 않는 문장은 직접 코드 블록으로 남겨, 원래 동작이 그대로 유지된다.
"""
from __future__ import annotations

import copy
import re

KEYWORDS = {
    "abstract", "as", "base", "bool", "break", "byte", "case", "catch", "char", "checked", "class", "const", "continue",
    "decimal", "default", "delegate", "do", "double", "else", "enum", "event", "explicit", "extern", "false", "finally",
    "fixed", "float", "for", "foreach", "goto", "if", "implicit", "in", "int", "interface", "internal", "is", "lock",
    "long", "namespace", "new", "null", "object", "operator", "out", "override", "params", "private", "protected",
    "public", "readonly", "ref", "return", "sbyte", "sealed", "short", "sizeof", "stackalloc", "static", "string",
    "struct", "switch", "this", "throw", "true", "try", "typeof", "uint", "ulong", "unchecked", "unsafe", "ushort",
    "using", "virtual", "void", "volatile", "while", "var", "await", "async", "when", "nameof", "yield", "dynamic",
    "global", "not", "and", "or", "with", "record", "init", "get", "set", "value",
}
NUM_TYPES = {"int": "int", "decimal": "decimal", "float": "decimal", "double": "decimal", "long": "int", "Int32": "int",
             "Decimal": "decimal"}
PLUMBING = {"choiceContext", "cardPlay", "this", "CombatState", "CombatState!", "base", "null"}
_ID = re.compile(r"[A-Za-z_@][\w]*")
_NUM = re.compile(r"^-?\d+(?:\.\d+)?[mMfFdD]?$")
def call_signature(segs, rhs, aw=False):
    """호출 사슬과 인수 개수로 프로젝트에 저장할 안정적인 연결 키를 만든다."""
    parts = []
    for seg in segs:
        generic = ""
        if seg.get("gen"):
            a, b = seg["gen"]
            generic = "<" + re.sub(r"\s+", "", rhs[a:b]).replace("global::", "") + ">"
        if seg.get("args") is None:
            arity = "-"
        else:
            a, b = seg["args"]
            raw = rhs[a:b]
            arity = str(len(split_args(raw))) if raw.strip() else "0"
        parts.append(f"{seg['name']}{generic}/{arity}")
    return ("await " if aw else "") + ".".join(parts)


# ===========================================================================
# 글자 단위 도구 (문자열·주석 건너뛰기)
# ===========================================================================
def _skip_ws(s, i):
    n = len(s)
    while i < n:
        if s[i].isspace():
            i += 1
        elif s.startswith("//", i):
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
        elif s.startswith("/*", i):
            j = s.find("*/", i + 2)
            i = n if j < 0 else j + 2
        else:
            break
    return i


def _string_end(s, i):
    """s[i] 에서 문자열/문자 리터럴이 시작하면 그 끝 다음 위치, 아니면 -1."""
    n, j = len(s), i
    interp = verbatim = False
    while j < n and s[j] in "$@" and j - i < 3:
        interp |= s[j] == "$"
        verbatim |= s[j] == "@"
        j += 1
    if j >= n:
        return -1
    if s[j] == "'" and j == i:
        k = j + 1
        while k < n and s[k] != "'":
            k += 2 if s[k] == "\\" else 1
        return k + 1
    if s[j] != '"':
        return -1
    if s.startswith('"""', j):
        q = j
        while q < n and s[q] == '"':
            q += 1
        quotes = q - j
        end = s.find('"' * quotes, q)
        return n if end < 0 else end + quotes
    k = j + 1
    while k < n:
        c = s[k]
        if interp and c == "{":
            if s.startswith("{{", k):
                k += 2
                continue
            k = _scan_to(s, k + 1, "}") + 1
            continue
        if c == "\\" and not verbatim:
            k += 2
            continue
        if c == '"':
            if verbatim and s.startswith('""', k):
                k += 2
                continue
            return k + 1
        k += 1
    return n


def _scan_to(s, i, stops):
    """괄호 깊이 0 에서 stops 글자 중 하나가 나오는 위치 (없으면 len)."""
    depth, n = 0, len(s)
    while i < n:
        c = s[i]
        e = _string_end(s, i) if c in "\"'$@" else -1
        if e > 0:
            i = e
            continue
        if s.startswith("//", i) or s.startswith("/*", i):
            i = _skip_ws(s, i)
            continue
        if depth == 0 and c in stops:
            return i
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
            if depth < 0:
                return i
        i += 1
    return n


def _close(s, i):
    """s[i] 가 ( [ { 일 때 짝 닫는 괄호 위치."""
    j = _scan_to(s, i + 1, ")]}")
    return j


def _generic_end(s, i):
    """s[i] == '<' 가 제네릭 인수의 시작이면 '>' 다음 위치, 아니면 -1."""
    m = re.match(r"<(?:[\w\s.,?\[\]]|<(?:[\w\s.,?\[\]]|<[\w\s.,?\[\]]*>)*>)*>", s[i:])
    if not m or i == 0 or not (s[i - 1].isalnum() or s[i - 1] == "_"):
        return -1
    return i + m.end()


def split_args(s):
    """'a, Foo<A, B>(x), c' -> [(시작, 끝)] (s 안의 위치)."""
    out, depth, i, n, start = [], 0, 0, len(s), 0
    while i < n:
        c = s[i]
        e = _string_end(s, i) if c in "\"'$@" else -1
        if e > 0:
            i = e
            continue
        if c == "<":
            g = _generic_end(s, i)
            if g > 0:
                i = g
                continue
        if c in "([{":
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif c == "," and depth == 0:
            out.append((start, i))
            start = i + 1
        i += 1
    if s[start:].strip():
        out.append((start, n))
    res = []
    for a, b in out:
        while a < b and s[a].isspace():
            a += 1
        while b > a and s[b - 1].isspace():
            b -= 1
        res.append((a, b))
    return res


def map_idents(code, fn):
    """코드 속 식별자마다 fn(이름, 앞글자, 뒷부분) -> 바꿀 글자 (None = 그대로). 문자열 안은 건너뛰고
    보간 문자열의 {식} 안은 바꾼다."""
    out, i, n = [], 0, len(code)
    while i < n:
        c = code[i]
        if c in "\"'$@":
            e = _string_end(code, i)
            if e > 0:
                lit = code[i:e]
                if lit.lstrip("@").startswith("$"):
                    lit = _map_interp(lit, fn)
                out.append(lit)
                i = e
                continue
        if c.isalpha() or c == "_":
            j = i
            while j < n and (code[j].isalnum() or code[j] == "_"):
                j += 1
            name = code[i:j]
            k = i - 1
            while k >= 0 and code[k] in " \t\r\n":
                k -= 1
            prev = code[k] if k >= 0 else ""
            if prev == "." and k >= 1 and code[k - 1] == "?":
                prev = "."
            if prev == "!" and k >= 1 and code[k - 1] not in "( ,=":
                pass
            r = fn(name, prev, code[j:j + 40])
            out.append(name if r is None else r)
            i = j
            continue
        if c.isdigit():
            j = i
            while j < n and (code[j].isalnum() or code[j] in "._"):
                j += 1
            out.append(code[i:j])
            i = j
            continue
        out.append(c)
        i += 1
    return "".join(out)


def _map_interp(lit, fn):
    out, i, n = [], 0, len(lit)
    while i < n:
        if lit[i] == "{":
            if lit.startswith("{{", i):
                out.append("{{")
                i += 2
                continue
            j = _scan_to(lit, i + 1, "}:")
            k = _scan_to(lit, i + 1, "}")
            out.append("{" + map_idents(lit[i + 1:j], fn) + lit[j:k + 1])
            i = k + 1
            continue
        out.append(lit[i])
        i += 1
    return "".join(out)


def rename(code, mapping):
    """식별자 이름 바꾸기 (멤버 접근 .x 와 이름 붙은 인수 x: 는 건드리지 않음)."""
    if not mapping:
        return code

    def fn(name, prev, after):
        if name not in mapping or prev == ".":
            return None
        if re.match(r"\s*:(?!:)", after) and prev in ("(", ","):
            return None
        return mapping[name]
    return map_idents(code, fn)


def idents(code):
    found = set()
    map_idents(code, lambda name, prev, after: found.add(name) if prev != "." else None)
    return found


def dedent(text):
    lines = text.replace("\r", "").split("\n")
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    pad = min((len(l) - len(l.lstrip()) for l in lines[1:] if l.strip()), default=0)
    first = lines[0].strip() if lines else ""
    return "\n".join([first] + [l[pad:] if len(l) >= pad else l.strip() for l in lines[1:]]).replace("\t", "    ")


def one_line(text):
    return re.sub(r"\s*\n\s*", " ", text.strip())


# ===========================================================================
# 문장 읽기
# ===========================================================================
def parse_stmts(s):
    out, i, n = [], 0, len(s)
    while True:
        i = _skip_ws(s, i)
        if i >= n:
            return out
        node, i = _parse_stmt(s, i)
        if node is None:
            return out
        out.append(node)


def _embedded(s, i):
    """if/for 다음의 문장 하나 -> (문장 목록, 끝). 중괄호 묶음이면 그 안의 목록."""
    i = _skip_ws(s, i)
    if i < len(s) and s[i] == "{":
        j = _close(s, i)
        return parse_stmts(s[i + 1:j]), j + 1
    node, j = _parse_stmt(s, i)
    return ([node] if node else []), j


def _paren(s, i):
    i = _skip_ws(s, i)
    if i >= len(s) or s[i] != "(":
        return None, i
    j = _close(s, i)
    return s[i + 1:j], j + 1


_LOCAL_FN = re.compile(r"^(?:(?:async|static|unsafe|extern)\s+)*(?!(?:return|await|throw|yield|new|var|else|case|goto)\b)"
                       r"[\w.?\[\]]+(?:<[^()]*>)?\??\s+(\w+)\s*(?:<[^()]*>)?\s*\(")


def _parse_stmt(s, i):
    n = len(s)
    i = _skip_ws(s, i)
    if i >= n:
        return None, i
    start = i
    if s[i] == "{":
        j = _close(s, i)
        return {"k": "block", "body": parse_stmts(s[i + 1:j]), "src": s[start:j + 1]}, j + 1
    if s[i] == ";":
        return {"k": "stmt", "code": ";", "src": ";"}, i + 1
    m = re.match(r"(if|for|foreach|while|switch|do|try|lock|using|fixed|checked|unchecked|unsafe)\b", s[i:])
    if m:
        kw = m.group(1)
        j = i + m.end()
        if kw == "if":
            cond, j = _paren(s, j)
            if cond is None:
                return _plain_stmt(s, start)
            then, j = _embedded(s, j)
            k = _skip_ws(s, j)
            els = None
            if re.match(r"else\b", s[k:]):
                els, j = _embedded(s, k + 4)
            return {"k": "if", "cond": cond.strip(), "then": then, "else": els, "src": s[start:j]}, j
        if kw in ("for", "foreach", "while", "lock", "fixed") or (kw == "using" and _skip_ws(s, j) < n and s[_skip_ws(s, j)] == "("):
            head, j = _paren(s, j)
            if head is None:
                return _plain_stmt(s, start)
            body, j = _embedded(s, j)
            return {"k": "loop", "kw": kw, "head": f"{kw} ({one_line(head)})", "inner": head.strip(), "body": body,
                    "src": s[start:j]}, j
        if kw == "switch":
            expr, j = _paren(s, j)
            k = _skip_ws(s, j)
            if expr is None or k >= n or s[k] != "{":
                return _plain_stmt(s, start)
            e = _close(s, k)
            return {"k": "switch", "expr": expr.strip(), "sections": _sections(s[k + 1:e]), "src": s[start:e + 1]}, e + 1
        if kw == "do":
            _body, j = _embedded(s, j)
            k = _skip_ws(s, j)
            if re.match(r"while\b", s[k:]):
                _c, j = _paren(s, k + 5)
                j = _skip_ws(s, j)
                if j < n and s[j] == ";":
                    j += 1
            return {"k": "raw", "code": s[start:j], "src": s[start:j]}, j
        if kw == "try":
            _b, j = _embedded(s, j)
            while True:
                k = _skip_ws(s, j)
                mm = re.match(r"(catch|finally)\b", s[k:])
                if not mm:
                    break
                j = k + mm.end()
                if mm.group(1) == "catch":
                    k2 = _skip_ws(s, j)
                    if k2 < n and s[k2] == "(":
                        j = _close(s, k2) + 1
                    k2 = _skip_ws(s, j)
                    if re.match(r"when\b", s[k2:]):
                        _w, j = _paren(s, k2 + 4)
                _b, j = _embedded(s, j)
            return {"k": "raw", "code": s[start:j], "src": s[start:j]}, j
        if kw in ("checked", "unchecked", "unsafe") and _skip_ws(s, j) < n and s[_skip_ws(s, j)] == "{":
            _b, j = _embedded(s, j)
            return {"k": "raw", "code": s[start:j], "src": s[start:j]}, j
    return _plain_stmt(s, start)


def _plain_stmt(s, i):
    n = len(s)
    j = _scan_to(s, i, ";{")
    while j < n and s[j] == "{":
        head = s[i:j].strip()
        if _LOCAL_FN.match(head) and head.endswith(")") or re.search(r"\)\s*where\s[^;]*$", head):
            e = _close(s, j)
            return {"k": "local_fn", "name": _LOCAL_FN.match(head).group(1) if _LOCAL_FN.match(head) else "",
                    "code": s[i:e + 1], "src": s[i:e + 1]}, e + 1
        # 객체/컬렉션 초기화 {..} 는 문장의 일부
        e = _close(s, j)
        j = _scan_to(s, e + 1, ";{")
    code = s[i:j + 1] if j < n else s[i:j]
    head = code.strip()
    mm = _LOCAL_FN.match(head)
    if mm and "=>" in head and head.find("=>") > head.find("("):
        return {"k": "local_fn", "name": mm.group(1), "code": code, "src": code}, j + 1
    return {"k": "stmt", "code": code.strip(), "src": code}, j + 1


def _sections(s):
    """switch 안 -> [(라벨 목록, 문장 목록)]"""
    out, i, n = [], 0, len(s)
    while True:
        i = _skip_ws(s, i)
        if i >= n:
            return out
        labels = []
        while True:
            i = _skip_ws(s, i)
            m = re.match(r"(case\b|default\s*:)", s[i:])
            if not m:
                break
            if m.group(1).startswith("default"):
                labels.append("default")
                i += m.end()
            else:
                j = _scan_to(s, i + 4, ":")
                # 'case A.B:' 의 ':' 를 찾는다 (?: 삼항은 드묾)
                labels.append(s[i + 4:j].strip())
                i = j + 1
        if not labels:
            return None
        stmts = []
        while True:
            i = _skip_ws(s, i)
            if i >= n or re.match(r"(case\b|default\s*:)", s[i:]):
                break
            node, i = _parse_stmt(s, i)
            if node is None:
                break
            stmts.append(node)
        out.append((labels, stmts))


def _src(nodes):
    return "\n".join(dedent(x["src"]) for x in nodes)


# ===========================================================================
# 클래스 / 메서드 찾기
# ===========================================================================
_METHOD = re.compile(
    r"^\s*((?:\[[^\]]*\]\s*)*)((?:(?:public|protected|private|internal|override|virtual|sealed|static|async|new|"
    r"abstract|unsafe|extern)\s+)*)([\w.?\[\]<>,\s]+?)\s+(\w+)\s*(<[^()]*>)?\s*\(", re.S)


def members(body):
    """클래스 본문의 최상위 멤버 덩어리들."""
    out, i, n, start = [], 0, len(body), 0
    while i < n:
        c = body[i]
        e = _string_end(body, i) if c in "\"'$@" else -1
        if e > 0:
            i = e
            continue
        if body.startswith("//", i) or body.startswith("/*", i):
            i = _skip_ws(body, i)
            continue
        if c in "([{":
            j = _close(body, i)
            if c == "{":
                rest = body[j + 1:]
                mm = re.match(r"\s*(=[^;]*)?;", rest)
                if mm and not re.match(r"\s*$", body[start:i]):
                    j += mm.end()
                if not re.search(r"=\s*(new\b[^;]*)?$", body[start:i]) or mm:
                    out.append(body[start:j + 1])
                    start = j + 1
            i = j + 1
            continue
        if c == ";":
            out.append(body[start:i + 1])
            start = i + 1
        i += 1
    return [m for m in out if m.strip()]


def parse_method(text):
    m = _METHOD.match(text)
    if not m:
        return None
    mods = m.group(2).split()
    ret = m.group(3).strip()
    if ret in ("return", "await", "new", "else") or set(ret.split()) & {"class", "struct", "enum", "record", "interface"}:
        return None
    po = text.find("(", m.end() - 1)
    pc = _close(text, po)
    params = []
    plist = text[po + 1:pc]
    for a, b in split_args(plist):
        p = plist[a:b]
        default = None
        k = _scan_to(p, 0, "=")
        if k < len(p):
            default = p[k + 1:].strip()
            p = p[:k].strip()
        p = re.sub(r"^\[[^\]]*\]\s*", "", p)
        parts = p.split()
        mod = parts[0] if parts and parts[0] in ("ref", "out", "in", "params", "this") else ""
        if mod:
            parts = parts[1:]
        if len(parts) < 2:
            return None
        params.append({"name": parts[-1], "type": " ".join(parts[:-1]), "default": default, "mod": mod})
    rest = text[pc + 1:]
    rest_s = re.sub(r"^\s*where\s[^{=]*", "", rest)
    body, expr = None, None
    k = _skip_ws(rest_s, 0)
    if rest_s[k:k + 1] == "{":
        e = _close(rest_s, k)
        body = rest_s[k + 1:e]
    elif rest_s[k:k + 2] == "=>":
        expr = rest_s[k + 2:].strip().rstrip(";").strip()
    gen = [g.strip() for g in (m.group(5) or "<>")[1:-1].split(",") if g.strip()]
    return {"name": m.group(4), "ret": ret, "mods": mods, "params": params, "body": body, "expr": expr, "gen": gen}


def private_names(body):
    names = set()
    for mem in members(body):
        head = mem.split("{")[0].split("=>")[0]
        if re.match(r"\s*(?:\[[^\]]*\]\s*)*private\b", head) or not re.match(
                r"\s*(?:\[[^\]]*\]\s*)*(?:public|protected|internal)\b", head):
            pm = parse_method(mem)
            if pm:
                names.add(pm["name"])
                continue
            mm = re.match(r"\s*(?:\[[^\]]*\]\s*)*(?:\w+\s+)*?[\w.?<>\[\],]+\s+(\w+)\s*(?:[;={]|=>)", head + ";")
            if mm:
                names.add(mm.group(1))
        elif re.search(r"\bprivate\s+(?:set|init)\b", mem):
            # 공개 속성이지만 값 넣기는 그 클래스 안에서만 → 펼친 코드가 값을 넣으면 안 된다
            mm = re.match(r"\s*(?:\[[^\]]*\]\s*)*(?:\w+\s+)*?[\w.?<>\[\],]+\s+(\w+)\s*(?:[;={]|=>)", head + ";")
            if mm:
                names.add("set:" + mm.group(1))
    return names


def assigns_any(body, names):
    """body 가 names 중 하나에 값을 넣는지 (=, +=, ++ 등)."""
    for n in names:
        p = r"(?<![\w.])(?:this\s*\.\s*)?" + re.escape(n)
        if re.search(p + r"\s*(?:[-+*/%&|^]|<<|>>|\?\?)?=(?!=)", body) or re.search(p + r"\s*(?:\+\+|--)", body) or \
                re.search(r"(?:\+\+|--)\s*(?:this\s*\.\s*)?" + re.escape(n) + r"\b", body):
            return True
    return False


class ClassChain:
    """카드 클래스 -> 부모 -> ... (메서드 찾기, 펼쳐도 되는지 판단)."""

    def __init__(self, card_body, parents):
        # parents: [(이름, 본문)] 가까운 부모부터. 펼쳐서 복제 클래스 안에 넣을 수 있는 것만 넣는다.
        self.levels = [("card", card_body, set())] + [(nm, b, private_names(b)) for nm, b in parents]
        self._cache = {}

    def methods(self, name, start=0):
        out = []
        for li in range(start, len(self.levels)):
            key = (li, name)
            if key not in self._cache:
                self._cache[key] = [pm for pm in parsed_members(self.levels[li][1]) if pm["name"] == name]
            for pm in self._cache[key]:
                out.append((li, pm))
        return out

    def find(self, name, nargs, named=(), start=0):
        for li, pm in self.methods(name, start):
            ps = pm["params"]
            req = sum(1 for p in ps if p["default"] is None and p["mod"] != "params")
            if req <= nargs <= len(ps) or any(p["mod"] == "params" for p in ps):
                if all(any(p["name"] == nm for p in ps) for nm in named):
                    return li, pm
        return None


# ===========================================================================
# 값 알아보기
# ===========================================================================
def _num(text):
    t = text.strip()
    if _NUM.match(t):
        v = float(re.sub(r"[mMfFdD]$", "", t))
        return int(v) if v.is_integer() else v
    return None


_PURE_REF = re.compile(r"[A-Za-z_][\w.?]*(?:\s*\?\?\s*[A-Za-z_][\w.?]*)?")   # 값을 바꾸지 않는 이름·맴버 (Me, cardPlay.Target ?? Me)
_TYPED_LHS = re.compile(r"[\w.<>\[\]?]+\s+([A-Za-z_]\w*)\s*=")                 # 'Creature t =' 같은 자료형 선언


def _game_power_key(cls):
    """게임 기본 파워 클래스 이름(StrengthPower) -> 값 블록의 파워 키(Strength)."""
    import modgen as M
    return next((k for k, v in M.POWERS.items() if v[0] == cls), None)


_COMMON_BLOCK = re.compile(r"\s*await\s+CommonActions\.CardBlock\(\s*this\s*,\s*([^()]+?)\s*\)\s*;?\s*")
_COMMON_DRAW = re.compile(r"\s*await\s+CommonActions\.Draw\(\s*this\s*,\s*([^()]+?)\s*\)\s*;?\s*")


_EXISTS = re.compile(r"\(?\s*(Owner\??\.Creature|Me|cardPlay\.Target)\s*(==|!=)\s*null\s*\)?")


def _exists_cond(text):
    """'대상 == null' 같은 생물 유무 확인을 블록의 조건으로 바꾼다. 해당하지 않으면 None."""
    m = _EXISTS.fullmatch(text.strip())
    if not m:
        return None
    who = "target" if m.group(1) == "cardPlay.Target" else "self"
    return {"t": "exists", "who": who, "neg": m.group(2) == "=="}


def _has_raw(seq):
    """블록 목록 안(안쪽 포함)에 직접 코드·직접 호출이 있으면 True."""
    for b in seq or []:
        if b.get("op") in ("source_step", "src_call", "src_loop"):
            return True
        if any(_has_raw(b.get(k)) for k in ("body", "else", "third")):
            return True
    return False


def _common_rewrite(rhs):
    """BaseLib 'CommonActions' 의 자주 쓰는 도우미를 같은 효과의 게임 호출 문장으로 바꾼다.
    CardBlock(this, play) == CreatureCmd.GainBlock(Owner.Creature, 방어도 변수, 이동, play)
    Draw(this, ctx)       == CardPileCmd.Draw(ctx, 뽑을 장수 변수, Owner)"""
    m = _COMMON_BLOCK.fullmatch(rhs)
    if m:
        return f"await CreatureCmd.GainBlock(Owner.Creature, DynamicVars.Block.BaseValue, ValueProp.Move, {m.group(1)})"
    m = _COMMON_DRAW.fullmatch(rhs)
    if m:
        return f"await CardPileCmd.Draw({m.group(1)}, DynamicVars.Cards.BaseValue, Owner)"
    return rhs


_ARITH_UNSAFE = re.compile(r'[<>?:=!&|{}\[\]"%]')


def _split_arith(e):
    """최상위 사칙 연산 한 번을 (왼쪽, 연산자, 오른쪽) 으로 나눈다. 비교·대입·삼항·제네릭 등이 섞이면 None.
    나눗셈은 C# 정수 나눗셈과 값 블록의 내림 계산이 달라 제외한다."""
    if _ARITH_UNSAFE.search(e):
        return None
    depth, levels = 0, []
    for ch in e:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth -= 1
        levels.append(depth)

    def binary(i):   # 앞에 피연산자가 있어야 이항 연산자다 (단항 - 제외)
        j = i - 1
        while j >= 0 and e[j] == " ":
            j -= 1
        return j >= 0 and (e[j].isalnum() or e[j] in "_)")

    for ops in ("+-", "*/"):
        cand = [i for i, ch in enumerate(e) if ch in ops and levels[i] == 0 and binary(i)]
        if cand:
            i = cand[-1]
            left, right = e[:i].strip(), e[i + 1:].strip()
            if e[i] == "/" or not left or not right:
                return None
            return left, e[i], right
    return None


def _plain_value(rhs):
    """값 넣기 블록에 그대로 넣어도 되는 한 줄짜리 식인지 (대입·람다·객체 생성·블록 등은 제외)."""
    return bool(rhs.strip()) and not re.search(r"\b(?:await|new|delegate|stackalloc|throw)\b|=>|[{};]", rhs)


def _strings(v):
    """dict·list 안의 글 값들 (키는 빼고)."""
    if isinstance(v, str):
        return [v]
    if isinstance(v, dict):
        return [x for item in v.values() for x in _strings(item)]
    if isinstance(v, (list, tuple)):
        return [x for item in v for x in _strings(item)]
    return []


def _walk_blocks(seq):
    for b in seq or []:
        yield b
        for key in ("body", "else", "third"):
            yield from _walk_blocks(b.get(key))


def _settle_aliases(blocks):
    """'_alias' 표식(자료형 선언 = 값): 그 이름을 직접 코드나 직접 호출이 쓰면 선언을 되살리고, 아니면 버린다.
    블록으로 바뀐 곳은 이름 대신 원래 값을 쓰므로 선언이 없어도 된다."""
    markers = []

    def collect(seq):
        for b in seq or []:
            if b.get("op") == "_alias":
                markers.append(b)
            for key in ("body", "else", "third"):
                collect(b.get(key))

    def live_text(seq, out, restored):
        for b in seq or []:
            if b.get("op") != "_alias" or id(b) in restored:
                out.append(" ".join(_strings({k: v for k, v in b.items() if k not in ("op", "body", "else", "third")})))   # 값만 본다 (칸 이름 creature 등은 제외)
            for key in ("body", "else", "third"):
                live_text(b.get(key), out, restored)
        return out

    collect(blocks)
    # 블록 칸에 적힌 이름은 원래 값으로 바꾼다 (선언을 되살리지 않도록). 값이 같은 별칭만 해당된다.
    values = {}
    for m in markers:
        rhs = m["args"]["source"].split("=", 1)[1].strip().rstrip(";").strip()
        values[m["args"]["name"]] = rhs

    # 같은 이름이 람다 매개변수·새 선언·반복 변수로 다시 쓰이면 바꾸지 않는다 (그 이름은 다른 값이다)
    all_text = " ".join(x for b in _walk_blocks(blocks) if b.get("op") != "_alias"
                        for x in _strings({k: v for k, v in b.items() if k not in ("op", "body", "else", "third")}))
    for name in list(values):
        n = re.escape(name)
        if re.search(rf"(?<![\w.]){n}\s*=>|\([^()]*\b{n}\s*[,)][^()]*\)\s*=>|\b(?:from|foreach\s*\([^()]*?)\s+{n}\s+in\b"
                     rf"|\b(?!(?:in|is|as|return|await|new|out|ref|else|case|yield|throw)\b)[\w<>\[\]?]+\s+{n}\s*[=;,)]|(?<![\w.]){n}\s*(?:[+\-*/]?=(?!=)|\+\+|--)", all_text):
            del values[name]

    def subst(v):
        if isinstance(v, str):
            out = v
            for _ in range(8):
                nxt = rename(out, values)
                if nxt == out:
                    break
                out = nxt
            return out
        if isinstance(v, dict):
            return {k: (x if k in ("body", "else", "third", "op") else subst(x)) for k, x in v.items()}
        if isinstance(v, list):
            return [subst(x) for x in v]
        return v

    def apply(seq):
        for b in seq or []:
            if b.get("op") == "_alias":
                continue
            for k in list(b):
                if k not in ("op", "body", "else", "third"):
                    b[k] = subst(b[k])
            for key in ("body", "else", "third"):
                if key in b:
                    apply(b[key])
    if values:
        apply(blocks)
    restored = set()
    changed = True
    while changed:
        changed = False
        text = "\n".join(live_text(blocks, [], restored))
        for m in markers:
            if id(m) not in restored and re.search(r"\b" + re.escape(m["args"]["name"]) + r"\b", text):
                restored.add(id(m))
                changed = True

    def rebuild(seq):
        out = []
        for b in seq or []:
            if b.get("op") == "_alias":
                if id(b) in restored:
                    out.append({"op": "source_step", "args": {"source": b["args"]["source"]}})
                continue
            for key in ("body", "else", "third"):
                if key in b:
                    b[key] = rebuild(b[key])
            out.append(b)
        return out

    return rebuild(blocks)


class Decomposer:
    def __init__(self, card, chain, class_names=(), max_depth=6, project=None):
        self.card = card
        self.chain = chain
        self.project = project
        self.raw_vars = {v["name"]: v for v in card.get("raw_vars", []) if v.get("name")}
        self.classes = class_names if isinstance(class_names, dict) else {}
        self.class_names = set(class_names)
        self._sigs = {}
        self.taken = set()
        self.max_depth = max_depth
        self.stack = []
        # Local aliases let the recognizers understand decompiled code such as
        # ``var creature = Owner.Creature; ... Apply(..., creature, ...)``.
        self.aliases = {}
        self.stats = {"calls": 0, "inlined": 0, "folded": 0, "raw": 0}
        self.uid = 0

    # ---- 값 ----
    def resolve(self, expr, env=None, depth=0, start=0):
        """식 -> 값 블록 ({"t":"num"/"dynvar"}) 또는 None."""
        e = expr.strip()
        if e == "Amount" and getattr(self, "own_power", None):
            return {"t": "stack", "power": self.own_power, "who": "self"}
        m = (re.fullmatch(r"(?:Owner(?:\.Creature)?|Me)\??\.(?:GetPowerAmount|GetPower)<(\w+)>\(\)(?:\??\.Amount)?", e)
             or re.fullmatch(r"N<(\w+)>\(Me\)", e))
        if m:   # 내 생물의 게임 기본 파워 수치 (예: GetPowerAmount<StrengthPower>())
            key = _game_power_key(m.group(1))
            if key:
                return {"t": "stack", "power": key, "who": "self"}
        if depth > 6 or not e:
            return None
        while e.startswith("(") and _close(e, 0) == len(e) - 1:
            e = e[1:-1].strip()
        if env and any(isinstance(x, str) for x in env.values()) and e not in env:
            e = rename(e, {k: x for k, x in env.items() if isinstance(x, str)})
        m = re.fullmatch(r"\((?:int|decimal|float|double)\)\s*(.+)", e)
        if m:
            return self.resolve(m.group(1), env, depth + 1, start)
        if env and e in env:
            return self.resolve(env[e], None, depth + 1, start) if not isinstance(env[e], (int, float)) else \
                {"t": "num", "v": env[e]}
        n = _num(e)
        if n is not None:
            return {"t": "num", "v": n}
        m = re.fullmatch(r"(?:base\.|this\.)?DynamicVars(?:\.(\w+)|\[\s*\"(\w+)\"\s*\])(?:\.(BaseValue|IntValue|PreviewValue))?", e)
        if m:
            name = m.group(1) or m.group(2)
            if name in self.raw_vars:
                return {"t": "dynvar", "name": name, "prop": m.group(3) or ""}
            return None
        m = re.fullmatch(r"(!?)IsUpgraded\s*\?\s*(.+?)\s*:\s*(.+)", e)
        if m and _scan_to(m.group(2), 0, "?:") == len(m.group(2)):
            a = self.resolve(m.group(2), env, depth + 1, start)
            b = self.resolve(m.group(3), env, depth + 1, start)
            if m.group(1):
                a, b = b, a
            return self._up(b, a)
        m = re.fullmatch(r"(base\.|this\.)?(\w+)\s*\((.*)\)", e, re.S)
        if m and _close(e, e.find("(")) == len(e) - 1:
            args_s = m.group(3)
            args = [args_s[a:b] for a, b in split_args(args_s)]
            vals = []
            for a in args:
                if env and a.strip() in env:
                    vals.append(env[a.strip()])
                    continue
                v = _num(a)
                if v is None and re.fullmatch(r'"[\w ]*"', a.strip()):
                    v = a.strip()          # V("D") 처럼 변수 이름을 넘기는 도우미
                if v is None:
                    return None
                vals.append(v)
            found = self.chain.find(m.group(2), len(vals), start=(start + 1) if m.group(1) == "base." else 0)
            if not found:
                return None
            li, pm = found
            if NUM_TYPES.get(pm["ret"]) is None:
                return None
            env2 = {p["name"]: (vals[i] if i < len(vals) else _num(p["default"] or "0") or 0)
                    for i, p in enumerate(pm["params"])}
            return self._eval_body(pm, env2, depth + 1, li)
        sp = _split_arith(e)   # 'a + b' 같은 사칙 연산 (값 블록의 op)
        if sp:
            a = self.resolve(sp[0], env, depth + 1, start)
            b = self.resolve(sp[2], env, depth + 1, start)
            if a is not None and b is not None:
                return {"t": "op", "op": sp[1], "a": a, "b": b}
        return None

    def _up(self, normal, upgraded):
        if not normal or not upgraded:
            return None
        if normal == upgraded:
            return normal
        if normal.get("t") == "num" and upgraded.get("t") == "num" and not normal.get("up") and not upgraded.get("up"):
            d = upgraded["v"] - normal["v"]
            return {"t": "num", "v": normal["v"], "up": int(d) if float(d).is_integer() else d}
        return None

    def _eval_body(self, pm, env, depth, li):
        if pm["expr"] is not None:
            return self.resolve(pm["expr"], env, depth, li)
        if pm["body"] is None:
            return None
        r = self._eval_stmts(parse_stmts(pm["body"]), env, depth, li)
        return r[1] if r and r[0] == "ret" else None

    def _eval_stmts(self, stmts, env, depth, li):
        """-> ("ret", 값) / ("brk",) / ("fall",) / None (모름)"""
        for k, st in enumerate(stmts):
            if st["k"] == "stmt":
                if st["code"] == "break;":
                    return ("brk",)
                m = re.fullmatch(r"return\s+(.+);", st["code"], re.S)
                v = self.resolve(m.group(1), env, depth, li) if m else None
                return ("ret", v) if v is not None else None
            if st["k"] == "block":
                r = self._eval_stmts(st["body"], env, depth, li)
                if r is None or r[0] != "fall":
                    return r
                continue
            if st["k"] == "if":
                c = self._eval_cond(st["cond"], env)
                if c in (True, False):
                    branch = st["then"] if c else (st["else"] or [])
                    r = self._eval_stmts(branch, env, depth, li)
                    if r is None or r[0] != "fall":
                        return r
                    continue
                if c in ("up", "!up"):
                    a = self._eval_stmts(st["then"], env, depth, li)
                    b = self._eval_stmts(st["else"] if st["else"] is not None else stmts[k + 1:], env, depth, li)
                    if not (a and b and a[0] == "ret" and b[0] == "ret"):
                        return None
                    v = self._up(b[1], a[1]) if c == "up" else self._up(a[1], b[1])
                    return ("ret", v) if v is not None else None
                return None
            if st["k"] == "switch" and st["sections"]:
                key = rename(st["expr"], {kk: str(vv) for kk, vv in env.items()}).strip()
                if _num(key) is None and not re.fullmatch(r"[A-Z]\w*(?:\.[A-Z]\w*)+", key):
                    return None
                arm = next((s for s in st["sections"] if any(re.sub(r"\s", "", l) == key for l in s[0])), None) or \
                    next((s for s in st["sections"] if "default" in s[0]), None)
                if arm is not None:
                    r = self._eval_stmts(arm[1], env, depth, li)
                    if r is None or r[0] == "ret":
                        return r
                continue
            return None
        return ("fall",)

    def const_prop(self, name):
        """'protected override X VfxAnchor => MageVfxAnchor.EnemyCenter;' 처럼 클래스마다 정해진 값."""
        if name in self.taken:
            return None
        for _nm, body, _priv in self.chain.levels:
            for mem in members(body):
                m = re.match(r"\s*(?:\[[^\]]*\]\s*)*(?:(?:public|protected|internal|private|override|virtual|sealed|"
                             r"static|new)\s+)*[\w.?<>\[\]]+\s+" + re.escape(name) +
                             r"\s*=>\s*([A-Z]\w*(?:\.[A-Z]\w*)+|-?\d+|true|false)\s*;\s*$", mem)
                if m:
                    return m.group(1)
                if re.match(r"\s*(?:\[[^\]]*\]\s*)*(?:\w+\s+)*[\w.?<>\[\]]+\s+" + re.escape(name) + r"\s*(?:=>|\{)", mem):
                    return None
        return None

    def _eval_cond(self, cond, env):
        c = cond.strip()
        if c in ("IsUpgraded", "base.IsUpgraded", "this.IsUpgraded"):
            return "up"
        if c in ("!IsUpgraded", "!base.IsUpgraded", "!this.IsUpgraded"):
            return "!up"
        expr = rename(c, {k: str(v) for k, v in env.items()})
        if not re.fullmatch(r"[\d\s.()<>=!&|+\-*/%]+", expr):
            return None
        py = expr.replace("&&", " and ").replace("||", " or ").replace("!=", " != ")
        py = re.sub(r"!(?!=)", " not ", py)
        try:
            return bool(eval(py, {"__builtins__": {}}, {}))
        except Exception:
            return None

    # ---- 블록 만들기 ----
    def blocks(self, stmts):
        out = []
        outer_aliases = self.aliases.copy()
        try:
            for st in stmts:
                out += self.node(st)
        finally:
            self.aliases = outer_aliases
        return out

    def _remember_alias(self, lhs, rhs):
        """Track only simple, side-effect-free local values for API recognition."""
        m = re.fullmatch(r"\s*(?:(?:[\w.?<>\[\],]+\s+)?)([A-Za-z_]\w*)\s*=\s*", lhs)
        if not m:
            return
        name = m.group(1)
        # A reassignment invalidates aliases which were derived from the old value.
        doomed = {name}
        changed = True
        while changed:
            changed = False
            for alias, expr in list(self.aliases.items()):
                if alias not in doomed and idents(expr) & doomed:
                    doomed.add(alias)
                    changed = True
        for alias in doomed:
            self.aliases.pop(alias, None)
        value = rhs.strip().rstrip(";").strip()
        if not value or name in idents(value):
            return
        if re.search(r"\b(?:await|new|throw|delegate|stackalloc)\b|=>|\+\+|--|(?<![=!<>])=(?!=)", value):
            return
        # Method calls and object initializers can have side effects; keep them opaque.
        if re.search(r"\b[A-Za-z_]\w*\s*\(", value) or re.search(r"\b(?:with|is)\s*\{", value):
            return
        self.aliases[name] = value

    def _expand_aliases(self, text):
        value = text or ""
        for _ in range(8):
            expanded = rename(value, self.aliases)
            if expanded == value:
                break
            value = expanded
        return value

    def raw(self, code):
        if re.fullmatch(r"return\s*(?:Task\.CompletedTask)?\s*;", code.strip()):
            return [{"op": "early_return", "args": {}}]   # 생성 코드의 메서드는 async Task 이므로 'return;' 과 같다
        if code.strip() in ("break;", "continue;"):   # 원래 자리에 그대로 들어가므로 반복을 끝내는/건너뛰는 뜻이 같다
            return [{"op": "loop_break" if code.strip() == "break;" else "loop_continue", "args": {}}]
        self.stats["raw"] += 1
        return [{"op": "source_step", "args": {"source": dedent(code)}}]

    def node(self, st):
        blocks = self._node(st)
        # 옮기는 모드(whole_raw): 안쪽에 직접 코드가 남는 if·반복 문장은 문장 전체를 직접 코드 한 줄로 둔다 (순서·원문 보존)
        if getattr(self, "whole_raw", False) and st["k"] in ("if", "loop", "block", "switch") and st.get("src") and _has_raw(blocks):
            return self.raw(st["src"])
        return blocks

    def _node(self, st):
        k = st["k"]
        if k == "block":
            return [{"op": "src_loop", "args": {"head": ""}, "body": self.blocks(st["body"])}]
        if k == "if":
            folded = self._fold_cond(st["cond"])
            if folded is True:
                self.stats["folded"] += 1
                return self.blocks(st["then"])
            if folded is False:
                self.stats["folded"] += 1
                return self.blocks(st["else"] or [])
            text = one_line(self._expand_aliases(st["cond"]))   # 별칭은 펼쳐서 선언이 필요 없게 한다
            cond = _exists_cond(text) or {"t": "src", "code": text}
            if st["else"] is None:
                return [{"op": "if", "args": {"cond": cond}, "body": self.blocks(st["then"])}]
            return [{"op": "if_else", "args": {"cond": cond}, "body": self.blocks(st["then"]),
                     "else": self.blocks(st["else"])}]
        if k == "loop":
            if st["kw"] == "for":
                m = re.fullmatch(r"\s*(?:int|var)\s+(\w+)\s*=\s*0\s*;\s*(\w+)\s*<\s*(.+?)\s*;\s*(?:\1\+\+|\+\+\1|\1\s*\+=\s*1)\s*",
                                 st["inner"], re.S)
                if m and m.group(1) == m.group(2) and m.group(1) not in idents(_src(st["body"])):
                    times = self.value(m.group(3))
                    return [{"op": "repeat", "args": {"times": times}, "body": self.blocks(st["body"])}]
            return [{"op": "src_loop", "args": {"head": st["head"]}, "body": self.blocks(st["body"])}]
        if k == "switch":
            return self.switch(st)
        if k in ("raw", "local_fn"):
            return self.raw(st["src"])
        return self.stmt(st["code"])

    def _fold_cond(self, cond):
        m = re.fullmatch(r"\s*([\w.]+)\s*(==|!=)\s*([\w.]+)\s*", cond)
        if not m:
            return None
        a, op, b = m.groups()
        const = lambda x: bool(re.fullmatch(r"[A-Z]\w*(?:\.[A-Z]\w*)+|-?\d+|true|false", x))  # noqa: E731
        if not (const(a) and const(b)) or (a.count(".") != b.count(".") and not (_num(a) is not None and _num(b) is not None)):
            return None
        return (a == b) if op == "==" else (a != b)

    def switch(self, st):
        expr, secs = st["expr"], st["sections"]
        if secs is None:
            return self.raw(st["src"])
        if re.fullmatch(r"(?:this\.)?[A-Z]\w*", expr):
            cp = self.const_prop(expr.replace("this.", ""))
            if cp:
                expr = cp
        const = bool(re.fullmatch(r"[A-Z]\w*(?:\.[A-Z]\w*)+|-?\d+|true|false|\"[^\"]*\"", expr))
        def arm_body(stmts):
            body = list(stmts)
            if len(body) == 1 and body[0]["k"] == "block":
                body = list(body[0]["body"])
            if body and body[-1]["k"] == "stmt" and body[-1]["code"] == "break;":
                body = body[:-1]
            elif not (body and body[-1]["k"] == "stmt" and re.match(r"(return|throw)\b", body[-1]["code"])):
                return None
            if re.search(r"\bbreak\s*;", _src([b for b in body if b["k"] != "loop"])) or \
                    re.search(r"\bgoto\b", _src(body)):
                return None
            return body
        if const:
            hit = next((s for s in secs if any(re.sub(r"\s", "", l) == re.sub(r"\s", "", expr) for l in s[0])), None) or \
                next((s for s in secs if "default" in s[0]), None)
            self.stats["folded"] += 1
            if hit is None:
                return []
            body = arm_body(hit[1])
            if body is None:
                return self.raw(st["src"])
            return self.blocks(body)
        simple = re.fullmatch(r"[\w.]+", expr)
        conds = []
        for labels, stmts in secs:
            body = arm_body(stmts)
            if body is None or not simple or any(l != "default" and not re.fullmatch(r"[\w.\-]+|\"[^\"]*\"", l)
                                                 for l in labels):
                return self.raw(st["src"])
            conds.append((None if "default" in labels else " || ".join(f"{expr} == {l}" for l in labels), body))
        conds.sort(key=lambda x: x[0] is None)
        out, tail = None, []
        for cond, body in reversed(conds):
            if cond is None:
                tail = self.blocks(body)
                continue
            blk = {"op": "if_else" if tail else "if", "args": {"cond": {"t": "src", "code": cond}},
                   "body": self.blocks(body)}
            if tail:
                blk["else"] = tail
            tail = [blk]
        return tail

    # ---- 한 문장 ----
    def stmt(self, code):
        code = code.strip()
        if code in (";", "", "await Task.CompletedTask;"):   # 아무 일도 하지 않는 줄
            return []
        inc =re.fullmatch(r"([A-Za-z_][\w.]*)\s*(\+\+|--)\s*;", code)
        if inc:   # 'x++;' 는 '값 넣기 x += 1;' 과 같다
            code = f"{inc.group(1)} {inc.group(2)[0]}= 1;"
        decl = re.match(r"^((?:[\w.?<>\[\],]+\s+)?[A-Za-z_]\w*(?:\.\w+|\[[^\]]*\])*\s*(?:[+\-*/]?=)(?!=|>))\s*(.+);$", code, re.S)
        lhs, rhs = (decl.group(1), decl.group(2)) if decl else ("", code[:-1] if code.endswith(";") else code)
        if lhs:
            self._remember_alias(lhs, rhs)
        if lhs:
            nm = re.match(r"^(?:[\w.?<>\[\],]+\s+)?([A-Za-z_]\w*)", lhs)
            if nm:
                self.taken.add(nm.group(1))
        if lhs and re.fullmatch(r"_\s*=", lhs.strip()) and _PURE_REF.fullmatch(rhs.strip()):
            return []                                  # '_ = Me;' 처럼 값을 버리는 줄은 아무 일도 하지 않는다
        typed = _TYPED_LHS.match(lhs.strip()) if lhs else None
        if typed and _PURE_REF.fullmatch(rhs.strip()):
            return [{"op": "_alias", "args": {"name": typed.group(1), "source": code}}]   # 쓰는 곳이 없으면 decompose 에서 버린다
        # 도우미 메서드 펼치기
        if not lhs:
            inl = self.try_inline(rhs)
            if inl is not None:
                return inl
        v = self.resolve(rhs) if lhs and not re.search(r"\bawait\b", rhs) else None
        if v is not None:
            nm = re.match(r"^(?:[\w.?<>\[\],]+\s+)?([A-Za-z_][\w.]*)\s*([+\-*/]?=)", lhs.strip())
            label = "값 넣기: " + (f"{nm.group(1)} {nm.group(2)}" if nm else lhs.strip())
            slot = self._slot_value("v", rhs, v, "값", self._lhs_type(lhs))
            return [self._call_block(label, [lhs + " ", "v", ";"], [slot])]
        blk = self.call(lhs, rhs)
        if blk or not lhs or not _plain_value(rhs):
            return [blk] if blk else self.raw(code)
        # 기존 '값 넣기' 블록에 원래 식을 그대로 넣는다 (직접 코드 블록 대신)
        nm = re.match(r"^(?:[\w.?<>\[\],]+\s+)?([A-Za-z_][\w.]*)\s*([+\-*/]?=)", lhs.strip())
        label = "값 넣기: " + (f"{nm.group(1)} {nm.group(2)}" if nm else lhs.strip())
        slot = self._slot_value("v", rhs, {"t": "src", "code": one_line(self._expand_aliases(rhs))}, "값", self._lhs_type(lhs))
        return [self._call_block(label, [lhs + " ", "v", ";"], [slot])]

    def _lhs_type(self, lhs):
        m = re.match(r"^\s*(\w+)\s+\w+\s*=", lhs)
        return NUM_TYPES.get(m.group(1)) if m else None

    # ---- 호출 블록 ----
    def chain_parts(self, rhs):
        """'await A.B<T>(x).C(y)' -> 조각 목록 [{name, gen:(a,b), args:(a,b)|None}] 와 await 여부. 아니면 None."""
        i = _skip_ws(rhs, 0)
        aw = False
        m = re.match(r"await\s+", rhs[i:])
        if m:
            aw, i = True, i + m.end()
        segs, n = [], len(rhs)
        while True:
            i = _skip_ws(rhs, i)
            m = _ID.match(rhs, i)
            if not m:
                return None
            seg = {"name": m.group(0), "start": i, "gen": None, "args": None}
            i = m.end()
            if i < n and rhs[i] == "<":
                g = _generic_end(rhs, i)
                if g < 0:
                    return None
                seg["gen"] = (i + 1, g - 1)
                i = g
            j = _skip_ws(rhs, i)
            if j < n and rhs[j] == "(":
                c = _close(rhs, j)
                seg["args"] = (j + 1, c)
                i = c + 1
            while i < n and rhs[i] in "!":
                i += 1
            while i < n and rhs[i] == "[":
                i = _close(rhs, i) + 1
            seg["end"] = i
            segs.append(seg)
            j = _skip_ws(rhs, i)
            if j >= n:
                break
            if rhs.startswith("?.", j):
                i = j + 2
            elif rhs[j] == ".":
                i = j + 1
            else:
                return None
        if not any(s["args"] is not None for s in segs):
            return None
        return segs, aw

    def try_inline(self, rhs):
        if len(self.stack) >= self.max_depth:
            return None
        got = self.chain_parts(rhs)
        if not got:
            return None
        segs, aw = got
        if len(segs) != 1 and not (len(segs) == 2 and segs[0]["name"] in ("this", "base") and segs[0]["args"] is None):
            return None
        seg = segs[-1]
        if seg["args"] is None:
            return None
        base_call = segs[0]["name"] == "base"
        name = seg["name"]
        a_s = rhs[seg["args"][0]:seg["args"][1]]
        arg_spans = split_args(a_s)
        args = [a_s[a:b] for a, b in arg_spans]
        named = {}
        pos = []
        for a in args:
            mm = re.match(r"^(\w+)\s*:(?!:)\s*(.+)$", a, re.S)
            if mm:
                named[mm.group(1)] = mm.group(2).strip()
            else:
                if named:
                    return None
                pos.append(a.strip())
        gen_args = [g.strip() for g in rhs[seg["gen"][0]:seg["gen"][1]].split(",")] if seg["gen"] else []
        # 1) 지금 펼친 메서드 안의 지역 함수
        for frame in reversed(self.stack):
            lf = frame["locals"].get(name)
            if lf and lf["level"] is not None:
                return self._inline(lf["pm"], lf["level"], pos, named, gen_args, aw, local=True)
        if base_call:
            cur = self.stack[-1]["level"] if self.stack else 0
            found = self.chain.find(name, len(pos) + len(named), named, start=cur + 1)
        else:
            found = self.chain.find(name, len(pos) + len(named), named)
        if not found:
            return None
        li, pm = found
        if "static" in pm["mods"] and li > 0 and "private" in pm["mods"]:
            return None
        return self._inline(pm, li, pos, named, gen_args, aw)

    def _inline(self, pm, li, pos, named, gen_args, aw, local=False):
        if any(f["pm"] is pm for f in self.stack):
            return None
        if pm["body"] is None and pm["expr"] is None:
            return None
        if any(p["mod"] in ("ref", "out", "params") for p in pm["params"]):
            return None
        ret = pm["ret"]
        is_async = "async" in pm["mods"]
        if ret not in ("Task", "void") and not (ret == "Task" or ret.startswith("Task ")):
            return None
        if ret == "void" and aw:
            return None
        if ret == "Task" and not aw:
            return None   # 기다리지 않는 Task 호출은 그대로
        body = pm["body"] if pm["body"] is not None else f"{'await ' if ret == 'Task' and not is_async else ''}{pm['expr']};"
        if pm["body"] is not None and ret == "Task" and not is_async:
            # 기다리지 않는 Task 본문: 'return Task.CompletedTask;' 는 조기 반환으로, 마지막 'return X;' 는 'await X;' 로 바꾼다
            body = re.sub(r"return\s+Task\.CompletedTask\s*;", "return;", body)
            try:
                head = parse_stmts(body)
            except (ValueError, IndexError, KeyError):
                return None
            last = head[-1] if head else None
            mm = re.fullmatch(r"return\s+(.+);", last["code"], re.S) if last and last["k"] == "stmt" else None
            if mm:
                body = _src(head[:-1]) + f"\nawait {mm.group(1).strip()};"
            elif not head:
                return None
        if re.search(r"\byield\b", body):
            return None
        level_name, _lvl_body, privates = self.chain.levels[li]
        if li > 0 and not local:
            if "private" in pm["mods"] or not any(m in pm["mods"] for m in ("protected", "public", "internal")):
                return None
            if re.search(r"\bbase\s*\.", body):
                return None
            if {p for p in privates if not p.startswith("set:")} & idents(body):
                return None
            if assigns_any(body, [p[4:] for p in privates if p.startswith("set:")]):
                return None
        # 인수 -> 매개변수
        env, pre = {}, []
        for i, p in enumerate(pm["params"]):
            if i < len(pos):
                val = pos[i]
            elif p["name"] in named:
                val = named[p["name"]]
            elif p["default"] is not None:
                val = p["default"]
            else:
                return None
            env[p["name"]] = val
        gmap = {g: (gen_args[i] if i < len(gen_args) else None) for i, g in enumerate(pm["gen"])}
        if None in gmap.values():
            return None
        stmts = parse_stmts(body)
        stmts = self._guard_returns(stmts)
        if stmts is None:
            return None
        text_all = _src(stmts)
        for p in pm["params"]:
            if re.search(r"(?<![\w.])" + re.escape(p["name"]) + r"\s*(?:[+\-*/%]?=(?![=>])|\+\+|--)", text_all) or \
                    re.search(r"(?:\+\+|--)" + re.escape(p["name"]) + r"\b", text_all):
                return None
        # 지역 이름 충돌 피하기
        declared = self._declared(stmts)
        used_in_args = set()
        for v in env.values():
            used_in_args |= idents(v)
        ren = {}
        for d in declared:
            if d in self.taken or d in used_in_args or d in env:
                k = 2
                while f"{d}{k}" in self.taken or f"{d}{k}" in declared:
                    k += 1
                ren[d] = f"{d}{k}"
        mapping = dict(ren)
        counts = {}
        map_idents(text_all, lambda nm, prev, after: counts.__setitem__(nm, counts.get(nm, 0) + 1) if prev != "." else None)
        for p in pm["params"]:
            v = env[p["name"]].strip()
            ident_like = bool(re.fullmatch(r"[\w.!]+|-?\d+(?:\.\d+)?[mMfFdD]?|\"[^\"]*\"", v))
            atomic = ident_like or (bool(re.fullmatch(r"[\w.]+(?:<[\w.,\s]*>)?\s*\(.*\)", v, re.S))
                                    and _close(v, v.find("(")) == len(v) - 1)
            pure = ident_like or (atomic and self.resolve(v) is not None)
            redecl = re.search(r"(?<![\w.])" + re.escape(p["name"]) + r"\s*=>", text_all) or \
                re.search(r"\([^()]*\b" + re.escape(p["name"]) + r"\s*[,)][^()]*\)\s*=>", text_all) or p["name"] in declared
            if not redecl and (pure or counts.get(p["name"], 0) <= 1):
                mapping[p["name"]] = v if atomic else f"({v})"
            else:
                self.uid += 1
                tmp = f"{p['name']}_{self.uid}"
                pre.append({"k": "stmt", "code": f"var {tmp} = {v};", "src": f"var {tmp} = {v};"})
                mapping[p["name"]] = tmp
                self.taken.add(tmp)
        mapping.update({g: t for g, t in gmap.items()})
        new_stmts = parse_stmts(rename(_src(stmts), mapping))
        self.taken |= {ren.get(d, d) for d in declared}
        # 펼칠 지역 함수 표
        locals_ = {}
        for st in new_stmts:
            if st["k"] == "local_fn":
                lpm = parse_method(st["code"])
                if lpm:
                    locals_[lpm["name"]] = {"pm": lpm, "level": li}
        self.stack.append({"pm": pm, "level": li, "locals": locals_})
        try:
            out = self.blocks(pre + [s for s in new_stmts if s["k"] != "local_fn"])
        finally:
            self.stack.pop()
        # 아직 쓰이는 지역 함수만 남긴다 (펼치지 못한 호출이 남아 있을 때)
        left = _blocks_text(out)
        keep = [st for st in new_stmts if st["k"] == "local_fn" and re.search(r"\b" + re.escape(st.get("name") or "~") + r"\b", left)]
        while True:
            more = [st for st in new_stmts if st["k"] == "local_fn" and st not in keep and
                    any(re.search(r"\b" + re.escape(st.get("name") or "~") + r"\b", k["code"]) for k in keep)]
            if not more:
                break
            keep += more
        self.stats["inlined"] += 1
        if li > 0:
            self.stats.setdefault("levels", set()).add(li)
        return [b for st in keep for b in self.raw(st["src"])] + out

    def _guard_returns(self, stmts):
        """'if (A) return; 나머지' -> 'if (!(A)) { 나머지 }'. 다른 return 이 있으면 None."""
        out = []
        for k, st in enumerate(stmts):
            if st["k"] == "if" and st["else"] is None and len(st["then"]) == 1 and st["then"][0]["k"] == "stmt" and \
                    st["then"][0]["code"] in ("return;", "return Task.CompletedTask;"):
                rest = self._guard_returns(stmts[k + 1:])
                if rest is None:
                    return None
                cond = st["cond"]
                neg = cond[1:].strip() if re.fullmatch(r"!\s*\((.*)\)", cond, re.S) and _close(cond, cond.find("(")) == len(cond) - 1 \
                    else f"!({cond})"
                src = f"if ({neg})\n{{\n" + _src(rest) + "\n}"
                out.append({"k": "if", "cond": neg, "then": rest, "else": None, "src": src})
                return out
            if st["k"] == "stmt" and st["code"] == "return;" and k == len(stmts) - 1:
                return out
            if st["k"] != "local_fn" and re.search(r"\breturn\b", _strip_local_fns(st)):
                return None
            out.append(st)
        return out

    def _declared(self, stmts):
        names = set()
        for st in stmts:
            src = st["src"]
            for m in re.finditer(r"(?:^|[;{(]\s*|\n\s*)([\w.]+(?:<[^<>;()]*>)?\??(?:\[\])?)\s+([a-z_]\w*)\s*(?:=(?![=>])|;|\bin\b)", src):
                if m.group(2) not in KEYWORDS and m.group(1) not in ("return", "await", "throw", "yield", "else", "case",
                                                                      "goto", "new", "in", "is", "as"):
                    names.add(m.group(2))
            for m in re.finditer(r"\b(?:out\s+(?:var|[\w.<>]+)|is\s+[\w.<>]+)\s+([a-z_]\w*)", src):
                names.add(m.group(1))
            for m in re.finditer(r"\(\s*(?:[\w.<>?]+\s+)?([a-z_]\w*)\s*\)\s*=>|\b([a-z_]\w*)\s*=>", src):
                pass   # 람다 매개변수는 가려도 된다
            if st["k"] == "local_fn" and st.get("name"):
                names.add(st["name"])
        return {n for n in names if n not in KEYWORDS}

    def value(self, text):
        v = self.resolve(text)
        return v if v is not None else {"t": "src", "code": one_line(self._expand_aliases(text))}

    def _slot_value(self, key, orig, v, name, typ=None):
        if typ is None:
            if v and v.get("t") == "dynvar":
                typ = {"BaseValue": "decimal", "IntValue": "int", "PreviewValue": "decimal", "": "DynamicVar"}[v["prop"]]
            elif re.search(r"\d[mM]\b|\bBaseValue\b|\(decimal\)", orig):
                typ = "decimal"
            else:
                typ = "int"
        return {"key": key, "name": name, "kind": "value", "orig": one_line(orig), "v0": v, "type": typ}

    def _call_block(self, label, parts, slots):
        args = {s["key"]: copy.deepcopy(s["v0"]) if s["kind"] == "value" else s["orig"] for s in slots}
        self.stats["calls"] += 1
        return {"op": "src_call", "label": label, "parts": parts, "slots": slots, "args": args}

    def _native_value(self, text):
        value = self.resolve(self._expand_aliases(text))
        return value if value is not None else {"t": "src", "code": one_line(self._expand_aliases(text))}

    def _mapped_call(self, signature, segs, rhs, lhs=""):
        """Use a user's exact-call mapping before the built-in API recognizers."""
        # Replacing a call whose return value is consumed would drop that value;
        # keep those as editable call blocks instead.
        if lhs and lhs.strip():
            return None
        if not self.project or not signature:
            return None
        rules = self.project.get("call_mappings", [])
        if not isinstance(rules, list):
            return None
        for rule in reversed(rules):
            if not isinstance(rule, dict) or rule.get("signature") != signature:
                continue
            op = rule.get("op")
            bindings = rule.get("bindings")
            if not isinstance(bindings, dict):
                continue
            try:
                import blockcode as B
                if op not in B.MANUAL_MAP_OPS:
                    continue
                block = B.new_block(op)
                spec_args = B.SPECS[op].get("args", {})
            except (KeyError, TypeError):
                continue
            resolved = {}
            valid = True
            for field, binding in bindings.items():
                if field not in spec_args or not isinstance(binding, dict):
                    valid = False
                    break
                if binding.get("kind") == "fixed":
                    resolved[field] = copy.deepcopy(binding.get("value"))
                    continue
                field_kind = spec_args[field][0]
                if binding.get("kind") != "arg" or field_kind not in ("value", "code"):
                    valid = False
                    break
                try:
                    si, ai = int(binding.get("segment")), int(binding.get("index"))
                    if si < 0 or si >= len(segs) or ai < 0 or segs[si].get("args") is None:
                        raise ValueError
                    a, b = segs[si]["args"]
                    raw = rhs[a:b]
                    spans = split_args(raw)
                    if ai >= len(spans):
                        raise ValueError
                    x, y = spans[ai]
                    text = raw[x:y]
                    named = re.match(r"^\w+\s*:(?!:)\s*", text)
                    if named:
                        text = text[named.end():]
                    text = text.strip()
                    resolved[field] = self._native_value(text) if field_kind == "value" else one_line(text)
                except (ValueError, TypeError, IndexError):
                    valid = False
                    break
            if not valid:
                continue
            block["args"].update(resolved)
            block["mapped_signature"] = signature
            mapped_rule = copy.deepcopy(rule)
            for field, binding in mapped_rule.get("bindings", {}).items():
                if binding.get("kind") == "arg" and field in resolved:
                    binding["initial_value"] = copy.deepcopy(resolved[field])
            block["mapped_rule"] = mapped_rule
            self.stats["calls"] += 1
            return block
        return None

    @staticmethod
    def _expr_key(text):
        return re.sub(r"\s+", "", text or "").replace("global::", "").replace("?.", ".").rstrip("!")

    def _native_who(self, text):
        expr = self._expr_key(self._expand_aliases(text))
        if expr in {"Me", "Owner.Creature", "cardPlay.Owner.Creature", "choiceContext.Player.Creature"}:
            return "self"
        if expr in {"cardPlay.Target", "target", "cardPlay.TargetCreature"}:
            return "target"
        return None

    def _native_context(self, text):
        return self._expr_key(self._expand_aliases(text)) == "choiceContext"

    def _native_player(self, text):
        return self._expr_key(self._expand_aliases(text)) in {"Owner", "choiceContext.Player", "cardPlay.Owner",
                                                              "cardPlay.Card.Owner", "Owner.Player"}

    def _native_card_source(self, text):
        return self._expr_key(self._expand_aliases(text)) in {"this", "(CardModel)this", "cardPlay.Card"}

    def _native_block_amount(self, text):
        expr = self._expand_aliases(text).strip()
        m = re.fullmatch(r"new\s+(?:global::)?BlockVar\s*\((.*)\)", expr, re.S)
        if not m:
            return self._native_value(text), None
        spans = split_args(m.group(1))
        if not spans:
            return None, None
        amount = spans[0]
        prop = self._expr_key(spans[1]) if len(spans) > 1 else None
        if prop and not prop.startswith("ValueProp."):
            mode = self._native_damage_mode(spans[1])
            if isinstance(mode, tuple) and mode[0] == "damage" and not mode[2]:
                prop = "ValueProp.Move" if mode[1] else "ValueProp.Unpowered"
            else:
                return None, None
        return self._native_value(amount), prop

    def _native_damage_mode(self, text):
        """Resolve a DynamicVar.Props expression only when its imported definition states the flags."""
        expr = self._expr_key(self._expand_aliases(text))
        props = expr if expr.startswith("ValueProp.") else ""
        if not props:
            match = re.fullmatch(r"(?:this\.)?DynamicVars(?:\.([A-Za-z_]\w*)|\[\"([A-Za-z_]\w*)\"\])\.Props", expr)
            if not match:
                return None
            var = self.raw_vars.get(match.group(1) or match.group(2))
            code = (var or {}).get("expr", "")
            found = re.findall(r"ValueProp\.\w+", code)
            if not found:
                return None
            props = "|".join(found)
        names = set(props.split("|"))
        if "ValueProp.Unblockable" in names:
            if names <= {"ValueProp.Unblockable", "ValueProp.Unpowered"}:
                return "lose_hp"
            if names <= {"ValueProp.Unblockable", "ValueProp.Unpowered", "ValueProp.Move"}:
                return "damage", "ValueProp.Move" in names, True
            return None
        if names <= {"ValueProp.Move", "ValueProp.Unpowered"} and names:
            return "damage", "ValueProp.Move" in names, False
        if "ValueProp.Unpowered" in names and names <= {"ValueProp.Unpowered"}:
            return "damage", False, False
        return None



    def _class_full(self, name):
        cls = self.classes.get(name)
        if cls is not None:
            return getattr(cls, "full", "") or getattr(cls, "name", "")
        return ""

    def _native_power_type(self, text):
        value = str(text or "").strip().replace("global::", "")
        short = value.rsplit(".", 1)[-1]
        full = self._class_full(short)
        if full:
            return full
        if "." not in value and re.fullmatch(r"[A-Za-z_]\w*", value):
            return "MegaCrit.Sts2.Core.Models.Powers." + value
        return value

    def _power_key_for_type(self, power_type):
        if not self.project or not power_type:
            return None
        import modgen as M
        wanted = self._expr_key(power_type)
        matches = []
        for key, _label in M.power_options(self.project):
            meta = M.power_meta(self.project, key)
            full = self._expr_key((meta or {}).get("cls", "")).removeprefix("global::")
            if full and (full == wanted or full.endswith("." + wanted)):
                matches.append(key)
        return matches[0] if len(matches) == 1 else None

    def _native_call(self, head, segs, rhs, aw, lhs=""):
        """Map well-known effect APIs to this editor's built-in action blocks."""
        if not segs:
            return None
        names = [s["name"] for s in segs]
        # DamageCmd.Attack is a fluent builder rather than a two-part call.
        # Map only the plain card-attack chain; FX/animation/custom modifiers stay intact.
        if aw and not lhs and len(segs) >= 3 and head == "DamageCmd.Attack" and \
                all(n in {"DamageCmd", "Attack", "FromCard", "WithHitCount", "WithHitFx", "Targeting",
                          "TargetingAllOpponents", "TargetingAllOpponentsCompat",
                          "TargetingRandomOpponents", "Execute"} for n in names) and \
                names.count("FromCard") == 1 and names.count("Execute") == 1 and names.count("WithHitFx") <= 1:
            attack = segs[1]
            source = next((s for s in segs if s["name"] == "FromCard"), None)
            execute = next((s for s in segs if s["name"] == "Execute"), None)
            targeting = next((s for s in segs if s["name"] in {
                "Targeting", "TargetingAllOpponents", "TargetingAllOpponentsCompat",
                "TargetingRandomOpponents"}), None)
            hit_fx = next((s for s in segs if s["name"] == "WithHitFx"), None)
            if attack.get("args") and source and source.get("args") and execute and execute.get("args") and targeting and targeting.get("args") and \
                    (hit_fx is None or hit_fx.get("args")):
                aa, ab = attack["args"]
                ea, eb = execute["args"]
                sa, sb = source["args"]
                ta, tb = targeting["args"]
                amount_args = split_args(rhs[aa:ab])
                source_args = split_args(rhs[sa:sb])
                execute_args = split_args(rhs[ea:eb])
                target_args = split_args(rhs[ta:tb])
                hit_count = {"t": "num", "v": 1}
                hit_seg = next((s for s in segs if s["name"] == "WithHitCount"), None)
                if hit_seg:
                    if hit_seg.get("args") is None:
                        return None
                    ha, hb = hit_seg["args"]
                    hs = split_args(rhs[ha:hb])
                    if len(hs) != 1:
                        return None
                    h0, h1 = hs[0]
                    h_expr = self._expand_aliases(rhs[ha + h0:ha + h1]).strip()
                    h_value = _num(h_expr)
                    if h_value is not None:
                        if int(h_value) < 1:
                            return None
                        hit_count = {"t": "num", "v": int(h_value)}
                    else:
                        hit_count = self._native_value(rhs[ha + h0:ha + h1])
                if len(amount_args) == 1 and len(source_args) == 1 and len(execute_args) == 1 and \
                        len(target_args) == 1 and self._native_context(rhs[ea + execute_args[0][0]:ea + execute_args[0][1]]):
                    s0, s1 = source_args[0]
                    if not self._native_card_source(rhs[sa + s0:sa + s1]):
                        return None
                    t0, t1 = target_args[0]
                    target_expr = rhs[ta + t0:ta + t1]
                    target_name = targeting["name"]
                    if target_name in ("TargetingAllOpponents", "TargetingAllOpponentsCompat"):
                        combat = self._expr_key(self._expand_aliases(target_expr))
                        who = "all" if combat in {"CombatState", "this.CombatState", "Me.CombatState"} else None
                    elif target_name == "TargetingRandomOpponents":
                        combat = self._expr_key(self._expand_aliases(target_expr))
                        who = "random" if combat in {"CombatState", "this.CombatState", "Me.CombatState"} else None
                    else:
                        who = self._native_who(target_expr)
                    if who:
                        a0, a1 = amount_args[0]
                        vfx = sfx = ""
                        fx_extra = ""
                        if hit_fx:
                            fa, fb = hit_fx["args"]
                            fx_args = [rhs[fa + x:fa + y].strip() for x, y in split_args(rhs[fa:fb])]
                            if not 1 <= len(fx_args) <= 5:
                                return None
                            vfx = fx_args[0]
                            sfx = fx_args[1] if len(fx_args) == 2 else ""
                            if len(fx_args) > 2:
                                sfx = fx_args[1]
                                fx_extra = ", ".join(fx_args[2:])
                        self.stats["calls"] += 1
                        return {"op": "card_attack", "args": {"who": who,
                                "amount": self._native_value(rhs[aa + a0:aa + a1]),
                                "hits": hit_count, "vfx": vfx, "sfx": sfx, "fx_extra": fx_extra}}










        # Shared card/potion APIs and the source mod's own APIs are promoted to
        # Maker blocks so imported effects remain editable across different mods.
        if not lhs and len(segs) >= 2:
            method = segs[-1]
            method_name = method["name"]
            call_args = []
            if method.get("args") is not None:
                aa, ab = method["args"]
                raw_args = rhs[aa:ab]
                call_args = [raw_args[x:y].strip() for x, y in split_args(raw_args)] if raw_args.strip() else []

            def call_receiver(seg):
                prefix = rhs[:seg["start"]].rstrip()
                null_safe = prefix.endswith("?.")
                if null_safe:
                    prefix = prefix[:-2].rstrip()
                elif prefix.endswith("."):
                    prefix = prefix[:-1].rstrip()
                return prefix, null_safe



            if head.endswith(".EnergyCost.SetThisTurnOrUntilPlayed") and not aw and len(call_args) == 1:
                receiver, _null_safe = call_receiver(method)
                card_expr = receiver.removesuffix(".EnergyCost")
                if card_expr:
                    self.stats["calls"] += 1
                    return {"op": "card_set_cost_until_played", "args": {
                        "card": card_expr, "amount": self._native_value(call_args[0])}}

            if method_name == "SetToFreeThisTurn" and not aw and not call_args:
                receiver, _null_safe = call_receiver(method)
                if receiver:
                    self.stats["calls"] += 1
                    return {"op": "card_free_this_turn", "args": {"card": receiver}}

            if method_name == "InvokeEnergyCostChanged" and not aw and not call_args:
                receiver, _null_safe = call_receiver(method)
                if receiver:
                    self.stats["calls"] += 1
                    return {"op": "card_notify_cost_changed", "args": {"card": receiver}}

            if method_name in ("UpgradeInternal", "FinalizeUpgradeInternal") and not aw and not call_args:
                receiver, _null_safe = call_receiver(method)
                if receiver:
                    self.stats["calls"] += 1
                    op = "card_upgrade_internal" if method_name == "UpgradeInternal" else "card_finalize_upgrade_internal"
                    return {"op": op, "args": {"card": receiver}}






            if head == "Owner.AddPotionInternal" and not aw and len(call_args) == 2:
                self.stats["calls"] += 1
                return {"op": "potion_add_model_at", "args": {
                    "potion": call_args[0], "player": "Owner", "slot": call_args[1]}}











        if len(segs) != 2 or (not aw and head not in ("SfxCmd.Play", "VfxCmd.PlayOnCreature", "CardCmd.Upgrade", "CardCmd.ApplyKeyword",
                                                       "CardCmd.RemoveKeyword", "CardCmd.Preview", "CardCmd.PreviewCardPileAdd",
                                                       "PlayerCmd.EndTurn") and not head.endswith(".AddKeyword")):
            return None
        method = segs[1]
        if method["args"] is None:
            return None
        a, b = method["args"]
        raw = rhs[a:b]
        args = [raw[x:y].strip() for x, y in split_args(raw)] if raw.strip() else []

        def block(op, **values):
            self.stats["calls"] += 1
            return {"op": op, "args": values}

        def target_amount(target_index, amount_index):
            if len(args) <= max(target_index, amount_index):
                return None
            who = self._native_who(args[target_index])
            return (who, self._native_value(args[amount_index])) if who else None

        # Additional common effect commands whose arguments are best edited as
        # Maker fields rather than retained as a raw call string.
        if not lhs and len(segs) == 2 and method.get("args"):
            a, b = method["args"]
            raw = rhs[a:b]
            call_args = [raw[x:y].strip() for x, y in split_args(raw)] if raw.strip() else []
            if not aw and head == "SfxCmd.Play" and len(call_args) in (1, 2):
                self.stats["calls"] += 1
                # 음량을 생략하면 1 로 본다 (게임 기본값이라고 확인하지는 못함)
                volume = self._native_value(call_args[1]) if len(call_args) == 2 else {"t": "num", "v": 1}
                return {"op": "sfx", "args": {"path": call_args[0], "volume": volume}}
            if aw and head == "Cmd.Wait" and len(call_args) == 1:
                self.stats["calls"] += 1
                return {"op": "wait", "args": {"duration": self._native_value(call_args[0])}}
            if aw and head == "Cmd.CustomScaledWait" and len(call_args) == 2:
                self.stats["calls"] += 1
                return {"op": "wait_scaled", "args": {"minimum": call_args[0], "maximum": call_args[1]}}
            if aw and head == "CreatureCmd.TriggerAnim" and len(call_args) == 3:
                self.stats["calls"] += 1
                return {"op": "trigger_creature_anim", "args": {"creature": call_args[0],
                        "animation": call_args[1], "delay": call_args[2]}}
            if not aw and head == "VfxCmd.PlayOnCreature" and len(call_args) == 2:
                self.stats["calls"] += 1
                return {"op": "play_vfx_on_creature", "args": {"creature": call_args[0], "vfx": call_args[1]}}
            if aw and head == "DoomPower.DoomKill" and len(call_args) == 1:
                self.stats["calls"] += 1
                return {"op": "doom_kill", "args": {"creatures": call_args[0]}}
            if aw and head == "CardCmd.Exhaust" and len(call_args) in (2, 3, 4) and self._native_context(call_args[0]):
                flags = call_args[2:]
                if all(x in ("true", "false") for x in flags):
                    flags += ["false"] * (2 - len(flags))
                    self.stats["calls"] += 1
                    return {"op": "card_exhaust", "args": {"card": call_args[1],
                            "played": flags[0] == "true", "triggered": flags[1] == "true"}}
            if not aw and head == "CardCmd.Upgrade" and len(call_args) in (1, 2):
                self.stats["calls"] += 1
                one = re.fullmatch(r"new\s*\[\s*\]\s*\{\s*(\w+)\s*\}", call_args[0])   # CardCmd.Upgrade(new[] { card }) 는 한 장
                return {"op": "card_upgrade", "args": {"card": one.group(1) if one else call_args[0],
                        "style": call_args[1] if len(call_args) == 2 else ""}}
            if not aw and head in ("CardCmd.ApplyKeyword", "CardCmd.RemoveKeyword") and len(call_args) == 2 and \
                    re.fullmatch(r"CardKeyword\.\w+", self._expr_key(call_args[1])):
                self.stats["calls"] += 1
                return {"op": "card_keyword", "args": {"card": call_args[0],
                        "keyword": self._expr_key(call_args[1]).split(".")[-1],
                        "action": "add" if head.endswith("ApplyKeyword") else "remove"}}
            if not aw and head.endswith(".AddKeyword") and len(call_args) == 1:
                self.stats["calls"] += 1
                return {"op": "card_add_keyword_model", "args": {"card": head.rsplit(".", 1)[0],
                        "keyword": call_args[0]}}
            if not aw and head == "CardCmd.Preview" and 1 <= len(call_args) <= 2:
                self.stats["calls"] += 1
                return {"op": "card_preview_cards", "args": {"cards": call_args[0],
                        "scale": call_args[1] if len(call_args) == 2 else ""}}
            if not aw and head == "CardCmd.PreviewCardPileAdd" and 1 <= len(call_args) <= 3:
                self.stats["calls"] += 1
                return {"op": "card_preview", "args": {"cards": call_args[0],
                        "scale": self._native_value(call_args[1]) if len(call_args) >= 2 else {"t": "num", "v": 1},
                        "style": call_args[2] if len(call_args) >= 3 else "CardPreviewStyle.Default"}}
            if not aw and head == "PlayerCmd.EndTurn" and len(call_args) in (1, 2):
                player = call_args[0]
                can_back_out = "false"
                if len(call_args) == 2:
                    named = re.fullmatch(r"canBackOut\s*:\s*(.+)", call_args[1])
                    can_back_out = named.group(1).strip() if named else call_args[1]
                self.stats["calls"] += 1
                return {"op": "end_turn", "args": {"player": player, "can_back_out": can_back_out}}
            if aw and head == "CardCmd.AutoPlay" and len(call_args) >= 3 and len(call_args) <= 6 and self._native_context(call_args[0]):
                auto_type = "AutoPlayType.Default"
                skip_x = skip_visuals = "false"
                if len(call_args) >= 4:
                    auto_type = call_args[3]
                if len(call_args) >= 5:
                    named = re.fullmatch(r"skipXCapture\s*:\s*(.+)", call_args[4])
                    skip_x = named.group(1).strip() if named else call_args[4]
                if len(call_args) >= 6:
                    named = re.fullmatch(r"skipCardPileVisuals\s*:\s*(.+)", call_args[5])
                    skip_visuals = named.group(1).strip() if named else call_args[5]
                self.stats["calls"] += 1
                return {"op": "card_autoplay", "args": {"card": call_args[1], "target": call_args[2],
                        "type": auto_type, "skip_x": skip_x, "skip_visuals": skip_visuals}}
            if aw and head == "CardCmd.Discard" and len(call_args) == 2 and self._native_context(call_args[0]):
                self.stats["calls"] += 1
                return {"op": "card_discard", "args": {"cards": call_args[1]}}
            if aw and head == "CardPileCmd.AddGeneratedCardToCombat" and len(call_args) == 3 and \
                    self._expr_key(call_args[1]).startswith("PileType.") and self._native_player(call_args[2]):
                pile = self._expr_key(call_args[1]).split(".")[-1]
                if pile in {"Hand", "Draw", "Discard"}:
                    self.stats["calls"] += 1
                    return {"op": "card_add_generated", "args": {"card": call_args[0], "pile": pile}}
            if aw and head == "CardPileCmd.Add" and 2 <= len(call_args) <= 5 and \
                    self._expr_key(call_args[1]).startswith("PileType."):
                extra = ", ".join(call_args[2:])
                self.stats["calls"] += 1
                return {"op": "card_add_pile", "args": {"cards": call_args[0], "pile": call_args[1], "extra": extra}}
            if aw and head == "CardPileCmd.AddGeneratedCardsToCombat" and len(call_args) == 4 and \
                    self._expr_key(call_args[1]).startswith("PileType."):
                self.stats["calls"] += 1
                return {"op": "card_add_generated_many", "args": {"cards": call_args[0], "pile": call_args[1],
                        "player": call_args[2], "position": call_args[3]}}
            if aw and head == "CardPileCmd.RemoveFromCombat" and len(call_args) == 1:
                self.stats["calls"] += 1
                return {"op": "card_remove_combat", "args": {"cards": call_args[0]}}
            if aw and head == "CardPileCmd.Shuffle" and len(call_args) == 2 and self._native_context(call_args[0]):
                self.stats["calls"] += 1
                return {"op": "shuffle_draw_pile", "args": {"player": call_args[1]}}
            if aw and head == "CardPileCmd.AutoPlayFromDrawPile" and len(call_args) == 5 and \
                    self._native_context(call_args[0]):
                force_exhaust = call_args[4]
                named_force = re.fullmatch(r"forceExhaust\s*:\s*(.+)", force_exhaust)
                if named_force:
                    force_exhaust = named_force.group(1).strip()
                self.stats["calls"] += 1
                return {"op": "autoplay_draw_pile", "args": {"player": call_args[1],
                        "count": self._native_value(call_args[2]), "position": call_args[3],
                        "force_exhaust": force_exhaust}}
            if aw and head == "CreatureCmd.Stun" and len(call_args) == 1:
                self.stats["calls"] += 1
                return {"op": "stun", "args": {"creature": call_args[0]}}
            if aw and head == "PotionCmd.TryToProcure" and method.get("gen") and len(call_args) == 1:
                ga, gb = method["gen"]
                self.stats["calls"] += 1
                return {"op": "potion_add_type", "args": {"potion_type": rhs[ga:gb].strip(),
                        "player": call_args[0]}}
            if aw and head == "PotionCmd.TryToProcure" and not method.get("gen") and len(call_args) == 2:
                self.stats["calls"] += 1
                return {"op": "potion_add_model", "args": {"potion": call_args[0], "player": call_args[1]}}
            if aw and head == "CardCmd.TransformTo" and method.get("gen") and len(call_args) == 1:
                ga, gb = method["gen"]
                self.stats["calls"] += 1
                return {"op": "card_transform_to", "args": {"card_type": rhs[ga:gb].strip(),
                        "card": call_args[0]}}
            if aw and head == "PowerCmd.ModifyAmount" and len(call_args) == 5 and self._native_context(call_args[0]) and \
                    self._native_who(call_args[3]) == "self" and self._native_card_source(call_args[4]):
                self.stats["calls"] += 1
                return {"op": "modify_power_amount", "args": {"power": call_args[1],
                        "amount": self._native_value(call_args[2])}}
            if aw and head == "CreatureCmd.SetCurrentHp" and len(call_args) == 2:
                self.stats["calls"] += 1
                return {"op": "set_current_hp", "args": {"creature": call_args[0],
                        "amount": self._native_value(call_args[1])}}
            if aw and head == "OrbCmd.AddSlots" and len(call_args) == 2:
                self.stats["calls"] += 1
                return {"op": "orb_slots_to", "args": {"player": call_args[0],
                        "amount": self._native_value(call_args[1])}}
            if aw and head == "OrbCmd.Channel" and method.get("gen") and len(call_args) == 2 and \
                    self._native_context(call_args[0]):
                ga, gb = method["gen"]
                self.stats["calls"] += 1
                return {"op": "orb_channel_type", "args": {"orb_type": rhs[ga:gb].strip(),
                        "player": call_args[1]}}
            if aw and head == "OrbCmd.EvokeNext" and len(call_args) == 2 and \
                    self._native_context(call_args[0]) and self._native_player(call_args[1]):
                self.stats["calls"] += 1
                return {"op": "evoke", "args": {"which": "front", "count": {"t": "num", "v": 1}}}
            if aw and head == "OrbCmd.Passive" and len(call_args) == 3 and self._native_context(call_args[0]):
                self.stats["calls"] += 1
                return {"op": "orb_passive_model", "args": {"orb": call_args[1], "target": call_args[2]}}
            if aw and head == "OrbCmd.Channel" and len(call_args) == 3 and self._native_context(call_args[0]) and \
                    self._native_player(call_args[2]):
                self.stats["calls"] += 1
                return {"op": "orb_channel_model", "args": {"orb": call_args[1]}}
            if aw and head == "PowerCmd.Remove" and len(call_args) == 1:
                self.stats["calls"] += 1
                return {"op": "remove_power_model", "args": {"power": call_args[0]}}
            if aw and head == "PlayerCmd.LoseGold" and len(call_args) == 3:
                self.stats["calls"] += 1
                return {"op": "lose_gold", "args": {"amount": self._native_value(call_args[0]),
                        "player": call_args[1], "loss_type": call_args[2]}}

        if head == "CreatureCmd.GainBlock" and len(args) in (3, 4):
            who = self._native_who(args[0])
            amount, wrapped_prop = self._native_block_amount(args[1])
            prop_expr = next((x for x in args[2:] if self._expr_key(x).startswith("ValueProp.") or
                              self._expr_key(x).endswith(".Props")), "")
            prop = wrapped_prop or ""
            if prop_expr:
                prop_key = self._expr_key(prop_expr)
                prop = prop_key if prop_key.startswith("ValueProp.") else ""
                mode = self._native_damage_mode(prop_expr)
                if not prop and isinstance(mode, tuple) and mode[0] == "damage" and not mode[2]:
                    prop = "ValueProp.Move" if mode[1] else "ValueProp.Unpowered"
            extra = [self._expr_key(x) for x in args[2:]
                     if self._expr_key(x) != (self._expr_key(prop_expr) if prop_expr else "")]
            if wrapped_prop:
                extra = [self._expr_key(x) for x in args[2:]]
            if amount is not None and prop in ("", "ValueProp.Move", "ValueProp.Unpowered") and \
                    all(x in ("choiceContext", "cardPlay", "null", "this") for x in extra):
                if who == "self" and (prop == "ValueProp.Move" or (not prop and len(args) == 3 and extra == ["cardPlay"])):
                    return block("block", amount=amount)
                powered = prop == "ValueProp.Move" or (not prop and "cardPlay" in extra)
                return block("block_to", creature=args[0], amount=amount, powered=powered,
                             card_play="cardPlay" in extra)

        if head == "CreatureCmd.Damage" and len(args) in (5, 6, 7):
            who = self._native_who(args[1])
            amount = self._native_value(args[2])
            mode = self._native_damage_mode(args[3])
            if (mode and isinstance(mode, tuple) and mode[0] == "damage") or mode == "lose_hp":
                if self._native_context(args[0]) and who and len(args) == 7 and self._native_who(args[4]) == "self" and \
                        self._native_card_source(args[5]) and self._expr_key(self._expand_aliases(args[6])) in ("cardPlay", "null") and \
                        not (isinstance(mode, tuple) and mode[2]):
                    if mode == "lose_hp":
                        return block("lose_hp", who=who, amount=amount)
                    return block("damage", who=who, amount=amount, hits=1, powered=mode[1])
                return block("damage_to", creature=args[1], amount=amount,
                             powered=isinstance(mode, tuple) and mode[1],
                             unblockable=mode == "lose_hp" or (isinstance(mode, tuple) and mode[2]),
                             attacker=args[4], source_card=args[5] if len(args) >= 6 else "",
                             card_play=args[6] if len(args) >= 7 else "", context=args[0])

        if head == "CreatureCmd.LoseBlock" and len(args) == 4 and self._native_context(args[0]):
            pair = target_amount(1, 2)
            if pair and self._expr_key(args[3]) in {"this", "Me", "Owner.Creature", "null"}:
                who, amount = pair
                return block("lose_block", who=who, amount=amount)

        if head == "CreatureCmd.LoseBlock" and len(args) == 2:
            return block("lose_block_to", creature=args[0], amount=self._native_value(args[1]))

        if head == "CreatureCmd.Kill" and len(args) == 1:
            return block("kill_creature", creature=args[0])

        if head == "CreatureCmd.Heal" and len(args) == 2:
            pair = target_amount(0, 1)
            if pair:
                who, amount = pair
                return block("heal", who=who, amount=amount)
            return block("heal_to", creature=args[0], amount=self._native_value(args[1]))

        if head in ("CreatureCmd.LoseHp", "CreatureCmd.GainMaxHp") and len(args) == 3 and self._native_context(args[0]):
            pair = target_amount(1, 2)
            if pair:
                who, amount = pair
                if head == "CreatureCmd.LoseHp":
                    return block("lose_hp", who=who, amount=amount)
                if who == "self":
                    return block("max_hp", amount=amount)

        if head == "CreatureCmd.GainMaxHp" and len(args) == 2 and self._native_who(args[0]) == "self":
            return block("max_hp", amount=self._native_value(args[1]))

        if head == "CardPileCmd.Draw" and len(args) == 3 and self._native_context(args[0]):
            if self._native_player(args[2]):
                return block("draw", amount=self._native_value(args[1]))
            return block("draw_to", amount=self._native_value(args[1]), player=args[2])

        if head in ("PlayerCmd.GainEnergy", "PlayerCmd.GainGold", "PlayerCmd.GainStars") and len(args) == 2:
            op = {"PlayerCmd.GainEnergy": "energy", "PlayerCmd.GainGold": "gold",
                  "PlayerCmd.GainStars": "stars"}[head]
            if self._native_player(args[1]):
                return block(op, amount=self._native_value(args[0]))
            if op == "energy":
                return block("energy_to", amount=self._native_value(args[0]), player=args[1])
            if op == "gold":
                return block("gold_to", amount=self._native_value(args[0]), player=args[1])

        if head == "PlayerCmd.AddPet" and len(args) == 2:
            return block("add_pet_model", pet=args[0], player=args[1])

        if head == "PowerCmd.Apply" and method["gen"] and len(args) == 5 and self._native_context(args[0]):
            generic = rhs[method["gen"][0]:method["gen"][1]].strip()
            return block("power_apply_type", creature=args[1], power_type=self._native_power_type(generic),
                         amount=self._native_value(args[2]), applier=args[3], source=args[4])

        if head == "PowerCmd.Apply" and not method["gen"] and len(args) == 6 and self._native_context(args[0]):
            return block("power_apply_model", power=args[1], creature=args[2], amount=self._native_value(args[3]),
                         applier=args[4], source=args[5])

        silent = False
        apply_args = args
        if head == "CommonActions.Apply" and len(args) == 5:
            m = re.fullmatch(r"silent\s*:\s*(true|false)", args[4])
            if m:
                silent = m.group(1) == "true"
                apply_args = args[:4]
        if head == "CommonActions.Apply" and method["gen"] and len(apply_args) == 4 and self._native_context(apply_args[0]):
            generic = rhs[method["gen"][0]:method["gen"][1]].strip()
            power = self._power_key_for_type(generic)
            who = self._native_who(apply_args[1])
            amount = self._native_value(apply_args[3])
            if power and self._native_card_source(apply_args[2]):
                if who:
                    return block("apply_power", who=who, power=power, amount=amount, silent=silent)
                return block("apply_power_to", creature=apply_args[1], power=power, amount=amount, silent=silent)
            return block("apply_power_type", creature=apply_args[1], power_type=self._native_power_type(generic),
                         amount=amount, source=apply_args[2], silent=silent)
        return None

    def call(self, lhs, rhs):
        rhs = _common_rewrite(rhs)   # BaseLib 도우미를 같은 뜻의 게임 호출로 바꾼 뒤 풀이한다
        got = self.chain_parts(rhs)
        if not got:
            return None
        segs, aw = got
        head = ".".join(s["name"] for s in segs[:next(i for i, s in enumerate(segs) if s["args"] is not None) + 1])
        first_call = next(s for s in segs if s["args"] is not None)
        signature = call_signature(segs, rhs, aw)
        native = self._mapped_call(signature, segs, rhs, lhs)
        if native:
            return native
        native = self._native_call(head, segs, rhs, aw, lhs)
        if native:
            return native
        sig = None
        if len(segs) == 1 or (segs[0]["name"] in ("this", "base") and len(segs) == 2):
            ps = first_call["args"]
            a_s = rhs[ps[0]:ps[1]]
            found = self.chain.find(first_call["name"], len(split_args(a_s)))
            for frame in reversed(self.stack):
                lf = frame["locals"].get(first_call["name"])
                if lf:
                    found = (frame["level"], lf["pm"])
                    break
            sig = found[1] if found else None
        local_sig = sig is not None
        recv = segs[0]["name"] if segs[0] is not first_call else ""
        if sig is None and recv and (recv[0].islower() or recv in self.classes):
            ps = first_call["args"]
            sig = self.global_sig(first_call["name"], len(split_args(rhs[ps[0]:ps[1]])))
        cuts = []   # (시작, 끝, slot)
        n_slot = 0
        attack = head.endswith("DamageCmd.Attack")
        has_hits = any(s["name"] == "WithHitCount" for s in segs)
        for si, seg in enumerate(segs):
            if seg["gen"] and seg is first_call:
                g0, g1 = seg["gen"]
                gtxt = rhs[g0:g1].strip()
                if re.fullmatch(r"[\w.]+", gtxt):
                    n_slot += 1
                    cuts.append((g0, g1, {"key": f"s{n_slot}", "name": "종류", "kind": "code", "orig": gtxt,
                                          "options": self._type_options(gtxt)}))
            if seg["name"] in ("Targeting", "TargetingAllOpponents", "TargetingRandomOpponents", "TargetingAllCreatures") and attack:
                a0 = rhs.rfind(".", 0, seg["start"])
                orig = rhs[a0:seg["end"]].strip()
                n_slot += 1
                opts = [(orig, f"원래대로 ({_short(orig)})"), (".Targeting(cardPlay.Target!)", "고른 대상"),
                        (".TargetingAllOpponents(CombatState!)", "모든 적"),
                        (".TargetingRandomOpponents(CombatState!)", "무작위 적")]
                cuts.append((a0, seg["end"], {"key": f"s{n_slot}", "name": "대상", "kind": "choice", "orig": orig,
                                              "options": _uniq(opts)}))
                continue
            if seg["args"] is None:
                continue
            a_s0 = seg["args"][0]
            a_s = rhs[seg["args"][0]:seg["args"][1]]
            spans = split_args(a_s)
            labels = _arg_labels(head if seg is first_call else seg["name"], len(spans))
            for ai, (a, b) in enumerate(spans):
                text = a_s[a:b]
                mm = re.match(r"^(\w+)\s*:(?!:)\s*", text)
                pname = mm.group(1) if mm else None
                if mm:
                    a += mm.end()
                    text = a_s[a:b]
                t = text.strip()
                if t in PLUMBING or re.match(r"^(?:out|ref)\s", t) or "=>" in t or re.match(r"^new\b[^(]*\{", t) or \
                        t.startswith("delegate"):
                    continue
                p = None
                if sig:
                    if pname:
                        p = next((q for q in sig["params"] if q["name"] == pname), None)
                    elif ai < len(sig["params"]):
                        p = sig["params"][ai]
                label = pname or (labels[ai] if ai < len(labels) and labels[ai] else None) or \
                    (_param_label(p["name"]) if p else None)
                v = self.resolve(t)
                ptype = NUM_TYPES.get(p["type"].rstrip("?")) if p else None
                if ptype and not local_sig and v is None and not re.search(r"\d", t):
                    ptype = None    # 모드 전체에서 찾은 서명은 겹칠 수 있어 이름표로만 쓴다
                n_slot += 1
                key = f"s{n_slot}"
                if v is not None or ptype or _looks_numeric(t):
                    slot = self._slot_value(key, t, v if v is not None else {"t": "src", "code": one_line(t)},
                                            label or "수치", ptype)
                    if t.isdigit() and ptype is None and seg["name"] in ("WithHitCount",):
                        slot["type"] = "int"
                else:
                    slot = {"key": key, "name": label or f"인수 {ai + 1}", "kind": "code", "orig": one_line(t),
                            "options": self._code_options(t)}
                slot.update(source_segment=si, source_arg=ai)
                cuts.append((a_s0 + a, a_s0 + b, slot))
            # 기본값이 있어 생략된 인수도 칸으로 (바꿀 때만 이름 붙여 넣는다)
            if seg is first_call and sig and local_sig:
                given = {re.match(r"^(\w+)\s*:", a_s[a:b]).group(1) for a, b in spans if re.match(r"^(\w+)\s*:(?!:)", a_s[a:b])}
                npos = len(spans) - len(given)
                for pi, p in enumerate(sig["params"]):
                    if pi < npos or p["name"] in given or p["default"] is None:
                        continue
                    ptype = NUM_TYPES.get(p["type"].rstrip("?"))
                    if not ptype:
                        continue
                    v = self.resolve(p["default"]) or {"t": "src", "code": p["default"]}
                    n_slot += 1
                    slot = self._slot_value(f"s{n_slot}", "", v, _param_label(p["name"]), ptype)
                    slot.update(absent=True, wrap=(", " if spans else "") + p["name"] + ": {}", v0=v)
                    cuts.append((seg["args"][1], seg["args"][1], slot))
            if attack and seg is first_call and not has_hits:
                n_slot += 1
                slot = self._slot_value(f"s{n_slot}", "", {"t": "num", "v": 1}, "횟수", "int")
                slot.update(absent=True, wrap=".WithHitCount({})")
                cuts.append((seg["end"], seg["end"], slot))
        cuts.sort(key=lambda c: (c[0], c[1]))
        parts, last, slots = [], 0, []
        prefix = lhs + " " if lhs else ""
        for a, b, slot in cuts:
            if a < last:
                continue
            parts.append((prefix if not parts else "") + rhs[last:a])
            parts.append(slot["key"])
            slots.append(slot)
            last = b
        parts.append((prefix if not parts else "") + rhs[last:] + ";")
        label = _call_label(head, sig)
        if lhs:
            nm = re.match(r"^(?:[\w.?<>\[\],]+\s+)?([A-Za-z_][\w.]*)", lhs.strip())
            label += f" → {nm.group(1) if nm else lhs.strip()}"
        parts = [_squash(p) if i % 2 == 0 else p for i, p in enumerate(parts)]
        block = self._call_block(label, parts, slots)
        block["call_signature"] = signature
        return block

    def global_sig(self, name, nargs):
        """다른 클래스의 메서드 (예: b.SupportHeal) 이름이 모드 안에서 하나뿐이면 그 매개변수 이름·형식."""
        key = (name, nargs)
        if key in self._sigs:
            return self._sigs[key]
        found = []
        index = _global_index(self.classes)
        for pm in index.get(name, []):
            req = sum(1 for p in pm["params"] if p["default"] is None)
            if req <= nargs <= len(pm["params"]):
                found.append(pm)
        sigs = {tuple((p["name"], p["type"]) for p in pm["params"]) for pm in found}
        self._sigs[key] = found[0] if len(sigs) == 1 else None
        return self._sigs[key]

    def _type_options(self, orig):
        suffix = re.search(r"(Power|Card|Relic|Potion|Orb)$", orig)
        opts = [orig]
        if suffix:
            opts += sorted(n for n in self.class_names if n.endswith(suffix.group(1)) and n != orig)[:80]
        return opts

    def _code_options(self, orig):
        opts = [one_line(orig)]
        if re.fullmatch(r"[\w.!?]+", orig):
            opts += ["cardPlay.Target!", "Owner.Creature"]
        return _uniq_list(opts)


_INDEX_CACHE = {}


def _global_index(classes):
    key = id(classes)
    hit = _INDEX_CACHE.get(key)
    if hit is not None and hit[0] is classes:
        return hit[1]
    index = {}
    for c in classes.values():
        for pm in parsed_members(c.body):
            index.setdefault(pm["name"], []).append(pm)
    _INDEX_CACHE.clear()
    _INDEX_CACHE[key] = (classes, index)
    return index


_PM_CACHE = {}


def parsed_members(body):
    hit = _PM_CACHE.get(body)
    if hit is None:
        hit = [pm for pm in (parse_method(m) for m in members(body)) if pm]
        if len(_PM_CACHE) > 400:
            _PM_CACHE.clear()
        _PM_CACHE[body] = hit
    return hit


def _strip_local_fns(st):
    return st["src"]


def _blocks_text(blocks):
    out = []
    for b in blocks:
        for v in (b.get("args") or {}).values():
            if isinstance(v, str):
                out.append(v)
            elif isinstance(v, dict):
                out.append(str(v))
        out += [p for i, p in enumerate(b.get("parts") or []) if i % 2 == 0]
        for k in ("body", "else", "third"):
            out.append(_blocks_text(b.get(k) or []))
    return "\n".join(out)


def _squash(text):
    return re.sub(r"\s*\n\s*", "", text) if "\n" in text and '"' not in text else text


def _short(text, n=28):
    t = one_line(text)
    return t if len(t) <= n else t[:n - 1] + "…"


def _uniq(opts):
    seen, out = set(), []
    for code, lab in opts:
        if code not in seen:
            seen.add(code)
            out.append((code, lab))
    return out


def _uniq_list(xs):
    seen, out = set(), []
    for x in xs:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def _looks_numeric(t):
    if re.search(r"\"|=>|\bnew\b", t):
        return False
    if re.search(r"(?:\b[a-z_]\w*|\bMe|\bCreature|\)|\]|!)\s*\??\.(?:Amount|IntValue|BaseValue|Count|CurrentHp|MaxHp|Block|"
                 r"Length)\b|\.(?:IntValue|BaseValue)\b|GetPowerAmount|\bN<", t):
        return True
    return bool(re.fullmatch(r"[\w.()\s+\-*/%]*\d[\w.()\s+\-*/%]*", t)) and bool(re.search(r"[+\-*/%]", t))


API_LABELS = {
    "DamageCmd.Attack": "공격 피해", "CreatureCmd.Damage": "피해 주기", "CreatureCmd.GainBlock": "방어도 얻기",
    "CreatureCmd.LoseBlock": "방어도 잃기", "CreatureCmd.Heal": "체력 회복", "CreatureCmd.LoseHp": "체력 잃기",
    "CreatureCmd.GainMaxHp": "최대 체력 증가", "CreatureCmd.Kill": "죽이기", "CreatureCmd.TriggerAnim": "애니메이션",
    "CardPileCmd.Draw": "카드 뽑기", "CardPileCmd.Add": "카드 더미에 넣기", "CardPileCmd.AddGeneratedCardToCombat": "카드 만들기",
    "PlayerCmd.GainEnergy": "에너지 얻기", "PlayerCmd.GainGold": "골드 얻기", "PlayerCmd.GainStars": "별 얻기",
    "PowerCmd.Apply": "파워 부여", "PowerCmd.ModifyAmount": "파워 수치 바꾸기", "PowerCmd.Remove": "파워 제거",
    "CardCmd.Discard": "카드 버리기", "CardCmd.Exhaust": "카드 소멸", "CardCmd.Upgrade": "카드 강화",
    "CardCmd.ApplyKeyword": "키워드 부여", "CardCmd.RemoveKeyword": "키워드 제거",
    "CardSelectCmd.FromHand": "손패에서 고르기", "CardSelectCmd.FromCombatPile": "카드 더미에서 고르기",
    "CardSelectCmd.FromHandForDiscard": "버릴 카드 고르기", "OrbCmd.Channel": "구체 영창", "OrbCmd.EvokeNext": "구체 발현",
    "SfxCmd.Play": "효과음", "VfxCmd.PlayOnCreature": "이펙트", "Cmd.Wait": "기다리기", "Cmd.CustomScaledWait": "기다리기",
}
NAME_HINTS = [("hit", "피해"), ("attack", "공격"), ("damage", "피해"), ("dmg", "피해"), ("block", "방어도"),
              ("draw", "카드 뽑기"), ("heal", "회복"), ("apply", "파워 부여"), ("add", "더하기·부여"), ("energy", "에너지"),
              ("spend", "소모"), ("discard", "버리기"), ("exhaust", "소멸"), ("summon", "소환"), ("vfx", "이펙트"),
              ("sfx", "효과음"), ("upgrade", "강화"), ("gain", "얻기"), ("lose", "잃기"), ("remove", "제거"),
              ("cleanse", "정화"), ("getpower", "파워 찾기")]
ARG_LABELS = {
    "DamageCmd.Attack": ["피해량"], "WithHitCount": ["횟수"], "CreatureCmd.GainBlock": ["대상", "방어도"],
    "CreatureCmd.Damage": [None, "대상", "피해량"], "CreatureCmd.Heal": ["대상", "회복량"],
    "CreatureCmd.LoseHp": [None, "대상", "잃을 체력"], "CardPileCmd.Draw": [None, "장수", "플레이어"],
    "PlayerCmd.GainEnergy": ["에너지", "플레이어"], "PlayerCmd.GainGold": ["골드", "플레이어"],
    "PowerCmd.Apply": [None, "대상", "수치", "건 쪽", None], "PowerCmd.ModifyAmount": [None, "파워", "바뀔 수치", "건 쪽", None],
}
PARAM_LABELS = {"n": "수치", "amount": "수치", "value": "수치", "hits": "횟수", "times": "횟수", "count": "개수",
                "c": "대상", "t": "대상", "target": "대상", "a": "대상", "creature": "대상", "n2": "수치",
                "dmg": "피해량", "damage": "피해량", "block": "방어도"}


def _param_label(name):
    return PARAM_LABELS.get(name, name)


def _arg_labels(head, n):
    for k, v in ARG_LABELS.items():
        if head == k or head.endswith("." + k) or head.split(".")[-1] == k:
            return v
    return []


def _call_label(head, sig):
    short = ".".join(head.split(".")[-2:])
    for k, v in API_LABELS.items():
        if head.endswith(k):
            return v
    name = head.split(".")[-1]
    low = name.lower()
    for key, ko in NAME_HINTS:
        if key in low:
            return f"{ko} ({short})"
    return short


# ===========================================================================
# 밖에서 쓰는 함수
# ===========================================================================
def onplay_of(body):
    for mem in members(body):
        pm = parse_method(mem)
        if pm and pm["name"] == "OnPlay" and pm["body"] is not None and len(pm["params"]) == 2:
            return pm
    return None


def decompose(card, parents=(), class_names=(), project=None, own_power=None, whole_raw=False):
    """복제 카드 -> (블록 목록, 통계) 또는 (None, 이유).
    parents: [(이름, 본문)] 복제 클래스가 상속하는 원본 부모들 (가까운 것부터)."""
    cl = card.get("clone") or {}
    body = cl.get("body", "")
    pm = onplay_of(body)
    if not pm:
        return None, "원본 카드 클래스에서 OnPlay 메서드를 찾지 못했습니다. DLL 캐시를 다시 읽었는지 확인해 주세요."
    chain = ClassChain(body, list(parents) if cl.get("base") else [])
    d = Decomposer(card, chain, class_names, project=project)
    d.own_power = own_power   # 파워 훅이면 Amount 는 그 파워의 중첩 수치
    d.whole_raw = whole_raw
    names = [p["name"] for p in pm["params"]]
    want = ["choiceContext", "cardPlay"]
    text = pm["body"]
    pre = []
    if names != want:
        used = idents(text)
        if any(w in used for w, nm in zip(want, names) if w != nm):
            pre = [f"var {nm} = {w};" for nm, w in zip(names, want) if nm != w]
        else:
            text = rename(text, {nm: w for nm, w in zip(names, want) if nm != w})
    # No-op selection cards are successful analyses; an empty list is treated as a failed import by editors.
    if not text.strip() or re.fullmatch(r"\s*return\s+(?:System\.Threading\.Tasks\.)?Task\.CompletedTask\s*;\s*", text):
        return [{"op": "no_effect", "args": {}}], d.stats
    d.taken |= set(want) | idents(text)
    try:
        stmts = parse_stmts(text)
        if "async" not in pm["mods"]:
            # 'Task OnPlay(..) { ...; return X; }' -> 블록은 async 안에서 돌므로 마지막 return 을 await 로
            last = stmts[-1] if stmts else None
            m = re.fullmatch(r"return\s+(.+);", last["code"], re.S) if last and last["k"] == "stmt" else None
            if m:
                stmts = stmts[:-1]
                if not re.fullmatch(r"Task\.CompletedTask|Task\.FromResult\(.*\)", m.group(1).strip(), re.S):
                    stmts += parse_stmts(f"await {m.group(1).strip()};")
            if re.search(r"\breturn\b", _src(stmts)):
                return None, "async 가 아닌 OnPlay 의 중간 return 은 풀지 않습니다."
        blocks = d.blocks(stmts)
    except (ValueError, IndexError, KeyError, RecursionError) as exc:
        detail = str(exc).strip() or repr(exc).strip() or type(exc).__name__
        return None, f"원본 코드를 읽지 못했습니다 ({type(exc).__name__}): {detail}"
    blocks = [{"op": "source_step", "args": {"source": p}} for p in pre] + blocks
    return _settle_aliases(blocks), d.stats


def parents_from(classes, cls_name):
    """{짧은 이름: CsClass} 에서 부모 사슬 [(이름, 본문)]."""
    import modimport as MI
    out, seen = [], set()
    cur = classes.get(cls_name)
    while cur is not None and cur.base and cur.base not in seen:
        seen.add(cur.base)
        nxt = classes.get(cur.base)
        if nxt is None:
            break
        out.append((nxt.full, MI.fix_decompiled(nxt.body)))
        cur = nxt
    return out


def decompose_with_classes(card, classes, project=None, own_power=None, whole_raw=False):
    """classes: {짧은 이름: CsClass} (모드 전체)."""
    cl = card.get("clone") or {}
    orig = (cl.get("orig_class") or "").split(".")[-1]
    parents = parents_from(classes, orig)
    if cl.get("base") and parents and parents[0][0] != cl["base"]:
        parents = []
    blocks, info = decompose(card, parents, classes, project, own_power, whole_raw)
    if blocks is not None:
        # 부모 클래스 코드를 펼쳤으면 그 파일의 using 도 필요하다
        by_full = {c.full: c for c in classes.values()}
        extra = []
        for li in sorted(info.pop("levels", set())):
            c = by_full.get(parents[li - 1][0]) if li - 1 < len(parents) else None
            for u in (c.usings if c else []):
                if u not in extra:
                    extra.append(u)
        info["usings"] = extra
    return blocks, info


def merge_usings(card, usings):
    cl = card.get("clone") or {}
    have = cl.setdefault("usings", [])
    for u in usings or []:
        if u not in have:
            have.append(u)


def count_ops(blocks):
    import blockcode as B
    n = {}
    for b in B.walk(blocks):
        n[b["op"]] = n.get(b["op"], 0) + 1
    return n

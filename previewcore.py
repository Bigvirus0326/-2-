"""글 해석 · 값 채우기 · 색 (화면과 무관한 부분). Tk 의 preview.py 에서 옮겼다.

Qt 의 그림(preview_qt.py)과 설명 편집(descriptionqt.py) 이 쓴다."""

import modgen as M
import re


FONT = "Malgun Gothic"

TEXT_COLORS = {
    "gold": "#efc851", "blue": "#87ceeb", "green": "#7fff00", "red": "#ff5555", "orange": "#ffa518",
    "purple": "#ee82ee", "aqua": "#2aebbe", "pink": "#ff78a0",
}

RARITY_COLORS = {"Basic": "#5d5d5d", "Common": "#596370", "Uncommon": "#2f6fa8", "Rare": "#b8862b",
                 "Starter": "#5d5d5d", "Shop": "#3f8f5f"}

TYPE_COLORS = {"Attack": "#7a2e2e", "Skill": "#2e5a7a", "Power": "#7a6a2e"}

def fill_values(project, desc, item, upgraded=False, stacks=3):
    """{변수} 자리를 숫자로 바꾸고 BBCode는 남긴다."""
    values, ups = {"Amount": stacks}, {}
    effect_groups = [(e, "") for e in item.get("effects", [])]
    if item.get("separate_upgrade_effect"):
        effect_groups += [(e, "MakerUp") for e in M.upgrade_effects(item)]
    for e, prefix in effect_groups:
        if e["kind"] == "power":
            pm = M.power_meta(project, e["power"])
            name = pm["var"] if pm else ""
        else:
            name = M.VAR_NAME.get(e["kind"], "")
        if not name:
            continue
        name = prefix + name
        up = int(e.get("upgrade", 0) or 0)
        values[name] = int(e.get("amount", 0) or 0) + (up if upgraded else 0)
        ups[name] = up

    for _, name, amount in M.block_number_vars(item):
        up = amount.get("up") or 0
        values[name] = amount.get("v", 0) + (up if upgraded else 0)
        ups[name] = up

    for v in item.get("raw_vars", []) or []:
        try:
            base = float(v.get("value") or 0)
            up = float(v.get("upgrade") or 0)
        except (TypeError, ValueError):
            continue
        val = base + (up if upgraded else 0)
        values[v["name"]] = int(val) if float(val).is_integer() else round(val, 2)
        ups[v["name"]] = up
    return smart_format(desc or "", values, ups, upgraded)

def _split_top(s, sep="|"):
    out, depth, cur = [], 0, []
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch == sep and depth == 0:
            out.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    out.append("".join(cur))
    return out

def smart_format(s, values, ups, upgraded):
    """게임이 쓰는 SmartFormat 일부: diff/inverseDiff/energyIcons/starIcons/plural/show/cond/choose."""
    out, i, n = [], 0, len(s)
    while i < n:
        ch = s[i]
        if ch != "{":
            out.append(ch)
            i += 1
            continue
        depth, j = 0, i
        while j < n:
            if s[j] == "{":
                depth += 1
            elif s[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append(_placeholder(s[i + 1:j], values, ups, upgraded))
        i = j + 1
    return "".join(out)

def _placeholder(inner, values, ups, upgraded):
    name, _, rest = inner.partition(":")
    name = name.strip()
    fmt = lambda t: smart_format(t, values, ups, upgraded)  # noqa: E731
    if name == "IfUpgraded":
        mm = re.match(r"show:(.*)$", rest, re.S)
        if mm:
            parts = _split_top(mm.group(1))
            return fmt(parts[0] if upgraded else (parts[1] if len(parts) > 1 else ""))
    if name in ("singleStarIcon",):
        return "\u2605"
    if name == "energyPrefix":
        mm = re.search(r"energyIcons\((\d+)\)", rest)
        return f"[energy]{mm.group(1) if mm else 1}[/energy]"
    if name in ("InCombat", "IsTargeting", "OnTable", "OnPlayer", "IsMultiplayer"):
        parts = _split_top(rest)
        return fmt(parts[-1]) if len(parts) > 1 else ""
    v = values.get(name)
    if not rest:
        return "?" if v is None else str(v)
    if v is None:
        v_num = None
    else:
        v_num = v
    if rest.startswith("plural:"):
        parts = _split_top(rest[len("plural:"):])
        return fmt(parts[0] if v_num == 1 or len(parts) == 1 else parts[1])
    if rest.startswith("cond:"):
        body = rest[len("cond:"):]
        mm = re.match(r"([<>=!]=?)\s*(-?\d+(?:\.\d+)?)\?(.*)$", body, re.S)
        if mm:
            op, num, branches = mm.group(1), float(mm.group(2)), _split_top(mm.group(3))
            x = float(v_num or 0)
            ok = {">": x > num, "<": x < num, ">=": x >= num, "<=": x <= num, "=": x == num, "==": x == num,
                  "!=": x != num}.get(op, False)
            return fmt(branches[0] if ok else (branches[1] if len(branches) > 1 else ""))
        parts = _split_top(body)
        return fmt(parts[0] if v_num else (parts[1] if len(parts) > 1 else ""))
    if rest.startswith("choose("):
        mm = re.match(r"choose\(([^)]*)\):(.*)$", rest, re.S)
        if mm:
            opts = mm.group(1).split("|")
            parts = _split_top(mm.group(2))
            key = str(int(v_num)) if isinstance(v_num, (int, float)) and float(v_num).is_integer() else str(v_num)
            idx = opts.index(key) if key in opts else len(parts) - 1
            return fmt(parts[min(idx, len(parts) - 1)])
    if v is None:
        return "?"
    if "energyIcons" in rest:
        return f"[energy]{v}[/energy]"
    if "starIcons" in rest:
        return "\u2605" * int(v_num or 0)
    if "percent" in rest:
        return str(int(round(abs((float(v) - 1) * 100))))
    if upgraded and ups.get(name) and "diff" in rest.lower():
        return f"[green]{v}[/green]"
    return str(v)

_TAG_RE = re.compile(r"\[(/?)([a-z_]+)(?:[= ][^\]]*)?\]")

def parse_bbcode(s):
    """-> [(text, style)] ; style = dict(color, bold, italic, energy)"""
    runs = []
    stack = []
    pos = 0
    for m in _TAG_RE.finditer(s):
        if m.start() > pos:
            runs.append((s[pos:m.start()], _style(stack)))
        closing, tag = m.group(1) == "/", m.group(2)
        if closing:
            for i in range(len(stack) - 1, -1, -1):
                if stack[i].split("=", 1)[0] == tag:
                    del stack[i]
                    break
        else:
            if tag == "color":
                color = re.search(r"=\s*(#[a-fA-F0-9]{6})\]$", m.group(0))
                stack.append("color=" + color[1] if color else tag)
            else:
                stack.append(tag)
        pos = m.end()
    if pos < len(s):
        runs.append((s[pos:], _style(stack)))
    return runs

def _style(stack):
    st = {"color": None, "bold": False, "italic": False, "energy": False}
    for t in stack:
        if t.startswith("color="):
            st["color"] = t.split("=", 1)[1]
        elif t in TEXT_COLORS:
            st["color"] = TEXT_COLORS[t]
            if t == "gold":
                st["bold"] = True
        elif t == "b":
            st["bold"] = True
        elif t == "i":
            st["italic"] = True
        elif t == "energy":
            st["energy"] = True
    return st

def _shade(hexcol, k):
    h = (hexcol or "#888888").lstrip("#")
    if len(h) != 6:
        h = "888888"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * k))) for c in (r, g, b))

KW_TEXT = M.KEYWORD_NAMES

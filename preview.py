"""
카드 / 유물 / 물약 / 파워 미리보기 그리기 (tkinter Canvas).

게임 화면을 그대로 흉내 내지는 않고, 정보 확인용으로 비슷한 배치의 자체 디자인을 그린다.
Pillow가 있으면 고품질 축소·모양 자르기를 쓰고, 없으면 tk.PhotoImage로 단순 표시한다.
"""
from __future__ import annotations

import math
import os
import re
import tkinter as tk
import tkinter.font as tkfont

import modgen as M

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
    HAS_PIL = True
except Exception:  # noqa: BLE001
    HAS_PIL = False

FONT = "Malgun Gothic"
TEXT_COLORS = {
    "gold": "#efc851", "blue": "#87ceeb", "green": "#7fff00", "red": "#ff5555", "orange": "#ffa518",
    "purple": "#ee82ee", "aqua": "#2aebbe", "pink": "#ff78a0",
}
RARITY_COLORS = {"Basic": "#5d5d5d", "Common": "#596370", "Uncommon": "#2f6fa8", "Rare": "#b8862b",
                 "Starter": "#5d5d5d", "Shop": "#3f8f5f"}
TYPE_COLORS = {"Attack": "#7a2e2e", "Skill": "#2e5a7a", "Power": "#7a6a2e"}


# ---------------------------------------------------------------------------
# 이미지
# ---------------------------------------------------------------------------
class ImageCache:
    def __init__(self, limit=400):
        self.cache = {}
        self.limit = limit

    def info(self, path):
        """(가로, 세로) 또는 None"""
        if not path or not os.path.isfile(path):
            return None
        try:
            if HAS_PIL:
                with Image.open(path) as im:
                    return im.size
            img = tk.PhotoImage(file=path)
            return img.width(), img.height()
        except Exception:  # noqa: BLE001
            return None

    def get(self, path, w, h, mode="contain", mask=None):
        """mode: contain(전체 보이게) / cover(꽉 채우고 자르기). mask: None / round / ellipse / circle"""
        if not path or not os.path.isfile(path):
            return None
        w, h = max(1, int(w)), max(1, int(h))
        key = (path, os.path.getmtime(path), w, h, mode, mask)
        if key in self.cache:
            return self.cache[key]
        try:
            img = self._load_pil(path, w, h, mode, mask) if HAS_PIL else self._load_tk(path, w, h)
        except Exception:  # noqa: BLE001
            img = None
        if len(self.cache) > self.limit:
            self.cache.clear()
        self.cache[key] = img
        return img

    @staticmethod
    def _load_pil(path, w, h, mode, mask):
        im = Image.open(path).convert("RGBA")
        if mode == "cover":
            im = ImageOps.fit(im, (w, h), Image.LANCZOS)
        else:
            im.thumbnail((w, h), Image.LANCZOS)
        if mask:
            m = Image.new("L", im.size, 0)
            d = ImageDraw.Draw(m)
            box = (0, 0, im.size[0] - 1, im.size[1] - 1)
            if mask == "round":
                d.rounded_rectangle(box, radius=max(4, min(im.size) // 8), fill=255)
            else:
                d.ellipse(box, fill=255)
            alpha = Image.composite(im.getchannel("A"), Image.new("L", im.size, 0), m)
            im.putalpha(alpha)
        return ImageTk.PhotoImage(im)

    def placeholder(self, w, h, mask, color):
        """그림이 없을 때 쓰는 줄무늬 임시 그림 (Pillow 필요, 없으면 None)."""
        if not HAS_PIL:
            return None
        w, h = max(1, int(w)), max(1, int(h))
        key = ("__ph__", w, h, mask, color)
        if key in self.cache:
            return self.cache[key]
        im = Image.new("RGBA", (w, h), color)
        d = ImageDraw.Draw(im)
        step = max(8, w // 12)
        stripe = _shade(color, 1.18)
        for i in range(-h, w + h, step):
            d.line([(i, h), (i + h, 0)], fill=stripe, width=max(2, step // 4))
        if mask:
            m = Image.new("L", (w, h), 0)
            md = ImageDraw.Draw(m)
            if mask == "round":
                md.rounded_rectangle((0, 0, w - 1, h - 1), radius=max(4, min(w, h) // 8), fill=255)
            else:
                md.ellipse((0, 0, w - 1, h - 1), fill=255)
            im.putalpha(m)
        img = ImageTk.PhotoImage(im)
        self.cache[key] = img
        return img

    @staticmethod
    def _load_tk(path, w, h):
        src = tk.PhotoImage(file=path)
        f = max(1, math.ceil(max(src.width() / w, src.height() / h)))
        if f == 1:
            return src
        return src.subsample(f, f)


IMAGES = ImageCache()


# ---------------------------------------------------------------------------
# 설명문 → 서식 있는 글자
# ---------------------------------------------------------------------------
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


_FONTS = {}


def _font(size, bold=False, italic=False):
    """size: 96 DPI 기준 포인트. 화면 DPI와 상관없이 캔버스 좌표와 맞도록 픽셀 크기로 만든다."""
    key = (size, bold, italic)
    if key not in _FONTS:
        _FONTS[key] = tkfont.Font(family=FONT, size=-max(7, round(size * 4 / 3)), weight="bold" if bold else "normal",
                                  slant="italic" if italic else "roman")
    return _FONTS[key]


def draw_rich(canvas, cx, top, width, s, size=10, color="#f2ead8", align="center", tags=(), line_gap=4,
              measure_only=False):
    """서식 있는 글자를 줄바꿈해서 그린다. 그린 높이를 돌려준다."""
    pieces = []  # (text, style) 단어 단위, "\n" 은 줄바꿈
    for text, st in parse_bbcode(s):
        if st["energy"]:
            try:
                n = int(text)
            except ValueError:
                n = 1
            pieces.append(("◆" * max(1, min(n, 9)), dict(st, color="#ffa64d", bold=True)))
            continue
        for tok in re.findall(r"\n| +|[\u3400-\u9fff]|[^ \n\u3400-\u9fff]+", text):
            pieces.append((tok, st))
    lines, cur, cur_w = [], [], 0
    for tok, st in pieces:
        if tok == "\n":
            lines.append((cur, cur_w))
            cur, cur_w = [], 0
            continue
        f = _font(size, st["bold"], st["italic"])
        w = f.measure(tok)
        if tok.strip() == "" and not cur:
            continue
        if cur_w + w > width and cur and tok.strip():
            # 끝 공백 제거
            while cur and cur[-1][0].strip() == "":
                cur_w -= cur[-1][2]
                cur.pop()
            lines.append((cur, cur_w))
            cur, cur_w = [], 0
        if w > width and tok.strip():  # 너무 긴 단어는 글자 단위로
            for ch in tok:
                cw = f.measure(ch)
                if cur_w + cw > width and cur:
                    lines.append((cur, cur_w))
                    cur, cur_w = [], 0
                cur.append((ch, st, cw))
                cur_w += cw
            continue
        cur.append((tok, st, w))
        cur_w += w
    if cur:
        lines.append((cur, cur_w))
    lh = _font(size).metrics("linespace") + line_gap
    if measure_only:
        return lh * len(lines)
    y = top
    for line, lw in lines:
        if align == "center":
            x = cx - lw / 2
        else:
            x = cx - width / 2
        for tok, st, w in line:
            canvas.create_text(x, y, text=tok, anchor="nw", fill=st["color"] or color,
                               font=_font(size, st["bold"], st["italic"]), tags=tags)
            x += w
        y += lh
    return lh * len(lines)


def rounded_rect(canvas, x1, y1, x2, y2, r, **kw):
    pts = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
           x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
    return canvas.create_polygon(pts, smooth=True, **kw)


def _shade(hexcol, k):
    h = (hexcol or "#888888").lstrip("#")
    if len(h) != 6:
        h = "888888"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * k))) for c in (r, g, b))


# ---------------------------------------------------------------------------
# 카드
# ---------------------------------------------------------------------------
CARD_W, CARD_H = 300, 420
KW_TEXT = M.KEYWORD_NAMES


def render_card(canvas, project, card, x=0, y=0, s=1.0, lang="ko", upgraded=False, tags=()):
    S = lambda v: v * s  # noqa: E731
    ch = project["character"]
    border = ch["color"] if ch.get("enabled") else "#8a8a8a"
    if not M.HEX_RE.match(border or ""):
        border = "#8a8a8a"
    border = "#" + border.lstrip("#")
    ctype = card.get("type", "Attack")
    # 바탕
    rounded_rect(canvas, x + S(6), y + S(6), x + S(294), y + S(414), S(22), fill=_shade(border, 0.35),
                 outline=border, width=max(2, S(5)), tags=tags)
    rounded_rect(canvas, x + S(18), y + S(18), x + S(282), y + S(402), S(16),
                 fill=_shade(TYPE_COLORS.get(ctype, "#444"), 0.55), outline="", tags=tags)
    # 그림
    ax1, ay1, ax2, ay2 = x + S(30), y + S(70), x + S(270), y + S(253)
    mask = {"Attack": None, "Skill": "round", "Power": "ellipse"}.get(ctype)
    img = IMAGES.get(card.get("image"), ax2 - ax1, ay2 - ay1, "cover", mask)
    if img:
        canvas.create_image(ax1, ay1, image=img, anchor="nw", tags=tags)
    else:
        ph = IMAGES.placeholder(ax2 - ax1, ay2 - ay1, mask, "#3a3f4a")
        if ph:
            canvas.create_image(ax1, ay1, image=ph, anchor="nw", tags=tags)
        elif ctype == "Power":
            canvas.create_oval(ax1, ay1, ax2, ay2, fill="#3a3f4a", outline="", tags=tags)
        else:
            rounded_rect(canvas, ax1, ay1, ax2, ay2, S(14) if ctype == "Skill" else S(2), fill="#3a3f4a",
                         outline="", tags=tags)
        canvas.create_text((ax1 + ax2) / 2, (ay1 + ay2) / 2, text="그림 없음" if lang == "ko" else "No Art",
                           fill="#8f97a6", font=_font(max(7, int(S(12))), True), tags=tags)
    # 이름 띠
    rarity = card.get("rarity", "Common")
    rounded_rect(canvas, x + S(36), y + S(26), x + S(264), y + S(62), S(10), fill=RARITY_COLORS.get(rarity, "#555"),
                 outline=_shade(RARITY_COLORS.get(rarity, "#555"), 1.4), width=max(1, S(2)), tags=tags)
    name = M.text(card, "name", lang) + ("+" if upgraded else "")
    canvas.create_text(x + S(150), y + S(44), text=name, fill="#7fff00" if upgraded else "#ffffff",
                       font=_font(max(7, int(S(14))), True), tags=tags)
    # 종류
    tlabel = M.label_of(M.CARD_TYPES, ctype) if lang == "ko" else ctype
    import cardkind
    custom_kind = cardkind.definition(project, card)
    if lang == "zh":
        tlabel = {"Attack": "攻击", "Skill": "技能", "Power": "能力", "Curse": "诅咒", "Status": "状态", "Quest": "任务"}.get(ctype, ctype)
    if custom_kind:
        tlabel = M.text(custom_kind, "name", lang)
    rounded_rect(canvas, x + S(112), y + S(246), x + S(188), y + S(270), S(10), fill="#1b1b22", outline=border,
                 width=1, tags=tags)
    canvas.create_text(x + S(150), y + S(258), text=tlabel, fill="#d9d2c0", font=_font(max(6, int(S(9)))), tags=tags)
    # 설명
    px1, py1, px2, py2 = x + S(28), y + S(278), x + S(272), y + S(394)
    rounded_rect(canvas, px1, py1, px2, py2, S(10), fill="#17171d", outline="", tags=tags)
    kws = M.card_keywords(card, upgraded)
    before = [f"[gold]{KW_TEXT[lang][k]}[/gold]." for k in M.KEYWORDS_BEFORE if k in kws]
    after = [f"[gold]{KW_TEXT[lang][k]}[/gold]." for k in M.KEYWORDS_AFTER if k in kws]
    body = fill_values(project, M.description(project, card, "card", lang), card, upgraded)
    full = "\n".join(before + [body] + after)
    size = max(6, int(S(10.5)))
    width = px2 - px1 - S(16)
    hgt = draw_rich(canvas, 0, 0, width, full, size, measure_only=True)
    while hgt > (py2 - py1 - S(8)) and size > 6:
        size -= 1
        hgt = draw_rich(canvas, 0, 0, width, full, size, measure_only=True)
    draw_rich(canvas, (px1 + px2) / 2, py1 + max(S(4), (py2 - py1 - hgt) / 2), width, full, size, tags=tags)
    # 비용
    if card.get("no_cost"):
        return CARD_W * s, CARD_H * s
    cost = "X" if card.get("x_cost") else int(card.get("upgrade_cost" if upgraded else "cost", 0) or 0)
    ox, oy, r = x + S(32), y + S(34), S(24)
    canvas.create_oval(ox - r - S(3), oy - r - S(3), ox + r + S(3), oy + r + S(3), fill="#111", outline="", tags=tags)
    canvas.create_oval(ox - r, oy - r, ox + r, oy + r, fill=border, outline=_shade(border, 1.5),
                       width=max(1, S(2)), tags=tags)
    changed = upgraded and not card.get("x_cost") and int(card.get("upgrade_cost", 0)) != int(card.get("cost", 0))
    canvas.create_text(ox, oy, text=str(cost), fill="#7fff00" if changed else "#ffffff",
                       font=_font(max(8, int(S(18))), True), tags=tags)
    return CARD_W * s, CARD_H * s


# ---------------------------------------------------------------------------
# 유물 / 물약 / 파워
# ---------------------------------------------------------------------------
PANEL_W = 300


def _panel(canvas, x, y, s, h, accent, tags):
    rounded_rect(canvas, x + 6 * s, y + 6 * s, x + 294 * s, y + h - 6 * s, 18 * s, fill="#1d1f27",
                 outline=accent, width=max(2, 3 * s), tags=tags)


def render_relic(canvas, project, relic, x=0, y=0, s=1.0, lang="ko", tags=()):
    S = lambda v: v * s  # noqa: E731
    acc = RARITY_COLORS.get(relic.get("rarity"), "#888")
    h = S(400)
    _panel(canvas, x, y, s, h, acc, tags)
    cx = x + S(150)
    canvas.create_oval(cx - S(78), y + S(22), cx + S(78), y + S(178), fill="#262a35", outline="", tags=tags)
    img = IMAGES.get(relic.get("image"), S(128), S(128), "contain")
    if img:
        canvas.create_image(cx, y + S(100), image=img, tags=tags)
    else:
        canvas.create_oval(cx - S(46), y + S(54), cx + S(46), y + S(146), fill="#c9a227", outline="#7a6116",
                           width=max(1, S(4)), tags=tags)
        canvas.create_text(cx, y + S(100), text="?", fill="#5a4410", font=_font(max(8, int(S(30))), True), tags=tags)
    canvas.create_text(cx, y + S(198), text=M.text(relic, "name", lang), fill="#efc851",
                       font=_font(max(7, int(S(14))), True), tags=tags)
    rl = M.label_of(M.RELIC_RARITIES, relic.get("rarity")) if lang == "ko" else relic.get("rarity")
    canvas.create_text(cx, y + S(220), text=f"{rl} {'유물' if lang == 'ko' else 'Relic'}", fill=acc,
                       font=_font(max(6, int(S(9)))), tags=tags)
    desc = fill_values(project, M.description(project, relic, "relic", lang), relic)
    used = draw_rich(canvas, cx, y + S(240), S(250), desc, max(6, int(S(10.5))), tags=tags)
    flav = M.text(relic, "flavor", lang)
    if flav:
        draw_rich(canvas, cx, y + S(250) + used, S(250), f"[i]{flav}[/i]", max(6, int(S(9))), color="#8f8a7d",
                  tags=tags)
    return PANEL_W * s, h


def render_potion(canvas, project, potion, x=0, y=0, s=1.0, lang="ko", tags=()):
    S = lambda v: v * s  # noqa: E731
    acc = RARITY_COLORS.get(potion.get("rarity"), "#888")
    h = S(400)
    _panel(canvas, x, y, s, h, acc, tags)
    cx = x + S(150)
    img = IMAGES.get(potion.get("image"), S(150), S(150), "contain")
    if img:
        canvas.create_image(cx, y + S(100), image=img, tags=tags)
    else:
        canvas.create_oval(cx - S(48), y + S(78), cx + S(48), y + S(174), fill="#4aa3df", outline="#2a5f85",
                           width=max(1, S(4)), tags=tags)
        canvas.create_rectangle(cx - S(14), y + S(40), cx + S(14), y + S(84), fill="#4aa3df", outline="#2a5f85",
                                width=max(1, S(4)), tags=tags)
        canvas.create_rectangle(cx - S(18), y + S(30), cx + S(18), y + S(44), fill="#8a6a4a", outline="", tags=tags)
    canvas.create_text(cx, y + S(198), text=M.text(potion, "name", lang), fill="#ffffff",
                       font=_font(max(7, int(S(14))), True), tags=tags)
    rl = M.label_of(M.POTION_RARITIES, potion.get("rarity")) if lang == "ko" else potion.get("rarity")
    tg = M.label_of(M.POTION_TARGETS, potion.get("target")) if lang == "ko" else potion.get("target")
    canvas.create_text(cx, y + S(220), text=f"{rl} · {'대상' if lang == 'ko' else 'Target'}: {tg}", fill=acc,
                       font=_font(max(6, int(S(9)))), tags=tags)
    desc = fill_values(project, M.description(project, potion, "potion", lang), potion)
    draw_rich(canvas, cx, y + S(240), S(250), desc, max(6, int(S(10.5))), tags=tags)
    return PANEL_W * s, h


def render_power(canvas, project, power, x=0, y=0, s=1.0, lang="ko", stacks=3, tags=()):
    S = lambda v: v * s  # noqa: E731
    buff = power.get("type") == "Buff"
    acc = "#5fbf5f" if buff else "#b45fd4"
    h = S(400)
    _panel(canvas, x, y, s, h, acc, tags)
    cx = x + S(150)
    # 큰 아이콘
    img = IMAGES.get(power.get("image"), S(128), S(128), "contain")
    if img:
        canvas.create_image(cx, y + S(92), image=img, tags=tags)
    else:
        canvas.create_oval(cx - S(52), y + S(40), cx + S(52), y + S(144), fill="#4caf50" if buff else "#8e44ad",
                           outline=_shade(acc, 0.6), width=max(1, S(4)), tags=tags)
        canvas.create_text(cx, y + S(92), text=(M.text(power, "name", lang) or "?")[:1], fill="#ffffff",
                           font=_font(max(8, int(S(34))), True), tags=tags)
    if power.get("stack") == "Counter":
        bx, by = cx + S(46), y + S(136)
        canvas.create_oval(bx - S(16), by - S(16), bx + S(16), by + S(16), fill="#111", outline=acc, width=2,
                           tags=tags)
        canvas.create_text(bx, by, text=str(stacks), fill="#ffffff", font=_font(max(7, int(S(12))), True), tags=tags)
    canvas.create_text(cx, y + S(176), text=M.text(power, "name", lang), fill=acc,
                       font=_font(max(7, int(S(14))), True), tags=tags)
    kind = M.label_of(M.POWER_TYPES, power.get("type")) if lang == "ko" else power.get("type")
    stk = ("중첩" if power.get("stack") == "Counter" else "단일") if lang == "ko" else power.get("stack")
    canvas.create_text(cx, y + S(198), text=f"{kind} · {stk}", fill="#9a9a9a", font=_font(max(6, int(S(9)))),
                       tags=tags)
    desc = fill_values(project, M.description(project, power, "power", lang), power, stacks=stacks)
    draw_rich(canvas, cx, y + S(218), S(250), desc, max(6, int(S(10.5))), tags=tags)
    return PANEL_W * s, h


def render_item(canvas, project, kind, item, x=0, y=0, s=1.0, lang="ko", upgraded=False, stacks=3, tags=()):
    if kind == "card":
        return render_card(canvas, project, item, x, y, s, lang, upgraded, tags)
    if kind == "relic":
        return render_relic(canvas, project, item, x, y, s, lang, tags)
    if kind == "potion":
        return render_potion(canvas, project, item, x, y, s, lang, tags)
    return render_power(canvas, project, item, x, y, s, lang, stacks, tags)


# ---------------------------------------------------------------------------
# 캐릭터
# ---------------------------------------------------------------------------
def render_character(canvas, project, x=0, y=0, lang="ko", s=1.0):
    S = lambda v: v * s  # noqa: E731
    ch = project["character"]
    color = ch.get("color", "#888888")
    if not M.HEX_RE.match(color or ""):
        color = "#888888"
    color = "#" + color.lstrip("#")
    rounded_rect(canvas, x + S(6), y + S(6), x + S(294), y + S(554), S(18), fill="#1d1f27", outline=color,
                 width=max(2, S(3)))
    cx = x + S(150)
    if not ch.get("enabled"):
        canvas.create_text(cx, y + S(200), text="새 캐릭터를 만들지 않습니다\n(콘텐츠 모드)", fill="#aaa",
                           font=_font(S(11), True), justify="center")
        return
    canvas.create_text(cx, y + S(24), text="캐릭터 선택 화면" if lang == "ko" else "Character Select", fill="#888",
                       font=_font(S(9)))
    # 선택 초상화 (132x195 비율)
    w, h = S(160), S(236)
    top = y + S(42)
    img = IMAGES.get(ch.get("select_image"), w, h, "cover", "round")
    if img:
        canvas.create_image(cx, top, image=img, anchor="n")
    else:
        rounded_rect(canvas, cx - w / 2, top, cx + w / 2, top + h, S(14), fill=_shade(color, 0.45), outline=color,
                     width=2)
        ph = M.label_of(M.PLACEHOLDER_CHARS, ch.get("placeholder"))
        canvas.create_text(cx, top + h / 2, text=f"초상화 없음\n(임시 외형:\n{ph})", fill="#ddd",
                           font=_font(S(10)), justify="center")
    yy = top + h + S(14)
    canvas.create_text(cx, yy, text=M.text(ch, "name", lang), fill=color, font=_font(S(16), True), anchor="n")
    yy += _font(S(16), True).metrics("linespace") + S(4)
    canvas.create_text(cx, yy, text=f"♥ {ch.get('hp')}", fill="#ff7070", font=_font(S(11), True), anchor="n")
    yy += _font(S(11), True).metrics("linespace") + S(6)
    icons_top = y + S(462)
    desc = M.character_description(ch, lang)
    size = 10
    while size > 7 and yy + draw_rich(canvas, 0, 0, S(250), desc, S(size), measure_only=True) > icons_top - S(8):
        size -= 1
    draw_rich(canvas, cx, yy, S(250), desc, S(size), color="#d9d2c0")
    # 작은 그림들
    for i, (field, label) in enumerate((("icon_image", "아이콘"), ("map_marker_image", "지도 표시"),
                                        ("select_locked_image", "잠김"))):
        bx = x + S(60) + i * S(90)
        by = icons_top + S(32)
        src = ch.get(field) or (ch.get("select_image") if field == "select_locked_image" else "")
        im = IMAGES.get(src, S(56), S(56), "contain")
        canvas.create_rectangle(bx - S(32), by - S(32), bx + S(32), by + S(32), fill="#262a35", outline="#3a3f4a")
        if im:
            canvas.create_image(bx, by, image=im)
        else:
            canvas.create_text(bx, by, text="기본", fill="#777", font=_font(S(9)))
        canvas.create_text(bx, by + S(44), text=label, fill="#999", font=_font(S(8)))

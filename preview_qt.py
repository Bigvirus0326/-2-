"""미리보기 그리기의 Qt(QPainter) 版. preview.py 의 Tk 그리기와 같은 배치를 따른다.

공용으로 쓰는 것 (Tk 와 무관): 글 해석(parse_bbcode, 색 이름), 값 채우기(fill_values), 모드 데이터(modgen), 카드 종류(cardkind).
그림 파일은 PIL 로 읽어 Tk 쪽과 같은 방식으로 자르고 둥글게 만든 뒤 QPixmap 으로 바꾼다.
"""
import os
import re

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetricsF, QImage, QPainterPath, QPen, QPixmap

import cardkind
import modgen as M
import preview as PV          # 글 해석·값 채우기·색 (Tk 와 무관한 부분만 쓴다)

try:
    from PIL import Image, ImageDraw, ImageOps
    HAS_PIL = True
except Exception:   # noqa: BLE001
    HAS_PIL = False

FONT = PV.FONT
RARITY_COLORS = PV.RARITY_COLORS
TYPE_COLORS = PV.TYPE_COLORS
KW_TEXT = PV.KW_TEXT
CARD_W, CARD_H = 300, 420
PANEL_W = 300
_fonts = {}
_pixmaps = {}


# ---------------------------------------------------------------------------
# 글꼴 · 그림 도형
# ---------------------------------------------------------------------------
def font(size, bold=False, italic=False):
    """size: 96 DPI 기준 포인트. Tk 쪽 _font 와 같은 픽셀 크기로 만든다."""
    key = (size, bold, italic)
    if key not in _fonts:
        f = QFont(FONT)
        f.setPixelSize(max(7, round(size * 4 / 3)))
        f.setBold(bold)
        f.setItalic(italic)
        _fonts[key] = f
    return _fonts[key]


def linespace(size, bold=False):
    return QFontMetricsF(font(size, bold)).lineSpacing()


def rounded_rect(painter, x1, y1, x2, y2, r, fill=None, outline=None, width=1):
    path = QPainterPath()
    path.addRoundedRect(QRectF(x1, y1, x2 - x1, y2 - y1), r, r)
    painter.setPen(QPen(QColor(outline), width) if outline else Qt.PenStyle.NoPen)
    painter.setBrush(QColor(fill) if fill else Qt.BrushStyle.NoBrush)
    painter.drawPath(path)


def oval(painter, x1, y1, x2, y2, fill, outline="", width=1):
    painter.setPen(QPen(QColor(outline), width) if outline else Qt.PenStyle.NoPen)
    painter.setBrush(QColor(fill))
    painter.drawEllipse(QRectF(x1, y1, x2 - x1, y2 - y1))


def rect(painter, x1, y1, x2, y2, fill, outline="", width=1):
    painter.setPen(QPen(QColor(outline), width) if outline else Qt.PenStyle.NoPen)
    painter.setBrush(QColor(fill))
    painter.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))


def center_text(painter, cx, cy, text, color, f):
    """Tk 의 anchor='center' 와 같이 (cx, cy) 가운데에 글을 놓는다 (여러 줄 가능)."""
    painter.setFont(f)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(cx - 400, cy - 300, 800, 600), int(Qt.AlignmentFlag.AlignCenter), text)


def top_text(painter, cx, top, text, color, f):
    """Tk 의 anchor='n' 과 같이 (cx, top) 위쪽 가운데에 글을 놓는다."""
    painter.setFont(f)
    painter.setPen(QColor(color))
    painter.drawText(QRectF(cx - 400, top, 800, 600), int(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter), text)


def _qpixmap(im):
    im = im.convert("RGBA")
    data = im.tobytes("raw", "RGBA")
    qimg = QImage(data, im.width, im.height, im.width * 4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimg)


def _apply_mask(im, mask):
    """Tk 쪽 ImageCache 와 같은 모양 자르기 (round: 둥근 사각형, ellipse: 원)."""
    m = Image.new("L", im.size, 0)
    d = ImageDraw.Draw(m)
    box = (0, 0, im.size[0] - 1, im.size[1] - 1)
    if mask == "round":
        d.rounded_rectangle(box, radius=max(4, min(im.size) // 8), fill=255)
    else:
        d.ellipse(box, fill=255)
    alpha = Image.composite(im.getchannel("A"), Image.new("L", im.size, 0), m)
    im.putalpha(alpha)
    return im


def pixmap(path, w, h, mode="contain", mask=None):
    """그림 파일을 w×h 에 맞춘 QPixmap. mode: contain(전체 보이게) / cover(꽉 채우고 자르기).
    그림이 없거나 못 읽으면 None (호출하는 쪽에서 기본 모양을 그린다)."""
    if not path or not os.path.isfile(path) or not HAS_PIL:
        return None
    w, h = max(1, int(w)), max(1, int(h))
    key = (path, os.path.getmtime(path), w, h, mode, mask)
    if key not in _pixmaps:
        try:
            im = Image.open(path).convert("RGBA")
            if mode == "cover":
                im = ImageOps.fit(im, (w, h), Image.LANCZOS)
            else:
                im.thumbnail((w, h), Image.LANCZOS)
            if mask:
                im = _apply_mask(im, mask)
            _pixmaps[key] = _qpixmap(im)
        except Exception:   # noqa: BLE001
            _pixmaps[key] = None
    return _pixmaps[key]


def placeholder(w, h, mask, color):
    """그림이 없을 때 쓰는 줄무늬 임시 그림 (PIL 이 없으면 None)."""
    if not HAS_PIL:
        return None
    w, h = max(1, int(w)), max(1, int(h))
    key = ("__ph__", w, h, mask, color)
    if key not in _pixmaps:
        im = Image.new("RGBA", (w, h), color)
        d = ImageDraw.Draw(im)
        step = max(8, w // 12)
        stripe = PV._shade(color, 1.18)
        for i in range(-h, w + h, step):
            d.line([(i, h), (i + h, 0)], fill=stripe, width=max(2, step // 4))
        if mask:
            im = _apply_mask(im, mask)
        _pixmaps[key] = _qpixmap(im)
    return _pixmaps[key]


def _draw_pixmap_at(painter, pm, x, y):
    painter.drawPixmap(QPointF(x, y), pm)


# ---------------------------------------------------------------------------
# 서식 글
# ---------------------------------------------------------------------------
def draw_rich(painter, cx, top, width, text, size=10, color="#f2ead8", line_gap=4, measure_only=False):
    """서식 있는 글을 줄바꿈해서 가운데 맞춰 그린다. 그린 높이를 돌려준다.
    Tk 의 draw_rich 와 같은 규칙으로 줄을 나눈다. 글꼴 폭이 달라서 줄 끝은 조금 다를 수 있다."""
    pieces = []
    for run, st in PV.parse_bbcode(text):
        if st["energy"]:
            try:
                n = int(run)
            except ValueError:
                n = 1
            pieces.append(("◆" * max(1, min(n, 9)), dict(st, color="#ffa64d", bold=True)))
            continue
        for tok in re.findall(r"\n| +|[㐀-鿿]|[^ \n㐀-鿿]+", run):
            pieces.append((tok, st))
    lines, cur, cur_w = [], [], 0.0
    for tok, st in pieces:
        if tok == "\n":
            lines.append((cur, cur_w))
            cur, cur_w = [], 0.0
            continue
        fm = QFontMetricsF(font(size, st["bold"], st["italic"]))
        w = fm.horizontalAdvance(tok)
        if tok.strip() == "" and not cur:
            continue
        if cur_w + w > width and cur and tok.strip():
            while cur and cur[-1][0].strip() == "":
                cur_w -= cur[-1][2]
                cur.pop()
            lines.append((cur, cur_w))
            cur, cur_w = [], 0.0
        if w > width and tok.strip():
            for ch in tok:
                cw = fm.horizontalAdvance(ch)
                if cur_w + cw > width and cur:
                    lines.append((cur, cur_w))
                    cur, cur_w = [], 0.0
                cur.append((ch, st, cw))
                cur_w += cw
            continue
        cur.append((tok, st, w))
        cur_w += w
    if cur:
        lines.append((cur, cur_w))
    lh = linespace(size) + line_gap
    if measure_only:
        return lh * len(lines)
    y = top
    for line, lw in lines:
        x = cx - lw / 2
        for tok, st, w in line:
            f = font(size, st["bold"], st["italic"])
            painter.setFont(f)
            painter.setPen(QColor(st["color"] or color))
            painter.drawText(QPointF(x, y + QFontMetricsF(f).ascent()), tok)
            x += w
        y += lh
    return lh * len(lines)


# ---------------------------------------------------------------------------
# 카드
# ---------------------------------------------------------------------------
def render_card(painter, project, card, x=0, y=0, s=1.0, lang="ko", upgraded=False):
    S = lambda v: v * s  # noqa: E731
    ch = project["character"]
    border = ch["color"] if ch.get("enabled") else "#8a8a8a"
    if not M.HEX_RE.match(border or ""):
        border = "#8a8a8a"
    border = "#" + border.lstrip("#")
    ctype = card.get("type", "Attack")
    # 바탕
    rounded_rect(painter, x + S(6), y + S(6), x + S(294), y + S(414), S(22), fill=PV._shade(border, 0.35),
                 outline=border, width=max(2, round(S(5))))
    rounded_rect(painter, x + S(18), y + S(18), x + S(282), y + S(402), S(16),
                 fill=PV._shade(TYPE_COLORS.get(ctype, "#444"), 0.55))
    # 그림
    ax1, ay1, ax2, ay2 = x + S(30), y + S(70), x + S(270), y + S(253)
    mask = {"Attack": None, "Skill": "round", "Power": "ellipse"}.get(ctype)
    pm = pixmap(card.get("image"), ax2 - ax1, ay2 - ay1, "cover", mask)
    if pm:
        _draw_pixmap_at(painter, pm, ax1, ay1)
    else:
        ph = placeholder(ax2 - ax1, ay2 - ay1, mask, "#3a3f4a")
        if ph:
            _draw_pixmap_at(painter, ph, ax1, ay1)
        elif ctype == "Power":
            oval(painter, ax1, ay1, ax2, ay2, "#3a3f4a")
        else:
            rounded_rect(painter, ax1, ay1, ax2, ay2, S(14) if ctype == "Skill" else S(2), fill="#3a3f4a")
        center_text(painter, (ax1 + ax2) / 2, (ay1 + ay2) / 2, "그림 없음" if lang == "ko" else "No Art",
                    "#8f97a6", font(max(7, int(S(12))), True))
    # 이름 띠
    rarity = card.get("rarity", "Common")
    rounded_rect(painter, x + S(36), y + S(26), x + S(264), y + S(62), S(10),
                 fill=RARITY_COLORS.get(rarity, "#555"), outline=PV._shade(RARITY_COLORS.get(rarity, "#555"), 1.4),
                 width=max(1, round(S(2))))
    name = M.text(card, "name", lang) + ("+" if upgraded else "")
    center_text(painter, x + S(150), y + S(44), name, "#7fff00" if upgraded else "#ffffff",
                font(max(7, int(S(14))), True))
    # 종류
    tlabel = M.label_of(M.CARD_TYPES, ctype) if lang == "ko" else ctype
    custom_kind = cardkind.definition(project, card)
    if lang == "zh":
        tlabel = {"Attack": "攻击", "Skill": "技能", "Power": "能力", "Curse": "诅咒", "Status": "状态",
                  "Quest": "任务"}.get(ctype, ctype)
    if custom_kind:
        tlabel = M.text(custom_kind, "name", lang)
    rounded_rect(painter, x + S(112), y + S(246), x + S(188), y + S(270), S(10), fill="#1b1b22", outline=border, width=1)
    center_text(painter, x + S(150), y + S(258), tlabel, "#d9d2c0", font(max(6, int(S(9)))))
    # 설명
    px1, py1, px2, py2 = x + S(28), y + S(278), x + S(272), y + S(394)
    rounded_rect(painter, px1, py1, px2, py2, S(10), fill="#17171d")
    kws = M.card_keywords(card, upgraded)
    before = [f"[gold]{KW_TEXT[lang][k]}[/gold]." for k in M.KEYWORDS_BEFORE if k in kws]
    after = [f"[gold]{KW_TEXT[lang][k]}[/gold]." for k in M.KEYWORDS_AFTER if k in kws]
    body = PV.fill_values(project, M.description(project, card, "card", lang), card, upgraded)
    full = "\n".join(before + [body] + after)
    size = max(6, int(S(10.5)))
    width = px2 - px1 - S(16)
    hgt = draw_rich(painter, 0, 0, width, full, size, measure_only=True)
    while hgt > (py2 - py1 - S(8)) and size > 6:
        size -= 1
        hgt = draw_rich(painter, 0, 0, width, full, size, measure_only=True)
    draw_rich(painter, (px1 + px2) / 2, py1 + max(S(4), (py2 - py1 - hgt) / 2), width, full, size)
    # 비용
    if card.get("no_cost"):
        return CARD_W * s, CARD_H * s
    cost = "X" if card.get("x_cost") else int(card.get("upgrade_cost" if upgraded else "cost", 0) or 0)
    ox, oy, r = x + S(32), y + S(34), S(24)
    oval(painter, ox - r - S(3), oy - r - S(3), ox + r + S(3), oy + r + S(3), "#111")
    oval(painter, ox - r, oy - r, ox + r, oy + r, border, PV._shade(border, 1.5), max(1, round(S(2))))
    changed = upgraded and not card.get("x_cost") and int(card.get("upgrade_cost", 0)) != int(card.get("cost", 0))
    center_text(painter, ox, oy, str(cost), "#7fff00" if changed else "#ffffff", font(max(8, int(S(18))), True))
    return CARD_W * s, CARD_H * s


# ---------------------------------------------------------------------------
# 유물 · 물약 · 파워
# ---------------------------------------------------------------------------
def _panel(painter, x, y, s, h, accent):
    rounded_rect(painter, x + 6 * s, y + 6 * s, x + 294 * s, y + h - 6 * s, 18 * s,
                 fill="#1d1f27", outline=accent, width=max(2, round(3 * s)))


def render_relic(painter, project, relic, x=0, y=0, s=1.0, lang="ko"):
    S = lambda v: v * s  # noqa: E731
    acc = RARITY_COLORS.get(relic.get("rarity"), "#888")
    h = S(400)
    _panel(painter, x, y, s, h, acc)
    cx = x + S(150)
    oval(painter, cx - S(78), y + S(22), cx + S(78), y + S(178), "#262a35")
    pm = pixmap(relic.get("image"), S(128), S(128))
    if pm:
        _draw_pixmap_at(painter, pm, cx - pm.width() / 2, y + S(100) - pm.height() / 2)
    else:
        oval(painter, cx - S(46), y + S(54), cx + S(46), y + S(146), "#c9a227", "#7a6116", max(1, round(S(4))))
        center_text(painter, cx, y + S(100), "?", "#5a4410", font(max(8, int(S(30))), True))
    center_text(painter, cx, y + S(198), M.text(relic, "name", lang), "#efc851", font(max(7, int(S(14))), True))
    rl = M.label_of(M.RELIC_RARITIES, relic.get("rarity")) if lang == "ko" else relic.get("rarity")
    center_text(painter, cx, y + S(220), f"{rl} {'유물' if lang == 'ko' else 'Relic'}", acc, font(max(6, int(S(9)))))
    desc = PV.fill_values(project, M.description(project, relic, "relic", lang), relic)
    used = draw_rich(painter, cx, y + S(240), S(250), desc, max(6, int(S(10.5))))
    flav = M.text(relic, "flavor", lang)
    if flav:
        draw_rich(painter, cx, y + S(250) + used, S(250), f"[i]{flav}[/i]", max(6, int(S(9))), color="#8f8a7d")
    return PANEL_W * s, h


def render_potion(painter, project, potion, x=0, y=0, s=1.0, lang="ko"):
    S = lambda v: v * s  # noqa: E731
    acc = RARITY_COLORS.get(potion.get("rarity"), "#888")
    h = S(400)
    _panel(painter, x, y, s, h, acc)
    cx = x + S(150)
    pm = pixmap(potion.get("image"), S(150), S(150))
    if pm:
        _draw_pixmap_at(painter, pm, cx - pm.width() / 2, y + S(100) - pm.height() / 2)
    else:
        oval(painter, cx - S(48), y + S(78), cx + S(48), y + S(174), "#4aa3df", "#2a5f85", max(1, round(S(4))))
        rect(painter, cx - S(14), y + S(40), cx + S(14), y + S(84), "#4aa3df", "#2a5f85", max(1, round(S(4))))
        rect(painter, cx - S(18), y + S(30), cx + S(18), y + S(44), "#8a6a4a")
    center_text(painter, cx, y + S(198), M.text(potion, "name", lang), "#ffffff", font(max(7, int(S(14))), True))
    rl = M.label_of(M.POTION_RARITIES, potion.get("rarity")) if lang == "ko" else potion.get("rarity")
    tg = M.label_of(M.POTION_TARGETS, potion.get("target")) if lang == "ko" else potion.get("target")
    center_text(painter, cx, y + S(220), f"{rl} · {'대상' if lang == 'ko' else 'Target'}: {tg}", acc,
                font(max(6, int(S(9)))))
    desc = PV.fill_values(project, M.description(project, potion, "potion", lang), potion)
    draw_rich(painter, cx, y + S(240), S(250), desc, max(6, int(S(10.5))))
    return PANEL_W * s, h


def render_power(painter, project, power, x=0, y=0, s=1.0, lang="ko", stacks=3):
    S = lambda v: v * s  # noqa: E731
    buff = power.get("type") == "Buff"
    acc = "#5fbf5f" if buff else "#b45fd4"
    h = S(400)
    _panel(painter, x, y, s, h, acc)
    cx = x + S(150)
    pm = pixmap(power.get("image"), S(128), S(128))
    if pm:
        _draw_pixmap_at(painter, pm, cx - pm.width() / 2, y + S(92) - pm.height() / 2)
    else:
        oval(painter, cx - S(52), y + S(40), cx + S(52), y + S(144), "#4caf50" if buff else "#8e44ad",
             PV._shade(acc, 0.6), max(1, round(S(4))))
        center_text(painter, cx, y + S(92), (M.text(power, "name", lang) or "?")[:1], "#ffffff",
                    font(max(8, int(S(34))), True))
    if power.get("stack") == "Counter":
        bx, by = cx + S(46), y + S(136)
        oval(painter, bx - S(16), by - S(16), bx + S(16), by + S(16), "#111", acc, 2)
        center_text(painter, bx, by, str(stacks), "#ffffff", font(max(7, int(S(12))), True))
    center_text(painter, cx, y + S(176), M.text(power, "name", lang), acc, font(max(7, int(S(14))), True))
    kind = M.label_of(M.POWER_TYPES, power.get("type")) if lang == "ko" else power.get("type")
    stk = ("중첩" if power.get("stack") == "Counter" else "단일") if lang == "ko" else power.get("stack")
    center_text(painter, cx, y + S(198), f"{kind} · {stk}", "#9a9a9a", font(max(6, int(S(9)))))
    desc = PV.fill_values(project, M.description(project, power, "power", lang), power, stacks=stacks)
    draw_rich(painter, cx, y + S(218), S(250), desc, max(6, int(S(10.5))))
    return PANEL_W * s, h


def render_item(painter, project, kind, item, x=0, y=0, s=1.0, lang="ko", upgraded=False, stacks=3):
    if kind == "card":
        return render_card(painter, project, item, x, y, s, lang, upgraded)
    if kind == "relic":
        return render_relic(painter, project, item, x, y, s, lang)
    if kind == "potion":
        return render_potion(painter, project, item, x, y, s, lang)
    return render_power(painter, project, item, x, y, s, lang, stacks)


# ---------------------------------------------------------------------------
# 캐릭터
# ---------------------------------------------------------------------------
def render_character(painter, project, x=0, y=0, lang="ko", s=1.0):
    S = lambda v: v * s  # noqa: E731
    ch = project["character"]
    color = ch.get("color", "#888888")
    if not M.HEX_RE.match(color or ""):
        color = "#888888"
    color = "#" + color.lstrip("#")
    rounded_rect(painter, x + S(6), y + S(6), x + S(294), y + S(554), S(18), fill="#1d1f27", outline=color,
                 width=max(2, round(S(3))))
    cx = x + S(150)
    if not ch.get("enabled"):
        center_text(painter, cx, y + S(200), "새 캐릭터를 만들지 않습니다\n(콘텐츠 모드)", "#aaaaaa", font(S(11), True))
        return
    top_text(painter, cx, y + S(24), "캐릭터 선택 화면" if lang == "ko" else "Character Select", "#888888", font(S(9)))
    # 선택 초상화 (132x195 비율)
    w, h = S(160), S(236)
    top = y + S(42)
    pm = pixmap(ch.get("select_image"), w, h, "cover", "round")
    if pm:
        _draw_pixmap_at(painter, pm, cx - pm.width() / 2, top)
    else:
        rounded_rect(painter, cx - w / 2, top, cx + w / 2, top + h, S(14), fill=PV._shade(color, 0.45),
                     outline=color, width=2)
        ph = M.label_of(M.PLACEHOLDER_CHARS, ch.get("placeholder"))
        center_text(painter, cx, top + h / 2, f"초상화 없음\n(임시 외형:\n{ph})", "#dddddd", font(S(10)))
    yy = top + h + S(14)
    top_text(painter, cx, yy, M.text(ch, "name", lang), color, font(S(16), True))
    yy += linespace(S(16), True) + S(4)
    top_text(painter, cx, yy, f"♥ {ch.get('hp')}", "#ff7070", font(S(11), True))
    yy += linespace(S(11), True) + S(6)
    icons_top = y + S(462)
    desc = M.character_description(ch, lang)
    size = 10
    while size > 7 and yy + draw_rich(painter, 0, 0, S(250), desc, S(size), measure_only=True) > icons_top - S(8):
        size -= 1
    draw_rich(painter, cx, yy, S(250), desc, S(size), color="#d9d2c0")
    # 작은 그림들
    for i, (field, label) in enumerate((("icon_image", "아이콘"), ("map_marker_image", "지도 표시"),
                                        ("select_locked_image", "잠김"))):
        bx = x + S(60) + i * S(90)
        by = icons_top + S(32)
        src = ch.get(field) or (ch.get("select_image") if field == "select_locked_image" else "")
        im = pixmap(src, S(56), S(56), "contain")
        rect(painter, bx - S(32), by - S(32), bx + S(32), by + S(32), "#262a35", "#3a3f4a")
        if im:
            _draw_pixmap_at(painter, im, bx - im.width() / 2, by - im.height() / 2)
        else:
            center_text(painter, bx, by, "기본", "#777777", font(S(9)))
        top_text(painter, bx, by + S(44), label, "#999999", font(S(8)))

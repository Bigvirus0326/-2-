"""
시험장 전투 화면 — 게임 파일(pck)의 실제 그림·글꼴로 만든 1920×1080 전투 화면.

배경(덩굴 숲 레이어), 체력 바·방어도, 파워 아이콘, 적 의도, 에너지 구슬, 별 카운터, 턴 종료 버튼, 손패(실제 카드 합성),
그리고 모드의 전투 버튼(Godot StyleBoxFlat 과 같은 모양)과 설명 말풍선을 그린다.
캐릭터·몬스터 몸은 Spine 애니메이션이라 그림 한 장으로 만들 수 없어 실루엣으로 대신한다.

simulate(): 버튼의 블록을 시험장 상태(체력·방어도·에너지·별·자원)에 실제로 적용해 보는 작은 해석기.
"""
from __future__ import annotations

import math
import random

from PIL import Image, ImageDraw, ImageFilter

W, H = 1920, 1080
# 게임 설정 (project.binary): 기준 1920×1080, stretch = canvas_items, aspect = expand
# → 넓은 화면은 좌우가, 높은 화면은 위아래가 더 보인다. 아래 목록은 그때의 '게임 안 화면 크기'.
ASPECTS = [("16:9", 1920, 1080), ("21:9", 2520, 1080), ("32:9", 3840, 1080), ("16:10", 1920, 1200), ("4:3", 1920, 1440),
           ("5:4", 1920, 1536)]


def view_offset(vw, vh):
    """가운데 기준(캐릭터·배경)이 기준 화면에서 얼마나 밀리는지."""
    return (vw - W) // 2, (vh - H) // 2


def view_pos(p, vw=W, vh=H):
    dx, dy = view_offset(vw, vh)
    return (p[0] + dx, p[1] + dy)


def ui_scale(vw, vh):
    """버튼 크기 배율 (게임 코드와 같은 식)."""
    return min(vw / W, vh / H)
PLAYER = (470, 770)   # 캐릭터 발밑
ENEMY = (1430, 770)
PLACEHOLDER_ORB = {"ironclad": "ironclad", "silent": "silent", "defect": "defect", "necrobinder": "necrobinder",
                   "regent": "regent"}

_CACHE = {}


def _tex(assets, path):
    key = ("tex", path)
    if key not in _CACHE:
        try:
            _CACHE[key] = assets.texture(path).convert("RGBA")
        except Exception:  # noqa: BLE001 - 게임 버전에 따라 없을 수 있음
            _CACHE[key] = None
    return _CACHE[key]


def background(assets, act="overgrowth", vw=W, vh=H):
    key = ("bg", act, vw, vh)
    if key in _CACHE:
        return _CACHE[key]
    bg = Image.new("RGBA", (vw, vh), (20, 26, 22, 255))
    # 배경 레이어는 화면 가운데 기준 2765×1296 (화면이 더 크면 덮을 만큼 키운다)
    k = max(1.0, vw / 2765, vh / 1296)
    lw, lh = int(2765 * k), int(1296 * k)
    for lay in ("00", "01_a", "02_a", "03_a", "04_a"):
        im = _tex(assets, f"images/rooms/{act}/{act}_{lay}.png")
        if im is None:
            continue
        im = im.resize((lw, lh), Image.LANCZOS)
        bg.alpha_composite(im, (int(vw / 2 - lw / 2 + 23), int(vh / 2 - lh / 2)))
    _CACHE[key] = bg
    return bg


def _silhouette(img, feet, enemy=False):
    """Spine 캐릭터 대신 쓰는 실루엣 (그림자 + 몸 + 가장자리 빛)."""
    fx, fy = feet
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.ellipse((fx - 120, fy - 22, fx + 120, fy + 18), fill=(0, 0, 0, 110))
    body = (34, 38, 56, 235) if not enemy else (58, 30, 34, 235)
    rim = (150, 170, 230, 150) if not enemy else (230, 120, 110, 150)
    if not enemy:
        d.polygon([(fx - 70, fy - 10), (fx - 52, fy - 210), (fx - 40, fy - 300), (fx + 40, fy - 300), (fx + 56, fy - 210),
                   (fx + 78, fy - 10)], fill=body)              # 망토/몸
        d.ellipse((fx - 38, fy - 380, fx + 38, fy - 296), fill=body)  # 머리
        d.polygon([(fx + 40, fy - 250), (fx + 150, fy - 330), (fx + 158, fy - 318), (fx + 52, fy - 228)], fill=body)  # 칼
    else:
        d.ellipse((fx - 130, fy - 260, fx + 130, fy - 10), fill=body)
        d.ellipse((fx - 70, fy - 330, fx + 50, fy - 220), fill=body)
        d.polygon([(fx - 60, fy - 320), (fx - 95, fy - 380), (fx - 35, fy - 330)], fill=body)
        d.polygon([(fx + 20, fy - 325), (fx + 55, fy - 390), (fx + 40, fy - 318)], fill=body)
        d.ellipse((fx - 40, fy - 290, fx - 22, fy - 272), fill=(255, 190, 90, 230))
        d.ellipse((fx + 2, fy - 290, fx + 20, fy - 272), fill=(255, 190, 90, 230))
    edge = lay.getchannel("A").filter(ImageFilter.FIND_EDGES)
    glow = Image.new("RGBA", (W, H), rim)
    glow.putalpha(edge.point(lambda v: min(255, v * 2)).filter(ImageFilter.GaussianBlur(2)))
    img.alpha_composite(lay)
    img.alpha_composite(glow)


def _label(img, assets, text, center, size, color=(255, 246, 226), outline=(0, 0, 0), outline_w=4, font="bold", anchor="mm"):
    d = ImageDraw.Draw(img)
    try:
        f = assets.font(font, size)
    except Exception:  # noqa: BLE001
        f = None
    d.text(center, text, font=f, fill=color, anchor=anchor, stroke_width=outline_w, stroke_fill=outline)


def _is_kor(text):
    return any("가" <= ch <= "힣" for ch in text or "")


def _is_cjk(text):
    return any("一" <= ch <= "鿿" or "　" <= ch <= "〿" or "＀" <= ch <= "￯" for ch in text or "")


def font_for(text, lang="ko"):
    """글자에 맞는 글꼴: 중국어 → zh(微软雅黑), 한국어 → kor, 나머지 → 게임 bold."""
    if lang == "zh" or _is_cjk(text):
        return "zh"
    if lang == "ko" or _is_kor(text):
        return "kor"
    return "bold"


def btn_text(b, field, lang):
    """버튼 글자 (게임과 같은 대체: 중국어가 비면 영어, 영어가 비면 한국어)."""
    order = {"ko": ("ko", "en"), "en": ("en", "ko"), "zh": ("zh", "en", "ko")}.get(lang, ("en", "ko"))
    for l in order:
        v = (b.get(f"{field}_{l}") or "").strip()
        if v:
            return v
    return "?" if field == "label" else ""


def health_bar(img, assets, feet, hp, maxhp, block=0, enemy=False):
    fx, fy = feet
    x1, y1, x2, y2 = fx - 130, fy + 7, fx + 120, fy + 23
    d = ImageDraw.Draw(img)
    bg = _tex(assets, "images/ui/combat/health_bar_bg.png")
    if bg is not None:
        _nine(img, bg, (x1 + 1, y1, x2 - 1, y2), 8)
    else:
        d.rounded_rectangle((x1, y1, x2, y2), 6, fill=(20, 10, 10, 230))
    frac = max(0.0, min(1.0, hp / maxhp if maxhp else 0))
    if frac > 0:
        fx2 = x1 + 5 + (x2 - x1 - 10) * frac
        col = (196, 44, 44, 255)
        d.rounded_rectangle((x1 + 5, y1 + 3, fx2, y2 - 3), 4, fill=col)
        d.line([(x1 + 7, y1 + 5), (fx2 - 2, y1 + 5)], fill=(240, 120, 110, 200), width=2)
    if block > 0:
        d.rounded_rectangle((x1, y1, x2, y2), 6, outline=(90, 160, 230, 255), width=3)
    _label(img, assets, f"{int(hp)}/{int(maxhp)}", ((x1 + x2) / 2, (y1 + y2) / 2 + 1), 20, outline_w=3)
    if block > 0:
        ic = _tex(assets, "images/ui/combat/block.png")
        bx, by = fx - 166, fy - 26 + 7
        if ic is not None:
            img.alpha_composite(ic.resize((60, 60), Image.LANCZOS), (bx, by))
        _label(img, assets, str(int(block)), (bx + 30, by + 33), 26, outline=(28, 52, 92), outline_w=4)


def _nine(img, tex, rect, margin):
    x1, y1, x2, y2 = (int(round(v)) for v in rect)
    w, h = max(2, x2 - x1), max(2, y2 - y1)
    tw, th = tex.size
    m = min(margin, tw // 2 - 1)
    left = tex.crop((0, 0, m, th)).resize((m, h))
    mid = tex.crop((m, 0, tw - m, th)).resize((max(1, w - 2 * m), h))
    right = tex.crop((tw - m, 0, tw, th)).resize((m, h))
    img.alpha_composite(left, (x1, y1))
    img.alpha_composite(mid, (x1 + m, y1))
    img.alpha_composite(right, (x2 - m, y1))


def power_row(img, assets, feet, powers):
    """powers: [(아이콘 이미지, 수치)] — 체력 바 아래 줄."""
    fx, fy = feet
    x = fx - 130
    for icon, amount in powers:
        if icon is not None:
            img.alpha_composite(icon.resize((40, 40), Image.LANCZOS), (int(x), int(fy + 34)))
        if amount is not None:
            _label(img, assets, str(amount), (x + 36, fy + 66), 18, outline=(31, 26, 21), outline_w=3, anchor="rm")
        x += 44


def intent(img, assets, feet, dmg):
    fx, fy = feet
    ic = _tex(assets, "images/packed/intents/attack/intent_attack_2.png")
    if ic is not None:
        ic = ic.resize((int(ic.width * 0.9), int(ic.height * 0.9)), Image.LANCZOS)
        img.alpha_composite(ic, (int(fx - ic.width / 2), int(fy - 420)))
    _label(img, assets, str(dmg), (fx - 18, fy - 360), 28, outline_w=5)


def energy(img, assets, project, cur, mx, ox=0, oy=0):
    ch = project.get("character") or {}
    ph = PLACEHOLDER_ORB.get(ch.get("placeholder") or "ironclad", "ironclad")
    cx, cy = 164 + ox, 892 + oy
    layers = [_tex(assets, f"images/ui/combat/energy_counters/{ph}/{ph}_orb_layer_{i}.png") for i in range(1, 6)]
    for lay in layers:
        if lay is not None:
            im = lay.resize((128, 128), Image.LANCZOS)
            if cur <= 0:
                im = Image.blend(im, Image.new("RGBA", im.size, (40, 40, 40, 0)), 0.45)
            img.alpha_composite(im, (cx - 64, cy - 64))
    _label(img, assets, f"{cur}/{mx}", (cx, cy + 2), 36, outline=(76, 36, 22) if ph == "ironclad" else (30, 30, 50), outline_w=6)


def stars(img, assets, n, ox=0, oy=0):
    cx, cy = 100 + 64 + 30 + ox, 828 - 212 + 64 + 120 + oy
    st = _tex(assets, "images/ui/combat/energy_star.png")
    if st is not None:
        img.alpha_composite(st.resize((74, 74), Image.LANCZOS), (cx - 37, cy - 37))
    _label(img, assets, str(n), (cx, cy + 2), 30, outline=(26, 94, 107), outline_w=5)


END_TURN_POS = (1604, 846)   # NEndTurnButton._showPosRatio = (1604, 846) / 1920×1080 → 왼쪽 위 모서리
END_TURN_SIZE = (220, 90)    # end_turn_button.tscn 의 루트 크기


def end_turn_rect(vw=W, vh=H):
    """게임과 같은 계산: 위치 = 비율 × 보이는 화면 크기, 크기는 그대로 220×90."""
    x, y = END_TURN_POS[0] / W * vw, END_TURN_POS[1] / H * vh
    return x, y, x + END_TURN_SIZE[0], y + END_TURN_SIZE[1]


def end_turn(img, assets, lang="ko", vw=W, vh=H, turn=1):
    x1, y1, x2, y2 = end_turn_rect(vw, vh)
    cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
    btn = _tex(assets, "images/packed/combat_ui/end_turn_button.png")
    if btn is not None:
        # Image: 512×256 TextureRect 를 가운데 기준 scale 0.5 → 256×128
        im = btn.resize((btn.width // 2, btn.height // 2), Image.LANCZOS)
        img.alpha_composite(im, (int(round(cx - im.width / 2)), int(round(cy - im.height / 2))))
    # 글자: 게임 번역 'END_TURN_BUTTON' ("{turnNumber}턴 종료" / "End Turn {turnNumber}")
    try:
        txt = assets.loc(lang, "gameplay_ui").get("END_TURN_BUTTON") or ""
    except Exception:  # noqa: BLE001
        txt = ""
    txt = (txt or ("{turnNumber}턴 종료" if lang == "ko" else "End Turn {turnNumber}")).replace("{turnNumber}", str(turn))
    # Label: 안쪽 여백 29,11,-29,-7 → 칸 162×72, 글자 가운데는 상자 가운데보다 2px 아래.
    # 크기 30(넘치면 줄임, SetTextAutoSize), 크림색, 남색 외곽선 12(=반지름 6), 그림자 검정 19% (3,2)
    font = font_for(txt, lang)
    size = 30
    while size > 12:
        try:
            f = assets.font(font, size)
            if ImageDraw.Draw(img).textlength(txt, font=f) <= END_TURN_SIZE[0] - 58:
                break
        except Exception:  # noqa: BLE001
            break
        size -= 1
    tc = (cx, cy + 2)
    sh = Image.new("RGBA", img.size, (0, 0, 0, 0))   # 그림자는 따로 그려 섞는다
    _label(sh, assets, txt, (tc[0] + 3, tc[1] + 2), size, color=(0, 0, 0, 255), outline=(0, 0, 0, 255), outline_w=6, font=font)
    sh.putalpha(sh.getchannel("A").point(lambda v: v * 48 // 255))
    img.alpha_composite(sh)
    _label(img, assets, txt, tc, size, color=(255, 246, 226), outline=(19, 31, 46), outline_w=6, font=font)


def pile_rects(vw=W, vh=H):
    """combat_piles_container.tscn: 뽑을 더미 = 왼쪽 아래 (15,-95)~(95,-15), 버린 더미 = 오른쪽 아래 (-94,-95)~(-14,-15).
    돌려주는 값: (그림, 80×80 상자, 숫자 배지 48×48 상자)."""
    d = (15, vh - 95, 95, vh - 15)
    c = (vw - 94, vh - 95, vw - 14, vh - 15)
    # 배지(CountContainer): 상자 가운데 기준 뽑을 더미 (8,-4)~(56,44), 버린 더미 (-57.5,-3.5)~(-9.5,44.5)
    dcx, dcy = (d[0] + d[2]) / 2, (d[1] + d[3]) / 2
    ccx, ccy = (c[0] + c[2]) / 2, (c[1] + c[3]) / 2
    return [("images/packed/combat_ui/draw_pile.png", d, (dcx + 8, dcy - 4, dcx + 56, dcy + 44)),
            ("images/packed/combat_ui/discard_pile.png", c, (ccx - 57.5, ccy - 3.5, ccx - 9.5, ccy + 44.5))]


def piles(img, assets, draw_n=12, discard_n=0, vw=W, vh=H):
    badge = _tex(assets, "images/packed/combat_ui/pile_button_count.png")
    for (path, box, bb), n in zip(pile_rects(vw, vh), (draw_n, discard_n)):
        t = _tex(assets, path)
        if t is not None:   # Icon: 80×80 상자에 비율 유지·가운데 (stretch_mode 5)
            k = min((box[2] - box[0]) / t.width, (box[3] - box[1]) / t.height)
            t = t.resize((max(1, round(t.width * k)), max(1, round(t.height * k))), Image.LANCZOS)
            img.alpha_composite(t, (int(round((box[0] + box[2] - t.width) / 2)), int(round((box[1] + box[3] - t.height) / 2))))
        if badge is not None:
            k = min((bb[2] - bb[0]) / badge.width, (bb[3] - bb[1]) / badge.height)
            b = badge.resize((max(1, round(badge.width * k)), max(1, round(badge.height * k))), Image.LANCZOS)
            img.alpha_composite(b, (int(round((bb[0] + bb[2] - b.width) / 2)), int(round((bb[1] + bb[3] - b.height) / 2))))
        # Count: 크기 26, 크림색, 진홍 외곽선 12(=반지름 6), 그림자 검정 13% (2,1)
        cx, cy = (bb[0] + bb[2]) / 2, (bb[1] + bb[3]) / 2
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        _label(sh, assets, str(n), (cx + 2, cy + 1), 26, color=(0, 0, 0, 255), outline=(0, 0, 0, 255), outline_w=6)
        sh.putalpha(sh.getchannel("A").point(lambda v: v * 32 // 255))
        img.alpha_composite(sh)
        _label(img, assets, str(n), (cx, cy), 26, color=(255, 246, 226), outline=(136, 31, 32), outline_w=6)


def hand(img, assets, project, lang="ko"):
    """프로젝트 카드 최대 5장을 손패처럼 (게임 카드 합성 재사용)."""
    cards = [c for c in project.get("cards", []) if not c.get("clone")][:5]
    if not cards:
        return
    key = ("hand", lang, tuple((c["id"], str(c.get("effects")), c.get("cost"), c.get("name_ko"), c.get("star_cost"))
                               for c in cards))
    if key not in _CACHE:
        import ingame
        ims = []
        for c in cards:
            try:
                im = ingame.compose(assets, project, "card", c, lang, k=1)
            except Exception:  # noqa: BLE001
                im = None
            ims.append(im)
        _CACHE[key] = ims
    ims = _CACHE[key]
    n = len(ims)
    for i, im in enumerate(ims):
        if im is None:
            continue
        off = i - (n - 1) / 2
        sc = 0.62
        card = im.resize((int(im.width * sc), int(im.height * sc)), Image.LANCZOS).rotate(-off * 4, expand=True,
                                                                                        resample=Image.BICUBIC)
        x = 960 + off * 180 - card.width / 2
        y = 1080 - card.height * 0.62 + abs(off) * 10
        img.alpha_composite(card, (int(x), int(y)))


def button_image(assets, b, state="normal", value_text="", lang="ko"):
    """모드 버튼 (Godot Button + StyleBoxFlat: 모서리 10, 테두리 2, 글자 외곽선 5)."""
    w, h = int(b.get("w", 190) or 190), int(b.get("h", 70) or 70)
    im = Image.new("RGBA", (w + 4, h + 4), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)

    def rgb(hexcol, a=255):
        hcol = (hexcol or "#000000").lstrip("#")
        try:
            return tuple(int(hcol[i:i + 2], 16) for i in (0, 2, 4)) + (a,)
        except ValueError:
            return (0, 0, 0, a)
    bg, border, text = rgb(b.get("bg"), 230), rgb(b.get("border")), rgb(b.get("text"))
    if state == "hover":
        bg = tuple(int(c + (255 - c) * 0.18) for c in bg[:3]) + (242,)
        border = (255, 255, 255, 255)
    elif state == "disabled":
        bg, border = (20, 20, 26, 191), tuple(int(c * 0.5) for c in border[:3]) + (255,)
        text = (150, 145, 160, 255)
    d.rounded_rectangle((2, 2, w + 1, h + 1), 10, fill=bg, outline=border, width=2)
    label = btn_text(b, "label", lang)
    sub = btn_text(b, "sub", lang).replace("#", value_text)
    fk = font_for(label + sub, lang)
    main_y = h / 2 + 2 - (10 if sub else 0)
    _label(im, assets, label, (w / 2 + 2, main_y), 20, color=text, outline=(0, 0, 0), outline_w=3, font=fk)
    if sub:
        _label(im, assets, sub, (w / 2 + 2, main_y + 22), 14, color=border if state != "disabled" else text,
               outline=(0, 0, 0), outline_w=2, font=fk)
    return im


def tip_image(assets, title, desc, lang="ko"):
    import ingame
    key = ("tip", title, desc, lang)
    if key not in _CACHE:
        try:
            im = ingame.compose_hover_tip(assets, title, desc, lang)
            _CACHE[key] = im.resize((im.width // 2, im.height // 2), Image.LANCZOS)
        except Exception:  # noqa: BLE001
            _CACHE[key] = None
    return _CACHE[key]


def power_icon(project, key):
    """자원 파워 아이콘 (그림이 없으면 색 원)."""
    import modgen as M
    if not key:
        return None
    ck = ("picon", key)
    if ck in _CACHE:
        return _CACHE[ck]
    im = None
    if key.startswith("c:"):
        p = next((x for x in project.get("powers", []) if x["id"] == key[2:]), None)
        if p and p.get("image"):
            try:
                im = Image.open(p["image"]).convert("RGBA")
            except OSError:
                im = None
        if im is None:
            col = (76, 175, 80, 255) if (p or {}).get("type") != "Debuff" else (142, 68, 173, 255)
            im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
            ImageDraw.Draw(im).ellipse((4, 4, 60, 60), fill=col, outline=(255, 255, 255, 200), width=3)
    elif M.power_meta(project, key):
        im = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
        ImageDraw.Draw(im).ellipse((4, 4, 60, 60), fill=(200, 160, 60, 255), outline=(255, 255, 255, 200), width=3)
    _CACHE[ck] = im
    return im


def figure(path, scale=100, flip=False, lift=0):
    """사용자 그림 → 전투 화면에 세울 RGBA (pets.process_image 와 같은 처리)."""
    key = ("fig", path, scale, flip, lift)
    if key not in _CACHE:
        import pets as PT
        try:
            _CACHE[key] = PT.process_image(path, scale, flip, lift) if path else None
        except (OSError, ValueError):
            _CACHE[key] = None
    return _CACHE[key]


def _stand(img, fig, feet):
    fx, fy = feet
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).ellipse((fx - fig.width * 0.42, fy - 18, fx + fig.width * 0.42, fy + 14), fill=(0, 0, 0, 110))
    img.alpha_composite(lay)
    img.alpha_composite(fig, (int(fx - fig.width / 2), int(fy - fig.height)))


def static_layer(assets, project=None):
    """배경(16:9) + 캐릭터(그림 또는 실루엣) + 적 실루엣 (변하지 않는 부분, 캐시)."""
    ch = (project or {}).get("character") or {}
    spec = (ch.get("combat_image") or "", ch.get("combat_scale", 100), bool(ch.get("combat_flip")), ch.get("combat_lift", 0))
    key = ("static", spec)
    if key not in _CACHE:
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        fig = figure(*spec) if spec[0] else None
        if fig is not None:
            _stand(img, fig, PLAYER)
        else:
            _silhouette(img, PLAYER)
        _silhouette(img, ENEMY, enemy=True)
        _CACHE[key] = img
    return _CACHE[key]


def pet_feet(i):
    return (PLAYER[0] + 240 + i * 150, PLAYER[1] - 30)


def draw_pets(img, assets, project, st):
    import pets as PT
    for i, (pid, (hp, mx)) in enumerate((st.get("pets") or {}).items()):
        p = PT.find_pet(project, pid)
        if p is None:
            continue
        feet = pet_feet(i)
        fig = figure(p.get("image") or "", p.get("scale", 100), bool(p.get("flip")), p.get("lift", 0)) if p.get("image") else None
        if fig is None:
            key = ("petph",)
            if key not in _CACHE:
                _CACHE[key] = PT.placeholder()
            fig = _CACHE[key]
        if hp <= 0:
            fig = fig.copy()
            fig.putalpha(fig.getchannel("A").point(lambda v: v // 3))
        _stand(img, fig, feet)
        health_bar(img, assets, (feet[0] + 5, feet[1]), hp, mx)


def hand_layer(assets, project, lang="ko"):
    cards = [c for c in project.get("cards", []) if not c.get("clone")][:5]
    key = ("handlayer", lang, repr([(c["id"], c.get("effects"), c.get("cost"), c.get("x_cost"), c.get("name_ko"), c.get("star_cost"),
                                     c.get("type"), c.get("gtags"), c.get("frame_style")) for c in cards]) +
           repr(project.get("card_frames")) + repr((project.get("character") or {}).get("frame_style")))
    if key not in _CACHE:
        lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        hand(lay, assets, project, lang)
        _CACHE[key] = lay
    return _CACHE[key]


def scene(assets, project, st, lang="ko", ui=True, vw=W, vh=H):
    """시험장 상태 st 로 전투 화면을 그린다. vw×vh = 게임 안 화면 크기 (화면 비율에 따라 다름).
    게임처럼: 배경·캐릭터·적은 가운데 기준, 에너지·뽑을 더미는 왼쪽 아래, 버린 더미는 오른쪽 아래, 손패는 아래 가운데.
    턴 종료 버튼은 게임 코드처럼 화면 비율 (1604, 846)/1920×1080 자리 (모서리에 붙지 않음)."""
    img = background(assets, vw=vw, vh=vh).copy()
    dx, dy = view_offset(vw, vh)
    mid = static_layer(assets, project).copy()
    ch = project.get("character") or {}
    draw_pets(mid, assets, project, st)
    health_bar(mid, assets, PLAYER, st.get("hp", 75), st.get("maxhp", int(ch.get("hp", 75) or 75)), st.get("block", 0))
    health_bar(mid, assets, ENEMY, st.get("ehp", 60), st.get("emaxhp", 60), st.get("eblock", 0), enemy=True)
    pw = [(power_icon(project, k), v) for k, v in (st.get("res") or {}).items() if v]
    power_row(mid, assets, PLAYER, pw)
    intent(mid, assets, ENEMY, st.get("intent", 9))
    img.alpha_composite(mid, (dx, dy))
    if ui:
        by = vh - H
        piles(img, assets, vw=vw, vh=vh)
        energy(img, assets, project, st.get("energy", 3), st.get("maxenergy", 3), 0, by)
        if ch.get("show_stars") or st.get("stars"):
            stars(img, assets, st.get("stars", 0), 0, by)
        end_turn(img, assets, lang, vw, vh, st.get("turn", 1))
        img.alpha_composite(hand_layer(assets, project, lang), (dx, by))
    return img


# ---------------------------------------------------------------------------
# 블록 해석기 (시험장용)
# ---------------------------------------------------------------------------
class Sim:
    def __init__(self, project, st, log):
        self.p, self.st, self.log = project, st, log
        self.vars = {}
        self.events = []      # ("dmg", who, n) / ("fx", fx_id, who)
        self.steps = 0

    def val(self, v):
        if not isinstance(v, dict):
            return 0
        t = v.get("t")
        st = self.st
        if t == "num":
            return float(v.get("v", 0) or 0)
        if t == "op":
            a, b = self.val(v.get("a")), self.val(v.get("b"))
            o = v.get("op", "+")
            return a + b if o == "+" else a - b if o == "-" else a * b if o == "*" else (math.floor(a / b) if b else 0)
        if t == "var":
            return self.vars.get(v.get("name", "a"), 0)
        if t == "played":
            return st.get("played", 0)
        if t == "stars":
            return st.get("stars", 0)
        if t == "energy":
            return st.get("energy", 0)
        if t == "stat":
            enemy = v.get("who") in ("target", "it")
            stat = v.get("stat")
            if stat == "block":
                return st.get("eblock" if enemy else "block", 0)
            if stat == "maxhp":
                return st.get("emaxhp" if enemy else "maxhp", 0)
            return st.get("ehp" if enemy else "hp", 0)
        if t == "stack":
            return (st.get("res") or {}).get(v.get("power"), 0) if v.get("who", "self") == "self" else 0
        if t == "count":
            return 1 if v.get("what") == "enemies" else 5
        if t == "rand":
            lo, hi = int(self.val(v.get("min"))), int(self.val(v.get("max")))
            return random.randint(min(lo, hi), max(lo, hi))
        if t == "round":
            return st.get("turn", 1)
        if t == "amount":
            return 1
        if t == "pet":
            hp, mx = (st.get("pets") or {}).get(v.get("pet"), (0, 0))
            return (mx if v.get("what") == "maxhp" else hp) if hp > 0 else 0
        return 0

    def cond(self, c):
        if not isinstance(c, dict):
            return False
        t = c.get("t")
        if t == "cmp":
            a, b, o = self.val(c.get("a")), self.val(c.get("b")), c.get("op", ">=")
            return {">=": a >= b, ">": a > b, "==": a == b, "<": a < b, "<=": a <= b, "!=": a != b}.get(o, False)
        if t == "chance":
            return random.random() * 100 < self.val(c.get("pct"))
        if t == "has":
            return (self.st.get("res") or {}).get(c.get("power"), 0) > 0 if c.get("who", "self") == "self" else False
        if t == "and":
            return self.cond(c.get("a")) and self.cond(c.get("b"))
        if t == "or":
            return self.cond(c.get("a")) or self.cond(c.get("b"))
        if t == "not":
            return not self.cond(c.get("a"))
        if t == "pet_alive":
            return (self.st.get("pets") or {}).get(c.get("pet"), (0, 0))[0] > 0
        return False

    def hit(self, enemy, n):
        st = self.st
        n = max(0, int(n))
        bk, hk = ("eblock", "ehp") if enemy else ("block", "hp")
        absorbed = min(st.get(bk, 0), n)
        st[bk] = st.get(bk, 0) - absorbed
        st[hk] = max(0, st.get(hk, 0) - (n - absorbed))
        self.events.append(("dmg", "enemy" if enemy else "self", n))

    def run(self, blocks):
        import blockcode as B
        for b in blocks or []:
            self.steps += 1
            if self.steps > 500:
                return
            op, a = b.get("op"), b.get("args", {})
            st = self.st
            who = a.get("who", "self")
            enemy = who in ("target", "it", "all", "random")
            if op == "damage":
                for _ in range(max(1, int(a.get("hits", 1) or 1))):
                    self.hit(enemy, self.val(a.get("amount")))
                self.log(f"   · 피해 {int(self.val(a.get('amount')))}{'' if int(a.get('hits', 1) or 1) == 1 else ' ×' + str(a.get('hits'))} → {'적' if enemy else '나'}")
            elif op == "block":
                n = int(self.val(a.get("amount")))
                st["block"] = st.get("block", 0) + n
                self.log(f"   · 방어도 +{n}")
            elif op == "lose_block":
                k = "eblock" if enemy else "block"
                st[k] = max(0, st.get(k, 0) - int(self.val(a.get("amount"))))
            elif op == "heal":
                st["hp"] = min(st.get("maxhp", 75), st.get("hp", 75) + int(self.val(a.get("amount"))))
            elif op == "lose_hp":
                k = "ehp" if enemy else "hp"
                n = int(self.val(a.get("amount")))
                st[k] = max(0, st.get(k, 0) - n)
                self.events.append(("dmg", "enemy" if enemy else "self", n))
            elif op == "energy":
                st["energy"] = st.get("energy", 0) + int(self.val(a.get("amount")))
            elif op == "stars":
                st["stars"] = max(0, st.get("stars", 0) + int(self.val(a.get("amount"))))
                self.log(f"   · 별 → {st['stars']}")
            elif op in ("apply_power", "remove_power"):
                key = a.get("power")
                n = int(self.val(a.get("amount")))
                if not enemy:
                    res = st.setdefault("res", {})
                    if op == "apply_power":
                        res[key] = res.get(key, 0) + n
                    else:
                        res[key] = 0 if n <= 0 else max(0, res.get(key, 0) - n)
                    self.log(f"   · {_pname(self.p, key)} → {res[key]}")
                else:
                    self.log(f"   · 적에게 {_pname(self.p, key)} {n} {'부여' if op == 'apply_power' else '제거'}")
            elif op == "pay":
                key = a.get("power")
                n = int(self.val(a.get("amount")))
                res = st.setdefault("res", {})
                if res.get(key, 0) >= n:
                    res[key] = res.get(key, 0) - n
                    self.log(f"   · {_pname(self.p, key)} {n} 지불 → {res[key]}")
                    self.run(b.get("body"))
                else:
                    self.log(f"   · {_pname(self.p, key)} 부족 ({res.get(key, 0)} < {n})")
                    self.run(b.get("else"))
            elif op in ("if", "if_else"):
                if self.cond(a.get("cond")):
                    self.run(b.get("body"))
                else:
                    self.run(b.get("else"))
            elif op == "repeat":
                for _ in range(max(0, min(50, int(self.val(a.get("times")))))):
                    self.run(b.get("body"))
            elif op in ("each_enemy", "random_enemy", "delayed"):
                if op == "delayed":
                    self.log("   · (예약: 다음 턴에 실행 — 시험장에서는 지금 보여 줌)")
                self.run(b.get("body"))
            elif op == "choice":
                self.log("   · (하나 고르기: 시험장에서는 첫 번째 선택지)")
                self.run(b.get("body"))
            elif op == "set_var":
                self.vars[a.get("name", "a")] = self.val(a.get("amount"))
            elif op == "change_var":
                self.vars[a.get("name", "a")] = self.vars.get(a.get("name", "a"), 0) + self.val(a.get("amount"))
            elif op == "fx":
                self.events.append(("fx", a.get("fx"), "enemy" if enemy else "self"))
            elif op.startswith("pet_"):
                self.pet_op(op, a, b)
            elif op == "flash":
                pass
            else:
                desc = B.describe([b], self.p, "power", "ko")
                import blockui
                self.log(f"   · (시험장에서는 계산 생략) {blockui._plain(desc) or op}")


def _pet_op(self, op, a, b):
    import pets as PT
    pid = a.get("pet")
    p = PT.find_pet(self.p, pid)
    name = (p or {}).get("name_ko") or pid
    pets = self.st.setdefault("pets", {})
    hp, mx = pets.get(pid, (0, 0))
    if op == "pet_summon":
        n = int(self.val(a.get("amount")))
        if hp > 0:
            pets[pid] = (hp + n, mx + n)
            self.log(f"   · {name} 최대 체력 +{n} → {hp + n}/{mx + n}")
        else:
            pets[pid] = (n, n)
            self.log(f"   · {name} 소환 (체력 {n})" if mx == 0 else f"   · {name} 되살아남 (체력 {n})")
    elif op == "pet_attack":
        if hp <= 0:
            self.log(f"   · {name}가 없어서 공격하지 못함")
            return
        n = int(self.val(a.get("amount")))
        for _ in range(max(1, int(a.get("hits", 1) or 1))):
            self.hit(True, n)
        self.log(f"   · {name} 공격: 피해 {n} → 적")
    elif op == "pet_act":
        if hp > 0 and p:
            self.log(f"   · {name} 행동")
            self.run(p.get("blocks"))
    elif op == "pet_kill":
        if hp > 0:
            pets[pid] = (0, mx)
            self.log(f"   · {name} 희생")


Sim.pet_op = _pet_op


def _pname(project, key):
    import modgen as M
    pm = M.power_meta(project, key)
    return pm["ko"] if pm else str(key)

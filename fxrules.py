"""이펙트 · 버튼 탭의 화면과 무관한 부분 (Tk · Qt 공용): 무대 배경 모형, 도형 좌표 도우미, ID 변경 반영."""
import copy
import math

CW, CH = 900, 520                     # 무대 크기 (게임 좌표 1:1)
W_GAME, H_GAME = 1920, 1080
PLAYER_FEET = (250, 450)
ENEMY_FEET = (660, 450)

# ---------------------------------------------------------------------------
# 무대 배경 (전투 화면 모형)
# ---------------------------------------------------------------------------
_STAGE = {}
_ASSETS = {"get": None}


def _assets():
    try:
        return _ASSETS["get"]() if _ASSETS["get"] else None
    except Exception:  # noqa: BLE001
        return None


def stage_image(show_grid=True, enemy=False, project=None):
    ch = (project or {}).get("character") or {}
    key = (show_grid, enemy, ch.get("combat_image"), ch.get("combat_scale"), ch.get("combat_flip"), ch.get("combat_lift"))
    if key in _STAGE:
        return _STAGE[key].copy()
    from PIL import Image, ImageDraw
    a = _assets()
    if a is not None:
        import gamescene as GS
        full = GS.scene(a, {"character": ch, "gimmicks": {}}, {"hp": 75, "maxhp": 75, "ehp": 60, "emaxhp": 60}, ui=False)
        cx, cy = (GS.ENEMY[0] - ENEMY_FEET[0], GS.ENEMY[1] - ENEMY_FEET[1]) if enemy else \
            (GS.PLAYER[0] - PLAYER_FEET[0], GS.PLAYER[1] - PLAYER_FEET[1])
        im = full.crop((cx, cy, cx + CW, cy + CH))
        if show_grid:
            ov = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
            od = ImageDraw.Draw(ov)
            for x in range(0, CW, 50):
                od.line([(x, 0), (x, CH)], fill=(255, 255, 255, 22))
            for y in range(0, CH, 50):
                od.line([(0, y), (CW, y)], fill=(255, 255, 255, 22))
            im.alpha_composite(ov)
        _STAGE[key] = im
        return im.copy()
    im = Image.new("RGBA", (CW, CH), (0, 0, 0, 255))
    d = ImageDraw.Draw(im)
    for y in range(CH):
        k = y / CH
        d.line([(0, y), (CW, y)], fill=(int(28 + 20 * k), int(24 + 14 * k), int(44 + 10 * k), 255))
    d.rectangle((0, 455, CW, CH), fill=(36, 30, 40, 255))
    d.line([(0, 455), (CW, 455)], fill=(70, 60, 74, 255), width=2)
    if show_grid:
        ov = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for x in range(0, CW, 50):
            od.line([(x, 0), (x, CH)], fill=(255, 255, 255, 18))
        for y in range(0, CH, 50):
            od.line([(0, y), (CW, y)], fill=(255, 255, 255, 18))
        im.alpha_composite(ov)
        d = ImageDraw.Draw(im)

    def body(fx, fy, col, flip=False):
        d.ellipse((fx - 55, fy - 12, fx + 55, fy + 8), fill=(0, 0, 0, 90))
        d.rounded_rectangle((fx - 38, fy - 190, fx + 38, fy - 40), 26, fill=col)
        d.ellipse((fx - 30, fy - 250, fx + 30, fy - 190), fill=col)
        d.rectangle((fx - 30, fy - 45, fx - 10, fy), fill=col)
        d.rectangle((fx + 10, fy - 45, fx + 30, fy), fill=col)
    body(*PLAYER_FEET, (92, 110, 160, 255))
    body(*ENEMY_FEET, (150, 80, 80, 255))
    try:
        from PIL import ImageFont
        font = ImageFont.truetype("malgun.ttf", 16)
    except OSError:
        font = None
    d.text((PLAYER_FEET[0] - 8, PLAYER_FEET[1] + 14), "나", fill=(200, 210, 240, 255), font=font)
    d.text((ENEMY_FEET[0] - 8, ENEMY_FEET[1] + 14), "적", fill=(240, 200, 200, 255), font=font)
    _STAGE[key] = im
    return im.copy()


def _offset(s, dx, dy):
    if s["type"] in ("circle", "ring", "rect", "image"):
        s["cx"] = round(float(s.get("cx", 0)) + dx, 1)
        s["cy"] = round(float(s.get("cy", 0)) + dy, 1)
    else:
        s["points"] = [[round(p[0] + dx, 1), round(p[1] + dy, 1)] for p in s.get("points") or []]


def _bbox(s):
    t = s["type"]
    if t in ("circle", "ring"):
        r = float(s.get("r", 20))
        return s["cx"] - r, s["cy"] - r, s["cx"] + r, s["cy"] + r
    if t in ("rect", "image"):
        w2, h2 = float(s.get("w", 40)) / 2, float(s.get("h", 40)) / 2
        return s["cx"] - w2, s["cy"] - h2, s["cx"] + w2, s["cy"] + h2
    pts = s.get("points") or [[0, 0]]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def _simplify(pts, tol=1.6):
    """붓 선 점을 줄인다 (Ramer-Douglas-Peucker)."""
    if len(pts) < 3:
        return pts

    def rdp(a, b, seg):
        (x1, y1), (x2, y2) = a, b
        best, idx = 0.0, -1
        L = math.hypot(x2 - x1, y2 - y1) or 1e-9
        for i, (x, y) in enumerate(seg):
            d = abs((y2 - y1) * x - (x2 - x1) * y + x2 * y1 - y2 * x1) / L
            if d > best:
                best, idx = d, i
        if best > tol:
            m = seg[idx]
            return rdp(a, m, seg[:idx]) + [m] + rdp(m, b, seg[idx + 1:])
        return []
    return [pts[0]] + rdp(pts[0], pts[-1], pts[1:-1]) + [pts[-1]]


def _rename(project, kind, old, new):
    """이펙트/버튼 ID 변경을 블록·버튼 참조에 반영."""
    key = "fx" if kind == "fx" else "button"

    def fix(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if k == key and v == old and (kind == "fx" or "label_ko" not in o):
                    o[k] = new or ""
                else:
                    fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    for k in ("cards", "relics", "potions", "powers"):
        fix(project.get(k, []))
    g = project.get("gimmicks") or {}
    for k in ("summons", "orbs"):
        fix(g.get(k, []))
    for b in g.get("buttons", []):
        if kind == "fx" and b.get("fx") == old:
            b["fx"] = new or ""
        fix(b.get("blocks", []))

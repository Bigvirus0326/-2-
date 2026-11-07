"""
게임 그대로의 미리보기.

사용자 PC에 설치된 슬레이 더 스파이어 2의 SlayTheSpire2.pck 에서 카드 틀·배너·에너지 구슬·글꼴·장면 좌표를
그때그때 읽어 와서, 게임과 같은 방식으로 카드를 합성한다. 게임 파일은 프로그램에 포함되지 않으며
읽은 결과는 이 PC의 캐시 폴더에만 저장된다.

필요: Pillow, (한국어 글꼴 압축 해제용) Python 3.14+ 의 compression.zstd 또는 zstandard 패키지
"""
from __future__ import annotations

import io
import json
import math
import os
import re
import struct
import threading

from PIL import Image, ImageDraw, ImageFont

import modgen as M
import pngmake

# 게임 코드(StsColors)에 들어 있는 글자 색
COLORS = {
    "cream": (255, 246, 226), "gold": (0xEF, 0xC8, 0x51), "blue": (0x87, 0xCE, 0xEB), "green": (0x7F, 0xFF, 0x00),
    "red": (0xFF, 0x55, 0x55), "purple": (0xEE, 0x82, 0xEE), "aqua": (0x2A, 0xEB, 0xBE), "orange": (0xFF, 0xA5, 0x18),
    "pink": (0xFF, 0x78, 0xA0),
}
K = 2  # 게임 텍스처가 2배 해상도라 2배로 합성한다


# ---------------------------------------------------------------------------
# pck 읽기
# ---------------------------------------------------------------------------
class Pck:
    def __init__(self, path):
        self.path = path
        self.files = {}
        with open(path, "rb") as f:
            if f.read(4) != b"GDPC":
                raise ValueError("Godot pck 파일이 아닙니다")
            ver, _ma, _mi, _pa = struct.unpack("<4I", f.read(16))
            flags, base, dir_off = 0, 0, None
            if ver >= 2:
                flags, base = struct.unpack("<IQ", f.read(12))
            if ver >= 3:
                dir_off, = struct.unpack("<Q", f.read(8))
                f.seek(dir_off)
            else:
                f.read(64)
            if flags & 1:
                raise ValueError("암호화된 pck 는 읽을 수 없습니다")
            n, = struct.unpack("<I", f.read(4))
            for _ in range(n):
                ln, = struct.unpack("<I", f.read(4))
                name = f.read(ln).rstrip(b"\0").decode("utf-8", "replace")
                off, size = struct.unpack("<QQ", f.read(16))
                f.read(16)
                if ver >= 2:
                    f.read(4)
                self.files[name] = (off + base, size)

    def __contains__(self, name):
        return name in self.files

    def read(self, name):
        off, size = self.files[name]
        with open(self.path, "rb") as f:
            f.seek(off)
            return f.read(size)

    def text(self, name):
        return self.read(name).decode("utf-8", "replace")


def decode_ctex(data):
    """Godot 4 CompressedTexture2D(.ctex) -> PIL RGBA"""
    if data[:4] != b"GST2":
        raise ValueError("ctex 형식이 아닙니다")
    p = 4 + 4 * 5 + 12
    dfmt, = struct.unpack_from("<I", data, p)
    p += 4
    iw, ih = struct.unpack_from("<HH", data, p)
    p += 4
    _mips, fmt = struct.unpack_from("<II", data, p)
    p += 8
    if dfmt in (1, 2):
        size, = struct.unpack_from("<I", data, p)
        return Image.open(io.BytesIO(data[p + 4:p + 4 + size])).convert("RGBA")
    pw, ph = (iw + 3) // 4 * 4, (ih + 3) // 4 * 4
    if fmt == 22:
        im = Image.frombytes("RGBA", (pw, ph), data[p:p + pw * ph], "bcn", 7)
    elif fmt == 19:
        im = Image.frombytes("RGBA", (pw, ph), data[p:p + pw * ph], "bcn", 3)
    elif fmt == 18:
        im = Image.frombytes("RGBA", (pw, ph), data[p:p + pw * ph], "bcn", 2)
    elif fmt == 17:
        im = Image.frombytes("RGBA", (pw, ph), data[p:p + pw * ph // 2], "bcn", 1)
    elif fmt == 5:
        return Image.frombytes("RGBA", (iw, ih), data[p:p + iw * ih * 4])
    elif fmt == 4:
        return Image.frombytes("RGB", (iw, ih), data[p:p + iw * ih * 3]).convert("RGBA")
    else:
        raise ValueError(f"지원하지 않는 텍스처 형식 {fmt}")
    return im.crop((0, 0, iw, ih))


def rscc_decompress(data):
    if data[:4] != b"RSCC":
        return data
    mode, bsize, total = struct.unpack_from("<III", data, 4)
    nblocks = (total + bsize - 1) // bsize
    sizes = struct.unpack_from(f"<{nblocks}I", data, 16)
    p = 16 + 4 * nblocks
    if mode == 2:
        try:
            from compression import zstd

            def dec(b):
                return zstd.decompress(b)
        except ImportError:
            import zstandard

            def dec(b):
                return zstandard.ZstdDecompressor().decompress(b, max_output_size=bsize)
    elif mode == 1:
        import zlib

        def dec(b):
            return zlib.decompress(b, -15)
    else:
        raise ValueError(f"지원하지 않는 압축 {mode}")
    out = bytearray()
    for s in sizes:
        out += dec(data[p:p + s])
        p += s
    return bytes(out[:total])


def extract_sfnt(data):
    for m in re.finditer(rb"\x00\x01\x00\x00|OTTO", data):
        p = m.start()
        num, = struct.unpack_from(">H", data, p + 4)
        if not 4 <= num <= 64:
            continue
        end, ok = 0, True
        for i in range(num):
            q = p + 12 + i * 16
            tag = data[q:q + 4]
            if len(tag) < 4 or not all(32 <= c < 127 for c in tag):
                ok = False
                break
            off, ln = struct.unpack_from(">II", data, q + 8)
            end = max(end, off + ln)
        if ok and 1000 < end and p + end <= len(data):
            return data[p:p + end]
    return None


def parse_scene_rects(tscn):
    """tscn 의 노드별 offset_left/top/right/bottom (가운데 앵커 기준)."""
    rects = {}
    for block in re.split(r"\n(?=\[node )", tscn):
        m = re.match(r'\[node name="([^"]+)"', block)
        if not m:
            continue
        vals = {k: float(v) for k, v in re.findall(r"offset_(left|top|right|bottom) = ([-\d.]+)", block)}
        if len(vals) == 4:
            rects[m.group(1)] = (vals["left"], vals["top"], vals["right"], vals["bottom"])
    return rects


# ---------------------------------------------------------------------------
# HSV 셰이더 (shaders/hsv.gdshader 와 같은 계산)
# ---------------------------------------------------------------------------
_YIQ = [[0.2989, 0.5870, 0.1140], [0.5959, -0.2774, -0.3216], [0.2115, -0.5229, 0.3114]]


def _mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)] for i in range(3)]


def _inv(m):
    a, b, c = m[0]
    d, e, f = m[1]
    g, h, i = m[2]
    det = a * (e * i - f * h) - b * (d * i - f * g) + c * (d * h - e * g)
    return [[(e * i - f * h) / det, (c * h - b * i) / det, (b * f - c * e) / det],
            [(f * g - d * i) / det, (a * i - c * g) / det, (c * d - a * f) / det],
            [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det]]


def apply_hsv(img, h, s, v):
    hue = (1.0 - h) * 2 * math.pi
    c, sn = math.cos(hue), math.sin(hue)
    hue_t = [[1, 0, 0], [0, c, -sn], [0, sn, c]]       # col.rgb *= hue_shift (행벡터 곱)
    sat = [[v, 0, 0], [0, s * v, 0], [0, 0, s * v]]
    t = _mul(_inv(_YIQ), _mul(sat, _mul(hue_t, _YIQ)))
    matrix = (t[0][0], t[0][1], t[0][2], 0, t[1][0], t[1][1], t[1][2], 0, t[2][0], t[2][1], t[2][2], 0)
    rgb = img.convert("RGB").convert("RGB", matrix)
    out = rgb.convert("RGBA")
    out.putalpha(img.getchannel("A"))
    return out


MATERIAL_HSV = {}  # 이름 -> (h,s,v)


# ---------------------------------------------------------------------------
# 게임 에셋
# ---------------------------------------------------------------------------
def default_cache_dir():
    base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~/.cache")
    return os.path.join(base, "sts2_mod_maker", "game_cache")


class GameAssets:
    def __init__(self, sts2_path, cache_dir=None):
        self.sts2_path = sts2_path
        self.pck = Pck(os.path.join(sts2_path, "SlayTheSpire2.pck"))
        try:
            with open(os.path.join(sts2_path, "release_info.json"), encoding="utf-8") as f:
                self.version = json.load(f).get("version", "unknown")
        except (OSError, ValueError):
            self.version = "unknown"
        self.cache_dir = os.path.join(cache_dir or default_cache_dir(), self.version)
        self._tex, self._fonts, self._ttf, self._loc, self._mat = {}, {}, {}, {}, {}
        self.card_rects = parse_scene_rects(self.pck.text("scenes/cards/card.tscn"))

    # ---- 텍스처 ----
    def texture(self, res):
        name = res.replace("res://", "")
        if name in self._tex:
            return self._tex[name]
        if name.endswith(".tres"):
            t = self.pck.text(name)
            base = re.search(r'path="res://([^"]+)"', t).group(1)
            r = [float(x) for x in re.search(r"region = Rect2\(([^)]*)\)", t).group(1).split(",")]
            mm = re.search(r"margin = Rect2\(([^)]*)\)", t)
            mg = [float(x) for x in mm.group(1).split(",")] if mm else [0, 0, 0, 0]
            atlas = self.texture(base)
            crop = atlas.crop((int(r[0]), int(r[1]), int(r[0] + r[2]), int(r[1] + r[3])))
            img = Image.new("RGBA", (int(r[2] + mg[2]), int(r[3] + mg[3])), (0, 0, 0, 0))
            img.paste(crop, (int(mg[0]), int(mg[1])))
        else:
            imp = self.pck.text(name + ".import")
            m = re.search(r'path(?:\.bptc|\.s3tc)?="res://([^"]+\.ctex)"', imp)
            img = decode_ctex(self.pck.read(m.group(1)))
        self._tex[name] = img
        return img

    def hsv_texture(self, res, h, s, v):
        key = ("hsv", res, round(float(h), 4), round(float(s), 4), round(float(v), 4))
        img = self._tex.get(key)
        if img is None:
            img = apply_hsv(self.texture(res), h, s, v)
            self._tex[key] = img
        return img

    def material_hsv(self, name):
        if name not in self._mat:
            t = self.pck.text(name)
            vals = dict(re.findall(r"shader_parameter/([hsv]) = ([-\d.]+)", t))
            self._mat[name] = (float(vals.get("h", 1)), float(vals.get("s", 1)), float(vals.get("v", 1)))
        return self._mat[name]

    # ---- 글꼴 ----
    FONT_FILES = {"regular": "fonts/kreon_regular.ttf", "bold": "fonts/kreon_bold.ttf",
                  "kor": "fonts/kor/GyeonggiCheonnyeonBatangBold.ttf"}

    def font_bytes(self, key):
        if key in self._ttf:
            return self._ttf[key]
        path = os.path.join(self.cache_dir, "fonts", key + ".ttf")
        if os.path.isfile(path):
            with open(path, "rb") as f:
                data = f.read()
        else:
            imp = self.pck.text(self.FONT_FILES[key] + ".import")
            fd = re.search(r'path="res://([^"]+)"', imp).group(1)
            data = extract_sfnt(rscc_decompress(self.pck.read(fd)))
            if not data:
                raise ValueError(f"글꼴을 꺼낼 수 없습니다: {key}")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(data)
        self._ttf[key] = data
        return data

    def font(self, key, size):
        k = (key, int(size))
        if k not in self._fonts:
            if key == "zh":
                self._fonts[k] = ImageFont.truetype("msyh.ttc", int(size))
            else:
                self._fonts[k] = ImageFont.truetype(io.BytesIO(self.font_bytes(key)), int(size))
        return self._fonts[k]

    def loc(self, lang, name):
        k = (lang, name)
        if k not in self._loc:
            folder = {"ko": "kor", "zh": "zhs"}.get(lang, "eng")
            try:
                self._loc[k] = json.loads(self.pck.read(f"localization/{folder}/{name}.json"))
            except (KeyError, ValueError):
                self._loc[k] = {}
        return self._loc[k]


_ASSETS = {"path": None, "obj": None, "error": None}


def get_assets(sts2_path):
    """설치 경로별로 한 번만 연다. 실패하면 None (오류는 last_error())."""
    if not sts2_path:
        _ASSETS.update(path=None, obj=None, error="슬더스2 설치 폴더가 설정되지 않았습니다.")
        return None
    if _ASSETS["path"] != sts2_path:
        try:
            _ASSETS.update(path=sts2_path, obj=GameAssets(sts2_path), error=None)
        except Exception as e:  # noqa: BLE001
            _ASSETS.update(path=sts2_path, obj=None, error=f"게임 파일을 읽을 수 없습니다: {e}")
    return _ASSETS["obj"]


def last_error():
    return _ASSETS["error"]


# ---------------------------------------------------------------------------
# 그리기 도우미
# ---------------------------------------------------------------------------
class Canvas:
    """장면 좌표(카드 가운데 = 0,0)를 픽셀로 바꿔 그리는 도화지."""

    def __init__(self, left, top, right, bottom, k=K):
        self.ox, self.oy, self.k = -left, -top, k
        self.img = Image.new("RGBA", (int((right - left) * k), int((bottom - top) * k)), (0, 0, 0, 0))

    def box(self, l, t, r, b):
        k = self.k
        return (round((l + self.ox) * k), round((t + self.oy) * k), round((r + self.ox) * k), round((b + self.oy) * k))

    def paste(self, tex, rect, mode="contain"):
        """mode: contain(비율 유지 가운데) / cover(비율 유지 꽉 채움) / stretch"""
        x1, y1, x2, y2 = self.box(*rect)
        bw, bh = max(1, x2 - x1), max(1, y2 - y1)
        tw, th = tex.size
        if mode == "stretch":
            im = _resized(tex, bw, bh)
            px, py = x1, y1
        else:
            sc = (min if mode == "contain" else max)(bw / tw, bh / th)
            nw, nh = max(1, round(tw * sc)), max(1, round(th * sc))
            im = _resized(tex, nw, nh)
            px, py = x1 + (bw - nw) // 2, y1 + (bh - nh) // 2
            if mode == "cover":
                im = im.crop((x1 - px, y1 - py, x1 - px + bw, y1 - py + bh))
                px, py = x1, y1
        self.img.alpha_composite(im, (max(0, px), max(0, py)),
                                 (max(0, -px), max(0, -py)))

    def nine_patch(self, tex, rect, left, right):
        """Godot NinePatchRect (가로만): 좌우 여백은 텍스처 픽셀 그대로, 가운데는 늘림."""
        x1, y1, x2, y2 = self.box(*rect)
        bw, bh = x2 - x1, y2 - y1
        tw, th = tex.size
        lw = max(1, round(left * self.k))
        rw = max(1, round(right * self.k))
        parts = [(tex.crop((0, 0, left, th)), lw), (tex.crop((left, 0, tw - right, th)), max(1, bw - lw - rw)),
                 (tex.crop((tw - right, 0, tw, th)), rw)]
        x = x1
        for part, w in parts:
            self.img.alpha_composite(part.resize((w, bh), Image.LANCZOS), (x, y1))
            x += w


# 같은 텍스처를 같은 크기로 줄인 결과는 저장해 두고 다시 쓴다 (카드마다 틀·띠를 다시 줄이지 않게)
_RESIZE_CACHE = {}


def _resized(tex, w, h):
    if tex.size == (w, h):
        return tex
    key = (id(tex), tex.size, w, h)
    hit = _RESIZE_CACHE.get(key)
    if hit is not None and hit[0] is tex:
        return hit[1]
    im = tex.resize((w, h), Image.LANCZOS)
    if len(_RESIZE_CACHE) > 600:
        _RESIZE_CACHE.clear()
    _RESIZE_CACHE[key] = (tex, im)      # tex 를 함께 붙잡아 두어 id 가 재사용되지 않게 한다
    return im


def _rgba(c, a=255):
    return (c[0], c[1], c[2], c[3] if len(c) > 3 else a)


def draw_label(cv, text, rect, font, color, outline=None, outline_size=0, shadow=None, shadow_off=(2, 2),
               align="center"):  # align: center / left / right
    """게임 Label 처럼 가운데 정렬 + 외곽선 + 그림자."""
    x1, y1, x2, y2 = cv.box(*rect)
    stroke = max(1, round(outline_size / 8 * cv.k)) if outline else 0
    bb = font.getbbox(text, stroke_width=stroke)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    asc, desc = font.getmetrics()
    if align == "center":
        x = x1 + ((x2 - x1) - font.getlength(text)) / 2
    elif align == "right":
        x = x2 - font.getlength(text)
    else:
        x = x1
    y = y1 + ((y2 - y1) - (asc + desc)) / 2
    layer = Image.new("RGBA", cv.img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    if shadow:
        sh = Image.new("RGBA", cv.img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).text((x + shadow_off[0] * cv.k, y + shadow_off[1] * cv.k), text, font=font,
                                fill=_rgba(shadow[:3]), stroke_width=stroke, stroke_fill=_rgba(shadow[:3]))
        a = sh.getchannel("A").point(lambda v: int(v * shadow[3] / 255))
        sh.putalpha(a)
        cv.img.alpha_composite(sh)
    d.text((x, y), text, font=font, fill=_rgba(color), stroke_width=stroke,
           stroke_fill=_rgba(outline) if outline else None)
    cv.img.alpha_composite(layer)
    return tw, th


_TAG = re.compile(r"\[(/?)([a-z_]+)(?:[= ][^\]]*)?\]")


def _runs(s):
    runs, stack, pos = [], [], 0
    for m in _TAG.finditer(s):
        if m.start() > pos:
            runs.append((s[pos:m.start()], list(stack)))
        if m.group(1):
            for i in range(len(stack) - 1, -1, -1):
                if stack[i] == m.group(2):
                    del stack[i]
                    break
        else:
            stack.append(m.group(2))
        pos = m.end()
    if pos < len(s):
        runs.append((s[pos:], list(stack)))
    return runs


def draw_rich(cv, assets, text, rect, font_key, max_size, min_size, color, line_sep=-3, shadow=(0, 0, 0, 64),
              energy_icon=None, align="center", valign="center", shadow_off=(2, 2), measure_only=False, pad=(0, 0)):
    """게임 RichTextLabel(가운데 정렬, 세로 가운데, 글자 크기 자동 축소)."""
    x1, y1, x2, y2 = cv.box(*rect)
    width, height = x2 - x1, y2 - y1
    runs = _runs(text)

    def layout(size):
        font = assets.font(font_key, size * cv.k)
        bold = assets.font("bold" if font_key == "regular" else font_key, size * cv.k)
        lines, cur, cw = [], [], 0.0
        space = font.getlength(" ")
        for txt, tags in runs:
            col = color
            for t in tags:
                if t in COLORS:
                    col = COLORS[t]
            f = bold if "b" in tags else font
            if "energy" in tags:
                try:
                    n = int(txt)
                except ValueError:
                    n = 1
                isz = round(size * cv.k * 1.05)
                for _ in range(max(1, min(n, 9))):
                    if cw + isz > width and cur:
                        lines.append((cur, cw))
                        cur, cw = [], 0.0
                    cur.append(("icon", isz, None, None))
                    cw += isz
                continue
            for tok in re.findall(r"\n| +|[\u3400-\u9fff]|[^ \n\u3400-\u9fff]+", txt):
                if tok == "\n":
                    lines.append((cur, cw))
                    cur, cw = [], 0.0
                    continue
                if tok.strip() == "":
                    if cur:
                        cur.append(("space", space * len(tok), None, None))
                        cw += space * len(tok)
                    continue
                w = f.getlength(tok)
                if cw + w > width and cur:
                    while cur and cur[-1][0] == "space":
                        cw -= cur[-1][1]
                        cur.pop()
                    lines.append((cur, cw))
                    cur, cw = [], 0.0
                cur.append(("text", w, tok, (f, col)))
                cw += w
        lines.append((cur, cw))
        asc, desc = font.getmetrics()
        extra = (pad[0] + pad[1]) * cv.k
        lh = asc + desc + extra + line_sep * cv.k
        return lines, lh, asc + desc + extra, font

    size = max_size
    while True:
        lines, lh, fh, font = layout(size)
        total = lh * (len(lines) - 1) + fh
        widest = max((w for _, w in lines), default=0)
        if (total <= height and widest <= width) or size <= min_size:
            break
        size -= 1
    if measure_only:
        return total / cv.k
    y = y1 + (height - total) / 2 if valign == "center" else y1
    sh_layer = Image.new("RGBA", cv.img.size, (0, 0, 0, 0))
    tx_layer = Image.new("RGBA", cv.img.size, (0, 0, 0, 0))
    sd, td = ImageDraw.Draw(sh_layer), ImageDraw.Draw(tx_layer)
    sox, soy = shadow_off[0] * cv.k, shadow_off[1] * cv.k
    y += pad[0] * cv.k
    for items, lw in lines:
        x = x1 + (width - lw) / 2 if align == "center" else x1
        for kind, w, tok, st in items:
            if kind == "text":
                f, col = st
                sd.text((x + sox, y + soy), tok, font=f, fill=(0, 0, 0, 255))
                td.text((x, y), tok, font=f, fill=_rgba(col))
            elif kind == "icon" and energy_icon is not None:
                ic = energy_icon.resize((round(w), round(w)), Image.LANCZOS)
                tx_layer.alpha_composite(ic, (round(x), round(y + (fh - w) / 2)))
            x += w
        y += lh
    if shadow:
        sh_layer.putalpha(sh_layer.getchannel("A").point(lambda v: int(v * shadow[3] / 255)))
        cv.img.alpha_composite(sh_layer)
    cv.img.alpha_composite(tx_layer)
    return total / cv.k


# ---------------------------------------------------------------------------
# 카드 합성
# ---------------------------------------------------------------------------
_PLACEHOLDER = {}


def _mod_placeholder_art():
    """그림이 없을 때 게임에서 실제로 보이는 것 = 모드의 임시 그림(card.png)"""
    if "card" not in _PLACEHOLDER:
        import tempfile
        p = os.path.join(tempfile.gettempdir(), "sts2_mod_maker_card_placeholder.png")
        if not os.path.isfile(p):
            pngmake.write_png(p, 250, 190, "rect", "#6b7a8f")
        _PLACEHOLDER["card"] = Image.open(p).convert("RGBA")
    return _PLACEHOLDER["card"]


_IMG_CACHE = {}


def _open_user_image(path):
    try:
        if path and os.path.isfile(path):
            key = (path, os.path.getmtime(path))
            img = _IMG_CACHE.get(key)
            if img is None:
                if len(_IMG_CACHE) > 400:
                    _IMG_CACHE.clear()
                img = Image.open(path).convert("RGBA")
                _IMG_CACHE[key] = img
            return img
    except Exception:  # noqa: BLE001
        pass
    return None


def energy_icons(assets, project, item=None):
    """(카드 구슬, 설명 글자용) 에너지 아이콘 — 생성되는 모드와 같은 규칙. 다른 모드 항목은 그 모드의 것."""
    if item is not None and ("_energy_big" in item or "_colorless" in item):
        big = _open_user_image(item.get("_energy_big"))
        small = _open_user_image(item.get("_energy_small"))
        if big is None:
            big = assets.texture("images/atlases/ui_atlas.sprites/card/energy_colorless.tres")
        if small is None:
            small = assets.texture("images/packed/sprite_fonts/colorless_energy_icon.png")
        return big, small
    ch = project["character"]
    if ch.get("enabled"):
        big = _open_user_image(ch.get("energy_icon_image"))
        small = _open_user_image(ch.get("energy_text_icon_image"))
        ph = ch.get("placeholder", "ironclad")
        if big is None:
            big = assets.texture(f"images/atlases/ui_atlas.sprites/card/energy_{ph}.tres")
        if small is None:
            small = assets.texture(f"images/packed/sprite_fonts/{ph}_energy_icon.png")
        return big, small
    return (assets.texture("images/atlases/ui_atlas.sprites/card/energy_colorless.tres"),
            assets.texture("images/packed/sprite_fonts/colorless_energy_icon.png"))


def energy_outline_color(project):
    ch = project["character"]
    if ch.get("enabled"):
        return M.energy_outline_color(ch)
    return "#2b2b2b"


def _hex(c):
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


# 실제 게임 카드 렌더(여러 장, 영어·한국어)와 픽셀 단위로 비교해 맞춘 보정값.
# 장면 파일(card.tscn) 값과 실제 화면이 다른 부분만 고친다. 단위: 장면 좌표.
CAL_BANNER_DY = -11       # 제목 띠
CAL_TITLE_DY = -10        # 제목 글자
CAL_DESC_DY = -8.5        # 설명 글상자
CAL_DESC_SIZE = 19        # 설명 기본 글자 크기
CAL_ENERGY = (-166.5, -229.0, 54.0)  # 에너지 구슬 왼쪽, 위, 크기
CAL_TYPE_SIZE = 15        # 종류 명패 글자 크기
KOR_PAD = (2.25, 2.25)    # 한국어 글꼴 줄 위아래 여백
KOR_TITLE_SCALE = 0.86    # 한국어 제목 글자 크기 비율
KOR_TITLE_DY = -3         # 한국어 제목 위치


def text_pad(lang):
    return KOR_PAD if lang == "ko" else (0, 0)


def _shift(rect, dy):
    return (rect[0], rect[1] + dy, rect[2], rect[3] + dy)


def compose_card(assets, project, card, lang="ko", upgraded=False, k=K):
    """게임과 같은 카드 이미지(PIL RGBA, 장면 좌표 2배 크기)."""
    import preview as PV  # 설명 변수 채우기 재사용
    R = assets.card_rects
    cv = Canvas(-172, -232, 172, 228, k)
    ctype = card.get("type", "Attack").lower()
    ch = project["character"]
    frame = assets.texture(f"images/atlases/ui_atlas.sprites/card/card_frame_{ctype}_s.tres")
    if card.get("_hsv"):
        fh = tuple(card["_hsv"])
    elif card.get("_colorless") or not ch.get("enabled"):
        fh = assets.material_hsv("materials/cards/frames/card_frame_colorless_mat.tres")
    else:
        fh = (float(ch.get("card_h", 1)), float(ch.get("card_s", 1)), float(ch.get("card_v", 1)))
    rarity = {"Basic": "common", "Common": "common", "Uncommon": "uncommon", "Rare": "rare"}.get(card.get("rarity"), "common")
    bh = assets.material_hsv(f"materials/cards/banners/card_banner_{rarity}_mat.tres")
    # 카드 테두리 디자인 (모드가 게임에서 하는 것과 같게: 색 = hsv 셰이더, 내 그림 = 셰이더 없이)
    import cardframe as CF
    style = card.get("_frame_style") if "_frame_style" in card else CF.effective(project, card)
    ctype_cap = card.get("type", "Attack") if card.get("type") in CF.TYPES else "Skill"

    def styled(part, default_hsv):
        """(내 그림 또는 None, 쓸 hsv)"""
        if not style:
            return None, default_hsv
        sp = style[part]
        if sp.get("mode") == "color":
            return None, tuple(float(x) for x in sp.get("hsv", [1, 1, 1])[:3])
        if sp.get("mode") == "image":
            im = _open_user_image(CF.image_for(style, part, ctype_cap))
            if im is not None:
                return im, None
        return None, default_hsv
    frame_img, fh = styled("frame", fh)
    border_img, border_h = styled("border", bh)
    banner_img, banner_h = styled("banner", bh)
    plaque_h = banner_h if (style and style.get("plaque_follows", True) and style["banner"].get("mode") == "color") else bh
    if frame_img is not None:
        frame = frame_img
        frame_c = frame_img
    else:
        frame_c = assets.hsv_texture(f"images/atlases/ui_atlas.sprites/card/card_frame_{ctype}_s.tres", *fh)

    # 그림자
    shadow = assets._tex.get(("shadow", ctype)) if frame_img is None else None
    if shadow is None:
        shadow = Image.new("RGBA", frame.size, (0, 0, 0, 0))
        shadow.putalpha(frame.convert("RGBA").getchannel("A").point(lambda v: v * 64 // 255))
        if frame_img is None:
            assets._tex[("shadow", ctype)] = shadow
    cv.paste(shadow, R.get("Shadow", (-138, -199, 162, 223)))
    # 그림
    art = _open_user_image(card.get("image")) or _mod_placeholder_art()
    cv.paste(art, R.get("Portrait", (-125, -168, 125, 22)), "contain")
    # 틀
    cv.paste(frame_c, R.get("Frame", (-150, -211, 150, 211)), "contain")
    # 설명
    kwl = assets.loc(lang, "card_keywords")
    kws = M.card_keywords(card, upgraded)

    def kwname(k):
        return kwl.get(f"{k.upper()}.title", k)

    # 게임처럼 키워드마다 한 줄 (설명 위: 사용불가·선천성·보존·교활·휘발성 / 아래: 소멸·영구)
    before = [f"[gold]{kwname(k)}[/gold]." for k in M.KEYWORDS_BEFORE if k in kws]
    after = [f"[gold]{kwname(k)}[/gold]." for k in M.KEYWORDS_AFTER if k in kws]
    body = PV.fill_values(project, M.description(project, card, "card", lang), card, upgraded)
    full = "\n".join(before + ([body] if body else []) + after)
    fkey = {"zh": "zh", "ko": "kor"}.get(lang, "regular")
    _big_e, small_e = energy_icons(assets, project, card)
    draw_rich(cv, assets, full, _shift(R.get("DescriptionLabel", (-122, 37, 121, 173)), CAL_DESC_DY), fkey,
              CAL_DESC_SIZE, 12, COLORS["cream"], line_sep=-3, pad=text_pad(lang), energy_icon=small_e)
    # 그림 테두리 / 제목 띠 (희귀도 색)
    pb = assets.texture(f"images/atlases/ui_atlas.sprites/card/card_portrait_border_{ctype}_s.tres")
    cv.paste(border_img if border_img is not None else
             assets.hsv_texture(f"images/atlases/ui_atlas.sprites/card/card_portrait_border_{ctype}_s.tres", *border_h),
             R.get("PortraitBorder", (-137.5, -164, 137.5, 46)), "contain")
    banner = assets.texture("images/atlases/ui_atlas.sprites/card/card_banner.tres")
    cv.paste(banner_img if banner_img is not None else
             assets.hsv_texture("images/atlases/ui_atlas.sprites/card/card_banner.tres", *banner_h),
             _shift(R.get("TitleBanner", (-163, -207, 164, -124)), CAL_BANNER_DY), "cover")
    # 제목
    title = M.text(card, "name", lang) + ("+" if upgraded else "")
    tr = _shift(R.get("TitleLabel", (-105, -204, 105, -150)), CAL_TITLE_DY + (KOR_TITLE_DY if lang == "ko" else 0))
    size = round(26 * KOR_TITLE_SCALE) if lang == "ko" else 26
    while size > 12:
        f = assets.font(fkey, size * cv.k)
        if f.getlength(title) <= (tr[2] - tr[0]) * cv.k:
            break
        size -= 1
    draw_label(cv, title, tr, assets.font(fkey, size * cv.k), COLORS["green"] if upgraded else COLORS["cream"],
               outline=(77, 75, 64), outline_size=12, shadow=(0, 0, 0, 48))
    # 종류 명패
    tname = assets.loc(lang, "gameplay_ui").get(f"CARD_TYPE.{card.get('type', 'Attack').upper()}", card.get("type"))
    tfont = assets.font("bold" if fkey == "regular" else fkey, CAL_TYPE_SIZE * cv.k)
    pr = R.get("TypePlaque", (-30.5, 1, 30.5, 38))
    need = tfont.getlength(tname) / cv.k + 20
    half = max((pr[2] - pr[0]) / 2, need / 2)
    plaque = assets.texture("images/ui/cards/card_portrait_border_plaque2.png")
    cv.nine_patch(assets.hsv_texture("images/ui/cards/card_portrait_border_plaque2.png", *plaque_h),
                  (-half, pr[1], half, pr[3]), 13, 12)
    draw_label(cv, tname, (-half, pr[1], half, pr[3]), tfont, (0, 0, 0, 192), shadow=None)
    # 에너지 비용
    big_e, _ = energy_icons(assets, project, card)
    el_, et_, es_ = CAL_ENERGY
    er = (el_, et_, el_ + es_, et_ + es_)
    cv.paste(big_e, er)
    cost = "?" if card.get("cost_unknown") else "X" if card.get("x_cost") else         int(card.get("upgrade_cost" if upgraded else "cost", 0) or 0)
    changed = upgraded and not card.get("cost_unknown") and not card.get("x_cost") and         int(card.get("upgrade_cost", 0)) < int(card.get("cost", 0))
    ex, ey = (er[0] + er[2]) / 2, (er[1] + er[3]) / 2
    el = (ex - 23, ey - 26, ex + 23, ey + 30)
    if changed:
        col, out = (0, 255, 0), (31, 89, 35)
    else:
        col, out = COLORS["cream"], _hex(energy_outline_color(project))
    draw_label(cv, str(cost), el, assets.font("bold", 32 * cv.k), col, outline=out,
               outline_size=16, shadow=(0, 0, 0, 48))
    # 별 비용 (리젠트처럼): card.tscn 의 StarIcon (-186,-189)~(-128,-131), energy_star.png
    sc = int(card.get("star_cost") or 0)
    if card.get("star_x") or sc > 0:
        if upgraded and not card.get("star_x"):
            sc += int(card.get("star_cost_up") or 0)
        sr = (-186.0, -189.0 + (CAL_ENERGY[1] + 229.0), -128.0, -131.0 + (CAL_ENERGY[1] + 229.0))
        try:
            cv.paste(assets.texture("images/ui/combat/energy_star.png"), sr)
        except Exception:  # noqa: BLE001 - 텍스처가 없으면 숫자만
            pass
        sx, sy = (sr[0] + sr[2]) / 2, (sr[1] + sr[3]) / 2
        draw_label(cv, "X" if card.get("star_x") else str(max(0, sc)), (sx - 14, sy - 20, sx + 14, sy + 20),
                   assets.font("bold", 26 * cv.k), (255, 246, 226), outline=(26, 94, 107), outline_size=12,
                   shadow=(0, 0, 0, 48))
    return cv.img


# ---------------------------------------------------------------------------
# 유물 / 물약 / 파워: 게임의 아이콘 + 설명 말풍선(hover_tip.tscn)
# ---------------------------------------------------------------------------
def _nine_patch_full(cv, tex, rect, l, t, r, b):
    """양방향 9분할 (가운데·가장자리는 늘림)."""
    x1, y1, x2, y2 = cv.box(*rect)
    k = cv.k
    tw, th = tex.size
    xs_src = [0, l, tw - r, tw]
    ys_src = [0, t, th - b, th]
    xs = [x1, x1 + round(l * k), x2 - round(r * k), x2]
    ys = [y1, y1 + round(t * k), y2 - round(b * k), y2]
    for i in range(3):
        for j in range(3):
            sw, sh = xs_src[i + 1] - xs_src[i], ys_src[j + 1] - ys_src[j]
            dw, dh = xs[i + 1] - xs[i], ys[j + 1] - ys[j]
            if sw <= 0 or sh <= 0 or dw <= 0 or dh <= 0:
                continue
            part = tex.crop((xs_src[i], ys_src[j], xs_src[i + 1], ys_src[j + 1])).resize((dw, dh), Image.LANCZOS)
            cv.img.alpha_composite(part, (xs[i], ys[j]))


def compose_hover_tip(assets, title, desc, lang, energy_icon=None, icon=None):
    """게임 설명 말풍선 이미지 (너비 408, 높이는 내용에 맞춤)."""
    fkey_r = {"zh": "zh", "ko": "kor"}.get(lang, "regular")
    fkey_b = {"zh": "zh", "ko": "kor"}.get(lang, "bold")
    inner_w = 408 - 22 - 45
    probe = Canvas(0, 0, 408, 2000)
    desc_h = draw_rich(probe, assets, desc, (22, 0, 22 + inner_w, 1900), fkey_r, 22, 22, COLORS["cream"],
                       line_sep=-2, align="left", valign="top", measure_only=True, pad=text_pad(lang)) if desc else 0
    tfont = assets.font(fkey_b, 22 * K)
    asc, dsc = tfont.getmetrics()
    title_h = (asc + dsc) / K
    h = max(118 + 8, 16 + title_h + desc_h + 28 + 8)
    cv = Canvas(-10, -10, 408 + 4, h + 4)
    bg = assets.texture("images/ui/hover_tip.png")
    shadow = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    shadow.putalpha(bg.getchannel("A").point(lambda v: v * 64 // 255))
    _nine_patch_full(cv, shadow, (-8, -8, 400, h - 8), 55, 43, 91, 32)
    _nine_patch_full(cv, bg, (0, 0, 408, h), 55, 43, 91, 32)
    tw = tfont.getlength(title) / K
    draw_label(cv, title, (22, 16, 22 + tw, 16 + title_h), tfont, COLORS["gold"], shadow=(0, 0, 0, 64),
               shadow_off=(3, 2), align="left")
    if icon is not None:
        isz = title_h
        cv.paste(icon, (22 + tw + 5, 16, 22 + tw + 5 + isz, 16 + isz))
    if desc:
        draw_rich(cv, assets, desc, (22, 16 + title_h, 22 + inner_w, 16 + title_h + desc_h + 4), fkey_r, 22, 22,
                  COLORS["cream"], line_sep=-2, align="left", valign="top", shadow_off=(3, 2), pad=text_pad(lang),
                  energy_icon=energy_icon)
    return cv.img


def _mod_placeholder(kind):
    """그림이 없을 때 모드가 실제로 쓰는 임시 그림 (생성기와 같은 모양)."""
    if kind not in _PLACEHOLDER:
        import tempfile
        spec = {"relic": (94, 94, "circle", "#c9a227"), "potion": (256, 256, "potion", "#4aa3df")}[kind]
        p = os.path.join(tempfile.gettempdir(), f"sts2_mod_maker_{kind}_placeholder.png")
        if not os.path.isfile(p):
            pngmake.write_png(p, *spec)
        _PLACEHOLDER[kind] = Image.open(p).convert("RGBA")
    return _PLACEHOLDER[kind]


def _power_icon(power):
    img = _open_user_image(power.get("image"))
    if img is not None:
        return img
    key = ("power", power.get("type"))
    if key not in _PLACEHOLDER:
        import tempfile
        col = "#4caf50" if power.get("type") == "Buff" else "#8e44ad"
        p = os.path.join(tempfile.gettempdir(), f"sts2_mod_maker_power_{power.get('type')}.png")
        if not os.path.isfile(p):
            pngmake.write_png(p, 64, 64, "circle", col)
        _PLACEHOLDER[key] = Image.open(p).convert("RGBA")
    return _PLACEHOLDER[key]


def _stack_with_icon(icon_img, tip, icon_size):
    """아이콘(위) + 말풍선(아래) 한 장으로."""
    w = max(tip.size[0], icon_size)
    out = Image.new("RGBA", (w, icon_size + 16 + tip.size[1]), (0, 0, 0, 0))
    if icon_img is not None:
        out.alpha_composite(icon_img, ((w - icon_img.size[0]) // 2, (icon_size - icon_img.size[1]) // 2))
    out.alpha_composite(tip, (0, icon_size + 16))
    return out


def compose_relic(assets, project, relic, lang="ko"):
    import preview as PV
    img = (_open_user_image(relic.get("image")) or _mod_placeholder("relic")).copy()
    size = 128 * K
    img.thumbnail((size, size), Image.LANCZOS)
    _big, small = energy_icons(assets, project, relic)
    desc = PV.fill_values(project, M.description(project, relic, "relic", lang), relic)
    tip = compose_hover_tip(assets, M.text(relic, "name", lang), desc, lang, energy_icon=small)
    return _stack_with_icon(img, tip, size)


def compose_potion(assets, project, potion, lang="ko"):
    import preview as PV
    img = (_open_user_image(potion.get("image")) or _mod_placeholder("potion")).copy()
    size = 128 * K
    img.thumbnail((size, size), Image.LANCZOS)
    _big, small = energy_icons(assets, project, potion)
    desc = PV.fill_values(project, M.description(project, potion, "potion", lang), potion)
    tip = compose_hover_tip(assets, M.text(potion, "name", lang), desc, lang, energy_icon=small)
    return _stack_with_icon(img, tip, size)


def compose_power(assets, project, power, lang="ko", stacks=3):
    """전투 화면의 파워 아이콘(40x40 + 수치, power.tscn) + 설명 말풍선."""
    import preview as PV
    icon = _power_icon(power)
    cv = Canvas(-60, -4, 48, 48)
    cv.paste(icon, (0, 0, 40, 40))
    if power.get("stack", "Counter") == "Counter":
        draw_label(cv, str(stacks), (-56, 21, 44, 44), assets.font("bold", 18 * K), COLORS["cream"],
                   outline=(31, 26, 21), outline_size=10, shadow=(0, 0, 0, 48), shadow_off=(3, 3), align="right")
    big_icon = cv.img.resize((cv.img.size[0] * 2, cv.img.size[1] * 2), Image.LANCZOS)
    desc = PV.fill_values(project, M.description(project, power, "power", lang), power, stacks=stacks)
    tip = compose_hover_tip(assets, M.text(power, "name", lang), desc, lang, icon=icon)
    return _stack_with_icon(big_icon, tip, big_icon.size[1])


COMPOSE_LOCK = threading.RLock()   # 글꼴(FreeType)을 여러 스레드가 동시에 쓰지 않게


def compose(assets, project, kind, item, lang="ko", upgraded=False, stacks=3, k=K):
    with COMPOSE_LOCK:
        return _compose(assets, project, kind, item, lang, upgraded, stacks, k)


def _compose(assets, project, kind, item, lang="ko", upgraded=False, stacks=3, k=K):
    if kind == "card":
        return compose_card(assets, project, item, lang, upgraded, k)
    if kind == "relic":
        return compose_relic(assets, project, item, lang)
    if kind == "potion":
        return compose_potion(assets, project, item, lang)
    return compose_power(assets, project, item, lang, stacks)

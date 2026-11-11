"""
카드 테두리 디자인 — 카드 틀(Frame) · 그림 테두리(PortraitBorder) · 제목 띠(TitleBanner) · 종류 명패(TypePlaque).

게임은 이 네 가지를 NCard 의 UpdatePortrait / Reload / UpdateTypePlaque 에서 정한다 (CardModel 쪽은 바꿀 수 없음).
그래서 생성되는 모드는 그 세 메서드 뒤에 Harmony Postfix 를 걸어, 이 모드의 카드일 때만 그림·색(셰이더)을 바꾼다.

부위마다 세 가지:
  game  : 게임 그대로 (틀은 캐릭터 색, 테두리·띠는 희귀도 색)
  color : 게임 그림에 색만 입힘 — 게임 hsv 셰이더(h,s,v). 고른 색에 맞는 h,s,v 를 정확히 계산한다.
  image : 내가 그린 PNG (종류별로 다르게 할 수 있음). 셰이더 없이 그린 색 그대로.
"""
from __future__ import annotations

import copy
import math
import os
import re

PARTS = ("frame", "border", "banner")
PART_LABEL = {"frame": "카드 틀", "border": "그림 테두리", "banner": "제목 띠"}
MODES = {"frame": [("game", "게임 그대로 (캐릭터 색)"), ("color", "색 바꾸기"), ("image", "내 그림")],
         "border": [("game", "게임 그대로 (희귀도 색)"), ("color", "색 바꾸기"), ("image", "내 그림")],
         "banner": [("game", "게임 그대로 (희귀도 색)"), ("color", "색 바꾸기"), ("image", "내 그림")]}
TYPES = ("Attack", "Skill", "Power")
IMAGE_KEYS = {"frame": ("all",) + TYPES, "border": ("all",) + TYPES, "banner": ("all",)}
# 게임 텍스처 크기 (그림을 이 크기·비율로 그리면 딱 맞음)
SIZES = {"frame": (598, 844), "border": (551, 420), "banner": (655, 170)}
# 게임 원본 텍스처 (틀·테두리는 종류별)
TEX = {"frame": "images/atlases/ui_atlas.sprites/card/card_frame_{t}_s.tres",
       "border": "images/atlases/ui_atlas.sprites/card/card_portrait_border_{t}_s.tres",
       "banner": "images/atlases/ui_atlas.sprites/card/card_banner.tres"}
# 원본 텍스처의 대표색 (불투명 픽셀 평균). 게임 파일을 못 읽을 때 쓰는 값.
BASE_RGB = {"frame": (103, 51, 54), "border": (77, 175, 181), "banner": (111, 213, 226)}
NONE, GAME = "", "_game"     # 카드의 frame_style: "" = 캐릭터 기본 따르기, "_game" = 게임 원래 테두리

ID_RE = re.compile(r"^[a-z][a-z_]*$")


# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------
def new_part(part):
    return {"mode": "game", "color": "#d4a64a" if part == "frame" else "#e05a5a", "hsv": [1.0, 1.0, 1.0],
            "images": {k: "" for k in IMAGE_KEYS[part]}}


def new_style(sid, name="새 테두리"):
    st = {"id": sid, "name": name, "plaque_follows": True}
    for p in PARTS:
        st[p] = new_part(p)
    return st


def styles(project):
    return project.setdefault("card_frames", [])


def find(project, sid):
    return next((s for s in styles(project) if s.get("id") == sid), None)


def normalize(project):
    out = []
    for s in project.get("card_frames") or []:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        d = new_style(s["id"])
        for k, v in s.items():
            if k in PARTS and isinstance(v, dict):
                part = new_part(k)
                part.update({kk: vv for kk, vv in v.items() if kk != "images"})
                part["images"].update({kk: vv for kk, vv in (v.get("images") or {}).items() if kk in IMAGE_KEYS[k]})
                d[k] = part
            elif k not in PARTS:
                d[k] = v
        out.append(d)
    project["card_frames"] = out
    project.setdefault("character", {}).setdefault("frame_style", NONE)
    for c in project.get("cards", []):
        c.setdefault("frame_style", NONE)


def effective(project, card):
    """이 카드에 실제로 쓰이는 스타일 (없으면 None)."""
    sid = (card or {}).get("frame_style") or NONE
    if sid == GAME:
        return None
    if sid == NONE:
        sid = (project.get("character") or {}).get("frame_style") or NONE
    return find(project, sid) if sid and sid != GAME else None


def options(project, for_card=True):
    """콤보 선택지."""
    head = [(NONE, "캐릭터 기본 따르기"), (GAME, "게임 원래 테두리")] if for_card else [(NONE, "게임 원래 테두리")]
    return head + [(s["id"], s.get("name") or s["id"]) for s in styles(project)]


def rename(project, old, new):
    if (project.get("character") or {}).get("frame_style") == old:
        project["character"]["frame_style"] = new or NONE
    for c in project.get("cards", []):
        if c.get("frame_style") == old:
            c["frame_style"] = new or NONE


def image_for(style, part, ctype):
    imgs = style[part].get("images") or {}
    return (imgs.get(ctype) or imgs.get("all") or "").strip()


# ---------------------------------------------------------------------------
# 색 → 게임 hsv 셰이더 값 (shaders/hsv.gdshader 와 같은 YIQ 계산을 거꾸로)
# ---------------------------------------------------------------------------
_YIQ = ((0.2989, 0.5870, 0.1140), (0.5959, -0.2774, -0.3216), (0.2115, -0.5229, 0.3114))


def _yiq(rgb):
    r, g, b = (c / 255 for c in rgb)
    return tuple(row[0] * r + row[1] * g + row[2] * b for row in _YIQ)


def hex_rgb(col):
    h = (col or "#888888").lstrip("#")
    try:
        return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return (136, 136, 136)


def hsv_for(target_hex, part, base_rgb=None):
    """원본 대표색이 target 색이 되게 하는 (h, s, v).
    셰이더: YIQ 로 바꿔 IQ 평면을 (1-h)·2π 만큼 돌리고, IQ 에 s, 전체에 v 를 곱한다."""
    yb, ib, qb = _yiq(base_rgb or BASE_RGB[part])
    yt, it_, qt = _yiq(hex_rgb(target_hex))
    v = max(0.02, yt / yb) if yb > 1e-6 else 1.0
    cb, ct = math.hypot(ib, qb), math.hypot(it_, qt)
    s = min(5.0, ct / (v * cb)) if cb > 1e-6 else 0.0
    ang = (math.atan2(qt, it_) - math.atan2(qb, ib)) % (2 * math.pi) if ct > 1e-6 else 0.0
    h = 1.0 - ang / (2 * math.pi)
    if h <= 0:
        h += 1.0
    return [round(h, 4), round(s, 4), round(v, 4)]


def base_rgb_from(assets, part):
    """게임 텍스처에서 대표색을 다시 잰다 (버전마다 다를 수 있어서)."""
    try:
        im = assets.texture(TEX[part].format(t="attack")).convert("RGBA")
        im.thumbnail((128, 128))
        px = [p for p in im.getdata() if p[3] > 200]
        if px:
            return tuple(sum(p[i] for p in px) // len(px) for i in range(3))
    except Exception:  # noqa: BLE001 - 게임 파일이 없으면 기본값
        pass
    return BASE_RGB[part]


# ---------------------------------------------------------------------------
# 편집용 원본 틀 내보내기
# ---------------------------------------------------------------------------
def export_templates(assets, folder):
    """게임 원본 틀·테두리·띠를 PNG 로 저장 (그 위에 그려서 '내 그림'으로 쓰라고)."""
    os.makedirs(folder, exist_ok=True)
    out = []
    for part in PARTS:
        kinds = ("attack", "skill", "power") if part != "banner" else ("",)
        for t in kinds:
            im = assets.texture(TEX[part].format(t=t))
            name = f"card_{part}{'_' + t if t else ''}.png"
            im.save(os.path.join(folder, name))
            out.append(name)
    return out


# ---------------------------------------------------------------------------
# 검사
# ---------------------------------------------------------------------------
def validate(project):
    errors, warnings = [], []
    seen = set()
    for s in styles(project):
        sid = s.get("id", "")
        where = f"카드 테두리 '{s.get('name') or sid}'"
        if not ID_RE.match(sid):
            errors.append(f"{where}: ID 는 영문 소문자와 _ 만 쓸 수 있습니다 ({sid!r}).")
        if sid in seen:
            errors.append(f"{where}: ID '{sid}' 가 겹칩니다.")
        seen.add(sid)
        for part in PARTS:
            p = s[part]
            if p.get("mode") == "image":
                files = [v for v in (p.get("images") or {}).values() if v]
                if not files:
                    warnings.append(f"{where}: {PART_LABEL[part]}를 '내 그림'으로 했지만 그림이 없어 게임 그림을 씁니다.")
                for f in files:
                    if not os.path.isfile(f):
                        errors.append(f"{where}: {PART_LABEL[part]} 그림 파일이 없습니다: {f}")
    ids = {s.get("id") for s in styles(project)}
    refs = [("캐릭터", (project.get("character") or {}).get("frame_style"))] + \
        [(f"카드 '{c.get('id')}'", c.get("frame_style")) for c in project.get("cards", [])]
    for where, sid in refs:
        if sid and sid != GAME and sid not in ids:
            warnings.append(f"{where}: 없는 카드 테두리 '{sid}' — 게임 원래 테두리를 씁니다.")
    if any(s[p].get("mode") == "image" for s in styles(project) for p in PARTS):
        warnings.append("카드 테두리에 '내 그림'을 쓰면 ④ 게시(dll+pck)로 그림을 담아야 게임에 보입니다 (③ 빌드만 하면 게임 그림).")
    return errors, warnings


# ---------------------------------------------------------------------------
# 생성: 그림 / C#
# ---------------------------------------------------------------------------
def file_name(style, part, key):
    return f"{style['id']}_{part}_{key.lower()}.png"


def image_jobs(project):
    """(원본 경로, 모드 안 파일 이름)."""
    jobs = []
    for s in styles(project):
        for part in PARTS:
            p = s[part]
            if p.get("mode") != "image":
                continue
            for key, src in (p.get("images") or {}).items():
                if src and os.path.isfile(src):
                    jobs.append((src, file_name(s, part, key)))
    return jobs


def _used(project):
    """실제로 쓰이는 (카드 → 스타일)."""
    import modgen as M
    out = []
    for c in project.get("cards", []):
        st = effective(project, c)
        if st:
            out.append((M.pascal(c["id"]), st["id"]))
    return out


def _cs_str(v):
    return "null" if not v else '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _cs_part(style, part):
    p = style[part]
    mode = {"game": 0, "color": 1, "image": 2}.get(p.get("mode"), 0)
    h, s, v = (float(x) for x in (p.get("hsv") or [1, 1, 1])[:3])
    names = {}
    if mode == 2:
        for key in IMAGE_KEYS[part]:
            src = ((p.get("images") or {}).get(key) or "").strip()
            names[key] = file_name(style, part, key) if src and os.path.isfile(src) else ""
    args = [str(mode), f"new Vector3({h:.4f}f, {s:.4f}f, {v:.4f}f)"] + \
        [_cs_str(names.get(k, "")) for k in ("all",) + TYPES]
    return f"new Part({', '.join(args)})"


def gen_runtime(project):
    import modgen as M
    mid = project["mod"]["id"]
    used = _used(project)
    sty = [s for s in styles(project) if any(sid == s["id"] for _c, sid in used)]
    lines = [M._header(), M.USINGS_COMMON.rstrip(), "using Godot;", "using HarmonyLib;",
             "using MegaCrit.Sts2.Core.Nodes.Cards;", f"using {mid}.{mid}Code.Extensions;", "",
             f"namespace {mid}.{mid}Code.Cards;", "",
             "// 카드 테두리 디자인: NCard 가 틀·테두리·띠·명패를 정한 직후, 이 모드의 카드면 그림/색을 바꾼다.",
             f"public static class {mid}CardFrames", "{",
             "    // Mode: 0 = 게임 그대로, 1 = 색 바꾸기(hsv 셰이더), 2 = 내 그림",
             "    private sealed record Part(int Mode, Vector3 Hsv, string? All, string? Attack, string? Skill, string? Power);",
             "    private sealed record Style(Part Frame, Part Border, Part Banner, bool PlaqueFollows);", "",
             "    private static readonly Dictionary<string, Style> Styles = new()", "    {"]
    for s in sty:
        lines.append(f'        ["{s["id"]}"] = new Style({_cs_part(s, "frame")},')
        lines.append(f'            {_cs_part(s, "border")},')
        lines.append(f'            {_cs_part(s, "banner")}, {"true" if s.get("plaque_follows", True) else "false"}),')
    lines += ["    };", "",
              "    private static readonly Dictionary<Type, string> CardStyle = new()", "    {"]
    for cls, sid in used:
        lines.append(f'        [typeof({cls})] = "{sid}",')
    lines += ["    };", "",
              '    private static readonly AccessTools.FieldRef<NCard, TextureRect> FrameRef = AccessTools.FieldRefAccess<NCard, TextureRect>("_frame");',
              '    private static readonly AccessTools.FieldRef<NCard, TextureRect> BorderRef = AccessTools.FieldRefAccess<NCard, TextureRect>("_portraitBorder");',
              '    private static readonly AccessTools.FieldRef<NCard, TextureRect> BannerRef = AccessTools.FieldRefAccess<NCard, TextureRect>("_banner");',
              '    private static readonly AccessTools.FieldRef<NCard, NinePatchRect> PlaqueRef = AccessTools.FieldRefAccess<NCard, NinePatchRect>("_typePlaque");',
              "    private static readonly Dictionary<Vector3, ShaderMaterial> Mats = new();",
              "    private static readonly Dictionary<string, Texture2D?> Texs = new();",
              "    private static Shader? _hsv;", "",
              "    private static ShaderMaterial Mat(Vector3 hsv)", "    {",
              "        if (Mats.TryGetValue(hsv, out var m)) return m;",
              '        _hsv ??= ResourceLoader.Load<Shader>("res://shaders/hsv.gdshader");',
              "        m = new ShaderMaterial { Shader = _hsv };",
              '        m.SetShaderParameter("h", hsv.X);', '        m.SetShaderParameter("s", hsv.Y);', '        m.SetShaderParameter("v", hsv.Z);',
              "        Mats[hsv] = m;", "        return m;", "    }", "",
              "    private static Texture2D? Tex(string? file)", "    {",
              "        if (string.IsNullOrEmpty(file)) return null;",
              "        if (Texs.TryGetValue(file, out var t)) return t;",
              '        var path = ("card_frames/" + file).ImagePath();',
              "        t = ResourceLoader.Exists(path) ? ResourceLoader.Load<Texture2D>(path) : null;",
              "        Texs[file] = t;", "        return t;", "    }", "",
              "    private static string? Pick(Part p, CardType type) =>",
              "        (type switch { CardType.Attack => p.Attack, CardType.Power => p.Power, _ => p.Skill }) ?? p.All;", "",
              "    private static void ApplyPart(CanvasItem? node, Part p, CardType type)", "    {",
              "        if (node == null || p.Mode == 0) return;",
              "        if (p.Mode == 1) { node.Material = Mat(p.Hsv); return; }",
              "        var tex = Tex(Pick(p, type));",
              "        if (tex == null) return;",
              "        if (node is TextureRect tr) tr.Texture = tex;",
              "        node.Material = null;", "    }", "",
              "    public static void Apply(NCard card)", "    {",
              "        var model = card.Model;",
              "        if (model == null || model.Rarity == CardRarity.Ancient) return;",
              "        if (!CardStyle.TryGetValue(model.GetType(), out var id) || !Styles.TryGetValue(id, out var st)) return;",
              "        try", "        {",
              "            var visualType = model.Type;",
              *([f"            if (global::{mid}.{mid}Code.Cards.{mid}CardKinds.TryVisualType(visualType, out var mappedType)) visualType = mappedType;"]
                if any(t.get("card_kind") for t in (project.get("gimmicks") or {}).get("tags", [])) else []),
              "            ApplyPart(FrameRef(card), st.Frame, visualType);",
              "            ApplyPart(BorderRef(card), st.Border, visualType);",
              "            ApplyPart(BannerRef(card), st.Banner, visualType);",
              "            if (st.PlaqueFollows && st.Banner.Mode == 1 && PlaqueRef(card) is { } plaque) plaque.Material = Mat(st.Banner.Hsv);",
              "        }",
              "        catch (Exception e)", "        {",
              '            MainFile.Logger.Error($"card frame: {e.Message}");', "        }", "    }", "",
              '    [HarmonyPatch(typeof(NCard), "UpdatePortrait")]',
              "    private static class PortraitPatch { private static void Postfix(NCard __instance) => Apply(__instance); }", "",
              '    [HarmonyPatch(typeof(NCard), "Reload")]',
              "    private static class ReloadPatch { private static void Postfix(NCard __instance) => Apply(__instance); }", "",
              '    [HarmonyPatch(typeof(NCard), "UpdateTypePlaque")]',
              "    private static class PlaquePatch { private static void Postfix(NCard __instance) => Apply(__instance); }",
              "}", ""]
    return "\n".join(lines)


def add_example(project, uid=None):
    """예시: 금빛 틀 + 진홍 띠."""
    sid = "golden"
    used = {s["id"] for s in styles(project)}
    i = 1
    while sid in used:
        sid = "golden_" + "abcdefghijklmnopqrstuvwxyz"[i % 26]
        i += 1
    st = new_style(sid, "금빛 테두리")
    st["frame"].update(mode="color", color="#d9a441", hsv=hsv_for("#d9a441", "frame"))
    st["banner"].update(mode="color", color="#b8323a", hsv=hsv_for("#b8323a", "banner"))
    styles(project).append(st)
    return st


def clone_style(st, new_id):
    d = copy.deepcopy(st)
    d["id"] = new_id
    d["name"] = (st.get("name") or st["id"]) + " (복사)"
    return d

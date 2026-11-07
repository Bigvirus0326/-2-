"""
직접 그린 이펙트 + 전투 화면 버튼 (카스토리스의 '폴룩스 브레스' 버튼·나비 이펙트 같은 것).

이펙트 = 도형 목록. 도형마다 모양(붓 선/직선/원/고리/사각형/다각형/그림)과 애니메이션
(시작 시각, 길이, 이동, 크기, 회전, 사라짐, 가속, 복제 수·퍼짐)을 가진다.
같은 계산을 도구 안 미리보기(파이썬)와 게임(C#, Godot Tween)이 함께 쓴다.

버튼 = 플레이어 캐릭터 옆에 뜨는 Godot 버튼. 누르면 네트워크 안전한 GameAction 으로 블록 효과를 실행한다.
켜기: 블록 '버튼 켜기' 또는 정한 유물을 가지고 전투를 시작하면 자동.
"""
from __future__ import annotations

import copy
import math

SHAPE_TYPES = [("stroke", "붓 (자유 선)"), ("line", "직선"), ("circle", "원 (채움)"), ("ring", "고리"),
               ("rect", "사각형"), ("poly", "다각형"), ("image", "그림 (PNG)")]
EASES = [("out", "점점 느리게"), ("in", "점점 빠르게"), ("inout", "부드럽게"), ("linear", "일정하게"), ("back", "튕기듯")]


def new_anim():
    return {"start": 0.0, "dur": 0.5, "move": [0, 0], "scale": 1.0, "rot": 0, "fade": 0.0, "ease": "out",
            "copies": 1, "spread": 0}


def new_shape(kind="ring", **kw):
    s = {"type": kind, "points": [], "cx": 0, "cy": 0, "r": 40, "w": 80, "h": 80, "color": "#b48cff", "alpha": 1.0,
         "width": 4, "fill": kind in ("circle", "rect", "poly"), "image": "", "anim": new_anim()}
    s.update(kw)
    return s


def new_effect(eid="new_fx"):
    return {"id": eid, "name": "새 이펙트", "x": 0, "y": -120, "z": 14,
            "shapes": [new_shape("ring", r=60, color="#b48cff", width=5, anim=dict(new_anim(), scale=1.6, dur=0.6)),
                       new_shape("circle", r=18, color="#ffffff", anim=dict(new_anim(), scale=0.2, dur=0.4))]}


def new_button(bid="new_button"):
    return {"id": bid, "label_ko": "새 버튼", "label_en": "New Button", "label_zh": "", "sub_ko": "", "sub_en": "", "sub_zh": "", "value": None,
            "tip_ko": "", "tip_en": "", "tip_zh": "", "bg": "#1a0f33", "border": "#c9baff", "text": "#f2ecff",
            "w": 190, "h": 70, "x": -95, "y": -470, "anchor": "screen", "rx": 24.5, "ry": 31.0,
            "energy_cost": 0, "res_power": "", "res_cost": 0,
            "per_turn": 1, "per_combat": 0, "cond": None, "fx": "", "auto_relic": "",
            "blocks": [{"op": "block", "args": {"amount": {"t": "num", "v": 5}}}]}


def effects(project):
    return (project.get("gimmicks") or {}).get("effects", [])


def buttons(project):
    return (project.get("gimmicks") or {}).get("buttons", [])


def find_effect(project, fid):
    return next((e for e in effects(project) if e["id"] == fid), None)


def find_button(project, bid):
    return next((b for b in buttons(project) if b["id"] == bid), None)


def normalize(g):
    out = []
    for e in g.get("effects", []):
        d = dict(new_effect(e.get("id", "x")), **e)
        d["shapes"] = [dict(new_shape(s.get("type", "ring")), **dict(s, anim=dict(new_anim(), **(s.get("anim") or {}))))
                       for s in d.get("shapes", [])]
        out.append(d)
    g["effects"] = out
    # 예전 버튼(위치 기준이 없던 때)은 캐릭터 기준 그대로
    g["buttons"] = [dict(new_button(b.get("id", "x")), **dict({"anchor": "creature"}, **b)) for b in g.get("buttons", [])]


# ---------------------------------------------------------------------------
# 애니메이션 계산 (미리보기와 C# 가 같은 규칙)
# ---------------------------------------------------------------------------
def ease(p, kind):
    p = max(0.0, min(1.0, p))
    if kind == "linear":
        return p
    if kind == "in":
        return p * p
    if kind == "inout":
        return 2 * p * p if p < 0.5 else 1 - (-2 * p + 2) ** 2 / 2
    if kind == "back":
        c1, c3 = 1.70158, 2.70158
        return 1 + c3 * (p - 1) ** 3 + c1 * (p - 1) ** 2
    return 1 - (1 - p) * (1 - p)  # out (Quad)


def pivot(s):
    t = s["type"]
    if t in ("circle", "ring", "rect", "image"):
        return float(s.get("cx", 0)), float(s.get("cy", 0))
    pts = s.get("points") or [[0, 0]]
    return sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts)


def copies_dirs(a):
    n = max(1, int(a.get("copies", 1) or 1))
    if n == 1:
        return [(0.0, 0.0)]
    return [(math.cos(2 * math.pi * i / n - math.pi / 2), math.sin(2 * math.pi * i / n - math.pi / 2)) for i in range(n)]


def state_at(s, t):
    """시각 t(초) 의 각 복제본 상태 [(dx, dy, scale, rot_rad, alpha)] — 아직 시작 전이면 []."""
    a = s.get("anim") or new_anim()
    start, dur = float(a.get("start", 0) or 0), max(0.01, float(a.get("dur", 0.5) or 0.5))
    if t < start:
        return []
    e = ease((t - start) / dur, a.get("ease", "out"))
    mx, my = (a.get("move") or [0, 0])[:2]
    sc = 1 + (float(a.get("scale", 1) or 1) - 1) * e
    rot = math.radians(float(a.get("rot", 0) or 0)) * e
    al = (1 + (float(a.get("fade", 1) if a.get("fade") is not None else 1) - 1) * e) * float(s.get("alpha", 1) or 0)
    spread = float(a.get("spread", 0) or 0)
    out = []
    for dx, dy in copies_dirs(a):
        out.append(((mx + dx * spread) * e, (my + dy * spread) * e, sc, rot, max(0.0, min(1.0, al))))
    return out


def total_time(fx):
    t = 0.0
    for s in fx.get("shapes", []):
        a = s.get("anim") or {}
        t = max(t, float(a.get("start", 0) or 0) + float(a.get("dur", 0.5) or 0.5))
    return max(0.1, t)


# ---------------------------------------------------------------------------
# 도구 안 미리보기 그리기 (PIL)
# ---------------------------------------------------------------------------
_IMG_CACHE = {}


def _rgba(hexcol, alpha):
    h = (hexcol or "#ffffff").lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r = g = b = 255
    return (r, g, b, int(255 * max(0, min(1, alpha))))


def render(fx, t, size, origin, img=None, still=False, ss=2, zoom=1.0):
    """fx 를 시각 t 로 그린 RGBA 이미지. origin = 캐릭터 발밑(세계 좌표). size = 결과 크기(화면 픽셀).
    zoom = 세계 좌표 1px 이 화면 몇 px 인지. still=True 면 모든 도형을 처음 모습으로."""
    from PIL import Image, ImageDraw
    W, H = size
    k = ss * zoom
    layer = Image.new("RGBA", (int(W * ss), int(H * ss)), (0, 0, 0, 0))
    ox, oy = origin[0] + float(fx.get("x", 0)), origin[1] + float(fx.get("y", 0))
    for s in fx.get("shapes", []):
        states = [(0.0, 0.0, 1.0, 0.0, float(s.get("alpha", 1) or 0))] if still else state_at(s, t)
        px, py = pivot(s)
        for dx, dy, sc, rot, al in states:
            if al <= 0.003:
                continue
            cs, sn = math.cos(rot), math.sin(rot)

            def tf(x, y):
                rx, ry = (x - px) * sc, (y - py) * sc
                return ((ox + px + dx + rx * cs - ry * sn) * k, (oy + py + dy + rx * sn + ry * cs) * k)
            col = _rgba(s.get("color"), al)
            sub = Image.new("RGBA", layer.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(sub)
            typ = s["type"]
            wid = max(1, int(round(float(s.get("width", 3) or 1) * sc * k)))
            if typ in ("circle", "ring"):
                cx, cy = tf(px, py)
                r = float(s.get("r", 20)) * sc * k
                if typ == "circle" or s.get("fill"):
                    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=col)
                else:
                    d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=col, width=wid)
            elif typ in ("line", "stroke"):
                pts = [tf(*p) for p in s.get("points") or []]
                if len(pts) >= 2:
                    d.line(pts, fill=col, width=wid, joint="curve")
                    rr = wid / 2
                    for q in (pts[0], pts[-1]):
                        d.ellipse((q[0] - rr, q[1] - rr, q[0] + rr, q[1] + rr), fill=col)
            elif typ in ("rect", "poly"):
                if typ == "rect":
                    w2, h2 = float(s.get("w", 40)) / 2, float(s.get("h", 40)) / 2
                    raw = [(px - w2, py - h2), (px + w2, py - h2), (px + w2, py + h2), (px - w2, py + h2)]
                else:
                    raw = [tuple(p) for p in s.get("points") or []]
                pts = [tf(*p) for p in raw]
                if len(pts) >= 3:
                    if s.get("fill", True):
                        d.polygon(pts, fill=col)
                    else:
                        d.line(pts + [pts[0]], fill=col, width=wid, joint="curve")
            elif typ == "image":
                im = _load_img(s.get("image"))
                if im is not None:
                    w = max(1, int(float(s.get("w", 80)) * sc * k))
                    h = max(1, int(float(s.get("h", 80)) * sc * k))
                    pic = im.resize((w, h), Image.LANCZOS)
                    if rot:
                        pic = pic.rotate(-math.degrees(rot), expand=True, resample=Image.BICUBIC)
                    if al < 1:
                        a_ = pic.getchannel("A").point(lambda v: int(v * al))
                        pic.putalpha(a_)
                    cx, cy = tf(px, py)
                    sub.alpha_composite(pic, (int(cx - pic.width / 2), int(cy - pic.height / 2)))
                else:
                    cx, cy = tf(px, py)
                    w2, h2 = float(s.get("w", 80)) * sc * k / 2, float(s.get("h", 80)) * sc * k / 2
                    d.rectangle((cx - w2, cy - h2, cx + w2, cy + h2), outline=(255, 120, 120, 200), width=2)
            layer.alpha_composite(sub)
    if layer.size != (int(W), int(H)):
        layer = layer.resize((int(W), int(H)), Image.LANCZOS)
    if img is not None:
        base = img.copy()
        base.alpha_composite(layer)
        return base
    return layer


def _load_img(path):
    if not path:
        return None
    if path in _IMG_CACHE:
        return _IMG_CACHE[path]
    try:
        from PIL import Image
        im = Image.open(path).convert("RGBA")
    except (OSError, ValueError):
        im = None
    _IMG_CACHE[path] = im
    return im


# ---------------------------------------------------------------------------
# C#
# ---------------------------------------------------------------------------
def _pascal(s):
    return "".join(p[:1].upper() + p[1:] for p in str(s).split("_") if p)


def _f(v):
    try:
        x = float(v or 0)
    except (TypeError, ValueError):
        x = 0.0
    return (str(int(x)) if x.is_integer() else repr(round(x, 4))) + "f"


def _col(hexcol, alpha=1.0):
    r, g, b, a = _rgba(hexcol, alpha)
    return f"new Color({_f(r / 255)}, {_f(g / 255)}, {_f(b / 255)}, {_f(a / 255)})"


def _str(s):
    return '"' + str(s or "").replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


EASE_CS = {"linear": ("Linear", "In"), "in": ("Quad", "In"), "out": ("Quad", "Out"), "inout": ("Quad", "InOut"),
           "back": ("Back", "Out")}

USINGS = """using Godot;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Context;
using MegaCrit.Sts2.Core.DevConsole;
using MegaCrit.Sts2.Core.DevConsole.ConsoleCommands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Multiplayer;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.HoverTips;
using MegaCrit.Sts2.Core.Localization;
using MegaCrit.Sts2.Core.Localization.Fonts;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Multiplayer.Serialization;
using MegaCrit.Sts2.Core.Nodes.Combat;
using MegaCrit.Sts2.Core.Nodes.HoverTips;
using MegaCrit.Sts2.Core.Nodes.Rooms;
using MegaCrit.Sts2.Core.Runs;
using MegaCrit.Sts2.Core.Saves;
using MegaCrit.Sts2.Core.Settings;
using MegaCrit.Sts2.Core.ValueProps;
"""


def gen_shape(s, i, fid):
    """도형 하나 → C# 줄 (root 에 붙이고 애니메이션)."""
    a = s.get("anim") or new_anim()
    px, py = pivot(s)
    typ = s["type"]
    col = _col(s.get("color"), float(s.get("alpha", 1) or 0))
    L = [f"        // 도형 {i + 1}: {typ}"]
    n = max(1, int(a.get("copies", 1) or 1))
    L.append(f"        for (var c_ = 0; c_ < {n}; c_++)")
    L.append("        {")
    L.append(f"            var n_ = new Node2D {{ Position = new Vector2({_f(px)}, {_f(py)}) }};")
    L.append("            root.AddChild(n_);")
    if typ in ("circle", "ring"):
        if typ == "circle" or s.get("fill"):
            L.append(f"            n_.AddChild(new Polygon2D {{ Polygon = Circle({_f(s.get('r', 20))}), Color = {col} }});")
        else:
            L.append(f"            n_.AddChild(Line(Circle({_f(s.get('r', 20))}, true), {col}, {_f(s.get('width', 3))}));")
    elif typ in ("line", "stroke"):
        pts = ", ".join(f"new Vector2({_f(p[0] - px)}, {_f(p[1] - py)})" for p in s.get("points") or [])
        L.append(f"            n_.AddChild(Line(new Vector2[] {{ {pts} }}, {col}, {_f(s.get('width', 3))}));")
    elif typ in ("rect", "poly"):
        if typ == "rect":
            w2, h2 = float(s.get("w", 40)) / 2, float(s.get("h", 40)) / 2
            raw = [(-w2, -h2), (w2, -h2), (w2, h2), (-w2, h2)]
        else:
            raw = [(p[0] - px, p[1] - py) for p in s.get("points") or []]
        pts = ", ".join(f"new Vector2({_f(x)}, {_f(y)})" for x, y in raw)
        if s.get("fill", True):
            L.append(f"            n_.AddChild(new Polygon2D {{ Polygon = new Vector2[] {{ {pts} }}, Color = {col} }});")
        else:
            L.append(f"            n_.AddChild(Line(new Vector2[] {{ {pts}, new Vector2({_f(raw[0][0])}, {_f(raw[0][1])}) }}, {col}, {_f(s.get('width', 3))}));")
    elif typ == "image":
        L.append(f'            n_.AddChild(Sprite("{fid}_{i}.png", {_f(s.get("w", 80))}, {_f(s.get("h", 80))}, {_f(s.get("alpha", 1))}));')
    mv = a.get("move") or [0, 0]
    tr, ez = EASE_CS.get(a.get("ease", "out"), ("Quad", "Out"))
    fade = a.get("fade", 1) if a.get("fade") is not None else 1
    L.append(f"            var dir_ = {n} > 1 ? Vector2.FromAngle(Mathf.Tau * c_ / {n} - Mathf.Pi / 2) : Vector2.Zero;")
    L.append(f"            Anim(n_, {_f(a.get('start', 0))}, {_f(max(0.01, float(a.get('dur', 0.5) or 0.5)))}, "
             f"new Vector2({_f(mv[0])}, {_f(mv[1])}) + dir_ * {_f(a.get('spread', 0))}, {_f(a.get('scale', 1))}, "
             f"{_f(a.get('rot', 0))}, {_f(fade)}, Tween.TransitionType.{tr}, Tween.EaseType.{ez});")
    L.append("        }")
    return L


def gen_runtime(project, extras=None):
    import blockcode as B
    import gimmick as G
    import modgen as M
    mid = project["mod"]["id"]
    up = mid.upper()
    L = [M._header(), USINGS + f"using {mid}.{mid}Code.Powers;\nusing {mid}.{mid}Code.Extensions;\n",
         f"namespace {mid}.{mid}Code.Gimmicks;", "",
         "// ===== 직접 그린 이펙트 =====",
         f"public static class {mid}Fx", "{",
         "    private static bool Off => SaveManager.Instance.PrefsSave.FastMode == FastModeType.Instant;",
         "    private static float Speed => SaveManager.Instance.PrefsSave.FastMode == FastModeType.Fast ? 0.5f : 1f;", "",
         "    public static void Play(string id, Creature? at)", "    {", "        if (at == null || Off) return;",
         "        switch (id)", "        {"]
    for e in effects(project):
        L.append(f'            case "{e["id"]}": {_pascal(e["id"])}(at); break;')
    L += ["        }", "    }", "",
          "    private static Node2D? Root(Creature creature, Vector2 offset, int z)", "    {",
          "        var node = NCombatRoom.Instance?.GetCreatureNode(creature);",
          "        if (node == null || !node.IsInsideTree()) return null;",
          f'        var root = new Node2D {{ Name = "{mid}Fx", Position = offset, ZIndex = z }};',
          "        node.AddChild(root);", "        return root;", "    }", "",
          "    private static void Done(Node2D root, float total)", "    {",
          "        root.GetTree().CreateTimer(total * Speed + 0.05f).Timeout += () =>",
          "        {", "            if (GodotObject.IsInstanceValid(root)) root.QueueFree();", "        };", "    }", "",
          "    private static Vector2[] Circle(float r, bool closed = false)", "    {",
          "        var pts = new Vector2[closed ? 41 : 40];",
          "        for (var i = 0; i < pts.Length; i++) pts[i] = Vector2.FromAngle(Mathf.Tau * i / 40f) * r;",
          "        return pts;", "    }", "",
          "    private static Line2D Line(Vector2[] pts, Color color, float width) => new()",
          "    {", "        Points = pts, DefaultColor = color, Width = width, Antialiased = true,",
          "        JointMode = Line2D.LineJointMode.Round, BeginCapMode = Line2D.LineCapMode.Round, EndCapMode = Line2D.LineCapMode.Round",
          "    };", "",
          "    private static Node2D Sprite(string file, float w, float h, float alpha)", "    {",
          "        var tex = ResourceLoader.Load<Texture2D>(file.FxImagePath());",
          "        var sp = new Sprite2D { Texture = tex, Modulate = new Color(1, 1, 1, alpha) };",
          "        if (tex != null) sp.Scale = new Vector2(w / tex.GetWidth(), h / tex.GetHeight());",
          "        return sp;", "    }", "",
          "    private static void Anim(Node2D n, float start, float dur, Vector2 move, float scale, float rotDeg, float fade,",
          "                             Tween.TransitionType trans, Tween.EaseType ease)", "    {",
          "        start *= Speed;", "        dur *= Speed;",
          "        var tw = n.CreateTween().SetParallel();",
          "        if (start > 0f)", "        {", "            n.Visible = false;",
          "            tw.TweenCallback(Callable.From(() => n.Visible = true)).SetDelay(start);", "        }",
          "        tw.TweenProperty(n, \"position\", n.Position + move, dur).SetDelay(start).SetTrans(trans).SetEase(ease);",
          "        tw.TweenProperty(n, \"scale\", Vector2.One * scale, dur).SetDelay(start).SetTrans(trans).SetEase(ease);",
          "        tw.TweenProperty(n, \"rotation\", Mathf.DegToRad(rotDeg), dur).SetDelay(start).SetTrans(trans).SetEase(ease);",
          "        tw.TweenProperty(n, \"modulate:a\", fade, dur).SetDelay(start).SetTrans(trans).SetEase(ease);",
          "    }", ""]
    for e in effects(project):
        L += [f"    // 이펙트 '{e.get('name')}'", f"    public static void {_pascal(e['id'])}(Creature at)", "    {",
              f"        var root = Root(at, new Vector2({_f(e.get('x', 0))}, {_f(e.get('y', -120))}), {int(e.get('z', 14) or 14)});",
              "        if (root == null) return;"]
        for i, s in enumerate(e.get("shapes", [])):
            L += gen_shape(s, i, e["id"])
        L += [f"        Done(root, {_f(total_time(e))});", "    }", ""]
    L += ["}", ""]

    # ===== 버튼 =====
    L += ["// ===== 전투 화면 버튼 (플레이어에게 붙는 숨은 파워가 버튼을 띄움) =====",
          f"public abstract class {mid}ButtonPower : {mid}Power", "{",
          "    public override PowerType Type => PowerType.Buff;",
          "    public override PowerStackType StackType => PowerStackType.Single;",
          "    protected override bool IsVisibleInternal => false;",
          "    public abstract int Index { get; }",
          "    public int UsesThisTurn;", "    public int UsesThisCombat;",
          f"    private {mid}ButtonUi? _ui;", "    private int _retries;",
          "    public abstract string Label { get; }", "    public abstract string Sub { get; }",
          "    public abstract string Tip { get; }",
          "    public abstract Vector2 UiPos { get; }", "    public abstract Vector2 UiSize { get; }",
          "    /// <summary>true = 화면 비율 기준 (UiRatio = 버튼 가운데의 화면 위치 0~1), false = 캐릭터를 따라다님 (UiPos)</summary>",
          "    public virtual bool ScreenAnchored => false;", "    public virtual Vector2 UiRatio => new(0.5f, 0.3f);",
          "    public abstract Color Bg { get; }", "    public abstract Color Border { get; }", "    public abstract Color TextColor { get; }",
          "    public virtual int PerTurn => 0;", "    public virtual int PerCombat => 0;", "    public virtual int EnergyCost => 0;",
          "    // 다른 파워의 상시 효과 '버튼 에너지 비용 / 턴당 횟수' 반영",
          f"    public int RealEnergyCost => Math.Max(0, EnergyCost + (Owner?.Powers.OfType<{mid}Power>().Sum(p => p.ButtonCostDelta(Index)) ?? 0));",
          f"    public int RealPerTurn => PerTurn + (Owner?.Powers.OfType<{mid}Power>().Sum(p => p.ButtonUsesDelta(Index)) ?? 0);",
          "    protected virtual bool ExtraReady() => true;",
          "    protected virtual Task PayExtra(PlayerChoiceContext choiceContext) => Task.CompletedTask;",
          "    protected virtual void PlayFx() { }",
          "    protected abstract Task Run(PlayerChoiceContext choiceContext, Creature? other);",
          '    protected static string L(string ko, string en, string zh = "") => LocManager.Instance.Language switch { "kor" => ko, "zhs" => string.IsNullOrEmpty(zh) ? en : zh, _ => en };', "",
          "    public bool CanUse()", "    {",
          "        var p = Owner?.Player;",
          "        if (p == null || Owner!.IsDead || p.PlayerCombatState == null) return false;",
          "        var cs = Owner.CombatState;", "        var cm = CombatManager.Instance;",
          "        if (cs == null || !cm.IsInProgress || cm.IsOverOrEnding || cs.CurrentSide != Owner.Side || cm.IsPlayerReadyToEndTurn(p)) return false;",
          "        if (PerTurn > 0 && UsesThisTurn >= RealPerTurn) return false;",
          "        if (PerCombat > 0 && UsesThisCombat >= PerCombat) return false;",
          "        if (p.PlayerCombatState.Energy < RealEnergyCost) return false;",
          "        return ExtraReady();", "    }", "",
          "    public async Task Press(PlayerChoiceContext choiceContext)", "    {",
          "        if (!CanUse()) return;", "        UsesThisTurn++;", "        UsesThisCombat++;",
          "        var cost_ = RealEnergyCost;",
          "        if (cost_ > 0) await PlayerCmd.LoseEnergy(cost_, Owner.Player!);",
          "        await PayExtra(choiceContext);", "        PlayFx();",
          "        await Run(choiceContext, null);", "        RefreshUi();", "    }", "",
          "    public override Task AfterApplied(Creature? applier, CardModel? cardSource)", "    {",
          "        RefreshUi();", "        return Task.CompletedTask;", "    }", "",
          "    public override Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)", "    {",
          "        if (player.Creature == Owner)", "        {", "            UsesThisTurn = 0;", "            RefreshUi();", "        }",
          "        return Task.CompletedTask;", "    }", "",
          "    public override Task AfterRemoved(Creature oldOwner)", "    {",
          "        _ui?.Dispose();", "        _ui = null;", "        return Task.CompletedTask;", "    }", "",
          "    public void RefreshUi()", "    {",
          "        var p = Owner?.Player;", "        if (p == null || !LocalContext.IsMe(p)) return;",
          "        if (_ui != null && _ui.IsValid) { _ui.Refresh(); return; }",
          "        _ui?.Dispose();", f"        _ui = {mid}ButtonUi.TryCreate(this);",
          "        if (_ui == null && _retries < 20 && Engine.GetMainLoop() is SceneTree tree)", "        {",
          "            _retries++;", "            tree.CreateTimer(0.2).Timeout += RefreshUi;", "        }",
          "        else _retries = 0;", "    }", "}", "",
          f"public sealed class {mid}ButtonUi", "{",
          f"    private readonly {mid}ButtonPower host;", "    private readonly Control root;", "    private readonly Button button;",
          "    private readonly Label main;", "    private readonly Label sub;", "    private bool hovered;", "",
          "    public bool IsValid => GodotObject.IsInstanceValid(root) && root.IsInsideTree() && host.Owner != null && host.Owner.IsAlive;", "",
          f"    public static {mid}ButtonUi? TryCreate({mid}ButtonPower host)", "    {",
          "        var c = host.Owner;", "        if (c == null) return null;",
          "        var room = NCombatRoom.Instance;",
          "        if (room == null || !room.IsInsideTree()) return null;",
          "        if (host.ScreenAnchored)",
          f"            return new {mid}ButtonUi(host, room);",
          "        var node = room.GetCreatureNode(c);",
          "        if (node == null || !node.IsInsideTree()) return null;",
          f"        return new {mid}ButtonUi(host, node);", "    }", "",
          "    /// <summary>화면 비율 기준: 전투 화면(NCombatRoom) 크기에 맞춰 위치·크기를 다시 계산 (어떤 해상도·화면 비율에서도 같은 자리)</summary>",
          "    private void Layout()", "    {",
          "        if (!host.ScreenAnchored || root.GetParent() is not Control room) return;",
          "        var size = room.Size;",
          "        if (size.X <= 0 || size.Y <= 0) return;",
          "        var s = Mathf.Min(size.X / 1920f, size.Y / 1080f);",
          "        root.Scale = Vector2.One * s;",
          "        root.Position = size * host.UiRatio - host.UiSize * s / 2f;", "    }", "",
          f"    private {mid}ButtonUi({mid}ButtonPower host, Node node)", "    {",
          "        this.host = host;",
          f'        root = new Control {{ Name = "{mid}Button" + host.Index, Position = host.UiPos, MouseFilter = Control.MouseFilterEnum.Ignore, ZIndex = 20 }};',
          "        button = new Button { CustomMinimumSize = host.UiSize, Size = host.UiSize, FocusMode = Control.FocusModeEnum.None };",
          "        var normal = new StyleBoxFlat { BgColor = host.Bg, BorderColor = host.Border, CornerRadiusTopLeft = 10, CornerRadiusTopRight = 10, CornerRadiusBottomLeft = 10, CornerRadiusBottomRight = 10 };",
          "        normal.SetBorderWidthAll(2);",
          "        var hover = (StyleBoxFlat)normal.Duplicate();",
          "        hover.BgColor = host.Bg.Lightened(0.18f);", "        hover.BorderColor = new Color(1, 1, 1);",
          "        var off = (StyleBoxFlat)normal.Duplicate();",
          "        off.BgColor = new Color(0.08f, 0.08f, 0.1f, 0.75f);", "        off.BorderColor = host.Border.Darkened(0.5f);",
          '        button.AddThemeStyleboxOverride("normal", normal);', '        button.AddThemeStyleboxOverride("hover", hover);',
          '        button.AddThemeStyleboxOverride("pressed", hover);', '        button.AddThemeStyleboxOverride("disabled", off);',
          "        var font = GameFont(node);",
          "        var box = new VBoxContainer { MouseFilter = Control.MouseFilterEnum.Ignore, Position = new Vector2(0, 4), Size = host.UiSize - new Vector2(0, 8) };",
          '        box.AddThemeConstantOverride("separation", 0);', "        box.Alignment = BoxContainer.AlignmentMode.Center;",
          "        main = MakeLabel(font, 20, host.TextColor, host.UiSize.X);",
          "        sub = MakeLabel(font, 14, host.Border, host.UiSize.X);",
          "        box.AddChild(main);", "        box.AddChild(sub);", "        button.AddChild(box);",
          "        button.Pressed += OnPressed;",
          "        button.MouseEntered += () => { hovered = true; ShowTip(); };",
          "        button.MouseExited += () => { hovered = false; NHoverTipSet.Remove(button); };",
          "        root.AddChild(button);", "        node.AddChild(root);",
          "        if (host.ScreenAnchored && node is Control rc) rc.Resized += Layout;",
          "        Layout();",
          "        var timer = new global::Godot.Timer { WaitTime = 0.15, Autostart = true };",
          "        root.AddChild(timer);", "        timer.Timeout += Refresh;", "        Refresh();", "    }", "",
          "    private static Label MakeLabel(Font? font, int size, Color color, float width)", "    {",
          "        var l = new Label { HorizontalAlignment = HorizontalAlignment.Center, MouseFilter = Control.MouseFilterEnum.Ignore, CustomMinimumSize = new Vector2(width, 0) };",
          '        l.AddThemeFontSizeOverride("font_size", size);', '        l.AddThemeColorOverride("font_color", color);',
          '        l.AddThemeConstantOverride("outline_size", 5);', '        l.AddThemeColorOverride("font_outline_color", new Color(0, 0, 0, 0.9f));',
          '        if (font != null) l.AddThemeFontOverride("font", font);', "        return l;", "    }", "",
          "    private static Font? GameFont(Node creature)", "    {",
          '        foreach (var item in creature.FindChildren("*", "Label", true, false))',
          '            if (item is Label label && label.HasThemeFontOverride("font")) return label.GetThemeFont("font");',
          "        var lang = LocManager.Instance.Language;",
          "        return FontManager.NeedsFontSubstitution(lang) ? FontManager.GetSubstituteFont(lang, FontType.Bold) : null;", "    }", "",
          "    private void OnPressed()", "    {",
          "        if (!IsValid || !host.CanUse()) return;", "        var p = host.Owner!.Player!;",
          f"        RunManager.Instance.ActionQueueSynchronizer.RequestEnqueue(new {mid}ButtonAction(p, host.Index, p.PlayerCombatState!.TurnNumber));",
          "    }", "",
          "    public void Refresh()", "    {", "        if (!GodotObject.IsInstanceValid(root)) return;",
          "        if (host.Owner == null || !host.Owner.IsAlive) { Dispose(); return; }",
          "        Layout();",
          "        main.Text = host.Label;", "        sub.Text = host.Sub;", "        sub.Visible = host.Sub.Length > 0;",
          "        button.Disabled = !host.CanUse();", "        if (hovered) ShowTip();", "    }", "",
          "    private void ShowTip()", "    {", "        if (!IsValid || host.Tip.Length == 0) return;",
          "        NHoverTipSet.Remove(button);",
          "        NHoverTipSet.CreateAndShow(button, new HoverTip(host.Title, host.Tip), HoverTipAlignment.Right);", "    }", "",
          "    public void Dispose()", "    {",
          "        if (GodotObject.IsInstanceValid(button)) NHoverTipSet.Remove(button);",
          "        if (GodotObject.IsInstanceValid(root))", "        {",
          "            if (host.ScreenAnchored && root.GetParent() is Control rc) rc.Resized -= Layout;",
          "            root.QueueFree();", "        }", "    }", "}", "",
          f"public sealed class {mid}ButtonAction(Player player, int index, int turn) : GameAction", "{",
          "    public override ulong OwnerId => player.NetId;",
          "    public override GameActionType ActionType => GameActionType.CombatPlayPhaseOnly;", "",
          "    protected override async Task ExecuteAction()", "    {",
          "        var cm = CombatManager.Instance;",
          "        if (!cm.IsInProgress || cm.IsOverOrEnding || !player.Creature.IsAlive) return;",
          "        if (player.PlayerCombatState?.TurnNumber != turn || cm.IsPlayerReadyToEndTurn(player)) return;",
          f"        var host = player.Creature.Powers.OfType<{mid}ButtonPower>().FirstOrDefault(p => p.Index == index);",
          "        if (host != null) await host.Press(new GameActionPlayerChoiceContext(this));", "    }", "",
          f"    public override INetAction ToNetAction() => new {mid}ButtonNetAction {{ index = index, turn = turn }};",
          f'    public override string ToString() => $"{mid}ButtonAction(player={{player.NetId}}, index={{index}}, turn={{turn}})";', "}", "",
          f"public struct {mid}ButtonNetAction : INetAction, IPacketSerializable", "{",
          "    public int index;", "    public int turn;",
          f"    public GameAction ToGameAction(Player player) => new {mid}ButtonAction(player, index, turn);",
          "    public void Serialize(PacketWriter writer) { writer.WriteInt(index); writer.WriteInt(turn); }",
          "    public void Deserialize(PacketReader reader) { index = reader.ReadInt(); turn = reader.ReadInt(); }",
          f'    public override string ToString() => $"{mid}ButtonNetAction(index={{index}}, turn={{turn}})";', "}", "",
          f"public static class {mid}Buttons", "{",
          "    public static async Task On(string id, Creature owner, PlayerChoiceContext? ctx = null)", "    {",
          "        ctx ??= new ThrowingPlayerChoiceContext();", "        switch (id)", "        {"]
    for b in buttons(project):
        L.append(f'            case "{b["id"]}": if (owner.GetPower<{_pascal(b["id"])}ButtonPower>() == null) '
                 f'await PowerCmd.Apply<{_pascal(b["id"])}ButtonPower>(ctx, owner, 1m, owner, null); break;')
    L += ["        }", "    }", "", "    public static async Task Off(string id, Creature owner)", "    {", "        switch (id)", "        {"]
    for b in buttons(project):
        L.append(f'            case "{b["id"]}": {{ var p = owner.GetPower<{_pascal(b["id"])}ButtonPower>(); if (p != null) await PowerCmd.Remove(p); break; }}')
    L += ["        }", "    }", "}", ""]

    # 버튼 툴팁 제목은 PowerModel.Title (이 숨은 파워의 현지화 제목 = 버튼 이름)

    for i, b in enumerate(buttons(project)):
        cls = f"{_pascal(b['id'])}ButtonPower"
        Cb = M._Ctx("power", {"id": b["id"], "trigger": "none", "enemy_mode": "all"})
        lines, _e = B.compile_blocks(b.get("blocks") or [], project, Cb, "        ", prefix=cls, extras=extras)
        g = B._Gen(project, Cb)
        g.no_vars = True
        sub_ko, sub_en, sub_zh = (btn_text(b, "sub", l) for l in ("ko", "en", "zh"))
        if isinstance(b.get("value"), dict) and any("#" in x for x in (sub_ko, sub_en, sub_zh)):
            vexpr = g.val(b["value"])
            sub = f'L({_str(sub_ko)}, {_str(sub_en)}, {_str(sub_zh)}).Replace("#", ((int)({vexpr})).ToString())'
        else:
            sub = f"L({_str(sub_ko)}, {_str(sub_en)}, {_str(sub_zh)})"
        conds = []
        rm = M.power_meta(project, b.get("res_power")) if int(b.get("res_cost") or 0) > 0 else None
        if rm:
            conds.append(f"Owner.GetPowerAmount<{rm['cls']}>() >= {int(b['res_cost'])}")
        if isinstance(b.get("cond"), dict):
            conds.append(g.cond(b["cond"]))
        L += [f"// 버튼 '{b.get('label_ko')}'", f"public sealed class {cls} : {mid}ButtonPower", "{",
              f"    public override int Index => {i};",
              f"    public override string Label => L({_str(btn_text(b, 'label', 'ko'))}, {_str(btn_text(b, 'label', 'en'))}, {_str(btn_text(b, 'label', 'zh'))});",
              f"    public override string Sub => {sub};",
              f"    public override string Tip => L({_str(btn_text(b, 'tip', 'ko'))}, {_str(btn_text(b, 'tip', 'en'))}, {_str(btn_text(b, 'tip', 'zh'))});",
              f"    public override Vector2 UiPos => new({_f(b.get('x', -95))}, {_f(b.get('y', -470))});",
              f"    public override Vector2 UiSize => new({_f(b.get('w', 190))}, {_f(b.get('h', 70))});",
              f"    public override bool ScreenAnchored => {'true' if b.get('anchor', 'creature') == 'screen' else 'false'};",
              f"    public override Vector2 UiRatio => new({_f(float(b.get('rx', 50) or 0) / 100)}, {_f(float(b.get('ry', 30) or 0) / 100)});",
              f"    public override Color Bg => {_col(b.get('bg'), 0.9)};",
              f"    public override Color Border => {_col(b.get('border'))};",
              f"    public override Color TextColor => {_col(b.get('text'))};",
              f"    public override int PerTurn => {int(b.get('per_turn') or 0)};",
              f"    public override int PerCombat => {int(b.get('per_combat') or 0)};",
              f"    public override int EnergyCost => {int(b.get('energy_cost') or 0)};"]
        if conds:
            L.append(f"    protected override bool ExtraReady() => {' && '.join(conds)};")
        if rm:
            L += ["    protected override async Task PayExtra(PlayerChoiceContext choiceContext)", "    {",
                  f"        await {G.helper(project)}.Pay<{rm['cls']}>(choiceContext, Owner, {int(b['res_cost'])}m, null);", "    }"]
        if b.get("fx") and find_effect(project, b["fx"]):
            L.append(f'    protected override void PlayFx() => {mid}Fx.Play("{b["fx"]}", Owner);')
        L += ["", "    protected override async Task Run(PlayerChoiceContext choiceContext, Creature? other)", "    {"] + lines + \
             ["    }", "}", ""]

    # ===== 개발자 콘솔 명령 (게임 안에서 바로 시험) =====
    low = mid.lower()
    L += ["// ===== 게임 안 시험용 개발자 콘솔 명령 =====",
          f"public class {mid}FxConsoleCmd : AbstractConsoleCmd", "{",
          f'    public override string CmdName => "{low}fx";',
          '    public override string Args => "<이펙트id> [enemy]";',
          '    public override string Description => "모드 메이커 이펙트를 재생합니다 (enemy: 첫 번째 적 위치)";',
          "    public override bool IsNetworked => false;",
          "    public override CmdResult Process(Player? issuingPlayer, string[] args)", "    {",
          '        if (issuingPlayer == null || issuingPlayer.Creature.CombatState == null) return new CmdResult(false, "전투 중에만 쓸 수 있습니다.");',
          '        if (args.Length == 0) return new CmdResult(false, "이펙트 id 를 적으세요.");',
          "        var at = issuingPlayer.Creature;",
          '        if (args.Length > 1 && args[1] == "enemy") at = issuingPlayer.Creature.CombatState.HittableEnemies.FirstOrDefault() ?? at;',
          f"        {mid}Fx.Play(args[0], at);",
          '        return new CmdResult(true, "재생: " + args[0]);', "    }", "}", "",
          f"public class {mid}ButtonConsoleCmd : AbstractConsoleCmd", "{",
          f'    public override string CmdName => "{low}btn";',
          '    public override string Args => "<버튼id> [off]";',
          '    public override string Description => "모드 메이커 버튼을 켜거나 끕니다";',
          "    public override bool IsNetworked => false;",
          "    public override CmdResult Process(Player? issuingPlayer, string[] args)", "    {",
          '        if (issuingPlayer == null || issuingPlayer.Creature.CombatState == null) return new CmdResult(false, "전투 중에만 쓸 수 있습니다.");',
          '        if (args.Length == 0) return new CmdResult(false, "버튼 id 를 적으세요.");',
          '        var task = args.Length > 1 && args[1] == "off"',
          f"            ? {mid}Buttons.Off(args[0], issuingPlayer.Creature)",
          f"            : {mid}Buttons.On(args[0], issuingPlayer.Creature);",
          '        return new CmdResult(task, true, "버튼: " + args[0]);', "    }", "}", ""]
    return "\n".join(L) + "\n"


def relic_members(project, relic):
    """이 유물을 가지고 전투를 시작하면 켜지는 버튼."""
    mid = project["mod"]["id"]
    ids = [b["id"] for b in buttons(project) if b.get("auto_relic") == relic["id"]]
    if not ids:
        return []
    L = ["", "    // 전투 시작 시 버튼 켜기 (모드 메이커 '버튼')", "    public override async Task BeforeCombatStartLate()", "    {"]
    for bid in ids:
        L.append(f'        await global::{mid}.{mid}Code.Gimmicks.{mid}Buttons.On("{bid}", Owner.Creature);')
    return L + ["    }"]


def btn_text(b, field, lang):
    """버튼 글자. 중국어가 비면 영어, 영어가 비면 한국어 (시험장 gamescene.btn_text 와 같은 순서)."""
    order = {"ko": ("ko", "en"), "en": ("en", "ko"), "zh": ("zh", "en", "ko")}.get(lang, ("en", "ko"))
    for l in order:
        v = (b.get(f"{field}_{l}") or "").strip()
        if v:
            return v
    return ""


def localization(project, lang, files):
    import modgen as M
    for b in buttons(project):
        lid = M.loc_id(project, b["id"] + "_button_power")
        name = btn_text(b, "label", lang) or b["id"]
        tip = btn_text(b, "tip", lang)
        files["powers"][f"{lid}.title"] = name
        files["powers"][f"{lid}.description"] = tip
        files["powers"][f"{lid}.smartDescription"] = tip


def image_jobs(project):
    """(원본, images/fx/ 안 이름)"""
    out = []
    for e in effects(project):
        for i, s in enumerate(e.get("shapes", [])):
            if s["type"] == "image":
                out.append((s.get("image") or "", f"{e['id']}_{i}.png"))
    return out


def validate(project, seen):
    import blockcode as B
    import modgen as M
    errors, warnings = [], []
    for e in effects(project):
        if not M.ID_RE.match(e.get("id", "")):
            errors.append(f"이펙트 ID '{e.get('id')}'는 영문 소문자와 _ 만 쓸 수 있습니다.")
        if e["id"] in seen:
            errors.append(f"이펙트 ID '{e['id']}'가 다른 항목과 겹칩니다.")
        seen.add(e["id"])
        if not e.get("shapes"):
            warnings.append(f"이펙트 '{e.get('name') or e['id']}'에 그린 도형이 없습니다.")
        for i, s in enumerate(e.get("shapes", [])):
            if s["type"] == "image" and not s.get("image"):
                warnings.append(f"이펙트 '{e['id']}' 도형 {i + 1}: 그림 파일이 없습니다.")
            if s["type"] in ("line", "stroke", "poly") and len(s.get("points") or []) < (3 if s["type"] == "poly" else 2):
                errors.append(f"이펙트 '{e['id']}' 도형 {i + 1}: 점이 부족합니다.")
    for b in buttons(project):
        where = f"버튼 '{b.get('label_ko') or b['id']}'"
        if not M.ID_RE.match(b.get("id", "")):
            errors.append(f"버튼 ID '{b.get('id')}'는 영문 소문자와 _ 만 쓸 수 있습니다.")
        if b["id"] in seen:
            errors.append(f"{where}: ID가 다른 항목과 겹칩니다.")
        seen.add(b["id"])
        C = M._Ctx("power", {"id": b["id"], "trigger": "none"})
        _l, e = B.compile_blocks(b.get("blocks") or [], project, C)
        errors += [f"{where}: {x}" for x in dict.fromkeys(e)]
        g = B._Gen(project, C)
        g.no_vars = True
        if isinstance(b.get("cond"), dict):
            g.cond(b["cond"])
        if isinstance(b.get("value"), dict):
            g.val(b["value"])
        errors += [f"{where} 조건/표시 값: {x}" for x in dict.fromkeys(g.errors)]
        if b.get("fx") and not find_effect(project, b["fx"]):
            errors.append(f"{where}: 없는 이펙트 '{b['fx']}'")
        if b.get("auto_relic") and not any(r["id"] == b["auto_relic"] for r in project.get("relics", [])):
            errors.append(f"{where}: 켜는 유물 '{b['auto_relic']}'가 없습니다.")
        if not b.get("auto_relic") and not any(x["op"] == "button_on" and x.get("args", {}).get("button") == b["id"]
                                               for x in _all_ops(project)):
            warnings.append(f"{where}: 켜는 방법이 없습니다 (켜는 유물을 정하거나 블록 '버튼 켜기'를 쓰세요).")
    return errors, warnings


def _all_ops(project):
    import gimmick as G
    yield from G._all_blocks(project)
    import blockcode as B
    for b in buttons(project):
        yield from B.walk(b.get("blocks") or [])


def add_examples(project, uid, blk, N):
    """카스토리스식 예시: 나비 이펙트 + 숨결 버튼."""
    g = project["gimmicks"]
    butter = new_effect(uid("butterfly_burst"))
    wing = [[0, 0], [-14, -10], [-11, 6]]
    wing2 = [[0, 0], [14, -10], [11, 6]]
    butter.update(name="나비 폭발", x=0, y=-120, shapes=[
        new_shape("ring", r=90, color="#b48cff", width=4, anim=dict(new_anim(), dur=0.9, scale=1.6, fade=0.0)),
        new_shape("ring", r=55, color="#e3d6ff", width=2, anim=dict(new_anim(), dur=0.8, scale=1.8, fade=0.0)),
        new_shape("poly", points=wing, color="#e3d6ff", anim=dict(new_anim(), dur=0.9, move=[0, -60], rot=30, fade=0.0,
                                                                   copies=10, spread=120)),
        new_shape("poly", points=wing2, color="#e3d6ff", anim=dict(new_anim(), dur=0.9, move=[0, -60], rot=-30, fade=0.0,
                                                                    copies=10, spread=120)),
        new_shape("circle", r=26, color="#ffffff", alpha=0.9, anim=dict(new_anim(), dur=0.35, scale=2.2, fade=0.0))])
    slash = new_effect(uid("moon_slash"))
    slash.update(name="달빛 베기", x=0, y=-140, shapes=[
        new_shape("stroke", points=[[-90, -60], [-40, -20], [0, 0], [40, 30], [90, 80]], color="#bfe6ff", width=10,
                  anim=dict(new_anim(), dur=0.35, scale=1.2, fade=0.0, ease="out")),
        new_shape("stroke", points=[[-70, -70], [0, -5], [80, 60]], color="#ffffff", width=4,
                  anim=dict(new_anim(), start=0.05, dur=0.3, fade=0.0))])
    g["effects"] += [butter, slash]
    pw = project.get("powers") or []
    res = next((p for p in pw if int(p.get("cap") or 0) > 0), None)
    btn = new_button(uid("breath"))
    btn.update(label_ko="숨결", label_en="Breath", sub_ko="모든 적 피해 #", sub_en="Deal # to ALL", label_zh="吐息", sub_zh="对所有敌人造成#伤害",
               value={"t": "op", "op": "+", "a": N(6), "b": {"t": "played", "scope": "turn", "filter": "Any"}},
               tip_ko="에너지 1을 써서 모든 적에게 피해를 (6 + 이번 턴 사용한 카드 수) 줍니다. 턴마다 1번.",
               tip_en="Spend 1 Energy: deal (6 + cards played this turn) damage to ALL enemies. Once per turn.",
               tip_zh="消耗1点能量：对所有敌人造成（6 + 本回合打出的牌数）点伤害。每回合1次。",
               energy_cost=1, per_turn=1, fx=butter["id"],
               blocks=[blk("damage", who="all", amount={"t": "op", "op": "+", "a": N(6),
                                                        "b": {"t": "played", "scope": "turn", "filter": "Any"}},
                           hits=1, powered=False),
                       blk("fx", fx=slash["id"], who="all")])
    ch = project.get("character") or {}
    if ch.get("enabled") and ch.get("relics"):
        btn["auto_relic"] = ch["relics"][0]
    g["buttons"].append(btn)
    del res
    out = ["이펙트 '나비 폭발'(고리 2개 + 나비 날개 10쌍이 퍼짐)", "이펙트 '달빛 베기'(붓 선 베기)",
           "버튼 '숨결'(에너지 1, 턴당 1번: 모든 적 피해 + 나비·베기 이펙트)"]
    if btn["auto_relic"]:
        out.append(f"버튼은 시작 유물 '{btn['auto_relic']}'로 전투 시작 시 자동으로 켜짐")
    return out

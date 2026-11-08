"""
골골이형 동료 (네크로바인더의 골골이처럼 전장에 서 있는 체력 있는 생물).

게임의 골골이 소환(OstyCmd.Summon)과 같은 방식:
  처음 소환 → 동료 생성(PlayerCmd.AddPet) + 체력 N / 살아 있으면 최대 체력 +N / 쓰러졌으면 되살림.
  소환량은 게임 훅(Hook.ModifySummonAmount)을 거치므로 '골골이 소환량 +' 같은 효과가 똑같이 적용된다.
  '나 대신 맞기' = 게임의 DieForYouPower (주인을 노린 공격을 동료가 대신 받음).
동료마다 그림(PNG)·크기·좌우 반전, 매 턴 행동(블록)을 정한다.

캐릭터 전투 모습도 그림 한 장으로 바꿀 수 있다 (BaseLib 의 그림 → 전투 모습 변환).
"""
from __future__ import annotations

PET_TIMINGS = [("turn_end", "내 턴 종료 시 행동"), ("turn_start", "내 턴 시작 시 행동"), ("never", "자동 행동 없음 (블록으로만)")]


def new_pet(pid="new_pet"):
    return {"id": pid, "name_ko": "새 동료", "name_en": "New Companion", "desc_ko": "", "desc_en": "",
            "image": "", "scale": 100, "flip": False, "lift": 0, "guard": True, "timing": "turn_end",
            "blocks": [{"op": "pet_attack", "args": {"pet": "", "who": "random", "amount": {"t": "num", "v": 4}, "hits": 1}}]}


def pets(project):
    return (project.get("gimmicks") or {}).get("pets", [])


def find_pet(project, pid):
    return next((p for p in pets(project) if p["id"] == pid), None)


def normalize(g):
    g["pets"] = [dict(new_pet(p.get("id", "x")), **p) for p in g.get("pets", [])]
    for p in g["pets"]:
        for b in _walk(p.get("blocks")):
            if b.get("op", "").startswith("pet_") and not (b.get("args") or {}).get("pet"):
                b.setdefault("args", {})["pet"] = p["id"]


def _walk(blocks):
    import blockcode as B
    return B.walk(blocks or [])


def _pascal(s):
    return "".join(x[:1].upper() + x[1:] for x in str(s).split("_") if x)


def ns(project):
    mid = project["mod"]["id"]
    return f"global::{mid}.{mid}Code.Gimmicks"


def pet_cls(project, pid):
    return f"{ns(project)}.{_pascal(pid)}Pet"


def act_cls(project, pid):
    return f"{ns(project)}.{_pascal(pid)}PetActPower"


def helper(project):
    mid = project["mod"]["id"]
    return f"{ns(project)}.{mid}Pets"


def _txt(it, field, lang):
    if field == "name" and lang == "zh":
        from modgen import text
        return text(it, field, lang)
    other = "en" if lang == "ko" else "ko"
    return (it.get(f"{field}_{lang}") or it.get(f"{field}_{other}") or it.get("id", "")).strip()


# ---------------------------------------------------------------------------
# 설명
# ---------------------------------------------------------------------------
def pet_text(project, p, lang):
    import blockcode as B
    custom = (p.get(f"desc_{lang}") or "").strip()
    if custom:
        return custom
    d = B.describe(p.get("blocks"), project, "power", lang)
    when = {"turn_end": ("내 턴 종료 시", "At the end of your turn"), "turn_start": ("내 턴 시작 시", "At the start of your turn"),
            "never": ("", "")}[p.get("timing", "turn_end")]
    out = []
    if d and when[0]:
        out.append(f"{when[0]}: {d}" if lang == "ko" else f"{when[1]}: {d}")
    if p.get("guard", True):
        out.append("주인을 노린 공격을 대신 받습니다." if lang == "ko" else "Takes attack damage for its owner.")
    return " ".join(out)


# ---------------------------------------------------------------------------
# C#  (Gimmicks/Pets.cs)
# ---------------------------------------------------------------------------
def gen_runtime(project, extras):
    import blockcode as B
    import fxbtn
    import modgen as M
    mid = project["mod"]["id"]
    L = [M._header(), fxbtn.USINGS + "using BaseLib.Abstracts;\nusing BaseLib.Utils.NodeFactories;\nusing MegaCrit.Sts2.Core.Hooks;\n"
         "using MegaCrit.Sts2.Core.Models.Powers;\n" + f"using {mid}.{mid}Code.Powers;\nusing {mid}.{mid}Code.Extensions;\n",
         f"namespace {mid}.{mid}Code.Gimmicks;", "",
         "// ===== 골골이형 동료 =====",
         f"public static class {mid}Pets", "{",
         "    public static Creature? Find<T>(Player? owner) where T : MonsterModel", "    {",
         "        var cs = owner?.Creature.CombatState;", "        if (owner == null || cs == null) return null;",
         "        return cs.Allies.FirstOrDefault(c => c.Monster is T && c.PetOwner == owner);", "    }", "",
         "    public static bool Alive<T>(Player? owner) where T : MonsterModel => Find<T>(owner)?.IsAlive ?? false;", "",
         "    /// <summary>골골이 소환과 같은 규칙 (처음: 생성 / 살아 있음: 최대 체력 + / 쓰러짐: 되살림).</summary>",
         "    public static async Task Summon<T, TAct>(PlayerChoiceContext ctx, Player? summoner, decimal amount, AbstractModel? source, bool guard)",
         "        where T : MonsterModel where TAct : PowerModel", "    {",
         "        var cs = summoner?.Creature.CombatState;",
         "        if (summoner == null || cs == null || summoner.Creature.IsDead) return;",
         "        amount = Hook.ModifySummonAmount(cs, summoner, amount, source);",
         "        if (amount <= 0m) return;",
         "        var pet = Find<T>(summoner);",
         "        if (pet != null && pet.IsAlive)", "        {",
         "            await CreatureCmd.GainMaxHp(pet, amount);", "        }", "        else", "        {",
         "            if (pet == null)", "            {",
         "                pet = await PlayerCmd.AddPet<T>(summoner);",
         "                if (guard) await PowerCmd.Apply<DieForYouPower>(ctx, pet, 1m, null, null);", "            }",
         "            else", "            {", "                summoner.PlayerCombatState?.AddPetInternal(pet);", "            }",
         "            await CreatureCmd.SetMaxHp(pet, amount);", "            await CreatureCmd.Heal(pet, amount, false);",
         "            if (pet.GetPower<TAct>() == null) await PowerCmd.Apply<TAct>(ctx, pet, 1m, null, null);", "        }",
         "        await Hook.AfterSummon(cs, ctx, summoner, amount);", "    }", "",
         "    public static async Task Attack<T>(PlayerChoiceContext ctx, Player? owner, Creature? target, decimal amount, int hits) where T : MonsterModel",
         "    {", "        var pet = Find<T>(owner);",
         "        if (pet == null || pet.IsDead || target == null || target.IsDead) return;",
         "        Lunge(pet, target);",
         "        for (var h = 0; h < hits && target.IsAlive; h++)",
         "            await CreatureCmd.Damage(ctx, target, amount, ValueProp.Move, pet, null, null);", "    }", "",
         "    public static async Task Act<T, TAct>(PlayerChoiceContext ctx, Player? owner) where T : MonsterModel where TAct : PowerModel",
         "    {", "        var pet = Find<T>(owner);",
         f"        if (pet != null && pet.IsAlive && pet.GetPower<TAct>() is {mid}PetActPower p) await p.Act(ctx);", "    }", "",
         "    public static async Task Kill<T>(Player? owner) where T : MonsterModel", "    {",
         "        var pet = Find<T>(owner);", "        if (pet != null && pet.IsAlive) await CreatureCmd.Kill(pet);", "    }", "",
         "    /// <summary>공격할 때 앞으로 살짝 튀어 나갔다 돌아오는 움직임 (그림 한 장짜리 동료용).</summary>",
         "    public static void Lunge(Creature pet, Creature? target)", "    {",
         "        if (SaveManager.Instance.PrefsSave.FastMode == FastModeType.Instant) return;",
         "        var node = NCombatRoom.Instance?.GetCreatureNode(pet);",
         "        if (node == null || !node.IsInsideTree()) return;",
         "        var start = node.Position;",
         "        var tnode = target != null ? NCombatRoom.Instance?.GetCreatureNode(target) : null;",
         "        var dir = tnode != null ? (tnode.GlobalPosition - node.GlobalPosition).Normalized() : Vector2.Right;",
         "        var tw = node.CreateTween();",
         "        tw.TweenProperty(node, \"position\", start + dir * 70f, 0.09).SetTrans(Tween.TransitionType.Quad).SetEase(Tween.EaseType.Out);",
         "        tw.TweenProperty(node, \"position\", start, 0.18).SetTrans(Tween.TransitionType.Quad).SetEase(Tween.EaseType.InOut);",
         "    }", "}", "",
         "// 동료의 매 턴 행동 (동료에게 붙는 숨은 파워)",
         f"public abstract class {mid}PetActPower : {mid}Power", "{",
         "    public override PowerType Type => PowerType.Buff;",
         "    public override PowerStackType StackType => PowerStackType.Single;",
         "    protected override bool IsVisibleInternal => false;",
         "    public virtual int Timing => 0; // 0 = 턴 종료, 1 = 턴 시작, 2 = 없음",
         "    public abstract Task Act(PlayerChoiceContext choiceContext);", "",
         "    public override async Task BeforeSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)",
         "    {", "        if (Timing != 0 || side != Owner.Side || Owner.IsDead) return;", "        await Act(choiceContext);", "    }", "",
         "    public override async Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)",
         "    {", "        if (Timing != 1 || player != Owner.PetOwner || Owner.IsDead) return;", "        await Act(choiceContext);", "    }",
         "}", ""]
    for p in pets(project):
        P = _pascal(p["id"])
        C = M._Ctx("pet", {"id": p["id"], "trigger": "none", "enemy_mode": "all"})
        lines, _e = B.compile_blocks(p.get("blocks") or [], project, C, "        ", prefix=f"{P}PetAct", extras=extras)
        timing = {"turn_end": 0, "turn_start": 1, "never": 2}.get(p.get("timing", "turn_end"), 0)
        L += [f"// 동료 '{p.get('name_ko')}'", f"public sealed class {P}Pet() : CustomPetModel(true)", "{",
              "    public override int MinInitialHp => 1;", "    public override int MaxInitialHp => 1;",
              "    public override bool IsHealthBarVisible => Creature.IsAlive;",
              "    public override IEnumerable<string> AssetPaths => [];", "",
              "    public override NCreatureVisuals? CreateCustomVisuals()", "    {",
              f'        var tex = ResourceLoader.Load<Texture2D>("{p["id"]}.png".PetImagePath());',
              "        return tex == null ? null : NodeFactory<NCreatureVisuals>.CreateFromResource(tex);", "    }", "}", "",
              f"public sealed class {P}PetActPower : {mid}PetActPower", "{",
              f"    public override int Timing => {timing};", "",
              "    public override async Task Act(PlayerChoiceContext choiceContext)", "    {",
              "        if (Owner == null || Owner.IsDead) return;", "        Flash();"] + lines + ["    }", "}", ""]
    return "\n".join(L) + "\n"


def character_members(project, character=None, image_prefix=""):
    ch = character if character is not None else project.get("character") or {}
    if not ch.get("combat_image"):
        return []
    if any(ch.get(key) for key in ("attack_frames", "hit_frames")):
        return motion_members(ch, image_prefix)
    return ["", "    // 전투 모습: 그림 한 장 (모드 메이커 '캐릭터 그림')",
            "    public override global::MegaCrit.Sts2.Core.Nodes.Combat.NCreatureVisuals? CreateCustomVisuals()", "    {",
            f'        var tex = ResourceLoader.Load<Texture2D>("{image_prefix}combat.png".CharacterUiPath());',
            "        return tex == null ? null : NodeFactory<global::MegaCrit.Sts2.Core.Nodes.Combat.NCreatureVisuals>.CreateFromResource(tex);",
            "    }"]


def frame_ms(character, key):
    try:
        return max(16, min(5000, int(character.get(key + "_ms", 120))))
    except (TypeError, ValueError):
        return 120


def motion_members(ch, image_prefix=""):
    def textures(key):
        return ", ".join(f'ResourceLoader.Load<Texture2D>("{image_prefix}{key}_{i}.png".CharacterUiPath())'
                         for i in range(len(ch.get(key, []))))
    # Each visual owns its playback state. A new trigger interrupts the previous sequence.
    return ["""
    private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<
        global::MegaCrit.Sts2.Core.Nodes.Combat.NCreatureVisuals, Motion> Motions = new();

    public override global::MegaCrit.Sts2.Core.Nodes.Combat.NCreatureVisuals? CreateCustomVisuals()
    {
        var idle = ResourceLoader.Load<Texture2D>("IMAGE_PREFIXcombat.png".CharacterUiPath());
        if (idle == null) return null;
        var visual = NodeFactory<global::MegaCrit.Sts2.Core.Nodes.Combat.NCreatureVisuals>.CreateFromResource(idle);
        if (visual != null)
            Motions.Add(visual, new Motion(idle, [ATTACK_FRAMES], [HIT_FRAMES]));
        return visual;
    }

    private sealed class Motion(Texture2D idle, Texture2D[] attack, Texture2D[] hit)
    {
        private Tween? playback;

        public void Play(Sprite2D sprite, string trigger)
        {
            var frames = trigger == "Attack" ? attack : hit;
            if (frames.Length == 0) return;
            playback?.Kill();
            playback = sprite.CreateTween();
            foreach (var frame in frames)
            {
                playback.TweenCallback(Callable.From(() => {
                    sprite.Texture = frame;
                    sprite.Offset = new Vector2(0, (idle.GetHeight() - frame.GetHeight()) * 0.5f);
                }));
                playback.TweenInterval(trigger == "Attack" ? ATTACK_MS / 1000.0 : HIT_MS / 1000.0);
            }
            playback.TweenCallback(Callable.From(() => {
                sprite.Texture = idle;
                sprite.Offset = Vector2.Zero;
                playback = null;
            }));
        }
    }

    [HarmonyLib.HarmonyPatch(typeof(global::MegaCrit.Sts2.Core.Nodes.Combat.NCreature), "SetAnimationTrigger")]
    private static class CombatMotionPatch
    {
        private static void Postfix(global::MegaCrit.Sts2.Core.Nodes.Combat.NCreature __instance, string __0)
        {
            if (__0 is not ("Attack" or "Hit")) return;
            var visual = __instance.Visuals;
            if (visual != null && Motions.TryGetValue(visual, out var motion)
                && visual.GetNodeOrNull<Sprite2D>("Visuals") is Sprite2D sprite)
                motion.Play(sprite, __0);
        }
    }
""".replace("IMAGE_PREFIX", image_prefix).replace("ATTACK_FRAMES", textures("attack_frames")).replace("HIT_FRAMES", textures("hit_frames"))
    .replace("ATTACK_MS", str(frame_ms(ch, "attack_frames"))).replace("HIT_MS", str(frame_ms(ch, "hit_frames")))]


def localization(project, lang, files):
    import modgen as M
    files.setdefault("monsters", {})
    for p in pets(project):
        lid = M.loc_id(project, p["id"] + "_pet")
        files["monsters"][f"{lid}.name"] = _txt(p, "name", lang)
        alid = M.loc_id(project, p["id"] + "_pet_act_power")
        d = pet_text(project, p, lang)
        files["powers"][f"{alid}.title"] = _txt(p, "name", lang)
        files["powers"][f"{alid}.description"] = d
        files["powers"][f"{alid}.smartDescription"] = d


# ---------------------------------------------------------------------------
# 그림 (크기·좌우 반전·높이 보정을 미리 적용해 PNG 로 넣는다)
# ---------------------------------------------------------------------------
def process_image(src, scale=100, flip=False, lift=0, max_side=900):
    """원본 PNG → 게임에 넣을 RGBA. 발밑 = 그림 아래 가운데. lift>0 이면 위로 띄움(아래 여백)."""
    from PIL import Image
    im = Image.open(src).convert("RGBA")
    bb = im.getbbox()
    if bb:
        im = im.crop(bb)
    k = max(0.05, float(scale or 100) / 100.0)
    w, h = max(1, int(im.width * k)), max(1, int(im.height * k))
    if max(w, h) > max_side:
        r = max_side / max(w, h)
        w, h = max(1, int(w * r)), max(1, int(h * r))
    im = im.resize((w, h), Image.LANCZOS)
    if flip:
        im = im.transpose(Image.FLIP_LEFT_RIGHT)
    lift = int(lift or 0)
    if lift > 0:
        out = Image.new("RGBA", (w, h + lift), (0, 0, 0, 0))
        out.alpha_composite(im, (0, 0))
        im = out
    elif lift < 0:
        im = im.crop((0, 0, w, max(1, h + lift)))
    return im


def placeholder(size=(150, 170), color=(120, 170, 220)):
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    w, h = size
    d.ellipse((w * 0.2, h * 0.05, w * 0.8, h * 0.45), fill=color + (255,))
    d.rounded_rectangle((w * 0.12, h * 0.35, w * 0.88, h * 0.98), 30, fill=color + (255,))
    d.ellipse((w * 0.33, h * 0.18, w * 0.43, h * 0.28), fill=(30, 30, 40, 255))
    d.ellipse((w * 0.57, h * 0.18, w * 0.67, h * 0.28), fill=(30, 30, 40, 255))
    return im


def write_images(project, img_dir):
    import os
    os.makedirs(os.path.join(img_dir, "pets"), exist_ok=True)
    for p in pets(project):
        dst = os.path.join(img_dir, "pets", f"{p['id']}.png")
        if p.get("image") and os.path.isfile(p["image"]):
            process_image(p["image"], p.get("scale"), p.get("flip"), p.get("lift")).save(dst)
        else:
            placeholder().save(dst)
    ch = project.get("character") or {}
    if ch.get("combat_image") and os.path.isfile(ch["combat_image"]):
        os.makedirs(os.path.join(img_dir, "charui"), exist_ok=True)
        process_image(ch["combat_image"], ch.get("combat_scale"), ch.get("combat_flip"), ch.get("combat_lift")).save(
            os.path.join(img_dir, "charui", "combat.png"))
        for key in ("attack_frames", "hit_frames"):
            for i, frame in enumerate(ch.get(key, [])):
                process_image(frame["image"], ch.get("combat_scale"), ch.get("combat_flip"), ch.get("combat_lift")).save(
                    os.path.join(img_dir, "charui", f"{key}_{i}.png"))
    import modgen as M
    for ich in M.imported_characters(project):
        source = ich.get("combat_image") or ""
        if not source or not os.path.isfile(source):
            continue
        os.makedirs(os.path.join(img_dir, "charui"), exist_ok=True)
        prefix = M.ichar_stem(ich) + "_"
        process_image(source, ich.get("combat_scale"), ich.get("combat_flip"), ich.get("combat_lift")).save(
            os.path.join(img_dir, "charui", prefix + "combat.png"))
        for key in ("attack_frames", "hit_frames"):
            for i, frame in enumerate(ich.get(key, [])):
                frame_image = frame.get("image") or ""
                if frame_image and os.path.isfile(frame_image):
                    process_image(frame_image, ich.get("combat_scale"), ich.get("combat_flip"), ich.get("combat_lift")).save(
                        os.path.join(img_dir, "charui", f"{prefix}{key}_{i}.png"))


def validate(project, seen):
    import blockcode as B
    import modgen as M
    import os
    errors, warnings = [], []
    for p in pets(project):
        where = f"동료 '{p.get('name_ko') or p['id']}'"
        if not M.ID_RE.match(p.get("id", "")):
            errors.append(f"동료 ID '{p.get('id')}'는 영문 소문자와 _ 만 쓸 수 있습니다.")
        if p["id"] in seen:
            errors.append(f"{where}: ID가 다른 항목과 겹칩니다.")
        seen.add(p["id"])
        _l, e = B.compile_blocks(p.get("blocks") or [], project, M._Ctx("pet", {"id": p["id"], "trigger": "none"}))
        errors += [f"{where}: {x}" for x in dict.fromkeys(e)]
        if p.get("image") and not os.path.isfile(p["image"]):
            warnings.append(f"{where}: 그림 파일을 찾을 수 없습니다 ({p['image']}). 임시 그림을 씁니다.")
    ch = project.get("character") or {}
    if ch.get("combat_image") and not os.path.isfile(ch["combat_image"]):
        warnings.append(f"캐릭터 전투 모습 그림을 찾을 수 없습니다: {ch['combat_image']}")
    if ch.get("enabled") and (ch.get("attack_frames") or ch.get("hit_frames")):
        if not os.path.isfile(ch.get("combat_image") or ""):
            errors.append("캐릭터 모션 재생에는 기본 전투 그림이 필요합니다.")
        for key, label in (("attack_frames", "공격"), ("hit_frames", "피격")):
            for i, frame in enumerate(ch.get(key, []), 1):
                if not os.path.isfile(frame.get("image") or ""):
                    errors.append(f"캐릭터 {label} 모션 {i}번째 그림을 찾을 수 없습니다: {frame.get('image', '')}")
    for ich in M.imported_characters(project):
        where = f"가져온 캐릭터 '{M.text(ich, 'name', 'ko') or ich.get('class', '캐릭터')}'"
        if ich.get("attack_frames") or ich.get("hit_frames"):
            if not os.path.isfile(ich.get("combat_image") or ""):
                errors.append(f"{where}: 모션 재생에는 기본 전투 그림이 필요합니다.")
            for key, label in (("attack_frames", "공격"), ("hit_frames", "피격")):
                for i, frame in enumerate(ich.get(key, []), 1):
                    if not os.path.isfile(frame.get("image") or ""):
                        errors.append(f"{where}: {label} 모션 {i}번째 그림을 찾을 수 없습니다: {frame.get('image', '')}")
    return errors, warnings


def add_examples(project, uid, blk, N):
    import modgen as M
    g = project["gimmicks"]
    wisp = new_pet(uid("wisp"))
    wisp.update(name_ko="도깨비불", name_en="Wisp", guard=True, timing="turn_end",
                blocks=[blk("pet_attack", pet=wisp["id"], who="random", amount={"t": "op", "op": "+", "a": N(3),
                                                                                   "b": {"t": "pet", "pet": wisp["id"], "what": "maxhp"}},
                            hits=1)])
    g["pets"].append(wisp)
    c1 = M.new_card(uid("call_wisp"))
    c1.update(name_ko="도깨비불 부르기", name_en="Call Wisp", type="Skill", cost=1, upgrade_cost=1, target="Self",
              effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[blk("pet_summon", pet=wisp["id"], amount=N(6, 3))])])
    c2 = M.new_card(uid("wisp_strike"))
    c2.update(name_ko="불꽃 돌진", name_en="Wisp Dash", type="Attack", cost=1, upgrade_cost=1, target="AnyEnemy",
              effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                  blk("if_else", cond={"t": "pet_alive", "pet": wisp["id"]},
                      body=[blk("pet_attack", pet=wisp["id"], who="target", amount=N(8, 4), hits=1)],
                      els=[blk("pet_summon", pet=wisp["id"], amount=N(3))])])])
    project["cards"] += [c1, c2]
    return ["동료 '도깨비불'(골골이처럼 전장에 서서 대신 맞고, 턴 종료 시 최대 체력+3 피해)",
            "카드 '도깨비불 부르기'(소환 6)", "카드 '불꽃 돌진'(살아 있으면 돌진 공격, 없으면 소환 3)"]

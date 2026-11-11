"""
기믹 (캐릭터 고유 시스템) — 메이플 해적·마법사 모드에서 쓴 장치들을 누구나 조립할 수 있게 일반화한 것.

  * 카드 태그      : '격투', '포격' 같은 키워드. 카드에 붙이고, 툴팁·설명 앞머리가 자동으로 붙는다.
                     "이번 턴에 사용한 [격투] 카드 수"(연계), "[포격] 카드를 쓸 때마다"(유물·파워) 에 쓴다.
  * 자원 파워      : 최대 스택(넘치면 효과), N 이상이 되면 터지는 효과, 같은 그룹은 하나만(날씨·자세),
                     숨김(내부 카운터), 내 턴 시작에 초기화. 카드는 '자원 비용'으로 이 파워를 소모한다.
  * 소환수         : 슬롯 N칸, 같은 것을 다시 소환하면 단계 상승, 매 턴 자동 행동, '지휘'로 즉시 행동.
  * 선택지 / 카드 고르기 / 다음 턴 예약 : 블록 코딩에서 쓴다 (blockcode.py).

게임 쪽 구현은 모두 이 파일이 만드는 C# (Gimmicks/Gimmicks.cs) 와 카드·파워 클래스 안의 몇 줄이다.
"""
from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# 데이터
# ---------------------------------------------------------------------------
SUMMON_TIMINGS = [("turn_end", "내 턴 종료 시 자동 행동"), ("turn_start", "내 턴 시작 시 자동 행동"),
                  ("never", "자동 행동 없음 (지휘할 때만)")]
THRESHOLD_MODES = [("all", "발동 후 전부 없앰"), ("sub", "발동 후 기준치만큼 줄임"), ("keep", "그대로 둠 (바뀔 때마다 다시 발동)")]


TAG_TIMINGS = [("play", "사용할 때"), ("draw", "뽑을 때"), ("discard", "버릴 때"),
               ("exhaust", "소멸할 때"), ("hand_start", "손패에 있는 채로 내 턴 시작"),
               ("hand_end", "손패에 있는 채로 내 턴 종료"),
               ("hand_play", "손패에 있는 동안 다른 카드를 사용할 때마다"),
               ("hand_aura", "더미에 있는 동안 지속 보정")]


def tag_blocks(tag, timing="play"):
    return (tag.get("blocks") if timing == "play" else (tag.get("event_blocks") or {}).get(timing)) or []


def tag_play_filters(project):
    import modgen as M
    return [("Any", "아무 카드나 사용"), *[("tag:" + t["id"], "키워드 · " + (_txt(t, "name", "ko")))
            for t in tags(project)], *[("kw:" + key, "기본 키워드 · " + label) for key, label in M.CARD_KEYWORDS]]


def tag_play_filter_expr(project, tag):
    import modgen as M
    selected = tag.get("played_filter") or "Any"
    if selected not in dict(tag_play_filters(project)):
        raise ValueError("사용한 카드 조건을 다시 선택하세요: " + str(selected))
    if selected.startswith("kw:"):
        return "cardPlay.Card.Keywords.Contains(CardKeyword." + selected[3:] + ")"
    expression = filter_expr(project, selected, "cardPlay.Card")
    if selected.startswith("tag:"):
        found = find_tag(project, selected[4:])
        if found and found.get("keyword_member"):
            expression = "(" + expression + " || cardPlay.Card.Keywords.Contains(" + found["keyword_member"] + "))"
    return expression


def new_tag(tid="new_tag"):
    return {"id": tid, "name_ko": "새 태그", "name_en": "New Tag",
            "desc_ko": "", "desc_en": "", "show_in_text": True, "blocks": [], "event_blocks": {}, "played_filter": "Any", "played_every": 1, "played_scope": "turn",
            "hand_cost_enabled": False, "hand_cost_amount": 1, "hand_cost_filter": "Any"}


def new_summon(sid="new_summon"):
    return {"id": sid, "name_ko": "새 소환수", "name_en": "New Summon", "desc_ko": "", "desc_en": "",
            "image": "", "max_rank": 3, "timing": "turn_end", "act_on_max": True,
            "blocks": [{"op": "damage", "args": {"who": "random", "amount": {"t": "op", "op": "*", "a": {"t": "num", "v": 4},
                                                                              "b": {"t": "amount"}},
                                                 "hits": 1, "powered": False}}]}


def defaults():
    return {"tags": [], "summons": [], "summon_slots": 3, "orbs": [], "effects": [], "buttons": [], "pets": []}


CARD_DEFAULTS = {"gtags": [], "no_cost": False, "separate_upgrade_effect": False, "upgrade_effect_blocks": [], "res_power": "", "res_cost": 0, "play_cond": None, "glow_cond": None,
                 "star_cost": 0, "star_cost_up": 0, "star_x": False}
POWER_DEFAULTS = {"cap": 0, "overflow_blocks": [], "threshold": 0, "threshold_mode": "all", "threshold_blocks": [],
                  "group": "", "hidden": False}


def normalize(project):
    g = defaults()
    g.update(project.get("gimmicks") or {})
    g["tags"] = [dict(new_tag(t.get("id", "x")), **t) for t in g.get("tags", [])]
    import handaura
    for tag in g["tags"]:
        if tag.get("hand_cost_enabled"):
            tag.setdefault("event_blocks", {})["hand_aura"] = handaura.blocks(tag)
            tag["hand_cost_enabled"] = False
    g["summons"] = [dict(new_summon(s.get("id", "x")), **s) for s in g.get("summons", [])]
    g["orbs"] = [dict(new_orb(o.get("id", "x")), **o) for o in g.get("orbs", [])]
    import fxbtn
    import pets as PT
    fxbtn.normalize(g)
    PT.normalize(g)
    project["gimmicks"] = g
    ch = project.get("character")
    if isinstance(ch, dict):
        ch.setdefault("orb_slots", 0)
        ch.setdefault("show_stars", False)
        for k, v in (("combat_image", ""), ("combat_scale", 100), ("combat_flip", False), ("combat_lift", 0)):
            ch.setdefault(k, v)
    for c in project.get("cards", []):
        for k, v in CARD_DEFAULTS.items():
            c.setdefault(k, copy.deepcopy(v))
    for p in project.get("powers", []):
        for k, v in POWER_DEFAULTS.items():
            p.setdefault(k, copy.deepcopy(v))
    return project


def tags(project):
    return (project.get("gimmicks") or {}).get("tags", [])


def tag_play_lines(project, card, context, ind="        ", timing="play"):
    """Shared keyword actions run once, after the card's own actions."""
    import blockcode as B
    import modgen as M
    lines = []
    for index, tag in enumerate(tags(project)):
        blocks = tag_blocks(tag, timing)
        if not blocks:
            continue
        statements, errors = B.compile_blocks(blocks, project, context, ind + "    ",
                                              prefix=M.pascal(card["id"]) + "Tag" + str(index) + timing,
                                              extras=M._EXTRAS_SINK.get("x"))
        if errors:
            raise ValueError(f"키워드 '{tag.get('name_ko') or tag['id']}': " + ", ".join(errors))
        condition = f'{helper(project)}.HasTag(this, "{tag["id"]}")'
        if card.get("clone") and tag["id"] in card.get("gtags", []):
            condition = "true"  # Imported cards can inherit a foreign card base.
        if timing == "hand_play":
            condition = "(" + condition + ") && (" + tag_play_filter_expr(project, tag) + ")"
        if timing == "hand_play":
            every = int(tag.get("played_every", 1))
            scope = tag.get("played_scope", "turn")
            if not 1 <= every <= 999 or scope not in ("turn", "combat"):
                raise ValueError("키워드의 사용 장수·집계 기준을 다시 설정하세요.")
            field = "_makerTagCount" + str(index)
            reset = f"{field}Combat != Owner.Creature.CombatState"
            if scope == "turn":
                reset += f" || {field}Round != (Owner.Creature.CombatState?.RoundNumber ?? 0)"
            statements = [ind + f"    if ({reset}) {{ {field} = 0; {field}Combat = Owner.Creature.CombatState; {field}Round = Owner.Creature.CombatState?.RoundNumber ?? 0; }}",
                          ind + f"    {field}++;", ind + f"    if ({field} >= {every})", ind + "    {",
                          ind + f"        {field} = 0;", *["    " + line for line in statements], ind + "    }"]
        lines += [ind + "if (" + condition + ")", ind + "{", *statements, ind + "}"]
    return lines


def hand_aura_members(project, card, original_body=None):
    import handaura
    return handaura.members(project, card, original_body)


def summons(project):
    return (project.get("gimmicks") or {}).get("summons", [])


def find_tag(project, tid):
    return next((t for t in tags(project) if t["id"] == tid), None)


def find_summon(project, sid):
    return next((s for s in summons(project) if s["id"] == sid), None)


def _txt(it, field, lang):
    if field == "name" and lang == "zh":
        from modgen import text
        return text(it, field, lang)
    other = "en" if lang == "ko" else "ko"
    return (it.get(f"{field}_{lang}") or it.get(f"{field}_{other}") or it.get("id", "")).strip()


# ---------------------------------------------------------------------------
# 카드 필터 ('아무 카드' / 종류 / 태그)
# ---------------------------------------------------------------------------
BASE_FILTERS = [("Any", "아무 카드"), ("Attack", "공격 카드"), ("Skill", "스킬 카드"), ("Power", "파워 카드"),
                ("Curse", "저주 카드"), ("Status", "상태 이상 카드"), ("Quest", "퀘스트 카드")]


def card_filters(project):
    return BASE_FILTERS + [("tag:" + t["id"], f"#{t.get('name_ko') or t['id']} 카드") for t in tags(project)]


def filter_word(project, f, lang, plural=False):
    """'격투 카드' / 'a Combat card' 같은 말."""
    f = f or "Any"
    if f.startswith("tag:"):
        t = find_tag(project, f[4:])
        name = _txt(t, "name", lang) if t else f[4:]
        if lang == "ko":
            return f"[gold]{name}[/gold] 카드"
        return f"[gold]{name}[/gold] cards" if plural else f"a [gold]{name}[/gold] card"
    if lang == "ko":
        return "카드" if f == "Any" else dict(BASE_FILTERS).get(f, "카드")
    if plural:
        return "cards" if f == "Any" else f + "s"
    return "a card" if f == "Any" else ("an Attack" if f == "Attack" else f"a {f}")


def filter_expr(project, f, var):
    """C# bool 식. '아무 카드'면 'true'."""
    f = f or "Any"
    if f.startswith("tag:"):
        tag = find_tag(project, f[4:])
        if tag and tag.get("card_kind"):
            return _card_kind_filter(project, tag, var)
        mid = project["mod"]["id"]
        return f'global::{mid}.{mid}Code.Gimmicks.{mid}Gimmicks.HasTag({var}, "{f[4:]}")'
    if f == "Any":
        return "true"
    return f"{var}.Type == CardType.{f}"


def _card_kind_filter(project, tag, var):
    import cardkind
    import modgen as M
    return f"{var}.Type == {cardkind.runtime_class(project)}.{M.pascal(tag['id'])}"


# ---------------------------------------------------------------------------
# 이름
# ---------------------------------------------------------------------------
def _pascal(s):
    return "".join(p[:1].upper() + p[1:] for p in str(s).split("_") if p)


def letters(n):
    """0 -> A, 25 -> Z, 26 -> AA (클래스 이름에 숫자를 넣지 않으려고)."""
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def ns(project):
    mid = project["mod"]["id"]
    return f"global::{mid}.{mid}Code.Gimmicks"


def summon_cls(project, sid):
    return f"{ns(project)}.{_pascal(sid)}SummonPower"


def tag_cls(project, tid):
    return f"{ns(project)}.{_pascal(tid)}TagPower"


def helper(project):
    mid = project["mod"]["id"]
    return f"{ns(project)}.{mid}Gimmicks"


# ---------------------------------------------------------------------------
# 카드 / 파워에 들어가는 코드
# ---------------------------------------------------------------------------
def card_tips(project, card):
    out = class_tips(project, card)
    for tid in card.get("gtags") or []:
        if find_tag(project, tid):
            out.append(f"HoverTipFactory.FromPower<{tag_cls(project, tid)}>()")
    return out


def _res_meta(project, card):
    import modgen as M
    if not card.get("res_power") or int(card.get("res_cost") or 0) <= 0:
        return None
    return M.power_meta(project, card["res_power"])


def card_members(project, card):
    """카드 클래스 안에 들어갈 줄들 (태그 / 사용 조건 / 금색 테두리)."""
    import blockcode as B
    import modgen as M
    L = []
    sc = int(card.get("star_cost") or 0)
    if card.get("star_x"):
        L.append("    public override bool HasStarCostX => true;")
    elif sc > 0:
        L.append(f"    public override int CanonicalStarCost => {sc};")
    gt = [t for t in (card.get("gtags") or []) if find_tag(project, t)]
    if gt:
        L.append("    public override string[] GimmickTags => [" + ", ".join(f'"{t}"' for t in gt) + "];")
    conds = []
    rm = _res_meta(project, card)
    if rm:
        conds.append(f"Owner.Creature.GetPowerAmount<{rm['cls']}>() >= {helper(project)}.ResCost(this, {int(card['res_cost'])}, typeof({rm['cls']}))")
    C = M._Ctx("card", card)
    C.other = None
    C.single = None
    if isinstance(card.get("play_cond"), dict):
        g = B._Gen(project, C)
        conds.append(g.cond(card["play_cond"]))
    if conds:
        L.append("    protected override bool IsPlayable => base.IsPlayable && (IsCanonical || Owner == null || CombatState == null || "
                 f"({' && '.join(conds)}));")
    if isinstance(card.get("glow_cond"), dict):
        g = B._Gen(project, C)
        L.append("    protected override bool ShouldGlowGoldInternal => !IsCanonical && Owner != null && CombatState != null && "
                 f"{g.cond(card['glow_cond'])};")
    return L


def card_play_prefix(project, card, ind="        "):
    rm = _res_meta(project, card)
    if not rm:
        return []
    return [f"{ind}// 자원 비용: {rm['ko']} {int(card['res_cost'])}",
            f"{ind}if (!await {helper(project)}.Pay<{rm['cls']}>(choiceContext, Owner.Creature, {helper(project)}.ResCost(this, {int(card['res_cost'])}, typeof({rm['cls']})), this)) return;"]


def card_errors(project, card, where):
    import blockcode as B
    import modgen as M
    errs = []
    for tid in card.get("gtags") or []:
        if not find_tag(project, tid):
            errs.append(f"{where}: 없는 태그 '{tid}'")
    if card.get("res_power") and int(card.get("res_cost") or 0) > 0 and not M.power_meta(project, card["res_power"]):
        errs.append(f"{where}: 자원 비용의 파워 '{card['res_power']}'를 찾을 수 없습니다.")
    C = M._Ctx("card", card)
    C.other = None
    C.single = None
    for key, name in (("play_cond", "사용 조건"), ("glow_cond", "금색 테두리 조건")):
        c = card.get(key)
        if isinstance(c, dict):
            g = B._Gen(project, C)
            g.no_vars = True
            g.cond(c)
            for e in dict.fromkeys(g.errors):
                errs.append(f"{where}: {name} - {e}")
    return errs


def card_prefix_text(project, card, lang):
    """설명 맨 앞: '격투. 해룡 에너지 2 소모.'"""
    parts = []
    names = []
    for tid in card.get("gtags") or []:
        t = find_tag(project, tid)
        if t and not t.get("card_kind") and t.get("show_in_text", True):
            names.append(f"[gold]{_txt(t, 'name', lang)}[/gold]")
    if names:
        parts.append((", " if lang == "en" else ", ").join(names) + ".")
    rm = _res_meta(project, card)
    if rm:
        n = int(card["res_cost"])
        if lang == "zh":
            from card_zh import power_name
            parts.append(f"消耗{n}层[gold]{power_name(project, card.get('res_power'))}[/gold]。")
            return " ".join(parts)
        parts.append(f"[gold]{rm['ko']}[/gold] {n} 소모." if lang == "ko" else f"Spend {n} [gold]{rm['en']}[/gold].")
    return " ".join(parts)


def power_members(project, power, C, extras):
    """파워 클래스 안에 들어갈 줄 (최대 스택 / 임계치 / 그룹 / 숨김)."""
    import blockcode as B
    import modgen as M
    mid = project["mod"]["id"]
    L = []
    cls = M.pascal(power["id"]) + "Power"
    if power.get("hidden"):
        L.append("    protected override bool IsVisibleInternal => false;")
    grp = (power.get("group") or "").strip()
    slots = [m for m in power.get("modifiers", []) if m.get("kind") == "orb_slots"]
    applied = []
    if grp:
        L += ["", f'    public override string GimmickGroup => "{_cs_str(grp)}";']
        applied += ["        // 같은 그룹(예: 날씨·자세)의 다른 파워는 사라진다",
                    f"        foreach (var p_ in Owner.Powers.OfType<{mid}Power>().Where(p_ => p_ != this && p_.GimmickGroup == GimmickGroup).ToList())",
                    "            await PowerCmd.Remove(p_);"]
    if slots:
        n = sum(int(m.get("value") or 0) for m in slots)
        applied += ["        // 상시 효과: 구체 슬롯", f"        if (Owner.Player != null && {n} > 0) await OrbCmd.AddSlots(Owner.Player, {n});"]
        L += ["", "    public override Task AfterRemoved(Creature oldOwner)", "    {",
              f"        if (oldOwner.Player != null && {n} > 0) OrbCmd.RemoveSlots(oldOwner.Player, {n});",
              "        return Task.CompletedTask;", "    }"]
    if applied:
        L += ["", "    public override async Task AfterApplied(Creature? applier, CardModel? cardSource)", "    {"] + applied + ["    }"]
    cap = int(power.get("cap") or 0)
    thr = int(power.get("threshold") or 0)
    if cap > 0 or thr > 0:
        L += ["", "    private bool _gimmickBusy;", "",
              "    public override async Task AfterPowerAmountChanged(PlayerChoiceContext choiceContext, PowerModel power, decimal amount, Creature? applier, CardModel? cardSource)",
              "    {", "        if (power != this || _gimmickBusy || Owner == null || Owner.IsDead) return;",
              "        _gimmickBusy = true;", "        try", "        {"]
        if cap > 0:
            L += [f"            var cap_ = {cap} + Owner.Powers.OfType<{mid}Power>().Sum(p => p.CapBonus(this));",
                  "            if (Amount > cap_)", "            {",
                  "                var ev_ = (decimal)(Amount - cap_);",
                  "                await PowerCmd.ModifyAmount(choiceContext, this, -(Amount - cap_), Owner, null);",
                  "                await GimmickOverflow(choiceContext, applier, ev_);", "            }"]
        if thr > 0:
            mode = power.get("threshold_mode", "all")
            L += [f"            if (Amount >= {thr} && Owner.Powers.Contains(this))", "            {",
                  "                var ev_ = (decimal)Amount;",
                  "                await GimmickThreshold(choiceContext, applier, ev_);"]
            if mode == "all":
                L.append("                if (Owner.Powers.Contains(this)) await PowerCmd.Remove(this);")
            elif mode == "sub":
                L += [f"                if (Owner.Powers.Contains(this) && Amount > {thr}) await PowerCmd.ModifyAmount(choiceContext, this, -{thr}, Owner, null);",
                      f"                else if (Owner.Powers.Contains(this)) await PowerCmd.Remove(this);"]
            L.append("            }")
        L += ["        }", "        finally", "        {", "            _gimmickBusy = false;", "        }", "    }"]

        def prog(name, blocks, tag):
            Cp = M._Ctx("power", power)
            lines, _e = B.compile_blocks(blocks or [], project, Cp, "        ", prefix=f"{cls}{tag}",
                                         extras=extras, allow_event=True)
            return ["", f"    private async Task {name}(PlayerChoiceContext choiceContext, Creature? other, decimal ev_)",
                    "    {", "        Flash();"] + lines + ["    }"]
        if cap > 0:
            L += prog("GimmickOverflow", power.get("overflow_blocks"), "Ov")
        if thr > 0:
            L += prog("GimmickThreshold", power.get("threshold_blocks"), "Th")
    return L


# ---------------------------------------------------------------------------
# 파워 상시 효과 → 기믹 (구체·별·골골이·소환수·자원·버튼)
# ---------------------------------------------------------------------------
MOD_SENTENCE_KINDS = {"pet_dmg", "orb_value", "orb_passive_times", "orb_slots", "star_cost", "stars_for_energy", "osty_dmg",
                      "summon_amount", "summon_slots", "res_cap", "res_cost", "button_cost", "button_uses"}


def _ref_name(project, m, lang):
    import modgen as M
    kind, ref = m["kind"], m.get("ref") or ""
    if kind in ("orb_value", "orb_passive_times"):
        om = orb_meta(project, ref) if ref else None
        return (om["ko"] if lang == "ko" else om["en"]) if om else ("모든 구체" if lang == "ko" else "all Orbs")
    if kind in ("res_cap", "res_cost"):
        pm = M.power_meta(project, ref)
        return (pm["ko"] if lang == "ko" else pm["en"]) if pm else "?"
    if kind == "pet_dmg":
        import pets as PT
        p = PT.find_pet(project, ref) if ref else None
        return PT._txt(p, "name", lang) if p else ("모든 동료" if lang == "ko" else "your companions")
    if kind in ("button_cost", "button_uses"):
        import fxbtn
        b = fxbtn.find_button(project, ref) if ref else None
        if not b:
            return "모든 버튼" if lang == "ko" else "all buttons"
        return b.get(f"label_{lang}") or b.get("label_ko") or ref
    return ""


def modifier_sentence(project, m, lang):
    k = int(m.get("value", 0) or 0)
    v = ("[blue]{Amount}[/blue]" + (f"×{abs(k)}" if abs(k) != 1 else "")) if m.get("per_stack") else f"[blue]{abs(k)}[/blue]"
    neg = k < 0
    kind = m["kind"]
    ref = _ref_name(project, m, lang)
    f = m.get("filter") or "Any"
    ko = lang == "ko"
    up_ko, up_en = ("감소합니다", "less") if neg else ("증가합니다", "more")
    if kind == "orb_value":
        return f"[gold]{ref}[/gold]의 수치가 {v} {up_ko}." if ko else f"{ref} have {v} {'less' if neg else 'more'} value."
    if kind == "orb_passive_times":
        return f"[gold]{ref}[/gold]의 지속 효과가 {v}번 더 발동합니다." if ko else f"{ref} trigger their passive {v} more time(s)."
    if kind == "orb_slots":
        return f"구체 슬롯을 {v}개 얻습니다." if ko else f"Gain {v} Orb Slot(s)."
    if kind == "star_cost":
        w = filter_word(project, f, "ko") if ko else filter_word(project, f, "en", plural=True)
        return f"{w}의 [gold]별[/gold] 비용이 {v} {up_ko}." if ko else f"{w[:1].upper()}{w[1:]} cost {v} {up_en} [gold]Stars[/gold]."
    if kind == "stars_for_energy":
        return "에너지가 모자라면 모자란 만큼 [gold]별[/gold]로 냅니다." if ko else "Pay missing Energy with [gold]Stars[/gold]."
    if kind == "pet_dmg":
        return (f"[gold]{ref}[/gold]의 공격 피해가 {v} {up_ko}." if ko else
                f"[gold]{ref}[/gold] deal {v} {'less' if neg else 'additional'} damage.")
    if kind == "osty_dmg":
        return f"[gold]골골이[/gold]의 공격 피해가 {v} {up_ko}." if ko else f"[gold]Osty[/gold] deals {v} {'less' if neg else 'additional'} damage."
    if kind == "summon_amount":
        return f"[gold]소환[/gold]이 {v} {up_ko}." if ko else f"[gold]Summon[/gold] {v} {up_en}."
    if kind == "summon_slots":
        return f"소환수 슬롯이 {v}칸 {'줄어듭니다' if neg else '늘어납니다'}." if ko else f"Gain {v} summon slot(s)."
    if kind == "res_cap":
        return f"[gold]{ref}[/gold]의 최대치가 {v} {up_ko}." if ko else f"Max [gold]{ref}[/gold] increased by {v}."
    if kind == "res_cost":
        w = filter_word(project, f, "ko") if ko else filter_word(project, f, "en", plural=True)
        return f"{w}의 [gold]{ref}[/gold] 비용이 {v} {up_ko}." if ko else f"{w[:1].upper()}{w[1:]} cost {v} {up_en} [gold]{ref}[/gold]."
    btn_ko = f"[gold]{ref}[/gold] 버튼" if m.get("ref") else "모든 버튼"
    btn_en = f"The [gold]{ref}[/gold] button" if m.get("ref") else "Your buttons"
    if kind == "button_cost":
        return f"{btn_ko}의 에너지 비용이 {v} {up_ko}." if ko else f"{btn_en} cost {v} {up_en} Energy."
    if kind == "button_uses":
        return f"{btn_ko}을 턴마다 {v}번 더 쓸 수 있습니다." if ko else f"{btn_en} can be used {v} more time(s) per turn."
    return ""


def modifier_members(project, power):
    """파워 클래스에 들어갈 기믹 상시 효과 override (구체 슬롯·골골이 피해는 다른 곳에서)."""
    import modgen as M
    mods = power.get("modifiers", [])
    by = {}
    for m in mods:
        by.setdefault(m["kind"], []).append(m)
    V = lambda m: M._mod_value(m)  # noqa: E731
    L = []
    if by.get("orb_value"):
        L += ["", "    public override decimal ModifyOrbValue(OrbModel orb, decimal value)", "    {",
              "        if (orb.Owner?.Creature != Owner) return value;", "        var r = value;"]
        for m in by["orb_value"]:
            om = orb_meta(project, m.get("ref")) if m.get("ref") else None
            L.append(f"        if ({'orb is ' + om['cls'] if om else 'true'}) r += {V(m)};")
        L += ["        return r;", "    }"]
    if by.get("orb_passive_times"):
        L += ["", "    public override int ModifyOrbPassiveTriggerCounts(OrbModel orb, int triggerCount)", "    {",
              "        if (orb.Owner?.Creature != Owner) return triggerCount;", "        var r = triggerCount;"]
        for m in by["orb_passive_times"]:
            om = orb_meta(project, m.get("ref")) if m.get("ref") else None
            L.append(f"        if ({'orb is ' + om['cls'] if om else 'true'}) r += (int)({V(m)});")
        L += ["        return Math.Max(0, r);", "    }"]
    if by.get("star_cost"):
        L += ["", "    public override bool TryModifyStarCost(CardModel card, decimal originalCost, out decimal modifiedCost)",
              "    {", "        var d_ = 0m;"]
        for m in by["star_cost"]:
            L.append(f"        if (card.Owner?.Creature == Owner && {filter_expr(project, m.get('filter') or 'Any', 'card')}) d_ += {V(m)};")
        L += ["        modifiedCost = Math.Max(0m, originalCost + d_);", "        return d_ != 0m;", "    }"]
    if by.get("stars_for_energy"):
        L += ["", "    public override bool ShouldPayExcessEnergyCostWithStars(Player player) => player.Creature == Owner;"]
    if by.get("summon_amount"):
        L += ["", "    public override decimal ModifySummonAmount(Player summoner, decimal amount, AbstractModel? source)",
              f"        => summoner.Creature == Owner ? amount + {' + '.join(f'({V(m)})' for m in by['summon_amount'])} : amount;"]
    if by.get("summon_slots"):
        L += ["", f"    public override int SummonSlotBonus => (int)({' + '.join(f'({V(m)})' for m in by['summon_slots'])});"]
    if by.get("res_cap"):
        L += ["", "    public override int CapBonus(PowerModel res)", "    {", "        var r = 0;"]
        for m in by["res_cap"]:
            pm = M.power_meta(project, m.get("ref"))
            if pm:
                L.append(f"        if (res is {pm['cls']}) r += (int)({V(m)});")
        L += ["        return r;", "    }"]
    if by.get("res_cost"):
        L += ["", "    public override int ResCostDelta(CardModel card, System.Type res)", "    {", "        var r = 0;"]
        for m in by["res_cost"]:
            pm = M.power_meta(project, m.get("ref"))
            if pm:
                L.append(f"        if (res == typeof({pm['cls']}) && {filter_expr(project, m.get('filter') or 'Any', 'card')}) r += (int)({V(m)});")
        L += ["        return r;", "    }"]
    import fxbtn
    for kind, meth in (("button_cost", "ButtonCostDelta"), ("button_uses", "ButtonUsesDelta")):
        if by.get(kind):
            L += ["", f"    public override int {meth}(int index)", "    {", "        var r = 0;"]
            ids = [b["id"] for b in fxbtn.buttons(project)]
            for m in by[kind]:
                ref = m.get("ref") or ""
                cond = f"index == {ids.index(ref)}" if ref in ids else "true"
                L.append(f"        if ({cond}) r += (int)({V(m)});")
            L += ["        return r;", "    }"]
    return L


def modifier_errors(project, power, where):
    import modgen as M
    import fxbtn
    errs = []
    for m in power.get("modifiers", []):
        kind = m.get("kind")
        need = M.MODIFIER_REF.get(kind)
        if not need:
            continue
        what, optional = need
        ref = m.get("ref") or ""
        if not ref:
            if not optional:
                errs.append(f"{where}: 상시 효과 '{M.MODIFIER_LABEL.get(kind)}'에 대상 자원을 고르세요.")
            continue
        import pets as PT
        ok = (orb_meta(project, ref) if what == "orb" else M.power_meta(project, ref) if what == "power"
              else PT.find_pet(project, ref) if what == "pet" else fxbtn.find_button(project, ref))
        if not ok:
            errs.append(f"{where}: 상시 효과 '{M.MODIFIER_LABEL.get(kind)}'의 대상 '{ref}'를 찾을 수 없습니다.")
    return errs


def power_errors(project, power, where):
    import blockcode as B
    import modgen as M
    errs = modifier_errors(project, power, where)
    for key, n in (("overflow_blocks", "넘칠 때"), ("threshold_blocks", "기준치 도달 시")):
        if power.get(key):
            _l, e = B.compile_blocks(power[key], project, M._Ctx("power", power), allow_event=True)
            errs += [f"{where}: {n} 블록 - {x}" for x in dict.fromkeys(e)]
    if int(power.get("cap") or 0) > 0 and power.get("stack") == "Single":
        errs.append(f"{where}: '최대 스택'은 중첩 파워에서만 쓸 수 있습니다.")
    return errs


def power_text(project, power, lang):
    import blockcode as B
    out = []
    cap = int(power.get("cap") or 0)
    thr = int(power.get("threshold") or 0)
    if cap > 0:
        s = f"최대 {cap}까지 쌓입니다." if lang == "ko" else f"最多叠加{cap}层。" if lang == "zh" else f"Stacks up to {cap}."
        d = B.describe(power.get("overflow_blocks"), project, "power", lang)
        if d:
            s += (f" 넘친 만큼: {d}" if lang == "ko" else f"超出上限时：{d}" if lang == "zh" else f" When it overflows: {d}")
        out.append(s)
    if thr > 0:
        d = B.describe(power.get("threshold_blocks"), project, "power", lang)
        mode = power.get("threshold_mode", "all")
        if lang == "ko":
            s = f"{thr} 이상이 되면 {d or '발동합니다.'}"
            s += {"all": " 그 후 사라집니다.", "sub": f" 그 후 {thr} 줄어듭니다.", "keep": ""}[mode]
        elif lang == "zh":
            s = f"达到{thr}层时，{d or '触发效果。'}"
            s += {"all": "随后移除此效果。", "sub": f"随后减少{thr}层。", "keep": ""}[mode]
        else:
            s = f"At {thr} or more: {d}"
            s += {"all": " Then it is removed.", "sub": f" Then it decreases by {thr}.", "keep": ""}[mode]
        out.append(s)
    grp = (power.get("group") or "").strip()
    if grp:
        out.append(f"[gold]{grp}[/gold] 효과는 하나만 유지됩니다." if lang == "ko" else f"同一时间只能有一个[gold]{grp}[/gold]效果生效。" if lang == "zh" else f"Only one [gold]{grp}[/gold] effect can be active.")
    return " ".join(out)


def _cs_str(s):
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


# ---------------------------------------------------------------------------
# 소환수 설명
# ---------------------------------------------------------------------------
def summon_text(project, s, lang):
    import blockcode as B
    custom = (s.get(f"desc_{lang}") or "").strip()
    if custom:
        return custom
    d = B.describe(s.get("blocks"), project, "power", lang)
    when = {"turn_end": ("내 턴 종료 시", "At the end of your turn"),
            "turn_start": ("내 턴 시작 시", "At the start of your turn"),
            "never": ("지휘하면", "When commanded")}[s.get("timing", "turn_end")]
    mr = int(s.get("max_rank", 3) or 1)
    if lang == "ko":
        txt = f"{when[0]}: {d}" if d else ""
        txt += f" 단계: [blue]{{Amount}}[/blue]/{mr}. 다시 소환하면 단계가 오릅니다."
        if s.get("act_on_max", True):
            txt += " 최고 단계에서 다시 소환하면 즉시 행동합니다."
    else:
        txt = f"{when[1]}: {d}" if d else ""
        txt += f" Rank [blue]{{Amount}}[/blue]/{mr}. Summon again to rank up."
        if s.get("act_on_max", True):
            txt += " At max rank, summoning again makes it act immediately."
    return txt.strip()


# ---------------------------------------------------------------------------
# C# : Gimmicks/Gimmicks.cs
# ---------------------------------------------------------------------------
def gen_runtime(project, extras):
    import blockcode as B
    import modgen as M
    mid = project["mod"]["id"]
    g = project.get("gimmicks") or defaults()
    slots = max(1, int(g.get("summon_slots", 3) or 3))
    up = mid.upper()
    L = [M._header(), M.USINGS_COMMON.rstrip("\n"),
         "using BaseLib.Abstracts;", "using BaseLib.Extensions;",
         "using MegaCrit.Sts2.Core.CardSelection;", "using MegaCrit.Sts2.Core.Localization;",
         "using MegaCrit.Sts2.Core.Models.CardPools;",
         f"using {mid}.{mid}Code.Cards;", f"using {mid}.{mid}Code.Powers;", f"using {mid}.{mid}Code.Extensions;", "",
         f"namespace {mid}.{mid}Code.Gimmicks;", "",
         "// 모드 메이커 '기믹' 기능의 실행 코드 (태그, 자원, 소환수, 선택지, 카드 고르기)",
         f"public static partial class {mid}Gimmicks", "{",
         f"    public const int SummonSlots = {slots};", "",
         f"    public static bool HasTag(CardModel? card, string tag) => card != null && ((card is {mid}Card c && c.GimmickTags.Contains(tag)) || Data(card).Tags.Contains(tag));", "",
         "    // ---- 카드 인스턴스별 변수·태그 ----",
         "    // 같은 카드가 여러 장이어도 CardModel 한 장마다 따로 저장. 카드 더미를 옮겨도 같은 객체라 그대로 남는다.",
         "    // 복제(CloneOf): '값 복사' 변수만 물려받음. 전투 카드(DeckVersion): '덱에 남기기' 변수는 덱의 카드에도 써 두고 다음 전투에서 다시 읽는다.",
         "    public sealed class CardVar { public decimal Value; public bool CopyOnClone = true; public bool KeepAfterCombat; }",
         "    public sealed class CardData { public readonly Dictionary<string, CardVar> Vars = new(); public readonly HashSet<string> Tags = new(); }",
         "    private static readonly global::System.Runtime.CompilerServices.ConditionalWeakTable<CardModel, CardData> CardStates = new();", "",
         "    private static CardVar CopyVar(CardVar v) => new CardVar { Value = v.Value, CopyOnClone = v.CopyOnClone, KeepAfterCombat = v.KeepAfterCombat };", "",
         "    public static CardData Data(CardModel card)", "    {",
         "        if (CardStates.TryGetValue(card, out var d)) return d;",
         "        d = new CardData();",
         "        var deck = card.DeckVersion;",
         "        if (deck != null && !ReferenceEquals(deck, card) && CardStates.TryGetValue(deck, out var dd))",
         "            foreach (var kv in dd.Vars) if (kv.Value.KeepAfterCombat) d.Vars[kv.Key] = CopyVar(kv.Value);",
         "        var src = card.CloneOf;",
         "        if (src != null && !ReferenceEquals(src, card) && CardStates.TryGetValue(src, out var sd))", "        {",
         "            foreach (var kv in sd.Vars) if (kv.Value.CopyOnClone) d.Vars[kv.Key] = CopyVar(kv.Value);",
         "            foreach (var t in sd.Tags) d.Tags.Add(t);", "        }",
         "        CardStates.AddOrUpdate(card, d);",
         "        return d;", "    }", "",
         "    private static void SyncDeck(CardModel card, string key, CardVar? v)", "    {",
         "        var deck = card.DeckVersion;",
         "        if (deck == null || ReferenceEquals(deck, card) || card.IsClone) return;",
         "        if (v == null) { Data(deck).Vars.Remove(key); return; }",
         "        if (v.KeepAfterCombat) Data(deck).Vars[key] = CopyVar(v);", "    }", "",
         "    public static bool HasCardVar(CardModel? card, string key) => card != null && Data(card).Vars.ContainsKey(key);", "",
         "    public static decimal CardState(CardModel? card, string key) =>",
         "        card != null && Data(card).Vars.TryGetValue(key, out var v) ? v.Value : 0m;", "",
         "    public static void NewCardVar(CardModel? card, string key, decimal value, bool copyOnClone, bool keepAfterCombat)", "    {",
         "        if (card == null) return;",
         "        var v = new CardVar { Value = value, CopyOnClone = copyOnClone, KeepAfterCombat = keepAfterCombat };",
         "        Data(card).Vars[key] = v;",
         "        SyncDeck(card, key, v);", "    }", "",
         "    public static void RemoveCardVar(CardModel? card, string key)", "    {",
         "        if (card == null) return;",
         "        Data(card).Vars.Remove(key);",
         "        SyncDeck(card, key, null);", "    }", "",
         "    public static void SetCardState(CardModel? card, string key, decimal value)", "    {",
         "        if (card == null) return;",
         "        var vars = Data(card).Vars;",
         "        if (!vars.TryGetValue(key, out var v)) vars[key] = v = new CardVar();",
         "        v.Value = value;",
         "        SyncDeck(card, key, v);", "    }", "",
         "    public static void AddCardState(CardModel? card, string key, decimal amount) => SetCardState(card, key, CardState(card, key) + amount);", "",
         "    public static void AddCardTag(CardModel? card, string tag) { if (card != null) Data(card).Tags.Add(tag); }",
         "    public static void RemoveCardTag(CardModel? card, string tag) { if (card != null) Data(card).Tags.Remove(tag); }", "",
         "    // ---- 뽑을 카드 더미 N번째 (1 = 맨 위, -1 = 맨 아래, 0 = 무작위 위치). 게임 목록은 Cards[0] 이 맨 위 ----",
         "    public static CardModel? DrawPileAt(Player? player, int n)", "    {",
         "        var cards = player?.PlayerCombatState?.DrawPile.Cards;",
         "        if (cards == null || n == 0) return null;",
         "        var i = n > 0 ? n - 1 : cards.Count + n;",
         "        return i >= 0 && i < cards.Count ? cards[i] : null;", "    }", "",
         "    /// <summary>뽑을 카드 더미 안에 있는 카드를 N번째 자리로 옮긴다 (넘치면 맨 위/맨 아래).</summary>",
         "    public static void MoveInDrawPile(CardModel card, int n)", "    {",
         "        var pile = card.Owner?.PlayerCombatState?.DrawPile;",
         "        if (pile == null || n == 0 || !pile.Cards.Contains(card)) return;",
         "        pile.RemoveInternal(card, true);",
         "        var count = pile.Cards.Count;",
         "        var i = n > 0 ? Math.Min(n - 1, count) : Math.Max(0, count + 1 + n);",
         "        pile.AddInternal(card, i, true);",
         "        pile.InvokeContentsChanged();", "    }", "",
         "    public static async Task PutInDrawPile(CardModel card, int n)", "    {",
         "        await CardPileCmd.Add(card, PileType.Draw, n == 0 ? CardPilePosition.Random : n > 0 ? CardPilePosition.Top : CardPilePosition.Bottom);",
         "        MoveInDrawPile(card, n);", "    }", "",
         "    public static async Task AddGeneratedToDrawPile(CardModel card, Player player, int n)", "    {",
         "        await CardPileCmd.AddGeneratedCardToCombat(card, PileType.Draw, player, n == 0 ? CardPilePosition.Random : n > 0 ? CardPilePosition.Top : CardPilePosition.Bottom);",
         "        MoveInDrawPile(card, n);", "    }", "",
         "    /// <summary>뽑을 카드 더미 N번째 카드부터 count 장을 손으로 가져온다.</summary>",
         "    public static async Task DrawFromPosition(Player? player, int n, int count)", "    {",
         "        for (var i = 0; i < count; i++)", "        {",
         "            var card = DrawPileAt(player, n);",
         "            if (card == null) return;",
         "            await CardPileCmd.Add(card, PileType.Hand);", "        }", "    }", "",
         "    /// <summary>사용을 마친 카드 수 (지금 쓰고 있는 카드는 아직 들어가지 않음).</summary>",
         "    public static int Played(Player? player, bool thisTurn, Func<CardModel, bool> filter)", "    {",
         "        if (player == null) return 0;",
         "        var cm = global::MegaCrit.Sts2.Core.Combat.CombatManager.Instance;",
         "        if (cm == null || !cm.IsInProgress) return 0;",
         "        var state = player.Creature.CombatState;",
         "        var n = 0;",
         "        foreach (var e in cm.History.CardPlaysFinished)", "        {",
         "            var card = e.CardPlay?.Card;",
         "            if (card == null || card.Owner != player) continue;",
         "            if (thisTurn && (state == null || !e.HappenedThisTurn(state))) continue;",
         "            if (filter(card)) n++;", "        }", "        return n;", "    }", "",
         "    /// <summary>카드의 자원 비용 (다른 파워의 '카드 자원 비용 +' 상시 효과 반영).</summary>",
         "    public static int ResCost(CardModel card, int baseCost, Type res)", "    {",
         "        var o = card.Owner?.Creature;", "        if (o == null) return baseCost;",
         f"        return Math.Max(0, baseCost + o.Powers.OfType<{mid}Power>().Sum(p => p.ResCostDelta(card, res)));", "    }", "",
         "    /// <summary>자원 지불: 충분하면 소모하고 true.</summary>",
         "    public static async Task<bool> Pay<T>(PlayerChoiceContext ctx, Creature owner, decimal amount, CardModel? source) where T : PowerModel",
         "    {", "        var cost = (int)amount;", "        var p = owner.GetPower<T>();", "        var have = p?.Amount ?? 0;",
         "        if (have < cost) return false;", "        if (cost > 0 && p != null)", "        {",
         "            if (have == cost) await PowerCmd.Remove(p);",
         "            else await PowerCmd.ModifyAmount(ctx, p, -cost, owner, source);", "        }", "        return true;", "    }", "",
         "    // ---- 소환수 ----",
         f"    public static async Task Summon<T>(PlayerChoiceContext ctx, Creature owner, CardModel? source) where T : {mid}SummonPower",
         "    {", "        if (owner.IsDead) return;", "        var cur = owner.GetPower<T>();", "        if (cur != null)", "        {",
         "            if (cur.Amount < cur.MaxRank) await PowerCmd.ModifyAmount(ctx, cur, 1m, owner, source);",
         "            else if (cur.ActOnMax) await cur.Act(ctx, null);", "            return;", "        }",
         f"        var team = owner.Powers.OfType<{mid}SummonPower>().ToList();",
         f"        var slots = SummonSlots + owner.Powers.OfType<{mid}Power>().Sum(p => p.SummonSlotBonus);",
         "        if (team.Count >= Math.Max(1, slots)) await PowerCmd.Remove(team[0]); // 가장 먼저 온 소환수가 돌아간다",
         "        await PowerCmd.Apply<T>(ctx, owner, 1m, owner, source);", "    }", "",
         f"    public static async Task Command<T>(PlayerChoiceContext ctx, Creature owner) where T : {mid}SummonPower",
         "    {", "        var p = owner.GetPower<T>();", "        if (p != null && owner.IsAlive) await p.Act(ctx, null);", "    }", "",
         "    public static async Task CommandAll(PlayerChoiceContext ctx, Creature owner)", "    {",
         f"        foreach (var p in owner.Powers.OfType<{mid}SummonPower>().ToList())",
         "            if (owner.IsAlive) await p.Act(ctx, null);", "    }", "",
         f"    public static async Task Unsummon<T>(Creature owner) where T : {mid}SummonPower",
         "    {", "        var p = owner.GetPower<T>();", "        if (p != null) await PowerCmd.Remove(p);", "    }", "",
         f"    public static int SummonCount(Creature? owner) => owner == null ? 0 : owner.Powers.OfType<{mid}SummonPower>().Count();", "",
         "    // ---- 선택지 / 카드 고르기 ----",
         "    public static T Option<T>(Player player) where T : CardModel", "    {",
         "        var c = (T)ModelDb.Card<T>().ToMutable();", "        c.Owner = player;", "        return c;", "    }", "",
         "    public static async Task<int> Choose(PlayerChoiceContext ctx, Player? player, params CardModel[] options)", "    {",
         "        if (player == null || options.Length == 0) return -1;",
         "        var picked = await CardSelectCmd.FromChooseACardScreen(ctx, options, player, false);",
         "        return Array.IndexOf(options, picked);", "    }", "",
         "    public static async Task<List<CardModel>> Pick(PlayerChoiceContext ctx, Player? player, PileType pile, int count, Func<CardModel, bool> filter, AbstractModel source)",
         "    {", "        if (player == null || count <= 0) return [];",
         f'        var prompt = new LocString("cards", "{up}-GIMMICK_PICK.title");',
         "        var cards = pile.GetPile(player).Cards.Where(filter).ToList();",
         "        if (cards.Count == 0) return [];",
         "        var n = Math.Min(count, cards.Count);",
         "        if (pile == PileType.Hand)",
         "            return (await CardSelectCmd.FromHand(ctx, player, new CardSelectorPrefs(prompt, n), filter, source)).ToList();",
         "        return (await CardSelectCmd.FromSimpleGrid(ctx, cards, player, new CardSelectorPrefs(prompt, n))).ToList();",
         "    }", "}", "",
         "// 소환수: 플레이어에게 붙는 파워. 스택 = 단계.",
         f"public abstract class {mid}SummonPower : {mid}Power", "{",
         "    public override PowerType Type => PowerType.Buff;",
         "    public override PowerStackType StackType => PowerStackType.Counter;",
         "    public abstract int MaxRank { get; }", "    public virtual bool ActOnMax => true;",
         "    public virtual int Timing => 0; // 0 = 턴 종료, 1 = 턴 시작, 2 = 자동 행동 없음",
         "    public abstract Task Act(PlayerChoiceContext choiceContext, Creature? other);", "",
         "    public override async Task BeforeSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)",
         "    {", "        if (Timing != 0 || side != Owner.Side || Owner.IsDead) return;", "        await Act(choiceContext, null);", "    }", "",
         "    public override async Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)",
         "    {", "        if (Timing != 1 || player.Creature != Owner || Owner.IsDead) return;", "        await Act(choiceContext, null);", "    }",
         "}", "",
         "// 선택지 카드 (고르기 화면에만 나오고 덱에는 들어가지 않음)",
         f"public abstract class {mid}ChoiceCard() : CustomCardModel(0, CardType.Skill, CardRarity.Token, TargetType.Self, false, false)",
         "{", "    public override CardPoolModel Pool => ModelDb.CardPool<TokenCardPool>();",
         '    public override string CustomPortraitPath => "choice.png".BigCardImagePath();',
         '    public override string PortraitPath => "choice.png".CardImagePath();',
         '    public override string BetaPortraitPath => "choice.png".CardImagePath();',
         "    protected override Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay) => Task.CompletedTask;", "}", ""]

    L.append(gen_card_number_runtime(mid))

    # 태그 툴팁용 파워
    for t in tags(project):
        L += [f"// 태그 '{t.get('name_ko')}' 툴팁", f"public sealed class {_pascal(t['id'])}TagPower : {mid}Power", "{",
              "    public override PowerType Type => PowerType.Buff;",
              "    public override PowerStackType StackType => PowerStackType.Single;",
              "    protected override bool IsVisibleInternal => false;", "}", ""]
    # 소환수
    for s in summons(project):
        cls = f"{_pascal(s['id'])}SummonPower"
        Cs = M._Ctx("power", {"id": s["id"], "trigger": "none", "enemy_mode": "all"})
        lines, _e = B.compile_blocks(s.get("blocks") or [], project, Cs, "        ", prefix=cls, extras=extras)
        timing = {"turn_end": 0, "turn_start": 1, "never": 2}.get(s.get("timing", "turn_end"), 0)
        L += [f"// 소환수 '{s.get('name_ko')}'", f"public sealed class {cls} : {mid}SummonPower", "{",
              f"    public override int MaxRank => {max(1, int(s.get('max_rank', 3) or 1))};",
              f"    public override bool ActOnMax => {'true' if s.get('act_on_max', True) else 'false'};",
              f"    public override int Timing => {timing};", "",
              "    public override async Task Act(PlayerChoiceContext choiceContext, Creature? other)", "    {",
              "        if (Owner == null || Owner.IsDead) return;", "        Flash();"] + lines + ["    }", "}", ""]
    # 구체
    for o in orbs(project):
        L += gen_orb(project, o, extras)
    # 블록이 만든 클래스 (선택지 카드 / 예약 파워) — 예약 파워 본문이 또 만들 수 있으니 끝날 때까지
    done = 0
    while done < len(extras):
        x = extras[done]
        done += 1
        if x["kind"] == "choice":
            L += [f"public sealed class {x['cls']} : {mid}ChoiceCard {{ }}", ""]
        elif x["kind"] == "delayed":
            Cd = M._Ctx("power", {"id": x["cls"], "trigger": "none", "enemy_mode": "all"})
            lines, _e = B.compile_blocks(x["blocks"], project, Cd, "        ", prefix=x["cls"], extras=extras)
            if x["when"] == "end":
                hook = ["    public override async Task BeforeSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)",
                        "    {", "        if (side != Owner.Side || Owner.IsDead) return;"]
            else:
                hook = ["    public override async Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)",
                        "    {", "        if (player.Creature != Owner || Owner.IsDead) return;"]
            L += [f"public sealed class {x['cls']} : {mid}Power", "{",
                  "    public override PowerType Type => PowerType.Buff;",
                  "    public override PowerStackType StackType => PowerStackType.Counter;", ""] + hook + [
                  "        var times_ = Amount;", "        Flash();",
                  "        for (var t_ = 0; t_ < times_ && Owner.IsAlive; t_++) await Run(choiceContext, null);",
                  "        if (Owner.Powers.Contains(this)) await PowerCmd.Remove(this);", "    }", "",
                  "    private async Task Run(PlayerChoiceContext choiceContext, Creature? other)", "    {"] + lines + ["    }", "}", ""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------------------
# 현지화
# ---------------------------------------------------------------------------
def localization(project, lang, files, extras):
    import modgen as M
    up = project["mod"]["id"].upper()
    files["cards"][f"{up}-GIMMICK_PICK.title"] = {"ko": "카드를 고르세요", "zh": "选择卡牌"}.get(lang, "Choose cards")
    for t in tags(project):
        lid = M.loc_id(project, t["id"] + "_tag_power")
        files["powers"][f"{lid}.title"] = _txt(t, "name", lang)
        d = _txt(t, "desc", lang) if (t.get("desc_ko") or t.get("desc_en")) else ""
        import blockcode as B
        for timing, label in TAG_TIMINGS:
            blocks = tag_blocks(t, timing)
            if not blocks:
                continue
            detail = B.describe(blocks, project, "card", lang)
            names = {"en": {"play":"When played", "draw":"When drawn", "discard":"When discarded",
                            "exhaust":"When exhausted", "hand_start":"At turn start, while in hand",
                            "hand_end":"At turn end, while in hand"},
                     "zh": {"play":"打出时", "draw":"抽到时", "discard":"丢弃时", "exhaust":"消耗时",
                            "hand_start":"回合开始时，若在手牌中", "hand_end":"回合结束时，若在手牌中"}}
            if timing == "hand_play":
                selected = t.get("played_filter") or "Any"
                if selected.startswith("tag:"):
                    target_tag = find_tag(project, selected[4:])
                    filter_label = _txt(target_tag, "name", lang) if target_tag else selected
                elif selected.startswith("kw:"):
                    filter_label = dict(M.CARD_KEYWORDS).get(selected[3:], selected)
                else:
                    filter_label = {"ko":"아무 카드", "en":"any card", "zh":"任意牌"}.get(lang, "any card")
                names["en"][timing] = "While in hand, whenever you play another card · " + filter_label
                names["zh"][timing] = "在手牌中时，每当你打出另一张牌 · " + filter_label
                label += " · " + filter_label + f" {t.get('played_every', 1)}장마다 (" + ("이번 턴" if t.get("played_scope", "turn") == "turn" else "이번 전투") + ")"
                names["en"][timing] += f" · every {t.get('played_every', 1)} ({t.get('played_scope', 'turn')})"
                names["zh"][timing] += f" · 每{t.get('played_every', 1)}张 ({t.get('played_scope', 'turn')})"
            lead = names.get(lang, {}).get(timing, label)
            d = "\n".join(part for part in (d, lead + ": " + detail) if part)
        if t.get("hand_cost_enabled"):
            selected = t.get("hand_cost_filter", "Any")
            name = dict(tag_play_filters(project)).get(selected, selected)
            amount = int(t.get("hand_cost_amount", 1))
            aura = {"ko": f"손패에 있는 동안 다른 카드의 비용 {amount} 감소 · {name}",
                    "en": f"While in hand, other cards cost {amount} less · {selected}",
                    "zh": f"在手牌中时，其他牌费用降低{amount} · {selected}"}.get(lang)
            d = "\n".join(part for part in (d, aura) if part)
        files["powers"][f"{lid}.description"] = d
        files["powers"][f"{lid}.smartDescription"] = d
    for s in summons(project):
        lid = M.loc_id(project, s["id"] + "_summon_power")
        smart = summon_text(project, s, lang)
        files["powers"][f"{lid}.title"] = _txt(s, "name", lang)
        files["powers"][f"{lid}.description"] = smart.replace("[blue]{Amount}[/blue]", "X").replace("{Amount}", "X")
        files["powers"][f"{lid}.smartDescription"] = smart
    import fxbtn
    import pets as PT
    fxbtn.localization(project, lang, files)
    PT.localization(project, lang, files)
    files.setdefault("orbs", {})
    for o in orbs(project):
        lid = M.loc_id(project, o["id"] + "_orb")
        files["orbs"][f"{lid}.title"] = _txt(o, "name", lang)
        smart = orb_text(project, o, lang)
        files["orbs"][f"{lid}.smartDescription"] = smart
        files["orbs"][f"{lid}.description"] = smart.replace("[blue]{Passive}[/blue]", str(o.get("passive", 0))) \
            .replace("[blue]{Evoke}[/blue]", str(o.get("evoke", 0)))
    for x in extras:
        lid = f"{up}-{M.game_snake(x['cls'])}"
        if x["kind"] == "choice":
            files["cards"][f"{lid}.title"] = x["title"].get(lang) or x["title"]["ko"] or x["title"]["en"] or "?"
            files["cards"][f"{lid}.description"] = _no_amount(x["desc"].get(lang) or x["desc"]["ko"])
        elif x["kind"] == "delayed":
            files["powers"][f"{lid}.title"] = x["title"].get(lang) or x["title"]["ko"]
            files["powers"][f"{lid}.description"] = _no_amount(x["desc"].get(lang) or x["desc"]["ko"])
            files["powers"][f"{lid}.smartDescription"] = x["desc"].get(lang) or x["desc"]["ko"]


def _no_amount(s):
    return (s or "").replace("[blue]{Amount}[/blue]", "X").replace("{Amount}", "X")


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------
def validate(project):
    import blockcode as B
    import modgen as M
    errors, warnings = [], []
    seen = set()
    for t in tags(project):
        if not M.ID_RE.match(t.get("id", "")):
            errors.append(f"태그 ID '{t.get('id')}'는 영문 소문자와 _ 만 쓸 수 있습니다.")
        if t["id"] in seen:
            errors.append(f"태그 ID '{t['id']}'가 중복됩니다.")
        seen.add(t["id"])
        try:
            if not 1 <= int(t.get("played_every", 1)) <= 999 or t.get("played_scope", "turn") not in ("turn", "combat"):
                raise ValueError("사용 장수·집계 기준을 다시 설정하세요.")
            if not 0 <= int(t.get("hand_cost_amount", 1)) <= 99:
                raise ValueError("손패 비용 감소량은 0~99로 설정하세요.")
            tag_play_filter_expr(project, {"played_filter": t.get("hand_cost_filter", "Any")})
            tag_play_filter_expr(project, t)
        except ValueError as error:
            errors.append(f"키워드 '{t['id']}': {error}")
        sample = next(iter(project.get("cards", [])), M.new_card("keyword_sample"))
        for timing, label in TAG_TIMINGS:
            if timing == "hand_aura":
                try:
                    import handaura
                    handaura.rules(project, sample, t)
                except ValueError as error:
                    errors.append(f"키워드 '{t['id']}' 지속 보정: {error}")
                continue
            context = M._Ctx("card", sample) if timing == "play" else M.card_event_context(sample, timing)
            _lines, block_errors = B.compile_blocks(tag_blocks(t, timing), project, context)
            errors += [f"키워드 '{t.get('name_ko') or t['id']}' {label}: {message}" for message in dict.fromkeys(block_errors)]
    seen = set()
    for s in summons(project):
        where = f"소환수 '{s.get('name_ko') or s['id']}'"
        if not M.ID_RE.match(s.get("id", "")):
            errors.append(f"소환수 ID '{s.get('id')}'는 영문 소문자와 _ 만 쓸 수 있습니다.")
        if s["id"] in seen:
            errors.append(f"소환수 ID '{s['id']}'가 중복됩니다.")
        seen.add(s["id"])
        if not s.get("blocks") and s.get("timing") != "never":
            warnings.append(f"{where}: 행동 블록이 비어 있습니다.")
        _l, e = B.compile_blocks(s.get("blocks") or [], project, M._Ctx("power", {"id": s["id"], "trigger": "none"}))
        errors += [f"{where}: {x}" for x in dict.fromkeys(e)]
    for o in orbs(project):
        where = f"구체 '{o.get('name_ko') or o['id']}'"
        if not M.ID_RE.match(o.get("id", "")):
            errors.append(f"구체 ID '{o.get('id')}'는 영문 소문자와 _ 만 쓸 수 있습니다.")
        if o["id"] in seen:
            errors.append(f"{where}: ID가 다른 소환수/구체와 겹칩니다.")
        seen.add(o["id"])
        for key, n in (("passive_blocks", "지속"), ("evoke_blocks", "발현")):
            _l, e = B.compile_blocks(o.get(key) or [], project, M._Ctx("orb", o))
            errors += [f"{where} {n}: {x}" for x in dict.fromkeys(e)]
        if not HEX_RE.match(o.get("tint") or "#ffffff"):
            errors.append(f"{where}: 색은 #RRGGBB 형식이어야 합니다.")
    import fxbtn
    fe, fw = fxbtn.validate(project, seen)
    errors += fe
    warnings += fw
    import pets as PT
    pe, pw_ = PT.validate(project, seen)
    errors += pe
    warnings += pw_
    uses_orbs = any(b["op"] in ("channel", "evoke", "orb_passive_all") for b in _all_blocks(project))
    ch = project.get("character") or {}
    if uses_orbs and ch.get("enabled") and int(ch.get("orb_slots") or 0) <= 0 and \
            not any(b["op"] == "orb_slots" for b in _all_blocks(project)):
        warnings.append("구체를 영창하는 블록이 있지만 캐릭터의 구체 슬롯이 0개입니다 (캐릭터 탭에서 정하세요).")
    return errors, warnings


def orb_image_jobs(project):
    """(원본 경로, 파일 이름, 색) — 구체 아이콘 (images/orbs/)."""
    return [(o.get("image") or "", f"{o['id']}_orb.png", o.get("tint") or "#7fb3ff") for o in orbs(project)]


def image_jobs(project):
    """(원본 경로, 파워 이미지 이름) — 소환수 아이콘."""
    out = []
    for s in summons(project):
        out.append((s.get("image") or "", f"{s['id']}_summon_power.png"))
    for t in tags(project):
        out.append(("", f"{t['id']}_tag_power.png"))
    return out


# ---------------------------------------------------------------------------
# 예시: 해적·마법사 스타일 기믹 한 벌
# ---------------------------------------------------------------------------
def add_examples(project):
    """현재 프로젝트에 예시 기믹(태그·자원·소환수·날씨·선택지)을 추가한다. 추가한 이름 목록을 돌려준다."""
    import modgen as M
    normalize(project)
    g = project["gimmicks"]
    ids = {x["id"] for k in ("cards", "relics", "potions", "powers") for x in project.get(k, [])}
    ids |= {t["id"] for t in g["tags"]} | {s["id"] for s in g["summons"]}

    def uid(base):
        n, i = base, 0
        while n in ids:
            i += 1
            n = f"{base}_{letters(i).lower()}"
        ids.add(n)
        return n
    N = lambda v, up=0: {"t": "num", "v": v, "up": up}  # noqa: E731

    def blk(op, body=None, els=None, third=None, **args):
        import blockcode as B
        b = B.new_block(op)
        b["args"].update(args)
        if body is not None:
            b["body"] = body
        if els is not None:
            b["else"] = els
        if third is not None:
            b["third"] = third
        return b

    added = []
    # --- 1) 바이퍼식: 태그 + 지속 자원 + 연계 ---
    t_fist = new_tag(uid("fist"))
    t_fist.update(name_ko="격투", name_en="Brawl", desc_ko="사용하면 [gold]해룡 에너지[/gold]를 1 얻습니다.",
                  desc_en="When played, gain 1 [gold]Sea Dragon[/gold].")
    g["tags"].append(t_fist)
    dragon = M.new_power(uid("sea_dragon"))
    dragon.update(name_ko="해룡 에너지", name_en="Sea Dragon", type="Buff", stack="Counter", trigger="none", effects=[],
                  cap=10, desc_ko="", desc_en="")
    project["powers"].append(dragon)
    keyc = "c:" + dragon["id"]
    combo = M.new_power(uid("combo_counter"))
    combo.update(name_ko="연계 표시", name_en="Combo", trigger="none", effects=[], hidden=True)
    straight = M.new_card(uid("straight"))
    straight.update(name_ko="스트레이트", name_en="Straight", type="Attack", cost=1, upgrade_cost=1, target="AnyEnemy",
                    gtags=[t_fist["id"]],
                    glow_cond={"t": "cmp", "a": {"t": "played", "scope": "turn", "filter": "tag:" + t_fist["id"]}, "op": ">=", "b": N(2)},
                    effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                        blk("damage", who="target", amount=N(6, 3), hits=1, powered=True),
                        blk("apply_power", who="self", power=keyc, amount=N(1)),
                        blk("if", cond={"t": "cmp", "a": {"t": "played", "scope": "turn", "filter": "tag:" + t_fist["id"]},
                                        "op": ">=", "b": N(2)},
                            body=[blk("damage", who="target", amount=N(4, 2), hits=1, powered=True)])])])
    serpent = M.new_card(uid("dragon_strike"))
    serpent.update(name_ko="수룡 강타", name_en="Water Dragon Smash", type="Attack", cost=1, upgrade_cost=1, target="AnyEnemy",
                   res_power=keyc, res_cost=3, effects=[M.new_effect("damage", 16, 6)])
    project["cards"] += [straight, serpent]
    added += ["태그 '격투'", "파워 '해룡 에너지'(최대 10)", "카드 '스트레이트'(연계 2 이상이면 추가타·금색 테두리)",
              "카드 '수룡 강타'(해룡 에너지 3 소모)"]
    del combo  # 숨김 카운터 예시는 아래 마법사 예시로 대신

    # --- 2) 캐논슈터식: 최대 6 포탄 + 낼 수 있으면 보너스 ---
    shell = M.new_power(uid("cannon_shell"))
    shell.update(name_ko="포탄", name_en="Shell", trigger="none", effects=[], cap=6)
    project["powers"].append(shell)
    load = M.new_card(uid("load_shells"))
    load.update(name_ko="장전", name_en="Load", type="Skill", cost=1, upgrade_cost=0, target="Self",
                effects=[M.new_effect("block", 5, 3), M.new_effect("power", 3, 0, power="c:" + shell["id"], target="self")])
    barrage = M.new_card(uid("barrage"))
    barrage.update(name_ko="일제 포격", name_en="Barrage", type="Attack", cost=1, upgrade_cost=1, target="AllEnemies",
                   effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                       blk("damage", who="all", amount=N(5, 2), hits=1, powered=True),
                       blk("pay", power="c:" + shell["id"], amount=N(2),
                           body=[blk("damage", who="all", amount=N(8, 3), hits=1, powered=True)])])])
    project["cards"] += [load, barrage]
    added += ["파워 '포탄'(최대 6)", "카드 '장전'", "카드 '일제 포격'(포탄 2를 낼 수 있으면 추가 포격)"]

    # --- 3) 캡틴식: 소환수 ---
    octo = new_summon(uid("octopus"))
    octo.update(name_ko="옥토퍼스", name_en="Octopus", max_rank=3, timing="turn_end",
                blocks=[blk("repeat", times={"t": "amount"},
                            body=[blk("damage", who="random", amount=N(5), hits=1, powered=False)])])
    navi = new_summon(uid("navigator"))
    navi.update(name_ko="항해사", name_en="Navigator", max_rank=3, timing="turn_end",
                blocks=[blk("block", amount={"t": "op", "op": "*", "a": N(3), "b": {"t": "amount"}})])
    g["summons"] += [octo, navi]
    c_octo = M.new_card(uid("summon_octopus"))
    c_octo.update(name_ko="옥토퍼스 호출", name_en="Call Octopus", type="Skill", cost=1, upgrade_cost=0, target="Self",
                  effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[blk("summon", summon=octo["id"])])])
    c_cmd = M.new_card(uid("full_command"))
    c_cmd.update(name_ko="총지휘", name_en="Full Command", type="Skill", cost=1, upgrade_cost=1, target="Self",
                 keywords=["Exhaust"], upgrade_add_keyword="",
                 effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                     blk("summon", summon=navi["id"]), blk("command", summon="*")])])
    project["cards"] += [c_octo, c_cmd]
    added += ["소환수 '옥토퍼스'(단계만큼 연사)", "소환수 '항해사'(방어도)", "카드 '옥토퍼스 호출'", "카드 '총지휘'(모든 소환수 즉시 행동)"]

    # --- 4) 썬콜식: 날씨(하나만) + 빙결 임계치 + 충전 넘침 ---
    frostfront = M.new_power(uid("cold_front"))
    frostfront.update(name_ko="한파", name_en="Cold Front", trigger="turn_end", group="날씨", stack="Single",
                      effects=[M.new_effect("block", 4, 0)])
    thunder = M.new_power(uid("thunder_front"))
    thunder.update(name_ko="뇌운", name_en="Thunderhead", trigger="turn_end", group="날씨", stack="Single", enemy_mode="random",
                   effects=[M.new_effect("damage", 5, 0)])
    frost = M.new_power(uid("frost"))
    frost.update(name_ko="빙결", name_en="Frost", type="Debuff", trigger="none", effects=[], threshold=5, threshold_mode="all",
                 threshold_blocks=[blk("lose_hp", who="self", amount={"t": "op", "op": "*", "a": {"t": "event"}, "b": N(2)})])
    charge = M.new_power(uid("charge"))
    charge.update(name_ko="충전", name_en="Charge", trigger="none", effects=[], cap=10,
                  overflow_blocks=[blk("damage", who="random", amount={"t": "op", "op": "*", "a": {"t": "event"}, "b": N(2)},
                                       hits=1, powered=False)])
    project["powers"] += [frostfront, thunder, frost, charge]
    shift = M.new_card(uid("weather_shift"))
    shift.update(name_ko="기상 변화", name_en="Weather Shift", type="Skill", cost=0, upgrade_cost=0, target="Self",
                 effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                     blk("choice", opt1={"ko": "한파", "en": "Cold Front", "zh": "寒潮"}, opt2={"ko": "뇌운", "en": "Thunderhead", "zh": "雷云"},
                         opt3={"ko": "", "en": ""},
                         body=[blk("apply_power", who="self", power="c:" + frostfront["id"], amount=N(1))],
                         els=[blk("apply_power", who="self", power="c:" + thunder["id"], amount=N(1))], third=[])])])
    chill = M.new_card(uid("chilling_bolt"))
    chill.update(name_ko="냉기 화살", name_en="Chilling Bolt", type="Attack", cost=1, upgrade_cost=1, target="AnyEnemy",
                 effects=[M.new_effect("damage", 5, 2), M.new_effect("power", 2, 1, power="c:" + frost["id"], target="enemy"),
                          M.new_effect("power", 3, 0, power="c:" + charge["id"], target="self")])
    project["cards"] += [shift, chill]
    added += ["파워 '한파'·'뇌운'(그룹 '날씨': 하나만 유지)", "파워 '빙결'(5 이상이면 깨지며 피해)",
              "파워 '충전'(최대 10, 넘치면 무작위 적 피해)", "카드 '기상 변화'(둘 중 하나 고르기)", "카드 '냉기 화살'"]

    # --- 5) 비숍식: 카드 고르기 + 다음 턴 예약 ---
    prayer = M.new_card(uid("prayer"))
    prayer.update(name_ko="기도", name_en="Prayer", type="Skill", cost=1, upgrade_cost=1, target="Self",
                  effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                      blk("pick", pile="Discard", ctype="Any", count=N(1), action="hand"),
                      blk("delayed", when="start", times=N(1),
                          body=[blk("draw", amount=N(1)), blk("energy", amount=N(1))])])])
    project["cards"].append(prayer)
    added += ["카드 '기도'(버린 카드 1장을 골라 가져오고, 다음 턴에 드로우·에너지)"]

    # --- 6) 디펙트식: 새 구체 ---
    fire = new_orb(uid("kindling"))
    fire.update(name_ko="잉걸불", name_en="Ember", look="plasma_orb", tint="#ff8a3d", passive=2, evoke=5, timing="turn_end",
                passive_blocks=[blk("damage", who="all", amount={"t": "orb_passive"}, hits=1, powered=False)],
                evoke_blocks=[blk("damage", who="all", amount={"t": "orb_evoke"}, hits=1, powered=False),
                              blk("apply_power", who="all", power="Vulnerable", amount=N(1))])
    leech = new_orb(uid("leech"))
    leech.update(name_ko="흡혈", name_en="Leech", look="dark_orb", tint="#d03a5a", passive=2, evoke=4, timing="turn_end",
                 passive_blocks=[blk("orb_grow", amount={"t": "orb_passive"})],
                 evoke_blocks=[blk("random_enemy", body=[blk("damage", who="it", amount={"t": "orb_evoke"}, hits=1, powered=False)]),
                               blk("heal", who="self", amount=N(2))])
    g["orbs"] += [fire, leech]
    c_ch = M.new_card(uid("kindle"))
    c_ch.update(name_ko="불씨 영창", name_en="Kindle", type="Skill", cost=1, upgrade_cost=0, target="Self",
                effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[blk("channel", orb="o:" + fire["id"], count=N(1))])])
    c_ev = M.new_card(uid("overload"))
    c_ev.update(name_ko="과부하", name_en="Overload", type="Skill", cost=1, upgrade_cost=1, target="Self",
                effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                    blk("channel", orb="o:" + leech["id"], count=N(1)), blk("evoke", which="front", count=N(2))])])
    project["cards"] += [c_ch, c_ev]
    ch = project.get("character") or {}
    if ch.get("enabled") and int(ch.get("orb_slots") or 0) <= 0:
        ch["orb_slots"] = 3
        added.append("캐릭터 구체 슬롯을 3개로 설정")
    added += ["구체 '잉걸불'(지속: 모든 적 피해, 발현: 모든 적 피해 + 취약)", "구체 '흡혈'(지속: 발현 피해가 자람)",
              "카드 '불씨 영창'(잉걸불 영창)", "카드 '과부하'(흡혈 영창 후 맨 앞 구체 2번 발현)"]

    # --- 7) 리젠트식: 별 + 단조 ---
    c_star = M.new_card(uid("starfall"))
    c_star.update(name_ko="별똥별", name_en="Starfall", type="Attack", cost=0, upgrade_cost=0, target="AnyEnemy",
                  star_cost=2, effects=[M.new_effect("damage", 12, 4)])
    c_gain = M.new_card(uid("stargaze"))
    c_gain.update(name_ko="별 바라보기", name_en="Stargaze", type="Skill", cost=1, upgrade_cost=1, target="Self",
                  effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                      blk("stars", amount=N(2, 1)), blk("forge", amount=N(4, 2))])])
    c_x = M.new_card(uid("star_shower"))
    c_x.update(name_ko="유성우", name_en="Star Shower", type="Attack", cost=0, upgrade_cost=0, target="AllEnemies",
               star_x=True, effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                   blk("repeat", times={"t": "star_x"}, body=[blk("damage", who="all", amount=N(4, 2), hits=1, powered=True)])])])
    project["cards"] += [c_star, c_gain, c_x]
    if ch.get("enabled"):
        ch["show_stars"] = True
    added += ["카드 '별똥별'(별 2 비용)", "카드 '별 바라보기'(별 2 얻기 + 단조 4)", "카드 '유성우'(별 X: X번 모든 적 피해)",
              "캐릭터: 별 카운터 항상 표시"]

    # --- 8) 네크로바인더식: 골골이 ---
    c_sum = M.new_card(uid("raise_bones"))
    c_sum.update(name_ko="뼈 일으키기", name_en="Raise Bones", type="Skill", cost=1, upgrade_cost=1, target="Self",
                 effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[blk("osty_summon", amount=N(5, 3))])])
    c_poke = M.new_card(uid("bone_poke"))
    c_poke.update(name_ko="뼈 찌르기", name_en="Bone Poke", type="Attack", cost=1, upgrade_cost=1, target="AnyEnemy",
                  effects=[M.new_effect("code", 0, 0, auto_text=True, blocks=[
                      blk("osty_attack", who="target", amount={"t": "op", "op": "+", "a": N(4, 2), "b": {"t": "osty", "what": "hp"}},
                          hits=1)])])
    project["cards"] += [c_sum, c_poke]
    added += ["카드 '뼈 일으키기'(골골이 소환 5)", "카드 '뼈 찌르기'(골골이가 4 + 골골이 체력만큼 피해)"]

    # --- 9) 카스토리스식: 직접 그린 이펙트 + 전투 버튼 ---
    import fxbtn
    added += fxbtn.add_examples(project, uid, blk, N)

    # --- 네크로바인더식 골골이형 동료 ---
    import pets as PT
    added += PT.add_examples(project, uid, blk, N)

    # --- 10) 파워 카드의 상시 효과로 기믹 강화 ---
    mods = [
        dict(M.new_modifier("orb_value", 1, True), ref=""),
        dict(M.new_modifier("orb_passive_times", 1, False), ref="o:" + fire["id"]),
        dict(M.new_modifier("orb_slots", 1, False)),
        dict(M.new_modifier("star_cost", -1, False), filter="Attack"),
        dict(M.new_modifier("osty_dmg", 2, True)),
        dict(M.new_modifier("summon_amount", 2, False)),
        dict(M.new_modifier("summon_slots", 1, False)),
        dict(M.new_modifier("res_cap", 4, False), ref=keyc),
        dict(M.new_modifier("res_cost", -1, False), ref=keyc, filter="Any"),
        dict(M.new_modifier("button_cost", -1, False), ref=g["buttons"][-1]["id"] if g["buttons"] else ""),
        dict(M.new_modifier("button_uses", 1, False), ref=""),
        dict(M.new_modifier("stars_for_energy", 0, False)),
        dict(M.new_modifier("dmg_dealt_add", 2, True), filter="tag:" + t_fist["id"]),
        dict(M.new_modifier("pet_dmg", 2, False), ref=""),
    ]
    master = M.new_power(uid("gimmick_mastery"))
    master.update(name_ko="기믹 숙련", name_en="Gimmick Mastery", type="Buff", stack="Counter", trigger="none",
                  effects=[], modifiers=mods)
    project["powers"].append(master)
    c_m = M.new_card(uid("mastery"))
    c_m.update(name_ko="숙련", name_en="Mastery", type="Power", cost=2, upgrade_cost=1, target="Self",
               effects=[M.new_effect("power", 1, 0, power="c:" + master["id"], target="self")])
    project["cards"].append(c_m)
    added += ["파워 '기믹 숙련' + 파워 카드 '숙련'(상시 효과로 구체 수치·구체 슬롯·별 비용·골골이 피해·소환 슬롯·"
              "해룡 에너지 최대치/비용·숨결 버튼 비용/횟수·격투 카드 피해를 바꿈)"]
    return added


# ---------------------------------------------------------------------------
# 직업 시스템: 구체(디펙트) · 별/단조(리젠트) · 골골이(네크로바인더)
# ---------------------------------------------------------------------------
HEX_RE = __import__("re").compile(r"^#?[0-9a-fA-F]{6}$")
ORB_LOOKS = [("lightning_orb", "전기 모양"), ("frost_orb", "냉기 모양"), ("dark_orb", "암흑 모양"),
             ("plasma_orb", "플라즈마 모양"), ("glass_orb", "유리 모양")]
ORB_TIMINGS = [("turn_end", "내 턴 종료 시 지속 효과"), ("turn_start", "내 턴 시작 시 지속 효과"), ("none", "지속 효과 없음 (발현만)")]
BASE_ORBS = {"Lightning": ("LightningOrb", "전기", "Lightning"), "Frost": ("FrostOrb", "냉기", "Frost"),
             "Dark": ("DarkOrb", "암흑", "Dark"), "Plasma": ("PlasmaOrb", "플라즈마", "Plasma"),
             "Glass": ("GlassOrb", "유리", "Glass")}
_ORB_SFX = {"lightning_orb": "lightning", "frost_orb": "frost", "dark_orb": "dark", "plasma_orb": "plasma", "glass_orb": "glass"}


def new_orb(oid="new_orb"):
    return {"id": oid, "name_ko": "새 구체", "name_en": "New Orb", "desc_ko": "", "desc_en": "",
            "look": "lightning_orb", "tint": "#ffffff", "image": "", "passive": 3, "evoke": 8, "timing": "turn_end",
            "passive_blocks": [{"op": "damage", "args": {"who": "random", "amount": {"t": "orb_passive"}, "hits": 1, "powered": False}}],
            "evoke_blocks": [{"op": "damage", "args": {"who": "random", "amount": {"t": "orb_evoke"}, "hits": 1, "powered": False}}]}


def orbs(project):
    return (project.get("gimmicks") or {}).get("orbs", [])


def find_orb(project, oid):
    return next((o for o in orbs(project) if o["id"] == oid), None)


def orb_meta(project, key):
    """'Lightning' (기본) / 'o:id' (새 구체) -> {cls, ko, en}"""
    if not key:
        return None
    if key in BASE_ORBS:
        cls, ko, en = BASE_ORBS[key]
        return {"cls": f"global::MegaCrit.Sts2.Core.Models.Orbs.{cls}", "ko": ko, "en": en}
    if key.startswith("o:"):
        o = find_orb(project, key[2:])
        if o:
            return {"cls": f"{ns(project)}.{_pascal(o['id'])}Orb", "ko": _txt(o, "name", "ko"), "en": _txt(o, "name", "en")}
    return None


def orb_options(project):
    return [(k, f"{v[1]} (기본)") for k, v in BASE_ORBS.items()] + \
        [("o:" + o["id"], f"◎ {o.get('name_ko') or o['id']} (새 구체)") for o in orbs(project)]


def _darker(hexcol, k=0.45):
    h = (hexcol or "#ffffff").lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        r = g = b = 255
    return "%02x%02x%02x" % (int(r * k), int(g * k), int(b * k))


def orb_text(project, o, lang):
    import blockcode as B
    custom = (o.get(f"desc_{lang}") or "").strip()
    if custom:
        return custom
    p = B.describe(o.get("passive_blocks"), project, "orb", lang)
    e = B.describe(o.get("evoke_blocks"), project, "orb", lang)
    t = o.get("timing", "turn_end")
    out = []
    if t != "none" and p:
        when = {"turn_end": ("턴 종료 시, ", "At the end of turn, "), "turn_start": ("턴 시작 시, ", "At the start of turn, ")}[t]
        out.append(("[gold]지속:[/gold] " + when[0] if lang == "ko" else "[gold]Passive:[/gold] " + when[1]) +
                   (p if lang == "ko" else p[:1].lower() + p[1:]))
    if e:
        out.append(("[gold]발현:[/gold] " if lang == "ko" else "[gold]Evoke:[/gold] ") + e)
    return "\n".join(out)


def gen_orb(project, o, extras):
    import blockcode as B
    import modgen as M
    cls = f"{_pascal(o['id'])}Orb"
    look = o.get("look") or "lightning_orb"
    sfx = _ORB_SFX.get(look, "lightning")
    tint = (o.get("tint") or "#ffffff").lstrip("#").lower()
    C = M._Ctx("orb", o)
    pl, _e = B.compile_blocks(o.get("passive_blocks") or [], project, C, "        ", prefix=cls + "Pa", extras=extras)
    el, _e = B.compile_blocks(o.get("evoke_blocks") or [], project, C, "        ", prefix=cls + "Ev", extras=extras)
    channel_sfx = f"event:/sfx/characters/defect/defect_{sfx}_channel"
    evoke_sfx = "event:/sfx/characters/defect/defect_lightning_evoke" if sfx == "lightning" else channel_sfx
    passive_sfx = "event:/sfx/characters/defect/defect_lightning_passive" if sfx == "lightning" else channel_sfx
    L = [f"// 구체 '{o.get('name_ko')}'", f"public sealed class {cls} : CustomOrbModel", "{",
         "    private decimal _grow = 0m; // '이 구체의 발현 수치 +' 블록이 쌓는 값",
         f'    public override global::Godot.Color DarkenedColor => new("{_darker(tint)}");',
         f'    public override string? CustomIconPath => "{o["id"]}_orb.png".OrbImagePath();',
         f'    public override string? CustomSpritePath => global::MegaCrit.Sts2.Core.Helpers.SceneHelper.GetScenePath("orbs/orb_visuals/{look}");',
         f'    public override string? CustomChannelSfx => "{channel_sfx}";',
         f'    public override string? CustomEvokeSfx => "{evoke_sfx}";',
         f'    public override string? CustomPassiveSfx => "{passive_sfx}";']
    if tint != "ffffff":
        L += ["", "    public override global::Godot.Node2D? CreateCustomSprite()", "    {",
              "        var scene = global::Godot.ResourceLoader.Load<global::Godot.PackedScene>(CustomSpritePath!);",
              "        if (scene == null) return null;",
              "        var node = scene.Instantiate<global::Godot.Node2D>();",
              f'        node.Modulate = new global::Godot.Color("{tint}");', "        return node;", "    }"]
    L += ["", f"    public override decimal PassiveVal => ModifyOrbValue({_num(o.get('passive'))}m);",
          f"    public override decimal EvokeVal => ModifyOrbValue({_num(o.get('evoke'))}m + _grow);", ""]
    t = o.get("timing", "turn_end")
    if t == "turn_end":
        L += ["    public override async Task BeforeTurnEndOrbTrigger(PlayerChoiceContext choiceContext)", "    {",
              "        await TriggerPassive(choiceContext, null);", "    }", ""]
    elif t == "turn_start":
        L += ["    public override async Task AfterTurnStartOrbTrigger(PlayerChoiceContext choiceContext)", "    {",
              "        await TriggerPassive(choiceContext, null);", "    }", ""]
    L += ["    public override async Task Passive(PlayerChoiceContext choiceContext, Creature? target)", "    {",
          "        ActivatePassive();", "        PlayPassiveSfx();"] + pl + ["    }", "",
          "    public override async Task<IEnumerable<Creature>> Evoke(PlayerChoiceContext choiceContext)", "    {",
          "        PlayEvokeSfx();"] + el + ["        return Array.Empty<Creature>();", "    }", "}", ""]
    return L


def _num(v):
    try:
        f = float(v or 0)
    except (TypeError, ValueError):
        f = 0.0
    return str(int(f)) if f.is_integer() else repr(f)


def _all_blocks(project):
    import blockcode as B
    progs = []
    for key in ("cards", "relics", "potions", "powers"):
        for it in project.get(key, []):
            for e in it.get("effects", []):
                progs.append(e.get("blocks") or [])
            for k in ("overflow_blocks", "threshold_blocks"):
                progs.append(it.get(k) or [])
    for x in summons(project):
        progs.append(x.get("blocks") or [])
    for o in orbs(project):
        progs += [o.get("passive_blocks") or [], o.get("evoke_blocks") or []]
    for prog in progs:
        yield from B.walk(prog)


def class_tips(project, item):
    """블록에 쓰인 직업 시스템의 툴팁 (영창·발현·단조·소환·구체)."""
    import blockcode as B
    out = []
    for e in item.get("effects", []):
        for b in B.walk(e.get("blocks") or []):
            op, a = b["op"], b.get("args", {})
            if op == "channel":
                out.append("HoverTipFactory.Static(StaticHoverTip.Channeling)")
                om = orb_meta(project, a.get("orb"))
                if om:
                    out.append(f"HoverTipFactory.FromOrb<{om['cls']}>()")
            elif op == "evoke":
                out.append("HoverTipFactory.Static(StaticHoverTip.Evoke)")
            elif op == "forge":
                out.append(".. HoverTipFactory.FromForge()")
            elif op == "osty_summon":
                out.append("HoverTipFactory.Static(StaticHoverTip.SummonStatic)")
    return list(dict.fromkeys(out))


def card_upgrade_lines(card):
    d = int(card.get("star_cost_up") or 0)
    if d and not card.get("star_x") and int(card.get("star_cost") or 0) > 0:
        return [f"        UpgradeStarCostBy({d});"]
    return []


def character_members(project):
    ch = project.get("character") or {}
    L = []
    n = int(ch.get("orb_slots") or 0)
    if n > 0:
        L.append(f"    public override int BaseOrbSlotCount => {n};")
    if ch.get("show_stars"):
        L.append("    public override bool ShouldAlwaysShowStarCounter => true;")
    return L


def gen_card_number_runtime(mid):
    """Track ordered damage edits on each combat card, with real expiry."""
    return r'''public static partial class $MID$Gimmicks
{
    private sealed record DamageEdit(decimal Amount, bool Set, string Duration);
    private sealed class DamageEdits
    {
        public decimal Base;
        public decimal Last;
        public readonly List<DamageEdit> Edits = new();
    }
    private sealed class CardDamageEdits
    {
        public readonly Dictionary<MegaCrit.Sts2.Core.Localization.DynamicVars.DynamicVar, DamageEdits> Vars = new();
    }
    private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<CardModel, CardDamageEdits> DamageChanges = new();

    // Preserve unrelated upgrades/changes made since our last update.
    private static void CaptureDamage(MegaCrit.Sts2.Core.Localization.DynamicVars.DynamicVar v, DamageEdits state)
        => state.Base += v.BaseValue - state.Last;

    private static void ApplyDamage(MegaCrit.Sts2.Core.Localization.DynamicVars.DynamicVar v, DamageEdits state)
    {
        var value = state.Base;
        foreach (var edit in state.Edits)
            value = Math.Max(0m, edit.Set ? edit.Amount : value + edit.Amount);
        v.BaseValue = value;
        state.Last = v.BaseValue;
    }

    public static void EditCardDamage(CardModel card, decimal amount, bool set, string duration)
        => EditCardNumber(card, "damage", amount, set, duration);

    private static bool MatchesCardNumber(MegaCrit.Sts2.Core.Localization.DynamicVars.DynamicVar v, string stat) => stat switch
    {
        "damage" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.DamageVar,
        "block" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.BlockVar,
        "draw" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.CardsVar,
        "energy" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.EnergyVar,
        "heal" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.HealVar,
        "lose_hp" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.HpLossVar,
        "max_hp" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.MaxHpVar,
        "gold" => v is MegaCrit.Sts2.Core.Localization.DynamicVars.GoldVar,
        _ => false
    };

    public static void EditCardNumber(CardModel card, string stat, decimal amount, bool set, string duration)
    {
        if (duration != "combat" && duration != "turn" && duration != "played") return;
        if (!DamageChanges.TryGetValue(card, out var data))
        {
            data = new CardDamageEdits();
            DamageChanges.Add(card, data);
            // Played is raised after all plays and damage have resolved.
            card.Played += () => ExpireCardDamage(card, "played");
        }
        foreach (var v in card.DynamicVars.Values.Where(v => MatchesCardNumber(v, stat)))
        {
            if (!data.Vars.TryGetValue(v, out var state))
            {
                state = new DamageEdits { Base = v.BaseValue, Last = v.BaseValue };
                data.Vars.Add(v, state);
            }
            CaptureDamage(v, state);
            state.Edits.Add(new DamageEdit(amount, set, duration));
            ApplyDamage(v, state);
        }
    }

    public static void ExpireCardDamage(CardModel card, string duration)
    {
        if (!DamageChanges.TryGetValue(card, out var data)) return;
        foreach (var entry in data.Vars)
        {
            var state = entry.Value;
            if (!state.Edits.Any(edit => edit.Duration == duration)) continue;
            CaptureDamage(entry.Key, state);
            state.Edits.RemoveAll(edit => edit.Duration == duration);
            ApplyDamage(entry.Key, state);
        }
    }
}

[HarmonyLib.HarmonyPatch(typeof(CardModel), nameof(CardModel.EndOfTurnCleanup))]
internal static class $MID$CardDamageTurnCleanup
{
    [HarmonyLib.HarmonyPostfix]
    private static void Postfix(CardModel __instance) => $MID$Gimmicks.ExpireCardDamage(__instance, "turn");
}
'''.replace("$MID$", mid)

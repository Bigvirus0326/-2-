"""Declarative, reversible card stat modifiers compiled from keyword blocks."""
import re
import blockcode as B
import modgen as M


def blocks(tag):
    result = list((tag.get("event_blocks") or {}).get("hand_aura") or [])
    if tag.get("hand_cost_enabled"):
        result.append({"op":"hand_aura_stat", "args":{"stat":"cost", "filter":tag.get("hand_cost_filter", "Any"),
                      "amount":{"t":"num", "v":-int(tag.get("hand_cost_amount", 1))}}})
    return result


def rules(project, card, tag, effects=False):
    import gimmick as G
    gen = B._Gen(project, M.card_event_context(card, "hand_aura"))
    output = []
    def stable(node):
        if isinstance(node, dict):
            if node.get("t") in ("rand", "chance", "src", "var", "event", "amount", "dynvar"):
                raise ValueError("지속 보정에서는 무작위·직접 코드·지역 변수 대신 고정 수치와 현재 상태 조건을 사용하세요.")
            for value in node.values(): stable(value)
        elif isinstance(node, list):
            for value in node: stable(value)
    def visit(nodes, condition="true"):
        for node in nodes:
            node = B.expand_compact(node)
            args = node.get("args") or {}
            if node["op"] in ("if", "if_else"):
                stable(args.get("cond"))
                test = gen.cond(args.get("cond"))
                visit(node.get("body") or [], f"({condition}) && ({test})")
                if node["op"] == "if_else": visit(node.get("else") or [], f"({condition}) && !({test})")
            elif node["op"] in ("hand_aura_stat", "aura_power_amount", "aura_card_effect"):
                stat = "power" if node["op"] == "aura_power_amount" else args.get("stat", "cost")
                if node["op"] == "hand_aura_stat" and stat not in ("cost", "damage", "block"): raise ValueError("지속 보정할 수치를 다시 선택하세요.")
                pile = args.get("active_pile", "Hand")
                if pile not in dict(B.PILES):
                    raise ValueError("지속 보정이 활성화될 더미를 다시 선택하세요.")
                target_pile = args.get("target_pile", "Any")
                if target_pile not in dict([("Any", "모든 더미")] + B.PILES):
                    raise ValueError("효과를 받는 카드의 더미를 다시 선택하세요.")
                condition_with_pile = f"({condition}) && PileType.{pile}.GetPile(Owner).Cards.Contains(this)"
                match = G.tag_play_filter_expr(project, {"played_filter":args.get("filter", "Any")}).replace("cardPlay.Card", "cardSource")
                if target_pile != "Any":
                    match = f"({match}) && MakerAuraMatchesPile(cardSource, PileType.{target_pile})"
                if node["op"] == "aura_card_effect":
                    context=M.card_event_context(card, "hand_play")
                    _, errors=B.compile_blocks(node.get("body") or [],project,context)
                    if errors: raise ValueError(", ".join(errors))
                    if effects:
                        output.append((f"({condition_with_pile}) && ({match.replace('MakerAuraMatchesPile', 'MakerAuraMatchesPlayedPile')})", node.get("body") or []))
                    continue
                if effects:
                    continue
                if stat == "power" and args.get("power_filter", "Any") != "Any":
                    meta=M.power_meta(project,args.get("power_filter"))
                    if not meta: raise ValueError("보정할 파워를 다시 선택하세요.")
                    match += f" && power is {meta['cls']}"
                stable(args.get("amount"))
                amount = gen.val(args.get("amount"))
                output.append((stat, f"({condition_with_pile}) && ({match})", amount))
            else:
                raise ValueError("더미 지속 효과에는 ‘수치 보정’ 또는 ‘조건에 맞는 카드 사용 시 저장한 효과 실행’ 블록을 놓고, 실행할 효과는 그 안에 넣으세요.")
    visit(blocks(tag))
    if gen.errors: raise ValueError(", ".join(gen.errors))
    return output


def members(project, card, original_body=None):
    import gimmick as G
    entries = []
    for tag in G.tags(project):
        active = "true" if card.get("clone") and tag["id"] in card.get("gtags", []) else f'{G.helper(project)}.HasTag(this, "{tag["id"]}")'
        entries += [(stat, f"({active}) && ({condition})", amount) for stat, condition, amount in rules(project, card, tag)]
    lines = []
    def inherit(method, result_type, call):
        nonlocal original_body
        if original_body is None: return []
        pattern = r"(?:public|protected)\s+override\s+" + result_type + r"\s+" + method + r"\s*\("
        original_body, count = re.subn(pattern, "private " + result_type + " MakerOriginal" + method + "(", original_body, count=1)
        target = ("MakerOriginal" if count else "base.") + method
        if result_type == "bool":
            return [f"        bool inherited = {target}({call}, out var inheritedCost);", "        if (inherited) originalCost = inheritedCost;"]
        return [f"        var inherited = {target}({call});"]
    for stat in ("cost", "damage", "block", "power"):
        items = [(condition, amount) for kind, condition, amount in entries if kind == stat]
        if not items: continue
        if stat == "cost":
            method = "TryModifyEnergyCostInCombat"
            previous = inherit(method, "bool", "card, originalCost")
            lines += [f"    public override bool {method}(CardModel card, decimal originalCost, out decimal modifiedCost)", "    {", *previous,
                      "        var cardSource = card;", "        var reduction = 0m;",
                      "        if (card != this && card.Owner == Owner && !card.EnergyCost.CostsX && originalCost >= 0 &&",
                      "            Owner.PlayerCombatState != null && !Owner.Creature.IsDead)", "        {"]
            lines += [f"            if ({condition}) reduction -= ({amount});" for condition, amount in items]
            lines += ["        }", "        modifiedCost = Math.Max(0m, originalCost - reduction);",
                      "        return reduction != 0m" + (" || inherited" if previous else "") + ";", "    }"]
        else:
            if stat == "damage":
                method = "ModifyDamageAdditive"
                args = "Creature? target, decimal amount, ValueProp props, Creature? dealer, CardModel? cardSource, CardPlay? cardPlay"
                call = "target, amount, props, dealer, cardSource, cardPlay"
                owner = "dealer == Owner.Creature"
            elif stat == "power":
                method = "ModifyPowerAmountGivenAdditive"
                args = "PowerModel power, Creature giver, decimal amount, Creature? target, CardModel? cardSource"
                call = "power, giver, amount, target, cardSource"
                owner = "giver == Owner.Creature && amount > 0"
            else:
                method = "ModifyBlockAdditive"
                args = "Creature target, decimal block, ValueProp props, CardModel? cardSource, CardPlay? cardPlay"
                call = "target, block, props, cardSource, cardPlay"
                owner = "target == Owner.Creature"
            previous = inherit(method, "decimal", call)
            lines += [f"    public override decimal {method}({args})", "    {", *previous,
                      "        var r = " + ("inherited" if previous else "0m") + ";",
                      f"        if ({owner}" + ("" if stat == "power" else " && props.HasFlag(ValueProp.Move)") + " && cardSource != null && cardSource != this && cardSource.Owner == Owner &&",
                      "            Owner.PlayerCombatState != null && !Owner.Creature.IsDead)", "        {"]
            lines += [f"            if ({condition}) r += ({amount});" for condition, amount in items]
            lines += ["        }", "        return r;", "    }"]
    has_effects=any(rules(project,card,tag,effects=True) for tag in G.tags(project))
    if entries or has_effects:
        lines += ["    private sealed class MakerAuraTracking { public object? Combat; public readonly Dictionary<CardModel, PileType> Origins = new(); }",
                  "    private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<CardModel, MakerAuraTracking> MakerAuraTrackingTable = new();",
                  "    private MakerAuraTracking MakerAuraTrackingData => MakerAuraTrackingTable.GetValue(this, _ => new MakerAuraTracking());",
                  "    private Dictionary<CardModel, PileType> _makerAuraOrigins => MakerAuraTrackingData.Origins;",
                  "    private object? _makerAuraCombat { get => MakerAuraTrackingData.Combat; set => MakerAuraTrackingData.Combat = value; }",
                  "    private bool MakerAuraMatchesPlayedPile(CardModel card, PileType expected) =>",
                  "        _makerAuraCombat == Owner.Creature.CombatState && _makerAuraOrigins.TryGetValue(card, out var origin) ? origin == expected : card.Pile?.Type == expected;",
                  "    private bool MakerAuraMatchesPile(CardModel card, PileType expected)", "    {",
                  "        if (card.Pile?.Type == expected) return true;",
                  "        return card.Pile?.Type == PileType.Play && _makerAuraCombat == Owner.Creature.CombatState &&",
                  "            _makerAuraOrigins.TryGetValue(card, out var origin) && origin == expected;", "    }"]
        changed = []
        if original_body is not None:
            pattern = r"(?:public|protected)\s+override\s+(async\s+)?Task\s+AfterCardChangedPiles\s*\("
            original_body, count = re.subn(pattern, lambda m: "private " + (m.group(1) or "") + "Task MakerOriginalAfterCardChangedPiles(", original_body, count=1)
            changed = ["        await " + ("MakerOriginal" if count else "base.") + "AfterCardChangedPiles(card, oldPileType, clonedBy);"]
        lines += ["    public override async Task AfterCardChangedPiles(CardModel card, PileType oldPileType, AbstractModel? clonedBy)", "    {", *changed,
                  "        if (card.Owner != Owner || Owner.PlayerCombatState == null) return;",
                  "        if (_makerAuraCombat != Owner.Creature.CombatState) { _makerAuraOrigins.Clear(); _makerAuraCombat = Owner.Creature.CombatState; }",
                  "        if (card.Pile?.Type == PileType.Play) { if (oldPileType != PileType.Play) _makerAuraOrigins[card] = oldPileType; }",
                  "        else if (oldPileType != PileType.Play) _makerAuraOrigins.Remove(card);",
                  "        if (card != this) return;",
                  "        foreach (var changed in Owner.PlayerCombatState.AllCards.ToList()) changed.InvokeEnergyCostChanged();",
                  "        await Task.CompletedTask;", "    }"]
    return lines, original_body


def play_effects(project, card):
    import gimmick as G
    output=[]
    context=M.card_event_context(card,"hand_play")
    for index,tag in enumerate(G.tags(project)):
        active="true" if card.get("clone") and tag["id"] in card.get("gtags",[]) else f'{G.helper(project)}.HasTag(this, "{tag["id"]}")'
        for number,(condition,body) in enumerate(rules(project,card,tag,effects=True)):
            lines,errors=B.compile_blocks(body,project,context,"            ",prefix=M.pascal(card["id"])+f"Grant{index}_{number}",extras=M._EXTRAS_SINK.get("x"))
            if errors: raise ValueError(", ".join(errors))
            condition=condition.replace("cardSource","cardPlay.Card")
            output += [f"        if (({active}) && ({condition}))", "        {", *lines,"        }"]
    return output

"""Simplified Chinese card rules text. Game format tokens stay in their original form."""
import blockcode as B
import gimmick as G
import modgen as M

POWERS = dict(Strength="力量", Dexterity="敏捷", Vigor="活力", Plating="覆甲", Weak="虚弱",
              Vulnerable="易伤", Frail="脆弱", Poison="中毒", Doom="灾厄", Focus="集中")
WHO = {"self": "你", "target": "目标", "it": "该敌人", "all": "所有敌人", "random": "一名随机敌人"}
PILES = {"Hand": "手牌", "Draw": "抽牌堆", "Discard": "弃牌堆", "Exhaust": "消耗牌堆"}
STATS = {"hp": "当前生命", "maxhp": "最大生命", "block": "格挡"}


def power_name(project, key):
    meta = M.power_meta(project, key) or {}
    return POWERS.get(key) or meta.get("zh") or meta.get("en") or str(key or "?")


def effect(project, e, scope, value, pm, owner_kind, item):
    kind = e["kind"]
    target = {"all": "所有敌人", "random": "一名随机敌人", "single": "目标"}[scope]
    if e.get("target") == "other":
        target = {"damage_received": "攻击者", "damage_given": "受伤的敌人", "card_played": "牌的目标"}.get(item.get("trigger"), target)
    hits = max(1, int(e.get("hits") or 1))
    if kind == "damage":
        times = f"，共{hits}次" if hits > 1 else ""
        return f"对{target}造成{value('Damage')}点伤害{times}。"
    simple = {"block": ("获得{}点[gold]格挡[/gold]。", "Block"), "draw": ("抽{}张牌。", "Cards"),
              "heal": ("恢复{}点生命。", "Heal"), "lose_hp": ("失去{}点生命。", "HpLoss"),
              "max_hp": ("最大生命增加{}点。", "MaxHp"), "gold": ("获得{}枚金币。", "Gold")}
    if kind in simple:
        template, variable = simple[kind]
        return template.format(value(variable))
    if kind == "energy":
        if owner_kind == "power":
            return f"获得{value('Energy')}点能量。"
        return f"获得{value('Energy', True)}。"
    if pm:
        name = f"[gold]{power_name(project, e['power'])}[/gold]"
        if kind == "remove_power":
            count = f"{value('')}层" if int(e.get("amount") or 0) else "全部"
            return f"移除{'你' if e.get('target') == 'self' else target}的{count}{name}。"
        verb = "获得" if e.get("target") == "self" else f"给予{target}"
        return f"{verb}{value(pm['var'])}层{name}。"
    return ""


def card_type(project, key):
    if key and key.startswith("tag:"):
        tag = G.find_tag(project, key[4:]) or {}
        return (M.text(tag, "name", "zh") or key[4:]) + "牌"
    return {"Attack": "攻击牌", "Skill": "技能牌", "Power": "能力牌"}.get(key, "牌")


def value(v, project, card):
    if not isinstance(v, dict):
        return str(v)
    t = v.get("t")
    who = WHO.get(v.get("who", "self"), "目标")
    if t == "stack":
        return f"{who}的[gold]{power_name(project, v.get('power'))}[/gold]层数"
    if t == "stat":
        return who + "的" + STATS.get(v.get("stat"), "生命")
    if t == "count":
        return {"hand": "手牌数", "draw": "抽牌堆牌数", "discard": "弃牌堆牌数",
                "exhaust": "消耗牌堆牌数", "enemies": "敌人数"}.get(v.get("what"), "?")
    if t == "played":
        return ("本回合" if v.get("scope") == "turn" else "本场战斗") + "打出的" + card_type(project, v.get("filter")) + "数"
    if t == "orbs":
        orb = G.orb_meta(project, v["orb"]) if v.get("orb") else {}
        return {"slots": "充能球栏位数", "empty": "空栏位数"}.get(v.get("what"), (orb or {}).get("en", "") + "充能球数")
    if t in ("pet", "osty"):
        name = B._pet_name(project, v.get("pet"), "zh") if t == "pet" else "奥斯提"
        return name + "的" + STATS.get(v.get("what"), "生命")
    if t == "op":
        return f"({value(v.get('a'), project, card)} {dict(B.ARITH).get(v.get('op'), '?')} {value(v.get('b'), project, card)})"
    if t == "rand":
        return f"{value(v.get('min'), project, card)}～{value(v.get('max'), project, card)}"
    labels = {"energy": "剩余能量", "round": "当前回合数", "summons": "召唤物数量", "stars": "星星数", "event": "该数值"}
    if t in labels:
        return labels[t]
    return B.value_label(v, project, "en", card)


def condition(c, project, card):
    c = c or {}
    t = c.get("t")
    if t == "cmp":
        a_, b_ = value(c.get("a"), project, card), value(c.get("b"), project, card)
        word = {">=": "不少于", "<=": "不超过", ">": "超过", "<": "少于", "==": "等于", "!=": "不等于"}.get(c.get("op"), c.get("op"))
        return f"{a_}{word}{b_}"
    if t == "chance":
        return f"以{value(c.get('pct'), project, card)}%的概率"
    if t == "has":
        return WHO.get(c.get("who", "self"), "目标") + "拥有" + power_name(project, c.get("power"))
    if t in ("and", "or"):
        return "(" + condition(c.get("a"), project, card) + ("且" if t == "and" else "或") + condition(c.get("b"), project, card) + ")"
    if t == "not":
        return "不满足（" + condition(c.get("a"), project, card) + "）"
    if t == "pet_alive":
        return B._pet_name(project, c.get("pet"), "zh") + "存活"
    return "奥斯提存活" if t == "osty_alive" else "?"


def blocks_text(blocks, project, card=True):
    return "".join(block_text(b, project, card) for b in blocks or [])


def block_text(b, project, card):
    op, a = b["op"], b.get("args", {})
    amount = value(a.get("amount"), project, card)
    count = value(a.get("count"), project, card)
    who = WHO.get(a.get("who", "self"), "目标")
    def body(key="body"):
        return blocks_text(b.get(key), project, card)
    simple = {"block": "获得{}点[gold]格挡[/gold]。", "draw": "抽{}张牌。", "energy": "获得{}点能量。",
              "max_hp": "最大生命增加{}点。", "gold": "获得{}枚金币。", "orb_slots": "获得{}个充能球栏位。",
              "orb_grow": "该充能球的激发数值增加{}。", "stars": "获得{}颗星星。", "forge": "锻造{}。",
              "osty_summon": "召唤{}。"}
    if op in simple:
        return simple[op].format(amount)
    if op in ("flash", "fx"):
        return ""
    if op in ("heal", "lose_hp", "lose_block"):
        return who + {"heal": f"恢复{amount}点生命。", "lose_hp": f"失去{amount}点生命。", "lose_block": f"失去{amount}点格挡。"}[op]
    if op in ("damage", "osty_attack", "pet_attack"):
        actor = "奥斯提" if op == "osty_attack" else B._pet_name(project, a.get("pet"), "zh") if op == "pet_attack" else ""
        hits = int(a.get("hits") or 1)
        return f"{actor}对{who}造成{amount}点伤害" + (f"，共{hits}次。" if hits > 1 else "。")
    if op in ("apply_power", "remove_power", "pay"):
        name = f"[gold]{power_name(project, a.get('power'))}[/gold]"
        if op == "pay":
            return f"若能消耗{amount}层{name}，则消耗并执行：{body()}" + ("否则：" + body("else") if b.get("else") else "")
        if op == "remove_power":
            return f"移除{who}的" + ("全部" if amount == "0" else amount + "层") + name + "。"
        return f"给予{who}{amount}层{name}。"
    if op in ("if", "if_else"):
        return f"若{condition(a.get('cond'), project, card)}，{body()}" + ("否则：" + body("else") if b.get("else") else "")
    if op in ("repeat", "each_enemy", "random_enemy", "delayed"):
        times = value(a.get("times", 1), project, card)
        when = "本回合结束时" if a.get("when") == "end" else "下回合开始时"
        return {"repeat": f"重复{times}次：", "each_enemy": "对每名敌人：", "random_enemy": "对一名随机敌人：",
                "delayed": when + (f"，重复{times}次" if times != "1" else "") + "："}[op] + body()
    if op == "choice":
        opts = [(B._label_text(a.get(k), "zh"), key) for k,key in (("opt1","body"),("opt2","else"),("opt3","third"))]
        return "选择一项：" + " / ".join(n + "（" + body(key) + "）" for n,key in opts if n) + "。"
    if op in ("summon", "command", "unsummon"):
        name = "所有召唤物" if a.get("summon") == "*" else B._summon_name(project, a.get("summon"), "zh")
        return {"summon": f"召唤{name}。", "command": f"{name}立即行动。", "unsummon": f"遣返{name}。"}[op]
    if op.startswith("pet_"):
        name = B._pet_name(project, a.get("pet"), "zh")
        return {"pet_act": f"{name}立即行动。", "pet_kill": f"献祭{name}。", "pet_summon": f"召唤{amount}点{name}。"}.get(op, "")
    if op in ("button_on", "button_off"):
        import fxbtn
        button = fxbtn.find_button(project, a.get("button")) or {}
        return ("获得" if op == "button_on" else "失去") + (M.text(button, "label", "zh") or str(a.get("button"))) + "按钮。"
    if op == "hand":
        verb = {"upgrade": "升级", "discard": "丢弃", "exhaust": "消耗"}.get(a.get("action"), "")
        return verb + "手牌中的" + ("所有" if a.get("which") == "all" else f"随机{count}张") + card_type(project, a.get("ctype")) + "。"
    if op in ("keyword_this", "keyword_cards"):
        kn = "[gold]" + M.KEYWORD_NAMES["zh"].get(a.get("keyword"), str(a.get("keyword"))) + "[/gold]"
        add = a.get("action", "add") == "add"
        if op == "keyword_this":
            return f"此牌获得{kn}。" if add else f"移除此牌的{kn}。"
        where = {"hand": "手牌", "draw": "抽牌堆", "discard": "弃牌堆", "all": "所有牌堆"}.get(a.get("where"), "手牌")
        whom = f"{where}中的" + ("所有" if a.get("which") == "all" else f"随机{count}张") + card_type(project, a.get("ctype"))
        return f"使{whom}获得{kn}。" if add else f"移除{whom}的{kn}。"
    if op in ("set_var", "change_var"):
        n = str(a.get("name", "a"))
        amt = a.get("amount") or {}
        if op == "change_var" and amt.get("t") == "num" and float(amt.get("v", 0) or 0) < 0:
            return f"{n}减少{value(dict(amt, v=-float(amt.get('v', 0))), project, card)}。"
        return f"将{n}设为{amount}。" if op == "set_var" else f"{n}增加{amount}。"
    if op == "add_card":
        key = a.get("card")
        card = next((c for c in project["cards"] if c["id"] == key), {})
        name = "此牌的复制品" if key == "this" else M.text(card, "name", "zh") or str(key)
        return f"将{count}张{name}加入{PILES.get(a.get('pile'), '手牌')}。"
    if op == "pick":
        action = {"hand":"放入手牌", "top":"放到抽牌堆顶", "exhaust":"消耗", "discard":"丢弃", "upgrade":"升级"}
        return f"从{PILES.get(a.get('pile'), '手牌')}中选择{count}张{card_type(project, a.get('ctype'))}，{action.get(a.get('action'), '')}。"
    if op == "channel":
        orb = G.orb_meta(project, a.get("orb")) or {}
        return f"生成{count}个{orb.get('en', '?')}充能球。"
    if op == "evoke":
        return f"激发{'最前' if a.get('which', 'front') == 'front' else '最后'}的充能球{count}次。"
    return {"orb_passive_all":"触发所有充能球的被动效果。", "osty_kill":"献祭奥斯提。"}.get(op, "")


def trigger_text(project, item, kind):
    trigger = item["trigger"]
    if trigger == "card_played":
        card = card_type(project, item.get("played_filter"))
        if kind == "relic":
            return f"每打出{item.get('played_every') or 1}张{card}，"
        actor = "任意玩家" if item.get("played_by") == "any" else "你"
        return f"每当{actor}打出一张{card}时，"
    return {"none": "", "first_turn": "每场战斗开始时，", "turn_start": "回合开始时，",
            "turn_end": "回合结束时，", "combat_victory": "战斗结束时，", "pickup": "拾取时，",
            "damage_received": "每当受到攻击伤害时，", "damage_given": "每当造成攻击伤害时，"}[trigger]


def modifier(project, m):
    kind = m["kind"]
    if kind == "keep_block":
        return "回合结束时保留[gold]格挡[/gold]。"
    if kind == "stars_for_energy":
        return "能量不足时，用星星支付剩余费用。"
    k = int(m.get("value") or 0)
    amount = f"[blue]{abs(k)}[/blue]"
    if m.get("per_stack"):
        amount = "[blue]{Amount}[/blue]" + (f"×{abs(k)}" if abs(k) != 1 else "")
    card = card_type(project, m.get("filter"))
    ref = G._ref_name(project, m, "zh") if m.get("ref") else ""
    if kind in ("res_cost", "res_cap"):
        ref = power_name(project, m.get("ref"))
    damage = (card if m.get("filter") not in (None, "Any", "") else "攻击") + "造成的伤害"
    label = {"cost_add": card + "的能量费用", "dmg_dealt_add": damage, "dmg_dealt_pct": damage,
             "dmg_taken_add": "受到的攻击伤害", "dmg_taken_pct": "受到的攻击伤害", "block_add": "从牌获得的格挡",
             "hand_draw": "回合开始时的抽牌数", "max_energy": "最大能量", "orb_slots": "充能球栏位数",
             "orb_value": (ref or "所有充能球") + "的数值", "orb_passive_times": (ref or "所有充能球") + "的被动触发次数",
             "star_cost": card + "的星星费用", "pet_dmg": (ref or "所有同伴") + "的攻击伤害",
             "osty_dmg": "奥斯提的攻击伤害", "summon_amount": "召唤量", "summon_slots": "召唤物栏位数",
             "res_cap": ref + "的上限", "res_cost": card + "消耗的" + ref,
             "button_cost": (ref or "所有按钮") + "的能量费用", "button_uses": (ref or "所有按钮") + "每回合的使用次数"}[kind]
    return label + ("减少" if k < 0 else "增加") + amount + ("%" if kind.endswith("_pct") else "") + "。"

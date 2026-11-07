"""Conservative lowering of decompiled card OnPlay methods into ordered blocks."""
import re
import modimport as MI


def fragment(code):
    # Preserve the exact call chain (target, attribution, VFX, await and hit count);
    # expose only its verified numeric argument.
    patterns = (("피해", r"\bDamageCmd\.Attack\(\s*"),
                ("드로우", r"\bCardPileCmd\.Draw\(\s*\w+\s*,\s*"),
                ("방어도", r"\bCreatureCmd\.GainBlock\(\s*[\w.]+\s*,\s*"))
    for label, pattern in patterns:
        m = re.search(pattern + r"(?P<n>\d+)(?P<suffix>[mM]?)(?=\s*[,\)])", code)
        if m and code.strip().startswith("await ") and code.count(";") == 1:
            return {"op":"source_amount", "label":label, "prefix":code[:m.start("n")],
                    "suffix":code[m.end("n"):], "args":{"amount":{"t":"num","v":int(m["n"])}}}
    return {"op": "source_step", "args": {"source": code.strip()}}


def statements(body):
    # Keep control flow and its local scope intact when it is not a straight-line body.
    if any(c in body for c in '{}\'"') or re.search(r"\b(if|for|foreach|while|switch|try|using|return|goto)\b", body):
        return []
    return [part.strip() + ";" for part in body.split(";") if part.strip()]


def lower(card, parent=""):
    cl = card.get("clone") or {}
    play = MI.member_text(cl.get("body", ""), "OnPlay")
    sig = re.search(r"\bTask\s+OnPlay\(\s*PlayerChoiceContext\s+(\w+)\s*,\s*CardPlay\s+(\w+)\s*\)\s*\{", play)
    if not sig or not play.rstrip().endswith("}"):
        return []
    body = play[sig.end():play.rfind("}")].strip()
    args = dict(zip(sig.groups(), ("choiceContext", "cardPlay")))
    # Never rewrite strings, comments or arbitrary interpolated C#.
    if any(c in body for c in ('"', "'", '#')) or '//' in body or '/*' in body:
        return []
    body = re.sub(r"\b\w+\b", lambda m: args.get(m[0], m[0]), body)
    result = []
    for step in statements(body):
        call = re.fullmatch(r"await\s+(\w+)\(choiceContext,\s*cardPlay,\s*(\w+\.\w+)\);", step)
        expanded = dispatch(card, parent, *call.groups()) if call and parent else None
        result.extend(expanded or [fragment(step)])
    return result


def dispatch(card, parent, method, selector):
    helper = MI.member_text(parent, method)
    # This adapter recognizes the Bishop dispatcher by its actual initialization,
    # selected enum arm, and epilogue. Other helper shapes remain source calls.
    signature = re.search(r"Task\s+\w+\(PlayerChoiceContext ctx, CardPlay play, \w+ spell\)\s*\{", helper)
    switch = re.search(r"switch\s*\(spell\)\s*\{", helper)
    if not signature or not switch:
        return None
    prefix = helper[signature.end():switch.start()].strip()
    norm = lambda s: re.sub(r"\s+", "", s)
    expected = """BishopPrayerPower bishopPrayerPower = Me.GetPower<BishopPrayerPower>();
    if (bishopPrayerPower == null) { bishopPrayerPower = await PowerCmd.Apply<BishopPrayerPower>(ctx, Me, 1m, Me, this); }
    BishopPrayerPower b = bishopPrayerPower; await BishopPrayerPower.ResolveAll(ctx, CombatState);
    BishopLedger s = b.State; Creature t = play.Target ?? Me;"""
    if norm(prefix) != norm(expected):
        return None
    end = MI.match_bracket(helper, switch.end()-1)
    tail = helper[end+1:].strip()
    while (extra := re.match(r"switch\s*\(spell\)\s*\{", tail)):
        stop = MI.match_bracket(tail, extra.end()-1)
        if stop < 0 or re.search(r"\bdefault\s*:|case\s+" + re.escape(selector) + r"\s*:", tail[:stop]):
            return None
        tail = tail[stop+1:].strip()
    resolve = "await BishopPrayerPower.ResolveAll(ctx, CombatState);"
    if not tail.startswith(resolve) or not re.match(r"^(?:async Task\b|\})", tail[len(resolve):].strip()):
        return None
    arm = re.search(r"case\s+" + re.escape(selector) + r"\s*:\s*(.*?)\bbreak;", helper[switch.end():end], re.S)
    hit = re.fullmatch(r"await Hit\(ctx, t, BishopNumber\((\d+), (\d+)\)\);\s*", arm[1]) if arm else None
    hit_impl = MI.member_text(parent, "Hit")
    if not hit or not all(x in hit_impl for x in ("DamageCmd.Attack(n)", ".WithHitCount(hits)", ".Execute(ctx)")):
        return None
    mapping = MI.member_text(card["clone"]["body"], "BishopNumber")
    var = re.search(r"normal\s*==\s*" +hit[1]+r"\s*&&\s*upgraded\s*==\s*"+hit[2]+r"\s*\)\s*\{\s*return DynamicVars\[\"(\w+)\"\].IntValue;", mapping)
    if not var or not any(v["name"] == var[1] for v in card.get("raw_vars", [])):
        return None
    init = prefix[:prefix.index("BishopPrayerPower b =")].strip().replace("ctx,", "choiceContext,")
    resolved = resolve.replace("ctx,", "choiceContext,")
    return [fragment(init), fragment(resolved),
            fragment("_ = bishopPrayerPower.State;"),
            {"op":"source_hit", "args":{"stat":var[1], "target":"target", "hits":1}},
            fragment(resolved)]


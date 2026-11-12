"""외부 모드의 파워를 모드메이커의 기본 파워 설정(발동 시점·효과 블록)으로 옮긴다.

완전히 블록으로만 옮길 수 있을 때만 바꾼다. 조건에 하나라도 맞지 않으면 원본 C# 을 그대로 둔다:
- 발동 훅은 턴 시작·턴 종료·카드 사용 중 하나이거나 없다. 공격 피해 보정은 '카드 종류 조건 + 수치' 한 가지 모양만 허용한다.
- 그 밖의 멤버(다른 훅·도우미 메서드·필드)가 없고, 부모 파워는 게임 기본 클래스다.
- Type / StackType 을 함께 지정했다.
- 훅 본문이 블록으로 모두 풀리고, 직접 코드 블록·직접 호출·식 안의 원본 코드가 하나도 없다.
"""
import re

import csblocks
import modgen as M

TURN_HOOKS = {"AfterPlayerTurnStart": "turn_start", "BeforeSideTurnEnd": "turn_end", "AfterCardPlayed": "card_played"}
RAW_OPS = {"source_step", "src_call", "src_loop", "source_amount", "source_hit", "original_play"}
PROP = re.compile(r"\s*(?:(?:public|protected|private)\s+)?override\s+(\w+)\s+(\w+)\s*=>\s*(\w+)\.(\w+)\s*;\s*", re.S)
TYPES = {"Buff", "Debuff"}
STACKS = {"Counter", "Single"}
CARD_KINDS = {"Attack", "Skill", "Power", "Curse", "Status", "Quest"}
DMG_MOD = re.compile(r"return\s*\(\s*dealer\s*==\s*Owner\s*&&\s*card\s*!=\s*null\s*&&\s*card\.Type\s*==\s*CardType\.(\w+)"
                     r"\s*&&\s*!props\.HasFlag\(ValueProp\.Unpowered\)\s*\)\s*\?\s*Amount\s*:\s*0\s*;", re.S)


def _pure(seq):
    """블록 목록 안에 원본 코드가 남아 있으면 False."""
    for b in seq or []:
        if b.get("op") in RAW_OPS:
            return False
        if not _values_pure(b.get("args", {})) or not _values_pure(b.get("slots", [])):
            return False
        if not all(_pure(b.get(k)) for k in ("body", "else", "third")):
            return False
    return True


def _values_pure(v):
    if isinstance(v, dict):
        if v.get("t") == "src":
            return False
        return all(_values_pure(x) for x in v.values())
    if isinstance(v, (list, tuple)):
        return all(_values_pure(x) for x in v)
    return True


def _hook_rest(hook, text, params):
    """훅 본문에서 발동 조건을 떼어 내고 (나머지 본문, 누가 쓴 카드인지) 를 돌려준다. 맞지 않으면 None."""
    text = text.strip()
    if hook == "AfterCardPlayed":
        cp = params[1]["name"]
        m = re.match(r"if\s*\(\s*Owner\.IsDead\s*\)\s*return\s*;\s*(.*)$", text, re.S)
        if m:
            text = m.group(1)
        m = re.match(rf"if\s*\(\s*{cp}\.Card\.Owner\?\.Creature\s*!=\s*Owner\s*\)\s*return\s*;\s*(.*)$", text, re.S)
        if m:
            return m.group(1), "owner"
        return text, "any"   # 조건이 없으면 누가 사용하든 발동한다
    if hook == "AfterPlayerTurnStart":
        p = params[1]["name"]
        m = re.match(rf"if\s*\(\s*{p}\.Creature\s*!=\s*Owner\s*\)\s*return\s*;\s*(.*)$", text, re.S)
        if m:
            return m.group(1), None
        m = re.match(rf"if\s*\(\s*{p}\.Creature\s*==\s*Owner\s*\)\s*\{{(.*)\}}\s*$", text, re.S)
        if m and csblocks._close(text, text.index("{")) == len(text) - 1:
            return m.group(1), None
        return None
    s = params[1]["name"]
    m = re.match(rf"if\s*\(\s*{s}\s*!=\s*Owner\.Side\s*\)\s*return\s*;\s*(.*)$", text, re.S)
    return (m.group(1), None) if m else None


ICON = re.compile(r"\s*(?:(?:public|protected|private)\s+)?override\s+string\s+Custom\w*Icon\w*\s*=>.*", re.S)   # 아이콘 경로는 그림 파일로 대신한다


def _chain(em, c):
    """c 와 모드 안의 부모들. 게임 기본 클래스 앞에서 멈춘다."""
    out, seen = [c], {c.name}
    while out[-1].base and out[-1].base in em.classes and out[-1].base not in seen:
        seen.add(out[-1].base)
        out.append(em.classes[out[-1].base])
    return out


def _no(new, why):
    """옮기지 못한 이유를 항목에 남기고 False 를 돌려준다 (보고서용, 저장되는 파워에는 남지 않는다)."""
    new["_why"] = why
    return False


BOOL_PROP = re.compile(r"\s*(?:(?:public|protected|private)\s+)?override\s+bool\s+(AllowNegative|IsVisibleInternal|ShouldPlayVfx)\s*=>\s*(true|false)\s*;\s*", re.S)


def _remove_on_play(pm):
    """카드 사용 후 '내 kind 카드 사용 시 이 파워 제거' 한 가지 모양이면 카드 종류, 아니면 None."""
    if len(pm["params"]) != 2:
        return None
    cp = pm["params"][1]["name"]
    body = " ".join((pm["body"] or "").split())
    m = re.fullmatch(rf"if \({cp}\.Card\.Owner\.Creature != Owner \|\| {cp}\.Card\.Type != CardType\.(\w+)\) "
                     r"\{ return Task\.CompletedTask; \} return PowerCmd\.Remove\(this\);", body)
    return m.group(1) if m else None


def _cost_filter(pm):
    """TryModifyEnergyCostInCombat 가 '내 생물 카드 + 카드 종류 조건일 때 비용 -수치' 한 가지 모양이면 카드 종류, 아니면 None."""
    if len(pm["params"]) != 3:
        return None
    card, cost = pm["params"][0]["name"], pm["params"][1]["name"]
    body = " ".join((pm["body"] or "").split())
    m = re.fullmatch(rf"bool flag = {card}\.Owner\.Creature == Owner && {card}\.Type == CardType\.(\w+); "
                     rf"modifiedCost = \(flag \? Math\.Max\(0m, {cost} - \(decimal\)Amount\) : {cost}\); return flag;", body)
    return m.group(1) if m else None


def _decay_of(pm):
    """AfterSideTurnEnd 본문이 '내 쪽 턴 종료 시 1 감소 / 사라짐' 한 가지 모양이면 그 decay 값, 아니면 None."""
    side = pm["params"][1]["name"] if len(pm["params"]) >= 2 else ""
    body = (pm["body"] or "").strip()
    for call, decay in (("PowerCmd.TickDownDuration(this);", "tick"), ("PowerCmd.Remove(this);", "remove")):
        if re.fullmatch(rf"if\s*\(\s*{side}\s*==\s*Owner\.Side\s*\)\s*\{{\s*await {re.escape(call)}\s*\}}", body) or                 re.fullmatch(rf"if\s*\(\s*{side}\s*!=\s*Owner\.Side\s*\)\s*return\s*;\s*await {re.escape(call)}", body):
            return decay
    return None


def convert(em, c, new, project):
    """c: 외부 파워 클래스, new: 만들어진 프로젝트 파워. 옮기면 True (new 를 고쳐 쓴다).
    모드 안의 부모는 Type·StackType·아이콘 경로만 정의할 때 허용한다 (그 밖의 동작은 옮기지 못함)."""
    hook, dmg_kind, props, decay, keep, visible, cost_kind, remove_kind = None, None, {}, None, False, [], None, None
    for k, cls in enumerate(_chain(em, c)):
        for mem in csblocks.members(cls.body):
            if ICON.fullmatch(mem.strip()):
                continue
            pm = csblocks.parse_method(mem)
            if pm is None:
                bp = BOOL_PROP.fullmatch(mem.strip())
                if bp:   # AllowNegative 는 기본값(false)만 옮길 수 있고, IsVisibleInternal 은 숨김 설정이 된다
                    if bp.group(1) == "AllowNegative":
                        if bp.group(2) == "true":
                            return _no(new, "음수를 허용하는 파워입니다")
                    elif bp.group(1) == "ShouldPlayVfx":   # 화면 연출만 정한다 (옮기지 않음, 보고서에 남지 않음)
                        pass
                    else:
                        visible.append(bp.group(2) == "true")
                    continue
                pr = PROP.fullmatch(mem.strip())
                if not pr or pr.group(2) not in ("Type", "StackType"):
                    return _no(new, "처리하지 않는 속성·멤버가 있습니다: " + mem.strip()[:40])
                props.setdefault(pr.group(2), pr.group(4))   # 가장 가까운 클래스의 값을 쓴다
                continue
            if k > 0 or "override" not in pm["mods"]:
                return _no(new, "모드 안 부모 파워의 동작은 옮기지 않습니다" if k > 0 else "override 가 아닌 메서드가 있습니다")
            if pm["name"] == "TryModifyEnergyCostInCombat" and cost_kind is None and _cost_filter(pm):
                cost_kind = _cost_filter(pm)
            elif pm["name"] == "TryModifyEnergyCostInCombat":
                return _no(new, "에너지 비용 보정의 모양을 읽을 수 없습니다")
            elif pm["name"] == "AfterSideTurnEnd" and decay is None and _decay_of(pm):
                decay = _decay_of(pm)
            elif pm["name"] == "ShouldClearBlock" and not keep and pm["params"] and                     re.fullmatch(rf"return\s+{pm['params'][0]['name']}\s*!=\s*Owner\s*;", (pm["body"] or "").strip()):
                keep = True
            elif pm["name"] == "ModifyDamageAdditive" and dmg_kind is None:
                m = DMG_MOD.fullmatch((pm["body"] or "").strip())
                if not m or m.group(1) not in CARD_KINDS:
                    return _no(new, "공격 피해 보정이 카드 종류 조건 한 가지 모양이 아닙니다")
                dmg_kind = m.group(1)
            elif pm["name"] == "AfterCardPlayed" and hook is None and _remove_on_play(pm):
                hook, remove_kind = pm, _remove_on_play(pm)
            elif pm["name"] in TURN_HOOKS and hook is None:
                hook = pm
            else:
                return _no(new, "처리하지 않는 메서드가 있습니다: " + pm["name"])
    if set(props) != {"Type", "StackType"} or props["Type"] not in TYPES or props["StackType"] not in STACKS:
        return _no(new, "종류(Type)·중첩(StackType)을 정해진 값으로 읽을 수 없습니다")
    played_by = None
    if remove_kind:   # 카드 사용 뒤 이 파워를 없앤다 (원본: 해당 카드 종류를 쓰면 제거)
        new["trigger"], new["played_by"], new["played_filter"] = "card_played", "owner", remove_kind
        new["type"], new["stack"] = props["Type"], props["StackType"]
        eff = M.new_effect("code")
        eff["blocks"] = [{"op": "remove_power_model", "args": {"power": "this"}}]
        new["effects"] = [eff]
        new.pop("clone", None)
        new.pop("_why", None)
        return True
    if hook is not None:
        got = _hook_rest(hook["name"], hook["body"] or "", hook["params"])
        if got is None:
            return _no(new, "발동 조건 모양을 읽을 수 없습니다: " + hook["name"])
        rest, played_by = got
        # 훅 매개변수를 블록 풀이가 아는 이름으로 바꾼다 (턴 훅의 대상은 발동 조건으로 이미 Owner 임이 확인됨)
        ps = hook["params"]
        mapping = {ps[0]["name"]: "choiceContext"} if ps[0]["name"] != "choiceContext" else {}
        if hook["name"] == "AfterCardPlayed":
            mapping = {ps[0]["name"]: "choiceContext", ps[1]["name"]: "cardPlay"}
        else:
            mapping[ps[1]["name"]] = "Owner.Player" if hook["name"] == "AfterPlayerTurnStart" else "Owner.Side"
        rest = csblocks.rename(rest, mapping)
        text = "protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)\n{\n" + rest + "\n}"
        card = {"clone": {"body": text, "base": "", "orig_class": c.full, "namespace": c.namespace, "usings": c.usings}}
        try:
            blocks, _info = csblocks.decompose_with_classes(card, em.classes, project, own_power="c:" + new["id"])
        except Exception:   # 풀기에 실패하면 원본 C# 을 그대로 둔다
            return _no(new, "훅 본문을 블록으로 풀지 못했습니다")
        if blocks is None or not _pure(blocks):
            return _no(new, "훅 본문에 블록으로 옮기지 못한 줄이 남았습니다")
    else:
        blocks = []
    new["trigger"] = TURN_HOOKS[hook["name"]] if hook is not None else "none"
    if played_by:
        new["played_by"] = played_by
    new["type"], new["stack"] = props["Type"], props["StackType"]
    if decay:
        new["decay"] = decay
    if any(visible):
        new["hidden"] = True
    if keep:
        new.setdefault("modifiers", []).append(M.new_modifier("keep_block", 0, False))
    if cost_kind:   # 카드 종류가 맞으면 비용 1 감소 × 수치 (원본 Math.Max(0, 비용 - 수치) 와 같다)
        mod = M.new_modifier("cost_add", -1, True)
        mod["filter"] = cost_kind
        new.setdefault("modifiers", []).append(mod)
    if dmg_kind:
        mod = M.new_modifier("dmg_dealt_add", 1, True)
        mod["filter"] = dmg_kind
        new.setdefault("modifiers", []).append(mod)
    if blocks:
        eff = M.new_effect("code")
        eff["blocks"] = blocks
        new["effects"] = [eff]
    else:
        new["effects"] = []
    new.pop("clone", None)
    new.pop("_why", None)
    return True

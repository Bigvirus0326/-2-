"""효과 목록의 규칙 (Tk · Qt 공용, 화면과 무관): 효과 요약 글과 C# 직접 입력 안내.
"""
import re

import blockcode
import modgen as M


CODE_HELP = {
    "card": "쓸 수 있는 것: choiceContext, cardPlay (cardPlay.Target = 대상), Owner (플레이어), Owner.Creature, "
            "DynamicVars, this\n예: await CreatureCmd.GainBlock(Owner.Creature, 5m, ValueProp.Move, cardPlay);",
    "relic": "쓸 수 있는 것: choiceContext, Owner (플레이어), Owner.Creature, DynamicVars, Flash()\n"
             "예: await PlayerCmd.GainEnergy(1m, Owner);",
    "potion": "쓸 수 있는 것: choiceContext, target (대상, null 가능), Owner (플레이어), Owner.Creature\n"
              "예: if (target != null) await CreatureCmd.Damage(choiceContext, target, 10m, ValueProp.Unpowered, Owner.Creature, null, null);",
    "power": "쓸 수 있는 것: choiceContext, Owner (파워를 가진 생물), Owner.Player (플레이어면), Amount (스택 수), "
             "other (상대, null 가능), OwnerEnemies(), RandomOwnerEnemy()\n"
             "예: await CreatureCmd.Heal(Owner, Amount);",
}


def effect_summary(project, e):
    parts = []
    if e["kind"] == "damage" and int(e.get("hits", 1)) > 1:
        parts.append(f"{e['hits']}회 타격")
    if e["kind"] in ("power", "remove_power"):
        pm = M.power_meta(project, e["power"])
        name = pm["ko"] if pm else f"⚠{e['power']}"
        parts.append(f"{name} → {dict(self='자신', enemy='적', other='상대').get(e['target'], e['target'])}")
    if e.get("per_stack"):
        parts.append("×스택")
    sm = M.power_meta(project, e.get("scale_power"))
    if sm and int(e.get("scale_per", 0) or 0):
        parts.append(f"+{sm['ko']}×{e['scale_per']}")
    cm = M.power_meta(project, e.get("cond_power"))
    if cm:
        parts.append(f"조건: {cm['ko']}≥{e.get('cond_min', 1)}")
    if e["kind"] == "code" and e.get("blocks"):
        import blockcode
        n = sum(1 for _ in blockcode.walk(e["blocks"]))
        d = blockcode.describe(e["blocks"], project, "card", "ko")
        d = re.sub(r"\{IfUpgraded:show:([^|}]*)\|([^}]*)\}", r"\2", d)
        d = re.sub(r"\[/?[a-z_]+\]", "", d)
        parts.append(f"🧩 블록 {n}개: {d[:50]}")
    elif e["kind"] == "code":
        first = (e.get("code") or "").strip().split("\n")[0]
        parts.append(first[:40])
    return ", ".join(parts)

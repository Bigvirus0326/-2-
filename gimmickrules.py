"""기믹(태그·소환수·구체·동료) ID 가 바뀌거나 지워질 때 프로젝트 안의 참조를 맞춘다 (Tk · Qt 공용, 화면과 무관)."""
import re

import modgen as M


def plain(s):
    """블록 설명 글에서 강조 태그와 치환 표시를 걷어 낸 글 (blockui._plain 과 같다)."""
    s = re.sub(r"\{IfUpgraded:show:([^|}]*)\|([^}]*)\}", r"\2(강화 \1)", s or "")
    s = s.replace("{Passive}", "지속 수치").replace("{Evoke}", "발현 수치").replace("{Amount}", "스택")
    return re.sub(r"\[/?[a-z_]+\]", "", s)


def rename_gimmick_ref(project, kind, old, new):
    """태그/소환수 ID 가 바뀌거나(new) 지워질 때(None) 프로젝트 안의 참조를 고친다."""
    M.rename_description_references(project, kind, old, new)
    if kind == "tag":
        for c in project.get("cards", []):
            g = c.get("gtags") or []
            if old in g:
                c["gtags"] = [new if t == old else t for t in g if new or t != old]
        old_s, new_s = "tag:" + old, ("tag:" + new) if new else "Any"
    elif kind == "orb":
        old_s, new_s = "o:" + old, ("o:" + new) if new else "Lightning"
    elif kind == "pet":
        old_s, new_s = "\0pet:" + old, ""     # 동료는 'pet' 키로만 참조
    else:
        old_s, new_s = "s:" + old, ("s:" + new) if new else ""

    def fix(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if v == old_s:
                    o[k] = new_s
                elif kind == "summon" and k == "summon" and v == old:
                    o[k] = new or ""
                elif kind == "pet" and k in ("pet", "ref") and v == old:
                    o[k] = new or ""
                elif kind == "pet" and k == "anchor" and v == "pet:" + old:
                    o[k] = ("pet:" + new) if new else "creature"     # 버튼 위치 기준 동료
                else:
                    fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    for key in ("cards", "relics", "potions", "powers"):
        fix(project.get(key, []))
    fix(project.get("gimmicks", {}).get("tags", []))
    fix(project.get("gimmicks", {}).get("summons", []))
    fix(project.get("gimmicks", {}).get("orbs", []))
    fix(project.get("gimmicks", {}).get("pets", []))
    fix(project.get("gimmicks", {}).get("buttons", []))

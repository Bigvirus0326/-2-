"""외부 모드(소스 폴더)의 카드·파워를 모드메이커 프로젝트로 옮기고, 항목별 보고서를 만든다.

- 원본 폴더는 읽기만 한다. 결과는 out_dir 에 새 프로젝트 파일과 보고서로 쓴다.
- 카드: OnPlay 를 블록으로 풀고, 풀리지 않은 최상위 줄은 '직접 입력한 코드' 효과로 남겨 순서를 지킨다(보고서에 줄 수를 적는다).
  수치 변수(DynamicVars)는 extra_vars 로 선언하고, 강화 수치는 자동으로 옮기지 않는다(보고서에 적는다).
- 파워: powerconv 가 완전히 옮길 수 있는 파워만 옮긴다. 나머지는 이유를 보고서에 적는다.
- 유물·물약은 아직 옮기지 않는다.
"""
import json
import os
import re

import blockcode as B
import csblocks
import modgen as M
import modimport as MI
import powerconv

RAW_TO_KIND = {"Damage": "damage", "Block": "block", "Cards": "draw", "Energy": "energy",
               "Heal": "heal", "HpLoss": "lose_hp", "MaxHp": "max_hp", "Gold": "gold"}


def _num(value):
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def convert_card(em, item, project):
    """-> (새 카드 또는 None, 보고 줄 목록). 옮기지 못하면 None."""
    notes = []
    card = MI.clone_item(em, item, project)
    if not (card.get("effects") or [None])[0] or not card["effects"][0].get("decomposed"):
        return None, ["OnPlay 를 블록으로 풀지 못했습니다 (원본 코드를 그대로 써야 합니다)"]
    # 옮기는 용도로 다시 풀기: 안쪽에 직접 코드가 남은 if·반복은 문장 전체를 직접 코드 한 줄로 둔다
    blocks, _info = csblocks.decompose_with_classes(card, em.classes, project, whole_raw=True)
    if blocks is None:
        return None, ["OnPlay 를 블록으로 풀지 못했습니다 (원본 코드를 그대로 써야 합니다)"]
    eff = {"blocks": blocks}
    # 순서를 지키며 나눈다: 블록으로 된 묶음은 블록 효과로, 한 줄짜리 직접 코드는 '직접 입력한 코드' 효과로
    effects, raw_lines = [], []
    run = []
    for b in eff.get("blocks") or []:
        if powerconv._pure([b]):
            run.append(b)
            continue
        if run:
            effects.append(dict(M.new_effect("code"), blocks=run))
            run = []
        if b.get("op") == "source_step":
            text = b["args"]["source"]
        else:   # 직접 호출처럼 블록으로 두지 못한 한 문장: 블록 코드로 풀어서 C# 문장으로 남긴다
            lines, errs = B.compile_blocks([b], project, M._Ctx("card", card))
            if errs:
                return None, ["직접 호출 한 줄을 C# 으로 풀지 못했습니다: " + "; ".join(errs)[:80]]
            text = "\n".join(lines)
        raw_lines.append(text)
        effects.append(dict(M.new_effect("code"), code=text))
    if run:
        effects.append(dict(M.new_effect("code"), blocks=run))
    if raw_lines:
        notes.append(f"직접 코드 {len(raw_lines)}줄이 남았습니다 (블록으로 바꿔 주세요)")
    extra = []
    for v in card.get("raw_vars") or []:
        kind = RAW_TO_KIND.get(v.get("name"))
        amount = _num(v.get("value"))
        if kind is None or amount is None:
            notes.append(f"설명용 수치 '{v.get('name')}' 은 새 카드에 선언하지 않았습니다 (블록의 값은 그대로 들어갑니다)")
            continue
        extra.append({"kind": kind, "amount": amount})
        if _num(v.get("upgrade")):
            notes.append(f"강화 시 {v['name']} +{_num(v.get('upgrade'))} 는 직접 설정하세요")
    card.pop("clone", None)   # raw_vars 는 남긴다: 블록의 수치 변수가 이 값을 읽는다
    card["effects"] = effects or [M.new_effect("code")]
    card["extra_vars"] = extra
    return card, notes


def convert_power(em, item, project):
    """-> (새 파워 또는 None, 보고 줄 목록)."""
    power = MI.clone_item(em, item, project)
    if power.get("clone"):
        return None, [power.get("_why") or "직접 코드 클래스로 남았습니다"]
    power.pop("_why", None)
    power.pop("raw_vars", None)
    return power, []


VAR_NAMES = {"damage": "Damage", "block": "Block", "draw": "Cards", "energy": "Energy", "heal": "Heal",
             "lose_hp": "HpLoss", "max_hp": "MaxHp", "gold": "Gold"}
DYN_RE = re.compile(r'DynamicVars\["(\w+)"\]|DynamicVars\.(\w+)')


def _describe_card(card, project):
    parts = []
    for e in card["effects"]:
        if e.get("blocks"):
            parts.append(B.describe(e["blocks"], project, "card", "ko", card))
        elif e.get("code"):
            parts.append("직접 코드: " + e["code"].strip().split("\n")[0][:60])
    return " / ".join(p for p in parts if p)


def _check_card(card, project):
    """생성된 C# 이 선언하지 않은 수치를 읽으면 문제를 적는다 (빈 목록이면 통과)."""
    errors = []
    for e in card.get("effects") or []:
        if e.get("blocks"):   # 생성 과정은 블록 오류를 조용히 버리므로 여기서 따로 확인한다
            errors += B.compile_blocks(e["blocks"], project, M._Ctx("card", card))[1]
    if errors:
        return [f"블록 오류: {'; '.join(errors)[:120]}"]
    code = M.gen_card(project, card)
    declared = {VAR_NAMES[e["kind"]] for e in card.get("extra_vars") or [] if e.get("kind") in VAR_NAMES}
    used = {a or b for a, b in DYN_RE.findall(code)}
    missing = sorted(used - declared)
    return [f"선언되지 않은 수치를 읽습니다: {', '.join(missing)}"] if missing else []


def build(em, out_dir, log=print):
    project = M.default_project()
    project["mod"]["id"] = em.id
    project["mod"]["name"] = em.name or em.id
    project["cards"], project["powers"], project["relics"], project["potions"] = [], [], [], []
    rows = []
    cards = []
    for kind, items, conv in (("카드", em.items["card"], convert_card), ("파워", em.items["power"], convert_power)):
        for it in items:
            label = it.get("name_ko") or it.get("name_en") or it.get("id") or it.get("class")
            try:
                new, notes = conv(em, it, project)
            except Exception as exc:  # noqa: BLE001  - 한 항목 실패가 전체를 막지 않게
                new, notes = None, [f"변환 중 오류: {type(exc).__name__}"]
            if new is None:
                rows.append([kind, label, "변환 안 됨", notes])
                continue
            if kind == "카드":
                cards.append([new, label, notes])
            else:
                project["powers"].append(new)
                rows.append([kind, label, "변환됨", notes])
    project["cards"] = [c for c, _, _ in cards]
    for new, label, notes in cards:
        try:
            problems = _check_card(new, project)
        except Exception as exc:  # noqa: BLE001
            problems = [f"생성 중 오류: {type(exc).__name__}"]
        if problems:
            project["cards"].remove(new)
            rows.append(["카드", label, "변환 안 됨", notes + problems])
            continue
        status = "부분 변환 (확인 필요)" if any(e.get("code") for e in new["effects"]) else "변환됨"
        desc = _describe_card(new, project)
        rows.append(["카드", label, status, notes + ([desc] if desc else [])])
    path = os.path.join(out_dir, f"{em.id}_converted.sts2mod.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=1)
    report = os.path.join(out_dir, "conversion_report.md")
    with open(report, "w", encoding="utf-8") as f:
        f.write(render(em, rows))
    log(f"프로젝트: {path}")
    log(f"보고서: {report}")
    return project, rows


def render(em, rows):
    full = sum(1 for r in rows if r[2] == "변환됨")
    part = sum(1 for r in rows if r[2].startswith("부분"))
    lines = [f"# {em.name or em.id} 변환 보고서", "",
             f"변환됨 {full}, 부분 변환(확인 필요) {part}, 전체 {len(rows)}", "",
             "| 종류 | 이름 | 상태 | 메모 |", "|---|---|---|---|"]
    for kind, label, status, notes in rows:
        memo = "<br>".join(n.replace("|", "\\|").replace("\n", " ") for n in notes)
        lines.append(f"| {kind} | {label} | {status} | {memo} |")
    return "\n".join(lines) + "\n"

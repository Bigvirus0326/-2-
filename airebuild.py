"""직접 코드가 남은 항목을 AI 에게 블록으로 다시 만들게 한다 (화면과 무관한 부분).

흐름: request_text() 로 요청 글을 만들고 → 기존 AI 설명서(aiguide.build_prompt)와 함께 복사해 AI 채팅에 붙여 넣는다 →
AI 답을 plan_answer() 에 주면 바꿀 계획이 나온다: 그 항목들의 '효과', 새 파워·기믹 넣기, 지울 파워·기믹.
이름·그림·원본 클래스(clone) 같은 나머지 칸은 그대로 둔다. 계획은 넣기 전에 검사한다 (apply_plan 은 검사를 마친 뒤에만 부른다).
"""
import copy
import json
import re

import aipaste as AP
import blockcode as B
import modgen as M

RAW_OPS = ("source_step", "src_call", "src_loop")
NOUN = {"card": "카드", "relic": "유물", "potion": "물약", "power": "파워"}
ADD_KINDS = ("power",) + tuple(AP.GIMMICKS)   # 이 창에서 새로 넣거나 지울 수 있는 것: 파워와 기믹
REMOVABLE = ADD_KINDS
CARD_FIELDS = ("res_power", "res_cost", "star_cost", "play_cond", "glow_cond")   # 카드 칸 중 자원 비용·사용 조건

# 자주 나오는 원본 코드 모양 -> 쉬운 설명 (위에서부터 처음 맞는 것)
_EXPLAIN = [
    (r"^\s*goto\s|^\s*IL_\w+\s*:", "원본 코드의 흐름을 옮기는 줄입니다 (코드를 되돌려 읽을 때 생긴 흔적)."),
    (r"\.Pay<|\bPay\(", "자원을 내고 씁니다. 카드라면 자원 비용 칸(res_power·res_cost)으로 옮기세요."),
    (r"^\s*foreach\s*\(", "목록의 항목 하나하나에 같은 행동을 반복합니다."),
    (r"^\s*(for|while)\s*\(", "조건이 맞는 동안 행동을 반복합니다."),
    (r"^\s*if\s*\(.*\)\s*(\{?\s*)?return", "조건이 맞으면 여기서 효과를 끝냅니다."),
    (r"^\s*if\s*\(", "조건에 따라 행동을 나눕니다."),
    (r"CardSelectorPrefs|CardSelectCmd", "플레이어에게 카드를 고르게 하는 설정입니다."),
    (r"new\s+List<CardModel>|List<CardModel>", "카드 목록을 만듭니다."),
    (r"List<Creature>|Creature\[\]", "생물(적·아군) 목록을 만듭니다."),
    (r"new\s+List<|\.ToList\(\)", "목록을 만듭니다."),
    (r"PowerCmd\.Apply|CommonActions\.Apply", "생물에게 파워를 부여합니다."),
    (r"CreatureCmd\.Damage|DamageCmd\.Attack", "피해를 줍니다."),
    (r"CreatureCmd\.GainBlock", "방어도를 얻습니다."),
    (r"CardPileCmd\.Draw", "카드를 뽑습니다."),
    (r"CardPileCmd\.Add|CardCmd\.", "카드를 옮기거나 바꿉니다."),
    (r"VfxCmd|SfxCmd|Visuals|Godot", "화면 연출이나 소리를 냅니다."),
    (r"^\s*[\w<>\[\],?]+\s+\w+\s*=", "값을 계산해서 이름을 붙여 기억합니다."),
    (r"^\s*\w[\w.]*\s*(\+\+|--|[+\-*/]?=)", "기억해 둔 값을 바꿉니다."),
    (r"\bawait\s+\w+\(|^\s*\w+\(", "이 모드가 따로 만든 기능을 부릅니다."),
]


def explain(code):
    """원본 코드 한 덩어리를 쉬운 말 한 줄로. 모르면 일반적인 설명."""
    first = next((line for line in str(code or "").splitlines() if line.strip()), "")
    for pattern, text in _EXPLAIN:
        if re.search(pattern, first):
            return text
    return "원본 코드로만 표현된 동작입니다."


def _raw_parts(blocks, project, ctx):
    """블록 안의 직접 코드 조각들 [(설명, 코드)]."""
    out = []
    for b in B.walk(blocks):
        if b.get("op") == "source_step":
            code = b.get("args", {}).get("source", "")
        elif b.get("op") in ("src_call", "src_loop"):
            lines, _errs = B.compile_blocks([dict(b, body=[])], project, ctx)
            code = "\n".join(line.strip() for line in lines if line.strip() and not line.strip().startswith(("{", "}", "//")))
        else:
            continue
        if code.strip():
            out.append((explain(code), code.strip()))
    return out


def direct_code_parts(project, kind, item):
    """항목의 효과 안에 남은 직접 코드 [(설명, 코드)]. 비어 있으면 AI 로 다시 만들 필요가 없다."""
    ctx = M._Ctx(kind, item)
    out = []
    for e in item.get("effects") or []:
        if e.get("blocks"):
            out += _raw_parts(e["blocks"], project, ctx)
        elif e.get("kind") == "code" and (e.get("code") or "").strip():
            out.append((explain(e["code"]), e["code"].strip()))
    return out


_IF_LINE = re.compile(r"^\s*(?:else\s+)?if\s*\(", re.M)
_IF_OPS = ("if", "if_else")


def _if_count(project, kind, item):
    """원본에 있던 조건문 수: 효과 블록의 if 와 직접 코드 안의 if 줄."""
    n = _answer_ifs(item.get("effects") or [])
    return n + sum(len(_IF_LINE.findall(code)) for _text, code in direct_code_parts(project, kind, item))


def _answer_ifs(effects):
    return sum(1 for e in effects for b in B.walk(e.get("blocks") or []) if b.get("op") in _IF_OPS)


RULES = ["- 직접 코드 블록(source_step)과 직접 입력 코드(kind \"code\" 의 code 칸)는 쓰지 마세요.",
         "- 블록으로 똑같이 만들 수 없는 부분은 가장 비슷한 블록으로 만들고, 무엇이 달라졌는지 답 앞의 설명에 적어 주세요.",
         "- 블록에 새 파워·기믹이 꼭 필요하면 같은 답의 powers / gimmicks 칸에 **새 ID** 로 넣으세요. 이미 있는 파워·기믹은 다시 보내지 마세요.",
         "- 더 쓰지 않는 파워·기믹은 답의 \"remove\" 칸에 [{\"kind\": \"power\", \"id\": \"...\"}] 처럼 적으세요 "
         "(kind: power · tag · summon · orb · pet · fx · button). 다른 카드·유물·물약이 쓰는 것은 지우지 마세요.",
         "- 카드라면: 원본 코드가 자원을 내고 쓰게 하면 효과가 아니라 res_power·res_cost 칸에 적고, 카드를 쓸 수 있는 조건은 "
         "play_cond 칸(cond 객체, 블록 코딩의 cond 형식)에 적으세요. 효과 안에서만 쓰는 if 조건은 효과 블록으로 두세요.",
         "- 원본 코드의 if 조건은 빼지 마세요. 조건으로 나뉘는 효과는 if 블록(또는 if_else)으로 그대로 옮기세요.",
         "- 파워를 몇 개 소모해서 추가 효과를 내는 블록은 설명이 길어지니, 그 효과에 짧은 설명을 text_ko·text_en·text_zh 로 적고 "
         "auto_text 를 false 로 두세요. 예: \"포격 2: 피해를 8 줍니다\" (이름 N: 효과 형식)."]
GROUPS = {"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}
BATCH = 8   # 한 번에 보낼 항목 수 (AI 답 길이 제한 때문에 나눈다)


def request_text(project, kind, item):
    """AI 에게 보낼 요청 (설명서 앞부분은 aiguide.build_prompt 가 붙인다)."""
    name = item.get("name_ko") or item.get("name_en") or item["id"]
    lines = [f"아래 {NOUN[kind]} '{name}' (id: {item['id']}) 의 효과를 **블록만으로** 다시 만들어 주세요.",
             f"- 답에는 이 {NOUN[kind]} 하나만, 같은 id \"{item['id']}\" 로 넣어 주세요. 툴은 effects 만 가져다 씁니다.",
             *RULES, ""]
    return "\n".join(lines + _item_lines(project, kind, item))


def _item_lines(project, kind, item):
    """항목 하나의 정보와 블록으로 바꿔야 하는 원본 코드."""
    lines = []
    if kind == "card":
        lines.append(f"카드 정보: 종류 {item.get('type')}, 비용 {item.get('cost')}, 대상 {item.get('target')}")
        if item.get("res_power") and int(item.get("res_cost") or 0) > 0:
            lines.append(f"자원 비용(지금): {item['res_power']} {item['res_cost']} (res_power·res_cost)")
        if item.get("star_cost"):
            lines.append(f"별 비용(지금): {item['star_cost']} (star_cost)")
        if isinstance(item.get("play_cond"), dict):
            lines.append("사용 조건(지금, play_cond): " + json.dumps(item["play_cond"], ensure_ascii=False, separators=(",", ":")))
    raw = [f"{v.get('name')}={v.get('value')}" + (f"(강화 +{v.get('upgrade')})" if v.get("upgrade") not in (None, 0, "0") else "")
           for v in item.get("raw_vars") or []]
    if raw:
        lines.append("원본 수치: " + ", ".join(raw))
    desc = item.get("desc_ko") or ""
    if desc:
        lines.append(f"원본 설명: {desc}")
    lines.append("")
    blocks = [b for e in item.get("effects") or [] for b in e.get("blocks") or []]
    if blocks:
        lines.append("지금 블록으로 된 부분 (그대로 살려 주세요): " + B.describe(blocks, project, kind, "ko", item))
    parts = direct_code_parts(project, kind, item)
    if parts:
        lines.append("")
        ifs = sum(len(_IF_LINE.findall(code)) for _text, code in parts)
        if ifs:
            lines.append(f"원본 코드에 조건문(if)이 {ifs}곳 있습니다. 조건을 빼지 말고 if 블록으로 옮기세요.")
        lines.append("블록으로 바꿔야 하는 원본 코드 (설명 → 코드):")
        for i, (text, code) in enumerate(parts, 1):
            lines.append(f"{i}. {text}")
            lines.append("```csharp")
            lines.append(code)
            lines.append("```")
    return lines


def full_prompt(project, kind, item):
    """복사할 전체 글: AI 설명서 + 이 항목 요청."""
    import aiguide as AG
    return AG.build_prompt(project, request_text(project, kind, item))


def targets(project, only=None):
    """직접 코드가 남은 항목 [(kind, item)]. only 를 주면 그 항목들(id 기준) 안에서만 찾는다."""
    ids = None if only is None else {id(x) for x in only}
    return [(kind, item) for kind, group in GROUPS.items() for item in project.get(group) or []
            if (ids is None or id(item) in ids) and direct_code_parts(project, kind, item)]


def chunks(pairs, size=BATCH):
    return [pairs[i:i + size] for i in range(0, len(pairs), size)]


def batch_request_text(project, pairs):
    """여러 항목을 한 번에 다시 만들게 하는 요청."""
    lines = [f"아래 {len(pairs)}개 항목의 효과를 **블록만으로** 다시 만들어 주세요.",
             "- 답 하나의 JSON 에 이 항목들을 모두, 각각 아래에 적힌 **같은 id** 로 넣어 주세요 (cards/relics/potions/powers 칸). "
             "툴은 각 항목의 effects 만 가져다 씁니다.",
             *RULES]
    for i, (kind, item) in enumerate(pairs, 1):
        name = item.get("name_ko") or item.get("name_en") or item["id"]
        lines += ["", f"### {i}. {NOUN[kind]} '{name}' (id: {item['id']})"] + _item_lines(project, kind, item)
    return "\n".join(lines)


# 요청을 파일로 첨부할 때 채팅창에 함께 보낼 문장. AI 는 첨부 파일 안의 지시를 '참고 자료'로만 보므로
# 무엇을 해 달라는지는 사용자가 채팅으로 직접 말해야 한다.
CHAT_MESSAGE = ("첨부한 파일은 제가 쓰는 '슬더스2 모드 메이커'의 작업 안내서와 제 요청서입니다. "
                "파일 맨 아래 '사용자의 요청'에 적힌 항목들은 제가 직접 부탁하는 것입니다. "
                "그 항목들의 효과를 안내서 형식대로 블록만으로 다시 만들어서, 안내서의 규칙대로 ```json 코드 블록 하나로 답해 주세요.")


def batch_prompt(project, pairs):
    import aiguide as AG
    return AG.build_prompt(project, batch_request_text(project, pairs))


def plan_answer(project, pairs, text):
    """AI 답 -> 바꿀 계획 (아무것도 바꾸지 않는다) -> (계획 또는 None, 알림 목록).
    계획 = {"effects": {(kind, id): 새 효과}, "adds": [새 파워·기믹], "removes": [(kind, id)]}.
    pairs 는 효과를 바꿀 항목들 [(kind, item)]. 답의 나머지 카드·유물·물약은 무시한다."""
    patch = AP.read_patch(text, project)
    notes = list(patch.errors)
    if patch.errors:
        return None, notes
    found = {(x["kind"], x["item"]["id"]): x["item"] for x in patch.items}
    effects = {}
    for kind, item in pairs:
        name = item.get("name_ko") or item.get("name_en") or item["id"]
        raw = found.get((kind, item["id"]))
        if raw is None and len(pairs) == 1:   # 한 항목 창: ID 가 조금 달라도 같은 종류가 하나뿐이면 그것을 쓴다
            same = [x["item"] for x in patch.items if x["kind"] == kind]
            raw = same[0] if len(same) == 1 else None
        if raw is None:
            notes.append(f"{name}: 답에 없습니다.")
            continue
        eff, more = _checked(project, kind, item, raw)
        notes += [f"{name}: {n}" for n in more]
        if eff is not None:
            effects[(kind, item["id"])] = eff
            want, have = _if_count(project, kind, item), _answer_ifs(eff)
            if have < want:
                notes.append(f"{name}: 원본에 조건문(if)이 {want}개 있는데 답에는 {have}개뿐입니다. 조건이 빠졌을 수 있으니 확인하세요.")
    targets_ = {(kind, item["id"]) for kind, item in pairs}
    adds = [x for x in patch.items if x["kind"] in ADD_KINDS and not x["exists"]]
    kept = [x["item"]["id"] for x in patch.items if x["kind"] in ADD_KINDS and x["exists"] and (x["kind"], x["item"]["id"]) not in targets_]
    if kept:
        notes.append("답에 있는 기존 파워·기믹은 이 창에서 바꾸지 않습니다: " + ", ".join(kept))
    removes, more = _removes(project, text, targets_)
    return {"effects": effects, "adds": adds, "removes": removes, "cardfields": _card_fields(text, found, effects)}, notes + more


def _answer_obj(text):
    try:
        obj, _fx = AP.extract(text)
    except ValueError:
        return None   # 읽기 오류는 read_patch 가 알려 준다
    return obj


def _card_fields(text, found, effects):
    """답의 카드 칸 중 자원 비용·사용 조건 (답에 적힌 것만) -> {(card, id): {칸: 값}}."""
    obj = _answer_obj(text)
    rows = obj.get("cards") if isinstance(obj, dict) else None
    out = {}
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        key = ("card", str(row.get("id") or ""))
        got = found.get(key)
        if got is None or key not in effects:
            continue
        fields = {k: got[k] for k in CARD_FIELDS if k in row and k in got}
        if fields:
            out[key] = fields
    return out


def _removes(project, text, skip):
    """답의 remove 칸 -> ([(kind, id)], 알림)."""
    try:
        obj, _fx = AP.extract(text)
    except ValueError:
        return [], []   # 읽기 오류는 read_patch 가 알려 준다
    rows = obj.get("remove") if isinstance(obj, dict) else None
    if not rows:
        return [], []
    if not isinstance(rows, list):
        return [], ["remove 칸은 목록으로 적어 주세요."]
    out, notes = [], []
    for row in rows:
        kind = row.get("kind") if isinstance(row, dict) else None
        ident = str(row.get("id") or "") if isinstance(row, dict) else ""
        label = f"{AP.NOUN.get(kind, '?')} '{ident}'"
        if kind not in REMOVABLE or not ident:
            notes.append(f"지울 항목을 알 수 없습니다: {str(row)[:60]}")
        elif (kind, ident) in skip:
            notes.append(f"{label}: 지금 바꾸는 항목이라 지우지 않습니다.")
        elif not _exists(project, kind, ident):
            notes.append(f"{label}: 프로젝트에 없어 건너뜁니다.")
        elif (kind, ident) not in out:
            out.append((kind, ident))
    return out, notes


def _exists(project, kind, ident):
    pool = project.get("powers", []) if kind == "power" else (project.get("gimmicks") or {}).get(AP.GIMMICKS[kind][0], [])
    return any(x["id"] == ident for x in pool)


def _pool(project, kind):
    if kind == "power":
        return project.setdefault("powers", [])
    return project.setdefault("gimmicks", {}).setdefault(AP.GIMMICKS[kind][0], [])


def plan_lines(plan):
    """계획을 사람이 읽을 줄로 (추가·제거가 없으면 빈 목록)."""
    lines = []
    if plan["adds"]:
        lines.append("새로 넣기: " + ", ".join(f"{AP.NOUN[x['kind']]} {x['item'].get('name_ko') or x['item']['id']}"
                                              for x in plan["adds"]))
    if plan["removes"]:
        lines.append("지우기: " + ", ".join(f"{AP.NOUN[k]} {i}" for k, i in plan["removes"]))
    for (_kind, ident), fields in plan["cardfields"].items():
        lines.append(f"카드 {ident} 자원·조건: " + ", ".join(_field_text(k, v) for k, v in fields.items()))
    return lines


def _field_text(key, value):
    if key in ("play_cond", "glow_cond"):
        return f"{key} {'있음' if isinstance(value, dict) else '없음'}"
    return f"{key} {value}"


def plan_errors(project, plan):
    """추가·제거·카드 자원 칸이 있을 때만: 넣었을 때 새로 생기는 검사 오류 (프로젝트는 건드리지 않는다)."""
    if not (plan["adds"] or plan["removes"] or plan["cardfields"]):
        return []
    try:
        base = M.validate(M.normalize(copy.deepcopy(project)))[0]
        tmp = copy.deepcopy(project)
        apply_plan(tmp, plan)
        errors = M.validate(tmp)[0]
    except Exception as ex:  # noqa: BLE001 - 검사 중 오류도 '넣지 않음' 사유로 보여 준다
        return [f"검사 중 오류: {ex}"]
    return [x for x in errors if x not in base]


def apply_extras(project, plan):
    """새 파워·기믹을 넣고, 지울 것을 지우고, 카드 자원·조건 칸을 넣는다 (효과는 바꾸지 않는다). 검사는 부르는 쪽이 먼저 한다."""
    if not (plan["adds"] or plan["removes"] or plan["cardfields"]):
        return
    if plan["adds"]:
        patch = AP.Patch()
        patch.items = [dict(x, take=True) for x in plan["adds"]]
        AP.apply(project, patch)
    for kind, ident in plan["removes"]:
        pool = _pool(project, kind)
        pool[:] = [x for x in pool if x["id"] != ident]
    for (_kind, ident), fields in plan["cardfields"].items():
        card = next(x for x in project.get("cards", []) if x["id"] == ident)
        card.update(copy.deepcopy(fields))
    M.normalize(project)


def apply_plan(project, plan):
    """계획 전체를 프로젝트에 넣는다: 효과 → 새 파워·기믹 → 지우기."""
    for (kind, ident), effects in plan["effects"].items():
        item = next(x for x in project[AP.KEY[kind]] if x["id"] == ident)
        item["effects"] = copy.deepcopy(effects)
    apply_extras(project, plan)


def apply_answer(project, kind, item, text):
    """한 항목의 AI 답 -> (새 효과 또는 None, 알림 목록). 항목을 직접 바꾸지는 않는다."""
    plan, notes = plan_answer(project, [(kind, item)], text)
    return (plan["effects"].get((kind, item["id"])) if plan else None), notes


def apply_batch_answer(project, pairs, text):
    """여러 항목의 AI 답 -> ({(kind, id): 새 효과}, 알림 목록). 문제가 있는 항목은 빼고 나머지만 돌려준다."""
    plan, notes = plan_answer(project, pairs, text)
    return (plan["effects"] if plan else {}), notes


def _checked(project, kind, item, raw):
    """답의 항목에서 효과를 꺼내 검사한다 -> (효과 또는 None, 알림)."""
    notes = []
    effects = copy.deepcopy(raw.get("effects") or [])
    if not effects:
        return None, notes + ["답에 효과가 없습니다."]
    left = sum(1 for e in effects for b in B.walk(e.get("blocks") or []) if b.get("op") in RAW_OPS)
    left += sum(1 for e in effects if e.get("kind") == "code" and not e.get("blocks") and (e.get("code") or "").strip())
    if left:
        notes.append(f"답에 직접 코드가 {left}곳 남아 있습니다. 그래도 넣을 수 있지만, AI에게 다시 요청해 보세요.")
    errors = []
    for e in effects:
        if e.get("blocks"):
            errors += B.compile_blocks(e["blocks"], project, M._Ctx(kind, item))[1]
    if errors:
        return None, notes + ["블록 오류: " + "; ".join(dict.fromkeys(errors))]
    return effects, notes

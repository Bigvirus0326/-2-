"""
AI(ChatGPT·Claude 등 채팅)에게 줄 설명서 만들기.

표·선택지는 모두 툴의 코드(modgen / blockcode / gimmick)에서 바로 만든다 — 툴이 바뀌어도 설명서가 같이 바뀐다.
설명서 끝에는 지금 프로젝트에 있는 ID 목록과 사용자의 요청이 붙는다.
AI는 ```json 코드 블록 하나로 답하고, 그 답을 'AI 결과 붙여넣기' 창(aipaste.py)에 붙여 넣는다.
"""
from __future__ import annotations

import json

import blockcode as B
import cardframe as CF
import gimmick as G
import modgen as M

FORMAT_TAG = "sts2mod-patch"   # AI 답의 머리 표시 (붙여넣기 창이 알아봄)

ARG_KIND_TEXT = {
    "who_multi": 'who: "self" | "target" | "it"(each_enemy/random_enemy 안의 그 적) | "all" | "random"',
    "value": "value 객체",
    "int": "정수",
    "bool": "true/false",
    "power": 'power 참조 (아래 "파워 참조")',
    "card_filter": '"Any" | "Attack" | "Skill" | "Power" | "tag:<태그ID>"',
    "which": '"random" | "all"',
    "hand_action": '"upgrade" | "exhaust" | "discard"',
    "keyword": '"Exhaust" | "Ethereal" | "Innate" | "Retain" | "Unplayable" | "Sly" | "Eternal"',
    "kw_action": '"add"(부여) | "remove"(제거)',
    "kw_where": '"hand" | "draw" | "discard" | "all"(세 더미 전부)',
    "card": '"this"(이 카드) 또는 카드 ID',
    "pile": '"Hand" | "Draw" | "Discard"',
    "cond": "cond 객체",
    "varname": "변수 이름 (영문 한 글자~단어)",
    "summon": "소환수 ID",
    "summon_any": '소환수 ID 또는 "*"(전부)',
    "label": '{"ko": "...", "en": "...", "zh": "..."}',
    "pick_pile": '"Hand" | "Draw" | "Discard" | "Exhaust"',
    "pick_action": '"hand" | "top" | "exhaust" | "discard" | "upgrade"',
    "delay_when": '"start"(다음 내 턴 시작) | "end"(이번 턴 끝)',
    "orb": '게임 구체 "Lightning" | "Frost" | "Dark" | "Plasma" | "Glass" 또는 새 구체 "o:<구체ID>"',
    "evoke_which": '"front" | "last"',
    "pet": "동료 ID",
    "fx": "이펙트 ID",
    "button": "버튼 ID",
}


def _opts(options):
    return " | ".join(f'"{v}"({l})' if v else f'""({l})' for v, l in options)


def _list(title, items):
    return f"- {title}: " + (", ".join(items) if items else "(없음)")


def project_summary(project):
    """AI가 겹치지 않게, 또 참조할 수 있게 지금 프로젝트의 ID 목록."""
    g = project.get("gimmicks") or {}
    out = [f"모드 ID: {project['mod']['id']}"]
    ch = project.get("character") or {}
    if ch.get("enabled"):
        out.append(f"캐릭터: {ch.get('name_ko')} ({ch.get('id')}), 체력 {ch.get('hp')}, 구체 슬롯 {ch.get('orb_slots', 0)}, "
                   f"별 표시 {'예' if ch.get('show_stars') else '아니오'}")
    out.append(_list("카드", [f"{c['id']}({c.get('name_ko', '')}, {c.get('type')}, {c.get('cost')}코)" for c in project.get("cards", [])]))
    out.append(_list("유물", [f"{r['id']}({r.get('name_ko', '')})" for r in project.get("relics", [])]))
    out.append(_list("물약", [f"{p['id']}({p.get('name_ko', '')})" for p in project.get("potions", [])]))
    out.append(_list("새 파워 (참조할 때 \"c:<ID>\")",
                     [f"{p['id']}({p.get('name_ko', '')}, {p.get('type')})" for p in project.get("powers", [])]))
    out.append(_list("카드 태그 (card_filter 에서 \"tag:<ID>\", 카드의 gtags)",
                     [f"{t['id']}({t.get('name_ko', '')})" for t in g.get("tags", [])]))
    out.append(_list("소환수 (power 참조 \"s:<ID>\", summon 블록)", [f"{s['id']}({s.get('name_ko', '')})" for s in g.get("summons", [])]))
    out.append(_list("구체", [f"{o['id']}({o.get('name_ko', '')})" for o in g.get("orbs", [])]))
    out.append(_list("동료", [f"{p['id']}({p.get('name_ko', '')})" for p in g.get("pets", [])]))
    out.append(_list("이펙트", [f"{e['id']}({e.get('name', '')})" for e in g.get("effects", [])]))
    out.append(_list("전투 버튼", [f"{b['id']}({b.get('label_ko', '')})" for b in g.get("buttons", [])]))
    out.append(_list("카드 테두리 디자인 (카드의 frame_style)", [f"{s['id']}({s.get('name', '')})" for s in CF.styles(project)]))
    return "\n".join(out)


def _blocks_reference():
    lines = []
    for cat, ops in B.PALETTE:
        lines.append(f"[{B.CATS[cat][0]}]")
        for op in ops:
            spec = B.SPECS[op]
            args = ", ".join(f"{k}: {ARG_KIND_TEXT.get(kind, kind)}" for k, (kind, _d) in spec["args"].items())
            extra = []
            if spec.get("body"):
                extra.append("body")
            if spec.get("else"):
                extra.append("else")
            if spec.get("third"):
                extra.append("third")
            lines.append(f'  "{op}": {spec["ko"]}' + (f"  — args {{{args}}}" if args else "") +
                         (f"  — 안쪽 블록 목록: {', '.join(extra)}" if extra else ""))
    return "\n".join(lines)


EXAMPLE = {
    "format": FORMAT_TAG,
    "cards": [
        {"id": "ember_slash", "name_ko": "불씨 베기", "name_en": "Ember Slash", "name_zh": "余烬斩",
         "type": "Attack", "rarity": "Common", "cost": 1, "upgrade_cost": 1, "target": "AnyEnemy",
         "effects": [{"kind": "damage", "amount": 7, "upgrade": 3},
                     {"kind": "power", "power": "Weak", "amount": 1, "upgrade": 1, "target": "enemy"}]},
        {"id": "chain_spark", "name_ko": "연쇄 불꽃", "name_en": "Chain Spark", "type": "Skill", "rarity": "Uncommon",
         "cost": 1, "upgrade_cost": 0, "target": "Self", "keywords": ["Exhaust"],
         "effects": [{"kind": "code", "auto_text": True, "blocks": [
             {"op": "repeat", "args": {"times": {"t": "count", "what": "enemies"}}, "body": [
                 {"op": "damage", "args": {"who": "random", "amount": {"t": "num", "v": 4, "up": 2}, "hits": 1, "powered": True}}]},
             {"op": "if", "args": {"cond": {"t": "cmp", "a": {"t": "stat", "who": "self", "stat": "hp"}, "op": "<=",
                                             "b": {"t": "num", "v": 20}}},
              "body": [{"op": "block", "args": {"amount": {"t": "num", "v": 8}}}]}]}]},
    ],
    "powers": [
        {"id": "kindling", "name_ko": "불쏘시개", "name_en": "Kindling", "type": "Buff", "stack": "Counter",
         "trigger": "turn_start", "decay": "none",
         "effects": [{"kind": "block", "amount": 2, "per_stack": True}],
         "modifiers": [{"kind": "dmg_dealt_add", "value": 1, "per_stack": True, "filter": "Attack"}]},
    ],
    "relics": [
        {"id": "ash_charm", "name_ko": "재 부적", "name_en": "Ash Charm", "rarity": "Uncommon", "trigger": "card_played",
         "played_filter": "Attack", "played_every": 3,
         "effects": [{"kind": "power", "power": "c:kindling", "amount": 1, "target": "self"}],
         "flavor_ko": "따뜻한 재가 남아 있다.", "flavor_en": "Still warm."},
    ],
}


def build_prompt(project, request="", include_blocks=True, include_project=True):
    custom_powers = [f"c:{p['id']}" for p in project.get("powers", [])]
    game_powers = ", ".join(f'"{k}"({v[1]}, 기본 대상 {v[3]})' for k, v in M.POWERS.items())
    parts = [f"""# 슬레이 더 스파이어 2 모드 메이커 — AI 작업 설명서

너는 '슬더스2 모드 메이커'라는 툴의 프로젝트에 넣을 카드·유물·물약·파워를 만드는 도우미다.
사용자가 원하는 것을 아래 형식의 JSON 으로 만들어 준다. 사용자는 그 JSON 을 툴의 'AI 결과 붙여넣기' 창에 붙여 넣고,
툴이 검사·미리보기한 뒤 프로젝트에 넣는다. 툴이 C# 코드를 만들어 주므로 너는 C# 를 쓰지 않는다.

## 답하는 방법 (꼭 지킬 것)
1. 먼저 무엇을 만들지 한두 줄로 설명한다 (선택).
2. 그다음 ```json 코드 블록 **하나**에 결과를 넣는다. 맨 위에 "format": "{FORMAT_TAG}" 를 넣는다.
3. JSON 은 주석·끝 쉼표 없이 올바른 JSON 이어야 한다.
4. 새로 만드는 것만 넣는다. 이미 있는 ID 를 쓰면 그 항목을 **바꾸는** 것으로 처리된다 (사용자가 고칠 것을 요청했을 때만 그렇게 한다).
5. 빠뜨린 칸은 기본값으로 채워지므로 필요한 칸만 쓰면 된다. 그림(image) 칸은 쓰지 않는다.
6. 사용자가 툴에서 받은 오류 목록을 보내면, 그 오류를 고친 **전체 JSON** 을 다시 보낸다.

## 최상위 형식
{{"format": "{FORMAT_TAG}", "cards": [...], "relics": [...], "potions": [...], "powers": [...]}}

## 공통 규칙
- id: 영문 소문자로 시작, 소문자·숫자·밑줄(_)만 (예: "fire_slash"). 다른 카드·유물·물약·파워·기믹과 겹치면 안 된다.
- 이름: name_ko(한국어), name_en(영어), name_zh(중국어 간체, 선택). 설명(desc_ko/desc_en/desc_zh)은 **비워 두면 효과에서 자동으로**
  만들어지므로 보통 쓰지 않는다.
- 효과(effects)는 위에서부터 차례로 실행된다.

## 카드 (cards)
- type: {_opts(M.CARD_TYPES)}
- rarity: {_opts(M.CARD_RARITIES)}  (기본 카드는 시작 덱용)
- cost / upgrade_cost: 에너지 비용 0~9 (강화 후 비용).
- x_cost: true 면 X 비용 (남은 에너지를 전부 씀, 소용돌이처럼; cost 는 무시). x_plus_up: true 면 강화 시 X+1.
  X 를 쓰는 법: 효과의 x_use ("times" = 그 효과를 X번, 피해는 타격 횟수 × X / "mult" = 수치 × X) 또는 블록 값 {{"t": "energy_x"}}.
- target: {_opts(M.CARD_TARGETS)}  (적 하나에게 피해를 주면 "AnyEnemy", 자신에게만 쓰면 "Self")
- keywords: [{_opts(M.CARD_KEYWORDS)}] 중 여러 개
- upgrade_add_keyword: 강화하면 붙는 키워드 하나 또는 ""
- upgrade_remove_keyword: 강화하면 없어지는 키워드 하나 또는 "" (예: 강화하면 소멸이 사라짐 → "Exhaust", keywords 에도 있어야 함)
- tag: {_opts(M.CARD_TAGS)}
- gtags: 기믹 카드 태그 ID 목록 (프로젝트에 있는 것만)
- res_power / res_cost: 쓰려면 파워 자원을 내야 하는 카드 (예: "c:<파워ID>", 3)
- star_cost / star_cost_up: 별 비용 (리젠트처럼), star_x: true 면 가진 별을 전부 씀
- frame_style: "" (캐릭터 기본) | "_game" | 카드 테두리 디자인 ID

## 유물 (relics)
- rarity: {_opts(M.RELIC_RARITIES)}
- trigger: {_opts(M.RELIC_TRIGGERS)}
- trigger 가 "card_played" 일 때: played_filter {_opts(M.PLAYED_CARD_FILTERS)} (또는 "tag:<태그ID>"), played_every 몇 장마다 (1~99)
- enemy_mode: {_opts(M.RELIC_ENEMY_MODES)}  (적에게 가는 효과의 대상)
- flavor_ko / flavor_en / flavor_zh: 설명 아래 짧은 글

## 물약 (potions)
- rarity: {_opts(M.POTION_RARITIES)}
- target: {_opts(M.POTION_TARGETS)}

## 새 파워 (powers) — 게임에 없는 버프·디버프·자원
- type: {_opts(M.POWER_TYPES)}
- stack: {_opts(M.POWER_STACKS)}
- trigger: {_opts(M.POWER_TRIGGERS)}
- decay: {_opts(M.POWER_DECAY)}
- trigger 가 "card_played" 일 때: played_filter (위와 같음), played_by {_opts(M.POWER_PLAYED_BY)}
- enemy_mode: 유물과 같음
- 효과의 per_stack: true 면 수치 × 파워 스택 (예: 스택마다 방어도 2)
- 효과의 target 에 "other" 를 쓰면 트리거의 상대 (카드 사용 시 = 카드의 대상, 피해를 받을 때 = 공격자, 피해를 줄 때 = 맞은 적)
- modifiers (상시 효과): [{{"kind": ..., "value": 수, "per_stack": true/false, "filter": "Any"|"Attack"|"Skill"|"Power"|"tag:<태그ID>", "ref": ""}}]
  kind: {_opts(M.MODIFIER_KINDS)}
  filter 는 {", ".join(sorted(M.MODIFIER_FILTERED))} 에만 쓰인다. ref 가 필요한 kind: {", ".join(f"{k}({v[0]})" for k, v in M.MODIFIER_REF.items())}.
  수치가 필요 없는 kind: {", ".join(sorted(M.MODIFIER_NO_VALUE))}.
- 자원으로 쓰는 파워: cap (최대 스택, 0 = 없음), group (같은 group 의 파워는 하나만 유지 — 날씨·자세), hidden (아이콘 숨김)

## 효과 (effects) — 카드·유물·물약·파워 공통
{{"kind": 종류, "amount": 수치, "upgrade": 강화 시 더할 수치(카드만), ...}}
- kind: {_opts(M.EFFECT_KINDS)}
- damage: hits (몇 번), 대상은 카드 target / 유물 enemy_mode 를 따른다.
- x_use (X 비용 카드만): "" | "times" | "mult"
- power / remove_power: power (아래 파워 참조), target "self" | "enemy" | "other"(파워 전용). remove_power 의 amount 0 = 전부 제거.
- 조건(선택): cond_power 파워 참조, cond_min 몇 이상, cond_on "self" | "target" — 그 파워가 cond_min 이상 있을 때만 실행.
- 스택 비례(선택): scale_power 파워 참조, scale_per 수, scale_on "self" | "target" — 그 파워 1 스택마다 수치 + scale_per.
- code: 블록 코딩으로 만든 새 능력. {{"kind": "code", "auto_text": true, "blocks": [블록...]}}
  위의 단순 효과로 안 되는 것(반복, 조건 분기, 손패 조작, 카드 만들기, 하나 고르기, 소환, 구체, 별, 동료 등)은 code 로 만든다.

## 파워 참조 (power 칸에 쓰는 문자열)
- 게임 파워: {game_powers}
- 이 프로젝트의 새 파워: "c:<파워ID>"  지금 있는 것: {", ".join(custom_powers) or "(없음)"}
  같은 답 안에서 새로 만드는 파워도 "c:<ID>" 로 참조할 수 있다.
- 소환수의 단계: "s:<소환수ID>"
"""]
    if include_blocks:
        parts.append(f"""## 블록 코딩 (effects 의 kind "code")
블록 = {{"op": 이름, "args": {{...}}, "body": [블록...], "else": [블록...], "third": [블록...]}}
(body/else/third 는 그 블록이 안쪽 블록을 가질 때만)

value 객체 (수치가 들어가는 자리):
- {{"t": "num", "v": 6, "up": 3}}  숫자 (up = 카드 강화 시 더함, 선택)
- {{"t": "stack", "who": "self"|"target"|"it", "power": 파워 참조}}  그 파워 스택 수
- {{"t": "stat", "who": ..., "stat": "hp"|"maxhp"|"block"}}
- {{"t": "count", "what": "hand"|"draw"|"discard"|"exhaust"|"enemies"}}
- {{"t": "energy_x"}} X (X 비용 카드에 쓴 에너지),  {{"t": "star_x"}} X (별 X 카드에 쓴 별)
- {{"t": "energy"}} 남은 에너지,  {{"t": "round"}} 현재 턴 수,  {{"t": "amount"}} 이 파워의 스택(파워 안에서)
- {{"t": "played", "scope": "turn"|"combat", "filter": "Any"|"Attack"|"Skill"|"Power"|"tag:<태그ID>"}} 사용한 카드 수
- {{"t": "rand", "min": value, "max": value}},  {{"t": "var", "name": "a"}}
- {{"t": "op", "op": "+"|"-"|"*"|"/", "a": value, "b": value}}
- {{"t": "summons"}}, {{"t": "stars"}}, {{"t": "orbs", "what": "count"|"slots"|"empty", "orb": 구체 참조(선택)}},
  {{"t": "osty", "what": "hp"|"maxhp"}}, {{"t": "pet", "pet": 동료ID, "what": "hp"|"maxhp"}}

cond 객체 (조건):
- {{"t": "cmp", "a": value, "op": ">="|">"|"=="|"<"|"<="|"!=", "b": value}}
- {{"t": "chance", "pct": value}}  확률(%)
- {{"t": "has", "who": "self"|"target"|"it", "power": 파워 참조}}
- {{"t": "and"|"or", "a": cond, "b": cond}},  {{"t": "not", "a": cond}}
- {{"t": "osty_alive"}}, {{"t": "pet_alive", "pet": 동료ID}}

블록 목록 (op: 화면에 보이는 모양 — args):
{_blocks_reference()}

주의: 소환수·구체·동료·이펙트·버튼·태그 블록은 프로젝트에 그 기믹이 있어야 쓸 수 있다 (아래 '지금 프로젝트' 참고).
""")
    parts.append("## 예시\n```json\n" + json.dumps(EXAMPLE, ensure_ascii=False, indent=1) + "\n```\n")
    if include_project:
        parts.append("## 지금 프로젝트에 있는 것 (ID 가 겹치지 않게, 참조할 때 사용)\n" + project_summary(project) + "\n")
    parts.append("## 사용자의 요청\n" + ((request or "").strip() or "(사용자가 이 아래에 요청을 적는다)") + "\n")
    return "\n".join(parts)


def fix_request(errors, warnings=None, fixes=None):
    """툴의 검사 결과를 AI 에게 돌려보낼 문장."""
    lines = ["툴에 붙여 넣었더니 아래 문제가 나왔어. 고친 **전체 JSON** 을 같은 형식(```json, \"format\": \"%s\")으로 다시 보내줘." % FORMAT_TAG, ""]
    if errors:
        lines.append("오류 (꼭 고칠 것):")
        lines += [f"- {e}" for e in errors]
    if warnings:
        lines.append("")
        lines.append("경고 (가능하면 고칠 것):")
        lines += [f"- {w}" for w in warnings]
    if fixes:
        lines.append("")
        lines.append("툴이 자동으로 고친 것 (참고):")
        lines += [f"- {f}" for f in fixes]
    return "\n".join(lines)

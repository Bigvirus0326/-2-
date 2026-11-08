"""
슬레이 더 스파이어 2 (StS2) 모드 프로젝트 생성기.

프로젝트 데이터(dict, JSON으로 저장)를 받아 BaseLib 기반 C# / Godot 모드 프로젝트를 만든다.
구조는 Alchyr의 ModTemplate-StS2 (Character 템플릿)를 따른다.

새 메커니즘 지원:
  - 커스텀 파워(버프/디버프): 발동 시점 + 효과, 상시 수치 변경(피해/방어도/드로우/에너지), 감소 방식
  - 효과 조건(파워 N 이상이면), 스택 비례 추가 수치, 파워 제거(소모)
  - 직접 C# 코드 효과 / 클래스에 코드 추가
"""
from __future__ import annotations

import copy
import json
import os
import re
import shutil
from xml.sax.saxutils import escape as xml_escape

import cardframe
import gimmick
import pngmake

GENERATOR_VERSION = "1.2.0"

# ---------------------------------------------------------------------------
# 선택지 정의 (내부 값, 한국어 표시)
# ---------------------------------------------------------------------------
CARD_TYPES = [("Attack", "공격"), ("Skill", "스킬"), ("Power", "파워")]
CARD_RARITIES = [("Basic", "기본"), ("Common", "일반"), ("Uncommon", "특별"), ("Rare", "희귀")]
CARD_TARGETS = [("AnyEnemy", "적 하나"), ("AllEnemies", "모든 적"), ("RandomEnemy", "무작위 적"), ("Self", "자신")]
CARD_KEYWORDS = [("Exhaust", "소멸"), ("Ethereal", "휘발성"), ("Innate", "선천성"), ("Retain", "보존"),
                 ("Unplayable", "사용불가"), ("Sly", "교활"), ("Eternal", "영구")]
# 게임 번역(card_keywords)과 같은 이름
KEYWORD_NAMES = {"ko": dict(CARD_KEYWORDS),
                 "en": {k: k for k, _l in CARD_KEYWORDS},
                 "zh": {"Exhaust": "消耗", "Ethereal": "虚无", "Innate": "固有", "Retain": "保留", "Unplayable": "不能被打出",
                        "Sly": "奇巧", "Eternal": "永恒"}}
# 게임의 CardKeywordOrder: 설명 위(이 순서로 위에서부터) / 설명 아래
KEYWORDS_BEFORE = ("Unplayable", "Innate", "Retain", "Sly", "Ethereal")
KEYWORDS_AFTER = ("Exhaust", "Eternal")


def card_keywords(card, upgraded=False):
    """강화 여부를 반영한 키워드 목록."""
    kws = list(card.get("keywords", []))
    if upgraded:
        add, rem = card.get("upgrade_add_keyword"), card.get("upgrade_remove_keyword")
        if add and add not in kws:
            kws.append(add)
        if rem and rem in kws:
            kws.remove(rem)
    return kws
CARD_TAGS = [("", "없음"), ("Strike", "타격"), ("Defend", "수비")]
RELIC_RARITIES = [("Starter", "시작"), ("Common", "일반"), ("Uncommon", "특별"), ("Rare", "희귀"), ("Shop", "상점")]
RELIC_TRIGGERS = [
    ("first_turn", "전투 시작 시 (첫 턴)"),
    ("turn_start", "매 턴 시작 시"),
    ("turn_end", "턴 종료 시"),
    ("card_played", "카드 사용 시"),
    ("combat_victory", "전투 승리 시"),
    ("pickup", "획득 시 (1회)"),
]
RELIC_ENEMY_MODES = [("all", "모든 적"), ("random", "무작위 적")]
PLAYED_CARD_FILTERS = [("Any", "아무 카드"), ("Attack", "공격 카드"), ("Skill", "스킬 카드"), ("Power", "파워 카드")]
POTION_RARITIES = [("Common", "일반"), ("Uncommon", "특별"), ("Rare", "희귀")]
POTION_TARGETS = [("Self", "자신"), ("AnyEnemy", "적 하나"), ("AllEnemies", "모든 적")]
PLACEHOLDER_CHARS = [("ironclad", "아이언클래드"), ("silent", "사일런트"), ("defect", "디펙트"),
                     ("necrobinder", "네크로바인더"), ("regent", "리젠트")]

# 커스텀 파워
POWER_TYPES = [("Buff", "버프"), ("Debuff", "디버프")]
POWER_STACKS = [("Counter", "중첩 (수치가 쌓임)"), ("Single", "단일 (쌓이지 않음)")]
POWER_TRIGGERS = [
    ("none", "없음 (상시 효과만)"),
    ("turn_start", "소유자의 턴 시작 시"),
    ("turn_end", "소유자의 턴 종료 시"),
    ("card_played", "카드 사용 시"),
    ("damage_received", "공격 피해를 받을 때"),
    ("damage_given", "공격으로 피해를 줄 때"),
]
POWER_PLAYED_BY = [("owner", "소유자가 사용"), ("any", "아무 플레이어나 사용")]
POWER_DECAY = [("none", "줄어들지 않음"), ("tick", "턴 종료 시 1 감소"), ("remove", "턴 종료 시 사라짐"),
               ("remove_start", "내 턴 시작 시 사라짐 (턴마다 초기화)")]
MODIFIER_KINDS = [
    ("dmg_dealt_add", "주는 공격 피해 +"),
    ("dmg_dealt_pct", "주는 공격 피해 +%"),
    ("dmg_taken_add", "받는 공격 피해 +"),
    ("dmg_taken_pct", "받는 공격 피해 +%"),
    ("block_add", "카드로 얻는 방어도 +"),
    ("hand_draw", "턴 시작 드로우 +"),
    ("max_energy", "최대 에너지 +"),
    ("cost_add", "카드 비용 + (음수면 감소)"),
    ("keep_block", "턴이 끝나도 방어도 유지"),
    # ---- 새로 만든 기믹 / 직업 시스템 ----
    ("orb_value", "구체 수치 + (밀집처럼)"),
    ("orb_passive_times", "구체 지속 효과 발동 횟수 +"),
    ("orb_slots", "구체 슬롯 +"),
    ("star_cost", "카드 별 비용 + (음수면 감소)"),
    ("stars_for_energy", "에너지가 모자라면 별로 냄"),
    ("osty_dmg", "골골이 공격 피해 +"),
    ("pet_dmg", "동료(골골이형) 공격 피해 +"),
    ("summon_amount", "골골이 소환량 +"),
    ("summon_slots", "소환수 슬롯 +"),
    ("res_cap", "자원 최대 스택 +"),
    ("res_cost", "카드 자원 비용 + (음수면 감소)"),
    ("button_cost", "버튼 에너지 비용 + (음수면 감소)"),
    ("button_uses", "버튼 턴당 횟수 +"),
]
# 카드에 따라 적용되는 상시 효과 (카드 필터를 고를 수 있음)
MODIFIER_FILTERED = {"dmg_dealt_add", "dmg_dealt_pct", "cost_add", "star_cost", "res_cost"}
# 무엇에 적용할지 고르는 상시 효과: 종류 -> (무엇, 비워도 되는가)
MODIFIER_REF = {"orb_value": ("orb", True), "orb_passive_times": ("orb", True), "res_cap": ("power", False),
                "res_cost": ("power", False), "button_cost": ("button", True), "button_uses": ("button", True),
                "pet_dmg": ("pet", True)}
# 수치가 필요 없는 상시 효과
MODIFIER_NO_VALUE = {"keep_block", "stars_for_energy"}
MODIFIER_LABEL = dict(MODIFIER_KINDS)
# 파워 효과의 '상대' (트리거에 따라 의미가 다름)
POWER_OTHER = {"card_played": "카드의 대상", "damage_received": "공격자", "damage_given": "피해를 받은 대상"}

# 기본 게임 파워: key -> (클래스명, 한국어, 영어, 기본 대상)
POWERS = {
    "Strength": ("StrengthPower", "힘", "Strength", "self"),
    "Dexterity": ("DexterityPower", "민첩", "Dexterity", "self"),
    "Vigor": ("VigorPower", "활력", "Vigor", "self"),
    "Plating": ("PlatingPower", "판금", "Plating", "self"),
    "Weak": ("WeakPower", "약화", "Weak", "enemy"),
    "Vulnerable": ("VulnerablePower", "취약", "Vulnerable", "enemy"),
    "Frail": ("FrailPower", "손상", "Frail", "enemy"),
    "Poison": ("PoisonPower", "중독", "Poison", "enemy"),
    "Doom": ("DoomPower", "종말", "Doom", "enemy"),
    "Focus": ("FocusPower", "밀집", "Focus", "self"),
}

EFFECT_KINDS = [
    ("damage", "피해"),
    ("block", "방어도"),
    ("draw", "카드 뽑기"),
    ("energy", "에너지 획득"),
    ("heal", "체력 회복"),
    ("lose_hp", "체력 잃기 (자신)"),
    ("max_hp", "최대 체력 증가"),
    ("gold", "골드 획득"),
    ("power", "파워 부여"),
    ("remove_power", "파워 제거 (소모)"),
    ("code", "🧩 새 능력 (블록 코딩 / C#)"),
]
OUT_OF_COMBAT_OK = {"heal", "max_hp", "gold", "code"}
EFFECT_LABEL = dict(EFFECT_KINDS)
X_USES = [("", "쓰지 않음"), ("times", "X번 반복"), ("mult", "수치 × X")]


def x_use(e, owner_kind, item):
    """X 비용 카드의 효과일 때만 '횟수/곱하기' 를 돌려준다."""
    if owner_kind != "card" or not (item or {}).get("x_cost"):
        return ""
    return e.get("x_use") if e.get("x_use") in ("times", "mult") else ""


def _x_paren(xt):
    """곱셈 안에서는 X+1 을 괄호로: 4×(X+1)."""
    return xt.replace("show:X+1|", "show:(X+1)|")


def x_text(item):
    return "{IfUpgraded:show:X+1|X}" if (item or {}).get("x_plus_up") else "X"

VAR_NAME = {"damage": "Damage", "block": "Block", "draw": "Cards", "energy": "Energy", "heal": "Heal",
            "lose_hp": "HpLoss", "max_hp": "MaxHp", "gold": "Gold"}

ID_RE = re.compile(r"^[a-z][a-z0-9]*(_[a-z0-9]+)*$")
MODID_RE = re.compile(r"^[A-Z][A-Za-z0-9]*$")
HEX_RE = re.compile(r"^#?[0-9a-fA-F]{6}$")


def label_of(options, value):
    for v, l in options:
        if v == value:
            return l
    return value


# ---------------------------------------------------------------------------
# 기본 데이터
# ---------------------------------------------------------------------------
def new_effect(kind="damage", amount=6, upgrade=3, hits=1, power="Strength", target=None, **extra):
    if target is None:
        target = POWERS[power][3] if (kind in ("power", "remove_power") and power in POWERS) else "enemy"
    e = {"kind": kind, "amount": amount, "upgrade": upgrade, "hits": hits, "power": power, "target": target,
         "per_stack": False,
         "cond_power": "", "cond_min": 1, "cond_on": "self",
         "scale_power": "", "scale_per": 1, "scale_on": "self",
         "code": "", "text_ko": "", "text_en": "", "blocks": [], "auto_text": False,
         "x_use": ""}   # X 비용 카드: "" | "times"(X번 반복) | "mult"(수치 × X)
    e.update(extra)
    return e


def new_card(cid="new_card"):
    return {
        "id": cid, "name_ko": "새 카드", "name_en": "New Card",
        "type": "Attack", "rarity": "Common", "cost": 1, "upgrade_cost": 1, "target": "AnyEnemy",
        "pool_character": "",   # 통째로 가져온 모드에서 특정 캐릭터의 카드 풀에만 넣기
        "x_cost": False, "x_plus_up": False,   # 에너지 X 비용 (남은 에너지를 전부 씀), 강화하면 X+1
        "keywords": [], "upgrade_add_keyword": "", "upgrade_remove_keyword": "", "tag": "",
        "effects": [new_effect("damage", 8, 3)],
        "desc_ko": "", "desc_en": "", "image": "", "extra_code": "",
        **copy.deepcopy(gimmick.CARD_DEFAULTS),
    }


def new_relic(rid="new_relic"):
    return {
        "id": rid, "name_ko": "새 유물", "name_en": "New Relic", "rarity": "Common",
        "trigger": "turn_start", "played_filter": "Any", "played_every": 1, "enemy_mode": "all",
        "effects": [new_effect("block", 3, 0)],
        "flavor_ko": "", "flavor_en": "", "desc_ko": "", "desc_en": "", "image": "", "extra_code": "",
        "upgrade_relic": "",     # 고대의 존재(오로바스의 손길 등)가 이 시작 유물을 바꿔 줄 강화 버전 유물 ID
    }


def new_potion(pid="new_potion"):
    return {
        "id": pid, "name_ko": "새 물약", "name_en": "New Potion", "rarity": "Common", "target": "AnyEnemy",
        "effects": [new_effect("damage", 20, 0)],
        "desc_ko": "", "desc_en": "", "image": "", "extra_code": "",
    }


def new_power(pid="new_power"):
    return {
        "id": pid, "name_ko": "새 파워", "name_en": "New Power", "type": "Buff", "stack": "Counter",
        "trigger": "turn_start", "played_filter": "Any", "played_by": "owner", "enemy_mode": "all",
        "decay": "none", "modifiers": [],
        "effects": [new_effect("block", 1, 0, per_stack=True)],
        "desc_ko": "", "desc_en": "", "image": "", "extra_code": "",
        **copy.deepcopy(gimmick.POWER_DEFAULTS),
    }


def new_modifier(kind="dmg_dealt_add", value=1, per_stack=True):
    return {"kind": kind, "value": value, "per_stack": per_stack, "filter": "Any", "ref": ""}


def default_project():
    strike = new_card("strike")
    strike.update({"name_ko": "타격", "name_en": "Strike", "rarity": "Basic", "tag": "Strike",
                   "effects": [new_effect("damage", 6, 3)]})
    defend = new_card("defend")
    defend.update({"name_ko": "수비", "name_en": "Defend", "type": "Skill", "rarity": "Basic", "target": "Self",
                   "tag": "Defend", "effects": [new_effect("block", 5, 3)]})
    bash = new_card("heavy_blow")
    bash.update({"name_ko": "강타", "name_en": "Heavy Blow", "rarity": "Basic", "cost": 2, "upgrade_cost": 2,
                 "effects": [new_effect("damage", 8, 2), new_effect("power", 2, 1, power="Vulnerable", target="enemy")]})
    slash = new_card("twin_slash")
    slash.update({"name_ko": "쌍베기", "name_en": "Twin Slash", "rarity": "Common",
                  "effects": [new_effect("damage", 5, 2, hits=2)]})
    focus = new_card("deep_breath")
    focus.update({"name_ko": "심호흡", "name_en": "Deep Breath", "type": "Skill", "rarity": "Common", "target": "Self",
                  "cost": 1, "upgrade_cost": 0, "effects": [new_effect("block", 6, 0), new_effect("draw", 1, 0)]})
    ember_heart = new_card("ember_heart")
    ember_heart.update({"name_ko": "불씨의 심장", "name_en": "Ember Heart", "type": "Power", "rarity": "Rare",
                        "target": "Self", "cost": 2, "upgrade_cost": 2,
                        "effects": [new_effect("power", 2, 1, power="Strength", target="self")]})
    # ---- 새 메커니즘 예시: '불씨' 디버프 ----
    ignite = new_card("ignite")
    ignite.update({"name_ko": "점화", "name_en": "Ignite", "type": "Skill", "rarity": "Common", "cost": 1,
                   "upgrade_cost": 1, "effects": [new_effect("power", 3, 2, power="c:ember", target="enemy")]})
    burst = new_card("flare_burst")
    burst.update({"name_ko": "불꽃 폭발", "name_en": "Flare Burst", "rarity": "Uncommon", "cost": 2, "upgrade_cost": 2,
                  "effects": [new_effect("damage", 6, 3, scale_power="c:ember", scale_per=2, scale_on="target"),
                              new_effect("remove_power", 0, 0, power="c:ember", target="enemy")]})
    stoke = new_card("stoke")
    stoke.update({"name_ko": "불길 돋우기", "name_en": "Stoke", "type": "Skill", "rarity": "Uncommon", "cost": 1,
                   "upgrade_cost": 0,
                   "effects": [new_effect("power", 2, 0, power="c:ember", target="enemy"),
                               new_effect("draw", 2, 0, cond_power="c:ember", cond_min=5, cond_on="target")]})
    stance = new_card("blazing_guard")
    stance.update({"name_ko": "타오르는 방패", "name_en": "Blazing Guard", "type": "Power", "rarity": "Rare",
                   "target": "Self", "cost": 1, "upgrade_cost": 1,
                   "effects": [new_effect("power", 2, 1, power="c:blazing_guard_buff", target="self")]})
    ember = new_power("ember")
    ember.update({"name_ko": "불씨", "name_en": "Ember", "type": "Debuff", "stack": "Counter", "trigger": "turn_start",
                  "decay": "tick",
                  "effects": [new_effect("lose_hp", 1, 0, per_stack=True)]})
    guard = new_power("blazing_guard_buff")
    guard.update({"name_ko": "타오르는 방패", "name_en": "Blazing Guard", "type": "Buff", "stack": "Counter",
                  "trigger": "damage_received", "decay": "none",
                  "effects": [new_effect("power", 1, 0, power="c:ember", target="other", per_stack=True)],
                  "modifiers": []})
    relic = new_relic("warm_ember")
    relic.update({"name_ko": "따뜻한 불씨", "name_en": "Warm Ember", "rarity": "Starter", "trigger": "combat_victory",
                  "effects": [new_effect("heal", 6, 0)],
                  "flavor_ko": "꺼지지 않는 작은 불꽃.", "flavor_en": "A small flame that never goes out."})
    potion = new_potion("fire_flask")
    potion.update({"name_ko": "화염 플라스크", "name_en": "Fire Flask",
                   "effects": [new_effect("damage", 20, 0), new_effect("power", 5, 0, power="c:ember", target="enemy")]})
    return {
        "generator": GENERATOR_VERSION,
        "mod": {
            "id": "MyMod", "name": "내 모드", "author": "Author",
            "description": "슬레이 더 스파이어 2 모드 메이커로 만든 모드", "version": "v0.1.0",
            "min_game_version": "0.107.0", "baselib_version": "*",
        },
        "character": {
            "enabled": True, "id": "hero",
            "name_ko": "영웅", "name_en": "Hero", "name_zh": "", "desc_zh": "",
            "desc_ko": "첨탑에 도전하는 새로운 영웅.", "desc_en": "A new hero who challenges the Spire.",
            "hp": 75, "color": "#e76f51", "placeholder": "ironclad",
            "card_h": 1.0, "card_s": 1.0, "card_v": 1.0,
            "deck": [{"card": "strike", "count": 5}, {"card": "defend", "count": 4}, {"card": "ignite", "count": 1}],
            "relics": ["warm_ember"],
            "icon_image": "", "select_image": "", "select_locked_image": "", "map_marker_image": "", "select_bg_image": "",
            "energy_icon_image": "", "energy_text_icon_image": "",
            "orb_slots": 0, "show_stars": False,
        },
        "cards": [strike, defend, bash, slash, focus, ember_heart, ignite, burst, stoke, stance],
        "relics": [relic],
        "potions": [potion],
        "powers": [ember, guard],
        "call_mappings": [],
    }


def expose_clone_play(card):
    clone = card.get("clone") or {}
    if clone.get("editable_play"):
        return
    if re.search(r"\b(?:protected|public)\s+override\s+(?:async\s+)?Task\s+OnPlay\s*\(", clone.get("body", "")):
        clone["editable_play"] = True
        card["effects"].insert(0, dict(new_effect("code"), original_effect=True,
                                       blocks=[{"op": "original_play", "args": {}}]))


def normalize(project):
    """오래된/부분 프로젝트 파일에 빠진 키를 기본값으로 채운다."""
    if not isinstance(project, dict):
        raise ValueError("프로젝트 JSON의 최상위 값은 객체여야 합니다.")
    base = default_project()
    for sec in ("mod", "character"):
        merged = copy.deepcopy(base[sec])
        merged.update(project.get(sec, {}))
        project[sec] = merged
    # 가져온 모드의 호출을 블록에 연결한 규칙은 프로젝트 안에 저장한다.
    if not isinstance(project.get("call_mappings"), list):
        project["call_mappings"] = []
    for key, factory in (("cards", new_card), ("relics", new_relic), ("potions", new_potion), ("powers", new_power)):
        items = []
        for it in project.get(key, []):
            d = factory(it.get("id", "x"))
            d.update(it)
            d["effects"] = [dict(new_effect(), **e) for e in d.get("effects", [])]
            if key == "powers":
                d["modifiers"] = [dict(new_modifier(), **m) for m in d.get("modifiers", [])]
            if key == "cards":
                expose_clone_play(d)
            items.append(d)
        project[key] = items
    gimmick.normalize(project)
    cardframe.normalize(project)
    project["generator"] = GENERATOR_VERSION
    return project


# ---------------------------------------------------------------------------
# 이름 변환
# ---------------------------------------------------------------------------
def pascal(snake: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in snake.split("_") if p)


def game_snake(name: str) -> str:
    """게임의 ID 규칙: 첫 글자를 뺀 모든 대문자 앞에 _ 를 넣고 전부 대문자 (실제 모드 791개 항목으로 확인)."""
    return re.sub(r"(?<!^)([A-Z])", r"_\1", name).upper()


def loc_id(project, snake: str) -> str:
    return f"{project['mod']['id'].upper()}-{game_snake(pascal(snake))}"


def power_loc_id(project, pid):
    return loc_id(project, pid + "_power")


# ---- 통째로 가져온 모드의 항목: 원래 클래스 이름·네임스페이스를 그대로 쓴다 ----
KIND_KEY = {"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}
KIND_NS = {"card": "Cards", "relic": "Relics", "potion": "Potions", "power": "Powers"}


def keep_name(item):
    cl = (item or {}).get("clone") or {}
    return cl.get("class_name", "") if cl.get("keep_name") else ""


def find_item(project, kind, iid):
    return next((x for x in project.get(KIND_KEY[kind], []) if x.get("id") == iid), None)


def item_cls(project, kind, item):
    """항목 클래스의 전체 이름 (global::…). item 은 dict 또는 id."""
    if isinstance(item, str):
        item = find_item(project, kind, item) or {"id": item}
    kn = keep_name(item)
    if kn:
        ns = item["clone"].get("namespace") or ""
        return "global::" + (f"{ns}.{kn}" if ns else kn)
    mid = project["mod"]["id"]
    return f"global::{mid}.{mid}Code.{KIND_NS[kind]}.{pascal(item['id'])}" + ("Power" if kind == "power" else "")


def item_loc_id(project, kind, item):
    kn = keep_name(item)
    if kn:
        return item["clone"].get("orig_loc_id") or f"{project['mod']['id'].upper()}-{game_snake(kn)}"
    return power_loc_id(project, item["id"]) if kind == "power" else loc_id(project, item["id"])


def takeover(project):
    """통째로 가져온 모드 정보 (없으면 None)."""
    t = project.get("takeover")
    return t if isinstance(t, dict) and t.get("src") else None


def takeover_loc(project, lang):
    """원래 모드의 번역 표 (사본). lang: en/ko/zh"""
    t = takeover(project)
    if not t or not t.get("loc") or not os.path.isfile(t["loc"]):
        return None
    try:
        with open(t["loc"], encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return copy.deepcopy(data.get(lang) or {})


def img_stem(kind, item):
    """그림 파일 이름 (확장자 빼고). 게임은 Id.Entry 에서 접두어를 뺀 소문자로 찾는다."""
    kn = keep_name(item)
    if kn:
        lid = item["clone"].get("orig_loc_id") or ""
        return (lid.split("-", 1)[1] if "-" in lid else game_snake(kn)).lower()
    return item["id"] + ("_power" if kind == "power" else "")


def _has_jong(word: str) -> bool:
    for ch in reversed(word):
        if "가" <= ch <= "힣":
            return (ord(ch) - 0xAC00) % 28 != 0
        if ch.isalnum():
            return ch in "013678LMNlmn"
    return False


def josa(word, a, b):
    """받침 있으면 a(을/이/은), 없으면 b(를/가/는)."""
    return a if _has_jong(word) else b


def power_meta(project, key):
    """파워 키(기본 'Strength' / 커스텀 'c:ember') -> 정보 dict. 없으면 None."""
    if not key:
        return None
    if key.startswith("game:"):
        entry = key[5:]
        item = project["character"].get("game_powers", {}).get(entry)
        if item and re.fullmatch(r"[A-Z][A-Z0-9_]*", entry):
            cls = pascal(entry.lower())
            return {"cls": "global::MegaCrit.Sts2.Core.Models.Powers." + cls, "var": cls,
                    **{lang: text(item, "name", lang) for lang in ("ko", "en", "zh")}, "target": "enemy"}
        return None
    if key.startswith("c:"):
        pid = key[2:]
        for p in project.get("powers", []):
            if p["id"] == pid:
                full = item_cls(project, "power", p)
                cls = full.rsplit(".", 1)[-1].replace("global::", "")
                return {"cls": full, "var": cls,
                        "ko": text(p, "name", "ko"), "en": text(p, "name", "en"), "zh": text(p, "name", "zh"),
                        "target": "self" if p.get("type") == "Buff" else "enemy"}
        return None
    if key.startswith("t:"):
        cls_name = key[2:]
        for power in (project.get("takeover") or {}).get("extra_powers", []):
            if power.get("class") == cls_name and power.get("full"):
                full = power["full"]
                if not full.startswith("global::"):
                    full = "global::" + full
                return {"cls": full, "var": cls_name, "ko": power.get("name_ko") or cls_name,
                        "en": power.get("name_en") or cls_name, "zh": power.get("name_zh") or cls_name,
                        "target": "self" if power.get("type") == "Buff" else "enemy"}
        return None
    if key in POWERS:
        cls, ko, en, tgt = POWERS[key]
        return {"cls": f"global::MegaCrit.Sts2.Core.Models.Powers.{cls}", "var": cls, "ko": ko, "en": en, "target": tgt}
    if key.startswith("s:"):
        sm = gimmick.find_summon(project, key[2:])
        if not sm:
            return None
        return {"cls": gimmick.summon_cls(project, sm["id"]), "var": gimmick._pascal(sm["id"]) + "SummonPower",
                "ko": text(sm, "name", "ko"), "en": text(sm, "name", "en"), "zh": text(sm, "name", "zh"), "target": "self", "summon": True}
    if key.startswith("x:"):
        _x, dep_id, cname = (key.split(":", 2) + ["", ""])[:3]
        for d in project.get("dependencies", []):
            if d.get("id") != dep_id:
                continue
            for pw in d.get("powers", []):
                if pw.get("class") == cname:
                    return {"cls": "global::" + pw["full"], "var": cname, "ko": pw.get("name_ko") or cname,
                            "en": pw.get("name_en") or cname, "target": "self" if pw.get("type") == "Buff" else "enemy",
                            "dep": dep_id}
        return None
    return None


def power_options(project):
    opts = [(k, f"{v[1]} ({k})") for k, v in POWERS.items()]
    opts += [("game:" + k, "원작 · " + text(v, "name", "ko")) for k, v in project["character"].get("game_powers", {}).items()]
    opts += [("c:" + p["id"], f"★ {p.get('name_ko') or p['id']} (새 파워)") for p in project.get("powers", [])]
    opts += [("t:" + p["class"], f"◆ {p.get('name_ko') or p['class']} (가져온 파워)")
             for p in (project.get("takeover") or {}).get("extra_powers", [])]
    opts += [("s:" + sm["id"], f"☆ {sm.get('name_ko') or sm['id']} (소환수 · 수치 = 단계)") for sm in gimmick.summons(project)]
    for d in project.get("dependencies", []):
        for pw in d.get("powers", []):
            opts.append((f"x:{d['id']}:{pw['class']}", f"◆ {pw.get('name_ko') or pw['class']} ({d.get('name') or d['id']})"))
    return opts


def text(item, field, lang):
    """언어별 텍스트. 비어 있으면 다른 언어로 대체."""
    v = (item.get(f"{field}_{lang}") or "").strip()
    if v:
        return v
    if lang == "zh":
        if field == "name":
            return (item.get("name_en") or "").strip() or item.get("id", "")
        return text(item, field, "ko")
    other = "en" if lang == "ko" else "ko"
    return (item.get(f"{field}_{other}") or "").strip()


# ---------------------------------------------------------------------------
# 설명문 자동 생성
# ---------------------------------------------------------------------------
def character_description(character, lang):
    if lang == "zh" and not (character.get("desc_zh") or "").strip():
        return text(character, "desc", "en")
    return text(character, "desc", lang)


def _enemy_scope(owner_kind, item):
    """적 대상 효과가 누구에게 가는지: single / all / random"""
    if owner_kind == "card":
        return {"AnyEnemy": "single", "AllEnemies": "all", "RandomEnemy": "random"}.get(item["target"], "single")
    if owner_kind == "potion":
        return "all" if item["target"] == "AllEnemies" else "single"
    return item.get("enemy_mode", "all")


def _value_text(project, e, owner_kind, var, lang, energy=False):
    a = int(e.get("amount", 0) or 0)
    if owner_kind == "power":
        if e.get("per_stack"):
            v = "[blue]{Amount}[/blue]" + (f"×{a}" if a != 1 else "")
        else:
            v = f"[blue]{a}[/blue]"
    elif e["kind"] == "remove_power":
        v = f"[blue]{a}[/blue]"
    elif energy:
        v = "{%s:energyIcons()}" % var
    elif owner_kind == "card":
        v = "{%s:%s()}" % (var, "inverseDiff" if e["kind"] == "lose_hp" else "diff")
    else:
        v = "[blue]{%s}[/blue]" % var
    if e.get("_xmult"):
        v = e["_xmult"] if a == 1 and not int(e.get("upgrade", 0) or 0) else f"{v}×{_x_paren(e['_xmult'])}"
    sm = power_meta(project, e.get("scale_power"))
    if sm and int(e.get("scale_per", 0) or 0):
        k = int(e["scale_per"])
        on_self = e.get("scale_on", "self") == "self"
        if lang == "zh":
            from card_zh import power_name
            who = "你" if on_self else "目标"
            v += f"（{who}每有1层[gold]{power_name(project, e['scale_power'])}[/gold]，数值增加{k}）"
        elif lang == "ko":
            v += f" (+{'' if on_self else '대상의 '}[gold]{sm['ko']}[/gold] 1당 {k})"
        else:
            v += f" (+{k} per [gold]{sm['en']}[/gold]{'' if on_self else ' on the target'})"
    return v


def _other_phrase(item, lang):
    t = item.get("trigger")
    if lang == "ko":
        return {"card_played": "카드의 대상에게 ", "damage_received": "공격자에게 ",
                "damage_given": "피해를 받은 대상에게 "}.get(t, "")
    return {"card_played": " to the card's target", "damage_received": " to the attacker",
            "damage_given": " to the damaged enemy"}.get(t, "")


def effect_sentence(project, eff, owner_kind, item, lang):
    xu = x_use(eff, owner_kind, item)
    if not xu:
        return _effect_sentence(project, eff, owner_kind, item, lang)
    xt = x_text(item)
    if xu == "mult":
        return _effect_sentence(project, dict(eff, _xmult=xt), owner_kind, item, lang)
    hits = max(1, int(eff.get("hits", 1) or 1))
    if eff["kind"] == "damage":
        s = _effect_sentence(project, dict(eff, hits=7777), owner_kind, item, lang)
        return s.replace("7777", xt if hits == 1 else f"{_x_paren(xt)}×{hits}")
    s = _effect_sentence(project, eff, owner_kind, item, lang)
    if not s:
        return s
    return {"ko": f"{xt}번 반복: ", "zh": f"重复{xt}次："}.get(lang, f"{xt} times: ") + s


def _effect_sentence(project, eff, owner_kind, item, lang):
    k = eff["kind"]
    if k == "code":
        s = (eff.get(f"text_{lang}") or "").strip()
        if not s and eff.get("blocks"):
            import blockcode
            s = blockcode.describe(eff["blocks"], project, owner_kind, lang)
        if not s:
            s = (eff.get("text_ko") or eff.get("text_en") or "").strip()
        return _with_condition(project, eff, owner_kind, s, lang) if s else ""
    scope = _enemy_scope(owner_kind, item)
    tgt = eff.get("target", "enemy")
    hits = max(1, int(eff.get("hits", 1) or 1))
    V = lambda var, energy=False: _value_text(project, eff, owner_kind, var, lang, energy)  # noqa: E731
    pm = power_meta(project, eff.get("power")) if k in ("power", "remove_power") else None
    if lang == "zh":
        from card_zh import effect
        s = effect(project, eff, scope, V, pm, owner_kind, item)
    elif lang == "ko":
        pre = {"all": "모든 적에게 ", "random": "무작위 적에게 ", "single": ""}[scope]
        if tgt == "other":
            pre = _other_phrase(item, lang)
        s = ""
        if k == "damage":
            s = f"{pre}피해를 {V('Damage')}씩 {hits}번 줍니다." if hits > 1 else f"{pre}피해를 {V('Damage')} 줍니다."
        elif k == "block":
            s = f"[gold]방어도[/gold]를 {V('Block')} 얻습니다."
        elif k == "draw":
            s = f"카드를 {V('Cards')}장 뽑습니다."
        elif k == "energy":
            s = f"에너지를 {V('Energy')} 얻습니다." if owner_kind == "power" else f"{V('Energy', True)}를 얻습니다."
        elif k == "heal":
            s = f"체력을 {V('Heal')} 회복합니다."
        elif k == "lose_hp":
            s = f"체력을 {V('HpLoss')} 잃습니다."
        elif k == "max_hp":
            s = f"최대 체력이 {V('MaxHp')} 증가합니다."
        elif k == "gold":
            s = f"골드를 {V('Gold')} 얻습니다."
        elif k == "power" and pm:
            name = f"[gold]{pm['ko']}[/gold]{josa(pm['ko'], '을', '를')}"
            s = f"{name} {V(pm['var'])} 얻습니다." if tgt == "self" else f"{pre}{name} {V(pm['var'])} 부여합니다."
        elif k == "remove_power" and pm:
            amt = "모두" if int(eff.get("amount", 0) or 0) == 0 else V("")
            if tgt == "self":
                s = f"[gold]{pm['ko']}[/gold]{josa(pm['ko'], '을', '를')} {amt} 잃습니다."
            else:
                whom = {"all": "모든 적의 ", "random": "무작위 적의 ", "single": "대상의 "}[scope]
                if tgt == "other":
                    whom = _other_phrase(item, lang).replace("에게 ", "의 ")
                s = f"{whom}[gold]{pm['ko']}[/gold]{josa(pm['ko'], '을', '를')} {amt} 제거합니다."
    else:
        post = {"all": " to ALL enemies", "random": " to a random enemy", "single": ""}[scope]
        if tgt == "other":
            post = _other_phrase(item, lang)
        s = ""
        if k == "damage":
            s = f"Deal {V('Damage')} damage{post}{f' {hits} times' if hits > 1 else ''}."
        elif k == "block":
            s = f"Gain {V('Block')} [gold]Block[/gold]."
        elif k == "draw":
            s = f"Draw {V('Cards')} {'{Cards:plural:card|cards}' if owner_kind != 'power' else 'card(s)'}."
        elif k == "energy":
            s = f"Gain {V('Energy')} Energy." if owner_kind == "power" else f"Gain {V('Energy', True)}."
        elif k == "heal":
            s = f"Heal {V('Heal')} HP."
        elif k == "lose_hp":
            s = f"Lose {V('HpLoss')} HP."
        elif k == "max_hp":
            s = f"Raise your Max HP by {V('MaxHp')}."
        elif k == "gold":
            s = f"Gain {V('Gold')} [gold]Gold[/gold]."
        elif k == "power" and pm:
            s = f"Gain {V(pm['var'])} [gold]{pm['en']}[/gold]." if tgt == "self" else \
                f"Apply {V(pm['var'])} [gold]{pm['en']}[/gold]{post}."
        elif k == "remove_power" and pm:
            amt = "all" if int(eff.get("amount", 0) or 0) == 0 else V("")
            if tgt == "self":
                s = f"Lose {amt} [gold]{pm['en']}[/gold]."
            else:
                frm = {"all": " from ALL enemies", "random": " from a random enemy", "single": " from the target"}[scope]
                if tgt == "other":
                    frm = _other_phrase(item, lang).replace(" to ", " from ")
                s = f"Remove {amt} [gold]{pm['en']}[/gold]{frm}."
    return _with_condition(project, eff, owner_kind, s, lang) if s else ""


def _with_condition(project, eff, owner_kind, s, lang):
    cm = power_meta(project, eff.get("cond_power"))
    if not cm:
        return s
    n = int(eff.get("cond_min", 1) or 1)
    on_self = eff.get("cond_on", "self") == "self"
    if lang == "zh":
        from card_zh import power_name
        return f"若{'你' if on_self else '目标'}有至少{n}层[gold]{power_name(project, eff['cond_power'])}[/gold]，{s}"
    if lang == "ko":
        who = "자신" if on_self else ("상대" if owner_kind == "power" else "대상")
        return f"{who}의 [gold]{cm['ko']}[/gold]{josa(cm['ko'], '이', '가')} {n} 이상이면 {s}"
    who = "you have" if on_self else "the target has"
    return f"If {who} {n} or more [gold]{cm['en']}[/gold], {s[:1].lower() + s[1:]}"


def _relic_prefix(relic, lang, project=None):
    project = project or {"gimmicks": {}}
    t = relic["trigger"]
    if lang == "zh":
        from card_zh import trigger_text
        return trigger_text(project, relic, "relic")
    if lang == "ko":
        if t == "card_played":
            n = int(relic.get("played_every", 1) or 1)
            what = gimmick.filter_word(project, relic["played_filter"], "ko")
            return f"{what}를 사용할 때마다 " if n <= 1 else f"{what}를 {n}장 사용할 때마다 "
        return {"first_turn": "전투 시작 시 ", "turn_start": "매 턴 시작 시 ", "turn_end": "턴 종료 시 ",
                "combat_victory": "전투 종료 시 ", "pickup": "획득 시 "}[t]
    if t == "card_played":
        n = int(relic.get("played_every", 1) or 1)
        f = relic["played_filter"]
        if n <= 1:
            return f"Whenever you play {gimmick.filter_word(project, f, 'en')}, "
        return f"Every time you play {n} {gimmick.filter_word(project, f, 'en', plural=True)}, "
    return {"first_turn": "At the start of each combat, ", "turn_start": "At the start of your turn, ",
            "turn_end": "At the end of your turn, ", "combat_victory": "At the end of combat, ",
            "pickup": "Upon pickup, "}[t]


def _power_prefix(power, lang, project=None):
    project = project or {"gimmicks": {}}
    t = power["trigger"]
    f = power.get("played_filter", "Any")
    if lang == "zh":
        from card_zh import trigger_text
        return trigger_text(project, power, "power")
    if lang == "ko":
        if t == "card_played":
            what = gimmick.filter_word(project, f, "ko")
            who = "플레이어가 " if power.get("played_by") == "any" else ""
            return f"{who}{what}를 사용할 때마다 "
        return {"none": "", "turn_start": "턴 시작 시 ", "turn_end": "턴 종료 시 ",
                "damage_received": "공격 피해를 받을 때마다 ", "damage_given": "공격으로 피해를 줄 때마다 "}[t]
    if t == "card_played":
        what = gimmick.filter_word(project, f, "en")
        who = "a player plays" if power.get("played_by") == "any" else "you play"
        return f"Whenever {who} {what}, "
    return {"none": "", "turn_start": "At the start of the turn, ", "turn_end": "At the end of the turn, ",
            "damage_received": "Whenever attacked, ", "damage_given": "Whenever this deals attack damage, "}[t]


def modifier_sentence(m, lang, project=None):
    project = project or {"gimmicks": {}}
    k = int(m.get("value", 0) or 0)
    kind = m["kind"]
    f = m.get("filter") or "Any"
    if lang == "zh":
        from card_zh import modifier
        return modifier(project, m)
    if kind == "keep_block":
        return "턴이 끝나도 [gold]방어도[/gold]가 사라지지 않습니다." if lang == "ko" else "[gold]Block[/gold] is not removed at the end of the turn."
    if kind in gimmick.MOD_SENTENCE_KINDS:
        return gimmick.modifier_sentence(project, m, lang)
    if kind == "cost_add":
        vv = "[blue]{Amount}[/blue]" + (f"×{abs(k)}" if abs(k) != 1 else "") if m.get("per_stack") else f"[blue]{abs(k)}[/blue]"
        if lang == "ko":
            return f"{gimmick.filter_word(project, f, 'ko')}의 비용이 {vv} {'감소' if k < 0 else '증가'}합니다."
        return f"{gimmick.filter_word(project, f, 'en', plural=True)[:1].upper()}{gimmick.filter_word(project, f, 'en', plural=True)[1:]} cost {vv} {'less' if k < 0 else 'more'}."
    if kind in ("dmg_dealt_add", "dmg_dealt_pct") and f != "Any":
        base = modifier_sentence(dict(m, filter="Any"), lang, project)
        return (f"{gimmick.filter_word(project, f, 'ko')}로 " + base) if lang == "ko" else \
            base.replace("Attacks deal", f"{gimmick.filter_word(project, f, 'en', plural=True).capitalize()} deal")
    if m.get("per_stack"):
        v = "[blue]{Amount}[/blue]" + (f"×{abs(k)}" if abs(k) != 1 else "")
    else:
        v = f"[blue]{abs(k)}[/blue]"
    neg = k < 0
    kind = m["kind"]
    if lang == "ko":
        up = "감소합니다" if neg else "증가합니다"
        return {
            "dmg_dealt_add": f"주는 공격 피해가 {v} {up}.",
            "dmg_dealt_pct": f"주는 공격 피해가 {v}% {up}.",
            "dmg_taken_add": f"받는 공격 피해가 {v} {up}.",
            "dmg_taken_pct": f"받는 공격 피해가 {v}% {up}.",
            "block_add": f"카드로 얻는 [gold]방어도[/gold]가 {v} {up}.",
            "hand_draw": f"턴 시작 시 카드를 {v}장 {'덜' if neg else '더'} 뽑습니다.",
            "max_energy": f"최대 에너지가 {v} {up}.",
        }[kind]
    more = "less" if neg else "more"
    return {
        "dmg_dealt_add": f"Attacks deal {v} {'less' if neg else 'additional'} damage.",
        "dmg_dealt_pct": f"Attacks deal {v}% {more} damage.",
        "dmg_taken_add": f"Takes {v} {'less' if neg else 'additional'} damage from attacks.",
        "dmg_taken_pct": f"Takes {v}% {more} damage from attacks.",
        "block_add": f"Gain {v} {'less' if neg else 'additional'} [gold]Block[/gold] from cards.",
        "hand_draw": f"Draw {v} {'fewer' if neg else 'additional'} card(s) at the start of the turn.",
        "max_energy": f"Max Energy {'decreased' if neg else 'increased'} by {v}.",
    }[kind]


def auto_description(project, item, owner_kind, lang):
    sentences = [effect_sentence(project, e, owner_kind, item, lang) for e in item.get("effects", [])]
    sentences = [s for s in sentences if s]
    if owner_kind in ("relic", "power"):
        prefix = _relic_prefix(item, lang, project) if owner_kind == "relic" else _power_prefix(item, lang, project)
        if owner_kind == "power" and item.get("trigger") == "none":
            sentences = []
        out = []
        if sentences:
            if lang == "en" and prefix:
                sentences[0] = sentences[0][:1].lower() + sentences[0][1:]
            out.append(prefix + " ".join(sentences))
        elif owner_kind == "relic":
            out.append(prefix.strip())
        if owner_kind == "power":
            out += [modifier_sentence(m, lang, project) for m in item.get("modifiers", [])]
            gt = gimmick.power_text(project, item, lang)
            if gt:
                out.append(gt)
            d = item.get("decay", "none")
            if d == "tick":
                out.append("턴 종료 시 1 감소합니다." if lang == "ko" else "回合结束时减少1层。" if lang == "zh" else "Decreases by 1 at the end of the turn.")
            elif d == "remove":
                out.append("턴 종료 시 사라집니다." if lang == "ko" else "回合结束时移除此效果。" if lang == "zh" else "Removed at the end of the turn.")
            elif d == "remove_start":
                out.append("내 턴 시작 시 사라집니다." if lang == "ko" else "你的回合开始时移除此效果。" if lang == "zh" else "Removed at the start of your turn.")
        return " ".join(out)
    if owner_kind == "card":
        pre = gimmick.card_prefix_text(project, item, lang)
        if pre:
            sentences = [pre] + sentences
    sep = "\n" if owner_kind == "card" else " "
    return sep.join(sentences)


def description(project, item, owner_kind, lang):
    if item.get("raw_desc_only") or item.get("clone"):
        base = text(item, "desc", lang)
        extra = [effect_sentence(project, e, owner_kind, item, lang) for e in item.get("effects", [])]
        extra = [x for x in extra if x]
        return "\n".join([base] + extra) if base and extra else (base or "\n".join(extra))
    custom = (item.get(f"desc_{lang}") or "").strip()
    if custom:
        return custom
    return auto_description(project, item, owner_kind, lang)


# ---------------------------------------------------------------------------
# 검증
# ---------------------------------------------------------------------------
def _power_refs(e):
    refs = []
    if e["kind"] in ("power", "remove_power"):
        refs.append(e.get("power"))
    for f in ("cond_power", "scale_power"):
        if e.get(f):
            refs.append(e[f])
    return refs


def validate(project):
    errors, warnings = [], []
    mod = project["mod"]
    if not MODID_RE.match(mod["id"] or ""):
        errors.append("모드 ID는 영문 대문자로 시작하고 영문/숫자만 쓸 수 있습니다 (예: MyMod).")
    if mod["id"] in ("BaseLib", "Godot", "System", "MegaCrit"):
        errors.append(f"모드 ID '{mod['id']}'는 쓸 수 없습니다.")
    if not re.match(r"^v?\d+\.\d+\.\d+$", mod.get("version", "")):
        warnings.append("버전은 v0.1.0 같은 형식을 권장합니다.")

    reserved = {mod["id"], mod["id"] + "Card", mod["id"] + "Relic", mod["id"] + "Potion", mod["id"] + "Power",
                "MainFile"}
    seen = {}
    ch = project["character"]
    if ch["enabled"]:
        if not ID_RE.match(ch["id"] or ""):
            errors.append("캐릭터 ID는 영문 소문자와 _ 만 쓸 수 있습니다 (예: fire_mage).")
        else:
            seen[ch["id"]] = "캐릭터"
            reserved |= {pascal(ch["id"]) + s for s in ("CardPool", "RelicPool", "PotionPool")}
        if not HEX_RE.match(ch.get("color", "")):
            errors.append("캐릭터 색상은 #RRGGBB 형식이어야 합니다.")
        try:
            if int(ch["hp"]) <= 0:
                errors.append("캐릭터 체력은 1 이상이어야 합니다.")
        except (TypeError, ValueError):
            errors.append("캐릭터 체력은 숫자여야 합니다.")

    for key, kname in (("cards", "카드"), ("relics", "유물"), ("potions", "물약"), ("powers", "파워")):
        owner_kind = key[:-1]
        for it in project.get(key, []):
            iid = it.get("id", "")
            where = f"{kname} '{iid or '(이름 없음)'}'"
            if not ID_RE.match(iid):
                errors.append(f"{where}: ID는 영문 소문자와 _ 만 쓸 수 있습니다 (예: fire_ball).")
                continue
            if iid in seen:
                errors.append(f"{where}: ID가 {seen[iid]} ID와 겹칩니다.")
            seen[iid] = kname
            if pascal(iid) in reserved:
                errors.append(f"{where}: 예약된 이름과 겹칩니다. 다른 ID를 쓰세요.")
            if not text(it, "name", "ko"):
                errors.append(f"{where}: 이름이 비어 있습니다.")
            if owner_kind == "card" and it.get("pool_character") and not card_pool_for_character(project, it["pool_character"]):
                errors.append(f"{where}: 캐릭터 전용 카드의 원래 카드 풀을 찾을 수 없습니다 ({it['pool_character']}).")
            effs = it.get("effects", [])
            gimmicky = owner_kind == "power" and (int(it.get("cap") or 0) or int(it.get("threshold") or 0)
                                                  or it.get("group") or it.get("hidden"))
            if not effs and not it.get("modifiers") and not (it.get("desc_ko") or it.get("desc_en")) \
                    and not it.get("extra_code") and not gimmicky and not it.get("clone"):
                warnings.append(f"{where}: 효과가 없습니다.")
            kinds = []
            for e in effs:
                if e["kind"] in ("power", "remove_power"):
                    kinds.append(f"{e['kind']}:{e['power']}")
                elif e["kind"] != "code":
                    kinds.append(e["kind"])
            dup = {k for k in kinds if kinds.count(k) > 1}
            if dup and owner_kind != "power":
                errors.append(f"{where}: 같은 종류의 효과를 두 번 넣을 수 없습니다 ({', '.join(sorted(dup))}). "
                              "피해는 '타격 횟수'를 쓰세요.")
            for e in effs:
                try:
                    if int(e["amount"]) < 0 or int(e.get("upgrade", 0)) < -99 or int(e.get("hits", 1)) < 1:
                        raise ValueError
                    int(e.get("cond_min", 1))
                    int(e.get("scale_per", 0))
                except (TypeError, ValueError):
                    errors.append(f"{where}: 효과 수치가 올바르지 않습니다.")
                for ref in _power_refs(e):
                    if not power_meta(project, ref):
                        errors.append(f"{where}: 없는 파워를 참조합니다 ({ref}).")
                if e["kind"] == "code" and e.get("blocks"):
                    import blockcode
                    _l, berr = blockcode.compile_blocks(e["blocks"], project, _Ctx(owner_kind, it))
                    for be in dict.fromkeys(berr):
                        errors.append(f"{where}: 블록 코드 - {be}")
                elif e["kind"] == "code" and not (e.get("code") or "").strip():
                    errors.append(f"{where}: '직접 코드' 효과에 코드가 비어 있습니다.")
                elif e["kind"] == "code" and not (e.get("text_ko") or e.get("text_en")):
                    warnings.append(f"{where}: '직접 코드' 효과의 설명 문구가 비어 있습니다.")
                if e.get("target") == "other" and (owner_kind != "power" or it.get("trigger") not in POWER_OTHER):
                    errors.append(f"{where}: '상대' 대상은 파워의 카드 사용/피해 받을 때/피해 줄 때 발동에서만 쓸 수 있습니다.")
                needs_target = (e.get("cond_power") and e.get("cond_on") == "target") or \
                               (e.get("scale_power") and e.get("scale_on") == "target")
                if needs_target:
                    ok = (owner_kind == "card" and it.get("target") == "AnyEnemy") or \
                         (owner_kind == "potion" and it.get("target") == "AnyEnemy") or \
                         (owner_kind == "power" and it.get("trigger") in POWER_OTHER)
                    if not ok:
                        errors.append(f"{where}: '대상의 파워' 조건/비례는 대상이 '적 하나'인 카드·물약, "
                                      "또는 상대가 있는 파워 발동에서만 쓸 수 있습니다.")
                if e.get("per_stack") and owner_kind != "power":
                    e["per_stack"] = False
            enemy_effects = [e for e in effs if (e["kind"] == "damage" and e.get("target") != "other") or
                             (e["kind"] in ("power", "remove_power") and e["target"] == "enemy")]
            if key == "cards":
                if enemy_effects and it["target"] == "Self":
                    errors.append(f"{where}: 적에게 주는 효과가 있으면 대상을 '자신'으로 할 수 없습니다.")
                if any(e["kind"] == "damage" for e in effs) and it["type"] != "Attack":
                    warnings.append(f"{where}: 피해를 주는 카드는 보통 '공격' 타입입니다.")
                for fld in ("cost", "upgrade_cost"):
                    try:
                        c = int(it[fld])
                        if not 0 <= c <= 9:
                            raise ValueError
                    except (TypeError, ValueError):
                        errors.append(f"{where}: 비용은 0~9 사이 숫자여야 합니다.")
                if it["tag"] and it["rarity"] != "Basic":
                    warnings.append(f"{where}: 타격/수비 태그는 보통 기본 카드에 붙입니다.")
            if key == "potions" and enemy_effects and it["target"] == "Self":
                errors.append(f"{where}: 적에게 주는 효과가 있으면 대상을 '자신'으로 할 수 없습니다.")
            if key == "relics":
                if it["trigger"] in ("combat_victory", "pickup"):
                    bad = [EFFECT_LABEL[e["kind"]] for e in effs if e["kind"] not in OUT_OF_COMBAT_OK]
                    if bad:
                        errors.append(f"{where}: '{label_of(RELIC_TRIGGERS, it['trigger'])}' 발동에는 체력 회복/"
                                      f"최대 체력/골드만 쓸 수 있습니다 (문제: {', '.join(bad)}).")
                if it["trigger"] == "card_played":
                    try:
                        if int(it.get("played_every", 1)) < 1:
                            raise ValueError
                    except (TypeError, ValueError):
                        errors.append(f"{where}: '몇 장마다' 값은 1 이상이어야 합니다.")
            if key == "powers":
                if it["trigger"] == "none" and effs:
                    warnings.append(f"{where}: 발동 시점이 '없음'이라 효과 목록은 쓰이지 않습니다 (상시 효과만 적용).")
                for m in it.get("modifiers", []):
                    try:
                        int(m.get("value", 0))
                    except (TypeError, ValueError):
                        errors.append(f"{where}: 상시 효과 수치가 올바르지 않습니다.")
                if it["stack"] == "Single" and any(e.get("per_stack") for e in effs):
                    warnings.append(f"{where}: '단일' 파워는 스택이 1이라 '스택 비례'가 의미 없습니다.")
            img = it.get("image", "")
            if img and not os.path.isfile(img):
                warnings.append(f"{where}: 이미지 파일을 찾을 수 없습니다 ({img}). 임시 그림을 씁니다.")
            elif img and not img.lower().endswith(".png"):
                errors.append(f"{where}: 이미지는 PNG 파일이어야 합니다.")

    tk = project.get("takeover")
    if isinstance(tk, dict) and tk.get("src"):
        if not os.path.isdir(tk["src"]):
            errors.append(f"통째로 가져온 모드 '{tk.get('mod')}'의 원래 코드 폴더가 없습니다 ({tk['src']}). "
                          "'다른 모드' 탭에서 원래 모드를 다시 통째로 가져오세요.")
        ids = {k: {x["id"] for x in project.get(k, [])} for k in ("cards", "relics")}
        for ich in imported_characters(project):
            where = f"가져온 캐릭터 '{text(ich, 'name', 'ko') or ich['class']}'"
            for d in ich.get("deck", []):
                c = d.get("card", "")
                if not c.startswith(("raw:", "game:")) and c not in ids["cards"]:
                    errors.append(f"{where}: 시작 덱의 카드 '{c}' 가 없습니다.")
            for r in ich.get("relics", []):
                if not r.startswith(("raw:", "game:")) and r not in ids["relics"]:
                    errors.append(f"{where}: 시작 유물 '{r}' 가 없습니다.")
            if not ich.get("deck_fixed") and not any(int(d.get("count", 0) or 0) for d in ich.get("deck", [])):
                warnings.append(f"{where}: 시작 덱이 비어 있습니다.")
            for field in ICHAR_FILES:
                if ich.get(field) and not os.path.isfile(ich[field]):
                    warnings.append(f"{where}: 그림 파일이 없습니다 ({ich[field]}). 원래 그림을 씁니다.")
        if tk.get("mod") and tk["mod"] != project["mod"]["id"]:
            warnings.append(f"모드 ID 를 '{tk['mod']}' 에서 바꿨습니다. 원래 코드가 옛 ID 로 리소스를 찾으면 그림·번역이 안 보일 수 있습니다.")
    dep_ids = {d.get("id") for d in project.get("dependencies", [])}
    for d in project.get("dependencies", []):
        if not d.get("dll") or not os.path.isfile(d["dll"]):
            warnings.append(f"참조한 모드 '{d.get('id')}'의 dll 을 찾을 수 없습니다 ({d.get('dll')}). 빌드가 실패할 수 있습니다.")
    for key, kname in (("cards", "카드"), ("relics", "유물"), ("potions", "물약"), ("powers", "파워")):
        for it in project.get(key, []):
            cl = it.get("clone")
            where = f"{kname} '{it.get('id')}'"
            if cl:
                if cl.get("mod") not in dep_ids and not cl.get("keep_name") and not cl.get("game_original"):
                    errors.append(f"{where}: 복제한 원본 모드 '{cl.get('mod')}'가 참조 목록에 없습니다. '다른 모드' 탭에서 참조를 추가하세요.")
                names = [v.get("name") for v in it.get("raw_vars", [])]
                for e in it.get("effects", []):
                    vn = (power_meta(project, e.get("power")) or {}).get("var") if e["kind"] == "power" else VAR_NAME.get(e["kind"])
                    if vn and vn in names:
                        errors.append(f"{where}: 추가한 효과의 값 이름 '{vn}'이 원본 값과 겹칩니다. 원본 값 표에서 수치를 바꾸세요.")
                if key != "cards" and (it.get("effects") or it.get("modifiers")):
                    warnings.append(f"{where}: 복제한 유물·물약·파워에는 추가 효과가 적용되지 않습니다 (원본 동작만 유지).")
    ge, gw = gimmick.validate(project)
    errors += ge
    warnings += gw
    fe, fw = cardframe.validate(project)
    errors += fe
    warnings += fw
    for c in project.get("cards", []):
        if c.get("clone"):
            continue
        uses_x = any(e.get("x_use") in ("times", "mult") for e in c.get("effects", [])) or             '"energy_x"' in json.dumps(c.get("effects", []))
        if c.get("x_cost") and not uses_x:
            warnings.append(f"카드 '{c.get('id')}': X 비용인데 X 를 쓰는 효과가 없습니다 (효과의 'X 사용' 또는 블록 값 'X (쓴 에너지)').")
        rk = c.get("upgrade_remove_keyword")
        if rk and rk not in c.get("keywords", []):
            warnings.append(f"카드 '{c.get('id')}': 강화 시 제거할 키워드 '{rk}' 가 카드에 없어 무시됩니다.")
        if not c.get("x_cost") and any(e.get("x_use") for e in c.get("effects", [])):
            warnings.append(f"카드 '{c.get('id')}': X 비용이 아닌데 'X 사용' 효과가 있어 무시됩니다.")
    gseen = {t["id"] for t in gimmick.tags(project)} | {x["id"] for x in gimmick.summons(project)}
    for key, kname in (("cards", "카드"), ("powers", "파워")):
        for it in project.get(key, []):
            where = f"{kname} '{it.get('id')}'"
            if key == "cards":
                errors += gimmick.card_errors(project, it, where)
            else:
                errors += gimmick.power_errors(project, it, where)
    del gseen
    if ch["enabled"]:
        original = ch.get("game_cards", {})
        if not isinstance(original, dict) or any(not re.fullmatch(r"[A-Z][A-Z0-9_]*", key) for key in original):
            errors.append("캐릭터 원작 카드 목록에 잘못된 ID가 있습니다.")
            original = {}
        card_ids = {c["id"] for c in project["cards"]} | {"game:" + key for key in original}
        relic_ids = {r["id"] for r in project["relics"]} | {"game:" + k for k in ch.get("game_relics", {})}
        total = 0
        for d in ch["deck"]:
            if d["card"] not in card_ids:
                errors.append(f"시작 덱: 카드 '{d['card']}'가 없습니다.")
            total += int(d.get("count", 0) or 0)
        if total == 0:
            errors.append("시작 덱이 비어 있습니다.")
        for r in ch["relics"]:
            if r not in relic_ids:
                errors.append(f"시작 유물: '{r}'가 없습니다.")
        if not ch["relics"]:
            warnings.append("시작 유물이 없습니다.")
        if not any(c["rarity"] != "Basic" for c in project["cards"]):
            warnings.append("보상으로 나올 카드(일반/특별/희귀)가 하나도 없습니다.")
        for f in ("icon_image", "select_image", "select_locked_image", "map_marker_image", "energy_icon_image",
                  "energy_text_icon_image", "select_bg_image"):
            p = ch.get(f, "")
            if p and not os.path.isfile(p):
                warnings.append(f"캐릭터 이미지 파일을 찾을 수 없습니다: {p}")
        for i, txt in ((lang, ch.get(f"architect_{lang}") or "") for lang in ("ko", "en", "zh")):
            if txt.strip() and not architect_dialogues(txt):
                warnings.append(f"아키텍트 대사({i})를 읽지 못했습니다 — '아키텍트: …' / '나: …' 줄로 쓰세요. 기본 대사를 씁니다.")
    ids = {r["id"] for r in project.get("relics", [])}
    for r in project.get("relics", []):
        up = r.get("upgrade_relic") or ""
        if not up:
            continue
        where = f"유물 '{r.get('name_ko') or r['id']}'"
        if up == r["id"]:
            errors.append(f"{where}: 강화 버전으로 자기 자신을 고를 수 없습니다.")
        elif up not in ids:
            errors.append(f"{where}: 강화 버전 유물 '{up}' 이(가) 없습니다.")
        else:
            if r.get("rarity") != "Starter":
                warnings.append(f"{where}: 강화 버전은 시작 유물(희귀도 '시작')일 때만 고대의 존재가 바꿔 줍니다.")
            target = next(x for x in project["relics"] if x["id"] == up)
            if target.get("rarity") != "Starter":
                warnings.append(f"{where}: 강화 버전 '{target.get('name_ko') or up}' 의 희귀도가 '시작'이 아니라 "
                                "무작위 보상·상점에도 나올 수 있습니다.")
    return errors, warnings


# ---------------------------------------------------------------------------
# C# 코드 생성
# ---------------------------------------------------------------------------
def _num(v):
    return f"{int(v)}m"


def _canonical_vars(project, item, owner_kind):
    if owner_kind == "power":
        return []
    out = []
    prop = "ValueProp.Move" if owner_kind == "card" else "ValueProp.Unpowered"
    for e in item["effects"]:
        a = int(e["amount"])
        k = e["kind"]
        if k == "damage":
            out.append(f"new DamageVar({_num(a)}, {prop})")
        elif k == "block":
            out.append(f"new BlockVar({_num(a)}, {prop})")
        elif k == "draw":
            out.append(f"new CardsVar({a})")
        elif k == "energy":
            out.append(f"new EnergyVar({a})")
        elif k == "heal":
            out.append(f'new HealVar("Heal", {_num(a)})')
        elif k == "lose_hp":
            out.append(f'new HpLossVar("HpLoss", {_num(a)})')
        elif k == "max_hp":
            out.append(f'new MaxHpVar("MaxHp", {_num(a)})')
        elif k == "gold":
            out.append(f'new GoldVar("Gold", {a})')
        elif k == "power":
            pm = power_meta(project, e["power"])
            out.append(f'new PowerVar<{pm["cls"]}>("{pm["var"]}", {_num(a)})')
    return out


class _Ctx:
    """효과 코드를 만들 때 쓰는 이름들 (카드/유물/물약/파워마다 다름)."""

    def __init__(self, owner_kind, item):
        if owner_kind in ("summon", "button"):
            owner_kind = "power"
        self.kind = owner_kind
        self.item = item
        self.cc = "choiceContext"
        if owner_kind == "pet":
            # 동료(골골이형)의 행동: Owner 는 동료 생물, 주인은 Owner.PetOwner
            self.kind, self.me, self.player, self.src, self.play = "power", "Owner", "Owner.PetOwner", "null", "null"
            self.single = None
            self.other = "other"
            self.scope = "all"
            return
        if owner_kind == "orb":
            # 구체: Owner 는 플레이어
            self.me, self.player, self.src, self.play = "Owner.Creature", "Owner", "null", "null"
            self.single = None
            self.other = None
            self.scope = "all"
            return
        if owner_kind == "power":
            self.me = "Owner"
            self.player = "Owner.Player"
            self.src = "null"
            self.play = "null"
            self.single = None
            self.other = "other"
        else:
            self.me = "Owner.Creature"
            self.player = "Owner"
            self.src = "this" if owner_kind == "card" else "null"
            self.play = "cardPlay" if owner_kind == "card" else "null"
            self.single = {"card": "cardPlay.Target", "potion": "target"}.get(owner_kind)
            self.other = self.single
        self.scope = _enemy_scope(owner_kind, item)


def _amount_expr(project, e, C):
    a = int(e.get("amount", 0) or 0)
    if C.kind == "power":
        base = f"{a}m * Amount" if e.get("per_stack") else f"{a}m"
    elif e["kind"] in VAR_NAME:
        base = f'DynamicVars["{VAR_NAME[e["kind"]]}"].BaseValue'
    elif e["kind"] == "power":
        base = f'DynamicVars["{power_meta(project, e["power"])["var"]}"].BaseValue'
    else:
        base = f"{a}m"
    sm = power_meta(project, e.get("scale_power"))
    k = int(e.get("scale_per", 0) or 0)
    if sm and k:
        if e.get("scale_on", "self") == "self":
            amt = f"{C.me}.GetPowerAmount<{sm['cls']}>()"
        else:
            amt = f"({C.other}?.GetPowerAmount<{sm['cls']}>() ?? 0)"
        return f"({base} + {k}m * {amt})"
    return base


def _is_scaled(e):
    return bool(e.get("scale_power")) and int(e.get("scale_per", 0) or 0) != 0


def _targets_block(C, tgt, body_fn):
    """적/상대 대상에 대해 body_fn(대상식)을 실행하는 코드 줄."""
    L = []
    if tgt == "other":
        L.append(f"if ({C.other} != null)")
        L.append("{")
        L += ["    " + b for b in body_fn(C.other)]
        L.append("}")
        return L
    if C.kind == "power":
        if C.scope == "random":
            L += ["{", "    var randomEnemy = RandomOwnerEnemy();", "    if (randomEnemy != null)", "    {"]
            L += ["        " + b for b in body_fn("randomEnemy")]
            L += ["    }", "}"]
        else:
            L += ["foreach (var enemy in OwnerEnemies().ToList())", "{"]
            L += ["    " + b for b in body_fn("enemy")]
            L.append("}")
        return L
    if C.scope == "single":
        L += [f"if ({C.single} != null)", "{"]
        L += ["    " + b for b in body_fn(C.single)]
        L.append("}")
    elif C.scope == "random":
        L += ["{", f"    var randomEnemy = Owner.RunState.Rng.CombatTargets.NextItem({C.me}.CombatState!.HittableEnemies);",
              "    if (randomEnemy != null)", "    {"]
        L += ["        " + b for b in body_fn("randomEnemy")]
        L += ["    }", "}"]
    else:
        L += [f"foreach (var enemy in {C.me}.CombatState!.HittableEnemies.ToList())", "{"]
        L += ["    " + b for b in body_fn("enemy")]
        L.append("}")
    return L


def _effect_code(project, e, C, ind, idx):
    k = e["kind"]
    V = _amount_expr(project, e, C)
    hits = max(1, int(e.get("hits", 1) or 1))
    xu = x_use(e, C.kind, C.item)
    if xu == "mult":
        V = f"(({V}) * XCount)"
    xscaled = _is_scaled(e) or xu == "mult"
    hx = (f"XCount * {hits}" if hits > 1 else "XCount") if xu == "times" else str(hits)
    tgt = e.get("target", "enemy")
    cc, me = C.cc, C.me
    L = []

    def need_player(lines):
        if C.kind == "power":
            return [f"if ({C.player} != null)", "{"] + ["    " + x for x in lines] + ["}"]
        return lines

    if k == "damage":
        if C.kind == "card" and tgt != "other":
            if xscaled:
                L.append(f"await CommonActions.CardAttack(this, cardPlay, cardPlay.Target, {V}, ValueProp.Move, {hx}).Execute({cc});")
            else:
                L.append(f"await CommonActions.CardAttack(this, cardPlay, {hx}).Execute({cc});")
        else:
            def dmg(t):
                line = f"await CreatureCmd.Damage({cc}, {t}, {V}, ValueProp.Unpowered, {me}, null, null);"
                return [line] if hits == 1 else [f"for (var hit = 0; hit < {hits}; hit++)", "    " + line]
            L += _targets_block(C, tgt, dmg)
    elif k == "block":
        if C.kind == "card" and not xscaled:
            L.append(f"await CreatureCmd.GainBlock({me}, DynamicVars.Block, cardPlay);")
        elif C.kind == "card":
            L.append(f"await CreatureCmd.GainBlock({me}, {V}, ValueProp.Move, cardPlay);")
        else:
            L.append(f"await CreatureCmd.GainBlock({me}, {V}, ValueProp.Unpowered, null);")
    elif k == "draw":
        L += need_player([f"await CardPileCmd.Draw({cc}, {V}, {C.player});"])
    elif k == "energy":
        L += need_player([f"await PlayerCmd.GainEnergy({V}, {C.player});"])
    elif k == "gold":
        L += need_player([f"await PlayerCmd.GainGold({V}, {C.player});"])
    elif k == "heal":
        L.append(f"await CreatureCmd.Heal({me}, {V});")
    elif k == "lose_hp":
        L.append(f"await CreatureCmd.Damage({cc}, {me}, {V}, ValueProp.Unblockable | ValueProp.Unpowered, {me}, {C.src}, {C.play});")
    elif k == "max_hp":
        L.append(f"await CreatureCmd.GainMaxHp({me}, {V});")
    elif k == "power":
        cls = power_meta(project, e["power"])["cls"]
        if tgt == "self":
            L.append(f"await CommonActions.Apply<{cls}>({cc}, {me}, {C.src}, {V});")
        else:
            L += _targets_block(C, tgt, lambda t: [f"await CommonActions.Apply<{cls}>({cc}, {t}, {C.src}, {V});"])
    elif k == "remove_power":
        cls = power_meta(project, e["power"])["cls"]
        all_ = int(e.get("amount", 0) or 0) == 0

        def rm(t):
            out = [f"var pw{idx} = {t}.GetPower<{cls}>();"]
            if all_:
                out.append(f"if (pw{idx} != null) await PowerCmd.Remove(pw{idx});")
            else:
                out.append(f"if (pw{idx} != null) await PowerCmd.ModifyAmount({cc}, pw{idx}, -{V}, {me}, {C.src});")
            return out
        if tgt == "self":
            L += ["{"] + ["    " + x for x in rm(me)] + ["}"]
        else:
            L += _targets_block(C, tgt, rm)
    elif k == "code" and e.get("blocks"):
        import blockcode
        lines, _errs = blockcode.compile_blocks(e["blocks"], project, C, "", prefix=_prog_prefix(C, idx),
                                                extras=_EXTRAS_SINK.get("x"))
        L += lines
    elif k == "code":
        L.append("// --- 직접 입력한 코드 ---")
        L += (e.get("code") or "").replace("\r\n", "\n").split("\n")
        L.append("// --- 끝 ---")

    if xu == "times" and not (k == "damage" and C.kind == "card" and tgt != "other"):
        L = ["for (var xi = 0; xi < XCount; xi++)", "{"] + ["    " + x for x in L] + ["}"]
    cm = power_meta(project, e.get("cond_power"))
    if cm:
        n = int(e.get("cond_min", 1) or 1)
        if e.get("cond_on", "self") == "self":
            cond = f"{me}.GetPowerAmount<{cm['cls']}>() >= {n}"
        else:
            cond = f"({C.other}?.GetPowerAmount<{cm['cls']}>() ?? 0) >= {n}"
        L = [f"if ({cond})", "{"] + ["    " + x for x in L] + ["}"]
    return [ind + x if x.strip() else "" for x in L]


_EXTRAS_SINK = {}   # generate() 중에만 {"x": [...]} — 블록이 만든 클래스(선택지 카드·예약 파워)


def _prog_prefix(C, idx):
    kind = {"card": "Card", "relic": "Relic", "potion": "Potion", "power": "Pow"}.get(C.kind, "Blk")
    return f"{pascal((C.item or {}).get('id') or 'x')}{kind}E{gimmick.letters(idx).lower()}"


def _filter_check(project, f, card_expr):
    """카드 필터가 맞지 않으면 return 하는 C# 한 줄 (아무 카드면 None)."""
    if not f or f == "Any":
        return None
    return f"        if (!({gimmick.filter_expr(project, f, card_expr)})) return;"


def _hover_tips(project, item):
    seen = []
    for e in item.get("effects", []):
        for ref in _power_refs(e):
            pm = power_meta(project, ref)
            if pm and pm["cls"] not in seen:
                seen.append(pm["cls"])
    return [f"HoverTipFactory.FromPower<{c}>()" for c in seen]


def _extra_code(item, ind="    "):
    code = (item.get("extra_code") or "").replace("\r\n", "\n").strip("\n")
    if not code.strip():
        return []
    return ["", ind + "// --- 직접 추가한 코드 ---"] + [ind + x if x.strip() else "" for x in code.split("\n")] + \
           [ind + "// --- 끝 ---"]


USINGS_COMMON = """using BaseLib.Utils;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Commands;
using MegaCrit.Sts2.Core.Entities.Cards;
using MegaCrit.Sts2.Core.Entities.Creatures;
using MegaCrit.Sts2.Core.Entities.Players;
using MegaCrit.Sts2.Core.Entities.Powers;
using MegaCrit.Sts2.Core.GameActions.Multiplayer;
using MegaCrit.Sts2.Core.HoverTips;
using MegaCrit.Sts2.Core.Localization.DynamicVars;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.ValueProps;
"""


def _header():
    return f"// 이 파일은 StS2 모드 메이커 {GENERATOR_VERSION}가 생성했습니다. 다시 생성하면 덮어씁니다.\n"


def _effects_body(project, item, C, ind="        "):
    L = []
    for i, e in enumerate(item["effects"]):
        L += _effect_code(project, e, C, ind, i)
    return L


def _num_lit(value, suffix):
    v = float(value or 0)
    if suffix in ("m", "M"):
        return (str(int(v)) if v.is_integer() else repr(v)) + "m"
    if suffix in ("f", "F"):
        return repr(v) + "f"
    if suffix in ("d", "D"):
        return repr(v) + "d"
    return str(int(v)) if v.is_integer() else repr(v)


def _raw_var_exprs(item):
    out = []
    for v in item.get("raw_vars", []) or []:
        expr = v.get("expr") or ""
        if "{VALUE}" in expr:
            expr = expr.replace("{VALUE}", _num_lit(v.get("value"), v.get("suffix", "m")))
        if expr:
            out.append(expr)
    return out


def _pool_type(project, kind, which, their_pool=""):
    mid = project["mod"]["id"]
    if which == "theirs" and their_pool:
        return "global::" + their_pool
    ch = project["character"]
    if ch["enabled"]:
        return f"global::{mid}.{mid}Code.Character.{pascal(ch['id'])}" + {"card": "CardPool", "relic": "RelicPool",
                                                                          "potion": "PotionPool"}[kind]
    return {"card": "global::MegaCrit.Sts2.Core.Models.CardPools.ColorlessCardPool",
            "relic": "global::MegaCrit.Sts2.Core.Models.RelicPools.SharedRelicPool",
            "potion": "global::MegaCrit.Sts2.Core.Models.PotionPools.SharedPotionPool"}[kind]


def _clone_head(project, item, ns_sub):
    cl = item["clone"]
    mid = project["mod"]["id"]
    usings = [u for u in cl.get("usings", []) if u.strip() and u.strip() not in USINGS_COMMON]
    ns = cl.get("namespace", "")
    parts = ns.split(".") if ns else []
    extra = [f"using {'.'.join(parts[:i])};" for i in range(len(parts), 0, -1)]
    lines = [_header(), USINGS_COMMON.rstrip("\n"), "using BaseLib.Utils;", "using BaseLib.Extensions;"]
    if not keep_name(item):      # 원래 이름 그대로면 원본의 확장 메서드와 겹치지 않게 내 것은 전체 이름으로 부른다
        lines.append(f"using {mid}.{mid}Code.Extensions;")
    for u in usings + extra:
        if u not in lines:
            lines.append(u)
    if keep_name(item):
        return lines + (["", f"namespace {ns};", ""] if ns else [""])
    return lines + ["", f"namespace {mid}.{mid}Code.{ns_sub};", ""]


def _img_path(project, item, method, suffix=""):
    """그림 경로 식. 원래 이름 그대로인 항목은 확장 메서드 대신 전체 이름으로 (원본 코드의 같은 이름 메서드와 겹침 방지)."""
    arg = f'$"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}{suffix}.png"'
    if keep_name(item):
        mid = project["mod"]["id"]
        return f"global::{mid}.{mid}Code.Extensions.StringExtensions.{method}({arg})"
    return f"{arg}.{method}()"


def _fix_upgrade(body, item, cost_delta, add_kw):
    """원본 OnUpgrade 를 살리면서 수치·비용·키워드만 바꾼다."""
    vals = {v["name"]: v for v in item.get("raw_vars", []) or []}
    acc = {"Damage", "Block", "Cards", "Energy", "Heal", "HpLoss", "MaxHp", "Gold", "Repeat"}
    seen = set()

    def r1(m):
        name = m.group(1) or m.group(2)
        seen.add(name)
        v = vals.get(name)
        if v is None:
            return m.group(0)
        return m.group(0)[:m.start(3) - m.start(0)] + _num_lit(v.get("upgrade"), "m") + m.group(0)[m.end(3) - m.start(0):]
    body = re.sub(r'DynamicVars\s*(?:\[\s*"(\w+)"\s*\]|\.(\w+))\s*\.UpgradeValueBy\(\s*(-?[\d.]+[mMfF]?)\s*\)', r1, body)
    body = re.sub(r"\s*EnergyCost\.UpgradeBy\(\s*-?\d+\s*\)\s*;", "", body)
    body = re.sub(r"\s*AddKeyword\(\s*CardKeyword\.\w+\s*\)\s*;", "", body)
    add = []
    for name, v in vals.items():
        if name not in seen and float(v.get("upgrade") or 0):
            add.append(f'DynamicVars["{name}"].UpgradeValueBy({_num_lit(v.get("upgrade"), "m")});')
    if cost_delta:
        add.append(f"EnergyCost.UpgradeBy({cost_delta});")
    if add_kw:
        add.append(f"AddKeyword(CardKeyword.{add_kw});")
    if not body.strip():
        body = "protected override void OnUpgrade()\n{\n}"
    body = body.expandtabs(4)
    k = body.rfind("}")
    ls = body.rfind("\n", 0, k) + 1          # 닫는 괄호가 있는 줄의 시작
    ind = body[ls:k] if body[ls:k].strip() == "" else ""
    return body[:ls] + "".join(f"{ind}    {a}\n" for a in add) + body[ls:]


def _indent(text, ind="    "):
    """원본(디컴파일) 코드의 탭·들여쓰기를 정리해서 한 단계 들여쓴다."""
    import textwrap
    t = textwrap.dedent(text.replace("\r\n", "\n").expandtabs(4)).strip("\n")
    t = re.sub(r"\n[ \t]*\n(?:[ \t]*\n)+", "\n\n", t)
    return [ind + ln if ln.strip() else "" for ln in t.split("\n")]


def canonical_keyword_terms(project, item):
    terms = ["CardKeyword." + k for k in item.get("keywords", [])]
    for tag_id in item.get("gtags", []):
        tag = gimmick.find_tag(project, tag_id) or {}
        member = tag.get("keyword_member", "")
        if re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+", member):
            terms.append("global::" + member)
    return list(dict.fromkeys(terms))


def gen_clone(project, item, kind):
    mid = project["mod"]["id"]
    cl = item["clone"]
    cls = keep_name(item) or (pascal(item["id"]) + ("Power" if kind == "power" else ""))
    ns_sub = {"card": "Cards", "relic": "Relics", "potion": "Potions", "power": "Powers"}[kind]
    our_base = {"card": f"{mid}Card", "relic": f"{mid}Relic", "potion": f"{mid}Potion", "power": f"{mid}Power"}[kind]
    if keep_name(item):     # 원래 네임스페이스에 있으므로 내 기본 클래스는 전체 이름으로
        our_base = f"global::{mid}.{mid}Code.{ns_sub}.{our_base}"
    base = ("global::" + cl["base"]) if cl.get("base") else our_base
    L = _clone_head(project, item, ns_sub)
    body = cl.get("body", "")
    if kind != "power":
        assigned_pool = card_pool_for_character(project, item.get("pool_character")) if kind == "card" else ""
        pool = assigned_pool or _pool_type(project, kind, cl.get("pool", "mine"), cl.get("their_pool", ""))
        if cl.get("base") or cl.get("pool") == "theirs" or assigned_pool:
            L.append(f"[Pool(typeof({pool}))]")
    L += [f"public sealed class {cls} : {base}", "{"]
    rv = _raw_var_exprs(item)
    if kind == "card":
        effs = item.get("effects", [])
        args = list(cl.get("ctor_args") or []) if cl.get("base") else []
        new_args = [str(int(item["cost"])), f"CardType.{item['type']}", f"CardRarity.{item['rarity']}",
                    f"TargetType.{item['target']}"]
        if args:
            out, used = [], set()
            for a in args:
                if re.match(r"^-?\d+$", a.strip()) and "cost" not in used:
                    out.append(new_args[0]); used.add("cost")
                elif "CardType." in a and "type" not in used:
                    out.append(new_args[1]); used.add("type")
                elif "CardRarity." in a and "rarity" not in used:
                    out.append(new_args[2]); used.add("rarity")
                elif "TargetType." in a and "target" not in used:
                    out.append(new_args[3]); used.add("target")
                else:
                    out.append(a)
            args = out
        else:
            args = new_args
        L += [f"    public {cls}() : base({', '.join(args)})", "    {", "    }", ""]
        if cl.get("base"):
            L += [f'    public override string CustomPortraitPath => {_img_path(project, item, "BigCardImagePath", "")};',
                  f'    public override string PortraitPath => {_img_path(project, item, "CardImagePath", "")};',
                  f'    public override string BetaPortraitPath => {_img_path(project, item, "CardImagePath", "")};']
        if item.get("tag"):
            L.append(f"    protected override HashSet<CardTag> CanonicalTags => [CardTag.{item['tag']}];")
        keywords = canonical_keyword_terms(project, item)
        if keywords:
            L.append(f"    public override IEnumerable<CardKeyword> CanonicalKeywords => [{', '.join(keywords)}];")
        cv = rv + _canonical_vars(project, item, "card")
        L.append(f"    protected override IEnumerable<DynamicVar> CanonicalVars => [{', '.join(cv)}];")
        if any(e["kind"] == "block" for e in effs) and "GainsBlock" not in body:
            L.append("    public override bool GainsBlock => true;")
        tips = gimmick.card_tips(project, item) + _hover_tips(project, item)
        if tips and "ExtraHoverTips" not in body:
            L.append(f"    protected override IEnumerable<IHoverTip> ExtraHoverTips => [{', '.join(tips)}];")
        cost_delta = int(item.get("upgrade_cost", item["cost"])) - int(item["cost"])
        add_kw = item.get("upgrade_add_keyword") if item.get("upgrade_add_keyword") not in item.get("keywords", []) else ""
        L += [""] + _indent(_fix_upgrade(cl.get("upgrade_body", ""), item, cost_delta, add_kw))
        if effs or cl.get("editable_play"):
            has_play = re.search(r"\bOnPlay\s*\(", body)
            if has_play:
                body = re.sub(r"(?:protected|public)\s+override\s+(async\s+)?Task\s+OnPlay\s*\(",
                              lambda m: f"private {m.group(1) or ''}Task OriginalOnPlay(", body, count=1)
            C = _Ctx("card", item)
            L += ["", "    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)", "    {"]
            if has_play and not cl.get("editable_play"):
                L.append("        await OriginalOnPlay(choiceContext, cardPlay);")
            L += _effects_body(project, item, C)
            L.append("    }")
    elif kind == "relic":
        L.append(f"    public override RelicRarity Rarity => RelicRarity.{item['rarity']};")
        if not cl.get("base") and "GetUpgradeReplacement" not in body:     # 내 기본 클래스(CustomRelicModel)를 이어받을 때만
            L += relic_upgrade_lines(project, item)
        if cl.get("base"):
            L += [f'    public override string PackedIconPath => {_img_path(project, item, "RelicImagePath", "")};',
                  f'    protected override string PackedIconOutlinePath => {_img_path(project, item, "RelicOutlineImagePath", "_outline")};',
                  f'    protected override string BigIconPath => {_img_path(project, item, "BigRelicImagePath", "")};']
        if rv:
            L.append(f"    protected override IEnumerable<DynamicVar> CanonicalVars => [{', '.join(rv)}];")
    elif kind == "potion":
        L.append(f"    public override PotionRarity Rarity => PotionRarity.{item['rarity']};")
        if "Usage" not in body:
            L.append("    public override PotionUsage Usage => PotionUsage.CombatOnly;")
        L.append(f"    public override TargetType TargetType => TargetType.{item['target']};")
        if cl.get("base"):
            L += [f'    public override string? CustomPackedImagePath => {_img_path(project, item, "PotionImagePath", "")};',
                  f'    public override string? CustomPackedOutlinePath => {_img_path(project, item, "PotionOutlineImagePath", "")};']
        if rv:
            L.append(f"    protected override IEnumerable<DynamicVar> CanonicalVars => [{', '.join(rv)}];")
    elif kind == "power":
        L += [f"    public override PowerType Type => PowerType.{item['type']};",
              f"    public override PowerStackType StackType => PowerStackType.{item['stack']};"]
        if cl.get("base"):
            L += [f'    public override string? CustomPackedIconPath => {_img_path(project, item, "PowerImagePath", "")};',
                  f'    public override string? CustomBigIconPath => {_img_path(project, item, "BigPowerImagePath", "")};']
        if rv:
            L.append(f"    protected override IEnumerable<DynamicVar> CanonicalVars => [{', '.join(rv)}];")
    L += ["", f"    // ---- 원본 '{cl.get('orig_class', '')}' ({cl.get('mod', '')}) 에서 가져온 코드 ----"]
    L += _indent(body.strip("\n"))
    L += _extra_code(item)
    L.append("}")
    return "\n".join(L) + "\n"


CARD_EVENTS = {"draw":"AfterCardDrawn", "discard":"AfterCardDiscarded", "exhaust":"AfterCardExhausted"}

def gen_card(project, card):
    if card.get("clone"):
        return gen_clone(project, card, "card")
    mid = project["mod"]["id"]
    cls = pascal(card["id"])
    effs = card["effects"]
    C = _Ctx("card", card)
    pool = card_pool_for_character(project, card.get("pool_character"))
    lines = [_header(), USINGS_COMMON, f"namespace {mid}.{mid}Code.Cards;", ""]
    if pool:
        lines.append(f"[Pool(typeof({pool}))]")
    lines += [f"public sealed class {cls}() : {mid}Card({0 if card.get('x_cost') else int(card['cost'])}, CardType.{card['type']}, "
              f"CardRarity.{card['rarity']}, TargetType.{card['target']})", "{"]
    if card["tag"]:
        lines.append(f"    protected override HashSet<CardTag> CanonicalTags => [CardTag.{card['tag']}];")
    keywords = canonical_keyword_terms(project, card)
    if keywords:
        kws = ", ".join(keywords)
        lines.append(f"    public override IEnumerable<CardKeyword> CanonicalKeywords => [{kws}];")
    if any(e["kind"] == "block" for e in effs):
        lines.append("    public override bool GainsBlock => true;")
    cv = _canonical_vars(project, card, "card")
    lines.append(f"    protected override IEnumerable<DynamicVar> CanonicalVars => [{', '.join(cv)}];")
    tips = gimmick.card_tips(project, card) + _hover_tips(project, card)
    rm = gimmick._res_meta(project, card)
    if rm and f"HoverTipFactory.FromPower<{rm['cls']}>()" not in tips:
        tips.append(f"HoverTipFactory.FromPower<{rm['cls']}>()")
    if tips:
        lines.append(f"    protected override IEnumerable<IHoverTip> ExtraHoverTips => [{', '.join(tips)}];")
    lines += gimmick.card_members(project, card)
    if card.get("x_cost"):
        lines += ["    protected override bool HasEnergyCostX => true;",
                  "    // X = 이 카드에 쓴 에너지 (화학 X 같은 효과 포함)" + (", 강화하면 +1" if card.get("x_plus_up") else ""),
                  "    private int XCount => ResolveEnergyXValue()" + (" + (IsUpgraded ? 1 : 0)" if card.get("x_plus_up") else "") + ";"]
    lines += ["", "    protected override async Task OnPlay(PlayerChoiceContext choiceContext, CardPlay cardPlay)", "    {"]
    lines += gimmick.card_play_prefix(project, card)
    lines += _effects_body(project, card, C)
    if not effs:
        lines.append("        await Task.CompletedTask;")
    lines += ["    }", "", "    protected override void OnUpgrade()", "    {"]
    for e in effs:
        u = int(e.get("upgrade", 0) or 0)
        if not u:
            continue
        if e["kind"] in VAR_NAME:
            lines.append(f'        DynamicVars["{VAR_NAME[e["kind"]]}"].UpgradeValueBy({u}m);')
        elif e["kind"] == "power":
            lines.append(f'        DynamicVars["{power_meta(project, e["power"])["var"]}"].UpgradeValueBy({u}m);')
    dc = 0 if card.get("x_cost") else int(card["upgrade_cost"]) - int(card["cost"])
    if dc:
        lines.append(f"        EnergyCost.UpgradeBy({dc});")
    lines += gimmick.card_upgrade_lines(card)
    if card.get("upgrade_add_keyword") and card["upgrade_add_keyword"] not in card["keywords"]:
        lines.append(f"        AddKeyword(CardKeyword.{card['upgrade_add_keyword']});")
    if card.get("upgrade_remove_keyword") and card["upgrade_remove_keyword"] in card["keywords"]:
        lines.append(f"        RemoveKeyword(CardKeyword.{card['upgrade_remove_keyword']});")
    lines.append("    }")
    import blockcode
    for event, method in CARD_EVENTS.items():
        blocks = card.get("event_blocks", {}).get(event)
        if not blocks:
            continue
        ctx = _Ctx("card", card)
        ctx.single = ctx.other = None
        ctx.play = "null"
        statements, errors = blockcode.compile_blocks(blocks, project, ctx, prefix=pascal(card["id"])+event)
        if errors:
            raise ValueError(f"{card['id']} {event}: " + ", ".join(errors))
        flag = "" if event == "discard" else ", bool flag"
        lines.extend([f"    public override async Task {method}(PlayerChoiceContext choiceContext, CardModel card{flag})",
                      "    {", "        if (card != this) return;", *statements, "    }"])
    lines += _extra_code(card)
    lines.append("}")
    return "\n".join(lines) + "\n"


def relic_upgrade_lines(project, relic):
    """고대의 존재 '오로바스의 손길' 등이 시작 유물을 바꿀 강화 버전 (BaseLib StarterUpgradePatches 가 읽음)."""
    up = relic.get("upgrade_relic") or ""
    if not up or up == relic.get("id") or not any(r["id"] == up for r in project.get("relics", [])):
        return []
    return [f"    public override RelicModel? GetUpgradeReplacement() => ModelDb.Relic<{item_cls(project, 'relic', up)}>();"]


def gen_relic(project, relic):
    if relic.get("clone"):
        return gen_clone(project, relic, "relic")
    mid = project["mod"]["id"]
    cls = pascal(relic["id"])
    t = relic["trigger"]
    C = _Ctx("relic", relic)
    usings = USINGS_COMMON + "using MegaCrit.Sts2.Core.Entities.Relics;\nusing MegaCrit.Sts2.Core.Rooms;\n"
    L = [_header(), usings, f"namespace {mid}.{mid}Code.Relics;", "",
         f"public sealed class {cls} : {mid}Relic", "{",
         f"    public override RelicRarity Rarity => RelicRarity.{relic['rarity']};"]
    L += relic_upgrade_lines(project, relic)
    cv = _canonical_vars(project, relic, "relic")
    if cv:
        L.append(f"    protected override IEnumerable<DynamicVar> CanonicalVars => [{', '.join(cv)}];")
    tips = _hover_tips(project, relic)
    if tips:
        L.append(f"    protected override IEnumerable<IHoverTip> ExtraHoverTips => [{', '.join(tips)}];")
    L.append("")

    def body(own_ctx=True):
        out = [] if own_ctx else ["        var choiceContext = new ThrowingPlayerChoiceContext();"]
        out.append("        Flash();")
        return out + _effects_body(project, relic, C)

    if t in ("first_turn", "turn_start"):
        L += ["    private int _turn;", "", "    public override Task BeforeCombatStart()", "    {",
              "        _turn = 0;", "        return Task.CompletedTask;", "    }", "",
              "    public override async Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)",
              "    {", "        if (player != Owner) return;", "        _turn++;"]
        if t == "first_turn":
            L.append("        if (_turn != 1) return;")
        L += body() + ["    }"]
    elif t == "turn_end":
        L += ["    public override async Task BeforeSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)",
              "    {", "        if (side != CombatSide.Player || !participants.Contains(Owner.Creature)) return;"]
        L += body() + ["    }"]
    elif t == "card_played":
        n = max(1, int(relic.get("played_every", 1) or 1))
        f = relic.get("played_filter", "Any")
        if n > 1:
            L += ["    private int _count;", "", "    public override Task BeforeCombatStart()", "    {",
                  "        _count = 0;", "        return Task.CompletedTask;", "    }", ""]
        L += ["    public override async Task AfterCardPlayed(PlayerChoiceContext choiceContext, CardPlay cardPlay)",
              "    {", "        if (cardPlay.Card.Owner != Owner) return;"]
        fc = _filter_check(project, f, "cardPlay.Card")
        if fc:
            L.append(fc)
        if n > 1:
            L += [f"        if (++_count < {n}) return;", "        _count = 0;"]
        L += body() + ["    }"]
    elif t == "combat_victory":
        L += ["    public override async Task AfterCombatVictory(CombatRoom room)", "    {"] + body(False) + ["    }"]
    elif t == "pickup":
        L += ["    public override async Task AfterObtained()", "    {"] + body(False) + ["    }"]
    import fxbtn
    L += fxbtn.relic_members(project, relic)
    L += _extra_code(relic)
    L.append("}")
    return "\n".join(L) + "\n"


def gen_potion(project, potion):
    if potion.get("clone"):
        return gen_clone(project, potion, "potion")
    mid = project["mod"]["id"]
    cls = pascal(potion["id"])
    effs = potion["effects"]
    C = _Ctx("potion", potion)
    usings = USINGS_COMMON + "using MegaCrit.Sts2.Core.Entities.Potions;\n"
    L = [_header(), usings, f"namespace {mid}.{mid}Code.Potions;", "",
         f"public sealed class {cls} : {mid}Potion", "{",
         f"    public override PotionRarity Rarity => PotionRarity.{potion['rarity']};",
         "    public override PotionUsage Usage => PotionUsage.CombatOnly;",
         f"    public override TargetType TargetType => TargetType.{potion['target']};"]
    cv = _canonical_vars(project, potion, "potion")
    if cv:
        L.append(f"    protected override IEnumerable<DynamicVar> CanonicalVars => [{', '.join(cv)}];")
    tips = _hover_tips(project, potion)
    if tips:
        L.append(f"    public override IEnumerable<IHoverTip> ExtraHoverTips => [{', '.join(tips)}];")
    L += ["", "    protected override async Task OnUse(PlayerChoiceContext choiceContext, Creature? target)", "    {"]
    L += _effects_body(project, potion, C)
    if not effs:
        L.append("        await Task.CompletedTask;")
    L.append("    }")
    L += _extra_code(potion)
    L.append("}")
    return "\n".join(L) + "\n"


def _mod_value(m):
    v = int(m.get("value", 0) or 0)
    return f"{v}m * Amount" if m.get("per_stack") else f"{v}m"


def gen_power(project, power):
    if power.get("clone"):
        return gen_clone(project, power, "power")
    mid = project["mod"]["id"]
    cls = pascal(power["id"]) + "Power"
    t = power["trigger"]
    C = _Ctx("power", power)
    L = [_header(), USINGS_COMMON, f"namespace {mid}.{mid}Code.Powers;", "",
         f"public sealed class {cls} : {mid}Power", "{",
         f"    public override PowerType Type => PowerType.{power['type']};",
         f"    public override PowerStackType StackType => PowerStackType.{power['stack']};"]
    tips = _hover_tips(project, power)
    tips = [x for x in tips if f".{cls}>" not in x]
    if tips:
        L.append(f"    protected override IEnumerable<IHoverTip> ExtraHoverTips => [{', '.join(tips)}];")
    effs = power["effects"] if t != "none" else []

    def trigger_body():
        out = ["    private async Task Trigger(PlayerChoiceContext choiceContext, Creature? other)", "    {",
               "        Flash();"]
        out += _effects_body(project, power, C)
        out.append("    }")
        return out

    if effs:
        L.append("")
        if t == "turn_start":
            L += ["    public override async Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)",
                  "    {", "        if (player.Creature != Owner) return;",
                  "        await Trigger(choiceContext, null);"] + (
                  ["        if (Owner.Powers.Contains(this)) await PowerCmd.Remove(this);"]
                  if power.get("decay") == "remove_start" else []) + ["    }", "",
                  "    public override async Task AfterSideTurnStart(CombatSide side, IReadOnlyList<Creature> participants, ICombatState combatState)",
                  "    {", "        // 적이 가진 파워는 적의 턴 시작에 발동",
                  "        if (Owner.IsPlayer || side != Owner.Side || Owner.IsDead) return;",
                  "        await Trigger(new ThrowingPlayerChoiceContext(), null);", "    }"]
        elif t == "turn_end":
            L += ["    public override async Task BeforeSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)",
                  "    {", "        if (side != Owner.Side || Owner.IsDead) return;",
                  "        await Trigger(choiceContext, null);", "    }"]
        elif t == "card_played":
            L += ["    public override async Task AfterCardPlayed(PlayerChoiceContext choiceContext, CardPlay cardPlay)",
                  "    {", "        if (Owner.IsDead) return;"]
            if power.get("played_by", "owner") == "owner":
                L.append("        if (cardPlay.Card.Owner?.Creature != Owner) return;")
            fc = _filter_check(project, power.get("played_filter", "Any"), "cardPlay.Card")
            if fc:
                L.append(fc)
            L += ["        await Trigger(choiceContext, cardPlay.Target);", "    }"]
        elif t == "damage_received":
            L += ["    public override async Task AfterDamageReceived(PlayerChoiceContext choiceContext, Creature target, DamageResult result, ValueProp props, Creature? dealer, CardModel? cardSource)",
                  "    {",
                  "        if (target != Owner || dealer == null || dealer == Owner || !props.HasFlag(ValueProp.Move)) return;",
                  "        await Trigger(choiceContext, dealer);", "    }"]
        elif t == "damage_given":
            L += ["    public override async Task AfterDamageGiven(PlayerChoiceContext choiceContext, Creature? dealer, DamageResult result, ValueProp props, Creature target, CardModel? cardSource)",
                  "    {",
                  "        if (dealer != Owner || target == Owner || !props.HasFlag(ValueProp.Move)) return;",
                  "        await Trigger(choiceContext, target);", "    }"]
        L.append("")
        L += trigger_body()

    mods = power.get("modifiers", [])
    move = "props.HasFlag(ValueProp.Move) && !props.HasFlag(ValueProp.Unpowered)"
    add_lines, mul_lines = [], []
    for m in mods:
        v = _mod_value(m)
        mf = m.get("filter") or "Any"
        if m["kind"] in ("dmg_dealt_add", "dmg_dealt_pct") and mf != "Any":
            fx = f"cardSource != null && {gimmick.filter_expr(project, mf, 'cardSource')}"
            if m["kind"] == "dmg_dealt_add":
                add_lines.append(f"        if (dealer == Owner && {move} && {fx}) r += {v};")
            else:
                mul_lines.append(f"        if (dealer == Owner && {move} && {fx}) r *= 1m + ({v}) / 100m;")
            continue
        if m["kind"] == "osty_dmg":
            add_lines.append(f"        if (dealer != null && Owner.Player != null && dealer == Owner.Player.Osty && {move}) r += {v};")
            continue
        if m["kind"] == "pet_dmg":
            import pets as PT
            pc = f" && dealer.Monster is {PT.pet_cls(project, m['ref'])}" if m.get("ref") and PT.find_pet(project, m["ref"]) else ""
            add_lines.append(f"        if (dealer != null && dealer.PetOwner != null && dealer.PetOwner.Creature == Owner{pc} && {move}) r += {v};")
            continue
        if m["kind"] == "dmg_dealt_add":
            add_lines.append(f"        if (dealer == Owner && {move}) r += {v};")
        elif m["kind"] == "dmg_taken_add":
            add_lines.append(f"        if (target == Owner && {move}) r += {v};")
        elif m["kind"] == "dmg_dealt_pct":
            mul_lines.append(f"        if (dealer == Owner && {move}) r *= 1m + ({v}) / 100m;")
        elif m["kind"] == "dmg_taken_pct":
            mul_lines.append(f"        if (target == Owner && {move}) r *= 1m + ({v}) / 100m;")
    sig = "(Creature? target, decimal amount, ValueProp props, Creature? dealer, CardModel? cardSource, CardPlay? cardPlay)"
    if add_lines:
        L += ["", f"    public override decimal ModifyDamageAdditive{sig}", "    {", "        var r = 0m;"] + add_lines + \
             ["        return r;", "    }"]
    if mul_lines:
        L += ["", f"    public override decimal ModifyDamageMultiplicative{sig}", "    {", "        var r = 1m;"] + mul_lines + \
             ["        return r;", "    }"]
    blk = [m for m in mods if m["kind"] == "block_add"]
    if blk:
        L += ["", "    public override decimal ModifyBlockAdditive(Creature target, decimal block, ValueProp props, CardModel? cardSource, CardPlay? cardPlay)",
              "    {", f"        if (target != Owner || !props.HasFlag(ValueProp.Move)) return 0m;",
              f"        return {' + '.join(_mod_value(m) for m in blk)};", "    }"]
    hd = [m for m in mods if m["kind"] == "hand_draw"]
    if hd:
        L += ["", "    public override decimal ModifyHandDraw(Player player, decimal count)", "    {",
              f"        return player.Creature == Owner ? count + {' + '.join(_mod_value(m) for m in hd)} : count;", "    }"]
    me_ = [m for m in mods if m["kind"] == "max_energy"]
    if me_:
        L += ["", "    public override decimal ModifyMaxEnergy(Player player, decimal amount)", "    {",
              f"        return player.Creature == Owner ? amount + {' + '.join(_mod_value(m) for m in me_)} : amount;", "    }"]

    ca = [m for m in mods if m["kind"] == "cost_add"]
    if ca:
        L += ["", "    public override bool TryModifyEnergyCostInCombat(CardModel card, decimal originalCost, out decimal modifiedCost)",
              "    {", "        var d_ = 0m;"]
        for m in ca:
            L.append(f"        if (card.Owner?.Creature == Owner && {gimmick.filter_expr(project, m.get('filter') or 'Any', 'card')}) d_ += {_mod_value(m)};")
        L += ["        modifiedCost = Math.Max(0m, originalCost + d_);", "        return d_ != 0m;", "    }"]
    if any(m["kind"] == "keep_block" for m in mods):
        L += ["", "    public override bool ShouldClearBlock(Creature creature) => creature != Owner;"]
    L += gimmick.modifier_members(project, power)
    L += gimmick.power_members(project, power, C, _EXTRAS_SINK.get("x"))
    d = power.get("decay", "none")
    if d == "remove_start" and t != "turn_start" or (d == "remove_start" and not effs):
        L += ["", "    public override async Task AfterPlayerTurnStart(PlayerChoiceContext choiceContext, Player player)",
              "    {", "        if (player.Creature != Owner) return;", "        await PowerCmd.Remove(this);", "    }"]
    if d in ("tick", "remove"):
        L += ["", "    public override async Task AfterSideTurnEnd(PlayerChoiceContext choiceContext, CombatSide side, IEnumerable<Creature> participants)",
              "    {", "        if (side != Owner.Side) return;",
              "        await PowerCmd.TickDownDuration(this);" if d == "tick" else "        await PowerCmd.Remove(this);",
              "    }"]
    L += _extra_code(power)
    L.append("}")
    return "\n".join(L) + "\n"


def game_card_expression(entry):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", entry):
        raise ValueError(f"잘못된 원작 카드 ID: {entry}")
    return f'global::MegaCrit.Sts2.Core.Models.ModelDb.GetById<global::MegaCrit.Sts2.Core.Models.CardModel>(new global::MegaCrit.Sts2.Core.Models.ModelId("CARD", "{entry}"))'


def gen_character(project):
    mid = project["mod"]["id"]
    ch = project["character"]
    cls = pascal(ch["id"])
    color = ch["color"].lstrip("#").lower()
    deck = []
    for d in ch["deck"]:
        for _ in range(int(d.get("count", 0) or 0)):
            if d["card"].startswith("game:"):
                deck.append("        " + game_card_expression(d["card"][5:]))
            else:
                deck.append(f"        ModelDb.Card<{item_cls(project, 'card', d['card'])}>()")
    relics = [("        " + game_item_expression("Relic", r[5:])) if r.startswith("game:") else f"        ModelDb.Relic<{item_cls(project, 'relic', r)}>()" for r in ch["relics"]]
    L = [_header(), """using BaseLib.Abstracts;
using BaseLib.Utils.NodeFactories;
using Godot;
using MegaCrit.Sts2.Core.Entities.Characters;
using MegaCrit.Sts2.Core.Models;
""", f"using {mid}.{mid}Code.Extensions;", "", f"namespace {mid}.{mid}Code.Character;", "",
         f"public class {cls} : PlaceholderCharacterModel", "{",
         f'    public const string CharacterId = "{cls}";',
         f'    public static readonly Color Color = new("{color}");', "",
         f'    // 전투/상점/휴식 애니메이션 등 아직 직접 만들지 않은 에셋은 이 캐릭터의 것을 빌려 씁니다.',
         f'    public override string PlaceholderID => "{ch["placeholder"]}";',
         "    public override Color NameColor => Color;",
         "    public override CharacterGender Gender => CharacterGender.Neutral;",
         f"    public override int StartingHp => {int(ch['hp'])};", "",
         "    public override IEnumerable<CardModel> StartingDeck =>", "    [",
         ",\n".join(deck), "    ];", "",
         "    public override IReadOnlyList<RelicModel> StartingRelics =>", "    [",
         ",\n".join(relics), "    ];", "",
         f"    public override CardPoolModel CardPool => ModelDb.CardPool<{cls}CardPool>();",
         f"    public override RelicPoolModel RelicPool => ModelDb.RelicPool<{cls}RelicPool>();",
         f"    public override PotionPoolModel PotionPool => ModelDb.PotionPool<{cls}PotionPool>();"]
    L += gimmick.character_members(project)
    import pets as PT
    L += PT.character_members(project)
    if ch.get("icon_image"):
        L += ["", "    public override Control CustomIcon", "    {", "        get", "        {",
              "            var icon = NodeFactory<Control>.CreateFromResource(CustomIconTexturePath);",
              "            icon.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);",
              "            return icon;", "        }", "    }",
              '    public override string CustomIconTexturePath => "character_icon.png".CharacterUiPath();']
    if ch.get("select_image"):
        L.append('    public override string CustomCharacterSelectIconPath => "char_select.png".CharacterUiPath();')
    if ch.get("select_locked_image") or ch.get("select_image"):
        L.append('    public override string CustomCharacterSelectLockedIconPath => "char_select_locked.png".CharacterUiPath();')
    if ch.get("map_marker_image"):
        L.append('    public override string CustomMapMarkerPath => "map_marker.png".CharacterUiPath();')
    if ch.get("select_bg_image"):
        L.append(f'    public override string CustomCharacterSelectBg => MainFile.ResPath + "/scenes/{SELECT_BG_SCENE}";')
    L.append("}")
    return "\n".join(L) + "\n"


def imported_characters(project):
    return [c for c in project.get("imported_characters") or [] if isinstance(c, dict) and c.get("class")]


def card_characters(project):
    """통째로 가져온 프로젝트의 모든 캐릭터와 원래 카드 풀 정보."""
    rows = list(imported_characters(project))
    takeover_data = project.get("takeover") if isinstance(project.get("takeover"), dict) else {}
    rows.extend(c for c in takeover_data.get("characters", []) if isinstance(c, dict) and c.get("class"))
    out, seen = [], set()
    for ch in rows:
        cls = ch.get("class", "")
        if not cls or cls in seen:
            continue
        seen.add(cls)
        pool_class = ch.get("card_pool_class") or ch.get("pool_class") or ""
        pool_full = ch.get("card_pool_full") or ""
        if not pool_full:
            match = re.search(r"\bCardPool\s*<\s*(?:global::)?([\w.]+)\s*>", ch.get("body", "") or "")
            if match:
                pool_name = match.group(1)
                pool_class = pool_class or pool_name.rsplit(".", 1)[-1]
                pool_full = pool_name if "." in pool_name else ".".join(x for x in (ch.get("namespace", ""), pool_name) if x)
        out.append({
            "class": cls,
            "name": text(ch, "name", "ko") or ch.get("name_ko") or cls,
            "card_pool_class": pool_class,
            "card_pool_full": pool_full,
        })
    return out


def card_pool_for_character(project, character_class):
    """캐릭터 클래스 이름으로 원래 카드 풀의 전체 형식을 찾는다."""
    if not character_class:
        return ""
    return next(("global::" + c["card_pool_full"] for c in card_characters(project)
                 if c["class"] == character_class and c.get("card_pool_full")), "")


def transform_pools(project):
    pools = {"": ("전체 카드 풀", "")}
    for cls, label in (("Ironclad","아이언클래드"), ("Silent","사일런트"), ("Defect","디펙트"),
                       ("Regent","리젠트"), ("Necrobinder","네크로바인더")):
        pools["game:"+cls] = (label, "global::MegaCrit.Sts2.Core.Models.CardPools."+cls+"CardPool")
    ch = project["character"]
    if ch.get("enabled"):
        pools["mine"] = (text(ch,"name","ko") or ch["id"], _pool_type(project,"card","mine"))
    for c in card_characters(project):
        if c["card_pool_full"]:
            pools["mod:"+c["class"]] = (c["name"], "global::"+c["card_pool_full"])
    return pools


def effective_card_pool(project, card):
    clone = card.get("clone") or {}
    return card_pool_for_character(project, card.get("pool_character")) or _pool_type(
        project, "card", clone.get("pool","mine"), clone.get("their_pool",""))


def ichar_stem(ich):
    return ich["class"].lower()


ICHAR_FILES = {"select_image": "select", "select_locked_image": "select_locked", "icon_image": "icon",
               "map_marker_image": "map", "select_bg_image": "select_bg", "combat_image": "combat"}


def ichar_ref(project, kind, r):
    """가져온 캐릭터의 덱·유물 항목 → C# 형식 식 (ModelDb.Card<…>() 안에 넣을 이름 또는 전체 식)."""
    if r.startswith("raw:"):
        return f"ModelDb.{kind.capitalize()}<{r[4:]}>()"
    if r.startswith("game:"):
        return game_card_expression(r[5:]) if kind == "card" else game_item_expression("Relic", r[5:])
    return f"ModelDb.{kind.capitalize()}<{item_cls(project, kind, r)}>()"


def gen_imported_character(project, ich):
    """원래 모드의 캐릭터 클래스를 같은 이름으로 다시 쓴다: 체력·골드·시작 덱·시작 유물·고른 그림만 바꾸고 나머지는 원래 코드."""
    import modimport as MI
    mid = project["mod"]["id"]
    ui = f"global::{mid}.{mid}Code.Extensions.StringExtensions.CharacterUiPath"
    stem = ichar_stem(ich)
    remove, add = [], []

    def has(field):
        return bool(ich.get(field)) and os.path.isfile(ich[field])
    if int(ich.get("hp") or 0) > 0:
        remove.append("StartingHp")
        add.append(f"    public override int StartingHp => {int(ich['hp'])};")
    if str(ich.get("gold", "")).strip().isdigit():
        remove.append("StartingGold")
        add.append(f"    public override int StartingGold => {int(ich['gold'])};")
    if not ich.get("deck_fixed"):
        remove.append("StartingDeck")
        deck = [f"        {ichar_ref(project, 'card', d['card'])}" for d in ich.get("deck", [])
                for _ in range(int(d.get("count", 0) or 0))]
        add += ["    public override IEnumerable<CardModel> StartingDeck =>", "    [", ",\n".join(deck), "    ];"]
    if not ich.get("relics_fixed"):
        remove.append("StartingRelics")
        rel = [f"        {ichar_ref(project, 'relic', r)}" for r in ich.get("relics", [])]
        add += ["    public override IReadOnlyList<RelicModel> StartingRelics =>", "    [", ",\n".join(rel), "    ];"]
    if has("select_image"):
        remove.append("CustomCharacterSelectIconPath")
        add.append(f'    public override string CustomCharacterSelectIconPath => {ui}("{stem}_select.png");')
    if has("select_locked_image"):
        remove.append("CustomCharacterSelectLockedIconPath")
        add.append(f'    public override string CustomCharacterSelectLockedIconPath => {ui}("{stem}_select_locked.png");')
    if has("icon_image"):
        remove += ["CustomIconTexturePath", "CustomIconOutlineTexturePath", "CustomIcon", "CustomIconPath"]
        add += ["    public override Control CustomIcon", "    {", "        get", "        {",
                "            var icon = global::BaseLib.Utils.NodeFactories.NodeFactory<Control>.CreateFromResource(CustomIconTexturePath);",
                "            icon.SetAnchorsAndOffsetsPreset(Control.LayoutPreset.FullRect);",
                "            return icon;", "        }", "    }",
                f'    public override string CustomIconTexturePath => {ui}("{stem}_icon.png");']
    if has("map_marker_image"):
        remove.append("CustomMapMarkerPath")
        add.append(f'    public override string CustomMapMarkerPath => {ui}("{stem}_map.png");')
    if has("select_bg_image"):
        remove.append("CustomCharacterSelectBg")
        add.append(f'    public override string CustomCharacterSelectBg => global::{mid}.{mid}Code.MainFile.ResPath + "/scenes/{stem}_select_bg.tscn";')
    if has("combat_image"):
        remove.append("CreateCustomVisuals")
        import pets as PT
        add += PT.character_members(project, ich, image_prefix=f"{stem}_")
    body = MI.remove_members(ich.get("body", ""), remove)
    usings = ["using System.Collections.Generic;", "using Godot;", "using MegaCrit.Sts2.Core.Models;",
              f"using {mid}.{mid}Code.Extensions;"]
    for u in ich.get("usings", []):
        if u not in usings:
            usings.append(u)
    mods = (ich.get("mods") or "public ").strip()
    L = [_header()] + usings + [""]
    if ich.get("namespace"):
        L += [f"namespace {ich['namespace']};", ""]
    if ich.get("attrs"):
        L.append(ich["attrs"])
    bases = ich.get("bases") or ich.get("base") or "PlaceholderCharacterModel"
    L += [f"{mods} class {ich['class']} : {bases}", "{"]
    L += ["    // ---- 모드 메이커에서 고친 값 ----"] + add + ["", "    // ---- 원래 코드 ----"]
    L += _indent(body.strip("\n"))
    L.append("}")
    return "\n".join(L) + "\n"


def energy_outline_color(ch):
    """카드 비용 숫자의 외곽선 색 (캐릭터 색을 어둡게). 생성 코드와 미리보기가 같은 값을 쓴다."""
    h = (ch.get("color") or "#888888").lstrip("#")
    if not HEX_RE.match(h):
        h = "888888"
    r, g, b = (int(h[i:i + 2], 16) for i in (0, 2, 4))
    return "#%02x%02x%02x" % (int(r * 0.32), int(g * 0.32), int(b * 0.32))


def energy_icon_paths(ch):
    """(큰 아이콘, 글자용 아이콘) C# 식. 직접 넣은 그림이 없으면 임시 외형 캐릭터의 게임 아이콘을 쓴다."""
    ph = ch.get("placeholder", "ironclad")
    big = '"charui/big_energy.png".ImagePath()' if ch.get("energy_icon_image") else         f'"res://images/atlases/ui_atlas.sprites/card/energy_{ph}.tres"'
    small = '"charui/text_energy.png".ImagePath()' if ch.get("energy_text_icon_image") else         f'"res://images/packed/sprite_fonts/{ph}_energy_icon.png"'
    return big, small


def game_item_expression(kind, entry):
    if not re.fullmatch(r"[A-Z][A-Z0-9_]*", entry):
        raise ValueError(f"잘못된 원작 ID: {entry}")
    ns = "global::MegaCrit.Sts2.Core.Models."
    return f'{ns}ModelDb.GetById<{ns}{kind}Model>(new {ns}ModelId("{kind.upper()}", "{entry}"))'


def with_game_items(pool, kind, entries):
    if not entries:
        return pool
    method = "GenerateAll" + kind + "s"
    items = ", ".join(game_item_expression(kind, entry) for entry in entries)
    return pool.rstrip()[:-1] + (
        f"    protected override System.Collections.Generic.IEnumerable<global::MegaCrit.Sts2.Core.Models.{kind}Model> {method}() =>\n"
        f"        [..base.{method}(), {items}];\n}}\n")


def gen_pools(project):
    mid = project["mod"]["id"]
    ch = project["character"]
    cls = pascal(ch["id"])
    color = ch["color"].lstrip("#").lower()
    E_BIG, E_SMALL = energy_icon_paths(ch)  # noqa: N806
    ns = f"namespace {mid}.{mid}Code.Character;"
    head = _header() + f"using BaseLib.Abstracts;\nusing {mid}.{mid}Code.Extensions;\nusing Godot;\n\n{ns}\n\n"
    card_pool = head + f"""public class {cls}CardPool : CustomCardPoolModel
{{
    public override string Title => {cls}.CharacterId; // 표시 이름이 아님

    public override string BigEnergyIconPath => {E_BIG};
    public override string TextEnergyIconPath => {E_SMALL};

    // 카드 뒷면 색 (HSV, 0~1). 원래 색 위에 셰이더로 적용되므로 직접 조절해 보세요.
    public override float H => {float(ch['card_h']):.3f}f;
    public override float S => {float(ch['card_s']):.3f}f;
    public override float V => {float(ch['card_v']):.3f}f;

    public override Color DeckEntryCardColor => new("{color}");
    public override Color EnergyOutlineColor => new("{energy_outline_color(ch).lstrip('#')}");

    public override bool IsColorless => false;
}}
"""
    if ch.get("game_cards"):
        entries = ",\n        ".join(game_card_expression(key) for key in ch["game_cards"])
        card_pool = card_pool.rstrip()[:-1] + (
            "    protected override global::MegaCrit.Sts2.Core.Models.CardModel[] GenerateAllCards() =>\n"
            f"        [..base.GenerateAllCards(),\n        {entries}];\n}}\n")
    relic_pool = head + f"""public class {cls}RelicPool : CustomRelicPoolModel
{{
    public override Color LabOutlineColor => {cls}.Color;

    public override string BigEnergyIconPath => {E_BIG};
    public override string TextEnergyIconPath => {E_SMALL};
}}
"""
    potion_pool = head + f"""public class {cls}PotionPool : CustomPotionPoolModel
{{
    public override Color LabOutlineColor => {cls}.Color;

    public override string BigEnergyIconPath => {E_BIG};
    public override string TextEnergyIconPath => {E_SMALL};
}}
"""
    return (card_pool, with_game_items(relic_pool, "Relic", ch.get("game_relics")),
            with_game_items(potion_pool, "Potion", ch.get("game_potions")))


def gen_bases(project):
    mid = project["mod"]["id"]
    ch = project["character"]
    if ch["enabled"]:
        cls = pascal(ch["id"])
        card_pool = f"{cls}CardPool"
        relic_pool = f"{cls}RelicPool"
        potion_pool = f"{cls}PotionPool"
        pool_using = f"using {mid}.{mid}Code.Character;\n"
    else:
        card_pool = "global::MegaCrit.Sts2.Core.Models.CardPools.ColorlessCardPool"
        relic_pool = "global::MegaCrit.Sts2.Core.Models.RelicPools.SharedRelicPool"
        potion_pool = "global::MegaCrit.Sts2.Core.Models.PotionPools.SharedPotionPool"
        pool_using = ""
    h = _header()
    card = h + f"""using BaseLib.Abstracts;
using BaseLib.Extensions;
using BaseLib.Utils;
{pool_using}using {mid}.{mid}Code.Extensions;
using MegaCrit.Sts2.Core.Entities.Cards;

namespace {mid}.{mid}Code.Cards;

// 모든 카드의 부모 클래스. [Pool]로 카드 풀에 자동 등록되고, 그림은 {mid}/images/card_portraits/카드id.png 에서 읽습니다.
[Pool(typeof({card_pool}))]
public abstract class {mid}Card(int cost, CardType type, CardRarity rarity, TargetType target) :
    CustomCardModel(cost, type, rarity, target)
{{
    public override string CustomPortraitPath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".BigCardImagePath();
    public override string PortraitPath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".CardImagePath();
    public override string BetaPortraitPath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".CardImagePath();

    /// <summary>모드 메이커 '기믹' 태그 (예: 격투, 포격)</summary>
    public virtual string[] GimmickTags => [];
}}
"""
    relic = h + f"""using BaseLib.Abstracts;
using BaseLib.Extensions;
using BaseLib.Utils;
{pool_using}using {mid}.{mid}Code.Extensions;

namespace {mid}.{mid}Code.Relics;

[Pool(typeof({relic_pool}))]
public abstract class {mid}Relic : CustomRelicModel
{{
    public override string PackedIconPath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".RelicImagePath();
    protected override string PackedIconOutlinePath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}_outline.png".RelicOutlineImagePath();
    protected override string BigIconPath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".BigRelicImagePath();
}}
"""
    potion = h + f"""using BaseLib.Abstracts;
using BaseLib.Extensions;
using BaseLib.Utils;
{pool_using}using {mid}.{mid}Code.Extensions;

namespace {mid}.{mid}Code.Potions;

[Pool(typeof({potion_pool}))]
public abstract class {mid}Potion : CustomPotionModel
{{
    public override string? CustomPackedImagePath =>
        $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".PotionImagePath();
    public override string? CustomPackedOutlinePath =>
        $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".PotionOutlineImagePath();
}}
"""
    power = h + f"""using BaseLib.Abstracts;
using BaseLib.Extensions;
using {mid}.{mid}Code.Extensions;
using MegaCrit.Sts2.Core.Combat;
using MegaCrit.Sts2.Core.Entities.Creatures;

using MegaCrit.Sts2.Core.Models;

namespace {mid}.{mid}Code.Powers;

// 모든 새 파워의 부모 클래스. 아이콘은 {mid}/images/powers/파워id_power.png 에서 읽습니다.
public abstract class {mid}Power : CustomPowerModel
{{
    public override string? CustomPackedIconPath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".PowerImagePath();
    public override string? CustomBigIconPath => $"{{Id.Entry.RemovePrefix().ToLowerInvariant()}}.png".BigPowerImagePath();

    /// <summary>같은 그룹(예: 날씨)의 파워는 하나만 유지된다 (모드 메이커 '기믹')</summary>
    public virtual string GimmickGroup => "";

    // ---- 다른 파워의 상시 효과가 기믹을 바꿀 때 쓰는 자리 (모드 메이커가 채움) ----
    public virtual int SummonSlotBonus => 0;
    public virtual int CapBonus(PowerModel res) => 0;
    public virtual int ResCostDelta(CardModel card, System.Type res) => 0;
    public virtual int ButtonCostDelta(int index) => 0;
    public virtual int ButtonUsesDelta(int index) => 0;

    /// <summary>파워 소유자의 적 목록 (플레이어 소유면 몬스터, 몬스터 소유면 플레이어).</summary>
    protected IReadOnlyList<Creature> OwnerEnemies()
    {{
        var state = Owner.CombatState;
        if (state == null) return [];
        return Owner.Side == CombatSide.Player
            ? state.HittableEnemies
            : state.PlayerCreatures.Where(c => c.IsAlive).ToList();
    }}

    protected Creature? RandomOwnerEnemy()
    {{
        var list = OwnerEnemies();
        if (list.Count == 0 || Owner.CombatState == null) return null;
        return Owner.CombatState.RunState.Rng.CombatTargets.NextItem(list);
    }}
}}
"""
    return card, relic, potion, power


def gen_extensions(project):
    mid = project["mod"]["id"]

    def fn(name, sub, fallback):
        return f"""
    public static string {name}(this string path)
    {{
        var full = Path.Join(MainFile.ResPath, "images", {sub}, path);
        if (ResourceLoader.Exists(full)) return full;
        return Path.Join(MainFile.ResPath, "images", {sub}, "{fallback}");
    }}
"""
    body = "".join([
        fn("CardImagePath", '"card_portraits"', "card.png"),
        fn("BigCardImagePath", 'Path.Join("card_portraits", "big")', "card.png"),
        fn("RelicImagePath", '"relics"', "relic.png"),
        fn("RelicOutlineImagePath", '"relics"', "relic_outline.png"),
        fn("BigRelicImagePath", 'Path.Join("relics", "big")', "relic.png"),
        fn("PotionImagePath", '"potions"', "potion.png"),
        fn("PotionOutlineImagePath", 'Path.Join("potions", "outline")', "potion.png"),
        fn("PowerImagePath", '"powers"', "power.png"),
        fn("BigPowerImagePath", 'Path.Join("powers", "big")', "power.png"),
        fn("OrbImagePath", '"orbs"', "orb.png"),
        fn("FxImagePath", '"fx"', "fx.png"),
        fn("PetImagePath", '"pets"', "pet.png"),
    ])
    return _header() + f"""using Godot;

namespace {mid}.{mid}Code.Extensions;

// 에셋 경로 도우미. 파일이 없으면 기본 임시 그림으로 대체합니다.
public static class StringExtensions
{{
    public static string ImagePath(this string path) => Path.Join(MainFile.ResPath, "images", path);

    public static string CharacterUiPath(this string path) => Path.Join(MainFile.ResPath, "images", "charui", path);
{body}}}
"""


def gen_mainfile(project):
    mid = project["mod"]["id"]
    return _header() + f"""using System.Reflection;
using Godot;
using HarmonyLib;
using MegaCrit.Sts2.Core.Modding;

namespace {mid}.{mid}Code;

[ModInitializer(nameof(Initialize))]
public partial class MainFile : Node
{{
    public const string ModId = "{mid}"; // 리소스 경로에 사용
    public const string ResPath = $"res://{{ModId}}";

    public static MegaCrit.Sts2.Core.Logging.Logger Logger {{ get; }} = new(ModId, MegaCrit.Sts2.Core.Logging.LogType.Generic);

    public static void Initialize()
    {{
        var assembly = Assembly.GetExecutingAssembly();{_takeover_init(project)}
    }}
}}
"""


def _takeover_init(project):
    """MainFile.Initialize 본문: 보통은 Harmony 패치. 통째로 가져온 모드면 원래 리소스 팩도 읽는다."""
    t = takeover(project)
    patch = """
        Harmony harmony = new(ModId);
        harmony.PatchAll(assembly);"""
    if not t:
        return patch
    out = ""
    if t.get("pck"):
        out += f"""
        // 원래 모드의 그림·장면·번역 (이 모드가 새로 만든 파일이 우선)
        var dir = System.IO.Path.GetDirectoryName(assembly.Location) ?? "";
        var basePack = System.IO.Path.Combine(dir, ModId + "{TAKEOVER_PCK_SUFFIX}.pck");
        if (System.IO.File.Exists(basePack) && !ProjectSettings.LoadResourcePack(basePack, false))
            MegaCrit.Sts2.Core.Logging.Log.Error("원래 리소스 팩을 읽지 못했습니다: " + basePack);"""
    if not t.get("patches_all"):      # 원래 코드가 직접 패치하면 두 번 하지 않는다
        out += patch
    return out


# ---------------------------------------------------------------------------
# 프로젝트 설정 파일 (ModTemplate-StS2 기반)
# ---------------------------------------------------------------------------
def _dep_refs(project):
    out = []
    deps = [d for d in project.get("dependencies", []) if d.get("dll")]
    if deps:
        # 참조한 모드의 internal 멤버도 쓸 수 있게 (복제한 원본 코드가 쓰는 경우)
        out.append("""
        <PackageReference Include="Krafs.Publicizer" Version="2.3.0" PrivateAssets="All"/>""")
        for d in deps:
            asm = os.path.splitext(os.path.basename(d["dll"]))[0]
            out.append(f"""
        <Publicize Include="{asm}" IncludeVirtualMembers="false" IncludeCompilerGeneratedMembers="false" />""")
    for d in project.get("dependencies", []):
        if d.get("dll"):
            out.append(f"""
        <Reference Include="{d['id']}">
            <HintPath>{d['dll']}</HintPath>
            <Private>false</Private>
        </Reference>""")
    return "".join(out)


def gen_csproj(project):
    mid = project["mod"]["id"]
    blv = project["mod"].get("baselib_version") or "*"
    dep_refs = _dep_refs(project)
    if takeover(project):   # 원래 코드는 암시적 using 없이 만들어져서 Godot 형식(Timer·Thread·HttpClient 등)과 겹치지 않게
        dep_refs += """
        <Using Remove="System.Threading" />
        <Using Remove="System.Net.Http" />"""
    return f"""<Project Sdk="Godot.NET.Sdk/4.5.1" InitialTargets="CheckDependencyPaths">
    <Import Project=".\\Sts2PathDiscovery.props"/>
    <PropertyGroup>
        <TargetFramework>net9.0</TargetFramework>
        <ImplicitUsings>true</ImplicitUsings>
        <Nullable>enable</Nullable>
        <Publicize>false</Publicize>
        <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
        <AppOutputBase>$(MSBuildProjectDirectory)\\</AppOutputBase>
        <PathMap>$(AppOutputBase)=.\\</PathMap>
        <GodotDisabledSourceGenerators>GodotPluginsInitializer</GodotDisabledSourceGenerators>
        <NoWarn>$(NoWarn);MSB3270</NoWarn>
    </PropertyGroup>

    <ItemGroup Condition="Exists('$(Sts2DataDir)')" >
        <Reference Include="0Harmony">
            <HintPath>$(Sts2DataDir)/0Harmony.dll</HintPath>
            <Private>false</Private>
        </Reference>
        <Reference Include="sts2">
            <HintPath>$(Sts2DataDir)/sts2.dll</HintPath>
            <Private>false</Private>
        </Reference>
    </ItemGroup>

    <ItemGroup Condition="$(Publicize)">
        <PackageReference Include="Krafs.Publicizer" Version="2.3.0" PrivateAssets="All"/>
        <Publicize Include="sts2" IncludeVirtualMembers="false" IncludeCompilerGeneratedMembers="false" />
    </ItemGroup>

    <ItemGroup>
        <PackageReference Include="Alchyr.Sts2.BaseLib" Version="{blv}" PrivateAssets="All"/>
        <PackageReference Include="Alchyr.Sts2.ModAnalyzers" Version="*" />{dep_refs}
        <AdditionalFiles Include="{mid}/localization/**/*.json"/>
    </ItemGroup>

    <ItemGroup>
        <Compile Remove="{mid}/**" />
        <EmbeddedResource Remove="{mid}/**" />
    </ItemGroup>

    <ItemGroup>
        <None Condition="Exists('Directory.Build.props')" Include="Directory.Build.props"/>
        <None Include="{mid}.json" />
        <None Include="project.godot"/>
        <None Include="{mid}/**" />
    </ItemGroup>

    <Target Name="CheckDependencyPaths" >
        <Error Text=" Slay the Spire 2 data not found at path '$(Sts2DataDir)'. Directory.Build.props 의 Sts2Path 를 설정하세요."
               Condition="'$(Sts2DataDir)' == '' or !Exists('$(Sts2DataDir)')" />
    </Target>

    <Target Name="UpdateDependencyVersions" BeforeTargets="BeforeBuild" Condition="Exists('.godot/mono/temp/obj/project.assets.json')">
        <PropertyGroup>
            <ManifestPath>$(MSBuildProjectName).json</ManifestPath>
            <NuGetData>$([System.IO.File]::ReadAllText(".godot/mono/temp/obj/project.assets.json"))</NuGetData>
            <ActiveBaseLibVersion>$([System.Text.RegularExpressions.Regex]::Match($(NuGetData), '"Alchyr.Sts2.BaseLib\\/([^"]*)').Result('$1'))</ActiveBaseLibVersion>
            <OldContent>$([System.IO.File]::ReadAllText($(ManifestPath)))</OldContent>
            <NewContent>$([System.Text.RegularExpressions.Regex]::Replace($(OldContent), '("id":\\s*"BaseLib",\\s*"min_version":\\s*")[^"]*', '${{1}}$(ActiveBaseLibVersion)'))</NewContent>
        </PropertyGroup>
        <WriteLinesToFile Condition="'$(OldContent)' != '$(NewContent)'" File="$(ManifestPath)" Lines="$(NewContent)" Overwrite="true" Encoding="UTF-8" />
    </Target>

    <Target Name="CopyToModsFolderOnBuild" AfterTargets="PostBuildEvent">
        <Message Text="Copying .dll .pdb and .json to mods folder: $(ModsPath)$(MSBuildProjectName)/" Importance="high" />
        <Copy SourceFiles="$(TargetPath)" DestinationFolder="$(ModsPath)$(MSBuildProjectName)/" />
        <Copy SourceFiles="$(AssemblyName).json" DestinationFolder="$(ModsPath)$(MSBuildProjectName)/" />
        <Copy SourceFiles="$(TargetDir)$(TargetName).pdb" DestinationFolder="$(ModsPath)$(MSBuildProjectName)/" />
        <Copy Condition="Exists('$(MSBuildProjectName)_original.pck')" SourceFiles="$(MSBuildProjectName)_original.pck" DestinationFolder="$(ModsPath)$(MSBuildProjectName)/" />
    </Target>

    <Target Name="NeedGodotForPublish" BeforeTargets="Publish">
        <Error Text=" Godot(MegaDot 4.5.1) path must be set before publishing; not found at '$(GodotPath)'. Check Directory.Build.props."
               Condition="'$(GodotPath)' == '' or !Exists('$(GodotPath)')"/>
    </Target>

    <Target Name="GodotPublish" AfterTargets="Publish" Condition="'$(GodotPath)' != '' and Exists('$(GodotPath)') and '$(IsInnerGodotExport)' != 'true'">
        <PropertyGroup>
            <PackStage>$(MSBuildProjectDirectory)/.godot/pack-$([System.Guid]::NewGuid())</PackStage>
            <PackOutput>$(PackStage)/../pack-$([System.Guid]::NewGuid()).pck</PackOutput>
        </PropertyGroup>
        <ItemGroup>
            <PackAsset Include="$(MSBuildProjectName)/**/*" Exclude="$(MSBuildProjectName)/**/*.import"/>
        </ItemGroup>
        <MakeDir Directories="$(PackStage)"/>
        <Copy SourceFiles="@(PackAsset)" DestinationFiles="@(PackAsset->'$(PackStage)/$(MSBuildProjectName)/%(RecursiveDir)%(Filename)%(Extension)')"/>
        <WriteLinesToFile File="$(PackStage)/project.godot" Lines="config_version=5" Overwrite="true"/>
        <Copy SourceFiles="export_presets.cfg" DestinationFolder="$(PackStage)"/>
        <Exec WorkingDirectory="$(PackStage)" Command="&quot;$(GodotPath)&quot; --headless --import"/>
        <Exec WorkingDirectory="$(PackStage)" Command="&quot;$(GodotPath)&quot; --headless --export-pack BasicExport &quot;$(PackOutput)&quot;"/>
        <Error Condition="!Exists('$(PackOutput)')" Text="MegaDot did not produce the new resource pack."/>
        <Copy SourceFiles="$(PackOutput)" DestinationFiles="$(ModsPath)$(MSBuildProjectName)/$(MSBuildProjectName).pck"/>
        <Delete Files="$(PackOutput)"/>
        <RemoveDir Directories="$(PackStage)"/>
    </Target>
</Project>
"""


def gen_build_props(settings):
    godot = xml_escape((settings.get("godot_path") or "C:/megadot/MegaDot_v4.5.1-stable_mono_win64.exe").replace("\\", "/"))
    sts2 = xml_escape((settings.get("sts2_path") or "").replace("\\", "/"))
    sts2_line = f"        <Sts2Path>{sts2}</Sts2Path>" if sts2 else \
        "        <!-- <Sts2Path>?/steamapps/common/Slay the Spire 2</Sts2Path> -->"
    return f"""<Project>
    <PropertyGroup>
        <!-- MegaDot / Godot 4.5.1 mono 실행 파일 (dotnet publish 로 .pck 를 만들 때 필요). 더 새 버전으로 만든 .pck 는 게임이 못 읽습니다. -->
        <GodotPath>{godot}</GodotPath>
        <!-- 슬더스2 설치 폴더. 자동으로 못 찾으면 직접 지정하세요. -->
{sts2_line}
    </PropertyGroup>
</Project>
"""


STS2_PATH_DISCOVERY = r"""<Project>
    <!-- Fills Sts2Path and Sts2DataDir when not set. (from Alchyr/ModTemplate-StS2) -->
    <PropertyGroup>
        <IsLinux>false</IsLinux>
        <IsOSX>false</IsOSX>
        <IsLinux Condition="$([MSBuild]::IsOSPlatform('Linux'))">true</IsLinux>
        <IsOSX Condition="$([MSBuild]::IsOSPlatform('OSX'))">true</IsOSX>
    </PropertyGroup>

    <PropertyGroup Condition="'$(IsLinux)' != 'true' And '$(IsOSX)' != 'true'">
        <RegistrySts2Path>$([MSBuild]::GetRegistryValueFromView('HKEY_LOCAL_MACHINE\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\Steam App 2868840', 'InstallLocation', '', RegistryView.Registry64, RegistryView.Registry32))</RegistrySts2Path>
        <AutoSteamPath>$(registry:HKEY_CURRENT_USER\Software\Valve\Steam@SteamPath)\steamapps</AutoSteamPath>
        <SteamLibraryPath Condition="'$(SteamLibraryPath)' == '' and Exists('$(AutoSteamPath)/common/Slay the Spire 2')">$(AutoSteamPath)</SteamLibraryPath>
        <SteamLibraryPath Condition="'$(SteamLibraryPath)' == ''">C:/Program Files (x86)/Steam/steamapps</SteamLibraryPath>

        <Sts2Path Condition="'$(Sts2Path)' == '' and Exists('$(SteamLibraryPath)/common/Slay the Spire 2')">$(SteamLibraryPath)/common/Slay the Spire 2</Sts2Path>
        <Sts2Path Condition="'$(Sts2Path)' == '' and Exists('$(RegistrySts2Path)/data_sts2_windows_x86_64')">$(RegistrySts2Path)</Sts2Path>
        <Sts2Path Condition="'$(Sts2Path)' == ''">$(SteamLibraryPath)/common/Slay the Spire 2</Sts2Path>

        <ModsPath>$(Sts2Path)/mods/</ModsPath>
        <Sts2DataDir>$(Sts2Path)/data_sts2_windows_x86_64</Sts2DataDir>
    </PropertyGroup>

    <PropertyGroup Condition="'$(IsLinux)' == 'true'">
        <SteamLibraryPath Condition="'$(SteamLibraryPath)' == ''">$(HOME)/.local/share/Steam/steamapps</SteamLibraryPath>
        <Sts2Path Condition="'$(Sts2Path)' == ''">$(SteamLibraryPath)/common/Slay the Spire 2</Sts2Path>
        <ModsPath>$(Sts2Path)/mods/</ModsPath>
        <Sts2DataDir>$(Sts2Path)/data_sts2_linuxbsd_x86_64</Sts2DataDir>
    </PropertyGroup>

    <PropertyGroup Condition="'$(IsOSX)' == 'true'">
        <SteamLibraryPath Condition="'$(SteamLibraryPath)' == ''">$(HOME)/Library/Application Support/Steam/steamapps</SteamLibraryPath>
        <Sts2Path Condition="'$(Sts2Path)' == ''">$(SteamLibraryPath)/common/Slay the Spire 2</Sts2Path>
        <ModsPath>$(Sts2Path)/SlayTheSpire2.app/Contents/MacOS/mods/</ModsPath>
        <Sts2DataDir>$(Sts2Path)/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_x86_64</Sts2DataDir>
    </PropertyGroup>
</Project>
"""


def gen_project_godot(project):
    mid = project["mod"]["id"]
    return f"""; Engine configuration file.

config_version=5

[application]

config/name="{mid}"
config/features=PackedStringArray("4.5", "C#", "Mobile")
config/icon="res://{mid}/mod_image.png"

[display]

window/size/viewport_width=1920
window/size/viewport_height=1080
window/stretch/mode="canvas_items"
window/stretch/aspect="expand"

[dotnet]

project/assembly_name="{mid}"

[rendering]

renderer/rendering_method="mobile"
"""


def gen_export_presets(project):
    mid = project["mod"]["id"]
    return f"""[preset.0]

name="BasicExport"
platform="Windows Desktop"
runnable=true
advanced_options=false
dedicated_server=false
custom_features=""
export_filter="all_resources"
include_filter="*.json"
exclude_filter="{mid}.json"
export_path=""
patches=PackedStringArray()
encryption_include_filters=""
encryption_exclude_filters=""
seed=0
encrypt_pck=false
encrypt_directory=false
script_export_mode=2

[preset.0.options]

custom_template/debug=""
custom_template/release=""
debug/export_console_wrapper=1
binary_format/embed_pck=false
texture_format/s3tc_bptc=true
texture_format/etc2_astc=false
shader_baker/enabled=false
binary_format/architecture="msil"
codesign/enable=false
application/modify_resources=false
dotnet/include_scripts_content=false
dotnet/include_debug_symbols=true
dotnet/embed_build_outputs=false
"""


def gen_manifest(project):
    m = project["mod"]
    blv = m.get("baselib_version") or "*"
    return json.dumps({
        "id": m["id"], "name": m["name"], "author": m["author"], "description": m["description"],
        "version": m["version"], "min_game_version": m["min_game_version"],
        "has_pck": True, "has_dll": True,
        "dependencies": [{"id": "BaseLib", "min_version": "3.3.0" if blv == "*" else blv}] +
                        [{"id": d["id"], "min_version": (d.get("version") or "0.0.0").lstrip("vV")}
                         for d in project.get("dependencies", []) if d.get("id") and d["id"] != "BaseLib"],
        "affects_gameplay": True,
    }, ensure_ascii=False, indent=2) + "\n"


GITIGNORE = """.godot/
.vs/
.idea/
bin/
obj/
*.user
"""


# ---------------------------------------------------------------------------
# 현지화
# ---------------------------------------------------------------------------
CHAR_TEXT_DEFAULTS = {
    "ko": {
        "pronounSubject": "그", "pronounObject": "그", "pronounPossessive": "그의 것", "possessiveAdjective": "그의",
        "unlockText": "{Prerequisite}(으)로 승리하면 해금됩니다.",
        "cardsModifierTitle": "{name} 카드", "cardsModifierDescription": "{name} 카드가 보상과 상점에 등장합니다.",
        "eventDeathPrevention": "아직 쓰러질 수 없어.", "goldMonologue": "도움이 되겠군.",
        "aromaPrinciple": "아직 쓰이지 않은 이야기.",
        "banter.alive.endTurnPing": "준비되면 알려줘.", "banter.dead.endTurnPing": "...",
    },
    "en": {
        "pronounSubject": "they", "pronounObject": "them", "pronounPossessive": "theirs", "possessiveAdjective": "their",
        "unlockText": "Win a run as {Prerequisite} to unlock.",
        "cardsModifierTitle": "{name} Cards", "cardsModifierDescription": "{name} cards will appear in rewards and shops.",
        "eventDeathPrevention": "Not yet...", "goldMonologue": "This will help.",
        "aromaPrinciple": "A story not yet written.",
        "banter.alive.endTurnPing": "Let me know when you're ready.", "banter.dead.endTurnPing": "...",
    },
}

ARCHITECT_LINES = {
    "ko": [("ancient", "또 한 명의 도전자인가. 너는 무엇을 찾아 여기까지 왔지?"), ("next", "대답한다"),
           ("char", "끝까지 올라가 보고 싶을 뿐이다."),
           ("ancient", "다시 왔군. 지난번보다 조금은 단단해졌나?"), ("next", "계속"),
           ("char", "넘어질 때마다 배웠으니까."), ("next", "계속"),
           ("ancient", "좋다. 그 배움이 얼마나 버티는지 보지."),
           ("ancient", "끈질기군. 첨탑은 너를 기억할 것이다."), ("next", "계속"),
           ("char", "그렇다면, 이번에는 끝을 기억하게 해 주지."), ("next", "계속"),
           ("ancient", "말은 쉽지. 증명해 봐라.")],
    "en": [("ancient", "Another challenger. What did you come here seeking?"), ("next", "Answer"),
           ("char", "Only to see the top."),
           ("ancient", "You return. A little sturdier than before?"), ("next", "Continue"),
           ("char", "Every fall taught me something."), ("next", "Continue"),
           ("ancient", "Good. Let us see how long those lessons hold."),
           ("ancient", "Persistent. The Spire will remember you."), ("next", "Continue"),
           ("char", "Then this time, let it remember the ending."), ("next", "Continue"),
           ("ancient", "Words are easy. Prove it.")],
}
_ARCHITECT_KEYS = ["0-0r.ancient", "0-0r.next", "0-1r.char",
                   "1-0r.ancient", "1-0r.next", "1-1r.char", "1-1r.next", "1-2r.ancient",
                   "2-0r.ancient", "2-0r.next", "2-1r.char", "2-1r.next", "2-2r.ancient"]
ARCHITECT_LINES["zh"] = [("ancient", "又一个挑战者。你来这里寻找什么？"), ("next", "回答"),
                         ("char", "我只想看看塔顶。"),
                         ("ancient", "你又回来了。比上次更坚强了吗？"), ("next", "继续"),
                         ("char", "每一次跌倒都让我学到了东西。"), ("next", "继续"),
                         ("ancient", "很好。让我们看看这些教训能撑多久。"),
                         ("ancient", "真执着。尖塔会记住你的。"), ("next", "继续"),
                         ("char", "那么这一次，让它记住结局。"), ("next", "继续"),
                         ("ancient", "说起来容易。证明给我看。")]
ARCHITECT_NEXT = {"ko": ("대답한다", "계속"), "en": ("Answer", "Continue"), "zh": ("回答", "继续")}
_ARCH_WHO = {"ancient": ("아키텍트", "architect", "건축가", "a", "建筑师", "the architect"),
             "char": ("나", "me", "char", "c", "我", "캐릭터", "player")}


def architect_dialogues(text, char_names=()):
    """'아키텍트: …' / '나: …' 줄, '---' 로 대화 구분 -> [[(speaker, 글), …], …]. 못 읽으면 []."""
    convs, cur = [], []
    names = {n.strip().lower() for n in char_names if n and n.strip()}
    for raw in (text or "").replace("\r", "").split("\n"):
        line = raw.strip()
        if not line:
            continue
        if re.fullmatch(r"-{3,}|={3,}", line):
            if cur:
                convs.append(cur)
            cur = []
            continue
        m = re.match(r"^([^:：]{1,20})[:：]\s*(.*)$", line)
        who = None
        if m:
            tag = m.group(1).strip().lower()
            if tag in _ARCH_WHO["ancient"]:
                who = "ancient"
            elif tag in _ARCH_WHO["char"] or tag in names:
                who = "char"
        if who:
            if m.group(2).strip():
                cur.append((who, m.group(2).strip()))
        elif cur:
            cur[-1] = (cur[-1][0], cur[-1][1] + " " + line)     # 이어지는 줄
        else:
            return []
    if cur:
        convs.append(cur)
    return [c for c in convs if c]


def default_architect(lang):
    """기본 대사를 대화 목록으로."""
    convs, cur = [], []
    for who, line in ARCHITECT_LINES.get(lang, ARCHITECT_LINES["en"]):
        if who == "next":
            continue
        cur.append((who, line))
    # 기본 대사는 2·3·3 줄 대화 세 개
    convs = [cur[0:2], cur[2:5], cur[5:8]]
    return convs


def architect_text(convs, lang):
    lab = {"ko": ("아키텍트", "나"), "en": ("Architect", "Me"), "zh": ("建筑师", "我")}.get(lang, ("Architect", "Me"))
    return "\n---\n".join("\n".join(f"{lab[0] if w == 'ancient' else lab[1]}: {t}" for w, t in c) for c in convs)


def architect_loc(ch, lid, lang):
    """THE_ARCHITECT.talk.<캐릭터>.<대화>-<줄>r.(ancient|char|next). 대화 n 번째는 n 번째 승리 뒤 방문에 나오고,
    'r' (반복) 이라 그 뒤 방문에도 무작위로 다시 나온다 → 몇 번을 이겨도 대사가 비지 않는다."""
    convs = architect_dialogues(ch.get(f"architect_{lang}") or "", (ch.get("name_ko"), ch.get("name_en"), ch.get("name_zh")))
    if not convs and lang == "zh":
        convs = architect_dialogues(ch.get("architect_en") or "", (ch.get("name_en"),))
    if not convs:
        convs = default_architect(lang)
    nxt = ARCHITECT_NEXT.get(lang, ARCHITECT_NEXT["en"])
    out = {}
    for i, conv in enumerate(convs):
        for j, (who, line) in enumerate(conv):
            out[f"THE_ARCHITECT.talk.{lid}.{i}-{j}r.{who}"] = line
            if j < len(conv) - 1:
                out[f"THE_ARCHITECT.talk.{lid}.{i}-{j}r.next"] = nxt[0] if who == "ancient" else nxt[1]
    return out


def architect_from_loc(project, lid, lang):
    """통째로 가져온 모드의 원래 아키텍트 대사 → 대화 목록 (없으면 None)."""
    base = takeover_loc(project, lang) if lid else None
    if not base:
        return None
    pat = re.compile(r"^THE_ARCHITECT\.talk\." + re.escape(lid) + r"\.(\d+)-(\d+)r?\.(ancient|char)$")
    rows = {}
    for k, v in (base.get("ancients") or {}).items():
        m = pat.match(k)
        if m:
            rows.setdefault(int(m.group(1)), []).append((int(m.group(2)), m.group(3), v))
    if not rows:
        return None
    return [[(who, line) for _j, who, line in sorted(rows[i])] for i in sorted(rows)]


def gen_architect_safety(project):
    """아키텍트 대사가 없어 Dialogue 가 비면 게임이 WinRun 에서 멈춘다(널 참조) → 빈 대화로 막고,
    이 캐릭터 대사가 방문 횟수와 안 맞으면 이 캐릭터 대사 아무거나 고르게 한다."""
    mid = project["mod"]["id"]
    cls = pascal(project["character"]["id"])
    return _header() + f"""using System;
using System.Collections.Generic;
using System.Linq;
using HarmonyLib;
using MegaCrit.Sts2.Core.Entities.Ancients;
using MegaCrit.Sts2.Core.Models;
using MegaCrit.Sts2.Core.Models.Events;

namespace {mid}.{mid}Code.Character;

[HarmonyPatch(typeof(TheArchitect), "WinRun")]
internal static class {cls}ArchitectWinRunGuard
{{
    private static readonly System.Reflection.FieldInfo? DialogueField = AccessTools.Field(typeof(TheArchitect), "_dialogue");

    [HarmonyPrefix]
    private static void Prefix(TheArchitect __instance)
    {{
        if (DialogueField == null || DialogueField.GetValue(__instance) != null) return;
        DialogueField.SetValue(__instance, new AncientDialogue(Array.Empty<string>()) {{ EndAttackers = ArchitectAttackers.Both }});
    }}
}}

[HarmonyPatch(typeof(AncientDialogueSet), nameof(AncientDialogueSet.GetValidDialogues))]
internal static class {cls}AncientDialogueFallback
{{
    [HarmonyPostfix]
    private static void Postfix(AncientDialogueSet __instance, ModelId characterId, ref IEnumerable<AncientDialogue> __result)
    {{
        if (characterId.Entry != ModelDb.Character<{cls}>().Id.Entry) return;
        var list = __result?.ToList() ?? new List<AncientDialogue>();
        if (list.Count == 0 && __instance.CharacterDialogues.TryGetValue(characterId.Entry, out var mine) && mine.Count > 0)
            list = mine.ToList();
        __result = list;
    }}
}}
"""


SELECT_BG_SCENE = "char_select_bg.tscn"
TAKEOVER_PCK_SUFFIX = "_original"     # 통째로 가져온 모드의 원래 리소스 팩: <ID>_original.pck
TAKEOVER_CODE_DIR = "Original"        # 원래 C# 코드를 넣는 폴더 (<ID>Code/Original)


def gen_select_bg_scene(project, png="char_select_bg.png"):
    """캐릭터 선택 화면 전체 배경: 화면을 꽉 채우는 TextureRect 하나 (비율 유지, 넘치는 곳은 잘림)."""
    mid = project["mod"]["id"]
    return f"""; StS2 모드 메이커가 만든 파일 (캐릭터 선택 화면 배경)
[gd_scene load_steps=2 format=3]

[ext_resource type="Texture2D" path="res://{mid}/images/charui/{png}" id="1_bg"]

[node name="CharSelectBg" type="Control"]
layout_mode = 3
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
mouse_filter = 2

[node name="Image" type="TextureRect" parent="."]
layout_mode = 1
anchors_preset = 15
anchor_right = 1.0
anchor_bottom = 1.0
grow_horizontal = 2
grow_vertical = 2
mouse_filter = 2
texture = ExtResource("1_bg")
expand_mode = 1
stretch_mode = 6
"""


def gen_localization(project, lang, extras=None):
    """lang: 'ko' or 'en' -> dict of filename -> data"""
    files = {n: {} for n in ("cards", "relics", "potions", "powers", "card_keywords", "static_hover_tips",
                             "characters", "ancients")}
    for c in project["cards"]:
        lid = item_loc_id(project, "card", c)
        files["cards"][f"{lid}.title"] = text(c, "name", lang)
        files["cards"][f"{lid}.description"] = description(project, c, "card", lang)
    for r in project["relics"]:
        lid = item_loc_id(project, "relic", r)
        files["relics"][f"{lid}.title"] = text(r, "name", lang)
        files["relics"][f"{lid}.description"] = description(project, r, "relic", lang)
        files["relics"][f"{lid}.flavor"] = text(r, "flavor", lang)
    for p in project["potions"]:
        lid = item_loc_id(project, "potion", p)
        files["potions"][f"{lid}.title"] = text(p, "name", lang)
        files["potions"][f"{lid}.description"] = description(project, p, "potion", lang)
    for pw in project.get("powers", []):
        lid = item_loc_id(project, "power", pw)
        smart = description(project, pw, "power", lang)
        files["powers"][f"{lid}.title"] = text(pw, "name", lang)
        # 정적 설명(카드 툴팁 등)에는 {Amount}가 없으므로 X로 바꾼다
        static = text(pw, "static_desc", lang) if pw.get("clone") else ""
        files["powers"][f"{lid}.description"] = static or smart.replace("[blue]{Amount}[/blue]", "X").replace("{Amount}", "X")
        files["powers"][f"{lid}.smartDescription"] = smart
    # 복제한 항목: 원본 텍스트의 다른 키(선택 화면 문구 등)도 새 ID 로
    for key, fname, kind in (("cards", "cards", "card"), ("relics", "relics", "relic"), ("potions", "potions", "potion"),
                             ("powers", "powers", "power")):
        for it in project.get(key, []):
            extra = (it.get("extra_loc") or {}).get(lang) or (it.get("extra_loc") or {}).get("en" if lang == "ko" else "ko") or {}
            lid = item_loc_id(project, kind, it)
            for k, v in extra.items():
                files[fname].setdefault(f"{lid}.{k}", v)
    ch = project["character"]
    if ch["enabled"]:
        lid = loc_id(project, ch["id"])
        name = text(ch, "name", lang)
        d = files["characters"]
        d[f"{lid}.title"] = name
        d[f"{lid}.titleObject"] = name
        d[f"{lid}.description"] = character_description(ch, lang)
    if ch["enabled"]:
        # 중국어 기본 대사가 없으면 영어 대사를 쓴다
        for k, v in CHAR_TEXT_DEFAULTS.get(lang, CHAR_TEXT_DEFAULTS["en"]).items():
            d[f"{lid}.{k}"] = v.replace("{name}", name)
        files["ancients"].update(architect_loc(ch, lid, lang))
    gimmick.localization(project, lang, files, extras or [])
    base = takeover_loc(project, lang)
    if base is not None:      # 통째로 가져온 모드: 원래 번역(캐릭터·몬스터·이벤트 등)을 바탕에 깔고 내 항목 번역을 덮어쓴다
        for name, data in files.items():
            base.setdefault(name, {}).update(data)
        files = base
    for ich in imported_characters(project):
        lid = ich["loc_id"]
        chars = files.setdefault("characters", {})
        orig = ich.get("orig") or {}
        name = text(ich, "name", lang)
        if name:
            chars[f"{lid}.title"] = name
            if name != text(orig, "name", lang) or f"{lid}.titleObject" not in chars:
                chars[f"{lid}.titleObject"] = name
        desc = text(ich, "desc", lang)
        if desc:
            chars[f"{lid}.description"] = desc
        anc = files.setdefault("ancients", {})
        mine = any((ich.get(f"architect_{lg}") or "").strip() for lg in ("ko", "en", "zh"))
        pre = f"THE_ARCHITECT.talk.{lid}."
        if mine:        # 내가 쓴 대사로 바꾼다
            for k in [k for k in anc if k.startswith(pre)]:
                del anc[k]
            anc.update(architect_loc(ich, lid, lang))
        elif not any(k.startswith(pre) for k in anc):
            anc.update(architect_loc(ich, lid, lang))     # 원래도 없으면 기본 대사 (없으면 3막 뒤 멈춤)
    t = takeover(project)
    if t:
        # 원래 캐릭터에 아키텍트 대사가 없으면 기본 대사를 넣는다 (없으면 3막 뒤 아키텍트에서 게임이 멈춘다)
        anc = files.setdefault("ancients", {})
        for oc in t.get("characters", []):
            lid = oc.get("loc_id", "")
            if lid and not any(k.startswith(f"THE_ARCHITECT.talk.{lid}.") for k in anc):
                anc.update(architect_loc(oc, lid, lang))
    return files


# ---------------------------------------------------------------------------
# 프로젝트 쓰기
# ---------------------------------------------------------------------------
def _write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def _copy_img(src, dst):
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    shutil.copyfile(src, dst)


def _image_output_paths(project, previous=False):
    """Return tool-managed image paths relative to the resource root."""
    import fxbtn
    import pets as PT

    paths = set()

    def valid_id(value):
        return isinstance(value, str) and bool(ID_RE.match(value))

    def include_source(source):
        return bool(source) if previous else bool(source) and os.path.isfile(source)

    for card in project.get("cards", []):
        item_id = card.get("id", "")
        if valid_id(item_id) and include_source(card.get("image")):
            stem = img_stem("card", card)
            paths.update((f"images/card_portraits/{stem}.png",
                          f"images/card_portraits/big/{stem}.png"))
    for relic in project.get("relics", []):
        item_id = relic.get("id", "")
        if valid_id(item_id) and include_source(relic.get("image")):
            stem = img_stem("relic", relic)
            paths.update((f"images/relics/{stem}.png", f"images/relics/{stem}_outline.png",
                          f"images/relics/big/{stem}.png"))
    for potion in project.get("potions", []):
        item_id = potion.get("id", "")
        if valid_id(item_id) and include_source(potion.get("image")):
            stem = img_stem("potion", potion)
            paths.update((f"images/potions/{stem}.png", f"images/potions/outline/{stem}.png"))
    for ich in imported_characters(project):
        for field, suffix in ICHAR_FILES.items():
            if include_source(ich.get(field)):
                paths.add(f"images/charui/{ichar_stem(ich)}_{suffix}.png")
        if include_source(ich.get("combat_image")):
            for key in ("attack_frames", "hit_frames"):
                for i, frame in enumerate(ich.get(key, [])):
                    if include_source(frame.get("image")):
                        paths.add(f"images/charui/{ichar_stem(ich)}_{key}_{i}.png")
    # Powers receive a generated placeholder when they have no custom image.
    for power in project.get("powers", []):
        item_id = power.get("id", "")
        if valid_id(item_id):
            stem = img_stem("power", power)
            paths.update((f"images/powers/{stem}.png", f"images/powers/big/{stem}.png"))

    # These features always write either a custom icon or a generated placeholder.
    for pet in PT.pets(project):
        item_id = pet.get("id", "")
        if valid_id(item_id):
            paths.add(f"images/pets/{item_id}.png")
    for orb in gimmick.orbs(project):
        item_id = orb.get("id", "")
        if valid_id(item_id):
            paths.add(f"images/orbs/{item_id}_orb.png")
    for _, filename in gimmick.image_jobs(project):
        paths.update((f"images/powers/{filename}", f"images/powers/big/{filename}"))

    # Effect images are copied only when their source exists.
    for effect in (project.get("gimmicks") or {}).get("effects", []):
        effect_id = effect.get("id", "")
        if not valid_id(effect_id):
            continue
        for index, shape in enumerate(effect.get("shapes", [])):
            source = shape.get("image") or ""
            if shape.get("type") == "image" and include_source(source):
                paths.add(f"images/fx/{effect_id}_{index}.png")

    # 카드 테두리 '내 그림'
    for style in project.get("card_frames") or []:
        if not valid_id(style.get("id", "")):
            continue
        for part in cardframe.PARTS:
            p = style.get(part) or {}
            if p.get("mode") != "image":
                continue
            for key, source in (p.get("images") or {}).items():
                if include_source(source):
                    paths.add(f"images/card_frames/{cardframe.file_name(style, part, key)}")

    ch = project.get("character") or {}
    if ch.get("enabled"):
        fields = (("energy_icon_image", "big_energy.png"), ("energy_text_icon_image", "text_energy.png"),
                  ("icon_image", "character_icon.png"), ("select_image", "char_select.png"),
                  ("map_marker_image", "map_marker.png"), ("select_bg_image", "char_select_bg.png"))
        for field, filename in fields:
            if include_source(ch.get(field)):
                paths.add(f"images/charui/{filename}")
        locked = ch.get("select_locked_image") or ch.get("select_image")
        if include_source(locked):
            paths.add("images/charui/char_select_locked.png")
        if include_source(ch.get("combat_image")):
            paths.add("images/charui/combat.png")
            for key in ("attack_frames", "hit_frames"):
                for i, frame in enumerate(ch.get(key, [])):
                    if include_source(frame.get("image")):
                        paths.add(f"images/charui/{key}_{i}.png")
    return paths


def _cleanup_stale_image_outputs(previous, current, res, log=print):
    """Remove only image paths that the previous project generated."""
    lexical_base = os.path.abspath(res)
    base = os.path.realpath(res)
    stale = _image_output_paths(previous, previous=True) - _image_output_paths(current)
    for relative in stale:
        target = os.path.abspath(os.path.join(lexical_base, relative))
        resolved = os.path.realpath(target)
        try:
            if os.path.normcase(os.path.commonpath((lexical_base, target))) != os.path.normcase(lexical_base):
                continue
            if os.path.normcase(os.path.commonpath((base, resolved))) != os.path.normcase(base):
                continue
            os.remove(target)
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            log(f"[경고] 이전 그림을 정리하지 못했습니다 ({relative}): {exc}")


def generate(project, out_root, settings=None, log=print):
    """out_root/<ModId>/ 에 프로젝트를 만든다. 생성된 폴더 경로를 돌려준다."""
    settings = settings or {}
    project = normalize(copy.deepcopy(project))
    errors, warnings = validate(project)
    if errors:
        raise ValueError("\n".join(errors))
    for w in warnings:
        log("[경고] " + w)

    mid = project["mod"]["id"]
    root = os.path.join(out_root, mid)
    code = os.path.join(root, f"{mid}Code")
    res = os.path.join(root, mid)
    os.makedirs(root, exist_ok=True)

    old_project = None
    old_project_path = os.path.join(root, "modmaker_project.json")
    if os.path.isfile(old_project_path):
        try:
            with open(old_project_path, encoding="utf-8") as f:
                previous_data = json.load(f)
            if isinstance(previous_data, dict):
                old_project = normalize(previous_data)
        except Exception as exc:  # noqa: BLE001 - keep generation available if old metadata is damaged
            log(f"[경고] 이전 생성 정보를 읽지 못해 오래된 그림 정리를 건너뜁니다: {exc}")

    # 이전에 생성된 코드는 생성 표시가 있는 파일만 정리한다.
    for sub in ("Cards", "Relics", "Potions", "Powers", "Character", "Extensions", "Gimmicks"):
        p = os.path.join(code, sub)
        if os.path.isdir(p):
            for fn in os.listdir(p):
                fp = os.path.join(p, fn)
                if fn.endswith(".cs") and _is_generated(fp):
                    os.remove(fp)
    # Localization files below are updated individually; preserve custom files.

    # 설정 파일
    _write(os.path.join(root, f"{mid}.csproj"), gen_csproj(project))
    _write(os.path.join(root, f"{mid}.json"), gen_manifest(project))
    _write(os.path.join(root, "Directory.Build.props"), gen_build_props(settings))
    _write(os.path.join(root, "Sts2PathDiscovery.props"), STS2_PATH_DISCOVERY)
    _write(os.path.join(root, "project.godot"), gen_project_godot(project))
    _write(os.path.join(root, "export_presets.cfg"), gen_export_presets(project))
    _write(os.path.join(root, ".gitignore"), GITIGNORE)
    _write(os.path.join(root, "README.md"), gen_readme(project))
    with open(os.path.join(root, "modmaker_project.json"), "w", encoding="utf-8") as f:
        json.dump(project, f, ensure_ascii=False, indent=2)

    # 코드 (블록이 만드는 선택지 카드·예약 파워는 extras 에 모은다)
    extras = []
    _EXTRAS_SINK["x"] = extras
    try:
        _generate_code(project, code, mid)
        import fxbtn
        import pets as PT
        ui_fx = fxbtn.gen_runtime(project, extras)  # 버튼 블록이 만드는 클래스도 extras 에 들어가므로 먼저
        _write(os.path.join(code, "Gimmicks", "Pets.cs"), PT.gen_runtime(project, extras))
        _write(os.path.join(code, "Gimmicks", "Gimmicks.cs"), gimmick.gen_runtime(project, extras))
        _write(os.path.join(code, "Gimmicks", "ButtonsAndEffects.cs"), ui_fx)
    finally:
        _EXTRAS_SINK.pop("x", None)
    ch = project["character"]
    _write_takeover(project, root, code, res, log)

    # 현지화 (eng, kor)
    for lang, folder in (("en", "eng"), ("ko", "kor"), ("zh", "zhs")):
        for name, data in gen_localization(project, lang, extras).items():
            _write(os.path.join(res, "localization", folder, f"{name}.json"),
                   json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    _write_images(project, res, ch)
    if old_project is not None:
        _cleanup_stale_image_outputs(old_project, project, res, log)
    log(f"프로젝트 생성 완료: {root}")
    return root


def _write_takeover(project, root, code, res, log=print):
    """통째로 가져온 모드: 원래 C# 코드(항목 파일 제외)·원래 리소스 팩·원래 리소스 폴더를 넣는다."""
    orig_dir = os.path.join(code, TAKEOVER_CODE_DIR)
    shutil.rmtree(orig_dir, ignore_errors=True)
    pck_dst = os.path.join(root, f"{project['mod']['id']}{TAKEOVER_PCK_SUFFIX}.pck")
    t = takeover(project)
    if not t:
        if os.path.isfile(pck_dst):
            os.remove(pck_dst)
        return
    skip = {os.path.normcase(os.path.normpath(p)) for p in t.get("exclude", [])}
    # 가져온 항목의 원래 파일은 넣지 않는다 (그 클래스는 이 프로그램이 같은 이름으로 다시 만든다)
    n = 0
    for dp, _dirs, files in os.walk(t["src"]):
        for fn in files:
            if not fn.endswith(".cs"):
                continue
            full = os.path.join(dp, fn)
            rel = os.path.relpath(full, t["src"])
            if os.path.normcase(os.path.normpath(rel)) in skip:
                continue
            dst = os.path.join(orig_dir, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(full, dst)
            n += 1
    if n:
        # 디컴파일한 Godot 클래스는 생성기가 만들던 코드를 이미 품고 있어 partial 이 아니어도 된다 → 그 검사만 끈다
        _write(os.path.join(orig_dir, ".editorconfig"),
               "# StS2 모드 메이커: 원래 모드 코드 (디컴파일)\n[*.cs]\ndotnet_diagnostic.GD0001.severity = none\n")
    if t.get("res_dir") and os.path.isdir(t["res_dir"]):
        # 소스 프로젝트의 리소스 폴더: 원래 파일을 먼저 깔고 (뒤에서 쓰는 내 파일이 덮어씀)
        shutil.copytree(t["res_dir"], res, dirs_exist_ok=True,
                        ignore=shutil.ignore_patterns("*.import", ".godot"))
    if t.get("pck") and os.path.isfile(t["pck"]):
        shutil.copyfile(t["pck"], pck_dst)
    elif os.path.isfile(pck_dst):
        os.remove(pck_dst)
    log(f"원래 모드 코드 {n}개 파일을 넣었습니다 ({TAKEOVER_CODE_DIR}/).")


def _generate_code(project, code, mid):
    _write(os.path.join(code, "MainFile.cs"), gen_mainfile(project))
    _write(os.path.join(code, "Extensions", "StringExtensions.cs"), gen_extensions(project))
    bc, br, bp, bpw = gen_bases(project)
    _write(os.path.join(code, "Powers", f"{mid}Power.cs"), bpw)
    for pw in project["powers"]:
        _write(os.path.join(code, "Powers", f"{pascal(pw['id'])}Power.cs"), gen_power(project, pw))
    _write(os.path.join(code, "Cards", f"{mid}Card.cs"), bc)
    _write(os.path.join(code, "Relics", f"{mid}Relic.cs"), br)
    _write(os.path.join(code, "Potions", f"{mid}Potion.cs"), bp)
    for c in project["cards"]:
        _write(os.path.join(code, "Cards", f"{pascal(c['id'])}.cs"), gen_card(project, c))
    _write(os.path.join(code, "Cards", f"{mid}CardFrames.cs"), cardframe.gen_runtime(project))
    for r in project["relics"]:
        _write(os.path.join(code, "Relics", f"{pascal(r['id'])}.cs"), gen_relic(project, r))
    for p in project["potions"]:
        _write(os.path.join(code, "Potions", f"{pascal(p['id'])}.cs"), gen_potion(project, p))
    ch = project["character"]
    if ch["enabled"]:
        cls = pascal(ch["id"])
        _write(os.path.join(code, "Character", f"{cls}.cs"), gen_character(project))
        _write(os.path.join(code, "Character", f"{cls}ArchitectGuard.cs"), gen_architect_safety(project))
        scene = os.path.join(os.path.dirname(code), mid, "scenes", SELECT_BG_SCENE)    # code = <root>/<mid>Code
        if ch.get("select_bg_image") and os.path.isfile(ch["select_bg_image"]):
            _write(scene, gen_select_bg_scene(project))
        elif os.path.isfile(scene):
            try:
                with open(scene, encoding="utf-8") as fh:
                    mine = "StS2 모드 메이커" in fh.readline()
                if mine:
                    os.remove(scene)     # 배경 그림을 뺐으면 그 장면도 치운다 (깨진 참조로 내보내기 실패 방지)
            except OSError:
                pass
        cp, rp, pp = gen_pools(project)
        _write(os.path.join(code, "Character", f"{cls}CardPool.cs"), cp)
        _write(os.path.join(code, "Character", f"{cls}RelicPool.cs"), rp)
        _write(os.path.join(code, "Character", f"{cls}PotionPool.cs"), pp)
    # 통째로 가져온 모드의 캐릭터들 (원래 이름 그대로, 고친 값만 다시 만든다)
    scenes = os.path.join(os.path.dirname(code), mid, "scenes")
    for ich in imported_characters(project):
        _write(os.path.join(code, "Character", f"{ich['class']}.cs"), gen_imported_character(project, ich))
        scene = os.path.join(scenes, f"{ichar_stem(ich)}_select_bg.tscn")
        if ich.get("select_bg_image") and os.path.isfile(ich["select_bg_image"]):
            _write(scene, gen_select_bg_scene(project, f"{ichar_stem(ich)}_select_bg.png"))
        elif os.path.isfile(scene):
            os.remove(scene)


def _write_images(project, res, ch):
    img = os.path.join(res, "images")
    color = ch["color"] if ch["enabled"] else "#8a8a8a"
    placeholders = [
        (os.path.join(img, "card_portraits", "card.png"), 250, 190, "rect", "#6b7a8f"),
        (os.path.join(img, "card_portraits", "big", "card.png"), 500, 380, "rect", "#6b7a8f"),
        (os.path.join(img, "card_portraits", "choice.png"), 250, 190, "rect", "#8a6fb0"),
        (os.path.join(img, "card_portraits", "big", "choice.png"), 500, 380, "rect", "#8a6fb0"),
        (os.path.join(img, "relics", "relic.png"), 94, 94, "circle", "#c9a227"),
        (os.path.join(img, "relics", "big", "relic.png"), 256, 256, "circle", "#c9a227"),
        (os.path.join(img, "potions", "potion.png"), 256, 256, "potion", "#4aa3df"),
        (os.path.join(img, "powers", "power.png"), 64, 64, "circle", "#9b9b9b"),
        (os.path.join(img, "orbs", "orb.png"), 64, 64, "circle", "#7fb3ff"),
        (os.path.join(img, "fx", "fx.png"), 64, 64, "circle", "#ffffff"),
        (os.path.join(img, "powers", "big", "power.png"), 256, 256, "circle", "#9b9b9b"),
        (os.path.join(img, "charui", "big_energy.png"), 74, 74, "circle", color),
        (os.path.join(img, "charui", "text_energy.png"), 24, 24, "circle", color),
        (os.path.join(res, "mod_image.png"), 420, 420, "circle", color),
    ]
    for path, w, h, shape, col in placeholders:
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pngmake.write_png(path, w, h, shape, col)
    for path, w, h, shape in ((os.path.join(img, "relics", "relic_outline.png"), 94, 94, "circle"),
                              (os.path.join(img, "potions", "outline", "potion.png"), 256, 256, "potion")):
        if not os.path.exists(path):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            pngmake.write_png(path, w, h, shape, "#ffffff", outline_only=True)

    for ich in imported_characters(project):
        for field, suffix in ICHAR_FILES.items():
            if ich.get(field) and os.path.isfile(ich[field]):
                _copy_img(ich[field], os.path.join(img, "charui", f"{ichar_stem(ich)}_{suffix}.png"))

    for c in project["cards"]:
        if c.get("image") and os.path.isfile(c["image"]):
            stem = img_stem("card", c)
            _copy_img(c["image"], os.path.join(img, "card_portraits", f"{stem}.png"))
            _copy_img(c["image"], os.path.join(img, "card_portraits", "big", f"{stem}.png"))
    for r in project["relics"]:
        if r.get("image") and os.path.isfile(r["image"]):
            stem = img_stem("relic", r)
            _copy_img(r["image"], os.path.join(img, "relics", f"{stem}.png"))
            _copy_img(r["image"], os.path.join(img, "relics", f"{stem}_outline.png"))
            _copy_img(r["image"], os.path.join(img, "relics", "big", f"{stem}.png"))
    for p in project["potions"]:
        if p.get("image") and os.path.isfile(p["image"]):
            stem = img_stem("potion", p)
            _copy_img(p["image"], os.path.join(img, "potions", f"{stem}.png"))
            _copy_img(p["image"], os.path.join(img, "potions", "outline", f"{stem}.png"))
    for pw in project["powers"]:
        name = f"{img_stem('power', pw)}.png"
        small, big = os.path.join(img, "powers", name), os.path.join(img, "powers", "big", name)
        if pw.get("image") and os.path.isfile(pw["image"]):
            _copy_img(pw["image"], small)
            _copy_img(pw["image"], big)
        else:
            col = "#4caf50" if pw.get("type") == "Buff" else "#8e44ad"
            for path, size in ((small, 64), (big, 256)):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                pngmake.write_png(path, size, size, "circle", col)
    import fxbtn
    import pets as PT
    PT.write_images(project, img)
    pet_placeholder = os.path.join(img, "pets", "pet.png")
    if not os.path.exists(pet_placeholder):
        pngmake.write_png(pet_placeholder, 150, 170, "circle", "#78aadc", "#2a3448")
    for src, name in fxbtn.image_jobs(project):
        if src and os.path.isfile(src):
            _copy_img(src, os.path.join(img, "fx", name))
    for src, name, col in gimmick.orb_image_jobs(project):
        dst = os.path.join(img, "orbs", name)
        if src and os.path.isfile(src):
            _copy_img(src, dst)
        else:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            pngmake.write_png(dst, 64, 64, "circle", col if col.lower() not in ("#ffffff", "ffffff") else "#7fb3ff")
    for src, name in gimmick.image_jobs(project):
        small, big = os.path.join(img, "powers", name), os.path.join(img, "powers", "big", name)
        if src and os.path.isfile(src):
            _copy_img(src, small)
            _copy_img(src, big)
        else:
            for path, size in ((small, 64), (big, 256)):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                pngmake.write_png(path, size, size, "circle", "#d6457a" if "summon" in name else "#b0a060")
    for src, name in cardframe.image_jobs(project):
        _copy_img(src, os.path.join(img, "card_frames", name))
    if ch["enabled"]:
        for field, name in (("energy_icon_image", "big_energy.png"), ("energy_text_icon_image", "text_energy.png"),
                            ("icon_image", "character_icon.png"), ("select_image", "char_select.png"),
                            ("map_marker_image", "map_marker.png")):
            if ch.get(field) and os.path.isfile(ch[field]):
                _copy_img(ch[field], os.path.join(img, "charui", name))
        locked = ch.get("select_locked_image") or ch.get("select_image")
        if locked and os.path.isfile(locked):
            _copy_img(locked, os.path.join(img, "charui", "char_select_locked.png"))
        if ch.get("select_bg_image") and os.path.isfile(ch["select_bg_image"]):
            _copy_img(ch["select_bg_image"], os.path.join(img, "charui", "char_select_bg.png"))


def _is_generated(path):
    try:
        with open(path, encoding="utf-8") as f:
            return "StS2 모드 메이커" in f.readline()
    except OSError:
        return False


def gen_readme(project):
    mid = project["mod"]["id"]
    return f"""# {project['mod']['name']} ({mid})

슬레이 더 스파이어 2 모드 메이커로 생성한 BaseLib 기반 모드 프로젝트입니다.

## 빌드

```
dotnet build
```
`{mid}.dll`과 `{mid}.json`이 게임의 `mods/{mid}/` 폴더로 복사됩니다.

```
dotnet publish
```
위 작업에 더해, MegaDot(Godot 4.5.1 mono)로 그림·현지화가 들어 있는 `{mid}.pck`를 만들어 같은 폴더에 넣습니다.
`Directory.Build.props`의 `GodotPath`가 올바르게 설정되어 있어야 합니다.

BaseLib 모드도 `mods/` 폴더에 설치되어 있어야 합니다.

## 폴더 구조
- `{mid}Code/` C# 코드 (모드 메이커가 만든 파일은 첫 줄에 표시가 있으며, 다시 생성하면 덮어씁니다)
- `{mid}/localization/kor`, `eng` 텍스트
- `{mid}/images/` 그림 (card_portraits, relics, potions, charui)

## 게임 안에서 확인
`~` 키로 콘솔을 열고 전투 중에 `card {loc_id(project, project['cards'][0]['id']) if project['cards'] else 'MODID-CARD'}` 처럼 입력하면 카드를 얻을 수 있습니다.
"""

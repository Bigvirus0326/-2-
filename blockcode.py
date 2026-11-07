"""
블록 코딩 -> C# 변환.

프로그램 = 블록 목록. 블록 = {"op": 이름, "args": {...}, "body": [...], "else": [...]}
값(value) = {"t": "num"|"stack"|"stat"|"count"|"energy"|"amount"|"round"|"rand"|"var"|"op", ...}
조건(cond) = {"t": "cmp"|"chance"|"has"|"and"|"or"|"not", ...}

같은 블록이 카드 / 유물 / 물약 / 파워 어디에 있든 그 자리에 맞는 C# 를 만든다 (modgen._Ctx 이름 사용).
"""
from __future__ import annotations

import copy

# ---------------------------------------------------------------------------
# 블록 정의 (팔레트와 화면이 같이 쓴다)
# ---------------------------------------------------------------------------
CATS = {
    "action": ("행동", "#4c97ff"),
    "card": ("카드 조작", "#9966ff"),
    "flow": ("흐름", "#ffab19"),
    "var": ("변수", "#ff8c1a"),
    "gimmick": ("기믹 (소환·자원·선택)", "#d6457a"),
    "class": ("직업 시스템 (구체·별·골골이)", "#2a9d8f"),
    "fx": ("이펙트 · 버튼", "#e07a1f"),
}

# 템플릿의 {이름} 자리에 입력 칸이 들어간다.
SPECS = {
    "source_amount": {"cat":"action", "ko":"원본 효과 수치 {amount}", "args":{"amount":("value", {"t":"num","v":1})}},
    "source_step": {"cat":"action", "ko":"원본 코드 {source}", "args":{"source":("source", "")}},
    "source_hit": {"cat":"action", "ko":"{target}에게 피해 {stat} · {hits}회", "args":{"target":("who_one","target"), "stat":("raw_stat","V0"), "hits":("int",1)}},
    "original_play": {"cat": "action", "ko": "원본 카드 사용 효과 실행", "args": {}},
    # 원본 C# 를 풀어 만든 블록 (csblocks). 칸 이름·종류는 블록마다 다르다 (block_caption / arg_kind).
    "src_call": {"cat": "action", "ko": "원본 호출", "args": {}},
    "src_loop": {"cat": "flow", "ko": "원본 {head}", "args": {"head": ("code", "")}, "body": True},
    "damage": {"cat": "action", "ko": "{who}에게 피해 {amount}를 {hits}번  힘·약화 적용 {powered}",
               "args": {"who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 6}),
                        "hits": ("int", 1), "powered": ("bool", True)}},
    "block": {"cat": "action", "ko": "방어도 {amount} 얻기", "args": {"amount": ("value", {"t": "num", "v": 5})}},
    "lose_block": {"cat": "action", "ko": "{who}의 방어도 {amount} 없애기",
                   "args": {"who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 5})}},
    "draw": {"cat": "action", "ko": "카드 {amount}장 뽑기", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "energy": {"cat": "action", "ko": "에너지 {amount} 얻기", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "heal": {"cat": "action", "ko": "{who} 체력 {amount} 회복",
             "args": {"who": ("who_multi", "self"), "amount": ("value", {"t": "num", "v": 3})}},
    "lose_hp": {"cat": "action", "ko": "{who} 체력 {amount} 잃기 (방어도 무시)",
                "args": {"who": ("who_multi", "self"), "amount": ("value", {"t": "num", "v": 2})}},
    "max_hp": {"cat": "action", "ko": "최대 체력 {amount} 증가", "args": {"amount": ("value", {"t": "num", "v": 2})}},
    "gold": {"cat": "action", "ko": "골드 {amount} 얻기", "args": {"amount": ("value", {"t": "num", "v": 10})}},
    "apply_power": {"cat": "action", "ko": "{who}에게 {power} {amount} 부여",
                    "args": {"who": ("who_multi", "target"), "power": ("power", "Weak"),
                             "amount": ("value", {"t": "num", "v": 1})}},
    "remove_power": {"cat": "action", "ko": "{who}의 {power} {amount} 제거 (0 = 전부)",
                     "args": {"who": ("who_multi", "target"), "power": ("power", "Weak"),
                              "amount": ("value", {"t": "num", "v": 0})}},
    "flash": {"cat": "action", "ko": "반짝임 표시 (유물·파워)", "args": {}},
    "hand": {"cat": "card", "ko": "손패의 {ctype} {which} {count}장 {action}",
             "args": {"ctype": ("card_filter", "Any"), "which": ("which", "random"),
                      "count": ("value", {"t": "num", "v": 1}), "action": ("hand_action", "upgrade")}},
    "keyword_this": {"cat": "card", "ko": "이 카드에 {keyword} {action}",
                     "args": {"keyword": ("keyword", "Retain"), "action": ("kw_action", "add")}},
    "keyword_cards": {"cat": "card", "ko": "{where}의 {ctype} {which} {count}장에 {keyword} {action}",
                      "args": {"where": ("kw_where", "hand"), "ctype": ("card_filter", "Any"), "which": ("which", "all"),
                               "count": ("value", {"t": "num", "v": 1}), "keyword": ("keyword", "Retain"),
                               "action": ("kw_action", "add")}},
    "add_card": {"cat": "card", "ko": "{card} {count}장을 {pile}에 만들기",
                 "args": {"card": ("card", "this"), "count": ("value", {"t": "num", "v": 1}), "pile": ("pile", "Hand")}},
    "if": {"cat": "flow", "ko": "만약 {cond} 이면", "args": {"cond": ("cond", {"t": "chance", "pct": {"t": "num", "v": 50}})},
           "body": True},
    "if_else": {"cat": "flow", "ko": "만약 {cond} 이면", "args": {"cond": ("cond", {"t": "chance", "pct": {"t": "num", "v": 50}})},
                "body": True, "else": True, "sections": [("else", "아니면")]},
    "repeat": {"cat": "flow", "ko": "{times}번 반복", "args": {"times": ("value", {"t": "num", "v": 2})}, "body": True},
    "each_enemy": {"cat": "flow", "ko": "모든 적 각각에게 (안에서 '그 적')", "args": {}, "body": True},
    "random_enemy": {"cat": "flow", "ko": "무작위 적 1명에게 (안에서 '그 적')", "args": {}, "body": True},
    "set_var": {"cat": "var", "ko": "변수 {name} 을(를) {amount}(으)로 정하기",
                "args": {"name": ("varname", "a"), "amount": ("value", {"t": "num", "v": 0})}},
    "change_var": {"cat": "var", "ko": "변수 {name} 에 {amount} 더하기",
                   "args": {"name": ("varname", "a"), "amount": ("value", {"t": "num", "v": 1})}},
    # ---- 기믹 ----
    "summon": {"cat": "gimmick", "ko": "{summon} 소환 (있으면 단계 상승)", "args": {"summon": ("summon", "")}},
    "command": {"cat": "gimmick", "ko": "{summon} 지금 행동시키기 (지휘)", "args": {"summon": ("summon_any", "*")}},
    "unsummon": {"cat": "gimmick", "ko": "{summon} 돌려보내기", "args": {"summon": ("summon", "")}},
    "pay": {"cat": "gimmick", "ko": "{power} {amount} 을(를) 낼 수 있으면 내고",
            "args": {"power": ("power", ""), "amount": ("value", {"t": "num", "v": 1})},
            "body": True, "else": True, "sections": [("else", "낼 수 없으면")]},
    "choice": {"cat": "gimmick", "ko": "하나 고르기  ① {opt1}",
               "args": {"opt1": ("label", {"ko": "공격", "en": "Attack"}), "opt2": ("label", {"ko": "방어", "en": "Defend"}),
                        "opt3": ("label", {"ko": "", "en": ""})},
               "body": True, "else": True, "third": True,
               "sections": [("else", "② {opt2}"), ("third", "③ {opt3}  (이름을 비우면 둘 중 고르기)")]},
    "pick": {"cat": "gimmick", "ko": "{pile}에서 {ctype} {count}장 골라서 {action}",
             "args": {"pile": ("pick_pile", "Discard"), "ctype": ("card_filter", "Any"),
                      "count": ("value", {"t": "num", "v": 1}), "action": ("pick_action", "hand")}},
    "delayed": {"cat": "gimmick", "ko": "{when} {times}번 실행 (예약)",
                "args": {"when": ("delay_when", "start"), "times": ("value", {"t": "num", "v": 1})}, "body": True},
    # ---- 직업 시스템 ----
    "channel": {"cat": "class", "ko": "구체 {orb} {count}개 영창",
                "args": {"orb": ("orb", "Lightning"), "count": ("value", {"t": "num", "v": 1})}},
    "evoke": {"cat": "class", "ko": "{which} 구체를 {count}번 발현",
              "args": {"which": ("evoke_which", "front"), "count": ("value", {"t": "num", "v": 1})}},
    "orb_passive_all": {"cat": "class", "ko": "모든 구체의 지속 효과 발동", "args": {}},
    "orb_slots": {"cat": "class", "ko": "구체 슬롯 {amount}개 추가 (음수면 감소)", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "orb_grow": {"cat": "class", "ko": "이 구체의 발현 수치 +{amount} (구체 전용)", "args": {"amount": ("value", {"t": "num", "v": 2})}},
    "stars": {"cat": "class", "ko": "별 {amount} 얻기 (음수면 잃기)", "args": {"amount": ("value", {"t": "num", "v": 1})}},
    "forge": {"cat": "class", "ko": "단조 {amount}", "args": {"amount": ("value", {"t": "num", "v": 5})}},
    "osty_summon": {"cat": "class", "ko": "골골이 소환 {amount} (있으면 최대 체력 증가)", "args": {"amount": ("value", {"t": "num", "v": 5})}},
    "osty_attack": {"cat": "class", "ko": "골골이가 {who}에게 피해 {amount}를 {hits}번",
                    "args": {"who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 6}), "hits": ("int", 1)}},
    "osty_kill": {"cat": "class", "ko": "골골이 희생 (죽이기)", "args": {}},
    "pet_summon": {"cat": "class", "ko": "동료 {pet} 소환 {amount} (있으면 최대 체력 증가, 쓰러졌으면 되살림)",
                   "args": {"pet": ("pet", ""), "amount": ("value", {"t": "num", "v": 5})}},
    "pet_attack": {"cat": "class", "ko": "동료 {pet} 가 {who}에게 피해 {amount}를 {hits}번",
                   "args": {"pet": ("pet", ""), "who": ("who_multi", "target"), "amount": ("value", {"t": "num", "v": 6}),
                            "hits": ("int", 1)}},
    "pet_act": {"cat": "class", "ko": "동료 {pet} 지금 행동", "args": {"pet": ("pet", "")}},
    "pet_kill": {"cat": "class", "ko": "동료 {pet} 희생 (쓰러뜨리기)", "args": {"pet": ("pet", "")}},
    # ---- 이펙트 · 버튼 ----
    "fx": {"cat": "fx", "ko": "이펙트 {fx} 를 {who} 위치에 재생", "args": {"fx": ("fx", ""), "who": ("who_multi", "self")}},
    "button_on": {"cat": "fx", "ko": "버튼 {button} 켜기", "args": {"button": ("button", "")}},
    "button_off": {"cat": "fx", "ko": "버튼 {button} 끄기", "args": {"button": ("button", "")}},
}
EVOKE_WHICH = [("front", "맨 앞"), ("last", "맨 뒤")]
ORB_COUNTS = [("count", "구체 수"), ("slots", "구체 슬롯 수"), ("empty", "빈 구체 슬롯 수")]
OSTY_STATS = [("hp", "골골이 현재 체력"), ("maxhp", "골골이 최대 체력")]
PALETTE = [
    ("action", ["original_play", "source_step", "damage", "block", "lose_block", "draw", "energy", "heal", "lose_hp", "max_hp", "gold",
                "apply_power", "remove_power", "flash"]),
    ("card", ["hand", "add_card", "keyword_this", "keyword_cards"]),
    ("flow", ["if", "if_else", "repeat", "each_enemy", "random_enemy"]),
    ("var", ["set_var", "change_var"]),
    ("gimmick", ["pay", "summon", "command", "unsummon", "choice", "pick", "delayed"]),
    ("class", ["channel", "evoke", "orb_passive_all", "orb_slots", "orb_grow", "stars", "forge",
               "osty_summon", "osty_attack", "osty_kill", "pet_summon", "pet_attack", "pet_act", "pet_kill"]),
    ("fx", ["fx", "button_on", "button_off"]),
]
BODY_KEYS = ("body", "else", "third")
PICK_PILES = [("Hand", "손패"), ("Draw", "뽑을 카드 더미"), ("Discard", "버린 카드 더미"), ("Exhaust", "소멸한 카드 더미")]
PICK_ACTIONS = [("hand", "손으로 가져오기"), ("top", "뽑을 더미 맨 위에 놓기"), ("exhaust", "소멸"), ("discard", "버리기"),
                ("upgrade", "강화 (이번 전투)")]
DELAY_WHEN = [("start", "다음 내 턴 시작에"), ("end", "이번 턴이 끝날 때")]
PLAYED_SCOPES = [("turn", "이번 턴에"), ("combat", "이번 전투에서")]

WHO = {"self": "나", "target": "대상", "it": "그 적", "all": "모든 적", "random": "무작위 적"}
WHO_EN = {"self": "you", "target": "the target", "it": "that enemy", "all": "ALL enemies", "random": "a random enemy"}
CARD_TYPES = [("Any", "아무"), ("Attack", "공격"), ("Skill", "스킬"), ("Power", "파워")]
WHICH = [("random", "무작위로"), ("all", "전부")]
HAND_ACTIONS = [("upgrade", "강화"), ("exhaust", "소멸"), ("discard", "버리기")]
KW_WHERE = [("hand", "손패"), ("draw", "뽑을 카드 더미"), ("discard", "버린 카드 더미"), ("all", "모든 카드 더미")]
KW_ACTIONS = [("add", "부여"), ("remove", "제거")]
PILES = [("Hand", "손패"), ("Draw", "뽑을 카드 더미"), ("Discard", "버린 카드 더미")]
STATS = [("hp", "현재 체력"), ("maxhp", "최대 체력"), ("block", "방어도")]
COUNTS = [("hand", "손패 카드 수"), ("draw", "뽑을 카드 수"), ("discard", "버린 카드 수"), ("exhaust", "소멸한 카드 수"),
          ("enemies", "살아 있는 적 수")]
CMP_OPS = [(">=", "≥"), (">", ">"), ("==", "="), ("<", "<"), ("<=", "≤"), ("!=", "≠")]
ARITH = [("+", "+"), ("-", "−"), ("*", "×"), ("/", "÷")]


def who_options(owner_kind, multi=True):
    opts = [("self", "나")]
    if owner_kind in ("card", "potion"):
        opts.append(("target", "대상"))
    if owner_kind == "power":
        opts[0] = ("self", "나(소유자)")
        opts.append(("target", "상대(트리거)"))
    if owner_kind in ("summon", "button"):
        opts[0] = ("self", "나(플레이어)")
    if owner_kind == "pet":
        opts[0] = ("self", "나(동료 자신)")
    opts.append(("it", "그 적 (반복 안)"))
    if multi:
        opts += [("all", "모든 적"), ("random", "무작위 적")]
    return opts


def new_block(op):
    spec = SPECS[op]
    b = {"op": op, "args": {k: copy.deepcopy(v[1]) for k, v in spec["args"].items()}}
    if spec.get("body"):
        b["body"] = []
    if spec.get("else"):
        b["else"] = []
    if spec.get("third"):
        b["third"] = []
    if op in ("summon", "unsummon"):
        b["args"]["summon"] = _first_summon()
    if op == "fx":
        p = _PROJECT_HINT.get("p") or {}
        fx = (p.get("gimmicks") or {}).get("effects") or []
        b["args"]["fx"] = fx[0]["id"] if fx else ""
    if op.startswith("pet_"):
        p = _PROJECT_HINT.get("p") or {}
        pt = (p.get("gimmicks") or {}).get("pets") or []
        b["args"]["pet"] = pt[0]["id"] if pt else ""
    if op in ("button_on", "button_off"):
        p = _PROJECT_HINT.get("p") or {}
        bt = (p.get("gimmicks") or {}).get("buttons") or []
        b["args"]["button"] = bt[0]["id"] if bt else ""
    if op == "pay":
        b["args"]["power"] = _first_custom_power()
    return b


_PROJECT_HINT = {}


def set_project_hint(project):
    """새 블록의 기본값(첫 소환수·첫 새 파워)을 고를 때 쓸 프로젝트."""
    _PROJECT_HINT["p"] = project


def _first_summon():
    p = _PROJECT_HINT.get("p") or {}
    s = (p.get("gimmicks") or {}).get("summons") or []
    return s[0]["id"] if s else ""


def _first_custom_power():
    p = _PROJECT_HINT.get("p") or {}
    pw = p.get("powers") or []
    return "c:" + pw[0]["id"] if pw else "Strength"


def block_caption(b):
    """블록에 보일 글 ({칸} 자리 포함). 원본에서 풀어낸 블록은 블록마다 다르다."""
    op = b.get("op")
    if op == "src_call":
        return (b.get("label") or "원본 호출") + "".join(f"  {s['name']} {{{s['key']}}}" for s in b.get("slots", []))
    if op == "src_loop":
        return "원본 {head}" if (b.get("args") or {}).get("head") else "묶음 { }"
    if op == "source_amount":
        return b.get("label", "효과") + " {amount}"
    return SPECS[op]["ko"]


def arg_kind(b, key):
    if b.get("op") == "src_call":
        s = next((s for s in b.get("slots", []) if s["key"] == key), None)
        return s["kind"] if s else "code"
    return SPECS[b["op"]]["args"][key][0]


def slot_info(b, key):
    return next((s for s in b.get("slots", []) if s["key"] == key), {}) if b.get("op") == "src_call" else {}


_ITEM_HINT = {}


def set_item_hint(item):
    """원본 변수 (DynamicVars) 이름표에 현재 수치를 보여 주려고 편집 중인 항목을 기억한다."""
    _ITEM_HINT["i"] = item


def _short_code(code, n=34):
    t = " ".join(str(code or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def walk(blocks):
    for b in blocks or []:
        yield b
        for k in BODY_KEYS:
            yield from walk(b.get(k))


def _label_text(v, lang):
    if isinstance(v, dict):
        order = (lang, "en", "ko") if lang == "zh" else (lang, "ko", "en")   # 중국어가 비면 영어 (이름 규칙과 같게)
        return next((v[l].strip() for l in order if (v.get(l) or "").strip()), "")
    return str(v or "").strip()


def _j(word, a, b):
    import modgen as M
    return M.josa(word, a, b)


def _describe_class(b, op, a, project, lang, V, W):
    import gimmick as G
    ko = lang == "ko"
    if op == "channel":
        om = G.orb_meta(project, a.get("orb")) or {"ko": "?", "en": "?"}
        n = om["ko"] if ko else om["en"]
        return f"[gold]{n}[/gold]{_j(n, '을', '를')} {V('count')}번 [gold]영창[/gold]합니다." if ko else \
            f"[gold]Channel[/gold] {V('count')} [gold]{n}[/gold]."
    if op == "evoke":
        front = a.get("which", "front") == "front"
        cnt = V("count")
        if ko:
            return f"{'맨 앞' if front else '맨 뒤'} 구체를 {cnt}번 [gold]발현[/gold]합니다."
        return f"[gold]Evoke[/gold] your {'next' if front else 'last'} Orb{'' if cnt == '1' else f' {cnt} times'}."
    if op == "orb_passive_all":
        return "모든 구체의 지속 효과를 발동합니다." if ko else "Trigger the passive of all your Orbs."
    if op == "orb_slots":
        return f"구체 슬롯을 {V('amount')}개 얻습니다." if ko else f"Gain {V('amount')} Orb Slot(s)."
    if op == "orb_grow":
        return f"이 구체의 발현 수치가 {V('amount')} 증가합니다." if ko else f"Increase this Orb's Evoke amount by {V('amount')}."
    if op == "stars":
        return f"[gold]별[/gold]을 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]Stars[/gold]."
    if op == "forge":
        return f"[gold]단조[/gold] {V('amount')}." if ko else f"[gold]Forge[/gold] {V('amount')}."
    if op == "osty_summon":
        return f"[gold]소환[/gold] {V('amount')}." if ko else f"[gold]Summon[/gold] {V('amount')}."
    if op == "osty_attack":
        hits = int(a.get("hits", 1) or 1)
        times = (f" {hits}번" if ko else f" {hits} times") if hits > 1 else ""
        if ko:
            who = "" if a.get("who") == "target" else f"{W('who')}에게 "
            return f"[gold]골골이[/gold]가 {who}피해를 {V('amount')}{'씩' if hits > 1 else ''}{times} 줍니다."
        return f"[gold]Osty[/gold] deals {V('amount')} damage{'' if a.get('who') == 'target' else ' to ' + W('who')}{times}."
    if op == "osty_kill":
        return "[gold]골골이[/gold]를 희생합니다." if ko else "Sacrifice [gold]Osty[/gold]."
    return ""


def _pet_name(project, pid, lang):
    import pets as PT
    p = PT.find_pet(project or {}, pid)
    return PT._txt(p, "name", lang) if p else str(pid or "?")


def _summon_name(project, sid, lang):
    if sid == "*":
        return "모든 소환수" if lang == "ko" else "all summons"
    import gimmick as G
    s = G.find_summon(project or {}, sid)
    return G._txt(s, "name", lang) if s else str(sid)


# ---------------------------------------------------------------------------
# 값 / 조건 설명 (화면 표시용 짧은 글)
# ---------------------------------------------------------------------------
def _pname(project, key, lang="ko"):
    import modgen as M
    pm = M.power_meta(project, key)
    return (pm["ko"] if lang == "ko" else pm["en"]) if pm else str(key)


def value_label(v, project=None, lang="ko", card=False):
    if not isinstance(v, dict):
        return str(v)
    t = v.get("t")
    if t == "num":
        n = _fmt(v.get("v", 0))
        up = v.get("up") or 0
        if up and card:
            return "{IfUpgraded:show:%s|%s}" % (_fmt(float(v.get("v", 0)) + float(up)), n)
        return n + (f"(+{_fmt(up)})" if up and project is None else "")
    if t == "stack":
        who = (WHO if lang == "ko" else WHO_EN).get(v.get("who", "self"), "")
        p = _pname(project, v.get("power"), lang) if project else v.get("power")
        return f"{who}의 [gold]{p}[/gold]" if lang == "ko" else f"{_poss(v.get('who'))} [gold]{p}[/gold]"
    if t == "stat":
        who = (WHO if lang == "ko" else WHO_EN).get(v.get("who", "self"), "")
        s = dict(STATS).get(v.get("stat"), "")
        if lang == "en":
            s = {"hp": "current HP", "maxhp": "Max HP", "block": "Block"}.get(v.get("stat"), "")
        return f"{who}의 {s}" if lang == "ko" else f"{_poss(v.get('who'))} {s}"
    if t == "count":
        if lang == "ko":
            return dict(COUNTS).get(v.get("what"), "")
        return {"hand": "cards in your hand", "draw": "cards in your draw pile", "discard": "cards in your discard pile",
                "exhaust": "exhausted cards", "enemies": "enemies"}.get(v.get("what"), "")
    if t == "energy":
        return "남은 에너지" if lang == "ko" else "your Energy"
    if t == "amount":
        return "[blue]{Amount}[/blue]"
    if t == "round":
        return "현재 턴 수" if lang == "ko" else "the turn number"
    if t == "rand":
        return f"{value_label(v.get('min'), project, lang, card)}~{value_label(v.get('max'), project, lang, card)}"
    if t == "var":
        return str(v.get("name", "a"))
    if t == "played":
        import gimmick as G
        f = v.get("filter", "Any")
        if lang == "ko":
            what = G.filter_word(project or {"gimmicks": {}}, f, "ko") if project else "카드"
            return f"{dict(PLAYED_SCOPES).get(v.get('scope'), '')} 사용한 {what} 수"
        what = G.filter_word(project or {"gimmicks": {}}, f, "en", plural=True) if project else "cards"
        return f"the number of {what} played {'this turn' if v.get('scope') == 'turn' else 'this combat'}"
    if t == "summons":
        return "소환수 수" if lang == "ko" else "your number of summons"
    if t == "orb_passive":
        return "[blue]{Passive}[/blue]"
    if t == "orb_evoke":
        return "[blue]{Evoke}[/blue]"
    if t == "orbs":
        import gimmick as G
        w = v.get("what", "count")
        om = G.orb_meta(project or {}, v.get("orb")) if v.get("orb") and w == "count" else None
        if lang == "ko":
            base = dict(ORB_COUNTS).get(w, "구체 수")
            return f"[gold]{om['ko']}[/gold] 구체 수" if om else base
        if om:
            return f"your [gold]{om['en']}[/gold] Orbs"
        return {"count": "your Orbs", "slots": "your Orb Slots", "empty": "your empty Orb Slots"}.get(w, "your Orbs")
    if t == "stars":
        return "[gold]별[/gold] 수" if lang == "ko" else "your [gold]Stars[/gold]"
    if t == "pet":
        n = _pet_name(project, v.get("pet"), lang)
        if lang == "ko":
            return f"[gold]{n}[/gold] {'최대 체력' if v.get('what') == 'maxhp' else '체력'}"
        return f"[gold]{n}'s[/gold] {'Max HP' if v.get('what') == 'maxhp' else 'HP'}"
    if t in ("star_x", "energy_x"):
        return "X"
    if t == "osty":
        if lang == "ko":
            return dict(OSTY_STATS).get(v.get("what"), "골골이 체력").replace("골골이", "[gold]골골이[/gold]")
        return "[gold]Osty's[/gold] " + ("Max HP" if v.get("what") == "maxhp" else "HP")
    if t == "event":
        return "그 수치" if lang == "ko" else "that amount"
    if t == "op":
        sym = dict(ARITH).get(v.get("op"), v.get("op"))
        return f"({value_label(v.get('a'), project, lang, card)} {sym} {value_label(v.get('b'), project, lang, card)})"
    if t == "dynvar":
        item = _ITEM_HINT.get("i") or {}
        rv = next((x for x in item.get("raw_vars", []) if x.get("name") == v.get("name")), None)
        if rv is None:
            return f"원본 변수 {v.get('name')}"
        up = rv.get("upgrade") or 0
        num = _fmt(rv.get("value", 0))
        if card and up:
            num = "{IfUpgraded:show:%s|%s}" % (_fmt(float(rv.get("value") or 0) + float(up)), num)
        elif up:
            num += f"(+{_fmt(up)})"
        return f"{v.get('name')}={num}" if lang == "ko" else num
    if t == "src":
        return "C# " + _short_code(v.get("code"))
    return "?"


def _visible(text):
    """조사 판단용: [태그] 를 빼고, {IfUpgraded:show:A|B} 는 B(강화 전)로."""
    import re
    t = re.sub(r"\{IfUpgraded:show:[^|}]*\|([^}]*)\}", r"\1", str(text))
    t = re.sub(r"\[/?[a-z]+\]", "", t)
    t = re.sub(r"\{[^}]*\}", "0", t)
    return t.strip().rstrip(")").strip()


_DIGIT_JONG = {"0": "ㅇ", "1": "ㄹ", "3": "ㅁ", "6": "ㄱ", "7": "ㄹ", "8": "ㄹ"}   # 영 일 삼 육 칠 팔


def _jong(word):
    """마지막 글자의 받침 ('' = 없음). 숫자·영어는 읽는 소리로."""
    t = _visible(word)
    if not t:
        return ""
    ch = t[-1]
    if "가" <= ch <= "힣":
        j = (ord(ch) - 0xAC00) % 28
        return "" if j == 0 else ("ㄹ" if j == 8 else "x")
    if ch.isdigit():
        return _DIGIT_JONG.get(ch, "")
    if ch.upper() in "LMNR":          # 엘 엠 엔 알
        return "ㄹ" if ch.upper() in "LR" else "x"
    return ""


def _jj(word, a, b):
    """받침 있으면 a(이/을/과), 없으면 b(가/를/와)."""
    return a if _jong(word) else b


def _ro(word):
    j = _jong(word)
    return "으로" if j and j != "ㄹ" else "로"


def cmp_text(c, project, lang, card, conditional=False):
    """비교 조건을 말로: '별 수가 3 이상' / 조건문이면 '별 수가 3 이상이면'."""
    A = value_label(c.get("a"), project, lang, card)
    Bv = value_label(c.get("b"), project, lang, card)
    op = c.get("op", ">=")
    if lang == "ko":
        subj = f"{A}{_jj(A, '이', '가')}"
        stem, tail = {
            ">=": (f"{subj} {Bv} 이상", "이면"),
            "<=": (f"{subj} {Bv} 이하", "이면"),
            ">": (f"{subj} {Bv}{_jj(Bv, '을', '를')} 초과", "하면"),
            "<": (f"{subj} {Bv} 미만", "이면"),
            "==": (f"{subj} {Bv}{_jj(Bv, '과', '와')} 같", "으면"),
            "!=": (f"{subj} {Bv}{_jj(Bv, '과', '와')} 다르", "면"),
        }.get(op, (f"{A} {op} {Bv}", "이면"))
        if conditional:
            return stem + tail
        return stem + {"==": "음", "!=": "다"}.get(op, "")
    return {">=": f"{A} is {Bv} or more", "<=": f"{A} is {Bv} or less", ">": f"{A} is more than {Bv}",
            "<": f"{A} is less than {Bv}", "==": f"{A} is {Bv}", "!=": f"{A} is not {Bv}"}.get(op, f"{A} {op} {Bv}")


def _poss(who):
    return {"self": "your", "target": "the target's", "it": "that enemy's"}.get(who or "self", "your")


def cond_label(c, project=None, lang="ko", card=False):
    if not isinstance(c, dict):
        return "?"
    t = c.get("t")
    V = lambda x: value_label(x, project, lang, card)  # noqa: E731
    if t == "cmp":
        return cmp_text(c, project, lang, card)
    if t == "chance":
        return f"{V(c.get('pct'))}% 확률" if lang == "ko" else f"a {V(c.get('pct'))}% chance"
    if t == "has":
        who = (WHO if lang == "ko" else WHO_EN).get(c.get("who", "self"), "")
        p = _pname(project, c.get("power"), lang) if project else c.get("power")
        return f"{who}에게 [gold]{p}[/gold]이(가) 있음" if lang == "ko" else f"{who} {'have' if c.get('who') == 'self' else 'has'} [gold]{p}[/gold]"
    if t in ("and", "or"):
        j = {"and": "그리고", "or": "또는"}[t] if lang == "ko" else t
        return f"({cond_label(c.get('a'), project, lang, card)} {j} {cond_label(c.get('b'), project, lang, card)})"
    if t == "not":
        return f"({cond_label(c.get('a'), project, lang, card)})이 아님" if lang == "ko" else f"not ({cond_label(c.get('a'), project, lang, card)})"
    if t == "osty_alive":
        return "[gold]골골이[/gold]가 살아 있음" if lang == "ko" else "[gold]Osty[/gold] is alive"
    if t == "pet_alive":
        n = _pet_name(project, c.get("pet"), lang)
        return f"[gold]{n}[/gold]{_j(n, '이', '가')} 살아 있음" if lang == "ko" else f"[gold]{n}[/gold] is alive"
    if t == "src":
        return "C# " + _short_code(c.get("code"), 48)
    return "?"


def _fmt(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        return str(x)
    return str(int(f)) if f.is_integer() else str(f)


# ---------------------------------------------------------------------------
# 설명문 자동 생성
# ---------------------------------------------------------------------------
def describe(blocks, project, owner_kind, lang="ko"):
    if lang == "zh":
        from card_zh import blocks_text
        return blocks_text(blocks, project, owner_kind == "card")
    card = owner_kind == "card"
    out = []
    for b in blocks or []:
        s = _describe_one(b, project, owner_kind, lang, card)
        if s:
            out.append(s)
    return " ".join(out)


def _describe_one(b, project, owner_kind, lang, card):
    a = b.get("args", {})
    V = lambda k: value_label(a.get(k), project, lang, card)  # noqa: E731
    W = lambda k: (WHO if lang == "ko" else WHO_EN).get(a.get(k, "self"), "")  # noqa: E731
    op = b["op"]
    ko = lang == "ko"
    if op == "damage":
        hits = int(a.get("hits", 1) or 1)
        times = (f" {hits}번" if ko else f" {hits} times") if hits > 1 else ""
        who = "" if a.get("who") == "target" else (f"{W('who')}에게 " if ko else "")
        return f"{who}피해를 {V('amount')}{'씩' if hits > 1 else ''}{times} 줍니다." if ko else \
            f"Deal {V('amount')} damage{'' if a.get('who') == 'target' else ' to ' + W('who')}{times}."
    if op == "block":
        return f"[gold]방어도[/gold]를 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]Block[/gold]."
    if op == "lose_block":
        return f"{W('who')}의 [gold]방어도[/gold]를 {V('amount')} 없앱니다." if ko else f"Remove {V('amount')} [gold]Block[/gold] from {W('who')}."
    if op == "draw":
        return f"카드를 {V('amount')}장 뽑습니다." if ko else f"Draw {V('amount')} card(s)."
    if op == "energy":
        return f"에너지를 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} Energy."
    if op == "heal":
        return (f"{'' if a.get('who') == 'self' else W('who') + '의 '}체력을 {V('amount')} 회복합니다." if ko
                else f"Heal {V('amount')} HP.")
    if op == "lose_hp":
        return (f"{'' if a.get('who') == 'self' else W('who') + '이(가) '}체력을 {V('amount')} 잃습니다." if ko
                else f"Lose {V('amount')} HP.")
    if op == "max_hp":
        return f"최대 체력이 {V('amount')} 증가합니다." if ko else f"Raise your Max HP by {V('amount')}."
    if op == "gold":
        return f"골드를 {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]Gold[/gold]."
    if op in ("apply_power", "remove_power"):
        p = _pname(project, a.get("power"), lang)
        allp = op == "remove_power" and value_label(a.get("amount"), project, lang, card) == "0"
        if op == "apply_power":
            if a.get("who") == "self":
                return f"[gold]{p}[/gold]{_j(p, '을', '를')} {V('amount')} 얻습니다." if ko else f"Gain {V('amount')} [gold]{p}[/gold]."
            return f"{W('who')}에게 [gold]{p}[/gold]{_j(p, '을', '를')} {V('amount')} 부여합니다." if ko else \
                f"Apply {V('amount')} [gold]{p}[/gold] to {W('who')}."
        amt = ("모두" if ko else "all") if allp else V("amount")
        return f"{W('who')}의 [gold]{p}[/gold]{_j(p, '을', '를')} {amt} 제거합니다." if ko else f"Remove {amt} [gold]{p}[/gold] from {W('who')}."
    if op == "flash":
        return ""
    if op == "hand":
        import gimmick as G
        act = dict(HAND_ACTIONS).get(a.get("action"), "")
        ctype = a.get("ctype") or "Any"
        if ko:
            what = G.filter_word(project, ctype, "ko")
            if a.get("which") == "all":
                return f"손패의 모든 {what}를 {act}합니다." if act != "버리기" else f"손패의 모든 {what}를 버립니다."
            return f"손패의 무작위 {what} {V('count')}장을 {act if act != '버리기' else '버립'}{'합니다' if act != '버리기' else '니다'}."
        acte = {"upgrade": "Upgrade", "exhaust": "Exhaust", "discard": "Discard"}.get(a.get("action"))
        cte = G.filter_word(project, ctype, "en", plural=True)
        return f"{acte} all {cte} in your hand." if a.get("which") == "all" else \
            f"{acte} {V('count')} random {cte} in your hand."
    if op in ("keyword_this", "keyword_cards"):
        import modgen as M
        import gimmick as G
        kn = M.KEYWORD_NAMES["ko" if ko else "en"].get(a.get("keyword"), a.get("keyword"))
        add = a.get("action", "add") == "add"
        if op == "keyword_this":
            if ko:
                return (f"이 카드에 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 부여합니다." if add else
                        f"이 카드의 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 제거합니다.")
            return f"This card gains [gold]{kn}[/gold]." if add else f"This card loses [gold]{kn}[/gold]."
        ctype = a.get("ctype") or "Any"
        if ko:
            where = dict(KW_WHERE).get(a.get("where"), "손패")
            what = G.filter_word(project, ctype, "ko")
            whom = f"{where}의 모든 {what}" if a.get("which") == "all" else f"{where}의 무작위 {what} {V('count')}장"
            return (f"{whom}에 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 부여합니다." if add else
                    f"{whom}에서 [gold]{kn}[/gold]{_jj(kn, '을', '를')} 제거합니다.")
        where = {"hand": "your hand", "draw": "your draw pile", "discard": "your discard pile",
                 "all": "all your piles"}.get(a.get("where"), "your hand")
        cte = G.filter_word(project, ctype, "en", plural=True)
        whom = f"all {cte} in {where}" if a.get("which") == "all" else f"{V('count')} random {cte} in {where}"
        return f"Give {whom} [gold]{kn}[/gold]." if add else f"Remove [gold]{kn}[/gold] from {whom}."
    if op in ("set_var", "change_var"):
        n = str(a.get("name", "a"))
        amt = a.get("amount") or {}
        neg = op == "change_var" and amt.get("t") == "num" and float(amt.get("v", 0) or 0) < 0
        val = value_label(dict(amt, v=-float(amt.get("v", 0))) if neg else amt, project, lang, card)
        if op == "set_var":
            return f"{n}{_jj(n, '을', '를')} {val}{_ro(val)} 정합니다." if ko else f"Set {n} to {val}."
        if neg:
            return f"{n}에서 {val}{_jj(val, '을', '를')} 뺍니다." if ko else f"Subtract {val} from {n}."
        return f"{n}에 {val}{_jj(val, '을', '를')} 더합니다." if ko else f"Add {val} to {n}."
    if op == "add_card":
        import modgen as M
        if a.get("card") == "this":
            nm = "이 카드의 복사본" if ko else "a copy of this card"
        else:
            c = next((x for x in project.get("cards", []) if x["id"] == a.get("card")), None)
            nm = f"[gold]{M.text(c, 'name', lang)}[/gold]" if c else a.get("card")
        pile = dict(PILES).get(a.get("pile"), "") if ko else {"Hand": "your hand", "Draw": "your draw pile",
                                                              "Discard": "your discard pile"}.get(a.get("pile"))
        return f"{nm} {V('count')}장을 {pile}에 넣습니다." if ko else f"Add {V('count')} {nm} into {pile}."
    if op in ("if", "if_else"):
        c = a.get("cond") or {}
        cond = cond_label(c, project, lang, card)
        body = describe(b.get("body"), project, owner_kind, lang)
        if ko and c.get("t") == "cmp":
            s = f"{cmp_text(c, project, lang, card, conditional=True)} {body}"   # '3 이상이면', '3을 초과하면', '3과 같으면'
        elif ko and cond.endswith("있음"):
            s = f"{cond[:-2]}있으면 {body}"       # '살아 있음' → '살아 있으면'
        elif ko and cond.endswith("확률"):
            s = f"{cond}로 {body}"                # '50% 확률로'
        else:
            s = f"{cond}이면 {body}" if ko else f"If {cond}: {body}"
        if op == "if_else" and b.get("else"):
            s += (" 아니면 " if ko else " Otherwise: ") + describe(b.get("else"), project, owner_kind, lang)
        return s
    if op == "repeat":
        return (f"{V('times')}번: " if ko else f"{V('times')} times: ") + describe(b.get("body"), project, owner_kind, lang)
    if op == "each_enemy":
        return ("모든 적에게 각각: " if ko else "For each enemy: ") + describe(b.get("body"), project, owner_kind, lang)
    if op == "random_enemy":
        return ("무작위 적 1명에게: " if ko else "To a random enemy: ") + describe(b.get("body"), project, owner_kind, lang)
    # ---- 기믹 ----
    if op == "summon":
        n = _summon_name(project, a.get("summon"), lang)
        return f"[gold]{n}[/gold]{_j(n, '을', '를')} 소환합니다." if ko else f"Summon [gold]{n}[/gold]."
    if op == "command":
        n = _summon_name(project, a.get("summon"), lang)
        if a.get("summon") == "*":
            return "모든 소환수가 즉시 행동합니다." if ko else "All your summons act immediately."
        return f"[gold]{n}[/gold]{_j(n, '이', '가')} 즉시 행동합니다." if ko else f"[gold]{n}[/gold] acts immediately."
    if op == "unsummon":
        n = _summon_name(project, a.get("summon"), lang)
        return f"[gold]{n}[/gold]{_j(n, '을', '를')} 돌려보냅니다." if ko else f"Dismiss [gold]{n}[/gold]."
    if op == "pay":
        p = _pname(project, a.get("power"), lang)
        body = describe(b.get("body"), project, owner_kind, lang)
        els = describe(b.get("else"), project, owner_kind, lang)
        s = f"[gold]{p}[/gold]{_j(p, '을', '를')} {V('amount')} 소모할 수 있으면 소모하고 {body}" if ko else \
            f"If you can, spend {V('amount')} [gold]{p}[/gold] to: {body}"
        if els:
            s += (f" 아니면 {els}" if ko else f" Otherwise: {els}")
        return s
    if op == "choice":
        opts = [(_label_text(a.get(k), lang), b.get(bk)) for k, bk in (("opt1", "body"), ("opt2", "else"), ("opt3", "third"))]
        opts = [(n, body) for n, body in opts if n]
        if ko:
            return "하나를 고릅니다: " + " / ".join(
                f"[gold]{n}[/gold]({describe(body, project, owner_kind, lang).rstrip('.')})" for n, body in opts) + "."
        return "Choose one: " + " / ".join(
            f"[gold]{n}[/gold] ({describe(body, project, owner_kind, lang).rstrip('.')})" for n, body in opts) + "."
    if op == "pick":
        import gimmick as G
        pile_ko = dict(PICK_PILES).get(a.get("pile"), "")
        pile_en = {"Hand": "your hand", "Draw": "your draw pile", "Discard": "your discard pile",
                   "Exhaust": "your exhaust pile"}.get(a.get("pile"), "")
        if ko:
            act = {"hand": "손으로 가져옵니다", "top": "뽑을 카드 더미 맨 위에 놓습니다", "exhaust": "소멸시킵니다",
                   "discard": "버립니다", "upgrade": "강화합니다"}.get(a.get("action"), "")
            return f"{pile_ko}에서 {G.filter_word(project, a.get('ctype'), 'ko')} {V('count')}장을 골라 {act}."
        act = {"hand": "put it into your hand", "top": "put it on top of your draw pile", "exhaust": "Exhaust it",
               "discard": "discard it", "upgrade": "Upgrade it"}.get(a.get("action"), "")
        return f"Choose {V('count')} {G.filter_word(project, a.get('ctype'), 'en', plural=True)} in {pile_en} and {act}."
    if op in ("channel", "evoke", "orb_passive_all", "orb_slots", "orb_grow", "stars", "forge",
              "osty_summon", "osty_attack", "osty_kill"):
        return _describe_class(b, op, a, project, lang, V, W)
    if op.startswith("pet_"):
        n = _pet_name(project, a.get("pet"), lang)
        if op == "pet_summon":
            return (f"[gold]{n}[/gold]{_j(n, '을', '를')} [gold]소환[/gold]합니다 ({V('amount')})." if ko else
                    f"[gold]Summon[/gold] {V('amount')} [gold]{n}[/gold].")
        if op == "pet_attack":
            hits = int(a.get("hits", 1) or 1)
            times = (f" {hits}번" if ko else f" {hits} times") if hits > 1 else ""
            if ko:
                who = "" if a.get("who") == "target" else f"{W('who')}에게 "
                return f"[gold]{n}[/gold]{_j(n, '이', '가')} {who}피해를 {V('amount')}{'씩' if hits > 1 else ''}{times} 줍니다."
            return f"[gold]{n}[/gold] deals {V('amount')} damage{'' if a.get('who') == 'target' else ' to ' + W('who')}{times}."
        if op == "pet_act":
            return f"[gold]{n}[/gold]{_j(n, '이', '가')} 즉시 행동합니다." if ko else f"[gold]{n}[/gold] acts immediately."
        if op == "pet_kill":
            return f"[gold]{n}[/gold]{_j(n, '을', '를')} 희생합니다." if ko else f"Sacrifice [gold]{n}[/gold]."
    if op == "fx":
        return ""  # 보이기만 하는 연출이라 설명에는 넣지 않음
    if op in ("button_on", "button_off"):
        import fxbtn
        bt = fxbtn.find_button(project, a.get("button")) or {}
        n = (bt.get(f"label_{lang}") or bt.get("label_ko") or a.get("button") or "?")
        if op == "button_on":
            return f"[gold]{n}[/gold] 버튼이 생깁니다." if ko else f"Gain the [gold]{n}[/gold] button."
        return f"[gold]{n}[/gold] 버튼이 사라집니다." if ko else f"Lose the [gold]{n}[/gold] button."
    if op == "delayed":
        body = describe(b.get("body"), project, owner_kind, lang)
        tv = V("times")
        rep = "" if tv == "1" else (f" ({tv}번)" if ko else f" ({tv} times)")
        if a.get("when") == "end":
            return (f"이번 턴이 끝날 때{rep}: {body}" if ko else f"At the end of this turn{rep}: {body}")
        return (f"다음 턴 시작 시{rep}: {body}" if ko else f"At the start of your next turn{rep}: {body}")
    return ""


# ---------------------------------------------------------------------------
# C# 로 변환
# ---------------------------------------------------------------------------
class _Gen:
    def __init__(self, project, C, prefix="Blk", extras=None, allow_event=False):
        self.project = project
        self.C = C
        self.n = 0
        self.its = []        # 반복 안의 '그 적' 변수 이름 스택
        self.errors = []
        self.prefix = prefix          # 블록이 만드는 클래스(선택지 카드·예약 파워) 이름 앞부분
        self.extras = extras          # 그 클래스들을 모을 목록 (None 이면 버림)
        self.allow_event = allow_event
        self.no_vars = False          # 사용 조건처럼 변수를 쓸 수 없는 곳
        self.k = 0

    def uid(self, base):
        self.n += 1
        return f"{base}{self.n}"

    def cls_name(self, kind):
        import gimmick as G
        name = f"{self.prefix}{kind}{G.letters(self.k).capitalize()}"  # 대문자가 연달아 오지 않게 (게임 ID 규칙)
        self.k += 1
        return name

    def helper(self):
        import gimmick as G
        return G.helper(self.project)

    # ---- 생물 ----
    def creature(self, who):
        C = self.C
        if who == "self":
            return C.me
        if who == "target":
            if C.kind == "relic" or not C.other:
                self.errors.append("유물에는 '대상'이 없습니다 ('그 적'이나 '모든 적'을 쓰세요).")
                return "null"
            return C.other
        if who == "it":
            if not self.its:
                self.errors.append("'그 적'은 '모든 적 각각에게' / '무작위 적 1명에게' 블록 안에서만 쓸 수 있습니다.")
                return "null"
            return self.its[-1]
        return "null"

    def enemies(self):
        C = self.C
        return "OwnerEnemies()" if C.kind == "power" else f"{C.me}.CombatState!.HittableEnemies"

    def rng(self):
        C = self.C
        return f"{C.me}.CombatState!.RunState.Rng.CombatTargets"

    def player(self):
        return self.C.player

    # ---- 값 ----
    def val(self, v):
        if not isinstance(v, dict):
            return "0m"
        t = v.get("t")
        if t == "num":
            base = _dec(v.get("v", 0))
            up = v.get("up") or 0
            if up and self.C.kind == "card":
                return f"(IsUpgraded ? {_dec(float(v.get('v', 0)) + float(up))} : {base})"
            return base
        if t == "stack":
            import modgen as M
            pm = M.power_meta(self.project, v.get("power"))
            if not pm:
                self.errors.append(f"없는 파워: {v.get('power')}")
                return "0m"
            cr = self.creature(v.get("who", "self"))
            return f"(decimal)({cr}?.GetPowerAmount<{pm['cls']}>() ?? 0)" if cr != self.C.me else \
                f"(decimal){cr}.GetPowerAmount<{pm['cls']}>()"
        if t == "stat":
            cr = self.creature(v.get("who", "self"))
            prop = {"hp": "CurrentHp", "maxhp": "MaxHp", "block": "Block"}.get(v.get("stat"), "CurrentHp")
            return f"(decimal)({cr}?.{prop} ?? 0)"
        if t == "count":
            w = v.get("what")
            if w == "enemies":
                return f"(decimal){self.enemies()}.Count"
            pile = {"hand": "Hand", "draw": "DrawPile", "discard": "DiscardPile", "exhaust": "ExhaustPile"}.get(w, "Hand")
            return f"(decimal)({self.player()}?.PlayerCombatState?.{pile}.Cards.Count ?? 0)"
        if t == "energy":
            return f"(decimal)({self.player()}?.PlayerCombatState?.Energy ?? 0)"
        if t == "amount":
            if self.C.kind != "power":
                self.errors.append("'이 파워의 스택 수'는 파워에서만 쓸 수 있습니다.")
                return "0m"
            return "(decimal)Amount"
        if t == "round":
            return f"(decimal)({self.C.me}.CombatState?.RoundNumber ?? 0)"
        if t == "rand":
            lo, hi = self.val(v.get("min")), self.val(v.get("max"))
            return f"(decimal){self.rng()}.NextInt((int)({lo}), (int)({hi}) + 1)"
        if t == "var":
            if self.no_vars:
                self.errors.append("여기서는 변수를 쓸 수 없습니다.")
                return "0m"
            return "v_" + _ident(v.get("name", "a"))
        if t == "played":
            import gimmick as G
            f = G.filter_expr(self.project, v.get("filter", "Any"), "c_")
            return f"(decimal){self.helper()}.Played({self.player()}, {'true' if v.get('scope', 'turn') == 'turn' else 'false'}, c_ => {f})"
        if t == "summons":
            return f"(decimal){self.helper()}.SummonCount({self.C.me})"
        if t in ("orb_passive", "orb_evoke"):
            if self.C.kind != "orb":
                self.errors.append("'이 구체의 지속/발현 수치'는 구체 블록에서만 쓸 수 있습니다.")
                return "0m"
            return "PassiveVal" if t == "orb_passive" else "EvokeVal"
        if t == "orbs":
            import gimmick as G
            q = f"{self.player()}?.PlayerCombatState?.OrbQueue"
            w = v.get("what", "count")
            if w == "slots":
                return f"(decimal)({q}?.Capacity ?? 0)"
            if w == "empty":
                return f"(decimal)(({q}?.Capacity ?? 0) - ({q}?.Orbs.Count ?? 0))"
            om = G.orb_meta(self.project, v.get("orb")) if v.get("orb") else None
            if om:
                return f"(decimal)({q}?.Orbs.Count(o_ => o_ is {om['cls']}) ?? 0)"
            return f"(decimal)({q}?.Orbs.Count ?? 0)"
        if t == "stars":
            return f"(decimal)({self.player()}?.PlayerCombatState?.Stars ?? 0)"
        if t == "pet":
            import pets as PT
            if not PT.find_pet(self.project, v.get("pet")):
                self.errors.append(f"없는 동료: {v.get('pet')}")
                return "0m"
            H, cls = PT.helper(self.project), PT.pet_cls(self.project, v.get("pet"))
            prop = "MaxHp" if v.get("what") == "maxhp" else "CurrentHp"
            return f"(decimal)({H}.Alive<{cls}>({self.player()}) ? {H}.Find<{cls}>({self.player()})!.{prop} : 0)"
        if t == "dynvar":
            if self.C.kind != "card" or not any(x.get("name") == v.get("name") for x in self.C.item.get("raw_vars", [])):
                self.errors.append(f"원본 변수 {v.get('name')} 이(가) 이 카드에 없습니다.")
                return "0m"
            prop = v.get("prop") or "BaseValue"
            cast = "(decimal)" if prop == "IntValue" else ""
            return f'{cast}DynamicVars["{v.get("name")}"].{prop}'
        if t == "src":
            code = str(v.get("code") or "").strip()
            if not code:
                self.errors.append("C# 식 칸이 비어 있습니다.")
                return "0m"
            return f"(decimal)({code})"
        if t == "star_x":
            if self.C.kind != "card":
                self.errors.append("'X (쓴 별)'은 카드에서만 쓸 수 있습니다.")
                return "0m"
            return "(decimal)ResolveStarXValue()"
        if t == "energy_x":
            if self.C.kind != "card" or not (self.C.item or {}).get("x_cost"):
                self.errors.append("'X (쓴 에너지)'는 'X 비용' 카드에서만 쓸 수 있습니다 (카드 탭에서 X 비용을 켜세요).")
                return "0m"
            return "(decimal)XCount"
        if t == "osty":
            pl = self.player()
            prop = "MaxHp" if v.get("what") == "maxhp" else "CurrentHp"
            return f"(decimal)(({pl}?.IsOstyAlive ?? false) ? {pl}!.Osty!.{prop} : 0)"
        if t == "event":
            if not self.allow_event:
                self.errors.append("'그 수치'는 파워의 '넘칠 때' / '기준치 도달 시' 블록에서만 쓸 수 있습니다.")
                return "0m"
            return "ev_"
        if t == "op":
            o = v.get("op", "+")
            a, b = self.val(v.get("a")), self.val(v.get("b"))
            if o == "/":
                return f"({b} == 0m ? 0m : Math.Floor({a} / {b}))"
            return f"({a} {o} {b})"
        return "0m"

    def cond(self, c):
        if not isinstance(c, dict):
            return "false"
        t = c.get("t")
        if t == "cmp":
            return f"({self.val(c.get('a'))} {c.get('op', '>=')} {self.val(c.get('b'))})"
        if t == "chance":
            return f"({self.rng()}.NextInt(100) < (int)({self.val(c.get('pct'))}))"
        if t == "has":
            import modgen as M
            pm = M.power_meta(self.project, c.get("power"))
            if not pm:
                self.errors.append(f"없는 파워: {c.get('power')}")
                return "false"
            cr = self.creature(c.get("who", "self"))
            return f"(({cr}?.GetPowerAmount<{pm['cls']}>() ?? 0) > 0)"
        if t in ("and", "or"):
            j = "&&" if t == "and" else "||"
            return f"({self.cond(c.get('a'))} {j} {self.cond(c.get('b'))})"
        if t == "not":
            return f"(!{self.cond(c.get('a'))})"
        if t == "osty_alive":
            return f"({self.player()}?.IsOstyAlive ?? false)"
        if t == "pet_alive":
            import pets as PT
            if not PT.find_pet(self.project, c.get("pet")):
                self.errors.append(f"없는 동료: {c.get('pet')}")
                return "false"
            return f"{PT.helper(self.project)}.Alive<{PT.pet_cls(self.project, c.get('pet'))}>({self.player()})"
        if t == "src":
            code = str(c.get("code") or "").strip()
            if not code:
                self.errors.append("C# 조건 칸이 비어 있습니다.")
                return "false"
            return f"({code})"
        return "false"

    def src_slot(self, s, cur):
        """원본 호출 블록의 칸 하나 -> C# 글자. 바꾸지 않았으면 원래 글자 그대로."""
        kind = s.get("kind")
        if kind == "value":
            if cur == s.get("v0"):
                return "" if s.get("absent") else s.get("orig", "")
            if s.get("type") == "DynamicVar":
                if isinstance(cur, dict) and cur.get("t") == "dynvar":
                    return f'DynamicVars["{cur.get("name")}"]'
                self.errors.append(f"'{s.get('name')}' 칸은 원본 변수(DynamicVar)만 받습니다. 수치는 그 변수의 값을 바꾸세요.")
                return s.get("orig", "")
            code = self.val(cur)
            if s.get("type") == "int":
                code = f"(int)({code})"
            return s["wrap"].replace("{}", code) if s.get("absent") else code
        text = str(cur if cur is not None else "").strip()
        return text or s.get("orig", "")

    # ---- 문장 ----
    def stmts(self, blocks, ind):
        out = []
        for b in blocks or []:
            out += self.stmt(b, ind)
        return out

    def each_target(self, who, ind, body_fn):
        """who 가 모든 적/무작위 적이면 반복으로 감싼다."""
        if who == "all":
            v = self.uid("e")
            return [f"{ind}foreach (var {v} in {self.enemies()}.ToList())", f"{ind}{{"] + \
                body_fn(v, ind + "    ") + [f"{ind}}}"]
        if who == "random":
            v = self.uid("r")
            return [f"{ind}{{", f"{ind}    var {v} = {self.rng()}.NextItem({self.enemies()}.ToList());",
                    f"{ind}    if ({v} != null)", f"{ind}    {{"] + body_fn(v, ind + "        ") + [f"{ind}    }}", f"{ind}}}"]
        cr = self.creature(who)
        if cr == self.C.me:
            return body_fn(cr, ind)
        return [f"{ind}if ({cr} != null)", f"{ind}{{"] + body_fn(cr, ind + "    ") + [f"{ind}}}"]

    def stmt(self, b, ind):
        import modgen as M
        C, a, op = self.C, b.get("args", {}), b.get("op")
        if op in ("src_call", "src_loop"):
            if C.kind != "card" or not C.item.get("clone"):
                self.errors.append("원본 코드 블록은 복제 카드에서만 사용할 수 있습니다.")
                return []
            if op == "src_loop":
                head = str(a.get("head") or "").strip()
                return ([ind + head] if head else []) + [f"{ind}{{"] + self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
            slots = {s["key"]: s for s in b.get("slots", [])}
            out = []
            for i, part in enumerate(b.get("parts") or []):
                out.append(part if i % 2 == 0 else self.src_slot(slots.get(part, {}), a.get(part)))
            return [ind + line for line in "".join(out).splitlines()]
        if op in ("source_step", "source_hit", "source_amount"):
            if C.kind != "card" or not C.item.get("clone"):
                self.errors.append("원본 코드 블록은 복제 카드에서만 사용할 수 있습니다.")
                return []
            if op == "source_amount":
                suffix = b["suffix"]
                if suffix.startswith(("m", "M")):
                    suffix = suffix[1:]
                amount = self.val(a.get("amount"))
                if b.get("label") == "드로우":
                    amount = f"(int)({amount})"
                return [ind + b["prefix"] + amount + suffix]
            if op == "source_step":
                return [ind + line for line in a.get("source", "").splitlines()]
            stat = a.get("stat")
            if not any(v["name"] == stat for v in C.item.get("raw_vars", [])) or not str(stat).isidentifier():
                self.errors.append("원본 피해 변수 참조가 없습니다.")
                return []
            who = "(cardPlay.Target ?? Me)" if a.get("target") == "target" else self.creature(a.get("target"))
            return [f'{ind}await Hit(choiceContext, {who}, DynamicVars["{stat}"].IntValue, {max(1,int(a.get("hits",1)))});']
        if op == "original_play":
            if C.kind == "card" and (C.item.get("clone") or {}).get("editable_play"):
                return [ind + "await OriginalOnPlay(choiceContext, cardPlay);"]
            self.errors.append("원본 실행 블록은 원본 사용 효과가 있는 복제 카드에서만 사용할 수 있습니다.")
            return []
        cc, me = C.cc, C.me
        need_player = C.kind == "power"

        def with_player(lines):
            if need_player:
                return [f"{ind}if ({C.player} != null)", f"{ind}{{"] + ["    " + x for x in lines] + [f"{ind}}}"]
            return lines

        if op == "damage":
            amt = self.val(a.get("amount"))
            hits = max(1, int(a.get("hits", 1) or 1))
            props = "ValueProp.Move" if a.get("powered", True) else "ValueProp.Unpowered"

            def body(t, i2):
                line = f"{i2}await CreatureCmd.Damage({cc}, {t}, {amt}, {props}, {me}, {C.src}, {C.play});"
                return [line] if hits == 1 else [f"{i2}for (var h_ = 0; h_ < {hits}; h_++)", "    " + line]
            return self.each_target(a.get("who", "target"), ind, body)
        if op == "block":
            return [f"{ind}await CreatureCmd.GainBlock({me}, {self.val(a.get('amount'))}, "
                    f"{'ValueProp.Move' if C.kind == 'card' else 'ValueProp.Unpowered'}, {C.play});"]
        if op == "lose_block":
            amt = self.val(a.get("amount"))
            return self.each_target(a.get("who", "target"), ind,
                                    lambda t, i2: [f"{i2}await CreatureCmd.LoseBlock({cc}, {t}, {amt}, {me});"])
        if op == "draw":
            return with_player([f"{ind}await CardPileCmd.Draw({cc}, {self.val(a.get('amount'))}, {C.player});"])
        if op == "energy":
            return with_player([f"{ind}await PlayerCmd.GainEnergy({self.val(a.get('amount'))}, {C.player});"])
        if op == "gold":
            return with_player([f"{ind}await PlayerCmd.GainGold({self.val(a.get('amount'))}, {C.player});"])
        if op == "max_hp":
            return [f"{ind}await CreatureCmd.GainMaxHp({me}, {self.val(a.get('amount'))});"]
        if op == "heal":
            amt = self.val(a.get("amount"))
            return self.each_target(a.get("who", "self"), ind, lambda t, i2: [f"{i2}await CreatureCmd.Heal({t}, {amt});"])
        if op == "lose_hp":
            amt = self.val(a.get("amount"))
            return self.each_target(a.get("who", "self"), ind, lambda t, i2: [
                f"{i2}await CreatureCmd.Damage({cc}, {t}, {amt}, ValueProp.Unblockable | ValueProp.Unpowered, {me}, {C.src}, {C.play});"])
        if op in ("apply_power", "remove_power"):
            pm = M.power_meta(self.project, a.get("power"))
            if not pm:
                self.errors.append(f"없는 파워: {a.get('power')}")
                return []
            amt = self.val(a.get("amount"))
            if op == "apply_power":
                return self.each_target(a.get("who", "target"), ind, lambda t, i2: [
                    f"{i2}await CommonActions.Apply<{pm['cls']}>({cc}, {t}, {C.src}, {amt});"])
            pv = self.uid("pw")

            def rm(t, i2):
                return [f"{i2}{{", f"{i2}    var {pv} = {t}.GetPower<{pm['cls']}>();",
                        f"{i2}    if ({pv} != null)", f"{i2}    {{",
                        f"{i2}        if ({amt} <= 0m) await PowerCmd.Remove({pv});",
                        f"{i2}        else await PowerCmd.ModifyAmount({cc}, {pv}, -({amt}), {me}, {C.src});",
                        f"{i2}    }}", f"{i2}}}"]
            return self.each_target(a.get("who", "target"), ind, rm)
        if op == "flash":
            if C.kind in ("relic", "power"):
                return [f"{ind}Flash();"]
            return []
        if op == "hand":
            import gimmick as G
            lst, cv, i_ = self.uid("cards"), self.uid("c"), self.uid("i")
            ct = a.get("ctype", "Any") or "Any"
            cond = ["true"]
            if C.kind == "card":
                cond.append(f"{cv} != this")
            if ct != "Any":
                cond.append(G.filter_expr(self.project, ct, cv))
            if a.get("action") == "upgrade":
                cond.append(f"{cv}.IsUpgradable")
            act = {"upgrade": f"CardCmd.Upgrade({cv});", "exhaust": f"await CardCmd.Exhaust({cc}, {cv});",
                   "discard": f"await CardCmd.Discard({cc}, {cv});"}[a.get("action", "upgrade")]
            lines = [f"{ind}{{",
                     f"{ind}    var {lst} = ({C.player}?.PlayerCombatState?.Hand.Cards ?? System.Array.Empty<CardModel>()).Where({cv} => {' && '.join(cond)}).ToList();"]
            if a.get("which") == "all":
                lines += [f"{ind}    foreach (var {cv} in {lst})", f"{ind}    {{", f"{ind}        {act}", f"{ind}    }}"]
            else:
                lines += [f"{ind}    for (var {i_} = 0; {i_} < (int)({self.val(a.get('count'))}) && {lst}.Count > 0; {i_}++)",
                          f"{ind}    {{", f"{ind}        var {cv} = {self.rng()}.NextItem({lst});",
                          f"{ind}        {lst}.Remove({cv});", f"{ind}        {act}", f"{ind}    }}"]
            return lines + [f"{ind}}}"]
        if op in ("keyword_this", "keyword_cards"):
            import gimmick as G
            kw = a.get("keyword") or "Retain"
            verb = "ApplyKeyword" if a.get("action", "add") == "add" else "RemoveKeyword"
            if op == "keyword_this":
                if C.kind != "card":
                    self.errors.append("'이 카드에 키워드'는 카드에서만 쓸 수 있습니다 (다른 곳은 '카드들에 키워드').")
                    return []
                return [f"{ind}CardCmd.{verb}(this, CardKeyword.{kw});"]
            lst, cv, i_, pcs = self.uid("cards"), self.uid("c"), self.uid("i"), self.uid("pcs")
            piles = {"hand": ["Hand"], "draw": ["DrawPile"], "discard": ["DiscardPile"],
                     "all": ["Hand", "DrawPile", "DiscardPile"]}.get(a.get("where"), ["Hand"])
            src = ".Concat".join(f"({pcs}.{x}.Cards)" for x in piles)
            ct = a.get("ctype", "Any") or "Any"
            has = f"{cv}.Keywords.Contains(CardKeyword.{kw})"
            cond = [f"!{has}" if verb == "ApplyKeyword" else has]
            if C.kind == "card":
                cond.append(f"{cv} != this")
            if ct != "Any":
                cond.append(G.filter_expr(self.project, ct, cv))
            act = f"CardCmd.{verb}({cv}, CardKeyword.{kw});"
            lines = [f"{ind}{{", f"{ind}    var {pcs} = {C.player}?.PlayerCombatState;",
                     f"{ind}    var {lst} = {pcs} == null ? new List<CardModel>() : "
                     f"{src}.Where({cv} => {' && '.join(cond)}).ToList();"]
            if a.get("which") == "all":
                lines += [f"{ind}    foreach (var {cv} in {lst})", f"{ind}    {{", f"{ind}        {act}", f"{ind}    }}"]
            else:
                lines += [f"{ind}    for (var {i_} = 0; {i_} < (int)({self.val(a.get('count'))}) && {lst}.Count > 0; {i_}++)",
                          f"{ind}    {{", f"{ind}        var {cv} = {self.rng()}.NextItem({lst});",
                          f"{ind}        {lst}.Remove({cv});", f"{ind}        {act}", f"{ind}    }}"]
            return lines + [f"{ind}}}"]
        if op == "add_card":
            mid = self.project["mod"]["id"]
            i_, nc = self.uid("i"), self.uid("nc")
            card = a.get("card", "this")
            if card == "this":
                if C.kind != "card":
                    self.errors.append("'이 카드의 복사본'은 카드에서만 쓸 수 있습니다.")
                    return []
                make = f"{me}.CombatState!.CreateCard(CanonicalInstance, {C.player})"
            else:
                if not any(x["id"] == card for x in self.project.get("cards", [])):
                    self.errors.append(f"없는 카드: {card}")
                    return []
                make = f"{me}.CombatState!.CreateCard<global::{mid}.{mid}Code.Cards.{M.pascal(card)}>({C.player})"
            inner = [f"{ind}    for (var {i_} = 0; {i_} < (int)({self.val(a.get('count'))}); {i_}++)", f"{ind}    {{",
                     f"{ind}        var {nc} = {make};"]
            if card == "this":
                inner.append(f"{ind}        if (IsUpgraded) CardCmd.Upgrade({nc});")
            inner += [f"{ind}        await CardPileCmd.AddGeneratedCardToCombat({nc}, PileType.{a.get('pile', 'Hand')}, {C.player});",
                      f"{ind}    }}"]
            if need_player:
                return [f"{ind}if ({C.player} != null)", f"{ind}{{"] + inner + [f"{ind}}}"]
            return [f"{ind}{{"] + inner + [f"{ind}}}"]
        if op in ("if", "if_else"):
            lines = [f"{ind}if ({self.cond(a.get('cond'))})", f"{ind}{{"] + self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
            if op == "if_else":
                lines += [f"{ind}else", f"{ind}{{"] + self.stmts(b.get("else"), ind + "    ") + [f"{ind}}}"]
            return lines
        if op == "repeat":
            i_ = self.uid("k")
            return [f"{ind}for (var {i_} = 0; {i_} < (int)({self.val(a.get('times'))}); {i_}++)", f"{ind}{{"] + \
                self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
        if op in ("each_enemy", "random_enemy"):
            v = self.uid("it")
            self.its.append(v)
            try:
                body = self.stmts(b.get("body"), ind + ("    " if op == "each_enemy" else "        "))
            finally:
                self.its.pop()
            if op == "each_enemy":
                return [f"{ind}foreach (var {v} in {self.enemies()}.ToList())", f"{ind}{{"] + body + [f"{ind}}}"]
            return [f"{ind}{{", f"{ind}    var {v} = {self.rng()}.NextItem({self.enemies()}.ToList());",
                    f"{ind}    if ({v} != null)", f"{ind}    {{"] + body + [f"{ind}    }}", f"{ind}}}"]
        if op == "set_var":
            return [f"{ind}v_{_ident(a.get('name', 'a'))} = {self.val(a.get('amount'))};"]
        if op == "change_var":
            return [f"{ind}v_{_ident(a.get('name', 'a'))} += {self.val(a.get('amount'))};"]
        if op in ("summon", "command", "unsummon", "pay", "choice", "pick", "delayed"):
            return self.gimmick_stmt(b, op, a, ind)
        if op in SPECS and SPECS[op]["cat"] == "class":
            return self.class_stmt(b, op, a, ind)
        if op.startswith("pet_"):
            import pets as PT
            pid = a.get("pet") or ""
            p = PT.find_pet(self.project, pid)
            if not p:
                self.errors.append("동료를 고르세요 ('🎲 기믹' 탭에서 먼저 만드세요)." if not pid else f"없는 동료: {pid}")
                return []
            H, cls, act = PT.helper(self.project), PT.pet_cls(self.project, pid), PT.act_cls(self.project, pid)
            pl = C.player
            if op == "pet_summon":
                return [f"{ind}await {H}.Summon<{cls}, {act}>({C.cc}, {pl}, {self.val(a.get('amount'))}, this, "
                        f"{'true' if p.get('guard', True) else 'false'});"]
            if op == "pet_act":
                return [f"{ind}await {H}.Act<{cls}, {act}>({C.cc}, {pl});"]
            if op == "pet_kill":
                return [f"{ind}await {H}.Kill<{cls}>({pl});"]
            amt = self.val(a.get("amount"))
            hits = max(1, int(a.get("hits", 1) or 1))
            return self.each_target(a.get("who", "target"), ind,
                                    lambda t, i2: [f"{i2}await {H}.Attack<{cls}>({C.cc}, {pl}, {t}, {amt}, {hits});"])
        if op in ("fx", "button_on", "button_off"):
            import fxbtn
            mid = self.project["mod"]["id"]
            nsp = f"global::{mid}.{mid}Code.Gimmicks"
            if op == "fx":
                fid = a.get("fx") or ""
                if not fxbtn.find_effect(self.project, fid):
                    self.errors.append("이펙트를 고르세요 ('🎨 이펙트·버튼' 탭에서 먼저 그리세요)." if not fid else f"없는 이펙트: {fid}")
                    return []
                return self.each_target(a.get("who", "self"), ind, lambda t, i2: [f'{i2}{nsp}.{mid}Fx.Play("{fid}", {t});'])
            bid = a.get("button") or ""
            if not fxbtn.find_button(self.project, bid):
                self.errors.append("버튼을 고르세요 ('🎨 이펙트·버튼' 탭에서 먼저 만드세요)." if not bid else f"없는 버튼: {bid}")
                return []
            if op == "button_on":
                return [f'{ind}await {nsp}.{mid}Buttons.On("{bid}", {self.C.me}, {self.C.cc});']
            return [f'{ind}await {nsp}.{mid}Buttons.Off("{bid}", {self.C.me});']
        return [f"{ind}// 알 수 없는 블록: {op}"]

    # ---- 직업 시스템 블록 ----
    def class_stmt(self, b, op, a, ind):
        import gimmick as G
        C, cc = self.C, self.C.cc
        pl = self.uid("pl")
        src = "this"

        def wrap(lines):
            return [f"{ind}{{", f"{ind}    var {pl} = {C.player};", f"{ind}    if ({pl} != null)", f"{ind}    {{"] + \
                [f"{ind}        {x}" for x in lines] + [f"{ind}    }}", f"{ind}}}"]
        if op == "channel":
            om = G.orb_meta(self.project, a.get("orb"))
            if not om:
                self.errors.append(f"없는 구체: {a.get('orb')}")
                return []
            k = self.uid("k")
            return wrap([f"for (var {k} = 0; {k} < (int)({self.val(a.get('count'))}); {k}++)",
                         f"    await OrbCmd.Channel<{om['cls']}>({cc}, {pl});"])
        if op == "evoke":
            k = self.uid("k")
            fn = "EvokeNext" if a.get("which", "front") == "front" else "EvokeLast"
            return wrap([f"for (var {k} = 0; {k} < (int)({self.val(a.get('count'))}) && {pl}.PlayerCombatState.OrbQueue.Orbs.Count > 0; {k}++)",
                         f"    await OrbCmd.{fn}({cc}, {pl});"])
        if op == "orb_passive_all":
            o = self.uid("o")
            return wrap([f"foreach (var {o} in {pl}.PlayerCombatState.OrbQueue.Orbs.ToList())",
                         f"    await OrbCmd.Passive({cc}, {o}, null);"])
        if op == "orb_slots":
            n = self.uid("n")
            return wrap([f"var {n} = (int)({self.val(a.get('amount'))});",
                         f"if ({n} > 0) await OrbCmd.AddSlots({pl}, {n});",
                         f"else if ({n} < 0) OrbCmd.RemoveSlots({pl}, -{n});"])
        if op == "orb_grow":
            if C.kind != "orb":
                self.errors.append("'이 구체의 발현 수치 +'는 구체 블록에서만 쓸 수 있습니다.")
                return []
            return [f"{ind}_grow += {self.val(a.get('amount'))};"]
        if op == "stars":
            n = self.uid("n")
            return wrap([f"var {n} = {self.val(a.get('amount'))};",
                         f"if ({n} > 0m) await PlayerCmd.GainStars({n}, {pl});",
                         f"else if ({n} < 0m) await PlayerCmd.LoseStars(-{n}, {pl});"])
        if op == "forge":
            return wrap([f"await ForgeCmd.Forge({self.val(a.get('amount'))}, {pl}, {src});"])
        if op == "osty_summon":
            return wrap([f"await OstyCmd.Summon({cc}, {pl}, {self.val(a.get('amount'))}, {src});"])
        if op == "osty_kill":
            return wrap([f"if ({pl}.IsOstyAlive) await CreatureCmd.Kill({pl}.Osty!);"])
        if op == "osty_attack":
            amt = self.val(a.get("amount"))
            hits = max(1, int(a.get("hits", 1) or 1))
            if C.kind == "card":
                check = "global::MegaCrit.Sts2.Core.Models.Monsters.Osty.CheckMissingWithAnim(Owner)"

                def body(t, i2):
                    return [f"{i2}if (!{check})",
                            f"{i2}    await DamageCmd.Attack({amt}).FromOsty(Owner.Osty!, this, cardPlay).Targeting({t})"
                            f".WithHitCount({hits}).Execute({cc});"]
            else:
                def body(t, i2):
                    return [f"{i2}if ({C.player}?.IsOstyAlive ?? false)",
                            f"{i2}    for (var h_ = 0; h_ < {hits}; h_++)",
                            f"{i2}        await CreatureCmd.Damage({cc}, {t}, {amt}, ValueProp.Move, {C.player}!.Osty!, null, null);"]
            return self.each_target(a.get("who", "target"), ind, body)
        return []

    # ---- 기믹 블록 ----
    def gimmick_stmt(self, b, op, a, ind):
        import gimmick as G
        import modgen as M
        C, cc, me = self.C, self.C.cc, self.C.me
        H = self.helper()
        if op in ("summon", "command", "unsummon"):
            sid = a.get("summon") or ""
            if op == "command" and sid == "*":
                return [f"{ind}await {H}.CommandAll({cc}, {me});"]
            if not G.find_summon(self.project, sid):
                self.errors.append("소환수를 고르세요 ('기믹' 탭에서 먼저 만드세요)." if not sid else f"없는 소환수: {sid}")
                return []
            cls = G.summon_cls(self.project, sid)
            if op == "summon":
                return [f"{ind}await {H}.Summon<{cls}>({cc}, {me}, {C.src});"]
            if op == "command":
                return [f"{ind}await {H}.Command<{cls}>({cc}, {me});"]
            return [f"{ind}await {H}.Unsummon<{cls}>({me});"]
        if op == "pay":
            pm = M.power_meta(self.project, a.get("power"))
            if not pm:
                self.errors.append(f"'낼 수 있으면' 블록: 자원 파워를 고르세요 ({a.get('power') or '없음'}).")
                return []
            lines = [f"{ind}if (await {H}.Pay<{pm['cls']}>({cc}, {me}, {self.val(a.get('amount'))}, {C.src}))", f"{ind}{{"] + \
                self.stmts(b.get("body"), ind + "    ") + [f"{ind}}}"]
            if b.get("else"):
                lines += [f"{ind}else", f"{ind}{{"] + self.stmts(b.get("else"), ind + "    ") + [f"{ind}}}"]
            return lines
        if op == "choice":
            opts = []
            for k, bk in (("opt1", "body"), ("opt2", "else"), ("opt3", "third")):
                lab = a.get(k)
                if _label_text(lab, "ko") or _label_text(lab, "en"):
                    opts.append((lab, b.get(bk) or []))
            if len(opts) < 2:
                self.errors.append("'하나 고르기'에는 이름이 있는 선택지가 2개 이상 필요합니다.")
                return []
            names = []
            for lab, body in opts:
                cls = self.cls_name("Choice")
                names.append(cls)
                if self.extras is not None:
                    owner = "card" if C.kind == "card" else "power"
                    self.extras.append({
                        "kind": "choice", "cls": cls,
                        "title": {"ko": _label_text(lab, "ko"), "en": _label_text(lab, "en"), "zh": _label_text(lab, "zh")},
                        "desc": {"ko": describe(body, self.project, owner, "ko"), "en": describe(body, self.project, owner, "en"),
                                 "zh": describe(body, self.project, owner, "zh")}})
            pv, iv = self.uid("pl"), self.uid("pick")
            mid = self.project["mod"]["id"]
            opt_list = ", ".join(f"{H}.Option<global::{mid}.{mid}Code.Gimmicks.{n}>({pv})" for n in names)
            lines = [f"{ind}{{", f"{ind}    var {pv} = {C.player};", f"{ind}    if ({pv} != null)", f"{ind}    {{",
                     f"{ind}        var {iv} = await {H}.Choose({cc}, {pv}, {opt_list});"]
            for i, (_lab, body) in enumerate(opts):
                lines += [f"{ind}        {'if' if i == 0 else 'else if'} ({iv} == {i})", f"{ind}        {{"] + \
                    self.stmts(body, ind + "            ") + [f"{ind}        }}"]
            return lines + [f"{ind}    }}", f"{ind}}}"]
        if op == "pick":
            pile = a.get("pile", "Discard")
            cv, lst, pv = self.uid("c"), self.uid("picked"), self.uid("pl")
            conds = [G.filter_expr(self.project, a.get("ctype") or "Any", cv)]
            if C.kind == "card":
                conds.append(f"{cv} != this")
            if a.get("action") == "upgrade":
                conds.append(f"{cv}.IsUpgradable")
            act = {"hand": f"await CardPileCmd.Add({cv}, PileType.Hand);",
                   "top": f"await CardPileCmd.Add({cv}, PileType.Draw, CardPilePosition.Top);",
                   "exhaust": f"await CardCmd.Exhaust({cc}, {cv});",
                   "discard": f"await CardCmd.Discard({cc}, {cv});",
                   "upgrade": f"CardCmd.Upgrade({cv});"}.get(a.get("action", "hand"))
            if pile == "Hand" and a.get("action") == "hand":
                self.errors.append("손패에서 골라 손으로 가져올 수는 없습니다.")
            return [f"{ind}{{", f"{ind}    var {pv} = {C.player};",
                    f"{ind}    var {lst} = await {H}.Pick({cc}, {pv}, PileType.{pile}, (int)({self.val(a.get('count'))}), "
                    f"{cv} => {' && '.join(conds)}, this);",
                    f"{ind}    foreach (var {cv} in {lst})", f"{ind}    {{", f"{ind}        {act}", f"{ind}    }}", f"{ind}}}"]
        if op == "delayed":
            cls = self.cls_name("Later")
            mid = self.project["mod"]["id"]
            if self.extras is not None:
                owner = "card" if C.kind == "card" else "power"
                d_ko = describe(b.get("body"), self.project, "power", "ko")
                d_en = describe(b.get("body"), self.project, "power", "en")
                d_zh = describe(b.get("body"), self.project, "power", "zh")
                when = a.get("when", "start")
                self.extras.append({
                    "kind": "delayed", "cls": cls, "when": when, "blocks": copy.deepcopy(b.get("body") or []),
                    "title": {"ko": "예약: 다음 턴" if when == "start" else "예약: 턴 종료",
                              "en": "Next Turn" if when == "start" else "End of Turn",
                              "zh": "预约：下回合" if when == "start" else "预约：回合结束"},
                    "desc": {"ko": (f"다음 턴 시작 시 ([blue]{{Amount}}[/blue]번): " if when == "start" else
                                    "이번 턴이 끝날 때 ([blue]{Amount}[/blue]번): ") + d_ko,
                             "en": ("At the start of your next turn ([blue]{Amount}[/blue] times): " if when == "start" else
                                    "At the end of this turn ([blue]{Amount}[/blue] times): ") + d_en,
                             "zh": ("下回合开始时（[blue]{Amount}[/blue]次）：" if when == "start" else
                                    "本回合结束时（[blue]{Amount}[/blue]次）：") + d_zh}})
                del owner
            # 본문도 미리 검사 (오류를 바로 보여 주려고)
            sub = _Gen(self.project, _power_ctx(), prefix=cls)
            sub.stmts(b.get("body"), ind)
            self.errors += sub.errors
            return [f"{ind}await PowerCmd.Apply<global::{mid}.{mid}Code.Gimmicks.{cls}>({cc}, {me}, {self.val(a.get('times'))}, {me}, {C.src});"]
        return []


def _dec(x):
    try:
        f = float(x)
    except (TypeError, ValueError):
        f = 0.0
    return (str(int(f)) if f.is_integer() else repr(f)) + "m"


def _ident(name):
    import re
    s = re.sub(r"[^0-9A-Za-z_가-힣]", "_", str(name or "a"))
    return s if s and not s[0].isdigit() else "_" + s


def _used_vars(blocks):
    names = set()

    def scan_val(v):
        if isinstance(v, dict):
            if v.get("t") == "var":
                names.add(v.get("name", "a"))
            for k in ("a", "b", "min", "max", "pct"):
                scan_val(v.get(k))
    for b in walk(blocks):
        a = b.get("args", {})
        if b["op"] in ("set_var", "change_var"):
            names.add(a.get("name", "a"))
        for v in a.values():
            scan_val(v)
            if isinstance(v, dict):
                for k in ("a", "b"):
                    scan_val(v.get(k)) if isinstance(v.get(k), dict) else None
    return sorted(names)


def _power_ctx():
    import modgen as M
    return M._Ctx("power", {"id": "x", "trigger": "none", "enemy_mode": "all"})


def compile_blocks(blocks, project, C, ind="        ", prefix="Blk", extras=None, allow_event=False):
    """-> (C# 줄 목록, 오류 목록). extras 목록을 주면 블록이 만든 클래스(선택지 카드·예약 파워) 정보가 쌓인다."""
    g = _Gen(project, C, prefix=prefix, extras=extras, allow_event=allow_event)
    lines = [f"{ind}{{", f"{ind}    // --- 블록 코딩 ---"]
    for n in _used_vars(blocks):
        lines.append(f"{ind}    decimal v_{_ident(n)} = 0m;")
    lines += g.stmts(blocks, ind + "    ")
    lines.append(f"{ind}}}")
    return lines, g.errors

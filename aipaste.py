"""
AI(채팅)가 준 JSON 을 읽고 → 자동으로 고칠 수 있는 건 고치고 → 검사 → 미리보기 → 프로젝트에 합치기.

read_patch(text, project) -> Patch (항목 목록, 고친 것, 오류)
check(project, patch)     -> (새로 생긴 오류, 경고)   — 툴의 modgen.validate 를 그대로 씀
merge(project, patch)     -> 넣은 항목 목록
"""
from __future__ import annotations

import copy
import json
import re

import blockcode as B
import cardframe as CF
import gimmick as G
import modgen as M

import fxbtn
import pets

GIMMICKS = {"tag": ("tags", "태그", G.new_tag), "summon": ("summons", "소환수", G.new_summon), "orb": ("orbs", "구체", G.new_orb), "pet": ("pets", "동료", pets.new_pet), "fx": ("effects", "이펙트", fxbtn.new_effect), "button": ("buttons", "버튼", fxbtn.new_button)}
KINDS = ("card", "relic", "potion", "power")
KEY = {"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}
NOUN = {"card": "카드", "relic": "유물", "potion": "물약", "power": "파워"}
NOUN.update({k: v[1] for k, v in GIMMICKS.items()})
FACTORY = {"card": M.new_card, "relic": M.new_relic, "potion": M.new_potion, "power": M.new_power}
EXTRA_KEYS = {"name_zh", "desc_zh", "flavor_zh", "frame_style"}
ENUMS = {
    "card": {"type": M.CARD_TYPES, "rarity": M.CARD_RARITIES, "target": M.CARD_TARGETS, "tag": M.CARD_TAGS,
             "upgrade_add_keyword": [("", "없음")] + M.CARD_KEYWORDS,
             "upgrade_remove_keyword": [("", "없음")] + M.CARD_KEYWORDS},
    "relic": {"rarity": M.RELIC_RARITIES, "trigger": M.RELIC_TRIGGERS, "enemy_mode": M.RELIC_ENEMY_MODES},
    "potion": {"rarity": M.POTION_RARITIES, "target": M.POTION_TARGETS},
    "power": {"type": M.POWER_TYPES, "stack": M.POWER_STACKS, "trigger": M.POWER_TRIGGERS, "decay": M.POWER_DECAY,
              "played_by": M.POWER_PLAYED_BY, "enemy_mode": M.RELIC_ENEMY_MODES},
}
INTS = {"cost", "upgrade_cost", "played_every", "res_cost", "star_cost", "star_cost_up", "cap", "threshold"}


class Patch:
    def __init__(self):
        self.items = []      # dict(kind, item, exists, take)
        self.fixes = []      # 자동으로 고친 것 (사람이 읽을 문장)
        self.errors = []     # 읽기 단계 오류 (JSON 이 깨짐, 모르는 블록 등)
        self.notes = []      # AI 가 앞에 쓴 설명 등


# ---------------------------------------------------------------------------
# 1) 글에서 JSON 꺼내기
# ---------------------------------------------------------------------------
_FENCE = re.compile(r"```[ \t]*([A-Za-z0-9_-]*)[ \t]*\n(.*?)```", re.S)


def _strip_json(src):
    """문자열 밖의 // · /* */ 주석과 끝 쉼표를 지우고, 휘어진 따옴표를 곧게."""
    src = src.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    src = src.replace("﻿", "")
    out, i, n, in_str = [], 0, len(src), False
    while i < n:
        ch = src[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(src[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        if src.startswith("//", i):
            while i < n and src[i] != "\n":
                i += 1
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            i = n if j < 0 else j + 2
            continue
        out.append(ch)
        i += 1
    s = "".join(out)
    return re.sub(r",(\s*[}\]])", r"\1", s)


def extract(text):
    """(파이썬 객체, 고친 것 목록) — 실패하면 ValueError."""
    text = text or ""
    blocks = [(lang.lower(), body) for lang, body in _FENCE.findall(text)]
    cands = [b for l, b in blocks if l in ("json", "jsonc", "")] or [b for _l, b in blocks]
    tagged = [b for b in cands if "sts2mod-patch" in b]
    if tagged:
        src = max(tagged, key=len)
    elif cands:
        src = max(cands, key=len)
    else:
        a, b = text.find("{"), text.rfind("}")
        a2, b2 = text.find("["), text.rfind("]")
        if a < 0 and a2 < 0:
            raise ValueError("JSON 을 찾지 못했습니다. AI 답에서 ```json 으로 시작하는 부분을 통째로 붙여 넣어 주세요.")
        if a < 0 or (0 <= a2 < a):
            a, b = a2, b2
        src = text[a:b + 1]
    fixes = []
    try:
        return json.loads(src), fixes
    except ValueError:
        pass
    cleaned = _strip_json(src)
    try:
        obj = json.loads(cleaned)
        fixes.append("JSON 의 주석·끝 쉼표·휘어진 따옴표를 정리했습니다.")
        return obj, fixes
    except ValueError as e:
        line = cleaned.splitlines()[e.lineno - 1] if getattr(e, "lineno", 0) and e.lineno <= len(cleaned.splitlines()) else ""
        raise ValueError(f"JSON 형식 오류: {e.msg} ({e.lineno}번째 줄 {e.colno}번째 글자)\n  → {line.strip()[:120]}") from None


# ---------------------------------------------------------------------------
# 2) 모양 맞추기 / 자동 고치기
# ---------------------------------------------------------------------------
def _guess_kind(it):
    k = str(it.get("kind") or it.get("category") or it.get("item_type") or "").lower()
    for kk, words in (("card", ("card", "카드")), ("relic", ("relic", "유물")), ("potion", ("potion", "물약")),
                      ("power", ("power", "파워", "buff", "debuff"))):
        if k in words or k == KEY[kk]:
            return kk
    if "cost" in it or "upgrade_cost" in it or "keywords" in it:
        return "card"
    if "stack" in it or "decay" in it or "modifiers" in it:
        return "power"
    if any(x.startswith("flavor") for x in it) or "played_every" in it:
        return "relic"
    if "trigger" in it:
        return "relic"
    return "potion"


def _items_from(obj, patch):
    out = []
    if isinstance(obj, dict) and ("gimmicks" in obj or any(k in obj for k in ("cards", "relics", "potions", "powers", "card", "relic", "potion", "power"))):
        for kind in KINDS:
            for key in (KEY[kind], kind):
                v = obj.get(key)
                if v is None:
                    continue
                for it in (v if isinstance(v, list) else [v]):
                    if isinstance(it, dict):
                        out.append((kind, it))
                    else:
                        patch.errors.append(f"'{key}' 안에 객체가 아닌 값이 있습니다: {str(it)[:60]}")
        groups = obj.get("gimmicks", {})
        if not isinstance(groups, dict):
            patch.errors.append("gimmicks는 종류별 목록을 담은 객체여야 합니다.")
        else:
            for kind, (group, label, factory) in GIMMICKS.items():
                rows = groups.get(group, [])
                if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                    patch.errors.append(f"{label}에는 항목 목록을 넣어 주세요.")
                    continue
                for row in rows:
                    out.append((kind, row))
            for group in groups.keys() - {v[0] for v in GIMMICKS.values()}:
                patch.errors.append(f"지원하지 않는 기믹 종류: {group}")
        other = [k for k in obj if k not in ("format", "gimmicks", "cards", "relics", "potions", "powers", "card", "relic", "potion", "power",
                                             "notes", "note", "description", "summary")]
        if other:
            patch.fixes.append(f"알 수 없는 최상위 칸은 무시했습니다: {', '.join(other)}")
        for nk in ("notes", "note", "description", "summary"):
            if isinstance(obj.get(nk), str):
                patch.notes.append(obj[nk])
    elif isinstance(obj, list):
        for it in obj:
            if isinstance(it, dict):
                out.append((_guess_kind(it), it))
        if out:
            patch.fixes.append("목록 형식이라 각 항목의 종류를 칸 이름으로 짐작했습니다.")
    elif isinstance(obj, dict) and "id" in obj:
        out.append((_guess_kind(obj), obj))
        patch.fixes.append(f"항목 하나만 있어 {NOUN[out[0][0]]}로 짐작했습니다.")
    else:
        patch.errors.append('카드·유물·물약·파워가 없습니다. {"cards": [...], "powers": [...]} 같은 형식이어야 합니다.')
    return out


def _fix_id(raw, where, patch):
    s = str(raw or "").strip()
    fixed = re.sub(r"[^a-z0-9_]", "", re.sub(r"[\s\-]+", "_", s.lower()))
    fixed = re.sub(r"_+", "_", fixed).strip("_")
    if fixed and not fixed[0].isalpha():
        fixed = "x_" + fixed
    if fixed != s:
        if fixed:
            patch.fixes.append(f"{where}: ID '{s}' → '{fixed}' (영문 소문자·숫자·_ 만)")
        else:
            patch.errors.append(f"{where}: ID '{s}' 를 쓸 수 없습니다 (영문 소문자로 시작, 소문자·숫자·_ 만).")
    return fixed


def _enum(val, options, where, field, patch):
    """대소문자 · 한국어 이름도 받아준다."""
    if val is None:
        return None
    s = str(val).strip()
    for v, lab in options:
        if s == v:
            return v
    for v, lab in options:
        if s.lower() == v.lower() or s == lab or (lab and s == lab.split(" (")[0]):
            patch.fixes.append(f"{where}: {field} '{s}' → '{v}'")
            return v
    patch.errors.append(f"{where}: {field} '{s}' 은(는) 쓸 수 없는 값입니다. 가능한 값: {', '.join(v for v, _l in options if v) }")
    return None


def _power_ref(val, ctx, where, field, patch):
    """파워 참조 고치기: 'strength' → 'Strength', '힘' → 'Strength', 'ember' → 'c:ember'."""
    if val in (None, ""):
        return val
    s = str(val).strip()
    if s in M.POWERS or s.startswith(("c:", "s:", "x:")):
        if s.startswith("c:") and s[2:] not in ctx["powers"]:
            patch.errors.append(f"{where}: {field} '{s}' — 그런 새 파워가 없습니다 (프로젝트나 이 답의 powers 에 있어야 함).")
        if s.startswith("s:") and s[2:] not in ctx["summons"]:
            patch.errors.append(f"{where}: {field} '{s}' — 그런 소환수가 없습니다.")
        return s
    for k, v in M.POWERS.items():
        if s.lower() in (k.lower(), v[0].lower(), v[2].lower()) or s == v[1]:
            patch.fixes.append(f"{where}: {field} '{s}' → '{k}'")
            return k
    sid = s[:-6] if s.lower().endswith("_power") else s
    sid = re.sub(r"[\s\-]+", "_", sid.lower())
    if sid in ctx["powers"]:
        patch.fixes.append(f"{where}: {field} '{s}' → 'c:{sid}' (새 파워는 c: 를 붙임)")
        return "c:" + sid
    for pid, names in ctx["power_names"].items():
        if s in names:
            patch.fixes.append(f"{where}: {field} '{s}' → 'c:{pid}'")
            return "c:" + pid
    patch.errors.append(f"{where}: {field} '{s}' — 모르는 파워입니다. 게임 파워({', '.join(M.POWERS)}) 또는 \"c:<새 파워 ID>\".")
    return s


def _num(v, default, where, field, patch, as_int=True):
    if v is None or v == "":
        return default
    try:
        f = float(v)
    except (TypeError, ValueError):
        patch.errors.append(f"{where}: {field} '{v}' 는 숫자가 아닙니다.")
        return default
    return int(round(f)) if as_int else f


def _fix_value(v, ctx, where, patch):
    if not isinstance(v, dict):
        if isinstance(v, (int, float)) or (isinstance(v, str) and re.fullmatch(r"-?\d+(\.\d+)?", v.strip())):
            return {"t": "num", "v": float(v) if "." in str(v) else int(float(v))}
        return v
    if v.get("t") in ("stack", "has") and v.get("power"):
        v["power"] = _power_ref(v["power"], ctx, where, "블록 파워", patch)
    for k in ("a", "b", "min", "max", "pct"):
        if k in v:
            v[k] = _fix_value(v[k], ctx, where, patch)
    return v


def _fix_cond(c, ctx, where, patch):
    if not isinstance(c, dict):
        return c
    if c.get("t") == "group":
        c["items"] = [_fix_cond(x, ctx, where, patch) for x in c.get("items", [])]
        return c
    if c.get("t") == "has" and c.get("power"):
        c["power"] = _power_ref(c["power"], ctx, where, "조건 파워", patch)
    if c.get("t") in ("and", "or", "not"):
        for k in ("a", "b"):
            if k in c:
                c[k] = _fix_cond(c[k], ctx, where, patch)
    else:
        for k in ("a", "b", "pct", "value", "count"):
            if k in c:
                c[k] = _fix_value(c[k], ctx, where, patch)
    return c


def _fix_blocks(blocks, ctx, where, patch):
    out = []
    for b in blocks or []:
        if not isinstance(b, dict):
            patch.errors.append(f"{where}: 블록이 객체가 아닙니다: {str(b)[:50]}")
            continue
        op = b.get("op")
        if op not in B.SPECS:
            patch.errors.append(f"{where}: 모르는 블록 '{op}'. 쓸 수 있는 블록: {', '.join(B.SPECS)}")
            continue
        nb = B.new_block(op)
        args = dict(b.get("args")) if isinstance(b.get("args"), dict) else {}
        if op in B.F.FAMILIES:
            mode = args.get("mode", b.get("mode", nb["args"]["mode"]))
            if not isinstance(mode,str) or mode not in dict(B.F.FAMILIES[op][1]):
                patch.errors.append(f"{where}: 블록 '{op}'의 실행 방식을 다시 선택하세요: {mode}")
                continue
            B.F.switch(nb, mode, B.SPECS)
        schema = B.block_spec(nb)["args"]
        # args 없이 바로 쓴 경우도 받아준다
        for k in schema:
            if k not in args and k in b:
                args[k] = b[k]
        for k, val in args.items():
            if k not in schema:
                patch.fixes.append(f"{where}: 블록 '{op}' 의 모르는 칸 '{k}' 무시")
                continue
            kind = schema[k][0]
            if kind == "value":
                val = _fix_value(val, ctx, where, patch)
            elif kind == "cond":
                val = _fix_cond(val, ctx, where, patch)
            elif kind == "power":
                val = _power_ref(val, ctx, where, f"블록 '{op}' 파워", patch)
            elif kind == "int":
                val = _num(val, 1, where, k, patch)
            nb["args"][k] = val
        for bk in B.BODY_KEYS:
            if bk in nb:
                nb[bk] = _fix_blocks(b.get(bk), ctx, where, patch)
        out.append(nb)
    return out


def _fix_effects(effs, kind, ctx, where, patch):
    out = []
    labels = M.EFFECT_KINDS + [("power", "apply_power"), ("draw", "cards"), ("energy", "gain_energy")]
    for i, e in enumerate(effs or []):
        w = f"{where} 효과 {i + 1}"
        if not isinstance(e, dict):
            patch.errors.append(f"{w}: 객체가 아닙니다.")
            continue
        k = _enum(e.get("kind", "damage"), labels, w, "kind", patch) or "damage"
        if k == "code" and not e.get("blocks") and not e.get("code"):
            patch.errors.append(f"{w}: kind 'code' 에는 blocks 가 있어야 합니다.")
        power = _power_ref(e.get("power"), ctx, w, "power", patch) if k in ("power", "remove_power") else None
        ne = M.new_effect(k, _num(e.get("amount"), 0 if k in ("remove_power", "code") else 1, w, "amount", patch),
                          _num(e.get("upgrade"), 0, w, "upgrade", patch) if kind == "card" else 0,
                          max(1, _num(e.get("hits"), 1, w, "hits", patch)),
                          power or "Strength", e.get("target"))
        if ne["target"] not in ("self", "enemy", "other"):
            fixed = {"enemy": "enemy", "target": "enemy", "enemies": "enemy", "player": "self", "me": "self"}.get(str(ne["target"]).lower())
            if fixed:
                patch.fixes.append(f"{w}: target '{ne['target']}' → '{fixed}'")
                ne["target"] = fixed
            else:
                patch.errors.append(f"{w}: target '{ne['target']}' 은(는) \"self\" | \"enemy\" | \"other\" 중 하나여야 합니다.")
        if ne["target"] == "other" and kind != "power":
            patch.errors.append(f"{w}: target \"other\" 는 파워의 효과에서만 쓸 수 있습니다.")
        ne["per_stack"] = bool(e.get("per_stack")) and kind == "power"
        if e.get("x_use"):
            xu = _enum(e["x_use"], M.X_USES, w, "x_use", patch)
            ne["x_use"] = xu or ""
        for f in ("cond_power", "scale_power"):
            if e.get(f):
                ne[f] = _power_ref(e[f], ctx, w, f, patch)
        for f, d in (("cond_min", 1), ("scale_per", 1)):
            if f in e:
                ne[f] = _num(e[f], d, w, f, patch)
        for f in ("cond_on", "scale_on"):
            if e.get(f) in ("self", "target"):
                ne[f] = e[f]
        if k == "code":
            ne["blocks"] = _fix_blocks(e.get("blocks"), ctx, w, patch)
            ne["auto_text"] = bool(e.get("auto_text", True)) if ne["blocks"] else False
            ne["code"] = str(e.get("code") or "") if not ne["blocks"] else ""
            for lang in ("ko", "en", "zh"):
                if e.get(f"text_{lang}"):
                    ne[f"text_{lang}"] = str(e[f"text_{lang}"])
        out.append(ne)
    return out


def _fix_item(kind, raw, ctx, patch):
    raw = copy.deepcopy(raw)
    name = raw.get("name_ko") or raw.get("name_en") or raw.get("id") or "?"
    where = f"{NOUN[kind]} '{name}'"
    base = FACTORY[kind](raw.get("id") or "x")
    allowed = set(base) | EXTRA_KEYS
    unknown = [k for k in raw if k not in allowed and k not in ("kind", "category", "item_type", "image")]
    if unknown:
        patch.fixes.append(f"{where}: 모르는 칸 무시 — {', '.join(unknown)}")
    it = base
    it["id"] = _fix_id(raw.get("id") or name, where, patch)
    for k, v in raw.items():
        if k in allowed and k not in ("id", "effects", "modifiers", "image"):
            it[k] = v
    for field, opts in ENUMS[kind].items():
        if field in raw:
            v = _enum(raw[field], opts, where, field, patch)
            it[field] = v if v is not None else base[field]
    if "played_filter" in raw:
        flt = [f for f, _l in G.card_filters(ctx["project_view"])]
        v = str(raw["played_filter"])
        if v not in flt:
            fv = _enum(v, [(f, f) for f in flt], where, "played_filter", patch)
            it["played_filter"] = fv or "Any"
    for f in INTS & set(raw):
        it[f] = _num(raw[f], base.get(f, 0), where, f, patch)
    if kind == "card":
        if "upgrade_cost" not in raw and "cost" in raw:
            it["upgrade_cost"] = it["cost"]
        for f in ("cost", "upgrade_cost"):
            if not 0 <= int(it.get(f, 0)) <= 9:
                patch.errors.append(f"{where}: {f} {it[f]} — 에너지 비용은 0~9 입니다.")
        kws = []
        for kw in raw.get("keywords") or []:
            v = _enum(kw, M.CARD_KEYWORDS, where, "keywords", patch)
            if v and v not in kws:
                kws.append(v)
        it["keywords"] = kws
        if raw.get("res_power"):
            it["res_power"] = _power_ref(raw["res_power"], ctx, where, "res_power", patch)
        fs = raw.get("frame_style", "")
        if fs and fs != CF.GAME and fs not in ctx["frames"]:
            patch.errors.append(f"{where}: frame_style '{fs}' — 그런 카드 테두리 디자인이 없습니다.")
        it["gtags"] = [t for t in (raw.get("gtags") or []) if t in ctx["tags"]]
        if len(it["gtags"]) != len(raw.get("gtags") or []):
            patch.errors.append(f"{where}: gtags 에 없는 태그가 있습니다 (있는 태그: {', '.join(ctx['tags']) or '없음'}).")
    if kind == "power":
        mods = []
        for i, m in enumerate(raw.get("modifiers") or []):
            w = f"{where} 상시 효과 {i + 1}"
            if not isinstance(m, dict):
                continue
            mk = _enum(m.get("kind"), M.MODIFIER_KINDS, w, "kind", patch)
            if not mk:
                continue
            nm = M.new_modifier(mk, _num(m.get("value"), 1, w, "value", patch), bool(m.get("per_stack", True)))
            nm["filter"] = str(m.get("filter") or "Any")
            nm["ref"] = str(m.get("ref") or "")
            if mk in ("res_cap", "res_cost") and nm["ref"]:
                nm["ref"] = _power_ref(nm["ref"], ctx, w, "ref", patch)
            mods.append(nm)
        it["modifiers"] = mods
    it["effects"] = _fix_effects(raw.get("effects"), kind, ctx, where, patch)
    if not it["effects"] and not it.get("modifiers") and kind != "power":
        patch.fixes.append(f"{where}: 효과가 없습니다.")
    for lang in ("ko", "en"):
        if not it.get(f"name_{lang}"):
            it[f"name_{lang}"] = it.get("name_en" if lang == "ko" else "name_ko") or it["id"]
    it["image"] = ""
    return it


def read_patch(text, project):
    patch = Patch()
    try:
        obj, fx = extract(text)
    except ValueError as e:
        patch.errors.append(str(e))
        return patch
    patch.fixes += fx
    pairs = _items_from(obj, patch)
    # 이 답 안의 새 파워도 참조할 수 있게 먼저 모은다
    new_powers = {}
    for kind, raw in pairs:
        if kind == "power" and raw.get("id"):
            pid = re.sub(r"[^a-z0-9_]", "", re.sub(r"[\s\-]+", "_", str(raw["id"]).lower()))
            new_powers[pid] = {raw.get("name_ko"), raw.get("name_en"), raw.get("name_zh"), pid} - {None, ""}
    g = project.get("gimmicks") or {}
    ctx = {"powers": {p["id"] for p in project.get("powers", [])} | set(new_powers),
           "power_names": {**{p["id"]: {p.get("name_ko"), p.get("name_en")} - {None, ""} for p in project.get("powers", [])},
                           **new_powers},
           "summons": {s["id"] for s in g.get("summons", [])},
           "tags": [t["id"] for t in g.get("tags", [])],
           "frames": {s["id"] for s in CF.styles(project)},
           "project_view": project}
    view = copy.deepcopy(project)
    prepared = {}
    for kind, raw in pairs:
        if kind not in GIMMICKS:
            continue
        group, label, factory = GIMMICKS[kind]
        ident = _fix_id(raw.get("id"), label, patch)
        if not ident:
            patch.errors.append(f"{label}에 ID가 필요합니다.")
        item = factory(ident)
        for key in item.keys() & raw.keys() - {"id", "image"}:
            if type(raw[key]) is type(item[key]):
                item[key] = copy.deepcopy(raw[key])
            else:
                patch.errors.append(f"{label} {ident}: {key} 값 형식을 확인하세요.")
        prepared[id(raw)] = item
        view.setdefault("gimmicks", {}).setdefault(group, []).append(item)
    ctx.update(project_view=view, tags=[t["id"] for t in G.tags(view)],
               summons={t["id"] for t in view["gimmicks"].get("summons", [])} if "gimmicks" in view else set())
    seen = {}
    for kind, raw in pairs:
        it = prepared[id(raw)] if kind in GIMMICKS else _fix_item(kind, raw, ctx, patch)
        if not it["id"]:
            continue
        if it["id"] in seen:
            previous = seen[it["id"]]
            patch.errors.append(f"AI 답변의 ID '{it['id']}' 중복 ({NOUN[previous]}, {NOUN[kind]}). 항목마다 다른 ID를 사용하세요.")
            continue
        seen[it["id"]] = kind
        existing = g.get(GIMMICKS[kind][0], []) if kind in GIMMICKS else project.get(KEY[kind], [])
        exists = any(x["id"] == it["id"] for x in existing)
        other = not exists and it["id"] in _all_ids(project)
        if other:
            patch.errors.append(f"{NOUN[kind]} ID '{it['id']}' 가 다른 종류(카드·유물·기믹 등)의 ID 와 겹칩니다.")
        patch.items.append({"kind": kind, "item": it, "exists": exists, "take": True})
    return patch


def missing_selections(patch):
    """Walk dependencies of selected AI items, including nested block arguments."""
    pending = [x for x in patch.items if x["take"]]
    available = {(x["kind"], x["item"]["id"]): x for x in patch.items if not x["take"] and not x["exists"]}
    needed = []
    def refs(node):
        if isinstance(node, list):
            for child in node:
                yield from refs(child)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key == "gtags" and isinstance(value, list):
                    yield from (("tag", t) for t in value if isinstance(t, str))
                elif isinstance(value, str):
                    if key in ("card", "card_id", "summon", "orb", "pet", "button", "fx"):
                        yield "card" if key == "card_id" else key, value
                    if key in ("filter", "result_filter", "ctype", "played_filter") and value.startswith("tag:"):
                        yield "tag", value[4:]
                    if key in ("power", "scale_power", "cond_power", "res_power", "ref"):
                        if value.startswith("c:"):
                            yield "power", value[2:]
                        elif value.startswith("s:"):
                            yield "summon", value[2:]
                else:
                    yield from refs(value)
    while pending:
        for key in refs(pending.pop()["item"]):
            match = available.pop(key, None)
            if match:
                needed.append(match)
                pending.append(match)
    return needed


def change_lines(old, new):
    labels = {"max_rank": "최대 단계", "timing": "발동 시점", "name_ko": "한국어 이름",
              "blocks": "실행 블록", "amount": "수치", "v": "값", "passive_blocks": "지속 효과"}
    def compare(a, b, path):
        if a == b:
            return
        if isinstance(a, dict) and isinstance(b, dict):
            for k in sorted(a.keys() | b.keys()):
                yield from compare(a.get(k), b.get(k), path + [labels.get(k, k)])
        elif isinstance(a, list) and isinstance(b, list):
            for i in range(max(len(a), len(b))):
                yield from compare(a[i] if i < len(a) else None, b[i] if i < len(b) else None, path + [f"{i+1}번째"])
        else:
            yield f"{' › '.join(path)}: {a if a is not None else '없음'} → {b if b is not None else '없음'}"
    return list(compare(old, {**new, **({"image": old["image"]} if old.get("image") else {})}, []))


def _all_ids(project):
    ids = {x["id"] for k in KEY.values() for x in project.get(k, [])}
    g = project.get("gimmicks") or {}
    for k in ("tags", "summons", "orbs", "effects", "buttons", "pets"):
        ids |= {x["id"] for x in g.get(k, []) or []}
    ids.add((project.get("character") or {}).get("id"))
    return ids


# ---------------------------------------------------------------------------
# 3) 검사 / 합치기
# ---------------------------------------------------------------------------
def _unique(project, base):
    used = _all_ids(project)
    if base not in used:
        return base
    i = 0
    while True:
        cand = f"{base}_{'abcdefghijklmnopqrstuvwxyz'[i % 26] * (1 + i // 26)}"
        if cand not in used:
            return cand
        i += 1


def _rename_refs(obj, kind, old, new):
    """같은 답 안의 참조를 새 ID 로 (파워 'c:old', 카드 블록의 card: old)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if kind == "power" and v == "c:" + old:
                obj[k] = "c:" + new
            elif kind in GIMMICKS and k == kind and v == old:
                obj[k] = new
            elif kind == "tag" and k == "gtags" and isinstance(v, list):
                obj[k] = [new if tag == old else tag for tag in v]
            elif kind == "tag" and v == "tag:" + old:
                obj[k] = "tag:" + new
            elif kind == "summon" and v == "s:" + old:
                obj[k] = "s:" + new
            elif kind == "card" and k in ("card", "card_id") and v == old:
                obj[k] = new
            else:
                _rename_refs(v, kind, old, new)
    elif isinstance(obj, list):
        for v in obj:
            _rename_refs(v, kind, old, new)


def apply(project, patch, keep_existing=False):
    """project 를 직접 바꾼다. keep_existing 이면 같은 ID 는 새 ID 로 추가. 넣은 (kind, id) 목록을 돌려준다."""
    added = []
    takes = [x for x in patch.items if x["take"]]
    if keep_existing:
        for x in takes:
            if x["exists"]:
                old = x["item"]["id"]
                new = _unique(project, old)
                x["item"]["id"] = new
                for y in takes:
                    _rename_refs(y["item"], x["kind"], old, new)
                x["exists"] = False
    # 파워 먼저 (다른 항목이 참조)
    for x in sorted(takes, key=lambda x: 0 if x["kind"] == "power" else 1):
        kind = x["kind"]
        lst = (project.setdefault("gimmicks", {}).setdefault(GIMMICKS[kind][0], [])
               if kind in GIMMICKS else project.setdefault(KEY[kind], []))
        it = copy.deepcopy(x["item"])
        idx = next((i for i, y in enumerate(lst) if y["id"] == it["id"]), None)
        if idx is not None:
            keep = {k: lst[idx][k] for k in ("image",) if lst[idx].get(k)}
            it.update(keep)
            lst[idx] = it
        else:
            lst.append(it)
        added.append((x["kind"], it["id"]))
    M.normalize(project)
    return added


def check(project, patch, keep_existing=False):
    """넣었을 때 새로 생기는 오류·경고만."""
    try:
        base_e, base_w = M.validate(M.normalize(copy.deepcopy(project)))
    except Exception:  # noqa: BLE001
        base_e, base_w = [], []
    tmp = copy.deepcopy(project)
    p2 = copy.deepcopy(patch)
    try:
        apply(tmp, p2, keep_existing)
        e, w = M.validate(tmp)
    except Exception as ex:  # noqa: BLE001
        return [f"검사 중 오류: {ex}"], []
    return [x for x in e if x not in base_e], [x for x in w if x not in base_w]


def describe(project, kind, it, lang="ko"):
    """미리보기용 설명 (자동 생성)."""
    if kind in GIMMICKS:
        return M.text(it, "desc", lang) or M.text(it, "name", lang), project, it
    tmp = copy.deepcopy(project)
    lst = tmp.setdefault(KEY[kind], [])
    lst[:] = [y for y in lst if y["id"] != it["id"]] + [copy.deepcopy(it)]
    M.normalize(tmp)
    item = next(y for y in tmp[KEY[kind]] if y["id"] == it["id"])
    try:
        return M.description(tmp, item, kind, lang), tmp, item
    except Exception as e:  # noqa: BLE001
        return f"(설명을 만들 수 없음: {e})", tmp, item

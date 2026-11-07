"""
AI 이미지 설명서 + 한꺼번에 적용.

1) slots(project)        : 모드에 필요한 모든 그림 칸 (카드 삽화·유물·물약·파워 아이콘·캐릭터 선택 초상화·지도 표시·
                           상단 아이콘·에너지 아이콘·전투 스탠딩·공격/피격 모션·동료·소환수·구체·이펙트 그림)
2) build_guide(...)      : 채팅 AI (ChatGPT·Claude·Gemini 등) 에게 그대로 줄 설명서. 칸마다 파일 이름·크기·배경·
                           무엇을 그릴지 + 카드 삽화는 '카드 원화 구도 설계 스킬' 을 적용한다.
3) match_files / apply   : AI 가 만든 그림 폴더를 고르면 파일 이름(또는 #번호)으로 칸을 찾아
                           크기 맞추기·배경 지우기를 한 뒤 모든 칸에 한 번에 넣는다.
"""
from __future__ import annotations

import os
import re

# kind -> (가로, 세로, 맞추는 방식, 투명 배경, 설명)
#   cover   : 꽉 채우고 넘치는 부분은 가운데 기준으로 자름 (카드 삽화·선택 초상화)
#   contain : 비율 유지, 남는 곳은 투명 (아이콘)
#   sprite  : 크기 유지 (너무 크면 줄임) + 배경 지우기 (스탠딩·모션·동료·이펙트)
SPECS = {
    "card": (1000, 760, "cover", False, "카드 삽화"),
    "relic": (256, 256, "contain", True, "유물 아이콘"),
    "potion": (256, 256, "contain", True, "물약 아이콘"),
    "power": (256, 256, "contain", True, "파워(버프·디버프) 아이콘"),
    "summon": (256, 256, "contain", True, "소환수 아이콘"),
    "orb": (128, 128, "contain", True, "구체 아이콘"),
    "pet": (0, 0, "sprite", True, "동료 전투 모습"),
    "fx": (0, 0, "sprite", True, "이펙트 그림"),
    "char_combat": (0, 0, "sprite", True, "캐릭터 전투 스탠딩"),
    "char_attack": (0, 0, "sprite", True, "캐릭터 공격 모션 프레임"),
    "char_hit": (0, 0, "sprite", True, "캐릭터 피격 모션 프레임"),
    "char_select": (132, 195, "cover", False, "캐릭터 선택 화면 초상화"),
    "char_select_bg": (1920, 1080, "cover", False, "캐릭터 선택 화면 전체 배경"),
    "char_icon": (88, 88, "contain", True, "상단 캐릭터 아이콘"),
    "char_map": (49, 64, "contain", True, "지도 위치 표시"),
    "char_energy": (74, 74, "contain", True, "카드 비용 에너지 아이콘"),
    "char_energy_text": (24, 24, "contain", True, "설명 글 속 작은 에너지 아이콘"),
}
SPRITE_MAX = 1024
GROUPS = [("character", "캐릭터"), ("pet", "동료"), ("card", "카드"), ("relic", "유물"), ("potion", "물약"),
          ("power", "파워"), ("gimmick", "소환수·구체"), ("fx", "이펙트")]
DEFAULT_ATTACK_FRAMES = 3
DEFAULT_HIT_FRAMES = 2


# ---------------------------------------------------------------------------
# 칸 목록
# ---------------------------------------------------------------------------
def _txt(item, field, lang="ko"):
    return (item.get(f"{field}_{lang}") or item.get(f"{field}_ko") or item.get(f"{field}_en") or "").strip()


def plain(text):
    t = str(text or "")
    t = re.sub(r"\{IfUpgraded:show:([^|}]*)\|([^}]*)\}", r"\2", t)
    t = re.sub(r"\[/?[a-zA-Z_]+\]", "", t)
    t = re.sub(r"\{([A-Za-z]\w*)(?::[^}]*)?\}", r"\1", t)
    return re.sub(r"\s+", " ", t).strip()


def _desc(project, item, kind):
    import modgen as M
    try:
        d = M.description(project, item, kind, "ko")
        if kind == "card":
            import preview as PV
            d = PV.fill_values(project, d, item, False)
    except Exception:          # 설명을 못 만들어도 설명서는 만든다
        d = item.get("desc_ko", "")
    return plain(d)


def slots(project):
    """-> [{key, group, kind, title, name, desc, obj, field, index, current, extra}] (설명서 번호 순)."""
    import gimmick as GM
    import pets as PT
    import fxbtn as FX
    out = []

    def add(key, group, kind, title, name, desc, obj, field, index=None, extra=None):
        cur = ""
        if index is None:
            cur = obj.get(field) or ""
        else:
            lst = obj.get(field) or []
            cur = (lst[index].get("image") or "") if index < len(lst) else ""
        out.append({"key": key, "group": group, "kind": kind, "title": title, "name": name, "desc": desc,
                    "obj": obj, "field": field, "index": index, "current": cur, "extra": extra or {}})

    ch = project.get("character") or {}
    if ch.get("enabled"):
        cname = f"{_txt(ch, 'name')} ({ch.get('name_en', '')})"
        cdesc = plain(_txt(ch, "desc"))
        add("char_combat", "character", "char_combat", "전투 스탠딩 (기준 그림)", cname, cdesc, ch, "combat_image")
        add("char_select", "character", "char_select", "캐릭터 선택 화면 초상화", cname, cdesc, ch, "select_image")
        add("char_select_bg", "character", "char_select_bg", "캐릭터 선택 화면 전체 배경", cname, cdesc, ch, "select_bg_image")
        add("char_icon", "character", "char_icon", "상단 캐릭터 아이콘", cname, cdesc, ch, "icon_image")
        add("char_map_marker", "character", "char_map", "지도 위치 표시", cname, cdesc, ch, "map_marker_image")
        add("char_energy", "character", "char_energy", "에너지 아이콘 (카드 비용)", cname, cdesc, ch, "energy_icon_image")
        add("char_energy_text", "character", "char_energy_text", "작은 에너지 아이콘 (설명 글 속)", cname, cdesc, ch,
            "energy_text_icon_image")
        for key, kind, title, default in (("attack_frames", "char_attack", "공격 모션", DEFAULT_ATTACK_FRAMES),
                                          ("hit_frames", "char_hit", "피격 모션", DEFAULT_HIT_FRAMES)):
            n = max(len(ch.get(key) or []), default)
            for i in range(n):
                add(f"char_{'attack' if kind == 'char_attack' else 'hit'}_{i + 1}", "character", kind,
                    f"{title} {i + 1}/{n}", cname, cdesc, ch, key, index=i, extra={"frame": i + 1, "frames": n})
    for p in PT.pets(project):
        add(f"pet_{p['id']}", "pet", "pet", "동료 전투 모습", f"{_txt(p, 'name')} ({p.get('name_en', '')})",
            plain(_txt(p, "desc")), p, "image")
    for c in project.get("cards", []):
        add(f"card_{c['id']}", "card", "card", "카드 삽화", f"{_txt(c, 'name')} ({c.get('name_en', '')})",
            _desc(project, c, "card"), c, "image",
            extra={"type": c.get("type"), "cost": c.get("cost"), "target": c.get("target"), "rarity": c.get("rarity"),
                   "comp": card_composition(c)})
    upgraded_from = {r.get("upgrade_relic"): r for r in project.get("relics", []) if r.get("upgrade_relic")}
    for kind, lst in (("relic", "relics"), ("potion", "potions"), ("power", "powers")):
        for it in project.get(lst, []):
            ex = {"ptype": it.get("type")} if kind == "power" else {}
            if kind == "relic" and it["id"] in upgraded_from:
                src = upgraded_from[it["id"]]
                ex["upgrade_of"] = (f"{_txt(src, 'name')} ({src.get('name_en', '')})", f"relic_{src['id']}.png")
            add(f"{kind}_{it['id']}", kind, kind, SPECS[kind][4], f"{_txt(it, 'name')} ({it.get('name_en', '')})",
                _desc(project, it, kind), it, "image", extra=ex)
    for s in GM.summons(project):
        add(f"summon_{s['id']}", "gimmick", "summon", "소환수 아이콘", f"{_txt(s, 'name')} ({s.get('name_en', '')})",
            plain(_txt(s, "desc")), s, "image")
    for o in GM.orbs(project):
        add(f"orb_{o['id']}", "gimmick", "orb", "구체 아이콘", f"{_txt(o, 'name')} ({o.get('name_en', '')})",
            plain(_txt(o, "desc")), o, "image", extra={"tint": o.get("tint")})
    for e in FX.effects(project):
        for i, sh in enumerate(e.get("shapes", [])):
            if sh.get("type") == "image":
                add(f"fx_{e['id']}_{i + 1}", "fx", "fx", f"이펙트 그림 (도형 {i + 1})", e.get("name") or e["id"], "",
                    sh, "image")
    for n, s in enumerate(out, 1):
        s["num"] = n
    return out


def card_composition(card):
    """스킬의 '카드 종류에 따른 기본 선택' + 실제 효과 우선."""
    kinds = [e.get("kind") for e in card.get("effects", [])]
    effs = card.get("effects", [])
    t = card.get("type", "Attack")
    if t == "Attack":
        if card.get("target") in ("AllEnemies",) or any(e.get("target") == "all" for e in effs):
            return "F", "광역 공격 → 추상 이펙트 (F)"
        if any(int(e.get("hits", 1) or 1) > 1 for e in effs) or "x_cost" in card and card.get("x_cost"):
            return "B", "연속 타격 → 동작 실루엣 (B)"
        return "A", "근접 타격 → 강한 단축법 (A, 필요하면 +B)"
    if t == "Power":
        if any(k in ("energy",) for k in kinds):
            return "F", "에너지 분출형 파워 → 추상 이펙트 (F)"
        return ("E", "지속 효과 파워 → 상태 연출 (E)") if any(k == "power" for k in kinds) else \
            ("D", "파워 → 상징물 강조 (D)")
    if "block" in kinds:
        return "E", "방어·반격 태세 → 상태 연출 (E)"
    if any(k in ("draw", "energy", "gold") for k in kinds):
        return "D", "준비·자원 → 상징물 강조 (D)"
    return "C", "능력 시전 → 시전 집중 (C)"


# ---------------------------------------------------------------------------
# 설명서
# ---------------------------------------------------------------------------
def composition_skill(app_dir=""):
    """카드 구도 스킬 본문. 앱 폴더에 card_composition_skill.md 가 있으면 그것을 쓴다."""
    for base in (app_dir, os.path.dirname(os.path.abspath(__file__))):
        p = os.path.join(base or ".", "card_composition_skill.md")
        if base and os.path.isfile(p):
            try:
                return open(p, encoding="utf-8").read()
            except OSError:
                pass
    import artskill
    return artskill.SKILL_MD


def _size_line(kind):
    w, h, mode, tr, _d = SPECS[kind]
    bg = "투명 배경 PNG (투명이 안 되면 단색 배경 — 적용할 때 자동으로 지움)" if tr else "불투명 (화면을 꽉 채움)"
    if kind == "card":
        return ("1:1 정사각형으로 그림 → 적용할 때 1000×760 가로 비율로 가운데를 자름 (위·아래 약 12%씩 잘림: "
                "주 피사체·행동 접점은 가운데 가로 띠 안에)", bg)
    if mode == "cover":
        if w > h:
            return f"가로 16:9 ({w}×{h}) → 적용할 때 {w}×{h} 로 맞추고 넘치면 가운데를 자름", bg
        return f"세로 {w}:{h} 비율 (예: {w * 4}×{h * 4}) → 적용할 때 {w}×{h} 로 줄이고 넘치면 가운데를 자름", bg
    if mode == "contain":
        return f"정사각형에 가깝게, 적용할 때 {w}×{h} 안에 맞춤 (작게 보이므로 굵은 실루엣·적은 디테일)", bg
    return "세로로 긴 캔버스 (예: 768×1024), 적용할 때 최대 1024 픽셀로 줄임", bg


def _what(s):
    k, ex = s["kind"], s["extra"]
    name, desc = s["name"], s["desc"]
    if k == "card":
        tline = {"Attack": "공격", "Skill": "스킬", "Power": "파워"}.get(ex.get("type"), ex.get("type") or "")
        comp = ex.get("comp") or ("", "")
        tgt = {"AnyEnemy": "적 1명", "AllEnemies": "모든 적", "RandomEnemy": "무작위 적", "Self": "자신",
               "None": "없음", "AnyAlly": "아군 1명", "AllAllies": "모든 아군"}.get(ex.get("target"), ex.get("target"))
        cost = "X" if s["obj"].get("x_cost") else ex.get("cost")
        return [f"카드: {name} · {tline} · 비용 {cost} · 대상 {tgt}",
                f"효과: {desc or '(설명 없음)'}",
                f"추천 구도: {comp[1]}",
                "할 일: 아래 '카드 원화 구도 설계 스킬' 의 작업 절차 1~7 을 따라 구성 요약 → 영어 프롬프트 → 네거티브 → 생성 → 검수."]
    if k == "char_combat":
        return [f"캐릭터: {name} — {desc}",
                "전신, 몸은 화면 오른쪽(적이 있는 쪽)을 향함, 발이 캔버스 아래 가운데에 닿게, 무기·특징이 실루엣으로 바로 읽히게.",
                "이 그림이 **모든 캐릭터 그림의 기준**입니다. 먼저 만들고, 뒤의 초상화·아이콘·모션은 이 그림을 참고로 같은 인물로 그리세요."]
    if k in ("char_attack", "char_hit"):
        f, n = ex.get("frame"), ex.get("frames")
        act = "공격 동작" if k == "char_attack" else "맞고 움찔하는 동작"
        phase = ["준비(예비 동작)", "타격 순간", "마무리"] if k == "char_attack" else ["맞는 순간(몸이 뒤로 젖혀짐)", "되돌아옴"]
        ph = phase[min(f - 1, len(phase) - 1)] if f else ""
        return [f"{name} 의 {act} {f}/{n} 번째 프레임: {ph}",
                "전투 스탠딩 그림과 **같은 캔버스 크기·같은 크기의 인물·같은 발 위치**로, 자세만 바꿈 (연속 재생됨)."]
    if k == "char_select":
        return [f"{name} 의 캐릭터 선택 화면 초상화 (세로로 긴 카드 모양 버튼 안에 들어감).",
                "상반신~무릎, 얼굴과 대표 무기가 위쪽 2/3 안에, 배경은 캐릭터 색 계열의 단순한 색면. 잠긴 버전은 자동으로 만듭니다."]
    if k == "char_select_bg":
        return [f"{name} 를 고르면 화면 전체를 채우는 배경 일러스트 (16:9 가로, 1920×1080).",
                "캐릭터가 자기 세계 속에 서 있는 장면. 왼쪽에는 이름·설명 글 패널, 아래쪽에는 캐릭터 고르기 버튼 줄이 "
                "겹쳐 올라가므로 주인공은 가운데~오른쪽에 크게, 왼쪽과 아래 가장자리는 어둡고 단순하게.",
                "16:9 가 아니면 가운데 기준으로 잘립니다."]
    if k == "char_icon":
        return [f"{name} 의 얼굴(또는 상징) 아이콘. 88 픽셀로 아주 작게 보이므로 얼굴·머리 실루엣만, 굵은 외곽선."]
    if k == "char_map":
        return [f"{name} 를 나타내는 지도 위 표시 (49×64). 핀/방패 모양 안의 얼굴 또는 상징, 아래쪽이 뾰족하면 좋음."]
    if k == "char_energy":
        return [f"{name} 전용 에너지 구슬 아이콘 (카드 왼쪽 위 비용 숫자가 그 위에 올라감 → 가운데는 밝고 단순하게)."]
    if k == "char_energy_text":
        return ["위 에너지 아이콘을 24 픽셀용으로 아주 단순하게 (같은 색·같은 모양, 디테일 없음)."]
    if k == "pet":
        return [f"동료: {name} — {desc}", "전신, 오른쪽을 향함, 발이 캔버스 아래 가운데, 플레이어 캐릭터보다 작은 체구."]
    if k == "power":
        good = (ex.get("ptype") or "Buff") == "Buff"
        return [f"{'버프' if good else '디버프'}: {name} — {desc}",
                "원형 안에 들어가는 상징 하나. " + ("밝고 따뜻한 색." if good else "어둡고 불길한 색.")]
    if k == "relic":
        out = [f"유물: {name} — {desc}", "물건 하나를 3/4 각도로, 굵은 외곽선, 그림자 없이."]
        if ex.get("upgrade_of"):
            out.append(f"이 유물은 시작 유물 '{ex['upgrade_of'][0]}'(`{ex['upgrade_of'][1]}`)의 **강화 버전**: 같은 물건·같은 실루엣을 "
                       "유지하되 더 크고 화려하게 (빛·장식·색 변화)로 강해진 것이 한눈에 보이게.")
        return out
    if k == "potion":
        return [f"물약: {name} — {desc}", "병 하나 (모양으로 구별되게), 안의 액체 색이 효과를 나타냄."]
    if k == "summon":
        return [f"소환수: {name} — {desc}", "소환수의 얼굴/상징 하나를 아이콘으로."]
    if k == "orb":
        return [f"구체: {name} — {desc}", f"빛나는 구슬 하나 (대표색 {ex.get('tint') or '자유'})."]
    if k == "fx":
        return [f"이펙트 '{name}' 의 그림 조각 (전투 화면 위에서 움직이며 재생됨).", "빛·불꽃·마법진 등 효과 하나, 가장자리는 부드럽게 사라지게."]
    return [desc]


def style_refs(project):
    """그림체 참고 그림 (있는 파일만)."""
    return [p for p in (project.get("art_style_refs") or []) if isinstance(p, str) and os.path.isfile(p)]


def ref_names(refs):
    return [f"style_ref_{i}{os.path.splitext(p)[1].lower() or '.png'}" for i, p in enumerate(refs, 1)]


def guide_options(project):
    o = project.get("art_guide") or {}
    return {"groups": o.get("groups") or [g for g, _l in GROUPS], "only_missing": bool(o.get("only_missing"))}


def chosen_slots(project, opts=None):
    o = opts or guide_options(project)
    out = [s for s in slots(project) if s["group"] in o["groups"]]
    if o["only_missing"]:
        out = [s for s in out if not (s["current"] and os.path.isfile(s["current"]))]
    return out


def quick_guide(project, app_dir=""):
    """저장된 선택(포함할 그림·화풍·참고 그림)으로 바로 설명서."""
    return build_guide(project, chosen_slots(project), project.get("art_style", ""), app_dir, style_refs(project))


def build_guide(project, chosen, style="", app_dir="", refs=()):
    """chosen: slots() 중 고른 것. refs: 그림체 참고 그림 경로. -> Markdown 문자열."""
    mod = project.get("mod", {})
    ch = project.get("character") or {}
    has_card = any(s["kind"] == "card" for s in chosen)
    refs = list(refs or [])
    L = [f"# '{mod.get('name', '')}' 모드 그림 만들기 설명서",
         "",
         "너는 슬레이 더 스파이어 2 모드용 그림을 만드는 일러스트레이터다. 아래 **그림 목록의 모든 칸**을 하나씩 만들어 줘.",
         "",
         "## 공통 규칙",
         "1. **파일 이름을 정확히** 지켜 줘 (예: `card_strike.png`). 이름을 붙일 수 없으면 그림마다 `#번호` 를 함께 알려 줘 —",
         "   사용자가 그 번호나 이름으로 저장하면 모드 메이커가 자동으로 알맞은 칸에 넣는다.",
         "2. 한 번에 다 못 만들면 **번호 순서대로** 이어서 만들어 줘. 캐릭터 그림(#1 전투 스탠딩)을 가장 먼저 만들고,",
         "   그 뒤 모든 캐릭터 그림(초상화·아이콘·지도 표시·모션)은 #1 을 참고해 **같은 인물**로 그린다.",
         "3. 그림 안에 글자·숫자·카드 테두리·UI·워터마크를 넣지 않는다.",
         "4. '투명 배경' 칸은 투명 PNG 로. 안 되면 **한 가지 단색 배경**(예: 순백)으로 — 적용할 때 자동으로 지운다.",
         "5. 크기는 대략이면 된다. 모드 메이커가 적용할 때 게임 크기로 맞추고(자르기·줄이기) 배경을 지운다.",
         "6. 기존 게임의 특정 그림을 그대로 베끼지 말고, 모든 그림이 **한 벌로 보이도록 같은 화풍·같은 색 체계**를 유지한다.",
         "7. **다 만들면 모든 그림을 위 파일 이름 그대로 넣은 zip 파일 하나**(`" + f"{mod.get('id', 'mod')}_images.zip" +
         "`)로 묶어 내려받을 수 있게 줘. 코드 실행(파일 만들기) 도구가 있으면 그것으로 묶고, 없으면 그림을 하나씩 주고 마지막에 "
         "파일 이름 목록을 정리해 줘.",
         ""]
    L += ["## 화풍", (style.strip() or "(사용자 지정 없음) 손으로 칠한 듯한 2D 판타지 게임 일러스트, 굵고 읽기 쉬운 형태, "
                                        "제한된 색 수, 강한 명암 대비."), ""]
    if refs:
        names = ref_names(refs)
        L += [f"### 그림체 참고 그림 (첨부 {len(refs)}장)",
              "이 설명서와 함께 첨부한 그림: " + ", ".join(f"`{n}`" for n in names),
              "- 이 그림들의 **선 굵기·채색 방식·명암·색감·질감·형태를 과장하는 정도**를 모든 그림에서 따라 한다.",
              "- 참고 그림 속 인물·물건·구도·글자는 베끼지 않는다. 그림체만 참고한다.",
              "- 첨부가 안 보이면 그림을 만들기 전에 다시 올려 달라고 말해 줘.", ""]
    if ch.get("enabled"):
        L += ["## 캐릭터 설정", f"- 이름: {_txt(ch, 'name')} / {ch.get('name_en', '')}",
              f"- 소개: {plain(_txt(ch, 'desc'))}", f"- 대표 색: {ch.get('color', '')}", ""]
    L += ["## 그림 목록", "", f"모두 {len(chosen)}장.", ""]
    for s in chosen:
        size, bg = _size_line(s["kind"])
        L += [f"### #{s['num']}  `{s['key']}.png` — {s['title']}",
              f"- 크기: {size}", f"- 배경: {bg}"]
        L += [f"- {x.rstrip(' —')}" for x in _what(s) if x]
        L.append("")
    if has_card:
        L += ["---", "", "## 카드 원화 구도 설계 스킬 (카드 삽화 칸에 적용)", "",
              "카드 삽화 칸은 아래 스킬을 그대로 따른다. 단, 출력 비율은 위 '크기' 줄을 따른다 "
              "(1:1 로 그리되 위·아래가 잘려도 행동이 읽히게).", ""]
        skill = composition_skill(app_dir)
        skill = re.sub(r"^---\n.*?\n---\n", "", skill, count=1, flags=re.S)     # 머리 정보 제거
        L += [skill.strip(), ""]
    L += ["---", "", "## 다 만든 뒤 (사용자가 할 일)",
          "1. AI 가 준 zip 을 내려받는다 (또는 그림을 한 폴더에 위 파일 이름·`번호.png` 로 저장).",
          "2. 모드 메이커 → `AI → 🖼 그림 한꺼번에 적용…` → **zip 고르기** (또는 폴더 고르기).",
          "3. 칸마다 짝지어진 그림·미리보기를 확인하고 [적용] — 크기 맞추기·배경 지우기가 자동으로 된다."]
    return "\n".join(L) + "\n"


def make_bundle(project, guide_text, refs, base_dir):
    """AI 에게 보낼 묶음: <base>/<모드>_그림요청/ 에 설명서.md + 참고 그림, 같은 내용의 zip. -> (폴더, zip)"""
    import shutil
    import zipfile
    mid = re.sub(r"[^\w.-]", "_", project.get("mod", {}).get("id") or "mod")
    folder = os.path.join(base_dir, f"{mid}_그림요청")
    if os.path.isdir(folder):
        for f in os.listdir(folder):          # 예전 묶음의 파일만 지운다 (이 함수가 만든 이름)
            if f == "설명서.md" or f.startswith("style_ref_"):
                try:
                    os.remove(os.path.join(folder, f))
                except OSError:
                    pass
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, "설명서.md"), "w", encoding="utf-8") as fh:
        fh.write(guide_text)
    for src, name in zip(refs, ref_names(refs)):
        shutil.copyfile(src, os.path.join(folder, name))
    zpath = folder + ".zip"
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(os.path.join(folder, "설명서.md"), "설명서.md")
        for name in ref_names(refs):
            z.write(os.path.join(folder, name), name)
    return folder, zpath


def extract_zip(zpath, dest=None):
    """AI 가 준 zip 에서 그림만 꺼낸다 (폴더 구조·이상한 경로는 무시, 파일 이름만). -> 그림 경로 목록"""
    import zipfile
    dest = dest or os.path.splitext(zpath)[0] + "_풀림"
    os.makedirs(dest, exist_ok=True)
    out = []
    with zipfile.ZipFile(zpath) as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            name = os.path.basename(info.filename.replace("\\", "/"))
            if not name.lower().endswith(IMAGE_EXT) or name.startswith(("._", ".")) or "__MACOSX" in info.filename:
                continue
            if info.file_size > 64 * 1024 * 1024:
                continue
            target = os.path.join(dest, name)
            stem, ext = os.path.splitext(name)
            k = 2
            while target in out:
                target = os.path.join(dest, f"{stem}_{k}{ext}")
                k += 1
            with z.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            out.append(target)
    return sorted(out)


# ---------------------------------------------------------------------------
# 파일 짝짓기
# ---------------------------------------------------------------------------
IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def list_images(folder):
    try:
        return sorted(os.path.join(folder, f) for f in os.listdir(folder)
                      if f.lower().endswith(IMAGE_EXT) and os.path.isfile(os.path.join(folder, f)))
    except OSError:
        return []


def match_files(slot_list, files):
    """-> {slot key: path}. 이름 그대로 > 이름이 들어 있음 > #번호 순으로 찾는다. 한 파일은 한 칸에만."""
    res, used = {}, set()
    stems = {f: os.path.splitext(os.path.basename(f))[0].lower() for f in files}
    keys = sorted((s["key"] for s in slot_list), key=len, reverse=True)
    for f, st in stems.items():          # 1) 이름이 정확히 같음
        k = next((k for k in keys if st == k.lower()), None)
        if k and k not in res:
            res[k], _ = f, used.add(f)
    for f, st in stems.items():          # 2) 이름 안에 칸 이름이 들어 있음 (가장 긴 것)
        if f in used:
            continue
        k = next((k for k in keys if k.lower() in st and k not in res), None)
        if k:
            res[k] = f
            used.add(f)
    by_num = {s["num"]: s["key"] for s in slot_list}
    for f, st in stems.items():          # 3) 번호 (#3, 03, 3_strike …)
        if f in used:
            continue
        m = re.match(r"^#?0*(\d{1,4})(?:\D|$)", st) or re.search(r"#0*(\d{1,4})", st)
        if m and int(m.group(1)) in by_num and by_num[int(m.group(1))] not in res:
            res[by_num[int(m.group(1))]] = f
            used.add(f)
    return res


# ---------------------------------------------------------------------------
# 그림 다듬기
# ---------------------------------------------------------------------------
def remove_background(im, tol=42):
    """알파가 없는 그림의 가장자리 단색 배경을 투명하게 (모서리·변 가운데에서 채우기)."""
    from PIL import Image, ImageDraw
    im = im.convert("RGBA")
    a = im.getchannel("A")
    if a.getextrema()[0] < 250:        # 이미 투명한 곳이 있으면 그대로
        return im
    w, h = im.size
    seeds = [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, 0), (w // 2, h - 1), (0, h // 2), (w - 1, h // 2)]
    corners = [im.getpixel(p)[:3] for p in seeds[:4]]
    base = corners[0]
    if max(max(abs(c[i] - base[i]) for i in range(3)) for c in corners) > tol * 2:
        return im                      # 배경이 단색이 아님 (그림이 가장자리까지 꽉 참)
    # 배경색과 가까운 픽셀 = 255 인 흑백 판 (RGBA 에 직접 floodfill 하면 일부 Pillow 에서 메모리가 깨짐)
    from PIL import ImageChops, ImageFilter
    rgb = im.convert("RGB")
    diff = ImageChops.difference(rgb, Image.new("RGB", rgb.size, tuple(base)))
    r_, g_, b_ = diff.split()
    near = ImageChops.lighter(ImageChops.lighter(r_, g_), b_).point(lambda v: 255 if v <= tol else 0)
    for p in seeds:
        if near.getpixel(p) == 255:
            ImageDraw.floodfill(near, p, 128)          # 가장자리와 이어진 배경만 128 로
    alpha = near.point(lambda v: 0 if v == 128 else 255)
    # 가장자리 반쯤 섞인 픽셀을 부드럽게
    alpha = alpha.filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    out = im.copy()
    out.putalpha(alpha)
    return out


def process(path, kind, remove_bg=True):
    from PIL import Image
    w, h, mode, transparent, _d = SPECS[kind]
    im = Image.open(path)
    im.load()
    im = im.convert("RGBA")
    if transparent and remove_bg:
        im = remove_background(im)
    if mode == "cover":
        sw, sh = im.size
        r = max(w / sw, h / sh)
        nw, nh = max(w, round(sw * r)), max(h, round(sh * r))
        im = im.resize((nw, nh), Image.LANCZOS)
        x, y = (nw - w) // 2, (nh - h) // 2
        return im.crop((x, y, x + w, y + h))
    if mode == "contain":
        bbox = im.getchannel("A").getbbox() if transparent else None
        if bbox:
            im = im.crop(bbox)          # 투명한 여백은 잘라 아이콘을 꽉 차게
        sw, sh = im.size
        r = min(w / sw, h / sh) * (0.94 if transparent else 1.0)
        nw, nh = max(1, round(sw * r)), max(1, round(sh * r))
        im = im.resize((nw, nh), Image.LANCZOS)
        canvas = Image.new("RGBA", (w, h), (0, 0, 0, 0) if transparent else (0, 0, 0, 255))
        canvas.alpha_composite(im, ((w - nw) // 2, (h - nh) // 2))
        return canvas
    sw, sh = im.size
    if max(sw, sh) > SPRITE_MAX:
        r = SPRITE_MAX / max(sw, sh)
        im = im.resize((round(sw * r), round(sh * r)), Image.LANCZOS)
    return im


def locked_version(im):
    """잠긴 캐릭터 선택 초상화: 흑백 + 어둡게."""
    from PIL import ImageEnhance
    g = im.convert("LA").convert("RGBA")
    g = ImageEnhance.Brightness(g).enhance(0.45)
    g.putalpha(im.getchannel("A"))
    return g


def out_dir_for(paths):
    base = os.path.dirname(os.path.abspath(next(iter(paths))))
    return os.path.join(base, "_적용됨")


def apply(project, slot_list, assignments, out_dir, remove_bg=True, log=None, progress=None):
    """assignments: {key: 원본 경로}. 다듬은 그림을 out_dir 에 저장하고 칸에 넣는다. -> [(칸, 결과 경로)]
    progress(i, n, 칸): 그림마다 부름 (화면이 멈추지 않게 이벤트를 돌릴 자리)."""
    os.makedirs(out_dir, exist_ok=True)
    by_key = {s["key"]: s for s in slot_list}
    done = []
    total = len(assignments)
    for i, (key, src) in enumerate(assignments.items(), 1):
        s = by_key.get(key)
        if not s or not src:
            continue
        if progress:
            progress(i, total, s)
        im = process(src, s["kind"], remove_bg)
        dst = os.path.join(out_dir, f"{key}.png")
        im.save(dst)
        if s["index"] is None:
            s["obj"][s["field"]] = dst
        else:
            lst = s["obj"].setdefault(s["field"], [])
            while len(lst) <= s["index"]:
                lst.append({"image": ""})
            lst[s["index"]]["image"] = dst
        done.append((s, dst))
        if s["kind"] == "char_select":
            lk = os.path.join(out_dir, "char_select_locked.png")
            locked_version(im).save(lk)
            s["obj"]["select_locked_image"] = lk
        if log:
            log(f"#{s['num']} {s['title']} ← {os.path.basename(src)}")
    # 비어 있는 모션 프레임 칸은 남기지 않는다 (앞에서부터 채워진 것만)
    ch = project.get("character") or {}
    for key in ("attack_frames", "hit_frames"):
        if isinstance(ch.get(key), list):
            ch[key] = [f for f in ch[key] if (f.get("image") or "").strip()]
    return done

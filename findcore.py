"""전체에서 찾기 규칙 (화면과 무관): 이름·ID·설명으로 찾고, 초성(ㅅㅂ → 수비)도 된다. 창은 findqt.py 가 맡는다."""

_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"

KIND_LABEL = {"card": "카드", "relic": "유물", "potion": "물약", "power": "파워", "tag": "태그", "summon": "소환수",
              "orb": "구체", "pet": "동료", "fx": "이펙트", "button": "전투 버튼", "character": "캐릭터"}


def chosung(text):
    out = []
    for ch in text or "":
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            out.append(_CHO[(o - 0xAC00) // 588])
        else:
            out.append(ch)
    return "".join(out)


def matches(query, *fields):
    """대소문자 무시 부분 일치. 질문이 초성만이면(ㅂㅇ) 초성으로도 찾는다. 띄어쓰기로 나눈 낱말은 모두 맞아야 한다."""
    words = (query or "").lower().split()
    if not words:
        return True
    hay = " ".join(str(f or "") for f in fields).lower()
    cho = chosung(hay)
    for w in words:
        if w in hay:
            continue
        if all(c in _CHO for c in w) and w in cho:
            continue
        return False
    return True


def all_entries(project):
    """(kind, id, 이름, 더 찾아볼 글, 항목) 목록."""
    out = []
    for kind, key in (("card", "cards"), ("relic", "relics"), ("potion", "potions"), ("power", "powers")):
        for it in project.get(key, []):
            out.append((kind, it["id"], it.get("name_ko") or it.get("name_en") or it["id"],
                        " ".join(str(it.get(k) or "") for k in ("name_en", "name_zh", "desc_ko", "desc_en")), it))
    g = project.get("gimmicks") or {}
    for kind, key, nm in (("tag", "tags", "name_ko"), ("summon", "summons", "name_ko"), ("orb", "orbs", "name_ko"),
                          ("pet", "pets", "name_ko"), ("fx", "effects", "name"), ("button", "buttons", "label_ko")):
        for it in g.get(key, []) or []:
            out.append((kind, it["id"], it.get(nm) or it.get("name_ko") or it.get("name") or it["id"],
                        " ".join(str(it.get(k) or "") for k in ("name_en", "label_en", "name")), it))
    ch = project.get("character") or {}
    if ch.get("id"):
        out.append(("character", ch["id"], ch.get("name_ko") or ch["id"], ch.get("name_en") or "", ch))
    return out

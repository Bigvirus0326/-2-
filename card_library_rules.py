"""카드 라이브러리의 화면과 무관한 규칙 (Tk · Qt 공용): 원작 카드·아이템 목록, 원작 코드 읽기, 프로젝트 카드 가져오기."""
import copy
import re
import os
import subprocess
from pathlib import Path

import modgen as M
import modimport as MI


def original_sources(assets):
    locales = {lang: assets.loc(lang, "cards") for lang in ("ko", "en", "zh")}
    names = assets.loc("ko", "characters")
    groups = {}
    for path in assets.pck.files:
        match = re.fullmatch(r"images/packed/card_portraits/([a-z0-9_]+)/([a-z0-9_]+)\.png\.import", path)
        if not match:
            continue
        group, slug = match.groups()
        entry = slug.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", entry) or entry + ".title" not in locales["en"]:
            continue
        card = {"id": entry, "portrait": path[:-7]}
        for lang, table in locales.items():
            card["name_" + lang] = table.get(entry + ".title", "")
            card["desc_" + lang] = table.get(entry + ".description", "")
        groups.setdefault(group, []).append(card)
    return {group: {"title": names.get(group.upper() + ".title", group), "cards": cards, "game": True}
            for group, cards in sorted(groups.items())}

def read_original_code(folder, entry, log=print):
    dll = Path(folder) / "data_sts2_windows_x86_64" / "sts2.dll"
    cls = M.pascal(entry.lower())
    if not dll.is_file():
        raise FileNotFoundError(f"게임 DLL을 찾을 수 없습니다. 설치 폴더를 확인해 주세요.\n{dll}")
    exe = MI.ensure_decompiler(log)
    result = subprocess.run([exe, "-t", "MegaCrit.Sts2.Core.Models.Cards." + cls, str(dll)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        creationflags=MI._NOWIN, env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
    if result.returncode:
        raise RuntimeError(MI._process_failure(f"{cls} 카드 디컴파일 실패", result.args, result))
    classes = MI.parse_cs(result.stdout)
    found = next((c for c in classes if c.name == cls), None)
    if found is None:
        raise ValueError(f"원작 DLL에서 카드 클래스 {cls}를 찾지 못했습니다. 게임 파일과 .NET 설치 상태를 확인해 주세요.")
    body = found.body
    variables = MI.parse_vars(MI.member_text(body, "CanonicalVars"))
    upgrades, _, _ = MI.parse_upgrades(MI.member_text(body, "OnUpgrade"))
    for v in variables:
        name = v["name"]
        v["upgrade"] = upgrades.get(name, upgrades.get(name[:-5] if name.endswith("Power") else name, 0))
    return result.stdout, [v for v in variables if v["value"] is not None]

def import_project_card(target, source, card, used):
    """Prepare changes on a copy so unresolved or conflicting references cannot partially import."""
    result = copy.deepcopy(target)
    item = copy.deepcopy(card)
    original = item["id"]
    suffix = 2
    while item["id"] in used:
        item["id"] = f"{original}_{suffix}"
        suffix += 1
    used = set(used) | {item["id"]}
    seen = set()
    def require(group, key):
        if not key or (group, key) in seen:
            return
        seen.add((group, key))
        source_list = source.get(group, []) if group in ("powers", "dependencies") else source.get("gimmicks", {}).get(group, [])
        found = next((obj for obj in source_list if obj["id"] == key), None)
        if found is None:
            return
        owner = result if group in ("powers", "dependencies") else result.setdefault("gimmicks", {})
        dest = owner.setdefault(group, [])
        prior = next((obj for obj in dest if obj["id"] == key), None)
        if prior == found:
            return
        if prior is not None or (group != "dependencies" and key in used):
            raise ValueError(f"참조 항목 '{key}'의 ID가 현재 프로젝트의 다른 항목과 겹칩니다.")
        obj = copy.deepcopy(found)
        dest.append(obj)
        if group != "dependencies":
            used.add(key)
            scan(obj)
    def scan(node):
        if isinstance(node, list):
            for value in node:
                scan(value)
        elif isinstance(node, dict):
            for field, value in node.items():
                if isinstance(value, str):
                    if field in ("power", "scale_power", "cond_power", "res_power", "ref") and value.startswith("c:"):
                        require("powers", value[2:])
                    elif value.startswith("tag:") and field in ("ctype", "filter", "played_filter", "result_filter"):
                        require("tags", value[4:])
                    elif value.startswith("s:") and field in ("power", "cond_power", "scale_power"):
                        require("summons", value[2:])
                    elif value.startswith("x:") and field in ("power", "cond_power", "scale_power"):
                        require("dependencies", value.split(":")[1])
                    elif field in ("summon", "orb", "pet", "button", "fx"):
                        require({"summon":"summons","orb":"orbs","pet":"pets","button":"buttons","fx":"effects"}[field], value)
                    elif field == "card" and value == original:
                        node[field] = item["id"]
                    elif field == "card" and value != "this" and not any(c["id"] == value for c in result["cards"]):
                        raise ValueError(f"이 카드가 참조하는 '{value}' 카드를 먼저 가져오세요.")
                elif field == "gtags":
                    for tag in value or []:
                        require("tags", tag)
                else:
                    scan(value)
            if isinstance(node.get("clone"), dict):
                require("dependencies", node["clone"].get("mod"))
    scan(item)
    result["cards"].append(item)
    return result

def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)

CATEGORIES = {"relics": "유물", "potions": "물약", "powers": "파워", "card_keywords": "키워드"}

def item_sources(assets):
    sources = {}
    for kind, label in CATEGORIES.items():
        tables = {lang: assets.loc(lang, kind) for lang in ("ko", "en", "zh")}
        items = []
        for key in sorted(tables["en"]):
            entry, _, field = key.partition(".")
            if field != "title" or not re.fullmatch(r"[A-Z][A-Z0-9_]*", entry):
                continue
            if kind == "card_keywords" and M.pascal(entry.lower()) not in dict(M.CARD_KEYWORDS):
                continue
            item = {"id": entry}
            for lang, table in tables.items():
                item["name_" + lang] = table.get(key, "")
                item["desc_" + lang] = table.get(entry + ".description") or table.get(entry + ".smartDescription", "")
            items.append(item)
        sources[kind] = {"kind": kind, "game": True, "title": "원작 " + label, "cards": items}
    return sources


def rename_refs(node, old, new):
    """가져온 카드 안에서 자기 자신을 가리키는 'card' 칸을 기존 카드 ID 로 바꾼다."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "card" and value == old:
                node[key] = new
            else:
                rename_refs(value, old, new)
    elif isinstance(node, list):
        for value in node:
            rename_refs(value, old, new)

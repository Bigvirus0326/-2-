"""프로젝트 작업 (화면과 무관): 그림을 프로젝트 옆 assets 폴더로 모으기, 다른 프로젝트 합치기.

Tk 앱의 '프로젝트 자산 모으기…' · '다른 프로젝트 합치기…' 와 같은 규칙. 창은 app_qt.py 가 맡는다.
"""
import copy
import hashlib
import json
import os
import shutil
import tempfile

import fxrules
import gimmick as GM
import gimmickrules
import modgen as M
import projectio as IO

GIMMICK_KINDS = (("tags", "tag"), ("summons", "summon"), ("orbs", "orb"), ("effects", "fx"),
                 ("buttons", "button"), ("pets", "pet"))
ITEM_KINDS = ("cards", "relics", "potions", "powers")


def project_ids(project):
    """프로젝트 안의 모든 ID (항목·기믹·캐릭터)."""
    ids = {c["id"] for k in ITEM_KINDS for c in project[k]}
    g = project.get("gimmicks") or {}
    for group, _kind in GIMMICK_KINDS:
        ids |= {x["id"] for x in g.get(group, [])}
    ids.add(project["character"]["id"])
    return ids


def load_project_file(path):
    """다른 프로젝트 파일을 읽는다 (그림 경로는 그 파일 기준으로 바꾼다). 실패하면 ValueError·OSError."""
    with open(path, encoding="utf-8") as f:
        other = M.normalize(json.load(f))
    return IO._resolve_project_image_paths(other, os.path.dirname(os.path.abspath(path)))


# ---- 그림 모으기 ----
def pack_plan(project):
    """프로젝트가 쓰는 그림 파일: (원본 경로 {정규화 경로: 절대 경로}, 찾지 못한 파일 목록)."""
    sources = {}
    for source in IO._project_image_paths(project):
        absolute = os.path.abspath(source)
        sources.setdefault(os.path.normcase(absolute), absolute)
    missing = [source for source in sources.values() if not os.path.isfile(source)]
    return sources, missing


def pack_assets(project, project_path, sources):
    """그림을 프로젝트 파일 옆 assets 폴더에 복사하고, 경로를 상대 경로로 바꾼 복사본을 돌려 준다.
    -> (복사본, 모은 그림 수, 새로 만든 파일 목록). 실패하면 만든 파일을 지우고 OSError 를 올린다."""
    project_dir = os.path.dirname(os.path.abspath(project_path))
    assets_dir = os.path.join(project_dir, "assets")
    created = []
    remap = {}
    try:
        os.makedirs(assets_dir, exist_ok=True)
        for key, source in sources.items():
            digest = hashlib.sha256()
            with open(source, "rb") as f:
                for chunk in iter(lambda: f.read(1024 * 1024), b""):
                    digest.update(chunk)
            stem, extension = os.path.splitext(os.path.basename(source))
            filename = f"{digest.hexdigest()[:20]}_{stem[:72]}{extension[:12]}"
            destination = os.path.abspath(os.path.join(assets_dir, filename))
            if os.path.normcase(source) != os.path.normcase(destination) and not os.path.isfile(destination):
                fd, temp_path = tempfile.mkstemp(prefix=".asset-", suffix=".tmp", dir=assets_dir)
                os.close(fd)
                try:
                    shutil.copy2(source, temp_path)
                    os.replace(temp_path, destination)
                except Exception:
                    try:
                        os.remove(temp_path)
                    except OSError:
                        pass
                    raise
                created.append(destination)
            remap[key] = destination
    except (OSError, ValueError):
        remove_files(created)
        raise

    packed = copy.deepcopy(project)

    def replace_source(source):
        return remap.get(os.path.normcase(os.path.abspath(source)), source)
    IO._transform_project_image_paths(packed, replace_source)
    return packed, len(set(remap.values())), created


def remove_files(paths):
    for path in paths:
        try:
            os.remove(path)
        except OSError:
            pass


# ---- 합치기 ----
def merge_into(project, other):
    """other 의 카드·유물·물약·파워·기믹을 project 에 붙인다. 겹치는 ID 는 뒤에 번호를 붙이고 참조도 고친다.
    project 를 바로 고친다. -> (종류별 개수 {키: 수}, 바꾼 ID가 있는지)"""
    used = project_ids(project)
    rename = {}
    counts = {}
    renamed = False
    for key in ("powers", "cards", "relics", "potions"):
        for it in other.get(key, []):
            nid, n = it["id"], 2
            while nid in used:
                nid = f"{it['id']}_{n}"
                n += 1
            used.add(nid)
            if key == "powers" and nid != it["id"]:
                rename[it["id"]] = nid
            renamed = renamed or nid != it["id"]
            it["id"] = nid
    for key in ("cards", "relics", "potions", "powers"):
        for it in other.get(key, []):
            for e in it.get("effects", []):
                for fld in ("power", "cond_power", "scale_power"):
                    v = e.get(fld) or ""
                    if v.startswith("c:") and v[2:] in rename:
                        e[fld] = "c:" + rename[v[2:]]
            project[key].append(it)
            counts[key] = counts.get(key, 0) + 1
    deps = project.setdefault("dependencies", [])
    for d in other.get("dependencies", []):
        if not any(x["id"] == d["id"] for x in deps):
            deps.append(d)
    # 기믹 (태그 · 소환수 · 구체 · 이펙트 · 버튼 · 동료): 겹치면 이름을 바꾸고 참조도 고친다
    GM.normalize(project)
    mine, theirs = project["gimmicks"], other.get("gimmicks") or {}
    for key, kind in GIMMICK_KINDS:
        for x in theirs.get(key, []):
            nid, n = x["id"], 2
            while nid in used:
                nid = f"{x['id']}_{GM.letters(n).lower()}"
                n += 1
            used.add(nid)
            if nid != x["id"]:
                renamed = True
                if kind in ("fx", "button"):
                    fxrules._rename(other, kind, x["id"], nid)
                else:
                    gimmickrules.rename_gimmick_ref(other, kind, x["id"], nid)
                x["id"] = nid
            mine[key].append(x)
            counts[key] = counts.get(key, 0) + 1
    return counts, renamed


COUNT_NAMES = {"cards": "카드", "relics": "유물", "potions": "물약", "powers": "파워", "tags": "태그",
               "summons": "소환수", "orbs": "구체", "effects": "이펙트", "buttons": "버튼", "pets": "동료"}


def merge_summary(counts, renamed):
    text = "합쳤습니다: " + ", ".join(f"{COUNT_NAMES.get(k, k)} {v}" for k, v in counts.items())
    if renamed:
        text += "\n(겹치는 ID 는 뒤에 번호를 붙였습니다)"
    return text

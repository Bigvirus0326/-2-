"""가져온 카드의 원본 효과를 블록으로 다시 풀기 (Tk 의 sts2_mod_maker 의 mod_classes · decompose 와 같다).

원본 모드 DLL 은 한 번만 디컴파일해 두고, 그 안의 클래스에서 OnPlay 를 블록으로 바꾼다.
화면과 무관한 부분만 둔다. 블록 편집 창은 blockqt.py 가 연다.
"""
import glob
import os
import re
from pathlib import Path

import csblocks
import modimport as MI
import projectio as IO

_CACHE = {}


def _parse_folder(folder):
    classes = {}
    for f in glob.glob(os.path.join(folder, "**", "*.cs"), recursive=True):
        for c in MI.parse_cs(MI._read_text(f), f):
            classes.setdefault(c.name, c)
    return classes


def _find_dll(project, mod_id, required_class, saved_body, game, log):
    """DLL 경로. 없으면 원본 소스 폴더의 클래스 묶음(dict) 또는 저장된 코드 (빈 dict), 못 찾으면 ValueError."""
    takeover = project.get("takeover") or {}
    if takeover.get("mod") != mod_id:
        takeover = {}
    folders = []
    if takeover.get("source"):
        source = Path(takeover["source"])
        folders.append(source if source.is_dir() else source.parent)
    candidates = [Path(takeover["original_dll"])] if takeover.get("original_dll") else []
    if mod_id and re.fullmatch(r"[\w.-]+", mod_id) and mod_id not in (".", ".."):
        if game:
            folders.extend(Path(game) / sub / mod_id for sub in ("mods", "mods.disabled"))
        candidates.extend(folder / (mod_id + ".dll") for folder in folders)
        if game and not any(f.is_file() for f in candidates):
            workshop = Path(game).parent.parent / "workshop" / "content" / "2868840"
            candidates.extend(workshop.glob("*/" + mod_id + ".dll"))
    dll = next((str(f) for f in candidates if f.is_file()), "")
    if dll:
        return dll, None
    src = takeover.get("src")
    if src and os.path.isdir(src):
        classes = _parse_folder(src)
        if classes and (not required_class or required_class in classes):
            return "", classes
    if saved_body.strip():
        log(f"[안내] {required_class}: 프로젝트에 저장된 카드 코드로 분석합니다. 외부 도우미 코드는 생략될 수 있습니다.")
        return "", {}
    raise ValueError(f"'{mod_id}' 원본 DLL과 저장된 카드 코드를 찾지 못했습니다. 게임 설치 경로를 확인하거나 원본 모드를 다시 불러오세요.")


def mod_classes(project, settings, mod_id, required_class="", saved_body="", log=print):
    """의존 모드의 모든 C# 클래스 {짧은 이름: CsClass}. DLL 은 한 번만 디컴파일한다."""
    dep = next((d for d in project.get("dependencies", []) if d.get("id") == mod_id), None)
    dll = (dep or {}).get("dll") or ""
    game = settings.get("sts2_path") or IO.detect_sts2_path()
    if not os.path.isfile(dll):
        dll, classes = _find_dll(project, mod_id, required_class, saved_body, game, log)
        if not dll:
            return classes
    key = (dll, os.path.getmtime(dll), os.path.getsize(dll))
    classes = _CACHE.get(key)
    refresh = classes is not None and bool(required_class) and required_class not in classes
    if refresh:
        log(f"[경고] 디컴파일 캐시에 원본 클래스 '{required_class}'가 없어 다시 읽습니다.")
    if classes is None or refresh:
        folder = MI.decompile(dll, settings.get("sts2_path", ""), log=log, force=refresh)
        classes = _parse_folder(folder)
        if required_class and required_class not in classes and not refresh:
            log(f"[경고] 원본 클래스 '{required_class}'가 없어 디컴파일 캐시를 다시 만듭니다.")
            folder = MI.decompile(dll, settings.get("sts2_path", ""), log=log, force=True)
            classes = _parse_folder(folder)
        if not classes:
            raise ValueError("디컴파일된 C# 파일에서 클래스를 찾지 못했습니다. 자세한 원인은 앱 로그를 확인해 주세요.")
        if required_class and required_class not in classes:
            raise ValueError(f"원본 DLL을 다시 읽었지만 클래스 '{required_class}'를 찾지 못했습니다.\n"
                             f"읽은 클래스 수: {len(classes)} · 캐시 폴더: {folder}")
        _CACHE[key] = classes
    return classes


def decompose_original(project, settings, draft, log=print):
    """draft(항목 복사본)의 원본 코드를 블록으로 푼다 -> (블록 목록 또는 빈 값, 설명). Tk 의 decompose 와 같다."""
    orig_class = (draft["clone"].get("orig_class") or "").split(".")[-1]
    classes = mod_classes(project, settings, draft["clone"].get("mod"), required_class=orig_class,
                          saved_body=draft["clone"].get("body", ""), log=log)
    source_class = classes.get(orig_class)
    if source_class is not None:
        source_body = MI.fix_decompiled(source_class.body)
        draft["clone"]["body"] = MI.remove_members(source_body, MI.REGENERATED["card"] + [source_class.name]).strip("\n")
        draft["clone"]["usings"] = list(source_class.usings)
        draft["clone"]["upgrade_body"] = MI.member_text(source_body, "OnUpgrade")
    got, info = csblocks.decompose_with_classes(draft, classes, project)
    if got:
        csblocks.merge_usings(draft, info.get("usings"))
    return got, info

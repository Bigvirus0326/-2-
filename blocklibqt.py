"""블록 편집기의 '보관함' 규칙 (Tk 의 blockui 와 같은 파일 형식): 즐겨찾기, 저장한 블록 묶음, 블록 모음 파일,
내 블록 정의, 문장으로 만들기(레시피). 화면과 무관한 부분만 둔다. 대화상자는 blockqt.py 가 연다.
"""
import copy
import hashlib
import json
import os
import re
from pathlib import Path

import blockcode as B
import gimmick as G
import modgen as M

PRESET_DIR = Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "sts2_mod_maker" / "block_presets"
FAVORITE_FILE = PRESET_DIR.parent / "favorite_blocks.json"
FILE_FORMAT = "sts2blocks-1"


# ---- 즐겨찾기 ----
def load_favorites(path=FAVORITE_FILE):
    """저장한 순서대로 블록 종류 목록을 돌려 준다 (Tk 와 같은 파일을 쓴다)."""
    try:
        saved = json.loads(Path(path).read_text("utf8"))
    except (OSError, ValueError):
        return []
    if not isinstance(saved, list):
        return []
    ops = [B.compact_op(op) if isinstance(op, str) else op for op in saved]
    return list(dict.fromkeys(op for op in ops if isinstance(op, str) and op in B.SPECS))


def save_favorites(order, path=FAVORITE_FILE):
    order = list(dict.fromkeys(B.compact_op(op) for op in order))
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(order), encoding="utf8")
    temp.replace(path)
    return order


def toggle_favorite(order, op):
    """즐겨찾기 목록에서 op 를 넣거나 뺀 새 목록."""
    op = B.compact_op(op)
    if op in order:
        return [x for x in order if x != op]
    return list(order) + [op]


# ---- 저장한 블록 묶음 (보관함) ----
def load_presets(directory=PRESET_DIR):
    """{키: {"name": 이름, "blocks": [...]}} — 잘못된 파일은 건너뛴다."""
    presets = {}
    directory = Path(directory)
    if not directory.is_dir():
        return presets
    for preset_file in sorted(directory.glob("*.json")):
        try:
            record = json.loads(preset_file.read_text(encoding="utf8"))
            if isinstance(record["name"], str) and isinstance(record["blocks"], list) and all(
                    isinstance(b, dict) and b.get("op") in B.SPECS for b in B.walk(record["blocks"])):
                B.upgrade_numeric_blocks(record["blocks"])
                presets[preset_file.stem] = record
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return presets


def store_preset(key, name, blocks, directory=PRESET_DIR):
    record = {"name": name, "blocks": copy.deepcopy(blocks)}
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    dest = directory / (key + ".json")
    temp = dest.with_suffix(".tmp")
    temp.write_text(json.dumps(record, ensure_ascii=False), encoding="utf8")
    temp.replace(dest)
    return record


def delete_preset(key, directory=PRESET_DIR):
    (Path(directory) / (key + ".json")).unlink(missing_ok=True)


def new_preset_key(name, presets):
    """같은 이름(대소문자 무시)이 있으면 그 키를 쓴다. 없으면 새 키."""
    import uuid
    existing = next((k for k, v in presets.items() if v["name"].casefold() == name.casefold()), None)
    return existing or uuid.uuid4().hex


def register_file_preset(path, blocks, directory=PRESET_DIR):
    """불러오거나 저장한 파일을 보관함에도 한 번 올린다 (경로마다 같은 키)."""
    source = Path(path).resolve()
    key = hashlib.sha256(os.path.normcase(str(source)).encode("utf8")).hexdigest()
    return key, store_preset(key, source.stem, blocks, directory)


def preset_summary(project, preset):
    """보관함 항목에 마우스를 올렸을 때 보이는 줄글."""
    lines = [preset["name"]]

    def show(rows, depth):
        for block in rows:
            caption = B.block_caption(block)
            args = block.get("args", {})

            def field(match):
                k = match.group(1)
                v = args.get(k, "")
                if isinstance(v, dict):
                    return B.cond_label(v, project) if k == "cond" else B.value_label(v, project)
                return str(v)
            lines.append("  " * depth + "• " + re.sub(r"\{(\w+)\}", field, caption))
            for branch in B.BODY_KEYS:
                if block.get(branch):
                    if branch != "body":
                        lines.append("  " * depth + ("아니면" if branch == "else" else "세 번째 갈래"))
                    show(block[branch], depth + 1)
    show(preset["blocks"], 0)
    return "\n".join(lines)


def missing_card_refs(blocks, project):
    """저장한 묶음 안에서 지금 프로젝트에 없는 카드·태그를 찾는다: {(종류, ID): [(노드, 칸, 앞글자)]}"""
    groups = {"카드": project.get("cards", []), "태그": project.get("gimmicks", {}).get("tags", [])}
    ids = {kind: {row["id"] for row in rows} for kind, rows in groups.items()}
    missing = {}

    def collect(node, key, kind, prefix=""):
        value = node.get(key)
        if isinstance(value, str) and value.startswith(prefix):
            ident = value[len(prefix):]
            if ident and ident not in ids[kind]:
                missing.setdefault((kind, ident), []).append((node, key, prefix))

    def filters(node):
        if isinstance(node, list):
            for child in node:
                filters(child)
        elif isinstance(node, dict):
            for key, value in node.items():
                if key in ("filter", "ctype", "result_filter", "played_filter"):
                    collect(node, key, "태그", "tag:")
                elif key == "card_id" and node.get("t") in ("pile_count", "card_identity"):
                    collect(node, key, "카드")
                else:
                    filters(value)

    for block in B.walk(blocks):
        args = block.get("args", {})
        for key in args:
            if (B.block_spec(block) or {}).get("args", {}).get(key, (None,))[0] == "card" and args[key] != "this":
                collect(args, key, "카드")
        filters(args)
    return missing


def resolve_preset(blocks, project, pick):
    """저장한 묶음을 이 프로젝트에 맞춘 복사본으로 돌려 준다.
    pick(종류, 없는 ID, 고를 수 있는 항목들) 은 고른 항목의 ID 를, 취소하면 None 을 돌려 준다.
    고를 항목이 하나도 없으면 LookupError."""
    result = copy.deepcopy(blocks)
    groups = {"카드": project.get("cards", []), "태그": project.get("gimmicks", {}).get("tags", [])}
    for (kind, old), slots in missing_card_refs(result, project).items():
        rows = groups[kind]
        if not rows:
            raise LookupError(f"이 프로젝트에는 '{old}' 대신 연결할 {kind}가 없습니다. 먼저 {kind}를 추가하세요.")
        chosen = pick(kind, old, rows)
        if not chosen:
            return None
        for node, key, prefix in slots:
            node[key] = prefix + chosen
    return result


# ---- 블록 모음 파일 (.sts2blocks) ----
def save_blocks_file(path, blocks):
    data = {"format": FILE_FORMAT, "blocks": blocks}
    Path(path).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf8")


def load_blocks_file(path):
    """저장한 블록 목록. 모드 메이커 형식이 아니면 ValueError."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or data.get("format") != FILE_FORMAT:
        raise ValueError("모드 메이커에서 저장한 블록 모음을 선택하세요.")
    blocks = data.get("blocks")
    if not isinstance(blocks, list) or not blocks:
        raise ValueError("저장된 블록 목록이 비어 있거나 손상되었습니다.")
    for block in B.walk(blocks):
        if (not isinstance(block, dict) or block.get("op") not in B.SPECS
                or not isinstance(block.get("args", {}), dict)
                or any(not isinstance(block[k], list) for k in B.BODY_KEYS if k in block)):
            raise ValueError("지원하지 않는 블록이 포함되어 있습니다.")
    return blocks


# ---- 내 블록 정의 ----
def shared_uses(project, name):
    """이 정의(name)를 부르는 카드 수 (정의끼리 부르는 것도 따라간다)."""
    defs = project.get("shared_blocks", {})

    def uses(node, seen):
        if isinstance(node, list):
            return any(uses(child, seen) for child in node)
        if isinstance(node, dict):
            if node.get("op") == "shared_call":
                ref = node.get("args", {}).get("name", "")
                if ref == name or (ref in defs and ref not in seen and uses(defs[ref], seen | {ref})):
                    return True
            return any(uses(child, seen) for child in node.values())
        return False
    return sum(uses(card, set()) for card in project.get("cards", []))


def define_shared(project, name, blocks):
    project.setdefault("shared_blocks", {})[name] = copy.deepcopy(blocks)


# ---- 문장으로 만들기 (효과 레시피) ----
def transform_recipe(project, pile, source_filter, count, pool, result_filter):
    """'조건에 맞는 카드로 변화': 더미에서 고른 카드를 다른 카드로 바꾼다."""
    block = B.new_block("random_transform")
    block["args"].update(pile=pile, ctype=source_filter, count={"t": "num", "v": int(count)},
                         result_pool=pool, result_filter=result_filter)
    return block


def threshold_recipe(power, stacks, action, amount):
    """'파워 수치에 따라 효과 실행': 파워가 stacks 이상이면 효과를 amount 만큼 준다."""
    block = B.new_block("if")
    block["args"]["cond"] = {"t": "cmp", "op": ">=", "a": {"t": "stack", "who": "self", "power": power},
                             "b": {"t": "num", "v": int(stacks)}}
    effect = B.new_block(action)
    effect["args"]["amount"] = {"t": "num", "v": int(amount)}
    block["body"] = [effect]
    return block


def recipe_choices(project):
    """레시피 화면에 줄 선택 목록: (더미, 카드 고르기, 변화 결과 고르기 ...)."""
    return {
        "piles": B.PICK_PILES,
        "sources": G.card_filters(project),
        "pools": [(k, v[0]) for k, v in M.transform_pools(project).items()],
        "results": G.card_filters(project) + [("kw:" + k, label + " 키워드 카드") for k, label in M.CARD_KEYWORDS],
        "powers": M.power_options(project),
        "actions": [("draw", "카드 뽑기"), ("block", "방어도 얻기"), ("energy", "에너지 얻기")],
    }

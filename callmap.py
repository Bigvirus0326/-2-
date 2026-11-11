"""가져온 호출(src_call)을 네이티브 효과 블록에 잇는 규칙 (Tk 의 blockui · project_review 와 같다).

화면과 무관한 부분만 둔다: 호출 묶음 찾기, 인수 위치 복구, 연결 적용. 대화상자는 callmapqt.py 가 맡는다.
"""
import copy
import re

import blockcode as B
import csblocks
import modgen as M


def source_call_slots(block):
    """Recover argument positions for imported call slots, including older saved blocks."""
    slots = {s.get("key"): s for s in block.get("slots", [])}
    if block.get("call_signature") and all(s.get("source_segment") is not None and s.get("source_arg") is not None
                                           for s in slots.values() if s.get("kind") in ("value", "code")):
        return block.get("call_signature"), list(slots.values())
    try:
        import csblocks
        parts = block.get("parts") or []
        stitched, original = [], []
        placeholders = {}
        for index, part in enumerate(parts):
            if index % 2:
                key = part
                token = f"__STS2_SLOT_{key}__"
                placeholders[token] = key
                stitched.append(token)
                original.append(str(slots.get(key, {}).get("orig", token)))
            else:
                stitched.append(str(part))
                original.append(str(part))
        statement = "".join(stitched).strip().rstrip(";").strip()
        original_statement = "".join(original).strip().rstrip(";").strip()
        assign = re.match(r"^(?:(?:var|[\w.?<>\[\],]+)\s+)?[A-Za-z_]\w*(?:\.\w+|\[[^\]]*\])*\s*(?:\+=|-=|\*=|/=|=(?!=))\s*", statement)
        rhs = statement[assign.end():] if assign else statement
        original_assign = re.match(r"^(?:(?:var|[\w.?<>\[\],]+)\s+)?[A-Za-z_]\w*(?:\.\w+|\[[^\]]*\])*\s*(?:\+=|-=|\*=|/=|=(?!=))\s*", original_statement)
        original_rhs = original_statement[original_assign.end():] if original_assign else original_statement
        parsed = csblocks.Decomposer.__new__(csblocks.Decomposer).chain_parts(rhs)
        if not parsed:
            return block.get("call_signature"), list(slots.values())
        sig_parsed = csblocks.Decomposer.__new__(csblocks.Decomposer).chain_parts(original_rhs) or parsed
        sig_segs, sig_aw = sig_parsed
        signature = csblocks.call_signature(sig_segs, original_rhs if sig_parsed is not parsed else rhs, sig_aw)
        segs, _aw = parsed
        for si, seg in enumerate(segs):
            if seg.get("args") is None:
                continue
            a, b = seg["args"]
            raw = rhs[a:b]
            for ai, (x, y) in enumerate(csblocks.split_args(raw)):
                arg = raw[x:y]
                for token, key in placeholders.items():
                    if token in arg:
                        slots[key].update(source_segment=si, source_arg=ai)
        block["call_signature"] = signature
        return signature, list(slots.values())
    except Exception:
        return block.get("call_signature"), list(slots.values())


def scan_calls(project):
    """가져온 호출 묶음: {(항목 종류, 호출 형태): [(노드, 칸 번호, 항목)]}. 같은 형태끼리 한 묶음이다."""
    groups = {}

    def scan(node, owner, item):
        if isinstance(node, list):
            for index, child in enumerate(node):
                if isinstance(child, dict) and child.get("op") == "src_call":
                    signature, _ = source_call_slots(child)
                    groups.setdefault((owner, signature or child.get("label", "호출")), []).append((node, index, item))
                else:
                    scan(child, owner, item)
        elif isinstance(node, dict):
            for value in node.values():
                scan(value, owner, item)

    for kind, group in (("card", "cards"), ("relic", "relics"), ("potion", "potions"), ("power", "powers")):
        for item in project.get(group, []):
            scan(item, kind, item)
    scan(project.get("character", {}), "character", project.get("character", {}))
    return groups


def apply_connection(project, owner, rows, block, rule):
    """rows 의 호출을 block 으로 바꿀 목록 [(노드, 칸, 새 블록)]을 돌려 준다.
    rule 이 있으면 같은 형태의 호출에만, 인수를 옮겨 적용한다. 인수 형태가 다르면 ValueError."""
    updates = []
    for parent, i, item in rows if rule else rows[:1]:
        original = parent[i]
        new_block = copy.deepcopy(block)
        if rule:
            signature, slots = source_call_slots(original)
            if signature != rule["signature"]:
                continue
            for field, binding in rule["bindings"].items():
                if binding["kind"] != "arg":
                    continue
                slot = next((s for s in slots if (s.get("source_segment"), s.get("source_arg"))
                             == (binding["segment"], binding["index"])), None)
                if not slot:
                    raise ValueError("인수 형식이 다른 호출이 있어 적용을 중단했습니다.")
                value = original.get("args", {}).get(slot["key"], slot.get("orig", ""))
                spec_kind = B.block_spec(new_block)["args"][field][0]
                if spec_kind == "value" and not isinstance(value, dict):
                    value = {"t": "src", "code": str(value)}
                elif spec_kind == "code" and isinstance(value, dict):
                    value = B._Gen(project, M._Ctx(owner, item)).val(value)
                new_block["args"][field] = copy.deepcopy(value)
        updates.append((parent, i, new_block))
    return updates

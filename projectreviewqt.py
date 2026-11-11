"""프로젝트 검토 (Qt 版): 카드 풀 밸런스 · 설명 검사, 미연결 호출·누락된 카드·파워 연결, 다른 모드 가져오기 결과.

Tk 의 project_review.py 와 같은 규칙. 아직 Qt 에서 못 하는 것: '다시 분석' (원본 코드 블록 다시 풀기).
"""
import re
from collections import Counter, defaultdict

from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QListWidget, QMessageBox,
                               QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget, QComboBox)

from types import SimpleNamespace

import blockcode as B
import callmap
import modgen as M
import projectio as IO
from callmapqt import CallMappingDialogQt

PATTERNS = {"damage": r"피해(?:를)?\s*(\d+)", "block": r"방어도(?:를)?\s*(\d+)", "draw": r"카드(?:를)?\s*(\d+)\s*장"}


def balance_text(project):
    """카드 풀마다 장수 · 비용 · 종류 · 태그 수와, 설명 숫자가 기본 효과와 다른 카드를 적는다."""
    lines = []
    pools = defaultdict(list)
    for card in project["cards"]:
        pools[card.get("pool_character") or "기본 풀"].append(card)
    tags = {t["id"]: t.get("name_ko") or t["id"] for t in project.get("gimmicks", {}).get("tags", [])}
    for pool, cards in pools.items():
        lines.append(f"{pool} · {len(cards)}장")
        costs = Counter("X" if c.get("x_cost") else str(c["cost"]) for c in cards)
        types = Counter(dict(M.CARD_TYPES).get(c["type"], c["type"]) for c in cards)
        for title, counts in (("비용", costs), ("종류", types)):
            lines.append(title + "   " + "   ".join(f"{key}: {n}장" for key, n in sorted(counts.items())))
        lines.append("종류 비율   " + "   ".join(f"{key} {n / len(cards):.0%}" for key, n in types.items()))
        lines.append("".join(f"#{label}: {sum(key in c.get('gtags', []) for c in cards)}장  "
                             for key, label in tags.items()))
        for c in cards:
            actions = []
            for e in c.get("effects", []):
                if e.get("blocks"):
                    for b in e["blocks"]:
                        v = b.get("args", {}).get("amount")
                        if isinstance(v, dict) and v.get("t") == "num":
                            actions.append((b["op"], v.get("v")))
                elif not e.get("scale_power") and not e.get("cond_power"):
                    actions.append((e.get("kind"), e.get("amount")))
            for kind, pattern in PATTERNS.items():
                values = [v for k, v in actions if k == kind]
                matches = re.findall(pattern, c.get("desc_ko", ""))
                if len(matches) == len(values) == 1 and int(matches[0]) != values[0]:
                    lines.append(f"설명 확인 · {c['name_ko']} · {kind}: 설명 {matches[0]} / 기본 효과 {values[0]}")
        lines.append("")
    if not pools:
        lines.append("프로젝트에 카드가 없습니다.")
    return "\n".join(lines)


def missing_refs(project):
    """없는 카드·파워를 가리키는 칸들: {(종류, 이름): [(노드, 칸, 앞 글자)]}"""
    ids = {"card": {c["id"] for c in project["cards"]}, "power": {p["id"] for p in project["powers"]}}
    missing = {}

    def scan(node, owner):
        if isinstance(node, list):
            for child in node:
                scan(child, owner)
        elif isinstance(node, dict):
            for key, value in node.items():
                target, prefix = None, ""
                if key == "args" and isinstance(value, dict):
                    schema = (B.block_spec(node) or {}).get("args", {})
                    for field, (slot_kind, _) in schema.items():
                        ref = value.get(field)
                        if slot_kind == "card" and ref and ref != "this" and ref not in ids["card"]:
                            missing.setdefault(("card", ref), []).append((value, field, ""))
                if owner == "character" and key == "card" and isinstance(value, str) and value and not value.startswith("game:"):
                    target = "card"
                if key == "card_id" and node.get("t") in ("pile_count", "card_identity") and isinstance(value, str) and value:
                    target = "card"
                if key in ("power", "res_power", "cond_power", "scale_power", "ref") and isinstance(value, str) \
                        and value.startswith("c:"):
                    target, prefix = "power", "c:"
                if target and value and value[len(prefix):] not in ids[target]:
                    missing.setdefault((target, value), []).append((node, key, prefix))
                scan(value, owner)

    for kind, group in (("card", "cards"), ("relic", "relics"), ("potion", "potions"), ("power", "powers")):
        for item in project.get(group, []):
            scan(item, kind)
    scan(project.get("character", {}), "character")
    return missing


def import_groups(project):
    """가져온 카드를 세 묶음으로: 편집 가능 · 호출 연결 가능 · 미분석 (블록 종류로 나눈다)."""
    groups = [[], [], []]
    for card in project["cards"]:
        ops = [b.get("op") for effect in card.get("effects", []) for b in B.walk(effect.get("blocks", []))]
        group = 2 if "original_play" in ops else 1 if "src_call" in ops else 0
        groups[group].append(card)
    return groups


class _TextDialog(QDialog):
    def __init__(self, parent, title, text):
        super().__init__(parent)
        self.setWindowTitle(title)
        root = QVBoxLayout(self)
        view = QPlainTextEdit()
        view.setReadOnly(True)
        view.setPlainText(text)
        root.addWidget(view, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)
        self.resize(760, 640)


def show_balance(parent, project):
    dialog = _TextDialog(parent, "카드 풀 밸런스 · 설명 검사", balance_text(project))
    dialog.exec()


class UnresolvedDialogQt(QDialog):
    """가져온 모드의 미연결 항목: 호출을 효과 블록에 잇고(Tk 의 '미연결 호출'), 없는 카드·파워를 다른 항목으로 잇는다."""

    def __init__(self, parent, project, on_change):
        super().__init__(parent)
        self.setWindowTitle("가져온 모드 · 미연결 호출")
        self.project = project
        self.on_change = on_change
        self.groups = {}
        self.missing = {}
        root = QVBoxLayout(self)
        self.listing = QListWidget()
        root.addWidget(self.listing, 1)
        button = QPushButton("선택한 항목 연결…")
        button.clicked.connect(self.connect)
        root.addWidget(button)
        self.refresh()

    def refresh(self):
        self.groups = callmap.scan_calls(self.project)
        self.missing = missing_refs(self.project)
        self.listing.clear()
        for (_owner, signature), rows in self.groups.items():
            self.listing.addItem(f"{len(rows)}곳 · {rows[0][2].get('name_ko', '')} · {signature}")
        for (kind, ref), slots in self.missing.items():
            self.listing.addItem(f"{len(slots)}곳 · 누락된 {'카드' if kind == 'card' else '파워'} · {ref}")
        if not self.groups and not self.missing:
            self.listing.addItem("연결할 항목이 없습니다.")

    def _pick_target(self, kind, ref):
        """대체할 항목을 고른다. 고른 항목의 ID, 취소하면 None."""
        candidates = self.project["cards" if kind == "card" else "powers"]
        chooser = QDialog(self)
        chooser.setWindowTitle(f"{ref} 대신 연결할 항목")
        col = QVBoxLayout(chooser)
        box = QComboBox()
        for c in candidates:
            box.addItem(f"{c['name_ko']} ({c['id']})", c["id"])
        col.addWidget(box)
        ok = QPushButton("모두 연결")
        ok.clicked.connect(chooser.accept)
        col.addWidget(ok)
        if chooser.exec() != QDialog.DialogCode.Accepted.value:
            return None
        return box.currentData()

    def connect(self):
        row = self.listing.currentRow()
        if row < 0:
            return
        if row < len(self.groups):
            self._connect_call(list(self.groups.items())[row])
            return
        if row - len(self.groups) >= len(self.missing):
            return
        kind, ref = list(self.missing)[row - len(self.groups)]
        candidates = self.project["cards" if kind == "card" else "powers"]
        if not candidates:
            QMessageBox.information(self, IO.APP_TITLE, "먼저 대체할 항목을 만드세요.")
            return
        target = self._pick_target(kind, ref)
        if not target:
            return
        for node, key, prefix in self.missing[kind, ref]:
            node[key] = prefix + target
        self.on_change()
        self.refresh()

    def _connect_call(self, group):
        (owner, _signature), rows = group
        parent, index, item = rows[0]
        dialog = CallMappingDialogQt(self, SimpleNamespace(project=self.project, owner_kind=owner, item=item),
                                     parent[index])
        if not dialog.exec() or not dialog.result:
            return
        rule = dialog.result.get("rule")
        try:
            updates = callmap.apply_connection(self.project, owner, rows, dialog.result["block"], rule)
        except ValueError as e:
            QMessageBox.warning(self, IO.APP_TITLE, str(e))
            return
        if rule:
            self.project.setdefault("call_mappings", []).append(rule)
        for node, index, block in updates:
            node[index] = block
        self.on_change()
        self.refresh()


class ImportResultsDialogQt(QDialog):
    """다른 모드를 가져온 뒤의 결과: 세 묶음으로 나눈 카드 목록 (Tk 의 import_results 와 같다).

    '카드 열기' · '다시 분석'(원본 코드를 다시 블록으로 푼다) · '같은 호출 연결…'(미연결 호출 창)."""

    def __init__(self, parent, project, notes, open_card, analyze_card=None, show_unresolved=None):
        super().__init__(parent)
        self.setWindowTitle("다른 모드 가져오기 결과")
        self.open_card = open_card
        self.analyze_card = analyze_card
        self.show_unresolved = show_unresolved
        root = QVBoxLayout(self)
        root.addWidget(QLabel(notes[0] if notes else ""))
        tabs = QTabWidget()
        root.addWidget(tabs, 1)
        names = ("편집 가능", "호출 연결 가능", "미분석 · 재분석 필요")
        for rows, title in zip(import_groups(project), names):
            page = QWidget()
            col = QVBoxLayout(page)
            listing = QListWidget()
            for card in rows:
                listing.addItem(f"{card.get('name_ko', '')} ({card['id']})")
            col.addWidget(listing)
            buttons = QHBoxLayout()
            open_button = QPushButton("카드 열기")
            open_button.clicked.connect(lambda _=False, lst=listing, cards=rows: self._open(lst, cards, False))
            buttons.addWidget(open_button)
            if title != "편집 가능" and analyze_card is not None:
                again = QPushButton("다시 분석")
                again.clicked.connect(lambda _=False, lst=listing, cards=rows: self._open(lst, cards, True))
                buttons.addWidget(again)
            if title == "호출 연결 가능" and show_unresolved is not None:
                connect = QPushButton("같은 호출 연결…")
                connect.clicked.connect(lambda _=False: self._after_accept(show_unresolved))
                buttons.addWidget(connect)
            buttons.addStretch(1)
            col.addLayout(buttons)
            tabs.addTab(page, f"{title} ({len(rows)})")
        if len(notes) > 1:
            root.addWidget(QLabel("\n".join(notes[1:])))
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(self.reject)
        close.accepted.connect(self.accept)
        root.addWidget(close)

    def _open(self, listing, cards, analyze):
        row = listing.currentRow()
        if row < 0:
            return
        card_id = cards[row]["id"]
        if analyze:
            self._after_accept(lambda: self.analyze_card(card_id))
        else:
            self._after_accept(lambda: self.open_card(card_id))

    def _after_accept(self, action):
        self.accept()
        action()

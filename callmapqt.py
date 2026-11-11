"""가져온 호출을 효과 블록에 잇는 창 (Qt 版 CallMappingDialog). 같은 형태의 호출을 계속 잇는 규칙도 함께 저장한다.

규칙 계산은 callmap.py 가 한다. 여기서는 칸을 그리고 고른 값을 블록 모양으로 바꾼다.
"""
import copy

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMessageBox, QSpinBox, QVBoxLayout, QWidget)

import blockcode as B
import callmap
import modgen as M
import projectio as IO
from gimmickrules import plain
import qtkit as Q

FIELD_LABELS = {"who": "대상", "amount": "수치", "hits": "타격 횟수", "powered": "상태 효과 보정",
                "power": "파워", "keyword": "키워드", "action": "동작"}


class CallMappingDialogQt(QDialog):
    """editor 는 project · owner_kind · item 을 가진 것이다 (Tk 의 editor 와 같다)."""

    def __init__(self, parent, editor, block):
        super().__init__(parent)
        self.editor, self.block = editor, block
        self.setWindowTitle("가져온 호출을 블록에 연결")
        self.result = None
        self.signature, slots = callmap.source_call_slots(block)
        self.source_slots = [s for s in slots if s.get("source_segment") is not None and
                             s.get("source_arg") is not None and s.get("kind") in ("value", "code")]
        self.widgets = {}

        root = QVBoxLayout(self)
        title = QLabel(block.get("label") or "가져온 호출")
        title.setStyleSheet("font-weight: bold;")
        title.setWordWrap(True)
        root.addWidget(title)
        hint = QLabel("이 호출을 어떤 공용 효과 블록으로 바꿀지 정하세요. 수치와 코드 칸을 원본 인수에 연결하거나 직접 지정할 수 있습니다.")
        hint.setWordWrap(True)
        root.addWidget(hint)

        pick = QHBoxLayout()
        pick.addWidget(QLabel("연결할 블록"))
        self.op = QComboBox()
        for op in B.MANUAL_MAP_OPS:
            if op == "flash" and editor.owner_kind not in ("relic", "power", "summon", "button", "pet"):
                continue
            self.op.addItem(f"{B.CATS[B.SPECS[op]['cat']][0]} · {B.SPECS[op]['ko']}", op)
        self.op.setCurrentIndex(max(0, self.op.findData("damage")))
        self.op.currentIndexChanged.connect(lambda _i: self._build_fields())
        pick.addWidget(self.op, 1)
        root.addLayout(pick)

        self.fields = QWidget()
        self.form = QGridLayout(self.fields)
        root.addWidget(self.fields)

        self.keep = QCheckBox("이 모드에서 같은 호출을 계속 이 블록에 연결")
        self.keep.setChecked(True)
        root.addWidget(self.keep)
        rule_hint = QLabel("규칙은 호출 형태가 정확히 같은 경우에만 다시 적용됩니다.")
        rule_hint.setStyleSheet(f"color: {Q.C['muted']};")
        root.addWidget(rule_hint)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.ok)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._build_fields()

    def _warn(self, text):
        QMessageBox.warning(self, IO.APP_TITLE, text)

    def _build_fields(self):
        while self.form.count():
            widget = self.form.takeAt(0).widget()
            if widget is not None:
                widget.deleteLater()
        self.widgets = {}
        op = self.op.currentData()
        spec = B.SPECS[op].get("args", {})
        who_opts = [x for x in B.who_options(self.editor.owner_kind, multi=True) if x[0] != "it"]
        power_opts = M.power_options(self.editor.project)
        source_opts = []
        for source in self.source_slots:
            key = source["key"]
            shown = self.block.get("args", {}).get(key, source.get("orig", ""))
            if source.get("kind") == "value" and isinstance(shown, dict):
                description = B.value_label(shown, self.editor.project, card=self.editor.owner_kind == "card")
            else:
                description = str(shown or source.get("orig", ""))
            source_opts.append((f"arg:{key}", f"원본 인수 · {source.get('name', key)} ({plain(description)[:45]})"))
        value_opts = [("fixed", "고정 수치 입력")] + source_opts
        code_opts = [("fixed", "고정 코드 식 입력")] + source_opts

        for row, (field, (kind, default)) in enumerate(spec.items()):
            self.form.addWidget(QLabel(FIELD_LABELS.get(field, field)), row, 0)
            if kind in ("value", "code"):
                box = QWidget()
                line = QHBoxLayout(box)
                line.setContentsMargins(0, 0, 0, 0)
                choice = QComboBox()
                for value, text in (value_opts if kind == "value" else code_opts):
                    choice.addItem(text, value)
                text_box = QLineEdit()
                if kind == "value":
                    text_box.setText(str(default.get("v", 1) if isinstance(default, dict) and default.get("t") == "num" else 1))
                else:
                    text_box.setText(str(default or ""))
                choice.currentIndexChanged.connect(
                    lambda _i, c=choice, e=text_box: e.setEnabled(c.currentData() == "fixed"))
                line.addWidget(choice, 1)
                line.addWidget(text_box)
                self.widgets[field] = {"kind": kind, "choice": choice, "value": text_box}
                self.form.addWidget(box, row, 1)
            elif kind in ("who_multi", "power", "keyword", "kw_action", "bool"):
                combo = QComboBox()
                options = {"who_multi": who_opts, "power": power_opts, "keyword": M.CARD_KEYWORDS,
                           "kw_action": B.KW_ACTIONS, "bool": [(True, "적용"), (False, "적용 안 함")]}[kind]
                for value, text in options:
                    combo.addItem(text, value)
                index = combo.findData(bool(default) if kind == "bool" else default)
                combo.setCurrentIndex(max(0, index))
                self.widgets[field] = {"kind": kind, "combo": combo}
                self.form.addWidget(combo, row, 1)
            elif kind == "int":
                spin = QSpinBox()
                spin.setRange(1, 99)
                spin.setValue(int(default or 1))
                self.widgets[field] = {"kind": kind, "spin": spin}
                self.form.addWidget(spin, row, 1)

    def ok(self):
        op = self.op.currentData()
        block = B.new_block(op)
        bindings = {}
        for field, widget in self.widgets.items():
            kind = widget["kind"]
            if kind in ("value", "code"):
                selected = widget["choice"].currentData()
                if selected.startswith("arg:"):
                    key = selected[4:]
                    source = next((s for s in self.source_slots if s.get("key") == key), None)
                    if not source:
                        self._warn("선택한 원본 인수를 찾을 수 없습니다.")
                        return
                    current = self.block.get("args", {}).get(key, source.get("orig", ""))
                    if kind == "code":
                        if isinstance(current, dict) and current.get("t") == "src":
                            code = current.get("code") or source.get("orig", "")
                        elif isinstance(current, dict):
                            try:
                                code = B._Gen(self.editor.project, M._Ctx(self.editor.owner_kind, self.editor.item)).val(current)
                            except Exception:  # noqa: BLE001 - 풀 수 없는 식이면 원본 글을 쓴다
                                code = source.get("orig", "")
                        else:
                            code = current or source.get("orig", "")
                        block["args"][field] = str(code).strip()
                    elif source.get("kind") == "value" and isinstance(current, dict):
                        block["args"][field] = copy.deepcopy(current)
                    else:
                        block["args"][field] = {"t": "src", "code": str(current or source.get("orig", ""))}
                    bindings[field] = {"kind": "arg", "segment": source["source_segment"], "index": source["source_arg"],
                                       "initial_value": copy.deepcopy(block["args"][field])}
                else:
                    raw = widget["value"].text().strip()
                    if kind == "code":
                        value = raw
                    else:
                        try:
                            number = float(raw) if "." in raw else int(raw)
                        except ValueError:
                            self._warn(f"{field}에 숫자를 입력해 주세요.")
                            return
                        value = {"t": "num", "v": number}
                    block["args"][field] = copy.deepcopy(value)
                    bindings[field] = {"kind": "fixed", "value": value}
            elif kind == "int":
                value = int(widget["spin"].value())
                block["args"][field] = value
                bindings[field] = {"kind": "fixed", "value": value}
            else:
                value = widget["combo"].currentData()
                block["args"][field] = value
                bindings[field] = {"kind": "fixed", "value": value}
        rule = {"signature": self.signature, "op": op, "bindings": bindings}
        self.result = {"block": block, "rule": rule if self.keep.isChecked() and self.signature else None}
        self.accept()

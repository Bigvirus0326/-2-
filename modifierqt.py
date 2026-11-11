"""파워의 '상시 효과'(수정자) 목록과 편집 창의 Qt 版 (Tk 의 ModifierList · ModifierDialog 와 같은 규칙)."""
import fxbtn as FX
import gimmick as GM
import modgen as M
import pets as PT
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout, QWidget)

import projectio as IO
import qtkit as Q


def _label(text=""):
    text_label = QLabel(text)
    text_label.setWordWrap(True)
    return text_label


def _warn(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


def _combo(options, value=None):
    box = QComboBox()
    for v, text in options:
        box.addItem(text, v)
    if value is not None:
        Q.set_combo_value(box, value)
    return box


class ModifierDialogQt(QDialog):
    def __init__(self, parent, mod, project):
        super().__init__(parent)
        self.setWindowTitle("상시 효과 편집")
        self.result = None
        self.project = project
        m = dict(M.new_modifier(), **(mod or {}))
        self._ref_init = m.get("ref") or ""
        root = QVBoxLayout(self)
        grid = QGridLayout()
        grid.addWidget(_label("종류"), 0, 0)
        self.kind = _combo(M.MODIFIER_KINDS, m["kind"])
        self.kind.currentIndexChanged.connect(lambda _i: self._kind_changed())
        grid.addWidget(self.kind, 0, 1)
        grid.addWidget(_label("수치"), 1, 0)
        self.value = QLineEdit(str(m["value"]))
        grid.addWidget(self.value, 1, 1)
        self.per_stack = QCheckBox("× 이 파워의 스택 수")
        self.per_stack.setChecked(bool(m["per_stack"]))
        grid.addWidget(self.per_stack, 2, 1)
        grid.addWidget(_label("어떤 카드에"), 3, 0)
        self.filter = _combo(GM.card_filters(project), m.get("filter") or "Any")
        grid.addWidget(self.filter, 3, 1)
        self.ref_lbl = _label("무엇에")
        self.ref = QComboBox()
        grid.addWidget(self.ref_lbl, 4, 0)
        grid.addWidget(self.ref, 4, 1)
        root.addLayout(grid)
        root.addWidget(_label("음수는 감소입니다. % 종류는 50 = 50% 증가, -25 = 25% 감소.\n"
                              "'공격 피해'는 카드 공격처럼 힘의 영향을 받는 피해에만 적용됩니다.\n"
                              "'어떤 카드에'는 공격 피해 / 카드 비용 / 별 비용 / 자원 비용에 쓰입니다 (예: #격투 카드 피해 +2).\n"
                              "기믹 종류: 구체 수치(밀집처럼)·구체 슬롯·별 비용·골골이·소환 슬롯·자원 최대치/비용·버튼 비용/횟수."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._kind_changed(first=True)

    def _ref_options(self, what):
        if what == "orb":
            return [("", "모든 구체")] + GM.orb_options(self.project), "어떤 구체에"
        if what == "power":
            return [("", "(자원 파워를 고르세요)")] + M.power_options(self.project), "어떤 자원에"
        if what == "pet":
            return [("", "모든 동료")] + [(p["id"], p.get("name_ko") or p["id"]) for p in PT.pets(self.project)], "어떤 동료에"
        return [("", "모든 버튼")] + [(b["id"], b.get("label_ko") or b["id"]) for b in FX.buttons(self.project)], "어떤 버튼에"

    def _kind_changed(self, first=False):
        k = self.kind.currentData()
        need = M.MODIFIER_REF.get(k)
        if need:
            options, text = self._ref_options(need[0])
            current = self._ref_init if first else self.ref.currentData()
            self.ref.blockSignals(True)
            self.ref.clear()
            for v, t in options:
                self.ref.addItem(t, v)
            index = self.ref.findData(current or "")
            self.ref.setCurrentIndex(index if index >= 0 else 0)
            self.ref.blockSignals(False)
            self.ref_lbl.setText(text)
            self.ref.setVisible(True)
            self.ref_lbl.setVisible(True)
        else:
            self.ref.setVisible(False)
            self.ref_lbl.setVisible(False)
        self.filter.setEnabled(k in M.MODIFIER_FILTERED)

    def _accept(self):
        try:
            v = int(self.value.text().strip() or "0")
        except ValueError:
            _warn(self, "숫자를 입력하세요.")
            return
        k = self.kind.currentData()
        ref = (self.ref.currentData() or "") if k in M.MODIFIER_REF else ""
        if k in M.MODIFIER_REF and not M.MODIFIER_REF[k][1] and not ref:
            _warn(self, "어떤 자원에 적용할지 고르세요.")
            return
        self.result = {"kind": k, "value": v, "per_stack": bool(self.per_stack.isChecked()),
                       "filter": (self.filter.currentData() or "Any") if k in M.MODIFIER_FILTERED else "Any",
                       "ref": ref}
        self.accept()


class ModifierListQt(QWidget):
    """상시 효과 목록. set() 에 넘긴 리스트를 직접 고친다 (Tk 와 같다)."""

    def __init__(self, project_of, on_change, parent=None):
        super().__init__(parent)
        self.project_of = project_of
        self.on_change = on_change
        self.mods = []
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lst.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.lst.itemDoubleClicked.connect(lambda _it: self.edit())
        row.addWidget(self.lst, 1)
        buttons = QVBoxLayout()
        for text, slot in (("추가", self.add), ("편집", self.edit), ("삭제", self.remove)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        row.addLayout(buttons)
        root.addLayout(row)

    def set(self, mods):
        self.mods = mods
        self.refresh()

    def _describe(self, m):
        unit = "%" if m["kind"].endswith("pct") else ""
        project = self.project_of()
        label = M.MODIFIER_LABEL.get(m["kind"], m["kind"])
        if (m.get("filter") or "Any") != "Any":
            label += f"  [{M.label_of(GM.card_filters(project), m['filter'])}]"
        if m.get("ref"):
            label += f"  → {GM._ref_name(project, m, 'ko')}"
        if m["kind"] in M.MODIFIER_NO_VALUE:
            label = label.replace(" +", "")
        return label, f"{m['value']:+d}{unit}", "예" if m["per_stack"] else "-"

    def refresh(self, select=None):
        self.lst.clear()
        for m in self.mods:
            label, value, stack = self._describe(m)
            self.lst.addItem(f"{label}    {value}    스택 비례: {stack}")
        if select is not None and 0 <= select < len(self.mods):
            self.lst.setCurrentRow(select)

    def _sel(self):
        row = self.lst.currentRow()
        return row if row >= 0 else None

    def add(self):
        d = ModifierDialogQt(self, None, self.project_of())
        d.exec()
        if d.result:
            self.mods.append(d.result)
            self.refresh(len(self.mods) - 1)
            self.on_change()

    def edit(self):
        i = self._sel()
        if i is None:
            return
        d = ModifierDialogQt(self, self.mods[i], self.project_of())
        d.exec()
        if d.result:
            self.mods[i] = d.result
            self.refresh(i)
            self.on_change()

    def remove(self):
        i = self._sel()
        if i is None:
            return
        del self.mods[i]
        self.refresh()
        self.on_change()

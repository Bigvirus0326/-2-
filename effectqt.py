"""효과 목록(EffectListQt)과 효과 편집 창(EffectDialogQt)의 Qt 版. Tk 의 EffectList · EffectDialog 와 같은 규칙을 쓴다.

아직 Qt 에서 못 하는 것: 블록 코딩 편집기 (블록 편집은 Tk 앱에서, 블록 해제는 여기서 된다), 원본 효과(통째로 가져온
카드)의 블록 다시 풀기. 블록이 있는 효과는 블록이 만든 C# 코드와 설명을 읽기 전용으로 보여 주고 그대로 저장한다.
"""
import blockcode
import modgen as M
from PySide6.QtCore import QByteArray, QMimeData, QRect, Qt
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox, QGridLayout,
                               QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPlainTextEdit, QPushButton,
                               QSpinBox, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

import effectrules as ER
import projectio as IO
import qtkit as Q

EFFECT_ROWS_MIME = "application/x-sts2-effect-rows"

SPIN_RANGE = (-9999, 9999)   # 기존 값을 위젯이 고쳐 쓰지 않게 넓게 둔다
LANG_NAMES = (("ko", "설명 문구 (한국어)"), ("en", "설명 문구 (영어)"), ("zh", "설명 문구 (중국어 간체)"))
UPGRADE_NAMES = (("ko", "강화 설명 (한국어)"), ("en", "강화 설명 (영어)"), ("zh", "강화 설명 (중국어)"))


def _label(text=""):
    label = QLabel(text)
    label.setWordWrap(True)
    return label


def _combo(options, value=None):
    box = QComboBox()
    for v, label in options:
        box.addItem(label, v)
    if value is not None:
        Q.set_combo_value(box, value)
    return box


def _spin(value, lo=SPIN_RANGE[0], hi=SPIN_RANGE[1]):
    spin = QSpinBox()
    spin.setRange(lo, hi)
    try:
        spin.setValue(int(value or 0))
    except (TypeError, ValueError):
        spin.setValue(0)
    return spin


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


def _warn(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


def _info(parent, text):
    QMessageBox.information(parent, IO.APP_TITLE, text)


def _show(widgets, on):
    for w in widgets:
        w.setVisible(on)


class EffectDialogQt(QDialog):
    def __init__(self, parent, effect, owner_kind, project, item):
        super().__init__(parent)
        self.setWindowTitle("효과 편집")
        self.result = None
        self.owner_kind = owner_kind
        self.item = item or {}
        self.project = project
        e = dict(M.new_effect(), **(effect or {}))
        self.blocks = list(e.get("blocks") or [])
        self.auto_text = bool(e.get("auto_text", True))
        popts = M.power_options(project)
        has_other = owner_kind == "power" and self.item.get("trigger") in M.POWER_OTHER
        other_label = f"상대 ({M.POWER_OTHER[self.item['trigger']]})" if has_other else ""
        on_opts = [("self", "자신")]
        if owner_kind in ("card", "potion"):
            on_opts.append(("target", "대상 (적 하나일 때)"))
        elif has_other:
            on_opts.append(("target", other_label))
        none_opt = [("", "(없음)")]
        tgt_opts = [("self", "자신"), ("enemy", "적 (대상 설정을 따름)")]
        if has_other:
            tgt_opts.append(("other", other_label))

        root = QVBoxLayout(self)

        # ---- 기본 ----
        basic_box = QGroupBox("기본")
        basic = QGridLayout(basic_box)
        self.kind = _combo(M.EFFECT_KINDS, e["kind"])
        basic.addWidget(_label("효과 종류"), 0, 0)
        basic.addWidget(self.kind, 0, 1, 1, 2)
        self.amount_lbl = _label("수치")
        self.amount = _spin(e["amount"])
        self.per_stack = QCheckBox("× 이 파워의 스택 수")
        self.per_stack.setChecked(bool(e.get("per_stack")))
        basic.addWidget(self.amount_lbl, 1, 0)
        basic.addWidget(self.amount, 1, 1)
        basic.addWidget(self.per_stack, 1, 2)
        self.up_lbl = _label("강화 시 +")
        self.upgrade = _spin(e["upgrade"], -99, 99)
        basic.addWidget(self.up_lbl, 2, 0)
        basic.addWidget(self.upgrade, 2, 1)
        self.hits_lbl = _label("타격 횟수")
        self.hits = _spin(e["hits"], 1, 99)
        basic.addWidget(self.hits_lbl, 3, 0)
        basic.addWidget(self.hits, 3, 1)
        self.pow_lbl = _label("파워")
        self.power = _combo(popts, e["power"])
        basic.addWidget(self.pow_lbl, 4, 0)
        basic.addWidget(self.power, 4, 1, 1, 2)
        self.tgt_lbl = _label("대상")
        self.target = _combo(tgt_opts, e["target"])
        basic.addWidget(self.tgt_lbl, 5, 0)
        basic.addWidget(self.target, 5, 1, 1, 2)
        self.x_lbl = _label("X 사용")
        self.x_use = _combo(M.X_USES, e.get("x_use", ""))
        self.x_lbl.setToolTip("X 비용 카드에서 X(쓴 에너지) 를 어떻게 쓸지: 'X번 반복' = 이 효과를 X번, "
                              "'수치 × X' = 수치에 X 를 곱함.")
        basic.addWidget(self.x_lbl, 6, 0)
        basic.addWidget(self.x_use, 6, 1, 1, 2)
        root.addWidget(basic_box)

        # ---- 조건 ----
        cond_box = QGroupBox("조건 (선택) - 이 조건을 만족할 때만 효과 발동")
        cond = QHBoxLayout(cond_box)
        self.cond_on = _combo(on_opts, e.get("cond_on", "self"))
        self.cond_power = _combo(none_opt + popts, e.get("cond_power", ""))
        self.cond_min = _spin(e.get("cond_min", 1), 1, 999)
        for w in (self.cond_on, _label("의"), self.cond_power, _label("이(가)"), self.cond_min, _label("이상이면")):
            cond.addWidget(w)
        cond.addStretch(1)
        root.addWidget(cond_box)

        # ---- 스택 비례 ----
        self.scale_box = QGroupBox("스택 비례 추가 (선택) - 수치 + (파워 스택 × N)")
        scale = QHBoxLayout(self.scale_box)
        self.scale_on = _combo(on_opts, e.get("scale_on", "self"))
        self.scale_power = _combo(none_opt + popts, e.get("scale_power", ""))
        self.scale_per = _spin(e.get("scale_per", 1), -99, 99)
        for w in (self.scale_on, _label("의"), self.scale_power, _label("1당 +"), self.scale_per):
            scale.addWidget(w)
        scale.addStretch(1)
        root.addWidget(self.scale_box)

        # ---- 직접 코드 (블록 또는 C#) ----
        self.code_box = QGroupBox("새 능력 (블록 코딩 또는 직접 C# 코드)")
        code = QVBoxLayout(self.code_box)
        bar = QHBoxLayout()
        block_btn = QPushButton("🧩 블록 코딩으로 만들기 / 편집")
        block_btn.clicked.connect(lambda _=False: self.open_blocks())
        self.unblock_btn = QPushButton("블록 해제 (C# 직접 편집)")
        self.unblock_btn.clicked.connect(self.release_blocks)
        self.block_info = _label("")
        self.block_info.setStyleSheet(f"color: {Q.C['success']};")
        for w in (block_btn, self.unblock_btn, self.block_info):
            bar.addWidget(w)
        bar.addStretch(1)
        code.addLayout(bar)
        self.code = QPlainTextEdit()
        self.code.setFixedHeight(9 * 18 + 12)
        self.code.setStyleSheet("font-family: Consolas;")
        self.code.setPlainText(e.get("code", ""))
        code.addWidget(self.code)
        code.addWidget(_label(ER.CODE_HELP.get(owner_kind, "")))
        grid = QGridLayout()
        self._text_boxes = {}
        for row, (lang, text) in enumerate(LANG_NAMES):
            box = QLineEdit(e.get(f"text_{lang}", ""))
            grid.addWidget(_label(text), row, 0)
            grid.addWidget(box, row, 1)
            self._text_boxes[lang] = box
        self._upgrade_boxes = {}
        for row, (lang, text) in enumerate(UPGRADE_NAMES, len(LANG_NAMES)):
            box = QLineEdit((e.get("upgraded_text") or {}).get(lang, ""))
            grid.addWidget(_label(text), row, 0)
            grid.addWidget(box, row, 1)
            self._upgrade_boxes[lang] = box
        code.addLayout(grid)
        root.addWidget(self.code_box)

        self.note = _label("")
        self.note.setStyleSheet(f"color: {Q.C['muted']};")
        root.addWidget(self.note)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self._rows = {"amount": [self.amount_lbl, self.amount], "per_stack": [self.per_stack],
                      "upgrade": [self.up_lbl, self.upgrade], "hits": [self.hits_lbl, self.hits],
                      "power": [self.pow_lbl, self.power], "target": [self.tgt_lbl, self.target],
                      "x": [self.x_lbl, self.x_use]}
        self.kind.currentIndexChanged.connect(lambda _i: self.refresh())
        self.power.currentIndexChanged.connect(lambda _i: self._power_default())
        self.refresh()
        self._sync_block_ui()

    # ---- 화면 규칙 (Tk 와 같다) ----
    def refresh(self):
        k = self.kind.currentData()
        is_power_owner = self.owner_kind == "power"
        r = self._rows
        _show(r["amount"], k != "code")
        _show(r["per_stack"], is_power_owner and k not in ("code", "remove_power"))
        _show(r["upgrade"], self.owner_kind == "card" and k not in ("code", "remove_power"))
        _show(r["hits"], k == "damage")
        _show(r["power"], k in ("power", "remove_power"))
        _show(r["target"], k in ("power", "remove_power") or (k == "damage" and is_power_owner))
        _show(r["x"], self.owner_kind == "card" and bool(self.item.get("x_cost")))
        self.scale_box.setVisible(k not in ("code", "remove_power"))
        self.code_box.setVisible(k == "code")
        self.amount_lbl.setText("제거량 (0 = 전부)" if k == "remove_power" else "수치")
        notes = {
            "damage": "카드: 카드의 대상(적 하나/모든 적/무작위)으로 공격합니다. 유물·파워는 '적 대상' 설정, 물약은 물약 대상을 따릅니다.",
            "power": "★ 표시는 '파워' 탭에서 직접 만든 새 파워입니다.",
            "remove_power": "대상이 가진 파워를 줄이거나 없앱니다. 예: 쌓아 둔 '불씨'를 터뜨리는 카드.",
            "lose_hp": "방어도를 무시하고 자신의 체력을 잃습니다.",
            "code": "🧩 블록 코딩: 블록을 끌어다 쌓아 새 능력을 만들면 C# 코드와 설명이 자동으로 만들어집니다. "
                    "블록 없이 C#을 직접 써도 됩니다 (문법 오류는 ③ 빌드 때 로그에 나옵니다).",
        }
        self.note.setText(notes.get(k, ""))
        if k == "damage" and not is_power_owner:
            Q.set_combo_value(self.target, "enemy")

    def _power_default(self):
        pm = M.power_meta(self.project, self.power.currentData())
        if pm and self.kind.currentData() == "power":
            Q.set_combo_value(self.target, pm["target"])

    def _sync_block_ui(self):
        """블록이 있으면 C# 칸은 블록이 만든 결과를 읽기 전용으로 보여 준다."""
        has = bool(self.blocks)
        if has:
            lines, errs = blockcode.compile_blocks(self.blocks, self.project, M._Ctx(self.owner_kind, self.item), "")
            self.code.setReadOnly(True)
            self.code.setPlainText("\n".join(lines))
            n = sum(1 for _ in blockcode.walk(self.blocks))
            info = f"🧩 블록 {n}개로 만든 능력"
            if self.auto_text:
                info += " · 설명 자동"
            if errs:
                info += f" · ⚠ 문제 {len(set(errs))}개"
            self.block_info.setText(info)
            self.block_info.setStyleSheet(f"color: {Q.C['danger'] if errs else Q.C['success']};")
            self.unblock_btn.setEnabled(True)
            if self.auto_text:
                for lang, box in self._text_boxes.items():
                    box.setText(blockcode.describe(self.blocks, self.project, self.owner_kind, lang))
        else:
            self.code.setReadOnly(False)
            self.block_info.setText("")
            self.unblock_btn.setEnabled(False)
        enabled = not (has and self.auto_text)
        for box in self._text_boxes.values():
            box.setEnabled(enabled)

    def open_blocks(self):
        from blockqt import edit_blocks
        result = edit_blocks(self, self.project, self.owner_kind, self.item, self.blocks,
                             text_ko=self._text_boxes["ko"].text(), text_en=self._text_boxes["en"].text(),
                             text_zh=self._text_boxes["zh"].text(), auto_text=self.auto_text,
                             upgraded_text={lang: box.text() for lang, box in self._upgrade_boxes.items()})
        if result is None:
            return
        self.blocks = result["blocks"]
        self.auto_text = result["auto_text"]
        for lang, box in self._upgrade_boxes.items():
            box.setText(result.get("upgraded_text", {}).get(lang, ""))
        if not self.auto_text:
            self._text_boxes["ko"].setText(result["text_ko"])
            self._text_boxes["en"].setText(result["text_en"])
            self._text_boxes["zh"].setText(result.get("text_zh", ""))
        self.code.setPlainText(result.get("code", ""))
        self._sync_block_ui()

    def release_blocks(self):
        if not _ask(self, "블록을 해제하고 지금 만들어진 C# 코드를 직접 편집할까요?\n(블록 편집기로는 다시 돌아갈 수 없습니다)"):
            return
        self.blocks = []
        self.auto_text = False
        self._sync_block_ui()

    def _accept(self):
        k = self.kind.currentData()
        use_blocks = k == "code" and bool(self.blocks)
        if k == "code" and not use_blocks and not self.code.toPlainText().strip():
            _warn(self, "블록 코딩으로 만들거나 코드를 입력하세요.")
            return
        keep_text = k == "code" and not (use_blocks and self.auto_text)
        tgt = self.target.currentData()
        if k not in ("power", "remove_power") and not (k == "damage" and self.owner_kind == "power"):
            tgt = "enemy"
        if k == "damage" and tgt == "self":
            tgt = "enemy"
        self.result = {
            "kind": k, "amount": int(self.amount.value()),
            "upgrade": int(self.upgrade.value()) if self.owner_kind == "card" else 0,
            "hits": max(1, int(self.hits.value())), "power": self.power.currentData(), "target": tgt,
            "per_stack": bool(self.per_stack.isChecked()) and self.owner_kind == "power",
            "x_use": self.x_use.currentData() if self.owner_kind == "card" and self.item.get("x_cost") else "",
            "cond_power": self.cond_power.currentData(), "cond_min": int(self.cond_min.value()),
            "cond_on": self.cond_on.currentData(),
            "scale_power": self.scale_power.currentData() if k not in ("code", "remove_power") else "",
            "scale_per": int(self.scale_per.value()), "scale_on": self.scale_on.currentData(),
            "code": self.code.toPlainText().rstrip() if k == "code" else "",
            "blocks": self.blocks if use_blocks else [],
            "auto_text": self.auto_text if use_blocks else False,
            # 설명 자동이면 비워 두고 빌드 때 블록에서 만든다 (블록과 설명이 어긋나지 않게)
            "upgraded_text": {lang: box.text().strip() for lang, box in self._upgrade_boxes.items()} if keep_text else {},
            "text_ko": self._text_boxes["ko"].text().strip() if keep_text else "",
            "text_en": self._text_boxes["en"].text().strip() if keep_text else "",
            "text_zh": self._text_boxes["zh"].text().strip() if keep_text else "",
        }
        self.accept()


class _EffectTree(Q.BandSelectMixin, QTreeWidget):
    """효과 표: 빈 곳을 끌어 고르고, 고른 줄을 끌어 순서를 바꾸고, Delete 로 지운다 (EffectListQt 가 처리한다)."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self._line = Q.DropLine(self.viewport())

    def _band_items(self):
        return [self.topLevelItem(i) for i in range(self.topLevelItemCount())]

    def startDrag(self, supported_actions):
        items = self.selectedItems()
        if not items:
            return
        mime = QMimeData()
        rows = sorted({self.indexOfTopLevelItem(it) for it in items})
        mime.setData(EFFECT_ROWS_MIME, QByteArray(",".join(str(r) for r in rows).encode("utf8")))
        drag = QDrag(self)
        drag.setMimeData(mime)
        picture, grab_at = Q.drag_picture(self, [self.visualItemRect(it) for it in items])
        if picture is not None:
            drag.setPixmap(picture)
            drag.setHotSpot(grab_at)
        drag.exec(Qt.DropAction.CopyAction)
        self._line.clear()

    def dragEnterEvent(self, event):
        if event.mimeData().hasFormat(EFFECT_ROWS_MIME):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not event.mimeData().hasFormat(EFFECT_ROWS_MIME):
            return event.ignore()
        event.acceptProposedAction()
        pos = event.position().toPoint()
        target = self.itemAt(pos)
        if target is not None:
            rect = self.visualItemRect(target)
            y = rect.bottom() if pos.y() > rect.center().y() else rect.top()
            self._line.show_at(QRect(rect.left(), y - 2, rect.width(), 4))
        elif self.topLevelItemCount():
            rect = self.visualItemRect(self.topLevelItem(self.topLevelItemCount() - 1))
            self._line.show_at(QRect(rect.left(), rect.bottom() - 1, rect.width(), 4))
        else:
            self._line.clear()

    def dragLeaveEvent(self, event):
        self._line.clear()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._line.clear()
        if not event.mimeData().hasFormat(EFFECT_ROWS_MIME):
            return event.ignore()
        picked = [int(x) for x in bytes(event.mimeData().data(EFFECT_ROWS_MIME)).decode("utf8").split(",") if x]
        pos = event.position().toPoint()
        target = self.itemAt(pos)
        if target is not None:
            rect = self.visualItemRect(target)
            row = self.indexOfTopLevelItem(target) + (1 if pos.y() > rect.center().y() else 0)
        else:
            row = self.topLevelItemCount()
        event.acceptProposedAction()
        self.owner._move_rows(picked, row)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Delete:
            self.owner.remove()
            return
        super().keyPressEvent(event)


class _RemoveZone(QLabel):
    """고른 효과를 여기로 끌어 놓으면 지운다."""

    def __init__(self, on_drop, parent=None):
        super().__init__("고른 효과를 여기로 끌어 놓으면 지웁니다", parent)
        self.on_drop = on_drop
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setStyleSheet(f"border: 1px dashed {Q.C['line2']}; border-radius: 6px; color: {Q.C['muted']}; padding: 6px;")

    def dragEnterEvent(self, event):
        (event.acceptProposedAction if event.mimeData().hasFormat(EFFECT_ROWS_MIME) else event.ignore)()

    def dragMoveEvent(self, event):
        (event.acceptProposedAction if event.mimeData().hasFormat(EFFECT_ROWS_MIME) else event.ignore)()

    def dropEvent(self, event):
        if event.mimeData().hasFormat(EFFECT_ROWS_MIME):
            event.acceptProposedAction()
            self.on_drop()
        else:
            event.ignore()


class EffectListQt(QWidget):
    """효과 목록 + 추가·편집·삭제·순서 바꾸기. set() 에 넘긴 리스트를 직접 고친다 (Tk 와 같다)."""

    def __init__(self, owner_kind, project_of, item_of, on_change, parent=None):
        super().__init__(parent)
        self.owner_kind = owner_kind
        self.project_of = project_of     # 호출할 때마다 현재 프로젝트를 돌려 준다
        self.item_of = item_of           # 편집 중인 항목 (없으면 {})
        self.on_change = on_change
        self.on_original = None          # 원본 효과를 고치는 함수 (항목 탭이 넣는다)
        self.effects = []

        root = QHBoxLayout(self)
        left = QVBoxLayout()
        self.tree = _EffectTree(self)
        self.tree.setHeaderLabels(["효과", "수치", "강화", "추가 정보"])
        self.tree.setRootIsDecorated(False)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)   # 빈 곳을 끌어 여러 줄을 고른다
        self.tree.setColumnHidden(2, owner_kind != "card")
        for col, width in enumerate((140, 60, 60)):
            self.tree.setColumnWidth(col, width)
        self.tree.header().setStretchLastSection(True)
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)   # 넓은 표는 표 안에서 가로로 스크롤
        self.tree.setMinimumWidth(0)
        self.tree.itemDoubleClicked.connect(lambda _it, _c: self.edit())
        left.addWidget(self.tree, 1)
        self.remove_zone = _RemoveZone(self.remove_picked)
        left.addWidget(self.remove_zone)
        root.addLayout(left, 1)
        buttons = QVBoxLayout()
        for text, slot in (("추가", self.add), ("편집", self.edit), ("삭제", self.remove),
                           ("▲", lambda: self.move(-1)), ("▼", lambda: self.move(1))):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        root.addLayout(buttons)

    def set(self, effects):
        self.effects = effects
        self.refresh()

    def refresh(self, select=None):
        self.tree.clear()
        for i, e in enumerate(self.effects):
            if e.get("original_effect"):
                item = self.item_of()
                raw = item.get("raw_vars", [])
                row = QTreeWidgetItem([
                    "원본 효과 · 블록 편집",
                    ", ".join(str(v.get("value", "")) for v in raw),
                    ", ".join(str(v.get("upgrade", "")) for v in raw),
                    (item.get("clone") or {}).get("orig_class", "")])
            else:
                up = e.get("upgrade", 0)
                amt = "" if e["kind"] == "code" else (
                    "전부" if e["kind"] == "remove_power" and not e["amount"] else e["amount"])
                row = QTreeWidgetItem([
                    M.EFFECT_LABEL.get(e["kind"], e["kind"]), str(amt),
                    (f"+{up}" if up > 0 else str(up)) if up else "-",
                    ER.effect_summary(self.project_of(), e)])
            row.setData(0, Qt.ItemDataRole.UserRole, i)
            self.tree.addTopLevelItem(row)
        if select is not None and 0 <= select < len(self.effects):
            self.tree.setCurrentItem(self.tree.topLevelItem(select))

    def _sel(self):
        row = self.tree.currentItem()
        return row.data(0, Qt.ItemDataRole.UserRole) if row is not None else None

    def _picked_rows(self):
        """고른 줄들의 번호 (고른 것이 없으면 현재 줄)."""
        items = self.tree.selectedItems() or ([self.tree.currentItem()] if self.tree.currentItem() else [])
        return sorted({self.tree.indexOfTopLevelItem(it) for it in items if it is not None
                       and self.tree.indexOfTopLevelItem(it) >= 0})

    def _move_rows(self, picked, row):
        """고른 줄들을 놓은 자리(row, 옛 번호 기준)로 옮긴다. 옮긴 줄은 다시 고른 채로 남는다."""
        picked = [i for i in picked if 0 <= i < len(self.effects)]
        if not picked:
            return
        moved = [self.effects[i] for i in picked]
        rest = [e for i, e in enumerate(self.effects) if i not in picked]
        at = row - sum(1 for i in picked if i < row)
        self.effects[:] = rest[:at] + moved + rest[at:]
        self.refresh()
        for r in range(at, at + len(moved)):
            self.tree.topLevelItem(r).setSelected(True)
        self._changed()

    def remove_picked(self):
        """끌어 놓은 자리(지우기 칸)로 지운다: 고른 줄 모두."""
        self.remove()

    def _dialog(self, effect):
        d = EffectDialogQt(self, effect, self.owner_kind, self.project_of(), self.item_of())
        d.exec()
        return d.result          # 취소하면 None (확인할 때만 결과를 채운다)

    def _changed(self):
        if self.on_change:
            self.on_change()

    def add(self):
        r = self._dialog(None)
        if r:
            self.effects.append(r)
            self.refresh(len(self.effects) - 1)
            self._changed()

    def edit(self):
        i = self._sel()
        if i is None:
            return
        if self.effects[i].get("original_effect"):
            if self.on_original is not None:
                self.on_original(i)
            return
        r = self._dialog(self.effects[i])
        if r:
            self.effects[i] = r
            self.refresh(i)
            self._changed()

    def remove(self):
        rows = self._picked_rows()
        if not rows:
            return
        for i in reversed(rows):
            del self.effects[i]
        self.refresh()
        self._changed()

    def move(self, d):
        i = self._sel()
        if i is None or not 0 <= i + d < len(self.effects):
            return
        self.effects[i], self.effects[i + d] = self.effects[i + d], self.effects[i]
        self.refresh(i + d)
        self._changed()

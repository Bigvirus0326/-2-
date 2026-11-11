"""'기믹' 탭의 Qt 版: 태그 · 소환수 · 구체 · 동료 (Tk 의 GimmickTab 과 같은 규칙).

아직 Qt 에서 못 하는 것: 블록 편집 (태그의 키워드 효과, 소환수·동료의 행동, 구체의 지속·발현 효과)과
'사용처 보기'. 블록이 있는 항목은 블록이 만든 설명을 읽기 전용으로 보여 준다.
"""
import blockcode
import gimmick as GM
import gimmickrules as GR
import pets as PT
import preview_qt as PQ
import projectio as IO
import qtkit as Q
from formqt import FieldsMixin, fill, label
from itemtabqt import all_ids

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QColorDialog, QComboBox, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QScrollArea,
                               QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

INT_RANGE = (-9999, 9999)
PET_CANVAS = (300, 260)
PET_BG = "#1c2a22"


def unique_gimmick_id(project, base):
    """Tk 의 GimmickTab._unique 와 같다: 겹치면 _B, _C ... 를 붙인다."""
    used = all_ids(project)
    if base not in used:
        return base
    i = 1
    while f"{base}_{GM.letters(i).lower()}" in used:
        i += 1
    return f"{base}_{GM.letters(i).lower()}"


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


def _info(parent, text):
    QMessageBox.information(parent, IO.APP_TITLE, text)


class _Panel(FieldsMixin, QWidget):
    """목록(왼쪽) + 편집 칸(오른쪽). 종류마다 key · kind · new_item · build_form 만 다르다."""
    key = ""          # gimmicks 안의 목록 이름
    kind = ""         # 참조를 고칠 때 쓰는 이름 (GR.rename_gimmick_ref)
    noun = ""
    prefix = "new"
    empty_note = ""

    def __init__(self, project, on_change=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.on_change = on_change
        self.cur = None
        self._loading = False
        self._fields = {}

        split = QSplitter(Qt.Orientation.Horizontal)
        root = QHBoxLayout(self)
        root.addWidget(split)

        left = QWidget()
        col = QVBoxLayout(left)
        head = QLabel(f"{self.noun} 목록")
        head.setStyleSheet("font-weight: bold;")
        col.addWidget(head)
        self.listing = QListWidget()
        self.listing.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.listing.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.listing.currentRowChanged.connect(self._row_changed)
        col.addWidget(self.listing, 1)
        bar = QHBoxLayout()
        for text, slot in (("＋ 새로 만들기", self.add), ("삭제", self.delete)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            bar.addWidget(button)
        col.addLayout(bar)
        split.addWidget(left)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        bcol = QVBoxLayout(body)
        self.title = QLabel(f"{self.noun} 편집")
        self.title.setStyleSheet("font-weight: bold; font-size: 14px;")
        bcol.addWidget(self.title)
        if self.empty_note:
            note = QLabel(self.empty_note)
            note.setWordWrap(True)
            note.setStyleSheet(f"color: {Q.C['muted']};")
            bcol.addWidget(note)
        self.form = QWidget()
        grid = QGridLayout(self.form)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.build_form(grid)
        bcol.addWidget(self.form)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        self.desc.setStyleSheet(f"color: {Q.C['secondary']};")
        bcol.addWidget(self.desc)
        bcol.addStretch(1)
        scroll.setWidget(body)
        split.addWidget(scroll)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 620])
        self.load_project(project)

    # ---- 칸 만들기 도우미 ----
    def _lang_row(self, g, row, text, key):
        """key 가 *_en 이면 같은 줄에 *_zh 칸을 하나 더 둔다 (Tk 의 lang_entry 와 같다)."""
        g.addWidget(label(text.replace("(영어)", "(영어 / 中文)") if key.endswith("_en") else text), row, 0)
        holder = QHBoxLayout()
        boxes = [QLineEdit()]
        if key.endswith("_en"):
            boxes.append(QLineEdit())
        for box in boxes:
            box.textChanged.connect(self._edited)
            holder.addWidget(box)
        g.addLayout(holder, row, 1, 1, 3)
        self._fields[key] = ("str", boxes[0])
        if len(boxes) > 1:
            self._fields[key[:-3] + "_zh"] = ("str", boxes[1])

    def _notice(self, g, row, text):
        g.addWidget(label(text), row, 0, 1, 4)

    def _block_button(self, text, slot):
        button = QPushButton(text)
        button.clicked.connect(lambda _=False: slot())
        return button

    def _edit_block_list(self, key, owner_kind, where, context=None, **extra):
        """항목의 블록 목록(key)을 블록 편집 창으로 고친다. context: 칸 이름 등을 찾는 데 쓰는 항목 (없으면 항목 자신)."""
        from blockqt import edit_blocks
        target = self.items[self.cur]
        result = edit_blocks(self, self.project, owner_kind, context if context is not None else target,
                             target.get(key) or [], where=where, **extra)
        if result is not None:
            target[key] = result["blocks"]
            self._notify()
            self._sync(target)

    # ---- 목록 ----
    @property
    def items(self):
        g = self.project.get("gimmicks")
        if not isinstance(g, dict) or any(k not in g for k in ("tags", "summons", "orbs", "effects", "buttons", "pets")):
            GM.normalize(self.project)
        return self.project["gimmicks"][self.key]

    def row_text(self, it):
        return f"{it.get('name_ko') or '?'}  ({it.get('id', '')})"

    def load_project(self, project):
        self.project = project
        self.cur = None
        self.refresh_list(0)

    def refresh_list(self, select=None):
        items = self.items
        self.listing.blockSignals(True)
        try:
            self.listing.clear()
            for i, it in enumerate(items):
                row = QListWidgetItem(self.row_text(it))
                row.setData(Qt.ItemDataRole.UserRole, i)
                self.listing.addItem(row)
        finally:
            self.listing.blockSignals(False)
        if not items:
            self.cur = None
            self.form.setEnabled(False)
            self.desc.setText("")
            return
        want = select if select is not None else (self.cur if self.cur is not None else 0)
        i = min(max(0, want), len(items) - 1)
        self.listing.blockSignals(True)
        self.listing.setCurrentRow(i)
        self.listing.blockSignals(False)
        self._load_item(i)

    def _row_changed(self, row):
        if row < 0:
            return
        idx = self.listing.item(row).data(Qt.ItemDataRole.UserRole)
        if idx != self.cur:
            self._load_item(idx)

    def _refresh_row(self):
        for r in range(self.listing.count()):
            row = self.listing.item(r)
            if row.data(Qt.ItemDataRole.UserRole) == self.cur:
                row.setText(self.row_text(self.items[self.cur]))
                return

    def _load_item(self, idx):
        self.cur = idx
        it = self.items[idx]
        self.title.setText(it.get("name_ko") or it.get("id") or self.noun + " 편집")
        self.form.setEnabled(True)
        self._loading = True
        try:
            self.load_extra(it)
            self.item_to_fields(it)
        finally:
            self._loading = False
        self._sync(it)

    def _sync(self, it):
        """설명 글과 칸의 사용 가능 여부를 맞춘다 (항목을 바꾼 뒤, 칸을 고친 뒤에 부른다)."""
        self.show_desc(it)

    def _edited(self, *_):
        if self._loading or self.cur is None:
            return
        it = self.items[self.cur]
        old_id = it.get("id")
        self.fields_to_item(it)
        self.dump_extra(it)
        if it.get("id") != old_id and it.get("id"):
            GR.rename_gimmick_ref(self.project, self.kind, old_id, it["id"])
        self._refresh_row()
        self._sync(it)
        self._notify()

    def _notify(self):
        if self.on_change:
            self.on_change()

    def add(self):
        self.items.append(self.new_item(unique_gimmick_id(self.project, self.prefix)))
        self._notify()
        self.refresh_list(len(self.items) - 1)

    def delete(self):
        if self.cur is None:
            return
        it = self.items[self.cur]
        if not _ask(self, f"{self.noun} '{it.get('name_ko') or it.get('id')}'을(를) 삭제할까요?"):
            return
        if self.kind == "tag":                 # Tk 와 같다: 태그를 지우면 카드에 붙은 태그도 빠진다
            GR.rename_gimmick_ref(self.project, "tag", it["id"], None)
        pos = self.cur
        del self.items[pos]
        self._notify()
        self.refresh_list(max(0, pos - 1))

    # ---- 종류별 훅 ----
    def build_form(self, g):
        raise NotImplementedError

    def new_item(self, iid):
        raise NotImplementedError

    def load_extra(self, it):
        pass

    def dump_extra(self, it):
        pass

    def show_desc(self, it):
        self.desc.setText("")


class TagPanel(_Panel):
    key, kind, noun, prefix = "tags", "tag", "태그", "new_tag"
    empty_note = "태그는 카드 키워드처럼 쓰입니다. 발동 블록은 발동 시점을 고른 뒤 블록 편집으로 만듭니다."

    def build_form(self, g):
        self._str(g, 0, 0, "ID (영문 소문자_)", "id")
        self._lang_row(g, 1, "이름 (한국어)", "name_ko")
        self._lang_row(g, 2, "이름 (영어)", "name_en")
        self._lang_row(g, 3, "툴팁 설명 (한국어)", "desc_ko")
        self._lang_row(g, 4, "툴팁 설명 (영어)", "desc_en")
        g.addWidget(self._check("show_in_text", "카드 설명 맨 앞에 태그 이름 표시 (예: '격투.')"), 5, 0, 1, 4)
        self.timing = QComboBox()
        fill(self.timing, GM.TAG_TIMINGS)
        self.timing.currentIndexChanged.connect(lambda _i: self._timing_changed())
        g.addWidget(label("발동 시점"), 6, 0)
        g.addWidget(self.timing, 6, 1)
        g.addWidget(self._block_button("🧩 블록 편집…", self.edit_tag_blocks), 6, 2, 1, 2)
        self._combo(g, 7, 0, "사용한 카드 조건", "played_filter", [("Any", "아무 카드나 사용")])
        self._int(g, 8, 0, "조건에 맞는 카드 (장마다)", "played_every")
        self._combo(g, 8, 2, "집계", "played_scope", [("turn", "이번 턴"), ("combat", "이번 전투")])
        self._notice(g, 9, "비용·피해량·방어도 지속 효과는 '더미에 있는 동안 지속 보정'을 선택해 블록으로 만드세요.")

    def new_item(self, iid):
        return GM.new_tag(iid)

    def load_extra(self, it):
        fill(self._box("played_filter"), GM.tag_play_filters(self.project))
        self._hand_controls()

    def _hand_controls(self):
        hand = self.timing.currentData() == "hand_play"
        for key in ("played_every", "played_scope", "played_filter"):
            self._box(key).setEnabled(hand)

    def edit_tag_blocks(self):
        """선택한 발동 시점의 블록을 고친다. 카드 샘플을 기준으로 편집한다 (Tk 의 edit_tag_blocks 와 같다)."""
        import copy
        import modgen as M
        from blockqt import edit_blocks
        if self.cur is None:
            return
        tag = self.items[self.cur]
        timing = self.timing.currentData() or "play"
        sample = copy.deepcopy(next(iter(self.project.get("cards", [])), M.new_card("keyword_sample")))
        sample["effects"] = []
        sample["clone"] = None
        result = edit_blocks(self, self.project, "card", sample, GM.tag_blocks(tag, timing),
                             where=f"'{tag.get('name_ko') or tag['id']}' · {dict(GM.TAG_TIMINGS)[timing]}",
                             show_text=False, card_event=None if timing == "play" else timing)
        if result is None:
            return
        if timing == "play":
            tag["blocks"] = result["blocks"]
        else:
            tag.setdefault("event_blocks", {})[timing] = result["blocks"]
        self._notify()
        self._sync(tag)
        self.show_desc(tag)

    def _timing_changed(self):
        self._hand_controls()
        if self.cur is not None:
            self.show_desc(self.items[self.cur])

    def show_desc(self, tag):
        timing = self.timing.currentData() or "play"
        text = GR.plain(blockcode.describe(GM.tag_blocks(tag, timing), self.project, "card", "ko"))
        lines = [dict(GM.TAG_TIMINGS)[timing] + ": " + (text or "설정한 효과 없음")]
        if timing == "hand_play":
            scope = "이번 턴" if tag.get("played_scope", "turn") == "turn" else "이번 전투"
            lines.append(f"손패에 있을 때 조건에 맞는 다른 카드 {tag.get('played_every', 1)}장마다 발동 · {scope}")
        elif timing == "hand_aura":
            lines.append("블록에서 선택한 더미를 떠나면 보정이 해제됩니다. 음수는 감소, 양수는 증가입니다.")
        elif timing.startswith("hand_"):
            lines.append("손패의 카드마다 턴당 한 번 발동합니다.")
        self.desc.setText("\n".join(lines))


class SummonPanel(_Panel):
    key, kind, noun, prefix = "summons", "summon", "소환수", "new_summon"

    def build_form(self, g):
        self.slots = QSpinBox()
        self.slots.setRange(1, 10)
        self.slots.valueChanged.connect(self._slots_changed)
        g.addWidget(label("소환 슬롯 수 (가득 차면 가장 먼저 온 소환수가 돌아갑니다)"), 0, 0, 1, 2)
        g.addWidget(self.slots, 0, 2)
        self._str(g, 1, 0, "ID (영문 소문자_)", "id")
        self._lang_row(g, 2, "이름 (한국어)", "name_ko")
        self._lang_row(g, 3, "이름 (영어)", "name_en")
        self._int(g, 4, 0, "최고 단계", "max_rank")
        self._combo(g, 4, 2, "행동", "timing", GM.SUMMON_TIMINGS)
        g.addWidget(self._check("act_on_max", "최고 단계에서 또 소환하면 즉시 행동"), 5, 0, 1, 4)
        self._image(g, 6)
        g.addWidget(self._block_button("🧩 행동 블록 편집…", self.edit_action_blocks), 7, 0, 1, 2)
        self._lang_row(g, 8, "설명 직접 (한국어)", "desc_ko")
        self._lang_row(g, 9, "설명 직접 (영어)", "desc_en")

    def new_item(self, iid):
        return GM.new_summon(iid)

    def edit_action_blocks(self):
        if self.cur is None:
            return
        x = self.items[self.cur]
        self._edit_block_list("blocks", "summon", f"소환수 '{x.get('name_ko')}'가 행동할 때",
                              context={"id": x["id"], "trigger": "none", "enemy_mode": "all"})

    def load_project(self, project):
        self.slots.blockSignals(True)
        self.slots.setValue(int(self._slots_value(project)))
        self.slots.blockSignals(False)
        super().load_project(project)

    @staticmethod
    def _slots_value(project):
        g = (project.get("gimmicks") or {})
        try:
            return int(g.get("summon_slots", 3))
        except (TypeError, ValueError):
            return 3

    def _slots_changed(self, value):
        if self._loading:
            return
        self.project["gimmicks"]["summon_slots"] = max(1, int(value))
        self._notify()

    def dump_extra(self, it):
        it["max_rank"] = max(1, int(it.get("max_rank", 1)))

    def show_desc(self, x):
        self.desc.setText("게임 설명: " + GR.plain(GM.summon_text(self.project, x, "ko")).replace("{Amount}", "N"))


class OrbPanel(_Panel):
    key, kind, noun, prefix = "orbs", "orb", "구체", "new_orb"

    def build_form(self, g):
        self._str(g, 0, 0, "ID (영문 소문자_)", "id")
        self._lang_row(g, 1, "이름 (한국어)", "name_ko")
        self._lang_row(g, 2, "이름 (영어)", "name_en")
        self._combo(g, 3, 0, "모양", "look", GM.ORB_LOOKS)
        tint_row = QHBoxLayout()
        self._str_tint = QLineEdit()
        self._str_tint.textChanged.connect(self._edited)
        self._fields["tint"] = ("str", self._str_tint)
        self.swatch = QLabel()
        self.swatch.setFixedSize(40, 20)
        pick = QPushButton("색 고르기…")
        pick.clicked.connect(self.pick_color)
        tint_row.addWidget(self._str_tint)
        tint_row.addWidget(self.swatch)
        tint_row.addWidget(pick)
        g.addWidget(label("색 (#ffffff = 원래 색)"), 3, 2)
        g.addLayout(tint_row, 3, 3)
        self._int(g, 4, 0, "지속 수치", "passive")
        self._int(g, 4, 2, "발현 수치", "evoke")
        self._combo(g, 5, 0, "지속 효과 시점", "timing", GM.ORB_TIMINGS)
        self._image(g, 6)
        g.addWidget(self._block_button("🧩 지속 효과 블록…", lambda: self.edit_orb_blocks("passive_blocks")), 7, 0, 1, 2)
        g.addWidget(self._block_button("🧩 발현 효과 블록…", lambda: self.edit_orb_blocks("evoke_blocks")), 7, 2, 1, 2)

    def new_item(self, iid):
        return GM.new_orb(iid)

    def edit_orb_blocks(self, key):
        if self.cur is None:
            return
        o = self.items[self.cur]
        where = f"구체 '{o.get('name_ko')}'의 " + ("지속 효과가 발동할 때" if key == "passive_blocks" else "발현될 때")
        self._edit_block_list(key, "orb", where)

    def pick_color(self):
        if self.cur is None:
            return
        start = QColor(self._str_tint.text().strip() or "#ffffff")
        chosen = QColorDialog.getColor(start, self, "구체 색 고르기")
        if chosen.isValid():
            self._str_tint.setText(chosen.name())

    def show_desc(self, o):
        color = o.get("tint") or "#ffffff"
        self.swatch.setStyleSheet(f"background: {color};")
        text = GM.orb_text(self.project, o, "ko").replace("[blue]{Passive}[/blue]", str(o.get("passive"))) \
            .replace("[blue]{Evoke}[/blue]", str(o.get("evoke")))
        self.desc.setText("게임 설명: " + GR.plain(text).replace("\n", "  /  "))


class PetPanel(_Panel):
    key, kind, noun, prefix = "pets", "pet", "동료", "new_pet"
    empty_note = "동료는 전장에 서 있는 체력 있는 소환수입니다. 행동 블록은 아래 버튼으로 편집합니다."

    def build_form(self, g):
        self._str(g, 0, 0, "ID (영문 소문자_)", "id")
        self._lang_row(g, 1, "이름 (한국어)", "name_ko")
        self._lang_row(g, 2, "이름 (영어)", "name_en")
        self._image(g, 3)
        self._int(g, 4, 0, "크기 %", "scale")
        self._int(g, 4, 2, "띄우기 (px)", "lift")
        self._check("flip", "좌우 반전")
        self._check("guard", "주인을 노린 공격을 대신 받음 (골골이처럼)")
        g.addWidget(self._box_row(self._fields["flip"][1], self._fields["guard"][1]), 5, 0, 1, 4)
        self._combo(g, 6, 0, "행동", "timing", PT.PET_TIMINGS)
        g.addWidget(self._block_button("🧩 행동 블록 편집…", self.edit_action_blocks), 7, 0, 1, 2)
        self.canvas = QLabel()
        self.canvas.setFixedSize(*PET_CANVAS)
        self.canvas.setStyleSheet(f"background: {PET_BG};")
        g.addWidget(self.canvas, 8, 0, 1, 4)

    @staticmethod
    def _box_row(*boxes):
        holder = QWidget()
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        for box in boxes:
            row.addWidget(box)
        row.addStretch(1)
        return holder

    def edit_action_blocks(self):
        if self.cur is None:
            return
        p = self.items[self.cur]
        self._edit_block_list("blocks", "pet", f"동료 '{p.get('name_ko')}'가 행동할 때",
                              context={"id": p["id"], "trigger": "none", "enemy_mode": "all"})

    def new_item(self, iid):
        p = PT.new_pet(iid)
        for b in p["blocks"]:
            b["args"]["pet"] = p["id"]
        return p

    def show_desc(self, p):
        self.desc.setText("게임 설명: " + GR.plain(PT.pet_text(self.project, p, "ko")))
        self._draw(p)

    def _draw(self, p):
        w, h = PET_CANVAS
        image = QImage(w, h, QImage.Format.Format_ARGB32)
        image.fill(QColor(PET_BG))
        painter = QPainter(image)
        try:
            try:
                im = PT.process_image(p.get("image"), p.get("scale"), p.get("flip"), p.get("lift")) \
                    if p.get("image") else PT.placeholder()
            except (OSError, ValueError):
                im = PT.placeholder()
            k = 0.5                                  # 게임 1px = 미리보기 0.5px (Tk 와 같다)
            im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
            pixmap = PQ._qpixmap(im)
            painter.drawPixmap(int(w / 2 - im.width / 2), int(h - 30 - im.height), pixmap)
        finally:
            painter.end()
        self.canvas.setPixmap(QPixmap.fromImage(image))


class GimmickQt(QWidget):
    """기믹 탭: 태그 · 소환수 · 구체 · 동료 (네 개의 하위 탭)."""

    def __init__(self, project, on_change=None, on_reload=None, parent=None):
        super().__init__(parent)
        self.project = project
        self.on_change = on_change
        self.on_reload = on_reload
        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        examples = QPushButton("예시 기믹 추가…")
        examples.clicked.connect(self.add_examples)
        examples.setToolTip("태그·자원·소환수·날씨·선택지와 그것을 쓰는 카드를 예시로 추가합니다 (기존 항목은 그대로 둡니다).")
        bar.addWidget(examples)
        bar.addStretch(1)
        root.addLayout(bar)
        self.tabs = QTabWidget()
        self.panels = {
            "tags": TagPanel(project, on_change), "summons": SummonPanel(project, on_change),
            "orbs": OrbPanel(project, on_change), "pets": PetPanel(project, on_change),
        }
        for key, title in (("tags", "태그"), ("summons", "소환수"), ("orbs", "구체"), ("pets", "동료")):
            self.tabs.addTab(self.panels[key], title)
        root.addWidget(self.tabs, 1)

    def load_project(self, project):
        self.project = project
        for panel in self.panels.values():
            panel.load_project(project)

    def add_examples(self):
        if not _ask(self, "현재 프로젝트에 예시 기믹을 추가할까요?\n기존 항목은 그대로 두고 새로 추가만 합니다."):
            return
        added = GM.add_examples(self.project)
        if self.on_change:
            self.on_change()
        if self.on_reload:
            self.on_reload()
        _info(self, "추가했습니다:\n\n• " + "\n• ".join(added))

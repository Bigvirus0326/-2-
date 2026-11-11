"""'캐릭터' 탭의 Qt 版: 내 캐릭터 편집 (이름·소개·색·체력·시작 덱·시작 유물·그림·미리보기).

아직 옮기지 않은 것: 가져온 캐릭터 고르기, 전투 모습·모션(움직이는 그림), 아키텍트 대사 편집,
카드 테두리 편집기 (지금은 Tk 앱에서 편집). 이 항목들은 Tk 앱에서 그대로 쓸 수 있다.
"""
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPixmap
from PySide6.QtWidgets import (QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
                               QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QAbstractItemView, QPushButton, QRadioButton, QScrollArea, QSpinBox,
                               QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QButtonGroup)

import cardframe as CF
import modgen as M
import preview_qt as PQ
import qtkit as Q

LANGS = [("ko", "한국어"), ("en", "영어"), ("zh", "중국어 간체")]
ART_FIELDS = [
    ("energy_icon_image", "카드 에너지 구슬", "74×74 (비우면 임시 외형 캐릭터 것)"),
    ("energy_text_icon_image", "설명용 에너지 아이콘", "24×24"),
    ("icon_image", "아이콘", "88×88"),
    ("select_image", "선택 화면 초상화", "132×195"),
    ("select_locked_image", "선택 화면 (잠김)", "132×195"),
    ("map_marker_image", "지도 표시", "49×64"),
    ("select_bg_image", "선택 화면 전체 배경", "1920×1080 (캐릭터를 고르면 화면 전체를 채움)"),
]


def _set_combo(combo, value):
    index = combo.findData(value)
    combo.setCurrentIndex(index if index >= 0 else 0)


class CharacterPanelQt(QWidget):
    def __init__(self, project, on_change=None, ui=1.0, parent=None):
        super().__init__(parent)
        self.project = project
        self.on_change = on_change
        self.ui = ui
        self._loading = False
        self._fields = {}

        root = QHBoxLayout(self)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        body = QWidget()
        scroll.setWidget(body)
        form = QVBoxLayout(body)
        root.addWidget(scroll, 1)

        self.enabled = QCheckBox("새 캐릭터 만들기  (끄면 카드는 무색, 유물/물약은 공용 풀에 추가됩니다)")
        self.enabled.toggled.connect(self.changed)
        form.addWidget(self.enabled)

        basics = QGridLayout()
        self._text(basics, 0, 0, "캐릭터 ID (영문 소문자_)", "id")
        self._text(basics, 0, 2, "시작 체력", "hp")
        form.addLayout(basics)

        names = QGridLayout()
        for row, (lang, label) in enumerate(LANGS):
            self._text(names, row, 0, f"이름 ({label})", f"name_{lang}")
            self._text(names, row, 2, f"소개 ({label})", f"desc_{lang}")
        form.addLayout(names)

        look = QGridLayout()
        look.addWidget(QLabel("대표 색상"), 0, 0)
        color = QLineEdit()
        color.textChanged.connect(lambda _t: self.changed())
        look.addWidget(color, 0, 1)
        self._fields["color"] = color
        self.swatch = QLabel()
        self.swatch.setFixedSize(40, 20)
        look.addWidget(self.swatch, 0, 2)
        pick = QPushButton("고르기…")
        pick.clicked.connect(self.pick_color)
        look.addWidget(pick, 0, 3)
        look.addWidget(QLabel("임시 외형 (애니메이션)"), 1, 0)
        self.placeholder = QComboBox()
        for value, label in M.PLACEHOLDER_CHARS:
            self.placeholder.addItem(label, value)
        self.placeholder.currentIndexChanged.connect(lambda _i: self.changed())
        look.addWidget(self.placeholder, 1, 1)
        look.addWidget(QLabel("카드 테두리"), 1, 2)
        self.frame_combo = QComboBox()
        self.frame_combo.currentIndexChanged.connect(lambda _i: self.changed())
        look.addWidget(self.frame_combo, 1, 3)
        form.addLayout(look)

        hsv = QHBoxLayout()
        hsv.addWidget(QLabel("카드 뒷면 HSV (0~1)"))
        for key, label in (("card_h", "H"), ("card_s", "S"), ("card_v", "V")):
            hsv.addWidget(QLabel(label))
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1.0)
            spin.setSingleStep(0.05)
            spin.setDecimals(2)
            spin.valueChanged.connect(lambda _v: self.changed())
            hsv.addWidget(spin)
            self._fields[key] = spin
        hsv.addWidget(QLabel("1 / 1 / 1 이 기본"))
        hsv.addStretch(1)
        form.addLayout(hsv)

        counts = QHBoxLayout()
        counts.addWidget(QLabel("구체 슬롯 수"))
        self.orb_slots = QSpinBox()
        self.orb_slots.setRange(0, 10)
        self.orb_slots.valueChanged.connect(lambda _v: self.changed())
        counts.addWidget(self.orb_slots)
        self.show_stars = QCheckBox("별 카운터 항상 표시 (리젠트처럼 별을 쓰는 캐릭터)")
        self.show_stars.toggled.connect(self.changed)
        counts.addWidget(self.show_stars)
        counts.addStretch(1)
        form.addLayout(counts)

        form.addWidget(self._deck_box())
        form.addWidget(self._relic_box())
        form.addWidget(self._art_box())
        form.addStretch(1)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {Q.C['danger']};")
        form.addWidget(self.status)

        side = QVBoxLayout()
        top = QHBoxLayout()
        top.addWidget(QLabel("미리보기"))
        self._lang_group = QButtonGroup(self)
        for i, (value, label) in enumerate(LANGS):
            button = QRadioButton(label)
            button.setChecked(value == "ko")
            button.toggled.connect(lambda on, v=value: on and self.set_preview_lang(v))
            self._lang_group.addButton(button, i)
            top.addWidget(button)
        side.addLayout(top)
        self.preview_lang = "ko"
        self.preview = QLabel()
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        side.addWidget(self.preview)
        side.addStretch(1)
        root.addLayout(side)

        self.load(project)

    # ---- 칸 만들기 ----
    def _text(self, grid, row, col, label, key):
        if label:
            grid.addWidget(QLabel(label), row, col)
        edit = QLineEdit()
        edit.textChanged.connect(lambda _t: self.changed())
        grid.addWidget(edit, row, col + 1)
        self._fields[key] = edit
        return edit

    def _deck_box(self):
        box = QGroupBox("시작 덱")
        layout = QVBoxLayout(box)
        self.deck_table = QTableWidget(0, 2)
        self.deck_table.setHorizontalHeaderLabels(["카드", "장수"])
        self.deck_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.deck_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.deck_table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.deck_table)
        row = QHBoxLayout()
        self.deck_card = QComboBox()
        self.deck_card.setMinimumWidth(260)
        self.deck_count = QSpinBox()
        self.deck_count.setRange(1, 20)
        add = QPushButton("추가 / 장수 변경")
        add.clicked.connect(self.deck_add)
        remove = QPushButton("선택 삭제")
        remove.clicked.connect(self.deck_remove)
        self.deck_total = QLabel("")
        for w in (self.deck_card, self.deck_count, add, remove, self.deck_total):
            row.addWidget(w)
        layout.addLayout(row)
        return box

    def _relic_box(self):
        box = QGroupBox("시작 유물")
        layout = QVBoxLayout(box)
        row = QHBoxLayout()
        self.relic_combo = QComboBox()
        self.relic_combo.setMinimumWidth(320)
        add = QPushButton("유물 추가")
        add.clicked.connect(self.relic_add)
        row.addWidget(self.relic_combo, 1)
        row.addWidget(add)
        layout.addLayout(row)
        self.relic_list = QListWidget()
        self.relic_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        layout.addWidget(self.relic_list)
        remove = QPushButton("선택 삭제")
        remove.clicked.connect(self.relic_remove)
        layout.addWidget(remove)
        layout.addWidget(QLabel("시작 시 지급할 유물을 고르세요. 여러 개를 추가할 수 있습니다. (희귀도 '시작' 권장)"))
        return box

    def _art_box(self):
        box = QGroupBox("캐릭터 그림 (선택 사항, 비우면 임시 외형 캐릭터의 그림을 씀)")
        grid = QGridLayout(box)
        for row, (key, label, hint) in enumerate(ART_FIELDS):
            grid.addWidget(QLabel(label), row, 0)
            edit = QLineEdit()
            edit.textChanged.connect(lambda _t: self.changed())
            grid.addWidget(edit, row, 1)
            browse = QPushButton("찾기…")
            browse.clicked.connect(lambda _=False, e=edit: self._browse(e))
            grid.addWidget(browse, row, 2)
            grid.addWidget(QLabel(hint), row, 3)
            self._fields[key] = edit
        return box

    # ---- 읽기 · 쓰기 ----
    def ch(self):
        return self.project["character"]

    def load(self, project):
        """프로젝트를 바꿔 끼운다(열기·되돌리기). 칸을 다시 채우되 바뀐 것으로 치지 않는다."""
        self.project = project
        ch = self.ch()
        self._loading = True
        try:
            self.enabled.setChecked(bool(ch.get("enabled")))
            for key, widget in self._fields.items():
                if isinstance(widget, QDoubleSpinBox):
                    widget.setValue(float(ch.get(key, 1.0)))
                elif isinstance(widget, QLineEdit):
                    widget.setText(str(ch.get(key, "")))
            _set_combo(self.placeholder, ch.get("placeholder", "ironclad"))
            self.frame_combo.clear()
            for value, label in CF.options(self.project, for_card=False):
                self.frame_combo.addItem(label, value)
            _set_combo(self.frame_combo, ch.get("frame_style", ""))
            self.orb_slots.setValue(int(ch.get("orb_slots", 0) or 0))
            self.show_stars.setChecked(bool(ch.get("show_stars")))
            self._refresh_deck_and_relic_choices()
            self.refresh_deck()
            self.refresh_relics()
        finally:
            self._loading = False
        self.update_swatch()
        self.update_preview()

    def changed(self, *_):
        if self._loading:
            return
        ch = self.ch()
        ch["enabled"] = self.enabled.isChecked()
        for key, widget in self._fields.items():
            if isinstance(widget, QDoubleSpinBox):
                ch[key] = float(widget.value())
                continue
            val = widget.text().strip()
            if key == "hp":
                try:
                    ch[key] = int(val)
                except ValueError:
                    pass
            elif key.endswith("_image"):
                ch[key] = val.strip('"')
            else:
                ch[key] = val
        ch["placeholder"] = self.placeholder.currentData()
        ch["frame_style"] = self.frame_combo.currentData()
        ch["orb_slots"] = int(self.orb_slots.value())
        ch["show_stars"] = bool(self.show_stars.isChecked())
        self.update_swatch()
        self.update_preview()
        if self.on_change:
            self.on_change()

    def _notify(self):
        if self.on_change:
            self.on_change()

    # ---- 색 · 그림 ----
    def update_swatch(self):
        c = self._fields["color"].text().strip()
        color = c if M.HEX_RE.match(c) and c.startswith("#") else "#" + c.lstrip("#")
        self.swatch.setStyleSheet(f"background: {color if M.HEX_RE.match(color) else '#888888'};")

    def pick_color(self):
        current = self._fields["color"].text().strip()
        start = QColor(current if M.HEX_RE.match(current) else "#ffffff")
        chosen = QColorDialog.getColor(start, self, "대표 색상 고르기")
        if chosen.isValid():
            self._fields["color"].setText(chosen.name())

    def _browse(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "그림 고르기", "", "PNG 이미지 (*.png);;모든 파일 (*.*)")
        if path:
            edit.setText(os.path.normpath(path))

    # ---- 덱 · 유물 ----
    def _card_choices(self):
        cards = list(self.project["cards"])
        cards.extend({"id": "game:" + entry, "name_ko": label + " · 원작"}
                     for entry, label in self.ch().get("game_cards", {}).items())
        return cards

    def _refresh_deck_and_relic_choices(self):
        self.deck_card.clear()
        for c in self._card_choices():
            self.deck_card.addItem(f"{c.get('name_ko') or c['id']} ({c['id']})", c["id"])
        self.relic_combo.clear()
        for r in self.project["relics"]:
            self.relic_combo.addItem(
                f"{r.get('name_ko') or r['id']} ({r['id']}) - {M.label_of(M.RELIC_RARITIES, r['rarity'])}", r["id"])
        for key, label in self.ch().get("game_relics", {}).items():
            self.relic_combo.addItem(label + " · 원작", "game:" + key)

    def refresh_deck(self):
        names = {c["id"]: c.get("name_ko") or c["id"] for c in self._card_choices()}
        deck = self.ch().get("deck", [])
        self.deck_table.setRowCount(0)
        total = 0
        for d in deck:
            row = self.deck_table.rowCount()
            self.deck_table.insertRow(row)
            if d["card"].startswith("raw:"):
                label = f"원래 코드: {d['card'][4:].split('.')[-1]}"
            else:
                label = f"{names.get(d['card'], '⚠ 없음')} ({d['card']})"
            self.deck_table.setItem(row, 0, QTableWidgetItem(label))
            self.deck_table.setItem(row, 1, QTableWidgetItem(str(d["count"])))
            total += int(d["count"])
        self.deck_total.setText(f"총 {total}장")

    def deck_add(self):
        cid = self.deck_card.currentData()
        if not cid:
            return
        n = max(1, int(self.deck_count.value()))
        deck = self.ch().setdefault("deck", [])
        for d in deck:
            if d["card"] == cid:
                d["count"] = n
                break
        else:
            deck.append({"card": cid, "count": n})
        self.refresh_deck()
        self._notify()

    def deck_remove(self):
        row = self.deck_table.currentRow()
        if row < 0:
            return
        del self.ch()["deck"][row]
        self.refresh_deck()
        self._notify()

    def refresh_relics(self):
        relics = {r["id"]: r for r in self.project["relics"]}
        self.relic_list.clear()
        for relic_id in self.ch().get("relics", []):
            relic = relics.get(relic_id)
            if relic is None:
                if relic_id.startswith("raw:"):
                    label = f"원래 코드: {relic_id[4:].split('.')[-1]}"
                elif relic_id.startswith("game:"):
                    label = self.ch().get("game_relics", {}).get(relic_id[5:], f"⚠ 없음 ({relic_id})")
                else:
                    label = f"⚠ 없음 ({relic_id})"
            else:
                label = f"{relic.get('name_ko') or relic_id} ({relic_id})"
            self.relic_list.addItem(label)

    def relic_add(self):
        relic_id = self.relic_combo.currentData()
        if not relic_id:
            return
        ids = self.ch().setdefault("relics", [])
        if relic_id not in ids:
            ids.append(relic_id)
            self.refresh_relics()
            self._notify()

    def relic_remove(self):
        selected = {self.relic_list.row(item) for item in self.relic_list.selectedItems()}
        if not selected:
            return
        self.ch()["relics"] = [r for i, r in enumerate(self.ch().get("relics", [])) if i not in selected]
        self.refresh_relics()
        self._notify()

    # ---- 미리보기 ----
    def set_preview_lang(self, lang):
        self.preview_lang = lang
        self.update_preview()

    def update_preview(self):
        u = self.ui
        width, height = int(310 * u), int(570 * u)
        image = QImage(width, height, QImage.Format.Format_ARGB32)
        image.fill(QColor("#121318"))
        painter = QPainter(image)
        try:
            PQ.render_character(painter, self.project, 5 * u, 5 * u, self.preview_lang, u)
        except Exception as e:  # noqa: BLE001
            painter.setPen(QColor("#ff6666"))
            painter.drawText(image.rect(), int(Qt.AlignmentFlag.AlignCenter), f"미리보기 오류:\n{e}")
        painter.end()
        self.preview.setPixmap(QPixmap.fromImage(image))

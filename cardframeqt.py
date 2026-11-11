"""카드 테두리 디자인 편집 창 (Qt 版): 스타일 목록 + 부위별(틀·그림 테두리·제목 띠) 설정 + 미리보기 3장.

Tk 의 FrameStyleDialog 와 같은 규칙을 쓴다. 계산(색 → 셰이더 H S V, 그림 고르기, 원본 틀 내보내기)은 cardframe.py ·
ingame.py 가 한다.
"""
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QImage, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QColorDialog, QDialog, QDoubleSpinBox, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QRadioButton, QScrollArea, QVBoxLayout, QWidget, QCheckBox, QComboBox, QGridLayout,
                               QButtonGroup)

import cardframe as CF
import ingame
import preview_qt as PQ
import projectio as IO
import qtkit as Q

TITLE = "카드 테두리 디자인"
KEY_LABEL = {"all": "공통", "Attack": "공격", "Skill": "스킬", "Power": "파워"}
SAMPLE = {"Attack": ("타격", "피해를 6 줍니다."), "Skill": ("수비", "방어도를 5 얻습니다."),
          "Power": ("각성", "힘을 2 얻습니다.")}
RARITIES = [("Common", "일반"), ("Uncommon", "특별"), ("Rare", "희귀")]
PREVIEW_DELAY_MS = 200


def _ask(parent, text):
    return QMessageBox.question(parent, TITLE, text) == QMessageBox.StandardButton.Yes


class FrameStyleDialogQt(QDialog):
    def __init__(self, parent, project, assets_fn, select=None, on_change=None):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.project = project
        self.assets_fn = assets_fn
        self.on_change = on_change
        self.cur = None
        self._loading = False
        self.ui = {}
        assets = self._assets()
        self._base = {part: (CF.base_rgb_from(assets, part) if assets is not None else CF.BASE_RGB[part])
                      for part in CF.PARTS}
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(PREVIEW_DELAY_MS)
        self._timer.timeout.connect(self.draw)

        root = QHBoxLayout(self)
        # ---- 왼쪽: 스타일 목록 ----
        left = QVBoxLayout()
        head = QLabel("테두리 디자인")
        head.setStyleSheet("font-weight: bold;")
        left.addWidget(head)
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lst.currentRowChanged.connect(self._select)
        left.addWidget(self.lst, 1)
        bar = QHBoxLayout()
        for text, slot in (("＋ 새로", self.add), ("복제", self.duplicate), ("삭제", self.delete)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            bar.addWidget(button)
        left.addLayout(bar)
        example = QPushButton("예시 추가 (청동빛)")
        example.clicked.connect(self.add_example)
        left.addWidget(example)
        export = QPushButton("게임 원본 틀 PNG로 저장…")
        export.clicked.connect(self.export)
        left.addWidget(export)
        note = QLabel("원본 틀·테두리·띠를 꺼내 그 위에 그려 '내 그림'으로 쓰면 크기가 딱 맞습니다.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Q.C['muted']};")
        left.addWidget(note)
        root.addLayout(left)

        # ---- 가운데: 설정 ----
        mid_scroll = QScrollArea()
        mid_scroll.setWidgetResizable(True)
        mid_scroll.setFrameShape(mid_scroll.Shape.NoFrame)
        mid_scroll.setMinimumWidth(520)
        mid_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)   # 색 줄이 길면 가로로 민다
        mid_body = QWidget()
        mid = QVBoxLayout(mid_body)
        names = QGridLayout()
        self.name = QLineEdit()
        self.sid = QLineEdit()
        self.name.textChanged.connect(self.changed)
        self.sid.textChanged.connect(self.changed)
        names.addWidget(QLabel("이름"), 0, 0)
        names.addWidget(self.name, 0, 1)
        names.addWidget(QLabel("ID"), 0, 2)
        names.addWidget(self.sid, 0, 3)
        mid.addLayout(names)
        for part in CF.PARTS:
            mid.addWidget(self._part_box(part))
        self.plaque = QCheckBox("종류 명패(공격·스킬·파워)도 제목 띠 색으로 (제목 띠가 '색 바꾸기'일 때)")
        self.plaque.setChecked(True)
        self.plaque.toggled.connect(lambda _c: self.changed())
        mid.addWidget(self.plaque)
        self.warn = QLabel("")
        self.warn.setWordWrap(True)
        self.warn.setStyleSheet(f"color: {Q.C['accent']};")
        mid.addWidget(self.warn)
        mid.addStretch(1)
        mid_scroll.setWidget(mid_body)
        root.addWidget(mid_scroll, 1)

        # ---- 오른쪽: 미리보기 ----
        right = QVBoxLayout()
        top = QHBoxLayout()
        pv_head = QLabel("미리보기")
        pv_head.setStyleSheet("font-weight: bold;")
        top.addWidget(pv_head)
        top.addStretch(1)
        top.addWidget(QLabel("희귀도"))
        self.rarity = QComboBox()
        for value, text in RARITIES:
            self.rarity.addItem(text, value)
        self.rarity.currentIndexChanged.connect(lambda _i: self.schedule())
        top.addWidget(self.rarity)
        right.addLayout(top)
        previews = QHBoxLayout()
        self.preview_labels = []
        for _ in CF.TYPES:
            label = QLabel()
            label.setMinimumSize(120, 200)
            label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignHCenter)
            previews.addWidget(label)
            self.preview_labels.append(label)
        right.addLayout(previews)
        right.addWidget(QLabel("게임과 같은 계산(색 = 게임 hsv 셰이더, 그림 = 그대로)으로 그립니다."))
        right.addStretch(1)
        root.addLayout(right)

        footer = QVBoxLayout()
        footer.addWidget(QLabel("쓰는 곳: 캐릭터 탭 '카드 테두리'(모든 카드 기본) · 카드 탭 '테두리 디자인'(카드마다)"))
        close = QPushButton("닫기")
        close.clicked.connect(self.close_dialog)
        footer.addWidget(close, 0, Qt.AlignmentFlag.AlignRight)
        root.addLayout(footer)
        self.resize(1320, 760)
        self.refresh_list(select)

    def _assets(self):
        try:
            return self.assets_fn() if self.assets_fn else None
        except Exception:  # noqa: BLE001 - 게임 파일이 없으면 기본 색으로 그린다
            return None

    # ---- 부위 설정 상자 ----
    def _part_box(self, part):
        from PySide6.QtWidgets import QGroupBox
        box = QGroupBox(f"{CF.PART_LABEL[part]}  (권장 {CF.SIZES[part][0]}×{CF.SIZES[part][1]})")
        col = QVBoxLayout(box)
        w = {"radios": {}, "group": QButtonGroup(box)}
        modes = QHBoxLayout()
        for i, (val, text) in enumerate(CF.MODES[part]):
            button = QRadioButton(text)
            button.toggled.connect(lambda on, p=part: on and (self._mode_ui(p), self.changed()))
            w["group"].addButton(button, i)
            w["radios"][val] = button
            modes.addWidget(button)
        modes.addStretch(1)
        col.addLayout(modes)
        # 색
        color_frame = QWidget()
        cf = QHBoxLayout(color_frame)
        cf.setContentsMargins(0, 0, 0, 0)
        w["swatch"] = QLabel()
        w["swatch"].setFixedSize(40, 20)
        cf.addWidget(w["swatch"])
        pick = QPushButton("색 고르기…")
        pick.clicked.connect(lambda _=False, p=part: self.pick_color(p))
        cf.addWidget(pick)
        w["color"] = QLineEdit()
        w["color"].setMaximumWidth(110)
        w["color"].textChanged.connect(lambda _t, p=part: self.color_typed(p))
        cf.addWidget(w["color"])
        cf.addWidget(QLabel("셰이더 H S V"))
        w["hsv"] = []
        for i, (lo, hi) in enumerate(((0, 1), (0, 5), (0, 5))):
            spin = QDoubleSpinBox()
            spin.setRange(lo, hi)
            spin.setDecimals(4)
            spin.setSingleStep(0.01 if i == 0 else 0.05)
            spin.valueChanged.connect(lambda _v: self.changed())
            cf.addWidget(spin)
            w["hsv"].append(spin)
        cf.addStretch(1)
        col.addWidget(color_frame)
        # 그림
        image_frame = QWidget()
        imf = QGridLayout(image_frame)
        imf.setContentsMargins(0, 0, 0, 0)
        w["images"] = {}
        for r, key in enumerate(CF.IMAGE_KEYS[part]):
            imf.addWidget(QLabel(KEY_LABEL[key] + (" (비우면 공통)" if key != "all" else "")), r, 0)
            edit = QLineEdit()
            edit.textChanged.connect(lambda _t: self.changed())
            imf.addWidget(edit, r, 1)
            browse = QPushButton("찾기…")
            browse.clicked.connect(lambda _=False, e=edit: self.browse(e))
            imf.addWidget(browse, r, 2)
            clear = QPushButton("지우기")
            clear.clicked.connect(lambda _=False, e=edit: e.setText(""))
            imf.addWidget(clear, r, 3)
            w["images"][key] = edit
        col.addWidget(image_frame)
        w["color_frame"] = color_frame
        w["image_frame"] = image_frame
        self.ui[part] = w
        self._mode_ui(part)
        return box

    def _mode(self, part):
        for val, button in self.ui[part]["radios"].items():
            if button.isChecked():
                return val
        return "game"

    def _set_mode(self, part, value):
        button = self.ui[part]["radios"].get(value)
        if button is not None:
            button.setChecked(True)

    def _mode_ui(self, part):
        w = self.ui[part]
        m = self._mode(part)
        w["color_frame"].setVisible(m == "color")
        w["image_frame"].setVisible(m == "image")

    # ---- 목록 ----
    @property
    def styles(self):
        return CF.styles(self.project)

    def refresh_list(self, select=None):
        styles = self.styles
        self.lst.blockSignals(True)
        self.lst.clear()
        for s in styles:
            self.lst.addItem(f"▣ {s.get('name') or s['id']}  ({s['id']})")
        self.lst.blockSignals(False)
        if styles:
            idx = next((i for i, s in enumerate(styles) if s["id"] == select), None)
            if idx is None:
                idx = min(self.cur or 0, len(styles) - 1)
            self.lst.setCurrentRow(idx)
            self.load(idx)
        else:
            self.cur = None
            self._enable(False)
            self.draw()

    def _enable(self, on):
        for part in CF.PARTS:
            for button in self.ui[part]["radios"].values():
                button.setEnabled(on)
            self.ui[part]["color_frame"].setEnabled(on)
            self.ui[part]["image_frame"].setEnabled(on)
        self.name.setEnabled(on)
        self.sid.setEnabled(on)
        self.plaque.setEnabled(on)

    def _select(self, row):
        if row >= 0:
            self.load(row)

    def _unique(self, base):
        used = {s["id"] for s in self.styles}
        if base not in used:
            return base
        i = 0
        while True:
            cand = f"{base}_{'abcdefghijklmnopqrstuvwxyz'[i % 26] * (1 + i // 26)}"
            if cand not in used:
                return cand
            i += 1

    def _notify(self):
        if self.on_change:
            self.on_change()

    def add(self):
        st = CF.new_style(self._unique("frame"), "새 테두리")
        st["frame"].update(mode="color", color="#3a6fb0", hsv=CF.hsv_for("#3a6fb0", "frame", self._base["frame"]))
        self.styles.append(st)
        self._notify()
        self.refresh_list(st["id"])

    def add_example(self):
        st = CF.new_style(self._unique("bronze"), "청동빛 테두리")
        st["frame"].update(mode="color", color="#8c6420", hsv=CF.hsv_for("#8c6420", "frame", self._base["frame"]))
        st["banner"].update(mode="color", color="#9c2a32", hsv=CF.hsv_for("#9c2a32", "banner", self._base["banner"]))
        self.styles.append(st)
        self._notify()
        self.refresh_list(st["id"])

    def duplicate(self):
        if self.cur is None:
            return
        st = CF.clone_style(self.styles[self.cur], self._unique(self.styles[self.cur]["id"]))
        self.styles.insert(self.cur + 1, st)
        self._notify()
        self.refresh_list(st["id"])

    def delete(self):
        if self.cur is None:
            return
        st = self.styles[self.cur]
        if not _ask(self, f"'{st.get('name') or st['id']}' 테두리를 지울까요?\n"
                          "이 테두리를 쓰던 카드는 게임 원래 테두리로 돌아갑니다."):
            return
        CF.rename(self.project, st["id"], None)
        del self.styles[self.cur]
        self._notify()
        self.refresh_list()

    # ---- 불러오기 · 바꾸기 ----
    def load(self, idx):
        self.cur = idx
        st = self.styles[idx]
        self._enable(True)
        self._loading = True
        try:
            self.name.setText(st.get("name", ""))
            self.sid.setText(st["id"])
            self.plaque.setChecked(bool(st.get("plaque_follows", True)))
            for part in CF.PARTS:
                w, p = self.ui[part], st[part]
                self._set_mode(part, p.get("mode", "game"))
                w["color"].setText(p.get("color", ""))
                for spin, x in zip(w["hsv"], p.get("hsv", [1, 1, 1])):
                    spin.setValue(float(x))
                for key, edit in w["images"].items():
                    edit.setText((p.get("images") or {}).get(key, ""))
                self._mode_ui(part)
                self._swatch(part)
        finally:
            self._loading = False
        self._warn()
        self.draw()

    def changed(self, *_):
        if self._loading or self.cur is None:
            return
        st = self.styles[self.cur]
        old = st["id"]
        st["name"] = self.name.text().strip()
        new = self.sid.text().strip()
        if new and new != old:
            st["id"] = new
            CF.rename(self.project, old, new)
        st["plaque_follows"] = bool(self.plaque.isChecked())
        for part in CF.PARTS:
            w, p = self.ui[part], st[part]
            p["mode"] = self._mode(part)
            p["color"] = w["color"].text().strip()
            p["hsv"] = [float(spin.value()) for spin in w["hsv"]]
            p["images"] = {k: edit.text().strip().strip('"') for k, edit in w["images"].items()}
        self.refresh_row()
        self._warn()
        self._notify()
        self.schedule()

    def refresh_row(self):
        st = self.styles[self.cur]
        item = self.lst.item(self.cur)
        if item is not None:
            item.setText(f"▣ {st.get('name') or st['id']}  ({st['id']})")

    # ---- 색 ----
    def _swatch(self, part):
        col = self.ui[part]["color"].text().strip()
        ok = col.startswith("#") and len(col) == 7
        self.ui[part]["swatch"].setStyleSheet(f"background: {col if ok else Q.C['muted']};")

    def pick_color(self, part):
        w = self.ui[part]
        chosen = QColorDialog.getColor(QColor(w["color"].text() or "#888888"), self, f"{CF.PART_LABEL[part]} 색")
        if chosen.isValid():
            w["color"].setText(chosen.name())

    def color_typed(self, part):
        """색을 정하면 게임 셰이더 H S V 를 계산해 채운다 (Tk 와 같다)."""
        if self._loading:
            return
        col = self.ui[part]["color"].text().strip()
        self._swatch(part)
        if len(col) == 7 and col.startswith("#"):
            h, s, v = CF.hsv_for(col, part, self._base[part])
            self._loading = True
            try:
                for spin, x in zip(self.ui[part]["hsv"], (h, s, v)):
                    spin.setValue(float(x))
            finally:
                self._loading = False
        self.changed()

    def _warn(self):
        if self.cur is None:
            self.warn.setText("")
            return
        st = self.styles[self.cur]
        msgs = []
        fr = st["frame"]
        if fr.get("mode") == "color" and float((fr.get("hsv") or [1, 1, 1])[2]) > 1.8:
            msgs.append("⚠ 카드 틀 색이 밝아 설명 칸도 밝아집니다 (게임에서도 같음). 글자가 잘 보이게 조금 어두운 색을 권합니다.")
        for part in CF.PARTS:
            p = st[part]
            if p.get("mode") == "image" and not any((p.get("images") or {}).values()):
                msgs.append(f"{CF.PART_LABEL[part]}: 그림을 고르지 않아 게임 그림을 씁니다.")
        if any(st[p].get("mode") == "image" for p in CF.PARTS):
            msgs.append("내 그림은 ④ 게시(dll+pck)로 담아야 게임에 보입니다.")
        self.warn.setText("\n".join(msgs))

    def browse(self, edit):
        path, _ = QFileDialog.getOpenFileName(self, "그림 고르기", "", "PNG 이미지 (*.png);;모든 파일 (*.*)")
        if path:
            edit.setText(path)

    def export(self):
        assets = self._assets()
        if assets is None:
            QMessageBox.critical(self, TITLE, "게임 파일을 찾지 못했습니다. '모드 / 빌드' 탭에서 슬더스2 설치 폴더를 정하세요.")
            return
        folder = QFileDialog.getExistingDirectory(self, "원본 틀을 저장할 폴더")
        if not folder:
            return
        try:
            names = CF.export_templates(assets, folder)
        except Exception as e:  # noqa: BLE001
            QMessageBox.critical(self, TITLE, f"저장하지 못했습니다:\n{e}")
            return
        QMessageBox.information(self, TITLE, f"{len(names)}개를 저장했습니다:\n" + "\n".join(names) +
                                "\n\n틀 598×844 · 그림 테두리 551×420 · 제목 띠 655×170")

    # ---- 미리보기 ----
    def schedule(self):
        self._timer.start()

    def draw(self):
        assets = self._assets()
        if assets is None:
            for label in self.preview_labels:
                label.setPixmap(QPixmap())          # setPixmap 은 글을 지우므로 글은 나중에 넣는다
                label.setText("게임 파일이 있어야 미리보기를 그릴 수 있습니다.")
            return
        st = self.styles[self.cur] if self.cur is not None else None
        rarity = self.rarity.currentData() or "Common"
        for label, t in zip(self.preview_labels, CF.TYPES):
            name, desc = SAMPLE[t]
            card = {"id": f"sample_{t.lower()}", "type": t, "rarity": rarity, "cost": 1, "upgrade_cost": 1,
                    "name_ko": name, "name_en": t, "desc_ko": desc, "effects": [], "keywords": [], "image": "",
                    "_frame_style": st}
            try:
                im = ingame.compose(assets, self.project, "card", card, "ko")
            except Exception as e:  # noqa: BLE001 - 한 장이 실패해도 나머지는 그린다
                label.setPixmap(QPixmap())
                label.setText(str(e)[:60])
                continue
            tw = 120
            im = im.resize((tw, max(1, int(im.height * tw / im.width))))
            label.setText("")
            label.setPixmap(PQ._qpixmap(im))

    def close_dialog(self):
        self.accept()

    def done(self, result):
        super().done(result)
        self._notify()

"""'이펙트 · 버튼' 탭의 Qt 版.

  * 이펙트 그리기: 붓·직선·원·고리·사각형·다각형·그림으로 그리고, 도형마다 움직임을 정한다. ▶ 재생으로 미리본다.
  * 전투 버튼:     버튼 모양·위치·비용·조건·이펙트를 정하고, 오른쪽 시험장에서 눌러 본다.

화면과 무관한 계산(도형, 재생 시간, 무대 배경, ID 변경)은 fxbtn.py · fxrules.py 가 한다. 이 파일은 그리기와 입력만 맡는다.
아직 Qt 에서 못 하는 것: 버튼의 값·조건 칸(블록 편집 창, Tk 앱에서), 버튼의 '눌렀을 때 블록' 편집 (Tk 앱에서).
"""
import copy
import math
import time

from PySide6.QtCore import Qt, QPointF, QTimer
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDoubleSpinBox,
                               QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
                               QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QScrollArea, QSlider,
                               QSpinBox, QSplitter, QTabWidget, QVBoxLayout, QWidget)

import blockcode as B
import fxbtn as FX
import fxrules as R
import gamescene as GS
import gimmickrules as GR
import ingame
import modgen as M
import preview_qt as PQ
import projectio as IO
import qtkit as Q
from formqt import label

TOOLS = [("select", "↖ 선택·이동"), ("stroke", "🖌 붓"), ("line", "／ 직선"), ("circle", "● 원"), ("ring", "◯ 고리"),
         ("rect", "▭ 사각형"), ("poly", "⬠ 다각형"), ("image", "🖼 그림")]
TOOL_HINTS = {"select": "도형을 눌러 고르고 끌어서 옮깁니다.", "stroke": "누른 채로 끌어서 자유롭게 그립니다.",
              "line": "끌어서 직선을 긋습니다.", "circle": "가운데를 누르고 끌어서 크기를 정합니다.",
              "ring": "가운데를 누르고 끌어서 크기를 정합니다.", "rect": "모서리에서 끌어 사각형을 그립니다.",
              "poly": "점을 하나씩 찍고, 더블클릭(또는 오른쪽 클릭)으로 마칩니다.",
              "image": "넣을 곳을 누르면 PNG 를 고릅니다 (불꽃·칼날 그림 등)."}
MAX_UNDO = 60


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


def _pil_pixmap(im):
    return PQ._qpixmap(im)


def _num(text, default=None, cast=float):
    try:
        return cast(float(text))
    except (TypeError, ValueError):
        return default


class _Stage(QLabel):
    """무대 그림. 마우스 입력을 주인(EffectPainterQt 나 ButtonDesignerQt)에게 넘긴다."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setMouseTracking(True)
        self.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)

    def mousePressEvent(self, e):
        self.owner.stage_press(e)

    def mouseMoveEvent(self, e):
        self.owner.stage_move(e)

    def mouseReleaseEvent(self, e):
        self.owner.stage_release(e)

    def mouseDoubleClickEvent(self, e):
        self.owner.stage_double(e)


class EffectPainterQt(QWidget):
    def __init__(self, tab, parent=None):
        super().__init__(parent)
        self.tab = tab
        self.z = tab.z
        self.cur = None
        self.sel = None
        self.color = "#b48cff"
        self.drawing = None
        self.history = []
        self.playing = False
        self.t = 0.0
        self._loading = False
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._tick)
        self._t0 = 0.0

        split = QSplitter(Qt.Orientation.Horizontal)
        root = QHBoxLayout(self)
        root.addWidget(split)

        # ---- 왼쪽: 이펙트 목록 ----
        left = QWidget()
        lc = QVBoxLayout(left)
        lc.addWidget(_bold("이펙트"))
        self.lst = QListWidget()
        self.lst.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.lst.currentRowChanged.connect(self._effect_row)
        lc.addWidget(self.lst, 1)
        bar = QHBoxLayout()
        for text, slot in (("새로", self.add_effect), ("복제", self.dup_effect), ("삭제", self.del_effect)):
            bar.addWidget(_button(text, slot))
        lc.addLayout(bar)
        self.ev = {}
        for key, text in (("id", "ID"), ("name", "이름"), ("x", "기준점 X"), ("y", "기준점 Y"), ("z", "앞뒤 (Z)")):
            row = QHBoxLayout()
            row.addWidget(label(text))
            edit = QLineEdit()
            edit.textChanged.connect(self.effect_changed)
            row.addWidget(edit, 1)
            lc.addLayout(row)
            self.ev[key] = edit
        lc.addWidget(label("기준점: 캐릭터 발밑에서의 위치. (0, -120) = 몸통 가운데.\n"
                           "블록 '이펙트 재생'에서 '모든 적'을 고르면 적마다 재생."))
        split.addWidget(left)

        # ---- 가운데: 도구 · 무대 · 재생 ----
        mid = QWidget()
        mc = QVBoxLayout(mid)
        tools = QHBoxLayout()
        self._tool_group = QButtonGroup(self)
        for i, (val, text) in enumerate(TOOLS):
            button = QRadioButton(text)
            button.setChecked(val == "stroke")
            button.toggled.connect(lambda on, v=val: on and self.tool_changed(v))
            self._tool_group.addButton(button, i)
            tools.addWidget(button)
        tools.addStretch(1)
        mc.addLayout(tools)
        self.tool = "stroke"
        style = QHBoxLayout()
        style.addWidget(label("색"))
        self.swatch = QLabel()
        self.swatch.setFixedSize(30, 18)
        style.addWidget(self.swatch)
        style.addWidget(_button("고르기", self.pick_color))
        style.addWidget(label("굵기"))
        self.width = _spin(4, 1, 60)
        self.width.valueChanged.connect(lambda _v: self.style_to_sel())
        style.addWidget(self.width)
        style.addWidget(label("불투명"))
        self.alpha = _dspin(1.0, 0.05, 1.0, 0.05)
        self.alpha.valueChanged.connect(lambda _v: self.style_to_sel())
        style.addWidget(self.alpha)
        self.fill = QCheckBox("채우기")
        self.fill.setChecked(True)
        self.fill.toggled.connect(lambda _c: self.style_to_sel())
        style.addWidget(self.fill)
        self.grid_on = QCheckBox("격자")
        self.grid_on.setChecked(True)
        self.grid_on.toggled.connect(lambda _c: self.redraw())
        style.addWidget(self.grid_on)
        self.at_enemy = QCheckBox("적 위치에서 보기")
        self.at_enemy.toggled.connect(lambda _c: self.redraw())
        style.addWidget(self.at_enemy)
        style.addStretch(1)
        mc.addLayout(style)
        self.stage = _Stage(self)
        self.stage.setFixedSize(int(R.CW * self.z), int(R.CH * self.z))
        self.stage.setStyleSheet(f"background: {Q.C['stage']};")
        mc.addWidget(self.stage, 0, Qt.AlignmentFlag.AlignHCenter)
        play = QHBoxLayout()
        self.play_btn = _button("▶ 재생", self.toggle_play)
        play.addWidget(self.play_btn)
        play.addWidget(_button("⏮ 처음", lambda: self.seek(0)))
        self.loop = QCheckBox("반복")
        self.loop.setChecked(True)
        play.addWidget(self.loop)
        play.addWidget(label("속도"))
        self.speed = QComboBox()
        self.speed.addItems(["1", "0.5", "0.25"])
        play.addWidget(self.speed)
        self.fast = QCheckBox("게임 '빠르게' 설정으로")
        play.addWidget(self.fast)
        self.scrub = QSlider(Qt.Orientation.Horizontal)
        self.scrub.setRange(0, 1000)
        self.scrub.valueChanged.connect(self._scrub_moved)
        play.addWidget(self.scrub, 1)
        self.tlabel = label("0.00 / 0.00초")
        play.addWidget(self.tlabel)
        mc.addLayout(play)
        self.hint = label("")
        self.hint.setStyleSheet(f"color: {Q.C['muted']};")
        mc.addWidget(self.hint)
        mc.addStretch(1)
        split.addWidget(mid)

        # ---- 오른쪽: 도형 · 움직임 ----
        right = QWidget()
        rc = QVBoxLayout(right)
        rc.addWidget(_bold("도형"))
        self.shapes = QListWidget()
        self.shapes.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.shapes.currentRowChanged.connect(self._shape_row)
        rc.addWidget(self.shapes, 1)
        sbar = QHBoxLayout()
        for text, slot in (("▲", lambda: self.move_shape(-1)), ("▼", lambda: self.move_shape(1)),
                           ("복제", self.dup_shape), ("삭제", self.del_shape), ("되돌리기", self.undo)):
            sbar.addWidget(_button(text, slot))
        rc.addLayout(sbar)
        self.av = {}
        anim = QGridLayout()
        rows = (("start", "시작 (초)", 0, 5, 0.05), ("dur", "길이 (초)", 0.05, 5, 0.05), ("mx", "이동 X", -900, 900, 10),
                ("my", "이동 Y", -600, 600, 10), ("scale", "크기 (배)", 0, 10, 0.1), ("rot", "회전 (도)", -1440, 1440, 15),
                ("fade", "끝 불투명", 0, 1, 0.1), ("copies", "복제 수", 1, 60, 1), ("spread", "퍼짐 (px)", 0, 900, 10))
        for r, (k, text, lo, hi, step) in enumerate(rows):
            anim.addWidget(label(text), r, 0)
            box = _dspin(lo, lo, hi, step) if k != "copies" else _spin(1, 1, 60)
            if k == "copies":
                box.setRange(1, 60)
            box.valueChanged.connect(lambda _v: self.anim_changed())
            anim.addWidget(box, r, 1)
            self.av[k] = box
        anim.addWidget(label("가속"), len(rows), 0)
        self.ease = QComboBox()
        for _k, text in FX.EASES:
            self.ease.addItem(text)
        self.ease.currentIndexChanged.connect(lambda _i: self.anim_changed())
        anim.addWidget(self.ease, len(rows), 1)
        anim.addWidget(label("복제 수 > 1 이면 사방으로 '퍼짐'만큼 흩어집니다 (나비 떼, 파편)."), len(rows) + 1, 0, 1, 2)
        rc.addLayout(anim)
        self.info = label("")
        self.info.setStyleSheet(f"color: {Q.C['secondary']};")
        rc.addWidget(self.info)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([240, 640, 300])
        self.swatch.setStyleSheet(f"background: {self.color};")
        self.load()

    # ---- 데이터 ----
    @property
    def fxs(self):
        return self.tab.g["effects"]

    @property
    def fx(self):
        return self.fxs[self.cur] if self.cur is not None and self.cur < len(self.fxs) else None

    def load(self):
        self.lst.blockSignals(True)
        self.lst.clear()
        for e in self.fxs:
            self.lst.addItem(f"✦ {e.get('name') or e['id']}  ({e['id']})")
        self.lst.blockSignals(False)
        if self.fxs:
            i = min(self.cur or 0, len(self.fxs) - 1)
            self.lst.setCurrentRow(i)
            self.select_effect(i)
        else:
            self.cur = None
            self.refresh_shapes()
            self.redraw()

    def _effect_row(self, row):
        if row >= 0 and row != self.cur:
            self.select_effect(row)

    def select_effect(self, i):
        self.cur = i
        self.sel = None
        self.history = []
        self._loading = True
        try:
            for k, edit in self.ev.items():
                edit.setText(str(self.fx.get(k, "")))
        finally:
            self._loading = False
        self.refresh_shapes()
        self.seek(0)

    def effect_changed(self, *_):
        if self._loading or self.fx is None:
            return
        e = self.fx
        old = e["id"]
        for k, edit in self.ev.items():
            val = edit.text().strip()
            if k in ("x", "y", "z"):
                try:
                    e[k] = float(val) if k != "z" else int(float(val))
                except ValueError:
                    continue
            else:
                e[k] = val
        if e["id"] != old and e["id"]:
            R._rename(self.tab.project, "fx", old, e["id"])
        self.lst.blockSignals(True)
        item = self.lst.item(self.cur)
        if item is not None:
            item.setText(f"✦ {e.get('name') or e['id']}  ({e['id']})")
        self.lst.blockSignals(False)
        self.tab.dirty()
        self.redraw()

    def add_effect(self):
        self.fxs.append(FX.new_effect(self.tab.unique("new_fx")))
        self.cur = len(self.fxs) - 1
        self.tab.dirty()
        self.load()

    def dup_effect(self):
        if self.fx is None:
            return
        e = copy.deepcopy(self.fx)
        e["id"] = self.tab.unique(e["id"])
        e["name"] = (e.get("name") or "") + " (복사)"
        self.fxs.insert(self.cur + 1, e)
        self.cur += 1
        self.tab.dirty()
        self.load()

    def del_effect(self):
        if self.fx is None:
            return
        if not _ask(self, f"이펙트 '{self.fx.get('name')}'를 삭제할까요?"):
            return
        R._rename(self.tab.project, "fx", self.fx["id"], None)
        del self.fxs[self.cur]
        self.cur = max(0, self.cur - 1)
        self.tab.dirty()
        self.load()

    # ---- 도형 목록 ----
    def refresh_shapes(self):
        self.shapes.blockSignals(True)
        self.shapes.clear()
        if self.fx is None:
            self.shapes.blockSignals(False)
            self.info.setText("")
            return
        names = dict(FX.SHAPE_TYPES)
        for i, s in enumerate(self.fx["shapes"]):
            a = s.get("anim") or {}
            extra = f" ×{a.get('copies')}" if int(a.get("copies", 1) or 1) > 1 else ""
            start = float(a.get("start", 0) or 0)
            self.shapes.addItem(f"{i + 1}. {names.get(s['type'], s['type'])}{extra}  "
                                f"{a.get('start', 0)}~{start + float(a.get('dur', 0.5) or 0.5):.2f}s")
        if self.sel is not None and self.sel < len(self.fx["shapes"]):
            self.shapes.setCurrentRow(self.sel)
        self.shapes.blockSignals(False)
        self.info.setText(f"도형 {len(self.fx['shapes'])}개 · 전체 {FX.total_time(self.fx):.2f}초")

    def _shape_row(self, row):
        self.select_shape(row if row >= 0 else None)

    def select_shape(self, i):
        self.sel = i
        if i is None or self.fx is None or i >= len(self.fx["shapes"]):
            self.sel = None
            self.redraw()
            return
        s = self.fx["shapes"][i]
        a = s.get("anim") or FX.new_anim()
        self._loading = True
        try:
            self.av["start"].setValue(float(a.get("start", 0)))
            self.av["dur"].setValue(float(a.get("dur", 0.5)))
            mv = a.get("move") or [0, 0]
            self.av["mx"].setValue(float(mv[0]))
            self.av["my"].setValue(float(mv[1]))
            for k in ("scale", "rot", "fade", "spread"):
                self.av[k].setValue(float(a.get(k, 0) or 0))
            self.av["copies"].setValue(int(a.get("copies", 1) or 1))
            keys = [k for k, _t in FX.EASES]
            self.ease.setCurrentIndex(keys.index(a.get("ease", "out")) if a.get("ease", "out") in keys else 0)
            self.color = s.get("color") or self.color
            self.swatch.setStyleSheet(f"background: {self.color};")
            self.width.setValue(int(float(s.get("width", 4))))
            self.alpha.setValue(float(s.get("alpha", 1)))
            self.fill.setChecked(bool(s.get("fill")))
        finally:
            self._loading = False
        self.shapes.blockSignals(True)
        self.shapes.setCurrentRow(i)
        self.shapes.blockSignals(False)
        self.redraw()

    def anim_changed(self):
        if self._loading or self.fx is None or self.sel is None:
            return
        s = self.fx["shapes"][self.sel]
        a = s.setdefault("anim", FX.new_anim())
        for k, cast in (("start", float), ("dur", float), ("scale", float), ("rot", float), ("fade", float),
                        ("copies", int), ("spread", float)):
            a[k] = cast(self.av[k].value())
        a["move"] = [float(self.av["mx"].value()), float(self.av["my"].value())]
        a["ease"] = FX.EASES[self.ease.currentIndex()][0]
        self.tab.dirty()
        self.refresh_shapes()
        self.redraw()

    def style_to_sel(self):
        if self._loading or self.fx is None or self.sel is None:
            return
        s = self.fx["shapes"][self.sel]
        self.push()
        s["color"] = self.color
        s["width"] = float(self.width.value())
        s["alpha"] = max(0.0, min(1.0, float(self.alpha.value())))
        s["fill"] = bool(self.fill.isChecked())
        self.tab.dirty()
        self.redraw()

    def pick_color(self):
        chosen = QColorDialog.getColor(QColor(self.color), self, "색 고르기")
        if chosen.isValid():
            self.color = chosen.name()
            self.swatch.setStyleSheet(f"background: {self.color};")
            self.style_to_sel()

    def move_shape(self, d):
        if self.fx is None or self.sel is None:
            return
        sh = self.fx["shapes"]
        j = self.sel + d
        if 0 <= j < len(sh):
            self.push()
            sh[self.sel], sh[j] = sh[j], sh[self.sel]
            self.sel = j
            self.tab.dirty()
            self.refresh_shapes()
            self.redraw()

    def dup_shape(self):
        if self.fx is None or self.sel is None:
            return
        self.push()
        s = copy.deepcopy(self.fx["shapes"][self.sel])
        R._offset(s, 20, 20)
        self.fx["shapes"].insert(self.sel + 1, s)
        self.sel += 1
        self.tab.dirty()
        self.refresh_shapes()
        self.redraw()

    def del_shape(self):
        if self.fx is None or self.sel is None:
            return
        self.push()
        del self.fx["shapes"][self.sel]
        self.sel = None
        self.tab.dirty()
        self.refresh_shapes()
        self.redraw()

    def push(self):
        if self.fx is not None:
            self.history.append(copy.deepcopy(self.fx["shapes"]))
            self.history = self.history[-MAX_UNDO:]

    def undo(self):
        if self.fx is not None and self.history:
            self.fx["shapes"] = self.history.pop()
            self.sel = None
            self.tab.dirty()
            self.refresh_shapes()
            self.redraw()

    # ---- 좌표 ----
    def origin(self):
        feet = R.ENEMY_FEET if self.at_enemy.isChecked() else R.PLAYER_FEET
        e = self.fx or {"x": 0, "y": -120}
        return feet[0] + float(e.get("x", 0)), feet[1] + float(e.get("y", -120))

    def to_local(self, pos):
        ox, oy = self.origin()
        return round(pos.x() / self.z - ox, 1), round(pos.y() / self.z - oy, 1)

    def to_screen(self, x, y):
        ox, oy = self.origin()
        return (x + ox) * self.z, (y + oy) * self.z

    # ---- 그리기 ----
    def tool_changed(self, value):
        self.tool = value
        self.hint.setText(TOOL_HINTS.get(value, ""))
        self.drawing = None
        self.redraw()

    def _style(self):
        return {"color": self.color, "width": float(self.width.value()), "alpha": max(0.05, min(1.0, float(self.alpha.value())))}

    def stage_press(self, e):
        if e.button() == Qt.MouseButton.RightButton:
            self.stage_double(e)
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self.fx is None:
            self.add_effect()
        self.stop()
        x, y = self.to_local(e.position())
        tool = self.tool
        if tool == "select":
            i = self.hit(x, y)
            self.select_shape(i)
            if i is not None:
                self.push()
                self.drawing = {"kind": "move", "last": (x, y)}
            return
        if tool == "poly":
            if not self.drawing or self.drawing.get("kind") != "poly":
                self.drawing = {"kind": "poly", "pts": []}
            self.drawing["pts"].append([x, y])
            self.redraw()
            return
        if tool == "image":
            path, _ = QFileDialog.getOpenFileName(self, "그림 고르기", "", "PNG 이미지 (*.png);;모든 파일 (*.*)")
            if not path:
                return
            im = FX._load_img(path)
            w, h = (im.size if im else (80, 80))
            k = 120 / max(w, h)
            self.add_shape(FX.new_shape("image", cx=x, cy=y, w=round(w * k), h=round(h * k), image=path, **self._style()))
            return
        self.drawing = {"kind": tool, "p0": (x, y), "pts": [[x, y]]}

    def stage_move(self, e):
        d = self.drawing
        if not d:
            return
        x, y = self.to_local(e.position())
        if d["kind"] == "move":
            lx, ly = d["last"]
            R._offset(self.fx["shapes"][self.sel], x - lx, y - ly)
            d["last"] = (x, y)
            self.redraw()
            return
        if d["kind"] == "stroke":
            lx, ly = d["pts"][-1]
            if math.hypot(x - lx, y - ly) >= 3:
                d["pts"].append([x, y])
        else:
            d["p1"] = (x, y)
        self.redraw()

    def stage_release(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        d = self.drawing
        if not d or d["kind"] == "poly":
            return
        self.drawing = None
        if d["kind"] == "move":
            self.tab.dirty()
            self.refresh_shapes()
            self.redraw()
            return
        x0, y0 = d["p0"]
        x1, y1 = d.get("p1", d["p0"])
        st = self._style()
        k = d["kind"]
        if k == "stroke" and len(d["pts"]) >= 2:
            self.add_shape(FX.new_shape("stroke", points=R._simplify(d["pts"]), fill=False, **st))
        elif k == "line" and (x0, y0) != (x1, y1):
            self.add_shape(FX.new_shape("line", points=[[x0, y0], [x1, y1]], fill=False, **st))
        elif k in ("circle", "ring"):
            r = max(4.0, round(math.hypot(x1 - x0, y1 - y0), 1))
            self.add_shape(FX.new_shape(k, cx=x0, cy=y0, r=r, fill=(k == "circle"), **st))
        elif k == "rect" and abs(x1 - x0) > 2 and abs(y1 - y0) > 2:
            self.add_shape(FX.new_shape("rect", cx=(x0 + x1) / 2, cy=(y0 + y1) / 2, w=abs(x1 - x0), h=abs(y1 - y0),
                                        fill=bool(self.fill.isChecked()), **st))
        else:
            self.redraw()

    def stage_double(self, _e):
        d = self.drawing
        if d and d.get("kind") == "poly":
            self.drawing = None
            pts = d["pts"]
            if len(pts) >= 3:
                self.add_shape(FX.new_shape("poly", points=pts, fill=bool(self.fill.isChecked()), **self._style()))
            else:
                self.redraw()

    def add_shape(self, s):
        self.push()
        self.fx["shapes"].append(s)
        self.sel = len(self.fx["shapes"]) - 1
        self.tab.dirty()
        self.refresh_shapes()
        self.select_shape(self.sel)

    def hit(self, x, y):
        if self.fx is None:
            return None
        for i in range(len(self.fx["shapes"]) - 1, -1, -1):
            x1, y1, x2, y2 = R._bbox(self.fx["shapes"][i])
            if x1 - 6 <= x <= x2 + 6 and y1 - 6 <= y <= y2 + 6:
                return i
        return None

    # ---- 화면 ----
    def redraw(self, t=None):
        """t 가 없으면 편집 화면(처음 모습), 있으면 그 시각의 재생 장면을 그린다."""
        base = R.stage_image(self.grid_on.isChecked(), self.at_enemy.isChecked(), self.tab.project)
        img = base
        if self.fx is not None:
            still = t is None
            ox, oy = self.origin()
            img = FX.render(self.fx, t or 0.0, (R.CW, R.CH),
                            (ox - float(self.fx.get("x", 0)), oy - float(self.fx.get("y", -120))),
                            img=base, still=still, ss=1 if (self.playing and not still) else 2)
        pm = _pil_pixmap(img)
        if self.z != 1:
            pm = pm.scaled(int(R.CW * self.z), int(R.CH * self.z), Qt.AspectRatioMode.IgnoreAspectRatio,
                           Qt.TransformationMode.SmoothTransformation)
        if self.fx is not None:
            p = QPainter(pm)
            try:
                ox, oy = self.to_screen(0, 0)
                p.setPen(QPen(QColor("#ffcc33"), 1))
                p.drawLine(QPointF(ox - 8, oy), QPointF(ox + 8, oy))
                p.drawLine(QPointF(ox, oy - 8), QPointF(ox, oy + 8))
                if t is None and self.sel is not None and self.sel < len(self.fx["shapes"]):
                    x1, y1, x2, y2 = R._bbox(self.fx["shapes"][self.sel])
                    a, b = self.to_screen(x1, y1)
                    c, d = self.to_screen(x2, y2)
                    p.setPen(QPen(QColor("#33d6ff"), 1, Qt.PenStyle.DashLine))
                    p.drawRect(int(a - 4), int(b - 4), int(c - a + 8), int(d - b + 8))
                if t is None and self.drawing and self.drawing.get("kind") == "poly":
                    self._draw_poly_points(p)
                elif t is None and self.drawing and self.drawing.get("kind") not in ("move", None):
                    self._draw_temp(p)
            finally:
                p.end()
        self.stage.setPixmap(pm)

    def _draw_temp(self, p):
        d = self.drawing
        col = QColor(self.color)
        w = max(1.0, float(self.width.value()) * self.z)
        p.setPen(QPen(col, w, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        if d["kind"] == "stroke":
            pts = [QPointF(*self.to_screen(*q)) for q in d["pts"]]
            for a, b in zip(pts, pts[1:]):
                p.drawLine(a, b)
            return
        x0, y0 = self.to_screen(*d["p0"])
        x1, y1 = self.to_screen(*d.get("p1", d["p0"]))
        if d["kind"] == "line":
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        elif d["kind"] in ("circle", "ring"):
            r = math.hypot(x1 - x0, y1 - y0)
            if d["kind"] == "circle":
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QBrush(col))
            else:
                p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(x0, y0), r, r)
        elif d["kind"] == "rect":
            p.setPen(QPen(col, 2))
            p.setBrush(QBrush(col) if self.fill.isChecked() else Qt.BrushStyle.NoBrush)
            p.drawRect(int(min(x0, x1)), int(min(y0, y1)), int(abs(x1 - x0)), int(abs(y1 - y0)))

    def _draw_poly_points(self, p):
        pts = [self.to_screen(*q) for q in self.drawing["pts"]]
        p.setPen(QPen(QColor("white"), 1))
        p.setBrush(QBrush(QColor(self.color)))
        for x, y in pts:
            p.drawEllipse(QPointF(x, y), 3, 3)
        if len(pts) >= 2:
            p.setPen(QPen(QColor(self.color), 2, Qt.PenStyle.DashLine))
            for a, b in zip(pts, pts[1:]):
                p.drawLine(QPointF(*a), QPointF(*b))

    # ---- 재생 ----
    def toggle_play(self):
        if self.playing:
            self.stop()
        else:
            self.play()

    def play(self):
        if self.fx is None or not self.fx.get("shapes"):
            return
        self.playing = True
        self.play_btn.setText("■ 정지")
        if self.t >= FX.total_time(self.fx) - 1e-3:
            self.t = 0.0
        self._t0 = time.perf_counter() - self.t / self._rate()
        self._timer.start()
        self._tick()

    def _rate(self):
        r = _num(self.speed.currentText(), 1.0)
        return r * (2.0 if self.fast.isChecked() else 1.0)   # 게임 '빠르게' = 시간 0.5배

    def _tick(self):
        if not self.playing or self.fx is None:
            return
        total = FX.total_time(self.fx)
        self.t = (time.perf_counter() - self._t0) * self._rate()
        if self.t > total + 0.25:
            if self.loop.isChecked():
                self._t0 = time.perf_counter()
                self.t = 0.0
            else:
                self.stop()
                return
        self.show_time(min(self.t, total))

    def stop(self):
        self.playing = False
        self.play_btn.setText("▶ 재생")
        self._timer.stop()
        self.redraw()

    def seek(self, t, from_scale=False):
        if self.fx is None:
            self.redraw()
            return
        total = FX.total_time(self.fx)
        if from_scale:
            t = float(t) * total
        self.t = t
        if t <= 0 and not from_scale:
            self.redraw()
            self.tlabel.setText(f"0.00 / {total:.2f}초")
            self._set_scrub(0)
            return
        self.show_time(t)

    def _set_scrub(self, value):
        self.scrub.blockSignals(True)
        self.scrub.setValue(int(value))
        self.scrub.blockSignals(False)

    def _scrub_moved(self, value):
        if self.fx is None or self.playing:
            return
        self.seek(value / 1000.0, from_scale=True)

    def show_time(self, t):
        total = FX.total_time(self.fx)
        self.redraw(t)
        self.tlabel.setText(f"{t:.2f} / {total:.2f}초")
        self._set_scrub(1000 * t / total if total else 0)


def _bold(text):
    lab = QLabel(text)
    lab.setStyleSheet("font-weight: bold;")
    return lab


def _button(text, slot):
    b = QPushButton(text)
    b.clicked.connect(slot)
    return b


def _spin(value, lo, hi):
    s = QSpinBox()
    s.setRange(lo, hi)
    s.setValue(int(value))
    return s


def _dspin(value, lo, hi, step):
    s = QDoubleSpinBox()
    s.setRange(lo, hi)
    s.setSingleStep(step)
    s.setDecimals(2)
    s.setValue(float(value))
    return s

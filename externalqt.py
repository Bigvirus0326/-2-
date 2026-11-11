"""'다른 모드' 탭의 Qt 版: 불러오기 · 보기 · 복제 · 참조 · 키워드 가져오기 · 통째로 열기 (Tk 의 ExternalTab 과 같은 규칙).

'게임 화면' 그림은 gameviewqt 로 백그라운드에서 만들어 칸에 그린다.
"""
import copy
import os
import re
import threading
import traceback

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout,
                               QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit,
                               QPushButton, QRadioButton, QScrollArea, QSplitter, QVBoxLayout, QWidget)

import gimmick as GM
import modgen as M
import modimport as MI
import preview_qt as PQ
import projectio as IO
import qtkit as Q
from itemtabqt import all_ids
from gameviewqt import GameModeBar

KINDS = (("card", "카드"), ("relic", "유물"), ("potion", "물약"), ("power", "파워"))
LANGS = (("ko", "한국어"), ("en", "English"), ("zh", "简体中文"))
KIND_NAMES = {"installed": "설치된 모드", "source": "C# 소스", "pck": ".pck 파일", "dll": ".dll 파일"}
GAP, PAD = 12, 14


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


def _info(parent, text):
    QMessageBox.information(parent, IO.APP_TITLE, text)


def _warn(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


def _btn(text, slot):
    button = QPushButton(text)
    button.clicked.connect(slot)
    return button


from qtkit import code_window as _code_window  # noqa: E402 - 원본 코드 창은 공용 부품


class _Tiles(QWidget):
    """다른 모드의 항목 그림 칸. 클릭 = 선택, 더블클릭 = 원본 코드."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setMouseTracking(False)
        self.setStyleSheet(f"background: {Q.C['stage']};")
        self.pos = {}              # (kind, index) -> (x, y, w, h)

    def paintEvent(self, _event):
        self.owner.paint_tiles(self)

    def mousePressEvent(self, e):
        key = self.owner.tile_at(e.position().toPoint())
        if key is not None:
            self.owner.toggle(*key)

    def mouseDoubleClickEvent(self, e):
        key = self.owner.tile_at(e.position().toPoint())
        if key is not None:
            self.owner.show_code(key[1])


class ExternalTabQt(QWidget):
    loaded = Signal(object)                 # 불러오기 성공 (화면 스레드에서 처리)
    load_failed = Signal(str, str, str)     # (메시지, 자세한 내용, 오류 종류)

    def __init__(self, app, parent=None):
        super().__init__(parent)
        self.app = app
        self.views = getattr(app, "views", None)     # 게임 화면 설정 (app 이 넣는다)
        self._pix = {}                                # 게임 화면 그림 (칸 크기에 맞춘 QPixmap)
        self.mods = []
        self.cur = None
        self.selected = set()
        self.loaded.connect(self._loaded)
        self.load_failed.connect(self._show_load_error)

        root = QVBoxLayout(self)
        bar = QHBoxLayout()
        self._bar_button(bar, "캐릭터 카드 라이브러리…", getattr(app, "open_card_library", None),
                         "카드 라이브러리를 쓸 수 없습니다.")
        self._bar_button(bar, "설치된 모드에서…", self.pick_installed)
        self._bar_button(bar, "모드 폴더 열기…", self.open_folder)
        self._bar_button(bar, "파일 열기 (.dll/.pck/.json)…", self.open_file)
        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {Q.C['muted']};")
        bar.addWidget(self.status)
        bar.addStretch(1)
        root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)

        # ---- 왼쪽: 모드 목록 · 참조 ----
        left = QWidget()
        lc = QVBoxLayout(left)
        self.listbox = QListWidget()
        self.listbox.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.listbox.currentRowChanged.connect(lambda _r: self.on_select())
        lc.addWidget(self.listbox)
        self.detail = QLabel("왼쪽 위 버튼으로 다른 모드를 불러오세요.")
        self.detail.setWordWrap(True)
        lc.addWidget(self.detail)
        self.take_btn = QPushButton("📂 이 모드를 통째로 내 프로젝트로")
        self.take_btn.clicked.connect(self.take_over)
        lc.addWidget(self.take_btn)
        note = QLabel("원래 코드·그림·번역을 그대로 담은 새 프로젝트를 만들고, 카드·유물·물약·파워를 여기서 고칠 수 있게 합니다.")
        note.setWordWrap(True)
        note.setStyleSheet(f"color: {Q.C['muted']};")
        lc.addWidget(note)
        self.dep_btn = QPushButton("내 모드에서 참조하기")
        self.dep_btn.clicked.connect(self.toggle_dep)
        lc.addWidget(self.dep_btn)
        kw = QPushButton("이 모드의 키워드 보기…")
        kw.clicked.connect(self.pick_keyword)
        lc.addWidget(kw)
        dep_note = QLabel("참조하면 그 모드의 파워를 내 카드 효과(◆ 표시)에서 쓸 수 있고, 생성되는 모드가 그 모드를 필요로 하게 됩니다.")
        dep_note.setWordWrap(True)
        dep_note.setStyleSheet(f"color: {Q.C['muted']};")
        lc.addWidget(dep_note)
        close = QPushButton("목록에서 닫기")
        close.clicked.connect(self.close_mod)
        lc.addWidget(close)
        split.addWidget(left)

        # ---- 오른쪽: 모드 내용 ----
        right = QWidget()
        rc = QVBoxLayout(right)
        fb = QHBoxLayout()
        self._kind_group = QButtonGroup(self)
        self.kind = "card"
        for i, (val, text) in enumerate(KINDS):
            button = QRadioButton(text)
            button.setChecked(val == "card")
            button.toggled.connect(lambda on, v=val: on and self.set_kind(v))
            self._kind_group.addButton(button, i)
            fb.addWidget(button)
        fb.addSpacing(10)
        self.lang = "ko"
        self._lang_group = QButtonGroup(self)
        for i, (val, text) in enumerate(LANGS):
            button = QRadioButton(text)
            button.setChecked(val == "ko")
            button.toggled.connect(lambda on, v=val: on and self.set_lang(v))
            self._lang_group.addButton(button, i)
            fb.addWidget(button)
        self.upgraded = QCheckBox("강화(+)")
        self.upgraded.toggled.connect(lambda _c: self.refresh())
        fb.addWidget(self.upgraded)
        fb.addSpacing(10)
        if self.views is not None:
            fb.addWidget(GameModeBar(self.views))
            fb.addSpacing(10)
        fb.addWidget(QLabel("찾기"))
        self.search = QLineEdit()
        self.search.setMaximumWidth(200)
        self.search.textChanged.connect(lambda _t: self.refresh())
        fb.addWidget(self.search)
        fb.addStretch(1)
        rc.addLayout(fb)
        self.tiles = _Tiles(self)
        if self.views is not None:
            self.views.changed.connect(self.tiles.update)
            self.views.ready.connect(self.tiles.update)
        scroll = QScrollArea()
        scroll.setWidgetResizable(False)
        scroll.setFrameShape(scroll.Shape.NoFrame)
        scroll.setWidget(self.tiles)
        self.scroll = scroll
        rc.addWidget(scroll, 1)
        act = QHBoxLayout()
        act.addWidget(_btn("모두 선택", self.select_all))
        act.addWidget(_btn("선택 해제", self.clear_sel))
        self.sel_lbl = QLabel("")
        act.addWidget(self.sel_lbl)
        act.addStretch(1)
        act.addWidget(QLabel("복제할 때 풀:"))
        self.pool = QComboBox()
        self.pool.addItem("내 캐릭터/공용 풀", "mine")
        self.pool.addItem("원본 캐릭터 풀", "theirs")
        act.addWidget(self.pool)
        act.addWidget(_btn("선택 항목을 내 프로젝트로 복제", self.clone_selected))
        rc.addLayout(act)
        hint = QLabel("클릭: 선택/해제 · 더블클릭: 원본 코드 보기")
        hint.setStyleSheet(f"color: {Q.C['muted']};")
        rc.addWidget(hint)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([300, 760])
        self._tile_pos = {}
        self.refresh_list()

    def _bar_button(self, bar, text, slot, tip=""):
        button = QPushButton(text)
        if slot is None:
            button.setEnabled(False)
            button.setToolTip(tip)
        else:
            button.clicked.connect(slot)
        bar.addWidget(button)
        return button

    # ---- 불러오기 ----
    def pick_installed(self):
        mods = MI.list_installed(self.app.settings.get("sts2_path", ""))
        if not mods:
            _info(self, "게임의 mods 폴더에서 모드를 찾지 못했습니다. '모드 / 빌드' 탭의 슬더스2 설치 폴더를 확인하세요.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("설치된 모드")
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        listing.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for name, path, on in mods:
            listing.addItem(f"{'●' if on else '○'} {name}" + ("" if on else "  (꺼짐: mods.disabled)"))
        layout.addWidget(listing)

        def go():
            for i in sorted({listing.row(it) for it in listing.selectedItems()}):
                self.load(mods[i][1])
            dialog.accept()
        button = QPushButton("불러오기")
        button.clicked.connect(go)
        layout.addWidget(button)
        listing.itemDoubleClicked.connect(lambda _it: go())
        dialog.exec()

    def open_folder(self):
        path = QFileDialog.getExistingDirectory(self, "모드 폴더 (설치된 모드 또는 C# 소스 프로젝트)")
        if path:
            self.load(path)

    def open_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "파일 열기", "", "모드 파일 (*.dll *.pck *.json);;모든 파일 (*.*)")
        if path:
            self.load(path)

    def load(self, path):
        self.status.setText(f"불러오는 중: {os.path.basename(path)} …")
        self.app.log(f"다른 모드 불러오는 중: {path}")
        sts2 = self.app.settings.get("sts2_path", "")

        def work():
            try:
                em = MI.load_mod(path, sts2, log=self.app.log)
                self.loaded.emit(em)
            except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여 준다
                msg = str(e).strip() or repr(e).strip() or f"{type(e).__name__} (자세한 내용 없음)"
                self.load_failed.emit(msg, traceback.format_exc(), type(e).__name__)
        threading.Thread(target=work, daemon=True).start()

    def _show_load_error(self, message, trace, error_type):
        self.status.setText("")
        self.app.log(f"[오류] 다른 모드 불러오기 실패 ({error_type}): {message}\n{trace}")
        _warn(self, f"불러오기에 실패했습니다.\n\n{error_type}: {message}\n\n"
                    "자세한 기록은 도움말 → 건의 / 오류 보내기에서 확인할 수 있습니다.")

    def _loaded(self, em):
        self.mods = [m for m in self.mods if m.root != em.root]
        self.mods.append(em)
        self.refresh_list(len(self.mods) - 1)
        self.status.setText("")
        self.app.log(f"불러옴: {em.name} ({em.id}) - {em.summary()}")
        for n in em.notes:
            self.app.log("  " + n)

    def refresh_list(self, select=None):
        deps = {d["id"] for d in self.app.project.get("dependencies", [])}
        self.listbox.blockSignals(True)
        self.listbox.clear()
        for m in self.mods:
            self.listbox.addItem(f"{'✔ ' if m.id in deps else ''}{m.name}  ({m.id})")
        self.listbox.blockSignals(False)
        if self.mods:
            i = select if select is not None else (self.mods.index(self.cur) if self.cur in self.mods else 0)
            self.listbox.setCurrentRow(i)
            self.on_select()
        else:
            self.cur = None
            self.detail.setText("왼쪽 위 버튼으로 다른 모드를 불러오세요.")
            self.refresh()

    def on_select(self):
        row = self.listbox.currentRow()
        if row < 0 or row >= len(self.mods):
            return
        self.cur = self.mods[row]
        self.selected = set()
        m = self.cur
        deps = {d["id"] for d in self.app.project.get("dependencies", [])}
        txt = [f"{m.name}", f"ID {m.id}  ·  {m.version}  ·  {m.author}", f"형태: {KIND_NAMES.get(m.kind, m.kind)}", m.summary()]
        if m.characters:
            txt.append("캐릭터: " + ", ".join(c["class"] for c in m.characters))
        if not m.dll:
            txt.append("dll 없음 → 복제·참조는 할 수 없고 보기만 됩니다.")
        txt += m.notes
        self.detail.setText("\n".join(txt))
        self.dep_btn.setText("참조 해제" if m.id in deps else "내 모드에서 참조하기")
        self.dep_btn.setEnabled(bool(m.dll))
        self.take_btn.setEnabled(bool(m.dll or m.kind == "source"))
        self.refresh()

    def take_over(self):
        if self.cur:
            self.app.open_mod_as_project(self.cur.root)

    def close_mod(self):
        if self.cur in self.mods:
            self.mods.remove(self.cur)
            self.cur = None
            self.refresh_list()

    # ---- 참조 ----
    def toggle_dep(self):
        m = self.cur
        if not m or not m.dll:
            return
        deps = self.app.project.setdefault("dependencies", [])
        if any(d["id"] == m.id for d in deps):
            used = [it["id"] for k in ("cards", "relics", "potions", "powers") for it in self.app.project[k]
                    if (it.get("clone") or {}).get("mod") == m.id]
            if used and not _ask(self, f"이 모드에서 복제한 항목 {len(used)}개가 있습니다. 그래도 참조를 해제할까요?"):
                return
            self.app.project["dependencies"] = [d for d in deps if d["id"] != m.id]
            self.app.log(f"참조 해제: {m.id}")
        else:
            deps.append(MI.dependency_entry(m))
            self.app.log(f"참조 추가: {m.id} (파워 {len(MI.dependency_entry(m)['powers'])}개를 ◆ 표시로 쓸 수 있습니다)")
        self.app.mark_dirty()
        self.refresh_list()

    def _ensure_dep(self, m):
        deps = self.app.project.setdefault("dependencies", [])
        for i, d in enumerate(deps):
            if d["id"] == m.id:
                deps[i] = MI.dependency_entry(m)
                return
        deps.append(MI.dependency_entry(m))

    # ---- 키워드 ----
    def pick_keyword(self):
        em = self.cur
        if not em:
            _info(self, "먼저 다른 모드를 열어 주세요.")
            return
        rows = MI.external_keywords(em)
        if not rows:
            _info(self, "이 모드에서 키워드 또는 툴팁 번역을 찾을 수 없습니다.")
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(em.name + " · 키워드")
        layout = QVBoxLayout(dialog)
        listing = QListWidget()
        for row in rows:
            listing.addItem(M.text(row, "name", "ko") + "  ·  " + row["source_keyword"][2])
        layout.addWidget(listing)
        description = QLabel("")
        description.setWordWrap(True)
        layout.addWidget(description)

        def preview(row_index):
            if row_index < 0:
                return
            row = rows[row_index]
            mode = "원본 모드의 키워드 동작을 참조합니다." if row.get("keyword_member") else "이름과 설명을 툴팁 태그로 가져옵니다."
            description.setText(M.text(row, "desc", "ko") + "\n" + mode)

        def take():
            i = listing.currentRow()
            if i < 0:
                return
            row = rows[i]
            tags = self.app.project["gimmicks"]["tags"]
            if not any(t.get("source_keyword") == row["source_keyword"] for t in tags):
                base = "kw_" + re.sub(r"[^a-z0-9]+", "_", (em.id + "_" + row["source_keyword"][2]).lower()).strip("_")
                ident, n = base, 2
                while ident in all_ids(self.app.project):
                    ident = f"{base}_{n}"
                    n += 1
                tag = GM.new_tag(ident)
                tag.update(copy.deepcopy(row))
                if row.get("keyword_member"):
                    self._ensure_dep(em)
                    tag["show_in_text"] = False
                tags.append(tag)
                self.app.mark_dirty()
                self.app.load_all()
            description.setText("가져왔습니다. 카드 편집기의 기믹 → 태그에서 적용하세요.")
        listing.currentRowChanged.connect(preview)
        listing.setCurrentRow(0)
        button = QPushButton("선택한 키워드 가져오기")
        button.clicked.connect(take)
        layout.addWidget(button)
        dialog.exec()

    # ---- 복제 ----
    def clone_selected(self):
        m = self.cur
        if not m or not self.selected:
            _info(self, "복제할 항목을 클릭해서 고르세요.")
            return
        has_code = any(m.items[k][i].get("_cls") is not None for k, i in self.selected)
        if has_code and not m.dll:
            _warn(self, "이 모드의 dll 을 찾지 못해 원래 동작을 유지한 복제를 할 수 없습니다.")
            return
        P = self.app.project
        used = all_ids(P)
        pool = self.pool.currentData()
        added = {"card": 0, "relic": 0, "potion": 0, "power": 0}
        for kind, i in sorted(self.selected):
            src = m.items[kind][i]
            new = MI.clone_item(m, src, P, pool)
            base_id = new["id"]
            nid, n = base_id, 2
            while nid in used:
                nid = f"{base_id}_{n}"
                n += 1
            new["id"] = nid
            used.add(nid)
            if pool == "theirs":
                pv = MI.preview_item(m, src)
                for k in ("_hsv", "_energy_big", "_energy_small", "_colorless"):
                    if k in pv:
                        new[k] = pv[k]
            P[{"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}[kind]].append(new)
            added[kind] += 1
        if has_code:
            self._ensure_dep(m)
        self.app.mark_dirty()
        self.app.reload_items()
        self.refresh_list()
        msg = f"복제했습니다: 카드 {added['card']} · 유물 {added['relic']} · 물약 {added['potion']} · 파워 {added['power']}"
        if has_code:
            msg += f"\n\n원본 모드 '{m.id}'를 참조(필수 모드)로 추가했습니다. 게임에 원본 모드도 설치되어 있어야 합니다."
        _info(self, msg)

    # ---- 그리기 ----
    def set_kind(self, value):
        self.kind = value
        self.selected = set()
        self.refresh()

    def set_lang(self, value):
        self.lang = value
        self.refresh()

    def visible_items(self):
        if not self.cur:
            return []
        q = self.search.text().strip().lower()
        out = []
        for i, it in enumerate(self.cur.items[self.kind]):
            if q and q not in (it.get("name_ko", "") + it.get("name_en", "") + it.get("class", "")).lower():
                continue
            out.append((i, it))
        return out

    def _tile_size(self):
        sc = 0.6
        return (344 * sc, 460 * sc) if self.kind == "card" else (300 * sc, 330 * sc), sc

    def refresh(self):
        self.sel_lbl.setText(f"{len(self.selected)}개 선택" if self.selected else "")
        if not self.cur:
            self._tile_pos = {}
            self.tiles.resize(max(300, self.scroll.viewport().width()), 40)
            self.tiles.update()
            return
        (tw, th), _sc = self._tile_size()
        width = max(300, self.scroll.viewport().width())
        cols = max(1, int((width - PAD * 2 + GAP) // (tw + GAP)))
        items = self.visible_items()
        rows = (len(items) + cols - 1) // cols
        self._tile_pos = {}
        for n, (i, _it) in enumerate(items):
            x0 = PAD + (n % cols) * (tw + GAP)
            y0 = PAD + (n // cols) * (th + GAP + 18)
            self._tile_pos[(self.kind, i)] = (x0, y0, tw, th)
        self.tiles.resize(width, PAD * 2 + rows * (th + GAP + 18) + 20)
        self.tiles.update()

    def paint_tiles(self, widget):
        painter = QPainter(widget)
        try:
            painter.fillRect(widget.rect(), QColor("#121318"))
            if not self.cur:
                painter.setPen(QColor("#888888"))
                painter.drawText(PAD, PAD + 14, "(모드를 불러오면 여기에 보입니다)")
                return
            items = self.visible_items()
            if not items:
                painter.setPen(QColor("#888888"))
                painter.drawText(PAD, PAD + 14, "(항목 없음)")
                return
            (tw, th), sc = self._tile_size()
            for i, it in items:
                x0, y0, w, h = self._tile_pos[(self.kind, i)]
                try:
                    pixmap = self._game_pixmap(it, w, h) if self._game_on() else None
                    if pixmap is not None:
                        painter.drawPixmap(int(x0 + (w - pixmap.width()) // 2), int(y0 + (h - pixmap.height()) // 2), pixmap)
                    else:
                        PQ.render_item(painter, self.app.project, self.kind, MI.preview_item(self.cur, it), x0, y0, sc,
                                       self.lang, self.upgraded.isChecked(), stacks=self._stacks())
                except Exception as e:  # noqa: BLE001 - 한 칸이 실패해도 나머지는 그린다
                    painter.setPen(QColor("#ff6666"))
                    painter.drawText(int(x0), int(y0 + 20), f"오류: {e}")
                painter.setPen(QColor("#777777"))
                painter.drawText(int(x0), int(y0 + h + 14), it.get("class", ""))
                if (self.kind, i) in self.selected:
                    painter.setPen(QColor("#4da3ff"))
                    painter.drawRect(int(x0 - 4), int(y0 - 4), int(w + 8), int(h + 20))
        finally:
            painter.end()

    def _stacks(self):
        return self.views.stacks if self.views is not None else 3

    def _game_on(self):
        return self.views is not None and self.views.available()

    def _game_pixmap(self, it, w, h):
        """다른 모드 항목의 게임 화면 그림을 칸에 맞춘다. 아직 만드는 중이면 None."""
        upgraded = self.upgraded.isChecked()
        key = (self.cur.root, self.kind, it.get("class"), self.lang, upgraded, self._stacks(), int(w), int(h))
        pixmap = self._pix.get(key)
        if pixmap is not None:
            return pixmap
        img = self.views.ext_image(self.cur, self.kind, it, self.lang, upgraded)
        if img is None:
            return None
        if len(self._pix) > 1500:
            self._pix.clear()
        pixmap = self.views.pixmap(img).scaled(int(w), int(h), Qt.AspectRatioMode.KeepAspectRatio,
                                               Qt.TransformationMode.SmoothTransformation)
        self._pix[key] = pixmap
        return pixmap

    def tile_at(self, point):
        for (kind, i), (x, y, w, h) in self._tile_pos.items():
            if x <= point.x() <= x + w and y <= point.y() <= y + h + 16:
                return (kind, i)
        return None

    def toggle(self, kind, i):
        key = (kind, i)
        if key in self.selected:
            self.selected.discard(key)
        else:
            self.selected.add(key)
        self.refresh()

    def select_all(self):
        for i, _ in self.visible_items():
            self.selected.add((self.kind, i))
        self.refresh()

    def clear_sel(self):
        self.selected = set()
        self.refresh()

    def show_code(self, index):
        items = self.cur.items[self.kind] if self.cur else []
        if index >= len(items):
            return
        it = items[index]
        c = it.get("_cls")
        if c is None:
            _info(self, "이 항목은 코드가 없습니다 (텍스트와 그림만).")
            return
        vars_ = "\n".join(f"//  {v['name']} = {v['value']} (강화 +{v['upgrade']})" for v in it.get("raw_vars", []))
        head = f"// {c.full} : {c.base}\n// 파일: {c.path}\n// 원본 수치:\n{vars_}\n\n"
        self._code_dialogs = getattr(self, "_code_dialogs", [])
        self._code_dialogs.append(_code_window(self, f"원본 코드 - {c.full}", head + MI.fix_decompiled(c.body)))

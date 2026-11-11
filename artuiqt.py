"""AI 그림 설명서 창 / 그림 한꺼번에 적용 창 (Qt 版). Tk 의 artui.py 와 같은 규칙.

계산(설명서 글, 묶음, 그림 짝짓기·처리·적용)은 artguide.py 가 한다. 이 파일은 화면만 맡는다.
"""
import os

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget, QApplication, QSplitter, QHeaderView)

import artguide as AG
import preview_qt as PQ
import projectio as IO
import qtkit as Q

NOTE_BG = (60, 60, 70, 255)
DEBOUNCE_MS = 400


def requests_dir(app):
    base = getattr(app, "app_dir", "") or os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")),
                                                       "sts2_mod_maker")
    return os.path.join(base, "ai_requests")


def open_folder(path):
    try:
        os.startfile(path)          # 윈도 탐색기로 연다 (끌어다 첨부하기 좋게)
    except (OSError, AttributeError):
        pass


def quick_copy(app):
    """설명서를 바로 복사한다. 참고 그림이 있으면 첨부할 폴더도 연다. 돌려 주는 것: 안내 글."""
    guide = AG.quick_guide(app.project, getattr(app, "app_dir", "") or "")
    QApplication.clipboard().setText(guide)
    refs = AG.style_refs(app.project)
    n = len(AG.chosen_slots(app.project))
    if refs:
        folder, _z = AG.make_bundle(app.project, guide, refs, requests_dir(app))
        open_folder(folder)
        return f"그림 설명서({n}장)를 복사했습니다. 열린 폴더의 참고 그림 {len(refs)}장을 함께 첨부하세요."
    return f"그림 설명서({n}장)를 복사했습니다. 채팅 AI 에 붙여 넣으세요."


def _ask(parent, text):
    return QMessageBox.question(parent, IO.APP_TITLE, text) == QMessageBox.StandardButton.Yes


def _info(parent, text):
    QMessageBox.information(parent, IO.APP_TITLE, text)


def _warn(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


def _checker(im):
    """투명 부분이 보이도록 체크무늬 위에 얹은 그림."""
    from PIL import Image, ImageDraw
    bg = Image.new("RGBA", im.size, NOTE_BG)
    tile = 16
    d = ImageDraw.Draw(bg)
    for y in range(0, im.size[1], tile):
        for x in range((y // tile) % 2 * tile, im.size[0], tile * 2):
            d.rectangle((x, y, x + tile - 1, y + tile - 1), fill=(80, 80, 92, 255))
    bg.alpha_composite(im)
    return bg


class ArtGuideDialogQt(QDialog):
    def __init__(self, app, parent=None):
        super().__init__(parent or app)
        self.app = app
        self.setWindowTitle("AI 그림 설명서 만들기")
        self.resize(1100, 760)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.rebuild)
        p = app.project
        root = QVBoxLayout(self)
        root.addWidget(QLabel("채팅 AI (ChatGPT·Claude·Gemini 등) 에 아래 설명서를 그대로 붙여 넣으면, 모드에 필요한 그림을 "
                              "파일 이름까지 맞춰 만들어 줍니다.\n카드 삽화에는 '카드 원화 구도 설계 스킬' 이 들어갑니다. "
                              "다 만든 그림은 '그림 한꺼번에 적용' 으로 한 번에 넣으세요."))
        opt = QHBoxLayout()
        opt.addWidget(QLabel("포함할 그림"))
        self.groups = {}
        saved = AG.guide_options(p)
        for key, text in AG.GROUPS:
            box = QCheckBox(text)
            box.setChecked(key in saved["groups"])
            box.toggled.connect(lambda _c: self._opts_changed())
            self.groups[key] = box
            opt.addWidget(box)
        self.only_missing = QCheckBox("그림이 아직 없는 칸만")
        self.only_missing.setChecked(bool(saved["only_missing"]))
        self.only_missing.toggled.connect(lambda _c: self._opts_changed())
        opt.addWidget(self.only_missing)
        opt.addStretch(1)
        root.addLayout(opt)
        root.addWidget(QLabel("화풍 (모든 그림 공통)"))
        self.style = QPlainTextEdit()
        self.style.setFixedHeight(70)
        self.style.setPlainText(p.get("art_style", ""))
        self.style.textChanged.connect(self._style_changed)
        root.addWidget(self.style)
        refs_row = QHBoxLayout()
        refs_row.addWidget(QLabel("그림체 참고 그림 (AI 에 첨부)"))
        self.ref_strip = QWidget()
        self.ref_layout = QHBoxLayout(self.ref_strip)
        refs_row.addWidget(self.ref_strip, 1)
        for text, slot in (("➕ 그림 추가…", self.add_refs), ("모두 빼기", self.clear_refs)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            refs_row.addWidget(button)
        root.addLayout(refs_row)
        status = QHBoxLayout()
        self.count = QLabel("")
        status.addWidget(self.count)
        self.copied = QLabel("")
        self.copied.setStyleSheet(f"color: {Q.C['success']}; font-weight: bold;")
        status.addWidget(self.copied)
        status.addStretch(1)
        root.addLayout(status)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        root.addWidget(self.text, 1)
        buttons = QHBoxLayout()
        for text, slot in (("📋 설명서 복사", self.copy), ("📦 AI에게 보낼 묶음 (설명서 + 참고 그림)", self.bundle),
                           ("💾 .md 파일로 저장…", self.save), ("🖼 그림 한꺼번에 적용…", self.open_apply)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        self.auto_copy = QCheckBox("창을 열면 자동으로 복사")
        self.auto_copy.setChecked(bool(app.settings.get("art_auto_copy", True)))
        self.auto_copy.toggled.connect(lambda on: app.settings.__setitem__("art_auto_copy", bool(on)))
        buttons.addWidget(self.auto_copy)
        close = QPushButton("닫기")
        close.clicked.connect(self.close)
        buttons.addWidget(close)
        root.addLayout(buttons)
        self.show_refs()
        self.rebuild()
        if self.auto_copy.isChecked():
            self.copy(quiet=True)

    # ---- 그림체 참고 그림 ----
    def refs(self):
        return AG.style_refs(self.app.project)

    def show_refs(self):
        while self.ref_layout.count():
            item = self.ref_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        refs = self.refs()
        if not refs:
            self.ref_layout.addWidget(QLabel("(없음) 원하는 그림체의 그림을 올리면, 설명서가 'AI 에 같이 첨부하라' 고 알려 주고 "
                                             "그 그림의 선·채색·명암·색감을 따르게 합니다."))
            return
        names = AG.ref_names(refs)
        for i, path in enumerate(refs):
            cell = QWidget()
            col = QVBoxLayout(cell)
            col.setContentsMargins(2, 2, 2, 2)
            thumb = QLabel()
            pm = PQ.pixmap(path, 64, 64, "contain")
            if pm is not None:
                thumb.setPixmap(pm)
            else:
                thumb.setText("?")
            col.addWidget(thumb)
            row = QHBoxLayout()
            row.addWidget(QLabel(names[i]))
            remove = QPushButton("✕")
            remove.setFixedWidth(26)
            remove.clicked.connect(lambda _=False, p=path: self.remove_ref(p))
            row.addWidget(remove)
            col.addLayout(row)
            self.ref_layout.addWidget(cell)
        self.ref_layout.addStretch(1)

    def add_refs(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "원하는 그림체의 그림", "", "그림 (*.png *.jpg *.jpeg *.webp)")
        if not fs:
            return
        cur = list(self.app.project.get("art_style_refs") or [])
        cur += [f for f in fs if f not in cur]
        self.app.project["art_style_refs"] = cur[:10]
        self.app.mark_dirty()
        self.show_refs()
        self.rebuild()

    def remove_ref(self, path):
        self.app.project["art_style_refs"] = [p for p in self.app.project.get("art_style_refs") or [] if p != path]
        self.app.mark_dirty()
        self.show_refs()
        self.rebuild()

    def clear_refs(self):
        if self.app.project.get("art_style_refs"):
            self.app.project["art_style_refs"] = []
            self.app.mark_dirty()
            self.show_refs()
            self.rebuild()

    def _opts_changed(self):
        self.app.project["art_guide"] = {"groups": [k for k, box in self.groups.items() if box.isChecked()],
                                         "only_missing": bool(self.only_missing.isChecked())}
        self.app.mark_dirty()
        self.rebuild()

    def _style_changed(self):
        val = self.style.toPlainText().strip()
        if self.app.project.get("art_style", "") != val:
            self.app.project["art_style"] = val
            self.app.mark_dirty()
        self._timer.start()

    def chosen(self):
        return AG.chosen_slots(self.app.project, {"groups": [k for k, box in self.groups.items() if box.isChecked()],
                                                  "only_missing": bool(self.only_missing.isChecked())})

    def guide(self):
        app_dir = getattr(self.app, "app_dir", "") or ""
        return AG.build_guide(self.app.project, self.chosen(), self.style.toPlainText(), app_dir, self.refs())

    def rebuild(self):
        ch = self.chosen()
        self.count.setText(f"그림 {len(ch)}장  (" + ", ".join(
            f"{lab} {sum(1 for s in ch if s['group'] == g)}" for g, lab in AG.GROUPS if any(s['group'] == g for s in ch)) + ")")
        self.text.setPlainText(self.guide())

    def copy(self, quiet=False):
        QApplication.clipboard().setText(self.guide())
        n = len(self.refs())
        self.copied.setText("✔ 설명서를 복사했습니다" + (f" · 참고 그림 {n}장은 '📦 묶음' 으로 첨부" if n else ""))
        if not quiet:
            _info(self, "복사했습니다. 채팅 AI 에 붙여 넣으세요.\n"
                        "(그림을 만들 수 있는 AI 여야 합니다: ChatGPT 이미지 생성, Gemini 등)" +
                  ("\n\n그림체 참고 그림이 있으니 '📦 AI에게 보낼 묶음' 으로 폴더를 열어 함께 첨부하세요." if n else ""))

    def bundle(self):
        folder, zpath = AG.make_bundle(self.app.project, self.guide(), self.refs(), requests_dir(self.app))
        self.copy(quiet=True)
        open_folder(folder)
        _info(self, "설명서를 복사했고, 아래 폴더를 열었습니다.\n"
                    f"{folder}\n\n채팅 AI 에 설명서를 붙여 넣고, 폴더의 style_ref 그림들을 끌어다 함께 첨부하세요.\n"
                    f"(zip 하나로 올리려면: {os.path.basename(zpath)})")

    def save(self):
        path, _ = QFileDialog.getSaveFileName(self, "설명서 저장", f"{self.app.project['mod'].get('id', 'mod')}_그림설명서.md",
                                              "Markdown (*.md)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.guide())

    def open_apply(self):
        self.close()
        dialog = ArtApplyDialogQt(self.app, parent=self.app)
        dialog.show()


class ArtApplyDialogQt(QDialog):
    def __init__(self, app, files=None, parent=None):
        super().__init__(parent or app)
        self.app = app
        self.setWindowTitle("그림 한꺼번에 적용")
        self.resize(1180, 720)
        self.slot_list = AG.slots(app.project)
        self.files = []
        self.assign = {}
        self._busy = False
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        for text, slot in (("📦 zip 고르기…", self.pick_zip), ("📁 폴더 고르기…", self.pick_folder),
                           ("그림 파일 고르기…", self.pick_files)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            top.addWidget(button)
        self.src_label = QLabel("AI 가 준 zip 이나 그림 폴더를 고르세요. 파일 이름(card_strike.png) 또는 #번호(3.png)로 칸을 찾습니다.")
        top.addWidget(self.src_label, 1)
        root.addLayout(top)
        opt = QHBoxLayout()
        self.remove_bg = QCheckBox("투명 배경 칸은 단색 배경을 자동으로 지우기")
        self.remove_bg.setChecked(True)
        self.remove_bg.toggled.connect(lambda _c: self.show_preview())
        opt.addWidget(self.remove_bg)
        opt.addWidget(QLabel("크기는 게임 크기로 자동 맞춤 (카드 1000×760 · 아이콘 256 · 초상화 132×195 · 지도 49×64 …)"))
        opt.addStretch(1)
        root.addLayout(opt)
        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["#", "칸", "넣을 그림", "지금"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.on_select)
        split.addWidget(self.table)
        right = QWidget()
        rc = QVBoxLayout(right)
        self.pv_title = QLabel("")
        self.pv_title.setStyleSheet("font-weight: bold;")
        self.pv_title.setWordWrap(True)
        rc.addWidget(self.pv_title)
        row = QHBoxLayout()
        row.addWidget(QLabel("그림:"))
        self.file_combo = QComboBox()
        self.file_combo.activated.connect(lambda _i: self.choose_file())
        row.addWidget(self.file_combo, 1)
        clear = QPushButton("비우기")
        clear.clicked.connect(self.clear_one)
        row.addWidget(clear)
        rc.addLayout(row)
        self.canvas = QLabel()
        self.canvas.setFixedSize(440, 440)
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setStyleSheet(f"background: {Q.C['stage']};")
        rc.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignHCenter)
        self.pv_note = QLabel("")
        self.pv_note.setWordWrap(True)
        self.pv_note.setStyleSheet(f"color: {Q.C['muted']};")
        rc.addWidget(self.pv_note)
        rc.addStretch(1)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        bottom = QHBoxLayout()
        self.summary = QLabel("")
        bottom.addWidget(self.summary, 1)
        cancel = QPushButton("취소")
        cancel.clicked.connect(self.reject)
        bottom.addWidget(cancel)
        self.apply_btn = QPushButton("✔ 적용")
        self.apply_btn.clicked.connect(self.do_apply)
        bottom.addWidget(self.apply_btn)
        root.addLayout(bottom)
        self.refresh()
        if files:
            self.load_files(files)

    # ---- 고르기 ----
    def pick_zip(self):
        z, _ = QFileDialog.getOpenFileName(self, "AI 가 준 그림 zip", "", "zip (*.zip)")
        if not z:
            return
        try:
            files = AG.extract_zip(z)
        except Exception as exc:  # noqa: BLE001
            _warn(self, f"zip 을 풀지 못했습니다: {exc}")
            return
        if not files:
            _info(self, "zip 안에 그림(png·jpg·webp)이 없습니다.")
            return
        self.load_files(files)

    def pick_folder(self):
        d = QFileDialog.getExistingDirectory(self, "AI 가 만든 그림 폴더")
        if d:
            self.load_files(AG.list_images(d))

    def pick_files(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "그림 고르기", "", "그림 (*.png *.jpg *.jpeg *.webp)")
        if fs:
            self.load_files(list(fs))

    def load_files(self, files):
        files = [f for f in files if "_적용됨" not in f.replace("\\", "/").split("/")]
        self.files = files
        self.assign = AG.match_files(self.slot_list, files)
        text = f"그림 {len(files)}개 · 짝지어진 칸 {len(self.assign)}개"
        if len(files) > len(self.assign):
            text += f" · 남은 그림 {len(files) - len(self.assign)}개 (칸을 골라 직접 지정)"
        self.src_label.setText(text)
        self.refresh()

    def refresh(self):
        current_row = self.table.currentRow()
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        for s in self.slot_list:
            row = self.table.rowCount()
            self.table.insertRow(row)
            f = self.assign.get(s["key"])
            now = "있음" if s["current"] and os.path.isfile(s["current"]) else "-"
            for col, value in enumerate((str(s["num"]), f"{s['title']} · {s['name']}  [{s['key']}]",
                                         os.path.basename(f) if f else "", now)):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, s["key"])
                self.table.setItem(row, col, item)
        self.table.blockSignals(False)
        if 0 <= current_row < self.table.rowCount():
            self.table.selectRow(current_row)
        self.summary.setText(f"적용할 그림 {len(self.assign)}장 / 칸 {len(self.slot_list)}개")

    def cur_slot(self):
        row = self.table.currentRow()
        if row < 0 or row >= len(self.slot_list):
            return None
        return self.slot_list[row]

    def on_select(self):
        s = self.cur_slot()
        if not s:
            return
        self.pv_title.setText(f"#{s['num']} {s['title']} — {s['name']}")
        f = self.assign.get(s["key"])
        self.file_combo.clear()
        self.file_combo.addItem("(없음)")
        for path in self.files:
            self.file_combo.addItem(os.path.basename(path))
        self.file_combo.setCurrentIndex(self.files.index(f) + 1 if f in self.files else 0)
        self.show_preview()

    def choose_file(self):
        s = self.cur_slot()
        if not s:
            return
        i = self.file_combo.currentIndex()
        if i <= 0:
            self.assign.pop(s["key"], None)
        else:
            f = self.files[i - 1]
            for k, v in list(self.assign.items()):       # 한 그림은 한 칸에만
                if v == f and k != s["key"]:
                    self.assign.pop(k)
            self.assign[s["key"]] = f
        self.refresh()
        self.show_preview()

    def clear_one(self):
        s = self.cur_slot()
        if s:
            self.assign.pop(s["key"], None)
            self.refresh()
            self.show_preview()

    def show_preview(self):
        from PIL import Image
        s = self.cur_slot()
        self.canvas.clear()
        if not s:
            return
        w, h, mode, tr, label = AG.SPECS[s["kind"]]
        src = self.assign.get(s["key"]) or (s["current"] if s["current"] and os.path.isfile(s["current"]) else "")
        note = f"{label}: " + (f"{w}×{h} " if w else "") + {"cover": "꽉 채우고 가운데 자르기", "contain": "비율 유지해 맞춤",
                                                          "sprite": "크기 유지"}[mode] + (" · 투명 배경" if tr else "")
        if not src:
            self.pv_note.setText(note + "\n(그림 없음)")
            return
        try:
            im = AG.process(src, s["kind"], self.remove_bg.isChecked()) if self.assign.get(s["key"]) \
                else Image.open(src).convert("RGBA")
        except Exception as exc:  # noqa: BLE001
            self.pv_note.setText(f"그림을 읽지 못했습니다: {exc}")
            return
        bg = _checker(im)
        r = min(430 / bg.size[0], 430 / bg.size[1], 4.0)
        show = bg.resize((max(1, int(bg.size[0] * r)), max(1, int(bg.size[1] * r))),
                         Image.NEAREST if r > 1.5 else Image.LANCZOS)
        self.canvas.setPixmap(PQ._qpixmap(show))
        self.pv_note.setText(note + f"\n결과 {im.size[0]}×{im.size[1]}" +
                             ("" if self.assign.get(s["key"]) else "  (지금 들어 있는 그림)"))

    def do_apply(self):
        if not self.assign:
            _info(self, "적용할 그림이 없습니다. 폴더를 고르세요.")
            return
        out = AG.out_dir_for(self.assign.values())
        replaced = sum(1 for s in self.slot_list if s["key"] in self.assign and s["current"])
        if replaced and not _ask(self, f"{len(self.assign)}장을 적용합니다. 이미 그림이 있는 칸 {replaced}개는 "
                                       "새 그림으로 바뀝니다 (Ctrl+Z 로 되돌릴 수 있음).\n계속할까요?"):
            return
        if self._busy:
            return
        self._busy = True
        self.apply_btn.setEnabled(False)

        def progress(i, n, s):
            self.summary.setText(f"적용 중… {i}/{n}  {s['title']} · {s['name']}")
            QApplication.processEvents()
        try:
            done = AG.apply(self.app.project, self.slot_list, self.assign, out, self.remove_bg.isChecked(),
                            log=self.app.log, progress=progress)
        except Exception as exc:  # noqa: BLE001
            self._busy = False
            self.apply_btn.setEnabled(True)
            _warn(self, f"적용하지 못했습니다: {exc}")
            return
        app = self.app
        self._busy = False
        self.accept()
        app.mark_dirty()
        app.load_all()
        app.commit_snapshot()
        app.status(f"✔ 그림 {len(done)}장을 적용했습니다", 6000)
        _info(self, f"{len(done)}장을 적용했습니다.\n다듬은 그림은 '{out}' 에 저장했습니다.")

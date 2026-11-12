"""AI(채팅) 복붙 연동 창 (Qt 版): ① 요청을 적고 설명서 복사  ② AI 결과 붙여넣기 (읽기·검사·미리보기·넣기).

Tk 의 aiui.py 와 같은 흐름. 설명서 글(aiguide)과 답 읽기·넣기(aipaste)는 화면과 무관한 모듈이 한다.
"""
import re

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel,
                               QMessageBox, QPlainTextEdit, QPushButton, QRadioButton, QTableWidget,
                               QTableWidgetItem, QTabWidget, QVBoxLayout, QWidget, QButtonGroup, QSplitter, QHeaderView)

import aiguide as AG
import aipaste as AP
import preview_qt as PQ
import projectio as IO
import qtkit as Q

TITLE = "AI로 만들기"
EXAMPLE = ("예) 불씨를 쌓았다가 터뜨리는 공격 카드 3장과, 불씨가 10 이상이면 에너지를 주는 유물 1개를 만들어줘. "
           "한국어·영어·중국어 이름 모두.")
READ_DELAY_MS = 700
MSG_KIND = {"err": "• ", "warn": "• ", "fix": "• "}


def _ask(parent, text):
    return QMessageBox.question(parent, TITLE, text) == QMessageBox.StandardButton.Yes


def _info(parent, text):
    QMessageBox.information(parent, TITLE, text)


def _warn(parent, text):
    QMessageBox.warning(parent, TITLE, text)


class GuidePageQt(QWidget):
    """요청을 적고 → 설명서(요청 포함)를 복사 → 채팅 AI 에 붙여 넣기."""

    def __init__(self, app, host):
        super().__init__()
        self.app = app
        self.host = host
        root = QVBoxLayout(self)
        head = QLabel("ChatGPT · Claude · Gemini 같은 채팅 AI에게 카드·유물·물약·파워·기믹을 만들거나 고치게 합니다.")
        head.setStyleSheet("font-weight: bold;")
        root.addWidget(head)
        steps = QLabel("1. 아래에 만들고 싶은 것을 적고 '설명서 복사'를 누릅니다.\n"
                       "2. AI 채팅창에 붙여넣고 보냅니다. (설명서에 형식·선택지·지금 프로젝트의 ID 가 다 들어 있습니다)\n"
                       "3. AI 의 답을 통째로 복사해서 '② 답변 붙여넣기'에 넣으면 검사·미리보기 후 프로젝트에 들어갑니다.")
        steps.setStyleSheet(f"color: {Q.C['muted']};")
        root.addWidget(steps)
        root.addWidget(QLabel("AI에게 시킬 내용"))
        self.req = QPlainTextEdit()
        self.req.setPlaceholderText(EXAMPLE)
        self.req.setFixedHeight(120)
        self.req.textChanged.connect(self._size)
        root.addWidget(self.req)
        opt = QHBoxLayout()
        self.blocks = QCheckBox("블록 코딩 설명 포함")
        self.blocks.setChecked(True)
        self.blocks.setToolTip("반복·조건·손패 조작·소환 같은 복잡한 능력을 만들 수 있게 합니다. 끄면 설명서가 짧아집니다.")
        self.blocks.toggled.connect(lambda _c: self._size())
        opt.addWidget(self.blocks)
        self.proj = QCheckBox("지금 프로젝트 목록 포함")
        self.proj.setChecked(True)
        self.proj.setToolTip("있는 카드·파워·태그·소환수 ID 를 알려줘서 겹치지 않고, 참조할 수 있게 합니다. "
                             "지금 있는 파워·기믹의 전체 내용도 넣어서 AI 가 고칠 수 있게 합니다.")
        self.proj.toggled.connect(lambda _c: self._size())
        opt.addWidget(self.proj)
        opt.addStretch(1)
        self.size_lbl = QLabel("")
        self.size_lbl.setStyleSheet(f"color: {Q.C['muted']};")
        opt.addWidget(self.size_lbl)
        root.addLayout(opt)
        buttons = QHBoxLayout()
        copy = QPushButton("📋 설명서 복사")
        copy.clicked.connect(self.copy)
        buttons.addWidget(copy)
        save = QPushButton("파일로 저장…")
        save.clicked.connect(self.save)
        buttons.addWidget(save)
        paste = QPushButton("② 답변 붙여넣기 →")
        paste.clicked.connect(lambda: self.host.tabs.setCurrentWidget(self.host.paste_page))
        buttons.addWidget(paste)
        buttons.addStretch(1)
        root.addLayout(buttons)
        self.status = QLabel("")
        self.status.setStyleSheet(f"color: {Q.C['success']};")
        root.addWidget(self.status)
        root.addStretch(1)
        self._size()

    def _request(self):
        return self.req.toPlainText().strip()

    def prompt(self):
        return AG.build_prompt(self.app.project, self._request(), self.blocks.isChecked(), self.proj.isChecked())

    def _size(self):
        self.size_lbl.setText(f"설명서 길이 약 {len(self.prompt()):,}자")

    def copy(self):
        text = self.prompt()
        QApplication.clipboard().setText(text)
        self.status.setText(f"복사했습니다 ({len(text):,}자). AI 채팅창에 붙여넣고 보내세요."
                            + ("" if self._request() else "  ※ 요청을 비워 두었으니 붙여넣은 뒤 끝에 요청을 적으세요."))

    def save(self):
        path, _ = QFileDialog.getSaveFileName(self, "설명서 저장", "sts2_ai_guide.md", "Markdown (*.md);;텍스트 (*.txt)")
        if path:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self.prompt())
            self.status.setText(f"저장했습니다: {path}")


class PastePageQt(QWidget):
    """AI 답 붙여넣기 → 읽기·자동 고침 → 검사 → 미리보기 → 넣기."""

    def __init__(self, app, host):
        super().__init__()
        self.app = app
        self.host = host
        self.patch = None
        self.errors, self.warnings = [], []
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(READ_DELAY_MS)
        self._timer.timeout.connect(self.read)
        root = QVBoxLayout(self)
        top = QHBoxLayout()
        head = QLabel("AI 의 답을 통째로 붙여 넣으세요 (설명 글이 섞여 있어도 JSON 부분만 읽습니다).")
        head.setStyleSheet("font-weight: bold;")
        top.addWidget(head)
        top.addStretch(1)
        again = QPushButton("① 설명서 다시 복사…")
        again.clicked.connect(lambda: self.host.tabs.setCurrentWidget(self.host.guide_page))
        top.addWidget(again)
        root.addLayout(top)
        self.src = QPlainTextEdit()
        self.src.setFixedHeight(140)
        self.src.setStyleSheet("font-family: Consolas;")
        self.src.textChanged.connect(lambda: self._timer.start())
        root.addWidget(self.src)
        bar = QHBoxLayout()
        paste = QPushButton("📋 클립보드에서 붙여넣기")
        paste.clicked.connect(self.paste_clip)
        bar.addWidget(paste)
        again_read = QPushButton("다시 읽기")
        again_read.clicked.connect(self.read)
        bar.addWidget(again_read)
        self.keep = QCheckBox("같은 ID 는 바꾸지 말고 새 ID 로 추가")
        self.keep.setToolTip("끄면(기본) AI 가 기존 항목과 같은 ID 를 쓴 경우 그 항목을 AI 버전으로 바꿉니다 (되돌리기로 되돌릴 수 있음).")
        self.keep.toggled.connect(lambda _c: self.recheck())
        bar.addWidget(self.keep)
        bar.addStretch(1)
        root.addLayout(bar)

        split = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(split, 1)
        left = QWidget()
        lc = QVBoxLayout(left)
        lc.addWidget(QLabel("읽은 항목 (더블클릭 = 넣기/빼기)"))
        self.tree = QTableWidget(0, 4)
        self.tree.setHorizontalHeaderLabels(["이름", "넣기", "종류", "ID"])
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tree.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tree.itemSelectionChanged.connect(self.show)
        self.tree.itemDoubleClicked.connect(lambda _it: self.toggle())
        lc.addWidget(self.tree, 1)
        lc.addWidget(QLabel("문제 · 자동으로 고친 것"))
        self.msg = QPlainTextEdit()
        self.msg.setReadOnly(True)
        self.msg.setFixedHeight(150)
        lc.addWidget(self.msg)
        split.addWidget(left)

        right = QWidget()
        rc = QVBoxLayout(right)
        pv = QHBoxLayout()
        pv.addWidget(QLabel("미리보기"))
        pv.addStretch(1)
        self.up = QCheckBox("강화(+)")
        self.up.toggled.connect(lambda _c: self.show())
        pv.addWidget(self.up)
        self._lang_group = QButtonGroup(self)
        self.lang = "ko"
        for i, (value, text) in enumerate((("zh", "中文"), ("en", "EN"), ("ko", "한국어"))):
            button = QRadioButton(text)
            button.setChecked(value == "ko")
            button.toggled.connect(lambda on, v=value: on and self.set_lang(v))
            self._lang_group.addButton(button, i)
            pv.addWidget(button)
        rc.addLayout(pv)
        self.canvas = QLabel()
        self.canvas.setFixedSize(300, 380)
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.canvas.setStyleSheet(f"background: {Q.C['stage']};")
        rc.addWidget(self.canvas, 0, Qt.AlignmentFlag.AlignHCenter)
        self.desc = QLabel("")
        self.desc.setWordWrap(True)
        rc.addWidget(self.desc)
        rc.addStretch(1)
        split.addWidget(right)
        split.setStretchFactor(0, 1)

        bot = QHBoxLayout()
        self.fix_btn = QPushButton("✉ AI에게 보낼 수정 요청 복사")
        self.fix_btn.setToolTip("오류·경고를 AI 에게 그대로 보낼 문장으로 복사합니다. AI 채팅창에 붙여넣으면 고친 JSON 을 다시 줍니다.")
        self.fix_btn.clicked.connect(self.copy_fix)
        bot.addWidget(self.fix_btn)
        self.dep_btn = QPushButton("필요한 항목 함께 선택")
        self.dep_btn.clicked.connect(self.include_dependencies)
        bot.addWidget(self.dep_btn)
        self.summary = QLabel("")
        bot.addWidget(self.summary, 1)
        close = QPushButton("닫기")
        close.clicked.connect(self.host.reject)
        bot.addWidget(close)
        self.ok_btn = QPushButton("✔ 프로젝트에 넣기")
        self.ok_btn.clicked.connect(self.commit)
        bot.addWidget(self.ok_btn)
        root.addLayout(bot)
        self.render_empty()

    def set_lang(self, lang):
        self.lang = lang
        self.show()

    # ---- 읽기 ----
    def paste_clip(self):
        text = QApplication.clipboard().text()
        if not text.strip():
            _info(self, "클립보드가 비어 있습니다. AI 의 답을 복사한 뒤 눌러 주세요.")
            return
        self.src.setPlainText(text)
        self.read()

    def read(self):
        self._timer.stop()
        text = self.src.toPlainText().strip()
        if not text:
            self.patch = None
            self.render_empty()
            return
        self.patch = AP.read_patch(text, self.app.project)
        self.recheck()

    def recheck(self):
        if self.patch is None:
            return
        self.errors, self.warnings = (AP.check(self.app.project, self.patch, self.keep.isChecked())
                                      if self.patch.items and not self.patch.errors else ([], []))
        self.render()

    def include_dependencies(self):
        for row in AP.missing_selections(self.patch):
            row["take"] = True
        self.recheck()

    # ---- 그리기 ----
    def render_empty(self):
        self.dep_btn.hide()
        self.tree.setRowCount(0)
        self.msg.setPlainText("AI 의 답을 붙여 넣으면 여기에 검사 결과가 나옵니다.")
        self.canvas.clear()
        self.desc.setText("")
        self.ok_btn.setEnabled(False)
        self.fix_btn.setEnabled(False)
        self.summary.setText("")

    def _all_errors(self):
        return (self.patch.errors if self.patch else []) + self.errors

    def render(self):
        p = self.patch
        self.tree.setRowCount(0)
        for i, x in enumerate(p.items):
            it = x["item"]
            state = "기존 항목 바꿈" if x["exists"] and not self.keep.isChecked() else ("새 ID 로 추가" if x["exists"] else "새로 추가")
            row = self.tree.rowCount()
            self.tree.insertRow(row)
            cells = ((it.get("name_ko") or it["id"]), "✔" if x["take"] else "—", AP.NOUN[x["kind"]], it["id"])
            for col, value in enumerate(cells):
                cell = QTableWidgetItem(value)
                cell.setData(Qt.ItemDataRole.UserRole, i)
                self.tree.setItem(row, col, cell)
            self.tree.setItem(row, 3, QTableWidgetItem(it["id"]))
            self.tree.item(row, 3).setToolTip(state)
        lines = []
        errs = self._all_errors()
        missing = AP.missing_selections(p)
        if missing:
            lines.append("함께 필요한 항목: " + ", ".join(x["item"].get("name_ko") or x["item"]["id"] for x in missing))
            self.dep_btn.show()
        else:
            self.dep_btn.hide()
        if errs:
            lines.append(f"오류 {len(errs)}개 — 고쳐야 넣을 수 있습니다")
            lines += ["• " + e for e in errs]
        if self.warnings:
            lines.append(f"경고 {len(self.warnings)}개")
            lines += ["• " + w for w in self.warnings]
        if p.fixes:
            lines.append(f"자동으로 고친 것 {len(p.fixes)}개")
            lines += ["• " + f for f in p.fixes]
        if not errs and not self.warnings and not p.fixes:
            lines.append("문제 없음 ✔")
        self.msg.setPlainText("\n".join(lines))
        n = sum(1 for x in p.items if x["take"])
        self.ok_btn.setEnabled(bool(n and not errs and not missing))
        self.fix_btn.setEnabled(bool(errs or self.warnings))
        cnt = {}
        for x in p.items:
            if x["take"]:
                cnt[AP.NOUN[x["kind"]]] = cnt.get(AP.NOUN[x["kind"]], 0) + 1
        self.summary.setText(("넣을 것: " + ", ".join(f"{k} {v}" for k, v in cnt.items())) if cnt else "넣을 것 없음")
        if p.items:
            self.tree.selectRow(0)
        else:
            self.canvas.clear()
            self.desc.setText("")

    def _selected(self):
        row = self.tree.currentRow()
        if row < 0 or self.patch is None or row >= len(self.patch.items):
            return None
        return row

    def toggle(self):
        row = self._selected()
        if row is None:
            return
        x = self.patch.items[row]
        x["take"] = not x["take"]
        self.recheck()
        self.tree.selectRow(row)

    def show(self):
        row = self._selected()
        if row is None:
            return
        x = self.patch.items[row]
        desc, tmp, item = AP.describe(self.app.project, x["kind"], x["item"], self.lang)
        try:
            import previewcore as PV
            desc = PV.fill_values(tmp, desc, item, bool(self.up.isChecked()))
        except Exception:  # noqa: BLE001 - 숫자 채우기에 실패하면 원문 그대로
            pass
        self.desc.setText(re.sub(r"\[/?[a-z]+\]", "", desc))
        self.canvas.clear()
        if x["kind"] in AP.GIMMICKS or x["kind"] == "power":
            old = self._old(x)
            if old is not None:   # 고치는 파워·기믹은 그림 대신 변경 전 → 변경 후
                self.canvas.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
                self.canvas.setText("변경 전 → 변경 후\n\n" + ("\n".join(AP.change_lines(old, x["item"])) or "변경 없음"))
                self.canvas.setStyleSheet(f"background: {Q.C['stage']}; color: white;")
                return
            if x["kind"] in AP.GIMMICKS:
                return
        self.canvas.setStyleSheet(f"background: {Q.C['stage']};")
        self.canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
        assets = self.app.game_assets()
        if assets is None:
            self.canvas.setText("게임 파일이 있으면 게임 모습으로 보여 줍니다.")
            return
        try:
            import ingame
            im = ingame.compose(assets, tmp, x["kind"], item, self.lang, bool(self.up.isChecked()))
        except Exception as ex:  # noqa: BLE001
            self.canvas.setText(f"미리보기 실패: {ex}")
            return
        k = min(300 / im.width, 380 / im.height)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
        self.canvas.setPixmap(PQ._qpixmap(im))

    def _old(self, x):
        """이 답이 고치는 기존 파워·기믹 (새로 만들거나 '새 ID 로 추가'면 None)."""
        if not x["exists"] or self.keep.isChecked():
            return None
        pool = ((self.app.project.get("gimmicks") or {}).get(AP.GIMMICKS[x["kind"]][0], []) if x["kind"] in AP.GIMMICKS
                else self.app.project.get("powers", []))
        return next((r for r in pool if r["id"] == x["item"]["id"]), None)

    # ---- 버튼 ----
    def copy_fix(self):
        from aiguide import fix_request
        text = fix_request(self._all_errors(), self.warnings, self.patch.fixes if self.patch else None)
        QApplication.clipboard().setText(text)
        self.summary.setText("복사했습니다. AI 채팅창에 붙여넣고, 받은 새 답을 위에 다시 붙여 넣으세요.")

    def commit(self):
        if self.patch is None or self._all_errors():
            return
        replaced = [x for x in self.patch.items if x["take"] and x["exists"] and not self.keep.isChecked()]
        if replaced and not _ask(self, "이미 있는 항목을 AI 버전으로 바꿉니다:\n" +
                                 "\n".join(f"• {AP.NOUN[x['kind']]} {x['item'].get('name_ko')} ({x['item']['id']})"
                                           for x in replaced) +
                                 "\n\n계속할까요? (되돌리기로 되돌릴 수 있습니다)"):
            return
        added = AP.apply(self.app.project, self.patch, self.keep.isChecked())
        app = self.app
        app.mark_dirty()
        app.load_all()
        app.log("AI 결과를 넣었습니다: " + ", ".join(f"{AP.NOUN[k]} {i}" for k, i in added))
        self.host.accept()
        if added:                # 파워는 먼저 들어가므로, 카드·유물·물약이 있으면 그쪽으로 데려간다
            first = next(((k, i) for k, i in added if k != "power"), added[0])
            app.goto_any(*first)
        app.status(f"AI 결과 {len(added)}개를 넣었습니다 (되돌리기로 되돌릴 수 있음)")


class AIWorkflowQt(QDialog):
    def __init__(self, app, paste=False, text=""):
        super().__init__(app)
        self.setWindowTitle(TITLE)
        self.resize(1060, 760)
        root = QVBoxLayout(self)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs)
        self.guide_page = GuidePageQt(app, self)
        self.paste_page = PastePageQt(app, self)
        self.tabs.addTab(self.guide_page, "① 요청 복사")
        self.tabs.addTab(self.paste_page, "② 답변 붙여넣기 · 변경 확인")
        self.tabs.setCurrentWidget(self.paste_page if paste else self.guide_page)
        if text:
            self.paste_page.src.setPlainText(text)
            self.paste_page.read()

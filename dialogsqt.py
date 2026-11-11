"""작은 대화상자 모음 (Qt 版): 아키텍트 대사, 원본 수치 편집.

Tk 의 ArchitectDialog · RawVarDialog 와 같은 규칙을 쓴다.
"""
import modgen as M
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPlainTextEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)

import projectio as IO
import qtkit as Q

LANGS = (("ko", "한국어"), ("en", "English"), ("zh", "中文"))


def _warn(parent, text):
    QMessageBox.warning(parent, IO.APP_TITLE, text)


class ArchitectDialogQt(QDialog):
    """3막을 깬 뒤 아키텍트와의 대화 (언어별). '아키텍트: …' / '나: …' 줄, '---' 로 대화 구분."""

    def __init__(self, parent, project, ch=None):
        super().__init__(parent)
        self.setWindowTitle("아키텍트 대사")
        self.project = project
        self.ch = ch if ch is not None else project["character"]
        # 가져온 캐릭터: 원래 모드에 있던 대사를 처음 내용으로 (그대로 두면 원래 대사 유지)
        self.base = {lang: self._base_text(lang) for lang, _t in LANGS}
        root = QVBoxLayout(self)
        root.addWidget(QLabel("한 줄에 한 마디: '아키텍트: …' 또는 '나: …' (캐릭터 이름도 됨). '---' 로 대화를 나눕니다.\n"
                              "첫 번째 대화는 이 캐릭터로 처음 이겼을 때, 두 번째는 두 번째 승리 때 … 나오고, "
                              "그 뒤에는 모든 대화가 무작위로 다시 나옵니다.\n비워 두면 기본 대사를 씁니다. "
                              "중국어를 비우면 영어 → 기본 중국어 대사 순서로 씁니다."))
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self.texts = {}
        self.status = {}
        names = (self.ch.get("name_ko"), self.ch.get("name_en"), self.ch.get("name_zh"))
        self._names = names
        for lang, title in LANGS:
            box = QPlainTextEdit()
            box.setPlainText(self.ch.get(f"architect_{lang}") or self.base[lang])
            box.textChanged.connect(lambda l=lang: self._check(l))
            wrap = QVBoxLayout()
            wrap.addWidget(box, 1)
            status = QLabel("")
            wrap.addWidget(status)
            holder = QWidget()
            holder.setLayout(wrap)
            self.tabs.addTab(holder, title)
            self.texts[lang] = box
            self.status[lang] = status
            self._check(lang)
        buttons = QHBoxLayout()
        reset = QPushButton("이 언어를 기본 대사로")
        reset.clicked.connect(self.reset)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        root.addLayout(buttons)
        dialog_buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        dialog_buttons.accepted.connect(self.ok)
        dialog_buttons.rejected.connect(self.reject)
        root.addWidget(dialog_buttons)
        self.resize(700, 520)

    def _base_text(self, lang):
        convs = M.architect_from_loc(self.project, self.ch.get("loc_id"), lang)
        if convs:
            return M.architect_text(convs, lang)
        return M.architect_text(M.default_architect(lang), lang)

    def _check(self, lang):
        convs = M.architect_dialogues(self.texts[lang].toPlainText(), self._names)
        label = self.status[lang]
        if convs:
            label.setText(f"✔ 대화 {len(convs)}개 · " + ", ".join(f"{len(c)}마디" for c in convs))
            label.setStyleSheet(f"color: {Q.C['success']};")
        else:
            label.setText("✖ 읽을 수 있는 줄이 없습니다 — 기본 대사를 씁니다")
            label.setStyleSheet(f"color: {Q.C['danger']};")

    def reset(self):
        lang = LANGS[self.tabs.currentIndex()][0]
        self.texts[lang].setPlainText(M.architect_text(M.default_architect(lang), lang))

    def ok(self):
        for lang, box in self.texts.items():
            txt = box.toPlainText().strip()
            same_as_default = txt == self.base[lang].strip()
            self.ch[f"architect_{lang}"] = "" if same_as_default else txt
        self.accept()


class RawVarDialogQt(QDialog):
    """원본 수치(코드에 있던 값) 하나를 고친다. 결과는 (수치, 강화 시 +)."""

    def __init__(self, parent, var):
        super().__init__(parent)
        self.setWindowTitle(f"원본 수치: {var.get('name')}")
        self.result = None
        grid = QGridLayout(self)
        grid.addWidget(QLabel(f"{var.get('name')}  ({var.get('type')})"), 0, 0, 1, 2)
        grid.addWidget(QLabel("수치"), 1, 0)
        self.value = QLineEdit(str(var.get("value", 0)))
        grid.addWidget(self.value, 1, 1)
        grid.addWidget(QLabel("강화 시 +"), 2, 0)
        self.up = QLineEdit(str(var.get("upgrade", 0)))
        grid.addWidget(self.up, 2, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.ok)
        buttons.rejected.connect(self.reject)
        grid.addWidget(buttons, 3, 0, 1, 2)

    def ok(self):
        try:
            v, u = float(self.value.text()), float(self.up.text() or 0)
        except ValueError:
            _warn(self, "숫자를 입력하세요.")
            return
        self.result = (int(v) if v.is_integer() else v, int(u) if u.is_integer() else u)
        self.accept()

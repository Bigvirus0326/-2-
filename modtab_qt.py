"""'모드 / 빌드' 탭의 Qt 시험판. Tk 의 sts2_mod_maker.ModTab 과 같은 입력 칸·준비 상태 표시를 그린다.

아직 옮기지 않은 것: ①~④ 단계의 실제 동작(검사·생성·빌드·게시)은 콜백으로 넘긴다.
실행 예: python modtab_qt.py
"""
import os
import shutil
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QFileDialog, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout, QWidget)

import qtkit as Q

def _caption(text):
    """칸 이름: 입력 칸과 붙어 보이지 않도록 오른쪽 여백을 둔다."""
    caption = QLabel(text)
    caption.setContentsMargins(0, 0, 14, 0)
    return caption


INFO_FIELDS = [("id", "모드 ID (영문, 대문자 시작)", 0, 0), ("name", "표시 이름", 0, 2),
               ("author", "제작자", 1, 0), ("version", "버전", 1, 2),
               ("description", "설명", 2, 0), ("min_game_version", "최소 게임 버전", 3, 0),
               ("baselib_version", "BaseLib 버전 (* = 최신)", 3, 2)]
ENV_FIELDS = [("out_dir", "출력 폴더", "dir"), ("sts2_path", "슬더스2 설치 폴더", "dir"),
              ("godot_path", "MegaDot 4.5.1 실행 파일 (pck용)", "file")]
STEPS = [("① 검사", "입력 내용에 문제가 없는지 확인"),
         ("② 생성", "출력 폴더에 C# / Godot 모드 프로젝트 파일 쓰기"),
         ("③ 빌드", "dotnet build → 게임 mods 폴더에 dll 복사 (코드만)"),
         ("④ 게시", "③ + MegaDot로 그림/텍스트가 든 .pck 생성 (게임에서 쓰려면 필요)")]
STATE_COLOR = {"ok": Q.C["success"], "warn": Q.C["warn"], "bad": Q.C["danger"]}


def check_lines(settings):
    """준비 상태 줄 (상태, 글). sts2_mod_maker.ModTab.run_checks 와 같은 판정."""
    lines = []
    dotnet = shutil.which("dotnet")
    lines.append(("ok" if dotnet else "bad", ".NET SDK (dotnet) " + ("설치됨" if dotnet else "없음 → https://dotnet.microsoft.com 에서 .NET SDK 9 이상 설치")))
    sp = settings.get("sts2_path", "")
    dll = os.path.join(sp, "data_sts2_windows_x86_64", "sts2.dll") if sp else ""
    ok = bool(dll) and os.path.isfile(dll)
    lines.append(("ok" if ok else "bad", "슬더스2 " + ("찾음" if ok else "못 찾음 → 설치 폴더를 지정하세요")))
    mods = os.path.join(sp, "mods") if sp else ""
    bl = bool(mods) and os.path.isdir(mods) and any(n.lower().startswith("baselib") for n in os.listdir(mods))
    lines.append(("ok" if bl else "warn", "BaseLib 모드 " + ("설치됨" if bl else "mods 폴더에 없음 → 'BaseLib 받기'로 설치해야 게임에서 모드가 켜집니다")))
    g = settings.get("godot_path", "")
    gok = bool(g) and os.path.isfile(g)
    lines.append(("ok" if gok else "warn", "MegaDot " + ("찾음" if gok else "미설정 → ④ 게시(pck)에 필요합니다 (③ 빌드는 없어도 됨)")))
    return lines


class ModTabQt(QWidget):
    def __init__(self, mod, settings, actions=None, on_settings_change=None, on_mod_change=None, parent=None):
        """mod: 모드 정보 dict (값을 바로 고쳐 쓴다). settings: 제작 환경 dict.
        actions: 네 단계 버튼에 붙일 함수 4개 (없으면 아무것도 하지 않는다)."""
        super().__init__(parent)
        self.mod, self.settings = mod, settings
        self._on_settings_change = on_settings_change
        self._on_mod_change = on_mod_change
        self._loading = False
        self._inputs = {}
        actions = actions or [lambda: None] * 4

        root = QVBoxLayout(self)
        title = QLabel("모드를 만들고 게임으로 보내기")
        title.setStyleSheet(f"font-size: 15pt; font-weight: bold; color: {Q.C['text']};")
        root.addWidget(title)
        root.addWidget(QLabel("모드 정보와 제작 환경을 확인한 뒤 검사부터 게시까지 차례로 진행"))

        info = QGroupBox("01  모드 정보")
        grid = QGridLayout(info)
        for key, label, r, c in INFO_FIELDS:
            grid.addWidget(_caption(label), r, c)
            edit = QLineEdit(str(mod.get(key, "")))
            edit.textChanged.connect(lambda text, k=key: self._mod_edited(k, text))
            span = 3 if key == "description" else 1
            grid.addWidget(edit, r, c + 1, 1, span)
            self._inputs[key] = edit
        root.addWidget(info)

        env = QGroupBox("02  제작 환경 · 이 PC에 저장")
        env_grid = QGridLayout(env)
        for r, (key, label, mode) in enumerate(ENV_FIELDS):
            env_grid.addWidget(_caption(label), r, 0)
            edit = QLineEdit(settings.get(key, ""))
            edit.textChanged.connect(lambda text, k=key: self._setting_edited(k, text))
            env_grid.addWidget(edit, r, 1)
            browse = QPushButton("찾기…")
            browse.clicked.connect(lambda _=False, e=edit, m=mode: self._browse(e, m))
            env_grid.addWidget(browse, r, 2)
            self._inputs["env:" + key] = edit
        root.addWidget(env)

        check = QGroupBox("03  준비 상태")
        check_row = QHBoxLayout(check)
        self._check_box = QVBoxLayout()
        check_row.addLayout(self._check_box)
        check_row.addStretch(1)
        recheck = QPushButton("다시 점검")
        recheck.clicked.connect(self.run_checks)
        check_row.addWidget(recheck)
        root.addWidget(check)

        act = QGroupBox("04  검사하고 게임에 적용하기")
        act_grid = QGridLayout(act)
        for i, (text, desc) in enumerate(STEPS):
            button = QPushButton(text)
            button.setProperty("primary", i == 0)        # 이 탭의 주된 동작 하나만 강조한다
            button.clicked.connect(actions[i])
            act_grid.addWidget(button, i, 0)
            act_grid.addWidget(QLabel(desc), i, 1)
        root.addWidget(act)
        root.addStretch(1)
        self.run_checks()

    # ---- 입력 ----
    def load(self, mod):
        """다른 모드를 불러왔을 때 입력 칸을 새로 채운다."""
        self._loading = True
        try:
            self.mod = mod
            for key, _, _, _ in INFO_FIELDS:
                self._inputs[key].setText(str(mod.get(key, "")))
        finally:
            self._loading = False

    def _mod_edited(self, key, text):
        if self._loading:
            return
        self.mod[key] = text.strip()
        if self._on_mod_change:
            self._on_mod_change(self.mod)

    def _setting_edited(self, key, text):
        if self._loading:
            return
        self.settings[key] = text.strip().strip('"')
        if self._on_settings_change:
            self._on_settings_change(self.settings)
        if key == "sts2_path" or key == "godot_path":
            self.run_checks()

    def _browse(self, edit, mode):
        if mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "폴더 고르기")
        else:
            path, _ = QFileDialog.getOpenFileName(self, "실행 파일 고르기", "", "실행 파일 (*.exe);;모든 파일 (*.*)")
        if path:
            edit.setText(os.path.normpath(path))

    # ---- 준비 상태 ----
    def run_checks(self):
        while self._check_box.count():
            item = self._check_box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        for state, text in check_lines(self.settings):
            row = QHBoxLayout()
            dot = QLabel("●")
            dot.setStyleSheet(f"color: {STATE_COLOR[state]};")
            row.addWidget(dot)
            row.addWidget(QLabel(text))
            row.addStretch(1)
            holder = QWidget()
            holder.setLayout(row)
            self._check_box.addWidget(holder)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    Q.apply_theme(app)
    ws = Q.DockWorkspace()
    ws.setWindowTitle("모드 / 빌드 · Qt 시험판")
    mod = {"id": "MyMod", "name": "내 모드", "author": "", "version": "0.1.0", "description": "",
           "min_game_version": "", "baselib_version": "*"}
    tab = ModTabQt(mod, {"out_dir": "", "sts2_path": "", "godot_path": ""})
    page = Q.ScrollPage()
    page.set_content(tab)
    ws.add_page(page, "모드 / 빌드")
    ws.resize(1000, 760)
    ws.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

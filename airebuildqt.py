"""'AI로 다시 만들기' 창: 직접 코드가 남은 항목을 AI 에게 블록으로 다시 만들게 한다.

① 요청 복사 → AI 채팅에 붙여 넣기 → ② 답 붙여넣기 → 읽기 → ③ 바꾸기.
바꾸는 것은 효과이고, 답에 새 파워·기믹이 있으면 넣고, remove 칸에 적힌 파워·기믹은 지운다 (확인 후).
"""
import os

from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox,
                               QPlainTextEdit, QPushButton, QVBoxLayout)

import aipaste as AP
import airebuild as AR
import blockcode as B
import qtkit as Q

TITLE = "AI로 다시 만들기"


def _confirm_removes(parent, plan):
    """지울 파워·기믹이 있으면 한 번 더 묻는다."""
    names = "\n".join(f"• {AP.NOUN[k]} {i}" for k, i in plan["removes"])
    return QMessageBox.question(parent, TITLE, f"프로젝트에서 아래 항목을 지웁니다:\n{names}\n\n계속할까요?") == QMessageBox.StandardButton.Yes


class RebuildDialogQt(QDialog):
    def __init__(self, parent, project, kind, item):
        super().__init__(parent)
        self.setWindowTitle(TITLE)
        self.resize(760, 640)
        self.project, self.kind, self.item = project, kind, item
        self.effects = None   # 읽기에 성공하면 새 효과 목록
        self.plan = None      # 읽은 계획 (새 파워·기믹, 지울 것)
        root = QVBoxLayout(self)

        parts = AR.direct_code_parts(project, kind, item)
        lines = [f"이 {AR.NOUN[kind]}에는 블록으로 바뀌지 않은 부분이 {len(parts)}곳 있습니다:"]
        lines += [f"  {i}. {text}" for i, (text, _code) in enumerate(parts, 1)]
        lines += ["", "AI에게 이 부분까지 블록으로 다시 만들어 달라고 요청합니다. 이름·그림 등 다른 칸은 바뀌지 않습니다.",
                  "필요하면 새 파워·기믹을 넣거나, 더 쓰지 않는 파워·기믹을 지울 수 있습니다 (지우기 전에 확인합니다)."]
        info = QLabel("\n".join(lines))
        info.setWordWrap(True)
        root.addWidget(info)

        step1 = QHBoxLayout()
        copy = QPushButton("① 요청 복사")
        copy.clicked.connect(self.copy_request)
        self.copied = QLabel("")
        step1.addWidget(copy)
        step1.addWidget(self.copied, 1)
        root.addLayout(step1)

        root.addWidget(QLabel("② AI 답을 아래에 붙여 넣고 '읽기'를 누르세요."))
        self.answer = QPlainTextEdit()
        self.answer.setPlaceholderText("AI가 보낸 답 전체를 붙여 넣으세요 (```json 으로 시작하는 부분 포함).")
        root.addWidget(self.answer, 1)
        row = QHBoxLayout()
        read = QPushButton("읽기")
        read.clicked.connect(self.read)
        self.take = QPushButton("③ 바꾸기")
        self.take.setEnabled(False)
        self.take.clicked.connect(self.take_changes)
        cancel = QPushButton("닫기")
        cancel.clicked.connect(self.reject)
        for w in (read, self.take):
            row.addWidget(w)
        row.addStretch(1)
        row.addWidget(cancel)
        root.addLayout(row)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        root.addWidget(self.result)

    def prompt(self):
        return AR.full_prompt(self.project, self.kind, self.item)

    def copy_request(self):
        QApplication.clipboard().setText(self.prompt())
        self.copied.setText("복사했습니다. AI 채팅(예: Claude)에 붙여 넣고 답을 기다리세요.")

    def _say(self, color, lines):
        self.result.setStyleSheet(f"color: {color};")
        self.result.setText("\n".join(lines))

    def read(self):
        plan, notes = AR.plan_answer(self.project, [(self.kind, self.item)], self.answer.toPlainText())
        self.plan = plan
        self.effects = plan["effects"].get((self.kind, self.item["id"])) if plan else None
        errors = AR.plan_errors(self.project, plan) if self.effects is not None else []
        self.take.setEnabled(self.effects is not None and not errors)
        if self.effects is None:
            self._say(Q.C["danger"], ["읽지 못했습니다."] + [f"• {n}" for n in notes])
            return
        if errors:
            self._say(Q.C["danger"], ["넣으면 검사 오류가 생겨서 넣을 수 없습니다. AI에게 고쳐 달라고 해 주세요."]
                      + [f"• {e}" for e in errors])
            return
        blocks = [b for e in self.effects for b in e.get("blocks") or []]
        summary = B.describe(blocks, self.project, self.kind, "ko", self.item) if blocks else f"효과 {len(self.effects)}개"
        lines = ["새 효과: " + summary] + AR.plan_lines(plan) + [f"• {n}" for n in notes]
        self._say(Q.C["warn"] if notes else Q.C["success"], lines)

    def take_changes(self):
        """새 파워·기믹을 넣고 지울 것을 지운 뒤 닫는다. 효과는 부르는 쪽이 넣는다."""
        if self.plan and self.plan["removes"] and not _confirm_removes(self, self.plan):
            return
        if self.plan:
            AR.apply_extras(self.project, self.plan)
        self.accept()


class BatchRebuildDialogQt(QDialog):
    """모드를 불러온 뒤, 직접 코드가 남은 항목 전부를 묶음 단위로 AI 에게 다시 만들게 한다.
    묶음마다: 요청 복사 → AI 답 붙여넣기 → 적용 (문제없는 항목의 효과만 바뀌고 다음 묶음으로 넘어간다)."""

    def __init__(self, parent, project, pairs, on_change=None):
        super().__init__(parent)
        self.setWindowTitle("AI로 한꺼번에 다시 만들기")
        self.resize(760, 600)
        self.project, self.on_change = project, on_change
        self.groups = AR.chunks(pairs)
        self.index, self.changed = 0, 0   # self.done 은 QDialog.done() 을 덮어써서 창이 안 닫힌다
        root = QVBoxLayout(self)
        info = QLabel(f"불러온 항목 중 {len(pairs)}개에 블록으로 바뀌지 않은 직접 코드가 남아 있습니다.\n"
                      f"AI 답 길이 때문에 {AR.BATCH}개씩 {len(self.groups)}번에 나눠 요청합니다. "
                      "효과만 바뀌고 이름·그림 등은 그대로입니다. 답에 새 파워·기믹을 넣거나 remove 칸으로 지울 수도 있습니다 "
                      "(지우기 전에 확인합니다). 닫았다가 나중에 'AI' 메뉴에서 이어서 할 수 있습니다.")
        info.setWordWrap(True)
        root.addWidget(info)
        self.all_at_once = QCheckBox("묶지 않고 남은 항목을 한 번에 보내기 (AI 답이 길어져 중간에 끊길 수 있습니다)")
        self.all_at_once.toggled.connect(self.regroup)
        root.addWidget(self.all_at_once)
        self.step = QLabel("")
        self.step.setWordWrap(True)
        root.addWidget(self.step)
        row1 = QHBoxLayout()
        copy = QPushButton("① 이 묶음 요청 복사")
        copy.clicked.connect(self.copy_request)
        save = QPushButton("md 파일로 저장")
        save.setToolTip("이 묶음 요청을 .md 파일로 저장합니다. AI 채팅에 파일로 올릴 때 씁니다.")
        save.clicked.connect(self.save_request)
        save_all = QPushButton("전체 묶음 md 저장")
        save_all.setToolTip("남은 묶음을 모두 .md 파일 여러 개로 한 폴더에 저장합니다. 파일 번호 = 묶음 번호.")
        save_all.clicked.connect(self.save_all)
        self.copied = QLabel("")
        self.copied.setWordWrap(True)
        row1.addWidget(copy)
        row1.addWidget(save)
        row1.addWidget(save_all)
        row1.addWidget(self.copied, 1)
        root.addLayout(row1)
        root.addWidget(QLabel("② AI 답 전체를 아래에 붙여 넣으세요."))
        self.answer = QPlainTextEdit()
        root.addWidget(self.answer, 1)
        row2 = QHBoxLayout()
        apply_btn = QPushButton("③ 적용하고 다음 묶음")
        apply_btn.clicked.connect(self.apply)
        skip = QPushButton("이 묶음 건너뛰기")
        skip.clicked.connect(self.next_group)
        close = QPushButton("닫기")
        close.clicked.connect(self.accept)
        row2.addWidget(apply_btn)
        row2.addWidget(skip)
        row2.addStretch(1)
        row2.addWidget(close)
        root.addLayout(row2)
        self.result = QLabel("")
        self.result.setWordWrap(True)
        root.addWidget(self.result)
        self.show_group()

    def current(self):
        return self.groups[self.index] if self.index < len(self.groups) else []

    def regroup(self, at_once):
        """남은 항목을 한 묶음으로 / 다시 BATCH 개씩 나눈다."""
        left = [pair for group in self.groups[self.index:] for pair in group]
        self.groups = [left] if at_once and left else AR.chunks(left)
        self.index = 0
        self.show_group()

    def show_group(self):
        group = self.current()
        if not group:
            self.step.setText(f"모든 묶음을 마쳤습니다. 블록으로 바꾼 항목: {self.changed}개")
            return
        names = ", ".join(it.get("name_ko") or it.get("name_en") or it["id"] for _k, it in group)
        self.step.setText(f"묶음 {self.index + 1}/{len(self.groups)}: {names}")
        self.copied.setText("")
        self.answer.clear()

    def copy_request(self):
        if self.current():
            QApplication.clipboard().setText(AR.batch_prompt(self.project, self.current()))
            self.copied.setText("복사했습니다. AI 채팅에 붙여 넣고 답을 기다리세요.")

    def save_request(self, path=None):
        """이 묶음 요청을 .md 파일로 저장한다 (path 를 주면 묻지 않는다)."""
        if not self.current():
            return
        if not path:
            path, _ = QFileDialog.getSaveFileName(self, "요청을 md 파일로 저장", self._md_name(self.index),
                                                  "Markdown (*.md)")
        if not path:
            return
        if self._write(path, self.current()):
            self._saved(os.path.basename(path))

    def save_all(self, folder=None):
        """남은 묶음을 전부 md 파일 여러 개로 한 폴더에 저장한다 (folder 를 주면 묻지 않는다)."""
        if not self.current():
            return
        if not folder:
            folder = QFileDialog.getExistingDirectory(self, "요청 파일들을 저장할 폴더")
        if not folder:
            return
        names = []
        for i in range(self.index, len(self.groups)):
            name = self._md_name(i)
            if not self._write(os.path.join(folder, name), self.groups[i]):
                return
            names.append(name)
        self._saved(f"{len(names)}개 파일 ({names[0]} …)" if len(names) > 1 else names[0])

    def _md_name(self, i):
        mod = (self.project.get("mod") or {}).get("id") or "mod"
        return f"{mod}_AI요청_{i + 1:02d}_of_{len(self.groups):02d}.md"

    def _write(self, path, group):
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(AR.batch_prompt(self.project, group))
            return True
        except OSError as e:
            self.copied.setText(f"저장하지 못했습니다: {e}")
            return False

    def _saved(self, what):
        QApplication.clipboard().setText(AR.CHAT_MESSAGE)
        self.copied.setText(f"저장했습니다: {what}\n파일을 AI 채팅에 첨부하고, 복사된 안내 문장을 채팅창에 붙여 넣어 함께 보내세요 "
                            "(파일만 보내면 AI가 참고 문서로만 읽고 아무것도 만들지 않습니다). "
                            "답은 묶음 번호 순서대로 아래에 붙여 넣으세요.")

    def _say(self, color, lines):
        self.result.setStyleSheet(f"color: {color};")
        self.result.setText("\n".join(lines))

    def apply(self):
        group = self.current()
        if not group:
            return
        plan, notes = AR.plan_answer(self.project, group, self.answer.toPlainText())
        found = plan["effects"] if plan else {}
        if plan is None or not (found or plan["adds"] or plan["removes"]):
            self._say(Q.C["danger"], ["적용하지 못했습니다."] + [f"• {n}" for n in notes])
            return
        errors = AR.plan_errors(self.project, plan)
        if errors:
            self._say(Q.C["danger"], ["검사 오류가 생겨서 이 묶음은 넣지 않았습니다. 답을 고쳐 다시 붙여 넣거나 건너뛰세요."]
                      + [f"• {e}" for e in errors])
            return
        if plan["removes"] and not _confirm_removes(self, plan):
            return
        AR.apply_plan(self.project, plan)
        self.changed += len(found)
        if self.on_change:
            self.on_change()
        lines = [f"{len(found)}/{len(group)}개 항목을 바꿨습니다."] + AR.plan_lines(plan) + [f"• {n}" for n in notes]
        self._say(Q.C["warn"] if notes else Q.C["success"], lines)
        self.next_group()

    def next_group(self):
        self.index += 1
        self.show_group()


def offer_batch(parent, project, items=None, on_change=None):
    """불러온 항목(items, 없으면 프로젝트 전체)에 직접 코드가 남았으면 한꺼번에 다시 만들기 창을 연다."""
    pairs = AR.targets(project, items)
    if pairs:
        BatchRebuildDialogQt(parent, project, pairs, on_change).exec()
    return bool(pairs)

"""건의 / 오류 보고 창 (Qt 版). 보고서는 사용자가 내용을 확인한 뒤에만 저장하거나 GitHub 초안으로 연다.

Tk 의 FeedbackDialog 와 같은 순서: 입력 → 미리보기 → (저장 또는) 확인 후 GitHub 초안. 로그는 체크했을 때만 넣는다.
"""
import platform
import webbrowser
from urllib.parse import urlencode

from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

import feedback as FB
import updater as UP
import qtkit as Q

KINDS = ("건의", "오류")


def _warn(parent, text):
    QMessageBox.warning(parent, "건의 / 오류 보고", text)


def _info(parent, text):
    QMessageBox.information(parent, "건의 / 오류 보고", text)


def _view(parent, title, text, width=720, height=520, close_button=True):
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    dialog.resize(width, height)
    col = QVBoxLayout(dialog)
    view = QPlainTextEdit()
    view.setReadOnly(True)
    view.setPlainText(text)
    col.addWidget(view, 1)
    if close_button:
        close = QPushButton("닫기")
        close.clicked.connect(dialog.accept)
        col.addWidget(close)
    return dialog


class FeedbackDialogQt(QDialog):
    def __init__(self, app_dir, parent=None, initial_kind="건의", initial_title="", initial_description=""):
        super().__init__(parent)
        self.app_dir = app_dir
        self.setWindowTitle("건의 / 오류 보고")
        self.resize(720, 590)
        root = QVBoxLayout(self)
        row = QHBoxLayout()
        row.addWidget(QLabel("종류"))
        self.kind = QComboBox()
        self.kind.addItems(list(KINDS))
        if initial_kind in KINDS:
            self.kind.setCurrentText(initial_kind)
        row.addWidget(self.kind)
        row.addWidget(QLabel("제목"))
        self.title_edit = QLineEdit(initial_title)
        row.addWidget(self.title_edit, 1)
        root.addLayout(row)
        root.addWidget(QLabel("무엇을 제안하거나 어떤 오류가 났는지 적어 주세요."))
        self.description = QPlainTextEdit()
        self.description.setPlainText(initial_description)
        root.addWidget(self.description, 1)
        self.include_logs = QCheckBox("최근 실행 로그와 오류 기록을 보고서에 포함")
        self.include_logs.setChecked(True)
        root.addWidget(self.include_logs)
        notice = QLabel("GitHub에 제출한 이슈는 공개될 수 있습니다. 로그에는 PC 사용자 이름이나 파일 경로가 보일 수 있습니다. "
                        "프로젝트·그림 파일은 포함하지 않습니다.")
        notice.setWordWrap(True)
        notice.setStyleSheet(f"color: {Q.C['warn']};")
        root.addWidget(notice)
        buttons = QHBoxLayout()
        for text, slot in (("미리보기", self.preview), ("보고서 저장", self.save_bundle)):
            button = QPushButton(text)
            button.clicked.connect(slot)
            buttons.addWidget(button)
        buttons.addStretch(1)
        send = QPushButton("GitHub에서 보내기…")
        send.clicked.connect(self.send_github)
        buttons.addWidget(send)
        close = QPushButton("닫기")
        close.clicked.connect(self.reject)
        buttons.addWidget(close)
        root.addLayout(buttons)

    def _collect(self):
        title = self.title_edit.text().strip()
        description = self.description.toPlainText().strip()
        if not title:
            _warn(self, "제목을 적어 주세요.")
            return None
        if not description:
            _warn(self, "내용을 적어 주세요.")
            return None
        return {"kind": self.kind.currentText(), "title": FB.redact(title), "description": FB.redact(description)}

    def _payload_preview(self, report):
        include_logs = self.include_logs.isChecked()
        return FB.issue_body({
            **report,
            "app_version": UP.VERSION,
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "reported_at": FB._now(),
        }) + ("\n\n[로그 포함] 최신 실행 로그와 오류 기록을 ZIP에 넣습니다." if include_logs else
              "\n\n[로그 제외] 설명과 앱 환경 정보만 보고서에 넣습니다.")

    def preview(self):
        report = self._collect()
        if report is None:
            return
        text = f"GitHub 제목: [{report['kind']}] {report['title']}\n\n" + self._payload_preview(report)
        if self.include_logs.isChecked():
            for name, content in FB.recent_logs(self.app_dir).items():
                if content.strip():
                    text += f"\n\n--- {name} (첨부 예정) ---\n{content[-12000:]}"
        _view(self, "보고서 미리보기", text).exec()

    def _make_bundle(self, report):
        return FB.make_report(self.app_dir, report, UP.VERSION, self.include_logs.isChecked())

    def save_bundle(self):
        report = self._collect()
        if report is None:
            return
        path, _payload = self._make_bundle(report)
        _info(self, f"보고서를 저장했습니다.\n\n{path}\n\n이 파일을 제작자에게 보내면 됩니다.")

    def send_github(self):
        report = self._collect()
        if report is None:
            return
        path, payload = self._make_bundle(report)
        title = f"[{report['kind']}] {report['title']}"
        body = FB.issue_body(payload, path)
        url = f"https://github.com/{UP.REPO}/issues/new?{urlencode({'title': title, 'body': body})}"
        if len(url) > 7000:
            body = FB.issue_body({**payload, "description": report["description"][:1800] +
                                  "\n\n자세한 내용은 첨부 ZIP의 report.json을 확인해 주세요."}, path)
            url = f"https://github.com/{UP.REPO}/issues/new?{urlencode({'title': title, 'body': body})}"
        confirm = _view(self, "GitHub로 보낼 내용 확인", title + "\n\n" + body, 760, 560, close_button=False)
        row = QHBoxLayout()
        cancel = QPushButton("취소")
        cancel.clicked.connect(confirm.reject)
        go = QPushButton("확인하고 GitHub 초안 열기")
        go.clicked.connect(lambda: (confirm.accept(), self._open_reviewed_issue(url, body, path)))
        row.addWidget(cancel)
        row.addWidget(go)
        confirm.layout().addLayout(row)
        confirm.exec()

    def _open_reviewed_issue(self, url, body, path):
        clipboard = QApplication.clipboard()
        clipboard.setText(body)
        try:
            opened = webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            _warn(self, f"보고서는 저장했지만 브라우저를 열지 못했습니다.\n{exc}\n\n{path}")
            return
        if not opened:
            clipboard.setText(url)
            _warn(self, "브라우저를 열지 못했습니다.\nGitHub 이슈 초안 주소를 클립보드에 복사했습니다.\n\n" f"보고서: {path}")
            return
        _info(self, "GitHub 이슈 작성 페이지를 열었습니다.\n내용을 확인한 뒤 제출하고, 저장된 ZIP 보고서를 첨부해 주세요.\n\n"
                    f"보고서: {path}")


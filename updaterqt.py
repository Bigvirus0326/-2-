"""업데이트 확인과 알림 창 (Qt 版). 확인하는 규칙·내려받기·교체는 updater.py 가 한다. 이 파일은 화면만 맡는다."""
import os
import shutil
import tempfile
import threading
import urllib.request
import webbrowser

from PySide6.QtCore import QTimer, Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton,
                               QVBoxLayout)

import projectio as IO
import release_signature
import updater as UP
import qtkit as Q


def _say(parent, text, title="업데이트 확인", kind="info"):
    box = {"info": QMessageBox.information, "warn": QMessageBox.warning, "error": QMessageBox.critical}[kind]
    box(parent, title, text)


def check(app, manual=False):
    """뒤에서 최신 릴리스를 확인하고, 새 버전이면 알림 창. manual=True 면 결과를 항상 알려 준다."""
    box = {}

    def work():
        try:
            box["rel"] = UP.fetch_latest(prerelease=bool(app.settings.get("update_prerelease")))
        except Exception as e:  # noqa: BLE001 — 인터넷 없음·차단 등은 조용히 넘어간다
            box["err"] = e

    threading.Thread(target=work, daemon=True).start()

    def poll():
        if "rel" not in box and "err" not in box:
            QTimer.singleShot(200, poll)
            return
        _done(app, box, manual)
    QTimer.singleShot(200, poll)


def auto_check(app):
    """프로그램을 켤 때 한 번만. 버전이 바뀌었으면 알리고, 설정이 꺼져 있으면 확인하지 않는다."""
    if UP._auto_done or os.environ.get("STS2MM_NO_UPDATE"):
        return
    UP._auto_done = True
    last = app.settings.get("last_version")
    if last != UP.VERSION:
        if last and UP.is_newer(UP.VERSION, last):
            app.status(f"v{UP.VERSION} 로 업데이트되었습니다.", 8000)
        app.settings["last_version"] = UP.VERSION
        app.persist_settings()
    if not app.settings.get("update_check", True):
        return
    check(app, manual=False)


def _done(app, box, manual):
    rel = box.get("rel")
    if rel is None:
        if manual:
            _say(app, "깃허브에 연결하지 못했습니다.\n인터넷 연결을 확인하거나 나중에 다시 해 보세요.\n\n"
                      f"({box.get('err')})", kind="warn")
        return
    if not rel["version"] or not UP.is_newer(rel["version"]):
        if manual:
            _say(app, f"지금 최신 버전입니다 (v{UP.VERSION}).")
        return
    if not manual and app.settings.get("update_skip") == rel["version_text"]:
        return
    UpdateDialogQt(app, rel).exec()


class UpdateDialogQt(QDialog):
    def __init__(self, app, rel):
        super().__init__(app)
        self.app, self.rel = app, rel
        self.asset = UP.pick_asset(rel.get("assets") or [])
        self.block = UP.self_update_block_reason()
        if not self.block and not self.asset:
            self.block = "이 릴리스에 맞는 zip 파일이 없어 자동 업데이트를 할 수 없습니다."
        self.cancel_ev = threading.Event()
        self.running = False
        self.state = None
        self.work = None
        self.setWindowTitle("업데이트 알림")
        self.resize(640, 480)

        root = QVBoxLayout(self)
        title = QLabel(f"새 {'시험판' if rel.get('prerelease') else '버전'} v{rel['version_text']} 이 나왔습니다")
        title.setStyleSheet("font-size: 14px; font-weight: bold;")
        root.addWidget(title)
        root.addWidget(QLabel(f"지금 쓰는 버전: v{UP.VERSION}    ·    {rel['name']}"))
        body = (rel.get("body") or "").strip()
        if body:
            root.addWidget(QLabel("바뀐 내용"))
            text = QPlainTextEdit()
            text.setReadOnly(True)
            text.setPlainText(body[:6000])
            root.addWidget(text, 1)
        if self.block:
            note = self.block + "\n다운로드 페이지에서 zip 을 받아 새 폴더에 풀어 쓰세요."
        else:
            note = ("[지금 업데이트] 를 누르면 새 버전을 받아 프로그램을 바꾸고 다시 켭니다.\n"
                    "설정·출력 폴더와 모드 프로젝트(.json)는 그대로 남습니다.")
        self.note = QLabel(note)
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color: {Q.C['muted']};")
        root.addWidget(self.note)
        self.prog = QProgressBar()
        self.prog.setRange(0, 100)
        self.prog.setVisible(False)
        root.addWidget(self.prog)

        buttons = QHBoxLayout()
        self.go_btn = None
        if not self.block:
            self.go_btn = QPushButton("⟳ 지금 업데이트")
            self.go_btn.clicked.connect(self.start)
            buttons.addWidget(self.go_btn)
            page = QPushButton("다운로드 페이지")
        else:
            page = QPushButton("⬇ 다운로드 페이지 열기")
        page.clicked.connect(self.open_page)
        buttons.addWidget(page)
        buttons.addStretch(1)
        self.skip_btn = QPushButton("이 버전은 다시 알리지 않기")
        self.skip_btn.clicked.connect(self.skip)
        buttons.addWidget(self.skip_btn)
        self.later_btn = QPushButton("나중에")
        self.later_btn.clicked.connect(self.close)
        buttons.addWidget(self.later_btn)
        root.addLayout(buttons)

    # ---- 버튼 ----
    def open_page(self):
        webbrowser.open(self.rel["url"])
        if not self.running:
            self.accept()

    def skip(self):
        self.app.settings["update_skip"] = self.rel["version_text"]
        self.app.persist_settings()
        self.accept()

    def closeEvent(self, event):
        if self.running:
            self.cancel_ev.set()
            event.ignore()
            return
        super().closeEvent(event)

    # ---- 자동 업데이트 ----
    def start(self):
        app = self.app
        if getattr(app, "busy", False):
            _say(self, "빌드 중에는 업데이트할 수 없습니다. 빌드가 끝난 뒤 다시 눌러 주세요.")
            return
        if not app.confirm_discard():
            return
        self.running = True
        self.go_btn.setEnabled(False)
        self.skip_btn.setEnabled(False)
        self.later_btn.setText("취소")
        self.prog.setVisible(True)
        self.note.setText("새 버전 받는 중…")
        self.state = {"done": 0, "total": self.asset.get("size", 0), "phase": "download"}
        self.work = tempfile.mkdtemp(prefix="sts2mm_update_")
        st = self.state

        def run():
            try:
                zp = os.path.join(self.work, "update.zip")
                name = self.asset["name"] + ".sig"
                signatures = [a for a in self.rel["assets"] if a["name"] == name]
                if len(signatures) != 1 or signatures[0]["size"] != 384:
                    raise ValueError("이 업데이트의 배포자 서명 파일이 없거나 올바르지 않습니다.")
                req = urllib.request.Request(signatures[0]["url"], headers={"User-Agent": UP.UA})
                with urllib.request.urlopen(req, timeout=20) as response:
                    signature = response.read(385)
                UP.download(self.asset["url"], zp, self.asset.get("size", 0),
                            progress=lambda d, t: st.update(done=d, total=t), cancel=self.cancel_ev,
                            digest=self.asset.get("digest"))
                release_signature.verify(zp, signature)
                st["phase"] = "stage"
                st["src"] = UP.stage(zp, self.work)
                os.remove(zp)
                st["phase"] = "ready"
            except Exception as e:  # noqa: BLE001
                st["phase"] = "error"
                st["err"] = e

        threading.Thread(target=run, daemon=True).start()
        QTimer.singleShot(150, self._poll)

    def _poll(self):
        st = self.state
        if st["phase"] == "download":
            tot = st["total"] or 1
            self.prog.setValue(int(min(100, st["done"] * 100 / tot)))
            self.note.setText(f"새 버전 받는 중… {st['done'] / 1e6:.1f} / {st['total'] / 1e6:.1f} MB")
        elif st["phase"] == "stage":
            self.prog.setValue(100)
            self.note.setText("압축 푸는 중…")
        if st["phase"] in ("download", "stage"):
            QTimer.singleShot(150, self._poll)
            return
        if st["phase"] == "error":
            shutil.rmtree(self.work, ignore_errors=True)
            self.running = False
            if isinstance(st.get("err"), InterruptedError):
                self.accept()
                return
            _say(self, f"자동 업데이트를 하지 못했습니다.\n{st['err']}\n\n[다운로드 페이지] 에서 직접 받을 수 있습니다.",
                 "업데이트 실패", kind="error")
            self.go_btn.setEnabled(True)
            self.skip_btn.setEnabled(True)
            self.later_btn.setText("나중에")
            self.prog.setVisible(False)
            self.note.setText("자동 업데이트에 실패했습니다. 다시 누르거나 다운로드 페이지에서 받아 주세요.")
            return
        self.note.setText("새 버전으로 바꾸고 다시 켭니다…")
        try:
            dst = UP.install_dir()
            script = UP.write_swap_script(st["src"], dst, os.getpid(), UP.relaunch_command(dst), self.work,
                                          self.rel["version_text"])
            UP.launch_swap(script)
        except Exception as e:  # noqa: BLE001
            shutil.rmtree(self.work, ignore_errors=True)
            self.running = False
            _say(self, f"업데이트 도우미를 실행하지 못했습니다:\n{e}", "업데이트 실패", kind="error")
            self.accept()
            return
        QTimer.singleShot(400, self._quit_app)

    def _quit_app(self):
        app = self.app
        app.dirty = False
        app._restart_state = None
        app.close()

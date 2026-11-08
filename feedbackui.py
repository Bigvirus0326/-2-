"""User-reviewed suggestions and error reports."""
from __future__ import annotations

import os
import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from urllib.parse import urlencode

import feedback as FB
import updater as UP
from winpos import center_window


class FeedbackDialog(tk.Toplevel):
    def __init__(self, app, app_dir, initial_kind="건의", initial_title="", initial_description=""):
        super().__init__(app)
        self.app = app
        self.app_dir = os.path.abspath(app_dir)
        self.title("건의 / 오류 보고")
        self.geometry("720x590")
        self.minsize(620, 500)
        self.transient(app)
        self.kind = tk.StringVar(value=initial_kind if initial_kind in ("건의", "오류") else "건의")
        self.title_var = tk.StringVar(value=initial_title)
        self.include_logs = tk.BooleanVar(value=True)

        outer = ttk.Frame(self, padding=12)
        outer.pack(fill="both", expand=True)
        outer.columnconfigure(1, weight=1)
        outer.rowconfigure(3, weight=1)

        ttk.Label(outer, text="종류").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(outer, textvariable=self.kind, values=("건의", "오류"), state="readonly", width=12).grid(
            row=0, column=1, sticky="w", pady=4)
        ttk.Label(outer, text="제목").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(outer, textvariable=self.title_var).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(outer, text="무엇을 제안하거나 어떤 오류가 났는지 적어 주세요.").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(7, 3))
        text_frame = ttk.Frame(outer)
        text_frame.grid(row=3, column=0, columnspan=2, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.description = tk.Text(text_frame, wrap="word", height=12, undo=True)
        self.description.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(text_frame, command=self.description.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.description.configure(yscrollcommand=scroll.set)
        if initial_description:
            self.description.insert("1.0", initial_description)

        ttk.Checkbutton(outer, text="최근 실행 로그와 오류 기록을 보고서에 포함",
                        variable=self.include_logs).grid(row=4, column=0, columnspan=2, sticky="w", pady=(9, 2))
        ttk.Label(outer, text="GitHub에 제출한 이슈는 공개될 수 있습니다. 로그에는 PC 사용자 이름이나 파일 경로가 보일 수 있습니다. 프로젝트·그림 파일은 포함하지 않습니다.",
                  foreground="#775b2f", wraplength=670).grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 9))

        buttons = ttk.Frame(outer)
        buttons.grid(row=6, column=0, columnspan=2, sticky="ew")
        ttk.Button(buttons, text="미리보기", command=self.preview).pack(side="left")
        ttk.Button(buttons, text="보고서 저장", command=self.save_bundle).pack(side="left", padx=(6, 0))
        ttk.Button(buttons, text="GitHub에서 보내기…", command=self.send_github).pack(side="right")
        ttk.Button(buttons, text="닫기", command=self.destroy).pack(side="right", padx=(0, 6))

        self.bind("<Escape>", lambda _event: self.destroy())
        center_window(self, app)
        self.grab_set()

    def _collect(self):
        title = self.title_var.get().strip()
        description = self.description.get("1.0", "end-1c").strip()
        if not title:
            messagebox.showwarning("건의 / 오류 보고", "제목을 적어 주세요.", parent=self)
            return None
        if not description:
            messagebox.showwarning("건의 / 오류 보고", "내용을 적어 주세요.", parent=self)
            return None
        return {"kind": self.kind.get(), "title": FB.redact(title), "description": FB.redact(description)}

    def _payload_preview(self, report):
        include_logs = bool(self.include_logs.get())
        return FB.issue_body({
            **report,
            "app_version": UP.VERSION,
            "platform": __import__("platform").platform(),
            "python_version": __import__("platform").python_version(),
            "reported_at": FB._now(),
        }) + ("\n\n[로그 포함] 최신 실행 로그와 오류 기록을 ZIP에 넣습니다." if include_logs else
              "\n\n[로그 제외] 설명과 앱 환경 정보만 보고서에 넣습니다.")

    def preview(self):
        report = self._collect()
        if report is None:
            return
        preview = tk.Toplevel(self)
        preview.title("보고서 미리보기")
        preview.geometry("700x520")
        preview.transient(self)
        body = ttk.Frame(preview, padding=10)
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        view = tk.Text(body, wrap="word")
        view.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(body, command=view.yview)
        bar.grid(row=0, column=1, sticky="ns")
        view.configure(yscrollcommand=bar.set)
        view.insert("1.0", f"GitHub 제목: [{report['kind']}] {report['title']}\n\n" + self._payload_preview(report))
        if self.include_logs.get():
            logs = FB.recent_logs(self.app_dir)
            for name, content in logs.items():
                if content.strip():
                    view.insert("end", f"\n\n--- {name} (첨부 예정) ---\n{content[-12000:]}")
        view.configure(state="disabled")
        ttk.Button(body, text="닫기", command=preview.destroy).grid(row=1, column=0, columnspan=2, sticky="e", pady=(8, 0))
        center_window(preview, self)

    def _make_bundle(self, report):
        return FB.make_report(self.app_dir, report, UP.VERSION, bool(self.include_logs.get()))

    def save_bundle(self):
        report = self._collect()
        if report is None:
            return
        path, _payload = self._make_bundle(report)
        messagebox.showinfo("보고서 저장", f"보고서를 저장했습니다.\n\n{path}\n\n이 파일을 제작자에게 보내면 됩니다.",
                            parent=self)
        self.app.log(f"[보고서] 사용자가 보고서를 저장했습니다: {path}")

    def send_github(self):
        report = self._collect()
        if report is None:
            return
        path, payload = self._make_bundle(report)
        title = f"[{report['kind']}] {report['title']}"
        body = FB.issue_body(payload, path)
        query = urlencode({"title": title, "body": body})
        url = f"https://github.com/{UP.REPO}/issues/new?{query}"
        if len(url) > 7000:
            body = FB.issue_body({**payload, "description": report["description"][:1800] + "\n\n자세한 내용은 첨부 ZIP의 report.json을 확인해 주세요."}, path)
            url = f"https://github.com/{UP.REPO}/issues/new?{urlencode({'title': title, 'body': body})}"
        preview = tk.Toplevel(self)
        preview.title("GitHub로 보낼 내용 확인")
        preview.transient(self)
        view = tk.Text(preview, wrap="word", width=76, height=24)
        view.pack(fill="both", expand=True)
        view.insert("1.0", title + "\n\n" + body)
        view.configure(state="disabled")
        ttk.Label(preview, text="초안을 열면 위 내용이 GitHub로 전달됩니다. ZIP은 직접 첨부합니다.").pack()
        actions = ttk.Frame(preview)
        actions.pack(pady=6)
        def proceed():
            preview.destroy()
            self._open_reviewed_issue(url, body, path)
        ttk.Button(actions, text="취소", command=preview.destroy).pack(side="left")
        ttk.Button(actions, text="확인하고 GitHub 초안 열기", command=proceed).pack(side="left")
        center_window(preview, self)
        preview.grab_set()

    def _open_reviewed_issue(self, url, body, path):
        try:
            self.app.clipboard_clear()
            self.app.clipboard_append(body)
        except tk.TclError:
            pass
        try:
            opened = webbrowser.open(url)
        except Exception as exc:  # noqa: BLE001
            messagebox.showwarning("GitHub 이슈", f"보고서는 저장했지만 브라우저를 열지 못했습니다.\n{exc}\n\n{path}", parent=self)
            return
        if not opened:
            try:
                self.app.clipboard_clear()
                self.app.clipboard_append(url)
            except tk.TclError:
                pass
            messagebox.showwarning("GitHub 이슈", "브라우저를 열지 못했습니다.\n"
                                   "GitHub 이슈 초안 주소를 클립보드에 복사했습니다.\n\n"
                                   f"보고서: {path}", parent=self)
            return
        self.app.log(f"[보고서] GitHub 이슈 초안용 묶음을 저장했습니다: {path}")
        messagebox.showinfo("GitHub 이슈 작성", "GitHub 이슈 작성 페이지를 열었습니다.\n"
                            "내용을 확인한 뒤 제출하고, 저장된 ZIP 보고서를 첨부해 주세요.\n\n"
                            f"보고서: {path}\n(로그 / 보고서 폴더는 도움말 메뉴에서 열 수 있습니다.)", parent=self)

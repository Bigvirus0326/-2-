"""Local diagnostics and user-approved feedback bundles for the mod maker."""
from __future__ import annotations

import datetime as dt
import json
import os
import platform
import re
import sys
import threading
import traceback
import zipfile

_LOCK = threading.RLock()
_HOOKS_INSTALLED = False
_HOOK_APP_DIR = ""
_APP_LOG_LIMIT = 2 * 1024 * 1024
_ERROR_LOG_LIMIT = 3 * 1024 * 1024
_REPORT_LOG_LIMIT = 512 * 1024


def log_dir(app_dir):
    return os.path.join(os.path.abspath(app_dir), "logs")


def report_dir(app_dir):
    return os.path.join(log_dir(app_dir), "reports")


def _now():
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def _rotate(path, limit, keep=2):
    try:
        if os.path.getsize(path) <= limit:
            return
    except OSError:
        return
    try:
        oldest = f"{path}.{keep}"
        if os.path.exists(oldest):
            os.remove(oldest)
        for index in range(keep - 1, 0, -1):
            old = f"{path}.{index}"
            if os.path.exists(old):
                os.replace(old, f"{path}.{index + 1}")
        os.replace(path, f"{path}.1")
    except OSError:
        pass


def _append(path, text, limit):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with _LOCK:
            _rotate(path, limit)
            with open(path, "a", encoding="utf-8", newline="\n") as stream:
                stream.write(text.rstrip() + "\n")
                stream.flush()
    except (OSError, UnicodeError):
        # Logging must not prevent the app from continuing to run.
        pass


def _looks_like_error(message):
    text = str(message or "")
    return bool(
        "[오류]" in text or "[미리보기 오류]" in text or "Traceback (most recent call last)" in text or
        "✘ 실패" in text or re.search(r"\berror\s+[A-Z]+\d+\b", text, re.I) or
        re.search(r"\b(exception|fatal error)\b", text, re.I)
    )


def append_app_log(message, app_dir):
    if "--selftest" in sys.argv:
        return
    text = str(message or "").rstrip()
    if not text:
        return
    stamp = _now()
    lines = text.splitlines() or [text]
    entry = "\n".join(f"{stamp} {line}" if i == 0 else f"{stamp}   {line}" for i, line in enumerate(lines))
    root = log_dir(app_dir)
    _append(os.path.join(root, "app.log"), entry, _APP_LOG_LIMIT)
    if _looks_like_error(text):
        _append(os.path.join(root, "errors.log"), entry, _ERROR_LOG_LIMIT)


def record_exception(exc_type, exc, tb, app_dir, context="예기치 않은 오류"):
    name = getattr(exc_type, "__name__", None) or type(exc).__name__
    formatted = "".join(traceback.format_exception(exc_type, exc, tb)).rstrip()
    entry = f"[{_now()}] {context} ({name})\n{formatted}"
    root = log_dir(app_dir)
    _append(os.path.join(root, "errors.log"), entry, _ERROR_LOG_LIMIT)
    _append(os.path.join(root, "app.log"), entry, _APP_LOG_LIMIT)
    return os.path.join(root, "errors.log")


def install_exception_hooks(app_dir):
    """Persist uncaught main-thread and worker-thread exceptions once per process."""
    global _HOOKS_INSTALLED, _HOOK_APP_DIR
    _HOOK_APP_DIR = os.path.abspath(app_dir)
    if _HOOKS_INSTALLED:
        return
    _HOOKS_INSTALLED = True
    original_sys_hook = sys.excepthook

    def main_hook(exc_type, exc, tb):
        record_exception(exc_type, exc, tb, _HOOK_APP_DIR, "프로그램 예외")
        original_sys_hook(exc_type, exc, tb)

    sys.excepthook = main_hook
    if hasattr(threading, "excepthook"):
        original_thread_hook = threading.excepthook

        def thread_hook(args):
            record_exception(args.exc_type, args.exc_value, args.exc_traceback, _HOOK_APP_DIR,
                             f"작업 스레드 예외 ({args.thread.name if args.thread else 'unknown'})")
            original_thread_hook(args)

        threading.excepthook = thread_hook


def _tail(path, limit=_REPORT_LOG_LIMIT):
    try:
        with open(path, "rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - limit), os.SEEK_SET)
            data = stream.read()
        return data.decode("utf-8", errors="replace")
    except OSError:
        return ""


def recent_logs(app_dir):
    root = log_dir(app_dir)
    return {
        "app.log": _tail(os.path.join(root, "app.log")),
        "errors.log": _tail(os.path.join(root, "errors.log")),
    }


def make_report(app_dir, report, app_version, include_logs=True):
    """Save a shareable zip. It never includes the user's project or its assets."""
    stamp = dt.datetime.now().astimezone().strftime("%Y%m%d-%H%M%S-%f")
    os.makedirs(report_dir(app_dir), exist_ok=True)
    safe_kind = re.sub(r"[^A-Za-z0-9_-]+", "_", str(report.get("kind") or "feedback"))[:24].strip("_") or "feedback"
    path = os.path.join(report_dir(app_dir), f"{stamp}-{safe_kind}.zip")
    payload = {
        "reported_at": _now(),
        "kind": str(report.get("kind") or "건의"),
        "title": str(report.get("title") or "").strip(),
        "description": str(report.get("description") or "").strip(),
        "app_version": str(app_version),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "logs_included": bool(include_logs),
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        bundle.writestr("report.json", json.dumps(payload, ensure_ascii=False, indent=2))
        if include_logs:
            for name, content in recent_logs(app_dir).items():
                if content.strip():
                    bundle.writestr(name, content)
    return path, payload


def issue_body(payload, bundle_path=""):
    lines = [
        f"## {payload.get('kind') or '피드백'}",
        "",
        str(payload.get("description") or "(내용 없음)"),
        "",
        "---",
        f"- 앱 버전: {payload.get('app_version') or '?'}",
        f"- 운영체제: {payload.get('platform') or '?'}",
        f"- Python: {payload.get('python_version') or '?'}",
        f"- 작성 시각: {payload.get('reported_at') or '?'}",
    ]
    lines.extend(["", "필요하면 저장된 보고서 ZIP을 이 이슈에 첨부해 주세요."])
    lines.extend(["", "프로젝트 파일과 그림은 보고서에 포함하지 않았습니다."])
    return "\n".join(lines)

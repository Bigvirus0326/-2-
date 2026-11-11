"""설정·프로젝트 파일 읽기·쓰기 (화면 기술과 무관). Tk 앱과 Qt 앱이 함께 쓴다."""
import copy
import json
import os
import re
import sys
import tempfile


def _app_dir():
    """설정·출력 폴더 위치. 소스 실행이면 .py 옆, exe 로 묶었으면 exe 옆 (쓸 수 없는 곳이면 %LOCALAPPDATA%)."""
    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(__file__))
    d = os.path.dirname(os.path.abspath(sys.executable))
    try:
        probe = os.path.join(d, ".write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return d
    except OSError:
        d = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "sts2_mod_maker")
        os.makedirs(d, exist_ok=True)
        return d


APP_DIR = _app_dir()
SETTINGS_PATH = os.path.join(APP_DIR, "settings.json")
APP_TITLE = "슬더스2 모드 메이커"
BASELIB_URL = "https://github.com/Alchyr/BaseLib-StS2/releases"
MEGADOT_URL = "https://megadot.megacrit.com/"


# ---------------------------------------------------------------------------
# 환경 탐지
# ---------------------------------------------------------------------------
def detect_sts2_path():
    candidates = []
    steam = None
    if sys.platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                steam = winreg.QueryValueEx(k, "SteamPath")[0]
        except OSError:
            steam = r"C:\Program Files (x86)\Steam"
    else:
        steam = os.path.expanduser("~/.local/share/Steam")
    if steam:
        candidates.append(os.path.join(steam, "steamapps"))
        vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
        try:
            with open(vdf, encoding="utf-8", errors="ignore") as f:
                for m in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                    candidates.append(os.path.join(m.group(1).replace("\\\\", "\\"), "steamapps"))
        except OSError:
            pass
    for c in candidates:
        p = os.path.join(c, "common", "Slay the Spire 2")
        if os.path.isdir(p):
            return os.path.normpath(p)
    return ""


def _atomic_write_json(path, value):
    """Write JSON beside the destination and replace it atomically."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix=".sts2-mod-maker-save-", suffix=".tmp", dir=parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            os.remove(temp_path)
        except OSError:
            pass
        raise


_IMAGE_PATH_FIELDS = {
    "image", "combat_image", "energy_icon_image", "energy_text_icon_image",
    "icon_image", "map_marker_image", "select_image", "select_locked_image", "select_bg_image",
}


def _transform_project_image_paths(project, transform):
    def visit(node):
        if isinstance(node, dict):
            for key, value in list(node.items()):
                if key in _IMAGE_PATH_FIELDS and isinstance(value, str) and value.strip():
                    node[key] = transform(value)
                else:
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(project)
    return project


def _resolve_project_image_paths(project, base_dir):
    def resolve(value):
        if os.path.isabs(value):
            return os.path.normpath(value)
        return os.path.abspath(os.path.join(base_dir, value))
    return _transform_project_image_paths(project, resolve)


def _project_data_for_save(project, path):
    base = os.path.abspath(os.path.dirname(path) or os.curdir)
    data = copy.deepcopy(project)

    def relative(value):
        if not os.path.isabs(value):
            return value
        absolute = os.path.abspath(value)
        try:
            if os.path.normcase(os.path.commonpath((base, absolute))) == os.path.normcase(base):
                return os.path.relpath(absolute, base).replace(chr(92), "/")
        except ValueError:
            pass
        return value
    return _transform_project_image_paths(data, relative)


def _project_image_paths(project):
    paths = []
    def visit(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _IMAGE_PATH_FIELDS and isinstance(value, str) and value.strip():
                    paths.append(value)
                else:
                    visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(project)
    return paths


def load_settings():
    s = {"out_dir": os.path.join(APP_DIR, "output"), "sts2_path": "", "godot_path": "", "last_project": ""}
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            s.update(stored)
    except (OSError, ValueError, TypeError):
        pass
    if not s["sts2_path"]:
        s["sts2_path"] = detect_sts2_path()
    return s


def save_settings(s):
    try:
        _atomic_write_json(SETTINGS_PATH, s)
    except (OSError, TypeError, ValueError):
        return False
    return True


def snapshot(project):
    return json.dumps(project, ensure_ascii=False, default=str)


class History:
    """프로젝트 상태(JSON 문자열) 기록. 각 단계에 '어디서 바뀌었는지(loc)'를 같이 남긴다."""

    def __init__(self, limit=200):
        self.limit = limit
        self.reset("")

    def reset(self, state):
        self.cur = state
        self.undos = []   # (이전 상태, 바뀐 곳)
        self.redos = []   # (다음 상태, 바뀐 곳)

    def push(self, state, loc):
        if state == self.cur:
            return False
        self.undos.append((self.cur, loc))
        if len(self.undos) > self.limit:
            del self.undos[0]
        self.redos.clear()
        self.cur = state
        return True

    def can_undo(self):
        return bool(self.undos)

    def can_redo(self):
        return bool(self.redos)

    def undo(self):
        prev, loc = self.undos.pop()
        self.redos.append((self.cur, loc))
        self.cur = prev
        return prev, loc

    def redo(self):
        nxt, loc = self.redos.pop()
        self.undos.append((self.cur, loc))
        self.cur = nxt
        return nxt, loc

"""
슬레이 더 스파이어 2 모드 메이커 (GUI)

카드 / 유물 / 물약 / 새 캐릭터를 화면에서 만들고, BaseLib 기반 C# 모드 프로젝트로 내보낸 뒤
dotnet 으로 빌드해 게임의 mods 폴더에 넣어 준다.

실행: python sts2_mod_maker.py   (Python 3.9+, 추가 설치 불필요)
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import sys
import threading
import tkinter as tk
import webbrowser
from tkinter import colorchooser, filedialog, messagebox, ttk

import gimmick as GM
import modgen as M
from pets import frame_ms
import modimport as MI
import preview as PV
from winpos import center_window
import uxkit as UX
import cardframe as CF

try:
    import ingame
    from PIL import ImageTk
except Exception:  # noqa: BLE001 - Pillow 가 없으면 게임 화면 미리보기는 끈다
    ingame = None

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
    "icon_image", "map_marker_image", "select_image", "select_locked_image",
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


# ---------------------------------------------------------------------------
# 설명 미리보기 (변수 → 숫자)
# ---------------------------------------------------------------------------
def render_preview(project, desc, item, upgraded=False, stacks=3):
    values = {"Amount": stacks}
    for e in item.get("effects", []):
        amount = int(e.get("amount", 0) or 0) + (int(e.get("upgrade", 0) or 0) if upgraded else 0)
        if e["kind"] == "power":
            pm = M.power_meta(project, e["power"])
            name = pm["var"] if pm else ""
        else:
            name = M.VAR_NAME.get(e["kind"], "")
        values[name] = amount

    def repl(m):
        name, rest = m.group(1), m.group(2) or ""
        v = values.get(name, "?")
        if rest.startswith(":plural:"):
            a, _, b = rest[len(":plural:"):].partition("|")
            return a if v == 1 else b
        if "energyIcons" in rest:
            return "⚡" * (v if isinstance(v, int) and 0 < v < 10 else 1)
        return str(v)

    out = re.sub(r"\{(\w+)(:[^{}]*)?\}", repl, desc)
    out = re.sub(r"\[/?[a-z_]+(=[^\]]*)?[^\]]*\]", "", out)
    return out


# ---------------------------------------------------------------------------
# 위젯 도우미
# ---------------------------------------------------------------------------
class LabeledCombo(ttk.Combobox):
    """내부 값(value)과 표시 이름(label)을 분리한 콤보박스."""

    def __init__(self, master, options, width=16, **kw):
        self.options = list(options)
        super().__init__(master, values=[l for _, l in self.options], state="readonly", width=width, **kw)

    def set_options(self, options):
        cur = self.get_value()
        self.options = list(options)
        self["values"] = [l for _, l in self.options]
        self.set_value(cur)

    def get_value(self):
        idx = self.current()
        return self.options[idx][0] if 0 <= idx < len(self.options) else (self.options[0][0] if self.options else "")

    def set_value(self, v):
        for i, (val, _l) in enumerate(self.options):
            if val == v:
                self.current(i)
                return
        if self.options:
            self.current(0)


class ScrollFrame(UX.AutoScroll):
    """세로·가로 자동 스크롤바 영역 (휠은 앱 전체 처리기 uxkit.install_wheel 이 굴린다)."""


def GM_cond_label(c, project):
    import blockcode
    return blockcode.cond_label(c, project, card=True)


def lang_entry(parent, store, key, label, on_change, width=44, row=0, col=1, span=3, label_col=0):
    """이름/설명 입력칸. key 가 *_en 이면 같은 줄에 *_zh (중국어 간체) 칸을 하나 더 만든다."""
    zh = key.endswith("_en")
    ttk.Label(parent, text=label.replace("(영어)", "(영어 / 中文)") if zh else label).grid(
        row=row, column=label_col, sticky="w", pady=2)
    holder = ttk.Frame(parent)
    holder.grid(row=row, column=col, columnspan=span, sticky="we", pady=2)
    keys = [key, key[:-3] + "_zh"] if zh else [key]
    for i, k in enumerate(keys):
        v = tk.StringVar()
        ttk.Entry(holder, textvariable=v, width=max(8, width // len(keys) - (1 if zh else 0))).pack(
            side="left", fill="x", expand=True, padx=(0, 4) if i == 0 and zh else 0)
        v.trace_add("write", lambda *_: on_change())
        store[k] = v
    return holder


def file_row(parent, row, label, var, on_change, filetypes=(("PNG 이미지", "*.png"),), hint=""):
    ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=4, pady=2)
    f = ttk.Frame(parent)
    f.grid(row=row, column=1, columnspan=3, sticky="we", padx=4, pady=2)
    ent = ttk.Entry(f, textvariable=var)
    ent.pack(side="left", fill="x", expand=True)

    def browse():
        p = filedialog.askopenfilename(filetypes=list(filetypes) + [("모든 파일", "*.*")])
        if p:
            var.set(p)
            on_change()

    ttk.Button(f, text="찾기…", width=6, command=browse).pack(side="left", padx=2)
    ttk.Button(f, text="지우기", width=6, command=lambda: (var.set(""), on_change())).pack(side="left")
    if hint:
        ttk.Label(f, text=hint, foreground="#777").pack(side="left", padx=6)
    return ent


# ---------------------------------------------------------------------------
# 효과 편집
# ---------------------------------------------------------------------------
class EffectDialog(tk.Toplevel):
    def __init__(self, master, effect, owner_kind, app, item):
        super().__init__(master)
        self.title("효과 편집")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.result = None
        self.owner_kind = owner_kind
        self.item = item or {}
        self.project = app.project
        e = dict(M.new_effect(), **(effect or {}))
        self.orig = e
        pad = dict(padx=6, pady=3)
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        popts = M.power_options(self.project)
        has_other = owner_kind == "power" and self.item.get("trigger") in M.POWER_OTHER

        # ---- 기본 ----
        basic = ttk.LabelFrame(body, text="기본", padding=6)
        basic.grid(row=0, column=0, sticky="we")
        ttk.Label(basic, text="효과 종류").grid(row=0, column=0, sticky="w", **pad)
        self.kind = LabeledCombo(basic, M.EFFECT_KINDS, width=26)
        self.kind.grid(row=0, column=1, columnspan=2, sticky="w", **pad)
        self.kind.set_value(e["kind"])

        self.amount_lbl = ttk.Label(basic, text="수치")
        self.amount_lbl.grid(row=1, column=0, sticky="w", **pad)
        self.amount = tk.StringVar(value=str(e["amount"]))
        self.amount_spin = ttk.Spinbox(basic, from_=0, to=999, textvariable=self.amount, width=8)
        self.amount_spin.grid(row=1, column=1, sticky="w", **pad)
        self.per_stack = tk.BooleanVar(value=bool(e.get("per_stack")))
        self.per_stack_chk = ttk.Checkbutton(basic, text="× 이 파워의 스택 수", variable=self.per_stack)
        self.per_stack_chk.grid(row=1, column=2, sticky="w", **pad)

        self.up_lbl = ttk.Label(basic, text="강화 시 +")
        self.up_lbl.grid(row=2, column=0, sticky="w", **pad)
        self.upgrade = tk.StringVar(value=str(e["upgrade"]))
        self.up_spin = ttk.Spinbox(basic, from_=-99, to=99, textvariable=self.upgrade, width=8)
        self.up_spin.grid(row=2, column=1, sticky="w", **pad)

        self.hits_lbl = ttk.Label(basic, text="타격 횟수")
        self.hits_lbl.grid(row=3, column=0, sticky="w", **pad)
        self.hits = tk.StringVar(value=str(e["hits"]))
        self.hits_spin = ttk.Spinbox(basic, from_=1, to=20, textvariable=self.hits, width=8)
        self.hits_spin.grid(row=3, column=1, sticky="w", **pad)

        self.pow_lbl = ttk.Label(basic, text="파워")
        self.pow_lbl.grid(row=4, column=0, sticky="w", **pad)
        self.power = LabeledCombo(basic, popts, width=30)
        self.power.grid(row=4, column=1, columnspan=2, sticky="w", **pad)
        self.power.set_value(e["power"])

        self.tgt_lbl = ttk.Label(basic, text="대상")
        self.tgt_lbl.grid(row=5, column=0, sticky="w", **pad)
        tgt_opts = [("self", "자신"), ("enemy", "적 (대상 설정을 따름)")]
        if has_other:
            tgt_opts.append(("other", f"상대 ({M.POWER_OTHER[self.item['trigger']]})"))
        self.target = LabeledCombo(basic, tgt_opts, width=30)
        self.target.grid(row=5, column=1, columnspan=2, sticky="w", **pad)
        self.target.set_value(e["target"])

        self.x_lbl = ttk.Label(basic, text="X 사용")
        self.x_lbl.grid(row=6, column=0, sticky="w", **pad)
        self.x_use = LabeledCombo(basic, M.X_USES, width=30)
        self.x_use.grid(row=6, column=1, columnspan=2, sticky="w", **pad)
        self.x_use.set_value(e.get("x_use", ""))
        UX.tip(self.x_lbl, "X 비용 카드에서 X(쓴 에너지) 를 어떻게 쓸지: 'X번 반복' = 이 효과를 X번 (피해는 타격 횟수 × X), "
                           "'수치 × X' = 수치에 X 를 곱함.")

        # ---- 조건 / 비례 ----
        on_opts = [("self", "자신")]
        if owner_kind in ("card", "potion"):
            on_opts.append(("target", "대상 (적 하나일 때)"))
        elif has_other:
            on_opts.append(("target", f"상대 ({M.POWER_OTHER[self.item['trigger']]})"))
        none_opt = [("", "(없음)")]

        cond = ttk.LabelFrame(body, text="조건 (선택) - 이 조건을 만족할 때만 효과 발동", padding=6)
        cond.grid(row=1, column=0, sticky="we", pady=(6, 0))
        self.cond_on = LabeledCombo(cond, on_opts, width=18)
        self.cond_on.grid(row=0, column=0, sticky="w", **pad)
        self.cond_on.set_value(e.get("cond_on", "self"))
        ttk.Label(cond, text="의").grid(row=0, column=1)
        self.cond_power = LabeledCombo(cond, none_opt + popts, width=24)
        self.cond_power.grid(row=0, column=2, sticky="w", **pad)
        self.cond_power.set_value(e.get("cond_power", ""))
        ttk.Label(cond, text="이(가)").grid(row=0, column=3)
        self.cond_min = tk.StringVar(value=str(e.get("cond_min", 1)))
        ttk.Spinbox(cond, from_=1, to=999, textvariable=self.cond_min, width=6).grid(row=0, column=4, **pad)
        ttk.Label(cond, text="이상이면").grid(row=0, column=5)

        self.scale_frame = ttk.LabelFrame(body, text="스택 비례 추가 (선택) - 수치 + (파워 스택 × N)", padding=6)
        self.scale_frame.grid(row=2, column=0, sticky="we", pady=(6, 0))
        self.scale_on = LabeledCombo(self.scale_frame, on_opts, width=18)
        self.scale_on.grid(row=0, column=0, sticky="w", **pad)
        self.scale_on.set_value(e.get("scale_on", "self"))
        ttk.Label(self.scale_frame, text="의").grid(row=0, column=1)
        self.scale_power = LabeledCombo(self.scale_frame, none_opt + popts, width=24)
        self.scale_power.grid(row=0, column=2, sticky="w", **pad)
        self.scale_power.set_value(e.get("scale_power", ""))
        ttk.Label(self.scale_frame, text="1당 +").grid(row=0, column=3)
        self.scale_per = tk.StringVar(value=str(e.get("scale_per", 1)))
        ttk.Spinbox(self.scale_frame, from_=-99, to=99, textvariable=self.scale_per, width=6).grid(row=0, column=4, **pad)

        # ---- 직접 코드 ----
        self.blocks = list(e.get("blocks") or [])
        self.auto_text = bool(e.get("auto_text", True))
        self.code_frame = ttk.LabelFrame(body, text="새 능력 (블록 코딩 또는 직접 C# 코드)", padding=6)
        self.code_frame.grid(row=3, column=0, sticky="we", pady=(6, 0))
        bbar = ttk.Frame(self.code_frame)
        bbar.grid(row=0, column=0, columnspan=2, sticky="we", pady=(0, 4))
        ttk.Button(bbar, text="🧩 블록 코딩으로 만들기 / 편집", command=self.open_blocks).pack(side="left")
        self.unblock_btn = ttk.Button(bbar, text="블록 해제 (C# 직접 편집)", command=self.release_blocks)
        self.unblock_btn.pack(side="left", padx=6)
        self.block_info = ttk.Label(bbar, text="", foreground="#2d6a4f")
        self.block_info.pack(side="left", padx=6)
        self.code = tk.Text(self.code_frame, width=72, height=9, font=("Consolas", 10), wrap="none", undo=True)
        self.code.grid(row=1, column=0, columnspan=2, sticky="we")
        self.code.insert("1.0", e.get("code", ""))
        ttk.Label(self.code_frame, text=CODE_HELP.get(owner_kind, ""), foreground="#555", justify="left",
                  font=("Malgun Gothic", 8)).grid(row=2, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(self.code_frame, text="설명 문구 (한국어)").grid(row=3, column=0, sticky="w")
        self.text_ko = tk.StringVar(value=e.get("text_ko", ""))
        self.text_ko_entry = ttk.Entry(self.code_frame, textvariable=self.text_ko, width=60)
        self.text_ko_entry.grid(row=3, column=1, sticky="we", pady=2)
        ttk.Label(self.code_frame, text="설명 문구 (영어)").grid(row=4, column=0, sticky="w")
        self.text_en = tk.StringVar(value=e.get("text_en", ""))
        self.text_en_entry = ttk.Entry(self.code_frame, textvariable=self.text_en, width=60)
        self.text_en_entry.grid(row=4, column=1, sticky="we", pady=2)
        ttk.Label(self.code_frame, text="설명 문구 (중국어 간체)").grid(row=5, column=0, sticky="w")
        self.text_zh = tk.StringVar(value=e.get("text_zh", ""))
        self.text_zh_entry = ttk.Entry(self.code_frame, textvariable=self.text_zh, width=60)
        self.text_zh_entry.grid(row=5, column=1, sticky="we", pady=2)
        self._sync_block_ui()

        self.note = ttk.Label(body, text="", foreground="#777", wraplength=560, justify="left")
        self.note.grid(row=4, column=0, sticky="w", pady=(6, 0))

        btns = ttk.Frame(body)
        btns.grid(row=5, column=0, sticky="e", pady=(8, 0))
        ttk.Button(btns, text="확인", command=self.ok).pack(side="left", padx=4)
        ttk.Button(btns, text="취소", command=self.destroy).pack(side="left")

        self.kind.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        self.power.bind("<<ComboboxSelected>>", lambda _e: self._power_default())
        self.refresh()
        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self)
        self.grab_set()
        self.wait_visibility()
        self.focus_set()

    def _sync_block_ui(self):
        """블록이 있으면 C# 칸은 자동 생성 결과를 읽기 전용으로 보여 줍니다."""
        has = bool(self.blocks)
        if has:
            import blockcode
            lines, errs = blockcode.compile_blocks(self.blocks, self.project, M._Ctx(self.owner_kind, self.item), "")
            self.code.configure(state="normal")
            self.code.delete("1.0", "end")
            self.code.insert("1.0", "\n".join(lines))
            self.code.configure(state="disabled", background="#f1f3f5")
            n = sum(1 for _ in blockcode.walk(self.blocks))
            info = f"🧩 블록 {n}개로 만든 능력"
            if self.auto_text:
                info += " · 설명 자동"
            if errs:
                info += f" · ⚠ 문제 {len(set(errs))}개"
            self.block_info.configure(text=info, foreground="#c0392b" if errs else "#2d6a4f")
            self.unblock_btn.configure(state="normal")
            if self.auto_text:
                self.text_ko.set(blockcode.describe(self.blocks, self.project, self.owner_kind, "ko"))
                self.text_en.set(blockcode.describe(self.blocks, self.project, self.owner_kind, "en"))
                self.text_zh.set(blockcode.describe(self.blocks, self.project, self.owner_kind, "zh"))
        else:
            self.code.configure(state="normal", background="white")
            self.block_info.configure(text="")
            self.unblock_btn.configure(state="disabled")
        st = "disabled" if has and self.auto_text else "normal"
        self.text_ko_entry.configure(state=st)
        self.text_en_entry.configure(state=st)
        self.text_zh_entry.configure(state=st)

    def open_blocks(self):
        import blockui
        ed = blockui.BlockEditor(self, self.project, self.owner_kind, self.item, self.blocks,
                                 self.text_ko.get(), self.text_en.get(), self.auto_text if self.blocks else True,
                                 text_zh=self.text_zh.get())
        self.wait_window(ed)
        try:
            self.grab_set()
        except tk.TclError:
            pass
        if ed.result is None:
            return
        self.blocks = ed.result["blocks"]
        self.auto_text = ed.result["auto_text"]
        if not self.auto_text:
            self.text_ko.set(ed.result["text_ko"])
            self.text_en.set(ed.result["text_en"])
            self.text_zh.set(ed.result.get("text_zh", ""))
        self._sync_block_ui()

    def release_blocks(self):
        if not messagebox.askyesno(APP_TITLE, "블록을 해제하고 지금 만들어진 C# 코드를 직접 편집할까요?\n"
                                              "(블록 편집기로는 다시 돌아갈 수 없습니다)", parent=self):
            return
        self.blocks = []
        self.auto_text = False
        self._sync_block_ui()

    def _power_default(self):
        pm = M.power_meta(self.project, self.power.get_value())
        if pm and self.kind.get_value() == "power":
            self.target.set_value(pm["target"])

    def refresh(self):
        k = self.kind.get_value()
        is_power_owner = self.owner_kind == "power"

        def show(widgets, on):
            for w in widgets:
                if on:
                    w.grid()
                else:
                    w.grid_remove()

        show([self.amount_lbl, self.amount_spin], k != "code")
        show([self.per_stack_chk], is_power_owner and k not in ("code", "remove_power"))
        show([self.up_lbl, self.up_spin], self.owner_kind == "card" and k not in ("code", "remove_power"))
        show([self.hits_lbl, self.hits_spin], k == "damage")
        show([self.pow_lbl, self.power], k in ("power", "remove_power"))
        show([self.tgt_lbl, self.target], k in ("power", "remove_power") or (k == "damage" and is_power_owner))
        show([self.x_lbl, self.x_use], self.owner_kind == "card" and bool(self.item.get("x_cost")))
        show([self.scale_frame], k not in ("code", "remove_power"))
        show([self.code_frame], k == "code")
        self.amount_lbl.configure(text="제거량 (0 = 전부)" if k == "remove_power" else "수치")
        notes = {
            "damage": "카드: 카드의 대상(적 하나/모든 적/무작위)으로 공격합니다. 유물·파워는 '적 대상' 설정, 물약은 물약 대상을 따릅니다.",
            "power": "★ 표시는 '파워' 탭에서 직접 만든 새 파워입니다.",
            "remove_power": "대상이 가진 파워를 줄이거나 없앱니다. 예: 쌓아 둔 '불씨'를 터뜨리는 카드.",
            "lose_hp": "방어도를 무시하고 자신의 체력을 잃습니다.",
            "code": "🧩 블록 코딩: 블록을 끌어다 쌓아 새 능력을 만들면 C# 코드와 설명이 자동으로 만들어집니다. "
                    "블록 없이 C#을 직접 써도 됩니다 (문법 오류는 ③ 빌드 때 로그에 나옵니다).",
        }
        self.note.configure(text=notes.get(k, ""))
        if k == "damage" and not is_power_owner:
            self.target.set_value("enemy")

    def ok(self):
        try:
            amount = int(self.amount.get() or 0)
            upgrade = int(self.upgrade.get() or 0)
            hits = int(self.hits.get() or 1)
            cond_min = int(self.cond_min.get() or 1)
            scale_per = int(self.scale_per.get() or 0)
        except ValueError:
            messagebox.showerror(APP_TITLE, "숫자를 입력하세요.", parent=self)
            return
        k = self.kind.get_value()
        use_blocks = k == "code" and bool(self.blocks)
        if k == "code" and not use_blocks and not self.code.get("1.0", "end").strip():
            messagebox.showerror(APP_TITLE, "블록 코딩으로 만들거나 코드를 입력하세요.", parent=self)
            return
        keep_text = k == "code" and not (use_blocks and self.auto_text)
        tgt = self.target.get_value()
        if k not in ("power", "remove_power") and not (k == "damage" and self.owner_kind == "power"):
            tgt = "enemy"
        if k == "damage" and tgt == "self":
            tgt = "enemy"
        self.result = {
            "kind": k, "amount": amount, "upgrade": upgrade if self.owner_kind == "card" else 0,
            "hits": max(1, hits), "power": self.power.get_value(), "target": tgt,
            "per_stack": bool(self.per_stack.get()) and self.owner_kind == "power",
            "x_use": self.x_use.get_value() if self.owner_kind == "card" and self.item.get("x_cost") else "",
            "cond_power": self.cond_power.get_value(), "cond_min": cond_min, "cond_on": self.cond_on.get_value(),
            "scale_power": self.scale_power.get_value() if k not in ("code", "remove_power") else "",
            "scale_per": scale_per, "scale_on": self.scale_on.get_value(),
            "code": self.code.get("1.0", "end").rstrip() if k == "code" else "",
            "blocks": self.blocks if use_blocks else [],
            "auto_text": self.auto_text if use_blocks else False,
            # 설명 자동이면 비워 두고 빌드 때 블록에서 만듭니다 (블록과 설명이 어긋나지 않게)
            "text_ko": self.text_ko.get().strip() if keep_text else "",
            "text_en": self.text_en.get().strip() if keep_text else "",
            "text_zh": self.text_zh.get().strip() if keep_text else "",
        }
        self.destroy()


CODE_HELP = {
    "card": "쓸 수 있는 것: choiceContext, cardPlay (cardPlay.Target = 대상), Owner (플레이어), Owner.Creature, "
            "DynamicVars, this\n예: await CreatureCmd.GainBlock(Owner.Creature, 5m, ValueProp.Move, cardPlay);",
    "relic": "쓸 수 있는 것: choiceContext, Owner (플레이어), Owner.Creature, DynamicVars, Flash()\n"
             "예: await PlayerCmd.GainEnergy(1m, Owner);",
    "potion": "쓸 수 있는 것: choiceContext, target (대상, null 가능), Owner (플레이어), Owner.Creature\n"
              "예: if (target != null) await CreatureCmd.Damage(choiceContext, target, 10m, ValueProp.Unpowered, Owner.Creature, null, null);",
    "power": "쓸 수 있는 것: choiceContext, Owner (파워를 가진 생물), Owner.Player (플레이어면), Amount (스택 수), "
             "other (상대, null 가능), OwnerEnemies(), RandomOwnerEnemy()\n"
             "예: await CreatureCmd.Heal(Owner, Amount);",
}


def effect_summary(project, e):
    parts = []
    if e["kind"] == "damage" and int(e.get("hits", 1)) > 1:
        parts.append(f"{e['hits']}회 타격")
    if e["kind"] in ("power", "remove_power"):
        pm = M.power_meta(project, e["power"])
        name = pm["ko"] if pm else f"⚠{e['power']}"
        parts.append(f"{name} → {dict(self='자신', enemy='적', other='상대').get(e['target'], e['target'])}")
    if e.get("per_stack"):
        parts.append("×스택")
    sm = M.power_meta(project, e.get("scale_power"))
    if sm and int(e.get("scale_per", 0) or 0):
        parts.append(f"+{sm['ko']}×{e['scale_per']}")
    cm = M.power_meta(project, e.get("cond_power"))
    if cm:
        parts.append(f"조건: {cm['ko']}≥{e.get('cond_min', 1)}")
    if e["kind"] == "code" and e.get("blocks"):
        import blockcode
        n = sum(1 for _ in blockcode.walk(e["blocks"]))
        d = blockcode.describe(e["blocks"], project, "card", "ko")
        d = re.sub(r"\{IfUpgraded:show:([^|}]*)\|([^}]*)\}", r"\2", d)
        d = re.sub(r"\[/?[a-z_]+\]", "", d)
        parts.append(f"🧩 블록 {n}개: {d[:50]}")
    elif e["kind"] == "code":
        first = (e.get("code") or "").strip().split("\n")[0]
        parts.append(first[:40])
    return ", ".join(parts)


class EffectList(ttk.Frame):
    def __init__(self, master, owner_kind, on_change, app, get_item):
        super().__init__(master)
        self.owner_kind = owner_kind
        self.on_change = on_change
        self.app = app
        self.get_item = get_item
        self.effects = []
        cols = ("kind", "amount", "upgrade", "extra")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=6, selectmode="browse")
        for c, t, w in zip(cols, ("효과", "수치", "강화", "추가 정보"), (150, 60, 60, 300)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        if owner_kind != "card":
            self.tree["displaycolumns"] = ("kind", "amount", "extra")
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        bf = ttk.Frame(self)
        bf.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        for txt, cmd in (("추가", self.add), ("편집", self.edit), ("삭제", self.remove), ("▲", lambda: self.move(-1)),
                         ("▼", lambda: self.move(1))):
            ttk.Button(bf, text=txt, width=6, command=cmd).pack(pady=1)
        self.columnconfigure(0, weight=1)

    def set(self, effects):
        self.effects = effects
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self.effects):
            up = e.get("upgrade", 0)
            amt = "" if e["kind"] == "code" else ("전부" if e["kind"] == "remove_power" and not e["amount"] else e["amount"])
            self.tree.insert("", "end", iid=str(i),
                             values=(M.EFFECT_LABEL.get(e["kind"], e["kind"]), amt,
                                     (f"+{up}" if up > 0 else str(up)) if up else "-",
                                     effect_summary(self.app.project, e)))

    def _sel(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def _dialog(self, effect):
        d = EffectDialog(self, effect, self.owner_kind, self.app, self.get_item())
        self.wait_window(d)
        return d.result

    def add(self):
        r = self._dialog(None)
        if r:
            self.effects.append(r)
            self.refresh()
            self.on_change()

    def edit(self):
        i = self._sel()
        if i is None:
            return
        r = self._dialog(self.effects[i])
        if r:
            self.effects[i] = r
            self.refresh()
            self.tree.selection_set(str(i))
            self.on_change()

    def remove(self):
        i = self._sel()
        if i is None:
            return
        del self.effects[i]
        self.refresh()
        self.on_change()

    def move(self, d):
        i = self._sel()
        if i is None or not 0 <= i + d < len(self.effects):
            return
        self.effects[i], self.effects[i + d] = self.effects[i + d], self.effects[i]
        self.refresh()
        self.tree.selection_set(str(i + d))
        self.on_change()


class ModifierDialog(tk.Toplevel):
    def __init__(self, master, mod):
        super().__init__(master)
        self.title("상시 효과 편집")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.result = None
        m = dict(M.new_modifier(), **(mod or {}))
        f = ttk.Frame(self, padding=10)
        f.pack()
        ttk.Label(f, text="종류").grid(row=0, column=0, sticky="w", padx=4, pady=3)
        self.kind = LabeledCombo(f, M.MODIFIER_KINDS, width=30, height=20)
        self.kind.grid(row=0, column=1, sticky="w", padx=4, pady=3)
        self.kind.set_value(m["kind"])
        ttk.Label(f, text="수치").grid(row=1, column=0, sticky="w", padx=4, pady=3)
        self.value = tk.StringVar(value=str(m["value"]))
        ttk.Spinbox(f, from_=-999, to=999, textvariable=self.value, width=8).grid(row=1, column=1, sticky="w", padx=4)
        self.per_stack = tk.BooleanVar(value=bool(m["per_stack"]))
        ttk.Checkbutton(f, text="× 이 파워의 스택 수", variable=self.per_stack).grid(row=2, column=1, sticky="w", padx=4)
        project = getattr(master.winfo_toplevel(), "project", None) or {"gimmicks": {}}
        ttk.Label(f, text="어떤 카드에").grid(row=3, column=0, sticky="w", padx=4, pady=3)
        self.filter = LabeledCombo(f, GM.card_filters(project), width=24)
        self.filter.grid(row=3, column=1, sticky="w", padx=4, pady=3)
        self.filter.set_value(m.get("filter") or "Any")
        self.project = project
        self.ref_lbl = ttk.Label(f, text="무엇에")
        self.ref_lbl.grid(row=4, column=0, sticky="w", padx=4, pady=3)
        self.ref = LabeledCombo(f, [("", "")], width=30)
        self.ref.grid(row=4, column=1, sticky="w", padx=4, pady=3)
        self._ref_init = m.get("ref") or ""
        ttk.Label(f, text="음수는 감소입니다. % 종류는 50 = 50% 증가, -25 = 25% 감소.\n"
                          "'공격 피해'는 카드 공격처럼 힘의 영향을 받는 피해에만 적용됩니다.\n"
                          "'어떤 카드에'는 공격 피해 / 카드 비용 / 별 비용 / 자원 비용에 쓰입니다 (예: #격투 카드 피해 +2).\n"
                          "기믹 종류: 구체 수치(밀집처럼)·구체 슬롯·별 비용·골골이·소환 슬롯·자원 최대치/비용·버튼 비용/횟수.",
                  foreground="#777", justify="left").grid(row=5, column=0, columnspan=2, sticky="w", pady=6)
        self.kind.bind("<<ComboboxSelected>>", lambda _e: self._kind_changed(), add="+")
        self._kind_changed(first=True)
        b = ttk.Frame(f)
        b.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(b, text="확인", command=self.ok).pack(side="left", padx=4)
        ttk.Button(b, text="취소", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda _e: self.ok())
        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self)
        self.grab_set()
        self.wait_visibility()

    def _kind_changed(self, first=False):
        import fxbtn
        k = self.kind.get_value()
        need = M.MODIFIER_REF.get(k)
        if need:
            what, optional = need
            if what == "orb":
                opts, lbl = [("", "모든 구체")] + GM.orb_options(self.project), "어떤 구체에"
            elif what == "power":
                opts, lbl = [("", "(자원 파워를 고르세요)")] + M.power_options(self.project), "어떤 자원에"
            elif what == "pet":
                import pets as PT
                opts, lbl = [("", "모든 동료")] + [(p["id"], p.get("name_ko") or p["id"]) for p in PT.pets(self.project)], "어떤 동료에"
            else:
                opts, lbl = [("", "모든 버튼")] + [(b["id"], b.get("label_ko") or b["id"]) for b in fxbtn.buttons(self.project)], "어떤 버튼에"
            cur = self._ref_init if first else self.ref.get_value()
            self.ref.set_options(opts)
            self.ref.set_value(cur)
            self.ref_lbl.configure(text=lbl)
            self.ref.grid()
            self.ref_lbl.grid()
        else:
            self.ref.grid_remove()
            self.ref_lbl.grid_remove()
        for w in (self.filter,):
            w.configure(state="readonly" if k in M.MODIFIER_FILTERED else "disabled")

    def ok(self):
        try:
            v = int(self.value.get())
        except ValueError:
            messagebox.showerror(APP_TITLE, "숫자를 입력하세요.", parent=self)
            return
        k = self.kind.get_value()
        ref = self.ref.get_value() if k in M.MODIFIER_REF else ""
        if k in M.MODIFIER_REF and not M.MODIFIER_REF[k][1] and not ref:
            messagebox.showerror(APP_TITLE, "어떤 자원에 적용할지 고르세요.", parent=self)
            return
        self.result = {"kind": k, "value": v, "per_stack": bool(self.per_stack.get()),
                       "filter": self.filter.get_value() if k in M.MODIFIER_FILTERED else "Any", "ref": ref}
        self.destroy()


class ModifierList(ttk.Frame):
    def __init__(self, master, on_change):
        super().__init__(master)
        self.on_change = on_change
        self.mods = []
        self.tree = ttk.Treeview(self, columns=("kind", "value", "stack"), show="headings", height=4, selectmode="browse")
        for c, t, w in (("kind", "상시 효과", 200), ("value", "수치", 80), ("stack", "스택 비례", 100)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        bf = ttk.Frame(self)
        bf.grid(row=0, column=1, sticky="ns", padx=(4, 0))
        for txt, cmd in (("추가", self.add), ("편집", self.edit), ("삭제", self.remove)):
            ttk.Button(bf, text=txt, width=6, command=cmd).pack(pady=1)
        self.columnconfigure(0, weight=1)

    def set(self, mods):
        self.mods = mods
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for i, m in enumerate(self.mods):
            unit = "%" if m["kind"].endswith("pct") else ""
            label = M.MODIFIER_LABEL.get(m["kind"], m["kind"])
            if (m.get("filter") or "Any") != "Any":
                proj = getattr(self.winfo_toplevel(), "project", None) or {"gimmicks": {}}
                label += f"  [{M.label_of(GM.card_filters(proj), m['filter'])}]"
            if m.get("ref"):
                proj = getattr(self.winfo_toplevel(), "project", None) or {"gimmicks": {}}
                label += f"  → {GM._ref_name(proj, m, 'ko')}"
            if m["kind"] in M.MODIFIER_NO_VALUE:
                label = label.replace(" +", "")
            self.tree.insert("", "end", iid=str(i), values=(label,
                                                            f"{m['value']:+d}{unit}", "예" if m["per_stack"] else "-"))

    def _sel(self):
        s = self.tree.selection()
        return int(s[0]) if s else None

    def add(self):
        d = ModifierDialog(self, None)
        self.wait_window(d)
        if d.result:
            self.mods.append(d.result)
            self.refresh()
            self.on_change()

    def edit(self):
        i = self._sel()
        if i is None:
            return
        d = ModifierDialog(self, self.mods[i])
        self.wait_window(d)
        if d.result:
            self.mods[i] = d.result
            self.refresh()
            self.on_change()

    def remove(self):
        i = self._sel()
        if i is None:
            return
        del self.mods[i]
        self.refresh()
        self.on_change()



IMAGE_RECOMMEND = {"card": (250, 190), "relic": (94, 94), "potion": (256, 256), "power": (64, 64)}


class AsyncTiles:
    """캔버스 격자 그림을 백그라운드에서 만들어 하나씩 채운다 (많은 카드를 불러와도 화면이 멈추지 않게)."""

    def __init__(self, widget, canvas):
        self.w, self.c = widget, canvas
        self.gen = 0
        self.jobs = queue.Queue()
        self.results = queue.Queue()
        self.photos = {}
        self.tiles = []
        self.polling = False
        threading.Thread(target=self._worker, daemon=True).start()

    def begin(self):
        self.gen += 1
        self.photos = {}
        self.tiles = []

    def add(self, key, x, y, w, h, tags, make):
        """make(): 백그라운드에서 PIL 그림을 돌려주는 함수 (None 이면 빈 칸 유지)."""
        self.c.create_rectangle(x + 8, y + 8, x + w - 8, y + h - 8, fill="#1c1e26", outline="#2b2e39", width=2,
                                tags=tags + (f"ph_{key}",))
        self.c.create_text(x + w / 2, y + h / 2, text="…", fill="#555a66", font=("Malgun Gothic", 14),
                           tags=tags + (f"ph_{key}",))
        self.tiles.append((key, x, y, w, h, tags, make))

    def start(self):
        top = self.c.canvasy(0)
        bottom = top + max(1, self.c.winfo_height())

        def prio(t):
            _k, _x, y, _w, h, _tags, _m = t
            visible = y + h >= top and y <= bottom
            return (0 if visible else 1, abs(y - top))
        gen = self.gen
        for t in sorted(self.tiles, key=prio):
            self.jobs.put((gen, t))
        if not self.polling:
            self.polling = True
            self.w.after(20, self._poll)

    def _worker(self):
        while True:
            gen, t = self.jobs.get()
            if gen != self.gen:
                continue
            key, x, y, w, h, tags, make = t
            try:
                img = make()
                if img is not None and img.size != (int(w), int(h)):
                    sc = min(w / img.size[0], h / img.size[1])
                    img = img.resize((max(1, int(img.size[0] * sc)), max(1, int(img.size[1] * sc))), ingame.Image.LANCZOS)
            except Exception:  # noqa: BLE001
                img = None
            self.results.put((gen, t, img))

    def _poll(self):
        n = 0
        try:
            while n < 16:
                gen, t, img = self.results.get_nowait()
                n += 1
                if gen != self.gen or img is None:
                    continue
                key, x, y, w, h, tags, _make = t
                photo = ImageTk.PhotoImage(img)
                self.photos[key] = photo
                self.c.delete(f"ph_{key}")
                iid = self.c.create_image(x + w / 2, y, image=photo, anchor="n", tags=tags)
                self.c.tag_lower(iid)
        except queue.Empty:
            pass
        if n == 0 and self.jobs.empty() and self.results.empty():
            self.polling = False
            return
        self.w.after(15 if n else 40, self._poll)



class PreviewPanel(ttk.Frame):
    """오른쪽 실시간 미리보기 (카드 / 유물 / 물약 / 파워)."""

    def __init__(self, master, app, kind):
        super().__init__(master, padding=6)
        self.app, self.kind, self.item = app, kind, None
        self._job = None
        self._photo = None
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="미리보기", font=("Malgun Gothic", 10, "bold")).pack(side="left")
        langs = [("ko", "한국어"), ("en", "English")]
        self.preview_lang = app.pv_lang
        if kind in ("card", "relic", "potion", "power"):
            langs.append(("zh", "简体中文"))
            self.preview_lang = tk.StringVar(value=app.pv_lang.get())
        for val, lbl in langs:
            ttk.Radiobutton(top, text=lbl, value=val, variable=self.preview_lang,
                            command=app.refresh_previews).pack(side="left", padx=(8, 0))
        mode = ttk.Frame(self)
        mode.pack(fill="x", pady=(2, 0))
        for val, lbl in (("game", "게임 화면"), ("simple", "간단히")):
            ttk.Radiobutton(mode, text=lbl, value=val, variable=app.pv_mode,
                            command=app.refresh_previews).pack(side="left", padx=(0, 8))
        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=(2, 4))
        if kind == "card":
            ttk.Checkbutton(opt, text="강화(+) 상태로 보기", variable=app.pv_upgraded,
                            command=app.refresh_previews).pack(side="left")
        elif kind == "power":
            ttk.Label(opt, text="스택 수").pack(side="left")
            sp = ttk.Spinbox(opt, from_=1, to=99, textvariable=app.pv_stacks, width=5, command=app.refresh_previews)
            sp.pack(side="left", padx=4)
            sp.bind("<KeyRelease>", lambda _e: app.refresh_previews())
        else:
            ttk.Label(opt, text=" ").pack(side="left")
        u = app.ui
        self.cw, self.ch = int(360 * u), int(480 * u)
        self.canvas = tk.Canvas(self, width=self.cw, height=self.ch, background="#121318", highlightthickness=0)
        self.canvas.pack()
        self.info = ttk.Label(self, text="", foreground="#666", wraplength=self.cw, justify="left")
        self.info.pack(fill="x", pady=(6, 0))

    def show(self, item):
        """입력 중에는 잠깐 기다렸다가 한 번만 그린다."""
        self.item = item
        if self._job:
            self.after_cancel(self._job)
        self._job = self.after(90, self._render)

    def _render(self):
        self._job = None
        item = self.item
        c = self.canvas
        c.delete("all")
        if not item:
            self.info.configure(text="")
            return
        P = self.app.project
        try:
            stacks = max(1, int(self.app.pv_stacks.get()))
        except ValueError:
            stacks = 3
        lang, upgraded = self.preview_lang.get(), bool(self.app.pv_upgraded.get())
        game_note = ""
        drawn = False
        if self.app.pv_mode.get() == "game":
            img, err = self.app.game_image(self.kind, item, lang, upgraded, stacks)
            if img is not None:
                sc = min(self.cw / img.size[0], self.ch / img.size[1])
                disp = img.resize((max(1, int(img.size[0] * sc)), max(1, int(img.size[1] * sc))), ingame.Image.LANCZOS)
                self._photo = ImageTk.PhotoImage(disp)
                c.create_image(self.cw // 2, 4, image=self._photo, anchor="n")
                drawn = True
                game_note = "게임 파일(" + self.app.game_version() + ")의 실제 틀·글꼴로 합성한 화면입니다."
            else:
                game_note = f"게임 화면을 만들 수 없어 간단히 표시합니다: {err}"
        if not drawn:
            try:
                u = self.app.ui
                PV.render_item(c, P, self.kind, item, 10 * u, 10 * u, u, lang, upgraded, stacks)
            except Exception as e:  # noqa: BLE001 - 미리보기 실패가 편집을 막지 않게
                c.create_text(160, 200, text=f"미리보기 오류:\n{e}", fill="#f66", width=280)
        gid = M.power_loc_id(P, item["id"]) if self.kind == "power" else M.loc_id(P, item["id"])
        lines = [f"게임 ID: {gid}"]
        rw, rh = IMAGE_RECOMMEND[self.kind]
        img = item.get("image")
        if img:
            sz = PV.IMAGES.info(img)
            if sz is None:
                lines.append("⚠ 그림 파일을 읽을 수 없습니다.")
            else:
                lines.append(f"그림: {sz[0]}×{sz[1]} (권장 {rw}×{rh})")
                r1, r2 = sz[0] / sz[1], rw / rh
                if abs(r1 - r2) / r2 > 0.08:
                    lines.append("비율이 권장과 달라 그림 칸에 빈 곳이 생깁니다.")
        else:
            lines.append("그림 없음 → 게임에서도 모드의 임시 그림이 보입니다.")
        if game_note:
            lines.append(game_note)
        self.info.configure(text="\n".join(lines))


class GalleryTab(ttk.Frame):
    """모든 카드 / 유물 / 물약 / 파워를 한눈에 보는 도감."""

    SIZES = [("small", "작게", 0.5), ("medium", "보통", 0.65), ("large", "크게", 0.85)]

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        self.filter = tk.StringVar(value="all")
        for val, lbl in (("all", "전체"), ("card", "카드"), ("relic", "유물"), ("potion", "물약"), ("power", "파워")):
            ttk.Radiobutton(bar, text=lbl, value=val, variable=self.filter, command=self.refresh).pack(side="left", padx=3)
        ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=10)
        for val, lbl in (("ko", "한국어"), ("en", "English"), ("zh", "简体中文")):
            ttk.Radiobutton(bar, text=lbl, value=val, variable=app.pv_lang,
                            command=app.refresh_previews).pack(side="left", padx=3)
        ttk.Checkbutton(bar, text="카드 강화(+)", variable=app.pv_upgraded,
                        command=app.refresh_previews).pack(side="left", padx=8)
        for val, lbl in (("game", "게임 화면"), ("simple", "간단히")):
            ttk.Radiobutton(bar, text=lbl, value=val, variable=app.pv_mode,
                            command=app.refresh_previews).pack(side="left", padx=3)
        ttk.Label(bar, text="크기").pack(side="left", padx=(10, 2))
        self.size = LabeledCombo(bar, [(v, l) for v, l, _ in self.SIZES], width=6)
        self.size.set_value("medium")
        self.size.pack(side="left")
        self.size.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(bar, text="클릭하면 편집 화면으로 이동합니다.", foreground="#777").pack(side="right")
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#121318", highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_resize)
        self._last_w = 0
        self._pending = None
        self._photos = []
        self.tiles = AsyncTiles(self, self.canvas)

    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_resize(self, e):
        if abs(e.width - self._last_w) < 20:
            return
        self._last_w = e.width
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(150, self.refresh)

    def refresh(self):
        self._pending = None
        c = self.canvas
        c.delete("all")
        self._photos = []
        self.tiles.begin()
        if self.app.nb.select() != str(self):
            return
        game = self.app.pv_mode.get() == "game" and self.app.game_assets() is not None
        P = self.app.project
        scale = dict((v, k) for v, _l, k in self.SIZES).get(self.size.get_value(), 0.65) * self.app.ui
        width = max(300, c.winfo_width())
        lang = self.app.pv_lang.get()
        try:
            stacks = max(1, int(self.app.pv_stacks.get()))
        except ValueError:
            stacks = 3
        gap, pad = 14, 16
        y = 10
        sections = [("card", "cards", "카드", 420), ("relic", "relics", "유물", 400),
                    ("potion", "potions", "물약", 400), ("power", "powers", "파워", 400)]
        for kind, key, title, base_h in sections:
            if self.filter.get() not in ("all", kind):
                continue
            items = P.get(key, [])
            c.create_text(pad, y, text=f"{title}  ({len(items)})", anchor="nw", fill="#e8e2d0",
                          font=("Malgun Gothic", 13, "bold"))
            y += 34
            tw, th = 300 * scale, base_h * scale
            if game and kind == "card":
                tw, th = 344 * scale, 460 * scale
            cols = max(1, int((width - pad * 2 + gap) // (tw + gap)))
            for i, it in enumerate(items):
                col, row = i % cols, i // cols
                x0 = pad + col * (tw + gap)
                y0 = y + row * (th + gap + 18)
                tag = f"g_{kind}_{i}"
                try:
                    if game:
                        up_ = bool(self.app.pv_upgraded.get())
                        snap = json.loads(json.dumps(it))
                        key = json.dumps([snap, self.app.project["character"], self.app.project.get("powers", []),
                                          self.app.project.get("card_frames", [])],
                                         sort_keys=True, ensure_ascii=False)
                        self.tiles.add(f"{kind}_{i}", x0, y0, tw, th, (tag,),
                                       lambda snap_=snap, key_=key, kind_=kind, up__=up_, tw_=tw, th_=th: self.app.thumb(
                                           key_, lambda: snap_, kind_, lang, up__, stacks, tw_, th_))
                    else:
                        PV.render_item(c, P, kind, it, x0, y0, scale, lang, bool(self.app.pv_upgraded.get()), stacks,
                                       tags=(tag,))
                except Exception as e:  # noqa: BLE001
                    c.create_text(x0 + tw / 2, y0 + th / 2, text=f"오류: {e}", fill="#f66", width=tw, tags=(tag,))
                c.create_text(x0 + tw / 2, y0 + th + 2, text=it["id"], anchor="n", fill="#777",
                              font=("Consolas", 8), tags=(tag,))
                c.tag_bind(tag, "<Button-1>", lambda _e, k=kind, j=i: self.app.goto(k, j))
                c.tag_bind(tag, "<Enter>", lambda _e: c.configure(cursor="hand2"))
                c.tag_bind(tag, "<Leave>", lambda _e: c.configure(cursor=""))
            rows = (len(items) + cols - 1) // cols
            y += rows * (th + gap + 18) + 20
            if not items:
                c.create_text(pad, y - 10, text="(없음)", anchor="nw", fill="#666")
                y += 20
        c.configure(scrollregion=(0, 0, width, y + 20))
        if game:
            self.tiles.start()


class RawVarDialog(tk.Toplevel):
    def __init__(self, master, var):
        super().__init__(master)
        self.title(f"원본 수치: {var.get('name')}")
        self.resizable(False, False)
        self.transient(master.winfo_toplevel())
        self.result = None
        f = ttk.Frame(self, padding=10)
        f.pack()
        ttk.Label(f, text=f"{var.get('name')}  ({var.get('type')})").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(f, text="수치").grid(row=1, column=0, sticky="w", pady=3)
        self.value = tk.StringVar(value=str(var.get("value", 0)))
        ttk.Entry(f, textvariable=self.value, width=10).grid(row=1, column=1, sticky="w")
        ttk.Label(f, text="강화 시 +").grid(row=2, column=0, sticky="w", pady=3)
        self.up = tk.StringVar(value=str(var.get("upgrade", 0)))
        ttk.Entry(f, textvariable=self.up, width=10).grid(row=2, column=1, sticky="w")
        b = ttk.Frame(f)
        b.grid(row=3, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(b, text="확인", command=self.ok).pack(side="left", padx=4)
        ttk.Button(b, text="취소", command=self.destroy).pack(side="left")
        self.bind("<Return>", lambda _e: self.ok())
        center_window(self)
        self.grab_set()
        self.wait_visibility()

    def ok(self):
        try:
            v, u = float(self.value.get()), float(self.up.get() or 0)
        except ValueError:
            messagebox.showerror(APP_TITLE, "숫자를 입력하세요.", parent=self)
            return
        self.result = (int(v) if v.is_integer() else v, int(u) if u.is_integer() else u)
        self.destroy()


def show_code_window(master, title, code):
    w = tk.Toplevel(master)
    w.title(title)
    w.geometry("900x700")
    t = tk.Text(w, wrap="none", font=("Consolas", 10))
    sy = ttk.Scrollbar(w, orient="vertical", command=t.yview)
    sx = ttk.Scrollbar(w, orient="horizontal", command=t.xview)
    t.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
    sy.pack(side="right", fill="y")
    sx.pack(side="bottom", fill="x")
    t.pack(fill="both", expand=True)
    t.insert("1.0", code)
    t.configure(state="disabled")
    center_window(w)


class ClonePanel(ttk.Frame):
    """복제한 항목: 원본 정보 + 원본 수치 표."""

    def __init__(self, master, tab):
        super().__init__(master, padding=(0, 4))
        self.tab = tab
        self.item = None
        self.info = ttk.Label(self, text="", foreground="#7a4b00", wraplength=760, justify="left")
        self.info.grid(row=0, column=0, columnspan=2, sticky="w")
        self.tree = ttk.Treeview(self, columns=("name", "type", "value", "up"), show="headings", height=3)
        for c, t, w in (("name", "원본 값 이름", 140), ("type", "종류", 140), ("value", "수치", 80), ("up", "강화 시 +", 80)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w)
        self.tree.grid(row=1, column=0, sticky="we", pady=4)
        self.tree.bind("<Double-1>", lambda _e: self.edit())
        bf = ttk.Frame(self)
        bf.grid(row=1, column=1, sticky="n", padx=4)
        ttk.Button(bf, text="수치 편집", command=self.edit).pack(fill="x", pady=1)
        ttk.Button(bf, text="원본 코드 보기", command=self.show_code).pack(fill="x", pady=1)
        self.pool = LabeledCombo(bf, [("mine", "내 카드/유물 풀"), ("theirs", "원본 캐릭터 풀")], width=14)
        self.pool.pack(fill="x", pady=1)
        self.pool.bind("<<ComboboxSelected>>", lambda _e: self._pool_changed())
        self.columnconfigure(0, weight=1)

    def set(self, item):
        self.item = item
        cl = item.get("clone") if item else None
        if not cl and not (item and item.get("raw_vars")):
            self.grid_remove()
            return
        self.grid()
        if cl:
            self.info.configure(text=f"복제한 항목 — 원본: {cl.get('orig_class')} ({cl.get('mod')}). 원래 동작(C# 코드)을 그대로 쓰고, "
                                     "이름·설명·비용·종류·희귀도·그림·아래 원본 수치를 바꿀 수 있습니다. 효과를 추가하면 원래 동작 뒤에 실행됩니다. "
                                     "게임에 원본 모드도 설치되어 있어야 합니다.")
            self.pool.set_value(cl.get("pool", "mine"))
        else:
            self.info.configure(text="불러온 항목 (코드 없음): 원본 텍스트를 그대로 씁니다.")
        self.tree.delete(*self.tree.get_children())
        for i, v in enumerate(item.get("raw_vars", []) or []):
            self.tree.insert("", "end", iid=str(i), values=(v.get("name"), v.get("type"), v.get("value"), v.get("upgrade")))

    def edit(self):
        s = self.tree.selection()
        if not s or not self.item:
            return
        v = self.item["raw_vars"][int(s[0])]
        d = RawVarDialog(self, v)
        self.wait_window(d)
        if d.result:
            v["value"], v["upgrade"] = d.result
            self.set(self.item)
            self.tab.changed()

    def _pool_changed(self):
        if self.item and self.item.get("clone"):
            self.item["clone"]["pool"] = self.pool.get_value()
            self.tab.changed()

    def show_code(self):
        if self.item and self.item.get("clone"):
            cl = self.item["clone"]
            show_code_window(self, f"원본 코드 - {cl.get('orig_class')}", cl.get("body", ""))


class ExternalTab(ttk.Frame):
    """📦 다른 모드: 불러오기 · 보기 · 복제 · 참조"""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.mods = []          # ExtMod
        self.cur = None
        self.selected = set()   # (kind, index)
        self._photos = []
        self._pending = None
        self._last_w = 0
        self._tile_pos = {}
        bar = ttk.Frame(self, padding=(8, 6))
        bar.pack(fill="x")
        ttk.Button(bar, text="캐릭터 카드 라이브러리…", command=app.open_card_library).pack(side="left", padx=2)
        ttk.Button(bar, text="설치된 모드에서…", command=self.pick_installed).pack(side="left", padx=2)
        ttk.Button(bar, text="모드 폴더 열기…", command=self.open_folder).pack(side="left", padx=2)
        ttk.Button(bar, text="파일 열기 (.dll/.pck/.json)…", command=self.open_file).pack(side="left", padx=2)
        self.status = ttk.Label(bar, text="", foreground="#555")
        self.status.pack(side="left", padx=12)
        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = ttk.Frame(pw, padding=6, width=300)
        pw.add(left, weight=0)
        self.listbox = tk.Listbox(left, exportselection=False, width=34, activestyle="none", height=10)
        self.listbox.pack(fill="x")
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self.on_select())
        self.detail = ttk.Label(left, text="왼쪽 위 버튼으로 다른 모드를 불러오세요.", wraplength=300, justify="left")
        self.detail.pack(fill="x", pady=8)
        self.dep_btn = ttk.Button(left, text="내 모드에서 참조하기", command=self.toggle_dep)
        self.dep_btn.pack(fill="x", pady=2)
        ttk.Label(left, text="참조하면 그 모드의 파워를 내 카드 효과(◆ 표시)에서 쓸 수 있고, 생성되는 모드가 그 모드를 필요로 하게 됩니다.",
                  foreground="#777", wraplength=300, justify="left").pack(fill="x")
        ttk.Button(left, text="목록에서 닫기", command=self.close_mod).pack(fill="x", pady=(12, 2))
        right = ttk.Frame(pw)
        pw.add(right, weight=1)
        fb = ttk.Frame(right, padding=(6, 4))
        fb.pack(fill="x")
        self.kind = tk.StringVar(value="card")
        for val, lbl in (("card", "카드"), ("relic", "유물"), ("potion", "물약"), ("power", "파워")):
            ttk.Radiobutton(fb, text=lbl, value=val, variable=self.kind, command=self.refresh).pack(side="left", padx=3)
        ttk.Separator(fb, orient="vertical").pack(side="left", fill="y", padx=8)
        for val, lbl in (("ko", "한국어"), ("en", "English"), ("zh", "简体中文")):
            ttk.Radiobutton(fb, text=lbl, value=val, variable=app.pv_lang, command=app.refresh_previews).pack(side="left", padx=3)
        ttk.Checkbutton(fb, text="강화(+)", variable=app.pv_upgraded, command=app.refresh_previews).pack(side="left", padx=6)
        self.search = tk.StringVar()
        ttk.Label(fb, text="찾기").pack(side="left", padx=(12, 2))
        se = ttk.Entry(fb, textvariable=self.search, width=16)
        se.pack(side="left")
        se.bind("<KeyRelease>", lambda _e: self._schedule())
        body = ttk.Frame(right)
        body.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(body, background="#121318", highlightthickness=0)
        vsb = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.canvas.bind("<Configure>", self._on_resize)
        self.tiles = AsyncTiles(self, self.canvas)
        act = ttk.Frame(right, padding=(6, 6))
        act.pack(fill="x")
        ttk.Button(act, text="모두 선택", command=self.select_all).pack(side="left", padx=2)
        ttk.Button(act, text="선택 해제", command=self.clear_sel).pack(side="left", padx=2)
        self.sel_lbl = ttk.Label(act, text="", foreground="#555")
        self.sel_lbl.pack(side="left", padx=10)
        ttk.Label(act, text="복제할 때 풀:").pack(side="left", padx=(20, 2))
        self.pool = LabeledCombo(act, [("mine", "내 캐릭터/공용 풀"), ("theirs", "원본 캐릭터 풀")], width=16)
        self.pool.set_value("mine")
        self.pool.pack(side="left")
        ttk.Button(act, text="선택 항목을 내 프로젝트로 복제", command=self.clone_selected).pack(side="right", padx=2)
        ttk.Label(right, text="클릭: 선택/해제 · 더블클릭: 원본 코드 보기", foreground="#777").pack(anchor="w", padx=8)

    # ---- 불러오기 ----
    def pick_installed(self):
        mods = MI.list_installed(self.app.settings.get("sts2_path", ""))
        if not mods:
            messagebox.showinfo(APP_TITLE, "게임의 mods 폴더에서 모드를 찾지 못했습니다. '모드 / 빌드' 탭의 슬더스2 설치 폴더를 확인하세요.")
            return
        w = tk.Toplevel(self)
        w.title("설치된 모드")
        w.transient(self.winfo_toplevel())
        lb = tk.Listbox(w, width=60, height=min(16, len(mods)), selectmode="extended")
        lb.pack(padx=10, pady=10)
        for name, path, on in mods:
            lb.insert("end", f"{'●' if on else '○'} {name}" + ("" if on else "  (꺼짐: mods.disabled)"))

        def go():
            for i in lb.curselection():
                self.load(mods[i][1])
            w.destroy()
        ttk.Button(w, text="불러오기", command=go).pack(pady=(0, 10))
        lb.bind("<Double-1>", lambda _e: go())
        center_window(w)

    def open_folder(self):
        p = filedialog.askdirectory(title="모드 폴더 (설치된 모드 또는 C# 소스 프로젝트)")
        if p:
            self.load(p)

    def open_file(self):
        p = filedialog.askopenfilename(filetypes=[("모드 파일", "*.dll *.pck *.json"), ("모든 파일", "*.*")])
        if p:
            self.load(p)

    def load(self, path):
        self.status.configure(text=f"불러오는 중: {os.path.basename(path)} …")
        self.app.log(f"다른 모드 불러오는 중: {path}")
        sts2 = self.app.settings.get("sts2_path", "")

        def work():
            try:
                em = MI.load_mod(path, sts2, log=self.app.log)
                self.after(0, lambda: self._loaded(em))
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                self.after(0, lambda: (self.status.configure(text=""), self.app.log(f"[오류] {msg}"),
                                       messagebox.showerror(APP_TITLE, f"불러오기 실패:\n{msg}")))
        threading.Thread(target=work, daemon=True).start()

    def _loaded(self, em):
        self.mods = [m for m in self.mods if m.root != em.root]
        self.mods.append(em)
        self.refresh_list(len(self.mods) - 1)
        self.status.configure(text="")
        self.app.log(f"불러옴: {em.name} ({em.id}) - {em.summary()}")
        for n in em.notes:
            self.app.log("  " + n)

    def refresh_list(self, select=None):
        deps = {d["id"] for d in self.app.project.get("dependencies", [])}
        self.listbox.delete(0, "end")
        for m in self.mods:
            self.listbox.insert("end", f"{'✔ ' if m.id in deps else ''}{m.name}  ({m.id})")
        if self.mods:
            i = select if select is not None else (self.mods.index(self.cur) if self.cur in self.mods else 0)
            self.listbox.selection_set(i)
            self.on_select()
        else:
            self.cur = None
            self.detail.configure(text="왼쪽 위 버튼으로 다른 모드를 불러오세요.")
            self.refresh()

    def on_select(self):
        s = self.listbox.curselection()
        if not s:
            return
        self.cur = self.mods[s[0]]
        self.selected = set()
        m = self.cur
        kinds = {"installed": "설치된 모드", "source": "C# 소스", "pck": ".pck 파일", "dll": ".dll 파일"}
        deps = {d["id"] for d in self.app.project.get("dependencies", [])}
        txt = [f"{m.name}", f"ID {m.id}  ·  {m.version}  ·  {m.author}", f"형태: {kinds.get(m.kind, m.kind)}", m.summary()]
        if m.characters:
            txt.append("캐릭터: " + ", ".join(c["class"] for c in m.characters))
        if not m.dll:
            txt.append("dll 없음 → 복제·참조는 할 수 없고 보기만 됩니다.")
        txt += m.notes
        self.detail.configure(text="\n".join(txt))
        self.dep_btn.configure(text="참조 해제" if m.id in deps else "내 모드에서 참조하기",
                               state="normal" if m.dll else "disabled")
        self.refresh()

    def close_mod(self):
        if self.cur in self.mods:
            self.mods.remove(self.cur)
            self.cur = None
            self.refresh_list()

    # ---- 참조 ----
    def toggle_dep(self):
        m = self.cur
        if not m or not m.dll:
            return
        deps = self.app.project.setdefault("dependencies", [])
        if any(d["id"] == m.id for d in deps):
            used = [it["id"] for k in ("cards", "relics", "potions", "powers") for it in self.app.project[k]
                    if (it.get("clone") or {}).get("mod") == m.id]
            if used and not messagebox.askyesno(APP_TITLE, f"이 모드에서 복제한 항목 {len(used)}개가 있습니다. 그래도 참조를 해제할까요?"):
                return
            self.app.project["dependencies"] = [d for d in deps if d["id"] != m.id]
            self.app.log(f"참조 해제: {m.id}")
        else:
            deps.append(MI.dependency_entry(m))
            self.app.log(f"참조 추가: {m.id} (파워 {len(MI.dependency_entry(m)['powers'])}개를 ◆ 표시로 쓸 수 있습니다)")
        self.app.mark_dirty()
        self.refresh_list()

    def _ensure_dep(self, m):
        deps = self.app.project.setdefault("dependencies", [])
        for i, d in enumerate(deps):
            if d["id"] == m.id:
                deps[i] = MI.dependency_entry(m)
                return
        deps.append(MI.dependency_entry(m))

    # ---- 복제 ----
    def clone_selected(self):
        m = self.cur
        if not m or not self.selected:
            messagebox.showinfo(APP_TITLE, "복제할 항목을 클릭해서 고르세요.")
            return
        has_code = any(m.items[k][i].get("_cls") is not None for k, i in self.selected)
        if has_code and not m.dll:
            messagebox.showerror(APP_TITLE, "이 모드의 dll 을 찾지 못해 원래 동작을 유지한 복제를 할 수 없습니다.")
            return
        P = self.app.project
        used = self.app.all_ids()
        added = {"card": 0, "relic": 0, "potion": 0, "power": 0}
        for kind, i in sorted(self.selected):
            src = m.items[kind][i]
            new = MI.clone_item(m, src, P, self.pool.get_value())
            base_id = new["id"]
            nid, n = base_id, 2
            while nid in used:
                nid = f"{base_id}_{n}"
                n += 1
            new["id"] = nid
            used.add(nid)
            if self.pool.get_value() == "theirs":
                pv = MI.preview_item(m, src)
                for k in ("_hsv", "_energy_big", "_energy_small", "_colorless"):
                    if k in pv:
                        new[k] = pv[k]
            P[{"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}[kind]].append(new)
            added[kind] += 1
        if has_code:
            self._ensure_dep(m)
        self.app.mark_dirty()
        for t in (self.app.card_tab, self.app.relic_tab, self.app.potion_tab, self.app.power_tab):
            t.refresh_list(len(t.items) - 1 if t.items else None)
        self.refresh_list()
        msg = f"복제했습니다: 카드 {added['card']} · 유물 {added['relic']} · 물약 {added['potion']} · 파워 {added['power']}"
        if has_code:
            msg += f"\n\n원본 모드 '{m.id}'를 참조(필수 모드)로 추가했습니다. 게임에 원본 모드도 설치되어 있어야 합니다."
        messagebox.showinfo(APP_TITLE, msg)

    # ---- 그리기 ----
    def _wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120), "units")

    def _on_resize(self, e):
        if abs(e.width - self._last_w) < 20:
            return
        self._last_w = e.width
        self._schedule()

    def _schedule(self):
        if self._pending:
            self.after_cancel(self._pending)
        self._pending = self.after(150, self.refresh)

    def visible_items(self):
        if not self.cur:
            return []
        q = self.search.get().strip().lower()
        out = []
        for i, it in enumerate(self.cur.items[self.kind.get()]):
            if q and q not in (it.get("name_ko", "") + it.get("name_en", "") + it.get("class", "")).lower():
                continue
            out.append((i, it))
        return out

    def refresh(self):
        self._pending = None
        c = self.canvas
        c.delete("all")
        self.tiles.begin()
        self._tile_pos = {}
        self._update_sel_label()
        if not self.cur or self.app.nb.select() != str(self):
            return
        kind = self.kind.get()
        lang = self.app.pv_lang.get()
        up = bool(self.app.pv_upgraded.get())
        width = max(300, c.winfo_width())
        sc = 0.6 * self.app.ui
        tw, th = (344 * sc, 460 * sc) if kind == "card" else (300 * sc, 330 * sc)
        gap, pad = 12, 14
        cols = max(1, int((width - pad * 2 + gap) // (tw + gap)))
        items = self.visible_items()
        if not items:
            c.create_text(pad, pad, text="(항목 없음)", anchor="nw", fill="#888")
        game = self.app.pv_mode.get() == "game" and self.app.game_assets() is not None
        em = self.cur
        for n, (i, it) in enumerate(items):
            x0 = pad + (n % cols) * (tw + gap)
            y0 = pad + (n // cols) * (th + gap + 18)
            tag = f"x_{i}"
            self._tile_pos[(kind, i)] = (x0, y0, tw, th)
            if game:
                key = (em.root, kind, it.get("class"))
                self.tiles.add(f"{kind}_{i}", x0, y0, tw, th, (tag,),
                               lambda it_=it, key_=key, kind_=kind: self.app.thumb(
                                   key_, lambda: MI.preview_item(em, it_), kind_, lang, up, 3, tw, th))
            else:
                PV.render_item(c, self.app.project, kind, MI.preview_item(em, it), x0, y0, sc, lang, up, 3, tags=(tag,))
            c.create_text(x0 + tw / 2, y0 + th + 2, text=it.get("class", ""), anchor="n", fill="#777",
                          font=("Consolas", 8), tags=(tag,))
            if (kind, i) in self.selected:
                self._draw_sel(kind, i)
            c.tag_bind(tag, "<Button-1>", lambda _e, k=kind, j=i: self.toggle(k, j))
            c.tag_bind(tag, "<Double-1>", lambda _e, it_=it: self.show_code(it_))
            c.tag_bind(tag, "<Enter>", lambda _e: c.configure(cursor="hand2"))
            c.tag_bind(tag, "<Leave>", lambda _e: c.configure(cursor=""))
        rows = (len(items) + cols - 1) // cols
        c.configure(scrollregion=(0, 0, width, pad * 2 + rows * (th + gap + 18)))
        if game:
            self.tiles.start()

    def _draw_sel(self, kind, i):
        pos = self._tile_pos.get((kind, i))
        if pos:
            x0, y0, tw, th = pos
            self.canvas.create_rectangle(x0 - 4, y0 - 4, x0 + tw + 4, y0 + th + 16, outline="#4da3ff", width=4,
                                         tags=(f"x_{i}", f"sel_{kind}_{i}"))

    def _update_sel_label(self):
        self.sel_lbl.configure(text=f"{len(self.selected)}개 선택" if self.selected else "")

    def toggle(self, kind, i):
        """선택 표시만 바꾼다 (전체를 다시 그리지 않음)."""
        key = (kind, i)
        if key in self.selected:
            self.selected.discard(key)
            self.canvas.delete(f"sel_{kind}_{i}")
        else:
            self.selected.add(key)
            self._draw_sel(kind, i)
        self._update_sel_label()

    def select_all(self):
        k = self.kind.get()
        for i, _ in self.visible_items():
            if (k, i) not in self.selected:
                self.selected.add((k, i))
                self._draw_sel(k, i)
        self._update_sel_label()

    def clear_sel(self):
        for k, i in list(self.selected):
            self.canvas.delete(f"sel_{k}_{i}")
        self.selected = set()
        self._update_sel_label()

    def show_code(self, it):
        c = it.get("_cls")
        if c is None:
            messagebox.showinfo(APP_TITLE, "이 항목은 코드가 없습니다 (텍스트와 그림만).")
            return
        vars_ = "\n".join(f"  {v['name']} = {v['value']} (강화 +{v['upgrade']})" for v in it.get("raw_vars", []))
        head = f"// {c.full} : {c.base}\n// 파일: {c.path}\n// 원본 수치:\n" + "\n".join("//" + ln for ln in vars_.split("\n")) + "\n\n"
        show_code_window(self, f"원본 코드 - {c.full}", head + MI.fix_decompiled(c.body))


# ---------------------------------------------------------------------------
# 카드 / 유물 / 물약 공통 편집 탭
# ---------------------------------------------------------------------------
class ItemTab(ttk.Frame):
    kind = "card"          # card / relic / potion
    key = "cards"
    noun = "카드"

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.cur = None
        self._loading = False
        self.vars = {}
        self.var_labels = {}
        self.query = ""
        self._drag = None

        pw = ttk.PanedWindow(self, orient="horizontal")
        pw.pack(fill="both", expand=True)
        left = ttk.Frame(pw, padding=(8, 8, 4, 8), width=300)
        pw.add(left, weight=0)
        head = ttk.Frame(left)
        head.pack(fill="x", pady=(0, 6))
        ttk.Label(head, text=f"{self.noun} 목록", style="Head.TLabel").pack(side="left")
        self.count_lbl = ttk.Label(head, text="", style="Count.TLabel")
        self.count_lbl.pack(side="left", padx=6)
        self.search = UX.SearchEntry(left, f"{self.noun} 찾기 (이름·ID·초성)  Ctrl+F", self.set_query,
                                     on_down=self._search_down, on_enter=self._search_down)
        self.search.pack(fill="x", pady=(0, 6))
        lf = ttk.Frame(left)
        lf.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(lf, columns=("id",), show="tree", selectmode="extended")
        self.tree.column("#0", width=190, stretch=True)
        self.tree.column("id", width=110, stretch=False, anchor="w")
        self.tree.tag_configure("muted", foreground=UX.C["muted"])
        tsb = ttk.Scrollbar(lf, command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tsb.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.on_select())
        self.tree.bind("<ButtonPress-1>", self._drag_start, add="+")
        self.tree.bind("<B1-Motion>", self._drag_move, add="+")
        self.tree.bind("<ButtonRelease-1>", self._drag_end, add="+")
        self.tree.bind("<Button-3>", self._context)
        self.tree.bind("<Delete>", lambda _e: self.delete())
        self.tree.bind("<Control-d>", lambda _e: (self.duplicate(), "break")[1])
        self.tree.bind("<Control-a>", lambda _e: (self.tree.selection_set(self.tree.get_children()), "break")[1])
        self.multi_bar = ttk.Frame(left)
        self.multi_lbl = ttk.Label(self.multi_bar, text="", style="Muted.TLabel")
        self.multi_lbl.pack(side="left")
        ttk.Button(self.multi_bar, text="한꺼번에 바꾸기…", style="Small.TButton",
                   command=self.bulk_edit).pack(side="right")
        lb = ttk.Frame(left)
        lb.pack(fill="x", pady=(6, 0))
        UX.tip(ttk.Button(lb, text="＋ 새로 만들기", style="Accent.TButton", command=self.add), f"새 {self.noun}를 목록 끝에 만듭니다.") \
            .pack(side="left", expand=True, fill="x", padx=(0, 3))
        UX.tip(ttk.Button(lb, text="복제", command=self.duplicate), "선택한 항목을 복사합니다 (Ctrl+D).") \
            .pack(side="left", expand=True, fill="x", padx=3)
        UX.tip(ttk.Button(lb, text="삭제", command=self.delete), "선택한 항목을 지웁니다 (Delete). Ctrl+Z 로 되돌릴 수 있습니다.") \
            .pack(side="left", expand=True, fill="x", padx=(3, 0))
        ttk.Label(left, text="끌어서 순서 변경 · Ctrl/Shift+클릭 여러 개\n오른쪽 클릭 = 메뉴 · Ctrl+Z 되돌리기",
                  style="Muted.TLabel", justify="left").pack(anchor="w", pady=(6, 0))

        right = ScrollFrame(pw)
        pw.add(right, weight=1)
        self.form = ttk.Frame(right.inner, padding=8)
        self.form.pack(fill="both", expand=True)
        for c in (1, 3):
            self.form.columnconfigure(c, weight=1)
        self.build_form(self.form)
        self.pv = PreviewPanel(pw, app, self.kind)
        pw.add(self.pv, weight=0)

    # ---- 폼 구성 도우미 ----
    def _field_label(self, parent, label, key, **grid):
        """칸 이름. 설명이 있으면 ⓘ 를 붙이고 마우스를 올리면 말풍선을 띄운다."""
        self.var_labels[key] = label.replace("\n", " ")
        help_text = UX.field_help(self.kind, key)
        lab = ttk.Label(parent, text=label + ("  ⓘ" if help_text else ""))
        lab.grid(**grid)
        if help_text:
            UX.tip(lab, help_text)
            lab.configure(cursor="question_arrow")
        return lab

    def entry(self, parent, row, col, label, key, width=24, hint="", span=1):
        self._field_label(parent, label, key, row=row, column=col, sticky="w", padx=4, pady=2)
        v = tk.StringVar()
        ttk.Entry(parent, textvariable=v, width=width).grid(row=row, column=col + 1, columnspan=span,
                                                            sticky="we", padx=4, pady=2)
        v.trace_add("write", lambda *_: self.changed())
        self.vars[key] = ("str", v)
        if hint:
            ttk.Label(parent, text=hint, foreground="#777").grid(row=row + 1, column=col + 1, sticky="w", padx=4)
        return v

    def spin(self, parent, row, col, label, key, lo=0, hi=9):
        self._field_label(parent, label, key, row=row, column=col, sticky="w", padx=4, pady=2)
        v = tk.StringVar()
        ttk.Spinbox(parent, from_=lo, to=hi, textvariable=v, width=6).grid(row=row, column=col + 1, sticky="w", padx=4, pady=2)
        v.trace_add("write", lambda *_: self.changed())
        self.vars[key] = ("int", v)
        return v

    def combo(self, parent, row, col, label, key, options, width=16):
        self._field_label(parent, label, key, row=row, column=col, sticky="w", padx=4, pady=2)
        c = LabeledCombo(parent, options, width=width)
        c.grid(row=row, column=col + 1, sticky="w", padx=4, pady=2)
        c.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.vars[key] = ("combo", c)
        return c

    def textbox(self, parent, row, label, key, height=3, font=("Malgun Gothic", 10), wrap="word"):
        self._field_label(parent, label, key, row=row, column=0, sticky="nw", padx=4, pady=2)
        t = tk.Text(parent, height=height, width=60, wrap=wrap, font=font, undo=True)
        t.grid(row=row, column=1, columnspan=3, sticky="we", padx=4, pady=2)
        t.bind("<KeyRelease>", lambda _e: self.changed())
        self.vars[key] = ("text", t)
        return t

    def common_bottom(self, f, row):
        self.clone_panel = ClonePanel(f, self)
        self.clone_panel.grid(row=row, column=0, columnspan=4, sticky="we", padx=4)
        self.clone_panel.grid_remove()
        row += 1
        ttk.Label(f, text="효과").grid(row=row, column=0, sticky="nw", padx=4, pady=(8, 2))
        self.effects = EffectList(f, self.kind, self.changed, self.app,
                                  lambda: self.items[self.cur] if self.cur is not None else {})
        self.effects.grid(row=row, column=1, columnspan=3, sticky="we", padx=4, pady=(8, 2))
        row += 1
        self.extra_rows(f, row)
        row += 3
        v = tk.StringVar()
        self.vars["image"] = ("str", v)
        file_row(f, row, "그림 (PNG)", v, self.changed, hint=self.image_hint)
        row += 1
        ttk.Separator(f).grid(row=row, column=0, columnspan=4, sticky="we", pady=8)
        row += 1
        ttk.Label(f, text="설명은 효과에서 자동으로 만들어집니다. 직접 쓰고 싶을 때만 아래 칸을 채우세요.",
                  foreground="#777").grid(row=row, column=0, columnspan=4, sticky="w", padx=4)
        row += 1
        self.textbox(f, row, "설명 직접 입력\n(한국어)", "desc_ko")
        row += 1
        self.textbox(f, row, "설명 직접 입력\n(영어)", "desc_en")
        row += 1
        self.textbox(f, row, "설명 직접 입력\n(중국어 간체)", "desc_zh")
        row += 1
        row += 1
        ttk.Separator(f).grid(row=row, column=0, columnspan=4, sticky="we", pady=8)
        row += 1
        ttk.Label(f, text="고급: 클래스 안에 그대로 추가할 C# 코드 (다른 훅 override, 필드, 메서드 등). 비워 두면 무시됩니다.",
                  foreground="#777").grid(row=row, column=0, columnspan=4, sticky="w", padx=4)
        row += 1
        self.textbox(f, row, "추가 C# 코드", "extra_code", height=7, font=("Consolas", 10), wrap="none")

    image_hint = ""

    def extra_rows(self, f, row):
        pass

    # ---- 데이터 ----
    @property
    def items(self):
        return self.app.project[self.key]

    def label(self, it):
        return f"{it.get('name_ko') or it.get('name_en') or '?'}  ({it['id']})"

    def row_text(self, it):
        return "  " + (it.get("name_ko") or it.get("name_en") or "?")

    def search_fields(self, it):
        return (it.get("name_ko"), it.get("name_en"), it.get("name_zh"), it.get("id"),
                M.label_of(M.CARD_TYPES, it.get("type")) if self.kind == "card" else "",
                it.get("desc_ko"))

    def _visible(self):
        return [i for i, it in enumerate(self.items) if UX.matches(self.query, *self.search_fields(it))]

    def refresh_list(self, select=None):
        """목록을 다시 그린다. select = 고를 항목 번호 (하나 또는 여러 개)."""
        self.tree.delete(*self.tree.get_children())
        vis = self._visible()
        for i in vis:
            it = self.items[i]
            self.tree.insert("", "end", iid=str(i), text=self.row_text(it), values=(it["id"],),
                             image=UX.item_icon(self.kind, it, self.app.ui), tags=("row",))
        total = len(self.items)
        self.count_lbl.configure(text=f"{len(vis)} / {total}" if self.query else f"{total}개")
        if vis:
            want = select if isinstance(select, (list, tuple)) else [select if select is not None else (self.cur or 0)]
            want = [w for w in want if w is not None]
            keep = [str(w) for w in want if w in vis]
            if not keep:   # 고른 항목이 검색에 걸러졌으면 가장 가까운 것
                w = want[0] if want else 0
                keep = [str(min(vis, key=lambda v: abs(v - w)))]
            self.tree.selection_set(keep)
            self.tree.focus(keep[0])
            self.tree.see(keep[0])
            self.load(int(keep[0]))
        else:
            self.cur = None
            self.set_form_state(False)
            self.update_preview()
        self._update_multi()

    def set_query(self, q):
        self.query = q
        self.refresh_list(self.cur)

    def _search_down(self):
        kids = self.tree.get_children()
        if kids:
            self.tree.focus_set()
            if not self.tree.selection():
                self.tree.selection_set(kids[0])
        return "break"

    def select_index(self, idx):
        """다른 곳에서 이 항목으로 올 때. 검색에 걸러져 있으면 검색을 지운다."""
        if str(idx) not in self.tree.get_children():
            self.search.set("")
            self.query = ""
        self.refresh_list(idx)

    def selected(self):
        return sorted(int(s) for s in self.tree.selection())

    def _update_multi(self):
        n = len(self.tree.selection())
        if n > 1:
            self.multi_lbl.configure(text=f"{n}개 선택됨")
            self.multi_bar.pack(fill="x", pady=(6, 0), after=self.tree.master)
        else:
            self.multi_bar.pack_forget()

    # ---- 끌어서 순서 바꾸기 ----
    def _drag_start(self, e):
        row = self.tree.identify_row(e.y)
        self._drag = {"row": row, "y": e.y, "moved": False} if row and not (e.state & 0x0005) else None

    def _drag_move(self, e):
        d = self._drag
        if not d or self.query:
            return
        if not d["moved"] and abs(e.y - d["y"]) < 6:
            return
        target = self.tree.identify_row(e.y)
        if not target or target == d["row"]:
            return
        d["moved"] = True
        self.tree.configure(cursor="sb_v_double_arrow")
        self.tree.move(d["row"], "", self.tree.index(target))
        self.tree.selection_set(d["row"])

    def _drag_end(self, _e):
        d, self._drag = self._drag, None
        self.tree.configure(cursor="")
        if not d or not d["moved"]:
            return
        order = [int(r) for r in self.tree.get_children()]
        if order == list(range(len(self.items))):
            return
        moved = int(d["row"])
        items = list(self.items)
        self.items[:] = [items[i] for i in order]
        self.app.mark_dirty()
        self.refresh_list(order.index(moved))
        self.app.on_items_changed()

    def move_by(self, delta):
        sel = self.selected()
        if len(sel) != 1:
            return
        i, j = sel[0], sel[0] + delta
        if not 0 <= j < len(self.items):
            return
        self.items[i], self.items[j] = self.items[j], self.items[i]
        self.app.mark_dirty()
        self.refresh_list(j)
        self.app.on_items_changed()

    def _context(self, e):
        row = self.tree.identify_row(e.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        sel = self.selected()
        m = tk.Menu(self, tearoff=0)
        m.add_command(label=f"＋ 새 {self.noun}", command=self.add)
        if sel:
            m.add_command(label="복제" + (f" ({len(sel)}개)" if len(sel) > 1 else ""), command=self.duplicate,
                          accelerator="Ctrl+D")
            m.add_command(label="삭제" + (f" ({len(sel)}개)" if len(sel) > 1 else ""), command=self.delete,
                          accelerator="Delete")
            m.add_separator()
            m.add_command(label="한꺼번에 바꾸기…", command=self.bulk_edit)
            if len(sel) == 1 and not self.query:
                m.add_separator()
                m.add_command(label="위로", command=lambda: self.move_by(-1))
                m.add_command(label="아래로", command=lambda: self.move_by(1))
            m.add_separator()
            m.add_command(label="ID 복사", command=lambda: (self.clipboard_clear(),
                                                             self.clipboard_append(", ".join(self.items[i]["id"] for i in sel))))
        try:
            m.tk_popup(e.x_root, e.y_root)
        finally:
            m.grab_release()

    # ---- 여러 개 한꺼번에 ----
    def bulk_edit(self):
        sel = self.selected()
        if not sel:
            return
        UX.BulkEditDialog(self, sel)

    def apply_bulk(self, indices, changes):
        for i in indices:
            self.items[i].update(changes)
        self.app.mark_dirty()
        self.refresh_list(list(indices))
        self.app.on_items_changed()
        self.app.log(f"{self.noun} {len(indices)}개를 바꿨습니다: " +
                     ", ".join(self.var_labels.get(k, k) for k in changes))

    def set_form_state(self, on):
        state = "normal" if on else "disabled"
        for w in self.form.winfo_children():
            try:
                if isinstance(w, ttk.Combobox):
                    w.configure(state="readonly" if on else "disabled")
                elif not isinstance(w, (ttk.Label, ttk.Separator, tk.Text)):
                    w.configure(state=state)
            except tk.TclError:
                pass

    def on_select(self):
        self._update_multi()
        if self._drag and self._drag.get("moved"):
            return
        foc = self.tree.focus()
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(foc) if foc in sel else int(sel[0])
        if idx != self.cur:
            self.load(idx)

    def load(self, idx):
        self.cur = idx
        it = self.items[idx]
        self._loading = True
        try:
            self.set_form_state(True)
            for key, (typ, w) in self.vars.items():
                val = it.get(key, "")
                if typ in ("str", "int"):
                    w.set(str(val))
                elif typ == "combo":
                    w.set_value(val)
                elif typ == "text":
                    w.delete("1.0", "end")
                    w.insert("1.0", val or "")
                elif typ == "bool":
                    w.set(bool(val))
            self.load_extra(it)
            self.effects.set(it["effects"])
            self.clone_panel.set(it)
        finally:
            self._loading = False
        self.update_preview()

    def load_extra(self, it):
        pass

    def dump_extra(self, it):
        pass

    def changed(self):
        if self._loading or self.cur is None:
            return
        it = self.items[self.cur]
        old_id = it["id"]
        for key, (typ, w) in self.vars.items():
            if typ == "str":
                it[key] = w.get().strip() if key != "image" else w.get().strip().strip('"')
            elif typ == "int":
                try:
                    it[key] = int(w.get())
                except ValueError:
                    pass
            elif typ == "combo":
                it[key] = w.get_value()
            elif typ == "text":
                it[key] = w.get("1.0", "end").strip()
            elif typ == "bool":
                it[key] = bool(w.get())
        self.dump_extra(it)
        if old_id != it["id"]:
            self.app.rename_ref(self.kind, old_id, it["id"])
        if self.tree.exists(str(self.cur)):
            self.tree.item(str(self.cur), text=self.row_text(it), values=(it["id"],),
                           image=UX.item_icon(self.kind, it, self.app.ui))
        self.app.mark_dirty()
        self.update_preview()

    def update_preview(self):
        self.pv.show(self.items[self.cur] if self.cur is not None and self.cur < len(self.items) else None)

    def new_item(self, iid):
        raise NotImplementedError

    def unique_id(self, base):
        used = self.app.all_ids()
        if base not in used:
            return base
        i = 2
        letters = "abcdefghijklmnopqrstuvwxyz"
        while True:
            # ID에는 숫자를 쓸 수 없으므로 접미사를 영문으로 만든다 (b, c, ...)
            suffix = ""
            n = i
            while n:
                n, r = divmod(n - 1, 26)
                suffix = letters[r] + suffix
            cand = f"{base}_{suffix}"
            if cand not in used:
                return cand
            i += 1

    def add(self):
        it = self.new_item(self.unique_id("new_" + self.kind))
        self.items.append(it)
        self.app.mark_dirty()
        if self.query:   # 새 항목이 검색에 안 걸릴 수 있으니 검색을 지운다
            self.search.set("")
            self.query = ""
        self.refresh_list(len(self.items) - 1)
        self.app.on_items_changed()

    def duplicate(self):
        sel = self.selected() or ([self.cur] if self.cur is not None else [])
        if not sel:
            return
        new_rows = []
        for n, i in enumerate(sel):
            pos = i + n + 1
            it = copy.deepcopy(self.items[pos - 1])
            it["id"] = self.unique_id(it["id"])
            it["name_ko"] = (it.get("name_ko") or "") + " (복사)"
            self.items.insert(pos, it)
            new_rows.append(pos)
        self.app.mark_dirty()
        if self.query:
            self.search.set("")
            self.query = ""
        self.refresh_list(new_rows)
        self.app.on_items_changed()

    def delete(self):
        sel = self.selected() or ([self.cur] if self.cur is not None else [])
        if not sel:
            return
        if len(sel) == 1:
            msg = f"{self.noun} '{self.items[sel[0]].get('name_ko')}'을(를) 삭제할까요?"
        else:
            msg = f"{self.noun} {len(sel)}개를 삭제할까요?"
        if not messagebox.askyesno(APP_TITLE, msg + "\n(Ctrl+Z 로 되돌릴 수 있습니다)"):
            return
        for i in reversed(sel):
            self.app.rename_ref(self.kind, self.items[i]["id"], None)
            del self.items[i]
        self.app.mark_dirty()
        self.refresh_list(min(sel[0], len(self.items) - 1))
        self.app.on_items_changed()


class CardTab(ItemTab):
    kind, key, noun = "card", "cards", "카드"
    image_hint = "250×190 권장"

    def build_form(self, f):
        self.entry(f, 0, 0, "ID (영문 소문자_)", "id", hint="예: fire_ball")
        self.entry(f, 2, 0, "이름 (한국어)", "name_ko")
        self.entry(f, 2, 2, "이름 (영어)", "name_en")
        self.entry(f, 3, 0, "이름 (중국어 간체)", "name_zh")
        self.combo(f, 4, 0, "종류", "type", M.CARD_TYPES)
        self.combo(f, 4, 2, "희귀도", "rarity", M.CARD_RARITIES)
        self.spin(f, 5, 0, "비용", "cost")
        self.spin(f, 5, 2, "강화 후 비용", "upgrade_cost")
        self.combo(f, 6, 0, "대상", "target", M.CARD_TARGETS)
        self.combo(f, 6, 2, "태그", "tag", M.CARD_TAGS)
        ttk.Label(f, text="키워드").grid(row=7, column=0, sticky="w", padx=4, pady=2)
        kf = ttk.Frame(f)
        kf.grid(row=7, column=1, columnspan=3, sticky="w", padx=4)
        self.kw_vars = {}
        for k, l in M.CARD_KEYWORDS:
            v = tk.BooleanVar()
            ttk.Checkbutton(kf, text=l, variable=v, command=self.changed).pack(side="left", padx=(0, 10))
            self.kw_vars[k] = v
        ttk.Separator(kf, orient="vertical").pack(side="left", fill="y", padx=(4, 12))
        for key, text, tip in (("x_cost", "X 비용", "남은 에너지를 전부 쓰는 카드 (소용돌이처럼). 비용 칸은 무시됩니다.\n"
                                                     "효과 편집에서 'X 사용'(X번 반복 / 수치 × X)을 고르거나, 블록 값 'X (쓴 에너지)'를 쓰세요."),
                               ("x_plus_up", "강화하면 X+1", "강화한 카드는 X 가 1 커집니다 (X+1 번 / 수치 × (X+1)).")):
            v = tk.BooleanVar()
            UX.tip(ttk.Checkbutton(kf, text=text, variable=v, command=self.changed), tip).pack(side="left", padx=(0, 10))
            self.vars[key] = ("bool", v)
            self.var_labels[key] = text
        self.combo(f, 8, 0, "강화 시 키워드 추가", "upgrade_add_keyword", [("", "없음")] + M.CARD_KEYWORDS)
        self._field_label(f, "테두리 디자인", "frame_style", row=8, column=2, sticky="w", padx=4, pady=2)
        ff = ttk.Frame(f)
        ff.grid(row=8, column=3, sticky="w", padx=4, pady=2)
        self.frame_combo = LabeledCombo(ff, CF.options({"card_frames": []}), width=18)
        self.frame_combo.pack(side="left")
        self.frame_combo.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        UX.tip(ttk.Button(ff, text="편집…", style="Small.TButton", command=self.edit_frames),
               "카드 틀·그림 테두리·제목 띠의 색이나 그림을 바꾸는 디자인을 만듭니다.").pack(side="left", padx=4)
        self.vars["frame_style"] = ("combo", self.frame_combo)
        self.combo(f, 9, 0, "강화 시 키워드 제거", "upgrade_remove_keyword", [("", "없음")] + M.CARD_KEYWORDS)
        self.common_bottom(f, 10)

    def edit_frames(self):
        import cardframeui
        it = self.items[self.cur] if self.cur is not None else {}
        sel = it.get("frame_style") or (self.app.project["character"].get("frame_style") or None)
        cardframeui.FrameStyleDialog(self.app, sel if sel not in ("", CF.GAME) else None, on_close=self.app.frames_changed)

    def extra_rows(self, f, row):
        g = ttk.LabelFrame(f, text="🎲 기믹 (태그 · 자원 비용 · 사용 조건)", padding=6)
        g.grid(row=row, column=0, columnspan=4, sticky="we", padx=4, pady=(8, 2))
        g.columnconfigure(1, weight=1)
        ttk.Label(g, text="태그").grid(row=0, column=0, sticky="w", padx=4, pady=2)
        self.tag_frame = ttk.Frame(g)
        self.tag_frame.grid(row=0, column=1, columnspan=3, sticky="w", padx=4)
        self.tag_vars = {}
        ttk.Label(g, text="자원 비용").grid(row=1, column=0, sticky="w", padx=4, pady=2)
        rf = ttk.Frame(g)
        rf.grid(row=1, column=1, columnspan=3, sticky="w", padx=4)
        self.res_power = LabeledCombo(rf, [("", "없음")], width=30)
        self.res_power.pack(side="left")
        self.res_power.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        self.vars["res_power"] = ("combo", self.res_power)
        self.var_labels["res_power"] = "자원 비용 (파워)"
        v = tk.StringVar()
        ttk.Spinbox(rf, from_=0, to=99, textvariable=v, width=5).pack(side="left", padx=6)
        v.trace_add("write", lambda *_: self.changed())
        self.vars["res_cost"] = ("int", v)
        self.var_labels["res_cost"] = "자원 비용 수치"
        ttk.Label(rf, text="소모 (부족하면 못 냄)", foreground="#777").pack(side="left")
        self.cond_btns = {}
        for r, (key, label, hint) in enumerate((("play_cond", "사용 조건", ""),
                                                ("glow_cond", "금색 테두리", "")), start=2):
            ttk.Label(g, text=label).grid(row=r, column=0, sticky="w", padx=4, pady=2)
            cf = ttk.Frame(g)
            cf.grid(row=r, column=1, columnspan=3, sticky="w", padx=4)
            b = ttk.Button(cf, text="", width=40, command=lambda k=key: self.edit_cond(k))
            b.pack(side="left")
            ttk.Button(cf, text="없애기", width=7, command=lambda k=key: self.clear_cond(k)).pack(side="left", padx=4)
            ttk.Label(cf, text=hint, foreground="#777").pack(side="left")
            self.cond_btns[key] = b
        ttk.Label(g, text="별 비용").grid(row=5, column=0, sticky="w", padx=4, pady=2)
        sf_ = ttk.Frame(g)
        sf_.grid(row=5, column=1, columnspan=3, sticky="w", padx=4)
        for key, w_ in (("star_cost", 4), ("star_cost_up", 4)):
            if key == "star_cost_up":
                ttk.Label(sf_, text="강화 시 ±").pack(side="left", padx=(8, 2))
            v = tk.StringVar()
            ttk.Spinbox(sf_, from_=-9 if key == "star_cost_up" else 0, to=20, textvariable=v, width=w_).pack(side="left")
            v.trace_add("write", lambda *_: self.changed())
            self.vars[key] = ("int", v)
        self.var_labels.update(star_cost="별 비용", star_cost_up="강화 시 별 비용 ±")
        xv = tk.BooleanVar()
        ttk.Checkbutton(sf_, text="별 X (가진 별을 전부 씀 → 블록 값 'X')", variable=xv, command=self.changed).pack(side="left", padx=8)
        self.vars["star_x"] = ("bool", xv)
        self.var_labels["star_x"] = "별 X (가진 별 전부)"
        ttk.Label(g, text="사용 조건: 이 조건일 때만 낼 수 있음. 금색 테두리: 조건이 맞으면 카드가 빛남 (연계 표시). "
                          "별 비용: 리젠트처럼 별을 소모. 태그는 '🎲 기믹' 탭, 자원은 '★ 파워' 탭(최대 스택)에서 만듭니다.",
                  foreground="#777", justify="left", wraplength=600).grid(row=6, column=0, columnspan=4, sticky="w", padx=4)

    def _build_tags(self, it):
        for w in self.tag_frame.winfo_children():
            w.destroy()
        self.tag_vars = {}
        tags = GM.tags(self.app.project)
        if not tags:
            ttk.Label(self.tag_frame, text="(없음)", foreground="#999").pack(side="left")
        for t in tags:
            v = tk.BooleanVar(value=t["id"] in (it.get("gtags") or []))
            ttk.Checkbutton(self.tag_frame, text=t.get("name_ko") or t["id"], variable=v,
                            command=self.changed).pack(side="left", padx=(0, 10))
            self.tag_vars[t["id"]] = v

    def _cond_text(self, it, key):
        c = it.get(key)
        if not isinstance(c, dict):
            return "(없음) ✎"
        import blockui
        return blockui._plain(GM_cond_label(c, self.app.project))[:60] + "  ✎"

    def edit_cond(self, key):
        if self.cur is None:
            return
        import types
        import blockui
        it = self.items[self.cur]
        ed = types.SimpleNamespace(project=self.app.project, owner_kind="card", allow_event=False)
        d = blockui.SlotDialog(self, ed, "cond", it.get(key) or {"t": "cmp", "a": {"t": "played", "scope": "turn", "filter": "Any"},
                                                                  "op": ">=", "b": {"t": "num", "v": 2}})
        self.wait_window(d)
        if d.result is not None:
            it[key] = d.result
            self.cond_btns[key].configure(text=self._cond_text(it, key))
            self.changed()

    def clear_cond(self, key):
        if self.cur is None:
            return
        it = self.items[self.cur]
        it[key] = None
        self.cond_btns[key].configure(text=self._cond_text(it, key))
        self.changed()

    def load_extra(self, it):
        for k, v in self.kw_vars.items():
            v.set(k in it.get("keywords", []))
        self._build_tags(it)
        self.res_power.set_options([("", "없음")] + M.power_options(self.app.project))
        self.res_power.set_value(it.get("res_power", ""))
        self.frame_combo.set_options(CF.options(self.app.project))
        self.frame_combo.set_value(it.get("frame_style", ""))
        for key, b in self.cond_btns.items():
            b.configure(text=self._cond_text(it, key))

    def dump_extra(self, it):
        it["keywords"] = [k for k, v in self.kw_vars.items() if v.get()]
        it["gtags"] = [k for k, v in self.tag_vars.items() if v.get()]

    def new_item(self, iid):
        return M.new_card(iid)

    def label(self, it):
        t = M.label_of(M.CARD_TYPES, it.get("type"))
        return f"[{t}] {it.get('name_ko') or '?'}  ({it.get('cost')})  - {it['id']}"


class RelicTab(ItemTab):
    kind, key, noun = "relic", "relics", "유물"
    image_hint = "94×94 권장"

    def build_form(self, f):
        self.entry(f, 0, 0, "ID (영문 소문자_)", "id", hint="예: lucky_coin")
        self.entry(f, 2, 0, "이름 (한국어)", "name_ko")
        self.entry(f, 2, 2, "이름 (영어)", "name_en")
        self.entry(f, 3, 0, "이름 (중국어 간체)", "name_zh")
        self.combo(f, 4, 0, "희귀도", "rarity", M.RELIC_RARITIES)
        self.combo(f, 4, 2, "발동 시점", "trigger", M.RELIC_TRIGGERS, width=22)
        self.combo(f, 5, 0, "사용한 카드 종류", "played_filter", M.PLAYED_CARD_FILTERS)
        self.spin(f, 5, 2, "몇 장마다", "played_every", 1, 99)
        self.combo(f, 6, 0, "적 대상", "enemy_mode", M.RELIC_ENEMY_MODES)
        ttk.Label(f, text="※ '사용한 카드 종류 / 몇 장마다'는 발동 시점이 '카드 사용 시'일 때만, "
                          "'적 대상'은 피해·약화 같은 적 효과에만 쓰입니다.",
                  foreground="#777", wraplength=640, justify="left").grid(row=7, column=0, columnspan=4, sticky="w", padx=4)
        self.common_bottom(f, 8)

    def extra_rows(self, f, row):
        self.entry(f, row, 0, "플레이버 (한국어)", "flavor_ko", span=3)
        self.entry(f, row + 1, 0, "플레이버 (영어)", "flavor_en", span=3)
        self.entry(f, row + 2, 0, "플레이버 (중국어 간체)", "flavor_zh", span=3)

    def load_extra(self, it):
        c = self.vars["played_filter"][1]
        c.set_options(GM.card_filters(self.app.project))
        c.set_value(it.get("played_filter", "Any"))

    def new_item(self, iid):
        return M.new_relic(iid)


class PotionTab(ItemTab):
    kind, key, noun = "potion", "potions", "물약"
    image_hint = "256×256 권장"

    def build_form(self, f):
        self.entry(f, 0, 0, "ID (영문 소문자_)", "id", hint="예: fire_potion")
        self.entry(f, 2, 0, "이름 (한국어)", "name_ko")
        self.entry(f, 2, 2, "이름 (영어)", "name_en")
        self.entry(f, 3, 0, "이름 (중국어 간체)", "name_zh")
        self.combo(f, 4, 0, "희귀도", "rarity", M.POTION_RARITIES)
        self.combo(f, 4, 2, "대상", "target", M.POTION_TARGETS)
        ttk.Label(f, text="물약은 전투 중에만 사용할 수 있습니다.", foreground="#777").grid(
            row=5, column=1, columnspan=3, sticky="w", padx=4)
        self.common_bottom(f, 6)

    def new_item(self, iid):
        return M.new_potion(iid)


class PowerTab(ItemTab):
    kind, key, noun = "power", "powers", "파워"
    image_hint = "64×64 권장 (큰 그림 256×256)"

    def build_form(self, f):
        ttk.Label(f, text="새 버프/디버프를 만들어 게임에 없는 메커니즘을 만듭니다. 카드·유물·물약의 '파워 부여' 효과에서 "
                          "★ 표시로 고를 수 있고, '조건'·'스택 비례'·'파워 제거'와 함께 쓰면 쌓고-터뜨리는 식의 시스템을 만들 수 있습니다.",
                  foreground="#555", wraplength=700, justify="left").grid(row=0, column=0, columnspan=4, sticky="w",
                                                                          padx=4, pady=(0, 6))
        self.entry(f, 1, 0, "ID (영문 소문자_)", "id", hint="예: burn → 게임 ID MYMOD-BURN_POWER")
        self.entry(f, 3, 0, "이름 (한국어)", "name_ko")
        self.entry(f, 3, 2, "이름 (영어)", "name_en")
        self.entry(f, 4, 0, "이름 (중국어 간체)", "name_zh")
        self.combo(f, 5, 0, "종류", "type", M.POWER_TYPES)
        self.combo(f, 5, 2, "중첩 방식", "stack", M.POWER_STACKS, width=20)
        self.combo(f, 6, 0, "발동 시점", "trigger", M.POWER_TRIGGERS, width=22)
        self.combo(f, 6, 2, "줄어드는 방식", "decay", M.POWER_DECAY, width=20)
        self.combo(f, 7, 0, "카드 종류", "played_filter", M.PLAYED_CARD_FILTERS)
        self.combo(f, 7, 2, "누가 사용", "played_by", M.POWER_PLAYED_BY, width=20)
        self.combo(f, 8, 0, "적 대상", "enemy_mode", M.RELIC_ENEMY_MODES)
        ttk.Label(f, text="※ '카드 종류 / 누가 사용'은 발동 시점이 '카드 사용 시'일 때만 쓰입니다. 효과 수치에 '× 스택 수'를 켜면 "
                          "쌓인 만큼 강해집니다. 효과의 '상대'는 공격자 / 맞은 적 / 카드의 대상입니다.",
                  foreground="#777", wraplength=700, justify="left").grid(row=9, column=0, columnspan=4, sticky="w", padx=4)
        self.common_bottom(f, 10)

    def extra_rows(self, f, row):
        ttk.Label(f, text="상시 효과").grid(row=row, column=0, sticky="nw", padx=4, pady=(8, 2))
        self.mods = ModifierList(f, self.changed)
        self.mods.grid(row=row, column=1, columnspan=3, sticky="we", padx=4, pady=(8, 2))
        g = ttk.LabelFrame(f, text="🎲 기믹 (자원 · 터지는 스택 · 날씨/자세 그룹)", padding=6)
        g.grid(row=row + 1, column=0, columnspan=4, sticky="we", padx=4, pady=(8, 2))
        self.spin(g, 0, 0, "최대 스택 (0 = 없음)", "cap", 0, 999)
        g.columnconfigure(2, weight=1)
        self.cap_btn = ttk.Button(g, text="", width=26, command=lambda: self.edit_prog("overflow_blocks"))
        self.cap_btn.grid(row=0, column=2, columnspan=2, sticky="w", padx=4)
        self.spin(g, 1, 0, "기준치 (0 = 없음)", "threshold", 0, 999)
        self.thr_btn = ttk.Button(g, text="", width=26, command=lambda: self.edit_prog("threshold_blocks"))
        self.thr_btn.grid(row=1, column=2, columnspan=2, sticky="w", padx=4)
        self.combo(g, 2, 0, "기준치 도달 후", "threshold_mode", GM.THRESHOLD_MODES, width=30)
        self.entry(g, 3, 0, "그룹 (같은 그룹은 하나만)", "group", width=16, hint="예: 날씨, 자세 — 비우면 없음")
        hv = tk.BooleanVar()
        ttk.Checkbutton(g, text="숨김 (아이콘 없이 내부 카운터로만 사용)", variable=hv, command=self.changed).grid(
            row=5, column=0, columnspan=4, sticky="w", padx=4, pady=2)
        self.vars["hidden"] = ("bool", hv)
        self.var_labels["hidden"] = "숨김 (아이콘 안 보임)"
        ttk.Label(g, text="자원 만들기: 중첩 + 최대 스택 (예: 포탄 최대 6). 카드의 '자원 비용'이나 블록 '낼 수 있으면'으로 소모합니다.\n"
                          "터지는 스택: 기준치 5 + 블록 (예: 빙결 5 이상이면 깨지며 피해). '그 수치' 값으로 넘친 양·스택 수를 씁니다.\n"
                          "턴마다 초기화하려면 '줄어드는 방식'을 '내 턴 시작 시 사라짐'으로 고르세요.",
                  foreground="#777", justify="left").grid(row=6, column=0, columnspan=4, sticky="w", padx=4)

    def _prog_text(self, it, key):
        import blockcode
        n = sum(1 for _ in blockcode.walk(it.get(key)))
        label = "넘칠 때" if key == "overflow_blocks" else "기준치 도달 시"
        return f"🧩 {label} 블록 {n}개 …"

    def edit_prog(self, key):
        if self.cur is None:
            return
        import blockui
        it = self.items[self.cur]
        where = "최대 스택을 넘칠 때 (넘친 만큼은 버려지고)" if key == "overflow_blocks" else "기준치 이상이 될 때"
        ed = blockui.BlockEditor(self, self.app.project, "power", it, it.get(key) or [], where=where, allow_event=True)
        self.wait_window(ed)
        if ed.result is not None:
            it[key] = ed.result["blocks"]
            self.load_extra(it)
            self.changed()

    def load_extra(self, it):
        self.mods.set(it.setdefault("modifiers", []))
        c = self.vars["played_filter"][1]
        c.set_options(GM.card_filters(self.app.project))
        c.set_value(it.get("played_filter", "Any"))
        self.cap_btn.configure(text=self._prog_text(it, "overflow_blocks"))
        self.thr_btn.configure(text=self._prog_text(it, "threshold_blocks"))

    def new_item(self, iid):
        return M.new_power(iid)

    def label(self, it):
        return f"[{M.label_of(M.POWER_TYPES, it.get('type'))}] {it.get('name_ko') or '?'}  - {it['id']}"



# ---------------------------------------------------------------------------
# 기믹 탭 (태그 · 소환수)
# ---------------------------------------------------------------------------
class GimmickTab(ttk.Frame):
    """카드 태그와 소환수를 만든다. 자원·날씨·터지는 스택은 파워 탭, 연계·선택지는 블록 코딩에서."""

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._loading = False
        sf = ScrollFrame(self)
        sf.pack(fill="both", expand=True)
        root = ttk.Frame(sf.inner, padding=10)
        root.pack(fill="both", expand=True)
        head = ttk.Frame(root)
        head.pack(fill="x")
        ttk.Label(head, text="🎲 기믹 — 캐릭터만의 고유 시스템", font=("Malgun Gothic", 13, "bold")).pack(side="left")
        ttk.Button(head, text="예시 기믹 한 벌 추가 (해적·마법사 스타일)", command=self.add_examples).pack(side="right")
        guide = ("메이플 해적·마법사 모드에 쓰인 장치들을 조립해서 만듭니다.\n"
                 "  • 태그 (아래): '격투', '포격' 같은 카드 키워드. 카드 탭에서 붙이고, 블록의 '사용한 카드 수'로 연계를, 유물·파워의 '카드 종류'로 '격투 카드를 쓸 때마다'를 만듭니다.\n"
                 "  • 소환수 (아래): 슬롯 N칸. 같은 것을 다시 소환하면 단계가 오르고, 매 턴 블록대로 행동합니다. 블록의 '소환 / 지휘'로 씁니다.\n"
                 "  • 자원 (★ 파워 탭): 최대 스택(포탄 6), 넘치면 효과(충전), 기준치에서 터짐(빙결 5), 같은 그룹은 하나만(날씨·자세), 숨김 카운터.\n"
                 "  • 카드 탭: 자원 비용(해룡 에너지 3 소모), 사용 조건, 금색 테두리(연계 표시).\n"
                 "  • 블록 코딩: '낼 수 있으면 내고', '하나 고르기', '더미에서 골라서', '다음 턴에 예약', '이번 턴 사용한 격투 카드 수'.")
        ttk.Label(root, text=guide, foreground="#444", justify="left", wraplength=1200).pack(fill="x", pady=(6, 10))

        cols = ttk.Frame(root)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1)
        cols.columnconfigure(1, weight=1)

        # ---- 태그 ----
        tf = ttk.LabelFrame(cols, text="카드 태그 (키워드)", padding=8)
        tf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        self.tag_list = tk.Listbox(tf, height=8, exportselection=False, activestyle="none")
        self.tag_list.grid(row=0, column=0, columnspan=4, sticky="we")
        self.tag_list.bind("<<ListboxSelect>>", lambda _e: self.load_tag())
        tb = ttk.Frame(tf)
        tb.grid(row=1, column=0, columnspan=4, sticky="we", pady=4)
        ttk.Button(tb, text="새 태그", command=self.add_tag).pack(side="left")
        ttk.Button(tb, text="삭제", command=self.del_tag).pack(side="left", padx=4)
        self.tv = {}
        for r, (k, label) in enumerate((("id", "ID (영문 소문자_)"), ("name_ko", "이름 (한국어)"), ("name_en", "이름 (영어)"),
                                        ("desc_ko", "툴팁 설명 (한국어)"), ("desc_en", "툴팁 설명 (영어)")), start=2):
            lang_entry(tf, self.tv, k, label, self.tag_changed, row=r)
        self.tag_show = tk.BooleanVar(value=True)
        ttk.Checkbutton(tf, text="카드 설명 맨 앞에 태그 이름 표시 (예: '격투.')", variable=self.tag_show,
                        command=self.tag_changed).grid(row=7, column=0, columnspan=4, sticky="w")
        tf.columnconfigure(1, weight=1)

        # ---- 소환수 ----
        sf2 = ttk.LabelFrame(cols, text="소환수", padding=8)
        sf2.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        top = ttk.Frame(sf2)
        top.grid(row=0, column=0, columnspan=4, sticky="we")
        ttk.Label(top, text="소환 슬롯 수").pack(side="left")
        self.slots = tk.StringVar()
        ttk.Spinbox(top, from_=1, to=10, textvariable=self.slots, width=4).pack(side="left", padx=4)
        self.slots.trace_add("write", lambda *_: self.slots_changed())
        ttk.Label(top, text="가득 차면 가장 먼저 온 소환수가 돌아갑니다.", foreground="#777").pack(side="left", padx=6)
        self.sum_list = tk.Listbox(sf2, height=6, exportselection=False, activestyle="none")
        self.sum_list.grid(row=1, column=0, columnspan=4, sticky="we", pady=(4, 0))
        self.sum_list.bind("<<ListboxSelect>>", lambda _e: self.load_summon())
        sb = ttk.Frame(sf2)
        sb.grid(row=2, column=0, columnspan=4, sticky="we", pady=4)
        ttk.Button(sb, text="새 소환수", command=self.add_summon).pack(side="left")
        ttk.Button(sb, text="삭제", command=self.del_summon).pack(side="left", padx=4)
        self.sv = {}
        for r, (k, label) in enumerate((("id", "ID (영문 소문자_)"), ("name_ko", "이름 (한국어)"), ("name_en", "이름 (영어)")), start=3):
            lang_entry(sf2, self.sv, k, label, self.summon_changed, row=r)
        ttk.Label(sf2, text="최고 단계").grid(row=6, column=0, sticky="w", pady=2)
        self.max_rank = tk.StringVar()
        ttk.Spinbox(sf2, from_=1, to=9, textvariable=self.max_rank, width=4).grid(row=6, column=1, sticky="w")
        self.max_rank.trace_add("write", lambda *_: self.summon_changed())
        ttk.Label(sf2, text="행동").grid(row=7, column=0, sticky="w", pady=2)
        self.timing = LabeledCombo(sf2, GM.SUMMON_TIMINGS, width=28)
        self.timing.grid(row=7, column=1, columnspan=3, sticky="w")
        self.timing.bind("<<ComboboxSelected>>", lambda _e: self.summon_changed())
        self.act_on_max = tk.BooleanVar(value=True)
        ttk.Checkbutton(sf2, text="최고 단계에서 또 소환하면 즉시 행동", variable=self.act_on_max,
                        command=self.summon_changed).grid(row=8, column=0, columnspan=4, sticky="w")
        self.sum_img = tk.StringVar()
        file_row(sf2, 9, "아이콘 (PNG)", self.sum_img, self.summon_changed, hint="64×64")
        bf = ttk.Frame(sf2)
        bf.grid(row=10, column=0, columnspan=4, sticky="we", pady=(6, 2))
        ttk.Button(bf, text="🧩 행동 블록 편집…", command=self.edit_summon_blocks).pack(side="left")
        ttk.Label(bf, text="블록 안의 '이 파워의 스택 수' = 소환수의 단계", foreground="#777").pack(side="left", padx=8)
        self.sum_desc = ttk.Label(sf2, text="", foreground="#2d4f6a", wraplength=560, justify="left")
        self.sum_desc.grid(row=11, column=0, columnspan=4, sticky="w", pady=4)
        for r, (k, label) in enumerate((("desc_ko", "설명 직접 (한국어)"), ("desc_en", "설명 직접 (영어)")), start=12):
            lang_entry(sf2, self.sv, k, label, self.summon_changed, row=r)
        sf2.columnconfigure(1, weight=1)
        self.tag_cur = None
        self.sum_cur = None
        self.orb_cur = None
        self._build_orbs(cols)
        self._build_pets(cols)

    # ---- 데이터 ----
    @property
    def g(self):
        # 정규화는 비어 있을 때만 (매번 하면 dict 가 새로 만들어져 편집 중인 참조가 끊긴다)
        g = self.app.project.get("gimmicks")
        if not isinstance(g, dict) or any(k not in g for k in ("tags", "summons", "orbs", "effects", "buttons", "pets")):
            GM.normalize(self.app.project)
        return self.app.project["gimmicks"]

    def load(self):
        self._loading = True
        try:
            self.slots.set(str(self.g.get("summon_slots", 3)))
        finally:
            self._loading = False
        self.refresh_tags()
        self.refresh_summons()
        self.refresh_orbs()
        self.refresh_pets()

    def refresh_tags(self, select=None):
        self.tag_list.delete(0, "end")
        for t in self.g["tags"]:
            self.tag_list.insert("end", f"#{t.get('name_ko') or '?'}  ({t['id']})")
        if self.g["tags"]:
            i = min(select if select is not None else (self.tag_cur or 0), len(self.g["tags"]) - 1)
            self.tag_list.selection_set(i)
            self.load_tag(i)
        else:
            self.tag_cur = None

    def refresh_summons(self, select=None):
        self.sum_list.delete(0, "end")
        for x in self.g["summons"]:
            self.sum_list.insert("end", f"{x.get('name_ko') or '?'}  (최고 {x.get('max_rank', 3)}단계, {x['id']})")
        if self.g["summons"]:
            i = min(select if select is not None else (self.sum_cur or 0), len(self.g["summons"]) - 1)
            self.sum_list.selection_set(i)
            self.load_summon(i)
        else:
            self.sum_cur = None
            self.sum_desc.configure(text="")

    def _unique(self, base):
        used = self.app.all_ids()
        if base not in used:
            return base
        i = 1
        while f"{base}_{GM.letters(i).lower()}" in used:
            i += 1
        return f"{base}_{GM.letters(i).lower()}"

    # ---- 태그 ----
    def load_tag(self, i=None):
        if i is None:
            sel = self.tag_list.curselection()
            if not sel:
                return
            i = sel[0]
        self.tag_cur = i
        t = self.g["tags"][i]
        self._loading = True
        try:
            for k, v in self.tv.items():
                v.set(t.get(k, ""))
            self.tag_show.set(bool(t.get("show_in_text", True)))
        finally:
            self._loading = False

    def tag_changed(self):
        if self._loading or self.tag_cur is None:
            return
        t = self.g["tags"][self.tag_cur]
        old = t["id"]
        for k, v in self.tv.items():
            t[k] = v.get().strip()
        t["show_in_text"] = bool(self.tag_show.get())
        if t["id"] != old and t["id"]:
            rename_gimmick_ref(self.app.project, "tag", old, t["id"])
        self.tag_list.delete(self.tag_cur)
        self.tag_list.insert(self.tag_cur, f"#{t.get('name_ko') or '?'}  ({t['id']})")
        self.tag_list.selection_set(self.tag_cur)
        self.app.mark_dirty()

    def add_tag(self):
        self.g["tags"].append(GM.new_tag(self._unique("new_tag")))
        self.app.mark_dirty()
        self.refresh_tags(len(self.g["tags"]) - 1)

    def del_tag(self):
        if self.tag_cur is None:
            return
        t = self.g["tags"][self.tag_cur]
        if not messagebox.askyesno(APP_TITLE, f"태그 '{t.get('name_ko')}'를 삭제할까요? 카드에 붙은 태그도 빠집니다.", parent=self):
            return
        rename_gimmick_ref(self.app.project, "tag", t["id"], None)
        del self.g["tags"][self.tag_cur]
        self.app.mark_dirty()
        self.refresh_tags(max(0, self.tag_cur - 1))

    # ---- 소환수 ----
    def load_summon(self, i=None):
        if i is None:
            sel = self.sum_list.curselection()
            if not sel:
                return
            i = sel[0]
        self.sum_cur = i
        x = self.g["summons"][i]
        self._loading = True
        try:
            for k, v in self.sv.items():
                v.set(x.get(k, ""))
            self.max_rank.set(str(x.get("max_rank", 3)))
            self.timing.set_value(x.get("timing", "turn_end"))
            self.act_on_max.set(bool(x.get("act_on_max", True)))
            self.sum_img.set(x.get("image", ""))
        finally:
            self._loading = False
        self.show_summon_desc(x)

    def show_summon_desc(self, x):
        import blockui
        self.sum_desc.configure(text="게임 설명: " + blockui._plain(GM.summon_text(self.app.project, x, "ko")).replace("{Amount}", "N"))

    def summon_changed(self):
        if self._loading or self.sum_cur is None:
            return
        x = self.g["summons"][self.sum_cur]
        old = x["id"]
        for k, v in self.sv.items():
            x[k] = v.get().strip()
        try:
            x["max_rank"] = max(1, int(self.max_rank.get()))
        except ValueError:
            pass
        x["timing"] = self.timing.get_value()
        x["act_on_max"] = bool(self.act_on_max.get())
        x["image"] = self.sum_img.get().strip().strip('"')
        if x["id"] != old and x["id"]:
            rename_gimmick_ref(self.app.project, "summon", old, x["id"])
        self.sum_list.delete(self.sum_cur)
        self.sum_list.insert(self.sum_cur, f"{x.get('name_ko') or '?'}  (최고 {x.get('max_rank', 3)}단계, {x['id']})")
        self.sum_list.selection_set(self.sum_cur)
        self.show_summon_desc(x)
        self.app.mark_dirty()

    def slots_changed(self):
        if self._loading:
            return
        try:
            self.g["summon_slots"] = max(1, int(self.slots.get()))
            self.app.mark_dirty()
        except ValueError:
            pass

    def add_summon(self):
        self.g["summons"].append(GM.new_summon(self._unique("new_summon")))
        self.app.mark_dirty()
        self.refresh_summons(len(self.g["summons"]) - 1)

    def del_summon(self):
        if self.sum_cur is None:
            return
        x = self.g["summons"][self.sum_cur]
        if not messagebox.askyesno(APP_TITLE, f"소환수 '{x.get('name_ko')}'를 삭제할까요?", parent=self):
            return
        del self.g["summons"][self.sum_cur]
        self.app.mark_dirty()
        self.refresh_summons(max(0, self.sum_cur - 1))

    def edit_summon_blocks(self):
        if self.sum_cur is None:
            return
        import blockui
        x = self.g["summons"][self.sum_cur]
        ed = blockui.BlockEditor(self, self.app.project, "summon", {"id": x["id"], "trigger": "none", "enemy_mode": "all"},
                                 x.get("blocks") or [], where=f"소환수 '{x.get('name_ko')}'가 행동할 때")
        self.wait_window(ed)
        if ed.result is not None:
            x["blocks"] = ed.result["blocks"]
            self.app.mark_dirty()
            self.show_summon_desc(x)


    # ---- 동료 (골골이형) ----
    def _build_pets(self, cols):
        pf = ttk.LabelFrame(cols, text="동료 (골골이형) — 전장에 서 있는 체력 있는 소환수. 블록 '동료 소환 / 공격 / 행동 / 희생'으로 씁니다", padding=8)
        pf.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        pf.columnconfigure(3, weight=1)
        left = ttk.Frame(pf)
        left.grid(row=0, column=0, rowspan=10, sticky="nsw", padx=(0, 12))
        self.pet_list = tk.Listbox(left, height=8, width=30, exportselection=False, activestyle="none")
        self.pet_list.pack(fill="both", expand=True)
        self.pet_list.bind("<<ListboxSelect>>", lambda _e: self.load_pet())
        bb = ttk.Frame(left)
        bb.pack(fill="x", pady=4)
        ttk.Button(bb, text="새 동료", command=self.add_pet).pack(side="left")
        ttk.Button(bb, text="삭제", command=self.del_pet).pack(side="left", padx=4)
        self.pv_ = {}
        for r, (k, label) in enumerate((("id", "ID (영문 소문자_)"), ("name_ko", "이름 (한국어)"), ("name_en", "이름 (영어)")), start=0):
            lang_entry(pf, self.pv_, k, label, self.pet_changed, width=40, row=r, col=2, span=1, label_col=1)
        ttk.Label(pf, text="그림 (PNG)").grid(row=3, column=1, sticky="w")
        imf = ttk.Frame(pf)
        imf.grid(row=3, column=2, sticky="w")
        self.pet_img = tk.StringVar()
        ttk.Entry(imf, textvariable=self.pet_img, width=34).pack(side="left")
        ttk.Button(imf, text="찾기…", command=self.pick_pet_img).pack(side="left", padx=4)
        ttk.Button(imf, text="지우기", command=lambda: (self.pet_img.set(""), self.pet_changed())).pack(side="left")
        tf = ttk.Frame(pf)
        tf.grid(row=4, column=1, columnspan=2, sticky="w", pady=2)
        self.pet_scale, self.pet_lift = tk.StringVar(), tk.StringVar()
        ttk.Label(tf, text="크기 %").pack(side="left")
        ttk.Spinbox(tf, from_=10, to=400, increment=5, textvariable=self.pet_scale, width=5).pack(side="left", padx=(2, 10))
        ttk.Label(tf, text="띄우기(px)").pack(side="left")
        ttk.Spinbox(tf, from_=-200, to=300, increment=5, textvariable=self.pet_lift, width=5).pack(side="left", padx=(2, 10))
        self.pet_flip = tk.BooleanVar()
        ttk.Checkbutton(tf, text="좌우 반전", variable=self.pet_flip, command=self.pet_changed).pack(side="left")
        for v in (self.pet_scale, self.pet_lift):
            v.trace_add("write", lambda *_: self.pet_changed())
        self.pet_guard = tk.BooleanVar(value=True)
        ttk.Checkbutton(pf, text="주인을 노린 공격을 대신 받음 (골골이처럼)", variable=self.pet_guard,
                        command=self.pet_changed).grid(row=5, column=1, columnspan=2, sticky="w")
        ttk.Label(pf, text="행동").grid(row=6, column=1, sticky="w")
        import pets as PT
        self.pet_timing = LabeledCombo(pf, PT.PET_TIMINGS, width=26)
        self.pet_timing.grid(row=6, column=2, sticky="w")
        self.pet_timing.bind("<<ComboboxSelected>>", lambda _e: self.pet_changed())
        ttk.Button(pf, text="🧩 행동 블록 편집…", command=self.edit_pet_blocks).grid(row=7, column=1, columnspan=2, sticky="w", pady=4)
        self.pet_desc = ttk.Label(pf, text="", foreground="#2d4f6a", wraplength=620, justify="left")
        self.pet_desc.grid(row=8, column=1, columnspan=2, sticky="w")
        ttk.Label(pf, text="소환하면 체력 N으로 생기고, 살아 있을 때 또 소환하면 최대 체력 +N, 쓰러졌으면 되살아납니다 (골골이와 같은 규칙).\n"
                           "그림 한 장으로 전장에 서고, 공격할 때 앞으로 튀어 나갑니다. 오른쪽은 전투 화면에서 보이는 모습입니다.",
                  foreground="#777", justify="left").grid(row=9, column=1, columnspan=2, sticky="w")
        self.pet_canvas = tk.Canvas(pf, width=300, height=260, background="#1c2a22", highlightthickness=0)
        self.pet_canvas.grid(row=0, column=3, rowspan=10, sticky="ne", padx=8)
        self.pet_cur = None
        self._pet_photo = None

    def refresh_pets(self, select=None):
        self.pet_list.delete(0, "end")
        for p in self.g["pets"]:
            self.pet_list.insert("end", f"🐾 {p.get('name_ko') or '?'}  ({p['id']})")
        if self.g["pets"]:
            i = min(select if select is not None else (self.pet_cur or 0), len(self.g["pets"]) - 1)
            self.pet_list.selection_set(i)
            self.load_pet(i)
        else:
            self.pet_cur = None
            self.pet_desc.configure(text="")
            self.pet_canvas.delete("all")

    def load_pet(self, i=None):
        if i is None:
            sel = self.pet_list.curselection()
            if not sel:
                return
            i = sel[0]
        self.pet_cur = i
        p = self.g["pets"][i]
        self._loading = True
        try:
            for k, v in self.pv_.items():
                v.set(p.get(k, ""))
            self.pet_img.set(p.get("image", ""))
            self.pet_scale.set(str(p.get("scale", 100)))
            self.pet_lift.set(str(p.get("lift", 0)))
            self.pet_flip.set(bool(p.get("flip")))
            self.pet_guard.set(bool(p.get("guard", True)))
            self.pet_timing.set_value(p.get("timing", "turn_end"))
        finally:
            self._loading = False
        self.show_pet(p)

    def show_pet(self, p):
        import blockui
        import pets as PT
        self.pet_desc.configure(text="게임 설명: " + blockui._plain(PT.pet_text(self.app.project, p, "ko")))
        self._pet_photo = pet_preview(self.pet_canvas, self.app, p.get("image"), p.get("scale"), p.get("flip"), p.get("lift"),
                                      p.get("name_ko") or p["id"])

    def pet_changed(self):
        if self._loading or self.pet_cur is None:
            return
        p = self.g["pets"][self.pet_cur]
        old = p["id"]
        for k, v in self.pv_.items():
            p[k] = v.get().strip()
        p["image"] = self.pet_img.get().strip().strip('"')
        for k, var in (("scale", self.pet_scale), ("lift", self.pet_lift)):
            try:
                p[k] = int(float(var.get()))
            except ValueError:
                pass
        p["flip"] = bool(self.pet_flip.get())
        p["guard"] = bool(self.pet_guard.get())
        p["timing"] = self.pet_timing.get_value()
        if p["id"] != old and p["id"]:
            rename_gimmick_ref(self.app.project, "pet", old, p["id"])
        self.pet_list.delete(self.pet_cur)
        self.pet_list.insert(self.pet_cur, f"🐾 {p.get('name_ko') or '?'}  ({p['id']})")
        self.pet_list.selection_set(self.pet_cur)
        self.show_pet(p)
        self.app.mark_dirty()

    def pick_pet_img(self):
        f = filedialog.askopenfilename(filetypes=[("PNG 이미지", "*.png"), ("모든 파일", "*.*")], parent=self)
        if f:
            self.pet_img.set(f)
            self.pet_changed()

    def add_pet(self):
        import pets as PT
        p = PT.new_pet(self._unique("new_pet"))
        for b in p["blocks"]:
            b["args"]["pet"] = p["id"]
        self.g["pets"].append(p)
        self.app.mark_dirty()
        self.refresh_pets(len(self.g["pets"]) - 1)

    def del_pet(self):
        if self.pet_cur is None:
            return
        p = self.g["pets"][self.pet_cur]
        if not messagebox.askyesno(APP_TITLE, f"동료 '{p.get('name_ko')}'를 삭제할까요?", parent=self):
            return
        del self.g["pets"][self.pet_cur]
        self.app.mark_dirty()
        self.refresh_pets(max(0, self.pet_cur - 1))

    def edit_pet_blocks(self):
        if self.pet_cur is None:
            return
        import blockui
        p = self.g["pets"][self.pet_cur]
        ed = blockui.BlockEditor(self, self.app.project, "pet", {"id": p["id"], "trigger": "none", "enemy_mode": "all"},
                                 p.get("blocks") or [], where=f"동료 '{p.get('name_ko')}'가 행동할 때")
        self.wait_window(ed)
        if ed.result is not None:
            p["blocks"] = ed.result["blocks"]
            self.app.mark_dirty()
            self.show_pet(p)

    # ---- 구체 ----
    def _build_orbs(self, cols):
        of = ttk.LabelFrame(cols, text="구체 (디펙트식) — 캐릭터 탭에서 구체 슬롯 수를 정하고, 블록 '구체 영창 / 발현'으로 씁니다", padding=8)
        of.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(12, 0))
        of.columnconfigure(3, weight=1)
        left = ttk.Frame(of)
        left.grid(row=0, column=0, rowspan=8, sticky="nsw", padx=(0, 12))
        self.orb_list = tk.Listbox(left, height=8, width=30, exportselection=False, activestyle="none")
        self.orb_list.pack(fill="both", expand=True)
        self.orb_list.bind("<<ListboxSelect>>", lambda _e: self.load_orb())
        ob = ttk.Frame(left)
        ob.pack(fill="x", pady=4)
        ttk.Button(ob, text="새 구체", command=self.add_orb).pack(side="left")
        ttk.Button(ob, text="삭제", command=self.del_orb).pack(side="left", padx=4)
        self.ov = {}
        for r, (k, label) in enumerate((("id", "ID (영문 소문자_)"), ("name_ko", "이름 (한국어)"), ("name_en", "이름 (영어)")), start=0):
            lang_entry(of, self.ov, k, label, self.orb_changed, width=40, row=r, col=2, span=2, label_col=1)
        ttk.Label(of, text="모양 / 색").grid(row=3, column=1, sticky="w", pady=2)
        lf = ttk.Frame(of)
        lf.grid(row=3, column=2, columnspan=2, sticky="w")
        self.orb_look = LabeledCombo(lf, GM.ORB_LOOKS, width=14)
        self.orb_look.pack(side="left")
        self.orb_look.bind("<<ComboboxSelected>>", lambda _e: self.orb_changed())
        self.ov["tint"] = tk.StringVar()
        ttk.Entry(lf, textvariable=self.ov["tint"], width=9).pack(side="left", padx=4)
        self.ov["tint"].trace_add("write", lambda *_: self.orb_changed())
        self.orb_swatch = tk.Label(lf, width=3, relief="groove")
        self.orb_swatch.pack(side="left")
        ttk.Button(lf, text="색 고르기…", command=self.pick_orb_color).pack(side="left", padx=4)
        ttk.Label(lf, text="게임 구체 모양에 색을 입힙니다 (#ffffff = 원래 색)", foreground="#777").pack(side="left")
        ttk.Label(of, text="지속 / 발현 수치").grid(row=4, column=1, sticky="w", pady=2)
        nf = ttk.Frame(of)
        nf.grid(row=4, column=2, columnspan=2, sticky="w")
        for k in ("passive", "evoke"):
            ttk.Label(nf, text="지속" if k == "passive" else "  발현").pack(side="left")
            v = tk.StringVar()
            ttk.Spinbox(nf, from_=0, to=999, textvariable=v, width=5).pack(side="left", padx=2)
            v.trace_add("write", lambda *_: self.orb_changed())
            self.ov[k] = v
        ttk.Label(nf, text="  (밀집이 더해짐. 블록 값 '이 구체의 지속/발현 수치')", foreground="#777").pack(side="left")
        ttk.Label(of, text="지속 효과 시점").grid(row=5, column=1, sticky="w", pady=2)
        self.orb_timing = LabeledCombo(of, GM.ORB_TIMINGS, width=26)
        self.orb_timing.grid(row=5, column=2, sticky="w")
        self.orb_timing.bind("<<ComboboxSelected>>", lambda _e: self.orb_changed())
        self.orb_img = tk.StringVar()
        ttk.Label(of, text="아이콘 (PNG, 툴팁)").grid(row=6, column=1, sticky="w")
        imf = ttk.Frame(of)
        imf.grid(row=6, column=2, columnspan=2, sticky="we")
        ttk.Entry(imf, textvariable=self.orb_img, width=40).pack(side="left")
        ttk.Button(imf, text="찾기…", command=lambda: (self.orb_img.set(filedialog.askopenfilename(
            filetypes=[("PNG 이미지", "*.png")]) or self.orb_img.get()), self.orb_changed())).pack(side="left", padx=4)
        bf = ttk.Frame(of)
        bf.grid(row=7, column=1, columnspan=3, sticky="w", pady=(6, 2))
        ttk.Button(bf, text="🧩 지속 효과 블록…", command=lambda: self.edit_orb_blocks("passive_blocks")).pack(side="left")
        ttk.Button(bf, text="🧩 발현 효과 블록…", command=lambda: self.edit_orb_blocks("evoke_blocks")).pack(side="left", padx=6)
        self.orb_desc = ttk.Label(of, text="", foreground="#2d4f6a", wraplength=900, justify="left")
        self.orb_desc.grid(row=8, column=0, columnspan=4, sticky="w", pady=4)

    def refresh_orbs(self, select=None):
        self.orb_list.delete(0, "end")
        for o in self.g["orbs"]:
            self.orb_list.insert("end", f"◎ {o.get('name_ko') or '?'}  ({o['id']})")
        if self.g["orbs"]:
            i = min(select if select is not None else (self.orb_cur or 0), len(self.g["orbs"]) - 1)
            self.orb_list.selection_set(i)
            self.load_orb(i)
        else:
            self.orb_cur = None
            self.orb_desc.configure(text="")

    def load_orb(self, i=None):
        if i is None:
            sel = self.orb_list.curselection()
            if not sel:
                return
            i = sel[0]
        self.orb_cur = i
        o = self.g["orbs"][i]
        self._loading = True
        try:
            for k, v in self.ov.items():
                v.set(str(o.get(k, "")))
            self.orb_look.set_value(o.get("look", "lightning_orb"))
            self.orb_timing.set_value(o.get("timing", "turn_end"))
            self.orb_img.set(o.get("image", ""))
        finally:
            self._loading = False
        self.show_orb(o)

    def show_orb(self, o):
        import blockui
        try:
            self.orb_swatch.configure(background=o.get("tint") or "#ffffff")
        except tk.TclError:
            pass
        t = GM.orb_text(self.app.project, o, "ko").replace("[blue]{Passive}[/blue]", str(o.get("passive"))) \
            .replace("[blue]{Evoke}[/blue]", str(o.get("evoke")))
        self.orb_desc.configure(text="게임 설명: " + blockui._plain(t).replace("\n", "  /  "))

    def orb_changed(self):
        if self._loading or self.orb_cur is None:
            return
        o = self.g["orbs"][self.orb_cur]
        old = o["id"]
        for k, v in self.ov.items():
            val = v.get().strip()
            if k in ("passive", "evoke"):
                try:
                    o[k] = int(val)
                except ValueError:
                    pass
            else:
                o[k] = val
        o["look"] = self.orb_look.get_value()
        o["timing"] = self.orb_timing.get_value()
        o["image"] = self.orb_img.get().strip().strip('"')
        if o["id"] != old and o["id"]:
            rename_gimmick_ref(self.app.project, "orb", old, o["id"])
        self.orb_list.delete(self.orb_cur)
        self.orb_list.insert(self.orb_cur, f"◎ {o.get('name_ko') or '?'}  ({o['id']})")
        self.orb_list.selection_set(self.orb_cur)
        self.show_orb(o)
        self.app.mark_dirty()

    def pick_orb_color(self):
        if self.orb_cur is None:
            return
        res = colorchooser.askcolor(color=self.ov["tint"].get() or "#ffffff", parent=self)
        if res and res[1]:
            self.ov["tint"].set(res[1])

    def add_orb(self):
        self.g["orbs"].append(GM.new_orb(self._unique("new_orb")))
        self.app.mark_dirty()
        self.refresh_orbs(len(self.g["orbs"]) - 1)

    def del_orb(self):
        if self.orb_cur is None:
            return
        o = self.g["orbs"][self.orb_cur]
        if not messagebox.askyesno(APP_TITLE, f"구체 '{o.get('name_ko')}'를 삭제할까요?", parent=self):
            return
        del self.g["orbs"][self.orb_cur]
        self.app.mark_dirty()
        self.refresh_orbs(max(0, self.orb_cur - 1))

    def edit_orb_blocks(self, key):
        if self.orb_cur is None:
            return
        import blockui
        o = self.g["orbs"][self.orb_cur]
        where = f"구체 '{o.get('name_ko')}'의 " + ("지속 효과가 발동할 때" if key == "passive_blocks" else "발현될 때")
        ed = blockui.BlockEditor(self, self.app.project, "orb", o, o.get(key) or [], where=where)
        self.wait_window(ed)
        if ed.result is not None:
            o[key] = ed.result["blocks"]
            self.app.mark_dirty()
            self.show_orb(o)

    def add_examples(self):
        if not messagebox.askyesno(APP_TITLE, "현재 프로젝트에 예시 기믹(태그·자원·소환수·날씨·선택지와 그것을 쓰는 카드)을 추가할까요?\n"
                                              "기존 항목은 그대로 두고 새로 추가만 합니다.", parent=self):
            return
        added = GM.add_examples(self.app.project)
        self.app.mark_dirty()
        self.app.load_all()
        messagebox.showinfo(APP_TITLE, "추가했습니다:\n\n• " + "\n• ".join(added), parent=self)


def pet_preview(canvas, app, image, scale, flip, lift, label):
    """게임 배경 위에 그림을 발밑 기준으로 세워 보여 준다 (전투 화면과 같은 크기 비율)."""
    from PIL import Image, ImageDraw, ImageTk
    import pets as PT
    cw, ch = int(canvas.cget("width")), int(canvas.cget("height"))
    k = 0.5  # 게임 1px = 미리보기 0.5px
    try:
        a = app.game_assets()
    except Exception:  # noqa: BLE001
        a = None
    bg = None
    if a is not None:
        try:
            import gamescene as GS
            full = GS.background(a)
            fx, fy = GS.PLAYER
            box = (int(fx - cw / k / 2), int(fy - (ch - 30) / k), int(fx + cw / k / 2), int(fy + 30 / k))
            bg = full.crop(box).resize((cw, ch), Image.LANCZOS)
        except Exception:  # noqa: BLE001
            bg = None
    if bg is None:
        bg = Image.new("RGBA", (cw, ch), (28, 42, 34, 255))
    d = ImageDraw.Draw(bg)
    feet = (cw // 2, ch - 30)
    d.ellipse((feet[0] - 60, feet[1] - 8, feet[0] + 60, feet[1] + 8), fill=(0, 0, 0, 90))
    try:
        im = PT.process_image(image, scale, flip, lift) if image else PT.placeholder()
    except (OSError, ValueError):
        im = PT.placeholder()
    im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))), Image.LANCZOS)
    bg.alpha_composite(im, (int(feet[0] - im.width / 2), int(feet[1] - im.height)))
    d.text((6, 6), f"{label}  ({im.width * 2}×{im.height * 2}px)", fill=(230, 230, 230, 255))
    photo = ImageTk.PhotoImage(bg)
    canvas.delete("all")
    canvas.create_image(0, 0, anchor="nw", image=photo)
    return photo


def rename_gimmick_ref(project, kind, old, new):
    """태그/소환수 ID 가 바뀌거나(new) 지워질 때(None) 프로젝트 안의 참조를 고친다."""
    if kind == "tag":
        for c in project.get("cards", []):
            g = c.get("gtags") or []
            if old in g:
                c["gtags"] = [new if t == old else t for t in g if new or t != old]
        old_s, new_s = "tag:" + old, ("tag:" + new) if new else "Any"
    elif kind == "orb":
        old_s, new_s = "o:" + old, ("o:" + new) if new else "Lightning"
    elif kind == "pet":
        old_s, new_s = "\0pet:" + old, ""     # 동료는 'pet' 키로만 참조
    else:
        old_s, new_s = "s:" + old, ("s:" + new) if new else ""

    def fix(o):
        if isinstance(o, dict):
            for k, v in list(o.items()):
                if v == old_s:
                    o[k] = new_s
                elif kind == "summon" and k == "summon" and v == old:
                    o[k] = new or ""
                elif kind == "pet" and k in ("pet", "ref") and v == old:
                    o[k] = new or ""
                else:
                    fix(v)
        elif isinstance(o, list):
            for v in o:
                fix(v)
    for key in ("cards", "relics", "potions", "powers"):
        fix(project.get(key, []))
    fix(project.get("gimmicks", {}).get("summons", []))
    fix(project.get("gimmicks", {}).get("orbs", []))
    fix(project.get("gimmicks", {}).get("pets", []))
    fix(project.get("gimmicks", {}).get("buttons", []))


# ---------------------------------------------------------------------------
# 캐릭터 탭
# ---------------------------------------------------------------------------
class CharacterTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self._loading = False
        outer = ttk.PanedWindow(self, orient="horizontal")
        outer.pack(fill="both", expand=True)
        sf = ScrollFrame(outer)
        outer.add(sf, weight=1)
        pvf = ttk.Frame(outer, padding=6)
        outer.add(pvf, weight=0)
        top = ttk.Frame(pvf)
        top.pack(fill="x")
        ttk.Label(top, text="미리보기", font=("Malgun Gothic", 10, "bold")).pack(side="left")
        self.preview_lang = tk.StringVar(value=app.pv_lang.get())
        for val, lbl in (("ko", "한국어"), ("en", "English"), ("zh", "简体中文")):
            ttk.Radiobutton(top, text=lbl, value=val, variable=self.preview_lang,
                            command=app.refresh_previews).pack(side="left", padx=(8, 0))
        self.pv_canvas = tk.Canvas(pvf, width=int(310 * app.ui), height=int(570 * app.ui), background="#121318",
                                   highlightthickness=0)
        self.pv_canvas.pack(pady=(6, 0))
        f = ttk.Frame(sf.inner, padding=10)
        f.pack(fill="both", expand=True)
        f.columnconfigure(1, weight=1)
        f.columnconfigure(3, weight=1)
        self.v = {}

        self.enabled = tk.BooleanVar()
        ttk.Checkbutton(f, text="새 캐릭터 만들기  (끄면 카드는 무색, 유물/물약은 공용 풀에 추가됩니다)",
                        variable=self.enabled, command=self.changed).grid(row=0, column=0, columnspan=4, sticky="w", pady=(0, 8))

        def ent(row, col, label, key, width=24, parent=f):
            ttk.Label(parent, text=label).grid(row=row, column=col, sticky="w", padx=4, pady=2)
            var = tk.StringVar()
            ttk.Entry(parent, textvariable=var, width=width).grid(row=row, column=col + 1, sticky="we", padx=4, pady=2)
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var

        ent(1, 0, "캐릭터 ID (영문 소문자_)", "id")
        ent(1, 2, "시작 체력", "hp", 8)
        translations = ttk.Frame(f)
        translations.grid(row=2, column=0, columnspan=4, rowspan=2, sticky="we")
        translations.columnconfigure(1, weight=1)
        translations.columnconfigure(3, weight=2)
        for row, (lang, label) in enumerate((("ko", "한국어"), ("en", "영어"), ("zh", "중국어 간체"))):
            ent(row, 0, f"이름 ({label})", f"name_{lang}", parent=translations)
            ent(row, 2, f"소개 ({label})", f"desc_{lang}", parent=translations)

        ttk.Label(f, text="대표 색상").grid(row=4, column=0, sticky="w", padx=4, pady=2)
        cf = ttk.Frame(f)
        cf.grid(row=4, column=1, sticky="w", padx=4)
        self.v["color"] = tk.StringVar()
        ttk.Entry(cf, textvariable=self.v["color"], width=10).pack(side="left")
        self.swatch = tk.Label(cf, width=4, relief="groove")
        self.swatch.pack(side="left", padx=4)
        ttk.Button(cf, text="고르기…", command=self.pick_color).pack(side="left")
        self.v["color"].trace_add("write", lambda *_: self.changed())

        ttk.Label(f, text="임시 외형 (애니메이션)").grid(row=4, column=2, sticky="w", padx=4)
        self.placeholder = LabeledCombo(f, M.PLACEHOLDER_CHARS)
        self.placeholder.grid(row=4, column=3, sticky="w", padx=4)
        self.placeholder.bind("<<ComboboxSelected>>", lambda _e: self.changed())

        ttk.Label(f, text="카드 뒷면 HSV (0~1)").grid(row=5, column=0, sticky="w", padx=4, pady=2)
        hf = ttk.Frame(f)
        hf.grid(row=5, column=1, columnspan=3, sticky="w", padx=4)
        for k, l in (("card_h", "H"), ("card_s", "S"), ("card_v", "V")):
            ttk.Label(hf, text=l).pack(side="left")
            var = tk.StringVar()
            ttk.Spinbox(hf, from_=0, to=1, increment=0.05, textvariable=var, width=6).pack(side="left", padx=(2, 10))
            var.trace_add("write", lambda *_: self.changed())
            self.v[k] = var
        ttk.Label(hf, text="1/1/1이 기본.", foreground="#777").pack(side="left")
        ttk.Label(hf, text="     카드 테두리").pack(side="left")
        self.frame_combo = LabeledCombo(hf, CF.options({"card_frames": []}, for_card=False), width=18)
        self.frame_combo.pack(side="left", padx=4)
        self.frame_combo.bind("<<ComboboxSelected>>", lambda _e: self.changed())
        UX.tip(ttk.Button(hf, text="편집…", style="Small.TButton", command=self.edit_frames),
               "이 캐릭터의 모든 카드에 쓰는 기본 테두리 디자인. 카드 탭에서 카드마다 바꿀 수도 있습니다.").pack(side="left")

        # 시작 덱
        ttk.Separator(f).grid(row=6, column=0, columnspan=4, sticky="we", pady=8)
        ttk.Label(f, text="시작 덱", font=("Malgun Gothic", 10, "bold")).grid(row=7, column=0, sticky="nw", padx=4)
        df = ttk.Frame(f)
        df.grid(row=7, column=1, columnspan=3, sticky="we", padx=4)
        self.deck_tree = ttk.Treeview(df, columns=("card", "count"), show="headings", height=6, selectmode="browse")
        self.deck_tree.heading("card", text="카드")
        self.deck_tree.heading("count", text="장수")
        self.deck_tree.column("card", width=260)
        self.deck_tree.column("count", width=60, anchor="center")
        self.deck_tree.pack(side="left", fill="x", expand=True)
        db = ttk.Frame(df)
        db.pack(side="left", padx=6, anchor="n")
        self.deck_card = LabeledCombo(db, [], width=22)
        self.deck_card.pack(pady=1)
        self.deck_count = tk.StringVar(value="1")
        ttk.Spinbox(db, from_=1, to=20, textvariable=self.deck_count, width=6).pack(pady=1)
        ttk.Button(db, text="추가 / 장수 변경", command=self.deck_add).pack(fill="x", pady=1)
        ttk.Button(db, text="선택 삭제", command=self.deck_remove).pack(fill="x", pady=1)
        self.deck_total = ttk.Label(db, text="", foreground="#777")
        self.deck_total.pack(pady=4)

        ttk.Label(f, text="시작 유물", font=("Malgun Gothic", 10, "bold")).grid(row=8, column=0, sticky="nw", padx=4, pady=(8, 0))
        rf = ttk.Frame(f)
        rf.grid(row=8, column=1, columnspan=3, sticky="we", padx=4, pady=(8, 0))
        rf.columnconfigure(0, weight=1)
        self.start_relic_combo = LabeledCombo(rf, [], width=34)
        self.start_relic_combo.grid(row=0, column=0, sticky="we")
        ttk.Button(rf, text="유물 추가", command=self.add_start_relic).grid(row=0, column=1, padx=(6, 0))
        self.start_relic_list = tk.Listbox(rf, selectmode="extended", height=4, exportselection=False)
        self.start_relic_list.grid(row=1, column=0, sticky="we", pady=(4, 0))
        ttk.Button(rf, text="선택 삭제", command=self.remove_start_relic).grid(row=1, column=1, sticky="n", padx=(6, 0), pady=(4, 0))
        ttk.Label(rf, text="시작 시 지급할 유물을 고르세요. 여러 개를 추가할 수 있습니다. (희귀도 '시작' 권장)",
                  foreground="#777").grid(row=2, column=0, columnspan=2, sticky="w", pady=(3, 0))

        ttk.Separator(f).grid(row=9, column=0, columnspan=4, sticky="we", pady=8)
        ttk.Label(f, text="캐릭터 그림 (선택 사항, 비우면 임시 외형 캐릭터의 그림을 씀)", foreground="#777").grid(
            row=10, column=0, columnspan=4, sticky="w", padx=4)
        r = 11
        for key, label, hint in (("energy_icon_image", "카드 에너지 구슬", "74×74 (비우면 임시 외형 캐릭터 것)"),
                                 ("energy_text_icon_image", "설명용 에너지 아이콘", "24×24"),
                                 ("icon_image", "아이콘", "128×128"), ("select_image", "선택 화면 초상화", "132×195"),
                                 ("select_locked_image", "선택 화면 (잠김)", "132×195"),
                                 ("map_marker_image", "지도 표시", "128×128")):
            var = tk.StringVar()
            self.v[key] = var
            file_row(f, r, label, var, self.changed, hint=hint)
            r += 1
        cm = ttk.LabelFrame(f, text="직업 시스템 (디펙트·리젠트처럼)", padding=6)
        cm.grid(row=r, column=0, columnspan=4, sticky="we", padx=4, pady=(8, 2))
        ttk.Label(cm, text="구체 슬롯 수").grid(row=0, column=0, sticky="w")
        self.orb_slots = tk.StringVar(value="0")
        ttk.Spinbox(cm, from_=0, to=10, textvariable=self.orb_slots, width=5).grid(row=0, column=1, sticky="w", padx=4)
        self.orb_slots.trace_add("write", lambda *_: self.changed())
        ttk.Label(cm, text="0이면 구체 없음. 디펙트는 3. '🎲 기믹' 탭에서 새 구체를 만들고 블록 '구체 영창'으로 씁니다.",
                  foreground="#777").grid(row=0, column=2, sticky="w", padx=6)
        self.show_stars = tk.BooleanVar()
        ttk.Checkbutton(cm, text="별 카운터 항상 표시 (리젠트처럼 별을 쓰는 캐릭터)", variable=self.show_stars,
                        command=self.changed).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(cm, text="골골이(네크로바인더의 동료)는 설정 없이 블록 '골골이 소환 / 공격'으로 바로 쓸 수 있습니다.",
                  foreground="#777").grid(row=2, column=0, columnspan=3, sticky="w")
        r += 1
        vf = ttk.LabelFrame(f, text="전투 모습", padding=6)
        vf.grid(row=r, column=0, columnspan=4, sticky="we", padx=4, pady=(8, 2))
        vf.columnconfigure(1, weight=1)
        self.combat_img = tk.StringVar()
        self.v["combat_image"] = self.combat_img
        file_row(vf, 0, "전투 그림 (PNG)", self.combat_img, self.changed, hint="비우면 임시 외형 캐릭터의 애니메이션")
        tf = ttk.Frame(vf)
        tf.grid(row=1, column=1, columnspan=3, sticky="w", pady=2)
        self.combat_scale, self.combat_lift = tk.StringVar(value="100"), tk.StringVar(value="0")
        ttk.Label(tf, text="크기 %").pack(side="left")
        ttk.Spinbox(tf, from_=10, to=400, increment=5, textvariable=self.combat_scale, width=5).pack(side="left", padx=(2, 10))
        ttk.Label(tf, text="띄우기(px)").pack(side="left")
        ttk.Spinbox(tf, from_=-200, to=300, increment=5, textvariable=self.combat_lift, width=5).pack(side="left", padx=(2, 10))
        self.combat_flip = tk.BooleanVar()
        ttk.Checkbutton(tf, text="좌우 반전 (캐릭터는 오른쪽을 봐야 함)", variable=self.combat_flip, command=self.changed).pack(side="left")
        for var in (self.combat_scale, self.combat_lift):
            var.trace_add("write", lambda *_: self.changed())
        self.combat_canvas = tk.Canvas(vf, width=300, height=320, background="#1c2a22", highlightthickness=0)
        self.combat_canvas.grid(row=0, column=4, rowspan=3, padx=8)
        ttk.Label(vf, text="기본 전투 그림을 지정한 뒤 모션에 사용할 PNG를 재생 순서대로 추가하세요.",
                  foreground="#777").grid(row=2, column=0, columnspan=4, sticky="w")
        self.motion_lists = {}
        self.motion_times = {}
        self.motion_job = None
        for row, (key, title) in enumerate((("attack_frames", "공격 모션"), ("hit_frames", "피격 모션")), 3):
            box = ttk.LabelFrame(vf, text=title, padding=4)
            box.grid(row=row, column=0, columnspan=4, sticky="we", pady=2)
            listing = tk.Listbox(box, height=3, exportselection=False)
            listing.pack(side="left", fill="x", expand=True)
            self.motion_lists[key] = listing
            timing = tk.StringVar(value="120")
            self.motion_times[key] = timing
            ttk.Label(box, text="프레임당 ms").pack(side="left")
            spin = ttk.Spinbox(box, from_=16, to=5000, increment=10, width=5, textvariable=timing)
            spin.pack(side="left")
            timing.trace_add("write", lambda *_, k=key: self.motion_speed_changed(k))
            spin.bind("<FocusOut>", lambda _, k=key: self.motion_times[k].set(str(frame_ms(self.app.project["character"], k))))
            for action, label in (("add", "PNG 추가"), ("remove", "선택 제거"), ("play", "재생")):
                ttk.Button(box, text=label, command=lambda k=key, a=action: self.edit_motion(k, a)).pack(side="left", padx=2)
        self._combat_photo = None
        r += 1
        self.status = ttk.Label(f, text="", foreground="#a33")
        self.status.grid(row=r, column=0, columnspan=4, sticky="w", padx=4, pady=6)

    def pick_color(self):
        cur = self.v["color"].get()
        res = colorchooser.askcolor(color=cur if M.HEX_RE.match(cur) else "#ffffff", parent=self)
        if res and res[1]:
            self.v["color"].set(res[1])

    def load(self):
        ch = self.app.project["character"]
        self._loading = True
        try:
            self.enabled.set(ch["enabled"])
            for k, var in self.v.items():
                var.set(str(ch.get(k, "")))
            self.placeholder.set_value(ch.get("placeholder", "ironclad"))
            self.frame_combo.set_options(CF.options(self.app.project, for_card=False))
            self.frame_combo.set_value(ch.get("frame_style", ""))
            self.orb_slots.set(str(ch.get("orb_slots", 0)))
            self.show_stars.set(bool(ch.get("show_stars")))
            self.combat_scale.set(str(ch.get("combat_scale", 100)))
            self.combat_lift.set(str(ch.get("combat_lift", 0)))
            self.combat_flip.set(bool(ch.get("combat_flip")))
            for key, timing in self.motion_times.items():
                timing.set(str(frame_ms(ch, key)))
            self.refresh_refs()
        finally:
            self._loading = False
        self.update_swatch()
        self.update_preview()
        self.refresh_motion_lists()
        self.update_combat_preview()

    def motion_speed_changed(self, key):
        if self._loading:
            return
        value = self.motion_times[key].get()
        if value.isascii() and value.isdigit() and len(value) <= 4 and 16 <= int(value) <= 5000:
            character = self.app.project["character"]
            if frame_ms(character, key) != int(value):
                character[key + "_ms"] = int(value)
                self.app.mark_dirty()

    def refresh_motion_lists(self):
        for key, listing in self.motion_lists.items():
            listing.delete(0, "end")
            for i, frame in enumerate(self.app.project["character"].get(key, []), 1):
                listing.insert("end", f"{i}. {os.path.basename(frame['image'])}")

    def edit_motion(self, key, action):
        ch = self.app.project["character"]
        frames = ch.get(key, [])
        if action == "play":
            if frames:
                self.update_combat_preview()
                def show(index):
                    self.motion_job = None
                    if index == len(frames):
                        self.update_combat_preview()
                        return
                    self._combat_photo = pet_preview(self.combat_canvas, self.app, frames[index]["image"],
                        ch.get("combat_scale"), ch.get("combat_flip"), ch.get("combat_lift"), "")
                    self.motion_job = self.after(frame_ms(ch, key), show, index + 1)
                show(0)
            return
        if action == "add":
            paths = filedialog.askopenfilenames(parent=self, filetypes=[("PNG 이미지", "*.png")])
            if not paths:
                return
            ch[key] = frames + [{"image": path} for path in paths]
        else:
            selected = self.motion_lists[key].curselection()
            if not selected:
                return
            ch[key] = [frame for i, frame in enumerate(frames) if i not in selected]
        self.app.mark_dirty()
        self.refresh_motion_lists()
        self.update_combat_preview()

    def update_combat_preview(self):
        if self.motion_job is not None:
            self.after_cancel(self.motion_job)
            self.motion_job = None
        ch = self.app.project["character"]
        if ch.get("combat_image"):
            self._combat_photo = pet_preview(self.combat_canvas, self.app, ch.get("combat_image"), ch.get("combat_scale"),
                                             ch.get("combat_flip"), ch.get("combat_lift"), M.text(ch, "name", "ko"))
        else:
            self.combat_canvas.delete("all")
            self.combat_canvas.create_text(150, 160, text="(그림 없음 — 임시 외형\n캐릭터의 애니메이션)", fill="#9ab", justify="center")

    def update_preview(self):
        self.pv_canvas.delete("all")
        try:
            u = self.app.ui
            PV.render_character(self.pv_canvas, self.app.project, 5 * u, 5 * u, self.preview_lang.get(), u)
        except Exception as e:  # noqa: BLE001
            self.pv_canvas.create_text(150, 200, text=f"미리보기 오류:\n{e}", fill="#f66", width=280)

    def edit_frames(self):
        import cardframeui
        cardframeui.FrameStyleDialog(self.app, self.app.project["character"].get("frame_style") or None,
                                     on_close=self.app.frames_changed)

    def refresh_refs(self):
        ch = self.app.project["character"]
        cards = list(self.app.project["cards"])
        cards.extend({"id": "game:" + entry, "name_ko": label + " · 원작"} for entry, label in ch.get("game_cards", {}).items())
        self.deck_card.set_options([(c["id"], f"{c.get('name_ko') or c['id']} ({c['id']})") for c in cards])
        names = {c["id"]: c.get("name_ko") or c["id"] for c in cards}
        self.deck_tree.delete(*self.deck_tree.get_children())
        total = 0
        for i, d in enumerate(ch["deck"]):
            self.deck_tree.insert("", "end", iid=str(i), values=(f"{names.get(d['card'], '⚠ 없음')} ({d['card']})", d["count"]))
            total += int(d["count"])
        self.deck_total.configure(text=f"총 {total}장")
        relics = self.app.project["relics"]
        self.start_relic_combo.set_options([
            (r["id"], f"{r.get('name_ko') or r['id']} ({r['id']}) - {M.label_of(M.RELIC_RARITIES, r['rarity'])}")
            for r in relics
        ])
        self.refresh_start_relics()

    def refresh_start_relics(self):
        self.start_relic_list.delete(0, "end")
        relics = {r["id"]: r for r in self.app.project["relics"]}
        for relic_id in self.app.project["character"].get("relics", []):
            relic = relics.get(relic_id)
            if relic is None:
                label = f"⚠ 없음 ({relic_id})"
            else:
                label = f"{relic.get('name_ko') or relic_id} ({relic_id})"
            self.start_relic_list.insert("end", label)

    def add_start_relic(self):
        relic_id = self.start_relic_combo.get_value()
        if not relic_id:
            return
        relic_ids = self.app.project["character"].setdefault("relics", [])
        if relic_id in relic_ids:
            index = relic_ids.index(relic_id)
            self.start_relic_list.selection_clear(0, "end")
            self.start_relic_list.selection_set(index)
            self.start_relic_list.see(index)
            return
        relic_ids.append(relic_id)
        self.app.mark_dirty()
        self.refresh_start_relics()
        index = len(relic_ids) - 1
        self.start_relic_list.selection_set(index)
        self.start_relic_list.see(index)

    def remove_start_relic(self):
        selected = set(self.start_relic_list.curselection())
        if not selected:
            return
        character = self.app.project["character"]
        character["relics"] = [
            relic_id for index, relic_id in enumerate(character.get("relics", []))
            if index not in selected
        ]
        self.app.mark_dirty()
        self.refresh_start_relics()

    def deck_add(self):
        cid = self.deck_card.get_value()
        if not cid:
            return
        try:
            n = max(1, int(self.deck_count.get()))
        except ValueError:
            n = 1
        deck = self.app.project["character"]["deck"]
        for d in deck:
            if d["card"] == cid:
                d["count"] = n
                break
        else:
            deck.append({"card": cid, "count": n})
        self.app.mark_dirty()
        self.refresh_refs()

    def deck_remove(self):
        s = self.deck_tree.selection()
        if not s:
            return
        del self.app.project["character"]["deck"][int(s[0])]
        self.app.mark_dirty()
        self.refresh_refs()

    def update_swatch(self):
        c = self.v["color"].get()
        try:
            self.swatch.configure(background=c if M.HEX_RE.match(c) and c.startswith("#") else "#" + c.lstrip("#"))
        except tk.TclError:
            pass

    def changed(self):
        if self._loading:
            return
        ch = self.app.project["character"]
        ch["enabled"] = self.enabled.get()
        for k, var in self.v.items():
            val = var.get().strip()
            if k == "hp":
                try:
                    ch[k] = int(val)
                except ValueError:
                    pass
            elif k.startswith("card_"):
                try:
                    ch[k] = float(val)
                except ValueError:
                    pass
            else:
                ch[k] = val.strip('"') if k.endswith("_image") else val
        ch["placeholder"] = self.placeholder.get_value()
        ch["frame_style"] = self.frame_combo.get_value()
        try:
            ch["orb_slots"] = max(0, int(self.orb_slots.get()))
        except ValueError:
            pass
        ch["show_stars"] = bool(self.show_stars.get())
        for k_, var in (("combat_scale", self.combat_scale), ("combat_lift", self.combat_lift)):
            try:
                ch[k_] = int(float(var.get()))
            except ValueError:
                pass
        ch["combat_flip"] = bool(self.combat_flip.get())
        self.update_combat_preview()
        self.update_swatch()
        self.update_preview()
        self.app.mark_dirty()


# ---------------------------------------------------------------------------
# 모드 정보 / 빌드 탭
# ---------------------------------------------------------------------------
class ModTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master, padding=10)
        self.app = app
        self._loading = False
        self.v = {}
        info = ttk.LabelFrame(self, text="모드 정보", padding=8)
        info.pack(fill="x")
        info.columnconfigure(1, weight=1)
        info.columnconfigure(3, weight=1)
        fields = [("id", "모드 ID (영문, 대문자 시작)", 0, 0), ("name", "표시 이름", 0, 2),
                  ("author", "제작자", 1, 0), ("version", "버전", 1, 2),
                  ("description", "설명", 2, 0), ("min_game_version", "최소 게임 버전", 3, 0),
                  ("baselib_version", "BaseLib 버전 (* = 최신)", 3, 2)]
        for key, label, r, c in fields:
            ttk.Label(info, text=label).grid(row=r, column=c, sticky="w", padx=4, pady=3)
            var = tk.StringVar()
            span = 3 if key == "description" else 1
            ttk.Entry(info, textvariable=var).grid(row=r, column=c + 1, columnspan=span, sticky="we", padx=4, pady=3)
            var.trace_add("write", lambda *_: self.changed())
            self.v[key] = var

        env = ttk.LabelFrame(self, text="환경 설정 (이 PC에 저장)", padding=8)
        env.pack(fill="x", pady=8)
        env.columnconfigure(1, weight=1)
        self.s = {}
        for r, (key, label, mode) in enumerate((("out_dir", "출력 폴더", "dir"),
                                                ("sts2_path", "슬더스2 설치 폴더", "dir"),
                                                ("godot_path", "MegaDot 4.5.1 실행 파일 (pck용)", "file"))):
            ttk.Label(env, text=label).grid(row=r, column=0, sticky="w", padx=4, pady=3)
            var = tk.StringVar(value=app.settings.get(key, ""))
            ttk.Entry(env, textvariable=var).grid(row=r, column=1, sticky="we", padx=4, pady=3)

            def browse(var=var, mode=mode):
                p = filedialog.askdirectory() if mode == "dir" else filedialog.askopenfilename(
                    filetypes=[("실행 파일", "*.exe"), ("모든 파일", "*.*")])
                if p:
                    var.set(os.path.normpath(p))

            ttk.Button(env, text="찾기…", command=browse).grid(row=r, column=2, padx=2)
            var.trace_add("write", lambda *_a, k=key, vv=var: self.setting_changed(k, vv))
            self.s[key] = var
        ttk.Button(env, text="자동 찾기", command=self.autodetect).grid(row=1, column=3, padx=2)
        ttk.Button(env, text="MegaDot 받기", command=lambda: webbrowser.open(MEGADOT_URL)).grid(row=2, column=3, padx=2)

        chk = ttk.LabelFrame(self, text="상태 점검", padding=8)
        chk.pack(fill="x")
        self.check_lbl = ttk.Label(chk, text="", justify="left", font=("Malgun Gothic", 9))
        self.check_lbl.pack(side="left", anchor="w")
        cb = ttk.Frame(chk)
        cb.pack(side="right")
        ttk.Button(cb, text="다시 점검", command=self.run_checks).pack(fill="x", pady=1)
        ttk.Button(cb, text="BaseLib 받기", command=lambda: webbrowser.open(BASELIB_URL)).pack(fill="x", pady=1)

        act = ttk.LabelFrame(self, text="만드는 순서 (위쪽 도구 막대의 버튼)", padding=8)
        act.pack(fill="x", pady=8)
        steps = [("① 검사", "입력 내용에 문제가 없는지 확인"),
                 ("② 생성", "출력 폴더에 C# / Godot 모드 프로젝트 파일 쓰기"),
                 ("③ 빌드", "dotnet build → 게임 mods 폴더에 dll 복사 (코드만)"),
                 ("④ 게시", "③ + MegaDot로 그림/텍스트가 든 .pck 생성 (게임에서 쓰려면 필요)")]
        for i, (t, desc) in enumerate(steps):
            ttk.Label(act, text=t, width=8).grid(row=i, column=0, sticky="w", pady=1)
            ttk.Label(act, text=desc, foreground="#555").grid(row=i, column=1, sticky="w", padx=8)
        of = ttk.Frame(act)
        of.grid(row=0, column=2, rowspan=4, sticky="ne", padx=20)
        ttk.Button(of, text="프로젝트 폴더 열기", command=self.app.open_project_dir).pack(fill="x", pady=1)
        ttk.Button(of, text="게임 mods 폴더 열기", command=self.app.open_mods_dir).pack(fill="x", pady=1)
        ttk.Button(of, text="VS Code로 열기", command=self.app.open_vscode).pack(fill="x", pady=1)
        act.columnconfigure(1, weight=1)

    def autodetect(self):
        p = detect_sts2_path()
        if p:
            self.s["sts2_path"].set(p)
        else:
            messagebox.showinfo(APP_TITLE, "슬더스2 설치 폴더를 찾지 못했습니다. 직접 지정하세요.")

    def setting_changed(self, key, var):
        self.app.settings[key] = var.get().strip().strip('"')
        save_settings(self.app.settings)

    def load(self):
        self._loading = True
        try:
            for k, var in self.v.items():
                var.set(self.app.project["mod"].get(k, ""))
        finally:
            self._loading = False

    def changed(self):
        if self._loading:
            return
        for k, var in self.v.items():
            self.app.project["mod"][k] = var.get().strip()
        self.app.mark_dirty()

    def run_checks(self):
        s = self.app.settings
        lines = []
        dotnet = shutil.which("dotnet")
        lines.append(("✔" if dotnet else "✘") + " .NET SDK (dotnet) " + ("설치됨" if dotnet else "없음 → https://dotnet.microsoft.com 에서 .NET SDK 9 이상 설치"))
        sp = s.get("sts2_path", "")
        dll = os.path.join(sp, "data_sts2_windows_x86_64", "sts2.dll") if sp else ""
        ok = bool(dll) and os.path.isfile(dll)
        ver = ""
        try:
            with open(os.path.join(sp, "release_info.json"), encoding="utf-8") as f:
                ver = json.load(f).get("version", "")
        except (OSError, ValueError):
            pass
        lines.append(("✔" if ok else "✘") + f" 슬더스2 {ver} " + ("찾음" if ok else "못 찾음 → 설치 폴더를 지정하세요"))
        mods = os.path.join(sp, "mods") if sp else ""
        bl = bool(mods) and os.path.isdir(mods) and any(n.lower().startswith("baselib") for n in os.listdir(mods))
        lines.append(("✔" if bl else "⚠") + " BaseLib 모드 " + ("설치됨" if bl else "mods 폴더에 없음 → 'BaseLib 받기'로 설치해야 게임에서 모드가 켜집니다"))
        g = s.get("godot_path", "")
        gok = bool(g) and os.path.isfile(g)
        lines.append(("✔" if gok else "⚠") + " MegaDot " + ("찾음" if gok else "미설정 → ④ 게시(pck)에 필요합니다 (③ 빌드는 없어도 됨)"))
        self.check_lbl.configure(text="\n".join(lines))


# ---------------------------------------------------------------------------
# 메인 앱
# ---------------------------------------------------------------------------
UI_SCALES = [0.7, 0.8, 0.9, 1.0, 1.1, 1.25, 1.4, 1.6]
_BASE_SCALING = None   # 처음 창의 tk scaling (화면 DPI)


class App(tk.Tk):
    def __init__(self, state=None):
        super().__init__()
        # 화면 배율 (보기 메뉴 · Ctrl+휠): 글자·위젯을 만들기 전에 tk scaling 에 곱한다
        try:
            scale = float(load_settings().get("ui_scale", 1.0) or 1.0)
        except (TypeError, ValueError):
            scale = 1.0
        self.ui_scale = min(max(scale, UI_SCALES[0]), UI_SCALES[-1])
        # 기준 배율은 프로그램이 처음 뜰 때 한 번만 잰다 (Tk 는 같은 프로그램 안의 이전 창 배율을 물려받는다)
        global _BASE_SCALING
        if _BASE_SCALING is None:
            _BASE_SCALING = float(self.tk.call("tk", "scaling"))
        self.tk.call("tk", "scaling", _BASE_SCALING * self.ui_scale)
        self.ui = max(min(1.0, self.ui_scale), self.winfo_fpixels("1i") / 96)  # 고해상도 화면 배율
        if "--selftest" in sys.argv:
            self.attributes("-alpha", 0.0)   # 점검 중에는 화면에 보이지 않게
        self.title(APP_TITLE)
        ico = os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__))), "app.ico")
        if sys.platform == "win32" and os.path.isfile(ico):
            try:
                self.iconbitmap(default=ico)   # 모든 창에 같은 아이콘
            except tk.TclError:
                pass
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        self.geometry(f"{min(1640, sw - 60)}x{min(980, sh - 90)}")
        center_window(self)  # 메인 창은 화면 가운데
        self.minsize(760, 480)   # 작아지면 탭마다 스크롤바가 생긴다
        UX.apply_theme(self)

        self.settings = load_settings()
        self.history = UX.History()
        self._saved_state = ""
        self._snap_job = None
        self._restoring = False
        self.project = M.default_project()
        self.project_path = ""
        self.dirty = False
        self.log_q = queue.Queue()
        self.busy = False
        self.pv_lang = tk.StringVar(value="ko")
        self.pv_upgraded = tk.BooleanVar(value=False)
        self.pv_stacks = tk.StringVar(value="3")
        self.pv_mode = tk.StringVar(value="game" if ingame else "simple")
        self._gcache = {}
        self._tcache = {}

        self.build_menu()
        UX.install_wheel(self, on_zoom=self.zoom_step)
        tb = ttk.Frame(self, padding=(10, 6), style="Toolbar.TFrame")
        tb.pack(fill="x")
        self._tb, self._tb_short, self._tb_full_w = tb, False, None
        self._tb_texts, self._tb_hide = [], []   # 창이 좁을 때: (위젯, 원래 글자, 짧은 글자) / 숨길 위젯
        # 오른쪽(찾기·상태)을 먼저 넣어야 좁아져도 잘리지 않는다
        self.status_lbl = ttk.Label(tb, text="", style="Toolbar.TLabel")
        self.status_lbl.pack(side="right", padx=(10, 0))
        self.top_search = UX.SearchEntry(tb, "전체에서 찾기  Ctrl+P", None, width=24,
                                         on_enter=lambda: self.open_find(self.top_search.get()))
        self.top_search.pack(side="right")
        b = UX.tip(ttk.Button(tb, text="💾 저장", style="Toolbar.TButton", command=self.save), "저장 (Ctrl+S)")
        b.pack(side="left")
        self._tb_texts.append((b, "💾 저장", "💾"))
        self.undo_btn = UX.tip(ttk.Button(tb, text="↶ 되돌리기", style="Toolbar.TButton", command=self.undo),
                               lambda: "되돌리기 (Ctrl+Z)" + (f"\n{self._loc_text(self.history.undos[-1][1])}의 바뀐 것을 되돌립니다"
                                                            if self.history.can_undo() else ""))
        self.undo_btn.pack(side="left")
        self._tb_texts.append((self.undo_btn, "↶ 되돌리기", "↶"))
        self.redo_btn = UX.tip(ttk.Button(tb, text="↷ 다시", style="Toolbar.TButton", command=self.redo),
                               "다시 실행 (Ctrl+Y)")
        self.redo_btn.pack(side="left")
        self._tb_texts.append((self.redo_btn, "↷ 다시", "↷"))
        ttk.Separator(tb, orient="vertical", style="Toolbar.TSeparator").pack(side="left", fill="y", padx=10, pady=2)
        steps = (("① 검사", self.do_validate, "만든 것에 빠진 칸이나 잘못된 값이 없는지 확인합니다."),
                 ("② 생성", self.do_generate, "C# 프로젝트 파일을 만듭니다."),
                 ("③ 빌드 (dll)", lambda: self.do_build(False), "dll 을 만들어 게임 mods 폴더에 넣습니다."),
                 ("④ 게시 (dll+pck)", lambda: self.do_build(True), "그림까지 담은 pck 와 dll 을 만들어 넣습니다."))
        for i, (t, cmd, h) in enumerate(steps):
            if i:
                arrow = ttk.Label(tb, text="›", style="Toolbar.TLabel")
                arrow.pack(side="left", padx=1)
                self._tb_hide.append(arrow)
            b = UX.tip(ttk.Button(tb, text=t, style="Step.TButton", command=cmd), h)
            b.pack(side="left", padx=2)
            self._tb_texts.append((b, t, t.split(" (")[0]))
        ttk.Separator(tb, orient="vertical", style="Toolbar.TSeparator").pack(side="left", fill="y", padx=10, pady=2)
        b = UX.tip(ttk.Button(tb, text="🤖 AI로 만들기", style="Toolbar.TButton", command=self.open_ai_guide),
                   "ChatGPT·Claude 같은 채팅 AI에게 카드·유물·물약·파워를 만들게 합니다.\n"
                   "설명서를 복사해 AI에게 보내고, AI 의 답을 붙여 넣으면 검사·미리보기 후 들어갑니다.")
        b.pack(side="left")
        self._tb_texts.append((b, "🤖 AI로 만들기", "🤖 AI"))
        b = UX.tip(ttk.Button(tb, text="AI 결과 붙여넣기", style="Toolbar.TButton", command=self.open_ai_paste),
                   "AI 가 준 답(JSON)을 붙여 넣어 검사하고 프로젝트에 넣습니다. (AI 메뉴에도 있음)")
        b.pack(side="left")
        self._tb_hide.append(b)
        tb.bind("<Configure>", self._fit_toolbar, add="+")
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        main = ttk.PanedWindow(self, orient="vertical")
        main.pack(fill="both", expand=True)
        # 탭마다 자동 스크롤바: 창이 작으면 아래·오른쪽 스크롤바로 전부 볼 수 있다
        self.nb = UX.ScrollNotebook(main)
        main.add(self.nb, weight=5)
        import fxui
        add = self.nb.add_scrolled
        self.mod_tab = add(lambda m: ModTab(m, self), "모드 / 빌드")
        self.char_tab = add(lambda m: CharacterTab(m, self), "캐릭터")
        self.card_tab = add(lambda m: CardTab(m, self), "카드")
        self.relic_tab = add(lambda m: RelicTab(m, self), "유물")
        self.potion_tab = add(lambda m: PotionTab(m, self), "물약")
        self.power_tab = add(lambda m: PowerTab(m, self), "★ 파워")
        self.gimmick_tab = add(lambda m: GimmickTab(m, self), "🎲 기믹")
        self.fx_tab = add(lambda m: fxui.FxTab(m, self), "🎨 이펙트·버튼")
        self.gallery_tab = add(lambda m: GalleryTab(m, self), "📖 도감")
        self.ext_tab = add(lambda m: ExternalTab(m, self), "📦 다른 모드")
        # 창이 좁으면 탭 이름을 줄인다 (탭 줄은 스크롤이 안 되므로)
        self._tab_names = [("모드 / 빌드", "빌드"), ("캐릭터", "캐릭터"), ("카드", "카드"), ("유물", "유물"), ("물약", "물약"),
                           ("★ 파워", "파워"), ("🎲 기믹", "기믹"), ("🎨 이펙트·버튼", "이펙트"), ("📖 도감", "도감"),
                           ("📦 다른 모드", "다른모드")]
        self._tab_short = False
        self._tab_full_w = None
        self.nb.bind("<Configure>", self._fit_tabs, add="+")
        self.nb.bind("<<NotebookTabChanged>>", lambda _e: self.on_tab())

        logf = ttk.Frame(main)
        main.add(logf, weight=1)
        self.log_text = tk.Text(logf, height=5, wrap="word", background=UX.C["console"], foreground=UX.C["console_fg"],
                                font=("Consolas", 10), state="disabled", padx=8, pady=4, highlightthickness=0,
                                insertbackground=UX.C["console_fg"])
        sb = ttk.Scrollbar(logf, command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=sb.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(100, self.pump_log)
        last = self.settings.get("last_project")
        if state:   # 화면 배율을 바꿔 창을 다시 만든 경우: 하던 작업 그대로
            self.project, self.project_path, self.dirty = state["project"], state["path"], state["dirty"]
            self.load_all()
            self.history, self._saved_state = state["history"], state["saved"]
            self._update_undo_ui()
            self.update_title()
            try:
                self.nb.select(state["tab"])
                if state.get("geometry"):
                    self.geometry(state["geometry"])
            except tk.TclError:
                pass
        elif last and os.path.isfile(last):
            self.open_project(last, quiet=True)
        else:
            self.load_all()
            self.reset_history()
        self.mod_tab.run_checks()
        self.log("슬더스2 모드 메이커를 시작했습니다. 카드/유물/물약/캐릭터를 만든 뒤 '모드 / 빌드' 탭에서 ②→③→④ 순서로 진행하세요.")

    # ---- 메뉴 / 파일 ----
    def open_card_library(self):
        from card_library import CardLibrary
        library = getattr(self, "_card_library", None)
        if library is None or not library.winfo_exists():
            self._card_library = CardLibrary(self, _resolve_project_image_paths, ingame)
        else:
            library.deiconify()
            library.lift()

    def build_menu(self):
        mb = tk.Menu(self)
        fm = tk.Menu(mb, tearoff=0)
        fm.add_command(label="새 프로젝트", command=self.new_project, accelerator="Ctrl+N")
        fm.add_command(label="열기…", command=self.open_dialog, accelerator="Ctrl+O")
        fm.add_command(label="저장", command=self.save, accelerator="Ctrl+S")
        fm.add_command(label="다른 이름으로 저장…", command=self.save_as)
        fm.add_command(label="캐릭터 카드 라이브러리…", command=self.open_card_library)
        fm.add_command(label="프로젝트 자산 모으기…", command=self.pack_project_assets)
        fm.add_separator()
        fm.add_command(label="다른 모드 불러오기 (dll/pck/소스)…", command=self.open_external)
        fm.add_command(label="다른 프로젝트 합치기…", command=self.merge_dialog)
        fm.add_command(label="예시 기믹 추가 (해적·마법사 스타일)…", command=lambda: self.gimmick_tab.add_examples())
        fm.add_separator()
        fm.add_command(label="종료", command=self.on_close)
        mb.add_cascade(label="파일", menu=fm)
        em = tk.Menu(mb, tearoff=0)
        em.add_command(label="되돌리기", command=self.undo, accelerator="Ctrl+Z")
        em.add_command(label="다시 실행", command=self.redo, accelerator="Ctrl+Y")
        em.add_separator()
        em.add_command(label="목록에서 찾기", command=self.focus_list_search, accelerator="Ctrl+F")
        em.add_command(label="전체에서 찾기…", command=self.open_find, accelerator="Ctrl+P")
        mb.add_cascade(label="편집", menu=em)
        self.edit_menu = em
        am = tk.Menu(mb, tearoff=0)
        am.add_command(label="① AI에게 시키기 (설명서 복사)…", command=self.open_ai_guide)
        am.add_command(label="② AI 결과 붙여넣기…", command=self.open_ai_paste)
        mb.add_cascade(label="AI", menu=am)
        vm = tk.Menu(mb, tearoff=0)
        self.scale_var = tk.IntVar(value=round(self.ui_scale * 100))
        for v in UI_SCALES:
            vm.add_radiobutton(label=f"화면 배율 {round(v * 100)}%", value=round(v * 100), variable=self.scale_var,
                               command=lambda v=v: self.set_scale(v))
        vm.add_separator()
        vm.add_command(label="크게", command=lambda: self.zoom_step(1), accelerator="Ctrl+=  /  Ctrl+휠↑")
        vm.add_command(label="작게", command=lambda: self.zoom_step(-1), accelerator="Ctrl+-  /  Ctrl+휠↓")
        vm.add_command(label="기본 크기 (100%)", command=lambda: self.set_scale(1.0), accelerator="Ctrl+0")
        mb.add_cascade(label="보기", menu=vm)
        for seq, fn in (("<Control-equal>", lambda _e: self.zoom_step(1)), ("<Control-plus>", lambda _e: self.zoom_step(1)),
                        ("<Control-minus>", lambda _e: self.zoom_step(-1)), ("<Control-0>", lambda _e: self.set_scale(1.0))):
            self.bind_all(seq, fn)
        hm = tk.Menu(mb, tearoff=0)
        hm.add_command(label="사용 방법", command=self.show_help)
        hm.add_command(label="BaseLib (GitHub)", command=lambda: webbrowser.open(BASELIB_URL))
        hm.add_command(label="StS2 모딩 튜토리얼", command=lambda: webbrowser.open("https://tutorials.sts2modding.com/en/"))
        mb.add_cascade(label="도움말", menu=hm)
        self.config(menu=mb)
        self.bind_all("<Control-s>", lambda _e: self.save())
        self.bind_all("<Control-o>", lambda _e: self.open_dialog())
        self.bind_all("<Control-n>", lambda _e: self.new_project())
        for seq, fn in (("<Control-z>", self._key_undo), ("<Control-Z>", self._key_redo), ("<Control-y>", self._key_redo),
                        ("<Control-f>", self._key_find), ("<Control-p>", self._key_palette)):
            self.bind_all(seq, fn)

    def update_title(self):
        name = os.path.basename(self.project_path) if self.project_path else "새 프로젝트"
        self.title(f"{'*' if self.dirty else ''}{name} - {APP_TITLE}")

    def mark_dirty(self):
        if not self.dirty:
            self.dirty = True
            self.update_title()
        if not self._restoring:
            # 입력이 잠깐 멈추면 한 단계로 기록 (글자 하나하나가 아니라 낱말·칸 단위로 되돌리기)
            if self._snap_job:
                self.after_cancel(self._snap_job)
            self._snap_job = self.after(500, self.commit_snapshot)

    # ---- 되돌리기 ----
    def _location(self):
        """지금 보고 있는 곳 (탭, 항목 번호, 하위 탭)."""
        sel = self.nb.select()
        loc = {"tab": sel}
        for t in (self.card_tab, self.relic_tab, self.potion_tab, self.power_tab):
            if sel == str(t):
                loc["item"] = t.cur
        if sel == str(self.fx_tab):
            loc["sub"] = self.fx_tab.nb.select()
        return loc

    def _loc_text(self, loc):
        try:
            name = self.nb.tab(loc["tab"], "text").strip()
        except (tk.TclError, KeyError):
            return "이전"
        return f"'{name}' 탭"

    def commit_snapshot(self):
        self._snap_job = None
        try:
            state = UX.snapshot(self.project)
        except (TypeError, ValueError):
            return
        self.history.push(state, self._location())
        self._update_undo_ui()

    def reset_history(self):
        if self._snap_job:
            self.after_cancel(self._snap_job)
            self._snap_job = None
        try:
            state = UX.snapshot(self.project)
        except (TypeError, ValueError):
            state = ""
        self.history.reset(state)
        self._saved_state = state
        self._update_undo_ui()

    def _update_undo_ui(self):
        if not hasattr(self, "undo_btn"):
            return
        self.undo_btn.configure(state="normal" if self.history.can_undo() else "disabled")
        self.redo_btn.configure(state="normal" if self.history.can_redo() else "disabled")
        try:
            self.edit_menu.entryconfigure(0, state="normal" if self.history.can_undo() else "disabled")
            self.edit_menu.entryconfigure(1, state="normal" if self.history.can_redo() else "disabled")
        except (tk.TclError, AttributeError):
            pass

    def undo(self):
        if self._snap_job:          # 아직 기록 안 된 입력부터 기록
            self.after_cancel(self._snap_job)
            self.commit_snapshot()
        if not self.history.can_undo():
            self.status("더 되돌릴 것이 없습니다")
            return
        state, loc = self.history.undo()
        self._restore(state, loc, "되돌렸습니다")

    def redo(self):
        if self._snap_job:
            self.after_cancel(self._snap_job)
            self.commit_snapshot()
        if not self.history.can_redo():
            self.status("다시 실행할 것이 없습니다")
            return
        state, loc = self.history.redo()
        self._restore(state, loc, "다시 실행했습니다")

    def _restore(self, state, loc, msg):
        self._restoring = True
        try:
            self.project = json.loads(state)
            self.dirty = state != self._saved_state
            # 바뀐 곳으로 가서 다시 읽는다
            item_tabs = (self.card_tab, self.relic_tab, self.potion_tab, self.power_tab)
            for t in item_tabs:
                if loc.get("tab") == str(t) and loc.get("item") is not None:
                    t.cur = loc["item"]
            if loc.get("sub") and loc.get("tab") == str(self.fx_tab):
                try:
                    self.fx_tab.nb.select(loc["sub"])
                except tk.TclError:
                    pass
            self.mod_tab.load()
            self.char_tab.load()
            self.gimmick_tab.load()
            self.fx_tab.load()
            for t in item_tabs:
                t.refresh_list(t.cur)
            try:
                self.nb.select(loc.get("tab"))
            except tk.TclError:
                pass
            self.update_title()
            self.refresh_previews()
        finally:
            self._restoring = False
            if self._snap_job:      # 다시 읽는 중에 생긴 기록 예약은 버린다
                self.after_cancel(self._snap_job)
                self._snap_job = None
        self._update_undo_ui()
        self.status(f"{msg} ({self._loc_text(loc)})")

    def status(self, text, ms=3000):
        self.status_lbl.configure(text=text)
        job = getattr(self, "_status_job", None)
        if job:
            self.after_cancel(job)
        self._status_job = self.after(ms, lambda: self.status_lbl.configure(text=""))

    def _main_focus(self, e):
        """단축키가 메인 창에서 눌렸는지 (대화 상자는 자기 단축키를 쓴다)."""
        try:
            return e.widget.winfo_toplevel() is self
        except (AttributeError, tk.TclError, KeyError):
            return False

    def _key_undo(self, e):
        if not self._main_focus(e) or isinstance(e.widget, tk.Text):
            return None          # 글 상자는 자기 되돌리기를 쓴다
        painter = self.fx_tab.painter
        if self.nb.select() == str(self.fx_tab) and self.fx_tab.nb.select() == str(painter) and painter.history:
            painter._undo_key(e)   # 이펙트 그리기는 획 단위로 되돌린다
            return "break"
        self.undo()
        return "break"

    def _key_redo(self, e):
        if not self._main_focus(e) or isinstance(e.widget, tk.Text):
            return None
        self.redo()
        return "break"

    def focus_list_search(self):
        for t in (self.card_tab, self.relic_tab, self.potion_tab, self.power_tab):
            if self.nb.select() == str(t):
                t.search.focus()
                return
        self.open_find()

    def _key_find(self, e):
        if not self._main_focus(e):
            return None
        self.focus_list_search()
        return "break"

    def _fit_toolbar(self, _e=None):
        """창이 좁으면 도구 막대 글자를 줄이고 덜 중요한 버튼을 숨긴다."""
        tb = self._tb
        if self._tb_full_w is None:
            self._tb_full_w = tb.winfo_reqwidth()
        short = tb.winfo_width() < self._tb_full_w
        if short == self._tb_short:
            return
        self._tb_short = short
        for w, full, sh in self._tb_texts:
            w.configure(text=sh if short else full)
        for w in self._tb_hide:
            if short:
                w.pack_forget()
        if not short:   # 원래 순서대로 다시 넣는다
            for w, *_ in self._tb_texts:
                w.pack_forget()
            for w in self._tb_hide:
                w.pack_forget()
            order = [x[0] for x in self._tb_texts]
            arrows = [w for w in self._tb_hide if isinstance(w, ttk.Label)]
            paste = [w for w in self._tb_hide if not isinstance(w, ttk.Label)]
            seps = [w for w in tb.pack_slaves() if isinstance(w, ttk.Separator)]
            for w in seps:
                w.pack_forget()
            seq = order[:3] + [seps[0]] + [order[3], arrows[0], order[4], arrows[1], order[5], arrows[2], order[6]] + \
                [seps[1], order[7]] + paste
            for w in seq:
                pad = {"padx": 10, "pady": 2, "fill": "y"} if isinstance(w, ttk.Separator) else \
                    {"padx": 1} if isinstance(w, ttk.Label) else {"padx": 2} if w in order[3:7] else {}
                w.pack(side="left", **pad)
        self.top_search.entry.configure(width=12 if short else 24)

    def _fit_tabs(self, _e=None):
        if self._tab_full_w is None:
            self._tab_full_w = self.nb.winfo_reqwidth()
        short = self.nb.winfo_width() < self._tab_full_w
        if short != self._tab_short:
            self._tab_short = short
            for i, (full, sh) in enumerate(self._tab_names):
                self.nb.tab(i, text=sh if short else full)

    # ---- 화면 배율 ----
    def zoom_step(self, d):
        """Ctrl+휠·단축키: 한 단계 크게/작게 (잠깐 멈추면 적용)."""
        cur = getattr(self, "_pending_scale", None) or self.ui_scale
        i = min(range(len(UI_SCALES)), key=lambda k: abs(UI_SCALES[k] - cur))
        nxt = UI_SCALES[max(0, min(len(UI_SCALES) - 1, i + d))]
        self._pending_scale = nxt
        self.status(f"화면 배율 {round(nxt * 100)}% …", 1500)
        job = getattr(self, "_scale_job", None)
        if job:
            self.after_cancel(job)
        self._scale_job = self.after(450, lambda: self.set_scale(self._pending_scale))
        return "break"

    def set_scale(self, v):
        self._pending_scale = None
        self._scale_job = None
        v = min(max(float(v), UI_SCALES[0]), UI_SCALES[-1])
        if abs(v - self.ui_scale) < 0.001:
            self.scale_var.set(round(v * 100))
            return
        self.settings["ui_scale"] = v
        save_settings(self.settings)
        if self._snap_job:
            self.after_cancel(self._snap_job)
            self.commit_snapshot()
        self._restart_state = {"project": self.project, "path": self.project_path, "dirty": self.dirty,
                               "history": self.history, "saved": self._saved_state,
                               "tab": self.nb.index(self.nb.select()), "geometry": self.geometry()}
        for job in self.tk.splitlist(self.tk.call("after", "info")):   # 이전 창의 예약 작업 정리
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self.destroy()

    def open_ai_guide(self):
        import aiui
        aiui.AIGuideDialog(self)

    def open_ai_paste(self):
        import aiui
        aiui.AIPasteDialog(self)

    def open_find(self, query=""):
        UX.FindPalette(self, query or "")
        if hasattr(self, "top_search"):
            self.top_search.set("")

    def _key_palette(self, e):
        if not self._main_focus(e):
            return None
        self.open_find()
        return "break"

    def confirm_discard(self):
        if not self.dirty:
            return True
        r = messagebox.askyesnocancel(APP_TITLE, "저장하지 않은 변경 사항이 있습니다. 저장할까요?")
        if r is None:
            return False
        if r:
            return self.save()
        return True

    def new_project(self):
        if not self.confirm_discard():
            return
        self.project = M.default_project()
        self.project_path = ""
        self.dirty = False
        self.load_all()
        self.reset_history()

    def open_dialog(self):
        if not self.confirm_discard():
            return
        p = filedialog.askopenfilename(filetypes=[("모드 메이커 프로젝트", "*.sts2mod.json *.json"), ("모든 파일", "*.*")])
        if p:
            self.open_project(p)

    def open_project(self, path, quiet=False):
        try:
            with open(path, encoding="utf-8") as f:
                loaded = json.load(f)
            project = M.normalize(loaded)
            project = _resolve_project_image_paths(project, os.path.dirname(os.path.abspath(path)))
        except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
            if quiet:
                self.log(f"[오류] 마지막 프로젝트를 열지 못했습니다 ({path}): {e}. 기본 프로젝트로 시작합니다.")
                self.settings["last_project"] = ""
                if not save_settings(self.settings):
                    self.log("[경고] 앱 설정을 저장하지 못했습니다.")
                self.project_path = ""
                self.dirty = False
                self.load_all()
                self.reset_history()
            else:
                messagebox.showerror(APP_TITLE, f"프로젝트를 열 수 없습니다:\n{e}")
            return False
        self.project = project
        self.project_path = path
        self.dirty = False
        self.settings["last_project"] = path
        if not save_settings(self.settings):
            self.log("[경고] 앱 설정을 저장하지 못했습니다.")
        self.load_all()
        self.reset_history()
        if path:
            self.log(f"열었습니다: {path}")
        return True

    def save(self):
        if not self.project_path:
            return self.save_as()
        try:
            _atomic_write_json(self.project_path, _project_data_for_save(self.project, self.project_path))
        except (OSError, TypeError, ValueError) as e:
            messagebox.showerror(APP_TITLE, f"저장 실패:\n{e}")
            return False
        self.dirty = False
        self.update_title()
        if self._snap_job:
            self.after_cancel(self._snap_job)
            self.commit_snapshot()
        self._saved_state = self.history.cur
        self.settings["last_project"] = self.project_path
        if not save_settings(self.settings):
            self.log("[경고] 프로젝트는 저장했지만 앱 설정은 저장하지 못했습니다.")
        self.log(f"저장했습니다: {self.project_path}")
        return True

    def save_as(self):
        p = filedialog.asksaveasfilename(defaultextension=".sts2mod.json",
                                         initialfile=f"{self.project['mod']['id']}.sts2mod.json",
                                         filetypes=[("모드 메이커 프로젝트", "*.sts2mod.json")])
        if not p:
            return False
        old_path = self.project_path
        self.project_path = p
        if not self.save():
            self.project_path = old_path
            self.update_title()
            return False
        return True

    def pack_project_assets(self):
        if self.busy:
            messagebox.showinfo(APP_TITLE, "빌드 중에는 프로젝트 자산을 모을 수 없습니다.")
            return
        if not self.project_path and not self.save_as():
            return

        sources = {}
        for source in _project_image_paths(self.project):
            absolute = os.path.abspath(source)
            sources.setdefault(os.path.normcase(absolute), absolute)
        if not sources:
            messagebox.showinfo(APP_TITLE, "모을 그림 파일이 없습니다.")
            return

        missing = [source for source in sources.values() if not os.path.isfile(source)]
        if missing:
            messagebox.showwarning(
                APP_TITLE,
                "그림 파일을 찾지 못했습니다. 경로를 수정한 뒤 다시 시도하세요:\n\n" +
                "\n".join(missing[:12]) +
                (f"\n… 외 {len(missing) - 12}개" if len(missing) > 12 else ""),
            )
            return

        project_dir = os.path.dirname(os.path.abspath(self.project_path))
        assets_dir = os.path.join(project_dir, "assets")
        created = []
        remap = {}
        try:
            os.makedirs(assets_dir, exist_ok=True)
            for key, source in sources.items():
                digest = hashlib.sha256()
                with open(source, "rb") as f:
                    for chunk in iter(lambda: f.read(1024 * 1024), b""):
                        digest.update(chunk)
                stem, extension = os.path.splitext(os.path.basename(source))
                filename = f"{digest.hexdigest()[:20]}_{stem[:72]}{extension[:12]}"
                destination = os.path.abspath(os.path.join(assets_dir, filename))
                if os.path.normcase(source) != os.path.normcase(destination) and not os.path.isfile(destination):
                    fd, temp_path = tempfile.mkstemp(prefix=".asset-", suffix=".tmp", dir=assets_dir)
                    os.close(fd)
                    try:
                        shutil.copy2(source, temp_path)
                        os.replace(temp_path, destination)
                    except Exception:
                        try:
                            os.remove(temp_path)
                        except OSError:
                            pass
                        raise
                    created.append(destination)
                remap[key] = destination
        except (OSError, ValueError) as e:
            for path in created:
                try:
                    os.remove(path)
                except OSError:
                    pass
            messagebox.showerror(APP_TITLE, f"자산을 복사하지 못했습니다:\n{e}")
            return

        packed = copy.deepcopy(self.project)
        def replace_source(source):
            return remap.get(os.path.normcase(os.path.abspath(source)), source)
        _transform_project_image_paths(packed, replace_source)

        old_project, old_dirty = self.project, self.dirty
        self.project = packed
        self.mark_dirty()
        if not self.save():
            self.project, self.dirty = old_project, old_dirty
            self.update_title()
            self.load_all()
            for path in created:
                try:
                    os.remove(path)
                except OSError:
                    pass
            return
        self.load_all()
        count = len(set(remap.values()))
        messagebox.showinfo(
            APP_TITLE,
            f"그림 {count}개를 프로젝트의 assets 폴더에 모았습니다.\n프로젝트 파일에는 상대 경로로 저장했습니다.",
        )

    def on_close(self):
        if self.confirm_discard():
            self.destroy()

    def load_all(self):
        self.mod_tab.load()
        self.char_tab.load()
        self.gimmick_tab.load()
        self.fx_tab.load()
        for t in (self.card_tab, self.relic_tab, self.potion_tab, self.power_tab):
            t.refresh_list()
        self.update_title()

    def on_tab(self):
        if self.nb.select() == str(self.char_tab):
            self.char_tab._loading = True
            try:
                self.char_tab.refresh_refs()
            finally:
                self.char_tab._loading = False
        elif self.nb.select() == str(self.mod_tab):
            self.mod_tab.run_checks()
        elif self.nb.select() == str(self.gallery_tab):
            self.gallery_tab.refresh()
        elif self.nb.select() == str(self.ext_tab):
            self.ext_tab.refresh()
        elif self.nb.select() == str(self.fx_tab):
            self.fx_tab.buttons.load()   # 유물·이펙트·파워 목록이 바뀌었을 수 있음
        for t in (self.card_tab, self.relic_tab, self.potion_tab, self.power_tab):
            if self.nb.select() == str(t):
                # 기믹 탭에서 태그·소환수가 바뀌었을 수 있으니 폼을 다시 읽는다
                if t.cur is not None and t.cur < len(t.items):
                    t.load(t.cur)
                t.update_preview()

    def on_items_changed(self):
        pass

    def frames_changed(self):
        """카드 테두리 디자인 창을 닫은 뒤: 고르기 목록과 미리보기를 새로."""
        self._gcache.clear()
        self.char_tab._loading = True
        try:
            self.char_tab.frame_combo.set_options(CF.options(self.project, for_card=False))
            self.char_tab.frame_combo.set_value(self.project["character"].get("frame_style", ""))
        finally:
            self.char_tab._loading = False
        ct = self.card_tab
        if ct.cur is not None and ct.cur < len(ct.items):
            ct.load(ct.cur)
        self.refresh_previews()

    def refresh_previews(self):
        sel = self.nb.select()
        if sel == str(self.char_tab):
            self.char_tab.update_preview()
        elif sel == str(self.gallery_tab):
            self.gallery_tab.refresh()
        elif sel == str(self.ext_tab):
            self.ext_tab.refresh()
        for t in (self.card_tab, self.relic_tab, self.potion_tab, self.power_tab):
            if sel == str(t):
                t.update_preview()

    def game_assets(self):
        if ingame is None:
            return None
        return ingame.get_assets(self.settings.get("sts2_path", ""))

    def game_version(self):
        a = self.game_assets()
        return a.version if a else "?"

    def game_image(self, kind, item, lang, upgraded, stacks):
        """게임 화면 합성 이미지 (같은 입력이면 저장해 둔 것을 씀). -> (이미지 또는 None, 오류)"""
        if ingame is None:
            return None, "Pillow 가 설치되어 있지 않습니다 (pip install pillow)."
        assets = self.game_assets()
        if assets is None:
            return None, ingame.last_error() or "게임 파일을 찾지 못했습니다."
        ch = self.project["character"]
        ch_key = {k: ch.get(k) for k in ("enabled", "color", "placeholder", "card_h", "card_s", "card_v",
                                         "energy_icon_image", "energy_text_icon_image", "frame_style")}
        try:
            key = json.dumps([kind, item, lang, upgraded, stacks, ch_key, self.project.get("powers", []),
                              self.project.get("card_frames", []) if kind == "card" else None],
                             sort_keys=True, ensure_ascii=False)
        except (TypeError, ValueError):
            key = None
        if key and key in self._gcache:
            return self._gcache[key], None
        try:
            img = ingame.compose(assets, self.project, kind, item, lang, upgraded, stacks)
        except Exception as e:  # noqa: BLE001
            return None, str(e)
        if key:
            if len(self._gcache) > 300:
                self._gcache.clear()
            self._gcache[key] = img
        return img, None

    def ext_image(self, em, kind, item, lang, upgraded):
        """다른 모드 항목의 게임 화면 (없으면 None)."""
        if self.pv_mode.get() != "game" or ingame is None:
            return None
        assets = self.game_assets()
        if assets is None:
            return None
        key = ("ext", em.root, kind, item.get("class"), lang, upgraded)
        if key in self._gcache:
            return self._gcache[key]
        try:
            img = ingame.compose(assets, self.project, kind, MI.preview_item(em, item), lang, upgraded, 3)
        except Exception as e:  # noqa: BLE001
            self.log(f"[미리보기 오류] {item.get('class')}: {e}")
            img = None
        if len(self._gcache) > 600:
            self._gcache.clear()
        self._gcache[key] = img
        return img

    def thumb(self, key, make_project_item, kind, lang, upgraded, stacks, w, h):
        """도감용 작은 그림 (백그라운드 스레드에서 불림). key 가 같으면 저장해 둔 것."""
        if ingame is None:
            return None
        assets = self.game_assets()
        if assets is None:
            return None
        full = ("thumb", key, kind, lang, upgraded, stacks, int(w), int(h))
        hit = self._tcache.get(full)
        if hit is not None:
            return hit
        item = make_project_item()
        k = 1 if kind == "card" and w <= 400 else 2
        img = ingame.compose(assets, self.project, kind, item, lang, upgraded, stacks, k=k)
        sc = min(w / img.size[0], h / img.size[1])
        img = img.resize((max(1, int(img.size[0] * sc)), max(1, int(img.size[1] * sc))), ingame.Image.LANCZOS)
        if len(self._tcache) > 1500:
            self._tcache.clear()
        self._tcache[full] = img
        return img

    def open_external(self):
        self.nb.select(self.ext_tab)
        self.ext_tab.open_file()

    def merge_dialog(self):
        p = filedialog.askopenfilename(title="합칠 프로젝트",
                                       filetypes=[("모드 메이커 프로젝트", "*.sts2mod.json *.json"), ("모든 파일", "*.*")])
        if not p:
            return
        try:
            with open(p, encoding="utf-8") as f:
                other = M.normalize(json.load(f))
                other = _resolve_project_image_paths(other, os.path.dirname(os.path.abspath(p)))
        except (OSError, ValueError, KeyError, TypeError) as e:
            messagebox.showerror(APP_TITLE, f"프로젝트를 읽을 수 없습니다:\n{e}")
            return
        used = self.all_ids()
        rename = {}
        counts = {}
        for key in ("powers", "cards", "relics", "potions"):
            for it in other.get(key, []):
                nid, n = it["id"], 2
                while nid in used:
                    nid = f"{it['id']}_{n}"
                    n += 1
                used.add(nid)
                if key == "powers" and nid != it["id"]:
                    rename[it["id"]] = nid
                it["id"] = nid
        for key in ("cards", "relics", "potions", "powers"):
            for it in other.get(key, []):
                for e in it.get("effects", []):
                    for fld in ("power", "cond_power", "scale_power"):
                        v = e.get(fld) or ""
                        if v.startswith("c:") and v[2:] in rename:
                            e[fld] = "c:" + rename[v[2:]]
                self.project[key].append(it)
                counts[key] = counts.get(key, 0) + 1
        deps = self.project.setdefault("dependencies", [])
        for d in other.get("dependencies", []):
            if not any(x["id"] == d["id"] for x in deps):
                deps.append(d)
        # 기믹 (태그 · 소환수): 겹치면 이름을 바꾸고 참조도 고친다
        GM.normalize(self.project)
        mine, theirs = self.project["gimmicks"], other.get("gimmicks") or {}
        for kind, key in (("tag", "tags"), ("summon", "summons"), ("orb", "orbs"), ("fx", "effects"), ("button", "buttons"),
                          ("pet", "pets")):
            for x in theirs.get(key, []):
                nid, n = x["id"], 2
                while nid in used:
                    nid = f"{x['id']}_{GM.letters(n).lower()}"
                    n += 1
                used.add(nid)
                if nid != x["id"]:
                    if kind in ("fx", "button"):
                        import fxui
                        fxui._rename(other, kind, x["id"], nid)
                    else:
                        rename_gimmick_ref(other, kind, x["id"], nid)
                    x["id"] = nid
                mine[key].append(x)
                counts[key] = counts.get(key, 0) + 1
        self.mark_dirty()
        self.load_all()
        messagebox.showinfo(APP_TITLE, "합쳤습니다: " + ", ".join(f"{ {'cards': '카드', 'relics': '유물', 'potions': '물약', 'powers': '파워', 'tags': '태그', 'summons': '소환수', 'orbs': '구체', 'effects': '이펙트', 'buttons': '버튼', 'pets': '동료'}[k]} {v}"
                                                                for k, v in counts.items()) +
                            ("\n(겹치는 ID 는 뒤에 번호를 붙였습니다)" if rename or any(True for _ in []) else ""))

    def goto(self, kind, idx):
        tab = {"card": self.card_tab, "relic": self.relic_tab, "potion": self.potion_tab,
               "power": self.power_tab}[kind]
        self.nb.select(tab)
        tab.select_index(idx)

    def goto_any(self, kind, iid):
        """전체 찾기에서 고른 항목으로 간다."""
        if kind in ("card", "relic", "potion", "power"):
            key = {"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}[kind]
            idx = next((i for i, x in enumerate(self.project[key]) if x["id"] == iid), None)
            if idx is not None:
                self.goto(kind, idx)
        elif kind in ("fx", "button"):
            self.nb.select(self.fx_tab)
            sub = self.fx_tab.painter if kind == "fx" else self.fx_tab.buttons
            self.fx_tab.nb.select(sub)
            items = sub.fxs if kind == "fx" else sub.items
            idx = next((i for i, x in enumerate(items) if x["id"] == iid), None)
            if idx is not None:
                sub.cur = idx
                sub.load()
        elif kind == "character":
            self.nb.select(self.char_tab)
        else:
            self.nb.select(self.gimmick_tab)
            jump = getattr(self.gimmick_tab, "reveal", None)
            if jump:
                jump(kind, iid)

    def all_ids(self):
        ids = {c["id"] for k in ("cards", "relics", "potions", "powers") for c in self.project[k]}
        g = self.project.get("gimmicks") or {}
        ids |= {x["id"] for x in g.get("tags", [])} | {x["id"] for x in g.get("summons", [])} | \
            {x["id"] for x in g.get("orbs", [])} | {x["id"] for x in g.get("effects", [])} | \
            {x["id"] for x in g.get("buttons", [])} | {x["id"] for x in g.get("pets", [])}
        ids.add(self.project["character"]["id"])
        return ids

    def rename_ref(self, kind, old, new):
        ch = self.project["character"]
        if kind == "card":
            if new is None:
                ch["deck"] = [d for d in ch["deck"] if d["card"] != old]
            else:
                for d in ch["deck"]:
                    if d["card"] == old:
                        d["card"] = new
        elif kind == "relic":
            ch["relics"] = [new if r == old else r for r in ch["relics"] if not (new is None and r == old)]
        elif kind == "power":
            if new is None:
                n = sum(1 for k in ("cards", "relics", "potions", "powers") for it in self.project[k]
                        for e in it["effects"] if f"c:{old}" in (e.get("power"), e.get("cond_power"), e.get("scale_power")))
                if n:
                    messagebox.showwarning(APP_TITLE, f"이 파워를 쓰는 효과가 {n}개 있습니다. ① 검사에서 위치를 확인해 고치세요.")
                return
            for k in ("cards", "relics", "potions", "powers"):
                for it in self.project[k]:
                    for e in it["effects"]:
                        for f in ("power", "cond_power", "scale_power"):
                            if e.get(f) == f"c:{old}":
                                e[f] = f"c:{new}"

    # ---- 로그 ----
    def log(self, msg):
        self.log_q.put(msg)

    def pump_log(self):
        try:
            while True:
                msg = self.log_q.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", msg.rstrip() + "\n")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        self.status_lbl.configure(text="빌드 중…" if self.busy else "")
        self.after(100, self.pump_log)

    # ---- 동작 ----
    def _validation_target(self, message):
        for label, kind in (("카드", "card"), ("유물", "relic"), ("물약", "potion"), ("파워", "power")):
            match = re.search(rf"{label} '([^']+)'", message)
            if match:
                return kind, match.group(1), f"{label}: {match.group(1)}"
        if message.startswith(("캐릭터", "시작 덱", "시작 유물")):
            return "character", "", "캐릭터"
        if any(word in message for word in ("태그", "소환수", "구체", "동료", "기믹")):
            return "gimmick", "", "기믹"
        if any(word in message for word in ("이펙트", "버튼")):
            return "fx", "", "이펙트·버튼"
        return "mod", "", "모드 / 빌드"

    def _open_validation_issue(self, targets, tree):
        selection = tree.selection()
        if not selection:
            return
        kind, item_id = targets.get(selection[0], ("mod", ""))
        if kind in ("card", "relic", "potion", "power"):
            keys = {"card": "cards", "relic": "relics", "potion": "potions", "power": "powers"}
            index = next((i for i, item in enumerate(self.project.get(keys[kind], []))
                          if item.get("id") == item_id), None)
            if index is not None:
                self.goto(kind, index)
                return
        tab = {"character": self.char_tab, "gimmick": self.gimmick_tab, "fx": self.fx_tab,
               "mod": self.mod_tab}.get(kind, self.mod_tab)
        self.nb.select(tab)

    def show_validation_results(self, errors, warnings):
        old = getattr(self, "_validation_window", None)
        if old is not None:
            try:
                if old.winfo_exists():
                    old.destroy()
            except tk.TclError:
                pass

        win = tk.Toplevel(self)
        self._validation_window = win
        win.title(f"검사 결과 — 오류 {len(errors)}개, 경고 {len(warnings)}개")
        win.geometry("980x560")
        win.minsize(760, 340)
        win.transient(self)
        center_window(win, self)

        summary = ttk.Label(win, text="항목을 더블클릭하면 해당 편집 화면으로 이동합니다.", padding=(10, 8))
        summary.pack(fill="x")
        body = ttk.Frame(win, padding=(8, 0, 8, 8))
        body.pack(fill="both", expand=True)
        columns = ("severity", "location", "message")
        tree = ttk.Treeview(body, columns=columns, show="headings", height=20)
        tree.heading("severity", text="구분")
        tree.heading("location", text="위치")
        tree.heading("message", text="내용")
        tree.column("severity", width=76, minwidth=70, stretch=False, anchor="center")
        tree.column("location", width=170, minwidth=130, stretch=False)
        tree.column("message", width=680, minwidth=300, stretch=True)
        tree.tag_configure("error", foreground="#a02020")
        tree.tag_configure("warning", foreground="#8a6500")
        scrollbar = ttk.Scrollbar(body, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        targets = {}
        for severity, messages, tag in (("오류", errors, "error"), ("경고", warnings, "warning")):
            for message in messages:
                kind, item_id, location = self._validation_target(message)
                row = tree.insert("", "end", values=(severity, location, message), tags=(tag,))
                targets[row] = (kind, item_id)
        tree.bind("<Double-1>", lambda _event: self._open_validation_issue(targets, tree))
        tree.bind("<Return>", lambda _event: self._open_validation_issue(targets, tree))

        footer = ttk.Frame(win, padding=(8, 0, 8, 8))
        footer.pack(fill="x")
        ttk.Button(footer, text="다시 검사", command=lambda: (win.destroy(), self.do_validate())).pack(side="left")
        ttk.Button(footer, text="닫기", command=win.destroy).pack(side="right")

    def do_validate(self):
        errors, warnings = M.validate(copy.deepcopy(self.project))
        for w in warnings:
            self.log("[경고] " + w)
        for e in errors:
            self.log("[오류] " + e)
        if errors or warnings:
            self.show_validation_results(errors, warnings)
        if errors:
            return False
        self.log(f"검사 통과 (경고 {len(warnings)}개).")
        if not warnings:
            messagebox.showinfo(APP_TITLE, "문제가 없습니다.")
        return True

    def project_dir(self):
        return os.path.join(self.settings.get("out_dir") or os.path.join(APP_DIR, "output"), self.project["mod"]["id"])

    def do_generate(self, quiet=False):
        if self.busy:
            if not quiet:
                messagebox.showinfo(APP_TITLE, "빌드 중에는 프로젝트를 다시 생성할 수 없습니다.")
            return None
        project = copy.deepcopy(self.project)
        errors, _ = M.validate(copy.deepcopy(project))
        if errors:
            self.do_validate()
            return None
        settings = copy.deepcopy(self.settings)
        out = settings.get("out_dir") or os.path.join(APP_DIR, "output")
        try:
            os.makedirs(out, exist_ok=True)
            root = M.generate(project, out, settings, log=self.log)
        except Exception as e:  # noqa: BLE001 - 사용자에게 그대로 보여 준다
            self.log(f"[오류] 생성 실패: {e}")
            messagebox.showerror(APP_TITLE, f"생성 실패:\n{e}")
            return None
        if not quiet:
            messagebox.showinfo(APP_TITLE, f"프로젝트를 만들었습니다:\n{root}")
        return root

    def do_build(self, publish):
        if self.busy:
            messagebox.showinfo(APP_TITLE, "이미 빌드 중입니다.")
            return
        if not shutil.which("dotnet"):
            messagebox.showerror(APP_TITLE, ".NET SDK(dotnet)가 없습니다. https://dotnet.microsoft.com 에서 .NET SDK 9 이상을 설치하세요.")
            return
        if publish and not os.path.isfile(self.settings.get("godot_path", "")):
            messagebox.showerror(APP_TITLE, "pck를 만들려면 MegaDot 4.5.1 (mono) 실행 파일 경로가 필요합니다.\n'모드 / 빌드' 탭의 환경 설정에서 지정하세요.")
            return
        root = self.do_generate(quiet=True)
        if not root:
            return
        build_sts2_path = self.settings.get("sts2_path", "")
        build_project_id = self.project["mod"]["id"]
        cmd = ["dotnet", "publish" if publish else "build", "-nologo"]
        if build_sts2_path:
            cmd.append(f"-p:Sts2Path={build_sts2_path}")
        self.busy = True
        self.log(f"$ {' '.join(cmd)}   (폴더: {root})")

        def run():
            try:
                flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
                env = dict(os.environ, DOTNET_CLI_UI_LANGUAGE="ko", DOTNET_NOLOGO="1")
                p = subprocess.Popen(cmd, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     creationflags=flags, env=env)
                for raw in p.stdout:
                    try:
                        line = raw.decode("utf-8")
                    except UnicodeDecodeError:
                        line = raw.decode("cp949", errors="replace")
                    if line.strip():
                        self.log(line)
                code = p.wait()
                if code == 0:
                    mods = os.path.join(build_sts2_path, "mods", build_project_id)
                    self.log(f"✔ {'게시' if publish else '빌드'} 성공! → {mods}")
                    if not publish:
                        self.log("  (그림·텍스트가 들어 있는 .pck는 ④ 게시에서 만들어집니다.)")
                else:
                    self.log(f"✘ 실패 (종료 코드 {code}). 위 로그의 error 줄을 확인하세요.")
            except Exception as e:  # noqa: BLE001
                self.log(f"[오류] 실행 실패: {e}")
            finally:
                self.busy = False

        threading.Thread(target=run, daemon=True).start()

    def _open(self, path):
        if not os.path.isdir(path):
            messagebox.showinfo(APP_TITLE, f"폴더가 없습니다:\n{path}")
            return
        if sys.platform == "win32":
            os.startfile(path)  # noqa: S606
        else:
            subprocess.Popen(["xdg-open", path])

    def open_project_dir(self):
        self._open(self.project_dir())

    def open_mods_dir(self):
        self._open(os.path.join(self.settings.get("sts2_path", ""), "mods"))

    def open_vscode(self):
        code = shutil.which("code")
        if not code:
            messagebox.showinfo(APP_TITLE, "VS Code(code 명령)를 찾지 못했습니다.")
            return
        if os.path.isdir(self.project_dir()):
            subprocess.Popen([code, self.project_dir()])

    def show_help(self):
        messagebox.showinfo(APP_TITLE, HELP_TEXT)


HELP_TEXT = """사용 순서

1. 캐릭터 탭: 새 캐릭터를 만들지 정하고 이름·체력·색·시작 덱·시작 유물을 정합니다. 시작 유물은 목록에서 여러 개 추가하고 선택 삭제할 수 있습니다.
2. 카드 / 유물 / 물약 탭: 왼쪽 '새로 만들기'로 추가하고, 효과를 넣습니다.
   설명은 효과에서 자동으로 만들어집니다 (한국어/영어/중국어 간체).
3. 모드 / 빌드 탭:
   ② 프로젝트 생성 → C# 프로젝트를 출력 폴더에 씁니다.
   ③ 빌드 → dll을 게임의 mods 폴더로 복사합니다.
   ④ 게시 → MegaDot로 그림/텍스트가 든 .pck까지 만들어 넣습니다.
4. 게임의 mods 폴더에 BaseLib도 설치되어 있어야 합니다.
5. 게임에서 ~ 키 콘솔에 `card 모드ID-카드ID` 를 입력해 카드를 바로 얻어 볼 수 있습니다.

검사 결과 창: 오류·경고를 더블클릭하거나 Enter 키를 눌러 해당 편집 화면으로 이동합니다.
파일 > 프로젝트 자산 모으기…: 참조 그림을 프로젝트 옆 assets 폴더에 복사하고 상대 경로로 저장합니다. 다른 폴더에 다른 이름으로 저장한 뒤 그림도 함께 옮기려면 새 위치에서 다시 실행하세요.

새 메커니즘 만들기
- ★ 파워 탭: 새 버프/디버프. 발동 시점(턴 시작/종료, 카드 사용, 피해 받을 때/줄 때) + 효과,
  상시 효과(주는/받는 피해, 방어도, 드로우, 최대 에너지), 줄어드는 방식을 정합니다.
- 효과 편집 창: '조건'(파워가 N 이상이면), '스택 비례 추가'(파워 1당 +N), '파워 제거'(쌓은 것 소모).
- '직접 C# 코드' 효과와 '추가 C# 코드' 칸으로 무엇이든 직접 쓸 수 있습니다.

ID 규칙: 영문 소문자와 _ 만 (예: fire_ball). 게임 안 ID는 MYMOD-FIRE_BALL 처럼 됩니다.
생성된 C# 파일은 직접 고쳐도 되지만, 다시 생성하면 덮어씁니다.
"""


def selftest(report_path):
    """배포본 점검: 창을 보이지 않게 띄워 모든 탭·창을 열고, 예시 모드를 생성·검사한 뒤 결과를 JSON 으로 쓴다."""
    import tempfile
    import traceback
    rep = {"ok": False, "app_dir": APP_DIR, "frozen": bool(getattr(sys, "frozen", False)), "steps": []}

    def step(name, fn):
        try:
            r = fn()
            rep["steps"].append({"step": name, "ok": True, "info": r})
        except Exception as e:  # noqa: BLE001
            rep["steps"].append({"step": name, "ok": False, "error": f"{e}", "trace": traceback.format_exc()[-1500:]})

    app = App()
    app.attributes("-alpha", 0.0)
    app.geometry("1400x900+-6000+-6000")
    app.update()
    for i in range(app.nb.index("end")):
        step(f"tab {app.nb.tab(i, 'text').strip()}", lambda i=i: (app.nb.select(i), app.update(), "ok")[2])

    def dialogs():
        import aiui
        import cardframeui
        import uxkit as ux
        for w in (aiui.AIGuideDialog(app), aiui.AIPasteDialog(app), ux.FindPalette(app, "ㅌ"),
                  cardframeui.FrameStyleDialog(app)):
            w.attributes("-alpha", 0.0)
            app.update()
            try:
                w.grab_release()
            except tk.TclError:
                pass
            w.destroy()
        return "ok"
    step("dialogs", dialogs)

    def game():
        a = app.game_assets()
        if a is None:
            return "게임 폴더 없음 (건너뜀)"
        im = ingame.compose(a, app.project, "card", app.project["cards"][0], "ko")
        return f"card render {im.size}"
    step("game assets", game)

    def gen():
        out = tempfile.mkdtemp(prefix="sts2mm_selftest_")
        p = M.normalize(copy.deepcopy(app.project))
        GM.add_examples(p)
        errs, _w = M.validate(p)
        root = M.generate(p, out)
        shutil.rmtree(out, ignore_errors=True)
        return {"validate_errors": errs[:3], "generated": bool(root)}
    step("generate", gen)
    rep["ok"] = all(s["ok"] for s in rep["steps"])
    app.dirty = False
    app.destroy()
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    return 0 if rep["ok"] else 1


def main():
    if "--selftest" in sys.argv:
        i = sys.argv.index("--selftest")
        out = sys.argv[i + 1] if len(sys.argv) > i + 1 else os.path.join(APP_DIR, "selftest.json")
        sys.exit(selftest(out))
    if sys.platform == "win32":
        try:  # 고해상도 화면에서 글자가 흐리지 않게
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    state = None
    while True:   # 화면 배율을 바꾸면 창을 새 배율로 다시 만든다 (작업 내용은 그대로)
        app = App(state)
        app.mainloop()
        state = getattr(app, "_restart_state", None)
        if not state:
            break
        UX._ICONS.clear()       # 이전 창의 그림은 새 창에서 쓸 수 없다
        PV.IMAGES.cache.clear()


if __name__ == "__main__":
    main()

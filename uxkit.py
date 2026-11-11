"""
편의 기능 모음 — 테마, 말풍선 도움말, 되돌리기 기록, 검색(초성 포함), 목록 아이콘, 검색칸, 전체 찾기 창, 일괄 수정 창.
"""
from __future__ import annotations

import json
import sys
import time
import _tkinter
import tkinter as tk
from tkinter import messagebox, ttk

from winpos import center_window
from docking import forget_floating_window, CheckedMenu, pointer_in_workspace, DockDrag, DockPanedWindow, install_panel_menu, is_panel_window, panel_groups, position_window, prepare_float_window

# Retain visible content until its replacement has been prepared. These helpers
# never pump events: callers keep control of when Tk paints the completed batch.
from functools import wraps
from contextlib import ExitStack, contextmanager


@contextmanager
def _canvas_batch(canvas, defer_new=False):
    if getattr(canvas, "_paint_batch_active", False):
        yield
        return
    canvas._paint_batch_active = True
    old = set(canvas.find_all())
    original_delete, original_create = canvas.delete, canvas._create
    clear = False
    pending = []
    def delete(*items):
        nonlocal clear
        if "all" in items:
            clear = True
            pending.clear()
            for item in set(canvas.find_all()) - old:
                original_delete(item)
        else:
            original_delete(*items)
    def create(kind, args, kw):
        if defer_new:
            # Only draw-only layout passes use this mode: they do not inspect
            # item IDs/bounds until the complete layout is ready.
            pending.append((kind,args,dict(kw)))
            return 0
        return original_create(kind,args,kw)
    canvas.delete, canvas._create = delete, create
    try:
        yield
        for kind,args,kw in pending:
            original_create(kind,args,kw)
    except BaseException:
        for item in set(canvas.find_all()) - old:
            original_delete(item)
        raise
    else:
        if clear:
            for item in old:
                original_delete(item)
    finally:
        canvas.delete, canvas._create = original_delete, original_create
        canvas._paint_batch_active = False


def buffered_canvas(*attributes, defer_new=False):
    def decorate(method):
        @wraps(method)
        def render(self, *args, **kwargs):
            # PhotoImage destruction blanks existing canvas images immediately.
            # Hold previous references through the entire drawing operation.
            retained = [v[:] if isinstance(v,list) else v for k,v in vars(self).items()
                        if "photo" in k or "image" in k]
            with ExitStack() as stack:
                for canvas in ([getattr(self,a) for a in attributes] if attributes else [self]):
                    stack.enter_context(_canvas_batch(canvas, defer_new))
                return method(self,*args,**kwargs)
        return render
    return decorate


def stable_tree(attribute="tree"):
    """Reuse root rows when a legacy refresh calls delete-all then insert."""
    def decorate(method):
        @wraps(method)
        def refresh(self,*args,**kwargs):
            tree = getattr(self,attribute)
            old = tuple(tree.get_children())
            delete, insert, children = tree.delete, tree.insert, tree.get_children
            rebuilding, used = False, []
            def remove(*items):
                nonlocal rebuilding
                if tuple(map(str,items)) == old:
                    rebuilding = True
                else:
                    delete(*items)
            def add(parent,index,iid=None,**options):
                if not rebuilding or parent != "":
                    return insert(parent,index,iid=iid,**options)
                key = str(iid) if iid is not None else old[len(used)] if len(used)<len(old) else None
                if key is not None and tree.exists(key):
                    for name,value in options.items():
                        if str(tree.item(key,name)) != str(value):
                            tree.item(key,**{name:value})
                    if tree.index(key) != len(used):
                        tree.move(key,"",len(used))
                else:
                    key = insert(parent,index,iid=key,**options)
                used.append(str(key))
                return key
            def get_children(item=None):
                if rebuilding and item in (None, ""):
                    return tuple(used)
                return children(item)
            tree.delete, tree.insert, tree.get_children = remove, add, get_children
            try:
                result = method(self,*args,**kwargs)
                if rebuilding:
                    stale = [key for key in old if key not in used]
                    if stale:
                        delete(*stale)
                return result
            finally:
                tree.delete, tree.insert, tree.get_children = delete, insert, children
        return refresh
    return decorate


def stable_listbox(*attributes):
    """Keep unchanged list entries, selection and scroll position in place."""
    def decorate(method):
        @wraps(method)
        def refresh(self,*args,**kwargs):
            restorers = []
            finishers = []
            for attribute in attributes:
                box = getattr(self,attribute)
                old = tuple(box.get(0,"end"))
                delete, insert = box.delete, box.insert
                state = {"clear":False,"count":0}
                def remove(first,last=None, state=state, delete=delete):
                    if str(first)=="0" and str(last)=="end":
                        state["clear"],state["count"] = True,0
                    else:
                        delete(first,last)
                def add(index,*values, box=box, old=old, state=state, delete=delete, insert=insert):
                    if not state["clear"] or str(index)!="end":
                        return insert(index,*values)
                    for value in values:
                        i = state["count"]
                        if i>=len(old):
                            insert("end",value)
                        elif old[i]!=str(value):
                            delete(i)
                            insert(i,value)
                        state["count"] += 1
                def finish(state=state, delete=delete, old=old):
                    if state["clear"] and state["count"]<len(old):
                        delete(state["count"],"end")
                box.delete,box.insert = remove,add
                restorers.append((box,delete,insert))
                finishers.append(finish)
            try:
                result = method(self,*args,**kwargs)
                for finish in finishers:
                    finish()
                return result
            finally:
                for box,delete,insert in restorers:
                    box.delete,box.insert = delete,insert
        return refresh
    return decorate


# ---------------------------------------------------------------------------
# 테마
# ---------------------------------------------------------------------------
C = {
    "bg": "#eef2f8", "surface": "#ffffff", "line": "#dfe5ef", "line2": "#ccd5e4",
    "text": "#24324b", "muted": "#66758c", "accent": "#365ee8", "accent_hi": "#2949bd",
    "accent_soft": "#e9eeff", "hover": "#f2f5ff", "warn": "#a46615", "danger": "#b8364b",
    "success": "#237b62", "workspace": "#f7f9fd", "panel": "#e8edf6",
    "console": "#262a31", "console_fg": "#d9dde4",
}

FONT = "Malgun Gothic"


def apply_theme(root, size=10):
    """밝고 깔끔한 평면 테마 (clam 기반). tk 위젯 기본값도 맞춘다."""
    st = ttk.Style(root)
    if st.theme_use() != "clam":
        st.theme_use("clam")
    f, fb, fs = (FONT, size), (FONT, size, "bold"), (FONT, size - 1)
    root.option_add("*Font", f)
    root.option_add("*Background", C["bg"])
    root.option_add("*Foreground", C["text"])
    root.option_add("*selectBackground", C["accent_soft"])
    root.option_add("*selectForeground", C["text"])
    for w in ("Listbox", "Text", "Entry"):
        root.option_add(f"*{w}.Background", C["surface"])
        root.option_add(f"*{w}.relief", "flat")
        root.option_add(f"*{w}.highlightThickness", 1)
        root.option_add(f"*{w}.highlightBackground", C["line"])
        root.option_add(f"*{w}.highlightColor", C["accent"])
        # selectForeground 의 옵션 클래스는 'Background' 라서 위 Background 에 덮이므로 이름으로 다시 지정
        root.option_add(f"*{w}.selectForeground", C["text"])
        root.option_add(f"*{w}.selectBackground", C["accent_soft"])
        root.option_add(f"*{w}.insertBackground", C["text"])
    root.option_add("*Listbox.activeStyle", "none")
    root.option_add("*Menu.Background", C["surface"])
    root.option_add("*Menu.activeBackground", C["accent_soft"])
    root.option_add("*Menu.activeForeground", C["text"])
    root.option_add("*Menu.relief", "flat")
    root.option_add("*Menu.font", f)
    root.configure(background=C["bg"])

    st.configure(".", background=C["bg"], foreground=C["text"], font=f, bordercolor=C["line"], lightcolor=C["bg"],
                 darkcolor=C["bg"], troughcolor=C["bg"], focuscolor=C["accent"], selectbackground=C["accent_soft"],
                 selectforeground=C["text"], fieldbackground=C["surface"], insertcolor=C["text"])
    st.configure("TFrame", background=C["surface"])
    st.configure("Card.TFrame", background=C["surface"], relief="solid", borderwidth=1)
    st.configure("TLabel", background=C["surface"], foreground=C["text"])
    st.configure("Muted.TLabel", foreground=C["muted"], font=fs)
    st.configure("Head.TLabel", font=(FONT, size + 1, "bold"), foreground=C["text"])
    st.configure("Count.TLabel", foreground=C["muted"], font=fs)
    st.configure("Help.TLabel", foreground=C["accent"], font=fs)
    st.configure("TLabelframe", background=C["surface"], bordercolor=C["line"], relief="solid", borderwidth=1)
    st.configure("TLabelframe.Label", background=C["surface"], foreground=C["text"], font=fb)
    st.configure("TSeparator", background=C["line"])

    st.configure("TButton", background=C["surface"], foreground=C["text"], bordercolor=C["line2"], lightcolor=C["surface"],
                 darkcolor=C["surface"], padding=(10, 4), relief="flat", focusthickness=1)
    st.map("TButton", background=[("disabled", C["bg"]), ("pressed", C["accent_soft"]), ("active", C["hover"])],
           bordercolor=[("focus", C["accent"]), ("active", C["accent"])],
           foreground=[("disabled", "#a2a7b1")])
    st.configure("Accent.TButton", background=C["accent"], foreground="#ffffff", bordercolor=C["accent"],
                 lightcolor=C["accent"], darkcolor=C["accent"], font=fb)
    st.map("Accent.TButton", background=[("disabled", "#9db6e6"), ("pressed", C["accent_hi"]), ("active", C["accent_hi"])],
           foreground=[("disabled", "#eef2fa")], bordercolor=[("active", C["accent_hi"])])
    st.configure("Tool.TButton", width=0, padding=(6, 3), background=C["bg"], bordercolor=C["bg"], lightcolor=C["bg"], darkcolor=C["bg"])
    st.map("Tool.TButton", background=[("pressed", C["accent_soft"]), ("active", C["hover"])],
           bordercolor=[("active", C["line"])])
    st.configure("Small.TButton", width=0, padding=(6, 2), font=fs)

    st.configure("TCheckbutton", background=C["surface"], indicatorbackground=C["surface"], indicatorforeground=C["accent"],
                 bordercolor=C["line2"])
    st.map("TCheckbutton", background=[("active", C["surface"])], indicatorbackground=[("selected", C["surface"])])
    st.configure("TRadiobutton", background=C["surface"], indicatorbackground=C["surface"], indicatorforeground=C["accent"],
                 bordercolor=C["line2"])
    st.map("TRadiobutton", background=[("active", C["surface"])])

    for w in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(w, fieldbackground=C["surface"], background=C["surface"], bordercolor=C["line2"],
                     lightcolor=C["surface"], darkcolor=C["surface"], padding=(7, 5), arrowcolor=C["muted"])
        st.map(w, bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent_soft"])],
               fieldbackground=[("readonly", C["surface"]), ("disabled", C["bg"])],
               foreground=[("disabled", "#9aa0aa")], arrowcolor=[("active", C["accent"])])
    st.configure("Placeholder.TEntry", foreground="#9aa0aa")
    root.option_add("*TCombobox*Listbox.background", C["surface"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent_soft"])
    root.option_add("*TCombobox*Listbox.font", f)

    st.configure("TNotebook", background=C["bg"], bordercolor=C["line"], tabmargins=(6, 6, 6, 0), padding=0)
    st.configure("TNotebook.Tab", background=C["bg"], foreground=C["muted"], bordercolor=C["bg"], lightcolor=C["bg"],
                 padding=(11, 7), font=f)
    st.map("TNotebook.Tab", background=[("selected", C["surface"]), ("active", C["hover"])],
           foreground=[("selected", C["accent_hi"]), ("active", C["text"])],
           bordercolor=[("selected", C["line"])], lightcolor=[("selected", C["surface"])],
           expand=[("selected", (0, 2, 0, 0))])

    st.configure("Treeview", background=C["surface"], fieldbackground=C["surface"], foreground=C["text"],
                 bordercolor=C["line"], rowheight=max(int(root.winfo_fpixels("1i") / 96 * 29), int(size * float(root.tk.call("tk", "scaling"))) + 12), font=f)
    st.map("Treeview", background=[("selected", C["accent_soft"])], foreground=[("selected", C["text"])])
    st.configure("Treeview.Heading", background=C["bg"], foreground=C["muted"], bordercolor=C["line"], font=fs, relief="flat", padding=(8, 6))
    st.configure("TScrollbar", background=C["bg"], troughcolor=C["bg"], bordercolor=C["bg"], arrowcolor=C["muted"],
                 lightcolor=C["bg"], darkcolor=C["bg"], gripcount=0)
    st.map("TScrollbar", background=[("active", C["line"]), ("!active", C["bg"])])
    st.configure("Vertical.TScrollbar", arrowsize=12)
    st.configure("Horizontal.TScrollbar", arrowsize=12)
    st.configure("TPanedwindow", background=C["bg"])
    st.configure("Sash", sashthickness=6, gripcount=0, background=C["bg"], lightcolor=C["bg"], bordercolor=C["bg"])
    st.configure("TProgressbar", background=C["accent"], troughcolor=C["line"], bordercolor=C["line"])
    st.configure("Status.TLabel", foreground=C["muted"], font=fs)
    st.configure("Toolbar.TFrame", background=C["surface"])
    st.configure("Toolbar.TLabel", background=C["surface"], foreground=C["muted"], font=fs)
    st.configure("Toolbar.TButton", width=0, background=C["surface"], bordercolor=C["surface"], lightcolor=C["surface"],
                 darkcolor=C["surface"], padding=(8, 4))
    st.map("Toolbar.TButton", background=[("pressed", C["accent_soft"]), ("active", C["hover"])],
           bordercolor=[("active", C["line"])], foreground=[("disabled", "#a2a7b1")])
    st.configure("Step.TButton", width=0, background=C["surface"], bordercolor=C["line2"], padding=(10, 4))
    st.map("Step.TButton", background=[("pressed", C["accent_soft"]), ("active", C["accent_soft"])],
           bordercolor=[("active", C["accent"])])
    st.configure("Toolbar.TSeparator", background=C["line"])
    # Shared visual hierarchy for main, floating and modal workspaces.
    st.configure("Desk.TFrame", background=C["bg"])
    st.configure("PanelHeader.TFrame", background=C["panel"])
    st.configure("PanelHeader.TLabel", background=C["panel"], foreground=C["muted"], font=(FONT,size-1,"bold"))
    st.configure("Panel.Tool.TButton", padding=(4, 0), font=fs, width=2, background=C["panel"],
                 bordercolor=C["panel"], lightcolor=C["panel"], darkcolor=C["panel"])
    st.map("Panel.Tool.TButton", background=[("active", C["accent_soft"])],
           foreground=[("active", C["accent"])])
    st.configure("Brand.TLabel", font=(FONT,size+3,"bold"), foreground=C["text"])
    st.configure("Project.TLabel", font=fs, foreground=C["muted"])
    st.configure("Badge.TLabel", padding=(8,3), background=C["accent_soft"], foreground=C["accent_hi"], font=fs)
    st.configure("Saved.Badge.TLabel", background="#e9f5ef", foreground=C["success"])
    st.configure("Unsaved.Badge.TLabel", background="#fff2df", foreground=C["warn"])
    st.configure("Footer.TFrame", background=C["bg"])
    st.configure("Footer.TLabel", background=C["bg"], foreground=C["muted"], font=fs)
    st.configure("Danger.TButton", foreground=C["danger"])
    st.map("Danger.TButton", background=[("active","#fff0f2")], foreground=[("disabled","#9da7b8")])
    st.layout("Segment.TRadiobutton", [("Button.border", {"sticky":"nswe", "children":[
        ("Button.padding", {"sticky":"nswe", "children":[("Radiobutton.label", {"sticky":"nswe"})]})]})])
    st.configure("Segment.TRadiobutton", padding=(9,6), background=C["bg"], foreground=C["muted"],
                 bordercolor=C["line"], font=f, anchor="center")
    st.map("Segment.TRadiobutton", background=[("selected",C["accent_soft"]),("active",C["hover"])],
           foreground=[("selected",C["accent_hi"])], bordercolor=[("selected",C["accent"])])
    return st


# ---------------------------------------------------------------------------
# 말풍선 도움말
# ---------------------------------------------------------------------------
class Tooltip:
    """위젯에 마우스를 잠시 올리면 설명 말풍선을 띄운다."""

    def __init__(self, widget, text, delay=450, wrap=360):
        self.w, self.text, self.delay, self.wrap = widget, text, delay, wrap
        self.tip = None
        self.job = None
        widget.bind("<Enter>", self._enter, add="+")
        widget.bind("<Leave>", self._leave, add="+")
        widget.bind("<ButtonPress>", self._leave, add="+")
        widget.bind("<Destroy>", self._destroy, add="+")

    def _destroy(self, event):
        if event.widget is self.w:
            self._leave()

    def _enter(self, _e=None):
        self._cancel()
        self.job = self.w.after(self.delay, self._show)

    def _leave(self, _e=None):
        self._cancel()
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None

    def _cancel(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _show(self):
        self.job = None
        text = self.text() if callable(self.text) else self.text
        if not text or not self.w.winfo_exists():
            return
        self.tip = tw = tk.Toplevel(self.w)
        tw.wm_overrideredirect(True)
        try:
            tw.attributes("-topmost", True)
        except tk.TclError:
            pass
        fr = tk.Frame(tw, background="#2a2e37", padx=10, pady=7)
        fr.pack()
        tk.Label(fr, text=text, background="#2a2e37", foreground="#f1f3f6", justify="left", wraplength=self.wrap,
                 font=(FONT, 9)).pack()
        tw.update_idletasks()
        x = self.w.winfo_rootx() + 8
        y = self.w.winfo_rooty() + self.w.winfo_height() + 4
        sw, sh = self.w.winfo_screenwidth(), self.w.winfo_screenheight()
        x = min(x, sw - tw.winfo_width() - 8)
        if y + tw.winfo_height() > sh - 40:
            y = self.w.winfo_rooty() - tw.winfo_height() - 4
        tw.geometry(f"+{x}+{y}")


def tip(widget, text):
    if text:
        Tooltip(widget, text)
    return widget


# 입력칸 설명 — "종류:키" 가 먼저, 없으면 "키".
FIELD_HELP = {
    "id": "코드와 파일 이름에 쓰이는 고유 이름입니다. 영문 소문자와 _ 만 쓰고, 숫자는 쓸 수 없습니다. "
          "바꾸면 이 항목을 쓰는 다른 곳도 함께 바뀝니다.",
    "name_ko": "게임 안에 보이는 한국어 이름입니다.",
    "name_en": "영어로 게임을 켰을 때 보이는 이름입니다. 비워 두면 한국어 이름을 씁니다.",
    "name_zh": "중국어(간체)로 게임을 켰을 때 보이는 이름입니다. 비워 두면 영어 이름을 씁니다.",
    "card:type": "공격·스킬·파워. 카드 틀 모양과, '공격 카드를 쓸 때마다' 같은 조건에 쓰입니다.",
    "card:rarity": "기본 카드는 시작 덱용, 일반·특별·희귀는 보상에 나오는 확률이 다릅니다.",
    "card:cost": "카드를 쓰는 데 드는 에너지입니다 (0~9). 남은 에너지를 전부 쓰는 X 비용은 키워드 줄의 'X 비용'을 켜세요.",
    "card:upgrade_cost": "강화했을 때의 비용입니다. 비용이 그대로면 같은 값을 두세요.",
    "card:target": "카드를 끌어다 놓을 대상입니다. 적 하나를 골라야 하면 '적 하나'.",
    "card:tag": "카드를 찾을 때 쓰는 분류 이름입니다. 예: 타격 태그가 있으면 ‘타격 카드’를 찾는 효과의 대상이 됩니다. 태그를 붙이는 것만으로 피해 같은 행동이 생기지는 않습니다.",
    "card:frame_style": "카드 틀·그림 테두리·제목 띠의 디자인. '캐릭터 기본 따르기'면 캐릭터 탭에서 고른 테두리를 씁니다. "
                        "'편집…'에서 색을 바꾸거나 직접 그린 그림을 넣을 수 있습니다.",
    "card:upgrade_add_keyword": "강화하면 붙는 키워드입니다 (예: 강화하면 보존).",
    "card:upgrade_remove_keyword": "강화하면 없어지는 키워드입니다 (예: 강화하면 소멸이 사라짐). 위 키워드 줄에서 켜 둔 키워드여야 합니다.",
    "relic:rarity": "유물이 어디서 나오는지 정합니다. 시작 유물은 캐릭터가 처음부터 가지고 시작합니다.",
    "relic:trigger": "유물 효과가 발동하는 때입니다.",
    "played_filter": "발동 횟수를 셀 카드의 조건입니다. 예: 공격을 고르면 스킬을 사용해도 횟수에 세지 않습니다.",
    "played_every": "카드를 이 장수만큼 쓸 때마다 한 번 발동합니다.",
    "enemy_mode": "'적' 대상 효과가 누구에게 갈지 정합니다 (모든 적 / 무작위 적).",
    "potion:rarity": "물약 보상에 나오는 확률입니다.",
    "potion:target": "물약을 쓸 때 대상을 고를지 정합니다.",
    "power:type": "버프는 좋은 효과(초록 테두리), 디버프는 나쁜 효과(빨간 테두리)입니다.",
    "power:stack": "같은 상태 효과를 또 받았을 때 수치를 어떻게 합칠지 정합니다. ‘중첩’은 쌓인 숫자입니다. 예: 중독 3에 중독 2를 더하면 중독 5가 됩니다.",
    "power:trigger": "파워 효과가 발동하는 때입니다. '없음'이면 상시 효과만 씁니다.",
    "power:decay": "턴이 지날 때 수치가 줄어드는 방식입니다.",
    "played_by": "누가 카드를 썼을 때 셀지 정합니다 (파워를 가진 쪽 / 아무나).",
    "image": "PNG 그림 파일입니다. 비워 두면 임시 그림을 씁니다.",
    "desc_ko": "효과에서 자동으로 만든 설명 대신 직접 쓴 설명을 씁니다. 보통은 비워 두세요.",
    "desc_en": "영어 설명을 직접 씁니다. 비워 두면 효과에서 자동으로 만듭니다.",
    "desc_zh": "중국어 설명을 직접 씁니다. 비워 두면 효과에서 자동으로 만듭니다.",
    "extra_code": "C# 코드를 클래스 안에 그대로 넣습니다. 코드를 아는 경우에만 쓰세요.",
    "flavor_ko": "유물 설명 아래에 기울어진 글씨로 나오는 짧은 글입니다.",
    "flavor_en": "영어 플레이버 문구입니다.",
    "flavor_zh": "중국어 플레이버 문구입니다. 비워 두면 한국어 문구를 씁니다.",
}


def field_help(kind, key):
    return FIELD_HELP.get(f"{kind}:{key}") or FIELD_HELP.get(key) or ""


# ---------------------------------------------------------------------------
# 되돌리기 기록
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 검색 (초성 검색 포함)
# ---------------------------------------------------------------------------
_CHO = "ㄱㄲㄴㄷㄸㄹㅁㅂㅃㅅㅆㅇㅈㅉㅊㅋㅌㅍㅎ"


def chosung(text):
    out = []
    for ch in text or "":
        o = ord(ch)
        if 0xAC00 <= o <= 0xD7A3:
            out.append(_CHO[(o - 0xAC00) // 588])
        else:
            out.append(ch)
    return "".join(out)


def matches(query, *fields):
    """대소문자 무시 부분 일치. 질문이 초성만이면(ㅂㅇ) 초성으로도 찾는다. 띄어쓰기로 나눈 낱말은 모두 맞아야 한다."""
    words = (query or "").lower().split()
    if not words:
        return True
    hay = " ".join(str(f or "") for f in fields).lower()
    cho = chosung(hay)
    for w in words:
        if w in hay:
            continue
        if all(c in _CHO for c in w) and w in cho:
            continue
        return False
    return True


# ---------------------------------------------------------------------------
# 목록 아이콘
# ---------------------------------------------------------------------------
TYPE_COL = {"Attack": (205, 82, 62), "Skill": (58, 128, 205), "Power": (206, 160, 52)}
RARITY_COL = {"Basic": (150, 154, 162), "Starter": (150, 154, 162), "Common": (198, 202, 210), "Uncommon": (70, 150, 240),
              "Rare": (236, 186, 60), "Shop": (120, 190, 120), "Event": (190, 120, 210), "Ancient": (190, 120, 210)}
_ICONS = {}


def item_icon(kind, it, scale=1.0):
    """종류별 작은 아이콘 (PhotoImage). 카드 = 종류 색 + 희귀도 테두리 + 비용, 유물 = 희귀도 색 보석, 물약 = 희귀도 색 병,
    파워 = 버프(초록 ▲)/디버프(빨강 ▼)."""
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageTk
    except ImportError:
        return ""
    s = max(16, int(18 * scale))
    if kind == "card":
        cost = it.get("cost")
        cost = "X" if isinstance(cost, int) and cost < 0 else str(cost if cost is not None else "")
        key = (kind, it.get("type"), it.get("rarity"), cost, s)
    elif kind == "power":
        key = (kind, it.get("type"), s)
    else:
        key = (kind, it.get("rarity"), s)
    if key in _ICONS:
        return _ICONS[key]
    k = 4
    S = s * k
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    rc = RARITY_COL.get(it.get("rarity"), (180, 184, 192))
    if kind == "card":
        tc = TYPE_COL.get(it.get("type"), (140, 140, 150))
        d.rounded_rectangle((k, k, S - k, S - k), radius=4 * k, fill=tc + (255,), outline=rc + (255,), width=2 * k)
        try:
            fnt = ImageFont.truetype("malgunbd.ttf", int(S * 0.6))
        except OSError:
            fnt = ImageFont.load_default()
        d.text((S / 2, S / 2 + k * 0.5), cost, font=fnt, fill=(255, 255, 255, 255), anchor="mm",
               stroke_width=k, stroke_fill=tuple(int(v * 0.55) for v in tc) + (255,))
    elif kind == "relic":
        pts = [(S / 2, 1.5 * k), (S - 1.5 * k, S * 0.42), (S / 2, S - 1.5 * k), (1.5 * k, S * 0.42)]
        d.polygon(pts, fill=rc + (255,), outline=tuple(int(v * 0.6) for v in rc) + (255,))
        d.polygon([(S / 2, 3 * k), (S * 0.72, S * 0.42), (S / 2, S * 0.42)], fill=(255, 255, 255, 110))
    elif kind == "potion":
        d.rounded_rectangle((S * 0.38, 1.5 * k, S * 0.62, S * 0.36), radius=k, fill=(150, 120, 90, 255))
        d.ellipse((2 * k, S * 0.3, S - 2 * k, S - 1.5 * k), fill=rc + (255,), outline=tuple(int(v * 0.6) for v in rc) + (255,),
                  width=k)
        d.ellipse((S * 0.3, S * 0.45, S * 0.45, S * 0.6), fill=(255, 255, 255, 140))
    elif kind == "power":
        buff = it.get("type") != "Debuff"
        col = (64, 170, 96) if buff else (196, 72, 80)
        d.ellipse((k, k, S - k, S - k), fill=col + (255,))
        if buff:
            d.polygon([(S / 2, S * 0.22), (S * 0.78, S * 0.66), (S * 0.22, S * 0.66)], fill=(255, 255, 255, 255))
        else:
            d.polygon([(S / 2, S * 0.78), (S * 0.78, S * 0.34), (S * 0.22, S * 0.34)], fill=(255, 255, 255, 255))
    else:
        d.ellipse((k, k, S - k, S - k), fill=(150, 150, 160, 255))
    im = im.resize((s, s), Image.LANCZOS)
    ph = ImageTk.PhotoImage(im)
    _ICONS[key] = ph
    return ph


# ---------------------------------------------------------------------------
# 검색칸
# ---------------------------------------------------------------------------
class SearchEntry(ttk.Frame):
    """🔍 + 입력칸 + ✕ 지우기. 비어 있으면 회색 안내 글자. on_change(query) 를 부른다."""

    def __init__(self, master, placeholder="찾기", on_change=None, width=20, on_enter=None, on_down=None):
        super().__init__(master)
        self.placeholder = placeholder
        self.on_change = on_change
        self.var = tk.StringVar()
        self._ph = False
        ttk.Label(self, text="🔍").pack(side="left", padx=(0, 3))
        self.entry = ttk.Entry(self, textvariable=self.var, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        self.clear_btn = ttk.Button(self, text="✕", width=2, style="Tool.TButton", command=self.clear)
        self.entry.bind("<FocusIn>", self._focus_in)
        self.entry.bind("<FocusOut>", self._focus_out)
        self.entry.bind("<Escape>", lambda _e: self.clear())
        if on_enter:
            self.entry.bind("<Return>", lambda _e: on_enter())
        if on_down:
            self.entry.bind("<Down>", lambda _e: on_down())
        self.var.trace_add("write", self._changed)
        self._focus_out()

    def get(self):
        return "" if self._ph else self.var.get().strip()

    def set(self, text):
        self._ph = False
        self.entry.configure(style="TEntry")
        self.var.set(text)
        if not text and self.focus_get() is not self.entry:
            self._focus_out()

    def clear(self):
        if self.get():
            self.set("")
        return "break"

    def focus(self):
        self.entry.focus_set()
        self.entry.select_range(0, "end")

    def _focus_in(self, _e=None):
        if self._ph:
            self._ph = False
            self.entry.configure(style="TEntry")
            self.var.set("")

    def _focus_out(self, _e=None):
        if not self.var.get():
            self._ph = True
            self.entry.configure(style="Placeholder.TEntry")
            self.var.set(self.placeholder)

    def _changed(self, *_):
        q = self.get()
        if q:
            self.clear_btn.pack(side="left", padx=(2, 0))
        else:
            self.clear_btn.pack_forget()
        if self.on_change and not (self._ph and self.var.get() == self.placeholder):
            self.on_change(q)


# ---------------------------------------------------------------------------
# 전체에서 찾기 (Ctrl+P)
# ---------------------------------------------------------------------------
KIND_LABEL = {"card": "카드", "relic": "유물", "potion": "물약", "power": "파워", "tag": "태그", "summon": "소환수",
              "orb": "구체", "pet": "동료", "fx": "이펙트", "button": "전투 버튼", "character": "캐릭터"}


def all_entries(project):
    """(kind, id, 이름, 더 찾아볼 글, 아이템) 목록."""
    out = []
    for kind, key in (("card", "cards"), ("relic", "relics"), ("potion", "potions"), ("power", "powers")):
        for it in project.get(key, []):
            out.append((kind, it["id"], it.get("name_ko") or it.get("name_en") or it["id"],
                        " ".join(str(it.get(k) or "") for k in ("name_en", "name_zh", "desc_ko", "desc_en")), it))
    g = project.get("gimmicks") or {}
    for kind, key, nm in (("tag", "tags", "name_ko"), ("summon", "summons", "name_ko"), ("orb", "orbs", "name_ko"),
                          ("pet", "pets", "name_ko"), ("fx", "effects", "name"), ("button", "buttons", "label_ko")):
        for it in g.get(key, []) or []:
            out.append((kind, it["id"], it.get(nm) or it.get("name_ko") or it.get("name") or it["id"],
                        " ".join(str(it.get(k) or "") for k in ("name_en", "label_en", "name")), it))
    ch = project.get("character") or {}
    if ch.get("id"):
        out.append(("character", ch["id"], ch.get("name_ko") or ch["id"], ch.get("name_en") or "", ch))
    return out


class FindPalette(tk.Toplevel):
    """프로젝트 전체에서 이름·ID·설명으로 찾고, 고르면 그 항목으로 바로 간다."""

    def __init__(self, app, query=""):
        super().__init__(app)
        self.app = app
        self.title("전체에서 찾기")
        self.transient(app)
        self.configure(background=C["bg"], padx=12, pady=12)
        self.geometry(f"{int(560 * app.ui)}x{int(440 * app.ui)}")
        ttk.Label(self, text="이름·ID·설명으로 찾기 (초성도 됩니다: ㅅㅂ → 수비)", style="Muted.TLabel").pack(anchor="w")
        self.search = SearchEntry(self, "찾을 말", self.refresh, width=40, on_enter=self.go, on_down=self._down)
        self.search.pack(fill="x", pady=(4, 8))
        fr = ttk.Frame(self)
        fr.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(fr, columns=("kind", "id"), show="tree", selectmode="browse")
        self.tree.column("#0", width=260, stretch=True)
        self.tree.column("kind", width=80, stretch=False, anchor="w")
        self.tree.column("id", width=150, stretch=False, anchor="w")
        sb = ttk.Scrollbar(fr, command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.bind("<Double-Button-1>", lambda _e: self.go())
        self.tree.bind("<Return>", lambda _e: self.go())
        self.count = ttk.Label(self, text="", style="Muted.TLabel")
        self.count.pack(anchor="w", pady=(6, 0))
        self.bind("<Escape>", lambda _e: self.destroy())
        self.rows = {}
        center_window(self, app)
        self.search.focus()
        if query:
            self.search.set(query)
        self.refresh(self.search.get())

    @stable_tree("tree")
    def refresh(self, q):
        self.tree.delete(*self.tree.get_children())
        self.rows = {}
        n = 0
        for kind, iid, name, extra, it in all_entries(self.app.project):
            if not matches(q, name, iid, extra, KIND_LABEL.get(kind, "")):
                continue
            img = item_icon(kind, it, self.app.ui) if kind in ("card", "relic", "potion", "power") else ""
            r = self.tree.insert("", "end", text="  " + name, image=img, values=(KIND_LABEL.get(kind, kind), iid))
            self.rows[r] = (kind, iid)
            n += 1
            if n >= 300:
                break
        kids = self.tree.get_children()
        if kids:
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
        self.count.configure(text=f"{len(kids)}개" + (" (처음 300개만 보여 줍니다)" if n >= 300 else ""))

    def _down(self):
        kids = self.tree.get_children()
        if kids:
            self.tree.focus_set()
            self.tree.selection_set(kids[0])
            self.tree.focus(kids[0])
        return "break"

    def go(self):
        sel = self.tree.selection()
        if not sel:
            return
        kind, iid = self.rows[sel[0]]
        self.destroy()
        self.app.goto_any(kind, iid)


# ---------------------------------------------------------------------------
# 여러 항목 한꺼번에 바꾸기
# ---------------------------------------------------------------------------
class BulkEditDialog(tk.Toplevel):
    """선택한 여러 항목의 공통 칸(종류·희귀도·비용 등)을 한 번에 바꾼다. 체크한 칸만 바뀐다."""

    def __init__(self, tab, indices):
        super().__init__(tab.app)
        self.tab, self.indices = tab, list(indices)
        self.title(f"{tab.noun} {len(self.indices)}개 한꺼번에 바꾸기")
        self.transient(tab.app)
        self.configure(background=C["bg"], padx=14, pady=12)
        first = tab.items[self.indices[0]]
        ttk.Label(self, text="바꿀 칸만 체크하세요. 체크하지 않은 칸은 그대로 둡니다.", style="Muted.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        self.rows = []
        r = 1
        for key, (typ, w) in tab.vars.items():
            if typ not in ("combo", "int", "bool") or key in ("id",):
                continue
            label = tab.var_labels.get(key, key)
            on = tk.BooleanVar(value=False)
            ttk.Checkbutton(self, variable=on).grid(row=r, column=0, sticky="w")
            ttk.Label(self, text=label).grid(row=r, column=1, sticky="w", padx=(0, 10), pady=2)
            if typ == "combo":
                opts = list(w.options)
                cw = ttk.Combobox(self, values=[l for _, l in opts], state="readonly", width=24)
                cur = first.get(key)
                cw.current(next((i for i, (v, _l) in enumerate(opts) if v == cur), 0) if opts else -1)
                cw.grid(row=r, column=2, sticky="w", pady=2)
                getter = (lambda cw=cw, opts=opts: opts[cw.current()][0] if cw.current() >= 0 else None)
                cw.bind("<<ComboboxSelected>>", lambda _e, on=on: on.set(True))
            elif typ == "int":
                v = tk.StringVar(value=str(first.get(key, 0)))
                sw = ttk.Spinbox(self, from_=-1, to=999, textvariable=v, width=8)
                sw.grid(row=r, column=2, sticky="w", pady=2)
                v.trace_add("write", lambda *_, on=on: on.set(True))

                def getter(v=v):
                    try:
                        return int(v.get())
                    except ValueError:
                        return None
            else:
                v = tk.BooleanVar(value=bool(first.get(key)))
                ttk.Checkbutton(self, text="켜기", variable=v, command=lambda on=on: on.set(True)).grid(
                    row=r, column=2, sticky="w", pady=2)
                getter = v.get
            self.rows.append((key, on, getter))
            r += 1
        self.tags = tab.app.project.get("gimmicks", {}).get("tags", []) if tab.kind == "card" else []
        self.tag_choice = ttk.Combobox(self, state="readonly", values=["태그 추가 안 함"] +
                                      [t.get("name_ko") or t["id"] for t in self.tags])
        if self.tags:
            self.tag_choice.current(0)
            self.tag_choice.grid(row=r, column=2)
            ttk.Label(self, text="기믹 태그 추가").grid(row=r,column=1)
            r += 1
        if not self.rows:
            ttk.Label(self, text="한꺼번에 바꿀 수 있는 칸이 없습니다.").grid(row=r, column=0, columnspan=3)
            r += 1
        bf = ttk.Frame(self)
        bf.grid(row=r, column=0, columnspan=3, sticky="e", pady=(12, 0))
        ttk.Button(bf, text="바꾸기", style="Accent.TButton", command=self.ok).pack(side="left", padx=4)
        ttk.Button(bf, text="취소", command=self.destroy).pack(side="left")
        self.bind("<Escape>", lambda _e: self.destroy())
        center_window(self, tab.app)
        self.grab_set()

    def ok(self):
        changes = {}
        for key, on, getter in self.rows:
            if on.get():
                val = getter()
                if val is not None:
                    changes[key] = val
        tag = self.tags[self.tag_choice.current()-1]["id"] if self.tag_choice.current() > 0 else None
        updates = []
        for i in self.indices:
            card = self.tab.items[i]
            diff = {k:v for k,v in changes.items() if card.get(k) != v}
            if tag and tag not in card.get("gtags", []):
                diff["gtags"] = card.get("gtags", []) + [tag]
            if diff:
                updates.append((i,diff))
        if not updates:
            self.destroy()
            return
        preview = "\n".join((self.tab.items[i].get("name_ko") or self.tab.items[i]["id"]) + ": " +
                            ", ".join(f"{self.tab.var_labels.get(k,k)} {self.tab.items[i].get(k,'')} → {v}" for k,v in diff.items())
                            for i,diff in updates)
        if messagebox.askyesno("일괄 변경 미리보기", preview, parent=self):
            for i,diff in updates:
                self.tab.items[i].update(diff)
            self.tab.app.mark_dirty()
            self.tab.refresh_list(self.indices)
            self.tab.app.on_items_changed()
            self.destroy()


# ---------------------------------------------------------------------------
# 자동 스크롤바 (창이 작으면 아래·오른쪽 스크롤바가 나타남)
# ---------------------------------------------------------------------------
class AutoScroll(ttk.Frame):
    """Keep one content tree; scrolling only moves its existing Canvas window.

    Position-only Configure events never trigger layout or synthetic painting.
    Tk handles normal exposure of the retained native widgets.
    """

    def __init__(self, master, x=True, y=True, **kw):
        super().__init__(master, **kw)
        self.x, self.y = x, y
        increment = max(12,int(self.winfo_fpixels("1i")/96*20))
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0,
                                yscrollincrement=increment,xscrollincrement=increment)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=lambda *a:self._drag(False,*a))
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=lambda *a:self._drag(True,*a))
        self.canvas.configure(yscrollcommand=lambda a,b:self._view_changed(False,a,b),
                              xscrollcommand=lambda a,b:self._view_changed(True,a,b))
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")
        self.vsb.grid_remove()
        self.hsb.grid_remove()
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        self.inner = ttk.Frame(self.canvas)
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self._job = None
        self._sizes = {}
        self._window_size = None
        self._region = None
        self.bind("<Destroy>",self._destroy,add="+")
        self.inner.bind("<Configure>", self._later, add="+")
        self.canvas.bind("<Configure>", self._later, add="+")

    def _destroy(self, event):
        if event.widget is self:
            for attr in ("_job",):
                job = getattr(self,attr)
                if job is not None:
                    self.after_cancel(job)
                    setattr(self,attr,None)

    def _drag(self, horizontal, *args):
        (self.canvas.xview if horizontal else self.canvas.yview)(*args)
        present_scroll(self.canvas)

    def _view_changed(self, horizontal, first, last):
        (self.hsb if horizontal else self.vsb).set(first,last)

    def _later(self, event=None):
        if event is not None:
            size = (event.width,event.height)
            if self._sizes.get(event.widget)==size:
                return
            self._sizes[event.widget] = size
        if self._job is None:
            self._job = self.after(16,self._sync)

    def _sync(self):
        if self._job is not None:
            self.after_cancel(self._job)
        self._job = None
        try:
            cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
            rw, rh = self.inner.winfo_reqwidth(), self.inner.winfo_reqheight()
        except tk.TclError:
            return
        if cw <= 1 or ch <= 1:
            return
        need_x, need_y = self.x and rw > cw + 1, self.y and rh > ch + 1
        w = max(cw, rw) if self.x else cw
        h = max(ch, rh) if self.y else ch
        if self._window_size != (w,h):
            self.canvas.itemconfigure(self._win,width=w,height=h)
            self._window_size = (w,h)
        region = (0,0,w,h)
        if self._region != region:
            self.canvas.configure(scrollregion=region)
            self._region = region
        for bar, need in ((self.hsb, need_x), (self.vsb, need_y)):
            if need and not bar.winfo_ismapped():
                bar.grid()
            elif not need and bar.winfo_ismapped():
                bar.grid_remove()
        if not need_x:
            self.canvas.xview_moveto(0)
        if not need_y:
            self.canvas.yview_moveto(0)



def _set_if(widget, **options):
    """Configure only options that differ: any Tk configure re-runs layout and redraw."""
    changed = {k:v for k,v in options.items() if str(widget.cget(k)) != str(v)}
    if changed:
        widget.configure(**changed)


class ResponsiveForm:
    """Reflow four-column forms without recreating their controls or variables."""
    def __init__(self, form, viewport):
        self.form, self.viewport = form, viewport
        self.original = {w:dict(w.grid_info()) for w in form.grid_slaves()}
        self.groups = {}
        self.job = None
        self._sizes = {}
        self.narrow = None
        viewport.bind("<Configure>",self.schedule,add="+")
        form.bind("<Configure>",self.schedule,add="+")
        form.bind("<Destroy>",self._destroy,add="+")
        self.schedule()

    def _destroy(self, event):
        if event.widget is self.form and self.job is not None:
            self.form.after_cancel(self.job)
            self.job = None

    def schedule(self, event=None):
        if event is not None:
            size = (event.width,event.height)
            if self._sizes.get(event.widget)==size:
                return
            self._sizes[event.widget] = size
        if self.job is None:
            self.job = self.form.after(16,self._sync)

    def _sync(self):
        if self.job is not None:
            self.form.after_cancel(self.job)
        self.job = None
        if not self.form.winfo_exists():
            return
        width = self.viewport.winfo_width()
        if width<2:
            return
        dpi = self.form.winfo_fpixels("1i")/96
        narrow = width<int(880*dpi)
        stacked = narrow and width<400
        if narrow != self.narrow or stacked != getattr(self,"stacked",None):
            self.stacked = stacked
            self.narrow = narrow
            for col in range(4):
                self.form.columnconfigure(col,weight=1 if col==(0 if stacked else 1) or (not narrow and col==3) else 0)
        for widget, original in self.original.items():
            current = widget.grid_info()
            if not current:
                continue
            row,col = int(original["row"]),int(original["column"])
            values = dict(row=row*4+col if stacked else row*2+col//2 if narrow else row,
                          column=0 if stacked else col%2 if narrow else col,
                          columnspan=1 if stacked else (2 if col==0 and int(original["columnspan"])>=4 else 1) if narrow else int(original["columnspan"]),
                          rowspan=1 if narrow else int(original["rowspan"]))
            if narrow:
                values["sticky"] = "we" if col%2 or int(original["columnspan"])>1 else "w"
            else:
                values["sticky"] = original["sticky"]
            if any(str(current.get(key)) != str(value) for key,value in values.items()):
                widget.grid_configure(**values)
            if isinstance(widget,ttk.Label):
                _set_if(widget,wraplength=max(110,min(180,width//3)) if narrow and not stacked and col%2==0 and int(original["columnspan"])==1 else max(160,width-50))
        controls = (ttk.Button,ttk.Checkbutton,ttk.Radiobutton,ttk.Menubutton,
                    ttk.Entry,ttk.Combobox,ttk.Spinbox,ttk.Label,ttk.Separator,tk.Label,tk.Button)
        def discover(parent):
            packed = parent.pack_slaves()
            if packed and all(isinstance(w,controls) and w.pack_info()["side"] in ("left","right") for w in packed):
                records = []
                for w in packed:
                    info = w.pack_info()
                    records.append((w,info))
                    w.pack_forget()
                self.groups[parent] = records
            for child in parent.winfo_children():
                if isinstance(child,(ttk.Frame,ttk.LabelFrame,tk.Frame,ttk.Notebook)):
                    discover(child)
        discover(self.form)
        for parent, records in list(self.groups.items()):
            if not parent.winfo_exists():
                del self.groups[parent]
                continue
            budget = max(160,width-(200 if parent.master is self.form and parent.grid_info().get("column")==1 else 60 if parent.master is self.form else 220))
            x,y,line_height,max_width = 0,0,0,0
            for widget,info in records:
                if not widget.winfo_exists():
                    continue
                if isinstance(widget,(ttk.Label,tk.Label)):
                    _set_if(widget,wraplength=budget)
                wanted,height = widget.winfo_reqwidth(),widget.winfo_reqheight()
                if x and x+wanted>budget:
                    y += line_height+6
                    x,line_height = 0,0
                current = widget.place_info()
                if not current or int(current["x"])!=x or int(current["y"])!=y:
                    widget.place(x=x,y=y)
                x += wanted+6
                max_width = max(max_width,x)
                line_height = max(line_height,height)
            # Keep native parents unchanged while wrapping controls. This also
            # stays stable when an ancestor panel is detached with wm manage.
            _set_if(parent,width=max(1,max_width),height=max(1,y+line_height+3))



class _TabHost(tk.Frame, tk.Wm):
    """Native Tk frame that can become a window without recreating its children."""


class ScrollNotebook(ttk.Notebook):
    """Scrollable pages with stable identities, visibility, and native floating windows."""
    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._inner_of, self._outer_of = {}, {}
        self._slot_of, self._key_of = {}, {}
        self._area = None
        self._park_job = None
        self._catch_job = None
        tag = "ScrollNotebookPages" + str(id(self))
        self.bind_class(tag, "<<NotebookTabChanged>>", self._layout_hosts)
        self.bindtags((tag,) + self.bindtags())
        self._pages, self._order = {}, []
        self._visual_order = []
        self._active_popup = None
        self._notify_job = None
        self._tab_drag = DockDrag(self, self._probe_tab, self._finish_tab)
        self._tab_font = None
        self._tab_font_spec = None
        self.bind("<ButtonPress-1>", self._tab_press, add="+")
        self.bind("<B1-Motion>", self._tab_drag.motion, add="+")
        self.bind("<ButtonRelease-1>", self._tab_drag.release, add="+")
        self.bind("<Button-3>", self._context_menu)
        self.bind("<Button-1>", lambda e:setattr(self, "_active_popup", None), add="+")
        self._focus_binding = self.bind_all("<FocusIn>", self._track_focus, add="+")
        self.bind("<Destroy>",self._on_destroy,add="+")

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._tab_drag.cancel()
        if self._catch_job is not None:
            self.after_cancel(self._catch_job)
            self._catch_job = None
        if self._notify_job is not None:
            self.after_cancel(self._notify_job)
            self._notify_job = None
        if self._focus_binding:
            try:
                self._root()._unbind(("bind","all","<FocusIn>"),self._focus_binding)
            except (tk.TclError,ValueError):
                pass
            self._focus_binding = None

    def _remember_tab_position(self, key, anchor):
        if anchor == key:
            return
        self._visual_order.remove(key)
        index = self._visual_order.index(anchor) if anchor in self._visual_order else len(self._visual_order)
        self._visual_order.insert(index,key)

    def add_scrolled(self, factory, text, **kw):
        host = _TabHost(self, background=C["bg"])
        header = ttk.Frame(host, padding=(10,3), style="PanelHeader.TFrame")
        title_label = ttk.Label(header, text="⠿ " + text + " · 끌어서 결합", style="PanelHeader.TLabel")
        title_label.pack(side="left")
        ttk.Button(header, text="탭으로 되돌리기", command=lambda:self.dock(str(host))).pack(side="right")
        ttk.Button(header, text="숨기기", command=lambda:self.set_visible(str(host), False)).pack(side="right", padx=4)
        browse = ttk.Menubutton(header, text="보기 ▾")
        browse.pack(side="right", padx=4)
        box = AutoScroll(host)
        box.pack(fill="both", expand=True)
        tab = factory(box.inner)
        tab.pack(fill="both", expand=True)
        slot = ttk.Frame(self)
        super().add(slot, text=text, **kw)
        key = str(host)
        self._slot_of[key], self._key_of[str(slot)] = str(slot), key
        slot.bind("<Configure>", self._slot_configure, add="+")
        self._inner_of[key] = str(tab)
        self._outer_of[str(tab)] = key
        self._order.append(key)
        self._visual_order.append(key)
        self._pages[key] = dict(host=host, box=box, header=header, browse=browse, slot=slot, placed=None,
                                title=text, options=dict(super().tab(slot)), detached=False,
                                visible=tk.BooleanVar(self, True), floating=tk.BooleanVar(self,False), geometry=None, close_handler=None)
        self._tab_drag.bind(title_label,key)
        self._tab_drag.bind(header,key)
        self._layout_hosts()
        return tab

    def _o(self, tab):
        if isinstance(tab, int):
            return self._order[tab]
        return self._outer_of.get(str(tab), str(tab)) if tab is not None else None

    # Pages are never unmapped on a tab switch: Tk would unmap and remap every widget
    # of both pages (hundreds of native windows, ~0.4 s). Unselected docked pages stay
    # mapped but parked far off-screen, so their coordinates never match a real point.
    _PARK = -30000

    def _n(self, key):
        return self._slot_of.get(str(key), key)

    def _k(self, native):
        return self._key_of.get(str(native), str(native))

    def _native_tabs(self):
        return [self._k(t) for t in super().tabs()]

    def _native_selected(self):
        cur = super().select()
        return self._k(cur) if cur else ""

    def _slot_configure(self, event):
        area = (event.x, event.y, event.width, event.height)
        if area != self._area and event.width > 1:
            self._area = area
            self._layout_hosts()

    # 창 크기가 바뀌면 보이는 탭만 바로 맞춘다. 숨긴 탭은 크기를 그대로 두고 위치만 옮기며,
    # 창을 멈춘 뒤 백그라운드에서 한 번에 하나씩 맞춘다 (창을 끄는 동안 위젯 수백 개를 다시 배치하지 않도록).
    _CATCH_UP_DELAY = 200

    def _place_host(self, record, want):
        if record["placed"] != want:
            record["host"].place(x=want[0], y=want[1], width=want[2], height=want[3])
            record["placed"] = want

    def _layout_hosts(self, _event=None):
        if self._area is None:
            return
        x, y, w, h = self._area
        selected = self._native_selected()
        for key, record in self._pages.items():
            if record["detached"]:
                continue
            if key == selected:
                self._place_host(record, (x, y, w, h))
                record["host"].lift()
            else:
                old = record["placed"] or (x, y, w, h)
                self._place_host(record, (self._PARK, y, old[2], old[3]))
        if any(not r["detached"] and k != selected and r["placed"] and r["placed"][2:] != (w, h)
               for k, r in self._pages.items()):
            if self._catch_job is not None:
                self.after_cancel(self._catch_job)
            self._catch_job = self.after(self._CATCH_UP_DELAY, self._catch_up)

    def _catch_up(self):
        self._catch_job = None
        if self._area is None:
            return
        x, y, w, h = self._area
        selected = self._native_selected()
        for key, record in self._pages.items():
            if record["detached"] or key == selected or record["placed"] is None:
                continue
            if record["placed"][2:] != (w, h):
                self._place_host(record, (self._PARK, y, w, h))
                self._catch_job = self.after_idle(self._catch_up)
                return

    def _notify(self):
        if self._notify_job is None:
            def emit():
                self._notify_job = None
                if self.winfo_exists():
                    self.event_generate("<<NotebookTabChanged>>")
            self._notify_job = self.after_idle(emit)

    def _track_focus(self, event):
        widget = event.widget
        page = None
        while isinstance(widget, tk.Misc):
            if str(widget) in self._pages:
                page = str(widget)
                break
            widget = widget.master
        old = self._active_popup
        if page is not None and not self._pages[page]["detached"] and page != self._native_selected() and self._park_job is None:
            self._park_job = self.after_idle(self._leave_parked_page)
        if page is not None:
            record = self._pages[page]
            self._active_popup = page if (record["detached"] and record["visible"].get()) or is_panel_window(self._root(),event.widget.winfo_toplevel()) else None
        else:
            try:
                if event.widget.winfo_toplevel() == self.winfo_toplevel():
                    self._active_popup = None
            except (AttributeError, tk.TclError):
                pass
        # 포커스만 바뀐 것이므로 탭 전환 알림(on_tab 재로딩)을 보내지 않는다.
        # 탭 선택·분리·숨김 등 실제 변화는 각각 _notify()로 알린다.

    def _leave_parked_page(self):
        self._park_job = None
        try:
            page = self.page_for_widget(self.focus_get())
        except (KeyError, tk.TclError):
            return
        if page is None or self._pages[page]["detached"] or page == self._native_selected():
            return
        current = self._pages.get(self._native_selected())
        target = current["host"].tk_focusNext() if current else None
        if target is None or not str(target).startswith(str(current["host"]) + "."):
            target = self
        target.focus_set()

    def select(self, tab_id=None):
        if tab_id is None:
            popup = self._pages.get(self._active_popup)
            if popup:
                return self._inner_of[self._active_popup]
            cur = self._native_selected()
            return self._inner_of.get(cur, cur)
        key = self._o(tab_id)
        record = self._pages.get(key)
        if record is None:
            return super().select(key)
        self.set_visible(key, True)
        if record["detached"]:
            self._active_popup = key
            record["host"].lift()
            record["host"].focus_set()
            self._notify()
            return None
        self._active_popup = None
        result = super().select(self._n(key))
        self._layout_hosts()
        return result

    def tab(self, tab_id, option=None, **kw):
        key = self._o(tab_id)
        record = self._pages.get(key)
        if record and record["detached"]:
            record["options"].update(kw)
            return record["options"].get(option) if option else dict(record["options"])
        result = super().tab(self._n(key), option, **kw)
        if record and kw:
            record["options"].update(kw)
        return result

    def index(self, tab_id):
        if tab_id == "end":
            return len(self._order)
        if isinstance(tab_id, str) and tab_id.startswith("@"):
            return self._order.index(self._native_tabs()[super().index(tab_id)])
        if tab_id == "current":
            tab_id = self.select()
        key = self._o(tab_id)
        if key in self._order:
            return self._order.index(key)
        return super().index(self._n(key))

    def tabs(self):
        return tuple(self._inner_of[key] for key in self._order)

    def is_detached_window(self, window):
        record = self._pages.get(str(window))
        return bool(record and record["detached"])

    def page_for_widget(self, widget):
        while isinstance(widget,tk.Misc):
            if str(widget) in self._pages:
                return str(widget)
            widget = widget.master
        return None

    def is_visible(self, tab_id):
        key = self._o(tab_id)
        record = self._pages.get(key)
        if record and record["visible"].get() and (record["detached"] or self._native_selected() == key):
            return True
        return any(self.page_for_widget(group)==key and any(r["detached"] and r["visible"].get() for r in group._records.values()) for group in panel_groups(self._root()))

    def _native_tab_at(self, x, y):
        try:
            index = self.tk.call(self._w,"index",f"@{int(x)},{int(y)}")
            if str(index) == "":
                return None
            return self._native_tabs()[int(index)]
        except (tk.TclError,ValueError,IndexError):
            return None

    def _tab_press(self, event):
        key = self._native_tab_at(event.x,event.y)
        if key is None:
            self._tab_drag.cancel()
            return
        self._tab_drag.start(event,key)

    def _tab_strip_height(self):
        selected = self._native_selected()
        current = self._pages.get(selected)
        if current and not current["detached"] and current["host"].winfo_ismapped():
            return max(1,current["host"].winfo_rooty()-self.winfo_rooty())
        import tkinter.font as tkfont
        spec = ttk.Style(self).lookup("TNotebook.Tab","font") or "TkDefaultFont"
        if self._tab_font is None or str(spec) != self._tab_font_spec:
            self._tab_font = tkfont.Font(font=spec)
            self._tab_font_spec = str(spec)
        return self._tab_font.metrics("linespace")+14

    def _tab_span(self, key, x, y):
        # Locate the hovered tab's two edges without changing notebook state.
        low,high = 0,int(x)
        while low < high:
            middle = (low+high)//2
            if self._native_tab_at(middle,y) == key:
                high = middle
            else:
                low = middle+1
        left = low
        low,high = int(x),self.winfo_width()
        while low < high:
            middle = (low+high)//2
            if self._native_tab_at(middle,y) == key:
                low = middle+1
            else:
                high = middle
        return left,low

    def _probe_tab(self, key, x, y):
        if not self.winfo_ismapped() or key not in self._pages:
            return None
        left,top = self.winfo_rootx(),self.winfo_rooty()
        width,height = self.winfo_width(),self.winfo_height()
        bar_height = self._tab_strip_height()
        # The content area is a tear-off area; only the tab strip accepts docking.
        if not (left <= x < left+width and top <= y < top+bar_height):
            return None
        if not pointer_in_workspace(self,x,y,self._tab_drag):
            return None
        native = self._native_tabs()
        local_x, row = x-left,max(0,bar_height//2)
        hovered = self._native_tab_at(local_x,row)
        anchor = "end"
        indicator = left+width-4
        if hovered is not None:
            start,end = self._tab_span(hovered,local_x,row)
            before = local_x < (start+end)/2
            index = native.index(hovered)
            anchor = hovered if before else native[index+1] if index+1<len(native) else "end"
            indicator = left+(start if before else end)
        elif native:
            first_x = next((px for px in range(0,min(width,80),4) if self._native_tab_at(px,row) is not None),None)
            if first_x is not None and local_x < first_x:
                anchor,indicator = native[0],left+first_x
            else:
                for px in range(min(width-1,local_x),-1,-4):
                    last = self._native_tab_at(px,row)
                    if last is not None:
                        _,end = self._tab_span(last,px,row)
                        indicator = left+end
                        break
        caption = "놓으면 이 위치에 탭으로 결합" if self._pages[key]["detached"] else "놓으면 이 위치로 탭 순서 변경"
        return ("dock",anchor),(indicator-2,top,4,bar_height),caption

    def _finish_tab(self, key, x, y, target):
        if key not in self._pages:
            return
        if target is None:
            self.detach(key,position=(x,y))
            return
        _,anchor = target if isinstance(target,tuple) else ("dock",target)
        record = self._pages[key]
        native = self._native_tabs()
        if not record["detached"]:
            if anchor == key:
                return
            others = [page for page in native if page != key]
            desired = len(others) if anchor in (None,"end") else others.index(anchor) if anchor in others else None
            if desired is None or native.index(key) == desired:
                return
            super().insert("end" if desired==len(others) else desired,record["slot"])
            self._remember_tab_position(key,anchor)
            super().select(self._n(key))
            self._layout_hosts()
            self._active_popup = None
        else:
            self.dock(key)
            if anchor not in (None,key):
                others = [page for page in self._native_tabs() if page != key]
                desired = len(others) if anchor == "end" else others.index(anchor) if anchor in others else None
                if desired is not None:
                    super().insert("end" if desired==len(others) else desired,record["slot"])
                    self._remember_tab_position(key,anchor)

    def set_visible(self, tab_id, show):
        key = self._o(tab_id)
        record = self._pages[key]
        previous = record["options"].get("state", "normal") != "hidden"
        record["visible"].set(bool(show))
        record["options"]["state"] = "normal" if show else "hidden"
        if record["detached"]:
            if show:
                if record["host"].state() == "withdrawn":
                    record["host"].deiconify()
                record["host"].lift()
            else:
                record["host"].withdraw()
        elif previous != bool(show):
            super().tab(self._n(key), state="normal" if show else "hidden")
            self._layout_hosts()
        if not show and self._active_popup == key:
            self._active_popup = None
        if previous != bool(show):
            self._notify()

    def detach(self, tab_id=None, position=None):
        key = self._o(tab_id if tab_id is not None else self.select())
        record = self._pages.get(key)
        if record is None:
            return
        if record["detached"]:
            if position is not None:
                position_window(record["host"],*position)
            self.select(key)
            return
        host = record["host"]
        native = self._native_tabs()
        old_index = native.index(key)
        record["dock_before"] = native[old_index+1] if old_index+1<len(native) else "end"
        record["dock_index"] = old_index
        old_selected,old_active = self._native_selected(),self._active_popup
        old_options = dict(super().tab(self._n(key)))
        record["options"] = dict(old_options)
        super().forget(self._n(key))
        host.place_forget()
        record["placed"] = None
        try:
            host.update_idletasks()
            self.tk.call("wm", "manage", host)
            host.withdraw()
            record["detached"] = True
            record["floating"].set(True)
            record["header"].pack(fill="x", before=record["box"])
            host.title(record["title"] + " — 슬더스2 모드 메이커")
            if record["close_handler"] is None:
                record["close_handler"] = host.register(lambda:self.dock(key))
            host.protocol("WM_DELETE_WINDOW", record["close_handler"])
            host.minsize(480, 320)
            prepare_float_window(host,self.winfo_toplevel(),(1200,850),record["geometry"],position)
            host.deiconify()
            self.select(key)
        except Exception:
            # A failed native transition must never leave a page forgotten and invisible.
            try:
                forget_floating_window(host)
            except tk.TclError:
                pass
            record["header"].pack_forget()
            record["detached"] = False
            record["floating"].set(False)
            record["options"] = old_options
            record["visible"].set(old_options.get("state","normal") != "hidden")
            super().insert(min(old_index,len(super().tabs())),record["slot"],**old_options)
            self._active_popup = old_active
            if old_selected == key:
                super().select(self._n(key))
            self._layout_hosts()
            self._notify()
            raise

    def dock(self, tab_id, select=True):
        key = self._o(tab_id)
        record = self._pages[key]
        if record["detached"]:
            host = record["host"]
            record["geometry"] = host.geometry()
            host.withdraw()
            try:
                forget_floating_window(host)
                record["header"].pack_forget()
                native = set(self._native_tabs())
                after = self._visual_order[self._visual_order.index(key)+1:]
                before = next((page for page in after if page in native),"end")
                options = dict(record["options"])
                options["state"] = "normal" if record["visible"].get() else "hidden"
                super().insert(self._n(before), record["slot"], **options)
                record["detached"] = False
                record["floating"].set(False)
                self._layout_hosts()
            except Exception:
                if key in self._native_tabs():
                    super().forget(self._n(key))
                host.place_forget()
                record["placed"] = None
                self.tk.call("wm","manage",host)
                host.withdraw()
                record["header"].pack(fill="x",before=record["box"])
                record["detached"] = True
                record["floating"].set(True)
                host.protocol("WM_DELETE_WINDOW",record["close_handler"])
                host.title(record["title"] + " — 슬더스2 모드 메이커")
                host.minsize(480,320)
                host.geometry(record["geometry"])
                if record["visible"].get():
                    host.deiconify()
                raise
        if self._active_popup == key:
            self._active_popup = None
        if select:
            self.select(key)
        self._notify()

    def dock_all(self):
        for key in self._order:
            self.dock(key, select=False)

    def reset_layout(self):
        self._visual_order[:] = self._order
        self.dock_all()
        for index,key in enumerate(self._order):
            super().insert(index,self._pages[key]["slot"])
        self.show_all()

    def show_all(self):
        for key in self._order:
            self.set_visible(key, True)

    def install_view_menu(self, menu):
        menu.add_separator()
        toggles = CheckedMenu(menu, tearoff=False)
        detach = CheckedMenu(menu, tearoff=False)
        for key in self._order:
            record = self._pages[key]
            toggles.add_checkbutton(label=record["title"], variable=record["visible"],
                                   command=lambda key=key:self.set_visible(key, self._pages[key]["visible"].get()))
            detach.add_checkbutton(label=record["title"], variable=record["floating"],
                                   command=lambda key=key:self.detach(key) if self._pages[key]["floating"].get() else self.dock(key))
        menu.add_cascade(label="작업 탭 표시", menu=toggles)
        menu.add_cascade(label="작업 탭 분리 (체크 = 분리됨)", menu=detach)
        menu.add_command(label="현재 탭을 팝업으로 분리", command=self.detach)
        menu.add_command(label="모든 팝업을 탭으로 합치기", command=self.dock_all)
        menu.add_command(label="모든 작업 탭 표시", command=self.show_all)
        for key in self._order:
            record = self._pages[key]
            popup_menu = CheckedMenu(record["browse"], tearoff=False)
            popup_menu.add_command(label="모든 작업 탭 활성화", command=self.show_all)
            popup_menu.add_separator()
            for other in self._order:
                other_record = self._pages[other]
                popup_menu.add_checkbutton(label=other_record["title"], variable=other_record["visible"],
                    command=lambda other=other:self.set_visible(other, self._pages[other]["visible"].get()))
            install_panel_menu(popup_menu,self._root())
            record["browse"].configure(menu=popup_menu)

    def _context_menu(self, event):
        try:
            key = self._o(self.index(f"@{event.x},{event.y}"))
        except (tk.TclError, ValueError, IndexError):
            return
        menu = tk.Menu(self, tearoff=False)
        menu.add_command(label="팝업으로 분리", command=lambda:self.detach(key))
        menu.add_command(label="숨기기", command=lambda:self.set_visible(key, False))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()


# ---------------------------------------------------------------------------
# 스크롤 직후 새로 드러난 줄을 같은 처리 안에서 그린다
# ---------------------------------------------------------------------------
_presenting = False


def present_scroll(canvas):
    """Paint the strip a scroll just revealed before the frame reaches the screen.

    Moving a Canvas window on Windows copies the old pixels, so the revealed strip
    shows stale copies until Tk handles WM_PAINT on a later loop pass. Only
    regions Windows already invalidated are painted (no extra invalidation).
    Canvases without embedded widgets are double-buffered and need nothing.
    """
    global _presenting
    if _presenting or sys.platform != "win32":
        return
    try:
        if not canvas.winfo_children():
            return
    except tk.TclError:
        return
    _presenting = True
    try:
        canvas.update_idletasks()
        _user32().RedrawWindow(canvas.winfo_id(), None, None, 0x0100 | 0x0080)  # UPDATENOW | ALLCHILDREN
        deadline = time.perf_counter() + 0.05
        for _ in range(400):
            if not canvas.tk.dooneevent(_tkinter.WINDOW_EVENTS | _tkinter.DONT_WAIT):
                break
            if time.perf_counter() > deadline:
                break
        canvas.update_idletasks()
    except (tk.TclError, OSError, AttributeError):
        pass
    finally:
        _presenting = False


def scroll_command(canvas, horizontal=False):
    """Scrollbar command for a Canvas that holds widgets (moves, then paints the new strip)."""
    def command(*args):
        (canvas.xview if horizontal else canvas.yview)(*args)
        present_scroll(canvas)
    return command


def _user32():
    import ctypes
    return ctypes.windll.user32


# ---------------------------------------------------------------------------
# 마우스 휠: 포인터 아래에서 스크롤할 수 있는 것을 찾아 굴린다 (Shift = 가로, Ctrl = 화면 배율)
# ---------------------------------------------------------------------------
def _can_scroll(w, horizontal):
    try:
        a, b = (w.xview() if horizontal else w.yview())
    except (AttributeError, tk.TclError, TypeError, ValueError):
        return False
    return a > 0.0001 or b < 0.9999


def install_wheel(root, on_zoom=None):
    acc = {}

    def steps(e, key):
        acc[key] = acc.get(key,0)+e.delta
        n = int(acc[key] / 120)
        if n:
            acc[key] -= n * 120
            return -n
        return 0

    def handler(e, horizontal=False):
        try:
            w = root.winfo_containing(e.x_root, e.y_root)
        except (tk.TclError, KeyError):
            w = None
        if w is None:   # 포인터 아래를 못 찾으면 이벤트를 받은 위젯
            w = e.widget
            if isinstance(w, str):
                try:
                    w = root.nametowidget(w)
                except (KeyError, tk.TclError):
                    return None
        if w is None:
            return None
        seq = "<Shift-MouseWheel>" if horizontal else "<MouseWheel>"
        first = w
        protect_value = isinstance(w,(ttk.Combobox,ttk.Spinbox,tk.Spinbox))
        # Scrolling over a form input must not change its selected value.
        # Popup listboxes and text/list widgets keep their own native scrolling.
        if protect_value:
            w = w.master
        elif root.bind_class(w.winfo_class(),seq):
            return None
        while w is not None:
            if _can_scroll(w, horizontal):
                # 글 상자·목록처럼 자체 휠 동작이 있는 위젯은 그 동작이 이미 굴렸다
                if w is first and root.bind_class(w.winfo_class(), seq):
                    return None
                n = steps(e,(str(w),horizontal))
                if n:
                    (w.xview_scroll if horizontal else w.yview_scroll)(n, "units")
                    if isinstance(w, tk.Canvas):
                        present_scroll(w)
                return "break"
            w = w.master
        return "break" if protect_value else None

    def zoom(e):
        if on_zoom:
            n = steps(e,("zoom",False))
            if n:
                on_zoom(-n)
        return "break"

    tag = "MakerWheel"+str(id(root))
    root.bind_class(tag,"<MouseWheel>",lambda e:handler(e,False))
    root.bind_class(tag,"<Shift-MouseWheel>",lambda e:handler(e,True))
    root.bind_class(tag,"<Control-MouseWheel>",zoom)
    def attach(widget):
        if isinstance(widget,str):
            try:
                widget = root.nametowidget(widget)
            except (KeyError,tk.TclError):
                return
        tags = widget.bindtags()
        if tag not in tags:
            widget.bindtags((tag,)+tags)
    def walk(widget):
        attach(widget)
        for child in widget.winfo_children():
            walk(child)
    walk(root)
    root.bind_all("<Map>",lambda e:attach(e.widget),add="+")
    # Also guard native input classes: Windows may deliver wheel input to a
    # focused control before newly mapped widgets receive their custom tag.
    for cls in ("TCombobox","TSpinbox","Spinbox"):
        root.bind_class(cls,"<MouseWheel>",lambda e:handler(e,False))
        root.bind_class(cls,"<Shift-MouseWheel>",lambda e:handler(e,True))
    for cls in ("Text","Listbox","Treeview","TCombobox","TSpinbox","Spinbox"):
        root.bind_class(cls,"<Control-MouseWheel>",zoom)

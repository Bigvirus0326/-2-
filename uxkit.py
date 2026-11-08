"""
편의 기능 모음 — 테마, 말풍선 도움말, 되돌리기 기록, 검색(초성 포함), 목록 아이콘, 검색칸, 전체 찾기 창, 일괄 수정 창.
"""
from __future__ import annotations

import json
import tkinter as tk
from tkinter import messagebox, ttk

from winpos import center_window

# ---------------------------------------------------------------------------
# 테마
# ---------------------------------------------------------------------------
C = {
    "bg": "#f3f4f7", "surface": "#ffffff", "line": "#d6d9e0", "line2": "#c3c8d2", "text": "#1d2129", "muted": "#6b7280",
    "accent": "#2f6bd8", "accent_hi": "#2559b8", "accent_soft": "#dce7fb", "hover": "#eef1f6", "warn": "#b4572f",
    "console": "#1d1f24", "console_fg": "#d7dae0",
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
    st.configure("TFrame", background=C["bg"])
    st.configure("Card.TFrame", background=C["surface"], relief="solid", borderwidth=1)
    st.configure("TLabel", background=C["bg"], foreground=C["text"])
    st.configure("Muted.TLabel", foreground=C["muted"], font=fs)
    st.configure("Head.TLabel", font=(FONT, size + 1, "bold"))
    st.configure("Count.TLabel", foreground=C["muted"], font=fs)
    st.configure("Help.TLabel", foreground=C["accent"], font=fs)
    st.configure("TLabelframe", background=C["bg"], bordercolor=C["line"], relief="solid", borderwidth=1)
    st.configure("TLabelframe.Label", background=C["bg"], foreground=C["accent_hi"], font=fb)
    st.configure("TSeparator", background=C["line"])

    st.configure("TButton", background=C["surface"], foreground=C["text"], bordercolor=C["line2"], lightcolor=C["surface"],
                 darkcolor=C["surface"], padding=(10, 4), relief="flat", focusthickness=0)
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

    st.configure("TCheckbutton", background=C["bg"], indicatorbackground=C["surface"], indicatorforeground=C["accent"],
                 bordercolor=C["line2"])
    st.map("TCheckbutton", background=[("active", C["bg"])], indicatorbackground=[("selected", C["surface"])])
    st.configure("TRadiobutton", background=C["bg"], indicatorbackground=C["surface"], indicatorforeground=C["accent"],
                 bordercolor=C["line2"])
    st.map("TRadiobutton", background=[("active", C["bg"])])

    for w in ("TEntry", "TCombobox", "TSpinbox"):
        st.configure(w, fieldbackground=C["surface"], background=C["surface"], bordercolor=C["line2"],
                     lightcolor=C["surface"], darkcolor=C["surface"], padding=(5, 3), arrowcolor=C["muted"])
        st.map(w, bordercolor=[("focus", C["accent"])], lightcolor=[("focus", C["accent_soft"])],
               fieldbackground=[("readonly", C["surface"]), ("disabled", C["bg"])],
               foreground=[("disabled", "#9aa0aa")], arrowcolor=[("active", C["accent"])])
    st.configure("Placeholder.TEntry", foreground="#9aa0aa")
    root.option_add("*TCombobox*Listbox.background", C["surface"])
    root.option_add("*TCombobox*Listbox.selectBackground", C["accent_soft"])
    root.option_add("*TCombobox*Listbox.font", f)

    st.configure("TNotebook", background=C["bg"], bordercolor=C["line"], tabmargins=(6, 6, 6, 0), padding=0)
    st.configure("TNotebook.Tab", background=C["bg"], foreground=C["muted"], bordercolor=C["bg"], lightcolor=C["bg"],
                 padding=(10, 5), font=f)
    st.map("TNotebook.Tab", background=[("selected", C["surface"]), ("active", C["hover"])],
           foreground=[("selected", C["accent_hi"]), ("active", C["text"])],
           bordercolor=[("selected", C["line"])], lightcolor=[("selected", C["surface"])],
           expand=[("selected", (0, 2, 0, 0))])

    st.configure("Treeview", background=C["surface"], fieldbackground=C["surface"], foreground=C["text"],
                 bordercolor=C["line"], rowheight=int(root.winfo_fpixels("1i") / 96 * 26), font=f)
    st.map("Treeview", background=[("selected", C["accent_soft"])], foreground=[("selected", C["text"])])
    st.configure("Treeview.Heading", background=C["bg"], foreground=C["muted"], bordercolor=C["line"], font=fs, relief="flat")
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

    def _enter(self, _e=None):
        self._cancel()
        self.job = self.w.after(self.delay, self._show)

    def _leave(self, _e=None):
        self._cancel()
        if self.tip is not None:
            self.tip.destroy()
            self.tip = None

    def _cancel(self):
        if self.job:
            try:
                self.w.after_cancel(self.job)
            except tk.TclError:
                pass
            self.job = None

    def _show(self):
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
    "card:tag": "타격·수비 같은 게임 태그입니다. 다른 카드가 '타격 카드' 등을 찾을 때 쓰입니다.",
    "card:frame_style": "카드 틀·그림 테두리·제목 띠의 디자인. '캐릭터 기본 따르기'면 캐릭터 탭에서 고른 테두리를 씁니다. "
                        "'편집…'에서 색을 바꾸거나 직접 그린 그림을 넣을 수 있습니다.",
    "card:upgrade_add_keyword": "강화하면 붙는 키워드입니다 (예: 강화하면 보존).",
    "card:upgrade_remove_keyword": "강화하면 없어지는 키워드입니다 (예: 강화하면 소멸이 사라짐). 위 키워드 줄에서 켜 둔 키워드여야 합니다.",
    "relic:rarity": "유물이 어디서 나오는지 정합니다. 시작 유물은 캐릭터가 처음부터 가지고 시작합니다.",
    "relic:trigger": "유물 효과가 발동하는 때입니다.",
    "played_filter": "어떤 종류의 카드를 썼을 때 셀지 고릅니다.",
    "played_every": "카드를 이 장수만큼 쓸 때마다 한 번 발동합니다.",
    "enemy_mode": "'적' 대상 효과가 누구에게 갈지 정합니다 (모든 적 / 무작위 적).",
    "potion:rarity": "물약 보상에 나오는 확률입니다.",
    "potion:target": "물약을 쓸 때 대상을 고를지 정합니다.",
    "power:type": "버프는 좋은 효과(초록 테두리), 디버프는 나쁜 효과(빨간 테두리)입니다.",
    "power:stack": "같은 파워를 또 받으면 수치를 더할지, 무시할지 등을 정합니다.",
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
    """안쪽(inner)이 창보다 크면 오른쪽·아래 스크롤바가 나타나고, 창이 더 크면 안쪽을 창에 맞게 늘린다."""

    def __init__(self, master, x=True, y=True, **kw):
        super().__init__(master, **kw)
        self.x, self.y = x, y
        self.canvas = tk.Canvas(self, highlightthickness=0, borderwidth=0)
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.hsb = ttk.Scrollbar(self, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vsb.set, xscrollcommand=self.hsb.set)
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
        self.inner.bind("<Configure>", self._later, add="+")
        self.canvas.bind("<Configure>", self._later, add="+")

    def _later(self, _e=None):
        if self._job is None:
            self._job = self.after_idle(self._sync)

    def _sync(self):
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
        self.canvas.itemconfigure(self._win, width=w, height=h)
        self.canvas.configure(scrollregion=(0, 0, w, h))
        for bar, need in ((self.hsb, need_x), (self.vsb, need_y)):
            if need and not bar.winfo_ismapped():
                bar.grid()
            elif not need and bar.winfo_ismapped():
                bar.grid_remove()
        if not need_x:
            self.canvas.xview_moveto(0)
        if not need_y:
            self.canvas.yview_moveto(0)


class ScrollNotebook(ttk.Notebook):
    """탭마다 AutoScroll 을 씌우는 Notebook. select()/tab()/index() 는 안쪽 탭 위젯으로 주고받는다."""

    def __init__(self, master, **kw):
        super().__init__(master, **kw)
        self._inner_of, self._outer_of = {}, {}

    def add_scrolled(self, factory, text, **kw):
        box = AutoScroll(self)
        tab = factory(box.inner)
        tab.pack(fill="both", expand=True)
        super().add(box, text=text, **kw)
        self._inner_of[str(box)] = str(tab)
        self._outer_of[str(tab)] = str(box)
        return tab

    def _o(self, t):
        return t if t is None or isinstance(t, int) else self._outer_of.get(str(t), t)

    def select(self, tab_id=None):
        if tab_id is None:
            cur = super().select()
            return self._inner_of.get(str(cur), cur)
        return super().select(self._o(tab_id))

    def tab(self, tab_id, option=None, **kw):
        return super().tab(self._o(tab_id), option, **kw)

    def index(self, tab_id):
        return super().index(self._o(tab_id))

    def tabs(self):
        return tuple(self._inner_of.get(str(t), t) for t in super().tabs())


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
    acc = {"d": 0}

    def steps(e):
        acc["d"] += e.delta
        n = int(acc["d"] / 120)
        if n:
            acc["d"] -= n * 120
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
        while w is not None:
            if _can_scroll(w, horizontal):
                # 글 상자·목록처럼 자체 휠 동작이 있는 위젯은 그 동작이 이미 굴렸다
                if w is first and root.bind_class(w.winfo_class(), seq):
                    return None
                n = steps(e)
                if n:
                    (w.xview_scroll if horizontal else w.yview_scroll)(n, "units")
                return "break"
            w = w.master
        return None

    def zoom(e):
        if on_zoom:
            on_zoom(1 if e.delta > 0 else -1)
        return "break"

    root.bind_all("<MouseWheel>", lambda e: handler(e, False))
    root.bind_all("<Shift-MouseWheel>", lambda e: handler(e, True))
    root.bind_all("<Control-MouseWheel>", zoom)

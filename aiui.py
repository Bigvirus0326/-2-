"""AI(채팅) 복붙 연동 창 — ① 설명서 복사  ② AI 결과 붙여넣기 (검사·미리보기·합치기)."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import aiguide as AG
import aipaste as AP
import uxkit as UX
from winpos import center_window

TITLE = "AI로 만들기"


def _text(parent, height, **kw):
    fr = ttk.Frame(parent)
    t = tk.Text(fr, height=height, wrap="word", undo=True, padx=6, pady=4, **kw)
    sb = ttk.Scrollbar(fr, command=t.yview)
    t.configure(yscrollcommand=sb.set)
    t.pack(side="left", fill="both", expand=True)
    sb.pack(side="right", fill="y")
    return fr, t


class GuidePage(ttk.Frame):
    """요청을 적고 → 설명서(요청 포함)를 복사 → ChatGPT/Claude 에 붙여넣기."""

    def __init__(self, app, host):
        super().__init__(host.tabs)
        self.app = app
        self.host = host
        self.configure(padding=12)
        ttk.Label(self, text="ChatGPT · Claude · Gemini 같은 채팅 AI에게 카드·유물·물약·파워·기믹을 만들게 합니다.",
                  style="Head.TLabel").pack(anchor="w")
        steps = ("1. 아래에 만들고 싶은 것을 적고 '설명서 복사'를 누릅니다.\n"
                 "2. AI 채팅창에 붙여넣고 보냅니다. (설명서에 형식·선택지·지금 프로젝트의 ID 가 다 들어 있습니다)\n"
                 "3. AI 의 답을 통째로 복사해서 '② AI 결과 붙여넣기'에 넣으면 검사·미리보기 후 프로젝트에 들어갑니다.")
        ttk.Label(self, text=steps, style="Muted.TLabel", justify="left").pack(anchor="w", pady=(4, 8))
        ttk.Label(self, text="AI에게 시킬 내용").pack(anchor="w")
        fr, self.req = _text(self, 6)
        fr.pack(fill="both", expand=True)
        self.req.insert("1.0", "예) 불씨를 쌓았다가 터뜨리는 공격 카드 3장과, 불씨가 10 이상이면 에너지를 주는 유물 1개를 만들어줘. "
                               "한국어·영어·중국어 이름 모두.")
        self.req.bind("<FocusIn>", self._clear_example)
        self._example = True
        opt = ttk.Frame(self)
        opt.pack(fill="x", pady=(8, 0))
        self.blocks = tk.BooleanVar(value=True)
        self.proj = tk.BooleanVar(value=True)
        UX.tip(ttk.Checkbutton(opt, text="블록 코딩 설명 포함", variable=self.blocks, command=self._size),
               "반복·조건·손패 조작·소환 같은 복잡한 능력을 만들 수 있게 합니다. 끄면 설명서가 짧아집니다.").pack(side="left")
        UX.tip(ttk.Checkbutton(opt, text="지금 프로젝트 목록 포함", variable=self.proj, command=self._size),
               "있는 카드·파워·태그·소환수 ID 를 알려줘서 겹치지 않고, 참조할 수 있게 합니다.").pack(side="left", padx=12)
        self.size_lbl = ttk.Label(opt, text="", style="Muted.TLabel")
        self.size_lbl.pack(side="right")
        bf = ttk.Frame(self)
        bf.pack(fill="x", pady=(10, 0))
        ttk.Button(bf, text="📋 설명서 복사", style="Accent.TButton", command=self.copy).pack(side="left")
        ttk.Button(bf, text="파일로 저장…", command=self.save).pack(side="left", padx=6)
        ttk.Button(bf, text="② AI 결과 붙여넣기 →", command=self.open_paste).pack(side="left", padx=6)
        ttk.Button(bf, text="닫기", command=self.host.destroy).pack(side="right")
        self.status = ttk.Label(self, text="", foreground="#2d6a4f")
        self.status.pack(anchor="w", pady=(6, 0))
        self.bind("<Escape>", lambda _e: self.host.destroy())
        self._size()

    def _clear_example(self, _e=None):
        if self._example:
            self._example = False
            self.req.delete("1.0", "end")

    def _request(self):
        return "" if self._example else self.req.get("1.0", "end").strip()

    def prompt(self):
        return AG.build_prompt(self.app.project, self._request(), self.blocks.get(), self.proj.get())

    def _size(self):
        n = len(self.prompt())
        self.size_lbl.configure(text=f"설명서 길이 약 {n:,}자")

    def copy(self):
        text = self.prompt()
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status.configure(text=f"복사했습니다 ({len(text):,}자). AI 채팅창에 붙여넣고 보내세요."
                                   + ("" if self._request() else "  ※ 요청을 비워 두었으니 붙여넣은 뒤 끝에 요청을 적으세요."))

    def save(self):
        p = filedialog.asksaveasfilename(parent=self, defaultextension=".md", initialfile="sts2_ai_guide.md",
                                         filetypes=[("Markdown", "*.md"), ("텍스트", "*.txt")])
        if p:
            with open(p, "w", encoding="utf-8") as f:
                f.write(self.prompt())
            self.status.configure(text=f"저장했습니다: {p}")

    def open_paste(self):
        self.host.tabs.select(self.host.paste)


class PastePage(ttk.Frame):
    """AI 답 붙여넣기 → 읽기·자동 고침 → 검사 → 미리보기 → 넣기."""

    def __init__(self, app, host, text=""):
        super().__init__(host.tabs)
        self.app = app
        self.host = host
        self.configure(padding=10)
        self.patch = None
        self.errors, self.warnings = [], []
        self._photo = None
        self._job = None

        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="AI 의 답을 통째로 붙여 넣으세요 (설명 글이 섞여 있어도 JSON 부분만 읽습니다).",
                  style="Head.TLabel").pack(side="left")
        ttk.Button(top, text="① 설명서 다시 복사…", command=lambda:self.host.tabs.select(self.host.guide)).pack(side="right")
        fr, self.src = _text(self, 7, font=("Consolas", 10))
        fr.pack(fill="x", pady=(4, 4))
        self.src.bind("<<Modified>>", self._modified)
        bf = ttk.Frame(self)
        bf.pack(fill="x")
        ttk.Button(bf, text="📋 클립보드에서 붙여넣기", command=self.paste_clip).pack(side="left")
        ttk.Button(bf, text="다시 읽기", command=self.read).pack(side="left", padx=6)
        self.keep = tk.BooleanVar(value=False)
        UX.tip(ttk.Checkbutton(bf, text="같은 ID 는 바꾸지 말고 새 ID 로 추가", variable=self.keep, command=self.recheck),
               "끄면(기본) AI 가 기존 항목과 같은 ID 를 쓴 경우 그 항목을 AI 버전으로 바꿉니다 (Ctrl+Z 로 되돌릴 수 있음).").pack(side="left", padx=12)

        mid = ttk.PanedWindow(self, orient="horizontal")
        mid.pack(fill="both", expand=True, pady=(8, 0))
        lf = ttk.Frame(mid)
        mid.add(lf, weight=1)
        ttk.Label(lf, text="읽은 항목 (더블클릭 = 넣기/빼기)").pack(anchor="w")
        self.tree = ttk.Treeview(lf, columns=("take", "kind", "id", "state"), show="tree headings", height=8,
                                 selectmode="browse")
        for c, t, w in (("#0", "이름", 170), ("take", "넣기", 44), ("kind", "종류", 56), ("id", "ID", 130), ("state", "상태", 110)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, stretch=c in ("#0", "id"))
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self.show())
        self.tree.bind("<Double-Button-1>", self.toggle)
        ttk.Label(lf, text="문제 · 자동으로 고친 것").pack(anchor="w", pady=(8, 0))
        mf, self.msg = _text(lf, 8)
        mf.pack(fill="both", expand=True)
        self.msg.tag_configure("err", foreground="#c0392b")
        self.msg.tag_configure("warn", foreground="#b4572f")
        self.msg.tag_configure("fix", foreground="#2d6a4f")
        self.msg.tag_configure("head", font=(UX.FONT, 10, "bold"))

        rf = ttk.Frame(mid)
        mid.add(rf, weight=0)
        pv = ttk.Frame(rf)
        pv.pack(fill="x")
        ttk.Label(pv, text="미리보기", style="Head.TLabel").pack(side="left")
        self.lang = tk.StringVar(value="ko")
        for v, l in (("zh", "中文"), ("en", "EN"), ("ko", "한국어")):
            ttk.Radiobutton(pv, text=l, value=v, variable=self.lang, command=self.show).pack(side="right")
        self.up = tk.BooleanVar(value=False)
        ttk.Checkbutton(pv, text="강화(+)", variable=self.up, command=self.show).pack(side="right", padx=6)
        self.canvas = tk.Canvas(rf, width=int(300 * app.ui), height=int(380 * app.ui), background="#1d1f24", highlightthickness=0)
        self.canvas.pack(pady=4)
        self.desc = ttk.Label(rf, text="", wraplength=int(300 * app.ui), justify="left")
        self.desc.pack(anchor="w")

        bot = ttk.Frame(self)
        bot.pack(fill="x", pady=(10, 0))
        self.fix_btn = UX.tip(ttk.Button(bot, text="✉ AI에게 보낼 수정 요청 복사", command=self.copy_fix),
                              "오류·경고를 AI 에게 그대로 보낼 문장으로 복사합니다. AI 채팅창에 붙여넣으면 고친 JSON 을 다시 줍니다.")
        self.fix_btn.pack(side="left")
        self.dep_btn = ttk.Button(bot, text="필요한 항목 함께 선택", command=self.include_dependencies)
        self.summary = ttk.Label(bot, text="", style="Muted.TLabel")
        self.summary.pack(side="left", padx=10)
        ttk.Button(bot, text="닫기", command=self.host.destroy).pack(side="right")
        self.ok_btn = ttk.Button(bot, text="✔ 프로젝트에 넣기", style="Accent.TButton", command=self.commit)
        self.ok_btn.pack(side="right", padx=6)
        self.bind("<Escape>", lambda _e: self.host.destroy())
        if text:
            self.src.insert("1.0", text)
            self.read()
        else:
            self._render_empty()
        self.src.focus_set()

    # ---- 읽기 ----
    def paste_clip(self):
        try:
            t = self.clipboard_get()
        except tk.TclError:
            t = ""
        if not t.strip():
            messagebox.showinfo(TITLE, "클립보드가 비어 있습니다. AI 의 답을 복사한 뒤 눌러 주세요.", parent=self)
            return
        self.src.delete("1.0", "end")
        self.src.insert("1.0", t)
        self.read()

    def _modified(self, _e=None):
        if self.src.edit_modified():
            self.src.edit_modified(False)
            if self._job:
                self.after_cancel(self._job)
            self._job = self.after(700, self.read)

    def read(self):
        self._job = None
        text = self.src.get("1.0", "end").strip()
        if not text:
            self.patch = None
            self._render_empty()
            return
        self.patch = AP.read_patch(text, self.app.project)
        self.recheck()

    def recheck(self):
        if self.patch is None:
            return
        self.errors, self.warnings = (AP.check(self.app.project, self.patch, self.keep.get())
                                      if self.patch.items and not self.patch.errors else ([], []))
        self._render()

    # ---- 그리기 ----
    def include_dependencies(self):
        for row in AP.missing_selections(self.patch):
            row["take"] = True
        self.recheck()

    def _render_empty(self):
        self.dep_btn.pack_forget()
        self.tree.delete(*self.tree.get_children())
        self.msg.configure(state="normal")
        self.msg.delete("1.0", "end")
        self.msg.insert("end", "AI 의 답을 붙여 넣으면 여기에 검사 결과가 나옵니다.")
        self.msg.configure(state="disabled")
        self.canvas.delete("all")
        self.desc.configure(text="")
        self.ok_btn.configure(state="disabled")
        self.fix_btn.configure(state="disabled")
        self.summary.configure(text="")

    def _all_errors(self):
        return (self.patch.errors if self.patch else []) + self.errors

    def _render(self):
        p = self.patch
        self.tree.delete(*self.tree.get_children())
        for i, x in enumerate(p.items):
            it = x["item"]
            state = "기존 항목 바꿈" if x["exists"] and not self.keep.get() else ("새 ID 로 추가" if x["exists"] else "새로 추가")
            self.tree.insert("", "end", iid=str(i), text="  " + (it.get("name_ko") or it["id"]),
                             image=UX.item_icon(x["kind"], it, self.app.ui),
                             values=("✔" if x["take"] else "—", AP.NOUN[x["kind"]], it["id"], state))
        m = self.msg
        m.configure(state="normal")
        m.delete("1.0", "end")
        errs = self._all_errors()
        missing = AP.missing_selections(p)
        if missing:
            m.insert("end", "함께 필요한 항목: " + ", ".join(x["item"].get("name_ko") or x["item"]["id"] for x in missing) + "\n", "warn")
            self.dep_btn.pack(side="left")
        else:
            self.dep_btn.pack_forget()
        if errs:
            m.insert("end", f"오류 {len(errs)}개 — 고쳐야 넣을 수 있습니다\n", ("head", "err"))
            for e in errs:
                m.insert("end", "• " + e + "\n", "err")
        if self.warnings:
            m.insert("end", f"경고 {len(self.warnings)}개\n", ("head", "warn"))
            for w in self.warnings:
                m.insert("end", "• " + w + "\n", "warn")
        if p.fixes:
            m.insert("end", f"자동으로 고친 것 {len(p.fixes)}개\n", ("head", "fix"))
            for f in p.fixes:
                m.insert("end", "• " + f + "\n", "fix")
        if not errs and not self.warnings and not p.fixes:
            m.insert("end", "문제 없음 ✔\n", ("head", "fix"))
        m.configure(state="disabled")
        n = sum(1 for x in p.items if x["take"])
        self.ok_btn.configure(state="normal" if n and not errs and not missing else "disabled")
        self.fix_btn.configure(state="normal" if errs or self.warnings else "disabled")
        cnt = {}
        for x in p.items:
            if x["take"]:
                cnt[AP.NOUN[x["kind"]]] = cnt.get(AP.NOUN[x["kind"]], 0) + 1
        self.summary.configure(text=("넣을 것: " + ", ".join(f"{k} {v}" for k, v in cnt.items())) if cnt else "넣을 것 없음")
        if p.items:
            self.tree.selection_set("0")
        else:
            self.canvas.delete("all")
            self.desc.configure(text="")

    def toggle(self, e):
        row = self.tree.identify_row(e.y)
        if not row or self.patch is None:
            return
        x = self.patch.items[int(row)]
        x["take"] = not x["take"]
        self.recheck()
        self.tree.selection_set(row)

    def show(self):
        sel = self.tree.selection()
        if not sel or self.patch is None:
            return
        x = self.patch.items[int(sel[0])]
        lang = self.lang.get()
        desc, tmp, item = AP.describe(self.app.project, x["kind"], x["item"], lang)
        try:
            import preview as PV
            desc = PV.fill_values(tmp, desc, item, bool(self.up.get()))
        except Exception:  # noqa: BLE001 - 숫자 채우기에 실패하면 원문 그대로
            pass
        import re
        self.desc.configure(text=re.sub(r"\[/?[a-z]+\]", "", desc))
        if getattr(self, "diff_widget", None):
            self.diff_widget.destroy()
            self.diff_widget = None
        self.canvas.delete("all")
        if x["kind"] in AP.GIMMICKS:
            if x["exists"] and not self.keep.get():
                group = AP.GIMMICKS[x["kind"]][0]
                old = next(row for row in self.app.project["gimmicks"][group] if row["id"] == item["id"])
                lines = AP.change_lines(old, item)
                self.canvas.create_text(8, 8, anchor="nw", text="변경 전 → 변경 후", fill="white")
                diff = tk.Text(self.canvas, wrap="word", width=32, height=16)
                diff.insert("1.0", "\n".join(lines) or "변경 없음")
                diff.configure(state="disabled")
                self.canvas.create_window(8, 36, anchor="nw", window=diff)
                self.diff_widget = diff
            return
        assets = self.app.game_assets()
        if assets is None:
            self.canvas.create_text(10, 10, anchor="nw", fill="#ccc", text="게임 파일이 있으면 게임 모습으로 보여 줍니다.",
                                    width=int(280 * self.app.ui))
            return
        try:
            import ingame
            from PIL import ImageTk
            im = ingame.compose(assets, tmp, x["kind"], item, lang, bool(self.up.get()))
        except Exception as ex:  # noqa: BLE001
            self.canvas.create_text(10, 10, anchor="nw", fill="#f88", text=f"미리보기 실패: {ex}", width=int(280 * self.app.ui))
            return
        cw, ch = int(self.canvas.cget("width")), int(self.canvas.cget("height"))
        k = min(cw / im.width, ch / im.height)
        im = im.resize((max(1, int(im.width * k)), max(1, int(im.height * k))))
        self._photo = ImageTk.PhotoImage(im)
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo)

    # ---- 버튼 ----
    def copy_fix(self):
        text = AG.fix_request(self._all_errors(), self.warnings, self.patch.fixes if self.patch else None)
        self.clipboard_clear()
        self.clipboard_append(text)
        self.summary.configure(text="복사했습니다. AI 채팅창에 붙여넣고, 받은 새 답을 위에 다시 붙여 넣으세요.")

    def commit(self):
        if self.patch is None or self._all_errors():
            return
        replaced = [x for x in self.patch.items if x["take"] and x["exists"] and not self.keep.get()]
        if replaced and not messagebox.askyesno(
                TITLE, "이미 있는 항목을 AI 버전으로 바꿉니다:\n" +
                "\n".join(f"• {AP.NOUN[x['kind']]} {x['item'].get('name_ko')} ({x['item']['id']})" for x in replaced) +
                "\n\n계속할까요? (Ctrl+Z 로 되돌릴 수 있습니다)", parent=self):
            return
        added = AP.apply(self.app.project, self.patch, self.keep.get())
        self.app.mark_dirty()
        self.app.load_all()
        self.app.log("AI 결과를 넣었습니다: " + ", ".join(f"{AP.NOUN[k]} {i}" for k, i in added))
        self.host.destroy()
        if added:   # 파워는 먼저 들어가므로, 카드·유물·물약이 있으면 그쪽으로 데려간다
            first = next(((k, i) for k, i in added if k != "power"), added[0])
            self.app.goto_any(*first)
        self.app.status(f"AI 결과 {len(added)}개를 넣었습니다 (Ctrl+Z 로 되돌리기)")

class AIWorkflow(tk.Toplevel):
    def __init__(self, app, paste=False, text=""):
        super().__init__(app)
        self.title("AI로 만들기")
        self.transient(app)
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both",expand=True)
        self.guide = GuidePage(app,self)
        self.paste = PastePage(app,self,text)
        self.tabs.add(self.guide,text="① 요청 복사")
        self.tabs.add(self.paste,text="② 답변 붙여넣기 · 변경 확인")
        self.tabs.select(self.paste if paste else self.guide)
        self.geometry(f"{min(self.winfo_screenwidth()-60,int(1060*app.ui))}x{min(self.winfo_screenheight()-100,int(760*app.ui))}")
        center_window(self,app)
        self.bind("<Escape>",lambda _:self.destroy())


def AIGuideDialog(app):
    return AIWorkflow(app)


def AIPasteDialog(app,text=""):
    return AIWorkflow(app,True,text)

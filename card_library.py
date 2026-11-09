"""Read-only character sources and selective card import."""
from uxkit import stable_listbox
import copy
import json
import os
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import modimport as MI
import modgen as M
import preview as PV


def original_sources(assets):
    locales = {lang: assets.loc(lang, "cards") for lang in ("ko", "en", "zh")}
    names = assets.loc("ko", "characters")
    groups = {}
    for path in assets.pck.files:
        match = re.fullmatch(r"images/packed/card_portraits/([a-z0-9_]+)/([a-z0-9_]+)\.png\.import", path)
        if not match:
            continue
        group, slug = match.groups()
        entry = slug.upper()
        if not re.fullmatch(r"[A-Z][A-Z0-9_]*", entry) or entry + ".title" not in locales["en"]:
            continue
        card = {"id": entry, "portrait": path[:-7]}
        for lang, table in locales.items():
            card["name_" + lang] = table.get(entry + ".title", "")
            card["desc_" + lang] = table.get(entry + ".description", "")
        groups.setdefault(group, []).append(card)
    return {group: {"title": names.get(group.upper() + ".title", group), "cards": cards, "game": True}
            for group, cards in sorted(groups.items())}


def read_original_code(folder, entry, log=print):
    dll = Path(folder) / "data_sts2_windows_x86_64" / "sts2.dll"
    cls = M.pascal(entry.lower())
    if not dll.is_file():
        raise FileNotFoundError(f"게임 DLL을 찾을 수 없습니다. 설치 폴더를 확인해 주세요.\n{dll}")
    exe = MI.ensure_decompiler(log)
    result = subprocess.run([exe, "-t", "MegaCrit.Sts2.Core.Models.Cards." + cls, str(dll)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        creationflags=MI._NOWIN, env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
    if result.returncode:
        raise RuntimeError(MI._process_failure(f"{cls} 카드 디컴파일 실패", result.args, result))
    classes = MI.parse_cs(result.stdout)
    found = next((c for c in classes if c.name == cls), None)
    if found is None:
        raise ValueError(f"원작 DLL에서 카드 클래스 {cls}를 찾지 못했습니다. 게임 파일과 .NET 설치 상태를 확인해 주세요.")
    body = found.body
    variables = MI.parse_vars(MI.member_text(body, "CanonicalVars"))
    upgrades, _, _ = MI.parse_upgrades(MI.member_text(body, "OnUpgrade"))
    for v in variables:
        name = v["name"]
        v["upgrade"] = upgrades.get(name, upgrades.get(name[:-5] if name.endswith("Power") else name, 0))
    return result.stdout, [v for v in variables if v["value"] is not None]


def import_project_card(target, source, card, used):
    """Prepare changes on a copy so unresolved or conflicting references cannot partially import."""
    result = copy.deepcopy(target)
    item = copy.deepcopy(card)
    original = item["id"]
    suffix = 2
    while item["id"] in used:
        item["id"] = f"{original}_{suffix}"
        suffix += 1
    used = set(used) | {item["id"]}
    seen = set()
    def require(group, key):
        if not key or (group, key) in seen:
            return
        seen.add((group, key))
        source_list = source.get(group, []) if group in ("powers", "dependencies") else source.get("gimmicks", {}).get(group, [])
        found = next((obj for obj in source_list if obj["id"] == key), None)
        if found is None:
            return
        owner = result if group in ("powers", "dependencies") else result.setdefault("gimmicks", {})
        dest = owner.setdefault(group, [])
        prior = next((obj for obj in dest if obj["id"] == key), None)
        if prior == found:
            return
        if prior is not None or (group != "dependencies" and key in used):
            raise ValueError(f"참조 항목 '{key}'의 ID가 현재 프로젝트의 다른 항목과 겹칩니다.")
        obj = copy.deepcopy(found)
        dest.append(obj)
        if group != "dependencies":
            used.add(key)
            scan(obj)
    def scan(node):
        if isinstance(node, list):
            for value in node:
                scan(value)
        elif isinstance(node, dict):
            for field, value in node.items():
                if isinstance(value, str):
                    if field in ("power", "scale_power", "cond_power", "res_power", "ref") and value.startswith("c:"):
                        require("powers", value[2:])
                    elif value.startswith("tag:") and field in ("ctype", "filter", "played_filter", "result_filter"):
                        require("tags", value[4:])
                    elif value.startswith("s:") and field in ("power", "cond_power", "scale_power"):
                        require("summons", value[2:])
                    elif value.startswith("x:") and field in ("power", "cond_power", "scale_power"):
                        require("dependencies", value.split(":")[1])
                    elif field in ("summon", "orb", "pet", "button", "fx"):
                        require({"summon":"summons","orb":"orbs","pet":"pets","button":"buttons","fx":"effects"}[field], value)
                    elif field == "card" and value == original:
                        node[field] = item["id"]
                    elif field == "card" and value != "this" and not any(c["id"] == value for c in result["cards"]):
                        raise ValueError(f"이 카드가 참조하는 '{value}' 카드를 먼저 가져오세요.")
                elif field == "gtags":
                    for tag in value or []:
                        require("tags", tag)
                else:
                    scan(value)
            if isinstance(node.get("clone"), dict):
                require("dependencies", node["clone"].get("mod"))
    scan(item)
    result["cards"].append(item)
    return result


def _strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for value in node:
            yield from _strings(value)


CATEGORIES = {"relics": "유물", "potions": "물약", "powers": "파워", "card_keywords": "키워드"}


def item_sources(assets):
    sources = {}
    for kind, label in CATEGORIES.items():
        tables = {lang: assets.loc(lang, kind) for lang in ("ko", "en", "zh")}
        items = []
        for key in sorted(tables["en"]):
            entry, _, field = key.partition(".")
            if field != "title" or not re.fullmatch(r"[A-Z][A-Z0-9_]*", entry):
                continue
            if kind == "card_keywords" and M.pascal(entry.lower()) not in dict(M.CARD_KEYWORDS):
                continue
            item = {"id": entry}
            for lang, table in tables.items():
                item["name_" + lang] = table.get(key, "")
                item["desc_" + lang] = table.get(entry + ".description") or table.get(entry + ".smartDescription", "")
            items.append(item)
        sources[kind] = {"kind": kind, "game": True, "title": "원작 " + label, "cards": items}
    return sources


class CardLibrary(ttk.Frame):
    def __init__(self, app, resolve_paths, game_module, parent=None):
        super().__init__(parent or app.card_tab.item_panes)
        self.app, self.resolve_paths, self.game_module = app, resolve_paths, game_module
        self.reader = ThreadPoolExecutor(max_workers=1)
        self.reading = False
        self.bind("<Destroy>", lambda e: self.reader.shutdown(wait=False, cancel_futures=True) if e.widget is self else None)
        self.sources = {}
        self.assets = None
        self.photo = None
        self.rows = []
        self._drag = None
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Button(top, text="원작 캐릭터 열기", command=self.open_game).pack(side="left")
        ttk.Button(top, text="프로젝트 파일 열기…", command=self.open_projects).pack(side="left", padx=4)
        ttk.Button(top,text="접기",command=app.close_card_library).pack(side="right")
        self.upgraded = tk.BooleanVar()
        ttk.Checkbutton(top, text="강화(+)", variable=self.upgraded, command=self.show_card).pack(side="right")
        self.search = tk.StringVar()
        ttk.Label(top, text="항목 검색").pack(side="left", padx=(12, 2))
        ttk.Entry(top, textvariable=self.search, width=23).pack(side="left")
        self.search.trace_add("write", lambda *_: self.refresh_cards())
        panes = ttk.PanedWindow(self, orient="horizontal")
        panes.pack(fill="both", expand=True)
        def listpane(label, width):
            frame = ttk.LabelFrame(panes, text=label, padding=3)
            panes.add(frame, weight=1)
            lb = tk.Listbox(frame, exportselection=False, width=width)
            bar = ttk.Scrollbar(frame, command=lb.yview)
            lb.configure(yscrollcommand=bar.set)
            bar.pack(side="right", fill="y")
            lb.pack(fill="both", expand=True)
            return lb
        self.groups = listpane("열린 캐릭터 · 프로젝트", 20)
        self.cards = listpane("항목", 24)
        self.groups.bind("<<ListboxSelect>>", lambda _: self.refresh_cards())
        self.cards.bind("<<ListboxSelect>>", lambda _: self.show_card())
        self.cards.bind("<ButtonPress-1>", self.drag_start, add="+")
        self.cards.bind("<B1-Motion>", self.drag_move, add="+")
        self.cards.bind("<ButtonRelease-1>", self.drag_end, add="+")
        self._target_release_bind = app.card_tab.tree.bind("<ButtonRelease-1>", self.drag_end, add="+")
        self.bind("<Destroy>", self._cleanup_drag, add="+")
        detail = ttk.LabelFrame(panes, text="선택한 항목", padding=6)
        panes.add(detail, weight=2)
        self.art = ttk.Label(detail)
        self.art.pack()
        self.info = tk.Text(detail, wrap="word", width=44, state="disabled")
        self.info.pack(fill="both", expand=True)
        foot = ttk.Frame(self, padding=6)
        foot.pack(fill="x")
        self.status = ttk.Label(self, text="원작 또는 프로젝트 파일을 열고 카드를 선택하세요.")
        self.status.pack(fill="x",before=foot)
        self.drop_zone = ttk.Label(self, text="↓ 여기로 카드를 끌어놓으면 프로젝트에 가져옵니다", anchor="center",
                                   padding=8, relief="groove")
        self.drop_zone.pack(fill="x", padx=6, pady=(0, 5), before=foot)
        self.apply_btn = ttk.Button(foot, text="편집 중인 카드에 적용", command=self.apply_selected)
        self.apply_btn.pack(side="right")
        self.code_btn = ttk.Button(foot, text="원작 코드·수치 보기", command=self.show_code)
        self.code_btn.pack(side="right", padx=3)
        self.remove_btn = ttk.Button(foot, text="내 풀에서 제거", command=self.remove)
        self.remove_btn.pack(side="right")
        self.add_btn = ttk.Button(foot, text="선택한 카드 가져오기", command=self.add)
        self.add_btn.pack(side="right", padx=3)
        app.card_tab.tree.bind("<<TreeviewSelect>>", lambda _: self.show_card(), add="+")
        self.show_card()

    def open_game(self):
        try:
            folder = self.app.settings.get("sts2_path")
            if not folder or not (Path(folder) / "SlayTheSpire2.pck").is_file():
                folder = filedialog.askdirectory(parent=self, title="SlayTheSpire2.pck가 있는 설치 폴더")
            if not folder:
                return
            if self.game_module is None:
                raise ValueError("게임 그림 라이브러리를 열려면 Pillow를 설치하세요.")
            self.assets = self.game_module.GameAssets(folder)
            groups = original_sources(self.assets)
            groups.update(item_sources(self.assets))
            if not groups:
                raise ValueError("원작 카드 목록을 찾을 수 없습니다.")
            for key, source in groups.items():
                self.sources["game:" + key] = source
            self.refresh_groups("game:" + ("ironclad" if "ironclad" in groups else next(iter(groups))))
        except Exception as exc:
            messagebox.showerror("원작 열기", str(exc), parent=self)

    def open_projects(self):
        paths = filedialog.askopenfilenames(parent=self, title="참고할 캐릭터 프로젝트 선택",
            filetypes=[("모드 메이커 프로젝트", "*.sts2mod.json *.json")])
        for path in paths:
            try:
                raw = json.loads(Path(path).read_text(encoding="utf-8-sig"))
                if not isinstance(raw, dict) or not isinstance(raw.get("cards"), list):
                    raise ValueError("카드 목록이 있는 모드 메이커 프로젝트를 선택하세요.")
                project = self.resolve_paths(M.normalize(raw), os.path.dirname(path))
                self.sources[path] = {"title": M.text(project["character"], "name", "ko") + " · " + Path(path).name,
                                      "cards": project["cards"], "project": project}
                self.refresh_groups(path)
            except Exception as exc:
                messagebox.showerror("프로젝트 열기", f"{path}\n{exc}", parent=self)

    @stable_listbox('groups')
    def refresh_groups(self, selected):
        self.groups.delete(0, "end")
        for src in self.sources.values():
            self.groups.insert("end", src["title"])
        index = list(self.sources).index(selected)
        self.groups.selection_set(index)
        self.groups.see(index)
        self.refresh_cards()

    def source(self):
        sel = self.groups.curselection()
        return list(self.sources.values())[sel[0]] if sel else {}

    @stable_listbox('cards')
    def refresh_cards(self):
        query = self.search.get().strip().casefold()
        self.rows = [c for c in self.source().get("cards", []) if any(query in str(c.get(k, "")).casefold()
                     for k in ("id", "name_ko", "name_en", "name_zh"))]
        self.cards.delete(0, "end")
        for card in self.rows:
            self.cards.insert("end", M.text(card, "name", "ko") or card["id"])
        if self.rows:
            self.cards.selection_set(0)
        self.show_card()

    def selection(self):
        sel = self.cards.curselection()
        return self.rows[sel[0]] if sel else None

    def show_card(self):
        card, source = self.selection(), self.source()
        retained_photo = self.photo
        self.photo = None
        lines = []
        imported = False
        if card:
            lines = [M.text(card, "name", "ko") + "  ·  " + card["id"]]
            for lang in ("ko", "en", "zh"):
                if source.get("game"):
                    desc = card["desc_" + lang]
                    if "raw_vars" in card:
                        desc = PV.fill_values({}, desc, card, self.upgraded.get())
                else:
                    p = source["project"]
                    desc = PV.fill_values(p, M.description(p, card, "card", lang), card, self.upgraded.get())
                lines.append(f"{M.text(card, 'name', lang)}\n{desc}")
            try:
                from PIL import ImageTk
                if source.get("game") and card.get("portrait"):
                    pic = self.assets.texture(card["portrait"]).copy()
                    pic.thumbnail((235, 165))
                    self.photo = ImageTk.PhotoImage(pic)
                elif card.get("image"):
                    self.photo = PV.IMAGES.get(card["image"], 235, 165, "contain")
            except (ImportError, OSError, ValueError, KeyError):
                pass
            imported = source.get("game") and card["id"] in self.app.project["character"].get("game_" + source.get("kind", "cards"), {})
        self.art.configure(image=self.photo or "")
        self.info.configure(state="normal")
        self.info.delete("1.0", "end")
        self.info.insert("1.0", "\n\n".join(lines))
        self.info.configure(state="disabled")
        self.add_btn.configure(state="normal" if card and (not imported or source.get("kind", "cards") == "cards") else "disabled",
            text="＋ 새 카드로 가져오기" if source.get("kind","cards")=="cards" else "프로젝트에 추가")
        tab = self.app.card_tab
        current = tab.items[tab.cur] if tab.cur is not None and tab.cur < len(tab.items) else {}
        name = M.text(current,"name","ko") if current else ""
        can_apply = card and current and (not source.get("game") or source.get("kind")=="card_keywords")
        self.apply_btn.configure(state="normal" if can_apply else "disabled",
                                 text=(f"‘{name}’에 키워드 적용" if source.get("kind")=="card_keywords" else
                                       f"‘{name}’에 덮어쓰기…" if name else "덮어쓸 카드를 선택하세요"))
        self.code_btn.configure(state="normal" if card and source.get("game") and not source.get("kind") and not self.reading else "disabled")
        self.remove_btn.configure(state="normal" if imported else "disabled")

    def apply_keyword(self, selected=None):
        tab = self.app.card_tab
        selected = selected or self.selection()
        if tab.cur is None or not selected:
            messagebox.showinfo("키워드 적용", "카드 탭에서 적용할 카드를 먼저 선택하세요.", parent=self)
            return
        card = tab.items[tab.cur]
        keyword = M.pascal(selected["id"].lower())
        if keyword not in card["keywords"]:
            card["keywords"].append(keyword)
            self.app.mark_dirty()
            tab.load(tab.cur)
        self.status.configure(text=f"{M.text(card, 'name', 'ko')}에 적용됨")

    def apply_selected(self, card=None, source=None):
        card = card or self.selection()
        source = source or self.source()
        tab = self.app.card_tab
        if not card:
            return False
        if source.get("game") and source.get("kind", "cards") == "cards":
            return self.add(card, source)
        if tab.cur is None or tab.cur >= len(tab.items):
            messagebox.showinfo("카드 적용", "카드 탭에서 적용할 카드를 먼저 선택하세요.", parent=self)
            return False
        if source.get("kind") == "card_keywords":
            self.apply_keyword(card)
            return True
        if source.get("game"):
            return False
        if not messagebox.askyesno("카드 적용", "현재 카드의 내용과 효과를 선택한 카드로 바꿀까요?\n카드 ID와 전용 캐릭터 설정은 유지됩니다.", parent=self):
            return False
        index = tab.cur
        old = tab.items[index]
        try:
            project = import_project_card(self.app.project, source["project"], card, self.app.all_ids())
        except ValueError as exc:
            messagebox.showwarning("카드 적용", str(exc), parent=self)
            return False
        replacement = project["cards"].pop()
        imported_id = replacement["id"]
        def rename_self(node):
            if isinstance(node, dict):
                for key, value in node.items():
                    if key == "card" and value == imported_id:
                        node[key] = old["id"]
                    else:
                        rename_self(value)
            elif isinstance(node, list):
                for value in node:
                    rename_self(value)
        rename_self(replacement)
        replacement["id"] = old["id"]
        replacement["pool_character"] = old.get("pool_character", "")
        project["cards"][index] = replacement
        self.app.project = project
        self.app.mark_dirty()
        self.app.load_all()
        tab.refresh_list(index)
        self.status.configure(text=f"{M.text(replacement, 'name', 'ko')}을(를) 편집 중인 카드에 적용했습니다.")
        return True

    def drag_start(self, event):
        index = self.cards.nearest(event.y)
        self._drag = (index, event.x_root, event.y_root) if 0 <= index < len(self.rows) else None
        if self._drag:
            self.cards.grab_set()

    def _cleanup_drag(self, event):
        if event.widget is not self:
            return
        try:
            if self.cards.grab_current() == self.cards:
                self.cards.grab_release()
        except tk.TclError:
            pass
        try:
            self.app.card_tab.tree.unbind("<ButtonRelease-1>", self._target_release_bind)
        except tk.TclError:
            pass

    def drag_move(self, event):
        if self._drag and abs(event.x_root - self._drag[1]) + abs(event.y_root - self._drag[2]) > 8:
            tree = self.app.card_tab.tree
            if not hasattr(self,"_tree_style"):
                self._tree_style = tree.cget("style")
            over = self.winfo_containing(event.x_root,event.y_root) == tree
            ttk.Style(self).configure("LibraryDrop.Treeview",fieldbackground="#dcecff",background="#dcecff")
            tree.configure(style="LibraryDrop.Treeview" if over else self._tree_style)
            self.status.configure(text="여기에 놓으면 새 카드로 추가됩니다." if over else "왼쪽 카드 목록에 놓으세요.")

    def drag_end(self, event):
        drag, self._drag = self._drag, None
        if hasattr(self,"_tree_style"):
            self.app.card_tab.tree.configure(style=self._tree_style)
        try:
            if self.cards.grab_current() == self.cards:
                self.cards.grab_release()
        except tk.TclError:
            pass
        if not drag or abs(event.x_root - drag[1]) + abs(event.y_root - drag[2]) <= 8:
            return
        def inside(widget):
            return (widget.winfo_ismapped() and widget.winfo_rootx() <= event.x_root < widget.winfo_rootx() + widget.winfo_width()
                    and widget.winfo_rooty() <= event.y_root < widget.winfo_rooty() + widget.winfo_height())
        card, source = self.rows[drag[0]], self.source()
        if inside(self.drop_zone):
            self.add(card, source)
            return
        if inside(self):
            self.status.configure(text="아래 가져오기 영역이나 카드 탭에 놓아 주세요.")
            return
        tab = self.app.card_tab
        if not inside(tab.tree):
            self.status.configure(text="카드 목록 위에 놓으면 가져올 수 있습니다.")
            return
        if source.get("kind") == "card_keywords":
            self.apply_selected(card, source)
        elif source.get("game") and source.get("kind", "cards") != "cards":
            self.status.configure(text="카드 탭에는 카드만 가져올 수 있습니다.")
        else:
            self.add(card, source)

    def _original_error(self, card, exc):
        # Windows 도구가 출력한 NUL과 제어 문자는 Tk 대화상자에 그대로 넘기지 않는다.
        detail = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", str(exc)).strip()
        if not detail:
            detail = "실패한 도구가 오류 설명을 반환하지 않았습니다. .NET SDK와 게임 설치 경로를 확인해 주세요."
        title = f"원작 카드 {card['id']} 읽기 실패"
        self.status.configure(text=f"{title} · {detail.splitlines()[0][:80]}")
        self.app.log(f"[오류] {title} ({type(exc).__name__})\n{detail}")
        win = tk.Toplevel(self)
        win.title(title)
        win.transient(self)
        ttk.Label(win, text=title, padding=8).pack(anchor="w")
        view = tk.Text(win, width=76, height=12, wrap="word")
        view.pack(fill="both", expand=True, padx=8)
        view.insert("1.0", f"{type(exc).__name__}\n{detail}")
        view.configure(state="disabled")
        ttk.Button(win, text="닫기", command=win.destroy).pack(pady=6)
        win.focus_set()

    def show_code(self):
        card = self.selection()
        if not card or not self.source().get("game") or self.reading:
            return
        def display():
            win = tk.Toplevel(self)
            win.title((M.text(card, "name", "ko") or card["id"]) + " · 원작 코드")
            view = tk.Text(win, height=32, width=100, wrap="none")
            view.pack(fill="both", expand=True)
            view.insert("1.0", card["_source"])
            view.configure(state="disabled")
        if "_source" in card:
            display()
            return
        self.reading = True
        self.show_card()
        self.status.configure(text="원작 카드 코드를 읽는 중…")
        future = self.reader.submit(read_original_code, self.assets.sts2_path, card["id"], self.app.log)
        def finish():
            if not future.done():
                self.after(100, finish)
                return
            self.reading = False
            try:
                card["_source"], card["raw_vars"] = future.result()
                display()
                self.status.configure(text="원작 수치를 설명에 반영했습니다.")
            except Exception as exc:
                self._original_error(card, exc)
            self.show_card()
        self.after(100, finish)

    def import_game_copy(self, card):
        if self.reading:
            self.status.configure(text="원작 코드를 읽는 중입니다.")
            return False
        project = self.app.project
        folder = self.assets.sts2_path
        self.reading = True
        self.status.configure(text="원작 카드 효과를 가져오는 중…")
        future = self.reader.submit(read_original_code, folder, card["id"])
        def finish():
            if not future.done():
                self.after(100, finish)
                return
            self.reading = False
            try:
                code, _ = future.result()
                if self.app.project is not project:
                    raise ValueError("프로젝트가 변경되었습니다. 카드를 다시 가져오세요.")
                em = MI.ExtMod()
                em.classes = {c.name: c for c in MI.parse_cs(code)}
                MI._extract_items(em)
                item = next((it for it in em.items["card"] if it["class"] == M.pascal(card["id"].lower())), None)
                if item is None:
                    raise ValueError("원작 카드의 기본 클래스와 효과를 확인할 수 없습니다.")
                item.update({k: v for k, v in card.items() if k.startswith(("name_", "desc_"))})
                copy_card = MI.clone_item(em, item, project)
                copy_card["clone"]["game_original"] = True
                self.add(copy_card, {"project": {"cards": [copy_card]}})
            except Exception as exc:
                self._original_error(card, exc)
        self.after(100, finish)
        return True

    def add(self, card=None, source=None):
        card, source = card or self.selection(), source or self.source()
        if not card:
            return False
        if source.get("game") and source.get("kind", "cards") == "cards":
            return self.import_game_copy(card)
        if source.get("game"):
            ch = self.app.project["character"]
            kind = source.get("kind", "cards")
            if kind in ("cards", "relics", "potions") and not ch.get("enabled"):
                messagebox.showinfo("원작 카드", "캐릭터 탭에서 새 캐릭터 만들기를 켜면 원작 카드를 풀에 추가할 수 있습니다.", parent=self)
                return False
            ch.setdefault("game_" + kind, {})[card["id"]] = dict(card) if kind in ("powers", "card_keywords") else M.text(card, "name", "ko")
        else:
            try:
                self.app.project = import_project_card(self.app.project, source["project"], card, self.app.all_ids())
            except ValueError as exc:
                messagebox.showwarning("카드 가져오기", str(exc), parent=self)
                return False
        self.app.mark_dirty()
        self.app.load_all()
        if not source.get("game"):
            tab = self.app.card_tab
            index = len(self.app.project["cards"]) - 1
            tab.search.set("")
            tab.select_index(index)
        self.status.configure(text=f"{M.text(card, 'name', 'ko')} 추가됨")
        self.show_card()
        return True

    def remove(self):
        card = self.selection()
        if not card or not self.source().get("game"):
            return
        ch = self.app.project["character"]
        key = "game:" + card["id"]
        kind = self.source().get("kind", "cards")
        if kind == "powers" and any(key == val for val in _strings(self.app.project)):
            messagebox.showinfo("원작 파워", "이 파워를 사용하는 효과를 먼저 변경하세요.", parent=self)
            return
        if kind == "relics" and key in ch["relics"]:
            if not messagebox.askyesno("원작 유물", "시작 유물에서도 제거할까요?", parent=self):
                return
            ch["relics"] = [v for v in ch["relics"] if v != key]
        if kind == "cards" and any(row["card"] == key for row in ch["deck"]):
            if not messagebox.askyesno("원작 카드 제거", "시작 덱에서도 이 카드를 제거할까요?", parent=self):
                return
            ch["deck"] = [row for row in ch["deck"] if row["card"] != key]
        ch.get("game_" + kind, {}).pop(card["id"], None)
        self.app.mark_dirty()
        self.app.load_all()
        self.status.configure(text="내 카드 풀에서 제거했습니다.")
        self.show_card()


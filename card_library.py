"""Read-only character sources and selective card import."""
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


def read_original_code(folder, entry):
    dll = Path(folder) / "data_sts2_windows_x86_64" / "sts2.dll"
    cls = M.pascal(entry.lower())
    exe = MI.ensure_decompiler()
    result = subprocess.run([exe, "-t", "MegaCrit.Sts2.Core.Models.Cards." + cls, str(dll)],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        creationflags=MI._NOWIN, env=dict(os.environ, DOTNET_ROLL_FORWARD="Major"))
    if result.returncode:
        raise ValueError(result.stderr.strip()[-600:] or "카드 원본 코드를 읽지 못했습니다.")
    classes = MI.parse_cs(result.stdout)
    body = next(c.body for c in classes if c.name == cls)
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
                    elif value.startswith("tag:") and field in ("ctype", "filter", "played_filter"):
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


class CardLibrary(tk.Toplevel):
    def __init__(self, app, resolve_paths, game_module):
        super().__init__(app)
        self.title("캐릭터 카드 라이브러리")
        self.geometry("965x570")
        self.app, self.resolve_paths, self.game_module = app, resolve_paths, game_module
        self.reader = ThreadPoolExecutor(max_workers=1)
        self.reading = False
        self.bind("<Destroy>", lambda e: self.reader.shutdown(wait=False, cancel_futures=True) if e.widget is self else None)
        self.sources = {}
        self.assets = None
        self.photo = None
        self.rows = []
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Button(top, text="원작 캐릭터 열기", command=self.open_game).pack(side="left")
        ttk.Button(top, text="프로젝트 파일 열기…", command=self.open_projects).pack(side="left", padx=4)
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
        detail = ttk.LabelFrame(panes, text="선택한 항목", padding=6)
        panes.add(detail, weight=2)
        self.art = ttk.Label(detail)
        self.art.pack()
        self.info = tk.Text(detail, wrap="word", width=44, state="disabled")
        self.info.pack(fill="both", expand=True)
        foot = ttk.Frame(self, padding=6)
        foot.pack(fill="x")
        self.status = ttk.Label(foot, text="원작 또는 프로젝트 파일을 열고 카드를 선택하세요.")
        self.status.pack(side="left")
        self.apply_kw = ttk.Button(foot, text="편집 중인 카드에 적용", command=self.apply_keyword)
        self.apply_kw.pack(side="right")
        self.code_btn = ttk.Button(foot, text="원작 코드·수치 보기", command=self.show_code)
        self.code_btn.pack(side="right", padx=3)
        self.remove_btn = ttk.Button(foot, text="내 풀에서 제거", command=self.remove)
        self.remove_btn.pack(side="right")
        self.add_btn = ttk.Button(foot, text="선택한 카드 가져오기", command=self.add)
        self.add_btn.pack(side="right", padx=3)
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
        self.add_btn.configure(state="normal" if card and not imported else "disabled",
            text="프로젝트에 추가" if source.get("game") else "편집용 사본 가져오기")
        self.apply_kw.configure(state="normal" if imported and source.get("kind") == "card_keywords" else "disabled")
        self.code_btn.configure(state="normal" if card and source.get("game") and not source.get("kind") and not self.reading else "disabled")
        self.remove_btn.configure(state="normal" if imported else "disabled")

    def apply_keyword(self):
        tab = self.app.card_tab
        if tab.cur is None or not self.selection():
            messagebox.showinfo("키워드 적용", "카드 탭에서 적용할 카드를 먼저 선택하세요.", parent=self)
            return
        card = tab.items[tab.cur]
        keyword = M.pascal(self.selection()["id"].lower())
        if keyword not in card["keywords"]:
            card["keywords"].append(keyword)
            self.app.mark_dirty()
            tab.load(tab.cur)
        self.status.configure(text=f"{M.text(card, 'name', 'ko')}에 적용됨")

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
        future = self.reader.submit(read_original_code, self.assets.sts2_path, card["id"])
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
                self.status.configure(text="원작 코드를 읽지 못했습니다.")
                messagebox.showerror("원작 코드", str(exc), parent=self)
            self.show_card()
        self.after(100, finish)

    def add(self):
        card, source = self.selection(), self.source()
        if not card:
            return
        if source.get("game"):
            ch = self.app.project["character"]
            kind = source.get("kind", "cards")
            if kind in ("cards", "relics", "potions") and not ch.get("enabled"):
                messagebox.showinfo("원작 카드", "캐릭터 탭에서 새 캐릭터 만들기를 켜면 원작 카드를 풀에 추가할 수 있습니다.", parent=self)
                return
            ch.setdefault("game_" + kind, {})[card["id"]] = dict(card) if kind in ("powers", "card_keywords") else M.text(card, "name", "ko")
        else:
            try:
                self.app.project = import_project_card(self.app.project, source["project"], card, self.app.all_ids())
            except ValueError as exc:
                messagebox.showwarning("카드 가져오기", str(exc), parent=self)
                return
        self.app.mark_dirty()
        self.app.load_all()
        self.status.configure(text=f"{M.text(card, 'name', 'ko')} 추가됨")
        self.show_card()

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


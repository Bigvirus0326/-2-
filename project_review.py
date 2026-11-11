"""Project-wide card summaries and imported call mapping."""
from collections import Counter, defaultdict
import copy
import re
from types import SimpleNamespace
import tkinter as tk
from tkinter import ttk, messagebox

import blockcode as B
import modgen as M


def balance(app):
    win = tk.Toplevel(app)
    win.title("카드 풀 밸런스 · 설명 검사")
    view = tk.Text(win, width=86, height=32, wrap="word")
    view.pack(fill="both", expand=True)
    pools = defaultdict(list)
    for card in app.project["cards"]:
        pools[card.get("pool_character") or "기본 풀"].append(card)
    tags = {t["id"]: t.get("name_ko") or t["id"] for t in app.project.get("gimmicks", {}).get("tags", [])}
    patterns = {"damage": r"피해(?:를)?\s*(\d+)", "block": r"방어도(?:를)?\s*(\d+)", "draw": r"카드(?:를)?\s*(\d+)\s*장"}
    for pool, cards in pools.items():
        view.insert("end", f"{pool} · {len(cards)}장\n")
        costs = Counter("X" if c.get("x_cost") else str(c["cost"]) for c in cards)
        types = Counter(dict(M.CARD_TYPES).get(c["type"],c["type"]) for c in cards)
        for title, counts in (("비용", costs), ("종류", types)):
            view.insert("end", title + "   " + "   ".join(f"{key}: {n}장" for key,n in sorted(counts.items())) + "\n")
        view.insert("end", "종류 비율   " + "   ".join(f"{key} {n/len(cards):.0%}" for key,n in types.items()) + "\n")
        for key,label in tags.items():
            view.insert("end", f"#{label}: {sum(key in c.get('gtags',[]) for c in cards)}장  ")
        view.insert("end", "\n")
        for c in cards:
            effects = c.get("effects", [])
            actions = []
            for e in effects:
                if e.get("blocks"):
                    for b in e["blocks"]:
                        v = b.get("args",{}).get("amount")
                        if isinstance(v,dict) and v.get("t") == "num":
                            actions.append((b["op"],v.get("v")))
                elif not e.get("scale_power") and not e.get("cond_power"):
                    actions.append((e.get("kind"), e.get("amount")))
            for kind, pattern in patterns.items():
                values = [v for k,v in actions if k == kind]
                matches = re.findall(pattern,c.get("desc_ko",""))
                if len(matches)==len(values)==1 and int(matches[0]) != values[0]:
                    view.insert("end", f"설명 확인 · {c['name_ko']} · {kind}: 설명 {matches[0]} / 기본 효과 {values[0]}\n")
        view.insert("end","\n")
    if not pools:
        view.insert("end","프로젝트에 카드가 없습니다.")
    view.configure(state="disabled")


def unresolved(app):
    import blockui
    win = tk.Toplevel(app)
    win.title("가져온 모드 · 미연결 호출")
    listing = tk.Listbox(win, width=85, height=20, exportselection=False)
    listing.pack(fill="both",expand=True)
    groups = {}
    missing = {}
    ids = {}
    def scan(node, owner, item):
        if isinstance(node,list):
            for index, child in enumerate(node):
                if isinstance(child,dict) and child.get("op")=="src_call":
                    signature, _ = blockui._source_call_slots(child)
                    groups.setdefault((owner, signature or child.get("label","호출")), []).append((node,index,item))
                else:
                    scan(child,owner,item)
        elif isinstance(node,dict):
            for key,value in node.items():
                target = None
                prefix = ""
                if key == "args" and isinstance(value,dict):
                    schema = (B.block_spec(node) or {}).get("args",{})
                    for field,(slot_kind,_) in schema.items():
                        ref = value.get(field)
                        if slot_kind == "card" and ref and ref != "this" and ref not in ids["card"]:
                            missing.setdefault(("card",ref),[]).append((value,field,""))
                if owner == "character" and key == "card" and isinstance(value,str) and value and not value.startswith("game:"):
                    target = "card"
                if key == "card_id" and node.get("t") in ("pile_count", "card_identity") and isinstance(value,str) and value:
                    target = "card"
                if key in ("power","res_power","cond_power","scale_power","ref") and isinstance(value,str) and value.startswith("c:"):
                    target, prefix = "power","c:"
                if target and value[len(prefix):] not in ids[target]:
                    missing.setdefault((target,value), []).append((node,key,prefix))
                scan(value,owner,item)
    def refresh():
        groups.clear()
        missing.clear()
        ids.update(card={c["id"] for c in app.project["cards"]},power={p["id"] for p in app.project["powers"]})
        listing.delete(0,"end")
        for kind, group in (("card","cards"),("relic","relics"),("potion","potions"),("power","powers")):
            for item in app.project.get(group,[]):
                scan(item,kind,item)
        scan(app.project.get("character",{}),"character",app.project.get("character",{}))
        for (kind,sig), rows in groups.items():
            listing.insert("end",f"{len(rows)}곳 · {rows[0][2].get('name_ko','')} · {sig}")
        for (kind,ref), slots in missing.items():
            listing.insert("end", f"{len(slots)}곳 · 누락된 {'카드' if kind=='card' else '파워'} · {ref}")
        if groups or missing:
            listing.selection_set(0)
        else:
            listing.insert("end","연결할 호출이 없습니다.")
    def connect():
        if not (groups or missing) or not listing.curselection():
            return
        index = listing.curselection()[0]
        if index >= len(groups):
            kind,ref = list(missing)[index-len(groups)]
            candidates = app.project["cards" if kind=="card" else "powers"]
            if not candidates:
                messagebox.showinfo("연결", "먼저 대체할 항목을 만드세요.",parent=win)
                return
            dialog = tk.Toplevel(win)
            dialog.title(f"{ref} 대신 연결할 항목")
            choice = ttk.Combobox(dialog,state="readonly",width=40,values=[f"{c['name_ko']} ({c['id']})" for c in candidates])
            choice.pack(padx=10,pady=10)
            def apply():
                if choice.current()<0:
                    return
                for node,key,prefix in missing[kind,ref]:
                    node[key]=prefix+candidates[choice.current()]["id"]
                dialog.destroy()
                app.mark_dirty()
                app.load_all()
                refresh()
            ttk.Button(dialog,text="모두 연결",command=apply).pack()
            dialog.transient(win)
            dialog.grab_set()
            return
        kind,sig = list(groups)[listing.curselection()[0]]
        rows = groups[kind,sig]
        parent,i,item = rows[0]
        dialog = blockui.CallMappingDialog(win,SimpleNamespace(project=app.project,owner_kind=kind,item=item),parent[i])
        win.wait_window(dialog)
        if not dialog.result:
            return
        rule = dialog.result.get("rule")
        updates = []
        for parent,i,item in rows if rule else rows[:1]:
            original = parent[i]
            block = copy.deepcopy(dialog.result["block"])
            if rule:
                signature, slots = blockui._source_call_slots(original)
                if signature != rule["signature"]:
                    continue
                for field, binding in rule["bindings"].items():
                    if binding["kind"] != "arg":
                        continue
                    slot = next((s for s in slots if (s.get("source_segment"),s.get("source_arg")) ==
                                 (binding["segment"],binding["index"])),None)
                    if not slot:
                        messagebox.showwarning("연결", "인수 형식이 다른 호출이 있어 적용을 중단했습니다.",parent=win)
                        return
                    value = original.get("args",{}).get(slot["key"],slot.get("orig",""))
                    if B.block_spec(block)["args"][field][0]=="value" and not isinstance(value,dict):
                        value = {"t":"src","code":str(value)}
                    elif B.block_spec(block)["args"][field][0]=="code" and isinstance(value,dict):
                        value = B._Gen(app.project,M._Ctx(kind,item)).val(value)
                    block["args"][field] = copy.deepcopy(value)
            updates.append((parent,i,block))
        if rule:
            app.project.setdefault("call_mappings",[]).append(rule)
        for parent,i,block in updates:
            parent[i]=block
        app.mark_dirty()
        app.load_all()
        refresh()
    ttk.Button(win,text="선택한 호출 연결…",command=connect).pack()
    refresh()

def import_results(app, notes):
    win = tk.Toplevel(app)
    win.title("다른 모드 가져오기 결과")
    win.transient(app)
    ttk.Label(win,text=notes[0],padding=8).pack(anchor="w")
    tabs = ttk.Notebook(win)
    tabs.pack(fill="both",expand=True)
    groups = [[] for _ in range(3)]
    for card in app.project["cards"]:
        ops = [b.get("op") for effect in card.get("effects",[]) for b in B.walk(effect.get("blocks",[]))]
        group = 2 if "original_play" in ops else 1 if "src_call" in ops else 0
        groups[group].append(card)
    def choose(card, analyze=False):
        if str(getattr(app,"_card_library","")) in app.card_tab.item_panes.panes():
            app.close_card_library()
        app.goto_any("card",card["id"])
        if analyze:
            effects = app.card_tab.effects
            for i,e in enumerate(card.get("effects",[])):
                if e.get("original_effect"):
                    effects.tree.selection_set(effects.tree.get_children()[i])
                    effects.edit(reanalyze=True)
                    break
        win.destroy()
    for rows,title in zip(groups,("편집 가능","호출 연결 가능","미분석 · 재분석 필요")):
        page = ttk.Frame(tabs,padding=6)
        tabs.add(page,text=f"{title} ({len(rows)})")
        listing = tk.Listbox(page,width=70,height=12,exportselection=False)
        listing.pack(fill="both",expand=True)
        for card in rows:
            listing.insert("end",f"{card.get('name_ko','')} ({card['id']})")
        if rows:
            listing.selection_set(0)
            def open_row(analyze=False, lb=listing, cards=rows):
                if lb.curselection():
                    choose(cards[lb.curselection()[0]],analyze)
            listing.bind("<Double-1>",lambda e,fn=open_row:fn())
            ttk.Button(page,text="카드 열기",command=open_row).pack(side="left")
            if title!="편집 가능":
                ttk.Button(page,text="다시 분석",command=lambda fn=open_row:fn(True)).pack(side="left")
            if title=="호출 연결 가능":
                ttk.Button(page,text="같은 호출 연결…",command=lambda:(win.destroy(),unresolved(app))).pack(side="left")
    ttk.Label(win,text="\n".join(notes[1:]),wraplength=650,justify="left",padding=8).pack(anchor="w")
    ttk.Button(win,text="닫기",command=win.destroy).pack()

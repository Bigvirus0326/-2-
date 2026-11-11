"""Native Tk docking regressions. Run: python -m unittest discover -s tests -v.

Uses the real editor widgets with isolated settings, no user project or game assets.
Pointer hit tests are supplied explicitly because test windows stay off-screen.
"""
import contextlib
import itertools
import json
import sys
import tempfile
import tkinter as tk
import traceback
import unittest
from pathlib import Path
from types import SimpleNamespace
from tkinter import ttk
from unittest.mock import patch

import blockcode as B
import blockui
import docking as D
import modgen as M
import sts2_mod_maker as S
import uxkit as U


class DockingRegressionTests(unittest.TestCase):
    operations = 0
    checked_tabs = set()
    checked_panels = set()

    @classmethod
    def setUpClass(cls):
        cls.patches = contextlib.ExitStack()
        cls.patches.enter_context(patch.object(sys, "argv", [sys.argv[0], "--selftest"]))
        cls.patches.enter_context(patch.object(S, "load_settings", return_value={
            "ui_scale": 1.0, "last_project": "", "sts2_path": "", "godot_path": "", "out_dir": ""}))
        cls.patches.enter_context(patch.object(S, "save_settings", return_value=None))
        cls.patches.enter_context(patch.object(S.App, "game_assets", return_value=None))
        cls.patches.enter_context(patch.object(S.App, "log", return_value=None))
        cls.patches.enter_context(patch.object(S, "detect_sts2_path", return_value=""))
        cls.errors = []
        def callback_error(app, typ, value, tb):
            cls.errors.append("".join(traceback.format_exception(typ, value, tb)))
        cls.patches.enter_context(patch.object(S.App, "report_callback_exception", callback_error))
        try:
            cls.app = S.App()
        except tk.TclError:
            cls.patches.close()
            raise
        # Use ordinary off-screen windows. Fully transparent native windows
        # take a separate Windows composition path during wm manage/forget.
        cls.app.state("normal")
        cls.app.geometry("1400x900+5000+5000")
        cls.app.attributes("-alpha", 1)
        original_float = D.prepare_float_window
        def offscreen_float(host,*args,**kwargs):
            original_float(host,*args,**kwargs)
            host.geometry("+5000+5000")
        cls.patches.enter_context(patch.object(D,"prepare_float_window",offscreen_float))
        cls.patches.enter_context(patch.object(U,"prepare_float_window",offscreen_float))
        cls.patches.enter_context(patch.object(blockui,"center_window",lambda win:win.geometry("+5000+5000")))
        cls.app.update()
        cls.nb = cls.app.nb
        cls.baseline = json.dumps(cls.app.project, sort_keys=True)

    @classmethod
    def tearDownClass(cls):
        # Tcl timers outlive Tk windows unless explicitly canceled. Keep this
        # interpreter isolated from subsequent test roots in the same thread.
        for job in cls.app.tk.splitlist(cls.app.tk.call("after","info")):
            cls.app.tk.call("after","cancel",job)
        cls.app.destroy()
        cls.patches.close()
        print(f"\nDocking coverage: {len(cls.checked_tabs)} task tabs, "
              f"{len(cls.checked_panels)} panel identities, {cls.operations} checked transitions")

    def setUp(self):
        self.assertFalse(self.errors, "\n".join(self.errors))
        self.nb.reset_layout()
        for group in D.panel_groups(self.app):
            group.reset_layout()
        self.app.update_idletasks()
        self.assertEqual(json.dumps(self.app.project, sort_keys=True), self.baseline)

    def tearDown(self):
        self.nb._tab_drag.cancel()
        for group in D.panel_groups(self.app):
            group.drag.cancel()
        self.app.update_idletasks()
        self.assertFalse(self.errors, "\n".join(self.errors))
        self.assertEqual(json.dumps(self.app.project, sort_keys=True), self.baseline)

    def test_card_kind_selection_and_curse_defaults(self):
        import copy
        import cardkind as K
        tab = self.app.card_tab
        card = self.app.project["cards"][0]
        saved = copy.deepcopy(card)
        tags = self.app.project["gimmicks"]["tags"]
        saved_tags = copy.deepcopy(tags)
        try:
            tab.load(0)
            tab.type_combo.set_value("Curse")
            tab._type_changed()
            self.assertEqual(card["type"], "Curse")
            self.assertEqual(card["rarity"], "Curse")
            self.assertTrue(tab.kw_vars["Unplayable"].get())
            key = K.create(self.app.project, "테스트 분류", "Skill", "테스트 설명")
            tab.load(0)
            tab.type_combo.set_value(key)
            tab._type_changed()
            self.assertEqual(card["type"], "Skill")
            self.assertEqual(tab.type_combo.get_value(), key)
            tab.changed()
            self.assertIn(key[5:], card["gtags"])
            tab.load(0)
            self.assertEqual(tab.type_combo.get_value(), key)
            tab.type_combo.set_value("Attack")
            tab._type_changed()
            self.assertNotIn(key[5:], card["gtags"])
            self.app.update()
        finally:
            card.clear()
            card.update(saved)
            tags[:] = saved_tags
            tab.load(0)

    def test_no_cost_checkbox_persists_and_disables_number_fields(self):
        import copy
        tab = self.app.card_tab
        card = self.app.project["cards"][0]
        saved = copy.deepcopy(card)
        try:
            tab.load(0)
            tab.vars["x_cost"][1].set(True)
            tab.vars["no_cost"][1].set(True)
            tab.changed()
            self.assertTrue(card["no_cost"])
            self.assertFalse(card["x_cost"])
            self.assertTrue(all(str(w.cget("state")) == "disabled" for w in tab.no_cost_controls))
            tab.load(0)
            self.assertTrue(tab.vars["no_cost"][1].get())
            tab.vars["no_cost"][1].set(False)
            tab.changed()
            self.assertTrue(all(str(w.cget("state")) == "normal" for w in tab.no_cost_controls))
            self.assertEqual(card["cost"], saved["cost"])
        finally:
            card.clear()
            card.update(saved)
            tab.load(0)

    def test_separate_upgrade_effect_editor_saves_and_toggles(self):
        import copy
        tab = self.app.card_tab
        card = self.app.project["cards"][0]
        saved = copy.deepcopy(card)
        draw = B.new_block("draw")
        try:
            tab.load(0)
            with patch.object(blockui, "BlockEditor", return_value=SimpleNamespace(result={"blocks":[draw]})), patch.object(tab, "wait_window"):
                tab.edit_upgrade_effect()
            self.assertTrue(card["separate_upgrade_effect"])
            self.assertEqual(card["upgrade_effect_blocks"], [draw])
            self.assertIn("뽑", tab.upgrade_effect_summary.cget("text"))
            tab.load(0)
            self.assertTrue(tab.vars["separate_upgrade_effect"][1].get())
            tab.vars["separate_upgrade_effect"][1].set(False)
            tab.changed()
            self.assertTrue(card["upgrade_effect_blocks"])
            self.assertEqual(card["effects"], saved["effects"])
        finally:
            card.clear()
            card.update(saved)
            tab.load(0)

    def test_variant_checkboxes_copy_add_remove_without_extra_tabs(self):
        import copy
        tab = self.app.card_tab
        card = self.app.project["cards"][0]
        saved = copy.deepcopy(card)
        try:
            tab.load(0)
            self.assertEqual(len(tab.effect_tabs.tabs()), 4)
            tab.vars["separate_upgrade_effect"][1].set(True)
            tab._change_play_variant()
            self.assertTrue(tab.edit_upgraded_play.get())
            self.assertEqual(card["upgrade_effects"], card["effects"])
            self.assertIsNot(card["upgrade_effects"][0], card["effects"][0])
            tab.effects.effects.append(M.new_effect("draw", 3))
            tab.effects.refresh()
            tab.changed()
            self.assertEqual(card["effects"], saved["effects"])
            tab.effects.tree.selection_set("0")
            tab.effects.remove()
            self.assertEqual(len(card["upgrade_effects"]), len(saved["effects"]))
            for event, panel in tab.event_panels.items():
                original = [B.new_block("energy")]
                card.setdefault("event_blocks", {})[event] = copy.deepcopy(original)
                panel.separate_var.set(True)
                panel.change_variant()
                self.assertTrue(panel.upgraded_var.get())
                self.assertEqual(panel.blocks(), original)
                self.assertIsNot(panel.blocks()[0], card["event_blocks"][event][0])
                panel.blocks().append(B.new_block("block"))
                panel.refresh()
                panel.tree.selection_set("0")
                panel.remove()
                self.assertEqual(card["event_blocks"][event], original)
                self.assertEqual(len(panel.blocks()), 1)
                panel.separate_var.set(False)
                panel.change_variant()
                self.assertEqual(panel.blocks(), original)
                self.assertTrue(card["upgrade_event_blocks"][event])
        finally:
            card.clear()
            card.update(saved)
            tab.load(0)

    def native_tabs(self):
        return [self.nb._k(t) for t in ttk.Notebook.tabs(self.nb)]

    def check_notebook(self):
        native = self.native_tabs()
        self.assertEqual(len(native), len(set(native)))
        self.assertCountEqual(self.nb._visual_order, self.nb._order)
        for key, record in self.nb._pages.items():
            self.assertNotEqual(key in native, record["detached"], record["title"])
            self.assertEqual(record["floating"].get(), record["detached"])
            self.assertTrue(record["host"].winfo_exists())
            if key in native:
                self.assertEqual(ttk.Notebook.tab(self.nb,self.nb._n(key),"state") != "hidden", record["visible"].get())
            else:
                self.assertEqual(record["host"].state() != "withdrawn",record["visible"].get())
        self.assertEqual(native, [k for k in self.nb._visual_order if not self.nb._pages[k]["detached"]])
        type(self).operations += 1

    def check_panels(self, group):
        actual = list(map(str, ttk.PanedWindow.panes(group)))
        expected = [str(group._records[k]["host"]) for k in group._order
                    if group._records[k]["visible"].get() and not group._records[k]["detached"]]
        self.assertEqual(actual, expected, group.title)
        self.assertEqual(len(actual), len(set(actual)))
        for key, record in group._records.items():
            self.assertEqual(record["floating"].get(), record["detached"])
            self.assertTrue(record["content"].winfo_exists())
        type(self).operations += 1

    def show_group(self, group):
        owner = self.nb.page_for_widget(group)
        if owner:
            self.nb.select(owner)
        if group.master in (self.app.fx_tab.painter, self.app.fx_tab.buttons):
            self.app.fx_tab.nb.select(group.master)
        self.app.update_idletasks()

    def float_tab(self, key):
        self.nb.detach(key, position=(400,180))
        self.nb._pages[key]["host"].geometry("+5000+5000")
        self.app.update_idletasks()
        self.check_notebook()

    def float_panel(self, group, key):
        group.detach(key,position=(400,180))
        group._records[key]["host"].geometry("+5000+5000")
        self.app.update_idletasks()
        self.check_panels(group)

    def test_all_tab_insertion_pairs(self):
        keys = self.nb._order[:]
        for source in keys:
            type(self).checked_tabs.add(self.nb._pages[source]["title"])
            for anchor in [*keys,"end"]:
                with self.subTest(source=self.nb._pages[source]["title"], anchor=anchor):
                    old = self.native_tabs()
                    expected = [key for key in old if key != source]
                    if anchor == source:
                        expected = old
                    else:
                        expected.insert(len(expected) if anchor == "end" else expected.index(anchor),source)
                    self.nb._finish_tab(source,0,0,("dock",anchor))
                    self.assertEqual(self.native_tabs(),expected)
                    self.check_notebook()
            self.app.update_idletasks()

    def test_all_tab_pointer_reorder_body_tearoff_and_close(self):
        for source in self.nb._order:
            with self.subTest(tab=self.nb._pages[source]["title"]):
                self.nb.select(source)
                self.app.update_idletasks()
                row = self.nb._tab_strip_height()//2
                other = next(key for key in self.native_tabs() if key != source)
                point = next(x for x in range(0,self.nb.winfo_width(),3)
                             if self.nb._native_tab_at(x,row) == other)
                start,end = self.nb._tab_span(other,point,row)
                x = (start+end)//2+2
                with patch.object(self.nb,"winfo_containing",return_value=self.nb):
                    target = self.nb._probe_tab(source,self.nb.winfo_rootx()+x,self.nb.winfo_rooty()+row)
                    self.assertIsNotNone(target)
                    self.assertEqual(target[1][2],4)
                    self.nb._finish_tab(source,0,0,target[0])
                    self.check_notebook()
                    prior = self.native_tabs()
                    self.nb.select(source)
                    self.app.update_idletasks()
                    self.nb.event_generate("<ButtonPress-1>",x=x,y=row,
                        rootx=self.nb.winfo_rootx()+x,rooty=self.nb.winfo_rooty()+row)
                    # Locate the source again after the reorder, rather than pressing its old label.
                    self.nb._tab_drag.cancel()
                    source_x = next(px for px in range(0,self.nb.winfo_width(),3)
                                    if self.nb._native_tab_at(px,row)==source)
                    self.nb.event_generate("<ButtonPress-1>",x=source_x,y=row,
                        rootx=self.nb.winfo_rootx()+source_x,rooty=self.nb.winfo_rooty()+row)
                    self.assertEqual(self.nb._tab_drag.drag["key"],source)
                    body_y = self.nb._tab_strip_height()+80
                    self.nb.event_generate("<B1-Motion>",x=140,y=body_y,
                        rootx=self.nb.winfo_rootx()+140,rooty=self.nb.winfo_rooty()+body_y)
                    self.nb.event_generate("<ButtonRelease-1>",x=140,y=body_y,
                        rootx=self.nb.winfo_rootx()+140,rooty=self.nb.winfo_rooty()+body_y)
                record = self.nb._pages[source]
                self.assertTrue(record["detached"])
                record["host"].geometry("+5000+5000")
                self.app.update_idletasks()
                self.check_notebook()
                self.app.tk.call(record["host"].protocol("WM_DELETE_WINDOW"))
                self.app.update_idletasks()
                self.assertEqual(self.native_tabs(),prior)
                self.check_notebook()

    def test_release_delivered_to_body_entry(self):
        key = self.nb._order[0]
        self.nb.select(key)
        self.app.update_idletasks()
        row = self.nb._tab_strip_height() // 2
        x = next(px for px in range(self.nb.winfo_width())
                 if self.nb._native_tab_at(px, row) == key)
        body = ttk.Entry(self.nb._pages[key]["box"])
        try:
            self.nb.event_generate("<ButtonPress-1>", x=x, y=row,
                rootx=self.nb.winfo_rootx()+x, rooty=self.nb.winfo_rooty()+row)
            # Native Windows controls may receive the final events instead of
            # the notebook. Deliberately deliver both events to that control.
            for sequence in ("<B1-Motion>", "<ButtonRelease-1>"):
                body.event_generate(sequence, x=10, y=10,
                    rootx=self.nb.winfo_rootx()+150,
                    rooty=self.nb.winfo_rooty()+100)
            self.assertTrue(self.nb._pages[key]["detached"])
            self.assertIsNone(self.nb._tab_drag.drag)
            self.assertEqual(self.nb._tab_drag._capture_bindings, [])
            self.nb.dock(key)
            self.check_notebook()
        finally:
            body.destroy()

    def test_batch_tab_restore_all_close_orders(self):
        keys = self.nb._order[:]
        self.nb._finish_tab(keys[0],0,0,("dock",keys[3]))
        self.nb._finish_tab(keys[-1],0,0,("dock",keys[1]))
        expected = self.native_tabs()
        for close_order in (keys, list(reversed(keys)), keys[::2]+keys[1::2]):
            for key in keys:
                self.float_tab(key)
            self.assertEqual(self.native_tabs(),[])
            for key in close_order:
                self.nb.dock(key)
                self.check_notebook()
            self.assertEqual(self.native_tabs(),expected)
        for key in keys:
            self.nb.set_visible(key,False)
        self.nb.show_all()
        self.assertEqual(self.native_tabs(),expected)
        self.nb.reset_layout()
        self.assertEqual(self.native_tabs(),keys)

    def test_hidden_floating_tabs_and_failed_docking(self):
        for key in self.nb._order:
            with self.subTest(tab=self.nb._pages[key]["title"]):
                self.float_tab(key)
                self.nb.set_visible(key,False)
                self.check_notebook()
                original = ttk.Notebook.insert
                calls = []
                def fail_once(widget,*args,**kw):
                    if widget is self.nb and not calls:
                        calls.append(True)
                        raise tk.TclError("injected insert failure")
                    return original(widget,*args,**kw)
                with patch.object(ttk.Notebook,"insert",new=fail_once):
                    with self.assertRaises(tk.TclError):
                        self.nb.dock(key)
                self.check_notebook()
                self.nb.select(key)
                self.check_notebook()
                self.nb.dock(key)
                self.check_notebook()

    def test_reset_restores_every_card_panel_permutation(self):
        self.app.open_card_library()
        group = self.app.card_tab.item_panes
        keys = group._default_order[:]
        for permutation in itertools.permutations(keys):
            for key in permutation:
                group.dock(key,before="end")
            self.assertEqual(group._order,list(permutation))
            group.reset_layout()
            self.check_panels(group)
            self.assertEqual(group._order,keys)

    def test_destroy_notebook_cancels_scheduled_drag_and_bindings(self):
        frame = ttk.Frame(self.app)
        frame.place(x=0,y=0,width=400,height=260)
        notebook = U.ScrollNotebook(frame)
        notebook.pack(fill="both",expand=True)
        notebook.add_scrolled(lambda p:ttk.Frame(p),"temporary")
        self.app.update_idletasks()
        key = notebook._order[0]
        with patch.object(notebook._tab_drag,"probe",return_value=("end",(10,10,80,30))):
            notebook._tab_drag.start(SimpleNamespace(widget=notebook,x_root=10,y_root=10),key)
            notebook._tab_drag.motion(SimpleNamespace(x_root=50,y_root=50))
            ghost=notebook._tab_drag.ghost
            notebook._tab_drag.motion(SimpleNamespace(x_root=70,y_root=60))
            self.assertIsNotNone(notebook._tab_drag._motion_job)
            notebook._notify()
            notebook.destroy()
        self.assertFalse(ghost.winfo_exists())
        self.assertIsNone(notebook._tab_drag._motion_job)
        self.assertIsNone(notebook._notify_job)
        self.assertIn(self.nb._focus_binding,self.app.bind_all("<FocusIn>"))
        frame.destroy()
        self.app.update()

    def test_every_internal_panel_reorder_float_close_and_hide(self):
        self.app.open_card_library()
        groups = list(D.panel_groups(self.app))
        for group in groups:
            self.show_group(group)
            keys = group._order[:]
            for source in keys:
                record = group._records[source]
                type(self).checked_panels.add((group.title,record["title"]))
                widget,parent = record["content"],record["content"].master
                for anchor in [*keys,"end"]:
                    with self.subTest(group=group.title,panel=record["title"],anchor=anchor):
                        group._finish(source,0,0,anchor)
                        self.check_panels(group)
                before = group._order[:]
                self.float_panel(group,source)
                group.set_visible(source,False)
                self.check_panels(group)
                group.set_visible(source,True)
                self.check_panels(group)
                self.app.tk.call(record["host"].protocol("WM_DELETE_WINDOW"))
                self.check_panels(group)
                self.assertEqual(group._order,before)
                self.assertIs(record["content"],widget)
                self.assertIs(widget.master,parent)
                group.set_visible(source,False)
                self.check_panels(group)
                group.show_all()
                self.check_panels(group)
            group.reset_layout()
            self.check_panels(group)

    def test_mixed_floating_panels_tabs_and_library_swap(self):
        tab = self.app.card_tab
        group = tab.item_panes
        for content in (tab.item_editor,tab.pv):
            self.float_panel(group,str(content))
        self.float_tab(self.nb._o(tab))
        self.app.open_card_library()
        self.check_panels(group)
        self.app.close_card_library()
        self.check_panels(group)
        self.app.tk.call(self.nb._pages[self.nb._o(tab)]["host"].protocol("WM_DELETE_WINDOW"))
        self.check_notebook()
        for content in (tab.item_editor,tab.pv):
            record = group._records[str(content)]
            self.app.tk.call(record["host"].protocol("WM_DELETE_WINDOW"))
        self.check_panels(group)

    def test_tab_and_panel_failed_transitions_recover(self):
        key = self.nb._order[2]
        with patch.object(U,"prepare_float_window",side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                self.nb.detach(key)
        self.check_notebook()
        group = self.app.card_tab.item_panes
        source = str(self.app.card_tab.pv)
        with patch.object(D,"prepare_float_window",side_effect=RuntimeError("injected")):
            with self.assertRaises(RuntimeError):
                group.detach(source)
        self.check_panels(group)
        self.float_panel(group,source)
        with patch.object(group,"_insert",side_effect=tk.TclError("injected")):
            with self.assertRaises(tk.TclError):
                group.dock(source)
        self.assertTrue(group._records[source]["detached"])
        self.check_panels(group)
        group.dock(source)
        group.set_visible(source,False)
        with patch.object(group,"_insert",side_effect=tk.TclError("injected")):
            with self.assertRaises(tk.TclError):
                group.set_visible(source,True)
        self.check_panels(group)
        old = group._order[:]
        with self.assertRaises(ValueError):
            group.dock(source,before="not-a-pane")
        self.assertEqual(group._order,old)
        group.add(source,before=source)
        self.check_panels(group)

    def test_checkmarks_bulk_activation_and_menu_cache(self):
        view = self.app.view_menu
        tab_index = next(i for i in range(view.index("end")+1)
                         if view.type(i)=="cascade" and view.entrycget(i,"label")=="작업 탭 표시")
        menu = self.app.nametowidget(view.entrycget(tab_index,"menu"))
        for i,key in enumerate(self.nb._order):
            self.assertTrue(menu.entrycget(i,"label").startswith("✓  "))
            menu.invoke(i)
            self.assertTrue(menu.entrycget(i,"label").startswith("□  "))
            self.check_notebook()
        for group in D.panel_groups(self.app):
            for key in group._order:
                group.set_visible(key,False)
        activate = next(i for i in range(view.index("end")+1)
                        if view.type(i)=="command" and view.entrycget(i,"label")=="모두 활성화")
        view.invoke(activate)
        self.assertTrue(all(r["visible"].get() for r in self.nb._pages.values()))
        for group in D.panel_groups(self.app):
            self.assertTrue(all(r["visible"].get() for r in group._records.values()))
            self.check_panels(group)
        self.check_notebook()

    def test_drag_feedback_reuse_and_close_cleanup(self):
        self.nb.select(self.app.mod_tab)
        self.app.update_idletasks()
        calls=[]
        def probe(key,x,y):
            calls.append((x,y))
            return "end",(20,20,100,30)
        finished=[]
        drag = D.DockDrag(self.nb,probe,lambda *args:finished.append(args))
        drag.start(SimpleNamespace(widget=self.nb,x_root=20,y_root=20),"key")
        drag.motion(SimpleNamespace(x_root=60,y_root=60))
        window=drag.preview
        for x in range(100,200):
            drag.motion(SimpleNamespace(x_root=x,y_root=60))
        self.assertEqual(len(calls),1)
        self.assertIs(drag.preview,window)
        drag.release(SimpleNamespace(x_root=250,y_root=60))
        self.assertEqual(finished[-1][1:3],(250,60))
        self.assertIsNone(drag._motion_job)
        self.assertIsNone(drag.ghost)
        self.assertIsNone(drag.preview)

    def test_selected_card_numeric_blocks_render_and_compile(self):
        card = M.new_card("test_numeric_edits")
        block = B.new_block("random_each")
        block["body"] = [B.new_block("card_cost_edit"), B.new_block("card_damage_edit")]
        editor = blockui.BlockEditor(self.app,self.app.project,"card",card,[block])
        editor.geometry("+5000+5000")
        try:
            editor.update()
            editor.render()
            editor.update_idletasks()
            self.assertTrue(editor.canvas.find_all())
            _, errors = B.compile_blocks(editor.blocks,self.app.project,M._Ctx("card",card))
            self.assertEqual(errors,[])
        finally:
            editor.destroy()

    def test_expanded_stat_and_compact_blocks_render(self):
        import copy
        import fxbtn
        project=copy.deepcopy(self.app.project)
        project.setdefault("gimmicks",{})["buttons"]=[fxbtn.new_button("compact_test")]
        card=M.new_card("expanded_numeric_test")
        block=B.new_block("random_each")
        block["body"]=[]
        for stat,_ in B.CARD_STATS:
            edit=B.new_block("card_number_edit")
            edit["args"]["stat"]=stat
            block["body"].append(edit)
        blocks=[block,B.new_block("edit_var"),B.new_block("card_state_edit"),B.new_block("button_switch")]
        blocks[-1]["args"]["button"]="compact_test"
        editor=blockui.BlockEditor(self.app,project,"card",card,blocks)
        editor.geometry("+5000+5000")
        try:
            editor.update()
            editor.render()
            editor.update_idletasks()
            _,errors=B.compile_blocks(editor.blocks,project,M._Ctx("card",card))
            self.assertEqual(errors,[])
            self.assertTrue(editor.canvas.find_all())
        finally:
            editor.destroy()

    def test_every_compact_family_mode_renders_and_selection_combo_switches(self):
        card=M.new_card("family_ui")
        editor=blockui.BlockEditor(self.app,self.app.project,"card",card,[])
        editor.geometry("+5000+5000")
        try:
            for family,_title,variants in B.F.GROUPS:
                block=B.new_block(family)
                for mode,_label in variants:
                    with self.subTest(family=family,mode=mode):
                        B.F.switch(block,mode,B.SPECS)
                        editor.blocks=[block]
                        editor.render()
                        editor.update_idletasks()
                        self.assertTrue(editor.canvas.find_all())
            selection=B.new_block("select_cards")
            selection["body"]=[B.new_block("card_number_edit")]
            selection["args"]["count"]={"t":"num","v":3}
            editor.blocks=[selection]
            editor.render()
            def children(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from children(child)
            for mode in ("random_each","pick_each"):
                combo=next(w for frame in editor.frames for w in children(frame)
                           if isinstance(w,blockui._Combo) and {v for v,_ in w.opts}=={"pick_each","random_each"})
                combo.set_value(mode)
                combo.event_generate("<<ComboboxSelected>>")
                editor.update()
                self.assertEqual(selection["args"]["mode"],mode)
                self.assertEqual(selection["args"]["count"]["v"],3)
                self.assertEqual(len(selection["body"]),1)
        finally:
            editor.destroy()

    def test_enemy_condition_fields_switch_without_losing_values(self):
        card = M.new_card("enemy_conditions")
        block = B.new_block("select_enemies")
        B.F.switch(block, "filtered_enemies", B.SPECS)
        editor = blockui.BlockEditor(self.app, self.app.project, "card", card, [block])
        block = editor.blocks[0]
        editor.geometry("+5000+5000")
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        def select(key, value):
            combo = next(w for frame in editor.frames for w in children(frame)
                         if isinstance(w, blockui._Combo) and key in {v for v, _ in w.opts})
            combo.set_value(value)
            combo.event_generate("<<ComboboxSelected>>")
            editor.update()
        try:
            editor.update()
            select("hp_below", "hp_below")
            self.assertEqual(block["args"]["enemy_filter"], "hp_below")
            self.assertIn("{limit}", B.block_caption(block))
            self.assertNotIn("{power}", B.block_caption(block))
            select("choose", "choose")
            select("hp_below", "power")
            self.assertIn("{power}", B.block_caption(block))
            self.assertEqual(block["args"]["limit"]["v"], 30)
            self.assertEqual(block["args"]["enemy_mode"], "choose")
            select("choose", "all")
            self.assertNotIn("{count}", B.block_caption(block))
        finally:
            editor.destroy()

    def test_compound_condition_dialog_add_edit_delete_and_modes(self):
        card = M.new_card("compound_ui")
        editor = blockui.BlockEditor(self.app,self.app.project,"card",card,[])
        editor.geometry("+5000+5000")
        dialog = None
        def children(widget):
            for child in widget.winfo_children():
                yield child
                yield from children(child)
        def button(text):
            return next(w for w in children(dialog.fields) if isinstance(w,ttk.Button) and w.cget("text")==text)
        try:
            editor.update()
            initial = {"t":"group","mode":"all","scope":"creature","items":[{"t":"has","who":"it","power":"Weak"}]}
            dialog = blockui.SlotDialog(editor,editor,"cond",initial)
            half = {"t":"hp_percent","who":"it","op":"<=","value":{"t":"num","v":50}}
            with patch.object(blockui,"SlotDialog",return_value=SimpleNamespace(result=half)), patch.object(dialog,"wait_window"):
                button("+ 조건 추가").invoke()
            self.assertEqual(len(dialog.data["items"]),2)
            combo = next(w for w in children(dialog.fields) if isinstance(w,blockui._Combo) and ("any","하나 이상 만족 (또는)") in w.opts)
            combo.set_value("any")
            combo.event_generate("<<ComboboxSelected>>")
            dialog.update()
            self.assertEqual(dialog.data["mode"],"any")
            listing = next(w for w in children(dialog.fields) if isinstance(w,tk.Listbox))
            listing.selection_set(0)
            button("삭제").invoke()
            self.assertEqual(dialog.data["items"],[half])
            self.assertEqual(len(initial["items"]),1)
            for kind in ("hp_percent","pile_count","card_identity","group","has","card_is"):
                dialog._type_changed(kind)
                dialog.update_idletasks()
                self.assertTrue(dialog.fields.winfo_children())
            dialog._type_changed("pile_count")
            self.assertEqual(dialog.data["who"],"it")
            self.assertEqual(dialog.data["pile"],"Deck")
            dialog.ok()
            dialog = None
        finally:
            if dialog is not None:
                dialog.destroy()
            editor.destroy()

    def test_card_list_drag_selection_reorder_filtered_move_delete_and_cancel(self):
        import copy
        tab = self.app.card_tab
        original = copy.deepcopy(self.app.project)
        active = self.nb.select()
        self.nb.select(tab)
        self.app.update()
        def event(row=None, column="#0", after=False, widget=None, blank=False):
            if widget is not None:
                xr,yr = widget.winfo_rootx()+10,widget.winfo_rooty()+10
                x,y = xr-tab.tree.winfo_rootx(),yr-tab.tree.winfo_rooty()
            else:
                box = tab.tree.bbox(str(row),column)
                self.assertTrue(box,(row,column))
                x,y = box[0]+min(12,box[2]//2),box[1]+(box[3]-2 if after else 2)
                if blank:
                    x=-6
                xr,yr = tab.tree.winfo_rootx()+x,tab.tree.winfo_rooty()+y
            return SimpleNamespace(x=x,y=y,x_root=xr,y_root=yr,state=0)
        def refresh():
            tab.refresh_list(0)
            self.app.update()
        def move(rows,target,after=False):
            tab.tree.selection_set([str(i) for i in rows])
            tab._drag_start(event(rows[0]))
            e=event(target,after=after)
            tab._drag_move(e)
            self.assertEqual(tab.card_drag.state['drop'][0],'move')
            self.assertTrue(tab.card_drag.marker.winfo_manager())
            tab._drag_end(e)
            self.app.update()
        try:
            self.app.project['cards'] = [M.new_card(f"drag_{i}") for i in range(8)]
            refresh()
            ids=[x['id'] for x in tab.items]
            with patch.object(self.app,"mark_dirty") as dirty:
                tab._drag_start(event(1,blank=True))
                tab._drag_move(event(3,after=True))
                self.assertTrue(all(edge.winfo_manager() for edge in tab.card_drag.selection_edges))
                tab._drag_end(event(3,after=True))
                self.assertFalse(any(edge.winfo_manager() for edge in tab.card_drag.selection_edges))
                self.assertEqual(tab.selected(),[1,2,3])
                self.assertEqual([x['id'] for x in tab.items],ids)
                dirty.assert_not_called()
                start,end=event(0,blank=True),event(2,after=True)
                tab.card_selection_margin.event_generate('<ButtonPress-1>',x=6,y=start.y)
                tab.tree.event_generate('<B1-Motion>',x=end.x,y=end.y)
                tab.tree.event_generate('<ButtonRelease-1>',x=end.x,y=end.y)
                self.app.update()
                self.assertEqual(tab.selected(),[0,1,2])
                self.assertEqual([x['id'] for x in tab.items],ids)
                # Tk sends a release on an outline to that child, even with
                # a grab on its parent tree. Every edge must finish the drag.
                for edge in tab.card_drag.selection_edges:
                    tab._drag_start(event(1,blank=True))
                    end=event(3,after=True)
                    tab._drag_move(end)
                    self.app.update_idletasks()
                    edge.event_generate('<ButtonRelease-1>',x=1,y=1,rootx=end.x_root,rooty=end.y_root)
                    self.app.update()
                    self.assertIsNone(tab.card_drag.state)
                    self.assertEqual(tab.selected(),[1,2,3])
                    self.assertFalse(any(w.winfo_manager() for w in tab.card_drag.selection_edges))
                    self.assertIsNone(tab.card_drag.scroll_job)
                    self.assertIsNone(tab.card_drag.release_bind)
                    self.assertIsNone(tab.tree.grab_current())
                # A release on another child of the same window is caught
                # by the temporary window binding, without triggering a drop
                # twice or disturbing unrelated window release handlers.
                tab._drag_start(event(1,blank=True))
                tab._drag_move(event(3,after=True))
                self.app.update_idletasks()
                end=event(3,after=True)
                tab.card_drag_status.event_generate('<ButtonRelease-1>',x=1,y=1,rootx=end.x_root,rooty=end.y_root)
                self.app.update()
                self.assertIsNone(tab.card_drag.state)
                self.assertFalse(any(w.winfo_manager() for w in tab.card_drag.selection_edges))
                tab._drag_start(event(1,blank=True))
                tab._drag_move(event(3,after=True))
                tab.card_drag._recover_release(SimpleNamespace(state=0))
                self.assertIsNone(tab.card_drag.state)
                self.assertEqual(tab.selected(),[1,2,3])
                self.assertFalse(any(w.winfo_manager() for w in tab.card_drag.selection_edges))
                tab._drag_start(event(1,blank=True))
                tab._drag_move(event(3,after=True))
                with patch.object(tab.card_drag,'move',side_effect=RuntimeError('release failure')):
                    with self.assertRaises(RuntimeError):
                        tab._drag_end(event(3,after=True))
                self.assertIsNone(tab.card_drag.state)
                self.assertFalse(any(w.winfo_manager() for w in tab.card_drag.selection_edges))
                last=tab.tree.bbox('7')
                y=last[1]+last[3]+12
                blank=SimpleNamespace(x=20,y=y,x_root=tab.tree.winfo_rootx()+20,y_root=tab.tree.winfo_rooty()+y,state=0)
                further=SimpleNamespace(x=40,y=y+10,x_root=blank.x_root+20,y_root=blank.y_root+10,state=0)
                tab._drag_start(blank)
                tab._drag_move(further)
                self.assertEqual(tab.selected(),[])
                tab._drag_end(further)
                tab._drag_start(blank)
                tab._drag_move(event(5))
                tab._drag_end(event(5))
                self.assertEqual(tab.selected(),[5,6,7])
                self.assertEqual([x['id'] for x in tab.items],ids)
                move([1,2],5,True)
                self.assertEqual([x['id'] for x in tab.items],[ids[i] for i in [0,3,4,5,1,2,6,7]])
                self.assertEqual(tab.selected(),[4,5])
                self.assertIsNone(tab.tree.grab_current())
                before=[x['id'] for x in tab.items]
                tab._drag_start(event(4))
                tab._drag_move(event(0))
                tab.card_drag.cancel()
                self.assertEqual([x['id'] for x in tab.items],before)
                self.assertEqual(tab.selected(),[4,5])
                self.assertFalse(tab.card_drag.marker.winfo_manager())
                tab._drag_start(event(4))
                outside=SimpleNamespace(x=-100,y=-100,x_root=tab.tree.winfo_rootx()-100,y_root=tab.tree.winfo_rooty()-100,state=0)
                tab._drag_move(outside)
                tab._drag_end(outside)
                self.assertEqual([x['id'] for x in tab.items],before)
                # Filtered reorder must retain every hidden row.
                self.app.project['cards'] = [M.new_card(f"drag_{i}") for i in range(8)]
                for i,c in enumerate(tab.items):
                    c['name_ko']='visible' if i%2 else 'hidden'
                tab.set_query('visible')
                self.app.update()
                move([1,3],7,True)
                self.assertEqual([x['id'] for x in tab.items],[ids[i] for i in [0,2,4,5,6,7,1,3]])
                self.assertEqual(len(tab.items),8)
                tab.set_query('')
                self.app.update()
                # A delete drop respects cancellation and uses existing ref cleanup.
                tab.tree.selection_set(('1','2'))
                tab._drag_start(event(1))
                drop=event(widget=tab.card_delete_zone)
                tab._drag_move(drop)
                before=copy.deepcopy(tab.items)
                with patch.object(S.messagebox,'askyesno',return_value=False):
                    tab._drag_end(drop)
                self.assertEqual(tab.items,before)
                tab._drag_start(event(1))
                tab._drag_move(drop)
                with patch.object(S.messagebox,'askyesno',return_value=True), patch.object(self.app,'rename_ref') as refs:
                    tab._drag_end(drop)
                self.assertEqual(len(tab.items),6)
                self.assertEqual(refs.call_count,2)
                self.assertIsNone(tab.tree.grab_current())
                self.app.project['cards']=[M.new_card(f"long_{i}") for i in range(80)]
                refresh()
                tab.tree.yview_moveto(0)
                self.app.update()
                tab._drag_start(event(0,blank=True))
                bottom=SimpleNamespace(x=12,y=tab.tree.winfo_height()-2,x_root=tab.tree.winfo_rootx()+12,y_root=tab.tree.winfo_rooty()+tab.tree.winfo_height()-2,state=0)
                before_view=tab.tree.yview()
                tab._drag_move(bottom)
                done=tk.BooleanVar(self.app,value=False)
                self.app.after(180,lambda:done.set(True))
                self.app.wait_variable(done)
                self.assertGreater(tab.tree.yview()[0],before_view[0])
                tab.card_drag.cancel()
                self.assertIsNone(tab.card_drag.scroll_job)
        finally:
            tab.card_drag.cancel()
            self.app.project.clear()
            self.app.project.update(original)
            tab.query=''
            tab.refresh_list(0)
            if active:
                self.nb.select(active)
            self.app.update()

    def test_existing_family_in_unsupported_owner_remains_editable(self):
        item=M.new_power("unsupported_family")
        for family,mode in (("damage_action","card_attack"),("manosaba_summon_action","manosaba_ema_summon")):
            block=B.new_block(family)
            B.F.switch(block,mode,B.SPECS)
            editor=blockui.BlockEditor(self.app,self.app.project,"power",item,[block])
            editor.geometry("+5000+5000")
            try:
                editor.update_idletasks()
                self.assertEqual(editor.blocks[0]["args"]["mode"],mode)
                self.assertTrue(editor.canvas.find_all())
            finally:
                editor.destroy()

    def test_hand_aura_block_editor_renders_stat_and_filter_lists(self):
        card=self.app.project["cards"][0]
        editor=blockui.BlockEditor(self.app,self.app.project,"card",card,[B.new_block("hand_aura_stat")],
                                   show_text=False,card_event="hand_aura")
        editor.geometry("+5000+5000")
        try:
            editor.update_idletasks()
            self.assertIn("TryModifyEnergyCostInCombat",editor.code.get("1.0","end"))
            def descend(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from descend(child)
            combos=[w for w in descend(editor) if isinstance(w,blockui._Combo)]
            stat=next(w for w in combos if {value for value,_ in w.opts}=={"cost","damage","block"})
            stat.set_value("damage")
            stat.event_generate("<<ComboboxSelected>>")
            self.assertIn("ModifyDamageAdditive",editor.code.get("1.0","end"))
            pile=next(w for w in combos if {value for value,_ in w.opts}=={"Hand","Draw","Discard"})
            pile.set_value("Draw")
            pile.event_generate("<<ComboboxSelected>>")
            self.assertIn("PileType.Draw.GetPile(Owner)",editor.code.get("1.0","end"))
            self.assertNotIn("⚠",editor.err.cget("text"))
        finally:
            editor.destroy()

    def test_saved_effect_and_power_aura_editors_render(self):
        power=B.new_block("aura_power_amount")
        effect=B.new_block("aura_card_effect")
        effect["body"]=[B.new_block("energy")]
        editor=blockui.BlockEditor(self.app,self.app.project,"card",self.app.project["cards"][0],[power,effect],
                                   show_text=False,card_event="hand_aura")
        editor.geometry("+5000+5000")
        try:
            editor.update_idletasks()
            code=editor.code.get("1.0","end")
            self.assertIn("ModifyPowerAmountGivenAdditive",code)
            self.assertIn("PlayerCmd.GainEnergy",code)
            self.assertNotIn("⚠",editor.err.cget("text"))
        finally:
            editor.destroy()

    def test_beginner_help_on_preview_fields_and_value_dialog(self):
        card=M.new_card("beginner_help")
        block=B.new_block("upgrade_card_action")
        editor=blockui.BlockEditor(self.app,self.app.project,"card",card,[block])
        editor.geometry("+5000+5000")
        dialog=None
        try:
            editor.update_idletasks()
            def children(widget):
                for child in widget.winfo_children():
                    yield child
                    yield from children(child)
            widgets=[w for frame in editor.frames for w in children(frame)]
            style=next(w for w in widgets if isinstance(w,blockui._Combo) and any("GridLayout" in str(value) for value,_ in w.opts))
            self.assertTrue(hasattr(style,"_maker_help"))
            self.assertIn("기본 배치",style._maker_help.text())
            labels=[w for w in widgets if isinstance(w,tk.Label) and hasattr(w,"_maker_help")]
            self.assertTrue(any("실제로 강화" in w._maker_help.text() for w in labels))
            dialog=blockui.SlotDialog(editor,editor,"value",{"t":"num","v":2})
            self.assertIn("강화 증가량",dialog.type._maker_help.text())
            dialog._type_changed("stack")
            dialog.update_idletasks()
            self.assertIn("중독",dialog.type._maker_help.text())
            self.assertTrue(all(hasattr(w,"_maker_help") for w in dialog.fields.winfo_children()))
            dialog.destroy()
            dialog=None
        finally:
            if dialog is not None:
                dialog.destroy()
            editor.destroy()

    def test_favorites_preserve_rows_and_bypass_advanced_filter(self):
        card = M.new_card("test_favorites")
        editor = blockui.BlockEditor(self.app,self.app.project,"card",card,[])
        editor.geometry("+5000+5000")
        try:
            with tempfile.TemporaryDirectory() as folder:
                editor.favorite_file = Path(folder)/"favorites.json"
                editor.favorites = set()
                editor.show_advanced.set(True)
                editor._build_palette()
                op = next(op for op, _, _ in editor._favorite_candidates
                          if blockui._advanced_palette_block(op, B.SPECS[op]))
                rows = list(editor.palette.winfo_children())
                editor._toggle_favorite(op)
                self.assertEqual(rows, editor.palette.winfo_children())
                self.assertEqual(json.loads(editor.favorite_file.read_text()), [op])
                editor.show_advanced.set(False)
                editor._apply_palette_visibility()
                self.assertEqual(rows, editor.palette.winfo_children())
                stars = [star for candidate,star in editor._palette_stars if candidate==op and star.master.master == editor._favorites_frame]
                self.assertEqual(len(stars),1)
                self.assertEqual(stars[0].master.master, editor._favorites_frame)
                self.assertEqual(stars[0].pack_info()["side"],"left")
                rows = list(editor.palette.winfo_children())
                editor._toggle_favorite(op)
                self.assertEqual(rows,editor.palette.winfo_children())
                self.assertNotIn(op, editor._favorite_rows)
                editor._toggle_favorite("damage")
                editor._toggle_favorite("draw")
                favorite_rows = dict(editor._favorite_rows)
                editor._move_favorite("draw", 0)
                self.assertEqual(editor.favorite_order, [B.compact_op("draw"), B.compact_op("damage")])
                self.assertEqual(json.loads(editor.favorite_file.read_text()), [B.compact_op("draw"), B.compact_op("damage")])
                self.assertEqual(favorite_rows, editor._favorite_rows)
                editor._build_palette()
                self.assertEqual(list(editor._favorite_rows), [B.compact_op("draw"), B.compact_op("damage")])
                cached = editor.palette.winfo_children()
                for show in (True,False,True):
                    editor.show_advanced.set(show)
                    editor._apply_palette_visibility()
                    self.assertEqual(cached, editor.palette.winfo_children())
                    for widget, advanced in editor._palette_visibility:
                        self.assertEqual(bool(widget.winfo_manager()), show or not advanced)
        finally:
            editor.destroy()

    def test_scrolling_keeps_controls_and_canvas_items(self):
        tab = self.app.card_tab
        self.nb.select(tab)
        self.app.update()
        area = tab.item_editor
        area._sync()
        widgets = tuple(tab.form.winfo_children())
        items = area.canvas.find_all()
        start = area.canvas.yview()[0]
        combo = tab.vars["type"][1]
        original_type = combo.get_value()
        with patch.object(self.app,"winfo_containing",return_value=combo):
            combo.event_generate("<MouseWheel>",state=0,delta=-120,x=0,y=0,rootx=0,rooty=0)
        self.app.update()
        self.assertEqual(combo.get_value(),original_type)
        self.assertGreater(area.canvas.yview()[0],start)
        for _ in range(5):
            area.canvas.yview_scroll(1,"units")
            self.app.update_idletasks()
        self.app.update()
        self.assertGreater(area.canvas.yview()[0],start)
        self.assertEqual(tuple(tab.form.winfo_children()),widgets)
        self.assertEqual(area.canvas.find_all(),items)
        area.canvas.yview_moveto(0)

    def test_scale_applies_without_recreating_editor(self):
        old = self.app.ui_scale
        geometry = self.app.geometry()
        self.app.geometry("760x700+5000+5000")
        self.app.update()
        self.app._fit_toolbar()
        tab = self.app.card_tab
        self.nb.select(tab)
        widgets = tuple(tab.form.winfo_children())
        try:
            with patch.object(U,"apply_theme",wraps=U.apply_theme) as theme:
                self.app.set_scale(1.25)
                theme.assert_not_called()
            self.app.update()
            self.assertEqual(self.app.ui_scale,1.25)
            self.assertEqual(self.app.scale_var.get(),125)
            self.assertEqual(int(tab.pv.canvas.cget("width")),int(360*self.app.ui))
            self.assertEqual(int(tab.pv.canvas.cget("height")),int(480*self.app.ui))
            self.assertEqual(tuple(tab.form.winfo_children()),widgets)
            self.assertIs(self.app.card_tab,tab)
            self.app._fit_toolbar()
            self.app.update_idletasks()
            right = self.app._tb.winfo_rootx()+self.app._tb.winfo_width()
            for button,_,_ in self.app._tb_texts[:7]:
                self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),right)
        finally:
            self.app.set_scale(old)
            self.app.geometry(geometry)
            self.app.update()

    def test_editor_focus_layout_and_responsive_toolbar(self):
        app = self.app
        previous_state, previous_geometry = app.state(),app.geometry()
        try:
            app.state("normal")
            for width in (760,1024,1440):
                app.geometry(f"{width}x700+5000+5000")
                app.update_idletasks()
                app._fit_toolbar()
                app.update_idletasks()
                right = app._tb.winfo_rootx()+app._tb.winfo_width()
                for button,_,_ in app._tb_texts[:7]:
                    self.assertTrue(button.winfo_ismapped())
                    self.assertLessEqual(button.winfo_rootx()+button.winfo_width(),right)
            tab = app.card_tab
            tab.set_editor_layout(True)
            self.assertFalse(tab.item_panes._records[str(tab.pv)]["visible"].get())
            self.assertFalse(tab.item_panes._records[str(tab.item_list)]["visible"].get())
            self.assertTrue(tab.item_panes._records[str(tab.item_editor)]["visible"].get())
            tab.set_editor_layout(False)
            self.assertTrue(tab.item_panes._records[str(tab.pv)]["visible"].get())
            self.assertTrue(tab.item_panes._records[str(tab.item_list)]["visible"].get())
        finally:
            app.geometry(previous_geometry)
            app.state(previous_state)

    def test_block_editor_float_drag_save_and_close(self):
        self._exercise_block_editor_float_close()

    def test_repeated_block_editor_float_close(self):
        for _ in range(3):
            self._exercise_block_editor_float_close()

    def _exercise_block_editor_float_close(self):
        card = M.new_card("test_drag")
        editor = blockui.BlockEditor(self.app,self.app.project,"card",card,
                                      [B.new_block("damage"),B.new_block("draw")])
        editor.geometry("+5000+5000")
        try:
            group=editor.block_panes
            for key,record in group._records.items():
                type(self).checked_panels.add((group.title,record["title"]))
                self.float_panel(group,key)
                self.assertEqual(str(record["host"].transient()),str(editor))
            library = group.floating_window(editor.library_panel)
            workspace = group.floating_window(editor.workspace_panel)
            old_owner = library.transient()
            event=SimpleNamespace(widget=editor.canvas,x_root=library.winfo_rootx()+40,y_root=library.winfo_rooty()+80)
            with tempfile.TemporaryDirectory(prefix="sts2-docking-regression-") as folder:
                editor.preset_dir=Path(folder)
                editor.saved_presets={}
                def name(*args,**kwargs):
                    self.assertIsNone(editor._drag_feedback)
                    self.assertFalse(editor._drag_window_owners)
                    return "test bundle"
                with patch.object(editor,"winfo_containing",return_value=library.winfo_children()[0]), patch.object(blockui.simpledialog,"askstring",side_effect=name):
                    editor.group_blocks=editor.blocks[:]
                    editor.group_source=editor.blocks
                    editor.group_anchor=(-100,-100)
                    editor.group_moving=True
                    editor._group_motion(event)
                    self.assertEqual(str(library.transient()),str(workspace))
                    self.assertIn("2개",editor._drag_feedback["badge"].cget("text"))
                    editor._group_end(event)
                self.assertEqual(len(editor.blocks),2)
                self.assertEqual(len(next(iter(editor.saved_presets.values()))["blocks"]),2)
                self.assertEqual(library.transient(),old_owner)
            for record in group._records.values():
                self.app.tk.call(record["host"].protocol("WM_DELETE_WINDOW"))
                self.assertFalse(record["detached"])
            self.check_panels(group)
        finally:
            editor.destroy()


if __name__ == "__main__":
    unittest.main()

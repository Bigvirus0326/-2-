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

    def native_tabs(self):
        return list(map(str, ttk.Notebook.tabs(self.nb)))

    def check_notebook(self):
        native = self.native_tabs()
        self.assertEqual(len(native), len(set(native)))
        self.assertCountEqual(self.nb._visual_order, self.nb._order)
        for key, record in self.nb._pages.items():
            self.assertNotEqual(key in native, record["detached"], record["title"])
            self.assertEqual(record["floating"].get(), record["detached"])
            self.assertTrue(record["host"].winfo_exists())
            if key in native:
                self.assertEqual(ttk.Notebook.tab(self.nb,key,"state") != "hidden", record["visible"].get())
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
                self.assertEqual(editor.favorite_order, ["draw", "damage"])
                self.assertEqual(json.loads(editor.favorite_file.read_text()), ["draw", "damage"])
                self.assertEqual(favorite_rows, editor._favorite_rows)
                editor._build_palette()
                self.assertEqual(list(editor._favorite_rows), ["draw", "damage"])
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

import time
import tkinter as tk
from tkinter import ttk
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import uxkit as U


class RefreshTests(TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()

    def tearDown(self):
        self.root.destroy()

    def test_canvas_keeps_previous_frame_until_commit_and_recovers_on_error(self):
        canvas = tk.Canvas(self.root)
        old = canvas.create_text(0,0,text="old")
        owner = SimpleNamespace(canvas=canvas)
        @U.buffered_canvas("canvas", defer_new=True)
        def draw(obj, fail=False):
            obj.canvas.delete("all")
            new = obj.canvas.create_rectangle(0,0,20,20)
            obj.canvas.update_idletasks()
            self.assertEqual(canvas.type(old),"text")
            self.assertEqual(canvas.find_all(), (old,))
            if fail:
                raise ValueError("test")
            return "drawn"
        with self.assertRaises(ValueError):
            draw(owner,True)
        self.assertEqual(canvas.find_all(),(old,))
        draw(owner)
        self.assertEqual(len(canvas.find_all()),1)
        self.assertEqual(canvas.type(canvas.find_all()[0]),"rectangle")
        canvas.delete("all")
        self.assertEqual(canvas.find_all(),())

    def test_tree_reuses_rows_and_reports_filtered_count(self):
        tree = ttk.Treeview(self.root)
        owner = SimpleNamespace(tree=tree)
        @U.stable_tree()
        def refresh(obj, values):
            obj.tree.delete(*obj.tree.get_children())
            for key,text in values:
                obj.tree.insert("","end",iid=key,text=text)
            return obj.tree.get_children()
        refresh(owner,[("a","first"),("b","second")])
        tree.selection_set("a")
        with patch.object(tree,"delete",wraps=tree.delete) as delete:
            refresh(owner,[("a","first"),("b","updated")])
            delete.assert_not_called()
        self.assertEqual(tree.selection(),("a",))
        self.assertEqual(refresh(owner,[("b","second")]),("b",))
        self.assertEqual(tree.get_children(),("b",))
        self.assertEqual(refresh(owner,[]),())
        self.assertEqual(tree.get_children(),())

    def test_listbox_keeps_unchanged_entries_and_updates_tail(self):
        box = tk.Listbox(self.root)
        owner = SimpleNamespace(box=box)
        @U.stable_listbox("box")
        def refresh(obj, values):
            obj.box.delete(0,"end")
            for value in values:
                obj.box.insert("end",value)
        refresh(owner,["a","b"])
        box.selection_set(1)
        with patch.object(box,"delete",wraps=box.delete) as delete:
            refresh(owner,["a","b"])
            delete.assert_not_called()
        self.assertEqual(box.curselection(),(1,))
        refresh(owner,["new","b","c"])
        self.assertEqual(box.get(0,"end"),("new","b","c"))
        refresh(owner,["new"])
        self.assertEqual(box.get(0,"end"),("new",))
        refresh(owner,[])
        self.assertEqual(box.size(),0)

    def test_description_same_source_preserves_cursor_and_widgets(self):
        from descriptionui import DescriptionText
        import modgen as M
        text = DescriptionText(self.root,lambda: ({},M.new_card("test"),"ko",False))
        source = "[gold]example[/gold]"
        text.set_source(source)
        text.mark_set("insert","1.2")
        with patch.object(text,"insert_source",wraps=text.insert_source) as insert:
            text.set_source(source)
            insert.assert_not_called()
        self.assertEqual(text.index("insert"),"1.2")
        self.assertEqual(text.source(),source)

    def test_async_tiles_reuse_exact_cached_images(self):
        from sts2_mod_maker import AsyncTiles
        tiles = AsyncTiles.__new__(AsyncTiles)
        tiles.c = tk.Canvas(self.root)
        tiles.gen,tiles.photos,tiles.tiles = 0,{},[]
        photo = tk.PhotoImage(master=self.root,width=10,height=10)
        identity = (("content","ko",False),100,120)
        tiles.photo_cache = {identity:photo}
        tiles.cache_keys = {}
        tiles.begin()
        tiles.add("card",0,0,100,120,(),lambda:None,cache_key=identity[0])
        self.assertEqual(tiles.tiles,[])
        self.assertIs(tiles.photos["card"],photo)
        self.assertEqual(tiles.c.type(tiles.c.find_all()[0]),"image")
        tiles.begin()
        tiles.add("card",0,0,100,120,(),lambda:None,cache_key=("content","en",False))
        self.assertEqual(len(tiles.tiles),1)

    def test_responsive_form_reflows_without_recreating_or_revealing_hidden_fields(self):
        viewport = ttk.Frame(self.root)
        form = ttk.Frame(viewport)
        first = ttk.Label(form,text="First")
        first.grid(row=0,column=0)
        value = tk.StringVar(master=self.root,value="unchanged")
        entry = ttk.Entry(form,textvariable=value)
        entry.grid(row=0,column=1)
        second = ttk.Label(form,text="Second")
        second.grid(row=0,column=2)
        other = ttk.Entry(form)
        other.grid(row=0,column=3)
        widgets = tuple(form.winfo_children())
        layout = U.ResponsiveForm(form,viewport)
        with patch.object(viewport,"winfo_width",return_value=600):
            layout._sync()
            self.assertEqual((int(other.grid_info()["row"]),int(other.grid_info()["column"])),(1,1))
            second.grid_remove()
            layout._sync()
            self.assertEqual(second.winfo_manager(),"")
            second.grid()
            layout._sync()
        with patch.object(viewport,"winfo_width",return_value=320):
            layout._sync()
            self.assertEqual((int(other.grid_info()["row"]),int(other.grid_info()["column"])),(3,0))
        with patch.object(viewport,"winfo_width",return_value=4000):
            layout._sync()
            self.assertEqual((int(other.grid_info()["row"]),int(other.grid_info()["column"])),(0,3))
        self.assertEqual(tuple(form.winfo_children()),widgets)
        self.assertEqual(value.get(),"unchanged")

    def test_block_category_colors_keep_white_labels_readable(self):
        import blockui
        import blockcode as B
        for category in B.CATS:
            color = blockui._block_color(category)
            channels = [int(color[i:i+2],16)/255 for i in (1,3,5)]
            linear = [v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in channels]
            luminance = sum(v*k for v,k in zip(linear,(.2126,.7152,.0722)))
            self.assertGreaterEqual(1.05/(luminance+.05),4.5,category)

    def test_wrapped_control_rows_do_not_share_wide_grid_columns(self):
        viewport = ttk.Frame(self.root)
        form = ttk.Frame(viewport)
        controls = ttk.Frame(form)
        controls.grid(row=0,column=1,columnspan=3)
        widgets = [ttk.Checkbutton(controls,text=text) for text in
                   ("one long keyword","two","a considerably longer keyword","four","another keyword")]
        for widget in widgets:
            widget.pack(side="left")
        layout = U.ResponsiveForm(form,viewport)
        with patch.object(viewport,"winfo_width",return_value=600):
            for _ in range(3):
                layout._sync()
                self.root.update_idletasks()
            self.assertGreater(len({widget.place_info()["y"] for widget in widgets}),1)
            self.assertLessEqual(controls.winfo_reqwidth(),400)
            self.assertTrue(all(widget.winfo_exists() and widget.master is controls for widget in widgets))

    def test_scroll_position_changes_do_not_relayout_forms(self):
        viewport = ttk.Frame(self.root)
        form = ttk.Frame(viewport)
        layout = U.ResponsiveForm(form,viewport)
        event = SimpleNamespace(widget=form,width=600,height=1200,x=0,y=0)
        layout.schedule(event)
        layout._sync()
        moved = SimpleNamespace(widget=form,width=600,height=1200,x=0,y=-100)
        layout.schedule(moved)
        self.assertIsNone(layout.job)
        layout.schedule(SimpleNamespace(widget=form,width=620,height=1200,x=0,y=-100))
        self.assertIsNotNone(layout.job)

    def test_scroll_container_keeps_geometry_without_repaint_jobs(self):
        area = U.AutoScroll(self.root)
        with patch.object(area.canvas,"winfo_width",return_value=500), patch.object(area.canvas,"winfo_height",return_value=300), patch.object(area.inner,"winfo_reqwidth",return_value=450), patch.object(area.inner,"winfo_reqheight",return_value=1200):
            area._sync()
            with patch.object(area.canvas,"itemconfigure",wraps=area.canvas.itemconfigure) as configure:
                area._sync()
                configure.assert_not_called()
        event = SimpleNamespace(widget=area.inner,width=500,height=1200,x=0,y=-20)
        area._sizes[area.inner]=(500,1200)
        with patch.object(area,"after",wraps=area.after) as schedule, patch.object(area.inner,"event_generate") as expose:
            area._later(event)
            area._later(SimpleNamespace(widget=area.inner,width=500,height=1200,x=0,y=-40))
            area._view_changed(False,"0.2","0.5")
            area._view_changed(False,"0.3","0.6")
            schedule.assert_not_called()
            expose.assert_not_called()
        self.assertIsNone(area._job)
        area.destroy()

    def test_ctrl_wheel_is_consumed_before_native_widget_wheel(self):
        text = tk.Text(self.root)
        text.pack(fill="both",expand=True)
        self.root.geometry("300x200+5000+5000")
        self.root.deiconify()
        self.root.update()
        native,zooms = [],[]
        self.root.bind_class("WheelNativeTest","<MouseWheel>",lambda e:native.append(e.delta))
        text.bindtags(tuple("WheelNativeTest" if tag=="Text" else tag for tag in text.bindtags()))
        U.install_wheel(self.root,on_zoom=zooms.append)
        with patch.object(self.root,"winfo_containing",return_value=text):
            text.event_generate("<MouseWheel>",state=4,delta=120,x=0,y=0,rootx=0,rooty=0)
            self.assertEqual(zooms,[1])
            self.assertEqual(native,[])
            text.event_generate("<MouseWheel>",delta=-120,x=0,y=0,rootx=0,rooty=0)
            self.assertEqual(native,[-120])
            text.event_generate("<MouseWheel>",state=4,delta=40,x=0,y=0,rootx=0,rooty=0)
            self.assertEqual(zooms,[1])

    def test_zoom_burst_does_not_postpone_first_frame(self):
        from unittest.mock import Mock
        from sts2_mod_maker import App
        owner = SimpleNamespace(ui_scale=1.0,_pending_scale=None,_scale_job=None,
                                after=Mock(return_value="frame"),after_cancel=Mock(),
                                status=Mock(),set_scale=Mock())
        for _ in range(3):
            App.zoom_step(owner,1)
        owner.after.assert_called_once()
        delay,callback = owner.after.call_args.args
        self.assertEqual(delay,16)
        target = owner._pending_scale
        callback()
        owner.set_scale.assert_called_once_with(target)
        owner.after_cancel.assert_not_called()

    def test_wheel_over_form_input_scrolls_parent_without_changing_value(self):
        area = U.AutoScroll(self.root)
        area.pack(fill="both",expand=True)
        combo = ttk.Combobox(area.inner,values=("A","B"))
        combo.current(0)
        combo.pack()
        spacer = ttk.Frame(area.inner,height=1500,width=100)
        spacer.pack()
        self.root.geometry("400x300+5000+5000")
        self.root.deiconify()
        self.root.update()
        area._sync()
        U.install_wheel(self.root)
        start = area.canvas.yview()[0]
        with patch.object(self.root,"winfo_containing",return_value=combo):
            combo.event_generate("<MouseWheel>",delta=-120,x=0,y=0,rootx=0,rooty=0)
        self.assertEqual(combo.get(),"A")
        self.assertGreater(area.canvas.yview()[0],start)

    def test_wheel_scroll_paints_revealed_strip_in_same_handler(self):
        area = U.AutoScroll(self.root)
        area.pack(fill="both",expand=True)
        label = ttk.Label(area.inner,text="x")
        label.pack()
        ttk.Frame(area.inner,height=1500,width=100).pack()
        self.root.geometry("400x300+5000+5000")
        self.root.deiconify()
        self.root.update()
        area._sync()
        U.install_wheel(self.root)
        with patch.object(U,"present_scroll") as present, patch.object(self.root,"winfo_containing",return_value=label):
            label.event_generate("<MouseWheel>",delta=-120,x=0,y=0,rootx=0,rooty=0)
            present.assert_called_once_with(area.canvas)
            area._drag(False,"scroll",1,"units")
            self.assertEqual(present.call_count,2)
        start = area.canvas.yview()[0]
        U.scroll_command(area.canvas)("scroll",1,"units")
        self.assertGreater(area.canvas.yview()[0],start)

    def test_present_scroll_skips_plain_canvases_and_nested_calls(self):
        canvas = tk.Canvas(self.root)
        with patch.object(canvas,"update_idletasks") as idle:
            U.present_scroll(canvas)
            idle.assert_not_called()
        ttk.Label(canvas).pack()
        with patch.object(canvas,"update_idletasks") as idle, patch.object(U,"_presenting",True):
            U.present_scroll(canvas)
            idle.assert_not_called()
        U.present_scroll(canvas)
        self.assertFalse(U._presenting)

    def test_unchanged_options_are_not_reconfigured(self):
        label = ttk.Label(self.root,text="x",wraplength=120)
        with patch.object(label,"configure",wraps=label.configure) as configure:
            U._set_if(label,wraplength=120)
            configure.assert_not_called()
            U._set_if(label,wraplength=140)
            configure.assert_called_once_with(wraplength=140)


    def test_tooltip_cancels_pending_display_when_widget_is_destroyed(self):
        label=ttk.Label(self.root,text="도움말")
        help=U.Tooltip(label,"설명",delay=10000)
        help._enter()
        pending=help.job
        self.assertIsNotNone(pending)
        label.destroy()
        self.assertIsNone(help.job)
        self.assertNotIn(pending,self.root.tk.splitlist(self.root.tk.call("after","info")))

    def test_visible_tooltip_is_closed_with_its_control(self):
        self.root.geometry("300x200+5000+5000")
        label=ttk.Label(self.root,text="설명할 말")
        label.pack()
        self.root.deiconify()
        self.root.update()
        help=U.Tooltip(label,lambda:"초보자 설명",delay=0)
        help._enter()
        self.root.update()
        self.assertIsNotNone(help.tip)
        self.assertIsNone(help.job)
        label.destroy()
        self.assertIsNone(help.tip)
        self.root.update()

    def test_tab_switch_parks_pages_instead_of_unmapping(self):
        nb = U.ScrollNotebook(self.root)
        nb.pack(fill="both",expand=True)
        pages = [nb.add_scrolled(lambda m,t=t:ttk.Entry(m), t) for t in ("a","b")]
        self.root.geometry("400x300+5000+5000")
        self.root.deiconify()
        self.root.update()
        nb.select(pages[1])
        self.root.update()
        hosts = [nb._pages[nb._o(p)]["host"] for p in pages]
        self.assertTrue(all(h.winfo_ismapped() for h in hosts))
        self.assertEqual(hosts[0].winfo_x(),nb._PARK)
        self.assertGreaterEqual(hosts[1].winfo_x(),0)
        self.assertEqual(nb.select(),str(pages[1]))
        pages[0].focus_force()
        self.root.update()
        self.assertNotEqual(nb.page_for_widget(self.root.focus_get()),nb._o(pages[0]))

    def test_focus_into_floating_tab_does_not_fire_tab_changed(self):
        # on_tab() reloads the current tab on this event; focus alone must not trigger it
        nb = U.ScrollNotebook(self.root)
        nb.pack(fill="both",expand=True)
        pages = [nb.add_scrolled(lambda m,t=t:ttk.Entry(m), t) for t in ("a","b")]
        self.root.geometry("400x300+5000+5000")
        self.root.deiconify()
        self.root.update()
        nb.detach(nb._o(pages[1]))
        self.root.update()
        nb._active_popup = None
        seen = []
        nb.bind("<<NotebookTabChanged>>", lambda _e: seen.append(1))
        nb._track_focus(SimpleNamespace(widget=pages[1]))
        nb._track_focus(SimpleNamespace(widget=nb))
        self.root.update()
        self.assertEqual(seen, [])

    def test_resize_sizes_visible_tab_now_and_hidden_tabs_later(self):
        nb = U.ScrollNotebook(self.root)
        nb.pack(fill="both",expand=True)
        pages = [nb.add_scrolled(lambda m,t=t:ttk.Entry(m), t) for t in ("a","b","c")]
        self.root.geometry("400x300+5000+5000")
        self.root.deiconify()
        self.root.update()
        self.root.geometry("500x380+5000+5000")
        self.root.update_idletasks()
        shown = nb._pages[nb._native_selected()]
        self.assertEqual(shown["placed"][2:], nb._area[2:])   # 보이는 탭은 바로 맞춘다
        end = time.perf_counter() + 2
        while nb._catch_job is not None and time.perf_counter() < end:
            self.root.update()
            time.sleep(0.01)
        for key, record in nb._pages.items():
            self.assertEqual(record["placed"][2:], nb._area[2:], key)   # 숨긴 탭도 나중에 맞춘다

"""Draggable, detachable workspace panels with docking previews."""
import tkinter as tk
from tkinter import ttk


class CheckedMenu(tk.Menu):
    """Keep check states legible even when Windows hides an inactive menu indicator."""
    def __init__(self, *args, **kw):
        super().__init__(*args, **kw)
        self._check_traces = []

    def add_checkbutton(self, cnf=None, **kw):
        options = dict(cnf or {})
        options.update(kw)
        variable = options.get("variable")
        title = options.get("label", "")
        if not isinstance(variable, tk.Variable):
            return super().add_checkbutton(**options)
        def label():
            return ("✓  " if self.tk.getboolean(variable.get()) else "□  ") + title
        options.update(label=label(), indicatoron=False)
        super().add_checkbutton(**options)
        index = self.index("end")
        def update(*_):
            try:
                self.entryconfigure(index, label=label())
            except tk.TclError:
                pass
        token = variable.trace_add("write", update)
        self._check_traces.append((variable,token))

    def destroy(self):
        for variable,token in self._check_traces:
            try:
                variable.trace_remove("write",token)
            except tk.TclError:
                pass
        self._check_traces.clear()
        super().destroy()


def pointer_in_workspace(area, x, y, drag=None):
    """Do not dock through an unrelated or floating window covering the target."""
    try:
        hit = area.winfo_containing(x,y)
        if hit is None:
            return False
        preview = drag.preview if drag is not None else None
        if preview is not None and hit.winfo_toplevel() == preview:
            return True
        if hit.winfo_toplevel() != area.winfo_toplevel():
            return False
        while hit is not None:
            if hit == area:
                return True
            hit = hit.master
    except (tk.TclError, KeyError):
        pass
    return False


class PanelHost(tk.Frame, tk.Wm):
    pass


def forget_floating_window(host):
    # Remove transient ownership before changing a floating window back
    # into an embedded frame, including rollback paths.
    try:
        host.transient("")
    except tk.TclError:
        pass
    host.update_idletasks()
    host.tk.call("wm", "forget", host)


class DockDrag:
    def __init__(self, owner, probe, finish):
        self.owner, self.probe, self.finish = owner, probe, finish
        self.drag = None
        self.ghost = self.preview = None
        self._motion_job = None
        self._pending_point = None
        self._preview_geometry = None
        self._ghost_caption = None
        self._capture_bindings = []

    def bind(self, widget, key):
        widget.bind("<ButtonPress-1>", lambda e:self.start(e, key), add="+")
        widget.bind("<B1-Motion>", self.motion, add="+")
        widget.bind("<ButtonRelease-1>", self.release, add="+")
        widget.configure(cursor="fleur")

    def start(self, event, key):
        self.cancel()
        self.drag = dict(key=key, source=event.widget, x=event.x_root, y=event.y_root, moved=False, target=None)
        # Native controls can receive the release after the pointer leaves a tab.
        # Capture only for this gesture, without replacing other global bindings.
        for sequence, callback in (("<B1-Motion>", self.motion),
                                   ("<ButtonRelease-1>", self.release),
                                   ("<Escape>", lambda _e: self.cancel())):
            token = self.owner.bind_all(sequence, callback, add="+")
            self._capture_bindings.append((sequence, token))

    def motion(self, event):
        d = self.drag
        if not d:
            return
        if not d["moved"] and abs(event.x_root-d["x"])+abs(event.y_root-d["y"]) < 8:
            return
        d["moved"] = True
        self._pending_point = (event.x_root,event.y_root)
        if self.ghost is None:
            self._paint_motion()
        elif self._motion_job is None:
            self._motion_job = self.owner.after(16,self._paint_motion)
        return "break"

    def _paint_motion(self):
        if self._motion_job is not None:
            self.owner.after_cancel(self._motion_job)
            self._motion_job = None
        if not self.drag or self._pending_point is None:
            return
        x,y = self._pending_point
        d = self.drag
        if self.ghost is None:
            self.ghost = tk.Toplevel(self.owner)
            self.ghost.withdraw()
            self.ghost.overrideredirect(True)
            self.ghost.attributes("-topmost", True)
            ttk.Label(self.ghost, padding=8).pack()
            d["source"].grab_set()
        self.ghost.geometry(f"+{max(0,x+16)}+{max(0,y+16)}")
        if not self.ghost.winfo_ismapped():
            self.ghost.deiconify()
        target = self.probe(d["key"], x, y)
        d["target"] = target[0] if target else None
        if target:
            left,top,w,h = target[1]
            geometry = f"{max(3,w)}x{max(3,h)}+{max(0,left)}+{max(0,top)}"
            if self.preview is None:
                self.preview = tk.Toplevel(self.owner)
                self.preview.withdraw()
                self.preview.overrideredirect(True)
                self.preview.attributes("-topmost", True)
                self.preview.attributes("-alpha", .30)
                self.preview.configure(background="#2469d8")
            if geometry != self._preview_geometry:
                self.preview.geometry(geometry)
                self._preview_geometry = geometry
            if not self.preview.winfo_ismapped():
                self.preview.deiconify()
            caption = target[2] if len(target)>2 else "놓으면 파란 위치에 결합"
        else:
            if self.preview is not None and self.preview.winfo_ismapped():
                self.preview.withdraw()
            caption = "놓으면 별도 패널로 분리"
        if caption != self._ghost_caption:
            self.ghost.winfo_children()[0].configure(text=caption)
            self._ghost_caption = caption

    def release(self, event):
        d = self.drag
        if not d:
            return
        moved = d["moved"] or abs(event.x_root-d["x"])+abs(event.y_root-d["y"]) >= 8
        target = self.probe(d["key"], event.x_root, event.y_root) if moved else None
        self.cancel()
        if moved:
            self.finish(d["key"], event.x_root, event.y_root, target[0] if target else None)
            return "break"

    def cancel(self):
        for sequence, token in self._capture_bindings:
            self.owner._root()._unbind(("bind", "all", sequence), token)
        self._capture_bindings.clear()
        if self._motion_job is not None:
            self.owner.after_cancel(self._motion_job)
            self._motion_job = None
        self._pending_point = None
        self._preview_geometry = None
        self._ghost_caption = None
        if self.drag:
            try:
                source = self.drag["source"]
                if source.grab_current() == source:
                    source.grab_release()
            except (tk.TclError,KeyError):
                pass
        self.drag = None
        for name in ("ghost", "preview"):
            window = getattr(self, name)
            if window is not None:
                window.destroy()
                setattr(self, name, None)


def position_window(host, x, y):
    host.geometry(f"+{max(0,x-45)}+{max(0,y-15)}")
    host.lift()


def prepare_float_window(host, owner, size, saved=None, position=None):
    """Set final geometry before showing; no intermediate centering or event flush."""
    width,height = size
    if saved:
        import re
        match = re.match(r"(\d+)x(\d+)",saved)
        if match:
            width,height = map(int,match.groups())
    width = min(width,max(280,host.winfo_screenwidth()-80))
    height = min(height,max(220,host.winfo_screenheight()-100))
    if position is not None:
        x,y = position[0]-45,position[1]-15
    elif saved:
        host.geometry(saved)
        return
    else:
        x = owner.winfo_rootx() + (owner.winfo_width()-width)//2
        y = owner.winfo_rooty() + (owner.winfo_height()-height)//2
    host.geometry(f"{width}x{height}+{max(0,x)}+{max(0,y)}")


class DockPanedWindow(ttk.PanedWindow):
    def __init__(self, parent, title="패널", **kw):
        super().__init__(parent, **kw)
        self.title = title
        self._records, self._hosts, self._order = {}, {}, []
        self._default_order = []
        self.window_owner = self.winfo_toplevel()
        self.workspace = not isinstance(self.window_owner,tk.Toplevel)
        root = self._root()
        if not hasattr(root, "_dock_groups"):
            root._dock_groups = []
        root._dock_groups.append(self)
        self.drag = DockDrag(self, self._probe, self._finish)
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _on_destroy(self, event):
        if event.widget == self:
            self.drag.cancel()
            groups = getattr(self._root(), "_dock_groups", [])
            if self in groups:
                groups.remove(self)

    def add_panel(self, factory, title, default_visible=True, **options):
        host = PanelHost(self, background="#f3f4f7")
        header = ttk.Frame(host, padding=(9,3), style="PanelHeader.TFrame")
        header.pack(fill="x")
        label = ttk.Label(header, text="⠿ " + title, anchor="w", style="PanelHeader.TLabel")
        label.pack(side="left", fill="x", expand=True)
        body = ttk.Frame(host)
        body.pack(fill="both", expand=True)
        widget = factory(body)
        widget.pack(fill="both", expand=True)
        key = str(widget)
        action = ttk.Button(header, text="↗", style="Panel.Tool.TButton", width=2, command=lambda:self.dock(key) if self._records[key]["detached"] else self.detach(key))
        action.pack(side="right")
        ttk.Button(header, text="×", style="Panel.Tool.TButton", width=2, command=lambda:self.close_panel(key)).pack(side="right", padx=2)
        self._records[key] = dict(host=host, content=widget, title=title, options=options,
                                  visible=tk.BooleanVar(self,True), floating=tk.BooleanVar(self,False), detached=False, action=action, geometry=None, default_visible=default_visible, close_handler=None)
        self._hosts[str(host)] = key
        self._order.append(key)
        self._default_order.append(key)
        self.drag.bind(label,key)
        self.drag.bind(header,key)
        super().add(host, **options)
        return widget

    def _key(self, widget):
        return self._hosts.get(str(widget), str(widget))

    def panes(self):
        return tuple(key for key in self._order if self._records[key]["visible"].get())

    def add(self, widget, **options):
        key = self._key(widget)
        record = self._records[key]
        before = options.pop("before",None)
        anchor = self._key(before) if before is not None else None
        if anchor is not None and anchor != "end" and anchor not in self._order:
            raise ValueError("결합할 패널 위치를 찾지 못했습니다.")
        old_order,old_options = self._order[:],dict(record["options"])
        record["options"].update(options)
        try:
            if record["detached"]:
                if anchor is not None and anchor != key:
                    self._order.remove(key)
                    self._order.insert(self._order.index(anchor) if anchor != "end" else len(self._order),key)
                self.set_visible(key,True)
            else:
                self.dock(key,before=anchor)
        except Exception:
            self._order[:] = old_order
            record["options"] = old_options
            raise

    def forget(self, widget):
        self.set_visible(widget, False)

    def set_visible(self, widget, show):
        key = self._key(widget)
        record = self._records[key]
        host = record["host"]
        native = tuple(map(str,super().panes()))
        previous = host.state() != "withdrawn" if record["detached"] else str(host) in native
        try:
            if record["detached"]:
                if show:
                    host.deiconify()
                    host.lift()
                else:
                    host.withdraw()
            elif show:
                if str(host) not in native:
                    self._insert(key)
            elif str(host) in native:
                super().forget(host)
            record["visible"].set(bool(show))
        except Exception:
            record["visible"].set(previous)
            raise

    def _insert(self, key):
        record = self._records[key]
        native = [str(host) for host in super().panes() if str(host) != str(record["host"])]
        after = self._order[self._order.index(key)+1:]
        anchor = next((str(self._records[k]["host"]) for k in after if str(self._records[k]["host"]) in native), None)
        index = native.index(anchor) if anchor is not None else "end"
        super().insert(index, record["host"], **record["options"])

    def floating_window(self, widget):
        record = self._records.get(self._key(widget))
        if record and record["detached"] and record["visible"].get():
            return record["host"]
        return None

    def _configure_floating(self, key, size, position=None):
        record = self._records[key]
        host = record["host"]
        host.title(self.title + " · " + record["title"])
        if not self.workspace and self.window_owner.winfo_exists():
            host.transient(self.window_owner)
        if record["close_handler"] is None:
            record["close_handler"] = host.register(lambda:self.close_panel(key))
        host.protocol("WM_DELETE_WINDOW",record["close_handler"])
        host.minsize(280,220)
        prepare_float_window(host,self.window_owner if self.window_owner.winfo_exists() else self._root(),size,record["geometry"],position)

    def detach(self, widget, position=None):
        key = self._key(widget)
        record = self._records[key]
        host = record["host"]
        if record["detached"]:
            if position is not None:
                position_window(host,*position)
            self.set_visible(key,True)
            return
        native = tuple(map(str,super().panes()))
        was_visible = str(host) in native
        size = max(360,host.winfo_width()),max(300,host.winfo_height())
        if was_visible:
            super().forget(host)
        try:
            host.update_idletasks()
            self.tk.call("wm","manage",host)
            host.withdraw()
            record["detached"] = True
            self._configure_floating(key,size,position)
            self.set_visible(key,True)
            record["floating"].set(True)
            record["action"].configure(text="↙")
        except Exception:
            try:
                forget_floating_window(host)
            except tk.TclError:
                pass
            record["detached"] = False
            record["floating"].set(False)
            record["visible"].set(was_visible)
            record["action"].configure(text="↗")
            if was_visible:
                self._insert(key)
            raise

    def dock(self, widget, before=None):
        key = self._key(widget)
        record = self._records[key]
        if before is not None and before != "end" and before not in self._order:
            raise ValueError("결합할 패널 위치를 찾지 못했습니다.")
        old_order = self._order[:]
        was_detached = record["detached"]
        host = record["host"]
        was_visible = host.state() != "withdrawn" if was_detached else str(host) in tuple(map(str,super().panes()))
        try:
            if was_detached:
                record["geometry"] = host.geometry()
                host.withdraw()
                forget_floating_window(host)
                record["detached"] = False
            if before is not None and before != key:
                self._order.remove(key)
                self._order.insert(self._order.index(before) if before != "end" else len(self._order),key)
            self._insert(key)
            record["visible"].set(True)
            record["floating"].set(False)
            record["action"].configure(text="↗")
        except Exception:
            self._order[:] = old_order
            if was_detached:
                if str(host) in tuple(map(str,super().panes())):
                    super().forget(host)
                self.tk.call("wm","manage",host)
                host.withdraw()
                record["detached"] = True
                self._configure_floating(key,(360,300))
                record["floating"].set(True)
                record["action"].configure(text="↙")
                if was_visible:
                    host.deiconify()
            elif was_visible:
                # Bypass a failed helper when restoring a previously docked pane.
                native = [str(pane) for pane in super().panes() if str(pane) != str(host)]
                after = old_order[old_order.index(key)+1:]
                anchor = next((str(self._records[k]["host"]) for k in after if str(self._records[k]["host"]) in native),None)
                super().insert(native.index(anchor) if anchor is not None else "end",host,**record["options"])
            elif str(host) in tuple(map(str,super().panes())):
                super().forget(host)
            record["visible"].set(was_visible)
            raise

    def close_panel(self, widget):
        key = self._key(widget)
        if self._records[key]["detached"]:
            self.dock(key)
        else:
            self.set_visible(key,False)

    def show_all(self):
        for key in self._order:
            self.set_visible(key,True)

    def dock_all(self):
        for key in list(self._order):
            self.dock(key)

    def reset_layout(self):
        self._order[:] = self._default_order
        for key in self._order:
            self.dock(key)
        # Sorting relative to a still-shuffled sibling does not restore every permutation.
        # Once all panes are present, place each at its final numeric index.
        for index,key in enumerate(self._order):
            record = self._records[key]
            super().insert(index,record["host"],**record["options"])
        for key in self._order:
            if not self._records[key]["default_visible"]:
                self.set_visible(key,False)

    def _probe(self, key, x, y):
        if not self.winfo_ismapped():
            return None
        left,top = self.winfo_rootx(),self.winfo_rooty()
        width,height = self.winfo_width(),self.winfo_height()
        if not (left <= x < left+width and top <= y < top+height):
            return None
        if not pointer_in_workspace(self,x,y,self.drag):
            return None
        horizontal = str(self.cget("orient")) == "horizontal"
        native = [self._hosts[str(host)] for host in super().panes() if self._hosts[str(host)] != key]
        for i, other in enumerate(native):
            host = self._records[other]["host"]
            start = host.winfo_rootx() if horizontal else host.winfo_rooty()
            size = host.winfo_width() if horizontal else host.winfo_height()
            pointer = x if horizontal else y
            if pointer < start+size:
                first = pointer < start+size/2
                anchor = other if first else (native[i+1] if i+1<len(native) else "end")
                rect = (start if first else start+size//2,top,max(40,size//2),height) if horizontal else (left,start if first else start+size//2,width,max(40,size//2))
                return anchor, rect
        return "end", (left,top,max(40,width//2),height) if horizontal else (left,top,width,max(40,height//2))

    def _finish(self, key, x, y, target):
        if target is not None:
            self.dock(key,before=target)
        else:
            self.detach(key,position=(x,y))


def panel_groups(root):
    return [group for group in getattr(root,"_dock_groups",[]) if group.winfo_exists()]


def is_panel_window(root, window):
    return any(str(record["host"]) == str(window) and record["detached"]
               for group in panel_groups(root) if group.workspace for record in group._records.values())


def install_panel_menu(menu, root, scope=None):
    panels = tk.Menu(menu, tearoff=False)
    cached_signature = None
    def groups():
        return [g for g in panel_groups(root) if scope is None or str(g).startswith(str(scope) + ".")]
    def activate_all():
        for group in groups():
            group.show_all()
        notebook = getattr(root,"nb",None)
        if scope is None and notebook and hasattr(notebook,"show_all"):
            notebook.show_all()
    def rebuild():
        nonlocal cached_signature
        current = groups()
        signature = tuple((str(group),tuple(group._order)) for group in current)
        if signature == cached_signature:
            return
        panels.delete(0,"end")
        for child in panels.winfo_children():
            child.destroy()
        panels.add_command(label="모두 활성화",command=activate_all)
        panels.add_separator()
        for group in current:
            choices = CheckedMenu(panels,tearoff=False)
            choices.add_command(label="이 그룹 모두 활성화",command=group.show_all)
            choices.add_separator()
            floating = CheckedMenu(choices,tearoff=False)
            for key in group._order:
                record = group._records[key]
                choices.add_checkbutton(label=record["title"],variable=record["visible"],
                    command=lambda group=group,key=key:group.set_visible(key,group._records[key]["visible"].get()))
                floating.add_checkbutton(label=record["title"],variable=record["floating"],
                    command=lambda group=group,key=key:group.detach(key) if group._records[key]["floating"].get() else group.dock(key))
            choices.add_separator()
            choices.add_cascade(label="패널 분리 (체크 = 분리됨)",menu=floating)
            panels.add_cascade(label=group.title,menu=choices)
        cached_signature = signature
    panels.configure(postcommand=rebuild)
    menu.add_cascade(label="패널 표시 (체크 = 표시됨)",menu=panels)
    menu.add_command(label="모두 활성화",command=activate_all)
    def reset():
        for group in groups():
            group.reset_layout()
        notebook = getattr(root,"nb",None)
        if scope is None and notebook and hasattr(notebook,"dock_all"):
            if hasattr(notebook,"reset_layout"):
                notebook.reset_layout()
            else:
                notebook.dock_all()
                notebook.show_all()
    menu.add_command(label="기본 작업 공간으로 되돌리기", command=reset)

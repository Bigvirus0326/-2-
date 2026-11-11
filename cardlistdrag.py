"""Card-list selection, ordered multi-item drops and an explicit delete target."""
import tkinter as tk
from uxkit import C


class CardListDrag:
    def __init__(self, tab):
        self.tab = tab
        self.tree = tab.tree
        self.marker = tk.Frame(self.tree, background="#2563eb", height=3)
        self.selection_edges = [tk.Frame(self.tree,background="#2563eb") for _ in range(4)]
        self.state = None
        self.scroll_job = None
        self.last_event = None
        self.release_host = None
        self.release_bind = None
        self.deactivate_bind = None
        # A Tk grab still delivers events to children of the grabbed widget.
        # The selection outline and insertion marker must forward those events.
        for overlay in [self.marker,*self.selection_edges]:
            overlay.bind("<B1-Motion>",self.move)
            overlay.bind("<ButtonRelease-1>",self.end)
        self.tree.bind("<Escape>", self.cancel, add="+")
        self.tree.bind("<Motion>",self._recover_release,add="+")
        self.tree.bind("<Destroy>", self.destroy, add="+")
        self.tree.bind("<Unmap>", self.cancel, add="+")

    def inside(self, widget, event):
        return (widget.winfo_ismapped() and widget.winfo_rootx() <= event.x_root < widget.winfo_rootx()+widget.winfo_width()
                and widget.winfo_rooty() <= event.y_root < widget.winfo_rooty()+widget.winfo_height())

    def start(self, event):
        self.clear()
        x,y = event.x_root-self.tree.winfo_rootx(),event.y_root-self.tree.winfo_rooty()
        if self.tree.identify_region(x,y) in ("heading","separator"):
            return
        if event.state & 0x0005:  # Preserve native Ctrl/Shift click selection.
            return
        row = self.tree.identify_row(y) if 0 <= x < self.tree.winfo_width() else ""
        mode = "move" if row else "select"
        before = self.tree.selection()
        if mode == "select" or row not in before:
            self.tree.selection_set((row,) if row else ())
        if row:
            self.tree.focus(row)
        self.tree.focus_set()
        self.state = {"row":row,"mode":mode,"x":event.x_root,"y":event.y_root,"moved":False,
                      "before":before,"rows":self.tree.selection(),"order":[x['id'] for x in self.tab.items],
                      "anchor_y":self.content_y(y),"anchor_x":x,"drop":None}
        self.tab._drag = self.state
        self.tree.grab_set()
        self.release_host = self.tree.winfo_toplevel()
        self.release_bind = self.release_host.bind("<ButtonRelease-1>",self.end,add="+")
        self.deactivate_bind = self.release_host.bind("<Deactivate>",self._lost_activation,add="+")
        return "break"

    def _recover_release(self, event):
        if self.state is not None and not (event.state & 0x0100):
            self._lost_activation()

    def _lost_activation(self, event=None):
        if self.state is not None:
            self.clear()
            self.tab.on_select()

    def content_y(self, y):
        for index,row in enumerate(self.tree.get_children()):
            box = self.tree.bbox(row)
            if box:
                return y-box[1]+index*box[3]
        return y

    def selection_box(self, x, y):
        d = self.state
        origin_y = d['anchor_y']-self.content_y(0)
        left,right = sorted((max(0,min(self.tree.winfo_width()-2,d['anchor_x'])),max(0,min(self.tree.winfo_width()-2,x))))
        top,bottom = sorted((max(20,min(self.tree.winfo_height()-2,origin_y)),max(20,min(self.tree.winfo_height()-2,y))))
        for edge,(ex,ey,ew,eh) in zip(self.selection_edges,[(left,top,max(2,right-left),2),(left,bottom,max(2,right-left),2),
                                                          (left,top,2,max(2,bottom-top)),(right,top,2,max(2,bottom-top))]):
            edge.place(x=ex,y=ey,width=ew,height=eh)
            edge.lift()

    def move(self, event):
        d = self.state
        if not d:
            return
        if not d['moved'] and abs(event.x_root-d['x'])+abs(event.y_root-d['y']) < 6:
            return "break"
        d['moved'] = True
        self.last_event = event
        y = event.y_root-self.tree.winfo_rooty()
        x = event.x_root-self.tree.winfo_rootx()
        kids = self.tree.get_children()
        if d['mode'] == 'select':
            self.tree.configure(cursor='crosshair')
            self.selection_box(x,y)
            if kids:
                lo,hi = sorted((d['anchor_y'],self.content_y(y)))
                height = next((self.tree.bbox(key)[3] for key in kids if self.tree.bbox(key)),1)
                rows = [key for i,key in enumerate(kids) if i*height < hi and (i+1)*height > lo]
                self.tree.selection_set(rows)
                self.tab._update_multi()
                self.tab.card_drag_status.configure(text=f"{len(rows)}장 선택 · 선택한 카드를 끌면 함께 이동/삭제")
            self._scroll(y)
            return "break"
        self.marker.place_forget()
        for edge in self.selection_edges:
            edge.place_forget()
        d['drop'] = None
        self.tab.card_delete_zone.configure(background='#fff1f0',foreground='#b42318')
        if self.inside(self.tab.card_delete_zone,event):
            d['drop'] = ('delete',None)
            self.tab.card_delete_zone.configure(background='#b42318',foreground='white')
            self.tab.card_drag_status.configure(text=f"{len(d['rows'])}장 삭제 · 놓으면 확인창이 열립니다")
            self.tree.configure(cursor='X_cursor')
        elif self.inside(self.tree,event) and y >= 20 and kids and self.tree.identify_region(x,y) not in ('heading','separator'):
            row = self.tree.identify_row(y)
            after = False
            if row:
                bx,by,bw,bh = self.tree.bbox(row)
                after = y >= by+bh/2
                line_y = by+bh if after else by
            else:
                visible = [key for key in kids if self.tree.bbox(key)]
                row = visible[-1] if visible else kids[-1]
                after = True
                box = self.tree.bbox(row)
                line_y = box[1]+box[3] if box else self.tree.winfo_height()-3
            d['drop'] = ('move',(int(row),after))
            self.marker.place(x=0,y=line_y-1,relwidth=1,height=3)
            self.marker.lift()
            self.tree.configure(cursor='sb_v_double_arrow')
            self.tab.card_drag_status.configure(text=f"{len(d['rows'])}장 이동 · 파란 선 위치에 놓기 · Esc 취소")
            self._scroll(y)
        else:
            self.tree.configure(cursor='X_cursor')
            self.tab.card_drag_status.configure(text="목록의 파란 선 또는 아래 삭제 영역에 놓으세요 · Esc 취소")
        return "break"

    def _scroll(self, y):
        direction = -1 if y < 35 else 1 if y > self.tree.winfo_height()-22 else 0
        if self.scroll_job is not None:
            self.tree.after_cancel(self.scroll_job)
            self.scroll_job = None
        if not direction:
            return
        before = self.tree.yview()
        self.tree.yview_scroll(direction,'units')
        if before != self.tree.yview():
            self.scroll_job = self.tree.after(70,self._continue_scroll)

    def _continue_scroll(self):
        self.scroll_job = None
        if self.state is not None and self.last_event is not None:
            self.move(self.last_event)

    def end(self, event):
        d = self.state
        if not d:
            return
        try:
            if d['moved']:
                self.move(event)  # Validate the actual release location.
        finally:
            self.clear()
        if d['mode'] == 'select':
            self.tab.on_select()
            return "break"
        if not d['moved']:
            self.tree.selection_set(d['row'])
            self.tab.on_select()
            return "break"
        if not d['moved'] or not d['drop'] or d['order'] != [x['id'] for x in self.tab.items]:
            return "break"
        chosen = sorted(int(row) for row in d['rows'])
        self.tree.selection_set(d['rows'])
        if d['drop'][0] == 'delete':
            self.tab.delete()
            return "break"
        target,after = d['drop'][1]
        old = list(self.tab.items)
        remaining = [i for i in range(len(old)) if i not in chosen]
        boundary = target+int(after)
        position = sum(i < boundary for i in remaining)
        order = remaining[:position]+chosen+remaining[position:]
        if order != list(range(len(old))):
            self.tab.items[:] = [old[i] for i in order]
            self.tab.app.mark_dirty()
            self.tab.refresh_list([order.index(i) for i in chosen])
            self.tab.app.on_items_changed()
        return "break"

    def cancel(self, event=None):
        d = self.state
        if not d:
            return
        self.clear()
        if d['order'] == [x['id'] for x in self.tab.items]:
            self.tree.selection_set([row for row in d['before'] if self.tree.exists(row)])
            self.tab.on_select()
        return "break"

    def clear(self):
        self._unbind_release()
        if self.scroll_job is not None:
            self.tree.after_cancel(self.scroll_job)
            self.scroll_job = None
        self.last_event = None
        self.state = None
        self.tab._drag = None
        self.marker.place_forget()
        for edge in self.selection_edges:
            edge.place_forget()
        self.tree.configure(cursor='')
        self.tab.card_delete_zone.configure(background=C['bg'],foreground=C['muted'])
        self.tab.card_drag_status.configure(text="카드 드래그: 이동/삭제 · 빈 여백 드래그: 여러 장 선택 · Esc 취소")
        if self.tree.grab_current() == self.tree:
            self.tree.grab_release()

    def _unbind_release(self):
        if self.release_host is not None:
            for sequence,ident in (("<ButtonRelease-1>",self.release_bind),("<Deactivate>",self.deactivate_bind)):
                if ident:
                    try:
                        self.release_host.unbind(sequence,ident)
                    except tk.TclError:
                        pass
        self.release_host = self.release_bind = self.deactivate_bind = None

    def destroy(self, event):
        if event.widget is self.tree:
            self._unbind_release()
            if self.scroll_job is not None:
                self.tree.after_cancel(self.scroll_job)
                self.scroll_job = None
            self.state = None
            self.tab._drag = None

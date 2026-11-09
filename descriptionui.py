"""Readable description editing with linked values and serializable text formatting."""
import re
import tkinter as tk
from tkinter import colorchooser, messagebox, ttk
import tkinter.font as tkfont

import modgen as M
import preview as PV


class DescriptionText(tk.Text):
    _clipboard_plain = None
    _clipboard_source = None
    def __init__(self, parent, context, **kw):
        kw["undo"] = False
        super().__init__(parent, **kw)
        self.context = context
        self.formats = {}
        self.chips = {}
        self._serial = 0
        self._busy = False
        self._history = [""]
        self._history_pos = 0
        self._fonts = []
        self.bind("<<Modified>>", self._modified, add="+")
        self.bind("<Control-z>", lambda e:self._undo(-1))
        self.bind("<Control-y>", lambda e:self._undo(1))
        self.bind("<Control-Z>", lambda e:self._undo(1)) 
        self.bind("<<Copy>>", self._copy)
        self.bind("<<Cut>>", lambda e:self._copy(e, cut=True))
        self.bind("<<Paste>>", self._paste)


    def _copy(self, event=None, cut=False):
        try:
            start, end = self.index("sel.first"), self.index("sel.last")
        except tk.TclError:
            return "break"
        source = self.source(start, end)
        project, item, lang, upgraded = self.context()
        rendered = M.resolve_description_references(M.resolve_block_description(source, item), project, lang)
        rendered = PV.fill_values(project, rendered, item, upgraded)
        plain = "".join(text for text, _ in PV.parse_bbcode(rendered))
        DescriptionText._clipboard_plain = plain
        DescriptionText._clipboard_source = source
        self.clipboard_clear()
        self.clipboard_append(plain)
        if cut:
            self.delete(start, end)
            self._remember()
            self.event_generate("<KeyRelease>")
        return "break"

    def _paste(self, event=None):
        try:
            plain = self.clipboard_get()
        except tk.TclError:
            return "break"
        source = DescriptionText._clipboard_source if plain == DescriptionText._clipboard_plain else plain
        try:
            self.delete("sel.first", "sel.last")
        except tk.TclError:
            pass
        self.insert_source("insert", source)
        self.event_generate("<KeyRelease>")
        return "break"

    def _style(self, opening, closing, **options):
        key = "format_" + str(len(self.formats))
        for name, (old_open, old_close) in self.formats.items():
            if (opening, closing) == (old_open, old_close):
                return name
        self.formats[key] = (opening, closing)
        self.tag_configure(key, **options)
        return key

    def _format(self, tag):
        raw = tag.lower()
        if raw.startswith("color="):
            color = tag.split("=", 1)[1].strip().strip('"\'')
            if re.fullmatch(r"#[a-fA-F0-9]{6}", color):
                return self._style("[color=" + color + "]", "[/color]", foreground=color)
        if raw in PV.TEXT_COLORS:
            return self._style("[" + raw + "]", "[/" + raw + "]", foreground=PV.TEXT_COLORS[raw])
        if raw in ("b", "i"):
            font = tkfont.Font(font=self.cget("font"))
            font.configure(**({"weight":"bold"} if raw == "b" else {"slant":"italic"}))
            self._fonts.append(font)
            return self._style("[" + raw + "]", "[/" + raw + "]", font=font)
        if raw == "energy":
            return self._style("[energy]", "[/energy]", foreground="#9a6500")
        return None

    def _label(self, token):
        project, item, lang, upgraded = self.context()
        rendered = M.resolve_description_references(M.resolve_block_description(token, item), project, lang)
        rendered = PV.fill_values(project, rendered, item, upgraded)
        plain = "".join(text for text, _ in PV.parse_bbcode(rendered)).strip()
        return plain if plain and plain != "?" else "연결 수치"

    def _chip(self, index, token, tags):
        self._serial += 1
        name = "chip_" + str(self._serial)
        label = tk.Label(self, text=self._label(token), background="#e8f1ff", foreground="#185197",
                         padx=4, pady=1, font=self.cget("font"), cursor="hand2")
        self.chips[str(label)] = (label, token)
        self.window_create(index, window=label, padx=1, stretch=False)
        self.tag_add(name, index, index + "+1c")
        for tag in tags:
            self.tag_add(tag, index, index + "+1c")
        def select(_):
            ranges = self.tag_ranges(name)
            if ranges:
                self.focus_set()
                self.tag_remove("sel", "1.0", "end")
                self.tag_add("sel", *ranges)
                self.mark_set("insert", ranges[-1])
            return "break"
        label.bind("<Button-1>", select)

    def insert_source(self, index, source):
        self.mark_set("rich_insert", index)
        self.mark_gravity("rich_insert", "right")
        active = []
        pos = 0
        while pos < len(source):
            if source[pos] == "[":
                match = re.match(r"\[(/?)([a-z_]+)(=#[a-fA-F0-9]{6})?\]", source[pos:])
                if match:
                    closing, tag, arg = match.groups()
                    if closing:
                        hit = next((i for i in range(len(active)-1,-1,-1) if active[i][0] == tag), None)
                        if hit is not None:
                            active.pop(hit)
                            pos += len(match[0])
                            continue
                    else:
                        style = self._format(tag + (arg or ""))
                        if style:
                            active.append((tag, style))
                            pos += len(match[0])
                            continue
            tags = tuple(style for _, style in active)
            if source[pos] == "{":
                depth, end = 1, pos + 1
                while end < len(source) and depth:
                    depth += (source[end] == "{") - (source[end] == "}")
                    end += 1
                if depth == 0:
                    where = self.index("rich_insert")
                    self._chip(where, source[pos:end], tags)
                    pos = end
                    continue
            super().insert("rich_insert", source[pos], tags)
            pos += 1
        self.mark_set("insert", "rich_insert")
        self.refresh_labels()
        self._remember()

    def source(self, start="1.0", end="end-1c"):
        segments = []
        for kind, value, index in self.dump(start, end, text=True, window=True):
            if kind == "window":
                pair = self.chips.get(value)
                value = pair[1] if pair else ""
            tags = tuple(name for name in self.tag_names(index) if name in self.formats)
            if segments and segments[-1][0] == tags:
                segments[-1] = (tags, segments[-1][1] + value)
            else:
                segments.append((tags, value))
        out = ["".join(self.formats[name][0] for name in tags) + value +
               "".join(self.formats[name][1] for name in reversed(tags))
               for tags, value in segments]
        return "".join(out)

    def set_source(self, source, history=True):
        source = source or ""
        if self.source() == source:
            self.refresh_labels()
            if history:
                self._history = [source]
                self._history_pos = 0
            return
        self._busy = True
        try:
            super().delete("1.0", "end")
            for label, _ in self.chips.values():
                label.destroy()
            self.chips.clear()
            self.insert_source("1.0", source or "")
            self.edit_modified(False)
        finally:
            self._busy = False
        if history:
            self._history = [self.source()]
            self._history_pos = 0

    def _remove_color_tags(self, start, end):
        openings = {"[" + name + "]" for name in PV.TEXT_COLORS}
        for tag, (opening, _) in self.formats.items():
            if opening in openings or opening.startswith("[color="):
                self.tag_remove(tag, start, end)

    def apply_color(self, start, end, color):
        self._remove_color_tags(start, end)
        tag = self._style("[color=" + color + "]", "[/color]", foreground=color)
        self.tag_add(tag, start, end)
        self.refresh_labels()
        self._remember()

    def apply_game_color(self, start, end, name):
        if name not in PV.TEXT_COLORS:
            raise ValueError("지원하지 않는 게임 색상입니다.")
        self._remove_color_tags(start, end)
        self.tag_add(self._format(name), start, end)
        self.refresh_labels()
        self._remember()

    def reset_color(self, start, end):
        self._remove_color_tags(start, end)
        self.refresh_labels()
        self._remember()

    def refresh_labels(self):
        for kind, value, index in self.dump("1.0", "end-1c", window=True):
            if kind != "window" or value not in self.chips:
                continue
            label, token = self.chips[value]
            color = "#185197"
            for tag in self.tag_names(index):
                if tag in self.formats and self.tag_cget(tag, "foreground"):
                    color = self.tag_cget(tag, "foreground")
            label.configure(text=self._label(token), foreground=color)

    def _remember(self):
        if self._busy:
            return
        source = self.source()
        if source != self._history[self._history_pos]:
            self._history = self._history[:self._history_pos+1] + [source]
            self._history = self._history[-100:]
            self._history_pos = len(self._history)-1

    def _modified(self, _=None):
        if self.edit_modified():
            self._remember()
            self.edit_modified(False)

    def _undo(self, direction):
        self._remember()
        target = self._history_pos + direction
        if 0 <= target < len(self._history):
            self._history_pos = target
            self.set_source(self._history[target], history=False)
            self.event_generate("<KeyRelease>")
        return "break"


GAME_COLOR_LABELS = [("gold", "금색"), ("blue", "파랑"), ("green", "초록"), ("red", "빨강"),
                     ("orange", "주황"), ("purple", "보라"), ("aqua", "청록"), ("pink", "분홍")]


class GameColorBar(ttk.Frame):
    """One-click native game colors, with a separate custom color picker."""
    def __init__(self, parent, field, on_change):
        super().__init__(parent)
        self.field, self.on_change = field, on_change
        from uxkit import Tooltip
        ttk.Label(self, text="게임 기본 색").grid(row=0, column=0, columnspan=4, sticky="w", padx=(0, 5))
        self.presets = {}
        for col, (name, label) in enumerate(GAME_COLOR_LABELS, 1):
            button = tk.Button(self, text=label, width=3, background=PV.TEXT_COLORS[name],
                               foreground="#17212e", activeforeground="#17212e", activebackground=PV.TEXT_COLORS[name],
                               relief="flat", borderwidth=1, cursor="hand2", takefocus=False,
                               command=lambda name=name:self.apply(name))
            button.grid(row=1+(col-1)//4, column=(col-1)%4, padx=2, pady=2,sticky="we")
            Tooltip(button, "선택한 글자를 게임의 " + label + "으로 표시합니다.")
            self.presets[name] = button
        actions = ttk.Frame(self)
        actions.grid(row=1+(len(GAME_COLOR_LABELS)+3)//4, column=0, columnspan=4, sticky="w", pady=(2, 0))
        ttk.Button(actions, text="기본색으로", command=lambda:self.apply(None)).pack(side="left")
        ttk.Button(actions, text="다른 색 직접 선택…", command=self.custom).pack(side="left", padx=4)

    def selection(self):
        try:
            return self.field.index("sel.first"), self.field.index("sel.last")
        except tk.TclError:
            messagebox.showinfo("글자 색", "색을 바꿀 글자를 먼저 드래그해서 선택하세요.", parent=self.winfo_toplevel())
            return None

    def apply(self, name):
        selected = self.selection()
        if selected is None:
            return
        if name is None:
            self.field.reset_color(*selected)
        else:
            self.field.apply_game_color(*selected, name)
        self.on_change()
        self.field.focus_set()

    def custom(self):
        selected = self.selection()
        if selected is None:
            return
        color = colorchooser.askcolor(parent=self.winfo_toplevel(), title="설명 글자 색 선택")[1]
        if color:
            self.field.apply_color(*selected, color)
            self.on_change()
            self.field.focus_set()

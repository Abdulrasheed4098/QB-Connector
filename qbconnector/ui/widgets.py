"""Reusable tkinter pieces: searchable combo, form grid, line grid, scroll frame."""
import tkinter as tk
from decimal import Decimal
from tkinter import ttk

from ..util import InputError, parse_amount, parse_qty, money, today_str

NAV_KEYS = {"Up", "Down", "Left", "Right", "Return", "Tab", "Escape", "Home", "End",
            "Shift_L", "Shift_R", "Control_L", "Control_R", "Alt_L", "Alt_R", "ISO_Left_Tab"}


class AutoCombo(ttk.Combobox):
    """Combobox you can type into; the drop-down list narrows to matching names.
    Press the Down arrow (or click the arrow) to open the list."""

    def __init__(self, master, source=None, **kw):
        kw.setdefault("height", 20)
        super().__init__(master, **kw)
        self._all = []
        self.source = source
        self.bind("<KeyRelease>", self._filter)
        self.bind("<FocusIn>", lambda e: self._refresh_if_empty())
        self.refresh()

    def refresh(self):
        if self.source is not None:
            self.set_values(self.source())

    def _refresh_if_empty(self):
        if not self._all and self.source is not None:
            self.refresh()

    def set_values(self, values):
        self._all = list(values or [])
        self["values"] = self._all

    def _filter(self, event):
        if event.keysym in NAV_KEYS:
            return
        s = self.get().strip().lower()
        if not s:
            self["values"] = self._all
            return
        starts = [v for v in self._all if v.lower().startswith(s)]
        contains = [v for v in self._all if s in v.lower() and not v.lower().startswith(s)]
        self["values"] = starts + contains


class ScrollFrame(ttk.Frame):
    """A frame with a vertical scrollbar; put children in .inner"""

    def __init__(self, master, height=240, **kw):
        super().__init__(master, **kw)
        self.canvas = tk.Canvas(self, highlightthickness=0, height=height, bg="white")
        self.vsb = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg="white")
        self.inner.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self._win = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(self._win, width=e.width))
        self.canvas.configure(yscrollcommand=self.vsb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.vsb.pack(side="right", fill="y")
        for w in (self.canvas, self.inner):
            w.bind("<Enter>", lambda e: self._wheel(True))
            w.bind("<Leave>", lambda e: self._wheel(False))

    def _wheel(self, on):
        if on:
            self.canvas.bind_all("<MouseWheel>", self._on_wheel)
        else:
            self.canvas.unbind_all("<MouseWheel>")

    def _on_wheel(self, e):
        self.canvas.yview_scroll(int(-e.delta / 120) or (-1 if e.delta > 0 else 1), "units")

    def to_bottom(self):
        self.update_idletasks()
        self.canvas.yview_moveto(1.0)


class Form(ttk.Frame):
    """Label + widget pairs laid out in columns.
    add(key, label, kind, ...) kinds: text, combo, choice, date, check, amount, memo"""

    def __init__(self, master, columns=2, **kw):
        super().__init__(master, **kw)
        self.columns = columns
        self.fields = {}
        self.labels = {}
        self.kinds = {}
        self.defaults = {}
        self._n = 0

    def add(self, key, label, kind="text", source=None, values=None, width=34, default=None,
            span=1, required=False):
        r, c = divmod(self._n, self.columns)
        lab = ttk.Label(self, text=label + (" *" if required else ""))
        lab.grid(row=r, column=c * 2, sticky="w", padx=(0 if c == 0 else 18, 6), pady=3)
        if kind == "combo":
            w = AutoCombo(self, source=source, width=width)
        elif kind == "choice":
            w = ttk.Combobox(self, values=values, state="readonly", width=width)
        elif kind == "check":
            var = tk.BooleanVar(value=bool(default))
            w = ttk.Checkbutton(self, variable=var)
            w.var = var
        elif kind == "memo":
            w = ttk.Entry(self, width=width)
        else:
            w = ttk.Entry(self, width=width if kind != "amount" else 18)
            if kind == "amount":
                w.configure(justify="right")
        if kind == "date":
            w.configure(width=14)
        w.grid(row=r, column=c * 2 + 1, sticky="w" if kind in ("check", "date", "amount") else "we",
               pady=3, columnspan=1 + (span - 1) * 2)
        self._n += span
        self.fields[key], self.labels[key], self.kinds[key] = w, lab, kind
        self.defaults[key] = default
        self.set(key, default)
        return w

    def get(self, key):
        w, kind = self.fields[key], self.kinds[key]
        if kind == "check":
            return w.var.get()
        return w.get().strip()

    def set(self, key, value):
        w, kind = self.fields[key], self.kinds[key]
        if kind == "check":
            w.var.set(bool(value))
            return
        if kind == "date" and value is None:
            value = today_str()
        if kind == "choice":
            w.set(value or "")
            return
        state = str(w.cget("state"))
        if state == "disabled":
            w.configure(state="normal")
        w.delete(0, "end")
        if value not in (None, ""):
            w.insert(0, value)
        if state == "disabled":
            w.configure(state="disabled")

    def values(self):
        return {k: self.get(k) for k in self.fields}

    def clear(self, keep=()):
        for k in self.fields:
            if k not in keep:
                self.set(k, self.defaults[k])

    def enable(self, key, on=True):
        w = self.fields[key]
        if self.kinds[key] == "choice":
            w.configure(state="readonly" if on else "disabled")
        else:
            w.configure(state="normal" if on else "disabled")
        self.labels[key].configure(foreground="" if on else "#9aa3b2")

    def refresh_sources(self):
        for w in self.fields.values():
            if isinstance(w, AutoCombo):
                w.refresh()


class LineGrid(ttk.Frame):
    """Editable lines (like the bottom part of a QuickBooks bill).
    cols: list of dict(key, label, kind[text|amount|qty|combo|choice], width, source, values)
    A combo's source may take the row dict: source(row) -> list (e.g. accounts or items)."""

    def __init__(self, master, cols, rows=5, on_change=None, height=230, **kw):
        super().__init__(master, **kw)
        self.cols = cols
        self.on_change = on_change
        self.rows = []
        self.start_rows = rows
        head = tk.Frame(self, bg="#e9eef6")
        head.pack(fill="x")
        self.sf = ScrollFrame(self, height=height)
        self.sf.pack(fill="both", expand=True)
        for i, c in enumerate(cols):
            tk.Label(head, text=c["label"], bg="#e9eef6", fg="#14213d", anchor="w",
                     font=("Segoe UI", 9, "bold"), width=c.get("width", 12)).grid(
                row=0, column=i, padx=1, pady=3, sticky="w")
            self.sf.inner.grid_columnconfigure(i, weight=c.get("weight", 0))
            head.grid_columnconfigure(i, weight=c.get("weight", 0))
        tk.Label(head, text="", bg="#e9eef6", width=3).grid(row=0, column=len(cols))
        bar = ttk.Frame(self)
        bar.pack(fill="x", pady=(4, 0))
        ttk.Button(bar, text="+ Add line", command=self.add_row).pack(side="left")
        ttk.Button(bar, text="Clear lines", command=self.clear).pack(side="left", padx=6)
        self.total_var = tk.StringVar()
        ttk.Label(bar, textvariable=self.total_var, font=("Segoe UI", 10, "bold")).pack(side="right")
        for _ in range(rows):
            self.add_row()

    def add_row(self, values=None):
        r = len(self.rows)
        row = {"widgets": {}}
        for i, c in enumerate(self.cols):
            kind = c.get("kind", "text")
            if kind == "combo":
                w = AutoCombo(self.sf.inner, width=c.get("width", 20))
                src = c.get("source")
                w.source = (lambda s=src, rw=row: s(self._row_values(rw))) if src else None
                w.refresh()
            elif kind == "choice":
                w = ttk.Combobox(self.sf.inner, values=c["values"], state="readonly",
                                 width=c.get("width", 10))
                w.set(c.get("default", c["values"][0]))
                w.bind("<<ComboboxSelected>>", lambda e, rw=row: self._choice_changed(rw))
            else:
                w = ttk.Entry(self.sf.inner, width=c.get("width", 12))
                if kind in ("amount", "qty"):
                    w.configure(justify="right")
            w.grid(row=r, column=i, padx=1, pady=1, sticky="we")
            w.bind("<FocusOut>", lambda e, rw=row: self._changed(rw), add="+")
            if kind in ("amount", "qty"):
                w.bind("<KeyRelease>", lambda e, rw=row: self._changed(rw, typing=True), add="+")
            row["widgets"][c["key"]] = w
        x = ttk.Button(self.sf.inner, text="✕", width=3, command=lambda rw=row: self.remove_row(rw))
        x.grid(row=r, column=len(self.cols), padx=2)
        row["x"] = x
        self.rows.append(row)
        if values:
            self.set_row(row, values)
        if len(self.rows) > self.start_rows:
            self.sf.to_bottom()
        return row

    def set_row(self, row, values):
        for k, v in values.items():
            w = row["widgets"].get(k)
            if w is None:
                continue
            if isinstance(w, ttk.Combobox) and str(w.cget("state")) == "readonly":
                w.set(v)
            else:
                w.delete(0, "end")
                w.insert(0, "" if v is None else str(v))
        self._changed(row)

    def remove_row(self, row):
        for w in row["widgets"].values():
            w.destroy()
        row["x"].destroy()
        self.rows.remove(row)
        if not self.rows:
            self.add_row()
        self._regrid()
        self._update_total()

    def _regrid(self):
        for r, row in enumerate(self.rows):
            for i, c in enumerate(self.cols):
                row["widgets"][c["key"]].grid(row=r, column=i)
            row["x"].grid(row=r, column=len(self.cols))

    def _row_values(self, row):
        return {k: w.get().strip() for k, w in row["widgets"].items()}

    def _choice_changed(self, row):
        for c in self.cols:
            w = row["widgets"][c["key"]]
            if isinstance(w, AutoCombo):
                w.refresh()
        self._changed(row)

    def _changed(self, row, typing=False):
        """Qty x Rate -> Amount, then totals."""
        if row not in self.rows:
            return
        ws = row["widgets"]
        if "qty" in ws and "rate" in ws and "amount" in ws:
            try:
                q = parse_qty(ws["qty"].get())
                rate = parse_amount(ws["rate"].get(), required=False, allow_zero=True)
                try:
                    focused = self.focus_get()
                except (KeyError, tk.TclError):
                    focused = None
                if q is not None and rate is not None and focused is not ws["amount"]:
                    a = (q * rate).quantize(Decimal("0.01"))
                    ws["amount"].delete(0, "end")
                    ws["amount"].insert(0, f"{a:.2f}")
            except InputError:
                pass
        self._update_total()

    def sums(self, key):
        tot = Decimal(0)
        for row in self.rows:
            try:
                v = parse_amount(row["widgets"][key].get(), required=False, allow_zero=True,
                                 allow_negative=True)
                tot += v or 0
            except InputError:
                pass
        return tot

    def _update_total(self):
        if self.on_change:
            self.on_change()
        elif any(c["key"] == "amount" for c in self.cols):
            self.total_var.set(f"Total: {money(self.sums('amount'))}")

    def lines(self):
        return [self._row_values(r) for r in self.rows]

    def clear(self):
        for row in list(self.rows):
            for w in row["widgets"].values():
                w.destroy()
            row["x"].destroy()
        self.rows = []
        for _ in range(self.start_rows):
            self.add_row()
        self._update_total()

    def refresh_sources(self):
        for row in self.rows:
            for w in row["widgets"].values():
                if isinstance(w, AutoCombo):
                    w.refresh()

"""Excel Import tab and Log tab."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import importer, storage
from ..records import KINDS, describe
from ..util import money, show_date


def open_path(path):
    try:
        os.startfile(path)          # Windows
    except AttributeError:
        pass
    except OSError as e:
        messagebox.showerror("Open", str(e))


class ImportTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        self.path = None
        self.batches = []
        self.result_file = None
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=8)
        ttk.Label(top, text="Excel Bulk Import", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, style="Hint.TLabel", wraplength=1000, justify="left", text=(
            "1) Create the template (once).  2) Fill the sheets you need: Items, Vendors, Customers, "
            "Accounts, Bills, Bill Payments, Cheques, Journal Entries, Deposits, Transfers.  "
            "3) Choose the file and click Check.  4) Post the rows marked Ready.  A RESULT copy "
            "of your file is saved with the status of every row.")).pack(anchor="w", pady=(2, 0))
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14)
        ttk.Button(bar, text="Create blank template…", command=self.make_template).pack(side="left")
        ttk.Button(bar, text="Choose Excel file…", command=self.choose).pack(side="left", padx=8)
        ttk.Button(bar, text="Check file", command=self.check_file).pack(side="left")
        self.path_var = tk.StringVar(value="No file chosen")
        ttk.Label(bar, textvariable=self.path_var, style="Hint.TLabel").pack(side="left", padx=10)

        cols = ("sheet", "rows", "type", "name", "party", "date", "amount", "status", "message")
        heads = ("Sheet", "Row(s)", "Type", "Name / Ref", "Party / Detail", "Date", "Amount", "Status",
                 "Message")
        widths = (110, 60, 100, 170, 190, 85, 110, 80, 420)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=14, pady=8)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="e" if c == "amount" else "w", stretch=c == "message")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        for tag, color in (("Ready", "#fff7d6"), ("Error", "#fde2e2"), ("Rejected", "#fde2e2"),
                           ("Failed", "#fde2e2"), ("Added", "#dcfce7")):
            self.tree.tag_configure(tag, background=color)
        self.tree.bind("<Double-1>", self.show_message)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=14, pady=(0, 10))
        self.summary = tk.StringVar()
        ttk.Label(bottom, textvariable=self.summary, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.post_btn = ttk.Button(bottom, text="Post Ready rows to QuickBooks", style="Accent.TButton",
                                   command=self.post, state="disabled")
        self.post_btn.pack(side="right")
        self.open_btn = ttk.Button(bottom, text="Open result file", command=self.open_result,
                                   state="disabled")
        self.open_btn.pack(side="right", padx=8)

    def refresh_lists(self):
        pass

    def make_template(self):
        path = filedialog.asksaveasfilename(
            parent=self, title="Save import template", defaultextension=".xlsx",
            initialfile="QB Import Template.xlsx", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            importer.make_template(path, self.app.lists)
        except PermissionError:
            messagebox.showerror("Template", "Cannot save - is that file open in Excel?", parent=self)
            return
        extra = "" if self.app.lists else ("\n\nTip: connect first to also get a 'QuickBooks Lists' "
                                          "sheet with all your account / item / vendor names.")
        if messagebox.askyesno("Template", f"Template saved:\n{path}{extra}\n\nOpen it now?", parent=self):
            open_path(path)

    def choose(self):
        path = filedialog.askopenfilename(parent=self, title="Choose filled import file",
                                          filetypes=[("Excel", "*.xlsx *.xlsm")])
        if path:
            self.path = path
            self.path_var.set(path)
            self.check_file()

    def check_file(self):
        if not self.path:
            self.choose()
            return
        if not self.app.require_lists():
            return
        try:
            batches, skipped, info = importer.read_workbook(self.path)
        except PermissionError:
            messagebox.showerror("Import", "Cannot read the file. Close it in Excel and try again.", parent=self)
            return
        except Exception as e:
            messagebox.showerror("Import", f"Cannot read the file:\n{e}", parent=self)
            return
        self.batches = importer.check_batches(batches, self.app.lists)
        self.result_file = None
        self.open_btn.configure(state="disabled")
        self.redraw()
        if not batches:
            messagebox.showinfo("Import", "No rows to import were found."
                                + (f"\n{skipped} row(s) already Added were skipped." if skipped else ""),
                                parent=self)
        elif skipped:
            self.app.status(f"{skipped} row(s) already marked Added were skipped.")

    def redraw(self):
        self.tree.delete(*self.tree.get_children())
        for i, b in enumerate(self.batches):
            if b.record:
                name, party, amount = describe(b.record)
                date = show_date(b.record.get("date", ""))
            else:
                name = b.raw.get("name") or b.raw.get("ref") or ""
                party = b.raw.get("vendor") or b.raw.get("payee") or ""
                amount, date = None, ""
            msg = b.result if b.status != "Added" else f"QuickBooks ID {b.result}"
            self.tree.insert("", "end", iid=str(i), tags=(b.status,), values=(
                b.sheet, b.row_text, KINDS[b.kind], name or "", party or "", date,
                money(amount) if amount is not None else "", b.status, (msg or "").replace("\n", " | ")))
        counts = {}
        for b in self.batches:
            counts[b.status] = counts.get(b.status, 0) + 1
        self.summary.set("   ".join(f"{k}: {v}" for k, v in sorted(counts.items())))
        self.post_btn.configure(state="normal" if counts.get("Ready") else "disabled")

    def show_message(self, e):
        sel = self.tree.selection()
        if sel:
            b = self.batches[int(sel[0])]
            messagebox.showinfo(f"{b.sheet} row {b.row_text}", f"Status: {b.status}\n\n{b.error or b.result}",
                                parent=self)

    def post(self):
        ready = [b for b in self.batches if b.status == "Ready"]
        if not ready:
            return
        bad = sum(1 for b in self.batches if b.status == "Error")
        msg = (f"Post {len(ready)} record(s) to QuickBooks?\n\nCompany: {self.app.company_label()}"
               + (f"\n\n{bad} row(s) with errors will NOT be posted." if bad else ""))
        if not self.app.confirm("Post to QuickBooks", msg):
            return

        def done(_):
            self.redraw()
            try:
                self.result_file = importer.write_result(self.path, self.batches)
                self.open_btn.configure(state="normal")
                saved = f"\n\nResult file saved:\n{self.result_file}"
            except Exception as e:
                saved = f"\n\n(Could not save result file: {e})"
            added = sum(1 for b in ready if b.status == "Added")
            self.app.notify("Import finished", f"{added} of {len(ready)} record(s) added to QuickBooks."
                            + (f"\n{len(ready) - added} rejected; see the Message column." if added < len(ready)
                               else "") + saved)

        self.app.post_batches(ready, done, progress=self.redraw)

    def open_result(self):
        if self.result_file:
            open_path(self.result_file)


class LogTab(ttk.Frame):
    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=8)
        ttk.Label(top, text="Posting Log", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, text="Everything sent to QuickBooks from this PC, newest first. "
                  "Double-click a row to see the full message.", style="Hint.TLabel").pack(anchor="w")
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14)
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Open log in Excel", command=lambda: open_path(storage.LOG_FILE)).pack(
            side="left", padx=8)
        ttk.Button(bar, text="Open data folder", command=lambda: open_path(storage.FOLDER)).pack(side="left")
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=14, pady=8)
        cols = storage.LOG_COLUMNS
        widths = (130, 110, 90, 140, 180, 85, 100, 75, 130, 380, 60)
        self.tree = ttk.Treeview(frame, columns=cols, show="headings")
        for c, w in zip(cols, widths):
            self.tree.heading(c, text=c)
            self.tree.column(c, width=w, anchor="e" if c == "Amount" else "w", stretch=c == "Message")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self.tree.tag_configure("Added", background="#dcfce7")
        self.tree.tag_configure("bad", background="#fde2e2")
        self.tree.bind("<Double-1>", self.show)
        self.refresh()

    def refresh_lists(self):
        pass

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for row in storage.read_log():
            row = (row + [""] * len(storage.LOG_COLUMNS))[:len(storage.LOG_COLUMNS)]
            st = row[7]
            self.tree.insert("", "end", values=row, tags=("Added",) if st == "Added" else ("bad",))

    def show(self, e):
        sel = self.tree.selection()
        if sel:
            v = self.tree.item(sel[0], "values")
            messagebox.showinfo("Log entry", "\n".join(f"{c}: {x}" for c, x in zip(storage.LOG_COLUMNS, v)),
                                parent=self)

"""Excel Import tab and Log tab."""
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .. import agent, importer, storage
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
                b.sheet, b.row_text, KINDS.get(b.kind, b.kind), name or "", party or "", date,
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


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return 0


class AgentTab(ImportTab):
    """Requests prepared by Claude arrive as files in the Agent folder; you check and post them."""

    POLL_MS = 3000

    def __init__(self, master, app):
        ttk.Frame.__init__(self, master)
        self.app = app
        self.requests = []
        self.current = None
        self.batches = []
        self._seen = set()
        self.folder = agent.ensure(app.settings.get("agent_folder") or agent.default_folder())
        top = ttk.Frame(self)
        top.pack(fill="x", padx=14, pady=8)
        ttk.Label(top, text="Agent Inbox", style="Title.TLabel").pack(anchor="w")
        ttk.Label(top, style="Hint.TLabel", wraplength=1100, justify="left", text=(
            "Ask Claude in the chat (e.g. 'invoice MCB Bank 45,250 October discount share, Store 1'). "
            "Claude puts the entries here. Check them, then click Post. Nothing goes to QuickBooks "
            "without your click. Claude reads the result back from the Results folder.")).pack(anchor="w")
        bar = ttk.Frame(self)
        bar.pack(fill="x", padx=14)
        ttk.Label(bar, text="Agent folder:").pack(side="left")
        self.folder_var = tk.StringVar(value=self.folder)
        ttk.Label(bar, textvariable=self.folder_var, style="Hint.TLabel").pack(side="left", padx=6)
        ttk.Button(bar, text="Open folder", command=lambda: open_path(self.folder)).pack(side="left")
        ttk.Button(bar, text="Change…", command=self.change_folder).pack(side="left", padx=6)
        ttk.Button(bar, text="Refresh", command=self.scan).pack(side="left")
        self.auto_var = tk.BooleanVar(value=bool(app.settings.get("agent_autopost")))
        ttk.Checkbutton(bar, variable=self.auto_var, command=self._auto_changed,
                        text="Post agent requests automatically (no click needed)").pack(side="right")

        pan = ttk.PanedWindow(self, orient="vertical")
        pan.pack(fill="both", expand=True, padx=14, pady=8)
        upper = ttk.Frame(pan)
        ttk.Label(upper, text="Waiting requests", style="Section.TLabel").pack(anchor="w")
        self.req_tree = ttk.Treeview(upper, columns=("title", "company", "entries", "received", "file"),
                                     show="headings", height=5, selectmode="browse")
        for c, h, w in (("title", "Request", 380), ("company", "Company", 160), ("entries", "Entries", 70),
                        ("received", "Received", 140), ("file", "File", 260)):
            self.req_tree.heading(c, text=h)
            self.req_tree.column(c, width=w, stretch=c == "title")
        self.req_tree.pack(fill="both", expand=True)
        self.req_tree.bind("<<TreeviewSelect>>", lambda e: self.select())
        pan.add(upper, weight=1)
        lower = ttk.Frame(pan)
        ttk.Label(lower, text="Entries in the selected request (double-click for details)",
                  style="Section.TLabel").pack(anchor="w")
        cols = ("sheet", "rows", "type", "name", "party", "date", "amount", "status", "message")
        heads = ("Request", "No", "Type", "Name / Ref", "Party / Detail", "Date", "Amount", "Status", "Message")
        widths = (150, 40, 100, 140, 200, 85, 110, 80, 420)
        self.tree = ttk.Treeview(lower, columns=cols, show="headings", height=9)
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="e" if c == "amount" else "w", stretch=c == "message")
        self.tree.pack(fill="both", expand=True)
        for tag, color in (("Ready", "#fff7d6"), ("Error", "#fde2e2"), ("Rejected", "#fde2e2"),
                           ("Failed", "#fde2e2"), ("Added", "#dcfce7")):
            self.tree.tag_configure(tag, background=color)
        self.tree.bind("<Double-1>", self.show_message)
        pan.add(lower, weight=2)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=14, pady=(0, 10))
        self.summary = tk.StringVar()
        ttk.Label(bottom, textvariable=self.summary, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.post_btn = ttk.Button(bottom, text="Post to QuickBooks", style="Accent.TButton",
                                   command=self.post, state="disabled")
        self.post_btn.pack(side="right")
        self.reject_btn = ttk.Button(bottom, text="Reject request", command=self.reject, state="disabled")
        self.reject_btn.pack(side="right", padx=8)
        self.after(500, self._poll)

    # -- folder
    def change_folder(self):
        path = filedialog.askdirectory(parent=self, title="Choose the Agent folder", initialdir=self.folder)
        if path:
            self.folder = agent.ensure(os.path.normpath(path))
            self.folder_var.set(self.folder)
            self.app.settings["agent_folder"] = self.folder
            storage.save_settings(self.app.settings)
            if self.app.lists:
                agent.write_lists(self.folder, self.app.lists)
            self.scan()

    def _auto_changed(self):
        self.app.settings["agent_autopost"] = self.auto_var.get()
        storage.save_settings(self.app.settings)
        if self.auto_var.get():
            self.app.status("Automatic posting is ON: requests from Claude are posted as soon as they arrive.")
            self.auto_post_next()

    def answer_queries(self):
        """Read-only question requests (open bills, balances...) are answered without asking."""
        if self.app.busy or self.app.lists is None:
            return False
        for r in self.requests:
            if r.queries and not r.error and not getattr(r, "answered", False):
                r.answered = True
                company = self.app.lists.company

                def done(result, r=r):
                    agent.finish_query(self.folder, r, result, company)
                    self.app.status(f"Answered Claude's question: {r.title}")
                    self.scan()
                    self.after(300, self.auto_post_next)

                self.app.run_query(r, done)
                return True
        return False

    def auto_post_next(self):
        """Post the first waiting request on its own, if automatic posting is on.
        Only when every entry checks out; otherwise it waits for review and a .check.json
        with the problems is written to Results for Claude to fix."""
        if self.answer_queries():
            return
        if not self.auto_var.get() or self.app.busy or self.app.lists is None:
            return
        for r in self.requests:
            if r.error or r.queries is not None or getattr(r, "auto_tried", False):
                continue
            r.auto_tried = True
            batches = r.build(self.app.lists)
            bad = [b for b in batches if b.status != "Ready"]
            if bad or not batches or agent.already_posted(self.folder, r.request_id):
                agent.write_check(self.folder, r, self.app.lists.company,
                                  "already posted before" if not bad and batches else "")
                self.app.status(f"Request '{r.title}' needs your review (see Agent Inbox).")
                continue
            self.current, self.batches = r, batches
            self.redraw()
            self._post(r, batches, auto=True)
            return

    def _poll(self):
        try:
            if not self.app.busy:
                self.scan(quiet=True)
        finally:
            self.after(self.POLL_MS, self._poll)

    def scan(self, quiet=False):
        paths = agent.pending(self.folder)
        stamp = [(p, _mtime(p)) for p in paths]
        if [(r.path, r.mtime) for r in self.requests] == stamp and quiet:
            return
        if self.app.busy:
            return
        keep = self.current.path if self.current else None
        old = {(r.path, r.mtime): r for r in self.requests}
        # keep already-checked requests as they are (same objects); re-read new or changed files
        self.requests = [old.get(st) or agent.Request(st[0]) for st in stamp]
        if self.current is not None and self.current not in self.requests:
            self.current, self.batches = None, []
        if keep not in paths:
            self.current, self.batches = None, []
        self.req_tree.delete(*self.req_tree.get_children())
        for i, r in enumerate(self.requests):
            self.req_tree.insert("", "end", iid=str(i), values=(
                r.title + ("   (cannot read)" if r.error else ""), r.company,
                len(r.data.get("records") or []), r.received.strftime("%d/%m/%Y %H:%M"), r.name))
        n = len(self.requests)
        self.app.nb.tab(self, text=f"  Agent Inbox ({n})  " if n else "  Agent Inbox  ")
        new = [r for r in self.requests if (r.path, r.mtime) not in self._seen]
        self._seen.update((r.path, r.mtime) for r in self.requests)
        if new:
            self.after(300, self.auto_post_next)
        if new and quiet:
            self.app.status(f"New request from the agent: {new[0].title}. Open the Agent Inbox tab.")
            try:
                self.app.deiconify()
                self.app.lift()
                self.app.bell()
            except tk.TclError:
                pass
        idx = next((i for i, r in enumerate(self.requests) if r.path == keep), 0 if self.requests else None)
        if idx is not None:
            self.req_tree.selection_set(str(idx))
            self.select()
        else:
            self.current, self.batches = None, []
            self.redraw()
            self.reject_btn.configure(state="disabled")

    def select(self):
        sel = self.req_tree.selection()
        if not sel or self.app.busy:
            return
        if self.current is not None and self.batches and \
                self.requests[int(sel[0])].path == self.current.path:
            return
        self.current = self.requests[int(sel[0])]
        self.recheck()

    def recheck(self):
        r = self.current
        if r is None or self.app.busy:
            return
        if r.error:
            self.batches = []
            self.redraw()
            self.summary.set(r.error)
        else:
            self.batches = r.build(self.app.lists)
            self.redraw()
            if self.app.lists is None:
                self.summary.set("Not connected: click 'Connect & Load Lists' to check these entries.")
                self.post_btn.configure(state="disabled")
            elif agent.already_posted(self.folder, r.request_id):
                self.summary.set("WARNING: a request with this ID was already posted before. "
                                 "Check QuickBooks before posting again.")
        self.reject_btn.configure(state="normal")

    def refresh_lists(self):
        if self.app.lists:
            agent.write_lists(self.folder, self.app.lists)
        self.recheck()
        self.after(300, self.auto_post_next)

    # -- actions
    def post(self):
        r = self.current
        ready = [b for b in self.batches if b.status == "Ready"]
        if not r or not ready:
            return
        total = sum((b.record.get("total") or 0 for b in ready), 0)
        bad = sum(1 for b in self.batches if b.status == "Error")
        msg = (f"Request: {r.title}\n\nPost {len(ready)} entr{'y' if len(ready) == 1 else 'ies'}"
               f" (total {money(total)}) to QuickBooks?\n\nCompany: {self.app.company_label()}"
               + (f"\n\n{bad} entr{'y' if bad == 1 else 'ies'} with errors will NOT be posted." if bad else ""))
        if not self.app.confirm("Post to QuickBooks", msg):
            return
        self._post(r, ready)

    def _post(self, r, ready, auto=False):
        def done(_):
            self.redraw()
            company = self.app.lists.company if self.app.lists else ""
            agent.finish(self.folder, r, company, "Posted")
            added = sum(1 for b in ready if b.status == "Added")
            text = (f"{added} of {len(ready)} entr{'y' if len(ready) == 1 else 'ies'} added to QuickBooks"
                    + (" (some rejected; ask Claude to check)" if added < len(ready) else ""))
            if auto:
                self.app.status(f"Posted automatically: {r.title}. {text}.")
            else:
                self.app.notify("Agent request posted", text + ".")
            self.current = None
            self.scan()
            self.after(500, self.auto_post_next)

        self.app.post_batches(ready, done, progress=self.redraw, source="Agent (auto)" if auto else "Agent")

    def reject(self):
        r = self.current
        if not r or not self.app.confirm("Reject request", f"Reject '{r.title}'? Nothing will be posted."):
            return
        agent.finish(self.folder, r, self.app.lists.company if self.app.lists else "", "Rejected")
        self.current = None
        self.scan()


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

"""Main window: company file chooser, connection, background work, tabs."""
import os
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import APP_TITLE, VERSION, poster, storage
from ..qbxml import QBError
from ..session import QBConnectError, QBConnection
from .forms import (AccountTab, BillTab, ChequeTab, CustomerTab, DepositTab, ItemTab, JournalTab,
                    PayBillsTab, TransferTab, VendorTab)
from .tabs_extra import ImportTab, LogTab

NAVY = "#14213d"


class App(tk.Tk):
    def __init__(self, demo=False):
        super().__init__()
        self.demo = demo
        self.lists = None
        self.busy = False
        self.settings = storage.load_settings()
        self.title(f"{APP_TITLE} {VERSION}" + ("  -  DEMO (not connected to real QuickBooks)" if demo else ""))
        self.geometry("1280x800")
        self.minsize(1050, 650)
        self._style()
        self._header()
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(6, 0))
        self.tabs = []
        for cls, label in [(BillTab, "Enter Bill"), (PayBillsTab, "Pay Bills"), (ChequeTab, "Write Cheque"),
                           (JournalTab, "Journal Entry"), (DepositTab, "Deposit"), (TransferTab, "Transfer"),
                           (ItemTab, "Item"), (VendorTab, "Vendor"), (CustomerTab, "Customer"),
                           (AccountTab, "Account"), (ImportTab, "Excel Import"), (LogTab, "Log")]:
            t = cls(self.nb, self)
            self.nb.add(t, text=f"  {label}  ")
            self.tabs.append(t)
        self.nb.bind("<<NotebookTabChanged>>", self._tab_changed)
        self.status_var = tk.StringVar(value="Not connected. Choose the company file and click "
                                              "'Connect & Load Lists'.")
        bar = tk.Frame(self, bg="#e9eef6")
        bar.pack(fill="x", side="bottom")
        tk.Label(bar, textvariable=self.status_var, bg="#e9eef6", anchor="w", padx=10, pady=4).pack(
            side="left", fill="x", expand=True)
        self._q = queue.Queue()

    # ------------------------------------------------------------ look
    def _style(self):
        s = ttk.Style(self)
        for theme in ("vista", "clam"):
            if theme in s.theme_names():
                s.theme_use(theme)
                break
        base = ("Segoe UI", 10)
        self.option_add("*Font", base)
        s.configure(".", font=base)
        s.configure("Title.TLabel", font=("Segoe UI", 15, "bold"), foreground=NAVY)
        s.configure("Hint.TLabel", foreground="#5b6475")
        s.configure("Section.TLabel", font=("Segoe UI", 10, "bold"), foreground=NAVY)
        s.configure("Accent.TButton", font=("Segoe UI", 10, "bold"), padding=(14, 6))
        s.configure("TNotebook.Tab", padding=(6, 5))
        s.configure("Treeview", rowheight=24)

    def _header(self):
        h = tk.Frame(self, bg=NAVY)
        h.pack(fill="x")
        tk.Label(h, text="Arcadian QB Connector", bg=NAVY, fg="white",
                 font=("Segoe UI", 15, "bold"), padx=14, pady=10).pack(side="left")
        right = tk.Frame(h, bg=NAVY)
        right.pack(side="right", padx=12)
        tk.Label(right, text="Company file:", bg=NAVY, fg="#c9d3e6").pack(side="left")
        self.company_cb = ttk.Combobox(right, state="readonly", width=58)
        self.company_cb.pack(side="left", padx=6)
        self.company_cb.bind("<<ComboboxSelected>>", self._company_changed)
        ttk.Button(right, text="Files…", command=self.manage_files).pack(side="left")
        ttk.Button(right, text="Connect & Load Lists", style="Accent.TButton",
                   command=self.connect).pack(side="left", padx=(8, 0))
        self.conn_var = tk.StringVar(value="● Not connected")
        self.conn_lbl = tk.Label(h, textvariable=self.conn_var, bg=NAVY, fg="#fca5a5",
                                 font=("Segoe UI", 10, "bold"))
        self.conn_lbl.pack(side="right", padx=10)
        self._fill_company_list()

    def _fill_company_list(self):
        files = self.settings.get("company_files", [])
        vals = [storage.CURRENT_FILE] + [f"{f['label']}   ({f['path']})" for f in files]
        self.company_cb["values"] = vals
        last = self.settings.get("last_company", storage.CURRENT_FILE)
        self.company_cb.set(last if last in vals else storage.CURRENT_FILE)

    def company_path(self):
        i = self.company_cb.current()
        files = self.settings.get("company_files", [])
        if i <= 0 or i - 1 >= len(files):
            return ""
        return files[i - 1]["path"]

    def company_label(self):
        if self.lists:
            return f"{self.lists.company}  ({self.lists.file_path})"
        return self.company_cb.get()

    def _company_changed(self, e=None):
        self.settings["last_company"] = self.company_cb.get()
        storage.save_settings(self.settings)
        if self.lists:
            self.lists = None
            self._set_connected(False)
            self.status("Company changed. Click 'Connect & Load Lists'.")
            self.refresh_lists()

    def manage_files(self):
        d = tk.Toplevel(self)
        d.title("Company files")
        d.transient(self)
        d.grab_set()
        ttk.Label(d, text="Save your company files here so you can switch between them.\n"
                  "'Currently open file' always uses whatever file is open in QuickBooks.",
                  justify="left").pack(anchor="w", padx=12, pady=(12, 6))
        lb = tk.Listbox(d, width=90, height=8)
        lb.pack(padx=12, fill="both", expand=True)

        def fill():
            lb.delete(0, "end")
            for f in self.settings["company_files"]:
                lb.insert("end", f"{f['label']}   ({f['path']})")

        def add():
            path = filedialog.askopenfilename(parent=d, title="Choose QuickBooks company file",
                                              filetypes=[("QuickBooks company file", "*.qbw")])
            if not path:
                return
            label = simpledialog.askstring("Name", "Short name for this file (e.g. Arcadian Cafe, AVERTICAL):",
                                           parent=d, initialvalue=os.path.splitext(os.path.basename(path))[0])
            if not label:
                return
            self.settings["company_files"].append({"label": label.strip(), "path": os.path.normpath(path)})
            storage.save_settings(self.settings)
            fill()

        def remove():
            sel = lb.curselection()
            if sel:
                del self.settings["company_files"][sel[0]]
                storage.save_settings(self.settings)
                fill()

        bar = ttk.Frame(d)
        bar.pack(fill="x", padx=12, pady=12)
        ttk.Button(bar, text="Add file…", command=add).pack(side="left")
        ttk.Button(bar, text="Remove", command=remove).pack(side="left", padx=6)
        ttk.Button(bar, text="Close", command=d.destroy).pack(side="right")
        fill()
        self.wait_window(d)
        self._fill_company_list()

    # ------------------------------------------------------------ helpers for tabs
    def names(self, cat):
        if not self.lists:
            return []
        return self.lists.payees() if cat == "payees" else self.lists.names(cat)

    def accounts_of(self, *types):
        return self.lists.accounts_of(*types) if self.lists else []

    def status(self, text):
        self.status_var.set(text)

    def confirm(self, title, msg):
        return messagebox.askyesno(title, msg, parent=self)

    def notify(self, title, msg):
        messagebox.showinfo(title, msg, parent=self)

    def error(self, title, msg):
        messagebox.showerror(title, msg, parent=self)

    def require_lists(self):
        if self.lists is not None:
            return True
        if self.confirm("Not connected", "The app is not connected to QuickBooks yet.\n\n"
                        "Connect and load the lists now? (Then click Save again.)"):
            self.connect()
        return False

    def refresh_lists(self):
        for t in self.tabs:
            t.refresh_lists()

    def _tab_changed(self, e=None):
        t = self.tabs[self.nb.index("current")]
        if isinstance(t, LogTab):
            t.refresh()

    def _set_connected(self, on):
        if on:
            self.conn_var.set(f"● {self.lists.company}")
            self.conn_lbl.configure(fg="#86efac")
        else:
            self.conn_var.set("● Not connected")
            self.conn_lbl.configure(fg="#fca5a5")

    # ------------------------------------------------------------ QuickBooks work (background)
    def open_qb(self):
        if self.demo:
            from ..demo import FakeQB
            return FakeQB()
        return QBConnection(self.company_path())

    def run_bg(self, text, fn, on_ok, on_done=None):
        """Run fn(report) in a worker thread; on_ok(result) runs back on the screen thread."""
        if self.busy:
            self.notify("Please wait", "Still working on the previous request.")
            return
        self.busy = True
        self.status(text)
        self.configure(cursor="watch")
        q = self._q

        def work():
            try:
                q.put(("ok", fn(lambda msg: q.put(("progress", msg)))))
            except Exception as e:
                q.put(("err", e, traceback.format_exc()))

        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    item = q.get_nowait()
                    if item[0] == "progress":
                        self.status(item[1])
                        if on_done:
                            on_done()
                        continue
                    self.busy = False
                    self.configure(cursor="")
                    if item[0] == "ok":
                        on_ok(item[1])
                    else:
                        self._show_error(item[1], item[2])
                    return
            except queue.Empty:
                self.after(100, poll)

        self.after(100, poll)

    def _show_error(self, e, tb):
        if isinstance(e, QBError):
            self.status("QuickBooks rejected the request.")
            self.error("QuickBooks rejected this", f"{e.message}\n\n(Error {e.code}; nothing was saved.)")
        elif isinstance(e, QBConnectError):
            self.status("Could not connect to QuickBooks.")
            self.error("QuickBooks connection", str(e))
        else:
            self.status("Unexpected error.")
            try:
                os.makedirs(storage.FOLDER, exist_ok=True)
                with open(os.path.join(storage.FOLDER, "crash.txt"), "a", encoding="utf-8") as f:
                    f.write(tb + "\n")
            except OSError:
                pass
            self.error("Error", f"{e}\n\nDetails saved in {storage.FOLDER}\\crash.txt")

    def connect(self):
        def work(report):
            with self.open_qb() as qb:
                report("Loading lists from QuickBooks…")
                lists = poster.load_lists(qb)
                lists.file_path = getattr(qb, "file_name", "") or lists.file_path
                return lists

        def ok(lists):
            self.lists = lists
            self._set_connected(True)
            self.refresh_lists()
            self.status(f"Connected: {lists.company}   {lists.file_path}   ({lists.summary()})")

        self.run_bg("Connecting to QuickBooks… (answer any QuickBooks window that opens)", work, ok)

    def post_record(self, record, done):
        company = self.lists.company if self.lists else ""

        def work(report):
            with self.open_qb() as qb:
                return poster.post(qb, record, company, "Screen")

        def ok(new_id):
            self.status(f"Saved to QuickBooks ({company}).")
            done(new_id)

        self.run_bg("Saving to QuickBooks…", work, ok)

    def fetch_open_bills(self, vendor, done):
        def work(report):
            with self.open_qb() as qb:
                return poster.open_bills(qb, vendor)

        def ok(bills):
            self.status(f"{len(bills)} unpaid bill(s) for {vendor}.")
            done(bills)

        self.run_bg(f"Loading unpaid bills for {vendor}…", work, ok)

    def post_batches(self, batches, done, progress=None):
        company = self.lists.company if self.lists else ""
        holder = {}

        def work(report):
            try:
                with self.open_qb() as qb:
                    for i, b in enumerate(batches, 1):
                        report(f"Posting {i} of {len(batches)}…")
                        try:
                            b.result = poster.post(qb, b.record, company, "Excel")
                            b.status = "Added"
                        except QBError as e:
                            b.status, b.result = "Rejected", e.message
            except QBConnectError as e:
                holder["err"] = e
            return None

        def ok(_):
            if "err" in holder:
                self.error("QuickBooks connection", f"Posting stopped:\n\n{holder['err']}\n\n"
                           "Rows still marked Ready were not posted.")
            self.status("Import finished.")
            done(None)

        self.run_bg("Posting to QuickBooks…", work, ok, on_done=progress)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        from .selftest import run
        sys.exit(run())
    app = App(demo="--demo" in argv)
    app.mainloop()

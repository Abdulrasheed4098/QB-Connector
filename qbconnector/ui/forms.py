"""One screen (tab) per kind of record."""
import tkinter as tk
from decimal import Decimal
from tkinter import messagebox, ttk

from ..records import ACCOUNT_TYPE_LABELS, ACCOUNT_TYPES, KINDS, check, describe
from ..util import InputError, money, show_date, parse_amount
from .widgets import Form, LineGrid

PAD = {"padx": 14, "pady": 8}


class BaseTab(ttk.Frame):
    kind = ""
    title = ""
    hint = ""
    keep_after_save = ()      # form fields kept after a successful save

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app
        top = ttk.Frame(self)
        top.pack(fill="x", **PAD)
        ttk.Label(top, text=self.title, style="Title.TLabel").pack(anchor="w")
        if self.hint:
            ttk.Label(top, text=self.hint, style="Hint.TLabel", wraplength=1000,
                      justify="left").pack(anchor="w", pady=(2, 0))
        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=14)
        self.build()
        bar = ttk.Frame(self)
        bar.pack(fill="x", side="bottom", padx=14, pady=10)
        self.save_btn = ttk.Button(bar, text="Save to QuickBooks", style="Accent.TButton",
                                   command=self.save)
        self.save_btn.pack(side="right")
        ttk.Button(bar, text="Clear", command=self.clear).pack(side="right", padx=8)

    # -- override
    def build(self):
        pass

    def collect(self):
        return {}

    def clear(self):
        pass

    def refresh_lists(self):
        for w in self.walk():
            if hasattr(w, "refresh_sources"):
                w.refresh_sources()

    def walk(self, w=None):
        w = w or self
        for c in w.winfo_children():
            yield c
            yield from self.walk(c)

    def after_saved(self, record, new_id):
        if record["kind"] in ("item", "vendor", "customer", "account") and self.app.lists:
            name, extra, _ = describe(record)
            cat = {"item": "items", "vendor": "vendors", "customer": "customers",
                   "account": "accounts"}[record["kind"]]
            self.app.lists.add_name(cat, name, record.get("type") if cat == "accounts"
                                    else (extra if cat == "items" else None))
            self.app.refresh_lists()
        self.clear()

    # -- shared save flow
    def save(self):
        if not self.app.require_lists():
            return
        try:
            record = check(self.kind, self.collect(), self.app.lists)
        except InputError as e:
            messagebox.showerror("Please correct", str(e), parent=self)
            return
        name, party, amount = describe(record)
        lines = [f"Type:  {KINDS[self.kind]}"]
        if name:
            lines.append(f"Name / Ref:  {name}")
        if party:
            lines.append(f"Party / Detail:  {party}")
        if record.get("date"):
            lines.append(f"Date:  {show_date(record['date'])}")
        if amount is not None:
            lines.append(f"Amount:  {money(amount)}")
        lines.append(f"\nCompany:  {self.app.company_label()}")
        if not self.app.confirm("Save to QuickBooks?", "\n".join(lines) + "\n\nSave this to QuickBooks?"):
            return

        def done(new_id):
            self.app.notify("Saved", f"{KINDS[self.kind]} added to QuickBooks."
                            + (f"\nQuickBooks ID: {new_id}" if new_id else ""))
            self.after_saved(record, new_id)

        self.app.post_record(record, done)


# ------------------------------------------------------------------ lists

class ItemTab(BaseTab):
    kind = "item"
    title = "New Item"
    hint = ("Inventory Part: stock you buy and track.  Non-inventory: things you buy/sell without "
            "tracking stock.  Service / Other Charge: services and charges.  "
            "Fields marked * are required.  Sub-item: choose a Parent item.")

    TYPES = ["Inventory Part", "Non-inventory Part", "Service", "Other Charge"]

    def build(self):
        f = self.f = Form(self.body, columns=2)
        f.pack(fill="x", anchor="w")
        L = lambda cat: (lambda: self.app.names(cat))  # noqa: E731
        f.add("type", "Item Type", "choice", values=self.TYPES, default="Non-inventory Part", required=True)
        f.fields["type"].bind("<<ComboboxSelected>>", lambda e: self.update_fields())
        f.add("name", "Item Name", required=True)
        f.add("parent", "Sub-item of (Parent)", "combo", source=L("items"))
        f.add("inactive", "Inactive", "check")
        self.both_var = tk.BooleanVar(value=False)
        ttk.Separator(self.body).pack(fill="x", pady=8)
        self.both_chk = ttk.Checkbutton(
            self.body, variable=self.both_var, command=self.update_fields,
            text="This item is bought from vendors AND sold (needs both Income and Expense accounts)")
        self.both_chk.pack(anchor="w")
        g = self.g = Form(self.body, columns=2)
        g.pack(fill="x", anchor="w", pady=(6, 0))
        g.add("sales_desc", "Sales Description")
        g.add("purchase_desc", "Purchase Description")
        g.add("price", "Sales Price", "amount")
        g.add("cost", "Cost", "amount")
        g.add("income_account", "Income Account", "combo", source=L("accounts"), required=True)
        g.add("expense_account", "COGS Account", "combo", source=L("accounts"), required=True)
        g.add("pref_vendor", "Preferred Vendor", "combo", source=L("vendors"))
        g.add("asset_account", "Inventory Asset Account", "combo", source=L("accounts"), required=True)
        g.add("reorder_point", "Reorder Point", "amount")
        g.add("qty_on_hand", "Qty On Hand", "amount")
        g.add("total_value", "Total Value", "amount")
        g.add("as_of", "Qty As Of Date", "date", default="")
        self.update_fields()

    def update_fields(self):
        t = self.f.get("type")
        inv = t == "Inventory Part"
        both = inv or self.both_var.get()
        self.both_chk.configure(state="disabled" if inv else "normal")
        for k in ("asset_account", "reorder_point", "qty_on_hand", "total_value", "as_of"):
            self.g.enable(k, inv)
        for k in ("purchase_desc", "cost", "expense_account", "pref_vendor"):
            self.g.enable(k, both)
        self.g.labels["income_account"].configure(
            text="Income Account *" if both else "Account (Income or Expense) *")
        self.g.labels["expense_account"].configure(
            text="COGS Account *" if inv else "Expense Account *")
        self.g.labels["sales_desc"].configure(text="Sales Description" if both else "Description")
        self.g.labels["price"].configure(text="Sales Price" if both else "Rate / Price")

    def collect(self):
        t = self.f.get("type")
        inv = t == "Inventory Part"
        both = inv or self.both_var.get()
        raw = {**self.f.values(), **self.g.values()}
        raw["inactive"] = self.f.get("inactive")
        if not both:
            for k in ("purchase_desc", "cost", "expense_account", "pref_vendor"):
                raw[k] = None
        if not inv:
            for k in ("asset_account", "reorder_point", "qty_on_hand", "total_value", "as_of"):
                raw[k] = None
        return raw

    def clear(self):
        self.f.clear(keep=("type",))
        self.g.clear(keep=("income_account", "expense_account", "asset_account"))


class VendorTab(BaseTab):
    kind = "vendor"
    title = "New Vendor"
    hint = "Supplier or anyone you pay through bills. Only the name is required."

    def build(self):
        f = self.f = Form(self.body, columns=2)
        f.pack(fill="x", anchor="w")
        f.add("name", "Vendor Name", required=True)
        f.add("company", "Company Name")
        f.add("addr1", "Address 1")
        f.add("addr2", "Address 2")
        f.add("city", "City", default="Lahore")
        f.add("phone", "Phone")
        f.add("email", "Email")
        f.add("contact", "Contact Person")
        f.add("print_as", "Print on Cheque As")
        f.add("account_no", "Account No (with vendor)")
        f.add("ntn", "NTN / Tax ID")
        f.add("terms", "Terms", "combo", source=lambda: self.app.names("terms"))
        f.add("open_balance", "Opening Balance", "amount")
        f.add("open_balance_date", "Opening Balance Date", "date", default="")
        f.add("notes", "Notes", span=2, width=80)

    def collect(self):
        return self.f.values()

    def clear(self):
        self.f.clear()


class CustomerTab(BaseTab):
    kind = "customer"
    title = "New Customer / Job"
    hint = "Customers (e.g. banks for discount reimbursement). A Job is a sub-customer: choose a Parent."

    def build(self):
        f = self.f = Form(self.body, columns=2)
        f.pack(fill="x", anchor="w")
        f.add("name", "Customer Name", required=True)
        f.add("parent", "Job of (Parent Customer)", "combo", source=lambda: self.app.names("customers"))
        f.add("company", "Company Name")
        f.add("contact", "Contact Person")
        f.add("addr1", "Address 1")
        f.add("addr2", "Address 2")
        f.add("city", "City", default="Lahore")
        f.add("phone", "Phone")
        f.add("email", "Email")
        f.add("account_no", "Account No")
        f.add("terms", "Terms", "combo", source=lambda: self.app.names("terms"))
        f.add("open_balance", "Opening Balance", "amount")
        f.add("open_balance_date", "Opening Balance Date", "date", default="")
        f.add("notes", "Notes", span=2, width=80)

    def collect(self):
        return self.f.values()

    def clear(self):
        self.f.clear()


class AccountTab(BaseTab):
    kind = "account"
    title = "New Account (Chart of Accounts)"
    hint = "Sub-account: choose a Parent account of the same type. Account Number max 7 characters."

    def build(self):
        f = self.f = Form(self.body, columns=2)
        f.pack(fill="x", anchor="w")
        f.add("type", "Account Type", "choice", values=[ACCOUNT_TYPE_LABELS[t] for t in ACCOUNT_TYPES],
              default="Expense", required=True)
        f.add("name", "Account Name", required=True)
        f.add("parent", "Sub-account of (Parent)", "combo", source=lambda: self.app.names("accounts"))
        f.add("number", "Account Number")
        f.add("desc", "Description")
        f.add("bank_no", "Bank Account No (bank accounts)")
        f.add("open_balance", "Opening Balance", "amount")
        f.add("open_balance_date", "Opening Balance Date", "date", default="")

    def collect(self):
        return self.f.values()

    def clear(self):
        self.f.clear(keep=("type",))


# ------------------------------------------------------------------ transactions

def purchase_cols(app):
    def target_source(row):
        return app.names("items") if row.get("kind") == "Item" else app.names("accounts")
    return [
        dict(key="kind", label="Type", kind="choice", values=["Expense", "Item"], width=8),
        dict(key="target", label="Account / Item", kind="combo", source=target_source, width=30, weight=2),
        dict(key="desc", label="Description / Memo", width=26, weight=2),
        dict(key="qty", label="Qty", kind="qty", width=7),
        dict(key="rate", label="Rate", kind="amount", width=10),
        dict(key="amount", label="Amount", kind="amount", width=13),
        dict(key="cls", label="Class", kind="combo", source=lambda r: app.names("classes"), width=12),
        dict(key="customer", label="Customer:Job", kind="combo", source=lambda r: app.names("customers"),
             width=16),
    ]


class BillTab(BaseTab):
    kind = "bill"
    title = "Enter Bill"
    hint = ("Type = Expense (pick an account) or Item (pick an item; Qty x Rate fills Amount). "
            "Dates DD/MM/YYYY.")
    keep = ("date",)

    def build(self):
        f = self.f = Form(self.body, columns=3)
        f.pack(fill="x", anchor="w")
        f.add("vendor", "Vendor", "combo", source=lambda: self.app.names("vendors"), width=32, required=True)
        f.add("date", "Bill Date", "date", required=True)
        f.add("ref", "Ref No (invoice no)", width=20)
        f.add("terms", "Terms", "combo", source=lambda: self.app.names("terms"), width=32)
        f.add("due_date", "Due Date", "date", default="")
        f.add("memo", "Memo", width=20)
        ttk.Label(self.body, text="Lines", style="Section.TLabel").pack(anchor="w", pady=(10, 2))
        self.grid = LineGrid(self.body, purchase_cols(self.app), rows=6)
        self.grid.pack(fill="both", expand=True)

    def collect(self):
        raw = self.f.values()
        raw["lines"] = self.grid.lines()
        return raw

    def clear(self):
        self.f.clear(keep=self.keep)
        self.grid.clear()


class InvoiceTab(BaseTab):
    kind = "invoice"
    title = "Create Invoice"
    hint = ("Bank discount claim: Customer:Job = the bank, Class = the store, Item = Bank Discount "
            "Receivable, Amount = the bank's share. Lines without a class use the invoice Class. "
            "Class and Item are remembered for the next invoice. Invoice No is saved exactly as typed; leave it blank and QuickBooks gives its own next number.")

    def build(self):
        st = self.app.settings
        f = self.f = Form(self.body, columns=3)
        f.pack(fill="x", anchor="w")
        f.add("customer", "Customer:Job", "combo", source=lambda: self.app.names("customers"), width=32,
              required=True)
        f.add("date", "Invoice Date", "date", required=True)
        f.add("ref", "Invoice No", width=16)
        f.add("cls", "Class", "combo", source=lambda: self.app.names("classes"), width=32,
              default=st.get("invoice_class", "Store 1"))
        f.add("terms", "Terms", "combo", source=lambda: self.app.names("terms"), width=16)
        f.add("due_date", "Due Date", "date", default="")
        f.add("memo", "Memo", width=32)
        f.add("po", "P.O. No", width=16)
        ttk.Label(self.body, text="Lines", style="Section.TLabel").pack(anchor="w", pady=(10, 2))
        cols = [
            dict(key="item", label="Item", kind="combo", source=lambda r: self.app.names("items"), width=32, weight=2),
            dict(key="desc", label="Description", width=34, weight=2),
            dict(key="qty", label="Qty", kind="qty", width=7),
            dict(key="rate", label="Rate", kind="amount", width=11),
            dict(key="amount", label="Amount", kind="amount", width=14),
            dict(key="cls", label="Class (blank = invoice class)", kind="combo",
                 source=lambda r: self.app.names("classes"), width=16),
        ]
        self.grid = LineGrid(self.body, cols, rows=4)
        self.grid.pack(fill="both", expand=True)
        self._prefill()

    def _prefill(self):
        item = self.app.settings.get("invoice_item", "Bank Discount Receivable")
        if item and self.grid.rows:
            self.grid.set_row(self.grid.rows[0], {"item": item})

    def collect(self):
        raw = self.f.values()
        raw["lines"] = self.grid.lines()
        return raw

    def clear(self):
        self.f.clear(keep=("date", "cls", "terms"))
        self.grid.clear()
        self._prefill()

    def after_saved(self, record, new_id):
        st = self.app.settings
        if record.get("cls"):
            st["invoice_class"] = record["cls"]
        if record["lines"]:
            st["invoice_item"] = record["lines"][0]["item"]
        from .. import storage
        storage.save_settings(st)
        self.clear()


class ChequeTab(BillTab):
    kind = "cheque"
    title = "Write Cheque"
    hint = ("Direct payment from a bank account (not paying a bill; for bills use Pay Bills). "
            "Tick 'To be printed' to leave the cheque number for QuickBooks to print.")
    keep = ("date", "bank")

    def build(self):
        f = self.f = Form(self.body, columns=3)
        f.pack(fill="x", anchor="w")
        f.add("bank", "Bank Account", "combo", width=32, required=True,
              source=lambda: self.app.accounts_of("Bank", "CreditCard"))
        f.add("date", "Date", "date", required=True)
        f.add("ref", "Cheque No", width=20)
        f.add("payee", "Pay to the Order of", "combo", source=lambda: self.app.names("payees"), width=32)
        f.add("to_print", "To be printed", "check")
        f.add("memo", "Memo", width=20)
        ttk.Label(self.body, text="Lines", style="Section.TLabel").pack(anchor="w", pady=(10, 2))
        self.grid = LineGrid(self.body, purchase_cols(self.app), rows=6)
        self.grid.pack(fill="both", expand=True)


class JournalTab(BaseTab):
    kind = "journal"
    title = "Journal Entry"
    hint = "Each line: Debit OR Credit. Total debits must equal total credits. A/P and A/R lines need a Name."

    def build(self):
        f = self.f = Form(self.body, columns=3)
        f.pack(fill="x", anchor="w")
        f.add("date", "Date", "date", required=True)
        f.add("ref", "Entry No", width=14)
        f.add("adjusting", "Adjusting entry", "check")
        ttk.Label(self.body, text="Lines", style="Section.TLabel").pack(anchor="w", pady=(10, 2))
        cols = [
            dict(key="account", label="Account", kind="combo", source=lambda r: self.app.names("accounts"),
                 width=32, weight=2),
            dict(key="debit", label="Debit", kind="amount", width=13),
            dict(key="credit", label="Credit", kind="amount", width=13),
            dict(key="memo", label="Memo", width=30, weight=2),
            dict(key="name", label="Name", kind="combo", source=lambda r: self.app.names("payees"), width=22),
            dict(key="cls", label="Class", kind="combo", source=lambda r: self.app.names("classes"), width=12),
        ]
        self.grid = LineGrid(self.body, cols, rows=6, on_change=self.totals)
        self.grid.pack(fill="both", expand=True)
        self.totals()

    def totals(self):
        d, c = self.grid.sums("debit"), self.grid.sums("credit")
        diff = d - c
        self.grid.total_var.set(f"Debit {money(d)}    Credit {money(c)}"
                                + ("    ✓ balanced" if diff == 0 and d else
                                   f"    Difference {money(diff)}" if diff else ""))

    def collect(self):
        raw = self.f.values()
        raw["lines"] = self.grid.lines()
        return raw

    def clear(self):
        self.f.clear(keep=("date",))
        self.grid.clear()


class DepositTab(BaseTab):
    kind = "deposit"
    title = "Make Deposit"
    hint = ("Money into a bank account. 'From Account' is where the money comes from "
            "(e.g. Bank Discount Receivable, Sales, Undeposited Funds).")

    def build(self):
        f = self.f = Form(self.body, columns=3)
        f.pack(fill="x", anchor="w")
        f.add("account", "Deposit To", "combo", width=32, required=True,
              source=lambda: self.app.accounts_of("Bank", "OtherCurrentAsset"))
        f.add("date", "Date", "date", required=True)
        f.add("memo", "Memo", width=26)
        ttk.Label(self.body, text="Lines", style="Section.TLabel").pack(anchor="w", pady=(10, 2))
        cols = [
            dict(key="from_name", label="Received From", kind="combo",
                 source=lambda r: self.app.names("payees"), width=22),
            dict(key="from_account", label="From Account", kind="combo",
                 source=lambda r: self.app.names("accounts"), width=30, weight=2),
            dict(key="memo", label="Memo", width=26, weight=2),
            dict(key="cheque_no", label="Cheque No", width=10),
            dict(key="cls", label="Class", kind="combo", source=lambda r: self.app.names("classes"), width=12),
            dict(key="amount", label="Amount", kind="amount", width=13),
        ]
        self.grid = LineGrid(self.body, cols, rows=5)
        self.grid.pack(fill="both", expand=True)

    def collect(self):
        raw = self.f.values()
        raw["lines"] = self.grid.lines()
        return raw

    def clear(self):
        self.f.clear(keep=("date", "account"))
        self.grid.clear()


class TransferTab(BaseTab):
    kind = "transfer"
    title = "Transfer Funds"
    hint = "Move money between two accounts (e.g. bank to petty cash, or bank to bank)."

    def build(self):
        f = self.f = Form(self.body, columns=2)
        f.pack(fill="x", anchor="w")
        f.add("date", "Date", "date", required=True)
        f.add("amount", "Amount", "amount", required=True)
        f.add("from_account", "Transfer From", "combo", required=True,
              source=lambda: self.app.accounts_of("Bank", "OtherCurrentAsset", "CreditCard"))
        f.add("to_account", "Transfer To", "combo", required=True,
              source=lambda: self.app.accounts_of("Bank", "OtherCurrentAsset", "CreditCard"))
        f.add("memo", "Memo")
        f.add("cls", "Class", "combo", source=lambda: self.app.names("classes"))

    def collect(self):
        return self.f.values()

    def clear(self):
        self.f.clear(keep=("date",))


class PayBillsTab(BaseTab):
    kind = "paybill"
    title = "Pay Bills"
    hint = ("1) Choose the vendor and click 'Show unpaid bills'.  2) Tick the bills to pay "
            "(double-click a row). To pay part of a bill, select it and change 'Amount to pay'. "
            "For WHT, select the bill and click 'Set Discount'.  3) Fill bank, cheque no and date, then Save.")

    def build(self):
        top = ttk.Frame(self.body)
        top.pack(fill="x")
        f = self.vf = Form(top, columns=1)
        f.pack(side="left")
        f.add("vendor", "Vendor", "combo", source=lambda: self.app.names("vendors"), width=40, required=True)
        ttk.Button(top, text="Show unpaid bills", command=self.load_bills).pack(side="left", padx=10)
        cols = ("pay", "date", "ref", "due", "amount", "open", "disc", "topay", "memo")
        heads = ("Pay", "Bill Date", "Ref No", "Due Date", "Bill Amount", "Unpaid", "Discount", "Amount to pay", "Memo")
        widths = (40, 90, 120, 90, 110, 110, 100, 120, 220)
        self.tree = ttk.Treeview(self.body, columns=cols, show="headings", height=10, selectmode="browse")
        for c, h, w in zip(cols, heads, widths):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="e" if c in ("amount", "open", "disc", "topay") else
                             "center" if c == "pay" else "w", stretch=c == "memo")
        self.tree.pack(fill="both", expand=True, pady=(8, 4))
        self.tree.bind("<Double-1>", lambda e: self.toggle())
        self.tree.bind("<space>", lambda e: self.toggle())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.show_selected())
        row = ttk.Frame(self.body)
        row.pack(fill="x")
        ttk.Button(row, text="Pay all", command=lambda: self.mark_all(True)).pack(side="left")
        ttk.Button(row, text="Clear selection", command=lambda: self.mark_all(False)).pack(side="left", padx=6)
        ttk.Label(row, text="   Amount to pay for selected bill:").pack(side="left")
        self.amt = ttk.Entry(row, width=14, justify="right")
        self.amt.pack(side="left", padx=4)
        self.amt.bind("<Return>", lambda e: self.set_amount())
        ttk.Button(row, text="Set", command=self.set_amount).pack(side="left")
        ttk.Button(row, text="Set Discount", command=self.set_discount).pack(side="left", padx=(12, 0))
        self.total_var = tk.StringVar(value="Total payment: 0.00")
        ttk.Label(row, textvariable=self.total_var, font=("Segoe UI", 10, "bold")).pack(side="right")
        ttk.Separator(self.body).pack(fill="x", pady=8)
        f = self.f = Form(self.body, columns=3)
        f.pack(fill="x", anchor="w")
        f.add("bank", "Pay from Bank", "combo", width=32, required=True,
              source=lambda: self.app.accounts_of("Bank"))
        f.add("date", "Payment Date", "date", required=True)
        f.add("ref", "Cheque No", width=16)
        f.add("memo", "Memo", width=32)
        f.add("to_print", "To be printed", "check")
        self.bills = {}       # iid -> bill dict (+ "pay": Decimal or None)
        self.loaded_vendor = None

    def load_bills(self):
        vendor = self.vf.get("vendor")
        if not vendor:
            messagebox.showinfo("Pay Bills", "Choose a vendor first.", parent=self)
            return
        if not self.app.require_lists():
            return
        exact = self.app.lists.match("vendors", vendor) if self.app.lists else vendor
        if self.app.lists and not exact:
            messagebox.showerror("Pay Bills", f"Vendor '{vendor}' not found in QuickBooks.", parent=self)
            return
        self.vf.set("vendor", exact)

        def done(bills):
            self.loaded_vendor = exact
            self.tree.delete(*self.tree.get_children())
            self.bills = {}
            for b in bills:
                iid = self.tree.insert("", "end", values=(
                    "", show_date(b["date"]), b["ref"], show_date(b["due_date"]),
                    money(Decimal(b["amount_due"])), money(Decimal(b["open_amount"])), "", "", b["memo"]))
                self.bills[iid] = {**b, "pay": None, "disc": None, "disc_acct": None}
            self.update_total()
            if not bills:
                self.app.notify("Pay Bills", f"No unpaid bills for {exact}.")

        self.app.fetch_open_bills(exact, done)

    def _redraw(self, iid):
        b = self.bills[iid]
        vals = list(self.tree.item(iid, "values"))
        vals[0] = "✓" if b["pay"] else ""
        vals[6] = money(b["disc"]) if b.get("disc") else ""
        vals[7] = money(b["pay"]) if b["pay"] else ""
        self.tree.item(iid, values=vals)

    def toggle(self):
        sel = self.tree.selection()
        if not sel:
            return
        b = self.bills[sel[0]]
        b["pay"] = None if b["pay"] else Decimal(b["open_amount"]) - (b.get("disc") or 0)
        self._redraw(sel[0])
        self.show_selected()
        self.update_total()

    def mark_all(self, on):
        for iid, b in self.bills.items():
            b["pay"] = Decimal(b["open_amount"]) - (b.get("disc") or 0) if on else None
            self._redraw(iid)
        self.update_total()

    def show_selected(self):
        sel = self.tree.selection()
        self.amt.delete(0, "end")
        if sel and self.bills[sel[0]]["pay"]:
            self.amt.insert(0, f"{self.bills[sel[0]]['pay']:.2f}")

    def set_amount(self):
        sel = self.tree.selection()
        if not sel:
            return
        b = self.bills[sel[0]]
        try:
            v = parse_amount(self.amt.get(), "Amount to pay", required=False)
        except InputError as e:
            messagebox.showerror("Pay Bills", str(e), parent=self)
            return
        if v and v + (b.get("disc") or 0) > Decimal(b["open_amount"]):
            messagebox.showerror("Pay Bills", f"This bill has only {money(Decimal(b['open_amount']))} "
                                 "unpaid (including the discount).", parent=self)
            return
        b["pay"] = v
        self._redraw(sel[0])
        self.update_total()

    def set_discount(self):
        """Like QuickBooks' Set Discount: discount amount + discount account for the selected bill.
        The amount to pay becomes the bill's unpaid amount less the discount."""
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Pay Bills", "Select a bill first.", parent=self)
            return
        b = self.bills[sel[0]]
        default_acct = b.get("disc_acct") or self.app.settings.get("discount_account", "Withholding Tax Payable")
        dlg = DiscountDialog(self, b, default_acct, self.app.names("accounts"))
        self.wait_window(dlg)
        if dlg.result is None:
            return
        disc, acct = dlg.result
        if disc and acct:
            self.app.settings["discount_account"] = acct
            from .. import storage
            storage.save_settings(self.app.settings)
        b["disc"] = disc or None
        b["disc_acct"] = acct if disc else None
        b["pay"] = Decimal(b["open_amount"]) - (disc or 0)
        self._redraw(sel[0])
        self.show_selected()
        self.update_total()

    def update_total(self):
        tot = sum((b["pay"] or 0 for b in self.bills.values()), Decimal(0))
        disc = sum((b.get("disc") or 0 for b in self.bills.values() if b["pay"]), Decimal(0))
        n = sum(1 for b in self.bills.values() if b["pay"])
        self.total_var.set(f"{n} bill(s)   Discount: {money(disc)}   Cheque amount: {money(tot)}")

    def collect(self):
        raw = self.f.values()
        raw["vendor"] = self.loaded_vendor or self.vf.get("vendor")
        if self.loaded_vendor and self.vf.get("vendor").lower() != self.loaded_vendor.lower():
            raw["bills"] = []
        else:
            raw["bills"] = [{"txn_id": b["txn_id"], "bill_ref": b["ref"], "amount": b["pay"],
                             "discount": b.get("disc"), "discount_account": b.get("disc_acct")}
                            for b in self.bills.values() if b["pay"]]
        return raw

    def clear(self):
        self.f.clear(keep=("date", "bank"))
        self.tree.delete(*self.tree.get_children())
        self.bills = {}
        self.loaded_vendor = None
        self.vf.clear()
        self.update_total()

    def after_saved(self, record, new_id):
        vendor = record["vendor"]
        self.clear()
        self.vf.set("vendor", vendor)
        self.load_bills()


class DiscountDialog(tk.Toplevel):
    """Set Discount for one bill: Amount of Discount + Discount Account."""

    def __init__(self, master, bill, default_acct, accounts):
        super().__init__(master)
        self.title("Set Discount")
        self.transient(master)
        self.resizable(False, False)
        self.result = None
        self.bill = bill
        frm = ttk.Frame(self, padding=14)
        frm.pack(fill="both")
        ttk.Label(frm, text=f"Bill Ref No {bill['ref']}    Amount Due {money(Decimal(bill['amount_due']))}"
                  ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frm, text="Amount of Discount").grid(row=1, column=0, sticky="w")
        self.amt = ttk.Entry(frm, width=16, justify="right")
        self.amt.grid(row=1, column=1, sticky="w", pady=3)
        if bill.get("disc"):
            self.amt.insert(0, f"{bill['disc']:.2f}")
        ttk.Label(frm, text="Discount Account").grid(row=2, column=0, sticky="w")
        self.acct = ttk.Combobox(frm, width=36, values=accounts)
        self.acct.set(default_acct or "")
        self.acct.grid(row=2, column=1, sticky="w", pady=3)
        bar = ttk.Frame(frm)
        bar.grid(row=3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(bar, text="Clear", command=self.clear).pack(side="left", padx=4)
        ttk.Button(bar, text="Cancel", command=self.destroy).pack(side="left", padx=4)
        ttk.Button(bar, text="Done", style="Accent.TButton", command=self.ok).pack(side="left", padx=4)
        self.amt.focus_set()
        self.bind("<Return>", lambda e: self.ok())
        self.grab_set()

    def clear(self):
        self.result = (None, None)
        self.destroy()

    def ok(self):
        try:
            v = parse_amount(self.amt.get(), "Amount of Discount", required=False)
        except InputError as e:
            messagebox.showerror("Set Discount", str(e), parent=self)
            return
        acct = self.acct.get().strip()
        if v and not acct:
            messagebox.showerror("Set Discount", "Choose the Discount Account "
                                 "(e.g. Withholding Tax Payable).", parent=self)
            return
        if v and v >= Decimal(self.bill["open_amount"]):
            messagebox.showerror("Set Discount", "The discount must be less than the unpaid amount.", parent=self)
            return
        self.result = (v, acct)
        self.destroy()

"""Turn raw input (from a screen or an Excel row) into a checked record.

Every kind of record has a ``check_<kind>(raw, lists)`` function. It returns a clean
record (dates in YYYY-MM-DD, amounts as Decimal, names matched to the exact spelling
used in QuickBooks) or raises InputError listing every problem found.
If ``lists`` is None (lists not loaded yet) the name checks are skipped and
QuickBooks itself will reject unknown names.
"""
from decimal import Decimal

from .util import (InputError, clean, parse_amount, parse_bool, parse_date, parse_qty,
                   split_name, is_blank)

KINDS = {
    "item": "Item",
    "vendor": "Vendor",
    "customer": "Customer",
    "account": "Account",
    "invoice": "Invoice",
    "bill": "Bill",
    "paybill": "Bill Payment",
    "cheque": "Cheque",
    "journal": "Journal Entry",
    "deposit": "Deposit",
    "transfer": "Transfer",
}

ITEM_TYPES = {
    "inventory": "Inventory", "inventorypart": "Inventory", "inv": "Inventory",
    "noninventory": "NonInventory", "noninventorypart": "NonInventory", "noninv": "NonInventory",
    "service": "Service",
    "othercharge": "OtherCharge", "charge": "OtherCharge",
}
ITEM_TYPE_LABELS = {"Inventory": "Inventory Part", "NonInventory": "Non-inventory Part",
                    "Service": "Service", "OtherCharge": "Other Charge"}

ACCOUNT_TYPES = ["Bank", "AccountsReceivable", "OtherCurrentAsset", "FixedAsset", "OtherAsset",
                 "AccountsPayable", "CreditCard", "OtherCurrentLiability", "LongTermLiability",
                 "Equity", "Income", "CostOfGoodsSold", "Expense", "OtherIncome", "OtherExpense",
                 "NonPosting"]
ACCOUNT_TYPE_LABELS = {
    "Bank": "Bank", "AccountsReceivable": "Accounts Receivable",
    "OtherCurrentAsset": "Other Current Asset", "FixedAsset": "Fixed Asset",
    "OtherAsset": "Other Asset", "AccountsPayable": "Accounts Payable",
    "CreditCard": "Credit Card", "OtherCurrentLiability": "Other Current Liability",
    "LongTermLiability": "Long Term Liability", "Equity": "Equity", "Income": "Income",
    "CostOfGoodsSold": "Cost of Goods Sold", "Expense": "Expense",
    "OtherIncome": "Other Income", "OtherExpense": "Other Expense", "NonPosting": "Non-Posting",
}

# qbXML 13.0 maximum lengths
MAX = {
    "item_name": 31, "account_name": 31, "vendor_name": 41, "customer_name": 41,
    "company": 41, "addr": 41, "city": 31, "phone": 21, "email": 1023, "contact": 41,
    "print_as": 41, "vendor_acct": 99, "ntn": 15, "acct_number": 7, "bank_no": 25,
    "acct_desc": 200, "bill_ref": 20, "check_ref": 11, "inv_ref": 11, "po": 25, "je_ref": 11, "billpay_ref": 11,
    "dep_check_no": 11, "memo": 4095, "desc": 4095, "notes": 4095,
}


def _key(s):
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


class Problems:
    def __init__(self):
        self.items = []

    def add(self, msg):
        self.items.append(msg)

    def run(self, fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except InputError as e:
            self.add(str(e))
            return None

    def text(self, field, value, max_len=None, required=False):
        v = clean(value)
        if v is None:
            if required:
                self.add(f"{field} is required")
            return None
        if max_len and len(v) > max_len:
            self.add(f"{field} '{v}' is too long ({len(v)} characters, QuickBooks allows {max_len})")
        return v

    def raise_if_any(self):
        if self.items:
            raise InputError("\n".join(self.items))


class Lists:
    """Names loaded from QuickBooks, used for drop-downs and checking."""
    CATS = ("accounts", "vendors", "customers", "employees", "othernames", "items",
            "classes", "terms")

    def __init__(self, company="", file_path=""):
        self.company = company
        self.file_path = file_path
        self.accounts = {}    # FullName -> AccountType
        self.items = {}       # FullName -> item type label
        self.vendors = []
        self.customers = []
        self.employees = []
        self.othernames = []
        self.classes = []
        self.terms = []
        self._idx = {}

    def names(self, cat):
        v = getattr(self, cat)
        return sorted(v.keys() if isinstance(v, dict) else v, key=str.lower)

    def payees(self):
        return sorted(set(self.vendors) | set(self.customers) | set(self.employees)
                      | set(self.othernames), key=str.lower)

    def accounts_of(self, *types):
        return sorted([n for n, t in self.accounts.items() if t in types], key=str.lower)

    def reindex(self):
        self._idx = {}
        for cat in self.CATS:
            v = getattr(self, cat)
            self._idx[cat] = {n.lower(): n for n in (v.keys() if isinstance(v, dict) else v)}
        self._idx["payees"] = {}
        for cat in ("vendors", "customers", "employees", "othernames"):
            self._idx["payees"].update(self._idx[cat])

    def match(self, cat, name):
        if not self._idx:
            self.reindex()
        return self._idx.get(cat, {}).get(str(name).strip().lower())

    def add_name(self, cat, name, extra=None):
        v = getattr(self, cat)
        if isinstance(v, dict):
            v[name] = extra
        elif name not in v:
            v.append(name)
        self.reindex()

    def summary(self):
        return (f"{len(self.accounts)} accounts, {len(self.items)} items, "
                f"{len(self.vendors)} vendors, {len(self.customers)} customers")


LABELS = {"accounts": "Account", "vendors": "Vendor", "customers": "Customer",
          "items": "Item", "classes": "Class", "terms": "Terms", "payees": "Name"}


def _ref(p, lists, cat, field, value, required=False):
    """Check a name exists in QuickBooks and return its exact spelling."""
    v = clean(value)
    if v is None:
        if required:
            p.add(f"{field} is required")
        return None
    if lists is None:
        return v
    exact = lists.match(cat, v)
    if exact is None:
        p.add(f"{field}: {LABELS.get(cat, cat)} '{v}' not found in QuickBooks"
              + (" (check spelling, or add it first)"))
        return v
    return exact


def _account_type(p, value):
    v = clean(value)
    if v is None:
        p.add("Account Type is required")
        return None
    k = _key(v)
    for t in ACCOUNT_TYPES:
        if _key(t) == k or _key(ACCOUNT_TYPE_LABELS[t]) == k:
            return t
    aliases = {"cogs": "CostOfGoodsSold", "ar": "AccountsReceivable", "ap": "AccountsPayable",
               "currentasset": "OtherCurrentAsset", "currentliability": "OtherCurrentLiability",
               "liability": "OtherCurrentLiability", "asset": "OtherCurrentAsset"}
    if k in aliases:
        return aliases[k]
    p.add(f"Account Type '{v}' is not valid. Use one of: "
          + ", ".join(ACCOUNT_TYPE_LABELS[t] for t in ACCOUNT_TYPES))
    return None


# ---------------------------------------------------------------- lists

def check_item(raw, lists=None):
    p = Problems()
    t = clean(raw.get("type"))
    itype = ITEM_TYPES.get(_key(t)) if t else None
    if itype is None:
        p.add(f"Item Type '{t or ''}' is not valid. Use Inventory, Non-inventory, Service or Other Charge")
    name, parent = split_name(raw.get("name"), raw.get("parent"))
    name = p.text("Item Name", name, MAX["item_name"], required=True)
    if name and ":" in name:
        p.add("Item Name cannot contain ':' (use the Parent column for sub-items)")
    parent = _ref(p, lists, "items", "Parent Item", parent)
    if lists is not None and name:
        full = f"{parent}:{name}" if parent else name
        if lists.match("items", full):
            p.add(f"Item '{full}' already exists in QuickBooks")
    r = {
        "kind": "item", "type": itype, "name": name, "parent": parent,
        "inactive": parse_bool(raw.get("inactive")),
        "sales_desc": p.text("Sales Description", raw.get("sales_desc"), MAX["desc"]),
        "price": p.run(parse_amount, raw.get("price"), "Sales Price", required=False, allow_zero=True),
        "income_account": _ref(p, lists, "accounts", "Income Account", raw.get("income_account")),
        "purchase_desc": p.text("Purchase Description", raw.get("purchase_desc"), MAX["desc"]),
        "cost": p.run(parse_amount, raw.get("cost"), "Cost", required=False, allow_zero=True),
        "expense_account": _ref(p, lists, "accounts", "Expense / COGS Account", raw.get("expense_account")),
        "asset_account": _ref(p, lists, "accounts", "Inventory Asset Account", raw.get("asset_account")),
        "pref_vendor": _ref(p, lists, "vendors", "Preferred Vendor", raw.get("pref_vendor")),
        "reorder_point": p.run(parse_qty, raw.get("reorder_point"), "Reorder Point"),
        "qty_on_hand": p.run(parse_qty, raw.get("qty_on_hand"), "Qty On Hand"),
        "total_value": p.run(parse_amount, raw.get("total_value"), "Total Value", required=False, allow_zero=True),
        "as_of": p.run(parse_date, raw.get("as_of"), "As Of Date", required=False),
    }
    if itype == "Inventory":
        for f, label in (("income_account", "Income Account"), ("expense_account", "COGS Account"),
                         ("asset_account", "Inventory Asset Account")):
            if not r[f]:
                p.add(f"{label} is required for an Inventory item")
        if r["qty_on_hand"] and not r["as_of"]:
            p.add("As Of Date is required when Qty On Hand is given")
    elif itype:
        r["both"] = bool(r["expense_account"] or r["purchase_desc"] or r["cost"] is not None
                         or r["pref_vendor"])
        if r["both"]:
            if not r["income_account"]:
                p.add("Income Account is required (purchase details were given, so both "
                      "Income and Expense accounts are needed)")
            if not r["expense_account"]:
                p.add("Expense Account is required when purchase details are given")
        elif not r["income_account"]:
            p.add("Account is required (Income or Expense account for this item)")
    p.raise_if_any()
    return r


def check_vendor(raw, lists=None):
    p = Problems()
    name = p.text("Vendor Name", raw.get("name"), MAX["vendor_name"], required=True)
    if lists is not None and name and lists.match("payees", name):
        p.add(f"Name '{name}' already exists in QuickBooks (vendor, customer, employee or other name)")
    r = {
        "kind": "vendor", "name": name,
        "company": p.text("Company Name", raw.get("company"), MAX["company"]),
        "addr1": p.text("Address 1", raw.get("addr1"), MAX["addr"]),
        "addr2": p.text("Address 2", raw.get("addr2"), MAX["addr"]),
        "city": p.text("City", raw.get("city"), MAX["city"]),
        "phone": p.text("Phone", raw.get("phone"), MAX["phone"]),
        "email": p.text("Email", raw.get("email"), MAX["email"]),
        "contact": p.text("Contact", raw.get("contact"), MAX["contact"]),
        "print_as": p.text("Print on Cheque As", raw.get("print_as"), MAX["print_as"]),
        "account_no": p.text("Account No", raw.get("account_no"), MAX["vendor_acct"]),
        "ntn": p.text("NTN / Tax ID", raw.get("ntn"), MAX["ntn"]),
        "terms": _ref(p, lists, "terms", "Terms", raw.get("terms")),
        "open_balance": p.run(parse_amount, raw.get("open_balance"), "Opening Balance",
                              required=False, allow_negative=True),
        "open_balance_date": p.run(parse_date, raw.get("open_balance_date"), "Opening Balance Date",
                                   required=False),
        "notes": p.text("Notes", raw.get("notes"), MAX["notes"]),
    }
    if r["open_balance"] and not r["open_balance_date"]:
        p.add("Opening Balance Date is required when an Opening Balance is given")
    p.raise_if_any()
    return r


def check_customer(raw, lists=None):
    p = Problems()
    name, parent = split_name(raw.get("name"), raw.get("parent"))
    name = p.text("Customer Name", name, MAX["customer_name"], required=True)
    parent = _ref(p, lists, "customers", "Parent Customer", parent)
    if lists is not None and name:
        full = f"{parent}:{name}" if parent else name
        if lists.match("customers", full) or (not parent and lists.match("payees", name)):
            p.add(f"Name '{full}' already exists in QuickBooks")
    r = {
        "kind": "customer", "name": name, "parent": parent,
        "company": p.text("Company Name", raw.get("company"), MAX["company"]),
        "addr1": p.text("Address 1", raw.get("addr1"), MAX["addr"]),
        "addr2": p.text("Address 2", raw.get("addr2"), MAX["addr"]),
        "city": p.text("City", raw.get("city"), MAX["city"]),
        "phone": p.text("Phone", raw.get("phone"), MAX["phone"]),
        "email": p.text("Email", raw.get("email"), MAX["email"]),
        "contact": p.text("Contact", raw.get("contact"), MAX["contact"]),
        "terms": _ref(p, lists, "terms", "Terms", raw.get("terms")),
        "account_no": p.text("Account No", raw.get("account_no"), MAX["vendor_acct"]),
        "open_balance": p.run(parse_amount, raw.get("open_balance"), "Opening Balance",
                              required=False, allow_negative=True),
        "open_balance_date": p.run(parse_date, raw.get("open_balance_date"), "Opening Balance Date",
                                   required=False),
        "notes": p.text("Notes", raw.get("notes"), MAX["notes"]),
    }
    if r["open_balance"] and not r["open_balance_date"]:
        p.add("Opening Balance Date is required when an Opening Balance is given")
    p.raise_if_any()
    return r


def check_account(raw, lists=None):
    p = Problems()
    name, parent = split_name(raw.get("name"), raw.get("parent"))
    name = p.text("Account Name", name, MAX["account_name"], required=True)
    parent = _ref(p, lists, "accounts", "Parent Account", parent)
    atype = _account_type(p, raw.get("type"))
    if lists is not None and name:
        full = f"{parent}:{name}" if parent else name
        if lists.match("accounts", full):
            p.add(f"Account '{full}' already exists in QuickBooks")
        if parent and atype and lists.accounts.get(lists.match("accounts", parent) or "") not in (None, atype):
            p.add(f"A sub-account must have the same type as its parent '{parent}' "
                  f"({ACCOUNT_TYPE_LABELS.get(lists.accounts.get(lists.match('accounts', parent)), '')})")
    r = {
        "kind": "account", "name": name, "parent": parent, "type": atype,
        "number": p.text("Account Number", raw.get("number"), MAX["acct_number"]),
        "desc": p.text("Description", raw.get("desc"), MAX["acct_desc"]),
        "bank_no": p.text("Bank Account No", raw.get("bank_no"), MAX["bank_no"]),
        "open_balance": p.run(parse_amount, raw.get("open_balance"), "Opening Balance",
                              required=False, allow_negative=True),
        "open_balance_date": p.run(parse_date, raw.get("open_balance_date"), "Opening Balance Date",
                                   required=False),
    }
    if r["open_balance"] and not r["open_balance_date"]:
        p.add("Opening Balance Date is required when an Opening Balance is given")
    p.raise_if_any()
    return r


# ---------------------------------------------------------------- transactions

def _purchase_lines(p, lists, raw_lines):
    """Expense / item lines for bills and cheques."""
    out = []
    for i, ln in enumerate(raw_lines or [], 1):
        if all(is_blank(ln.get(k)) for k in ("target", "amount", "qty", "rate", "desc")):
            continue
        tag = f"Line {i}: "
        kind = (clean(ln.get("kind")) or "Expense").lower()
        kind = "item" if kind.startswith("item") else "expense"
        r = {"kind": kind}
        if kind == "expense":
            r["account"] = _ref(p, lists, "accounts", tag + "Account", ln.get("target"), required=True)
            r["amount"] = p.run(parse_amount, ln.get("amount"), tag + "Amount")
        else:
            r["item"] = _ref(p, lists, "items", tag + "Item", ln.get("target"), required=True)
            r["qty"] = p.run(parse_qty, ln.get("qty"), tag + "Qty")
            r["rate"] = p.run(parse_amount, ln.get("rate"), tag + "Rate", required=False, allow_zero=True)
            amt = p.run(parse_amount, ln.get("amount"), tag + "Amount", required=False)
            if r["qty"] is not None and r["rate"] is not None:
                calc = (r["qty"] * r["rate"]).quantize(Decimal("0.01"))
                if amt is not None and abs(amt - calc) > Decimal("0.05"):
                    p.add(f"{tag}Qty x Rate = {calc} but Amount is {amt}")
                amt = calc
            if amt is None:
                p.add(f"{tag}Amount is required (or Qty and Rate)")
            r["amount"] = amt
        r["desc"] = p.text(tag + "Description/Memo", ln.get("desc"), MAX["desc"])
        r["cls"] = _ref(p, lists, "classes", tag + "Class", ln.get("cls"))
        r["customer"] = _ref(p, lists, "customers", tag + "Customer:Job", ln.get("customer"))
        out.append(r)
    if not out:
        p.add("At least one line (account or item with an amount) is required")
    return out


def _total(lines, key="amount"):
    return sum((ln.get(key) or Decimal(0) for ln in lines), Decimal(0))


def check_bill(raw, lists=None):
    p = Problems()
    r = {
        "kind": "bill",
        "vendor": _ref(p, lists, "vendors", "Vendor", raw.get("vendor"), required=True),
        "date": p.run(parse_date, raw.get("date"), "Bill Date"),
        "due_date": p.run(parse_date, raw.get("due_date"), "Due Date", required=False),
        "ref": p.text("Ref No", raw.get("ref"), MAX["bill_ref"]),
        "terms": _ref(p, lists, "terms", "Terms", raw.get("terms")),
        "memo": p.text("Memo", raw.get("memo"), MAX["memo"]),
    }
    r["lines"] = _purchase_lines(p, lists, raw.get("lines"))
    p.raise_if_any()
    r["total"] = _total(r["lines"])
    return r


def _strip_arc(v):
    """Invoice numbers must not contain the word ARC: 'ARC-1023' / 'arc 1023' -> '1023'."""
    import re
    s = clean(v)
    if s is None:
        return None
    s = re.sub(r"(?<![a-z])arc(?![a-z])", "", s, flags=re.I)
    s = re.sub(r"^[\s\-_/.#:]+|[\s\-_/.#:]+$", "", s)
    s = re.sub(r"[\s\-_/.#:]{2,}", "-", s)
    return s or None


def check_invoice(raw, lists=None):
    """Customer invoice, e.g. the bank-discount claim: Customer:Job = bank,
    Class = Store 1, Item = Bank Discount Receivable, Amount = bank's share."""
    p = Problems()
    r = {
        "kind": "invoice",
        "customer": _ref(p, lists, "customers", "Customer:Job", raw.get("customer"), required=True),
        "date": p.run(parse_date, raw.get("date"), "Invoice Date"),
        "ref": p.text("Invoice No", _strip_arc(raw.get("ref")), MAX["inv_ref"]),
        "cls": _ref(p, lists, "classes", "Class", raw.get("cls")),
        "po":p.text("P.O. No", raw.get("po"), MAX["po"]),
        "terms": _ref(p, lists, "terms", "Terms", raw.get("terms")),
        "due_date": p.run(parse_date, raw.get("due_date"), "Due Date", required=False),
        "memo": p.text("Memo", raw.get("memo"), MAX["memo"]),
        "lines": [],
    }
    for i, ln in enumerate(raw.get("lines") or [], 1):
        if all(is_blank(ln.get(k)) for k in ("item", "amount", "qty", "rate", "desc")):
            continue
        tag = f"Line {i}: "
        q = p.run(parse_qty, ln.get("qty"), tag + "Qty")
        rate = p.run(parse_amount, ln.get("rate"), tag + "Rate", required=False, allow_zero=True)
        amount = p.run(parse_amount, ln.get("amount"), tag + "Amount", required=False)
        if q is not None and rate is not None:
            calc = (q * rate).quantize(Decimal("0.01"))
            if amount is not None and abs(amount - calc) > Decimal("0.05"):
                p.add(f"{tag}Qty x Rate = {calc} but Amount is {amount}")
            amount = calc
        if amount is None:
            p.add(f"{tag}Amount is required (or Qty and Rate)")
        r["lines"].append({
            "item": _ref(p, lists, "items", tag + "Item", ln.get("item"), required=True),
            "desc": p.text(tag + "Description", ln.get("desc"), MAX["desc"]),
            "qty": q, "rate": rate if q is not None else None, "amount": amount,
            # a line without its own class takes the invoice's class (so income goes to that store)
            "cls": _ref(p, lists, "classes", tag + "Class", ln.get("cls")) or r["cls"],
        })
    if not r["lines"]:
        p.add("At least one line (item and amount) is required")
    p.raise_if_any()
    r["total"] = _total(r["lines"])
    return r


def check_cheque(raw, lists=None):
    p = Problems()
    bank = _ref(p, lists, "accounts", "Bank Account", raw.get("bank"), required=True)
    if lists is not None and bank and lists.accounts.get(bank) not in (None, "Bank", "CreditCard"):
        p.add(f"Bank Account '{bank}' is not a Bank account in QuickBooks")
    r = {
        "kind": "cheque", "bank": bank,
        "payee": _ref(p, lists, "payees", "Payee", raw.get("payee")),
        "date": p.run(parse_date, raw.get("date"), "Date"),
        "to_print": parse_bool(raw.get("to_print")),
        "memo": p.text("Memo", raw.get("memo"), MAX["memo"]),
    }
    r["ref"] = None if r["to_print"] else p.text("Cheque No", raw.get("ref"), MAX["check_ref"])
    r["lines"] = _purchase_lines(p, lists, raw.get("lines"))
    p.raise_if_any()
    r["total"] = _total(r["lines"])
    return r


def check_journal(raw, lists=None):
    p = Problems()
    r = {
        "kind": "journal",
        "date": p.run(parse_date, raw.get("date"), "Date"),
        "ref": p.text("Entry No", raw.get("ref"), MAX["je_ref"]),
        "adjusting": parse_bool(raw.get("adjusting")),
        "lines": [],
    }
    for i, ln in enumerate(raw.get("lines") or [], 1):
        if all(is_blank(ln.get(k)) for k in ("account", "debit", "credit")):
            continue
        tag = f"Line {i}: "
        dr = p.run(parse_amount, ln.get("debit"), tag + "Debit", required=False)
        cr = p.run(parse_amount, ln.get("credit"), tag + "Credit", required=False)
        if dr and cr:
            p.add(f"{tag}has both Debit and Credit; use one per line")
        if not dr and not cr:
            p.add(f"{tag}Debit or Credit amount is required")
        acct = _ref(p, lists, "accounts", tag + "Account", ln.get("account"), required=True)
        name = _ref(p, lists, "payees", tag + "Name", ln.get("name"))
        if lists is not None and acct and not name and \
                lists.accounts.get(acct) in ("AccountsPayable", "AccountsReceivable"):
            p.add(f"{tag}a Name (vendor/customer) is required for the A/P or A/R account '{acct}'")
        r["lines"].append({
            "account": acct, "side": "debit" if dr else "credit", "amount": dr or cr,
            "memo": p.text(tag + "Memo", ln.get("memo"), MAX["memo"]),
            "name": name,
            "cls": _ref(p, lists, "classes", tag + "Class", ln.get("cls")),
        })
    if len(r["lines"]) < 2:
        p.add("A journal entry needs at least 2 lines")
    d = sum((ln["amount"] or 0 for ln in r["lines"] if ln["side"] == "debit"), Decimal(0))
    c = sum((ln["amount"] or 0 for ln in r["lines"] if ln["side"] == "credit"), Decimal(0))
    if d != c:
        p.add(f"Debits ({d:,.2f}) and Credits ({c:,.2f}) are not equal; difference {d - c:,.2f}")
    p.raise_if_any()
    r["total"] = d
    return r


def check_deposit(raw, lists=None):
    p = Problems()
    r = {
        "kind": "deposit",
        "account": _ref(p, lists, "accounts", "Deposit To", raw.get("account"), required=True),
        "date": p.run(parse_date, raw.get("date"), "Date"),
        "memo": p.text("Memo", raw.get("memo"), MAX["memo"]),
        "lines": [],
    }
    for i, ln in enumerate(raw.get("lines") or [], 1):
        if all(is_blank(ln.get(k)) for k in ("from_account", "amount", "from_name")):
            continue
        tag = f"Line {i}: "
        r["lines"].append({
            "from_name": _ref(p, lists, "payees", tag + "Received From", ln.get("from_name")),
            "from_account": _ref(p, lists, "accounts", tag + "From Account", ln.get("from_account"),
                                 required=True),
            "memo": p.text(tag + "Memo", ln.get("memo"), MAX["memo"]),
            "cheque_no": p.text(tag + "Cheque No", ln.get("cheque_no"), MAX["dep_check_no"]),
            "cls": _ref(p, lists, "classes", tag + "Class", ln.get("cls")),
            "amount": p.run(parse_amount, ln.get("amount"), tag + "Amount"),
        })
    if not r["lines"]:
        p.add("At least one deposit line is required")
    p.raise_if_any()
    r["total"] = _total(r["lines"])
    return r


def check_transfer(raw, lists=None):
    p = Problems()
    r = {
        "kind": "transfer",
        "date": p.run(parse_date, raw.get("date"), "Date"),
        "from_account": _ref(p, lists, "accounts", "Transfer From", raw.get("from_account"), required=True),
        "to_account": _ref(p, lists, "accounts", "Transfer To", raw.get("to_account"), required=True),
        "amount": p.run(parse_amount, raw.get("amount"), "Amount"),
        "memo": p.text("Memo", raw.get("memo"), MAX["memo"]),
        "cls": _ref(p, lists, "classes", "Class", raw.get("cls")),
    }
    if r["from_account"] and r["from_account"] == r["to_account"]:
        p.add("Transfer From and Transfer To cannot be the same account")
    p.raise_if_any()
    r["total"] = r["amount"]
    return r


def check_paybill(raw, lists=None):
    """bills: list of {txn_id or bill_ref, amount}. Bills given only by Ref No are
    looked up (open bills of the vendor) just before posting."""
    p = Problems()
    bank = _ref(p, lists, "accounts", "Bank Account", raw.get("bank"), required=True)
    if lists is not None and bank and lists.accounts.get(bank) not in (None, "Bank"):
        p.add(f"Bank Account '{bank}' is not a Bank account in QuickBooks")
    r = {
        "kind": "paybill",
        "vendor": _ref(p, lists, "vendors", "Vendor", raw.get("vendor"), required=True),
        "date": p.run(parse_date, raw.get("date"), "Payment Date"),
        "bank": bank,
        "to_print": parse_bool(raw.get("to_print")),
        "memo": p.text("Memo", raw.get("memo"), MAX["memo"]),
        "bills": [],
    }
    r["ref"] = None if r["to_print"] else p.text("Cheque No", raw.get("ref"), MAX["billpay_ref"])
    for i, b in enumerate(raw.get("bills") or [], 1):
        amt = p.run(parse_amount, b.get("amount"), f"Bill {i}: Amount to pay")
        txn = clean(b.get("txn_id"))
        bref = clean(b.get("bill_ref"))
        if not txn and not bref:
            p.add(f"Bill {i}: Bill Ref No is required")
        r["bills"].append({"txn_id": txn, "bill_ref": bref, "amount": amt})
    if not r["bills"]:
        p.add("Select at least one bill to pay")
    p.raise_if_any()
    r["total"] = _total(r["bills"])
    return r


CHECKERS = {
    "item": check_item, "vendor": check_vendor, "customer": check_customer,
    "account": check_account, "invoice": check_invoice, "bill": check_bill, "cheque": check_cheque,
    "journal": check_journal, "deposit": check_deposit, "transfer": check_transfer,
    "paybill": check_paybill,
}


def check(kind, raw, lists=None):
    return CHECKERS[kind](raw, lists)


def describe(r):
    """Short text for logs and confirmations: (name/ref, party, amount)."""
    k = r["kind"]
    if k == "item":
        return (f"{r['parent']}:{r['name']}" if r.get("parent") else r["name"]), \
            ITEM_TYPE_LABELS.get(r["type"], ""), None
    if k in ("vendor", "customer", "account"):
        nm = f"{r['parent']}:{r['name']}" if r.get("parent") else r["name"]
        return nm, ACCOUNT_TYPE_LABELS.get(r.get("type"), "") if k == "account" else "", None
    if k == "bill":
        return r.get("ref") or "", r["vendor"], r["total"]
    if k == "invoice":
        return r.get("ref") or "", r["customer"], r["total"]
    if k == "cheque":
        return r.get("ref") or ("To print" if r["to_print"] else ""), r.get("payee") or "", r["total"]
    if k == "paybill":
        return r.get("ref") or ("To print" if r["to_print"] else ""), r["vendor"], r["total"]
    if k == "journal":
        return r.get("ref") or "", "", r["total"]
    if k == "deposit":
        return "", r["account"], r["total"]
    if k == "transfer":
        return "", f"{r['from_account']} -> {r['to_account']}", r["total"]
    return "", "", None

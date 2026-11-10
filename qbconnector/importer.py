"""Excel bulk import: template, reading rows into records, writing a result file.

Transactions with several lines: give the rows of one transaction the same value in
the 'Group' column (e.g. 1, 1, 1, 2, 2). Header values (vendor, date, ref...) are taken
from the first row of the group. A blank Group = the row is a transaction by itself.
Rows whose Status is already 'Added' are skipped, so a result file can be fixed and
imported again without double posting.
"""
import datetime as _dt
import os

from .records import ACCOUNT_TYPE_LABELS, ACCOUNT_TYPES, check
from .util import InputError, is_blank, clean

STATUS_COL = "Status"
RESULT_COL = "QuickBooks Result"

# (header, key, level)  level: "h" = transaction header, "l" = line, "" = list record
SHEETS = [
    ("Items", "item", [
        ("Type", "type", ""), ("Name", "name", ""), ("Parent", "parent", ""),
        ("Sales Description", "sales_desc", ""), ("Sales Price", "price", ""),
        ("Income Account", "income_account", ""), ("Purchase Description", "purchase_desc", ""),
        ("Cost", "cost", ""), ("Expense / COGS Account", "expense_account", ""),
        ("Inventory Asset Account", "asset_account", ""), ("Preferred Vendor", "pref_vendor", ""),
        ("Reorder Point", "reorder_point", ""), ("Qty On Hand", "qty_on_hand", ""),
        ("Total Value", "total_value", ""), ("As Of Date", "as_of", ""), ("Inactive", "inactive", "")]),
    ("Vendors", "vendor", [
        ("Name", "name", ""), ("Company Name", "company", ""), ("Address 1", "addr1", ""),
        ("Address 2", "addr2", ""), ("City", "city", ""), ("Phone", "phone", ""),
        ("Email", "email", ""), ("Contact", "contact", ""), ("Print On Cheque As", "print_as", ""),
        ("Account No", "account_no", ""), ("NTN", "ntn", ""), ("Terms", "terms", ""),
        ("Opening Balance", "open_balance", ""), ("Opening Balance Date", "open_balance_date", ""),
        ("Notes", "notes", "")]),
    ("Customers", "customer", [
        ("Name", "name", ""), ("Parent", "parent", ""), ("Company Name", "company", ""),
        ("Address 1", "addr1", ""), ("Address 2", "addr2", ""), ("City", "city", ""),
        ("Phone", "phone", ""), ("Email", "email", ""), ("Contact", "contact", ""),
        ("Terms", "terms", ""), ("Account No", "account_no", ""),
        ("Opening Balance", "open_balance", ""), ("Opening Balance Date", "open_balance_date", ""),
        ("Notes", "notes", "")]),
    ("Accounts", "account", [
        ("Name", "name", ""), ("Parent", "parent", ""), ("Type", "type", ""),
        ("Number", "number", ""), ("Description", "desc", ""), ("Bank Account No", "bank_no", ""),
        ("Opening Balance", "open_balance", ""), ("Opening Balance Date", "open_balance_date", "")]),
    ("Invoices", "invoice", [
        ("Group", "group", ""), ("Customer:Job", "customer", "h"), ("Date", "date", "h"),
        ("Invoice No", "ref", "h"), ("Class", "cls", "h"), ("P.O. No", "po", "h"),
        ("Terms", "terms", "h"), ("Due Date", "due_date", "h"), ("Memo", "memo", "h"),
        ("Item", "item", "l"), ("Description", "desc", "l"), ("Qty", "qty", "l"),
        ("Rate", "rate", "l"), ("Amount", "amount", "l"), ("Line Class", "line_cls", "l")]),
    ("Bills", "bill", [
        ("Group", "group", ""), ("Vendor", "vendor", "h"), ("Date", "date", "h"),
        ("Due Date", "due_date", "h"), ("Ref No", "ref", "h"), ("Terms", "terms", "h"),
        ("Memo", "memo", "h"), ("Line Type", "kind", "l"), ("Account / Item", "target", "l"),
        ("Description", "desc", "l"), ("Qty", "qty", "l"), ("Rate", "rate", "l"),
        ("Amount", "amount", "l"), ("Class", "cls", "l"), ("Customer:Job", "customer", "l")]),
    ("Bill Payments", "paybill", [
        ("Group", "group", ""), ("Vendor", "vendor", "h"), ("Date", "date", "h"),
        ("Bank Account", "bank", "h"), ("Cheque No", "ref", "h"), ("To Be Printed", "to_print", "h"),
        ("Memo", "memo", "h"), ("Bill Ref No", "bill_ref", "l"), ("Amount", "amount", "l"),
        ("Discount", "discount", "l"), ("Discount Account", "discount_account", "l"),
        ("Bill Amount", "bill_amount", "l")]),
    ("Cheques", "cheque", [
        ("Group", "group", ""), ("Bank Account", "bank", "h"), ("Payee", "payee", "h"),
        ("Date", "date", "h"), ("Cheque No", "ref", "h"), ("To Be Printed", "to_print", "h"),
        ("Memo", "memo", "h"), ("Line Type", "kind", "l"), ("Account / Item", "target", "l"),
        ("Description", "desc", "l"), ("Qty", "qty", "l"), ("Rate", "rate", "l"),
        ("Amount", "amount", "l"), ("Class", "cls", "l"), ("Customer:Job", "customer", "l")]),
    ("Journal Entries", "journal", [
        ("Group", "group", ""), ("Date", "date", "h"), ("Entry No", "ref", "h"),
        ("Adjusting", "adjusting", "h"), ("Account", "account", "l"), ("Debit", "debit", "l"),
        ("Credit", "credit", "l"), ("Memo", "memo", "l"), ("Name", "name", "l"),
        ("Class", "cls", "l")]),
    ("Deposits", "deposit", [
        ("Group", "group", ""), ("Deposit To", "account", "h"), ("Date", "date", "h"),
        ("Memo", "memo", "h"), ("Received From", "from_name", "l"), ("From Account", "from_account", "l"),
        ("Line Memo", "line_memo", "l"), ("Cheque No", "cheque_no", "l"), ("Class", "cls", "l"),
        ("Amount", "amount", "l")]),
    ("Transfers", "transfer", [
        ("Date", "date", ""), ("From Account", "from_account", ""), ("To Account", "to_account", ""),
        ("Amount", "amount", ""), ("Memo", "memo", ""), ("Class", "cls", "")]),
]
SHEET_BY_NAME = {s[0].lower(): s for s in SHEETS}

NOTES = {
    "Type": "Items: Inventory, Non-inventory, Service or Other Charge.  Accounts: Bank, Expense, "
            "Income, Other Current Asset, Cost of Goods Sold, ...",
    "Group": "Rows with the same Group number form ONE transaction (several lines). "
             "Header columns are read from the first row of the group.",
    "Line Type": "Expense (an account) or Item",
    "Parent": "Optional. For a sub-item / sub-account / job: the parent's name. "
              "You can also write Parent:Name in the Name column.",
    "Date": "DD/MM/YYYY", "Due Date": "DD/MM/YYYY", "As Of Date": "DD/MM/YYYY",
    "Opening Balance Date": "DD/MM/YYYY",
    "To Be Printed": "Yes = leave cheque number empty and mark 'To be printed'",
    "Bill Ref No": "The Ref No of the vendor's UNPAID bill in QuickBooks",
    "Expense / COGS Account": "Inventory: the COGS account. Others: purchase/expense account "
                              "(fill only if the item is also bought).",
    "Income Account": "Inventory: income account. Non-inventory/Service/Other Charge used only "
                      "for purchases: put the EXPENSE account here and leave purchase columns empty.",
    "Name": "Journal: vendor/customer name (required on A/P and A/R lines)",
    "Customer:Job": "Invoices: the customer, e.g. the bank you claim the discount share from. "
                    "Bills/Cheques: optional, the customer the cost is for.",
    "Line Class": "Leave blank to use the invoice's Class (e.g. Store 1)",
    "Item": "e.g. Bank Discount Receivable",
}


def make_template(path, lists=None):
    """Create the blank import workbook. With lists, a 'QuickBooks Lists' sheet is added
    for copy-paste of exact names."""
    from openpyxl import Workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.worksheet.datavalidation import DataValidation

    wb = Workbook()
    ws = wb.active
    ws.title = "Read Me"
    lines = [
        "Arcadian QB Connector - Excel import template",
        "",
        "1. Fill only the sheets you need. Leave the others empty (or delete them).",
        "2. Names (accounts, vendors, items, classes) must match QuickBooks exactly. "
        "Use the 'QuickBooks Lists' sheet to copy them.",
        "3. Dates: DD/MM/YYYY.  Amounts: plain numbers (commas are fine).",
        "4. Bills / Cheques / Journal Entries / Deposits / Bill Payments with several lines: "
        "give the rows the same Group number. Header columns come from the first row.",
        "5. In the app: Excel Import > choose this file > Check. Fix any errors, then Post.",
        "6. A RESULT copy of the file is saved next to it with a Status for every row. Rows "
        "marked 'Added' are skipped if you import that file again.",
        "",
        "Examples",
        "Bills: Group 1 | Pepsi Co | 05/11/2026 | | INV-1001 | | Nov drinks | Item | 7Up 1.5ltr | | 24 | 110 | | Store 1",
        "       Group 1 | (blank rest) ... | Expense | Freight | cartage | | | 500 | Store 1",
        "Journal: Group 1 | 05/11/2026 | JV-11 | | Bank Charges | 150 |  | SMS charges",
        "         Group 1 |            |       | | MCB Gulberg  |     | 150 |",
    ]
    for i, t in enumerate(lines, 1):
        ws.cell(i, 1, t)
    ws["A1"].font = Font(bold=True, size=14)
    ws["A10"].font = Font(bold=True)
    ws.column_dimensions["A"].width = 120

    head_fill = PatternFill("solid", fgColor="14213D")
    for name, kind, cols in SHEETS:
        sh = wb.create_sheet(name)
        for c, (header, key, level) in enumerate(cols, 1):
            cell = sh.cell(1, c, header)
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = head_fill if level != "l" else PatternFill("solid", fgColor="2563EB")
            cell.alignment = Alignment(vertical="center")
            if header in NOTES:
                cell.comment = Comment(NOTES[header], "QB Connector")
            letter = cell.column_letter
            sh.column_dimensions[letter].width = max(12, len(header) + 4)
            if "Date" in header:
                for r in range(2, 1002):
                    sh.cell(r, c).number_format = "DD/MM/YYYY"
            if header in ("Amount", "Debit", "Credit", "Sales Price", "Cost", "Rate",
                          "Total Value", "Opening Balance"):
                for r in range(2, 1002):
                    sh.cell(r, c).number_format = "#,##0.00"
            dv_list = None
            if header == "Type" and kind == "item":
                dv_list = '"Inventory,Non-inventory,Service,Other Charge"'
            elif header == "Line Type":
                dv_list = '"Expense,Item"'
            elif header in ("To Be Printed", "Inactive", "Adjusting"):
                dv_list = '"Yes,No"'
            if dv_list:
                dv = DataValidation(type="list", formula1=dv_list, allow_blank=True)
                sh.add_data_validation(dv)
                dv.add(f"{letter}2:{letter}1001")
        sh.freeze_panes = "A2"
    acc = wb.create_sheet("Account Types")
    acc.append(["Account Type (use in Accounts sheet)"])
    for t in ACCOUNT_TYPES:
        acc.append([ACCOUNT_TYPE_LABELS[t]])
    acc.column_dimensions["A"].width = 40
    if lists is not None:
        ls = wb.create_sheet("QuickBooks Lists")
        cols = [("Accounts", lists.names("accounts")), ("Account Type", None),
                ("Items", lists.names("items")), ("Vendors", lists.names("vendors")),
                ("Customers", lists.names("customers")), ("Classes", lists.names("classes")),
                ("Other Names / Employees", sorted(lists.othernames + lists.employees, key=str.lower)),
                ("Terms", lists.names("terms"))]
        for c, (h, vals) in enumerate(cols, 1):
            ls.cell(1, c, h).font = Font(bold=True)
            ls.column_dimensions[ls.cell(1, c).column_letter].width = 34
            if h == "Account Type":
                vals = [ACCOUNT_TYPE_LABELS.get(lists.accounts[a], lists.accounts[a])
                        for a in lists.names("accounts")]
            for r, v in enumerate(vals, 2):
                ls.cell(r, c, v)
        ls.freeze_panes = "A2"
    wb.save(path)
    return path


class Batch:
    """One record to post, made from one or more Excel rows."""

    def __init__(self, sheet, kind, rows, raw):
        self.sheet, self.kind, self.rows, self.raw = sheet, kind, rows, raw
        self.record = None
        self.error = None
        self.status = ""         # Ready / Error / Added / Rejected / Skipped
        self.result = ""

    @property
    def row_text(self):
        return f"{self.rows[0]}" if len(self.rows) == 1 else f"{self.rows[0]}-{self.rows[-1]}"


def _header_map(ws, cols):
    """Find our columns by header text (any order, case-insensitive)."""
    want = {h.lower(): key for h, key, _ in cols}
    found, status_c, result_c = {}, None, None
    for c, cell in enumerate(next(ws.iter_rows(min_row=1, max_row=1, values_only=True), ()), 1):
        h = (clean(cell) or "").lower()
        if h in want:
            found[want[h]] = c
        elif h == STATUS_COL.lower():
            status_c = c
        elif h == RESULT_COL.lower():
            result_c = c
    return found, status_c, result_c


def read_workbook(path):
    """Returns (batches, skipped_count, sheet_info)."""
    from openpyxl import load_workbook
    wb = load_workbook(path, data_only=True)
    batches, skipped, info = [], 0, []
    for ws in wb.worksheets:
        spec = SHEET_BY_NAME.get(ws.title.strip().lower())
        if not spec:
            continue
        name, kind, cols = spec
        cmap, status_c, _ = _header_map(ws, cols)
        if not cmap:
            continue
        level = {key: lv for _, key, lv in cols}
        groups = {}
        order = []
        n_rows = 0
        for r_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), 2):
            vals = {k: (row[c - 1] if c - 1 < len(row) else None) for k, c in cmap.items()}
            if all(is_blank(v) for v in vals.values()):
                continue
            n_rows += 1
            if status_c and (clean(row[status_c - 1] if status_c - 1 < len(row) else None) or "").lower() == "added":
                skipped += 1
                continue
            g = clean(vals.get("group"))
            gkey = ("g", g) if g else ("r", r_idx)
            if gkey not in groups:
                groups[gkey] = []
                order.append(gkey)
            groups[gkey].append((r_idx, vals))
        for gkey in order:
            rows = groups[gkey]
            if kind in ("item", "vendor", "customer", "account", "transfer"):
                raw = dict(rows[0][1])
            else:
                raw = {}
                for k, v in rows[0][1].items():
                    if level.get(k) == "h":
                        raw[k] = v
                lines = []
                for _, vals in rows:
                    ln = {k: v for k, v in vals.items() if level.get(k) == "l"}
                    if kind == "deposit":
                        ln["memo"] = ln.pop("line_memo", None)
                    if kind == "invoice":
                        ln["cls"] = ln.pop("line_cls", None)
                    lines.append(ln)
                raw["bills" if kind == "paybill" else "lines"] = lines
            batches.append(Batch(name, kind, [r for r, _ in rows], raw))
        info.append((name, n_rows))
    wb.close()
    return batches, skipped, info


def check_batches(batches, lists):
    for b in batches:
        try:
            b.record = check(b.kind, b.raw, lists)
            b.status, b.error, b.result = "Ready", None, ""
        except InputError as e:
            b.record, b.status, b.error = None, "Error", str(e)
            b.result = str(e).replace("\n", " | ")
    return batches


def result_path(src):
    stem, ext = os.path.splitext(src)
    if stem.endswith(" - RESULT"):
        return src if ext.lower() == ".xlsx" else stem + ".xlsx"
    return stem + " - RESULT.xlsx"


def write_result(src, batches, dest=None):
    """Copy the workbook with Status / QuickBooks Result columns filled in."""
    from openpyxl import load_workbook
    from openpyxl.styles import Font, PatternFill
    dest = dest or result_path(src)
    wb = load_workbook(src)
    colors = {"Added": "D1FAE5", "Error": "FEE2E2", "Rejected": "FEE2E2", "Failed": "FEE2E2",
              "Ready": "FEF3C7", "Not posted": "FEF3C7"}
    by_sheet = {}
    for b in batches:
        by_sheet.setdefault(b.sheet.lower(), []).append(b)
    for ws in wb.worksheets:
        spec = SHEET_BY_NAME.get(ws.title.strip().lower())
        if not spec or ws.title.lower() not in by_sheet:
            continue
        _, status_c, result_c = _header_map(ws, spec[2])
        last = ws.max_column
        if not status_c:
            last += 1
            status_c = last
            ws.cell(1, status_c, STATUS_COL)
        if not result_c:
            result_c = max(last, status_c) + 1
            ws.cell(1, result_c, RESULT_COL)
        for c in (status_c, result_c):
            ws.cell(1, c).font = Font(bold=True)
        ws.column_dimensions[ws.cell(1, result_c).column_letter].width = 70
        for b in by_sheet[ws.title.lower()]:
            for r in b.rows:
                ws.cell(r, status_c, b.status)
                ws.cell(r, result_c, b.result)
                if b.status in colors:
                    ws.cell(r, status_c).fill = PatternFill("solid", fgColor=colors[b.status])
    try:
        wb.save(dest)
    except PermissionError:
        stem, ext = os.path.splitext(dest)
        dest = f"{stem} {_dt.datetime.now():%H%M%S}{ext}"
        wb.save(dest)
    return dest

"""Build qbXML 13.0 requests and read QuickBooks' answers.

Element order matters to QuickBooks: every builder follows the order of Intuit's
qbXML 13.0 schema (tests/test_qbxml.py checks each one against that schema).
"""
import re
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

from . import QBXML_VERSION
from .util import fmt_amount, fmt_qty


def esc(v):
    return escape(str(v), {'"': "&quot;"})


def el(tag, v):
    if v is None or v == "":
        return ""
    if isinstance(v, bool):
        v = "true" if v else "false"
    return f"<{tag}>{esc(v)}</{tag}>"


def amt(tag, v):
    return "" if v is None else f"<{tag}>{fmt_amount(v)}</{tag}>"


def qty(tag, v):
    return "" if v is None else f"<{tag}>{fmt_qty(v)}</{tag}>"


def ref(tag, full_name):
    return f"<{tag}><FullName>{esc(full_name)}</FullName></{tag}>" if full_name else ""


def block(tag, *parts):
    inner = "".join(parts)
    return f"<{tag}>{inner}</{tag}>" if inner else ""


def envelope(*requests, on_error="stopOnError"):
    body = "".join(re.sub(r"^<(\w+)", lambda m: f'<{m.group(1)} requestID="{i}"', r, count=1)
                   for i, r in enumerate(requests, 1))
    return (f'<?xml version="1.0" encoding="utf-8"?><?qbxml version="{QBXML_VERSION}"?>'
            f'<QBXML><QBXMLMsgsRq onError="{on_error}">{body}</QBXMLMsgsRq></QBXML>')


def _add(tag, body):
    return f"<{tag}Rq><{tag}>{body}</{tag}></{tag}Rq>"


def _address(tag, r):
    return block(tag, el("Addr1", r.get("addr1")), el("Addr2", r.get("addr2")),
                 el("City", r.get("city")))


# ------------------------------------------------------------------ lists

def item_add(r):
    head = el("Name", r["name"]) + (el("IsActive", False) if r.get("inactive") else "") \
        + ref("ParentRef", r.get("parent"))
    t = r["type"]
    if t == "Inventory":
        body = (head + el("SalesDesc", r.get("sales_desc")) + amt("SalesPrice", r.get("price"))
                + ref("IncomeAccountRef", r.get("income_account"))
                + el("PurchaseDesc", r.get("purchase_desc")) + amt("PurchaseCost", r.get("cost"))
                + ref("COGSAccountRef", r.get("expense_account"))
                + ref("PrefVendorRef", r.get("pref_vendor"))
                + ref("AssetAccountRef", r.get("asset_account"))
                + qty("ReorderPoint", r.get("reorder_point"))
                + qty("QuantityOnHand", r.get("qty_on_hand"))
                + amt("TotalValue", r.get("total_value"))
                + el("InventoryDate", r.get("as_of")))
        return _add("ItemInventoryAdd", body)
    tag = {"NonInventory": "ItemNonInventoryAdd", "Service": "ItemServiceAdd",
           "OtherCharge": "ItemOtherChargeAdd"}[t]
    if r.get("both"):
        detail = ("<SalesAndPurchase>" + el("SalesDesc", r.get("sales_desc"))
                  + amt("SalesPrice", r.get("price"))
                  + ref("IncomeAccountRef", r.get("income_account"))
                  + el("PurchaseDesc", r.get("purchase_desc")) + amt("PurchaseCost", r.get("cost"))
                  + ref("ExpenseAccountRef", r.get("expense_account"))
                  + ref("PrefVendorRef", r.get("pref_vendor")) + "</SalesAndPurchase>")
    else:
        detail = ("<SalesOrPurchase>" + el("Desc", r.get("sales_desc"))
                  + amt("Price", r.get("price"))
                  + ref("AccountRef", r.get("income_account")) + "</SalesOrPurchase>")
    return _add(tag, head + detail)


def vendor_add(r):
    body = (el("Name", r["name"]) + el("CompanyName", r.get("company"))
            + _address("VendorAddress", r)
            + el("Phone", r.get("phone")) + el("Email", r.get("email"))
            + el("Contact", r.get("contact")) + el("NameOnCheck", r.get("print_as"))
            + el("AccountNumber", r.get("account_no")) + el("Notes", r.get("notes"))
            + ref("TermsRef", r.get("terms")) + el("VendorTaxIdent", r.get("ntn"))
            + amt("OpenBalance", r.get("open_balance")) + el("OpenBalanceDate", r.get("open_balance_date")))
    return _add("VendorAdd", body)


def customer_add(r):
    body = (el("Name", r["name"]) + ref("ParentRef", r.get("parent"))
            + el("CompanyName", r.get("company")) + _address("BillAddress", r)
            + el("Phone", r.get("phone")) + el("Email", r.get("email"))
            + el("Contact", r.get("contact")) + ref("TermsRef", r.get("terms"))
            + amt("OpenBalance", r.get("open_balance")) + el("OpenBalanceDate", r.get("open_balance_date"))
            + el("AccountNumber", r.get("account_no")) + el("Notes", r.get("notes")))
    return _add("CustomerAdd", body)


def account_add(r):
    body = (el("Name", r["name"]) + ref("ParentRef", r.get("parent"))
            + el("AccountType", r["type"]) + el("AccountNumber", r.get("number"))
            + el("BankNumber", r.get("bank_no")) + el("Desc", r.get("desc"))
            + amt("OpenBalance", r.get("open_balance")) + el("OpenBalanceDate", r.get("open_balance_date")))
    return _add("AccountAdd", body)


# ------------------------------------------------------------------ transactions

def _purchase_lines(lines):
    """Expense lines must come before item lines."""
    exp = "".join(
        "<ExpenseLineAdd>" + ref("AccountRef", ln["account"]) + amt("Amount", ln["amount"])
        + el("Memo", ln.get("desc")) + ref("CustomerRef", ln.get("customer"))
        + ref("ClassRef", ln.get("cls")) + "</ExpenseLineAdd>"
        for ln in lines if ln["kind"] == "expense")
    items = ""
    for ln in lines:
        if ln["kind"] != "item":
            continue
        if ln.get("qty") is not None and ln.get("rate") is not None:
            money = qty("Quantity", ln["qty"]) + amt("Cost", ln["rate"])
        else:
            money = qty("Quantity", ln.get("qty")) + amt("Amount", ln["amount"])
        items += ("<ItemLineAdd>" + ref("ItemRef", ln["item"]) + el("Desc", ln.get("desc"))
                  + money + ref("CustomerRef", ln.get("customer")) + ref("ClassRef", ln.get("cls"))
                  + "</ItemLineAdd>")
    return exp + items


def invoice_add(r):
    lines = ""
    for ln in r["lines"]:
        if ln.get("qty") is not None and ln.get("rate") is not None:
            money = qty("Quantity", ln["qty"]) + amt("Rate", ln["rate"]) + ref("ClassRef", ln.get("cls"))
        else:
            money = qty("Quantity", ln.get("qty")) + ref("ClassRef", ln.get("cls")) + amt("Amount", ln["amount"])
        lines += "<InvoiceLineAdd>" + ref("ItemRef", ln["item"]) + el("Desc", ln.get("desc")) + money \
            + "</InvoiceLineAdd>"
    body = (ref("CustomerRef", r["customer"]) + ref("ClassRef", r.get("cls")) + el("TxnDate", r["date"])
            + el("RefNumber", r.get("ref")) + el("PONumber", r.get("po")) + ref("TermsRef", r.get("terms"))
            + el("DueDate", r.get("due_date")) + el("Memo", r.get("memo")) + lines)
    return _add("InvoiceAdd", body)


def bill_add(r):
    body = (ref("VendorRef", r["vendor"]) + el("TxnDate", r["date"]) + el("DueDate", r.get("due_date"))
            + el("RefNumber", r.get("ref")) + ref("TermsRef", r.get("terms"))
            + el("Memo", r.get("memo")) + _purchase_lines(r["lines"]))
    return _add("BillAdd", body)


def cheque_add(r):
    body = (ref("AccountRef", r["bank"]) + ref("PayeeEntityRef", r.get("payee"))
            + el("RefNumber", r.get("ref")) + el("TxnDate", r["date"]) + el("Memo", r.get("memo"))
            + el("IsToBePrinted", True if r.get("to_print") else None)
            + _purchase_lines(r["lines"]))
    return _add("CheckAdd", body)


def journal_add(r):
    def line(tag, ln):
        return (f"<{tag}>" + ref("AccountRef", ln["account"]) + amt("Amount", ln["amount"])
                + el("Memo", ln.get("memo")) + ref("EntityRef", ln.get("name"))
                + ref("ClassRef", ln.get("cls")) + f"</{tag}>")
    lines = "".join(line("JournalDebitLine", ln) for ln in r["lines"] if ln["side"] == "debit") + \
        "".join(line("JournalCreditLine", ln) for ln in r["lines"] if ln["side"] == "credit")
    body = (el("TxnDate", r["date"]) + el("RefNumber", r.get("ref"))
            + el("IsAdjustment", True if r.get("adjusting") else None) + lines)
    return _add("JournalEntryAdd", body)


def deposit_add(r):
    lines = "".join(
        "<DepositLineAdd>" + ref("EntityRef", ln.get("from_name")) + ref("AccountRef", ln["from_account"])
        + el("Memo", ln.get("memo")) + el("CheckNumber", ln.get("cheque_no"))
        + ref("ClassRef", ln.get("cls")) + amt("Amount", ln["amount"]) + "</DepositLineAdd>"
        for ln in r["lines"])
    body = (el("TxnDate", r["date"]) + ref("DepositToAccountRef", r["account"])
            + el("Memo", r.get("memo")) + lines)
    return _add("DepositAdd", body)


def transfer_add(r):
    body = (el("TxnDate", r["date"]) + ref("TransferFromAccountRef", r["from_account"])
            + ref("TransferToAccountRef", r["to_account"]) + ref("ClassRef", r.get("cls"))
            + amt("Amount", r["amount"]) + el("Memo", r.get("memo")))
    return _add("TransferAdd", body)


def paybill_add(r):
    """All bills must already have txn_id (see poster.resolve_bills)."""
    pay = el("IsToBePrinted", True) if r.get("to_print") else el("RefNumber", r.get("ref"))
    applied = "".join("<AppliedToTxnAdd>" + el("TxnID", b["txn_id"]) + amt("PaymentAmount", b["amount"])
                      + "</AppliedToTxnAdd>" for b in r["bills"])
    body = (ref("PayeeEntityRef", r["vendor"]) + el("TxnDate", r["date"])
            + ref("BankAccountRef", r["bank"]) + pay + el("Memo", r.get("memo")) + applied)
    return _add("BillPaymentCheckAdd", body)


BUILDERS = {
    "item": item_add, "vendor": vendor_add, "customer": customer_add, "account": account_add,
    "invoice": invoice_add, "bill": bill_add, "cheque": cheque_add, "journal": journal_add, "deposit": deposit_add,
    "transfer": transfer_add, "paybill": paybill_add,
}


def build(record):
    return BUILDERS[record["kind"]](record)


# ------------------------------------------------------------------ queries

def lists_query():
    return [
        "<HostQueryRq/>",
        "<CompanyQueryRq/>",
        "<AccountQueryRq><IncludeRetElement>FullName</IncludeRetElement>"
        "<IncludeRetElement>AccountType</IncludeRetElement></AccountQueryRq>",
        "<VendorQueryRq><IncludeRetElement>Name</IncludeRetElement></VendorQueryRq>",
        "<CustomerQueryRq><IncludeRetElement>FullName</IncludeRetElement></CustomerQueryRq>",
        "<EmployeeQueryRq><IncludeRetElement>Name</IncludeRetElement></EmployeeQueryRq>",
        "<OtherNameQueryRq><IncludeRetElement>Name</IncludeRetElement></OtherNameQueryRq>",
        "<ItemQueryRq><IncludeRetElement>FullName</IncludeRetElement></ItemQueryRq>",
        "<ClassQueryRq><IncludeRetElement>FullName</IncludeRetElement></ClassQueryRq>",
        "<TermsQueryRq><IncludeRetElement>Name</IncludeRetElement></TermsQueryRq>",
    ]


def open_bills_query(vendor):
    return ("<BillQueryRq><EntityFilter>" + el("FullName", vendor) + "</EntityFilter>"
            "<PaidStatus>NotPaidOnly</PaidStatus>"
            + "".join(f"<IncludeRetElement>{t}</IncludeRetElement>" for t in
                      ("TxnID", "TxnDate", "RefNumber", "DueDate", "AmountDue", "OpenAmount", "Memo"))
            + "</BillQueryRq>")


# ------------------------------------------------------------------ responses

class QBError(Exception):
    """QuickBooks rejected a request."""

    def __init__(self, code, message, request=None, response=None):
        super().__init__(f"QuickBooks error {code}: {message}")
        self.code, self.message, self.request, self.response = code, message, request, response


class Rs:
    def __init__(self, node):
        self.tag = node.tag
        self.code = int(node.get("statusCode", "0"))
        self.severity = node.get("statusSeverity", "Info")
        self.message = node.get("statusMessage", "")
        self.rets = list(node)

    @property
    def ok(self):
        # 1 = "no matching object found" (an empty query result)
        return self.code in (0, 1) or self.severity in ("Info", "Warn")


def parse_response(xml_text):
    root = ET.fromstring(xml_text)
    msgs = root.find("QBXMLMsgsRs")
    return [Rs(n) for n in (msgs if msgs is not None else [])]


def txt(node, path, default=""):
    v = node.find(path)
    return v.text if v is not None and v.text is not None else default


ITEM_TAGS = {"ItemInventoryRet": "Inventory Part", "ItemNonInventoryRet": "Non-inventory Part",
             "ItemServiceRet": "Service", "ItemOtherChargeRet": "Other Charge",
             "ItemInventoryAssemblyRet": "Inventory Assembly", "ItemFixedAssetRet": "Fixed Asset",
             "ItemSubtotalRet": "Subtotal", "ItemDiscountRet": "Discount", "ItemPaymentRet": "Payment",
             "ItemSalesTaxRet": "Sales Tax Item", "ItemSalesTaxGroupRet": "Sales Tax Group",
             "ItemGroupRet": "Group"}


def fill_lists(lists, responses):
    """Put the answers of lists_query() into a records.Lists object."""
    for rs in responses:
        t = rs.tag
        for n in rs.rets:
            if t == "HostQueryRs":
                lists.product = txt(n, "ProductName")
            elif t == "CompanyQueryRs":
                lists.company = txt(n, "CompanyName")
            elif t == "AccountQueryRs":
                lists.accounts[txt(n, "FullName")] = txt(n, "AccountType")
            elif t == "VendorQueryRs":
                lists.vendors.append(txt(n, "Name"))
            elif t == "CustomerQueryRs":
                lists.customers.append(txt(n, "FullName"))
            elif t == "EmployeeQueryRs":
                lists.employees.append(txt(n, "Name"))
            elif t == "OtherNameQueryRs":
                lists.othernames.append(txt(n, "Name"))
            elif t == "ItemQueryRs":
                lists.items[txt(n, "FullName")] = ITEM_TAGS.get(n.tag, n.tag)
            elif t == "ClassQueryRs":
                lists.classes.append(txt(n, "FullName"))
            elif t == "TermsQueryRs":
                lists.terms.append(txt(n, "Name"))
    lists.reindex()
    return lists


def read_open_bills(rs):
    out = []
    for n in rs.rets:
        out.append({
            "txn_id": txt(n, "TxnID"), "date": txt(n, "TxnDate"), "ref": txt(n, "RefNumber"),
            "due_date": txt(n, "DueDate"), "amount_due": txt(n, "AmountDue", "0"),
            "open_amount": txt(n, "OpenAmount", "0"), "memo": txt(n, "Memo"),
        })
    out.sort(key=lambda b: (b["date"], b["ref"]))
    return out


def added_id(rs):
    """TxnID or ListID of a newly added record."""
    for n in rs.rets:
        return txt(n, "TxnID") or txt(n, "ListID")
    return ""

"""Checks every request the app can build against Intuit's qbXML 13.0 schema.

The schema files come with the QuickBooks SDK (or github.com/johnballantyne/qbxml lib/xsd).
Set QBXML_XSD_DIR to the folder holding qbxmlops130.xsd; the schema test is skipped otherwise.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from qbconnector import qbxml  # noqa: E402
from qbconnector.records import check, Lists  # noqa: E402

SAMPLES = {
    "item": [
        dict(type="Inventory", name="7Up 1.5ltr", parent="Beverages", sales_desc="7Up bottle",
             price="150", income_account="Sales", purchase_desc="7Up bottle", cost="110",
             expense_account="Cost of Goods Sold", asset_account="Inventory Asset",
             pref_vendor="Pepsi Co", reorder_point="10", qty_on_hand="24", total_value="2640",
             as_of="01/11/2026"),
        dict(type="Non-inventory", name="A4 Paper Rim", income_account="Stationery Expense"),
        dict(type="Non-inventory", name="Fry Oil 16L", price="0", income_account="Sales",
             cost="7500", expense_account="Kitchen Supplies", pref_vendor="Pepsi Co"),
        dict(type="Service", name="Pest Control", sales_desc="Monthly", price="5000",
             income_account="Repairs & Maintenance", inactive="yes"),
        dict(type="Other Charge", name="Delivery Charge", price="200", income_account="Sales"),
    ],
    "vendor": [dict(name="Pepsi Co", company="Pepsi Pakistan", addr1="Plot 1", addr2="Gulberg",
                    city="Lahore", phone="042-111", email="a@b.com", contact="Ali",
                    print_as="Pepsi Pakistan Pvt Ltd", account_no="C-123", ntn="1234567-8",
                    terms="Net 30", open_balance="1,000", open_balance_date="01/07/2026",
                    notes="Main supplier")],
    "customer": [dict(name="Askari Bank", company="Askari Bank Ltd", addr1="HO", city="Rawalpindi",
                      phone="051", email="x@y.com", contact="Bilal", terms="Net 30",
                      account_no="9", open_balance="500", open_balance_date="01/07/2026", notes="n"),
                 dict(name="Askari Bank:Discount Nov", parent=None)],
    "account": [dict(name="MCB Gulberg", type="Bank", number="1010", desc="Main", bank_no="0123456",
                     open_balance="10000", open_balance_date="30/06/2026"),
                dict(name="Expenses:Gas Bill", type="Expense")],
    "invoice": [dict(customer="MCB Bank", date="31/10/2026", ref="DC-OCT-01", cls="Store 1",
                     po="Oct claim", terms="Net 30", due_date="30/11/2026", memo="Oct discount share",
                     lines=[dict(item="Bank Discount Receivable", desc="Oct 2026 MCB share", amount="45,250.50"),
                            dict(item="Bank Discount Receivable", qty="2", rate="100", cls="Store 2")])],
    "bill": [dict(vendor="Pepsi Co", date="05/11/2026", due_date="05/12/2026", ref="INV-1001",
                  terms="Net 30", memo="Nov drinks",
                  lines=[dict(kind="Item", target="7Up 1.5ltr", qty="24", rate="110", cls="Store 1"),
                         dict(kind="Expense", target="Freight", amount="500", desc="cartage",
                              cls="Store 1", customer="Askari Bank"),
                         dict(kind="Item", target="Delivery Charge", amount="200")])],
    "cheque": [dict(bank="MCB Gulberg", payee="Pepsi Co", date="05/11/2026", ref="123456",
                    memo="Daily Cash Expenses Payment",
                    lines=[dict(kind="Expense", target="Petty Cash", amount="25,000", cls="Store 1"),
                           dict(kind="Item", target="A4 Paper Rim", qty="2", rate="1200")]),
               dict(bank="MCB Gulberg", date="05/11/2026", to_print="yes",
                    lines=[dict(target="Petty Cash", amount="100")])],
    "journal": [dict(date="05/11/2026", ref="JV-11", adjusting="yes",
                     lines=[dict(account="Bank Charges", debit="150", memo="SMS", cls="Store 1"),
                            dict(account="Accounts Payable", credit="100", name="Pepsi Co"),
                            dict(account="MCB Gulberg", credit="50")])],
    "deposit": [dict(account="MCB Gulberg", date="05/11/2026", memo="Card settlement",
                     lines=[dict(from_name="Askari Bank", from_account="Bank Discount Receivable",
                                 memo="Oct", cheque_no="998", cls="Store 1", amount="12,345.67"),
                            dict(from_account="Sales", amount="100")])],
    "transfer": [dict(date="05/11/2026", from_account="MCB Gulberg", to_account="Petty Cash",
                      amount="5000", memo="cash", cls="Store 1")],
    "paybill": [dict(vendor="Pepsi Co", date="05/11/2026", bank="MCB Gulberg", ref="654321",
                     memo="Oct bills", bills=[dict(txn_id="1A2B-123", amount="1000"),
                                              dict(txn_id="1A2C-124", amount="250.5")]),
                dict(vendor="Pepsi Co", date="05/11/2026", bank="MCB Gulberg", memo="cash, no cheque no",
                     bills=[dict(txn_id="1A2B-123", amount="10")]),
                dict(vendor="Pepsi Co", date="05/11/2026", bank="MCB Gulberg", to_print="y",
                     bills=[dict(txn_id="1A2B-123", amount="10")]),
                dict(vendor="Pepsi Co", date="23/10/2026", bank="MCB Gulberg", ref="4587", memo="WHT",
                     bills=[dict(txn_id="1A2B-123", bill_ref="268393", bill_amount="3800", amount="3790",
                                 discount="10", discount_account="Withholding Tax Payable")])],
}


def all_requests():
    out = []
    for kind, raws in SAMPLES.items():
        for raw in raws:
            r = check(kind, raw, None)
            out.append((kind, qbxml.build(r)))
    out.append(("query", qbxml.open_bills_query("Pepsi Co")))
    out.append(("query", qbxml.bills_by_id_query(["1A2B-123", "1A2C-124"])))
    from qbconnector.agent import PRESETS
    for name, q in PRESETS.items():
        out.append((name, q))
    for q in qbxml.lists_query():
        out.append(("query", q))
    return out


def test_schema():
    xsd_dir = os.environ.get("QBXML_XSD_DIR")
    if not xsd_dir:
        print("schema test skipped (QBXML_XSD_DIR not set)")
        return
    from lxml import etree
    schema = etree.XMLSchema(etree.parse(os.path.join(xsd_dir, "qbxmlops130.xsd")))
    bad = 0
    for kind, req in all_requests():
        doc = etree.fromstring(qbxml.envelope(req).split("?>", 2)[2].encode())
        if not schema.validate(doc):
            bad += 1
            print(f"INVALID {kind}: {schema.error_log}\n  {req}\n")
    whole = qbxml.envelope(*[r for _, r in all_requests()])
    assert schema.validate(etree.fromstring(whole.split("?>", 2)[2].encode())), schema.error_log
    assert bad == 0, f"{bad} invalid requests"
    print(f"schema: {len(all_requests())} requests valid")


def test_lists_and_checks():
    resp = """<?xml version="1.0" ?><QBXML><QBXMLMsgsRs>
    <HostQueryRs statusCode="0" statusSeverity="Info" statusMessage="Status OK"><HostRet><ProductName>QB</ProductName></HostRet></HostQueryRs>
    <CompanyQueryRs statusCode="0"><CompanyRet><CompanyName>Arcadian Cafe</CompanyName></CompanyRet></CompanyQueryRs>
    <AccountQueryRs statusCode="0"><AccountRet><FullName>MCB Gulberg</FullName><AccountType>Bank</AccountType></AccountRet>
      <AccountRet><FullName>Sales</FullName><AccountType>Income</AccountType></AccountRet>
      <AccountRet><FullName>Accounts Payable</FullName><AccountType>AccountsPayable</AccountType></AccountRet>
      <AccountRet><FullName>Expenses</FullName><AccountType>Expense</AccountType></AccountRet>
      <AccountRet><FullName>Bank Charges</FullName><AccountType>Expense</AccountType></AccountRet></AccountQueryRs>
    <VendorQueryRs statusCode="0"><VendorRet><Name>Pepsi Co</Name></VendorRet></VendorQueryRs>
    <CustomerQueryRs statusCode="1" statusSeverity="Info" statusMessage="no match"/>
    <ItemQueryRs statusCode="0"><ItemServiceRet><FullName>Pest Control</FullName></ItemServiceRet>
      <ItemInventoryRet><FullName>Bev:7Up</FullName></ItemInventoryRet></ItemQueryRs>
    <ClassQueryRs statusCode="0"><ClassRet><FullName>Store 1</FullName></ClassRet></ClassQueryRs>
    </QBXMLMsgsRs></QBXML>"""
    rs = qbxml.parse_response(resp)
    assert all(r.ok for r in rs)
    L = qbxml.fill_lists(Lists(), rs)
    assert L.company == "Arcadian Cafe" and L.items["Bev:7Up"] == "Inventory Part"
    # exact spelling restored
    r = check("journal", dict(date="1/1/2026", lines=[
        dict(account="bank charges", debit="10", cls="store 1"),
        dict(account="mcb gulberg", credit="10")]), L)
    assert r["lines"][0]["account"] == "Bank Charges" and r["lines"][0]["cls"] == "Store 1"
    # problems reported together
    for kind, raw, expect in [
        ("journal", dict(date="1/1/2026", lines=[dict(account="Bank Charges", debit="10"),
                                                 dict(account="MCB Gulberg", credit="9")]), "not equal"),
        ("journal", dict(date="1/1/2026", lines=[dict(account="Accounts Payable", debit="10"),
                                                 dict(account="MCB Gulberg", credit="10")]), "Name (vendor"),
        ("bill", dict(vendor="Nobody", date="31/02/2026", lines=[]), "not found"),
        ("bill", dict(vendor="Pepsi Co", date="5/11/2026",
                      lines=[dict(kind="Item", target="Pest Control", qty="2", rate="10", amount="25")]),
         "Qty x Rate"),
        ("item", dict(type="Service", name="Pest Control", income_account="Sales"), "already exists"),
        ("item", dict(type="Gadget", name="X"), "not valid"),
        ("item", dict(type="Inventory", name="Y", income_account="Sales"), "COGS Account is required"),
        ("account", dict(name="Expenses:Gas", type="Bank"), "same type"),
        ("cheque", dict(bank="Sales", date="1/1/2026", lines=[dict(target="Sales", amount="1")]),
         "not a Bank"),
        ("vendor", dict(name="x" * 50), "too long"),
    ]:
        try:
            check(kind, raw, L)
        except ValueError as e:
            assert expect in str(e), (kind, expect, str(e))
        else:
            raise AssertionError(f"{kind}: expected error '{expect}'")
    L.add_name("customers", "Askari Bank")
    inv = check("invoice", dict(customer="Askari Bank", date="31/10/2026", cls="Store 1",
                                lines=[dict(item="Pest Control", amount="1000")]), L)
    assert inv["lines"][0]["cls"] == "Store 1" and str(inv["total"]) == "1000.00"
    x = qbxml.build(inv)
    assert "<InvoiceLineAdd><ItemRef><FullName>Pest Control</FullName></ItemRef><ClassRef><FullName>Store 1" in x, x
    # sub-item via name with colon
    r = check("item", dict(type="Service", name="Bev:Tea", income_account="Sales"), None)
    assert r["name"] == "Tea" and r["parent"] == "Bev"
    print("lists & checks ok")


def test_errors_and_ids():
    resp = """<QBXML><QBXMLMsgsRs><BillAddRs requestID="1" statusCode="3140" statusSeverity="Error"
      statusMessage="There is an invalid reference to QuickBooks Vendor &quot;X&quot;"/></QBXMLMsgsRs></QBXML>"""
    rs = qbxml.parse_response(resp)[0]
    assert not rs.ok and rs.code == 3140 and '"X"' in rs.message
    ok = """<QBXML><QBXMLMsgsRs><BillAddRs statusCode="0" statusSeverity="Info" statusMessage="Status OK">
      <BillRet><TxnID>12-345</TxnID></BillRet></BillAddRs></QBXMLMsgsRs></QBXML>"""
    assert qbxml.added_id(qbxml.parse_response(ok)[0]) == "12-345"
    env = qbxml.envelope("<HostQueryRq/>", "<CompanyQueryRq></CompanyQueryRq>")
    assert '<HostQueryRq requestID="1"/>' in env and '<CompanyQueryRq requestID="2">' in env
    # escaping
    r = check("vendor", dict(name='A & B "Traders" <Pvt>'))
    assert "A &amp; B &quot;Traders&quot; &lt;Pvt&gt;" in qbxml.build(r)
    print("errors & ids ok")


def test_paybill_discount():
    from qbconnector import poster
    from qbconnector.demo import FakeQB
    from qbconnector.util import InputError
    raw = dict(vendor="Pepsi Co", date="23/10/2026", bank="MCB Gulberg", ref="4587",
               bills=[dict(txn_id="B-1", bill_ref="INV-9", bill_amount="1000", amount="997.50",
                           discount="2.50", discount_account="Withholding Tax Payable")])
    r = check("paybill", raw)
    assert str(r["total"]) == "997.50" and str(r["discount_total"]) == "2.50"
    x = qbxml.build(r)
    assert ("<TxnID>B-1</TxnID><PaymentAmount>997.50</PaymentAmount><DiscountAmount>2.50</DiscountAmount>"
            "<DiscountAccountRef><FullName>Withholding Tax Payable</FullName></DiscountAccountRef>") in x, x
    # no discount -> no discount elements
    assert "Discount" not in qbxml.build(check("paybill", dict(raw, bills=[dict(txn_id="B-1", amount="5")])))
    # discount needs an account
    try:
        check("paybill", dict(raw, bills=[dict(txn_id="B-1", amount="997.50", discount="2.50")]))
        raise AssertionError("discount without account accepted")
    except InputError as e:
        assert "Discount Account is required" in str(e)
    # payment + discount must equal the voucher's bill amount
    try:
        check("paybill", dict(raw, bills=[dict(txn_id="B-1", bill_amount="1000", amount="990",
                                               discount="2.50", discount_account="WHT")]))
        raise AssertionError("mismatch accepted")
    except InputError as e:
        assert "does not equal the bill amount" in str(e)
    # QuickBooks bill amount checked against the voucher before posting
    qb = FakeQB()
    poster.post(qb, check("paybill", raw), "Test")
    assert any("BillPaymentCheckAdd" in s and "<DiscountAmount>2.50" in s for s in qb.sent)
    qb = FakeQB()
    bad = dict(raw, bills=[dict(txn_id="B-1", bill_amount="1300", amount="1297.50", discount="2.50",
                                discount_account="Withholding Tax Payable")])
    try:
        poster.post(qb, check("paybill", bad), "Test")
        raise AssertionError("amount difference not caught")
    except qbxml.QBError as e:
        assert "Amount differs" in e.message and "1,000.00 in QuickBooks" in e.message and "1,300.00" in e.message
    assert not any("BillPaymentCheckAdd" in s for s in qb.sent)
    print("paybill discount ok")


if __name__ == "__main__":
    test_schema()
    test_lists_and_checks()
    test_errors_and_ids()
    test_paybill_discount()
    print("ALL OK")

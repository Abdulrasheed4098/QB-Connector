"""Excel template -> read -> check -> post (pretend QuickBooks) -> result file -> re-import."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ["APPDATA"] = tempfile.mkdtemp()

from openpyxl import load_workbook  # noqa: E402

from qbconnector import importer, poster, storage  # noqa: E402
from qbconnector.qbxml import QBError  # noqa: E402
from qbconnector.demo import FakeQB  # noqa: E402


def fill(path):
    wb = load_workbook(path)

    def put(sheet, rows):
        ws = wb[sheet]
        heads = [c.value for c in ws[1]]
        for r, row in enumerate(rows, 2):
            for h, v in row.items():
                ws.cell(r, heads.index(h) + 1, v)
    put("Items", [
        {"Type": "Non-inventory", "Name": "Tissue Box", "Income Account": "Stationery Expense"},
        {"Type": "Inventory", "Name": "Pepsi 1.5", "Income Account": "Sales",
         "Expense / COGS Account": "Cost of Goods Sold", "Inventory Asset Account": "Inventory Asset",
         "Cost": 110, "Sales Price": 150},
        {"Type": "Gadget", "Name": "Bad"},                          # error
    ])
    put("Vendors", [{"Name": "Coca Cola", "City": "Lahore", "NTN": "1234567-8"}])
    put("Bills", [
        {"Group": 1, "Vendor": "Pepsi Co", "Date": "05/11/2026", "Ref No": "INV-1", "Line Type": "Item",
         "Account / Item": "7Up 1.5ltr", "Qty": 24, "Rate": 110, "Class": "Store 1"},
        {"Group": 1, "Line Type": "Expense", "Account / Item": "Freight", "Amount": 500},
        {"Group": 2, "Vendor": "Pepsi Co", "Date": "06/11/2026", "Ref No": "INV-2",
         "Account / Item": "Freight", "Amount": "1,250.50"},
    ])
    put("Journal Entries", [
        {"Group": "J1", "Date": "05/11/2026", "Entry No": "JV1", "Account": "Bank Charges", "Debit": 150},
        {"Group": "J1", "Account": "MCB Gulberg", "Credit": 150},
        {"Group": "J2", "Date": "05/11/2026", "Account": "Bank Charges", "Debit": 10},
        {"Group": "J2", "Account": "MCB Gulberg", "Credit": 9},     # unbalanced -> error
    ])
    put("Bill Payments", [
        {"Group": 1, "Vendor": "Pepsi Co", "Date": "07/11/2026", "Bank Account": "MCB Gulberg",
         "Cheque No": "777", "Bill Ref No": "INV-9", "Amount": 1000},
        {"Group": 1, "Bill Ref No": "INV-10", "Amount": 300},
        {"Group": 2, "Vendor": "Pepsi Co", "Date": "07/11/2026", "Bank Account": "MCB Gulberg",
         "Cheque No": "778", "Bill Ref No": "INV-10", "Amount": 400},  # more than open -> rejected
    ])
    put("Transfers", [{"Date": "05/11/2026", "From Account": "MCB Gulberg", "To Account": "Petty Cash",
                       "Amount": 5000}])
    put("Deposits", [{"Group": 1, "Deposit To": "MCB Gulberg", "Date": "05/11/2026",
                      "Received From": "Askari Bank", "From Account": "Bank Discount Receivable",
                      "Line Memo": "Oct", "Amount": 2000}])
    put("Cheques", [{"Bank Account": "MCB Gulberg", "Payee": "Pepsi Co", "Date": "05/11/2026",
                     "Cheque No": "123", "Account / Item": "Freight", "Amount": 99}])
    wb.save(path)


def main():
    d = tempfile.mkdtemp()
    tpl = os.path.join(d, "import.xlsx")
    qb = FakeQB()
    lists = poster.load_lists(qb)
    assert lists.company == "Arcadian Cafe" and "Pepsi Co" in lists.vendors
    importer.make_template(tpl, lists)
    fill(tpl)

    batches, skipped, info = importer.read_workbook(tpl)
    assert skipped == 0
    importer.check_batches(batches, lists)
    by = {(b.sheet, b.row_text): b for b in batches}
    assert by[("Items", "4")].status == "Error" and "not valid" in by[("Items", "4")].error
    assert by[("Journal Entries", "4-5")].status == "Error"
    bill1 = by[("Bills", "2-3")]
    assert bill1.status == "Ready" and len(bill1.record["lines"]) == 2, bill1.error
    assert str(bill1.record["total"]) == "3140.00"
    print("rows:", [(b.sheet, b.row_text, b.status) for b in batches])

    for b in batches:
        if b.status != "Ready":
            continue
        try:
            b.result = poster.post(qb, b.record, "Arcadian Cafe", "Excel")
            b.status = "Added"
        except QBError as e:
            b.status, b.result = "Rejected", e.message
    pay2 = by[("Bill Payments", "4")]
    assert pay2.status == "Rejected" and "only 300.00 unpaid" in pay2.result, pay2.result
    pay1 = by[("Bill Payments", "2-3")]
    assert pay1.status == "Added"
    sent = [x for x in qb.sent if "BillPaymentCheckAdd" in x][0]
    assert "<TxnID>B-1</TxnID><PaymentAmount>1000.00" in sent and "<TxnID>B-2</TxnID><PaymentAmount>300.00" in sent

    out = importer.write_result(tpl, batches)
    assert out.endswith(" - RESULT.xlsx")
    ws = load_workbook(out)["Bills"]
    heads = [c.value for c in ws[1]]
    assert ws.cell(2, heads.index("Status") + 1).value == "Added"

    # re-import the result: Added rows are skipped, errors come back
    b2, skipped2, _ = importer.read_workbook(out)
    assert skipped2 >= 8, skipped2
    assert all(b.raw for b in b2)
    assert {b.sheet for b in b2} == {"Items", "Journal Entries", "Bill Payments"}, [(b.sheet, b.row_text) for b in b2]
    out2 = importer.write_result(out, importer.check_batches(b2, lists))
    assert out2 == out

    log = storage.read_log()
    assert any(r[7] == "Rejected" for r in log) and sum(r[7] == "Added" for r in log) >= 8
    print("log rows:", len(log))
    print("IMPORT OK")


if __name__ == "__main__":
    main()

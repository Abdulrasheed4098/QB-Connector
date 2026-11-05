"""Demo mode: a pretend QuickBooks (used by --demo and by the tests). Nothing real is touched."""
import re


class FakeQB:
    """Answers like QuickBooks would, from a small built-in sample company."""
    file_name = r"D:\Test\Arcadian Test.qbw"

    def __init__(self, reject=None):
        self.sent = []
        self.counter = 100
        self.reject = reject or {}     # {"BillAdd": "message"}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def send(self, xml):
        self.sent.append(xml)
        out = []
        for m in re.finditer(r"<(\w+)Rq( requestID=\"(\d+)\")?", xml):
            tag, rid = m.group(1), m.group(3) or "1"
            if tag == "QBXMLMsgs":
                continue
            out.append(self._answer(tag, rid))
        return "<?xml version=\"1.0\" ?><QBXML><QBXMLMsgsRs>" + "".join(out) + "</QBXMLMsgsRs></QBXML>"

    def _answer(self, tag, rid):
        ok = f'requestID="{rid}" statusCode="0" statusSeverity="Info" statusMessage="Status OK"'
        if tag in self.reject:
            return (f'<{tag}Rs requestID="{rid}" statusCode="3140" statusSeverity="Error" '
                    f'statusMessage="{self.reject[tag]}"/>')
        if tag == "HostQuery":
            return f"<HostQueryRs {ok}><HostRet><ProductName>Fake QB</ProductName></HostRet></HostQueryRs>"
        if tag == "CompanyQuery":
            return f"<CompanyQueryRs {ok}><CompanyRet><CompanyName>Arcadian Cafe</CompanyName></CompanyRet></CompanyQueryRs>"
        if tag == "AccountQuery":
            accts = [("MCB Gulberg", "Bank"), ("Petty Cash", "Bank"), ("Sales", "Income"),
                     ("Accounts Payable", "AccountsPayable"), ("Freight", "Expense"),
                     ("Bank Charges", "Expense"), ("Cost of Goods Sold", "CostOfGoodsSold"),
                     ("Inventory Asset", "OtherCurrentAsset"), ("Stationery Expense", "Expense"),
                     ("Bank Discount Receivable", "OtherCurrentAsset")]
            body = "".join(f"<AccountRet><FullName>{a}</FullName><AccountType>{t}</AccountType></AccountRet>"
                           for a, t in accts)
            return f"<AccountQueryRs {ok}>{body}</AccountQueryRs>"
        if tag == "VendorQuery":
            return f"<VendorQueryRs {ok}><VendorRet><Name>Pepsi Co</Name></VendorRet></VendorQueryRs>"
        if tag == "CustomerQuery":
            return (f"<CustomerQueryRs {ok}><CustomerRet><FullName>Askari Bank</FullName></CustomerRet>"
                    f"<CustomerRet><FullName>MCB Bank</FullName></CustomerRet></CustomerQueryRs>")
        if tag in ("EmployeeQuery", "OtherNameQuery", "TermsQuery"):
            return (f'<{tag}Rs requestID="{rid}" statusCode="1" statusSeverity="Info" '
                    f'statusMessage="A query request did not find a matching object in QuickBooks"/>')
        if tag == "ItemQuery":
            return (f"<ItemQueryRs {ok}><ItemInventoryRet><FullName>7Up 1.5ltr</FullName></ItemInventoryRet>"
                    f"<ItemNonInventoryRet><FullName>A4 Paper Rim</FullName></ItemNonInventoryRet>"
                    f"<ItemOtherChargeRet><FullName>Bank Discount Receivable</FullName></ItemOtherChargeRet></ItemQueryRs>")
        if tag == "ClassQuery":
            return f"<ClassQueryRs {ok}><ClassRet><FullName>Store 1</FullName></ClassRet></ClassQueryRs>"
        if tag == "BillQuery":
            return (f"<BillQueryRs {ok}>"
                    "<BillRet><TxnID>B-1</TxnID><TxnDate>2026-10-01</TxnDate><RefNumber>INV-9</RefNumber>"
                    "<AmountDue>1000.00</AmountDue><OpenAmount>1000.00</OpenAmount></BillRet>"
                    "<BillRet><TxnID>B-2</TxnID><TxnDate>2026-10-05</TxnDate><RefNumber>INV-10</RefNumber>"
                    "<AmountDue>500.00</AmountDue><OpenAmount>300.00</OpenAmount></BillRet>"
                    "</BillQueryRs>")
        if tag.endswith("Add"):
            self.counter += 1
            ret = tag[:-3] + "Ret"
            idtag = "ListID" if tag in ("VendorAdd", "CustomerAdd", "AccountAdd") or tag.startswith("Item") else "TxnID"
            return f"<{tag}Rs {ok}><{ret}><{idtag}>ID-{self.counter}</{idtag}></{ret}></{tag}Rs>"
        return f'<{tag}Rs requestID="{rid}" statusCode="0" statusSeverity="Info" statusMessage="ok"/>'

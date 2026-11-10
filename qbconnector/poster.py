"""Load lists from QuickBooks and post checked records, with logging."""
from decimal import Decimal

from . import qbxml, storage
from .records import KINDS, Lists, describe
from .util import show_date


def load_lists(qb):
    """qb: an open QBConnection (or anything with .send(xml) and .file_name)."""
    answer = qb.send(qbxml.envelope(*qbxml.lists_query(), on_error="continueOnError"))
    rs = qbxml.parse_response(answer)
    bad = [r for r in rs if not r.ok]
    if bad:
        raise qbxml.QBError(bad[0].code, f"{bad[0].tag}: {bad[0].message}")
    lists = Lists(file_path=getattr(qb, "file_name", ""))
    return qbxml.fill_lists(lists, rs)


def open_bills(qb, vendor):
    req = qbxml.open_bills_query(vendor)
    rs = qbxml.parse_response(qb.send(qbxml.envelope(req)))[0]
    if not rs.ok:
        raise qbxml.QBError(rs.code, rs.message, req)
    return qbxml.read_open_bills(rs)


def resolve_bills(qb, record):
    """Bill payments given by Bill Ref No: find the open bill's TxnID."""
    need = [b for b in record["bills"] if not b.get("txn_id")]
    if not need:
        return record
    bills = open_bills(qb, record["vendor"])
    by_ref = {}
    for b in bills:
        by_ref.setdefault(b["ref"].strip().lower(), []).append(b)
    problems = []
    for b in need:
        found = by_ref.get(b["bill_ref"].strip().lower(), [])
        if not found:
            problems.append(f"No unpaid bill with Ref No '{b['bill_ref']}' for vendor '{record['vendor']}'")
        elif len(found) > 1:
            problems.append(f"More than one unpaid bill with Ref No '{b['bill_ref']}' for "
                            f"'{record['vendor']}'; pay it from the Pay Bills screen instead")
        else:
            open_amt = Decimal(found[0]["open_amount"] or "0")
            if b["amount"] + (b.get("discount") or 0) > open_amt:
                problems.append(f"Bill '{b['bill_ref']}' has only {open_amt:,.2f} unpaid, "
                                f"cannot pay {b['amount'] + (b.get('discount') or 0):,.2f}")
            b["txn_id"] = found[0]["txn_id"]
    if problems:
        raise qbxml.QBError("-", "\n".join(problems))
    return record


def check_bill_amounts(qb, record):
    """Before paying: every bill must still be unpaid, payment + discount must fit in the bill,
    and when the voucher gives the bill amount, QuickBooks' bill must have the same amount."""
    ids = [b["txn_id"] for b in record["bills"] if b.get("txn_id")]
    if not ids:
        return record
    req = qbxml.bills_by_id_query(ids)
    rs = qbxml.parse_response(qb.send(qbxml.envelope(req)))[0]
    if not rs.ok:
        raise qbxml.QBError(rs.code, rs.message, req)
    found = {b["txn_id"]: b for b in qbxml.read_open_bills(rs)}
    problems = []
    for b in record["bills"]:
        name = b.get("bill_ref") or b["txn_id"]
        q = found.get(b["txn_id"])
        if q is None:
            problems.append(f"Bill '{name}' not found in QuickBooks")
            continue
        due = Decimal(q["amount_due"] or "0")
        if q.get("is_paid"):
            problems.append(f"Bill '{q['ref'] or name}' is already paid in QuickBooks")
        if b.get("bill_amount") is not None and b["bill_amount"] != due:
            problems.append(f"Amount differs: bill '{q['ref'] or name}' is {due:,.2f} in QuickBooks "
                            f"but {b['bill_amount']:,.2f} on the payment voucher")
        elif b["amount"] + (b.get("discount") or 0) > due:
            problems.append(f"Bill '{q['ref'] or name}' is {due:,.2f}; payment {b['amount']:,.2f} + "
                            f"discount {(b.get('discount') or 0):,.2f} is more than the bill")
    if problems:
        raise qbxml.QBError("-", "\n".join(problems))
    return record


def post(qb, record, company="", source="Screen"):
    """Send one checked record to QuickBooks. Returns the new TxnID/ListID.
    Raises QBError (rejected by QuickBooks) or QBConnectError (connection problem).
    Every attempt is written to the posting log."""
    name, party, amount = describe(record)
    date = show_date(record.get("date", ""))
    label = KINDS[record["kind"]]
    req = ""
    answer = ""
    try:
        if record["kind"] == "paybill":
            resolve_bills(qb, record)
            if any(b.get("discount") or b.get("bill_amount") is not None for b in record["bills"]):
                check_bill_amounts(qb, record)
        req = qbxml.envelope(qbxml.build(record))
        answer = qb.send(req)
        rs = qbxml.parse_response(answer)[0]
        if not rs.ok:
            raise qbxml.QBError(rs.code, rs.message, req, answer)
        new_id = qbxml.added_id(rs)
        storage.log(company, label, name, party, date, amount, "Added", new_id,
                    rs.message if rs.severity == "Warn" else "", source)
        return new_id
    except qbxml.QBError as e:
        path = storage.save_error(record["kind"], req, answer, e.message)
        storage.log(company, label, name, party, date, amount, "Rejected", "",
                    f"{e.message}" + (f" (details: {path})" if path else ""), source)
        raise
    except Exception as e:
        storage.log(company, label, name, party, date, amount, "Failed", "", str(e), source)
        raise

"""Agent Inbox: requests prepared by Claude (or anyone) as JSON files in a folder.

Folder (default Documents\\QB Connector Agent):
  Inbox\\    new requests  <name>.json
  Done\\     requests that were posted or rejected
  Results\\  <name>.result.json  - status of every entry (for Claude to read back)
  lists - <company>.json        - names from QuickBooks, written on every Connect

Request file:
{
  "request_id": "2026-11-05-bank-discount-oct",
  "title": "October bank discount invoices",
  "company": "Arcadian Cafe",            (optional; must match the connected company)
  "records": [
    {"kind": "invoice", "customer": "MCB Bank", "date": "31/10/2026", "ref": "1023",
     "cls": "Store 1", "memo": "Oct 2026 discount share",
     "lines": [{"item": "Bank Discount Receivable", "amount": "45250.50"}]}
  ]
}
kind: invoice, bill, paybill, cheque, journal, deposit, transfer, item, vendor, customer, account
(same fields as the screens; see records.py). Nothing is posted until the user clicks Post.
"""
import datetime as _dt
import json
import os
import shutil

from .importer import Batch
from .records import CHECKERS, KINDS, check
from .util import InputError

HOW_TO = __doc__


def default_folder():
    if os.environ.get("QBC_AGENT_FOLDER"):
        return os.environ["QBC_AGENT_FOLDER"]
    return os.path.join(os.path.expanduser("~"), "Documents", "QB Connector Agent")


def ensure(folder):
    for sub in ("Inbox", "Done", "Results"):
        os.makedirs(os.path.join(folder, sub), exist_ok=True)
    readme = os.path.join(folder, "HOW_TO.txt")
    if not os.path.exists(readme):
        with open(readme, "w", encoding="utf-8") as f:
            f.write(HOW_TO)
    return folder


class Request:
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.mtime = os.path.getmtime(path)
        self.received = _dt.datetime.fromtimestamp(self.mtime)
        self.data = {}
        self.error = None
        self.batches = []
        try:
            with open(path, encoding="utf-8-sig") as f:
                self.data = json.load(f)
            if not isinstance(self.data, dict) or not isinstance(self.data.get("records"), list):
                raise ValueError("file must contain a 'records' list")
        except Exception as e:
            self.error = f"Cannot read request: {e}"
        self.title = str(self.data.get("title") or os.path.splitext(self.name)[0])
        self.company = str(self.data.get("company") or "")
        self.request_id = str(self.data.get("request_id") or os.path.splitext(self.name)[0])

    def build(self, lists):
        """Check every record against the connected company's lists."""
        self.batches = []
        if self.error:
            return self.batches
        wrong_company = (lists is not None and self.company
                         and self.company.strip().lower() != (lists.company or "").strip().lower())
        for i, raw in enumerate(self.data.get("records") or [], 1):
            raw = dict(raw or {})
            kind = str(raw.pop("kind", "")).strip().lower()
            b = Batch(self.title, kind if kind in CHECKERS else "item", [i], raw)
            b.kind = kind
            if kind not in CHECKERS:
                b.status, b.error = "Error", f"Unknown kind '{kind}'. Use one of: {', '.join(KINDS)}"
            elif wrong_company:
                b.status = "Error"
                b.error = (f"This request is for '{self.company}' but QuickBooks is connected to "
                           f"'{lists.company}'. Open the right company file.")
            else:
                try:
                    b.record = check(kind, raw, lists)
                    b.status = "Ready"
                except InputError as e:
                    b.status, b.error = "Error", str(e)
            b.result = (b.error or "").replace("\n", " | ")
            self.batches.append(b)
        return self.batches


def pending(folder):
    inbox = os.path.join(folder, "Inbox")
    try:
        names = sorted(n for n in os.listdir(inbox) if n.lower().endswith(".json"))
    except OSError:
        return []
    return [os.path.join(inbox, n) for n in names]


def already_posted(folder, request_id):
    """True if a result for this request_id already shows posted entries (avoid double posting)."""
    rdir = os.path.join(folder, "Results")
    try:
        for n in os.listdir(rdir):
            if not n.endswith(".result.json"):
                continue
            try:
                with open(os.path.join(rdir, n), encoding="utf-8") as f:
                    r = json.load(f)
            except Exception:
                continue
            if r.get("request_id") == request_id and any(e.get("status") == "Added"
                                                         for e in r.get("entries", [])):
                return True
    except OSError:
        pass
    return False


def finish(folder, req, company, outcome):
    """Write the result file and move the request to Done. outcome: 'Posted' or 'Rejected'."""
    stem = os.path.splitext(req.name)[0]
    entries = []
    for b in req.batches:
        e = {"no": b.rows[0], "kind": b.kind, "status": b.status if outcome == "Posted" or b.status == "Error"
             else "Not posted (rejected by user)"}
        if b.status == "Added":
            e["quickbooks_id"] = b.result
        else:
            e["message"] = b.result or b.error or ""
        if b.record:
            e["total"] = str(b.record.get("total")) if b.record.get("total") is not None else None
            e["ref"] = b.record.get("ref")
            e["name"] = b.record.get("customer") or b.record.get("vendor") or b.record.get("payee") \
                or b.record.get("name")
        entries.append(e)
    result = {
        "request_id": req.request_id, "title": req.title, "file": req.name, "outcome": outcome,
        "company": company, "finished_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "added": sum(1 for b in req.batches if b.status == "Added"),
        "entries": entries,
    }
    rpath = os.path.join(folder, "Results", f"{stem}.result.json")
    with open(rpath, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    dest = os.path.join(folder, "Done", req.name)
    if os.path.exists(dest):
        dest = os.path.join(folder, "Done", f"{stem}_{_dt.datetime.now():%Y%m%d%H%M%S}.json")
    try:
        shutil.move(req.path, dest)
    except OSError:
        pass
    return rpath


def write_check(folder, req, company, note=""):
    """Automatic posting skipped a request: write what is wrong so Claude can fix it."""
    stem = os.path.splitext(req.name)[0]
    data = {"request_id": req.request_id, "title": req.title, "file": req.name, "company": company,
            "outcome": "Needs review (not posted)", "note": note or req.error or "",
            "checked_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "entries": [{"no": b.rows[0], "kind": b.kind, "status": b.status,
                         "message": b.error or ""} for b in req.batches]}
    try:
        with open(os.path.join(folder, "Results", f"{stem}.check.json"), "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except OSError:
        pass


def write_lists(folder, lists):
    """Snapshot of QuickBooks names so Claude can prepare entries with exact spellings."""
    try:
        ensure(folder)
        data = {
            "company": lists.company, "file": lists.file_path,
            "saved_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "accounts": [{"name": n, "type": t} for n, t in sorted(lists.accounts.items(), key=lambda x: x[0].lower())],
            "items": [{"name": n, "type": t} for n, t in sorted(lists.items.items(), key=lambda x: x[0].lower())],
            "customers": lists.names("customers"), "vendors": lists.names("vendors"),
            "employees": lists.names("employees"), "other_names": lists.names("othernames"),
            "classes": lists.names("classes"), "terms": lists.names("terms"),
        }
        safe = "".join(ch for ch in (lists.company or "company") if ch.isalnum() or ch in " -_").strip()
        path = os.path.join(folder, f"lists - {safe}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
        return path
    except OSError:
        return ""

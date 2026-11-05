"""--selftest: open the real window in demo mode, fill every screen, save, check the log.
Used by the build to prove the packaged app works. Writes selftest.txt."""
import os
import sys
import tempfile
import time


def run():
    os.environ["APPDATA"] = tempfile.mkdtemp()
    out = []
    ok = True

    def note(s):
        out.append(s)

    try:
        if sys.platform == "win32":
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401
            note("pywin32 ok")
        import openpyxl
        note(f"openpyxl {openpyxl.__version__}")
        from .. import storage
        storage.FOLDER = os.environ["APPDATA"]
        storage.LOG_FILE = os.path.join(storage.FOLDER, "posting_log.csv")
        storage.ERROR_FOLDER = os.path.join(storage.FOLDER, "errors")
        storage.SETTINGS_FILE = os.path.join(storage.FOLDER, "settings.json")
        agent_dir = os.path.join(os.environ["APPDATA"], "agent")
        os.environ["QBC_AGENT_FOLDER"] = agent_dir
        from .app import App
        app = App(demo=True)
        msgs = []
        app.confirm = lambda t, m: True
        app.notify = lambda t, m: msgs.append(("info", t, m))
        app.error = lambda t, m: msgs.append(("error", t, m))
        app.update()

        def wait():
            t0 = time.time()
            while app.busy and time.time() - t0 < 20:
                app.update()
                time.sleep(0.02)
            app.update()

        app.connect()
        wait()
        assert app.lists and app.lists.company == "Arcadian Cafe", "lists not loaded"
        note(f"lists: {app.lists.summary()}")
        tabs = {type(t).__name__: t for t in app.tabs}

        # --- Agent Inbox: a request file arrives, is checked, posted, and a result is written
        import json
        assert os.path.exists(os.path.join(agent_dir, "lists - Arcadian Cafe.json")), "lists snapshot missing"
        req = {"request_id": "test-1", "title": "Oct bank discount", "company": "Arcadian Cafe",
               "records": [
                   {"kind": "invoice", "customer": "MCB Bank", "date": "31/10/2026", "ref": "ARC-1023",
                    "cls": "Store 1", "lines": [{"item": "Bank Discount Receivable", "amount": "45250.50"}]},
                   {"kind": "invoice", "customer": "Nobody Bank", "date": "31/10/2026",
                    "lines": [{"item": "Bank Discount Receivable", "amount": "1"}]},
                   {"kind": "teleport"}]}
        with open(os.path.join(agent_dir, "Inbox", "req1.json"), "w") as f:
            json.dump(req, f)
        ag = tabs["AgentTab"]
        ag.scan()
        assert ag.current and [b.status for b in ag.batches] == ["Ready", "Error", "Error"], \
            [(b.status, b.error) for b in ag.batches]
        ag.post()
        wait()
        res = json.load(open(os.path.join(agent_dir, "Results", "req1.result.json")))
        assert res["added"] == 1 and res["entries"][0]["status"] == "Added", res
        assert os.path.exists(os.path.join(agent_dir, "Done", "req1.json")) and not ag.requests
        sent = open(storage.LOG_FILE, encoding="utf-8-sig").read()
        assert "ARC-1023" in sent and "Agent" in sent
        note("agent inbox ok")
        # automatic posting: a correct request posts by itself, a wrong one waits with a .check.json
        ag.auto_var.set(True)
        ag._auto_changed()
        good = {"request_id": "auto-1", "title": "auto", "company": "Arcadian Cafe", "records": [
            {"kind": "invoice", "customer": "MCB Bank", "date": "03/11/2026", "ref": "2026-10-08",
             "cls": "Store 1", "lines": [{"item": "Bank Discount Receivable", "amount": "10"}]}]}
        bad = {"request_id": "auto-2", "title": "auto bad", "records": [{"kind": "invoice", "customer": "X"}]}
        for nm, d in (("auto1.json", good), ("auto2.json", bad)):
            with open(os.path.join(agent_dir, "Inbox", nm), "w") as f:
                json.dump(d, f)
        ag.scan(quiet=True)
        t0 = time.time()
        while time.time() - t0 < 10 and not os.path.exists(os.path.join(agent_dir, "Results", "auto1.result.json")):
            app.update()
            time.sleep(0.05)
        wait()
        r1 = json.load(open(os.path.join(agent_dir, "Results", "auto1.result.json")))
        assert r1["added"] == 1, r1
        assert os.path.exists(os.path.join(agent_dir, "Results", "auto2.check.json"))
        assert os.path.exists(os.path.join(agent_dir, "Inbox", "auto2.json"))
        ag.auto_var.set(False)
        ag._auto_changed()
        note("agent auto-post ok")
        # remove the agent's invoice from the count below
        with open(storage.LOG_FILE, encoding="utf-8-sig") as f:
            lines = f.read().splitlines()
        with open(storage.LOG_FILE, "w", encoding="utf-8-sig") as f:
            f.write("\n".join(ln for ln in lines if ",Agent" not in ln) + "\n")

        inv = tabs["InvoiceTab"]
        inv.f.set("customer", "MCB Bank")
        inv.f.set("ref", "DC-OCT")
        inv.grid.set_row(inv.grid.rows[0], {"amount": "45250.50"})
        inv.save()
        wait()

        bill = tabs["BillTab"]
        bill.f.set("vendor", "Pepsi Co")
        bill.f.set("ref", "INV-1")
        bill.grid.set_row(bill.grid.rows[0], {"kind": "Item", "target": "7Up 1.5ltr", "qty": "24", "rate": "110"})
        bill.grid.set_row(bill.grid.rows[1], {"kind": "Expense", "target": "Freight", "amount": "500"})
        bill.save()
        wait()

        chq = tabs["ChequeTab"]
        chq.f.set("bank", "MCB Gulberg")
        chq.f.set("payee", "Pepsi Co")
        chq.f.set("ref", "123")
        chq.grid.set_row(chq.grid.rows[0], {"target": "Freight", "amount": "99"})
        chq.save()
        wait()

        je = tabs["JournalTab"]
        je.grid.set_row(je.grid.rows[0], {"account": "Bank Charges", "debit": "150"})
        je.grid.set_row(je.grid.rows[1], {"account": "MCB Gulberg", "credit": "150"})
        je.save()
        wait()

        dep = tabs["DepositTab"]
        dep.f.set("account", "MCB Gulberg")
        dep.grid.set_row(dep.grid.rows[0], {"from_account": "Sales", "amount": "1000"})
        dep.save()
        wait()

        tr = tabs["TransferTab"]
        tr.f.set("from_account", "MCB Gulberg")
        tr.f.set("to_account", "Petty Cash")
        tr.f.set("amount", "5000")
        tr.save()
        wait()

        it = tabs["ItemTab"]
        it.f.set("type", "Service")
        it.update_fields()
        it.f.set("name", "Pest Control")
        it.g.set("income_account", "Freight")
        it.save()
        wait()

        ven = tabs["VendorTab"]
        ven.f.set("name", "Coca Cola")
        ven.save()
        wait()

        acc = tabs["AccountTab"]
        acc.f.set("name", "Gas Bill")
        acc.save()
        wait()

        cus = tabs["CustomerTab"]
        cus.f.set("name", "UBL Bank")
        cus.save()
        wait()

        pb = tabs["PayBillsTab"]
        pb.vf.set("vendor", "pepsi co")
        pb.load_bills()
        wait()
        assert len(pb.bills) == 2, "open bills not shown"
        pb.mark_all(True)
        pb.f.set("bank", "MCB Gulberg")
        pb.f.set("ref", "777")
        pb.save()
        wait()

        # a mistake must be caught before posting
        bad = tabs["TransferTab"]
        bad.f.set("from_account", "MCB Gulberg")
        bad.f.set("to_account", "MCB Gulberg")
        bad.f.set("amount", "1")
        import tkinter.messagebox as mb
        caught = []
        orig = mb.showerror
        mb.showerror = lambda t, m, **k: caught.append(m)
        bad.save()
        mb.showerror = orig
        assert caught and "cannot be the same" in caught[0], caught

        errors = [m for m in msgs if m[0] == "error"]
        assert not errors, errors
        log = storage.read_log()
        added = [r for r in log if r[7] == "Added"]
        note(f"saved: {len(added)} records -> " + ", ".join(sorted({r[2] for r in added})))
        assert len(added) == 11, f"expected 11 added, got {len(added)}: {log}"

        tpl = os.path.join(os.environ["APPDATA"], "tpl.xlsx")
        from .. import importer
        importer.make_template(tpl, app.lists)
        note("template ok")
        app.destroy()
        note("SELFTEST OK")
    except Exception:
        import traceback
        ok = False
        note("SELFTEST FAILED\n" + traceback.format_exc())
    text = "\n".join(out)
    try:
        with open("selftest.txt", "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass
    print(text)
    return 0 if ok else 1

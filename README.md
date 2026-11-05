# Arcadian QB Connector

Adds lists and transactions to **QuickBooks Desktop** (built for Enterprise Solutions 15.0 / 2015)
through the official QuickBooks SDK. You don't need to type entries into QuickBooks by hand.

## What it can add
| Lists | Transactions |
|---|---|
| Items: Inventory Part, Non-inventory Part, Service, Other Charge (incl. sub-items) | Enter Bill (expense and item lines, class, customer:job) |
| Vendors (address, NTN, terms, opening balance) | Pay Bills (shows the vendor's unpaid bills; full or part payment) |
| Customers / Jobs | Create Invoice (bank discount claims: bank as Customer:Job, Class, Bank Discount Receivable item; "ARC" is removed from invoice numbers) |
| | Write Cheque (or "To be printed") |
| Accounts (all types, sub-accounts, opening balance) | Journal Entry (checks debits = credits) |
| | Make Deposit |
| | Transfer Funds |

Plus **Excel bulk import** for all of the above (template included), and a **posting log**.

Every entry is checked before it's sent: names must exist in QuickBooks, dates are DD/MM/YYYY,
journal entries must balance, and lengths are kept within QuickBooks' limits. Anything QuickBooks
rejects shows QuickBooks' own message, and nothing is saved for that entry.

## Install
1. GitHub → **Releases** → latest → download `QBConnector-Setup-x.y.z.exe` and run it.
   ("Windows protected your PC" → More info → Run anyway.)
2. The QuickBooks SDK (32-bit) must be installed on the same PC.

## First use
1. Open QuickBooks, log in as **Admin**, and open the company file.
2. Start Arcadian QB Connector → **Connect & Load Lists**.
3. The first time, QuickBooks asks about the certificate: choose **"Yes, always; allow access even if
   QuickBooks is not running"**, log in as Admin → Continue → Done.
4. **Files…** → add your company files (Arcadian Cafe, AVERTICAL) to switch between them.
   "Currently open file" uses whatever is open in QuickBooks.

**Practice mode:** Start menu → *Arcadian QB Connector (Demo)* runs every screen against a pretend
company. Nothing real is touched.

## Excel import
Excel Import → *Create blank template* (after connecting, it includes a **QuickBooks Lists** sheet with
all your exact names) → fill it → *Choose Excel file* → check the rows → **Post Ready rows**.
For transactions with several lines, give the rows the same **Group** number.
A `... - RESULT.xlsx` copy is saved with a Status for every row. Fix any errors in it and import it
again; rows already marked **Added** are skipped, so nothing is posted twice.

## Data
`%APPDATA%\ArcadianQBConnector\`: `settings.json`, `posting_log.csv`, and `errors\` (the exact
request and answer for every rejected entry).

## For developers
32-bit Python 3.11 (`pip install -r requirements.txt`), then `python main.py` (or `--demo`).
Tests: `python tests/test_qbxml.py` (set `QBXML_XSD_DIR` to the SDK's xsd folder to validate every
request against Intuit's qbXML 13.0 schema), `python tests/test_import.py`, `python main.py --selftest`.
GitHub Actions builds the installer on every push to `main`.

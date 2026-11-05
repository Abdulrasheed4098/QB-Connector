"""Settings, posting log and error files, kept in %APPDATA%\\ArcadianQBConnector."""
import csv
import datetime as _dt
import json
import os

FOLDER = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "ArcadianQBConnector")
LOG_FILE = os.path.join(FOLDER, "posting_log.csv")
SETTINGS_FILE = os.path.join(FOLDER, "settings.json")
ERROR_FOLDER = os.path.join(FOLDER, "errors")

LOG_COLUMNS = ["Time", "Company", "Type", "Name / Ref", "Party / Detail", "Date", "Amount",
               "Status", "QuickBooks ID", "Message", "Source"]

CURRENT_FILE = "Currently open file in QuickBooks"

DEFAULT_SETTINGS = {
    "company_files": [],        # [{"label": "Arcadian Cafe", "path": "D:\\...qbw"}]
    "last_company": CURRENT_FILE,
}


def _ensure():
    os.makedirs(FOLDER, exist_ok=True)


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            s = json.load(f)
        return {**DEFAULT_SETTINGS, **s}
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_settings(s):
    try:
        _ensure()
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(s, f, indent=2)
    except OSError:
        pass


def log(company, kind_label, name, party, date, amount, status, qb_id, message, source):
    _ensure()
    new = not os.path.exists(LOG_FILE)
    with open(LOG_FILE, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new:
            w.writerow(LOG_COLUMNS)
        w.writerow([_dt.datetime.now().strftime("%d/%m/%Y %H:%M:%S"), company, kind_label, name,
                    party, date, "" if amount is None else f"{amount:.2f}", status, qb_id,
                    (message or "").replace("\n", " | "), source])


def read_log(limit=2000):
    try:
        with open(LOG_FILE, newline="", encoding="utf-8-sig") as f:
            rows = list(csv.reader(f))
    except OSError:
        return []
    return rows[1:][-limit:][::-1]


def save_error(kind, request, response, message):
    """Keep the exact request/answer of a rejected posting so it can be checked later."""
    try:
        os.makedirs(ERROR_FOLDER, exist_ok=True)
        name = _dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f") + f"_{kind}.txt"
        path = os.path.join(ERROR_FOLDER, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"ERROR: {message}\n\n--- REQUEST ---\n{request}\n\n--- ANSWER ---\n{response or ''}\n")
        return path
    except OSError:
        return ""

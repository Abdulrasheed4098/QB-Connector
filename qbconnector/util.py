"""Small helpers: dates (DD/MM/YYYY), amounts, names."""
import datetime as _dt
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

TWO = Decimal("0.01")


class InputError(ValueError):
    """A value typed by the user (or in Excel) is not valid."""


def is_blank(v):
    return v is None or (isinstance(v, str) and v.strip() == "")


def clean(v):
    """Text value, trimmed. None for blanks. Numbers from Excel lose a trailing .0"""
    if is_blank(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def parse_date(v, field="Date", required=True):
    """Accept DD/MM/YYYY, DD-MM-YYYY, DD.MM.YYYY, DD/MM/YY, YYYY-MM-DD or a date object.
    Returns QuickBooks format YYYY-MM-DD (or None)."""
    if is_blank(v):
        if required:
            raise InputError(f"{field} is required (DD/MM/YYYY)")
        return None
    if isinstance(v, _dt.datetime):
        return v.date().isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    s = str(v).strip().split(" ")[0]
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})", s)
        if not m:
            raise InputError(f"{field} '{v}' is not a date. Use DD/MM/YYYY")
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
    try:
        return _dt.date(y, mo, d).isoformat()
    except ValueError:
        raise InputError(f"{field} '{v}' is not a valid date. Use DD/MM/YYYY")


def show_date(iso):
    """YYYY-MM-DD -> DD/MM/YYYY for display."""
    if not iso:
        return ""
    try:
        return _dt.date.fromisoformat(str(iso)[:10]).strftime("%d/%m/%Y")
    except ValueError:
        return str(iso)


def today_str():
    return _dt.date.today().strftime("%d/%m/%Y")


def parse_amount(v, field="Amount", required=True, allow_zero=False, allow_negative=False):
    """'1,234.5' / 1234.5 / 'Rs. 1,234' -> Decimal('1234.50')"""
    if is_blank(v):
        if required:
            raise InputError(f"{field} is required")
        return None
    if isinstance(v, (int, float, Decimal)):
        d = Decimal(str(v))
    else:
        s = str(v).strip().replace(",", "")
        s = re.sub(r"^(rs\.?|pkr)\s*", "", s, flags=re.I)
        neg = s.startswith("(") and s.endswith(")")
        s = s.strip("()")
        try:
            d = Decimal(s)
        except InvalidOperation:
            raise InputError(f"{field} '{v}' is not a number")
        if neg:
            d = -d
    d = d.quantize(TWO, rounding=ROUND_HALF_UP)
    if d < 0 and not allow_negative:
        raise InputError(f"{field} cannot be negative ({v})")
    if d == 0 and not allow_zero:
        if required:
            raise InputError(f"{field} cannot be zero")
        return None
    return d


def parse_qty(v, field="Qty"):
    if is_blank(v):
        return None
    try:
        d = Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        raise InputError(f"{field} '{v}' is not a number")
    return d.quantize(Decimal("0.00001")).normalize()


def fmt_amount(d):
    """Decimal -> '1234.50' for qbXML."""
    return f"{Decimal(d).quantize(TWO, rounding=ROUND_HALF_UP):.2f}"


def fmt_qty(d):
    s = format(Decimal(d).normalize(), "f")
    return s


def money(d):
    """Display: 1,234,567.50"""
    if d is None:
        return ""
    return f"{Decimal(d):,.2f}"


def split_name(full, parent=None):
    """'Beverages:7Up' -> ('7Up', 'Beverages'). A separate parent wins if given."""
    full = clean(full) or ""
    parent = clean(parent)
    if ":" in full and not parent:
        parts = [p.strip() for p in full.split(":")]
        return parts[-1], ":".join(parts[:-1])
    return full, parent


def parse_bool(v, default=False):
    if is_blank(v):
        return default
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("y", "yes", "true", "1", "x", "tick", "✓")

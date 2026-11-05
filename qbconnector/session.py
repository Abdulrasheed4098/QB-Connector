"""Talk to QuickBooks Desktop through the SDK request processor (QBXMLRP2, 32-bit COM).

Use as:   with QBConnection(company_file) as qb:  answer = qb.send(xml)
company_file "" = the company file currently open in QuickBooks.
"""
from . import APP_NAME

LOCAL_QBD = 1
FILE_MODE_DONT_CARE = 2     # works whether the file is open single- or multi-user

# Known SDK error codes -> plain advice
HINTS = {
    0x80040400: "QuickBooks could not read the request (please send the error file to support).",
    0x80040401: "Could not access the QuickBooks SDK. Reinstall the QuickBooks SDK (32-bit).",
    0x80040402: "Unexpected error. Restart QuickBooks and try again.",
    0x80040403: "Could not open the company file. Check the file path, or choose 'Currently open file'.",
    0x80040408: "Could not start QuickBooks. Open QuickBooks yourself, log in, and try again.",
    0x8004040A: "QuickBooks could not open that company file. Open it in QuickBooks first.",
    0x8004040D: "The connection to QuickBooks was lost. Try again.",
    0x80040410: "QuickBooks is open in a different mode. Switch to single-user mode and try again.",
    0x80040414: "A window or message is open inside QuickBooks. Close it (press Esc in QuickBooks) and try again.",
    0x80040416: "A different company file is open in QuickBooks. Open the right file, or choose "
                "'Currently open file' in this app.",
    0x80040417: "No company file is open in QuickBooks and none was selected. Open the company file in QuickBooks.",
    0x80040418: "This app has not been authorised yet. Log in to QuickBooks as Admin in single-user "
                "mode and try again, then answer 'Yes, always'.",
    0x8004041A: "This app is not allowed to access the company file. In QuickBooks go to Edit > "
                "Preferences > Integrated Applications > Company Preferences, tick 'Arcadian QB "
                "Connector' and remove 'Don't allow any applications'.",
    0x8004041D: "This app is not allowed to log in automatically. In QuickBooks: Edit > Preferences > "
                "Integrated Applications > select 'Arcadian QB Connector' > Properties > tick "
                "'Allow this application to login automatically' and choose Admin.",
    0x80040430: "This app is not allowed to log in to this company file automatically. In QuickBooks "
                "(logged in as Admin, single-user): Edit > Preferences > Integrated Applications > "
                "Company Preferences > select 'Arcadian QB Connector' > Properties > tick 'Allow this "
                "application to login automatically', choose Admin, OK. Or open the file in QuickBooks "
                "and choose 'Currently open file' here.",
    0x80040420: "QuickBooks needs a user to log in first. Open QuickBooks, log in, and try again.",
    0x80040422: "Another program is using QuickBooks in single-user mode. Close it and try again.",
    0x80040424: "QuickBooks is busy (another program or a backup is running). Try again in a minute.",
}


class QBConnectError(Exception):
    def __init__(self, step, code, text):
        self.step, self.code, self.text = step, code, text
        hint = HINTS.get(code, "")
        msg = f"{step} failed"
        if code:
            msg += f" (error 0x{code:08X})"
        msg += f": {text}"
        if hint:
            msg += f"\n\n{hint}"
        super().__init__(msg)


def _com_code(e):
    """Pull the real HRESULT out of a pywin32 com_error."""
    try:
        hr, text, exc, _ = e.args
        if exc and exc[5]:
            code = exc[5]
            text = exc[2] or text
        else:
            code = hr
        return code & 0xFFFFFFFF, str(text or "").strip()
    except Exception:
        return 0, str(e)


class QBConnection:
    def __init__(self, company_file=""):
        self.company_file = company_file or ""
        self.rp = None
        self.ticket = None
        self.file_name = ""

    def __enter__(self):
        import pythoncom
        import win32com.client
        pythoncom.CoInitialize()
        step = "Loading the QuickBooks SDK"
        try:
            self.rp = win32com.client.Dispatch("QBXMLRP2.RequestProcessor")
            step = "Connecting to QuickBooks"
            self.rp.OpenConnection2("", APP_NAME, LOCAL_QBD)
            step = "Opening the company file"
            self.ticket = self.rp.BeginSession(self.company_file, FILE_MODE_DONT_CARE)
            self.file_name = self.rp.GetCurrentCompanyFileName(self.ticket)
        except Exception as e:
            code, text = _com_code(e)
            self._close()
            raise QBConnectError(step, code, text) from None
        return self

    def send(self, xml):
        try:
            return self.rp.ProcessRequest(self.ticket, xml)
        except Exception as e:
            code, text = _com_code(e)
            raise QBConnectError("Sending to QuickBooks", code, text) from None

    def _close(self):
        try:
            if self.rp is not None and self.ticket:
                self.rp.EndSession(self.ticket)
        except Exception:
            pass
        try:
            if self.rp is not None:
                self.rp.CloseConnection()
        except Exception:
            pass
        self.ticket = None
        self.rp = None

    def __exit__(self, *exc):
        self._close()
        try:
            import pythoncom
            pythoncom.CoUninitialize()
        except Exception:
            pass
        return False

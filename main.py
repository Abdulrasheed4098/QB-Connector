"""Arcadian QB Connector - start here.
    python main.py            normal use
    python main.py --demo     try the screens with a pretend QuickBooks (nothing real is touched)
    python main.py --selftest automatic check used by the build
"""
from qbconnector.ui.app import main

if __name__ == "__main__":
    main()

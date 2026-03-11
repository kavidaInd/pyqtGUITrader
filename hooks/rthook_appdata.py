"""
hooks\rthook_appdata.py
=======================
PyInstaller runtime hook — runs before any app code.

Ensures the app stores user data (config, DB, logs) in
  %APPDATA%\TradingAssistant\
instead of the install directory (which may be read-only
when installed to Program Files).

Import this via trading_assistant.spec's runtime_hooks list:
    runtime_hooks=["hooks/rthook_appdata.py"]

Usage in your app code:
    import os, sys
    APP_DATA_DIR = os.environ.get("TRADING_APPDATA", os.path.dirname(sys.executable))
"""

import os
import sys

# Determine user data directory
if sys.platform == "win32":
    _appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    _user_dir = os.path.join(_appdata, "TradingAssistant")
else:
    _user_dir = os.path.join(os.path.expanduser("~"), ".TradingAssistant")

# Create the directory if it doesn't exist
os.makedirs(_user_dir, exist_ok=True)

# Expose via environment variable so app code can read it
os.environ["TRADING_APPDATA"] = _user_dir

# Sub-directories
os.makedirs(os.path.join(_user_dir, "logs"),    exist_ok=True)
os.makedirs(os.path.join(_user_dir, "config"),  exist_ok=True)
os.makedirs(os.path.join(_user_dir, "backups"), exist_ok=True)
# trading_assistant.spec
import sys
import os
from pathlib import Path

ROOT = Path(SPECPATH)

# --------------------------------------------------------------------------
# Hidden imports
# --------------------------------------------------------------------------
hidden_imports = [
    # Internal broker modules (loaded dynamically via importlib)
    "broker.FyersBroker",
    "broker.ZerodhaBroker",
    "broker.DhanBroker",
    "broker.AngelOneBroker",
    "broker.UpstoxBroker",
    "broker.ShoonyaBroker",
    "broker.AliceBlueBroker",
    "broker.FlattradeBroker",
    # PyQt5
    "PyQt5.QtPrintSupport",
    "PyQt5.QtSvg",
    "PyQt5.QtCore",
    "PyQt5.QtGui",
    "PyQt5.QtWidgets",
    # SQLAlchemy (sqlite only - no postgres/mysql needed)
    "sqlalchemy.dialects.sqlite",
    "sqlalchemy.dialects.sqlite.pysqlite",
    "sqlalchemy.orm",
    "sqlalchemy.ext.declarative",
    # pandas internals
    "pandas._libs.tslibs.base",
    "pandas._libs.tslibs.np_datetime",
    "pandas._libs.tslibs.nattype",
    "pandas._libs.tslibs.timestamps",
    # Auth / crypto
    "pyotp",
    "cryptography.hazmat.primitives.kdf.pbkdf2",
    "cryptography.hazmat.backends.openssl",
    # Networking
    "requests",
    "urllib3",
    "certifi",
    # Broker SDKs (included regardless - missing ones are ignored at runtime)
    "fyers_apiv3",
    "fyers_apiv3.FyersWebsocket",
    "kiteconnect",
    "dhanhq",
    "SmartApi",
    "SmartApi.smartConnect",
    "logzero",
    "upstox_client",
    "NorenRestApiPy",
    "NorenRestApiPy.NorenApi",
    "pkg_resources",
    "packaging",
    "packaging.version",
]

# --------------------------------------------------------------------------
# Data files
# --------------------------------------------------------------------------
datas = []

for p in ROOT.rglob("*.json"):
    if any(x in str(p) for x in ["backups", "__pycache__", "dist", "build"]):
        continue
    rel = str(p.parent.relative_to(ROOT))
    datas.append((str(p), rel))

for ext in ("*.png", "*.ico", "*.svg", "*.icns"):
    for p in ROOT.rglob(ext):
        if any(x in str(p) for x in ["__pycache__", "dist", "build"]):
            continue
        rel = str(p.parent.relative_to(ROOT))
        datas.append((str(p), rel))

# --------------------------------------------------------------------------
# Platform settings
# --------------------------------------------------------------------------
is_windows = sys.platform == "win32"
is_mac     = sys.platform == "darwin"

icon_path = None
if is_windows and (ROOT / "assets" / "icon.ico").exists():
    icon_path = str(ROOT / "assets" / "icon.ico")
elif is_mac and (ROOT / "assets" / "icon.icns").exists():
    icon_path = str(ROOT / "assets" / "icon.icns")

# --------------------------------------------------------------------------
# Analysis
# --------------------------------------------------------------------------
a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[str(ROOT / "hooks")],
    hooksconfig={},
    runtime_hooks=[str(ROOT / "hooks" / "rthook_appdata.py")],
    excludes=[
        "matplotlib",
        "scipy",
        "tkinter",
        "_tkinter",
        "test",
        "unittest",
        "IPython",
        "jupyter",
        "notebook",
        "statsmodels",
        "sklearn",
        "scikit_learn",
        "twisted",
        "boto3",
        "botocore",
        "awscrt",
        "wx",
        "gi",
        # Exclude breeze_connect from analysis entirely - it makes network
        # calls at module level (urlopen in __init__) which crash PyInstaller.
        # It is bundled separately via the hooks/rthook approach below.
        "breeze_connect",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=None,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TradingAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=is_mac,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TradingAssistant",
)

if is_mac:
    app = BUNDLE(
        coll,
        name="TradingAssistant.app",
        icon=icon_path,
        bundle_identifier="com.tradingassistant.app",
        info_plist={
            "CFBundleDisplayName": "Trading Assistant",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
        },
    )

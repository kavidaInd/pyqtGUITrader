# trading_assistant.spec
# ======================
# PyInstaller spec for building a single-folder native executable.
#
# Usage:
#   pip install pyinstaller
#   pyinstaller trading_assistant.spec
#
# Output: dist/TradingAssistant/   (folder you can zip and distribute)
#
# Platform notes:
#   Windows : produces TradingAssistant.exe  (no console window)
#   macOS   : produces TradingAssistant.app  (run `open dist/TradingAssistant.app`)
#   Linux   : produces TradingAssistant      (ELF binary, requires libQt5 on PATH)
#
# To create a macOS .dmg:
#   brew install create-dmg
#   create-dmg dist/TradingAssistant.app
#
# To create a Windows installer with NSIS:
#   See scripts/make_installer_win.nsi

import sys
import os
from pathlib import Path

ROOT = Path(SPECPATH)       # directory containing this .spec file

# ── Hidden imports needed because PyInstaller cannot see dynamic imports ──────
hidden_imports = [
    # Broker SDKs (only the ones you've installed will be available)
    "fyers_apiv3",
    "fyers_apiv3.FyersWebsocket",
    "kiteconnect",
    "dhanhq",
    "SmartApi",
    "upstox_client",
    "NorenRestApiPy.NorenApi",
    "breeze_connect",
    "pya3",
    "neo_api_client",
    # Internal modules that use importlib.import_module
    "broker.FyersBroker",
    "broker.ZerodhaBroker",
    "broker.DhanBroker",
    "broker.AngelOneBroker",
    "broker.UpstoxBroker",
    "broker.ShoonyaBroker",
    "broker.KotakNeoBroker",
    "broker.IciciBroker",
    "broker.AliceBlueBroker",
    "broker.FlattradeBroker",
    # PyQt5 plugins
    "PyQt5.QtPrintSupport",
    "PyQt5.QtSvg",
    # SQLAlchemy dialects
    "sqlalchemy.dialects.sqlite",
    # pandas backends
    "pandas._libs.tslibs.base",
    # pyotp
    "pyotp",
    # cryptography
    "cryptography.hazmat.primitives.kdf.pbkdf2",
]

# ── Data files to bundle ───────────────────────────────────────────────────────
datas = []

# Include all .json config templates
for p in ROOT.rglob("*.json"):
    if "backups" in str(p) or "__pycache__" in str(p):
        continue
    datas.append((str(p), str(p.parent.relative_to(ROOT))))

# Include icon assets
for ext in ("*.png", "*.ico", "*.svg"):
    for p in ROOT.rglob(ext):
        if "__pycache__" in str(p):
            continue
        datas.append((str(p), str(p.parent.relative_to(ROOT))))

# ── Platform-specific windowing ────────────────────────────────────────────────
is_windows = sys.platform == "win32"
is_mac = sys.platform == "darwin"

# On Windows use the .ico file if present; on macOS use the .icns
icon_win = str(ROOT / "assets" / "icon.ico") if (ROOT / "assets" / "icon.ico").exists() else None
icon_mac = str(ROOT / "assets" / "icon.icns") if (ROOT / "assets" / "icon.icns").exists() else None
icon = icon_win if is_windows else (icon_mac if is_mac else None)

# ── Analysis ───────────────────────────────────────────────────────────────────
a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[str(ROOT / "hooks")],   # custom hooks directory (optional)
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Exclude heavy packages not needed at runtime
        "matplotlib",
        "scipy",
        "tkinter",
        "test",
        "unittest",
        "IPython",
        "jupyter",
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
    console=False,           # no black terminal window
    disable_windowed_traceback=False,
    argv_emulation=is_mac,   # macOS: emulate argv for open-with support
    target_arch=None,
    codesign_identity=None,  # set to your Apple Developer ID for notarization
    entitlements_file=None,
    icon=icon,
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

# macOS: wrap in an .app bundle
if is_mac:
    app = BUNDLE(
        coll,
        name="TradingAssistant.app",
        icon=icon_mac,
        bundle_identifier="com.tradingassistant.app",
        info_plist={
            "CFBundleDisplayName": "Trading Assistant",
            "CFBundleVersion": "1.0.0",
            "CFBundleShortVersionString": "1.0.0",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "11.0",
        },
    )

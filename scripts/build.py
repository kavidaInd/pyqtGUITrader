#!/usr/bin/env python3
"""
scripts/build.py
================
Cross-platform build script.  Run with:

    python scripts/build.py [--dev | --exe | --install]

  --dev      Install in editable mode with dev extras (for development)
  --exe      Build native executable via PyInstaller
  --install  Install as a regular Python package (pip install .)
  --clean    Remove build artefacts

No arguments = --install (default)
"""

import argparse
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()


# ── Helpers ────────────────────────────────────────────────────────────────────

def run(cmd: list[str], **kwargs) -> int:
    print(f"\n▶  {' '.join(cmd)}")
    result = subprocess.run(cmd, **kwargs)
    if result.returncode != 0:
        print(f"✗  Command failed with exit code {result.returncode}")
        sys.exit(result.returncode)
    return result.returncode


def ensure_pip() -> None:
    """Upgrade pip and install build tools."""
    run([sys.executable, "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])


def check_python_version() -> None:
    if sys.version_info < (3, 10):
        print(f"✗  Python 3.10+ required (got {sys.version})")
        sys.exit(1)
    print(f"✓  Python {sys.version}")


def detect_platform() -> str:
    s = platform.system()
    return {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(s, s.lower())


# ── Actions ────────────────────────────────────────────────────────────────────

def action_install(editable: bool = False) -> None:
    ensure_pip()
    cmd = [sys.executable, "-m", "pip", "install"]
    if editable:
        cmd += ["-e", ".[dev]"]
    else:
        cmd += ["."]
    run(cmd, cwd=str(ROOT))
    print("\n✓  Package installed successfully")
    print_run_instructions()


def action_exe() -> None:
    ensure_pip()

    # Install PyInstaller if not present
    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        run([sys.executable, "-m", "pip", "install", "pyinstaller>=6.0"])

    spec = ROOT / "trading_assistant.spec"
    if not spec.exists():
        print(f"✗  Spec file not found: {spec}")
        sys.exit(1)

    run(
        [sys.executable, "-m", "PyInstaller", "--clean", str(spec)],
        cwd=str(ROOT),
    )

    dist = ROOT / "dist" / "TradingAssistant"
    plat = detect_platform()
    if plat == "macos":
        dist = ROOT / "dist" / "TradingAssistant.app"

    if dist.exists():
        print(f"\n✓  Executable built: {dist}")
        print_exe_instructions(plat, dist)
    else:
        print("✗  Build completed but output directory not found")


def action_clean() -> None:
    for name in ("build", "dist", "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache"):
        for p in ROOT.rglob(name):
            if p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                print(f"  removed {p.relative_to(ROOT)}")
    for p in ROOT.rglob("*.egg-info"):
        shutil.rmtree(p, ignore_errors=True)
    print("✓  Clean complete")


# ── Instructions ───────────────────────────────────────────────────────────────

def print_run_instructions() -> None:
    plat = detect_platform()
    print("\nTo run the application:")
    if plat == "windows":
        print("  trading-assistant")
        print("  — or double-click the shortcut created in the Start Menu")
    elif plat == "macos":
        print("  trading-assistant")
        print("  — or open from Applications")
    else:
        print("  trading-assistant")


def print_exe_instructions(plat: str, dist: Path) -> None:
    print("\nTo distribute:")
    if plat == "windows":
        print(f"  Zip the folder:  {dist}")
        print("  Recipients unzip and run TradingAssistant.exe")
        print("  Optional: run scripts/make_installer_win.nsi with NSIS to create a .exe installer")
    elif plat == "macos":
        print(f"  Distribute: {dist}")
        print("  create-dmg dist/TradingAssistant.app  # requires brew install create-dmg")
    else:
        print(f"  Zip the folder:  {dist}")
        print("  Recipients unzip and run ./TradingAssistant")


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    check_python_version()

    parser = argparse.ArgumentParser(description="Build / install Trading Assistant")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--dev", action="store_true", help="Editable install with dev extras")
    group.add_argument("--exe", action="store_true", help="Build native executable (PyInstaller)")
    group.add_argument("--install", action="store_true", help="Install as Python package")
    group.add_argument("--clean", action="store_true", help="Remove build artefacts")
    args = parser.parse_args()

    if args.exe:
        action_exe()
    elif args.dev:
        action_install(editable=True)
    elif args.clean:
        action_clean()
    else:
        # default
        action_install(editable=False)


if __name__ == "__main__":
    main()
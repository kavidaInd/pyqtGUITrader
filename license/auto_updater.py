"""
license/auto_updater.py
=======================
Over-the-air (OTA) update engine for the Algo Trading SaaS.

How it works
────────────
1. On startup, AutoUpdater.check_for_update() queries:
       GET  {server}/api/v1/version
   Response: { latest_version, download_url, release_notes, is_mandatory,
               min_version, checksum_sha256 }

2. If latest_version > APP_VERSION:
   - NotificationType.OPTIONAL → show a non-blocking banner in the GUI.
   - NotificationType.MANDATORY → block app start, force update dialog.

3. User clicks "Update Now":
   - File is downloaded to a temp path with progress tracking.
   - SHA-256 checksum is verified before anything is extracted.
   - A platform-aware installer script is written to disk.
   - The installer is launched and the current process exits.

Installer strategy (platform-specific)
───────────────────────────────────────
  Windows  : downloads a .exe / .msi → runs via subprocess
  macOS    : downloads a .dmg / .pkg → opens via subprocess
  Linux    : downloads a .tar.gz → extracts and runs install.sh

File formats
────────────
  The server's download_url should point to a platform-specific binary that
  can self-install.  For a PyInstaller-based app the simplest approach is:
    Windows : NSIS or InnoSetup installer .exe
    macOS   : .pkg or signed .dmg
    Linux   : tarball containing an install.sh

  Alternatively, supply a Python .zip that the updater unzips over the
  current installation (simpler for early-stage SaaS).

Server contract (GET /api/v1/version)
──────────────────────────────────────
  {
    "latest_version":  "1.2.0",
    "download_url":    "https://cdn.yourdomain.com/releases/1.2.0/installer.exe",
    "release_notes":   "Bug fixes and improvements.",
    "is_mandatory":    false,
    "min_version":     "1.0.0",
    "checksum_sha256": "abc123..."
  }
"""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional

import requests

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
ACTIVATION_SERVER_URL: str = "https://your-activation-server.com"   # ← same as license_manager
APP_VERSION: str = "1.0.0"       # must match license_manager.APP_VERSION
REQUEST_TIMEOUT: int = 15
DOWNLOAD_TIMEOUT: int = 300       # 5 min max for large installers
CHUNK_SIZE: int = 65_536          # 64 KB download chunks


# ── Result types ──────────────────────────────────────────────────────────────

class UpdateType(Enum):
    NONE      = "none"
    OPTIONAL  = "optional"
    MANDATORY = "mandatory"


@dataclass
class UpdateInfo:
    update_type:      UpdateType  = UpdateType.NONE
    latest_version:   str         = ""
    current_version:  str         = APP_VERSION
    download_url:     str         = ""
    release_notes:    str         = ""
    checksum_sha256:  str         = ""
    min_version:      str         = ""
    error:            str         = ""

    @property
    def available(self) -> bool:
        return self.update_type != UpdateType.NONE


@dataclass
class DownloadProgress:
    total_bytes:     int   = 0
    received_bytes:  int   = 0
    percent:         float = 0.0
    done:            bool  = False
    error:           str   = ""


# ── Version comparison ────────────────────────────────────────────────────────

def _parse_version(v: str):
    """Return a tuple of ints for comparison, e.g. '1.2.3' → (1, 2, 3)."""
    try:
        return tuple(int(x) for x in v.strip().split(".")[:3])
    except (ValueError, AttributeError):
        return (0, 0, 0)


def _version_gt(a: str, b: str) -> bool:
    """Return True if version a > version b."""
    return _parse_version(a) > _parse_version(b)


def _version_lt(a: str, b: str) -> bool:
    return _parse_version(a) < _parse_version(b)


# ── Main class ────────────────────────────────────────────────────────────────

class AutoUpdater:
    """
    Handles update checking and downloading.
    Use the module-level `auto_updater` singleton.
    """

    def __init__(self, server_url: str = ACTIVATION_SERVER_URL):
        self.server_url      = server_url.rstrip("/")
        self._update_info:   Optional[UpdateInfo] = None
        self._download_path: Optional[str] = None

    # ── Public API ─────────────────────────────────────────────────────────────

    def check_for_update(self) -> UpdateInfo:
        """
        Query the server for the latest version.

        Safe to call in a background thread. Returns UpdateInfo immediately
        (never blocks the UI for more than REQUEST_TIMEOUT seconds).
        """
        try:
            resp = requests.get(
                f"{self.server_url}/api/v1/version",
                params={"current_version": APP_VERSION, "platform": _get_platform()},
                timeout=REQUEST_TIMEOUT,
            )
            data = resp.json()

            latest   = data.get("latest_version", APP_VERSION)
            download = data.get("download_url", "")
            notes    = data.get("release_notes", "")
            checksum = data.get("checksum_sha256", "")
            is_mandatory = bool(data.get("is_mandatory", False))
            min_version  = data.get("min_version", "0.0.0")

            # Force update if current is below minimum required version
            if _version_lt(APP_VERSION, min_version):
                is_mandatory = True

            if _version_gt(latest, APP_VERSION):
                update_type = UpdateType.MANDATORY if is_mandatory else UpdateType.OPTIONAL
                info = UpdateInfo(
                    update_type     = update_type,
                    latest_version  = latest,
                    download_url    = download,
                    release_notes   = notes,
                    checksum_sha256 = checksum,
                    min_version     = min_version,
                )
                logger.info(
                    f"Update available: {APP_VERSION} → {latest} "
                    f"({'MANDATORY' if is_mandatory else 'optional'})"
                )
            else:
                info = UpdateInfo(update_type=UpdateType.NONE, latest_version=latest)
                logger.info(f"App is up to date (v{APP_VERSION})")

            self._update_info = info
            return info

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout):
            logger.info("Update check skipped — server unreachable")
            return UpdateInfo(update_type=UpdateType.NONE, error="server_unreachable")
        except Exception as e:
            logger.error(f"[AutoUpdater.check_for_update] {e}", exc_info=True)
            return UpdateInfo(update_type=UpdateType.NONE, error=str(e))

    def check_in_background(
        self,
        callback: Callable[[UpdateInfo], None],
    ) -> None:
        """
        Run check_for_update() in a daemon thread.
        `callback` is called on the background thread with the result —
        use Qt signals to marshal back to the GUI thread.
        """
        def _run():
            info = self.check_for_update()
            try:
                callback(info)
            except Exception as e:
                logger.error(f"AutoUpdater callback error: {e}", exc_info=True)

        t = threading.Thread(target=_run, daemon=True, name="UpdateCheck")
        t.start()

    def download_and_install(
        self,
        info: UpdateInfo,
        progress_callback: Optional[Callable[[DownloadProgress], None]] = None,
    ) -> bool:
        """
        Download the update installer and launch it.

        progress_callback is called periodically with a DownloadProgress object.
        Returns True if the installer was launched successfully.
        The current process will exit after a short delay.
        """
        if not info.download_url:
            logger.error("No download URL in UpdateInfo")
            return False

        try:
            # ── 1. Download ──────────────────────────────────────────────────
            suffix = _installer_suffix()
            tmp_fd, tmp_path = tempfile.mkstemp(
                prefix=f"algotrade_update_{info.latest_version}_",
                suffix=suffix,
            )
            os.close(tmp_fd)

            logger.info(f"Downloading update from {info.download_url}")
            progress = DownloadProgress()

            with requests.get(
                info.download_url, stream=True, timeout=DOWNLOAD_TIMEOUT
            ) as r:
                r.raise_for_status()
                total = int(r.headers.get("content-length", 0))
                progress.total_bytes = total
                received = 0
                sha256 = hashlib.sha256()

                with open(tmp_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                        if chunk:
                            f.write(chunk)
                            sha256.update(chunk)
                            received += len(chunk)
                            progress.received_bytes = received
                            progress.percent = (
                                (received / total * 100) if total > 0 else 0.0
                            )
                            if progress_callback:
                                try:
                                    progress_callback(progress)
                                except Exception:
                                    pass

            # ── 2. Checksum verify ───────────────────────────────────────────
            if info.checksum_sha256:
                actual = sha256.hexdigest()
                if actual.lower() != info.checksum_sha256.lower():
                    logger.error(
                        f"Checksum mismatch: expected {info.checksum_sha256}, got {actual}"
                    )
                    progress.error = "checksum_mismatch"
                    if progress_callback:
                        progress_callback(progress)
                    os.unlink(tmp_path)
                    return False
                logger.info("Checksum verified ✓")

            # ── 3. Make executable (POSIX) ────────────────────────────────────
            if platform.system() != "Windows":
                st = os.stat(tmp_path)
                os.chmod(tmp_path, st.st_mode | stat.S_IEXEC | stat.S_IXGRP)

            self._download_path = tmp_path

            # ── 4. Launch installer ───────────────────────────────────────────
            progress.done = True
            if progress_callback:
                progress_callback(progress)

            launched = self._launch_installer(tmp_path, info.latest_version)
            if launched:
                logger.info(f"Installer launched: {tmp_path}")
                # Give the installer a moment to start, then exit
                threading.Timer(2.0, lambda: os._exit(0)).start()
            return launched

        except Exception as e:
            logger.error(f"[AutoUpdater.download_and_install] {e}", exc_info=True)
            if progress_callback:
                p = DownloadProgress(error=str(e))
                progress_callback(p)
            return False

    # ── Platform-specific installer launcher ──────────────────────────────────

    def _launch_installer(self, path: str, version: str) -> bool:
        system = platform.system()
        try:
            if system == "Windows":
                # NSIS / InnoSetup installers accept /SILENT
                subprocess.Popen([path, "/SILENT"], close_fds=True)

            elif system == "Darwin":
                if path.endswith(".dmg"):
                    subprocess.Popen(["open", path])
                elif path.endswith(".pkg"):
                    subprocess.Popen(["sudo", "installer", "-pkg", path, "-target", "/"])
                else:
                    subprocess.Popen(["open", path])

            else:  # Linux
                if path.endswith(".tar.gz") or path.endswith(".tgz"):
                    return self._linux_tarball_install(path)
                else:
                    subprocess.Popen([path])

            return True
        except Exception as e:
            logger.error(f"[AutoUpdater._launch_installer] {e}", exc_info=True)
            return False

    def _linux_tarball_install(self, tarball_path: str) -> bool:
        """Extract tarball and run install.sh if present."""
        try:
            import tarfile
            extract_dir = tempfile.mkdtemp(prefix="algotrade_update_")
            with tarfile.open(tarball_path) as tf:
                tf.extractall(extract_dir)

            install_sh = os.path.join(extract_dir, "install.sh")
            if os.path.exists(install_sh):
                os.chmod(install_sh, 0o755)
                subprocess.Popen(
                    ["bash", install_sh],
                    cwd=extract_dir,
                    close_fds=True,
                )
                return True

            logger.warning("install.sh not found in tarball — extraction complete at " + extract_dir)
            return True
        except Exception as e:
            logger.error(f"[AutoUpdater._linux_tarball_install] {e}", exc_info=True)
            return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_platform() -> str:
    s = platform.system()
    return {"Windows": "windows", "Darwin": "macos", "Linux": "linux"}.get(s, "unknown")


def _installer_suffix() -> str:
    s = platform.system()
    return {
        "Windows": ".exe",
        "Darwin":  ".pkg",
        "Linux":   ".tar.gz",
    }.get(s, ".bin")


# ── Singleton ─────────────────────────────────────────────────────────────────
auto_updater = AutoUpdater()
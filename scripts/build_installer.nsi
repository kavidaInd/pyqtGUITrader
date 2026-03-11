; =============================================================================
; scripts\build_installer.nsi
; =============================================================================
; NSIS script that wraps the PyInstaller output folder into a professional
; Windows installer (.exe).
;
; Requirements:
;   NSIS 3.x  — https://nsis.sourceforge.io/Download
;   UltraModernUI (optional) — or use the bundled MUI2 (already included)
;
; Usage (called automatically by BUILD.bat, or manually):
;   "C:\Program Files (x86)\NSIS\makensis.exe" scripts\build_installer.nsi
;
; Output:
;   scripts\TradingAssistant_Setup_1.0.0.exe
; =============================================================================

Unicode True

; ── Application metadata ──────────────────────────────────────────────────────
!define APP_NAME        "Trading Assistant"
!define APP_EXE         "TradingAssistant.exe"
!define APP_VERSION     "1.0.0"
!define APP_PUBLISHER   "YourCompany"
!define APP_URL         "https://yourcompany.com"
!define APP_DESCRIPTION "Automated options trading for Indian markets"

; Registry key for uninstall info
!define REG_UNINSTALL   "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APP_NAME}"
!define REG_APP         "Software\${APP_PUBLISHER}\${APP_NAME}"

; Paths (relative to the .nsi file, i.e. the scripts\ folder)
!define DIST_DIR        "..\dist\TradingAssistant"
!define ICON_FILE       "..\assets\icon.ico"
!define OUTPUT_DIR      "."   ; installer lands in scripts\

; ── NSIS settings ─────────────────────────────────────────────────────────────
Name                    "${APP_NAME} ${APP_VERSION}"
OutFile                 "${OUTPUT_DIR}\TradingAssistant_Setup_${APP_VERSION}.exe"
InstallDir              "$PROGRAMFILES64\${APP_PUBLISHER}\${APP_NAME}"
InstallDirRegKey        HKLM "${REG_APP}" "InstallDir"
RequestExecutionLevel   admin          ; needed to write to Program Files
SetCompressor           /SOLID lzma    ; best compression
SetCompressorDictSize   32

; ── Modern UI ─────────────────────────────────────────────────────────────────
!include "MUI2.nsh"
!include "LogicLib.nsh"
!include "WinVer.nsh"

; MUI appearance
!define MUI_ICON                    "${ICON_FILE}"
!define MUI_UNICON                  "${ICON_FILE}"
!define MUI_WELCOMEPAGE_TITLE       "Welcome to ${APP_NAME} ${APP_VERSION} Setup"
!define MUI_WELCOMEPAGE_TEXT        "This wizard will guide you through the installation of ${APP_NAME}.$\r$\n$\r$\nClick Next to continue."
!define MUI_FINISHPAGE_RUN          "$INSTDIR\${APP_EXE}"
!define MUI_FINISHPAGE_RUN_TEXT     "Launch ${APP_NAME} now"
!define MUI_FINISHPAGE_SHOWREADME   ""
!define MUI_ABORTWARNING
!define MUI_UNABORTWARNING

; Installer pages
!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_LICENSE      "..\README.md"     ; shows README as license page
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH

; Uninstaller pages
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_UNPAGE_FINISH

; Language (English only — add more !insertmacro MUI_LANGUAGE lines as needed)
!insertmacro MUI_LANGUAGE "English"

; ── Version info embedded in the .exe ─────────────────────────────────────────
VIProductVersion                    "${APP_VERSION}.0"
VIAddVersionKey /LANG=1033 "ProductName"      "${APP_NAME}"
VIAddVersionKey /LANG=1033 "ProductVersion"   "${APP_VERSION}"
VIAddVersionKey /LANG=1033 "FileVersion"      "${APP_VERSION}.0"
VIAddVersionKey /LANG=1033 "FileDescription"  "${APP_DESCRIPTION}"
VIAddVersionKey /LANG=1033 "CompanyName"      "${APP_PUBLISHER}"
VIAddVersionKey /LANG=1033 "LegalCopyright"   "Copyright © 2025 ${APP_PUBLISHER}"

; ── Installer Section ─────────────────────────────────────────────────────────
Section "MainSection" SEC_MAIN

    SectionIn RO   ; always installed, can't be deselected

    ; Set output path and copy all files from PyInstaller dist folder
    SetOutPath "$INSTDIR"
    File /r "${DIST_DIR}\*.*"

    ; Write registry keys for Add/Remove Programs
    WriteRegStr   HKLM "${REG_APP}"       "InstallDir"   "$INSTDIR"
    WriteRegStr   HKLM "${REG_APP}"       "Version"      "${APP_VERSION}"

    WriteRegStr   HKLM "${REG_UNINSTALL}" "DisplayName"          "${APP_NAME}"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "DisplayVersion"        "${APP_VERSION}"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "Publisher"             "${APP_PUBLISHER}"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "URLInfoAbout"          "${APP_URL}"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "DisplayIcon"           "$INSTDIR\${APP_EXE}"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "UninstallString"       "$INSTDIR\Uninstall.exe"
    WriteRegStr   HKLM "${REG_UNINSTALL}" "QuietUninstallString"  "$INSTDIR\Uninstall.exe /S"
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoModify"              1
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "NoRepair"              1

    ; Estimate install size (in KB) for Add/Remove Programs panel
    ${GetSize} "$INSTDIR" "/S=0K" $0 $1 $2
    IntFmt $0 "0x%08X" $0
    WriteRegDWORD HKLM "${REG_UNINSTALL}" "EstimatedSize" "$0"

    ; Write uninstaller
    WriteUninstaller "$INSTDIR\Uninstall.exe"

    ; Desktop shortcut
    CreateShortCut  "$DESKTOP\${APP_NAME}.lnk" \
                    "$INSTDIR\${APP_EXE}" "" \
                    "$INSTDIR\${APP_EXE}" 0 \
                    SW_SHOWNORMAL "" "${APP_DESCRIPTION}"

    ; Start Menu shortcuts
    CreateDirectory "$SMPROGRAMS\${APP_PUBLISHER}"
    CreateShortCut  "$SMPROGRAMS\${APP_PUBLISHER}\${APP_NAME}.lnk" \
                    "$INSTDIR\${APP_EXE}" "" \
                    "$INSTDIR\${APP_EXE}" 0
    CreateShortCut  "$SMPROGRAMS\${APP_PUBLISHER}\Uninstall ${APP_NAME}.lnk" \
                    "$INSTDIR\Uninstall.exe"

SectionEnd

; ── Uninstaller Section ───────────────────────────────────────────────────────
Section "Uninstall"

    ; Remove all installed files
    RMDir /r "$INSTDIR"

    ; Remove shortcuts
    Delete "$DESKTOP\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_PUBLISHER}\${APP_NAME}.lnk"
    Delete "$SMPROGRAMS\${APP_PUBLISHER}\Uninstall ${APP_NAME}.lnk"
    RMDir  "$SMPROGRAMS\${APP_PUBLISHER}"

    ; Remove registry keys
    DeleteRegKey HKLM "${REG_UNINSTALL}"
    DeleteRegKey HKLM "${REG_APP}"

    ; Note: user data in %APPDATA%\TradingAssistant is intentionally left intact
    ;       so that settings / DB are preserved across reinstalls.
    ;       Add the block below to also wipe user data on uninstall if desired:
    ;
    ;   MessageBox MB_YESNO "Remove all user data (config, logs, database)?" IDNO skip_userdata
    ;   RMDir /r "$APPDATA\TradingAssistant"
    ;   skip_userdata:

SectionEnd

; ── OS version check (runs before anything else) ──────────────────────────────
Function .onInit
    ; Require Windows 10 or later
    ${IfNot} ${AtLeastWin10}
        MessageBox MB_OK|MB_ICONSTOP \
            "${APP_NAME} requires Windows 10 or later.$\r$\nSetup will now exit."
        Abort
    ${EndIf}
FunctionEnd

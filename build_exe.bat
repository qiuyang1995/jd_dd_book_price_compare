@echo off
setlocal

cd /d "%~dp0"

set "BUILD_NAME=book_price_gui"
set "ENTRY_SCRIPT=jd_dd_price_gui.py"
set "DIST_DIR=dist"
set "BUILD_DIR=build"
set "ICON_FILE=assets\app_icon.ico"

echo [INFO] Building single-file EXE ...

if not exist "%ENTRY_SCRIPT%" (
    echo [ERROR] Entry script not found: %ENTRY_SCRIPT%
    exit /b 1
)

if not exist "%ICON_FILE%" (
    echo [ERROR] Icon file not found: %ICON_FILE%
    exit /b 1
)

python --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python is not available in PATH.
    exit /b 1
)

python -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] PyInstaller is not installed.
    echo [ERROR] Run: python -m pip install pyinstaller
    exit /b 1
)

if exist "%DIST_DIR%\%BUILD_NAME%.exe" del /q "%DIST_DIR%\%BUILD_NAME%.exe"
if exist "%DIST_DIR%\jd_dd_price_gui" rmdir /s /q "%DIST_DIR%\jd_dd_price_gui"
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%BUILD_NAME%.spec" del /q "%BUILD_NAME%.spec"

python -c "from pathlib import Path; p = Path('dist') / '\u56fe\u4e66\u4ef7\u683c\u6293\u53d6\u5de5\u5177.exe'; p.unlink(missing_ok=True)"

python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onefile ^
    --windowed ^
    --icon "%ICON_FILE%" ^
    --name "%BUILD_NAME%" ^
    --collect-all playwright ^
    --hidden-import playwright.sync_api ^
    --hidden-import playwright.async_api ^
    "%ENTRY_SCRIPT%"

if errorlevel 1 (
    echo [ERROR] Build failed.
    exit /b 1
)

python -c "from pathlib import Path; src = Path('dist') / 'book_price_gui.exe'; dst = Path('dist') / '\u56fe\u4e66\u4ef7\u683c\u6293\u53d6\u5de5\u5177.exe'; dst.unlink(missing_ok=True); src.replace(dst)"
if errorlevel 1 (
    echo [ERROR] Rename failed.
    exit /b 1
)

echo [SUCCESS] Build completed.
echo [INFO] Final EXE is in dist.
exit /b 0

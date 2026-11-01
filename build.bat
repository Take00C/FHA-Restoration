@echo off
rem Builds two single-file programs (no Python needed to run them):
rem   dist\FHA-Restoration-Launcher.exe  the launcher, for players
rem   dist\FHA-Scene-Tester.exe          plays one restored 18+ scene at a time, to check them in game
rem Every module in fhar\ is bundled (they are imported by name at run time), plus side_art.py.
rem The launcher's icon is Caren's face, cut from your own 2005 game files by build_icon.py (no art
rem is stored in this repository).
rem Needs 64-bit Python 3.10-3.13 (the pinned NumPy has no packages for newer versions). It takes
rem the first of 3.10 (the version the release was built and tested with), 3.13, 3.12 and 3.11 that
rem the py launcher knows; set PY to use another interpreter, e.g. set PY=C:\Python312\python.exe.
rem Package versions: requirements.txt, plus PyInstaller below. The version shown under the exes'
rem Properties > Details is in assets\version_launcher.txt and assets\version_tester.txt.
setlocal enabledelayedexpansion
cd /d "%~dp0"
rem the probe must never make the Python install manager download a missing version
set PYTHON_MANAGER_AUTOMATIC_INSTALL=false
set "PYCHECK=import sys; sys.exit(sys.version_info[:2] not in [(3, 10), (3, 11), (3, 12), (3, 13)] or sys.maxsize == 2**31 - 1)"
if not defined PY for %%v in (3.10 3.13 3.12 3.11) do if not defined PY py -%%v -c "%PYCHECK%" <nul >nul 2>&1 && set "PY=py -%%v"
if not defined PY goto :nopython
%PY% -c "%PYCHECK%" <nul >nul 2>&1 || goto :nopython
echo Building with %PY%
%PY% -m pip install -r requirements.txt pyinstaller==6.22.3 || goto :fail
set HIDDEN=--hidden-import=side_art --hidden-import=launcher
for %%f in (fhar\*.py) do set HIDDEN=!HIDDEN! --hidden-import=%%~nf
rem icons: the launcher gets Caren's face from your 2005 files (Windows' default icon when they
rem aren't found); the Scene Tester gets Windows' default. assets\ (version details) is optional.
if not exist build mkdir build
set ICON_L=--icon NONE
for /f "usebackq delims=" %%i in (`%PY% build_icon.py`) do set ICON_L=--icon "%%i"
echo Launcher icon: !ICON_L!
set VL=
set VT=
if exist assets\version_launcher.txt set VL=--version-file assets\version_launcher.txt
if exist assets\version_tester.txt set VT=--version-file assets\version_tester.txt
set COMMON=--noconfirm --clean --onefile --windowed --paths . --paths fhar !HIDDEN! --collect-all soundfile
%PY% -m PyInstaller !COMMON! !ICON_L! --name FHA-Restoration-Launcher !VL! launcher.py || goto :fail
%PY% -m PyInstaller !COMMON! --icon NONE --name FHA-Scene-Tester !VT! scene_tester.py || goto :fail
echo.
echo Built: dist\FHA-Restoration-Launcher.exe and dist\FHA-Scene-Tester.exe
pause
exit /b 0
:nopython
echo.
if defined PY echo PY is set to %PY%, which is not a 64-bit Python 3.10, 3.11, 3.12 or 3.13.
if not defined PY echo No 64-bit Python 3.10, 3.11, 3.12 or 3.13 was found through the py launcher.
echo Install one from python.org (64-bit, with the py launcher option ticked) and run build.bat again,
echo or set PY to such an interpreter first, for example: set PY=C:\Python312\python.exe
echo Newer Python versions do not work yet: NumPy 2.2.6, which the build uses, has no packages for them.
:fail
echo Build failed.
pause
exit /b 1

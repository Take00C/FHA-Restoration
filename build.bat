@echo off
rem Builds two single-file programs (no Python needed to run them):
rem   dist\FHA-Restoration-Launcher.exe  the launcher, for players
rem   dist\FHA-Scene-Tester.exe          plays one restored 18+ scene at a time, to check them in game
rem Every module in fhar\ is bundled (they are imported by name at run time), plus side_art.py and
rem the icon images the windows load at run time. No game art is bundled: the picture and the
rem window icon are cut from the player's own 2005 files when the program runs.
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
rem the assets folder (icon, version details) is optional: without it the programs get Windows'
rem default icon and no version details, and work the same
set ART=
if exist assets\launcher.ico set ART=--icon assets\launcher.ico --add-data "assets\launcher.ico;assets"
if exist assets\launcher.png set ART=!ART! --add-data "assets\launcher.png;assets"
set VL=
set VT=
if exist assets\version_launcher.txt set VL=--version-file assets\version_launcher.txt
if exist assets\version_tester.txt set VT=--version-file assets\version_tester.txt
set COMMON=--noconfirm --clean --onefile --windowed !ART! --paths . --paths fhar !HIDDEN! --collect-all soundfile
%PY% -m PyInstaller !COMMON! --name FHA-Restoration-Launcher !VL! launcher.py || goto :fail
%PY% -m PyInstaller !COMMON! --name FHA-Scene-Tester !VT! scene_tester.py || goto :fail
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

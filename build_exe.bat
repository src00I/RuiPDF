@echo off
rem Build RuiPDF into dist\RuiPDF\RuiPDF.exe, then (if Inno Setup is installed) into an installer.
rem Usage: double-click, or run from the project folder. Needs the .venv created by run.bat.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" ( echo Run run.bat once first to create the environment. & pause & exit /b 1 )
".venv\Scripts\python.exe" -m pip show pyinstaller >nul 2>nul || ".venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 ( echo Could not install PyInstaller. & pause & exit /b 1 )

echo [1/3] Packaging (takes a few minutes)...
rem Remove the old output ourselves first. PyInstaller's own cleanup (--clean / overwriting dist) has failed here
rem with "access denied" on a folder it had just emptied; removing them up front avoids that.
if exist "build" rmdir /s /q "build"
if exist "dist\RuiPDF" rmdir /s /q "dist\RuiPDF"
".venv\Scripts\python.exe" -m PyInstaller RuiPDF.spec --noconfirm --log-level WARN
if errorlevel 1 ( echo Packaging failed. & pause & exit /b 1 )

echo [2/3] Self-test of the packaged program...
"dist\RuiPDF\RuiPDF.exe" --selftest "%TEMP%\ruipdf_selftest.json"
if errorlevel 1 ( echo Self-test FAILED. See %TEMP%\ruipdf_selftest.json & pause & exit /b 1 )
echo       OK

echo [3/3] Building the installer...
set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist "%ISCC%" ( echo Inno Setup 6 not found - skipped. The program itself is in dist\RuiPDF. & pause & exit /b 0 )
"%ISCC%" /Q installer.iss
if errorlevel 1 ( echo Installer build failed. & pause & exit /b 1 )
echo Done: dist\RuiPDF-Setup.exe
pause

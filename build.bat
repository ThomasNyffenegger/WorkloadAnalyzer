@echo off
echo Building WorkloadAnalyzer...
echo.

echo [1/2] PyInstaller...
pyinstaller WorkloadAnalyzer.spec --clean
if errorlevel 1 (
    echo PyInstaller failed.
    exit /b 1
)

echo.
echo [2/2] Inno Setup...
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer\WorkloadAnalyzer.iss
if errorlevel 1 (
    echo Inno Setup failed.
    exit /b 1
)

echo.
echo Done: installer\Output\WorkloadAnalyzer_Setup.exe

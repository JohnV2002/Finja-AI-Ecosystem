@echo off
REM Glorpo VS Code Extension Build Script
REM =====================================
REM Builds the VSIX package for the Glorpo language extension.
REM
REM Main Responsibilities:
REM - Check required tooling.
REM - Run the local build or install command.
REM - Report success or failure to the terminal.
REM
REM Side Effects:
REM - Creates build artifacts or installs packages.
REM - Writes terminal output.
echo === Glorpo VSIX Builder ===
echo Glorpo is pain. Building anyway.
echo.

where vsce >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] vsce not found. Install it once with:
    echo     npm install -g @vscode/vsce
    echo.
    echo     Node.js is required: https://nodejs.org
    pause
    exit /b 1
)

echo [*] Building glorpo-lang-1.1.0.vsix ...
vsce package --no-dependencies --allow-missing-repository

if %errorlevel% == 0 (
    echo.
    echo [OK] glorpo-lang-1.1.0.vsix ready!
    echo      Run install.bat to install it.
) else (
    echo.
    echo [!] Build failed. Check the error above.
)
echo.
pause

@echo off
REM Glorpo Package Install Script
REM =============================
REM Installs the Python package and optionally builds the VSIX asset.
REM
REM Main Responsibilities:
REM - Check required tooling.
REM - Run the local build or install command.
REM - Report success or failure to the terminal.
REM
REM Side Effects:
REM - Creates build artifacts or installs packages.
REM - Writes terminal output.
echo === Glorpo Esolang Installer ===
echo Glorpo is pain. Glorpo is having pain.
echo.

:: [1/3] Python package.
echo [1/3] Installing Glorpo CLI (Python)...
pip install .
if %errorlevel% neq 0 (
    echo [!] pip install failed. Are Python and pip installed?
    pause
    exit /b 1
)
echo.

:: [2/3] Build VSIX when vsce is available.
echo [2/3] Trying to build VSIX...
set VSIX_DIR=..\glorpo-vscode
set VSIX_NEW=%VSIX_DIR%\glorpo-lang-1.1.0.vsix
set VSIX_OLD=%VSIX_DIR%\glorpo-lang-1.0.0.vsix

where vsce >nul 2>&1
if %errorlevel% == 0 (
    pushd %VSIX_DIR%
    vsce package --no-dependencies --allow-missing-repository
    popd
    echo [OK] Built VSIX 1.1.0.
) else (
    echo [i] vsce not found - the new VSIX will not be built.
    echo     Run once for the new YourAI theme:
    echo       npm install -g @vscode/vsce
    echo     Dann: glorpo-vscode\build-vsix.bat
)
echo.

:: [3/3] Install the editor extension.
echo [3/3] Installing VSCodium / VS Code extension...

:: Prefer the new VSIX, fall back to the old one.
set VSIX_PATH=%VSIX_NEW%
if not exist "%VSIX_PATH%" set VSIX_PATH=%VSIX_OLD%

if not exist "%VSIX_PATH%" (
    echo [!] No VSIX found. Run build-vsix.bat in glorpo-vscode\ first.
    echo     Or install manually in VSCodium: Extensions ^> ... ^> Install from VSIX
    goto done
)

:: Try VSCodium first, then VS Code as fallback.
where codium >nul 2>&1
if %errorlevel% == 0 (
    echo [*] Installing in VSCodium...
    codium --install-extension "%VSIX_PATH%"
    goto done
)

where code >nul 2>&1
if %errorlevel% == 0 (
    echo [*] Installing in VS Code...
    code --install-extension "%VSIX_PATH%"
    goto done
)

echo [i] Neither 'codium' nor 'code' was found in PATH.
echo     Install manually in VSCodium:
echo       Extensions (Strg+Shift+X) ^> ... (oben rechts) ^> Install from VSIX
echo     Then select this file:
echo     %VSIX_PATH%

:done
echo.
echo === Done! ===
echo  Glorpo CLI:    glorpo --help
echo  Demo:          glorpo demo
echo  VSCodium Theme: Strg+K Strg+T  ->  "Glorpo - YourAI Dark"
echo.
pause

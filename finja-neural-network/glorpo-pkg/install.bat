@echo off
echo === Glorpo Esolang Installer ===
echo Glorpo is pain. Glorpo is having pain.
echo.
echo [1/2] Installing Glorpo CLI...
pip install .
echo.
echo [2/2] Installing VSCode Extension...
if exist glorpo-lang-1.0.0.vsix (
    code --install-extension glorpo-lang-1.0.0.vsix
) else (
    echo VSIX not found, skipping VSCode extension.
)
echo.
echo Done! Try: glorpo --help
pause

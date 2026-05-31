@echo off
REM Glorpo Interpreter Windows Build Script
REM =======================================
REM Builds the standalone interpreter on Windows.
REM
REM Main Responsibilities:
REM - Check required tooling.
REM - Run the local build or install command.
REM - Report success or failure to the terminal.
REM
REM Side Effects:
REM - Creates build artifacts or installs packages.
REM - Writes terminal output.
echo === Glorpo True Interpreter Builder ===
echo Glorpo is pain. Compiling the real thing.
echo.

where cmake >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] cmake not found: https://cmake.org/download/
    echo     or: winget install Kitware.CMake
    pause
    exit /b 1
)

where g++ >nul 2>&1
if %errorlevel% == 0 (
    echo [*] g++ found, building with MinGW...
    if not exist build mkdir build
    cmake -B build -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
    if %errorlevel% neq 0 exit /b %errorlevel%
    cmake --build build
    if %errorlevel% neq 0 exit /b %errorlevel%
    if exist build\glorpoi.exe (
        copy build\glorpoi.exe glorpoi.exe >nul
        echo.
        echo [OK] glorpoi.exe ready!
        echo     Test: glorpoi.exe --tokens example.glp
        echo     Run: glorpoi.exe example.glp
    )
    goto done
)

echo [*] Trying MSVC...
if not exist build mkdir build
cmake -B build -DCMAKE_BUILD_TYPE=Release
if %errorlevel% neq 0 exit /b %errorlevel%
cmake --build build --config Release
if %errorlevel% neq 0 exit /b %errorlevel%
if exist build\Release\glorpoi.exe (
    copy build\Release\glorpoi.exe glorpoi.exe >nul
    echo.
    echo [OK] glorpoi.exe ready!
)

:done
echo.
if /I "%~1"=="--pause" pause

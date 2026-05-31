@echo off
REM Glorpo Native Windows Build Script
REM ==================================
REM Builds the native runner on Windows.
REM
REM Main Responsibilities:
REM - Check required tooling.
REM - Run the local build or install command.
REM - Report success or failure to the terminal.
REM
REM Side Effects:
REM - Creates build artifacts or installs packages.
REM - Writes terminal output.
echo === Glorpo Native Builder ===
echo Glorpo is pain. Compiling anyway.
echo.

:: Try to locate cmake.
where cmake >nul 2>&1
if %errorlevel% neq 0 (
    echo [!] cmake not found.
    echo     Install it from: https://cmake.org/download/
    echo     Or run: winget install Kitware.CMake
    echo.
    echo     Alternativ direkt mit g++:
    echo     g++ -std=c++17 -O2 -o glorpo.exe glorpo.cpp
    pause
    exit /b 1
)

:: Compiler check: g++ or MSVC.
where g++ >nul 2>&1
if %errorlevel% == 0 (
    echo [*] g++ found, building with MinGW...
    if not exist build mkdir build
    cmake -B build -G "MinGW Makefiles" -DCMAKE_BUILD_TYPE=Release
    if %errorlevel% neq 0 exit /b %errorlevel%
    cmake --build build
    if %errorlevel% neq 0 exit /b %errorlevel%
    if exist build\glorpo.exe (
        copy build\glorpo.exe glorpo.exe >nul
        echo.
        echo [OK] glorpo.exe ready!
        echo     Test: glorpo.exe --help
    )
    goto done
)

:: MSVC fallback
echo [*] Trying MSVC...
if not exist build mkdir build
cmake -B build -DCMAKE_BUILD_TYPE=Release
if %errorlevel% neq 0 exit /b %errorlevel%
cmake --build build --config Release
if %errorlevel% neq 0 exit /b %errorlevel%
if exist build\Release\glorpo.exe (
    copy build\Release\glorpo.exe glorpo.exe >nul
    echo.
    echo [OK] glorpo.exe ready!
)

:done
echo.
if /I "%~1"=="--pause" pause

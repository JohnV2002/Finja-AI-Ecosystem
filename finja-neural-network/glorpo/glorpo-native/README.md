# Glorpo Native Runner

Documentation for the native Glorpo runner.

Main Responsibilities:
- Explain how to build and run the native runner.
- Document requirements, smoke tests, and dictionary regeneration.
- Provide troubleshooting steps for Windows network-drive execution.

Side Effects:
- Commands in this document build binaries and run local executables.
- Dictionary regeneration writes `glorpo_dict.hpp`.

Native `.exe` runner for Glorpo files.

This is not the true native interpreter. It deglorpifies `.glp` code into Python, writes a temporary `.py` file, and runs it with system Python.

## Requirements

On Laptop or PC you need:

- Windows
- Visual Studio / MSVC with C++ tools
- CMake
- Python in `PATH`

## Build

Open PowerShell in this folder:

```powershell
cd "Z:\YOURAI CORE\glorpo\glorpo-native"
```

If normal `cmake` is not found, add Visual Studio CMake:

```powershell
$env:PATH = "C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin;" + $env:PATH
```

Then build:

```powershell
cmd.exe /c build.bat
```

After a successful build, these should exist:

```text
glorpo.exe
build\Release\glorpo.exe
```

## Run A Glorpo File

From this folder:

```powershell
.\glorpo.exe "..\..\example.glp"
```

Or with any `.glp` file:

```powershell
.\glorpo.exe "path\to\file.glp"
```

## Show Translated Python

Use `--deglorpify` to print Python instead of running it:

```powershell
.\glorpo.exe --deglorpify "..\..\example.glp"
```

## Test If Everything Works

Build first, then run:

```powershell
.\glorpo.exe "..\..\example.glp"
.\glorpo.exe "native_smoke.glp"
```

Expected output from `example.glp`:

```text
Glorpo says: PAIN!
Fox says: Ring-ding-ding!
Cat says: Meow!
Zoo has 3 animals
Loudest: Fox
Glorpo is done. Glorpo is having done.
```

Expected output from `native_smoke.glp`:

```text
native smoke ok
```

## If Windows Says "Access Denied"

Sometimes Windows blocks running `.exe` files directly from the `Z:` network drive.
If that happens, copy the exe and test files to a local temp folder and run them there:

```powershell
$tmp = Join-Path $env:TEMP "glorpo-native-test"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Copy-Item ".\glorpo.exe" $tmp -Force
Copy-Item "..\..\example.glp" $tmp -Force
Copy-Item ".\native_smoke.glp" $tmp -Force

& (Join-Path $tmp "glorpo.exe") (Join-Path $tmp "example.glp")
& (Join-Path $tmp "glorpo.exe") (Join-Path $tmp "native_smoke.glp")
```

## Regenerate The Dictionary

`glorpo_dict.hpp` is generated from `glorpo-pkg\glorpo.py`.

Run this when the Glorpo dictionary changes:

```powershell
python gen_dict.py
```

Then rebuild:

```powershell
cmd.exe /c build.bat
```

## Native Runner vs True Interpreter

Use this runner when you want full Python behavior through Glorpo syntax.

Use `..\glorpo-interp\glorpoi.exe` when you want the true native C++ interpreter that does not depend on Python.

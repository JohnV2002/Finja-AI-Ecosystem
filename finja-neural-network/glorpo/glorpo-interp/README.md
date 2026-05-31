# Glorpo True Interpreter

Documentation for the standalone Glorpo interpreter.

Main Responsibilities:
- Explain how to build and run the interpreter.
- Document smoke tests, token debugging, and supported language coverage.
- Provide troubleshooting steps for Windows network-drive execution.

Side Effects:
- Commands in this document build binaries and run local executables.
- Debug commands print lexer token streams.

Native Glorpo interpreter for `.glp` files.

Glorpo is pain. This one compiles the pain into `glorpoi.exe`.

## Requirements

On Laptop or PC you need:

- Windows
- Visual Studio / MSVC with C++ tools
- CMake

If CMake is not in `PATH`, use the Visual Studio bundled CMake path before building.

## Build

Open PowerShell in this folder:

```powershell
cd "Z:\YOURAI CORE\glorpo\glorpo-interp"
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
glorpoi.exe
build\Release\glorpoi.exe
```

## Run A Glorpo File

From this folder:

```powershell
.\glorpoi.exe "..\..\example.glp"
```

Or with any `.glp` file:

```powershell
.\glorpoi.exe "path\to\file.glp"
```

## Test If Everything Works

Build first, then run:

```powershell
.\glorpoi.exe "..\..\example.glp"
.\glorpoi.exe "tests\smoke.glp"
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

Expected output from `tests\smoke.glp`:

```text
smoke ok
```

## If Windows Says "Access Denied"

Sometimes Windows blocks running `.exe` files directly from the `Z:` network drive.
If that happens, copy the exe and test files to a local temp folder and run them there:

```powershell
$tmp = Join-Path $env:TEMP "glorpo-interp-test"
New-Item -ItemType Directory -Force -Path $tmp | Out-Null
Copy-Item ".\glorpoi.exe" $tmp -Force
Copy-Item "..\..\example.glp" $tmp -Force
Copy-Item ".\tests\smoke.glp" $tmp -Force

& (Join-Path $tmp "glorpoi.exe") (Join-Path $tmp "example.glp")
& (Join-Path $tmp "glorpoi.exe") (Join-Path $tmp "smoke.glp")
```

## Debug Tokens

To inspect lexer output:

```powershell
.\glorpoi.exe --tokens "..\..\example.glp"
```

## Current Native Coverage

The interpreter supports the standard everyday Glorpo things:

- variables, assignment, destructuring
- numbers, strings, f-strings, bool, none
- lists, tuples, dicts, sets
- indexing and attribute access
- functions, lambdas, classes, methods, instances
- `glorb`, `glorbelif`, `glorpelse`
- `glorpach`, `glorploop`
- `glorptry`, `glorpcatch`, `glorpalways`
- `glorpwith`
- `glorpcheck`, `glorpwhen`
- common builtins and methods like `glorp`, `glorpsize`, `glorprange`, `glorplist`, `glorpsum`, `glorpsmol`, `glorpchonk`, `glorpmorph`, `glorpsift`, `glorpsort`, `glorpflip`, `glorpshove`, `glorpyoink`, string helpers, dict helpers

Some heavy Python-like features are declared but intentionally not fully native yet, for example `open`, `super`, properties, classmethod/staticmethod, bytes, complex, slice, `nonlocal`, and annotated assignment.

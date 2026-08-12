<!-- GITHUB_CONTRACT_BEGIN -->
# GitHub Contract — ALWAYS ACTIVE

Not optional. When the workspace is **git / GitHub / J. Apps public module / production packaging**:

## 1. Headers (every source file)

The target project's ecosystem banner is required (Project, Module, Author,
**Version**, Description, New-in, Copyright MIT J. Apps). Never stamp the
GitHub Contract plugin's own project identity onto an unrelated target.  
Python `"""` · Batch `@REM` · HTML/SVG `<!-- -->` · native comment syntax for
all other commentable source/config files. Do not force comments into JSON.

## 2. Version (module-wide)

Scheme: **MAJOR.FEATURES.BUGS** (example `1.0.0`).

- **Same** version in **every** file of that module (+ pyproject/package.json).
- **Changelog / New-in** may differ per file.

## 3. No leaks

No secrets, tokens, private keys, absolute drive/user paths, UNC/NAS paths,
private LAN addresses, or real env values in the tree.

## 4. README

Version in title; License + Support & Contact (J. Apps) at the end.

## CLI

```
github-contract preflight .
github-contract scan . --version X.Y.Z
```

ENGINE_ROOT: __ENGINE_ROOT__
<!-- GITHUB_CONTRACT_END -->

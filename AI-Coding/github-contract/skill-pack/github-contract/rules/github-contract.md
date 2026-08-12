# GitHub Contract — default coding policy

Applies in git/GitHub/public J. Apps modules and repositories.

1. **Headers** on every commentable source/config file (ecosystem banner),
   including existing Finja HTML banners. Never invalidate JSON to add one.
2. **One module version** `MAJOR.FEATURES.BUGS` in all files; per-file changelog OK.
3. **No secret or private-path leaks** in production trees: absolute drive/user
   paths, UNC/NAS paths and private LAN addresses are forbidden.
4. **README**: version + License + Support (J. Apps).
5. Before done: `github-contract scan . --version <module-version>` if you touched many files.

Generate headers: `github-contract header --kind py --version 1.0.0 --title "..." --module "..."`.

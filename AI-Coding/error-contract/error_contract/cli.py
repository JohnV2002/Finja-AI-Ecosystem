"""
======================================================================
                         Error Contract
======================================================================

  Project: J. Apps - AI-Coding Tooling
  Module:  error_contract/cli.py
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.3.2
  Description:
    Command-line interface: resolve, scan, ledger, reserve, install-skills, gate.

  New in v1.0.0:
    • Production release packaging for public GitHub
    • Cross-project engine, ambient hooks, global code ledger
    • See repository README.md / INSTALL.md / AMBIENT.md

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License.

======================================================================
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path  # noqa: TC003 - runtime Path for CLI paths

from . import __version__
from .ambient import format_gate, format_preflight, gate, preflight, save_baseline
from .detect import detect_project, load_taxonomy_for
from .docsgen import ensure_project_docs, format_ensure
from .install_skills import format_install, install_skills
from .path_wrapper import format_path_install, install_path_wrapper
from .registry import (
    format_registry_list,
    format_resolve,
    load_registry,
    register_project,
    resolve_project,
)
from .report import format_scan, format_taxonomy
from .scaffold import scaffold_project
from .scanner import scan_project
from .taxonomy import dump_contract_json, finja_reference_taxonomy, parse_exceptions_py, propose_code


def _print(msg: str) -> None:
    sys.stdout.write(msg if msg.endswith("\n") else msg + "\n")


def _csv(s: str) -> list[str]:
    if not s:
        return []
    return [p.strip() for p in s.split(",") if p.strip()]


def _prefix_from_registry(path: str, forced: str = "") -> str:
    if forced:
        return forced
    res = resolve_project(path)
    if res["status"] == "known":
        return res["effective_prefix"]
    return ""


def cmd_detect(args: argparse.Namespace) -> int:
    pref = args.prefix or _prefix_from_registry(args.path)
    prof = detect_project(args.path, prefix=pref)
    if args.json:
        _print(json.dumps(prof.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print(f"Root   : {prof.root}")
        _print(f"Prefix : {prof.prefix}")
        _print(f"Except : {prof.exceptions_path or '-'}")
        _print(f"Contr. : {prof.contract_path or '-'}")
        _print(f"Detect : {', '.join(prof.detected_systems) or '-'}")
        for n in prof.notes:
            _print(f"Note   : {n}")
        if prof.taxonomy:
            _print("")
            _print(format_taxonomy(prof.taxonomy, limit=args.limit))
    return 0


def cmd_codes(args: argparse.Namespace) -> int:
    if args.finja_builtin:
        tax = finja_reference_taxonomy()
        if args.prefix:
            tax.prefix = args.prefix.upper()
    elif args.file:
        tax = parse_exceptions_py(args.file, prefix_hint=args.prefix or "")
        if args.prefix:
            tax.prefix = args.prefix.upper()
    else:
        pref = args.prefix or _prefix_from_registry(args.path)
        _, tax = load_taxonomy_for(args.path, prefix=pref)
    if args.json:
        _print(json.dumps(tax.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print(format_taxonomy(tax, limit=args.limit))
    if args.export:
        dump_contract_json(tax, args.export)
        _print(f"Exported -> {args.export}")
    return 0


def cmd_scan(args: argparse.Namespace) -> int:
    pref = args.prefix or _prefix_from_registry(args.path)
    report = scan_project(
        args.path,
        prefix=pref,
        include_info=not args.no_info,
    )
    if args.json:
        _print(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print(format_scan(report, max_findings=args.max))
    counts = report.counts()
    if counts.get("critical") or counts.get("high"):
        return 1
    return 0


def cmd_propose(args: argparse.Namespace) -> int:
    pref = args.prefix or _prefix_from_registry(args.path)
    _, tax = load_taxonomy_for(
        args.path,
        prefix=pref,
        use_finja_builtin=args.finja_builtin,
    )
    # owner from project registry if known
    owner = args.owner or ""
    module = args.module or ""
    if not owner:
        res = resolve_project(args.path)
        if res["status"] == "known":
            owner = res["project"].get("id") or ""
            if not module:
                module = res["project"].get("module_default") or ""
    result = propose_code(
        tax,
        project_root=args.path,
        band=args.band,
        message=args.message or "",
        class_name=args.class_name or "",
        use_global_ledger=not args.local_only,
        owner_id=owner,
        module=module,
        reserve=args.reserve,
    )
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not result.get("ok"):
            _print(f"FAIL: {result.get('error')}")
            return 1
        _print(f"Proposed: {result['code']}  ({result['class_name']})")
        _print(f"Band    : {result['band']} - {result.get('band_label', '')}")
        if result.get("message_hint"):
            _print(f"Hint    : {result['message_hint']}")
        if result.get("ledger"):
            _print(f"Ledger  : {result['ledger']}  reserved={result.get('reserved')}")
        if result.get("placement_note"):
            _print(f"Note    : {result['placement_note']}")
        _print("")
        _print(result["skeleton"])
    return 0 if result.get("ok") else 1


def cmd_ledger(args: argparse.Namespace) -> int:
    from .ledger import format_ledger, load_ledger, load_namespace_ledger

    led = load_namespace_ledger(args.prefix, Path.cwd()) if args.prefix else load_ledger()
    if args.json:
        _print(json.dumps(led.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print(format_ledger(led, prefix=args.prefix or "", limit=args.limit))
    return 0


def cmd_code(args: argparse.Namespace) -> int:
    """Look up one branded code in its canonical namespace registry."""
    from .ledger import load_namespace_ledger

    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_]*)-(\d+)", args.code.strip())
    if not match:
        _print("FAIL: expected PREFIX-NUM, for example FINJA-406")
        return 1
    prefix, number = match.group(1).upper(), int(match.group(2))
    claim = load_namespace_ledger(prefix, Path.cwd()).get(prefix, number)
    if not claim:
        _print(f"{prefix}-{number}: unreserved")
        return 1
    if args.json:
        _print(json.dumps(claim.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print(claim.branded())
        _print(f"Owner      : {claim.owner_id or '-'}")
        _print(f"Module     : {claim.module or '-'}")
        _print(f"Type       : {claim.class_name}")
        _print(f"Category   : {claim.band}")
        _print(f"Description: {claim.description or '-'}")
        _print(f"Source     : {claim.source_path or 'registry-only'}")
    return 0


def cmd_category(args: argparse.Namespace) -> int:
    """Add a new, project-defined numeric category to the public root legend."""
    from .ledger import load_namespace_ledger

    prefix = (args.prefix or _prefix_from_registry(args.path) or "").upper()
    if not prefix:
        _print("FAIL: --prefix required (or register the project first)")
        return 1
    match = re.fullmatch(r"(\d+)\s*-\s*(\d+)", args.range.strip())
    if not match:
        _print("FAIL: --range must look like 1400-1499")
        return 1
    ledger = load_namespace_ledger(prefix, args.path)
    try:
        ledger.add_category(
            prefix,
            args.name,
            int(match.group(1)),
            int(match.group(2)),
            args.description or "",
            force=args.force,
        )
        ledger.save()
    except ValueError as error:
        _print(f"FAIL: {error}")
        return 1
    category = ledger.categories_for(prefix)[args.name.strip().lower().replace("-", "_")]
    _print(f"Added category: {prefix} / {args.name} = {category[0]}-{category[1]}")
    _print(f"Legend        : {ledger.path}")
    return 0


def cmd_ledger_import(args: argparse.Namespace) -> int:
    from .ledger import bootstrap_finja_core, import_taxonomy_into_ledger, load_ledger

    led = load_ledger()
    if args.finja_core:
        path = args.finja_core
        if not path:
            _print("FAIL: pass --finja-core PATH/to/core/exceptions.py")
            return 1
        result = bootstrap_finja_core(led, path, owner_id=args.owner or "finja")
    elif args.file:
        tax = parse_exceptions_py(args.file, prefix_hint=args.prefix or "APP")
        if args.prefix:
            tax.prefix = args.prefix.upper()
        result = import_taxonomy_into_ledger(
            led,
            prefix=tax.prefix,
            owner_id=args.owner or "unknown",
            tax_codes=tax.codes,
            source_path=args.file,
            force=args.force,
        )
        led.save()
        result["ledger"] = str(led.path)
        result["total"] = len(led.claims_for(tax.prefix))
    else:
        _print("Need --finja-core PATH or --file exceptions.py")
        return 1
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print(f"Ledger import: {result}")
    return 1 if result.get("conflicts") else 0


def cmd_reserve(args: argparse.Namespace) -> int:
    from .ledger import load_namespace_ledger, reserve_code

    pref = (args.prefix or _prefix_from_registry(args.path) or "APP").upper()
    owner = args.owner or ""
    module = args.module or ""
    if not owner:
        res = resolve_project(args.path)
        if res["status"] == "known":
            owner = res["project"].get("id") or ""
            if not module:
                module = res["project"].get("module_default") or ""
            if not args.prefix and res.get("effective_prefix"):
                pref = res["effective_prefix"]
    if not owner:
        _print("FAIL: --owner required (or register project first)")
        return 1
    root = Path(args.path).expanduser().resolve()
    target = getattr(args, "target", "") or ""
    if getattr(args, "create_local", False) and not target:
        res = resolve_project(root)
        rel = "core/exceptions.py"
        if res["status"] == "known":
            rel = res["project"].get("exceptions_rel") or rel
        target = str(root / rel)
    led = load_namespace_ledger(pref, root)
    # local used nums if project has exceptions
    extra: set[int] = set()
    try:
        _, tax = load_taxonomy_for(args.path, prefix=pref)
        extra = tax.used_nums()
    except Exception:
        pass
    result = reserve_code(
        led,
        prefix=pref,
        band=args.band,
        owner_id=owner,
        module=module,
        description=args.message or "",
        class_name=args.class_name or "",
        source_path="",
        code_num=int(args.num) if args.num else None,
        extra_used=extra,
        persist=not bool(target),
    )
    if target and result.get("ok"):
        from .ledger import CodeClaim, apply_class_to_file
        from .manifest import build_local_manifest, relative_source, write_local_manifest
        from .taxonomy import parse_exceptions_py

        claim = CodeClaim.from_dict(result["claim"])
        target_path = Path(target).expanduser().resolve()
        existed = target_path.is_file()
        previous = target_path.read_text(encoding="utf-8-sig") if existed else ""
        ledger_existed = led.path.is_file()
        previous_ledger = led.path.read_bytes() if ledger_existed else b""
        manifest_path = root / "contracts" / "error_contract.module.json"
        manifest_existed = manifest_path.is_file()
        previous_manifest = manifest_path.read_bytes() if manifest_existed else b""
        claim.source_path = relative_source(led.path.parent, target_path)
        applied = apply_class_to_file(target_path, claim)
        result["apply"] = applied
        if applied.get("ok"):
            try:
                led.upsert(claim, force=True)
                led.save()
                tax = parse_exceptions_py(target_path, prefix_hint=pref)
                manifest = build_local_manifest(
                    root=root,
                    prefix=pref,
                    owner=owner,
                    module=module,
                    exceptions_path=target_path,
                    local_codes=tax.codes,
                    legend_path=led.path,
                )
                write_local_manifest(manifest_path, manifest)
            except Exception as error:
                if existed:
                    target_path.write_text(previous, encoding="utf-8")
                elif target_path.exists():
                    target_path.unlink()
                if ledger_existed:
                    led.path.write_bytes(previous_ledger)
                elif led.path.exists():
                    led.path.unlink()
                if manifest_existed:
                    manifest_path.write_bytes(previous_manifest)
                elif manifest_path.exists():
                    manifest_path.unlink()
                result = {"ok": False, "error": f"Atomic create rolled back: {error}"}
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        if not result.get("ok"):
            _print(f"FAIL: {result.get('error')}")
            return 1
        _print(f"Reserved: {result['code']}  owner={owner} module={module or '-'}")
        _print(result.get("note", ""))
        if result.get("apply"):
            _print(f"Apply   : {result['apply']}")
        _print("")
        _print(result.get("skeleton") or "")
    return 0 if result.get("ok") else 1


def cmd_add_code(args: argparse.Namespace) -> int:
    """reserve + optional write to module-local file (never implied core dump)."""
    args.reserve = True  # type: ignore
    # map add-code flags onto reserve
    if not getattr(args, "message", None):
        args.message = ""
    return cmd_reserve(args)


def cmd_create(args: argparse.Namespace) -> int:
    """Reserve centrally and create the module-local runtime class as one operation."""
    args.create_local = True
    return cmd_reserve(args)


def cmd_scaffold(args: argparse.Namespace) -> int:
    pref = (args.prefix or _prefix_from_registry(args.path) or "").upper()
    resolved = resolve_project(args.path)
    if not pref:
        if resolved["status"] == "needs_onboard":
            _print("Project not registered. Onboard first:")
            _print(format_resolve(resolved))
            return 2
        pref = "APP"
    written = scaffold_project(
        args.path,
        prefix=pref,
        name=args.name or "",
        package_dir=args.package,
        force=args.force,
        owner=(resolved["project"].get("id") if resolved["status"] == "known" else ""),
        module=(resolved["project"].get("module_default") if resolved["status"] == "known" else ""),
    )
    for k, v in written.items():
        _print(f"{k}: {v}")
    return 0


def cmd_slap(args: argparse.Namespace) -> int:
    """Friendly alias: scan + short AI slap summary."""
    pref = args.prefix or _prefix_from_registry(args.path)
    res = resolve_project(args.path)
    if res["status"] == "needs_onboard" and not args.prefix:
        _print("*slap* Project UNKNOWN - register before inventing errors.")
        _print(format_resolve(res))
        return 2
    report = scan_project(args.path, prefix=pref, include_info=False)
    bad = [f for f in report.findings if f.severity in {"critical", "high", "medium"}]
    pref = report.profile.prefix
    _print(f"*slap*  Error-Contract Check - {report.profile.root}")
    _print(f"Prefix: {pref} | findings: {len(report.findings)} (shown: {min(len(bad), args.max)})")
    if report.profile.taxonomy and report.profile.taxonomy.style == "missing":
        _print("!! Kein Exception-System gefunden. ensure --scaffold, nicht print(e).")
    for f in report.sorted_findings()[: args.max]:
        if f.severity == "info":
            continue
        loc = f"{f.path}:{f.line}" if f.line else f.path
        _print(f" - [{f.severity}] {f.rule} @ {loc}: {f.message}")
    if not bad:
        _print("OK: keine groben Verstöße (console.log/print/bare except).")
        return 0
    _print("")
    _print(f"Regel: strukturierte {pref}-xxx Codes. Kein console.log / print(e) als Error-Path.")
    return 1


def cmd_resolve(args: argparse.Namespace) -> int:
    result = resolve_project(args.path)
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print(format_resolve(result))
    return 0 if result["status"] in {"known", "exempt"} else 2


def cmd_register(args: argparse.Namespace) -> int:
    try:
        entry, saved = register_project(
            args.path,
            project_id=args.id or "",
            name=args.name or "",
            prefix=args.prefix,
            mode=args.mode,
            parent_id=args.parent_id or "",
            ecosystem=_csv(args.ecosystem),
            owners=_csv(args.owners),
            tags=_csv(args.tags),
            module_default=args.module_default or "",
            notes=args.notes or "",
            exceptions_rel=args.exceptions_rel,
        )
    except ValueError as e:
        _print(f"FAIL: {e}")
        return 1
    if args.json:
        _print(json.dumps({"project": entry.to_dict(), "saved": str(saved)}, indent=2, ensure_ascii=False))
    else:
        _print(f"Registered: {entry.id}")
        _print(f"  name    : {entry.name}")
        _print(f"  prefix  : {entry.prefix}  mode={entry.mode}")
        _print(f"  parent  : {entry.parent_id or '-'}")
        _print(f"  owners  : {', '.join(entry.owners) or '-'}")
        _print(f"  eco     : {', '.join(entry.ecosystem) or '-'}")
        _print(f"  paths   : {entry.paths}")
        _print(f"  saved   : {saved}")
    if args.ensure:
        res = ensure_project_docs(args.path, scaffold_if_missing=args.scaffold, force=args.force_docs)
        if args.json:
            _print(json.dumps(res, indent=2, ensure_ascii=False))
        else:
            _print(format_ensure(res))
    return 0


def cmd_projects(args: argparse.Namespace) -> int:
    reg = load_registry()
    if args.json:
        _print(json.dumps(reg.to_dict(), indent=2, ensure_ascii=False))
    else:
        _print(format_registry_list(reg))
    return 0


def cmd_ensure(args: argparse.Namespace) -> int:
    pref = args.prefix or ""
    result = ensure_project_docs(
        args.path,
        prefix=pref,
        force=args.force,
        scaffold_if_missing=args.scaffold,
        package_dir=args.package,
        project_name=args.name or "",
        write_agent_stubs=args.agent_stubs,
    )
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print(format_ensure(result))
    if result.get("status") == "needs_onboard":
        return 2
    return 0


def cmd_install_skills(args: argparse.Namespace) -> int:
    engines = _csv(args.engines) if args.engines else None
    result = install_skills(
        engines=engines,
        write_global_agents=not args.no_global_agents,
        engine_root=args.engine_root or None,
        always_active=not args.no_always_active,
    )
    if not args.no_path_wrapper:
        path_res = install_path_wrapper(args.engine_root or result.get("engine_root"))
        result["path_wrapper"] = path_res
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print(format_install(result))
        if result.get("path_wrapper"):
            _print(format_path_install(result["path_wrapper"]))
    return 0


def cmd_install_path(args: argparse.Namespace) -> int:
    result = install_path_wrapper(args.engine_root or None)
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print(format_path_install(result))
    return 0


def cmd_preflight(args: argparse.Namespace) -> int:
    result = preflight(args.path, quiet=False)
    if args.json:
        # strip huge nested resolve questions for readability unless needed
        _print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        _print(format_preflight(result))
    if not result.get("is_code_project"):
        return 0
    return 0 if result.get("status") in {"known", "needs_onboard", "exempt", "skip"} else 0


def cmd_gate(args: argparse.Namespace) -> int:
    # Force dirty if --force so CLI testing works without session edits
    if args.force:
        from .ambient import load_session_state, save_session_state

        st = load_session_state()
        st["dirty"] = True
        if args.file:
            files = list(st.get("edited_files") or [])
            p = args.file.replace("\\", "/")
            if p not in files:
                files.append(p)
            st["edited_files"] = files
        save_session_state(st)
    result = gate(
        args.path,
        only_edited=not args.all_files,
        include_info=False,
    )
    if args.json:
        _print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        _print(format_gate(result))
    if result.get("skipped"):
        return 0
    return 0 if result.get("ok") else 1


def cmd_baseline(args: argparse.Namespace) -> int:
    pref = args.prefix or ""
    res = resolve_project(args.path)
    if res["status"] == "known":
        pref = res["effective_prefix"]
    report = scan_project(args.path, prefix=pref, include_info=False)
    path = save_baseline(Path(args.path).expanduser().resolve(), report)
    _print(f"Baseline saved: {path} ({len(report.findings)} findings)")
    return 0


def cmd_seed_finja(args: argparse.Namespace) -> int:
    """Convenience: register Finja Nervenzentrale as parent root."""
    path = args.path
    if not path or str(path).strip() in {".", ""}:
        _print("FAIL: seed-finja requires an explicit path to your Finja core checkout")
        _print('  example: error-contract seed-finja "<finja-root>"')
        return 1
    entry, saved = register_project(
        path,
        project_id="finja",
        name="Finja Nervenzentrale V2",
        prefix="FINJA",
        mode="own_prefix",
        owners=["finja"],
        ecosystem=["finja"],
        exceptions_rel="core/exceptions.py",
        notes="Reference taxonomy 1xx-11xx. Parent for Finja-ecosystem modules.",
    )
    _print(f"Seeded finja -> {saved}")
    _print(f"  paths: {entry.paths}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="error_contract",
        description="Cross-project Error Contract - dynamic registry, scan, docs, skills.",
    )
    p.add_argument("--version", action="version", version=f"error_contract {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_path(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("path", nargs="?", default=".", help="Project root (default: .)")
        sp.add_argument("--prefix", default="", help="Force code prefix")
        sp.add_argument("--json", action="store_true", help="JSON output")

    d = sub.add_parser("detect", help="Detect exception system + prefix")
    add_path(d)
    d.add_argument("--limit", type=int, default=0, help="Max codes to list (0=all)")
    d.set_defaults(func=cmd_detect)

    c = sub.add_parser("codes", help="List taxonomy codes (Source of Truth)")
    add_path(c)
    c.add_argument("--file", default="", help="Parse this exceptions.py directly")
    c.add_argument("--finja-builtin", action="store_true", help="Use built-in Finja reference taxonomy")
    c.add_argument("--export", default="", help="Write contract JSON to path")
    c.add_argument("--limit", type=int, default=0)
    c.set_defaults(func=cmd_codes)

    s = sub.add_parser("scan", help="Scan for print/console/broad-except violations")
    add_path(s)
    s.add_argument("--max", type=int, default=80, help="Max findings to print")
    s.add_argument("--no-info", action="store_true", help="Hide info-level (e.g. 999 usage)")
    s.set_defaults(func=cmd_scan)

    pr = sub.add_parser("propose", help="Propose next free code (local + canonical namespace registry)")
    add_path(pr)
    pr.add_argument("--band", required=True, help="Band: config|llm|memory|session|tool|pipeline|host|...")
    pr.add_argument("--message", default="", help="What failed (for class name / hint)")
    pr.add_argument("--class-name", default="", help="Force class name")
    pr.add_argument("--owner", default="", help="Owner project id (for --reserve)")
    pr.add_argument("--module", default="", help="module= tag (e.g. finja-chat)")
    pr.add_argument("--reserve", action="store_true", help="Also lock number in the namespace registry")
    pr.add_argument("--local-only", action="store_true", help="Ignore the repository legend when picking a free number")
    pr.add_argument("--finja-builtin", action="store_true")
    pr.set_defaults(func=cmd_propose)

    ld = sub.add_parser("ledger", help="Show global prefix code ledger (FINJA-820 unique world-wide)")
    ld.add_argument("--prefix", default="", help="Filter prefix e.g. FINJA")
    ld.add_argument("--limit", type=int, default=0)
    ld.add_argument("--json", action="store_true")
    ld.set_defaults(func=cmd_ledger)

    one = sub.add_parser("code", help="Look up one PREFIX-NUM in its namespace registry")
    one.add_argument("code", help="For example FINJA-406")
    one.add_argument("--json", action="store_true")
    one.set_defaults(func=cmd_code)

    category = sub.add_parser("category", help="Add a new numeric range to the public root legend")
    add_path(category)
    category.add_argument("name", help="Category name, for example multimodal")
    category.add_argument("--range", required=True, help="Inclusive range, for example 1400-1499")
    category.add_argument("--description", default="")
    category.add_argument("--force", action="store_true", help="Replace an existing category definition")
    category.set_defaults(func=cmd_category)

    li = sub.add_parser("ledger-import", help="Import existing exceptions.py into ledger")
    li.add_argument(
        "--finja-core",
        default="",
        help="Path to core/exceptions.py to import into the public repository legend",
    )
    li.add_argument("--file", default="", help="Any exceptions.py")
    li.add_argument("--prefix", default="FINJA")
    li.add_argument("--owner", default="finja", help="Owner id claiming these codes")
    li.add_argument("--force", action="store_true")
    li.add_argument("--json", action="store_true")
    li.set_defaults(func=cmd_ledger_import)

    rv = sub.add_parser(
        "reserve",
        help="Reserve a unique PREFIX-num for an owner (optional write to module file, not always core)",
    )
    add_path(rv)
    rv.add_argument("--band", required=True)
    rv.add_argument("--message", default="")
    rv.add_argument("--class-name", default="")
    rv.add_argument("--owner", default="", help="e.g. finja-chat, finja, obs-bridge")
    rv.add_argument("--module", default="", help="module= tag")
    rv.add_argument("--num", default="", help="Force code number (must be free)")
    rv.add_argument(
        "--target",
        default="",
        help="Optional module-local exceptions file to append class (omit = ledger only)",
    )
    rv.set_defaults(func=cmd_reserve)

    ac = sub.add_parser(
        "add-code",
        help="Alias of reserve: unique number + optional --target file (never auto-dumps into Finja core)",
    )
    add_path(ac)
    ac.add_argument("--band", required=True)
    ac.add_argument("--message", default="")
    ac.add_argument("--class-name", default="")
    ac.add_argument("--owner", default="")
    ac.add_argument("--module", default="")
    ac.add_argument("--num", default="")
    ac.add_argument("--target", default="", help="Module-local file; leave empty for ledger-only")
    ac.set_defaults(func=cmd_add_code)

    cr = sub.add_parser(
        "create",
        help="Atomically reserve in the namespace registry and add the module-local class",
    )
    add_path(cr)
    cr.add_argument("class_name")
    cr.add_argument("--band", required=True)
    cr.add_argument("--message", default="")
    cr.add_argument("--owner", default="")
    cr.add_argument("--module", default="")
    cr.add_argument("--num", default="")
    cr.add_argument("--target", default="", help="Override registered module-local exceptions file")
    cr.set_defaults(func=cmd_create, create_local=True)

    sc = sub.add_parser("scaffold", help="Create local exceptions plus root legend and module manifest")
    add_path(sc)
    sc.add_argument("--name", default="", help="Human project name")
    sc.add_argument("--package", default="core", help="Package dir for exceptions.py (default: core)")
    sc.add_argument("--force", action="store_true", help="Overwrite existing files")
    sc.set_defaults(func=cmd_scaffold)

    sl = sub.add_parser("slap", help="Short agent-facing slap report")
    add_path(sl)
    sl.add_argument("--max", type=int, default=25)
    sl.set_defaults(func=cmd_slap)

    rs = sub.add_parser("resolve", help="Lookup project in dynamic registry (or needs_onboard)")
    add_path(rs)
    rs.set_defaults(func=cmd_resolve)

    rg = sub.add_parser("register", help="Register/update a project in the user registry")
    rg.add_argument("path", nargs="?", default=".", help="Project root")
    rg.add_argument("--json", action="store_true")
    rg.add_argument("--id", default="", help="Stable project id (slug)")
    rg.add_argument("--name", default="", help="Display name")
    rg.add_argument(
        "--prefix",
        required=True,
        help="Code prefix (FINJA, OMNI, ...). Overridden by parent in inherit/module modes.",
    )
    rg.add_argument(
        "--mode",
        default="own_prefix",
        choices=["own_prefix", "inherit_parent", "module_under_parent"],
    )
    rg.add_argument("--parent-id", default="", help="Parent project id (inherit/module modes)")
    rg.add_argument("--owners", default="", help="Comma-separated owners (finja,vpet,...)")
    rg.add_argument("--ecosystem", default="", help="Comma-separated ecosystem tags")
    rg.add_argument("--tags", default="", help="Extra tags")
    rg.add_argument("--module-default", default="", help="Default module= for module_under_parent")
    rg.add_argument("--notes", default="")
    rg.add_argument("--exceptions-rel", default="core/exceptions.py")
    rg.add_argument("--ensure", action="store_true", help="Run ensure after register")
    rg.add_argument("--scaffold", action="store_true", help="With --ensure: scaffold exceptions if missing")
    rg.add_argument("--force-docs", action="store_true")
    rg.set_defaults(func=cmd_register)

    pl = sub.add_parser("projects", help="List registered projects")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=cmd_projects)

    en = sub.add_parser("ensure", help="Maintain the root legend and local module manifest")
    add_path(en)
    en.add_argument("--scaffold", action="store_true", help="Also scaffold exceptions.py if missing")
    en.add_argument("--force", action="store_true", help="Rewrite docs even if present")
    en.add_argument("--package", default="core")
    en.add_argument("--name", default="")
    en.add_argument(
        "--agent-stubs",
        action="store_true",
        help="Opt in to local AGENTS/CLAUDE pointer files (global installation normally suffices)",
    )
    en.set_defaults(func=cmd_ensure)

    inst = sub.add_parser(
        "install-skills",
        help="Install skill + ALWAYS-ACTIVE globals + PATH wrapper (no slash needed)",
    )
    inst.add_argument("--engines", default="grok,codex,claude", help="Comma list: grok,codex,claude")
    inst.add_argument("--engine-root", default="", help="Override path to this plugin repo")
    inst.add_argument("--no-global-agents", action="store_true", help="Skip AGENTS.md / CLAUDE.md")
    inst.add_argument(
        "--no-always-active",
        action="store_true",
        help="Only copy skill folders; do not upsert always-on global rules",
    )
    inst.add_argument(
        "--no-path-wrapper",
        action="store_true",
        help="Skip installing global error-contract.cmd on PATH",
    )
    inst.add_argument("--json", action="store_true")
    inst.set_defaults(func=cmd_install_skills)

    ip = sub.add_parser("install-path", help="Only install error-contract PATH wrapper (.cmd)")
    ip.add_argument("--engine-root", default="", help="Override path to this plugin repo")
    ip.add_argument("--json", action="store_true")
    ip.set_defaults(func=cmd_install_path)

    sf = sub.add_parser("seed-finja", help="Register Finja Nervenzentrale as FINJA parent")
    sf.add_argument(
        "path",
        help="Absolute path to your Finja core checkout (required; no machine-specific default)",
    )
    sf.set_defaults(func=cmd_seed_finja)

    pf = sub.add_parser("preflight", help="Ambient resolve + write .error_contract/ACTIVE.md")
    add_path(pf)
    pf.set_defaults(func=cmd_preflight)

    gt = sub.add_parser("gate", help="Post-change check: NEW findings vs baseline (edited files)")
    add_path(gt)
    gt.add_argument("--force", action="store_true", help="Treat session as dirty (CLI testing)")
    gt.add_argument("--all-files", action="store_true", help="Do not filter to edited files only")
    gt.add_argument("--file", default="", help="Pretend this file was edited (with --force)")
    gt.set_defaults(func=cmd_gate)

    bl = sub.add_parser("baseline", help="Snapshot current findings as baseline debt")
    add_path(bl)
    bl.set_defaults(func=cmd_baseline)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())

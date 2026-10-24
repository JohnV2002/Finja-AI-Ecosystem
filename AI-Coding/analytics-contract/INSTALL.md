# Analytics Contract v1.0.1 — Install Guide

**Project:** J. Apps - AI-Coding Tooling
**Version:** 1.0.1

From this module:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Or manually:

```powershell
python -m pip install -e .
python -m analytics_contract install-skills
analytics-contract --version
```

This installs the skill and always-active rules for Codex, Grok and Claude. Open
a new agent session after installation. Project analytics still remains disabled
until its `analytics_contract.json` explicitly sets `analytics.enabled` to true.

## Verify

```powershell
python -m unittest discover -v
analytics-contract detect .
analytics-contract init .
analytics-contract validate .
```

Do not commit real collector IPs or tokens. Configure them through
`ANALYTICS_ENDPOINT` and `ANALYTICS_TOKEN` at runtime.

## License

**MIT** © 2024–2026 J. Apps — full text: repository root
[`LICENSE`](../../LICENSE).

## Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)


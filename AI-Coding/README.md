# AI-Coding Contracts

**Project:** Finja AI Ecosystem  
**Module:** AI-Coding  
**Author:** J. Apps (JohnV2002 / Sodakiller1)  
**Copyright:** (c) 2026 J. Apps — Licensed under the MIT License.

AI-Coding contains the development contracts used by Codex, Grok and Claude in
the J. Apps workflow. These are coding assistants and repository guardrails —
they are not part of Finja's Twitch runtime and do not carry a Finja module's
identity into unrelated projects.

This README is the index for the folder. Each contract keeps its own detailed
README, installation guide, engine and tests one level below it.

## Included Contracts

| Contract | Version | Purpose | Documentation |
|----------|---------|---------|---------------|
| Error Contract | 1.3.2 | Structured error namespaces, public code legends, local implementations and baseline-aware gates | [Open README](error-contract/README.md) |
| GitHub Contract | 1.1.1 | Project-native headers, module-wide versions, README completeness and leak prevention | [Open README](github-contract/README.md) |

## Repository Model

```text
Finja-AI-Ecosystem/
├── README.md                         ecosystem overview
├── error_contract.json               public error-code legend
└── AI-Coding/
    ├── README.md                     this index
    ├── error-contract/
    │   └── README.md                 Error Contract details
    └── github-contract/
        └── README.md                 GitHub Contract details
```

The public [`../error_contract.json`](../error_contract.json) is readable
without installing either contract. It records all known namespaces, codes,
owners, meanings and logical source locations in one place.

Module-local `contracts/error_contract.module.json` files are only small
implementation indexes. Local `.error_contract/` and `.github_contract/`
folders are regenerated scanner state and must remain ignored.

## Installation

Install both contracts from their respective folders:

```powershell
cd AI-Coding\error-contract
python -m error_contract install-skills --engines grok,codex,claude

cd ..\github-contract
python -m github_contract install-skills
```

The installers configure the skills and lifecycle hooks for the supported
agents. Review and trust the installed Codex hooks once through `/hooks`, then
start a new task. Grok can reload its hooks or start a new session.

## Everyday Workflow

```text
error-contract preflight .
error-contract create . DedicatedFailureError --band tool --message "What failed"
error-contract category . api_auth --prefix FINJA --range 1600-1699
error-contract code FINJA-406
error-contract slap .

github-contract preflight .
github-contract scan . --version X.Y.Z
```

Number categories are defined by each namespace in the repository-root legend;
the engine does not impose a fixed maximum. New categories must have an
intentional meaning and a non-overlapping range before codes are created in
them.

## Development Checks

Run each contract's checks from its own folder:

```powershell
cd AI-Coding\error-contract
python -m unittest discover -v
github-contract scan . --version 1.3.2

cd ..\github-contract
python -m unittest discover -v
github-contract scan . --version 1.1.1
```

## License

**MIT** (c) 2026 J. Apps — full text: repository root
[`LICENSE`](../LICENSE). No duplicate license copy is kept here.

## Support & Contact

- **Email:** contact@jappshome.de
- **Website:** [jappshome.de](https://jappshome.de)
- **Support:** [Buy Me a Coffee](https://buymeacoffee.com/J.Apps)

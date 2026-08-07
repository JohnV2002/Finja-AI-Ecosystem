## Summary

<!-- What does this PR change, in 1–3 sentences? -->

## Module(s)

<!-- e.g. finja-chat, finja-weather, tools/, root README -->

- [ ] Affects Docker image / `docker-compose`
- [ ] Affects public API / env vars (document in module README)
- [ ] Affects dependencies (`requirements*.txt` / lock / pin)

## Checklist

- [ ] I ran relevant tests for the module(s) I touched (see [`TESTING.md`](../TESTING.md))
- [ ] Coverage still generated in CI (`pytest --cov --cov-branch --cov-report=xml` → Codecov)
- [ ] No secrets, cookies, or real `.env` values in the diff (incl. `CODECOV_TOKEN` only via GitHub Secrets)
- [ ] New third-party imports are reflected in the nearest `requirements*.txt`  
      (`python tools/dependency_guard.py --module <path>` if unsure)
- [ ] License / attribution: no new “must keep UI credit” rules; code stays MIT unless Apache submodule
- [ ] Character / brand / private prompts or weights are **not** being published by accident

## Test plan

<!-- How did you verify? Commands, manual steps, CI expectations -->

1.
2.

## Notes for reviewers

<!-- Risk areas, follow-ups, screenshots if UI -->

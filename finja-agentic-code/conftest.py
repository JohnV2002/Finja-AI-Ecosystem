"""
======================================================================
      Flare (Finja Agentic Code) – Shared Test Configuration
======================================================================

  Project: Finja - Twitch Interactivity Suite
  Module:  finja-agentic-code / tests
  Author:  J. Apps (JohnV2002 / Sodakiller1)
  Version: 1.11.0
  Description: Test-wide fixtures.

  New in v1.11.0:
    - Switches submission rate limiting off for every test by default.

----------------------------------------------------------------------

  The orchestrator rate-limits POST /jobs and POST /incidents with buckets
  that live for the lifetime of the process. Left on, a test module that
  submits a dozen jobs would start receiving 429 for reasons that have
  nothing to do with what it tests, and which test failed would depend on
  the order they ran in. So the limit is off unless a test asks for it:
  test_rate_limit.py turns it back on and resets the buckets itself.

----------------------------------------------------------------------

  Copyright (c) 2026 J. Apps
  Licensed under the MIT License

======================================================================
"""
import sys

import pytest


@pytest.fixture(autouse=True)
def _rate_limiting_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # The orchestrator is imported by name from orchestrator/app by the test
    # modules that need it, so look it up instead of importing it here.
    main = sys.modules.get("main")
    if main is not None and hasattr(main, "RATE_LIMITING_ENABLED"):
        monkeypatch.setattr(main, "RATE_LIMITING_ENABLED", False)
        main.SUBMISSION_LIMITER.reset()


@pytest.fixture(autouse=True)
def _supervisor_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # A TestClient used as a context manager runs the app lifespan; a real
    # supervisor thread sweeping a test's job folder would make results timing
    # dependent. test_supervisor.py drives sweeps by hand instead.
    main = sys.modules.get("main")
    if main is not None and hasattr(main, "SUPERVISOR_ENABLED"):
        monkeypatch.setattr(main, "SUPERVISOR_ENABLED", False)

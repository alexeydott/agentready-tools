# Interactive acceptance matrix

This matrix is the bounded L3 acceptance contract for the canonical v2
dashboard. Automated cases use the existing `scripts/dashboard-interactive.py`
runner or deterministic pytest/API fixtures. No raw page content, credentials,
or unsanitized screenshots belong in repository artifacts.

| Case | Coverage | Evidence path | Mode |
| --- | --- | --- | --- |
| IT-01 | Standard v2 audit and report persistence | `dashboard-interactive.py --target <local SiteLab URL>` | Automated headed |
| IT-02 | SEO profile, findings, inventory and localized report | Same runner, `--target <local SiteLab URL>` | Automated headed |
| IT-03 | Rendered Chromium audit and JS-discovered links | Same runner with Playwright/Edge | Automated headed |
| IT-04 | Virtual robots simulation and blocked URL projection | `tests/test_robots_simulation_service.py`, dashboard smoke | Automated fixture |
| IT-05 | Duplicate cluster list/detail and threshold projection | `tests/test_duplicates.py`, `/v2/runs/{run_id}/duplicates` | Automated fixture; no dedicated headed scenario |
| IT-06 | Project/run history and baseline selection | `tests/test_projects.py`, dashboard history controls | Automated fixture; no dedicated headed scenario |
| IT-07 | Durable schedule lease/catch-up/cancellation | `tests/test_schedules.py` | Automated fixture; no dedicated headed scenario |
| IT-08 | Finding remediation and selective rescan lineage | `tests/test_server.py`, dashboard rescan controls | Automated fixture; no dedicated headed scenario |
| IT-09 | EN/RU report download, print action and reload persistence | Existing headed runner download/print checks | Automated headed |
| IT-10 | Independent provider call budget under concurrency | `tests/test_acceptance_matrix.py::test_it10_provider_budget_caps_independent_fake_calls_under_concurrency` | Automated deterministic |
| IT-11 | Trusted loopback authenticated audit and redaction | `tests/test_trusted_audit.py`; local credentialed smoke only | Manual credentialed; never default CI |
| IT-12 | Narrow viewport, keyboard/focus, current-page-only inventory DOM | Existing headed runner narrow viewport/focus checks | Automated headed |

## Execution and retention

Run the stable browser cases against a local fixture or explicitly supplied
public target:

```powershell
python scripts/dashboard-interactive.py `
  --url http://127.0.0.1:8765 `
  --target http://127.0.0.1:<fixture-port> `
  --headed
```

The runner prints one JSON result per check. CI may retain sanitized console
diagnostics and bounded screenshots as short-lived artifacts; it must not retain
cookies, authorization headers, raw AI chat, full page bodies, or credentialed
IT-11 recordings. Missing optional AI providers are explicit skips, not failed
product checks.

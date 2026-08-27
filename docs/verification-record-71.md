# Verification record: PR #71

> PR: #71 (stage-f-freeze-34)
> Base: master@4c13023cad872a87c415fa5854bc51a12307bb75

## Test results

```
pytest -q -ra
1096 passed, 30 skipped, 3 xfailed in 219.39s (0:03:39)
```

### Freeze matrix tests (test_e_freeze_matrix.py)

```
14 passed in 2.42s
```

- test_frozen_catalog_is_unchanged PASSED
- test_semantics_artifact_pin_tracks_the_same_catalog PASSED
- test_registered_evaluator_targets_are_frozen PASSED
- test_score_model_id_is_frozen PASSED
- test_deferred_declared_not_produced_set_is_frozen PASSED
- test_frozen_retired_set_is_frozen PASSED
- test_frozen_intentionally_unbound_set_is_frozen PASSED
- test_retired_rows_have_terminal_resolution_status PASSED
- test_intentionally_unbound_rows_have_terminal_resolution_status PASSED
- test_retired_rows_are_never_bindable PASSED
- test_intentionally_unbound_rows_are_never_bindable PASSED
- test_no_duplicate_rule_ids_across_all_sets PASSED
- test_all_plan_references_have_disposition PASSED
- test_all_plan_references_have_terminal_classification PASSED

## verify-local

```
powershell -ExecutionPolicy Bypass -File scripts/verify-local.ps1
exit=0
dirty=false
```

## Artifact verification

| Check | Result |
|-------|--------|
| Catalog version matches baseline | ✅ 2.1.0-draft.2 |
| Catalog digest matches baseline | ✅ d596780a… |
| Semantics version matches baseline | ✅ 1.0.4 |
| Semantics digest matches baseline | ✅ 4c678b79… |
| Score model matches baseline | ✅ readiness-transparent-v2 |
| Evaluator targets match baseline | ✅ All 6 registries |
| Retired set matches reconciliation | ✅ 20 IDs |
| Unbound set matches reconciliation | ✅ 6 IDs |
| No bound/retired overlap | ✅ Clean |
| No bound/unbound overlap | ✅ Clean |

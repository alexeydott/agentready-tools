"""Known semantic deltas frozen as golden (Stage-2 freeze mode, #34).

The golden classification table freezes CURRENT runtime verdicts. Two cells
diverge from the accepted semantics artifact; each is a tracked follow-up —
they must never be silently accepted as equivalent.
"""

from __future__ import annotations

KNOWN_DELTAS = {
    "D1": {
        "cell": "CORE-CANON-002 @ off-origin-single",
        "accepted": "fail",
        "actual": "pass",
        "tracking": "#34 (Stage-2 follow-up)",
        "summary": "scheme/host drift vs audited origin is not enforced by the bound evaluator",
    },
    "D2": {
        "cell": "CORE-CANON-005 @ paginated-canonical-drift",
        "accepted": "fail",
        "actual": "pass",
        "tracking": "#34 (Stage-2 follow-up)",
        "summary": "rel-pagination signal is not consulted by the bound evaluator",
    },
}


def test_known_deltas_are_documented_and_tracked():
    assert set(KNOWN_DELTAS) == {"D1", "D2"}
    for key, delta in KNOWN_DELTAS.items():
        assert delta["accepted"] != delta["actual"], key
        assert "#34" in delta["tracking"], key
        assert delta["summary"], key


def test_golden_table_marks_every_delta_cell():
    import inspect

    import test_stage_f_canon_golden as g

    src = inspect.getsource(g)
    for key, delta in KNOWN_DELTAS.items():
        assert f"DELTA-{key}" in src, key
        row = next(r for r in g.EXPECTED_TABLE if r[0] == delta["cell"].split(" @ ")[1])
        assert row[1] == "fail", key

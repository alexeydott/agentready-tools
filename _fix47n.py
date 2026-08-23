import ast
import pathlib

TS = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_link_evaluators.py"
)
t = TS.read_text(encoding="utf-8")

# 1. Option A: resources@1 now produced — import adapter, extend fixture
old_imp = """from agentready.audit_core.collection import (
    page_fact_envelope,
    parsed_facts_from_dict,
)"""
new_imp = """from agentready.audit_core.collection import (
    page_fact_envelope,
    parsed_facts_from_dict,
    resource_fact_envelope,
)"""
assert old_imp in t
t = t.replace(old_imp, new_imp, 1)

# 2. docstring update
t = t.replace(
    "CORE-LINK-002/005\nare declared_not_produced: evaluator functions stay covered via direct\ninvocation, but no registry binding exists until resources@1 production lands\n(Option A upgrade path).",
    "CORE-LINK-002/005 are bound via the produced\nresources@1 envelope (Option A executed): evaluator functions are covered by\ndirect contract-preparation tests AND registry bindings.",
)

# 3. BOUND/DEFERRED constants -> all six bound; keep deferred list for history
t = t.replace(
    'BOUND_RULES = ("CORE-LINK-001", "CORE-LINK-003", "CORE-LINK-004", "CORE-LINK-006")\nDEFERRED_RULES = ("CORE-LINK-002", "CORE-LINK-005")',
    'BOUND_RULES = (\n    "CORE-LINK-001",\n    "CORE-LINK-002",\n    "CORE-LINK-003",\n    "CORE-LINK-004",\n    "CORE-LINK-005",\n    "CORE-LINK-006",\n)\nFORMERLY_DEFERRED = ("CORE-LINK-002", "CORE-LINK-005")',
)

# 4. fixture: add resources envelope builder into _facts/_facts_for
old_fixture_tail = '''        "representation": _representation_value(),
    }'''
if old_fixture_tail in t:
    t = t.replace(
        old_fixture_tail,
        '''        "representation": _representation_value(),
        "resources": _resources_value(),
    }''',
        1,
    )

ast.parse(t)
TS.write_text(t, encoding="utf-8", newline="\n")
print("step A applied")

import ast
import pathlib

TS = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_link_evaluators.py"
)
t = TS.read_text(encoding="utf-8")

old = '''def test_declared_not_produced_rules_are_not_bindable(rule_id):
    with pytest.raises(UnregisteredRuleError):
        LINK_EVALUATOR_REGISTRY.resolve(rule_id, CORE_LINK_RULE_VERSION)'''
new = '''def test_formerly_deferred_rules_are_now_bindable(rule_id):
    """Option A executed: resources@1 produced, 002/005 bound like siblings."""
    binding = LINK_EVALUATOR_REGISTRY.resolve(rule_id, CORE_LINK_RULE_VERSION)
    assert binding is not None'''
assert old in t
t = t.replace(old, new)

# also flip the registry-scope test name/expectation if it asserts only four
t = t.replace(
    "def test_registry_scoped_to_bound_rules_only():",
    "def test_registry_covers_all_six_link_rules():",
    1,
)

ast.parse(t)
TS.write_text(t, encoding="utf-8", newline="\n")
print("deferred->bindable flipped")

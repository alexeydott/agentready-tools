import ast
import pathlib

TS = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_e_wave1_reconciliation.py"
)
t = TS.read_text(encoding="utf-8")

# resources@1 now produced (Option A): remove it from forbidden sets everywhere
t = t.replace(
    'families == {"links", "structured-data"}',
    'families == {"links", "structured-data"}',
)
t = t.replace(
    'non_emitted_registered_families: [links, structured-data]',
    'non_emitted_registered_families: [links, structured-data]',
)
# forbidden family tuples/sets inside gate8 tests
t = t.replace(
    'families = ("links", "transport", "resources", "structured-data")',
    'families = ("links", "transport", "structured-data")',
)
t = t.replace(
    "families = {\"links\", \"transport\", \"resources\", \"structured-data\"}",
    "families = {\"links\", \"transport\", \"structured-data\"}",
)
t = t.replace(
    "families = (\"links\", \"resources\", \"structured-data\")",
    "families = (\"links\", \"structured-data\")",
)
t = t.replace(
    "non_emitted_registered_families: [links, resources, structured-data]",
    "non_emitted_registered_families: [links, structured-data]",
)

ast.parse(t)
TS.write_text(t, encoding="utf-8", newline="\n")
print("wave1 gates updated")

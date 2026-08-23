import ast
import pathlib
import re

TS = pathlib.Path(
    r"D:\projects\externals\agentready-tools\tests\test_stage_f_desc_golden.py"
)
t = TS.read_text(encoding="utf-8")

# replace direct fixture param with internal loader in the two tests
t = t.replace(
    "def test_manifest_pins_the_live_catalog(manifest):",
    "def test_manifest_pins_the_live_catalog():\n    manifest = _load_manifest()",
    1,
)
t = t.replace(
    "def test_classification_vocabulary_is_respected(manifest):",
    "def test_classification_vocabulary_is_respected():\n    manifest = _load_manifest()",
    1,
)

ast.parse(t)
TS.write_text(t, encoding="utf-8", newline="\n")
print("fixture params replaced")

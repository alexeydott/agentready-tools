import ast
import warnings
from pathlib import Path


def test_finding_evidence_status_contracts_use_explicit_allowlist():
    allowed = {
        "AtomicFinding",
        "Evidence",
        "EvidenceReference",
        "Finding",
        "FindingContract",
        "FindingKey",
        "FindingStateHash",
        "FindingRecord",
        "InteractionEvidence",
        "InteractionFinding",
        "InteractionStatus",
        "ProtocolEvidence",
        "ProtocolFinding",
        "ProtocolStatus",
        "ProviderStatus",
        "RobotsFetchStatus",
        "SeoPageEvidence",
        "Status",
        "FindingEvidence",
        "FindingStatus",
        "IdentityEvidenceSource",
        "JobStatus",
    }
    source_root = Path(__file__).parents[1] / "src" / "agentready"
    found = set()
    for path in source_root.rglob("*.py"):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(path.read_text(encoding="utf-8"))
        found.update(
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ClassDef)
            and (
                node.name.endswith("Finding")
                or node.name.endswith("Evidence")
                or node.name.endswith("Status")
            )
        )
    assert found <= allowed

import ast
import pathlib

COL = pathlib.Path(r"D:\projects\externals\agentready-tools\src\agentready\audit_core\collection.py")
t = COL.read_text(encoding="utf-8")

anchor = "def run_projection_fact_envelope("
adapter = '''def resource_fact_envelope(
    *,
    subject_url: str,
    resources: tuple[Mapping[str, Any], ...] = (),
    observed_at: str,
    representation_id: str | None = None,
    envelope_id: str | None = None,
) -> FactEnvelope:
    """Build the sanctioned ``resources@1`` evaluation envelope.

    ``resources`` are declared-resource rows (url / resolved_url /
    resource_type) as collected for the subject. Envelope identity is
    deterministic over subject URL, observation timestamp, representation id
    and the canonical resource rows.
    """
    identity = UrlIdentity.parse(subject_url)
    if not observed_at or not observed_at.strip():
        raise ValueError("resource fact envelope requires a non-empty observed_at")
    normalized_rows = sorted(
        (
            str(row.get("url", "")),
            str(row.get("resolved_url") or ""),
            str(row.get("resource_type", "")),
        )
        for row in resources
        if isinstance(row, Mapping)
    )
    payload: dict[str, object] = {"resources": [
        {"url": u, "resolved_url": ru, "resource_type": rt}
        for (u, ru, rt) in normalized_rows
    ]}
    digest_input = json.dumps(
        [identity.normalized(), observed_at, representation_id or "", payload],
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    from .fact_schema import DEFAULT_FACT_SCHEMA_VERSIONS

    resolved_id = envelope_id or (
        "resources-fact:"
        + hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    )
    return FactEnvelope(
        id=resolved_id,
        kind="resources",
        target=identity,
        value=payload,
        observed_at=observed_at,
        representation_id=representation_id,
        schema_family="resources",
        schema_version=DEFAULT_FACT_SCHEMA_VERSIONS["resources"],
    )


'''
i = t.index(anchor)
t = t[:i] + adapter + t[i:]

# imports: hashlib/json may already exist; ensure UrlIdentity imported
if "import hashlib" not in t:
    t = t.replace("from collections.abc import Iterable, Mapping", "import hashlib\nimport json\nfrom collections.abc import Iterable, Mapping", 1)

ast.parse(t)
COL.write_text(t, encoding="utf-8", newline="\n")
print("resource adapter added")

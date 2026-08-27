from pathlib import Path

from agentready.compatibility import COMPATIBILITY


def test_release_compatibility_manifest_exposes_only_v2_surfaces():
    payload = COMPATIBILITY.to_dict()
    assert payload["release"] == "0.14.0rc1"
    assert "agentready.ai-assistant.v2" in payload["schemas"]
    assert "agentready.protocol-findings.v2" in payload["schemas"]
    assert "mcp.seo_audit_v2" in payload["surfaces"]
    assert payload["channel"] == "prerelease"
    assert "/scan" not in payload["surfaces"]
    assert "agentready.audit.v2" in payload["schemas"]
    assert "/v2/audit" in payload["surfaces"]
    assert "/v2/jobs/{job_id}/cancel" in payload["surfaces"]
    assert "mcp.ai_chat" in payload["surfaces"]
    assert payload["contract_status"] == "v2-only"


def test_manifested_v2_schemas_have_published_schema_documents():
    schema_dir = Path(__file__).parents[1] / "schemas"
    for schema_id in COMPATIBILITY.schemas:
        schema_path = schema_dir / f"{schema_id}.schema.json"
        assert schema_path.is_file(), schema_id


def test_manifest_covers_all_versioned_http_routes():
    from agentready.server import app

    manifest_routes = set(COMPATIBILITY.surfaces)
    live_routes = {
        route.path
        for route in app.routes
        if route.path.startswith(("/v2/", "/ai/"))
    }

    assert live_routes <= manifest_routes

from agentready.compatibility import COMPATIBILITY


def test_release_compatibility_manifest_freezes_v1_and_v2_surfaces():
    payload = COMPATIBILITY.to_dict()
    assert payload["release"] == "0.8.2"
    assert payload["channel"] == "stable"
    assert "/scan" in payload["v1_facades"]
    assert "agentready.audit.v2" in payload["v2_schemas"]
    assert payload["migration_status"] == "v1-preserved-v2-additive"

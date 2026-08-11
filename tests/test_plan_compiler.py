from dataclasses import replace

from agentready.audit_service import AuditRequest
from agentready.plan_compiler import PlanCompiler


def test_plan_compiler_is_deterministic_and_network_free():
    request = AuditRequest(
        "https://example.test/",
        profile="standard",
        max_pages=7,
        include=("/docs",),
        exclude=("/private",),
        render=True,
        provider="pagespeed",
        language="ru",
    )

    first = PlanCompiler().compile(request)
    second = PlanCompiler().compile(request)

    assert first == second
    assert first.max_pages == 7
    assert first.provider == "pagespeed"
    assert first.language == "ru"
    assert first.capabilities == (
        "crawl",
        "static-facts",
        "coverage",
        "rendered-dom",
        "provider:pagespeed",
    )
    assert first.config_hash
    assert first.config_hash != PlanCompiler().compile(replace(request, language="en")).config_hash
    assert first.config_hash != PlanCompiler().compile(replace(request, provider="lighthouse")).config_hash

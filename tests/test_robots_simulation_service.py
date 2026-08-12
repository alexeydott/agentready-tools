from agentready.audit_core.store import (
    MemorySiteStore,
    RunRecord,
    RunUrlRecord,
    RunUrlState,
)
from agentready.query_service import QueryService
from agentready.robots import RobotsSimulationService, parse_robots


def test_robots_simulation_service_uses_stored_urls_without_writes():
    store = MemorySiteStore()
    store.begin_run(RunRecord("run-robots", "config", "tool", "rules"))
    store.put_run_url(RunUrlRecord("run-robots", "https://example.test/private", RunUrlState.PARSED))
    store.put_run_url(RunUrlRecord("run-robots", "https://example.test/public", RunUrlState.PARSED))
    live = parse_robots("User-agent: *\nAllow: /\n", "https://example.test")
    simulated = parse_robots("User-agent: *\nDisallow: /private\n", "https://example.test")

    diff = RobotsSimulationService(QueryService(store)).simulate("run-robots", live, simulated)
    assert diff.newly_blocked_urls == ("https://example.test/private",)
    assert diff.label.startswith("SIMULATION")


def test_robots_simulation_tracks_bot_and_sitemap_conflicts_without_writes(caplog):
    live = parse_robots("User-agent: Googlebot\nAllow: /\nSitemap: https://example.test/live.xml\n", "https://example.test")
    simulated = parse_robots("User-agent: Googlebot\nDisallow: /private\nSitemap: https://example.test/simulated.xml\n", "https://example.test")
    from agentready.robots import RobotsInterpretation, simulate_robots

    with caplog.at_level("INFO", logger="agentready.robots"):
        diff = simulate_robots(
            live,
            simulated,
            ["https://example.test/private"],
            user_agent="Googlebot",
            observed_search_pages=["https://example.test/private"],
            interpretation=RobotsInterpretation.GOOGLE,
        )
    assert diff.user_agent == "Googlebot"
    assert diff.sitemap_urls_affected == (
        "https://example.test/live.xml",
        "https://example.test/simulated.xml",
    )
    assert "interpretation=google" in caplog.records[-1].message
    assert "bot=Googlebot" in caplog.records[-1].message
    assert "sitemap_delta=2" in caplog.records[-1].message

from types import SimpleNamespace

from agentready.page_parser import Representation, parse_page
from agentready.robots import parse_robots
from agentready.seo.site_rules import evaluate_wp5_rules
from agentready.sitemap_reconciliation import generate_sitemap_documents


def _page(url: str, html: str, status: int = 200):
    parsed = parse_page(html.encode(), representation=Representation.from_body(html.encode(), url_key=url))
    return SimpleNamespace(url=url, status_code=status, parsed=parsed)


def test_wp5_image_inventory_reports_alt_and_observable_dimensions():
    results = evaluate_wp5_rules([_page("https://example.test/", '<img src="/hero.jpg" width="640" loading="lazy"><img src="/ok.jpg" alt="ok">')])
    result = next(item for item in results if item.id == "image-inventory-site")
    assert result.status == "fail"
    assert "missing_alt" in result.evidence[-1].metrics


def test_wp5_reconciles_sitemap_and_robots_without_network():
    policy = parse_robots("User-agent: *\nDisallow: /private\nSitemap: https://example.test/sitemap.xml", "https://example.test")
    pages = [_page("https://example.test/", "<title>Home</title>"), _page("https://example.test/private", "<title>Private</title>")]
    results = evaluate_wp5_rules(pages, sitemap_urls=("https://example.test/", "https://example.test/missing"), robots_policy=policy)
    assert next(item for item in results if item.id == "sitemap-reconciliation-site").status == "warn"
    assert next(item for item in results if item.id == "robots-reconciliation-site").status == "warn"


def test_sitemap_export_is_chunked_at_platform_limit():
    assert len(generate_sitemap_documents(tuple(f"https://example.test/{i}" for i in range(3)), chunk_size=2)) == 2

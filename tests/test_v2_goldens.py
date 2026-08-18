import hashlib
import json
import re

from test_agentfindings import _seo_report
from test_i18n import sample_report
from test_mobile import _check, _page, _report

from agentready.agentfindings import build_findings, build_remediation_plan
from agentready.mobile_report import render_mobile_html, render_mobile_json
from agentready.report import render_html, render_json
from agentready.seo_report import render_seo_html, render_seo_json


def _sha256(value: object) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_html(value: str) -> str:
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", "FIXED", value)


def test_v2_json_and_html_goldens_are_stable():
    scan = sample_report("en")
    seo = _seo_report("en")
    mobile = _report([_page("https://example.com", [_check("viewport-meta", "fail")])])

    goldens = {
        "scan_json": render_json(scan, "en"),
        "scan_html": _stable_html(render_html(scan, "en")),
        "seo_json": render_seo_json(seo, "en"),
        "seo_html": _stable_html(render_seo_html(seo, "en")),
        "mobile_json": render_mobile_json(mobile, "en"),
        "mobile_html": _stable_html(render_mobile_html(mobile, "en")),
        "findings_json": build_findings(scan, "en"),
        "remediation_json": build_remediation_plan(scan, "en"),
    }

    expected = {
            "scan_json": "a43d65be33d78137d34ab28eb346450c1a4044b2873091474ba5512b7cf63dcf",
            "scan_html": "fbfb3e71274cfcf905cabf0cafc31470c7b84b34b7f6e6a8f5624dba3091ee34",
            "seo_json": "ae05bb284633ad30a96af94b038c04e7cb5c53097cc329a7323c73818f46d829",
                "seo_html": "6df9809b9c1d7147af75b8a8d31e524ba21c241459599787a7ba9254deff0c59",
            "mobile_json": "8dd5017cc4c8d8bfa2d06e31485701b393a7571095f6c762be903d02c9b294b9",
            "mobile_html": "8ee6554d49c1d6d7feb1fe971f7a6d6d54df184715bd7c0c51d9a364dcb93532",
            "findings_json": "bd50d4adb5172b730ee791e806c36f98274d8003d719fb3908f32e91bec91b2c",
            "remediation_json": "72a088498c1a753e3825fb0f201e69ba1ef29e064484a6a32953437aac9e1413",
    }

    assert {key: _sha256(value) for key, value in goldens.items()} == expected


def test_seo_crawl_capability_golden_is_stable():
    from agentready.seo_crawler import CRAWL_CHECK_METADATA

    capability = {
        "checks": [item["id"] for item in CRAWL_CHECK_METADATA],
        "titles": {item["id"]: item["title"] for item in CRAWL_CHECK_METADATA},
        "categories": {item["id"]: item["category"] for item in CRAWL_CHECK_METADATA},
    }
    assert _sha256(capability) == "f3bea22ebd4ed2826e1348a36e82133d8685c980d6a8ba543fad09608fd6ef23"


def test_seo_capability_counts_are_frozen_for_wp0():
    from agentready.seo_analytics import ANALYTICS_CHECK_METADATA
    from agentready.seo_checks import SEO_CHECK_METADATA
    from agentready.seo_crawler import CRAWL_CHECK_METADATA

    assert len(SEO_CHECK_METADATA) == 23
    assert len(CRAWL_CHECK_METADATA) == 6
    assert len(ANALYTICS_CHECK_METADATA) == 6

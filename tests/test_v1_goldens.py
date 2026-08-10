import hashlib
import json
import re

from agentready.agentfindings import build_findings, build_remediation_plan
from agentready.mobile_report import render_mobile_html, render_mobile_json
from agentready.report import render_html, render_json
from agentready.seo_report import render_seo_html, render_seo_json
from test_agentfindings import _seo_report
from test_i18n import sample_report
from test_mobile import _check, _page, _report


def _sha256(value: object) -> str:
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _stable_html(value: str) -> str:
    return re.sub(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", "FIXED", value)


def test_v1_json_and_html_goldens_are_stable():
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
        "scan_json": "5baf68ac8747ee60bfd962959cc28e3cb265c49df4af7c76bcf5ad867d8a8954",
        "scan_html": "e3d27bf27f65dcec84ae7cb6104c8832b4f99b9704d8e49a77d5b31e734eda31",
        "seo_json": "bd25e2ea5973305c38a35c785b34549b333371d4a8551a85412e276014be5cd8",
        "seo_html": "361065ec717148ead95851a829c07d364d4f83e26e614519917d81051c941f9e",
        "mobile_json": "31600f9393c190ef5de15dbd6331913025385875f9d063670d84db88901925c5",
        "mobile_html": "b5f130b5cb52be008692e6bde2867c6b55bc03fc2e0ddeccb4c2c7320339c169",
        "findings_json": "7e451dffabe160b5891b4694adefc30bde2477624de5af6fe81c5ad4fdf3dcf2",
        "remediation_json": "91cf4d48acf171e19bc567173e4f8a4f5ece267dfb8bd130d0784bb02948d6b3",
    }

    assert {key: _sha256(value) for key, value in goldens.items()} == expected

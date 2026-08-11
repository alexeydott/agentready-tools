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
        "scan_json": "9b23f7506812b76f74edd6ba93ed425b1c6e1ab5b4ab2872a715f526d1943c75",
            "scan_html": "78b17793a030d012614b6f00a2da4c46853a077053bb767d344adde0aa0c5ec7",
        "seo_json": "98ed0dabb953c897e911c95d2cafcaafb200e81d002ed53ac98603dbe6d05d6f",
            "seo_html": "0045892e2bca0babfbe3a847de9fc45cba66257fce0ae56230a8380dca3b3431",
        "mobile_json": "d9470913fde57b307a8c1675df184ed548f4aee71638da1baec103ac8b2086d2",
            "mobile_html": "718b0d7c5ec428496564495c6a96c487fcf02b81f7f2b3c27d10265ae2966543",
        "findings_json": "7e451dffabe160b5891b4694adefc30bde2477624de5af6fe81c5ad4fdf3dcf2",
        "remediation_json": "91cf4d48acf171e19bc567173e4f8a4f5ece267dfb8bd130d0784bb02948d6b3",
    }

    assert {key: _sha256(value) for key, value in goldens.items()} == expected

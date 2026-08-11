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
        "scan_json": "bfe6fc89546282bad76aee47ab41885c46f5128e93bbacdffe5608112e8850d9",
        "scan_html": "cc1e1dde205624fea451e102e609fac14e792027aaa6eb91d8ca493ce001af08",
        "seo_json": "115bfe175a81a77cae5d9aa687620221c38fc7b2753a05c0e20456cff44decf0",
        "seo_html": "2a4f466e2f19e4a966c8278491ebe2c2746909881a14a848b65fc4c8cc5dcf64",
        "mobile_json": "f9f0e69032b5c6037c2d5fb668440c5e90a2f26c341cecefcd813d1dd7ad3d20",
        "mobile_html": "d9591087b5e9714dff68f51b4d5a83219aba18d25ddbda1d4d42f3da3580a3e6",
        "findings_json": "7e451dffabe160b5891b4694adefc30bde2477624de5af6fe81c5ad4fdf3dcf2",
        "remediation_json": "91cf4d48acf171e19bc567173e4f8a4f5ece267dfb8bd130d0784bb02948d6b3",
    }

    assert {key: _sha256(value) for key, value in goldens.items()} == expected

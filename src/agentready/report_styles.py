"""Shared styles for browser-rendered report profiles."""

BASE_REPORT_CSS = (
    "body{font:16px system-ui,sans-serif;max-width:1100px;margin:2rem auto;padding:0 1rem}"
    ".report-generated{margin:.25rem 0 1rem;color:#6b7280;font-size:.85rem}"
    "table{border-collapse:collapse;width:100%}"
    "td,th{border:1px solid #ccc;padding:.5rem;text-align:left;vertical-align:top}"
    ".grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px;margin-bottom:1.5rem}"
    ".card{position:relative;border:1px solid #ccc;border-radius:8px;padding:12px}"
    ".score{font-size:1.5rem;font-weight:700;margin-top:8px}"
    ".check-cell{position:relative;min-width:190px}"
    ".check-name{font-weight:600}"
    ".check-cell small{display:block;margin-top:4px;color:#666}"
    ".check-help{display:inline-grid;place-items:center;width:18px;height:18px;margin-left:4px;border:1px solid currentColor;border-radius:50%;font-size:12px;font-weight:700;cursor:help;vertical-align:middle}"
    ".check-help:hover::after,.check-help:focus::after{content:attr(data-tooltip);position:absolute;z-index:2;left:8px;top:38px;width:min(360px,calc(100vw - 48px));padding:10px 12px;border-radius:8px;background:#222;color:#fff;font-size:13px;font-weight:400;line-height:1.4;white-space:pre-line;box-shadow:0 4px 14px #0004}"
    "details{margin:1rem 0}"
    "summary{cursor:pointer;font-weight:700}"
    "@page{size:A4;margin:12mm}"
    "@media print{.toolbar{display:none!important}.check-help{display:none!important}body{max-width:none;margin:0}details:not([open])>*:not(summary){display:block}}"
)


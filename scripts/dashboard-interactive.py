"""Run an interactive dashboard smoke suite against a local AgentReady server."""

from __future__ import annotations

import argparse
import json

from playwright.sync_api import Page, sync_playwright


def _check(page: Page, label: str, action) -> None:
    action()
    print(json.dumps({"check": label, "status": "pass"}))


def _capture_console(errors: list[str], message) -> None:
    if message.type not in {"error", "warning"}:
        return
    if message.location.get("url", "").endswith("/favicon.ico"):
        return
    errors.append(f"console {message.type}: {message.text}")


def _capture_response(errors: list[str], response) -> None:
    if response.status < 400 or "favicon.ico" in response.url or ".well-known/appspecific" in response.url:
        return
    try:
        detail = response.text()[:300]
    except Exception:
        detail = "response body unavailable"
    errors.append(f"response {response.status}: {response.url} detail={detail}")


def run(
    base_url: str,
    executable: str | None = None,
    headed: bool = False,
    target: str | None = None,
) -> None:
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=executable,
            headless=not headed,
            args=["--auto-open-devtools-for-tabs"] if headed else None,
        )
        page = browser.new_page()
        page.on("pageerror", lambda error: errors.append(f"pageerror: {error}"))
        page.on("console", lambda message: _capture_console(errors, message))
        page.on("response", lambda response: _capture_response(errors, response))
        page.goto(f"{base_url}/dashboard?language=en", wait_until="networkidle")
        assert page.evaluate("typeof runScan") == "function"
        assert page.evaluate("typeof openAiCredentials") == "function"
        _check(page, "initial JavaScript handlers", lambda: None)
        page.evaluate(
            """localStorage.setItem("agentready.dashboard.state.v1", JSON.stringify({
                url: "https://example.test/session",
                "ai-message": "Restored session message",
                language: "en"
            }))"""
        )
        page.evaluate(
            """localStorage.setItem("agentready.ai.chat.v1", JSON.stringify({
                history: [{role: "user", content: "Restored session message"}],
                usage: {prompt_tokens: 3, completion_tokens: 2, total_tokens: 5}
            }))"""
        )
        page.reload(wait_until="networkidle")
        assert page.locator("#url").input_value() == "https://example.test/session"
        assert page.locator("#ai-message").input_value() == "Restored session message"
        assert "Restored session message" in page.locator("#ai-chat-history").inner_text()
        _check(page, "dashboard and chat localStorage restoration", lambda: None)
        page.evaluate("localStorage.removeItem('agentready.dashboard.state.v1')")
        page.evaluate("localStorage.removeItem('agentready.ai.chat.v1')")
        if target:
            page.locator("#url").fill(target)
            page.evaluate("saveDashboardState()")

        _check(page, "service health", lambda: page.locator('a[onclick*="runHealth"]').click())
        page.wait_for_timeout(150)
        _check(page, "readiness check catalog", lambda: page.locator('a[onclick*="loadChecks"]').click())
        page.wait_for_timeout(200)
        _check(page, "expand check selection", lambda: page.evaluate(
            "document.querySelector('#checks').closest('details').open = true"
        ))
        _check(page, "select all readiness checks", lambda: page.locator(
            'button[onclick*="selectApplicable(true)"]'
        ).click())
        _check(page, "clear readiness checks", lambda: page.locator(
            'button[onclick*="selectApplicable(false)"]'
        ).click())

        _check(page, "SEO profile and catalog", lambda: page.locator("#preset").select_option("seo"))
        page.wait_for_timeout(250)
        _check(page, "select all SEO checks", lambda: page.locator(
            'button[onclick*="selectApplicable(true)"]'
        ).click())
        _check(page, "clear SEO checks", lambda: page.locator(
            'button[onclick*="selectApplicable(false)"]'
        ).click())
        _check(page, "mobile profile and catalog", lambda: page.locator("#preset").select_option("mobile"))
        page.wait_for_timeout(250)
        _check(page, "vNext profile and catalog", lambda: page.locator("#preset").select_option("v2"))
        page.wait_for_timeout(250)

        _check(page, "advanced settings", lambda: page.locator("details").first.locator("summary").click())
        _check(page, "help panel", lambda: page.locator("#help-toggle").click())
        _check(page, "AI credentials dialog", lambda: page.locator(
            'a[onclick*="openAiCredentials"]'
        ).click())
        credential_state = page.evaluate(
            """async () => {
                const response = await fetch("/ai/status");
                return response.ok ? await response.json() : null;
            }"""
        )
        if credential_state and any(
            provider.get("credential", {}).get("configured")
            for provider in credential_state.get("providers", [])
        ):
            assert page.locator("#ai-key").input_value() == ""
            assert "api_key" not in page.evaluate("localStorage.getItem('agentready.dashboard.state.v1') || ''")
            _check(page, "credential vault redaction and status restoration", lambda: None)
        else:
            print(json.dumps({"check": "credential vault redaction and status restoration", "status": "skip", "reason": "no configured local provider"}))
        _check(page, "close AI credentials dialog", lambda: page.locator(
            '#ai-credentials-dialog button[onclick*="close"]'
        ).click())
        _check(page, "empty URL validation", lambda: page.locator(
            'button[onclick="runScan()"]'
        ).click())
        page.wait_for_timeout(100)
        if target:
            page.locator("#url").fill(target)
            for profile in ("all", "seo", "mobile", "v2"):
                page.locator("#preset").select_option(profile)
                page.wait_for_timeout(250)
                page.locator("#checks").evaluate(
                    "element => element.closest('details').open = true"
                )
                _check(page, f"real {profile} audit", lambda: page.locator(
                    'button[onclick="runScan()"]'
                ).click())
                page.locator("#report-frame").wait_for(state="visible", timeout=180_000)
                if profile == "v2":
                    assert "AgentReady v2 audit" in page.locator("#report-frame").get_attribute("srcdoc")
                if profile == "all":
                    report_frame = page.locator("#report-frame").content_frame
                    hint = report_frame.locator(".check-help").first
                    if hint.count() > 0:
                        hint.wait_for(state="attached")
                        page.wait_for_timeout(500)
                        assert hint.evaluate(
                            "element => { element.focus(); return getComputedStyle(element, '::after').content != 'none'; }"
                        )
                    else:
                        print(json.dumps({
                            "check": "report hover/focus hint",
                            "status": "skip",
                            "reason": "live report contained no check-help element",
                        }))
                assert page.locator("#ai-assistant-panel").is_visible()
            with page.expect_download(timeout=30_000):
                page.locator("#result a").first.click()
            page.locator("#report-frame").evaluate("(frame) => frame.contentWindow.print = () => {}")
            _check(page, "HTML report print action", lambda: page.locator("#result a").nth(1).click())
            if page.locator("#ai-run-button").is_enabled():
                page.locator("#ai-assistant-panel").evaluate("element => element.open = true")
                _check(page, "AI recommendation", lambda: page.locator("#ai-run-button").click())
                page.locator("#ai-result").wait_for(state="visible", timeout=180_000)
                page.locator("#ai-message").fill("Summarize the highest-impact verified issue.")
                if page.locator("#ai-chat-button").is_enabled():
                    _check(page, "AI chat", lambda: page.locator("#ai-chat-button").click())
                    page.locator("#ai-result").wait_for(state="visible", timeout=180_000)
                    _check(page, "apply prompt", lambda: page.locator(
                        'button[onclick="applyPrompt()"]'
                    ).click())
                    page.locator("#ai-prompt-title").fill("Dashboard interactive regression")
                    _check(page, "save prompt", lambda: page.locator(
                        'button[onclick="savePrompt()"]'
                    ).click())
                    page.wait_for_timeout(250)
                    _check(page, "retry AI chat", lambda: page.locator("#ai-retry-button").click())
                    page.locator("#ai-result").wait_for(state="visible", timeout=180_000)
                    page.evaluate("saveChat('Dashboard interactive gossnab')")
                    page.wait_for_timeout(250)
                    with page.expect_download(timeout=30_000):
                        page.evaluate("exportChat()")
                    _check(page, "start new chat", lambda: page.locator(
                        'button[onclick="startNewChat()"]'
                    ).click())
                else:
                    print(json.dumps({"check": "AI chat and prompt flows", "status": "skip", "reason": "provider recommendation did not enable chat"}))
            else:
                print(json.dumps({"check": "AI provider", "status": "skip", "reason": "not enabled"}))
        _check(page, "Russian locale", lambda: page.goto(
            f"{base_url}/dashboard?language=ru", wait_until="networkidle"
        ))
        assert page.evaluate("typeof runScan") == "function"
        assert not errors, errors
        print(json.dumps({"check": "browser diagnostics", "status": "pass"}))
        browser.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    parser.add_argument("--edge", default=None, help="Path to Edge/Chromium executable")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--target", default=None, help="Public site to audit with real audit requests")
    args = parser.parse_args()
    run(args.url.rstrip("/"), args.edge, args.headed, args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

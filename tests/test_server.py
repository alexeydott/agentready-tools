from fastapi.testclient import TestClient
from types import SimpleNamespace

import agentready.server as server_module
from agentready.ai_provider import ProviderModel
from agentready.server import app


def test_server_exposes_all_read_only_audit_modes():
    paths = {route.path for route in app.routes}
    assert {
        "/",
        "/dashboard",
        "/healthz",
        "/ai/status",
        "/ai/tools",
        "/ai/providers",
        "/ai/providers/active",
        "/ai/providers/{provider_id}/models",
        "/checks",
        "/seo/checks",
        "/scan",
        "/scan/dashboard",
        "/seo/audit",
        "/seo/audit/dashboard",
    } <= paths


def test_v2_endpoint_maps_request_fields_to_shared_audit_service(monkeypatch):
    captured = {}

    def fake_run(request):
        captured["request"] = request
        return SimpleNamespace(to_dict=lambda: {"schema": "agentready.audit.v2"})

    monkeypatch.setattr(server_module._AUDIT_SERVICE, "run", fake_run)
    response = server_module.audit_v2_endpoint(
        server_module.V2AuditRequest(
            url="https://example.com",
            profile="quick",
            max_pages=7,
            limits={"max_depth": 3},
            include=["https://example.com/*"],
            exclude=["https://example.com/private"],
            render=True,
            provider="local",
            language="ru",
            selected_urls=["https://example.com/page"],
        )
    )
    request = captured["request"]
    assert response["schema"] == "agentready.audit.v2"
    assert request.profile == "quick"
    assert request.max_pages == 7
    assert request.limits == {"max_depth": 3}
    assert request.include == ("https://example.com/*",)
    assert request.exclude == ("https://example.com/private",)
    assert request.render is True
    assert request.provider == "local"
    assert request.language == "ru"
    assert request.selected_urls == ("https://example.com/page",)


def test_v2_endpoint_propagates_all_supported_profiles(monkeypatch):
    captured = []

    def fake_run(request):
        captured.append(request)
        return SimpleNamespace(to_dict=lambda: {"schema": "agentready.audit.v2"})

    monkeypatch.setattr(server_module._AUDIT_SERVICE, "run", fake_run)
    for profile in ("quick", "standard", "deep", "custom"):
        response = server_module.audit_v2_endpoint(
            server_module.V2AuditRequest(
                url="https://example.com",
                profile=profile,
                limits={"max_depth": 2} if profile == "custom" else {},
            )
        )
        assert response["schema"] == "agentready.audit.v2"

    assert [request.profile for request in captured] == ["quick", "standard", "deep", "custom"]
    assert captured[-1].limits == {"max_depth": 2}


def test_ai_tools_exposes_localized_builtin_skills(monkeypatch, tmp_path):
    monkeypatch.setattr(server_module, "_SERVER_DATA_DIR", tmp_path)
    monkeypatch.setattr(server_module, "_require_loopback", lambda request: None)
    client = TestClient(app, base_url="http://127.0.0.1")
    response = client.get("/ai/tools", params={"language": "ru"})
    assert response.status_code == 200
    data = response.json()
    assert "seo-security-interpreter" in data["skills"]
    skill = next(item for item in data["skills_catalog"] if item["id"] == "seo-security-interpreter")
    assert skill["title"] == "Интерпретатор SEO-безопасности"
    assert skill["description"]


def test_dashboard_is_localized_and_describes_each_operation():
    response = TestClient(app).get("/dashboard", params={"language": "ru"})
    assert response.status_code == 200
    assert "Настройка и запуск аудита сайта" in response.text
    assert "Запустить" in response.text
    assert "Запустить аудит готовности AI-агентов" not in response.text
    assert 'id="result" hidden' in response.text
    assert "#result { min-height:80px; background:#fff8f2" in response.text
    assert "background:#24130d; color:#ffe8d8; border-radius:12px; padding:18px" not in response.text
    assert 'id="result-panel" class="panel" hidden' in response.text
    assert 'class="operation-grid"' not in response.text
    assert 'class="cards"' not in response.text
    assert 'class="advanced-links"' in response.text
    assert 'class="text-link"' in response.text
    assert "loadChecks(false)" in response.text
    assert "function showResult()" in response.text
    assert "Проверки, включённые в запуск" in response.text
    assert "<details><summary>Проверки, включённые в запуск" in response.text
    assert 'id="ai-result" class="ai-report" hidden' in response.text
    assert response.text.count('id="ai-assistant-panel"') == 1
    assert response.text.index('id="result-panel"') < response.text.index('id="ai-assistant-panel"')
    assert 'id="ai-assistant-panel" class="panel" hidden' in response.text
    assert "function renderAiReport(data)" in response.text
    assert "Приоритетные рекомендации" in response.text
    assert "Данные аудита" in response.text
    assert "AI получает выбранные данные аудита и ваш необязательный запрос" in response.text
    assert 'translations[language.value].ai_generated_with_model' in response.text
    assert "Сгенерировано: agent-ready-tools" in response.text
    assert "function updateAiModeHint()" in response.text
    assert "function runAll()" in response.text
    assert 'if (preset === "all") { await runAll(); return; }' in response.text
    assert "combinedReportDocument" in response.text
    assert "geo.querySelectorAll(\"style\")" in response.text
    assert "seo.querySelectorAll(\"style\")" in response.text
    assert "<meta charset='utf-8>" not in response.text
    assert "checks:null" in response.text
    assert "AI-помощник обрабатывает запрос..." in response.text
    assert "function setAiBusy(busy)" in response.text
    assert 'id="threshold" type="text" inputmode="decimal" data-decimal' in response.text
    assert 'value="0.8"' in response.text
    assert "function decimalValue(id, fallback=0)" in response.text
    assert 'replace(/^(-?)\\./, "$10.")' in response.text
    assert "element.dataset.decimal !== undefined ? normalizeDecimalString(state[id])" in response.text
    assert 'input.inputMode = "decimal"' in response.text
    assert 'input_price_per_million:decimalValue("ai-provider-input-price")' in response.text
    assert 'role", "status"' in response.text
    assert "Скачать отчёт" in response.text
    assert "Распечатать отчёт" in response.text
    assert "URL.createObjectURL" in response.text
    assert "frame.contentWindow.print()" in response.text
    assert "reportFilename(" in response.text
    assert '"agentready-report-" + slug + ".html"' in response.text
    assert "Запустить SEO-аудит" in response.text
    assert "Обновить каталог проверок" in response.text
    assert "Проверить состояние сервиса" in response.text
    assert "Управляйте именованными AI-провайдерами" in response.text
    assert ">AI<" in response.text
    assert "Base URL OpenAI-compatible API" in response.text
    assert "Модель, выбранная для этого провайдера" in response.text
    assert "Скрывает в списках embedding-" in response.text
    assert "Включает помощника и loopback-only HTTP-транспорт" in response.text
    assert "Интерпретатор SEO-безопасности" in response.text
    assert "Аналитик аудита" in response.text
    assert ".model-control button { width:auto; flex:0 0 46px" in response.text
    assert "/ai/providers" in response.text
    assert "function activateAiProvider()" in response.text
    assert 'id="ai-provider-chat-only"' in response.text
    assert "function toggleChatOnly()" in response.text
    assert "chat_only:document.getElementById(\"ai-provider-chat-only\").checked" in response.text
    assert 'id="ai-model"' in response.text
    assert "model:document.getElementById(\"ai-model\").value" in response.text
    assert "/scan/dashboard" in response.text
    assert "/seo/audit/dashboard" in response.text
    assert 'value="seo"' in response.text
    assert "progress-bar" in response.text
    assert "white-space:pre-line" in response.text
    assert "event.preventDefault()" in response.text
    assert 'id="help-toggle"' in response.text
    assert ">Справка<" in response.text
    assert 'id="help-content" class="panel help-content" hidden' in response.text
    assert "Скрыть справку" in response.text
    assert "Dashboard help toggled" in response.text
    assert "See Also" not in response.text
    assert "Back to README" not in response.text
    assert "dashboard-layout" in response.text
    assert "grid-template-columns:minmax(0,1fr) 0" in response.text
    assert ".dashboard-layout.help-open" in response.text
    assert "resize:horizontal" in response.text
    assert "max-width:50vw" in response.text
    assert response.text.count('id="help-toggle"') == 1
    assert response.text.index('id="language"') < response.text.index('id="help-toggle"')
    assert response.text.index('class="help-sidebar"') > response.text.index("<main class=\"dashboard-main\">")
    assert 'class="header-actions"' in response.text
    assert "body { width:100%; min-height:100vh; margin:0;" in response.text
    assert "max-width:1220px" not in response.text


def test_dashboard_uses_browser_locale_only_without_explicit_language():
    client = TestClient(app)
    russian = client.get("/dashboard", headers={"Accept-Language": "ru-RU,ru;q=0.9"})
    assert russian.status_code == 200
    assert '<html lang="ru">' in russian.text
    assert "Запустить аудит готовности AI-агентов" not in russian.text
    assert "const languageExplicit = new URLSearchParams(location.search).has(\"language\");" in russian.text
    assert "if (!languageExplicit && state.language" in russian.text

    english = client.get("/dashboard", headers={"Accept-Language": "de-DE,de;q=0.9"})
    assert english.status_code == 200
    assert '<html lang="en">' in english.text
    assert ">Help<" in english.text
    assert "Dashboard help" in english.text

    explicit_english = client.get("/dashboard", headers={"Accept-Language": "ru-RU"}, params={"language": "en"})
    assert explicit_english.status_code == 200
    assert '<html lang="en">' in explicit_english.text
    assert ">Execute<" in explicit_english.text
    assert ">Help<" in explicit_english.text

    explicit_russian = client.get("/dashboard", headers={"Accept-Language": "en-US"}, params={"language": "ru"})
    assert explicit_russian.status_code == 200
    assert '<html lang="ru">' in explicit_russian.text
    assert ">Запустить<" in explicit_russian.text
    assert ">Справка<" in explicit_russian.text


def test_dashboard_refreshes_provider_models_and_clears_new_provider_catalog():
    response = TestClient(app).get("/dashboard", params={"language": "ru"})
    assert response.status_code == 200
    assert 'id="ai-provider-model-refresh"' in response.text
    assert "function refreshAiModels()" in response.text
    assert "renderModelCatalog([], null)" in response.text
    assert "loadAiModels(provider.id, restoredDashboardState[\"ai-model\"] || provider.model)" in response.text
    assert 'id="ai-chat-provider"' in response.text
    assert "agentready.dashboard.state.v1" in response.text
    assert "localStorage.setItem" in response.text
    assert "provider-spin" in response.text
    assert 'id="ai-skill"' in response.text
    assert 'id="ai-mcp-tool"' in response.text
    assert 'id="ai-attachments"' in response.text
    assert ".docx" in response.text
    assert "clipboardData.files" in response.text
    assert "aiConversationHistory" in response.text
    assert "mcp_tools:selectedValues" in response.text
    assert '<textarea id="ai-message">' in response.text
    assert 'id="ai-retry-button"' in response.text
    assert "function exportChat()" in response.text
    assert "function startNewChat()" in response.text


def test_dashboard_inline_script_does_not_close_html_script_early():
    """Regression: a literal closing script tag breaks the dashboard parser."""
    response = TestClient(app).get("/dashboard", params={"language": "en"})
    assert response.status_code == 200
    assert 'reportText.indexOf("<" + "/script>", start)' in response.text
    assert 'reportText.indexOf("</script>", start)' not in response.text


def test_dashboard_hints_use_hover_tooltips_like_reports():
    """All dashboard hints use the report-style hover tooltip, not click popovers."""
    for language in ("en", "ru"):
        response = TestClient(app).get("/dashboard", params={"language": language})
        assert response.status_code == 200
        # New hover-tooltip pattern (same as report files)
        assert "class='hint'" in response.text
        assert "data-tooltip=" in response.text
        assert ".hint:hover::after" in response.text
        assert ".hint:focus::after" in response.text
        assert "content:attr(data-tooltip)" in response.text
        # Old click-popover pattern is fully removed
        assert "hint-popover" not in response.text
        assert "static-hint-button" not in response.text
        assert "bindStaticHints" not in response.text
        assert "data-hint-target" not in response.text


def test_dashboard_offers_mobile_profile_with_localized_hint_and_debug_gate():
    response = TestClient(app).get("/dashboard", params={"language": "ru"})
    assert response.status_code == 200
    # 1.1 mobile audit profile is selectable and routed to the mobile endpoints
    assert 'value="mobile"' in response.text
    assert "Мобильная дружественность" in response.text
    assert "/mobile/checks" in response.text
    assert "/mobile/audit/dashboard" in response.text
    assert "runMobile()" in response.text
    # 1.2 selected profile purpose is exposed only via the (?) hover tooltip
    assert 'id="preset-desc"' not in response.text
    assert "Что проверяет выбранный профиль аудита" in response.text
    assert "profile_mobile" in response.text
    assert "updatePresetHint()" in response.text
    assert "label[for='preset'] .hint" in response.text
    # 1.3 raw JSON responses are gated behind the debug flag
    assert 'id="debug"' in response.text
    assert "Отладка результатов" in response.text
    assert "debugMode()" in response.text
    assert "Каталог проверок обновлён." in response.text
    assert "Сервис работает" in response.text or "сервис аудита работает" in response.text.lower()


def test_dashboard_english_locale_has_mobile_profile_texts():
    response = TestClient(app).get("/dashboard", params={"language": "en"})
    assert response.status_code == 200
    assert ">Execute<" in response.text
    assert "Mobile-friendliness" in response.text
    assert "Debug results" in response.text
    assert "What the selected audit profile checks" in response.text


def test_ai_provider_profiles_are_selectable_and_shared(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("agentready.ai_credentials.store_api_key", lambda *args, **kwargs: None)
    monkeypatch.setattr("agentready.ai_credentials.clear_api_key", lambda *args, **kwargs: True)
    monkeypatch.setattr(
        "agentready.ai_credentials.api_key_status",
        lambda credential_id: {"configured": True, "source": "keyring", "credential_id": credential_id},
    )
    monkeypatch.setattr(server_module, "_require_loopback", lambda request: None)
    client = TestClient(app, base_url="http://127.0.0.1")
    saved = client.post(
        "/ai/providers",
        json={
            "name": "Local gateway",
            "base_url": "http://127.0.0.1:8080/v1",
            "api_key": "secret-key",
            "active": True,
        },
    )
    assert saved.status_code == 400
    # Loopback HTTP is rejected until explicitly enabled in trusted config.
    saved = client.post(
        "/ai/providers",
        json={
            "name": "Gateway",
            "base_url": "https://gateway.example/v1",
            "api_key": "secret-key",
            "active": True,
            "enable_ai": True,
            "chat_only": True,
            "input_price_per_million": 1.25,
            "output_price_per_million": 4.5,
        },
    )
    assert saved.status_code == 200
    status = client.get("/ai/status")
    assert status.status_code == 200
    assert status.json()["active_provider"] == "gateway"
    assert status.json()["enabled"] is True
    assert status.json()["transport_enabled"] is True
    gateway = next(item for item in status.json()["providers"] if item["id"] == "gateway")
    assert gateway["credential"]["configured"] is True
    assert gateway["chat_only"] is True
    assert gateway["input_price_per_million"] == 1.25
    assert gateway["output_price_per_million"] == 4.5
    assert client.post("/ai/providers/active", json={"provider_id": "openai"}).status_code == 200
    assert client.get("/ai/status").json()["active_provider"] == "openai"


def test_ai_provider_model_catalog_is_available_without_exposing_credentials(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("agentready.ai_credentials.store_api_key", lambda *args, **kwargs: None)
    monkeypatch.setattr("agentready.ai_credentials.api_key_status", lambda credential_id: {"configured": True})
    monkeypatch.setattr(server_module, "_require_loopback", lambda request: None)

    async def fake_list_models(self):
        return [ProviderModel("embed-small", ("embedding",)), ProviderModel("chat-model", ("chat",))]

    monkeypatch.setattr("agentready.ai_provider.OpenAICompatibleProvider.list_models", fake_list_models)
    client = TestClient(app, base_url="http://127.0.0.1")
    saved = client.post("/ai/providers", json={
        "name": "Catalog gateway",
        "base_url": "https://gateway.example/v1",
        "api_key": "secret-key",
        "model": "chat-model",
        "input_price_per_million": 1.25,
        "output_price_per_million": 4.5,
        "active": True,
    })
    assert saved.status_code == 200
    response = client.get("/ai/providers/catalog-gateway/models")
    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_model"] == "chat-model"
    assert [item["id"] for item in payload["models"]] == ["embed-small", "chat-model"]
    assert "secret-key" not in response.text


def test_every_dashboard_element_has_a_localized_hint():
    expected = ["url_hint", "language_hint", "run_hint", "checks_hint", "select_all_hint", "clear_checks_hint", "download_hint", "print_hint"]
    for language in ("ru", "en"):
        response = TestClient(app).get("/dashboard", params={"language": language})
        assert response.status_code == 200
        # Every hint key must have a non-empty localized text in the translations payload
        for key in expected:
            assert f'"{key}":' in response.text, f"{key} missing for {language}"
    ru = TestClient(app).get("/dashboard", params={"language": "ru"}).text
    assert "Публичный URL сайта для аудита" in ru
    assert "Переключает язык интерфейса дашборда" in ru
    assert "Сохраняет сформированный HTML-отчёт" in ru


def test_checks_endpoint_supports_localized_catalog():
    response = TestClient(app).get("/checks", params={"language": "ru"})
    assert response.status_code == 200
    payload = response.json()
    assert payload and all(item["language"] == "ru" for item in payload)
    assert {"all", "content", "api", "ai-search"} <= set(payload[0]["presets"])
    assert all(item["description"] for item in payload)
    assert all(item["hint"] for item in payload)
    robots = next(item for item in payload if item["id"] == "robots-txt")
    assert "robots.txt" in robots["hint"]
    robots = next(item for item in payload if item["id"] == "robots-txt")
    assert "Опубликуйте" in robots["description"]


def test_seo_checks_endpoint_returns_localized_descriptions():
    response = TestClient(app).get("/seo/checks", params={"language": "ru"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 29
    assert all(item["language"] == "ru" and item["description"] for item in payload)
    assert all(item["hint"] for item in payload)
    assert any(item["id"] == "jsonld" and "JSON-LD" in item["description"] for item in payload)
    insecure_pages = next(item for item in payload if item["id"] == "insecure-links-pages")
    assert "включённом обходе" in insecure_pages["hint"]


def test_seo_audit_endpoints_execute(monkeypatch):
    """Regression: /seo/audit and /seo/audit/dashboard must call a defined _run_seo."""
    from agentready.seo_models import SeoCategoryScore, SeoCheckResult, SeoReport

    report = SeoReport(
        schema="agentready.seo.v1",
        target="https://example.com/",
        origin="https://example.com",
        checks=[SeoCheckResult("page-metadata", "t", "metadata", "pass", True, "ok")],
        score=100,
        categories=[SeoCategoryScore("metadata", 1, 1, 100)],
        recommendations=[],
        started_at="now",
        finished_at="now",
    )
    monkeypatch.setattr(server_module, "audit_seo", lambda *args, **kwargs: report)
    assert hasattr(server_module, "_run_seo")

    client = TestClient(app)
    json_response = client.post("/seo/audit", json={"url": "https://example.com"})
    assert json_response.status_code == 200
    assert json_response.json()["schema"] == "agentready.seo.v1"

    html_response = client.post("/seo/audit/dashboard", json={"url": "https://example.com"})
    assert html_response.status_code == 200
    assert "SEO" in html_response.text


def test_seo_audit_accepts_crawl_check_ids(monkeypatch):
    """Regression: dashboard sends crawl check IDs from /seo/checks; they must not 400."""
    from agentready.seo_models import SeoCategoryScore, SeoCheckResult, SeoReport

    captured: dict = {}

    def fake_audit(url, **kwargs):
        captured.update(kwargs)
        return SeoReport(
            schema="agentready.seo.v1",
            target=url,
            origin="https://example.com",
            checks=[SeoCheckResult("page-metadata", "t", "metadata", "pass", True, "ok")],
            score=100,
            categories=[SeoCategoryScore("metadata", 1, 1, 100)],
            recommendations=[],
            started_at="now",
            finished_at="now",
        )

    monkeypatch.setattr(server_module, "audit_seo", fake_audit)
    client = TestClient(app)
    response = client.post(
        "/seo/audit/dashboard",
        json={"url": "https://example.com", "checks": ["page-metadata", "broken-links", "duplicate-metadata"]},
    )
    assert response.status_code == 200
    assert captured["crawl"] is True
    assert captured["crawl_checks"] is not None and len(captured["crawl_checks"]) == 2
    assert captured["checks"] is not None and len(captured["checks"]) == 1

    unknown = client.post("/seo/audit", json={"url": "https://example.com", "checks": ["bogus-id"]})
    assert unknown.status_code == 400

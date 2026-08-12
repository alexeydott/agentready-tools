import pytest

from agentready import cli
from agentready.cli import build_parser
from agentready.report_v2 import AuditReport, Coverage


def test_cli_help_includes_examples_for_top_level_modes():
    parser = build_parser()
    help_text = parser.format_help()
    for example in (
        "agentready audit",
        "agentready checks",
        "agentready init",
        "agentready indexnow",
        "agentready google-indexing",
        "agentready audit https://example.com --mode seo",
        "agentready geo",
        "agentready logs",
        "agentready serve",
        "agentready mcp",
    ):
        assert example in help_text


def test_cli_rejects_removed_v1_commands():
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["scan", "https://example.com"])
    with pytest.raises(SystemExit):
        parser.parse_args(["seo", "audit", "https://example.com"])
    with pytest.raises(SystemExit):
        parser.parse_args(["mobile", "audit", "https://example.com"])


def test_nested_cli_modes_include_usage_examples():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    choices = command.choices
    nested = {
        "indexnow": ("key", "verify", "submit", "git"),
        "google-indexing": ("publish", "status"),
        "geo": ("init-rules", "git-dates"),
        "logs": ("ai-bots",),
    }
    for parent, children in nested.items():
        subparser = next(action for action in choices[parent]._actions if action.dest.endswith("command"))
        for child in children:
            assert "Example" in (subparser.choices[child].epilog or "")


def test_all_cli_examples_have_descriptions():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    epilogs = [build_parser().epilog]
    for parser in command.choices.values():
        epilogs.append(parser.epilog)
        for action in parser._actions:
            if isinstance(getattr(action, "choices", None), dict):
                epilogs.extend(child.epilog for child in action.choices.values())
    for epilog in epilogs:
        if not epilog:
            continue
        lines = [line.strip() for line in epilog.splitlines()]
        for index, line in enumerate(lines):
            if line.startswith("agentready "):
                assert index > 0 and lines[index - 1].startswith("# "), line


def test_serve_passes_loaded_fastapi_app_to_uvicorn(monkeypatch):
    captured = {}

    class FakeUvicorn:
        @staticmethod
        def run(app, **kwargs):
            captured["app"] = app
            captured["kwargs"] = kwargs

    monkeypatch.setitem(__import__("sys").modules, "uvicorn", FakeUvicorn)
    args = type("Args", (), {"host": "127.0.0.1", "port": 8765})()

    assert cli._cmd_serve(args) == 0
    assert captured["app"].title == "AgentReady Tools API"
    assert captured["kwargs"] == {"host": "127.0.0.1", "port": 8765, "reload": False}


def test_serve_reports_bind_failure_with_alternate_port(monkeypatch, capsys):
    class FailingUvicorn:
        @staticmethod
        def run(app, **kwargs):
            raise SystemExit(3)

    monkeypatch.setitem(__import__("sys").modules, "uvicorn", FailingUvicorn)
    args = type("Args", (), {"host": "127.0.0.1", "port": 8765})()

    assert cli._cmd_serve(args) == 2
    assert "unable to bind serve to 127.0.0.1:8765" in capsys.readouterr().err


def test_mcp_command_dispatches_to_mcp_server_with_host_port(monkeypatch):
    import pytest

    pytest.importorskip("mcp")
    captured = {}

    def fake_main(host: str, port: int) -> None:
        captured["host"] = host
        captured["port"] = port

    from agentready import mcp_server

    monkeypatch.setattr(mcp_server, "main", fake_main)
    args = type("Args", (), {"host": "127.0.0.1", "port": 9999})()

    assert cli._cmd_mcp(args) == 0
    assert captured == {"host": "127.0.0.1", "port": 9999}


def test_mcp_command_returns_2_when_mcp_extra_missing(monkeypatch, capsys):
    monkeypatch.setitem(__import__("sys").modules, "agentready.mcp_server", None)
    args = type("Args", (), {"host": "127.0.0.1", "port": 8766})()

    assert cli._cmd_mcp(args) == 2
    assert 'python -m pip install -e ".[mcp]"' in capsys.readouterr().err


def test_mcp_parser_defaults_and_example():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    mcp_parser = command.choices["mcp"]
    assert "agentready mcp" in (mcp_parser.epilog or "")
    args = mcp_parser.parse_args([])
    assert args.host == "127.0.0.1"
    assert args.port == 8766


def test_serve_parser_defaults_to_cache_directory():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    args = command.choices["serve"].parse_args([])
    assert args.data_dir is None


def test_ai_cli_accepts_model_override():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    ai_parser = command.choices["ai"]
    recommend = next(action for action in ai_parser._actions if action.dest == "ai_command").choices["recommend"]
    args = recommend.parse_args(["https://example.com", "--model", "provider-model"])
    assert args.model == "provider-model"


def test_ai_nested_help_includes_simple_and_complex_examples():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    ai_parser = command.choices["ai"]
    ai_command = next(action for action in ai_parser._actions if action.dest == "ai_command")
    for name in ("credentials", "recommend", "chat"):
        epilog = ai_command.choices[name].epilog or ""
        assert epilog.count("agentready ai") >= 2
        lines = [line.strip() for line in epilog.splitlines()]
        for index, line in enumerate(lines):
            if line.startswith("agentready ai"):
                assert index > 0 and lines[index - 1].startswith("# ")


def test_audit_cli_maps_execution_fields_to_shared_request(monkeypatch, capsys):
    captured = {}

    class FakeResult:
        report = AuditReport("https://example.test", (), Coverage(0, 0, 0, 0))

        def to_dict(self):
            return {"schema": "agentready.audit.v2"}

    class FakeService:
        def run(self, request):
            captured["request"] = request
            return FakeResult()

    monkeypatch.setattr(cli, "AuditService", FakeService)
    args = build_parser().parse_args(
        [
            "audit",
            "https://example.test",
            "--profile",
            "quick",
            "--max-pages",
            "7",
            "--max-depth",
            "2",
            "--include",
            "/docs",
            "--exclude",
            "/private",
            "--select-url",
            "https://example.test/page",
            "--render",
            "--provider",
            "pagespeed",
            "--lang",
            "ru",
        ]
    )

    assert cli._cmd_audit(args) == 0
    request = captured["request"]
    assert request.profile == "quick"
    assert request.max_pages == 7
    assert request.limits == {"max_depth": 2}
    assert request.include == ("/docs",)
    assert request.exclude == ("/private",)
    assert request.selected_urls == ("https://example.test/page",)
    assert request.render is True
    assert request.provider == "pagespeed"
    assert request.language == "ru"
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["schema"] == "agentready.audit.v2"
    assert payload["score"] == 100


def test_audit_cli_propagates_all_supported_profiles(monkeypatch, capsys):
    captured = []

    class FakeResult:
        report = AuditReport("https://example.test", (), Coverage(0, 0, 0, 0))

        def to_dict(self):
            return {"schema": "agentready.audit.v2"}

    class FakeService:
        def run(self, request):
            captured.append(request)
            return FakeResult()

    monkeypatch.setattr(cli, "AuditService", FakeService)
    for profile in ("quick", "standard", "deep", "custom"):
        args = build_parser().parse_args(
            ["audit", "https://example.test", "--profile", profile]
            + (["--max-depth", "2"] if profile == "custom" else [])
        )
        assert cli._cmd_audit(args) == 0

    assert [request.profile for request in captured] == ["quick", "standard", "deep", "custom"]
    assert captured[-1].limits == {"max_depth": 2}
    capsys.readouterr()


def test_readiness_cli_renders_requested_v2_format_and_applies_score_gate(monkeypatch, capsys):
    class FakeService:
        def run(self, request):
            return type(
                "Result",
                (),
                {"report": AuditReport(
                    "https://example.test",
                    (),
                    Coverage(0, 0, 0, 0),
                )},
            )()

    monkeypatch.setattr(cli, "AuditService", FakeService)
    args = build_parser().parse_args(
        ["audit", "https://example.test", "--format", "markdown", "--min-score", "101"]
    )
    assert cli._cmd_audit(args) == 2
    assert "min-score must be between 0 and 100" in capsys.readouterr().err

    args = build_parser().parse_args(["audit", "https://example.test", "--format", "markdown"])
    assert cli._cmd_audit(args) == 0
    assert "# Audit report" in capsys.readouterr().out


def test_audit_cli_forwards_selected_seo_checks(monkeypatch, capsys):
    captured = {}

    def fake_seo(url, **kwargs):
        captured["checks"] = kwargs["checks"]
        return type("Seo", (), {"score": 100})()

    monkeypatch.setattr(cli, "audit_seo", fake_seo)
    monkeypatch.setattr(cli, "render_seo", lambda report, output_format, language: "ok\n")
    args = build_parser().parse_args(
        ["audit", "https://example.test", "--mode", "seo", "--checks", "page-metadata"]
    )
    assert cli._cmd_audit(args) == 0
    assert len(captured["checks"]) == 1
    assert capsys.readouterr().out == "ok\n"


def test_mcp_v2_maps_execution_fields_to_shared_request(monkeypatch):
    import pytest

    pytest.importorskip("mcp")
    from agentready import mcp_server

    captured = {}

    class FakeResult:
        def to_dict(self):
            return {"schema": "agentready.audit.v2"}

    class FakeService:
        def run(self, request):
            captured["request"] = request
            return FakeResult()

    monkeypatch.setattr(mcp_server, "AuditService", FakeService)
    result = mcp_server.audit_v2(
        "https://example.test",
        profile="quick",
        max_pages=7,
        timeout=4,
        limits={"max_depth": 2},
        include=["/docs"],
        exclude=["/private"],
        render=True,
        provider="pagespeed",
        language="ru",
        selected_urls=["https://example.test/page"],
    )

    request = captured["request"]
    assert result == {"schema": "agentready.audit.v2"}
    assert request.profile == "quick"
    assert request.max_pages == 7
    assert request.limits == {"max_depth": 2}
    assert request.selected_urls == ("https://example.test/page",)
    assert request.render is True
    assert request.provider == "pagespeed"
    assert request.language == "ru"


def test_mcp_v2_propagates_all_supported_profiles(monkeypatch):
    import pytest

    pytest.importorskip("mcp")
    from agentready import mcp_server

    captured = []

    class FakeResult:
        def to_dict(self):
            return {"schema": "agentready.audit.v2"}

    class FakeService:
        def run(self, request):
            captured.append(request)
            return FakeResult()

    monkeypatch.setattr(mcp_server, "AuditService", FakeService)
    for profile in ("quick", "standard", "deep", "custom"):
        result = mcp_server.audit_v2(
            "https://example.test",
            profile=profile,
            limits={"max_depth": 2} if profile == "custom" else None,
        )
        assert result == {"schema": "agentready.audit.v2"}

    assert [request.profile for request in captured] == ["quick", "standard", "deep", "custom"]
    assert captured[-1].limits == {"max_depth": 2}

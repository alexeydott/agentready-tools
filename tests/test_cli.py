from agentready.cli import build_parser
from agentready import cli


def test_cli_help_includes_examples_for_top_level_modes():
    parser = build_parser()
    help_text = parser.format_help()
    for example in (
        "agentready scan",
        "agentready checks",
        "agentready init",
        "agentready indexnow",
        "agentready google-indexing",
        "agentready seo audit",
        "agentready geo",
        "agentready logs",
        "agentready serve",
        "agentready mcp",
    ):
        assert example in help_text


def test_scan_help_includes_usage_examples():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    assert "agentready scan" in command.choices["scan"].epilog


def test_nested_cli_modes_include_usage_examples():
    command = next(action for action in build_parser()._actions if action.dest == "command")
    choices = command.choices
    nested = {
        "indexnow": ("key", "verify", "submit", "git"),
        "google-indexing": ("publish", "status"),
        "geo": ("init-rules", "git-dates"),
        "logs": ("ai-bots",),
        "seo": ("audit",),
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


def test_mcp_command_dispatches_to_mcp_server_with_host_port(monkeypatch):
    captured = {}

    def fake_main(host: str, port: int) -> None:
        captured["host"] = host
        captured["port"] = port

    import agentready.mcp_server as mcp_server

    monkeypatch.setattr(mcp_server, "main", fake_main)
    args = type("Args", (), {"host": "127.0.0.1", "port": 9999})()

    assert cli._cmd_mcp(args) == 0
    assert captured == {"host": "127.0.0.1", "port": 9999}


def test_mcp_command_returns_2_when_mcp_extra_missing(monkeypatch):
    monkeypatch.setitem(__import__("sys").modules, "agentready.mcp_server", None)
    args = type("Args", (), {"host": "127.0.0.1", "port": 8766})()

    assert cli._cmd_mcp(args) == 2


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

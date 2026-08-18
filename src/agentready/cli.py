from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import __version__
from .accesslog import analyze_ai_bot_log_file
from .audit_service import AuditRequest, AuditService
from .config import default_config_yaml, load_config
from .geo_rules import write_rules
from .gitutils import audit_git_dates, changed_urls_from_git
from .google_indexing import DEFAULT_MAX_NOTIFICATIONS, get_metadata
from .google_indexing import publish_urls as publish_google_urls
from .i18n import category_name, check_title, normalize_language, tr
from .indexnow import (
    PROVIDER_ENDPOINTS,
    generate_key,
    submit_urls,
    verify_key_file,
    write_key_file,
)
from .registry import CHECKS
from .report_storage import save_report
from .report_v2 import classify_finding_changes, diff_reports, render_audit_report
from .seo_report import render_seo
from .seo_scanner import audit_seo, compare_seo_baseline

logger = logging.getLogger(__name__)

_HELP_FORMATTER = argparse.RawDescriptionHelpFormatter
_ROOT_EPILOG = """Examples:
  # Run the canonical v2 readiness audit.
  agentready audit https://example.com --mode readiness --preset all
  # List implemented checks as machine-readable JSON.
  agentready checks --json
  # Validate an IndexNow submission without sending it.
  agentready indexnow submit https://example.com/page --key YOUR_KEY --dry-run
  # Preview deletion of an eligible Google Indexing URL notification.
  agentready google-indexing publish https://example.com/jobs/42 --type deleted --eligible-type job-posting
  # Write an HTML SEO optimization report.
  agentready audit https://example.com --mode seo --format html -o seo.html
  # Create or replace the project configuration file.
  agentready init .agentready.yml --force
  # Generate the project GEO rules template.
  agentready geo init-rules AI_SEARCH_RULES.md
  # Summarize AI crawler requests in an access log.
  agentready logs ai-bots access.log
  # Start the optional local FastAPI service.
  agentready serve --host 127.0.0.1 --port 8765 --data-dir .cache
  # Start the optional local MCP server for coding agents.
  agentready mcp --host 127.0.0.1 --port 8766

Set LOG_LEVEL=DEBUG for diagnostic logs on stderr."""


def _add_command_parser(sub: argparse._SubParsersAction, name: str, **kwargs) -> argparse.ArgumentParser:
    kwargs.setdefault("formatter_class", _HELP_FORMATTER)
    parser = sub.add_parser(name, **kwargs)
    if kwargs.get("epilog"):
        logger.debug("CLI help examples registered: command=%s", name)
    return parser


def _audit_parser(sub: argparse._SubParsersAction) -> None:
    p = _add_command_parser(sub, "audit", help="Run the canonical v2 audit report")
    p.add_argument("url", nargs="+")
    p.add_argument("--mode", choices=["readiness", "seo", "mobile"], default="readiness")
    p.add_argument("--format", choices=["console", "json", "markdown", "html"], default="json")
    p.add_argument("--preset", choices=["all", "content", "api", "ai-search"], default="all")
    p.add_argument("--profile", choices=["quick", "standard", "deep", "custom"], default="standard")
    p.add_argument("--max-pages", type=int, default=25)
    p.add_argument("--timeout", type=float, default=5.0)
    p.add_argument("--max-depth", type=int)
    p.add_argument("--max-duration", type=float)
    p.add_argument("--concurrency", type=int)
    p.add_argument("--per-origin-concurrency", type=int)
    p.add_argument("--include", action="append", default=[])
    p.add_argument("--exclude", action="append", default=[])
    p.add_argument("--select-url", action="append", default=[], help="Restrict a child rescan to explicit same-origin URLs")
    p.add_argument("--discovery", dest="discovery_kind", choices=["single", "list", "sitemap", "robots-sitemap", "crawl"], default="single")
    p.add_argument("--discovery-url", action="append", default=[], help="Bounded discovery URL for list or explicit sitemap roots")
    p.add_argument("--discovery-sitemap-xml", help="Read a local sitemap XML document for bounded discovery")
    p.add_argument("--discovery-limit", type=int, default=1000)
    p.add_argument("--render", action="store_true")
    p.add_argument("--provider")
    p.add_argument("--checks", action="append", default=[])
    p.add_argument("--crawl", action="store_true")
    p.add_argument("--recommendations", type=int, default=10)
    p.add_argument("--ga-property")
    p.add_argument("--gsc-site")
    p.add_argument("--min-score", type=int)
    p.add_argument("--baseline")
    p.add_argument("--output", "-o")
    p.add_argument("--lang", "--language", dest="language", choices=["en", "ru"], default="en")
    p.add_argument("--fail-on-checks", action="store_true", help="Exit 1 when a v2 finding fails")


def _workflow_parsers(sub: argparse._SubParsersAction) -> None:
    inventory = _add_command_parser(sub, "inventory", help="Query or export a bounded v2 run inventory")
    inventory.add_argument("run_id")
    inventory.add_argument("kind", choices=["pages", "run-urls", "links", "resources", "redirects", "findings", "metrics"])
    inventory.add_argument("--base-url", default="http://127.0.0.1:8765")
    inventory.add_argument("--limit", type=int, default=100)
    inventory.add_argument("--cursor")
    inventory.add_argument("--search")
    inventory.add_argument("--sort-by")
    inventory.add_argument("--descending", action="store_true")
    inventory.add_argument("--format", choices=["json", "jsonl", "csv", "markdown", "html"], default="json")
    inventory.add_argument("--output", "-o")

    view = _add_command_parser(sub, "view", help="List, inspect, or delete saved v2 inventory views")
    view.add_argument("action", choices=["list", "get", "delete"])
    view.add_argument("view_id", nargs="?")
    view.add_argument("--base-url", default="http://127.0.0.1:8765")

    rescan = _add_command_parser(sub, "rescan", help="Start a bounded same-origin v2 rescan")
    rescan.add_argument("url")
    rescan.add_argument("--base-url", default="http://127.0.0.1:8765")
    rescan.add_argument("--rescan-of")
    rescan.add_argument("--select-url", action="append", default=[])
    rescan.add_argument("--max-pages", type=int, default=25)

    compare = _add_command_parser(sub, "compare", help="Compare a v2 audit with a saved baseline")
    compare.add_argument("url")
    compare.add_argument("--baseline", required=True)
    compare.add_argument("--base-url", default="http://127.0.0.1:8765")
    compare.add_argument("--max-pages", type=int, default=25)

    robots = _add_command_parser(sub, "robots", help="Simulate bounded virtual robots policies over a stored v2 run")
    robots_commands = robots.add_subparsers(dest="robots_command", required=True)
    simulate = _add_command_parser(robots_commands, "simulate", help="Compare live and proposed robots rules without refetching")
    simulate.add_argument("run_id")
    simulate.add_argument("--proposed", required=True, help="Proposed robots.txt file")
    simulate.add_argument("--live", help="Live robots.txt file; defaults to an empty policy")
    simulate.add_argument("--user-agent", action="append", dest="user_agents", default=[])
    simulate.add_argument("--observed-page", action="append", default=[])
    simulate.add_argument("--interpretation", choices=["rfc9309", "google"], default="rfc9309")
    simulate.add_argument("--origin")
    simulate.add_argument("--base-url", default="http://127.0.0.1:8765")
    simulate.add_argument("--output", "-o")

    sitemap = _add_command_parser(sub, "sitemap", help="Reconcile or export a supplied sitemap over a stored v2 run")
    sitemap_commands = sitemap.add_subparsers(dest="sitemap_command", required=True)
    reconcile = _add_command_parser(sitemap_commands, "reconcile", help="Reconcile sitemap XML without refetching")
    reconcile.add_argument("run_id")
    reconcile.add_argument("--document", action="append", required=True, help="Local sitemap XML document (repeat for nested indexes)")
    reconcile.add_argument("--origin", required=True)
    reconcile.add_argument("--category", default="sitemap_only")
    reconcile.add_argument("--cursor")
    reconcile.add_argument("--limit", type=int, default=100)
    reconcile.add_argument("--format", choices=["json", "csv"], default="json")
    reconcile.add_argument("--base-url", default="http://127.0.0.1:8765")
    reconcile.add_argument("--output", "-o")

    rules = _add_command_parser(sub, "rules", help="Validate or test bounded declarative custom rules")
    rules_commands = rules.add_subparsers(dest="rules_command", required=True)
    validate = _add_command_parser(rules_commands, "validate", help="Validate a rules YAML document")
    validate.add_argument("rules_file")
    validate.add_argument("--base-url", default="http://127.0.0.1:8765")
    validate.add_argument("--output", "-o")
    test_rules = _add_command_parser(rules_commands, "test", help="Apply rules to a supplied representation")
    test_rules.add_argument("rules_file")
    test_rules.add_argument("run_id")
    test_rules.add_argument("--text", default="")
    test_rules.add_argument("--url", default="")
    test_rules.add_argument("--base-url", default="http://127.0.0.1:8765")
    test_rules.add_argument("--output", "-o")

    graph = _add_command_parser(sub, "graph", help="Inspect the bounded cached link graph of a v2 run")
    graph.add_argument("run_id")
    graph.add_argument("--base-url", default="http://127.0.0.1:8765")
    graph.add_argument("--origin")
    graph.add_argument("--node")
    graph.add_argument("--cursor")
    graph.add_argument("--limit", type=int, default=100)
    graph.add_argument("--dead-end", action="store_true")
    graph.add_argument("--disconnected", action="store_true")
    graph.add_argument("--format", choices=["json", "csv"], default="json")
    graph.add_argument("--output", "-o")

    duplicates = _add_command_parser(sub, "duplicates", help="Inspect bounded exact and near-duplicate clusters")
    duplicates.add_argument("run_id")
    duplicates.add_argument("--base-url", default="http://127.0.0.1:8765")
    duplicates.add_argument("--kind", choices=["all", "exact", "near"], default="all")
    duplicates.add_argument("--threshold", type=int, default=3)
    duplicates.add_argument("--cursor")
    duplicates.add_argument("--limit", type=int, default=100)
    duplicates.add_argument("--cluster")
    duplicates.add_argument("--output", "-o")


def build_parser() -> argparse.ArgumentParser:
    logger.debug("Building CLI parser: frozen=%s", bool(getattr(sys, "frozen", False)))
    parser = argparse.ArgumentParser(
        prog="agentready",
        description="Audit websites for AI-agent readiness protocols",
        epilog=_ROOT_EPILOG,
        formatter_class=_HELP_FORMATTER,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)
    _audit_parser(sub)
    _workflow_parsers(sub)
    ai = _add_command_parser(
        sub,
        "ai",
        help="Opt-in SEO/GEO AI assistant",
        epilog="""Examples:
  # Store the AI API key in the OS credential vault.
  agentready ai credentials set
  # Check whether an AI credential is configured.
  agentready ai credentials status
  # Generate recommendations from a deterministic SEO scan.
  agentready ai recommend https://example.com --mode seo --model gpt-4o-mini
  # Ask one bounded, stateless assistant question.
  agentready ai chat https://example.com --mode both --message "Prioritize technical fixes" """,
    )
    ai_commands = ai.add_subparsers(dest="ai_command", required=True)
    credentials = _add_command_parser(
        ai_commands,
        "credentials",
        help="Manage the OS-vault AI API key",
        epilog="""Examples:
  # Check whether an AI credential is configured.
  agentready ai credentials status
  # Store a provider API key securely in the OS credential vault.
  agentready ai credentials set""",
    )
    credentials.add_argument("action", choices=["set", "status", "clear"])
    recommend = _add_command_parser(
        ai_commands,
        "recommend",
        help="Generate one-shot SEO/GEO recommendations",
        epilog="""Examples:
  # Generate a basic SEO recommendation set from a public website.
  agentready ai recommend https://example.com --mode seo
  # Use a saved JSON audit, a specific model, and Russian output.
  agentready ai recommend --report seo.json --mode both --model qwen3.6-35b-a3b-noreason --lang ru""",
    )
    recommend.add_argument("url", nargs="?")
    recommend.add_argument("--report")
    recommend.add_argument("--mode", choices=["seo", "geo", "both"], default="both")
    recommend.add_argument("--model", help="Override the configured AI model")
    recommend.add_argument("--lang", "--language", dest="language", choices=["en", "ru"], default="en")
    recommend.add_argument("--config")
    chat = _add_command_parser(
        ai_commands,
        "chat",
        help="Run one stateless assistant chat turn",
        epilog="""Examples:
  # Ask one focused question about a public website.
  agentready ai chat https://example.com --mode seo --message "What should be fixed first?"
  # Continue an interactive conversation using a saved bounded history file.
  agentready ai chat --report seo.json --mode both --interactive --history chat-history.json --lang en""",
    )
    chat.add_argument("url", nargs="?")
    chat.add_argument("--report")
    chat.add_argument("--mode", choices=["seo", "geo", "both"], default="both")
    chat.add_argument("--model", help="Override the configured AI model")
    chat.add_argument("--message")
    chat.add_argument("--interactive", action="store_true", help="Continue with an in-process user/assistant history")
    chat.add_argument("--history", help="JSON file containing bounded user/assistant messages")
    chat.add_argument("--lang", "--language", dest="language", choices=["en", "ru"], default="en")
    chat.add_argument("--config")

    checks = _add_command_parser(
        sub,
        "checks",
        help="List implemented checks",
        epilog="Examples:\n  # List checks in a human-readable table.\n  agentready checks\n  # Export check metadata as JSON.\n  agentready checks --json\n  # Display localized check titles in Russian.\n  agentready checks --lang ru",
    )
    checks.add_argument("--json", action="store_true")
    checks.add_argument("--lang", "--language", dest="language", choices=["en", "ru"], default="en")

    credentials = _add_command_parser(
        sub,
        "credentials",
        help="Manage GA4/Search Console service-account credentials",
        epilog="""Examples:
  # Store a Google service-account JSON in the OS credential vault.
  agentready credentials set service-account.json
  # Show whether analytics credentials are configured.
  agentready credentials status
  # Remove the stored credential from the vault.
  agentready credentials clear""",
    )
    credentials.add_argument("action", choices=["set", "status", "clear"])
    credentials.add_argument("path", nargs="?", help="Service-account JSON file (required for set)")

    init = _add_command_parser(
        sub,
        "init",
        help="Create a documented .agentready.yml",
        epilog="Examples:\n  # Create the default project configuration.\n  agentready init\n  # Replace an existing configuration at a custom path.\n  agentready init config.yml --force",
    )
    init.add_argument("path", nargs="?", default=".agentready.yml")
    init.add_argument("--force", action="store_true")
    init.add_argument("--lang", "--language", dest="language", choices=["en", "ru"], default="en", help="Default report language written to config")

    indexnow = _add_command_parser(
        sub,
        "indexnow",
        help="IndexNow key verification and URL submission utilities",
        epilog="Examples:\n  # Generate an IndexNow key file in the current directory.\n  agentready indexnow key --dir .\n  # Validate an explicit URL submission without sending it.\n  agentready indexnow submit https://example.com/page --key YOUR_KEY --dry-run\n  # Map changed Git files to URLs for a preview.\n  agentready indexnow git --base-url https://example.com",
    )
    ix = indexnow.add_subparsers(dest="indexnow_command", required=True)

    ix_key = ix.add_parser(
        "key",
        help="Generate an IndexNow key and key file",
        epilog="Examples:\n  # Generate a key using the default output directory.\n  agentready indexnow key\n  # Write a specified key into the public directory, replacing an existing file.\n  agentready indexnow key --dir public --key YOUR_KEY --force",
    )
    ix_key.add_argument("--dir", default=".", help="Directory where <key>.txt is written")
    ix_key.add_argument("--key", help="Use an existing valid key instead of generating one")
    ix_key.add_argument("--force", action="store_true", help="Overwrite an existing key file")

    ix_verify = ix.add_parser(
        "verify",
        help="Verify a deployed IndexNow key file",
        epilog="Example:\n  # Check that the public key file matches the submitted key.\n  agentready indexnow verify https://example.com YOUR_KEY",
    )
    ix_verify.add_argument("site", help="Site URL, e.g. https://example.com")
    ix_verify.add_argument("key", help="IndexNow key")
    ix_verify.add_argument("--key-location", help="Explicit public key-file URL")
    ix_verify.add_argument("--timeout", type=float, default=10.0)
    ix_verify.add_argument("--insecure", action="store_true")

    ix_submit = ix.add_parser(
        "submit",
        help="Submit changed URLs to IndexNow",
        epilog="""Examples:
  # Validate one URL without contacting an IndexNow provider.
  agentready indexnow submit https://example.com/page --key YOUR_KEY --dry-run
  # Validate URLs loaded from a file for the Yandex provider.
  agentready indexnow submit --from-file changed-urls.txt --key YOUR_KEY --provider yandex""",
    )
    ix_submit.add_argument("urls", nargs="*", help="Absolute changed URLs")
    ix_submit.add_argument("--from-file", help="Read one absolute URL per line")
    ix_submit.add_argument("--key", required=True, help="IndexNow key")
    ix_submit.add_argument("--key-location", help="Explicit public key-file URL")
    ix_submit.add_argument("--provider", choices=sorted(PROVIDER_ENDPOINTS), default="global")
    ix_submit.add_argument("--endpoint", help="Explicit endpoint override; cannot be combined with --provider yandex")
    ix_submit.add_argument("--timeout", type=float, default=15.0)
    ix_submit.add_argument("--dry-run", action="store_true", help="Validate and print payload without sending")
    ix_submit.add_argument("--insecure", action="store_true")

    ix_git = ix.add_parser(
        "git",
        help="Preview or submit URLs mapped from changed Git files",
        epilog="""Examples:
  # Preview URL mappings from the latest Git change.
  agentready indexnow git --base-url https://example.com
  # Submit mapped URLs after explicitly enabling sending.
  agentready indexnow git --base-url https://example.com --key YOUR_KEY --send""",
    )
    ix_git.add_argument("--repo", default=".", help="Git repository")
    ix_git.add_argument("--base-url", required=True, help="Public site origin/base URL")
    ix_git.add_argument("--content-root", default=".", help="Repository subdirectory whose files map to public routes")
    ix_git.add_argument("--from-ref", default="HEAD~1", help="Older Git ref")
    ix_git.add_argument("--to-ref", default="HEAD", help="Newer Git ref")
    ix_git.add_argument("--url-style", choices=["pretty", "files"], default="pretty", help="Fallback path-to-URL mapping")
    ix_git.add_argument("--key", help="IndexNow key; required only with --send")
    ix_git.add_argument("--key-location", help="Explicit public key-file URL")
    ix_git.add_argument("--provider", choices=sorted(PROVIDER_ENDPOINTS), default="global")
    ix_git.add_argument("--endpoint", help="Explicit endpoint override; cannot be combined with --provider yandex")
    ix_git.add_argument("--timeout", type=float, default=15.0)
    ix_git.add_argument("--insecure", action="store_true")
    ix_git.add_argument("--send", action="store_true", help="Actually submit after printing the mapped URL plan; default is preview only")

    google = _add_command_parser(
        sub,
        "google-indexing",
        help="Publish eligible JobPosting/BroadcastEvent updates through the Google Indexing API",
        epilog="Examples:\n  # Preview an eligible URL_UPDATED notification.\n  agentready google-indexing publish https://example.com/jobs/42\n  # Preview an eligible URL_DELETED notification.\n  agentready google-indexing publish https://example.com/jobs/42 --type deleted --eligible-type job-posting\n  # Fetch notification metadata for a URL.\n  agentready google-indexing status https://example.com/jobs/42",
    )
    gi = google.add_subparsers(dest="google_indexing_command", required=True)

    gi_publish = gi.add_parser(
        "publish",
        help="Preview or publish eligible Google URL notifications",
        epilog="""Examples:
  # Preview an eligible notification with no mutation.
  agentready google-indexing publish https://example.com/jobs/42
  # Send a JobPosting update after explicit confirmation.
  agentready google-indexing publish https://example.com/jobs/42 --send --eligible-type job-posting
  # Preview notifications for URLs read from a file.
  agentready google-indexing publish --from-file urls.txt --dry-run""",
    )
    gi_publish.add_argument("urls", nargs="*", help="Absolute eligible URLs")
    gi_publish.add_argument("--from-file", help="Read one absolute URL per line")
    gi_publish.add_argument("--git-repo", help="Map changed files from this Git repository to public URLs")
    gi_publish.add_argument("--base-url", help="Public site origin/base URL required with --git-repo")
    gi_publish.add_argument("--content-root", default=".")
    gi_publish.add_argument("--from-ref", default="HEAD~1")
    gi_publish.add_argument("--to-ref", default="HEAD")
    gi_publish.add_argument("--url-style", choices=["pretty", "files"], default="pretty")
    gi_publish.add_argument("--type", choices=["updated", "deleted"], default="updated")
    gi_publish.add_argument("--eligible-type", choices=["job-posting", "broadcast-event"])
    gi_publish.add_argument("--credentials", help="Service-account JSON path; otherwise GOOGLE_APPLICATION_CREDENTIALS")
    gi_publish.add_argument("--max-notifications", type=int, default=DEFAULT_MAX_NOTIFICATIONS)
    gi_publish.add_argument("--max-retries", type=int, default=2)
    gi_publish.add_argument("--timeout", type=float, default=15.0)
    gi_publish.add_argument("--insecure", action="store_true", help="Disable TLS verification for eligibility preflight only")
    send_mode = gi_publish.add_mutually_exclusive_group()
    send_mode.add_argument("--send", action="store_true", help="Actually publish; default is validation and dry-run output")
    send_mode.add_argument("--dry-run", action="store_true", help="Explicitly select validation-only dry-run output")

    gi_status = gi.add_parser(
        "status",
        help="Fetch the latest Google notification metadata for one URL",
        epilog="Example:\n  # Read the latest Google notification metadata.\n  agentready google-indexing status https://example.com/jobs/42",
    )
    gi_status.add_argument("url")
    gi_status.add_argument("--credentials", help="Service-account JSON path; otherwise GOOGLE_APPLICATION_CREDENTIALS")
    gi_status.add_argument("--timeout", type=float, default=15.0)

    geo = _add_command_parser(
        sub,
        "geo",
        help="AI Search/GEO project utilities",
        epilog="Examples:\n  # Create a GEO rules file for the project.\n  agentready geo init-rules AI_SEARCH_RULES.md\n  # Compare declared content dates with Git history.\n  agentready geo git-dates docs/guide.md",
    )
    gs = geo.add_subparsers(dest="geo_command", required=True)
    rules = gs.add_parser(
        "init-rules",
        help="Create project rules for SEO/GEO work by humans and coding agents",
        epilog="Examples:\n  # Create the default Russian GEO rules file.\n  agentready geo init-rules\n  # Replace an English GEO rules file at a chosen path.\n  agentready geo init-rules AI_SEARCH_RULES.md --lang en --force",
    )
    rules.add_argument("path", nargs="?", default="AI_SEARCH_RULES.md")
    rules.add_argument("--lang", choices=["en", "ru"], default="ru")
    rules.add_argument("--force", action="store_true")
    dates = gs.add_parser(
        "git-dates",
        help="Compare declared content dates with Git history",
        epilog="Example:\n  # Check declared dates against repository history with a one-day tolerance.\n  agentready geo git-dates docs/guide.md --repo . --tolerance-days 1",
    )
    dates.add_argument("file")
    dates.add_argument("--repo", default=".")
    dates.add_argument("--tolerance-days", type=int, default=1)

    logs = _add_command_parser(
        sub,
        "logs",
        help="Analyze access logs for AI crawler activity",
        epilog="Example:\n  # Summarize known AI/search bot requests in an access log.\n  agentready logs ai-bots access.log",
    )
    ls = logs.add_subparsers(dest="logs_command", required=True)
    ai_logs = ls.add_parser(
        "ai-bots",
        help="Summarize known AI/search bot requests in a web access log",
        epilog="Examples:\n  # Show the default top paths requested by AI/search bots.\n  agentready logs ai-bots access.log\n  # Show more paths in the access-log summary.\n  agentready logs ai-bots access.log --top-paths 50",
    )
    ai_logs.add_argument("file")
    ai_logs.add_argument("--top-paths", type=int, default=20)

    serve = _add_command_parser(
        sub,
        "serve",
        help="Run the optional HTTP API",
        epilog="""Examples:
  # Start the local FastAPI service on port 8765.
  agentready serve --host 127.0.0.1 --port 8765 --data-dir .cache
  # Start a diagnostic instance with persistent runtime data in a custom directory.
  $env:LOG_LEVEL="DEBUG"; agentready serve --host 127.0.0.1 --port 8876 --data-dir .cache-debug""",
    )
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--data-dir", default=None, help="Directory for serve-owned AI skills and MCP settings (default: .cache beside the server)")

    mcp = _add_command_parser(
        sub,
        "mcp",
        help="Run the optional MCP server for coding agents",
        epilog="""Examples:
  # Start the local MCP server on the default port 8766.
  agentready mcp --host 127.0.0.1 --port 8766
  # Run a separate MCP instance for an integration test.
  agentready mcp --host 127.0.0.1 --port 8877""",
    )
    mcp.add_argument("--host", default="127.0.0.1")
    mcp.add_argument("--port", type=int, default=8766)
    return parser


def _cmd_checks(args: argparse.Namespace) -> int:
    rows = [
        {
            "id": c.id,
            "title": c.title,
            "category": c.category,
            "scored": c.scored,
            "presets": sorted(c.presets),
            "experimental": c.experimental,
            "supplemental": c.supplemental,
            "geo_scored": c.geo_scored,
            "effort": c.effort,
            "references": list(c.references),
        }
        for c in CHECKS
    ]
    lang = normalize_language(args.language)
    if args.json:
        localized_rows = []
        for row, c in zip(rows, CHECKS):
            item = dict(row)
            item["title"] = check_title(c.id, c.title, lang)
            item["category"] = category_name(c.category, lang)
            item["language"] = lang
            localized_rows.append(item)
        print(json.dumps(localized_rows, indent=2, ensure_ascii=False))
    else:
        for c in CHECKS:
            flags = [tr(lang, "scanned") if c.scored else tr(lang, "info")]
            if c.experimental:
                flags.append(tr(lang, "experimental"))
            if c.supplemental:
                flags.append(tr(lang, "supplemental"))
            print(f"{c.id:28} {category_name(c.category, lang):28} {', '.join(flags):28} {check_title(c.id, c.title, lang)}")
    return 0


def _cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.path)
    if path.exists() and not args.force:
        print(f"agentready: config already exists: {path} (use --force to replace)", file=sys.stderr)
        return 2
    content = default_config_yaml().replace("  language: en", f"  language: {normalize_language(args.language)}")
    path.write_text(content, encoding="utf-8")
    print(path)
    return 0


def _cmd_credentials(args: argparse.Namespace) -> int:
    from .credentials import (
        CredentialsError,
        clear_service_account,
        credential_status,
        store_service_account,
    )

    try:
        if args.action == "set":
            if not args.path:
                print("agentready credentials set requires a service-account JSON path", file=sys.stderr)
                return 2
            store_service_account(args.path)
            print("GA/GSC credentials stored in the OS credential vault.")
            return 0
        if args.action == "status":
            print(json.dumps(credential_status(), ensure_ascii=False, indent=2))
            return 0
        removed = clear_service_account()
        print("GA/GSC credentials removed." if removed else "No stored GA/GSC credentials found.")
        return 0
    except CredentialsError as exc:
        logger.error("[FIX:cli-contract] credentials operation failed: action=%s error=%s", args.action, exc)
        print(f"credentials: {exc}", file=sys.stderr)
        return 2


def _cmd_indexnow(args: argparse.Namespace) -> int:
    if args.indexnow_command == "key":
        key = args.key or generate_key()
        path = write_key_file(args.dir, key, overwrite=args.force)
        print(json.dumps({"key": key, "file": str(path)}, ensure_ascii=False, indent=2))
        return 0
    if args.indexnow_command == "verify":
        ok, status, detail = verify_key_file(
            args.site, args.key, key_location=args.key_location, timeout=args.timeout, verify_tls=not args.insecure
        )
        print(json.dumps({"ok": ok, "status_code": status, "detail": detail}, ensure_ascii=False, indent=2))
        return 0 if ok else 1
    if args.indexnow_command == "submit":
        urls = list(args.urls or [])
        if args.from_file:
            urls.extend(Path(args.from_file).read_text(encoding="utf-8").splitlines())
        result = submit_urls(
            urls, args.key, provider=args.provider, endpoint=args.endpoint, key_location=args.key_location,
            timeout=args.timeout, verify_tls=not args.insecure, dry_run=args.dry_run,
        )
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if args.dry_run or result.accepted else 1
    if args.indexnow_command == "git":
        rows = changed_urls_from_git(
            args.repo,
            args.base_url,
            from_ref=args.from_ref,
            to_ref=args.to_ref,
            content_root=args.content_root,
            style=args.url_style,
        )
        plan = {"from_ref": args.from_ref, "to_ref": args.to_ref, "send": bool(args.send), "urls": [x.to_dict() for x in rows]}
        if not args.send:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
            return 0
        if not args.key:
            raise ValueError("--key is required with --send")
        if not rows:
            print(json.dumps({**plan, "submission": None}, ensure_ascii=False, indent=2))
            return 0
        result = submit_urls(
            [x.url for x in rows], args.key, provider=args.provider, endpoint=args.endpoint, key_location=args.key_location,
            timeout=args.timeout, verify_tls=not args.insecure, dry_run=False,
        )
        print(json.dumps({**plan, "submission": result.to_dict()}, ensure_ascii=False, indent=2))
        return 0 if result.accepted else 1
    raise ValueError("unknown indexnow command")


def _cmd_google_indexing(args: argparse.Namespace) -> int:
    if args.google_indexing_command == "publish":
        urls = list(args.urls or [])
        if args.from_file:
            urls.extend(Path(args.from_file).read_text(encoding="utf-8").splitlines())
        if args.git_repo:
            if not args.base_url:
                raise ValueError("--base-url is required with --git-repo")
            rows = changed_urls_from_git(
                args.git_repo,
                args.base_url,
                from_ref=args.from_ref,
                to_ref=args.to_ref,
                content_root=args.content_root,
                style=args.url_style,
            )
            urls.extend(row.url for row in rows)
        elif args.base_url:
            raise ValueError("--base-url requires --git-repo")
        notification_type = "URL_UPDATED" if args.type == "updated" else "URL_DELETED"
        result = publish_google_urls(
            urls,
            notification_type=notification_type,
            eligible_type=args.eligible_type,
            credentials_path=args.credentials,
            max_notifications=args.max_notifications,
            timeout=args.timeout,
            verify_tls=not args.insecure,
            max_retries=args.max_retries,
            dry_run=not args.send,
        )
        output = {"send": bool(args.send), **result.to_dict()}
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0 if result.failed_count == 0 else 1
    if args.google_indexing_command == "status":
        result = get_metadata(args.url, credentials_path=args.credentials, timeout=args.timeout)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.found else 1
    raise ValueError("unknown google-indexing command")


def _cmd_geo(args: argparse.Namespace) -> int:
    if args.geo_command == "init-rules":
        path = write_rules(args.path, language=args.lang, overwrite=args.force)
        print(path)
        return 0
    if args.geo_command == "git-dates":
        audit = audit_git_dates(args.file, args.repo, tolerance_days=args.tolerance_days)
        print(json.dumps(audit.to_dict(), ensure_ascii=False, indent=2))
        return 1 if audit.warnings else 0
    raise ValueError("unknown geo command")


def _cmd_logs(args: argparse.Namespace) -> int:
    if args.logs_command == "ai-bots":
        result = analyze_ai_bot_log_file(args.file, top_paths=args.top_paths)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    raise ValueError("unknown logs command")


def _cmd_ai(args: argparse.Namespace) -> int:
    from .ai_assistant import AIAssistant
    from .ai_context import load_report_file
    from .ai_credentials import api_key_status, clear_api_key, store_api_key
    from .ai_models import AssistantRequest, ConversationMessage
    from .ai_provider import OpenAICompatibleProvider
    from .config import active_ai_provider

    if args.ai_command == "credentials":
        cfg, _ = load_config()
        credential_id = active_ai_provider(cfg["ai"])["credential_id"]
        if args.action == "set":
            key = getpass.getpass("AI API key (hidden): ")
            store_api_key(key, credential_id)
            print("AI credential stored in the OS credential vault.")
        elif args.action == "status":
            print(json.dumps(api_key_status(credential_id), ensure_ascii=False, indent=2))
        else:
            print("AI credential removed." if clear_api_key(credential_id) else "No stored AI credential found.")
        return 0

    cfg, _ = load_config(getattr(args, "config", None))
    ai_cfg = cfg["ai"]
    selected_provider = active_ai_provider(ai_cfg)
    selected_model = getattr(args, "model", None) or selected_provider.get("model") or ai_cfg["model"]
    if not ai_cfg["enabled"]:
        print("AI assistant is disabled in configuration.", file=sys.stderr)
        return 2
    report = load_report_file(args.report) if args.report else None
    if report is None:
        if not args.url:
            print("Provide a URL or --report.", file=sys.stderr)
            return 2
        report = audit_seo(args.url, allow_private=False, language=args.language).to_dict()
    history: tuple[ConversationMessage, ...] = ()
    if getattr(args, "history", None):
        raw_history = json.loads(Path(args.history).read_text(encoding="utf-8"))
        if not isinstance(raw_history, list) or len(raw_history) > ai_cfg["history_limit"]:
            raise ValueError("history must be a bounded JSON list")
        history = tuple(ConversationMessage(item["role"], item["content"]) for item in raw_history)
    provider = OpenAICompatibleProvider(
        base_url=selected_provider["base_url"],
        credential_id=selected_provider["credential_id"],
        timeout=ai_cfg["timeout"],
        max_retries=ai_cfg["max_retries"],
        allow_loopback_http=ai_cfg["allow_loopback_http"],
    )
    if args.ai_command == "chat" and args.interactive:
        current_history = list(history)
        message = args.message
        while message is not None or not current_history:
            if message is None:
                message = input("You (empty line to exit): ").strip()
            if not message:
                break
            request = AssistantRequest(operation="chat", mode=args.mode, language=args.language, target=args.url, report=report, message=message, history=tuple(current_history))
            response = asyncio.run(AIAssistant(provider, context_limit=ai_cfg["context_limit"], history_limit=ai_cfg["history_limit"], max_concurrent=ai_cfg["max_concurrent"]).run(request, model=selected_model))
            print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
            current_history.extend([ConversationMessage("user", message), ConversationMessage("assistant", response.summary)])
            message = None
        return 0
    if args.ai_command == "chat" and not args.message:
        print("--message is required unless --interactive is used.", file=sys.stderr)
        return 2
    request = AssistantRequest(operation="chat" if args.ai_command == "chat" else "recommend", mode=args.mode, language=args.language, target=args.url, report=report, message=getattr(args, "message", None), history=history)
    response = asyncio.run(AIAssistant(provider, context_limit=ai_cfg["context_limit"], history_limit=ai_cfg["history_limit"], max_concurrent=ai_cfg["max_concurrent"]).run(request, model=selected_model))
    print(json.dumps(response.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn
    except ImportError:
        print("Install server extras: pip install 'agentready-tools[server]'", file=sys.stderr)
        return 2
    cfg, _ = load_config()
    if cfg["ai"]["transport_enabled"] and args.host not in {"127.0.0.1", "::1", "localhost"}:
        print("AI-enabled serve must bind to loopback; use an authenticated external gateway for remote access.", file=sys.stderr)
        return 2
    from .server import app, configure_data_dir

    data_dir = configure_data_dir(getattr(args, "data_dir", None))
    logger.debug("Starting FastAPI app directly: host=%s port=%s data_dir=%s", args.host, args.port, data_dir)
    try:
        uvicorn.run(app, host=args.host, port=args.port, reload=False)
    except SystemExit as exc:
        exit_code = exc.code if isinstance(exc.code, int) else 2
        if exit_code:
            logger.error("FastAPI bind failed: host=%s port=%s exit_code=%s", args.host, args.port, exit_code)
            print(
                f"agentready: unable to bind serve to {args.host}:{args.port}; "
                f"the port may be reserved or blocked by Windows. Try --port {args.port + 1}.",
                file=sys.stderr,
            )
            return 2
        return 0
    return 0


def _cmd_mcp(args: argparse.Namespace) -> int:
    try:
        from .mcp_server import main as run_mcp
    except (ImportError, RuntimeError):
        print(
            "MCP dependency is missing. Activate the project virtual environment and run "
            '`python -m pip install -e ".[mcp]"`; verify with '
            '`python -c "import mcp; print(mcp.__file__)"`.',
            file=sys.stderr,
        )
        return 2
    logger.debug("Starting MCP server from CLI: host=%s port=%s", args.host, args.port)
    run_mcp(host=args.host, port=args.port)
    return 0


def _http_json(base_url: str, path: str, *, method: str = "GET", payload: dict | None = None) -> dict:
    url = base_url.rstrip("/") + path
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(url, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc


def _write_cli_output(content: str, output: str | None) -> None:
    if output:
        Path(output).write_text(content, encoding="utf-8")
    else:
        print(content, end="" if content.endswith("\n") else "\n")


def _cmd_inventory(args: argparse.Namespace) -> int:
    params = {"limit": args.limit, "descending": str(args.descending).lower()}
    if args.cursor:
        params["cursor"] = args.cursor
    if args.search:
        params["search"] = args.search
    if args.sort_by:
        params["sort_by"] = args.sort_by
    query = urllib.parse.urlencode(params)
    page = _http_json(args.base_url, f"/v2/runs/{urllib.parse.quote(args.run_id, safe='')}/inventory/{args.kind}?{query}")
    if args.format == "json":
        content = json.dumps(page, ensure_ascii=False, indent=2)
    else:
        exported = _http_json(args.base_url, "/v2/export", method="POST", payload={"items": page.get("items", []), "format": args.format})
        content = str(exported.get("content", ""))
    _write_cli_output(content, args.output)
    logger.info("CLI inventory query run_id=%s kind=%s limit=%d", args.run_id, args.kind, args.limit)
    return 0


def _cmd_view(args: argparse.Namespace) -> int:
    if args.action != "list" and not args.view_id:
        raise ValueError("view get/delete requires a view_id")
    path = "/v2/saved-views" if args.action == "list" else f"/v2/saved-views/{urllib.parse.quote(args.view_id, safe='')}"
    result = _http_json(args.base_url, path, method="DELETE" if args.action == "delete" else "GET")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


def _cmd_sitemap(args: argparse.Namespace) -> int:
    if args.sitemap_command != "reconcile":
        raise ValueError("unsupported sitemap command")
    payload = {
        "documents": [Path(path).read_text(encoding="utf-8") for path in args.document],
        "origin": args.origin,
        "category": args.category,
        "cursor": args.cursor,
        "limit": args.limit,
        "format": args.format,
    }
    result = _http_json(args.base_url, f"/v2/runs/{urllib.parse.quote(args.run_id, safe='')}/sitemap/reconcile", method="POST", payload=payload)
    content = result.get("content") if args.format == "csv" else json.dumps(result, ensure_ascii=False, indent=2)
    _write_cli_output(str(content), args.output)
    logger.info("CLI sitemap reconciliation run_id=%s category=%s", args.run_id, args.category)
    return 0


def _cmd_rules(args: argparse.Namespace) -> int:
    rules_text = Path(args.rules_file).read_text(encoding="utf-8")
    if args.rules_command == "validate":
        result = _http_json(args.base_url, "/v2/custom-rules/validate", method="POST", payload={"rules": rules_text})
    elif args.rules_command == "test":
        result = _http_json(args.base_url, "/v2/custom-rules/debug", method="POST", payload={"rules": rules_text, "url": args.url, "text": args.text})
    else:
        raise ValueError("unsupported rules command")
    _write_cli_output(json.dumps(result, ensure_ascii=False, indent=2), args.output)
    logger.info("CLI custom rules command=%s", args.rules_command)
    return 0


def _cmd_graph(args: argparse.Namespace) -> int:
    params = {"limit": args.limit}
    if args.origin:
        params["origin"] = args.origin
    if args.cursor:
        params["cursor"] = args.cursor
    if args.dead_end:
        params["dead_end"] = "true"
    if args.disconnected:
        params["disconnected"] = "true"
    path = f"/v2/runs/{urllib.parse.quote(args.run_id, safe='')}/graph"
    if args.node:
        path += "/node?" + urllib.parse.urlencode({"url": args.node, **({"origin": args.origin} if args.origin else {})})
    else:
        path += "?" + urllib.parse.urlencode(params)
    result = _http_json(args.base_url, path)
    if args.format == "csv" and not args.node:
        rows = result.get("items", [])
        content = "url,inlinks,outlinks,unique_inlinks,unique_outlinks,depth,dead_end,disconnected,authority\n" + "\n".join(",".join(str(row.get(key, "")) for key in ("url", "inlinks", "outlinks", "unique_inlinks", "unique_outlinks", "depth", "dead_end", "disconnected", "authority")) for row in rows) + "\n"
    else:
        content = json.dumps(result, ensure_ascii=False, indent=2)
    _write_cli_output(content, args.output)
    logger.info("CLI graph query run_id=%s node=%s", args.run_id, bool(args.node))
    return 0


def _cmd_duplicates(args: argparse.Namespace) -> int:
    base = f"/v2/runs/{urllib.parse.quote(args.run_id, safe='')}/duplicates"
    if args.cluster:
        path = base + "/" + urllib.parse.quote(args.cluster, safe="") + "?" + urllib.parse.urlencode({"threshold": args.threshold})
    else:
        params = {"kind": args.kind, "threshold": args.threshold, "limit": args.limit}
        if args.cursor:
            params["cursor"] = args.cursor
        path = base + "?" + urllib.parse.urlencode(params)
    result = _http_json(args.base_url, path)
    _write_cli_output(json.dumps(result, ensure_ascii=False, indent=2), args.output)
    logger.info("CLI duplicate query run_id=%s cluster=%s", args.run_id, bool(args.cluster))
    return 0


def _cmd_rescan(args: argparse.Namespace) -> int:
    payload = {
        "url": args.url,
        "preset": "all",
        "profile": "standard",
        "max_pages": args.max_pages,
        "selected_urls": args.select_url,
        "rescan_of": args.rescan_of,
    }
    print(json.dumps(_http_json(args.base_url, "/v2/rescan", method="POST", payload=payload), ensure_ascii=False, indent=2))
    return 0


def _cmd_compare(args: argparse.Namespace) -> int:
    baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    payload = {
        "request": {"url": args.url, "preset": "all", "profile": "standard", "max_pages": args.max_pages},
        "baseline": baseline,
    }
    print(json.dumps(_http_json(args.base_url, "/v2/diff", method="POST", payload=payload), ensure_ascii=False, indent=2))
    return 0


def _cmd_robots(args: argparse.Namespace) -> int:
    live = Path(args.live).read_text(encoding="utf-8") if args.live else ""
    proposed = Path(args.proposed).read_text(encoding="utf-8")
    payload = {
        "live_robots": live,
        "proposed_robots": proposed,
        "user_agents": args.user_agents or ["*"],
        "observed_search_pages": args.observed_page,
        "interpretation": args.interpretation,
        "origin": args.origin,
    }
    result = _http_json(
        args.base_url,
        f"/v2/runs/{urllib.parse.quote(args.run_id, safe='')}/robots/simulate",
        method="POST",
        payload=payload,
    )
    content = json.dumps(result, ensure_ascii=False, indent=2)
    _write_cli_output(content, args.output)
    logger.info("CLI robots simulation run_id=%s bots=%d", args.run_id, len(args.user_agents or ["*"]))
    return 0


def main(argv: list[str] | None = None) -> int:
    try:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8")
        _configure_logging()
        parser = build_parser()
        try:
            args = parser.parse_args(argv)
        except SystemExit as exc:
            code = exc.code if isinstance(exc.code, int) else 2
            logger.info("CLI argument processing completed: exit_code=%s", code)
            return code
        logger.info(
            "CLI command selected: command=%s frozen=%s",
            args.command,
            bool(getattr(sys, "frozen", False)),
        )
        if args.command == "audit":
            return _cmd_audit(args)
        if args.command == "inventory":
            return _cmd_inventory(args)
        if args.command == "view":
            return _cmd_view(args)
        if args.command == "rescan":
            return _cmd_rescan(args)
        if args.command == "compare":
            return _cmd_compare(args)
        if args.command == "robots":
            return _cmd_robots(args)
        if args.command == "sitemap":
            return _cmd_sitemap(args)
        if args.command == "rules":
            return _cmd_rules(args)
        if args.command == "graph":
            return _cmd_graph(args)
        if args.command == "duplicates":
            return _cmd_duplicates(args)
        if args.command == "ai":
            return _cmd_ai(args)
        if args.command == "checks":
            return _cmd_checks(args)
        if args.command == "credentials":
            return _cmd_credentials(args)
        if args.command == "init":
            return _cmd_init(args)
        if args.command == "indexnow":
            return _cmd_indexnow(args)
        if args.command == "google-indexing":
            return _cmd_google_indexing(args)
        if args.command == "geo":
            return _cmd_geo(args)
        if args.command == "logs":
            return _cmd_logs(args)
        if args.command == "serve":
            return _cmd_serve(args)
        if args.command == "mcp":
            return _cmd_mcp(args)
        parser.error("unknown command")
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001 - CLI boundary converts failures to exit status 2.
        print(f"agentready: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    return 0


def _cmd_audit(args: argparse.Namespace) -> int:
    if args.min_score is not None and not 0 <= args.min_score <= 100:
        logger.error("[FIX:cli-contract] invalid score gate: min_score=%s", args.min_score)
        print("agentready: min-score must be between 0 and 100", file=sys.stderr)
        return 2
    urls = tuple(args.url)
    if args.mode == "mobile":
        from .mobile_report import render_mobile
        from .mobile_scanner import audit_mobile

        report = audit_mobile(
            urls,
            render=args.render,
            timeout=args.timeout,
            allow_private=False,
            recommendation_limit=args.recommendations,
            language=args.language,
        )
        output = render_mobile(report, args.format, args.language)
        saved_path = save_report(output, target=urls[0], surface="cli-mobile", fmt=args.format)
        logger.info("report saved path=%s", saved_path)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        return 1 if args.min_score is not None and report.score < args.min_score else 0

    if args.mode == "seo":
        from .seo_checks import SEO_CHECKS_BY_ID
        from .seo_crawler import CRAWL_CHECKS_BY_ID
        known = set(SEO_CHECKS_BY_ID) | set(CRAWL_CHECKS_BY_ID)
        unknown = [item for item in args.checks if item not in known]
        if unknown:
            raise ValueError(f"Unknown SEO check(s): {', '.join(unknown)}")
        report = audit_seo(
            urls[0],
            checks=tuple(SEO_CHECKS_BY_ID[item] for item in args.checks if item in SEO_CHECKS_BY_ID),
            crawl_checks=tuple(CRAWL_CHECKS_BY_ID[item] for item in args.checks if item in CRAWL_CHECKS_BY_ID),
            timeout=args.timeout, allow_private=False,
            recommendation_limit=args.recommendations, language=args.language,
            crawl=args.crawl or bool(args.checks), max_pages=args.max_pages,
            render=args.render, ga_property=args.ga_property, gsc_site=args.gsc_site,
        )
        output = render_seo(report, args.format, args.language)
        saved_path = save_report(output, target=urls[0], surface="cli-seo", fmt=args.format)
        logger.info("report saved path=%s", saved_path)
        if args.output:
            Path(args.output).write_text(output, encoding="utf-8")
        else:
            print(output, end="")
        if args.baseline:
            regressions = compare_seo_baseline(report, args.baseline)
            if regressions:
                print("\n".join(f"baseline: {item}" for item in regressions), file=sys.stderr)
                return 1
        return 1 if args.min_score is not None and report.score < args.min_score else 0

    limits = {
        key: value
        for key, value in {
            "max_depth": args.max_depth,
            "max_duration": args.max_duration,
            "concurrency": args.concurrency,
            "per_origin_concurrency": args.per_origin_concurrency,
        }.items()
        if value is not None
    }
    result = AuditService().run(
        AuditRequest(
            target=urls[0],
            preset=args.preset,
            profile=args.profile,
            max_pages=args.max_pages,
            timeout=args.timeout,
            limits=limits,
            include=tuple(args.include),
            exclude=tuple(args.exclude),
            selected_urls=tuple(args.select_url),
            discovery_kind=args.discovery_kind,
            discovery_urls=tuple(args.discovery_url),
            discovery_sitemap_xml=Path(args.discovery_sitemap_xml).read_text(encoding="utf-8") if args.discovery_sitemap_xml else None,
            discovery_sitemap_urls=tuple(args.discovery_url) if args.discovery_kind == "robots-sitemap" else (),
            discovery_limit=args.discovery_limit,
            render=args.render,
            provider=args.provider,
            language=args.language,
        )
    )
    output = render_audit_report(result.report, args.format)
    saved_path = save_report(output, target=urls[0], surface="cli-readiness", fmt=args.format)
    logger.info("report saved path=%s", saved_path)
    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
    else:
        print(output)
    if args.baseline:
        baseline = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
        changes = classify_finding_changes(result.report, baseline)
        if changes["regressed"]:
            print("baseline regressions: " + ", ".join(changes["regressed"]), file=sys.stderr)
            return 1
        diff_reports(result.report, baseline)
    if args.min_score is not None and result.report.score < args.min_score:
        logger.warning("[FIX:cli-contract] readiness score gate failed: score=%d required=%d", result.report.score, args.min_score)
        return 1
    return 1 if args.fail_on_checks and any(item.status.value == "fail" for item in result.report.findings) else 0


def _configure_logging() -> None:
    level_name = os.environ.get("LOG_LEVEL", "WARNING").strip().upper()
    level = getattr(logging, level_name, None)
    if not isinstance(level, int):
        raise TypeError(f"invalid LOG_LEVEL {level_name!r}; expected DEBUG, INFO, WARNING, or ERROR")
    logging.basicConfig(
        level=level,
        format="%(levelname)s %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logger.debug("CLI logging configured: level=%s stream=stderr", level_name)


if __name__ == "__main__":
    raise SystemExit(main())

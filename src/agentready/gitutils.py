from __future__ import annotations

import html as html_lib
import json
import re
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import yaml


class GitAuditError(ValueError):
    pass


@dataclass(slots=True)
class ChangedUrl:
    source_path: str
    url: str
    mapping: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


@dataclass(slots=True)
class GitDateAudit:
    file: str
    repo: str
    first_commit: str | None
    last_file_commit: str | None
    last_semantic_change: str | None
    declared_published: str | None
    declared_modified: str | None
    warnings: list[str]
    semantic_method: str = "normalized visible/content text heuristic; not proof of editorial intent"

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _run_git(repo: str | Path, args: list[str]) -> str:
    root = Path(repo).resolve()
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as exc:
        raise GitAuditError("git executable not found") from exc
    if proc.returncode != 0:
        raise GitAuditError(proc.stderr.strip() or f"git command failed: {' '.join(args)}")
    return proc.stdout


def git_root(repo: str | Path = ".") -> Path:
    out = _run_git(repo, ["rev-parse", "--show-toplevel"]).strip()
    if not out:
        raise GitAuditError("not a Git repository")
    return Path(out).resolve()


def changed_files(repo: str | Path = ".", from_ref: str = "HEAD~1", to_ref: str = "HEAD") -> list[str]:
    root = git_root(repo)
    out = _run_git(root, ["diff", "--name-only", "--diff-filter=ACMRT", from_ref, to_ref, "--"])
    return [line.strip().replace("\\", "/") for line in out.splitlines() if line.strip()]


def _frontmatter_url(text: str, base_url: str) -> tuple[str | None, str | None]:
    if not text.startswith("---"):
        return None, None
    m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
    if not m:
        return None, None
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None, None
    if not isinstance(data, dict):
        return None, None
    for key in ("canonical", "canonical_url", "permalink", "url"):
        value = data.get(key)
        if isinstance(value, str) and value.strip():
            value = value.strip()
            return (value if urlsplit(value).scheme else urljoin(base_url.rstrip("/") + "/", value.lstrip("/"))), f"frontmatter:{key}"
    return None, None


def _html_canonical(text: str, base_url: str) -> tuple[str | None, str | None]:
    m = re.search(
        r"<link\b(?=[^>]*\brel\s*=\s*['\"]?canonical['\"]?)(?=[^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"])[^>]*>",
        text,
        re.IGNORECASE,
    )
    if not m:
        m = re.search(
            r"<link\b(?=[^>]*\bhref\s*=\s*['\"]([^'\"]+)['\"])(?=[^>]*\brel\s*=\s*['\"]?canonical['\"]?)[^>]*>",
            text,
            re.IGNORECASE,
        )
    if not m:
        return None, None
    href = m.group(1).strip()
    return urljoin(base_url.rstrip("/") + "/", href), "html:canonical"


def _path_url(relative: Path, base_url: str, style: str) -> str:
    if style not in {"pretty", "files"}:
        raise GitAuditError("url style must be pretty or files")
    posix = relative.as_posix().lstrip("/")
    if style == "files":
        return urljoin(base_url.rstrip("/") + "/", posix)
    suffix = relative.suffix.lower()
    if suffix in {".html", ".htm", ".md", ".mdx"}:
        without = relative.with_suffix("")
        if without.name.lower() == "index":
            route = without.parent.as_posix().strip("/") + "/"
        else:
            route = without.as_posix().strip("/") + "/"
        return urljoin(base_url.rstrip("/") + "/", route)
    return urljoin(base_url.rstrip("/") + "/", posix)


def changed_urls_from_git(
    repo: str | Path,
    base_url: str,
    *,
    from_ref: str = "HEAD~1",
    to_ref: str = "HEAD",
    content_root: str = ".",
    style: str = "pretty",
    extensions: tuple[str, ...] = (".html", ".htm", ".md", ".mdx"),
) -> list[ChangedUrl]:
    base = urlsplit(base_url if "://" in base_url else "https://" + base_url)
    if base.scheme not in {"http", "https"} or not base.hostname:
        raise GitAuditError("base_url must be an absolute http(s) URL")
    root = git_root(repo)
    content = (root / content_root).resolve()
    try:
        content.relative_to(root)
    except ValueError as exc:
        raise GitAuditError("content_root must be inside the Git repository") from exc

    allowed = {x.lower() if x.startswith(".") else "." + x.lower() for x in extensions}
    out: list[ChangedUrl] = []
    seen: set[str] = set()
    for rel_text in changed_files(root, from_ref, to_ref):
        full = (root / rel_text).resolve()
        if not full.exists() or not full.is_file() or full.suffix.lower() not in allowed:
            continue
        try:
            relative = full.relative_to(content)
        except ValueError:
            continue
        text = full.read_text(encoding="utf-8", errors="replace")
        url: str | None = None
        mapping: str | None = None
        if full.suffix.lower() in {".md", ".mdx"}:
            url, mapping = _frontmatter_url(text, base_url)
        elif full.suffix.lower() in {".html", ".htm"}:
            url, mapping = _html_canonical(text, base_url)
        if not url:
            url = _path_url(relative, base_url, style)
            mapping = f"path:{style}"
        parsed = urlsplit(url)
        if parsed.netloc.lower() != base.netloc.lower():
            raise GitAuditError(f"mapped URL leaves requested host: {rel_text} -> {url}")
        if url not in seen:
            out.append(ChangedUrl(rel_text, url, mapping or "path"))
            seen.add(url)
    return out


def _normalize_semantic(text: str, suffix: str) -> str:
    if suffix in {".md", ".mdx"}:
        text = re.sub(r"^---\s*\n.*?\n---\s*(?:\n|$)", "", text, flags=re.DOTALL)
        text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    elif suffix in {".html", ".htm"}:
        text = re.sub(r"(?is)<(?:script|style|noscript|svg)\b.*?</(?:script|style|noscript|svg)>", " ", text)
        text = re.sub(r"(?is)<[^>]+>", " ", text)
        text = html_lib.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def _git_history(root: Path, rel: str) -> list[tuple[str, str]]:
    out = _run_git(root, ["log", "--follow", "--format=%H%x09%cI", "--", rel])
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        if "\t" in line:
            commit, when = line.split("\t", 1)
            rows.append((commit.strip(), when.strip()))
    return rows


def _git_show(root: Path, commit: str, rel: str) -> str | None:
    try:
        return _run_git(root, ["show", f"{commit}:{rel}"])
    except GitAuditError:
        return None


def git_file_dates(path: str | Path, repo: str | Path = ".") -> tuple[str | None, str | None, str | None]:
    root = git_root(repo)
    full = Path(path)
    if not full.is_absolute():
        full = (root / full).resolve()
    try:
        rel = full.relative_to(root).as_posix()
    except ValueError as exc:
        raise GitAuditError("file must be inside the Git repository") from exc
    history = _git_history(root, rel)
    if not history:
        return None, None, None
    first_commit = history[-1][1]
    last_file_commit = history[0][1]

    newest_text = _git_show(root, history[0][0], rel)
    last_semantic = history[0][1]
    if newest_text is not None:
        newer_norm = _normalize_semantic(newest_text, full.suffix.lower())
        for older_hash, _older_when in history[1:]:
            older_text = _git_show(root, older_hash, rel)
            if older_text is None:
                break
            older_norm = _normalize_semantic(older_text, full.suffix.lower())
            if older_norm != newer_norm:
                break
            last_semantic = _older_when
            newer_norm = older_norm
        # last_semantic above walks through metadata-only commits. The semantic
        # change belongs to the newer side of the first differing pair, so find
        # the newest commit whose normalized content differs from its predecessor.
        for idx in range(len(history) - 1):
            a = _git_show(root, history[idx][0], rel)
            b = _git_show(root, history[idx + 1][0], rel)
            if a is not None and b is not None and _normalize_semantic(a, full.suffix.lower()) != _normalize_semantic(b, full.suffix.lower()):
                last_semantic = history[idx][1]
                break
    return first_commit, last_file_commit, last_semantic


def _declared_dates(path: Path) -> tuple[str | None, str | None]:
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix.lower() in {".md", ".mdx"}:
        m = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", text, re.DOTALL)
        if not m:
            return None, None
        try:
            data = yaml.safe_load(m.group(1)) or {}
        except yaml.YAMLError:
            return None, None
        if not isinstance(data, dict):
            return None, None
        pub = data.get("datePublished") or data.get("date") or data.get("published")
        mod = data.get("dateModified") or data.get("lastmod") or data.get("updated") or data.get("modified")
        return (str(pub) if pub else None, str(mod) if mod else None)

    if path.suffix.lower() in {".html", ".htm"}:
        scripts = re.findall(r"(?is)<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>", text)
        for raw in scripts:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                continue
            nodes: list[dict] = []
            items = data if isinstance(data, list) else [data]
            for item in items:
                if isinstance(item, dict) and isinstance(item.get("@graph"), list):
                    nodes.extend(x for x in item["@graph"] if isinstance(x, dict))
                elif isinstance(item, dict):
                    nodes.append(item)
            for node in nodes:
                types = node.get("@type")
                vals = types if isinstance(types, list) else [types]
                if any(str(x).lower().endswith(("article", "blogposting", "newsarticle", "techarticle")) for x in vals if x):
                    pub = node.get("datePublished")
                    mod = node.get("dateModified")
                    return (str(pub) if pub else None, str(mod) if mod else None)
    return None, None


def _date_only(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        try:
            return datetime.fromisoformat(raw[:10])
        except ValueError:
            return None


def audit_git_dates(path: str | Path, repo: str | Path = ".", tolerance_days: int = 1) -> GitDateAudit:
    root = git_root(repo)
    full = Path(path)
    if not full.is_absolute():
        full = (root / full).resolve()
    first, last_file, last_semantic = git_file_dates(full, root)
    pub, mod = _declared_dates(full)
    warnings: list[str] = []
    pub_dt = _date_only(pub)
    mod_dt = _date_only(mod)
    first_dt = _date_only(first)
    semantic_dt = _date_only(last_semantic)
    tolerance = max(0, tolerance_days)
    if pub and not pub_dt:
        warnings.append("declared publication date is not parseable as ISO-8601")
    if mod and not mod_dt:
        warnings.append("declared modification date is not parseable as ISO-8601")
    if pub_dt and mod_dt and mod_dt < pub_dt:
        warnings.append("declared modification date precedes publication date")
    if pub_dt and first_dt and abs((pub_dt.date() - first_dt.date()).days) > tolerance:
        warnings.append("declared publication date differs from first Git commit beyond tolerance; this can be legitimate after migrations, so review manually")
    if mod_dt and semantic_dt and abs((mod_dt.date() - semantic_dt.date()).days) > tolerance:
        warnings.append("declared modification date differs from the last normalized-content Git change beyond tolerance; review whether dateModified reflects a real content update")
    return GitDateAudit(
        file=str(full), repo=str(root), first_commit=first, last_file_commit=last_file,
        last_semantic_change=last_semantic, declared_published=pub, declared_modified=mod,
        warnings=warnings,
    )

-- Immutable schema reference for SQLiteSiteStore schema version 1.
PRAGMA foreign_keys=ON;
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
) STRICT;
CREATE TABLE runs (
    id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    config_hash TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    rule_catalog_version TEXT NOT NULL,
    state TEXT NOT NULL
) STRICT;
CREATE TABLE urls (
    id INTEGER PRIMARY KEY,
    url_key TEXT NOT NULL UNIQUE,
    url TEXT NOT NULL,
    scheme TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER,
    path TEXT NOT NULL,
    query TEXT
) STRICT;
CREATE INDEX idx_urls_host ON urls(host);
CREATE TABLE fetches (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES runs(id),
    request_url TEXT NOT NULL,
    final_url TEXT,
    status_code INTEGER,
    error_kind TEXT,
    total_ms REAL,
    wire_bytes INTEGER,
    decoded_bytes INTEGER,
    body_hash TEXT
) STRICT;
CREATE TABLE pages (
    run_id TEXT NOT NULL REFERENCES runs(id),
    url_key TEXT NOT NULL,
    requested_url TEXT NOT NULL,
    final_url TEXT,
    depth INTEGER NOT NULL,
    status_code INTEGER,
    content_type TEXT,
    title TEXT,
    canonical TEXT,
    locally_indexable INTEGER,
    content_hash TEXT,
    content TEXT,
    PRIMARY KEY(run_id, url_key)
) STRICT;
CREATE TABLE links (
    run_id TEXT NOT NULL REFERENCES runs(id),
    source_key TEXT NOT NULL,
    raw_href TEXT NOT NULL,
    target_key TEXT,
    resolved_url TEXT,
    rel_flags INTEGER NOT NULL,
    anchor_text TEXT,
    discovery_method TEXT NOT NULL,
    PRIMARY KEY(run_id, source_key, raw_href)
) WITHOUT ROWID;
CREATE TABLE redirects (
    run_id TEXT NOT NULL REFERENCES runs(id),
    from_url TEXT NOT NULL,
    to_url TEXT,
    status_code INTEGER NOT NULL,
    location_raw TEXT NOT NULL,
    PRIMARY KEY(run_id, from_url, to_url)
) WITHOUT ROWID;
CREATE TABLE resources (
    run_id TEXT NOT NULL REFERENCES runs(id),
    page_key TEXT NOT NULL,
    resource_url TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    status_code INTEGER,
    PRIMARY KEY(run_id, page_key, resource_url)
) WITHOUT ROWID;
CREATE TABLE evidence (
    run_id TEXT NOT NULL REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(run_id, item_id)
) WITHOUT ROWID;
CREATE TABLE findings (
    run_id TEXT NOT NULL REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL,
    PRIMARY KEY(run_id, item_id)
) WITHOUT ROWID;
CREATE TABLE coverage (
    run_id TEXT PRIMARY KEY REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL
) WITHOUT ROWID;
CREATE TABLE version_manifests (
    run_id TEXT PRIMARY KEY REFERENCES runs(id),
    item_id TEXT NOT NULL,
    payload TEXT NOT NULL
) WITHOUT ROWID;
CREATE INDEX idx_pages_run_status ON pages(run_id, status_code);
CREATE INDEX idx_fetches_run ON fetches(run_id);
PRAGMA user_version=1;

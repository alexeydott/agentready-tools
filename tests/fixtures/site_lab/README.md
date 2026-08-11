# Site Lab fixture

`SiteLabServer` is a deterministic, same-origin HTTP server for integration
tests. It binds to a random loopback port, does not require public internet
access, suppresses request logging by default, and shuts down cleanly through
its context manager.

```python
from tests.fixtures.site_lab import SiteLabServer

with SiteLabServer() as site:
    target = site.base_url
    # Run a bounded audit against target.
```

The scenario manifest is in `manifest.json`. The Basic Auth credentials are
local fixture values only and must never be reused in production or emitted in
logs, evidence, reports, or archives.

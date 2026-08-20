"""Anything marketplace lookups.

Anything (https://anything.notte.cc) is the hosted version of this tool: you
describe a task and get back a deployed API function instead of a local file.
Its marketplace already holds several hundred ready-made functions, so before
we spend a capture run reverse-engineering a site from scratch it is worth
asking whether somebody already did it.

Everything here is best-effort and strictly optional. The marketplace search
endpoint is public (no key, no account), every call is wrapped in a short
timeout, and any failure degrades to "no suggestions" rather than an error —
a capture must never fail because a marketing lookup did.

Set ``RAE_NO_CLOUD=1`` (or turn off ``cloud_suggestions`` in settings) to
disable the network call entirely.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlparse

CLOUD_HOST = "anything.notte.cc"
CLOUD_URL = f"https://{CLOUD_HOST}"
MARKETPLACE_URL = f"{CLOUD_URL}/marketplace"
MCP_URL = f"{CLOUD_URL}/mcp"
SEARCH_ENDPOINT = f"{CLOUD_URL}/api/marketplace/search"

#: The search endpoint is serverless: ~0.3s warm, but several seconds after an
#: idle period and occasionally worse. A tight timeout would drop real matches
#: exactly when the answer is most useful, so the budget is generous and
#: callers show a spinner rather than hiding the wait. A very cold call can
#: still exceed this, which is fine — the caller just shows no suggestions.
DEFAULT_TIMEOUT = 12.0

#: Second-level labels that are effectively part of the public suffix. Used to
#: keep "bbc.co.uk" from collapsing to the useless registrable domain "co.uk".
_COMPOUND_SLDS = frozenset({"co", "com", "org", "net", "gov", "edu", "ac"})


@dataclass(frozen=True)
class MarketplaceFunction:
    """One ready-made function published on the Anything marketplace."""

    function_id: str
    label: str
    description: str
    domain: str
    run_count: int = 0

    @property
    def url(self) -> str:
        """Canonical marketplace page for this function."""
        return f"{MARKETPLACE_URL}/{self.function_id}"

    @classmethod
    def from_api(cls, raw: dict) -> MarketplaceFunction | None:
        """Build from one search-result object, or None if it is unusable."""
        function_id = str(raw.get("function_id") or "").strip()
        label = str(raw.get("label") or "").strip()
        if not function_id or not label:
            return None
        try:
            run_count = int(raw.get("run_count") or 0)
        except (TypeError, ValueError):
            run_count = 0
        return cls(
            function_id=function_id,
            label=label,
            description=str(raw.get("description") or "").strip(),
            domain=_normalize_host(str(raw.get("domain") or "")),
            run_count=run_count,
        )


def suggestions_enabled(config_manager=None) -> bool:
    """Whether marketplace lookups are allowed at all.

    The env var wins over config so CI and scripted wrappers can turn the
    network call off without touching the user's settings file.
    """
    if _env_flag("RAE_NO_CLOUD"):
        return False
    if config_manager is None:
        return True
    return bool(config_manager.get("cloud_suggestions", True))


def cloud_link(url: str, campaign: str) -> str:
    """Tag an outbound cloud URL with the placement it came from."""
    joiner = "&" if "?" in url else "?"
    return f"{url}{joiner}utm_source=rae&utm_medium=cli&utm_campaign={campaign}"


def registrable_domain(url_or_host: str) -> str | None:
    """Reduce a URL or hostname to the domain a marketplace entry would use.

    ``https://jobs.ashbyhq.com/openai?x=1`` -> ``ashbyhq.com``
    ``www.bbc.co.uk``                       -> ``bbc.co.uk``

    Returns None when there is no usable hostname (bare paths, IPs, garbage).
    """
    host = _extract_host(url_or_host)
    if not host:
        return None

    labels = host.split(".")
    if len(labels) < 2:
        return None
    # An IPv4 literal has no registrable domain worth searching for.
    if all(label.isdigit() for label in labels):
        return None

    if len(labels) >= 3 and labels[-2] in _COMPOUND_SLDS and len(labels[-1]) <= 3:
        return ".".join(labels[-3:])
    return ".".join(labels[-2:])


def search(
    query: str | None = None,
    *,
    base_url: str | None = None,
    category: str | None = None,
    limit: int = 5,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MarketplaceFunction]:
    """Search the public marketplace. Returns [] on any failure.

    The endpoint needs no authentication, so this works for every user. All
    three filters are optional and compose: `base_url` scopes to one site,
    `category` to one marketplace category, and `query` ranks within whatever
    is left. At least one must be supplied — an unfiltered call would just
    return the most-run functions overall, which is never what a caller here
    wants.

    `base_url` accepts any form the site is written in: a bare hostname, a
    full URL, or a glob. Matching happens server-side and covers subdomains.
    """
    params: dict[str, str | int] = {"limit": max(1, limit)}
    if query and query.strip():
        params["q"] = query.strip()
    if base_url and base_url.strip():
        params["base_url"] = base_url.strip()
    if category and category.strip():
        params["category"] = category.strip()

    if not any(key in params for key in ("q", "base_url", "category")):
        return []

    try:
        import requests

        response = requests.get(
            SEARCH_ENDPOINT,
            params=params,
            timeout=timeout,
            headers={"User-Agent": _user_agent()},
        )
        if response.status_code != 200:
            return []
        payload = response.json()
    except Exception:
        # Offline, DNS failure, timeout, non-JSON body, requests missing —
        # all mean the same thing here: no suggestions.
        return []

    if not isinstance(payload, dict):
        return []
    results = payload.get("results")
    if not isinstance(results, list):
        return []

    functions = []
    for raw in results:
        if isinstance(raw, dict):
            fn = MarketplaceFunction.from_api(raw)
            if fn is not None:
                functions.append(fn)
    return functions


def search_for_site(
    url_or_host: str,
    *,
    limit: int = 3,
    timeout: float = DEFAULT_TIMEOUT,
) -> list[MarketplaceFunction]:
    """Find existing functions for one site, with no false positives.

    `base_url` scopes the search server-side and understands full URLs, so the
    target is passed through untouched. `registrable_domain` is still consulted
    first to skip inputs that are not sites at all (localhost, IP literals,
    free text), and the results are re-checked against it afterwards: server-
    side matching is deliberately fuzzy, and suggesting the wrong site is worse
    than suggesting nothing.
    """
    domain = registrable_domain(url_or_host)
    if not domain:
        return []

    matches = [fn for fn in search(base_url=url_or_host, limit=limit, timeout=timeout) if _covers(fn.domain, domain)]
    matches.sort(key=lambda fn: fn.run_count, reverse=True)
    return matches[:limit]


def _covers(candidate_host: str, domain: str) -> bool:
    """True when `candidate_host` belongs to `domain`."""
    if not candidate_host:
        return False
    return candidate_host == domain or candidate_host.endswith(f".{domain}")


def _extract_host(url_or_host: str) -> str:
    raw = (url_or_host or "").strip()
    if not raw:
        return ""
    if "//" not in raw:
        # urlparse needs a scheme to populate `netloc`.
        raw = f"//{raw}"
    try:
        netloc = urlparse(raw).netloc
    except ValueError:
        return ""
    # Drop credentials and port.
    netloc = netloc.rsplit("@", 1)[-1]
    if netloc.startswith("["):  # IPv6 literal
        return ""
    netloc = netloc.split(":", 1)[0]
    return _normalize_host(netloc)


def _normalize_host(host: str) -> str:
    host = (host or "").strip().lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _user_agent() -> str:
    try:
        from . import __version__

        return f"reverse-api-engineer/{__version__}"
    except Exception:
        return "reverse-api-engineer"

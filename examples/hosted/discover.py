"""Search the Anything marketplace for a function that already exists.

Runs with no API key and no account — the marketplace search endpoint is
public. Use it before spending a capture run on a site somebody has already
reverse-engineered.

    python discover.py nfl.com
    python discover.py "instagram post comments"
"""

import json
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SEARCH_ENDPOINT = "https://anything.notte.cc/api/marketplace/search"
MARKETPLACE_URL = "https://anything.notte.cc/marketplace"


def search(query: str | None = None, base_url: str | None = None, limit: int = 5) -> list[dict]:
    """Return marketplace functions matching `query`, `base_url`, or both.

    `base_url` scopes to one site and understands any form it is written in:
    a bare hostname, a full URL, or a glob like `*.nfl.*`. `query` ranks
    within whatever is left. The two compose.
    """
    params = {"limit": limit}
    if query:
        params["q"] = query
    if base_url:
        params["base_url"] = base_url

    url = f"{SEARCH_ENDPOINT}?{urlencode(params)}"
    with urlopen(Request(url, headers={"User-Agent": "anything-example"}), timeout=15) as response:
        payload = json.load(response)
    return payload.get("results", [])


def functions_for_site(site: str, limit: int = 5) -> list[dict]:
    """Return the functions that belong to one site, most-run first."""
    matches = sorted(
        search(base_url=site, limit=limit),
        key=lambda fn: fn.get("run_count", 0),
        reverse=True,
    )
    return matches[:limit]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    query = " ".join(sys.argv[1:])
    # A bare hostname is almost always a "is this site covered?" question.
    looks_like_domain = "." in query and " " not in query
    results = functions_for_site(query) if looks_like_domain else search(query)

    if not results:
        print(f"No hosted function matches {query!r} yet.")
        print("Describe the task at https://anything.notte.cc and it gets built for you.")
        return 0

    print(f"{len(results)} function(s) for {query!r}:\n")
    for fn in results:
        print(f"  {fn['label']}  [{fn.get('domain', '?')}] · {fn.get('run_count', 0)} runs")
        if fn.get("description"):
            print(f"    {fn['description']}")
        print(f"    {MARKETPLACE_URL}/{fn['function_id']}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

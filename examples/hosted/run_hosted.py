"""Run a hosted Anything function instead of a locally generated client.

Unlike `discover.py`, this one needs a key: get one at https://console.notte.cc
and export it as NOTTE_API_KEY.

    export NOTTE_API_KEY=...
    python run_hosted.py 365309fa-acb6-4226-b410-9a5f86fb72d9 '{"season": 2025}'

Each function declares its own variables. The names and types are listed on
that function's marketplace page — `discover.py` prints the URL for every
result, so start there rather than guessing.
"""

import json
import os
import sys
from urllib.error import HTTPError
from urllib.request import Request, urlopen

RUN_ENDPOINT = "https://anything.notte.cc/api/functions/{function_id}/run"


def run(function_id: str, variables: dict, api_key: str) -> dict:
    """Execute one hosted function and return its result JSON.

    The request mirrors the `run` tool exposed on the MCP endpoint: the
    function id identifies which skill to execute, and `variables` carries the
    values it declared.
    """
    request = Request(
        RUN_ENDPOINT.format(function_id=function_id),
        data=json.dumps({"variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "anything-example",
        },
        method="POST",
    )
    # Hosted runs drive a real browser, so they are slow by design.
    with urlopen(request, timeout=180) as response:
        return json.load(response)


def main() -> int:
    api_key = os.environ.get("NOTTE_API_KEY")
    if not api_key:
        print("error: set NOTTE_API_KEY (get one at https://console.notte.cc)", file=sys.stderr)
        return 2

    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    function_id = sys.argv[1]
    try:
        variables = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
    except json.JSONDecodeError as exc:
        print(f"error: variables must be a JSON object ({exc})", file=sys.stderr)
        return 2

    try:
        result = run(function_id, variables, api_key)
    except HTTPError as exc:
        body = exc.read().decode(errors="replace")
        print(f"error: HTTP {exc.code} — {body}", file=sys.stderr)
        return 1

    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# The same job, three ways

Every other folder in `examples/` is the output of a local capture: a client
file you own, pinned to the site as it looked that day. This one is the
comparison — the same "get data out of a website" job done locally, done
hosted over HTTP, and done hosted from an agent.

Nothing here is a pitch for one of them. They fail differently, and which one
you want depends on who maintains the result.

## The three routes

| | Local (this repo) | Hosted over HTTP | Hosted over MCP |
|---|---|---|---|
| You get | a client file in your repo | a callable endpoint | a tool your agent can call |
| Setup | install the CLI, run a capture | an API key | one config line |
| Runs on | your machine | Anything's browsers | Anything's browsers |
| Site changes | you re-run the capture | re-engineered for you | re-engineered for you |
| Cost | your model tokens | per run | per run |
| Offline | yes | no | no |
| Code review | you read every line | you read the output | you read the output |

## 1. Local — reverse-engineer it yourself

```bash
reverse-api-engineer
> get NFL team standings for the current season
```

A browser opens, traffic is captured, and your model writes the client into
`./scripts/nfl_standings_api/`. See any of the sibling example folders for
what that output looks like in practice.

The client is MIT, yours, and runs anywhere. It also stops working the day
nfl.com changes its endpoints, and re-running the capture is on you.

## 2. Hosted over HTTP

First, find out whether the function already exists. The marketplace search
endpoint is public — no key, no account:

```bash
python discover.py nfl.com
```

```
5 function(s) for 'nfl.com':

  get_nfl_team_standings  [nfl.com] · 7 runs
    Returns NFL team standings from https://nfl.com for a selected season,
    season type, and week...
    https://anything.notte.cc/marketplace/365309fa-acb6-4226-b410-9a5f86fb72d9
```

`discover.py` passes the site straight through as `base_url`, which scopes
the search server-side. Any form works — a bare hostname, a full URL, or a
glob like `*.nfl.*` — and subdomains are covered. Add a query alongside it to
narrow further: the two filters compose.

Then run one. This part needs a key from
[console.notte.cc](https://console.notte.cc):

```bash
export NOTTE_API_KEY=...
python run_hosted.py <function_id> '{"season": 2025}'
```

Each function declares its own variables; the names and types are on that
function's marketplace page, which `discover.py` prints for every result.

## 3. Hosted over MCP

Point an MCP client at the endpoint and your agent searches the same catalogue
on its own — checking for an existing function before it builds anything:

```json
{
  "mcpServers": {
    "anything": {
      "url": "https://anything.notte.cc/mcp"
    }
  }
}
```

The server exposes `search` (public), plus `spec`, `run`, and `build` once
authenticated. `build` describes a task in plain English and deploys a new
function, which is the hosted equivalent of a capture run here.

## Which to use

Use the **local** route when the client belongs in your repo, when you need it
to run offline or inside your own network, when the site needs your logged-in
session, or when you want to read every line before it executes.

Use the **hosted** route when you want an endpoint rather than a file, when
you would rather not own the repair work each time the site shifts, or when an
agent needs to reach hundreds of sites without you building each one.

The [CLI ships with a marketplace lookup](../../README.md#hosted-version) for
exactly this reason: before a capture, it tells you if the site is already
covered, and enter carries on capturing anyway.

## Files

- `discover.py` — public marketplace search, runs with no credentials.
- `run_hosted.py` — execute one hosted function, needs `NOTTE_API_KEY`.

Both are dependency-free (standard library only) and target Python 3.11+.

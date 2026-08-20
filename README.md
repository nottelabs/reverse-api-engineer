<div align="center">
  <img src="https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/reverse-api-banner.png" alt="Reverse API Engineer Banner">
  <br><br>
  <a href="https://pypi.org/project/reverse-api-engineer/"><img src="https://img.shields.io/pypi/v/reverse-api-engineer?style=flat&color=e50d75&labelColor=1f1f1f" alt="PyPI"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-e50d75?style=flat&labelColor=1f1f1f" alt="Python"></a>
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-e50d75?style=flat&labelColor=1f1f1f" alt="License"></a>
  <a href="https://anything.notte.cc?utm_source=rae&utm_medium=readme&utm_campaign=badge"><img src="https://img.shields.io/badge/hosted-anything.notte.cc-e50d75?style=flat&labelColor=1f1f1f" alt="Anything API"></a>
  <br>

[![Greptile: The War on Bugs](https://www.greptile.com/badge.svg)](https://www.greptile.com/?utm_source=oss_badge&utm_medium=readme&utm_campaign=greptile_for_open_source)

</div>

# Reverse API Engineer

> **Turn websites into APIs.** Browse (or let an agent browse), and get a clean, typed client for the endpoints the site actually uses.

<p align="center">
  <img src="https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/rae-autoscout.gif" alt="Agent Mode Demo">
  <br>
  <em>Agent mode</em>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/kalil0321/reverse-api-engineer/main/assets/reverse-api-engineer.gif" alt="Manual Mode Demo">
  <br>
  <em>Manual mode</em>
</p>

---

## How it works

1. You give it a website and a goal ("fetch all Apple jobs").
2. A browser visits the site, either driven by you or by an AI agent.
3. Network traffic is captured to a HAR file.
4. Your configured model reads the traffic and writes a working API client in Python, JavaScript, TypeScript, Go, Java, C#, PHP, Ruby, or C.

No more manually opening DevTools, copying cURL commands, and gluing together a client.

## Hosted version

[**anything.notte.cc**](https://anything.notte.cc?utm_source=rae&utm_medium=readme&utm_campaign=hosted_section)
is the managed version of the same idea — *describe the task, we engineer the
skill*. You get back a deployed API function instead of a local file, with the
proxies, retries, and re-engineering-when-the-site-changes handled for you.

Two reasons to look there before capturing anything locally:

- **It may already exist.** The
  [marketplace](https://anything.notte.cc/marketplace?utm_source=rae&utm_medium=readme&utm_campaign=hosted_section)
  has 950+ ready-made functions across 400+ sites — job boards, retailers,
  social, finance, sports, public data. Browsing needs no account.
- **Your agent can call it directly.** Point any MCP client at
  `https://anything.notte.cc/mcp` and it searches that marketplace before it
  builds anything.

Reverse API Engineer stays what it is: local, MIT, no account required, and the
client it generates is yours to keep. Reach for the cloud when you'd rather not
own the maintenance.

Because a capture run costs time and tokens, agent mode checks the marketplace
for the target site first and tells you when something already exists — press
enter to carry on capturing anyway. The lookup is anonymous, needs no account,
and only ever reports functions whose own domain matches your target. Turn it
off with `RAE_NO_CLOUD=1` or **Cloud Suggestions** in `/settings`.

## Install

```bash
uv tool install reverse-api-engineer   # or: pip install reverse-api-engineer
```

Agent mode (the default) captures through `npx`-launched browser tooling —
browser MCP servers (Playwright or Chrome DevTools) or the Vercel `agent-browser`
CLI — and needs no extra Python packages. **Manual mode** drives a local
Playwright browser, which ships in the optional `[manual]` extra:

```bash
uv tool install "reverse-api-engineer[manual]"   # or: pip install "reverse-api-engineer[manual]"
playwright install chromium
```

## Quick start

```bash
reverse-api-engineer
> fetch all apple jobs from their careers page

# Browser opens. Navigate, interact, close when done.
# → ./scripts/apple_jobs_api/  (api_client.py, README.md, example_usage.py)
```

> Before you capture: someone may have already done it. Search the
> [Anything marketplace](https://anything.notte.cc/marketplace?utm_source=rae&utm_medium=readme&utm_campaign=quick_start)
> for your target site and skip straight to a hosted endpoint.

Cycle modes with **Shift+Tab**:

| Mode | What it does |
|------|--------------|
| `manual` | You drive the browser; AI generates the client from captured traffic. |
| `agent` | An AI agent drives capture autonomously (Playwright or Chrome MCP, or Vercel agent-browser CLI). |
| `engineer` | Re-run generation on a previous capture (`engineer <run_id>`). |
| `collector` | Agent collects structured data (JSON/CSV) using web search + fetch. |

Agent mode providers:
- **auto** (default): Playwright MCP, single workflow for browsing + reverse engineering.
- **chrome-mcp**: drives your real Chrome so you keep existing sessions/cookies. Requires Chrome 146+ and Node.js 20.19+.
- **agent-browser**: [Vercel agent-browser](https://github.com/vercel-labs/agent-browser) **CLI** (not a Reverse API Engineer browser MCP server). At session start RAE uses whatever `agent-browser` is already on `PATH`, otherwise runs **`npm install -g <pin>`** (same pin as config / `RAE_AGENT_BROWSER_PACKAGE`), prints a yellow notice, validates with **`--help`**, and only then falls back to **`npx -y <pin>`** if npm cannot install. Prompts embed the resolved shell prefix alongside **`skills get core --full`**, **`skills list`**, HAR phases, cloud notes from `agent_browser_notes`. Tune with `agent_browser_npx_package` (optional), env `RAE_AGENT_BROWSER_*`. First Chromium fetch: **`agent-browser install`** (add `--with-deps` on trimmed Linux).


Optional sanity checks:

```bash
agent-browser doctor --offline --quick || true
agent-browser skills list >/dev/null
```

## Configuration

Settings live in `~/.reverse-api/config.json` and can be edited via `/settings` in the CLI:

```json
{
  "agent_provider": "auto",
  "agent_browser_npx_package": "agent-browser@0",
  "agent_browser_notes": "",
  "claude_code_model": "claude-sonnet-4-6",
  "cloud_suggestions": true,
  "collector_model": "claude-sonnet-4-6",
  "ollama_auto_start": true,
  "ollama_base_url": "http://127.0.0.1:11434",
  "opencode_auto_start": true,
  "opencode_base_url": "http://127.0.0.1:4096",
  "opencode_model": "big-pickle",
  "opencode_npx_package": "opencode-ai@latest",
  "opencode_provider": "opencode",
  "copilot_model": "gpt-5",
  "cursor_model": "composer-2.5",
  "output_dir": null,
  "output_language": "python",
  "real_time_sync": true,
  "sdk": "claude"
}
```

- **Models**: Sonnet 4.6 (default), Opus 4.6 (most capable), Haiku 4.5 (fastest). For OpenCode see [models.dev](https://models.dev).
- **SDK**: `claude` (default), `opencode`, `cursor`, or `copilot` (GitHub Copilot).
- **OpenCode setup**: with `sdk: "opencode"`, RAE reuses an existing server or downloads/starts `opencode-ai@latest` through `npx`; a global OpenCode installation is not required. Fresh configurations default to the free `opencode/big-pickle` model. `/settings` shows a loading spinner, then offers a searchable **OpenCode Provider / Model** picker populated from the server's connected, tool-capable catalog and marks free OpenCode options. Before creating a session, RAE validates the saved pair again and suggests currently available free models when configuration is invalid. Compatible older servers are reused with a version warning. Node.js 20+ is required for automatic startup. Password-protected servers use `OPENCODE_SERVER_PASSWORD` and optional `OPENCODE_SERVER_USERNAME`. Override startup with `OPENCODE_BASE_URL`, `RAE_OPENCODE_PACKAGE`, or `RAE_OPENCODE_AUTO_START=0`.
- **Ollama through OpenCode**: choose provider `ollama` in `/settings`; RAE starts an installed Ollama daemon if needed, lists only installed models with tool calling and 64k+ context, and supplies OpenCode's provider config inline. Models are never downloaded silently. Override with `RAE_OLLAMA_BASE_URL` or `RAE_OLLAMA_AUTO_START=0`.
- **Output language**: `python`, `javascript`, `typescript`, `go`, `java`, `csharp`, `php`, `ruby`, or `c`. C needs a POSIX toolchain (`cc`, libcurl headers) — macOS/Linux, or WSL/MSYS2 on Windows.

## CLI

Slash commands inside the CLI:
- `/settings`: configure model, SDK, agent provider, and sync settings.
- `/history`: list past runs with timestamps, costs, and status.
- `/messages <run_id>`: view detailed message logs for a run.
- `/cloud`: show the hosted version and how to search its marketplace.
- `/help` (alias: `/commands`): show the command list.
- `/exit` (alias: `/quit`): leave the CLI.

Scriptable subcommands (pipe to `jq`):

```bash
reverse-api-engineer agent --prompt "capture the public jobs api" \
  --url https://example.com/jobs --json | jq

reverse-api-engineer list --json
reverse-api-engineer show <run_id> --json

# Check whether a hosted function already covers a site (public, no account).
reverse-api-engineer marketplace search --site https://www.nfl.com
reverse-api-engineer marketplace search --category Jobs
reverse-api-engineer marketplace search "nfl standings" --json | jq
reverse-api-engineer run <run_id> --file api_client.py \
  --no-interactive --auto-install -- --org acme
```

Pass `--no-interactive` (and/or `--json`) to skip prompts. With `--json`, stdout is one JSON document and logs go to stderr.

### `agent --json` schema

| Field            | Type                | Notes                                                                  |
|------------------|---------------------|------------------------------------------------------------------------|
| `schema_version` | `int`               | Currently `1`.                                                         |
| `status`         | `"ok"` \| `"error"` | Top-level result.                                                      |
| `run_id`         | `string` \| `null`  | Use with `show` / `engineer` / `run`.                                  |
| `prompt`         | `string`            |                                                                        |
| `url`            | `string` \| `null`  |                                                                        |
| `mode`           | `string` \| `null`  | `"auto"`, `"chrome-mcp"`, or `"agent-browser"`.                                        |
| `har_path`       | `string` \| `null`  | Captured HAR.                                                          |
| `script_path`    | `string` \| `null`  | Generated client.                                                      |
| `usage`          | `object`            | `{input_tokens, output_tokens, total_cost}`.                           |
| `error`          | `string` \| `null`  | When `status == "error"`.                                              |

### Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success. |
| `1` | Runtime error. |
| `2` | Missing required arg under `--no-interactive` / `--json`. |

For `run`, the exit code is the underlying script's return code on success, `1` if no script was found, or non-zero if `--no-interactive` would have had to prompt.

## Output locations

- `~/.reverse-api/runs/scripts/{run_id}/`: permanent storage
- `./scripts/{descriptive_name}/`: local copy with a readable name
- Collector: `./collected/{folder_name}/` (`items.json`, `items.csv`, `README.md`)

## Caveats

- Generated code runs locally via Claude Code, so review before executing.
- Sites with aggressive bot detection may block capture or require manual interaction.

## Development

```bash
git clone https://github.com/kalil0321/reverse-api-engineer.git
cd reverse-api-engineer
uv sync
uv run reverse-api-engineer
```

Build: `./scripts/clean_build.sh`. Requires Python 3.11+ and an API key for agent mode. Manual mode additionally needs the `[manual]` extra plus `playwright install chromium`.

## License

MIT. See [LICENSE](LICENSE).

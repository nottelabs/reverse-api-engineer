# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.13.1] - 2026-08-30

### Fixed
- **`ModuleNotFoundError: No module named 'httpx'` on a fresh install**: `httpx` was imported at module top level in five modules but never declared as a dependency. It had always arrived transitively through `mcp`, which required `httpx` up to 1.x. `mcp` 2.0 switched to `httpx2` and `claude-agent-sdk` relaxed its pin to `mcp<3`, so new installs stopped resolving `httpx` entirely and every CLI invocation died at import time, `--version` included. Environments created before `mcp` 2.0 kept working, which is why the break only appeared for new users. The package now uses `httpx2` (imported as `httpx`) and declares `httpx2>=2.5.0` explicitly, matching what `mcp` 2.x already pulls in rather than installing a second HTTP client alongside it. ([#122](https://github.com/kalil0321/reverse-api-engineer/issues/122))

## [0.13.0] - 2026-07-27

### Added
- **`client_executed` json-stream event**: a non-interactive `--json`/`--json-stream` run is a single SDK turn end-to-end, so `result` only fires once the whole turn is over — a caller watching the stream had no earlier way to know a working, live-verified client already existed, even when the agent spent a long tail of that turn on unrelated busywork. `--json-stream` now emits `{"event": "client_executed", "script_path": "..."}` as soon as the agent successfully runs the generated client with its own language-specific run command, giving wrapper scripts a signal they can bound cost and time against. Emitted for both `engineer` and `agent`; Claude SDK only (OpenCode/Copilot/Cursor have separate streaming handlers). See the [scripted usage docs](https://reverseapi.dev/docs/cli/scripted-usage).

### Changed
- **Slimmer source distribution**: the sdist no longer ships the repo's binary banner/demo assets, the `examples/` and `design/` trees, or `uv.lock` — none of which are needed to build, install, or test the package (README images are served from GitHub, not the tarball). The published `.tar.gz` drops from ~1.0 MB to ~0.2 MB. The wheel is unchanged.

## [0.12.0] - 2026-07-22

### Changed
- **Playwright is now an optional `[manual]` extra**: agent mode (the default) captures through `npx`-launched browser tooling (browser MCP servers or the `agent-browser` CLI) and never imports the Python Playwright package, so `playwright` and `playwright-stealth` moved out of the base dependencies into a `[manual]` optional-dependency group. This keeps the base install (and any runtime that bundles the package) lightweight. Manual capture mode now requires `pip install "reverse-api-engineer[manual]"` followed by `playwright install chromium`. Entering manual mode without the extra fails fast — before any run is recorded — with an actionable hint listing both steps, so a base-only install never leaves a phantom `manual` run in history.

### Fixed
- **Manual capture no longer wedges the REPL after a failed start**: if a capture failed to launch (for example a mistyped or scheme-less URL), Playwright's sync event loop was left running, so every subsequent prompt died in a loop with "asyncio.run() cannot be called from a running event loop". The browser is now torn down on a failed start, so the error is shown once and the prompt returns to normal.
- **Scheme-less capture URLs are accepted**: entering a bare host such as `jobs.example.com/x` is now treated as `https://jobs.example.com/x` instead of failing with an invalid-URL error.
- **CLI error text with brackets renders in full**: error messages are escaped before Rich renders them, so hints like `reverse-api-engineer[manual]` are no longer partially swallowed as markup.

## [0.11.0] - 2026-07-22

### Changed
- **OpenCode setup**: RAE now reuses an existing server or downloads/starts `opencode-ai@latest` through `npx` without requiring a global OpenCode install, with configurable auto-start, package, and base URL settings plus password inheritance. Fresh configurations default to free `opencode/big-pickle`. Provider/model pairs are validated before session creation, invalid configurations include current free-model suggestions, and older compatible servers show an upgrade warning. `/settings` shows a loading spinner, uses a live searchable provider/model picker, saves the pair atomically, and remains open across related changes until Back is selected.
- **Ollama setup**: OpenCode mode can discover tool-capable Ollama models, start an installed daemon, and inject provider configuration without modifying the user's `opencode.json`.

### Fixed
- **"Prompt is too long" session deadlock** (#93): Claude SDK sessions now run with proactive auto-compaction configured per the Claude Code docs — `CLAUDE_CODE_AUTO_COMPACT_WINDOW` (capped by the CLI to the model's real context window) plus `CLAUDE_AUTOCOMPACT_PCT_OVERRIDE=85` — leaving enough headroom that a max-size HAR read landing near the threshold no longer jumps straight past the hard context limit. Both variables are respected if the user sets them explicitly. When the window is exhausted anyway, the error is now explained (progress is saved on disk; start a new run for the same target to continue) and the follow-up prompt is no longer offered on the dead session, where every further message would fail with the same error.
- **OpenCode permissions**: Permission V2 events now reply through OpenCode's current, non-deprecated permission endpoint while retaining compatibility with older servers.
- **OpenCode errors**: Known authentication, model configuration, and temporary provider-availability failures now produce one actionable message without the unexpected-error issue prompt.
- **OpenCode TUI prompt echo**: Streamed text is now restricted to assistant message IDs, preventing RAE's internal browser and reverse-engineering instructions from appearing as model output.
- **`run`/`list` now work for every output language**: `discover_scripts()` previously only found `.py` files, so `reverse-api-engineer run <run_id>` failed with "No Python scripts found" for JS/TS/Go/Java/C#/PHP/Ruby/C clients. Discovery now covers all supported extensions (excluding build dirs and the vendored cJSON sources), and the run command dispatches to the right toolchain per language (compile+execute for C), with a clear error when the required tool isn't on PATH.
- **Windows-safe run-command quoting**: the Java/C#/PHP/Ruby/C run commands quoted paths with POSIX-only `shlex.quote`, which cmd.exe/PowerShell parse incorrectly for paths containing spaces. Paths are now quoted per-platform (`subprocess.list2cmdline` on Windows).

### Added
- **Go output language**: `output_language: "go"` is now supported alongside python/javascript/typescript, generating a standard-library-first (`net/http`, `encoding/json`) Go program, with the same auth-hardcoding/refresh and bot-detection-fallback guidance as the other languages.
- **Java output language**: `output_language: "java"` is now supported alongside python/javascript/typescript, generating a small Maven project using `java.net.http.HttpClient` (JDK 11+, no HTTP library dependency) and Gson for JSON, with the same auth-hardcoding/refresh guidance as the other languages.
- **C# output language**: `output_language: "csharp"` is now supported alongside python/javascript/typescript, generating a minimal .NET project using `System.Net.Http.HttpClient` and `System.Text.Json` (both part of the .NET 5+ base class library — no NuGet dependency needed), with the same auth-hardcoding/refresh guidance as the other languages.
- **PHP output language**: `output_language: "php"` is now supported alongside python/javascript/typescript, generating a script using the `curl` and `json_encode`/`json_decode` core extensions (`ext-curl`, `ext-json` — no Composer dependency needed), with the same auth-hardcoding/refresh guidance as the other languages.
- **Ruby output language**: `output_language: "ruby"` is now supported alongside python/javascript/typescript, generating a script using `net/http` and `json` (both part of Ruby's standard library — no gem/Bundler dependency needed), with the same auth-hardcoding/refresh guidance as the other languages.
- **C output language**: `output_language: "c"` is now supported alongside python/javascript/typescript, generating a program using `libcurl` for HTTP and a vendored `cJSON` for JSON (C has neither in its standard library), compiled and run as a single `{run_command}` step, with the same auth-hardcoding/refresh guidance as the other languages.

## [0.10.0] - 2026-06-01

### Changed
- **Packaging metadata**: Refreshed the package `description`, `keywords`, and `classifiers`, bumped `Development Status` to `4 - Beta`, and updated the project URLs (`Homepage` now points to https://reverseapi.dev, added `Documentation` and `Changelog`)
- **Source distribution excludes `website/`**: The marketing site under `website/` (Astro/Cloudflare Pages source) is now excluded from the sdist build so it no longer ships inside the PyPI package; the wheel already only packaged `src/reverse_api`

### Added

- **`agent_provider: "agent-browser"`**: Shell-driven **[Vercel agent-browser CLI](https://github.com/vercel-labs/agent-browser)**—RAE prefers an `agent-browser` binary on `PATH`, otherwise runs **`npm install -g <pin>`** (with a console notice), validates **`--help`**, and only then falls back to **`npx -y <pin>`** if npm cannot install. Prompts embed the resolved shell prefix plus **`skills get …` / `skills list`**, HAR flows, and optional `agent_browser_notes`. No bundled browser MCP shim; pin via `agent_browser_npx_package` / `RAE_AGENT_BROWSER_PACKAGE`.

### Added
- **Cursor SDK support**: Added `sdk=cursor` / `--sdk cursor` engineering support through a bundled Node bridge around the Cursor TypeScript SDK. Cursor runs use the configured Cursor model (default `composer-2`), accept MCP server configuration, resume Cursor agents across follow-up turns, and normalize streamed tool output plus token usage into the existing TUI/message-store flow
- **Cursor bridge packaging**: Bundled the `src/reverse_api/cursor_bridge/` Node package so `@cursor/sdk` dependencies can be installed on demand when Cursor mode is first used

### Fixed
- **Manual REPL model resolution**: Follow-up engineering now resolves model settings from the selected SDK, including Cursor, OpenCode, and Copilot
- **Cursor streaming**: Buffered Cursor model text before rendering so streamed deltas are shown as coherent blocks and no longer produce stray `..` lines or bridge hangs
- **Sync test compatibility**: Restored the temporary-file helper used by the existing sync test surface

### Removed
- **Chrome extension and native messaging host**: The `chrome-extension/` workspace and the Python `native_host` module are removed. The `install-host`, `uninstall-host`, and `run-host` CLI subcommands no longer exist. The extension was an experimental/WIP capture surface that never reached parity with `manual` and `agent` modes; deleting it also eliminates a JS dev-tooling supply chain (vite, postcss, picomatch, rollup, prismjs) and the corresponding dependabot churn

### Security
- **Drop `[pricing]` extra (litellm)**: LiteLLM 1.83.7 patched 3 advisories (1 critical SQLi + 2 high RCE/SSTI) but hard-pins `click==8.1.8`, which would force a click downgrade for all users. The vulnerable code paths are all in the LiteLLM proxy server, which we do not run — we only used litellm as a library for cost lookups. Removed the optional dependency entirely; `pricing.py` keeps a graceful import-detect path so users who install `litellm` independently still get the extended model coverage
- **cryptography** `>=46.0.7` (was `>=46.0.6`) — patches a buffer overflow on non-contiguous buffer inputs (medium)
- **pytest** `>=9.0.3` (was `>=8.0.0`) — patches vulnerable `tmpdir` handling (medium, dev only)
- **python-multipart** `>=0.0.27` (was 0.0.22 transitively via `mcp`) — patches DoS via large multipart preamble/epilogue (medium)

## [0.8.0] - 2026-05-06

### Added
- **Agent-friendly CLI surface**: First-class non-interactive mode for invocation from other agents and scripts
  - **`--json`** on `agent` and `engineer`: emit a single structured JSON result (run_id, status, artifacts, usage, error info) instead of streaming TUI output. Auto-suppresses follow-up prompts and TTY-detects at REPL entry
  - **`--no-interactive`** on `engineer`: skip the follow-up loop without forcing JSON output
  - **`agent --dry-run`**: pre-flight validation (config, network, MCP availability) without launching a browser
  - **`agent --headless`**: run agent mode without a visible browser window (manual mode keeps the human-in-the-loop and does not accept `--headless`)
  - **`--json-schema-version`**: explicit version string (`v2`) on JSON output so callers can pin their parser
  - **Stable usage normalization** and **`error_kind` enum**: machine-readable error categories and consistent token/cost shapes across SDKs
- **`engineer --prompt`** and **`engineer --fresh`** CLI flags: replace the equivalent `@id <run_id> [--fresh] <prompt>` REPL syntax. With `--fresh`, `--prompt` fully replaces the captured run's goal; without `--fresh`, it layers additional instructions on top
- **`--help` epilogs**: expanded help output with examples for every subcommand

### Changed
- **Prompts**: extracted to standalone markdown templates under `src/reverse_api/prompts/` for easier review and iteration; LLM guidelines tightened
- **Banner**: replaced the SVG banner with a new painted-ruins JPG

### Removed
- **`browser-use` and `stagehand` agent providers**: Both retired due to upstream churn. Agent mode now offers only `auto` (Playwright MCP) and `chrome-mcp` (Chrome DevTools MCP). Configs with `agent_provider` set to `browser-use` or `stagehand` migrate to `auto`; the `browser_use_model` and `stagehand_model` keys are dropped silently. The `[agent]` optional-dependency extra is removed
- **Tag system (`@record-only`, `@codegen`, `@id`, `@docs`, `@help`)**: The inline tag syntax inside REPL prompts has been removed. Surviving capabilities have first-class CLI flags / arguments instead:
  - `@record-only` → `manual --no-engineer` (already existed)
  - `@id <run_id>` → `engineer <run_id>` (positional, already existed)
  - `@id <run_id> <prompt>` → `engineer <run_id> --prompt "..."`
  - `@id <run_id> --fresh <prompt>` → `engineer <run_id> --fresh --prompt "..."`
  - `@codegen` and Playwright-action recording: removed entirely with the `ActionRecorder` and `playwright_codegen` modules (low usage, replaced by the standard capture+engineer flow)
  - `@docs` (OpenAPI generation): removed for now; will return as a dedicated `docs` subcommand in a follow-up
  - `@help`: superseded by the existing `/help` slash command in the REPL
- **`--reverse-engineer/--no-engineer` flag on `agent`**: was parsed but never propagated to the auto-capture path — removed. Agent mode runs an integrated capture + engineering pipeline; use `manual --no-engineer` for HAR-only recordings

### Fixed
- **`engineer --json`**: emits JSON even when `RUN_ID` is missing (previously fell through to TUI error)
- **Follow-up prompt**: suppressed in `--json` / `--no-interactive` mode so non-interactive callers never block on stdin

## [0.7.1] - 2026-04-06

### Fixed
- **Packaging**: Exclude `.claude/worktrees/`, `.claude/plans/`, and demo GIFs from sdist (29MB → 503KB)

## [0.7.0] - 2026-04-06

### Added
- **`run` command**: Execute generated scripts directly from the CLI with `reverse-api-engineer run <id|name>`. Supports fuzzy name matching, `--ls` to list scripts, `--file` to pick a specific script, and `--` to pass arguments through to the script
- **Shared venv**: Scripts run inside a shared venv at `~/.reverse-api/runs/.venv` with `requests` pre-installed. Per-run `requirements.txt` is installed on top automatically
- **Auto-install missing imports**: When a script fails with `ModuleNotFoundError`, offers to install the missing package and retry

### Security
- **litellm** >=1.83.0 — fixes critical OIDC auth bypass + high privilege escalation
- **requests** >=2.33.0 — fixes insecure temp file reuse
- **aiohttp** >=3.13.4 — fixes header injection, SSRF, DoS vulnerabilities
- **pygments** >=2.20.0 — fixes ReDoS
- **cryptography** >=46.0.6 — fixes incomplete DNS constraint enforcement

## [0.6.0] - 2026-04-01

### Added
- **Chrome DevTools MCP agent provider (`chrome-mcp`)**: Agent mode can drive the browser through [Chrome DevTools MCP](https://www.npmjs.com/package/chrome-devtools-mcp) (`--autoConnect`, optional `--no-usage-statistics`) with a dedicated system prompt and SDK wiring alongside the existing Playwright MCP path

### Changed
- **Agent provider selection**: CLI settings and mode flow distinguish **auto (Playwright MCP)** from **chrome-mcp (Chrome DevTools MCP)**
- **Packaging**: Source distributions exclude local demo video, packed Chrome extension zip, store-asset screenshots, and per-machine `.claude/settings.local.json` files so PyPI artifacts stay small (wheel unchanged: `src/reverse_api` only)

### Fixed
- **Tool result blocks** (engineer / agent streaming): When `content` is empty, fall back to `result` or `output` on tool-result blocks so alternate SDK shapes still surface output in the UI and message store
- **Process title**: Set when the CLI module loads so the terminal shows `reverse-api` earlier in startup
- **Follow-up prompt**: Flush local sync before reading follow-up input so state is up to date
- **Tests**: `ClaudeAutoEngineer` analyze tests now use real `claude_agent_sdk` message types (so `isinstance` checks in the streaming loop match) and stub `_prompt_follow_up` to avoid the interactive follow-up path

### Documentation
- **README**: Agent mode demo GIF

## [0.5.0] - 2026-03-17

### Added
- **Follow-up chat**: After a run completes, type follow-up messages to iterate in the same session without creating new run IDs or folders. Press Enter to finish
- **Abort run (Ctrl+C)**: Gracefully cancel a running agent/engineer session and return to the REPL instead of exiting the app
- **AskUserQuestion free mode**: All select/checkbox prompts now include "Other (type your answer)" so users can always provide free-text input. Updated agent prompt to document free-form, multi-select, and multi-question capabilities
- **Random task suggestions (Ctrl+R)**: Press Ctrl+R in agent mode to fill the prompt with a random curated task idea. Press again to cycle

### Fixed
- **Usage tracking across follow-ups**: Token counts now accumulate across all turns in a session instead of being overwritten by the last turn
- **Agent mode follow-up**: Auto engineer (agent mode) was using a copy-pasted streaming loop without follow-up support; now reuses the shared conversation loop

## [0.4.5] - 2026-03-15

### Fixed
- **Stream closed errors (#51)**: Reverted from `query()` to `ClaudeSDKClient` which maintains a persistent bidirectional connection, eliminating "Error in hook callback hook_0: Stream closed" errors. The original AUQ fix (v0.4.3) unnecessarily switched APIs — only the `can_use_tool` callback signature needed updating
- **CLAUDECODE env var leak**: Clear inherited `CLAUDECODE` env var from CLI subprocess to prevent nested session interference when running inside Claude Code
- **CLI stderr noise**: Filter minified JS stack traces into a single clean error line (use `DEBUG=1` for full output)

### Changed
- **claude-agent-sdk**: Bumped minimum version to 0.1.48
- **Agent mode**: No longer prompts for URL (agent navigates autonomously)
- **Header UI**: Version and task labels now use mode-specific colors (agent=coral, engineer=blue, collector=gold)

## [0.4.4] - 2026-03-15

### Fixed
- **Stream closed errors (#51)**: Partial fix using `query()` with env var workarounds (superseded by v0.4.5)

## [0.4.3] - 2026-03-12

### Fixed
- **AskUserQuestion interactive prompt**: Fixed interactive questionary UI not rendering in engineer and agent modes. Switched from `ClaudeSDKClient` to `query()` function, as `ClaudeSDKClient` silently auto-approves `AskUserQuestion` without triggering the `can_use_tool` callback

## [0.4.2] - 2026-03-12

### Fixed
- **Engineer client resolution**: Prefer the active engineer client recorded in session history over config defaults, preventing iterative edits from switching to the wrong file when multiple language clients exist

## [0.4.1] - 2026-03-12

### Added
- **`show` CLI subcommand**: View details of a specific run by ID
- **Chrome Extension improvements**: Multi-session support, codegen recording, side panel UX overhaul
  - Session isolation fixes to prevent capture data bleeding across sessions
  - Message persistence across panel reloads and session switches
  - Traffic list with expandable request details and clear button
  - Restricted page detection with user feedback
  - ANSI escape code stripping in terminal output
  - PrismLight language fallback for unregistered languages
  - Bundle size reduced from 1112KB to 436KB (removed shiki, lucide-react, ansi-to-react, @base-ui/react)
- **Mintlify API client example**

### Changed
- **Background update check**: Version check now runs in a background thread to avoid blocking CLI startup

### Fixed
- **Engineer language preservation**: Iterative edits now preserve the original output language instead of resetting
- **Native host Gatekeeper handling**: Scoped xattr to the actual claude-code package directory
- **Codegen selector escaping**: Dynamic attribute values now escaped with CSS.escape() to prevent broken selectors
- **Chrome Extension manifest**: Removed unused `scripting` permission; pinned devicon CDN to v2.16.0

## [0.4.0] - 2026-03-10

### Added
- **`list` CLI subcommand**: Non-interactive command to list generated scripts and runs
  - Rich table output (compact and full modes) and JSON output (`--json`)
  - Filter by mode (`--mode`), model (`--model`), prompt search (`--search`), and limit (`--limit`)
  - Shows script directory paths, file counts, and local path detection

## [0.3.3] - 2026-03-10

### Added
- **GitHub Copilot SDK**: Third SDK option for reverse engineering using GitHub Copilot
  - New `CopilotEngineer` for HAR analysis via Copilot subscription (cost: $0)
  - Auto mode support with MCP browser integration via Copilot SDK
  - Interactive `AskUserQuestion` tool support for Copilot sessions
  - Permission handler and tool use hooks for agent visibility
  - Install with: `pip install 'reverse-api-engineer[copilot]'`
- **Comprehensive Test Suite**: 593 tests achieving 97.4% code coverage

### Changed
- **Claude Model Updates**: Updated from Claude 4.5 to Claude 4.6 (Opus and Sonnet)
- **Sync Filtering**: Unified sync filtering logic with relative paths; excludes `node_modules`
- **TUI Improvements**: Reduced thinking truncation for better agent visibility

### Fixed
- **Python 3.11 Compatibility**: Fixed multi-line f-string expressions that required Python 3.12+
- **Thread Safety**: Used `loop.call_soon_threadsafe` for Copilot SDK event callbacks
- **Session Timeouts**: Added 10-minute timeout protection for Copilot session completion
- **Resource Cleanup**: Ensured `CopilotClient` is always stopped via `try/finally`
- **HAR Recording**: Changed HAR recording content mode to embed and optimized file saving

## [0.3.2] - 2026-01-15

### Added
- **Update Notifications**: CLI now checks for newer versions on startup and displays update prompt

### Changed
- **README Improvements**: Redesigned badge styling with flat-square style and centered layout
- **Banner Redesign**: Modernized SVG banner with centered content and improved visual hierarchy
- **Font Compatibility**: Fixed banner fonts for better GitHub rendering support

### Fixed
- **Banner Display**: Corrected package name display and font rendering in GitHub

## [0.3.1] - 2026-01-15

### Added
- **Chrome Extension (WIP)**: Beta support for capturing browser traffic via Chrome extension
  - Alternative to Playwright browser for HAR capture
  - Works with existing browser sessions
  - Note: This feature is work in progress and may have limitations

### Fixed
- **OpenCode Server**: Fixed error formatting and connection handling
- **Process Title**: Added process title for better identification in system monitors
- **Auth Error Handling**: Improved handling of authentication failures

## [0.3.0] - 2026-01-10

### Added
- **Collector Mode**: New AI-powered web data collection mode using Claude Agent SDK
  - Natural language prompts to collect structured data from any website
  - Automatic export to JSON and CSV formats
  - Generates README with collection metadata and schema
  - Uses WebFetch, WebSearch, and file tools for autonomous collection
- **Playwright Codegen**: Generate automation scripts from recorded browser actions
  - Captures clicks, fills, key presses, and navigations
  - Produces stealth-enabled Playwright scripts with proper escaping
  - Deduplicates redundant fill actions and navigations
- **@docs Tag**: Generate OpenAPI specifications from HAR files
  - Standalone usage: `@docs` to generate from latest run
  - With run ID: `@docs run_id` to generate from specific run
- **@record-only Tag**: Record HAR files without reverse engineering step
- **AskUserQuestion Tool**: Interactive prompts during engineering sessions
- **JS/TS Client Generation**: Support for generating JavaScript/TypeScript API clients

### Changed
- **Improved HAR Filtering**: Better path-based filtering for skip patterns
- **Enhanced Price Computation**: Fixed pricing for OpenCode provider
- **Centralized Run Resolution**: Refactored latest run parsing logic

### Fixed
- **Selector Escaping**: Fixed attribute selector escaping for special characters in `name`, `data-testid`, `aria-label`, and `placeholder` values
- **Null Checks in Codegen**: Added validation for `action.selector` and `action.value` to prevent crashes
- **CSV Export**: Fixed DictWriter error when items have inconsistent keys
- **HAR Validation**: Validate HAR file exists when using @docs tag
- **Path Normalization**: Fixed path handling in various utilities

## [0.2.10] - 2026-01-03

### Added
- **Claude Code Plugin**: Official plugin for seamless integration with Claude Code CLI
  - Three operation modes: manual browser capture, autonomous agent browsing, and re-engineering from HAR files
  - Comprehensive skill system with progressive disclosure of reverse engineering techniques
  - Slash commands for quick access: `/agent`, `/engineer`, `/manual`
  - Reference documentation for HAR analysis and authentication patterns
  - API client templates for common patterns
- **Example API Clients**: Added production-ready examples for major platforms
  - Apple Jobs API client with field extraction utilities
  - Ashby Jobs API client with comprehensive endpoint coverage
  - Ikea API client for product search and catalog browsing
  - Uber Careers API client with pagination support
- **Engineer Tagging System**: Enhanced metadata tracking for generated API clients
  - Automatic tagging of runs with descriptive identifiers
  - Improved organization and searchability of reverse-engineered APIs

### Changed
- **Enhanced Auto Mode**: Improved MCP browser integration with better error handling
- **Better Sync Fallback**: More robust file synchronization with fallback mechanisms
- **Code Quality**: Comprehensive formatting and linting improvements across codebase

### Fixed
- **Agent Mode Screenshots**: Reduced unnecessary screenshot captures in agent mode
- **Sync Error Handling**: Fixed sync fallback when primary sync method fails
- **Path Handling**: Corrected CLAUDE.md documentation paths
- **Import Errors**: Fixed missing imports in various modules

## [0.2.9] - 2025-12-30

### Added
- **Real-time File Sync**: Watch and automatically sync generated scripts to local directory
  - Debounced file watching with configurable delay (default 500ms)
  - Visual feedback for sync operations in terminal UI
  - Prevents overwriting existing directories by appending counter suffix
- **MCP Browser Integration**: Native integration with `rae-playwright-mcp` for auto mode
  - Seamless browser automation via Model Context Protocol
  - Works with both Claude SDK and OpenCode SDK
  - Combines browser control and real-time reverse engineering in single workflow
- **CLAUDE.md Autogeneration**: Automatic generation of project documentation for Claude Code

### Changed
- **Enhanced Settings Management**: Improved settings configuration and UI
- **Better Sync Error Handling**: Improved error handling and resource cleanup for sync operations

### Fixed
- **Sync Directory Overwrite**: Fixed issue where sync would overwrite existing directories
- **Sync Resource Leaks**: Fixed memory leaks when sync errors occurred
- **UI Improvements**: Various UI fixes and enhancements

## [0.2.8] - 2025-12-28

### Added
- **3-Tier Pricing Fallback System**: Automatic pricing lookup for 100+ LLM models
  - Local pricing for common models (highest priority)
  - Optional LiteLLM integration for extended coverage (install with `pip install 'reverse-api-engineer[pricing]'`)
  - Default fallback to Claude Sonnet 4.5 pricing
- **New Model Pricing**: Added pricing for Gemini 3 and Claude thinking series models

### Changed
- **Enhanced OpenCode Prompts**: Improved prompt handling for code generation
- **Better Folder Naming**: Folder name generation with OpenCode SDK
- **Antigravity Documentation**: Added comprehensive documentation for free models via Antigravity

### Fixed
- Model name mismatch in pricing lookups
- Pricing computation for extended thinking models

## [0.2.7] - 2025-12-27

### Changed
- **Version management**: Implemented single source of truth for versioning
  - Version now defined only in `pyproject.toml`
  - `__init__.py` reads version dynamically using `importlib.metadata`
  - Eliminates need to manually update version in multiple files
  - Added `RELEASING.md` with release process documentation

## [0.2.6] - 2025-12-27

### Fixed
- **Version flag**: Updated `__version__` to 0.2.6 to ensure `--version` displays correctly
- **OpenCodeEngineer initialization**: Refactored to properly pop specific kwargs (`opencode_provider` and `opencode_model`) before passing to parent class
  - Ensures only relevant arguments are sent to BaseEngineer
  - Improves initialization logic clarity and prevents unintended argument passing

### Changed
- **README improvements**: Added table of contents and removed repetitive sections for better readability

## [0.2.5] - 2025-12-27

### Fixed
- Initial release attempt (superseded by 0.2.6 due to missing version flag update)

## [0.2.4] - 2025-12-27

### Fixed
- **Version string**: Fixed `--version` flag to correctly display 0.2.4 instead of outdated 0.2.0
  - Previous release (0.2.3) was built with stale bytecode cache
  - Added clean build script (`scripts/clean_build.sh`) to prevent future stale builds

## [0.2.3] - 2025-12-27

### Changed
- **Version display**: Fix hardcoded version display
- **Logs display**: Remove agent logs, claude agent sdk logs
- **Browser-use installation**: Better instructions on how to install bu for agent mode

## [0.2.2] - 2025-12-26

### Changed
- **Better HAR Recording**: Improved HAR file recording and capture functionality

## [0.2.1] - 2025-12-26

### Added
- **Stagehand Agent Support**: Added Stagehand as an alternative agent provider alongside browser-use
  - Supports OpenAI Computer Use models (e.g., `computer-use-preview-2025-03-11`)
  - Supports Anthropic Computer Use models (e.g., `claude-sonnet-4-5-20250929`, `claude-haiku-4-5-20251001`, `claude-opus-4-5-20251101`)
- **Separate Model Configurations**: Enhanced settings system with independent model configurations
  - `claude_code_model`: Model for Claude SDK (renamed from `model`)
  - `opencode_provider`: Provider for OpenCode SDK (e.g., "anthropic", "openai", "google")
  - `opencode_model`: Model for OpenCode SDK
  - `browser_use_model`: Model for browser-use agent provider
  - `stagehand_model`: Model for stagehand agent provider

### Changed
- **Improved Settings Management**: Separated model configurations for different SDKs and agent providers
  - Each SDK and agent provider now has its own independent model setting
  - Settings menu updated with clearer options for each component
- **Better Configuration Isolation**: OpenCode model settings no longer interfere with Claude SDK settings
- **Backward Compatibility**: Automatic migration of old config files to new structure

### Fixed
- Fixed issue where OpenCode model settings were being overridden by Claude SDK model settings
- Fixed model configuration conflicts between different SDKs and agent providers

## [0.2.0] - 2025-12-25

### Added
- **OpenCode SDK Support**: Native integration with OpenCode SDK for more flexibility in reverse engineering workflows
- **Agent Mode**: Fully automated browser interaction using AI agents (browser-use) with support for multiple LLM providers
  - Browser-Use LLM (default)
  - OpenAI models (gpt-4, gpt-3.5-turbo, etc.)
  - Google models (gemini-pro, gemini-1.5-pro, etc.)
- **Multi-Provider Agent Support**: Configure agent models via settings with automatic API key detection

### Changed
- Improved UX with better CLI interactions and mode cycling
- Enhanced settings management for model, agent model, SDK, and output directory configuration
- Better error handling and user feedback throughout the application

## [0.1.0] - 2025-12-22

### Added
- Initial release
- Browser automation with Playwright and stealth mode
- HAR recording and capture
- AI-powered API client generation using Claude
- Interactive CLI with manual and engineer modes
- Session history and cost tracking
- Production-ready code generation with type hints and documentation

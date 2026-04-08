# 🎙️ Read AI CLI

A command-line interface for [Read AI](https://read.ai) meeting notetaker. Access transcripts, summaries, action items, topics, metrics, and more — all from your terminal.

Wraps [Read AI's REST API](https://api.read.ai) with OAuth 2.1 authentication and automatic token refresh.

## Installation

### Human

**One-liner (recommended):**

```bash
curl -fsSL https://raw.githubusercontent.com/WorldInnovationsDepartment/read-ai-cli/main/install.sh | bash
```

This creates an isolated venv at `~/.venvs/read-ai` and prints an alias command to add to your shell config.

**Manual install into venv:**

```bash
python3 -m venv ~/.venvs/read-ai
~/.venvs/read-ai/bin/pip install git+https://github.com/WorldInnovationsDepartment/read-ai-cli.git
```

Then add the alias to avoid activating the venv each time:

```bash
echo 'alias readai="~/.venvs/read-ai/bin/readai"' >> ~/.bashrc  # or ~/.zshrc
source ~/.bashrc
```

**Direct install (no venv):**

```bash
pip install git+https://github.com/WorldInnovationsDepartment/read-ai-cli.git
```

Requires Python 3.10+.

### AI Agent

This CLI ships with a skill definition at [`skills/read-ai/SKILL.md`](skills/read-ai/SKILL.md) for AI agent integration (e.g. [Hermes](https://hermes-agent.nousresearch.com/#)).

To install, point your agent's `external_dirs` at this repo's `skills/` directory, or add the repo as a git submodule. The skill describes when and how to use each CLI command, API details, pitfalls, and common workflows.

## Features

- **List meetings** with date/duration filtering
- **Full transcripts** with speaker attribution (chronologically sorted)
- **AI summaries** including chapter-by-chapter breakdowns
- **Action items** with assignees and status
- **Topics & key questions** extracted from meetings
- **Meeting metrics** — Read Score, sentiment, engagement
- **Search** meetings by title
- **Export** to Markdown or JSON
- **Auto token refresh** — access tokens expire every 10 minutes, CLI handles it transparently
- **JSON output** for every command (`--json` flag) for scripting/piping

## Quick Start

### 1. Authenticate

```bash
readai auth
```

This will:
1. Register an OAuth client with Read AI (first time only)
2. Print a URL — open it in your browser
3. Complete the OAuth flow, click "Copy Command"
4. Paste the curl command back into the terminal

Tokens are saved to `~/.config/readai/tokens.json` (override with `READAI_TOKEN_FILE` env var).

### 2. List Recent Meetings

```bash
readai meetings
readai meetings --days 7 --limit 10
```

### 3. Get Meeting Details

```bash
readai get <MEETING_ID>
readai transcript <MEETING_ID>
readai summary <MEETING_ID>
readai actions <MEETING_ID>
```

## Command Reference

| Command | Aliases | Description |
|---------|---------|-------------|
| `readai auth [--register]` | | Authenticate with Read AI |
| `readai meetings [--days N] [--limit N] [--json]` | `list`, `ls` | List recent meetings |
| `readai get <ID> [--expand ...] [--json]` | | Get meeting details |
| `readai transcript <ID> [--json]` | `t` | Get full transcript |
| `readai summary <ID> [--json]` | `s` | Get summary + chapters |
| `readai actions <ID> [--json]` | `a` | Get action items |
| `readai topics <ID> [--json]` | | Get topics discussed |
| `readai questions <ID> [--json]` | `q` | Get key questions |
| `readai metrics <ID> [--json]` | `m` | Get meeting metrics |
| `readai search <query> [--days N] [--limit N] [--json]` | | Search by title |
| `readai export <ID> [--format md\|json] [--output FILE]` | `e` | Export meeting |
| `readai token-test` | | Test token validity |

### Expand Fields

When using `readai get`, you can specify which fields to expand:

```bash
readai get <ID> --expand summary transcript action_items metrics
```

Available fields: `summary`, `chapter_summaries`, `action_items`, `key_questions`, `topics`, `transcript`, `metrics`, `recording_download`

Default expand: `summary`, `action_items`, `metrics`

## API Details

- **Base URL:** `https://api.read.ai`
- **Auth:** OAuth 2.1 with PKCE, dynamic client registration
- **Token URL:** `https://authn.read.ai/oauth2/token`
- **MCP Server:** `https://api.read.ai/mcp` (same data via MCP protocol)
- **Pagination:** Cursor-based, max 10 per request (CLI auto-paginates)
- **Token lifetime:** Access tokens expire every 10 minutes; refresh tokens rotate on each use

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/meetings` | List meetings (cursor-paginated, time-filtered) |
| GET | `/v1/meetings/{id}` | Get meeting with expandable fields |
| GET | `/v1/meetings/{id}/live` | Live meeting data (requires dashboard open) |

### Time Filters

Use epoch milliseconds:
- `start_time_ms.gt` / `.gte` — after/at-or-after
- `start_time_ms.lt` / `.lte` — before/at-or-before

### Important Notes

- **Refresh token rotation:** Each refresh invalidates the old token. Never run two CLI instances simultaneously.
- **No server-side search:** `search` command fetches meetings and filters client-side by title.
- **Transcript format:** API returns `{speakers, turns}` with turns in **reverse** chronological order. The CLI normalizes this.
- **`expand[]` format:** Must use repeated keys (`expand[]=summary&expand[]=transcript`). Indexed keys don't work.
- **PKCE required:** Always use the full curl command from the OAuth UI "Copy Command" button.

## Read AI MCP Server

Read AI also provides an MCP (Model Context Protocol) server at `https://api.read.ai/mcp` with two tools:
- **Get Meeting by ID** — same as `readai get`
- **List Meetings** — same as `readai meetings`

See [Read AI API docs](https://support.read.ai/hc/en-us/articles/49381161088659) for details.

## License

MIT — see [LICENSE](LICENSE).

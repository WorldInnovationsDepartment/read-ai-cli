---
name: read-ai
description: Read AI meeting notetaker — list meetings, fetch transcripts, summaries, action items, topics, metrics via REST API
type: skill
version: 2.1.0
metadata:
  hermes:
    tags:
      - meetings
      - notetaker
      - productivity
    category: business
---

# Read AI — Meeting Notetaker CLI

Access Read AI meeting data: transcripts, summaries, action items, topics, metrics.

## When to Use

- User asks about meeting notes, transcripts, or action items
- "What was discussed in yesterday's meeting?"
- "Get the transcript from the standup"
- "List recent meetings"
- "Export meeting notes"
- "What action items came out of [meeting]?"
- "What was the sentiment/engagement score?"
- "What topics were discussed?"

## Prerequisites

- **Auth:** OAuth 2.1 tokens stored in `~/.config/readai/tokens.json` (override with `READAI_TOKEN_FILE` env var)
- **First-time setup:** Run `readai auth` — opens OAuth UI in browser, user pastes back the curl command from the success page
- **PKCE required:** OAuth flow uses PKCE. The `auth` command parses the full curl command (which includes `code_verifier`) — do NOT try to manually enter auth code separately
- **Dependency:** `pip install requests` (usually already installed)
- **Workspace setting:** "Downloads" option must be enabled in Read AI workspace settings under Reports & Sharing

## CLI Reference

Command: `readai` (installed globally via pip)

### Commands

```bash
# List recent meetings (last 30 days)
readai meetings
readai meetings --days 7 --limit 10
readai meetings --json    # raw JSON output

# Get meeting details by ID (ULID)
readai get <MEETING_ID>
readai get <MEETING_ID> --expand transcript summary action_items metrics
readai get <MEETING_ID> --json

# Get full transcript
readai transcript <MEETING_ID>
readai transcript <MEETING_ID> --json

# Get summary + chapter summaries
readai summary <MEETING_ID>

# Get action items only
readai actions <MEETING_ID>

# Get topics discussed
readai topics <MEETING_ID>

# Get key questions from meeting
readai questions <MEETING_ID>

# Get meeting metrics (read_score, sentiment, engagement)
readai metrics <MEETING_ID>

# Search meetings by title (client-side filter)
readai search "standup" --days 14

# Export meeting to markdown or JSON file (includes all data)
readai export <MEETING_ID> --format md --output meeting.md
readai export <MEETING_ID> --format json --output meeting.json

# Test token validity
readai token-test
```

## API Details

- **Base URL:** `https://api.read.ai`
- **Auth:** OAuth 2.1 (Authorization Code + refresh tokens)
- **MCP endpoint:** `https://api.read.ai/mcp` (same data, MCP protocol — 2 tools: Get Meeting by ID, List Meetings)
- **Token refresh:** Access tokens expire every 10 minutes; CLI auto-refreshes
- **Refresh token rotation:** Each refresh returns a NEW refresh token — old one invalidated
- **API status:** Open beta — endpoints may change
- **Public REST API is read-only for meetings:** official docs list only `GET /v1/meetings`, `GET /v1/meetings/{id}`, and `GET /v1/meetings/{id}/live`. No documented REST endpoint creates public/share links or modifies report sharing.
- **Report sharing is app/internal, not OAuth REST:** the web app uses internal session ACL routes (`/sessions/{id}/acl`) with browser session cookies, not the OAuth `meeting:read` token. UI-derived payload for link access is `PATCH /sessions/{id}/acl` with `{"generalAccess":{"accessPattern":"anyone","accessLevel":"viewer_full","readaiAccountRequired":false}}`; restricted access is `accessPattern:"people_with_access"`. Do not run this blindly — it requires owner/editor browser auth and changes report visibility.

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/v1/meetings` | List meetings (cursor-paginated, time-filtered) |
| GET | `/v1/meetings/{id}` | Get specific meeting (with expand params) |
| GET | `/v1/meetings/{id}/live` | Get live meeting data (requires live dashboard open) |

### Pagination (cursor-based)

- `limit` — max 10 per request (API hard limit)
- `cursor` — ID of last meeting from previous page
- `has_more` — boolean, continue until false
- The CLI auto-paginates to fetch requested number of results

### Time Filters (epoch milliseconds)

- `start_time_ms.gt` / `.gte` — after/at-or-after timestamp
- `start_time_ms.lt` / `.lte` — before/at-or-before timestamp

### Expandable Fields (`expand[]`)

| Field | Description |
|-------|-------------|
| `summary` | AI-generated meeting summary |
| `chapter_summaries` | Per-chapter/topic summaries |
| `action_items` | Extracted action items with assignees |
| `key_questions` | Key questions raised in meeting |
| `topics` | Topics discussed |
| `transcript` | Full transcript with speaker attribution |
| `metrics` | read_score, sentiment, engagement (0-1 scale) |
| `recording_download` | Recording download URL |

### Response Fields (per meeting)

`id`, `start_time_ms`, `end_time_ms`, `scheduled_start_time_ms`, `scheduled_end_time_ms`, `participants` (name, email, invited, attended), `owner`, `title`, `report_url`, `platform`, `platform_id`, `folders`, `live_enabled`

### Meeting States

- **Active:** In progress (`end_time_ms` is null)
- **Completed:** Finished and processed
- **Processing:** Ended, still being processed (expanded fields may be empty)

## Common Workflows

### 1. Quick meeting recap
```
readai meetings --days 1  →  find meeting ID  →  readai get <ID>
```

### 2. Extract action items from today's standup
```
readai search "standup" --days 1  →  readai actions <ID>
```

### 3. Check meeting quality metrics
```
readai metrics <ID>
```

### 4. Export full meeting for Confluence/Slack
```
readai export <ID> --format md --output /tmp/meeting.md
```
Then convert to PDF/DOCX and deliver.

### 5. Get all data at once
```
readai get <ID> --expand summary chapter_summaries action_items key_questions topics transcript metrics
```

### 6. Bulk process audit across many meetings

For requests like “read all meetings from the last 2 months and describe company processes”, use the packaged workflow in `references/bulk-process-audit.md`: bulk-list meetings with a high `--limit`, sequentially expand each meeting, build a digest, split analysis by process domains, then synthesize a concise report.

### 7. Export all available transcripts for a company corpus

For semantic-core / knowledge-graph datasets, first list meetings with:

```bash
readai meetings --days 3650 --limit 10000 --json
```

Then sequentially fetch each meeting (avoid parallel runs because refresh-token rotation can race):

```bash
readai get <MEETING_ID> --expand summary chapter_summaries action_items key_questions topics transcript metrics --json
```

Normalize transcript dicts by mapping `speakers[]` to `turns[]`; turns can be reverse chronological, so sort by start timestamp if available. For full cross-source YTC corpus exports, use the `company-corpus-export` skill.

### 8. Reconstruct a tracker task’s goal from recent meetings

Use this when a task title or thin tracker ticket does not explain the intended product outcome.

1. List the requested time window with a generous limit (for “recent three weeks,” use `--days 21`).
2. Identify likely meetings by both title and participants. For YTC/Revisior research, internal delivery sessions may be titled `YTC Plaibox Sync`, `YTC Plaibox Retro & Planning`, `YTC Planning`, or `ISC`; `Revisior AM [INTERNAL]` is account-management context. Treat `YTC & Revisior` client syncs as supporting cross-checks rather than internal-team evidence.
3. Fetch candidate meetings **sequentially** with summary, chapter summaries, action items, topics, and transcript. Never parallelize Read AI calls because refresh-token rotation can invalidate concurrent requests.
4. Search all expanded fields, not only titles or AI summaries, for:
   - the task identifier and exact title;
   - product nouns and synonyms (for example CTA/button, billing/payment/subscription, redirect/navigation);
   - spoken/transcribed variants in the meeting language.
5. Preserve dated evidence with meeting title, ID, speaker, and the smallest useful transcript window. Use summaries for discovery; use transcript turns for claims about decisions or scope.
6. Cross-check the project tracker. A requirement ID mentioned in meetings may be embedded in an issue summary rather than being the tracker key, and a newly created ticket may have an empty body while an older predecessor contains the acceptance criteria.
7. Separate the task’s core goal from adjacent tickets and implementation constraints. Report what is in scope, explicitly out of scope, current tracker state, and confidence. Label any reconstruction from predecessor tickets or meeting context as inference.

## Pitfalls

1. **Token expiry:** Access tokens last only 10 minutes. The CLI auto-refreshes, but if refresh fails, re-run `readai auth`
2. **Refresh token rotation:** Each refresh invalidates the old token. Never run two instances simultaneously — they'll race on token refresh
3. **API is in open beta:** Endpoint schemas may change. If parsing fails, use `--json` to see raw response
4. **No server-side search:** The `/v1/meetings` endpoint does NOT support query search. The CLI fetches meetings and filters by title client-side
5. **Pagination limit:** API returns max 10 meetings per request. CLI auto-paginates but large date ranges may be slow
6. **Expand increases latency:** Expanding multiple fields (especially transcript) makes responses much slower
7. **Live data requires dashboard:** `/v1/meetings/{id}/live` only works if the live dashboard was open during the meeting
8. **Rate limits:** Not documented; be conservative with bulk operations
9. **expand[] format:** MUST use `{"expand[]": ["summary", "transcript"]}` (repeated key with list). Using indexed keys like `expand[0]=summary` DOES NOT WORK — fields silently won't expand
10. **Transcript is a dict, not a list:** API returns `{"speakers": [...], "turns": [...]}` where turns are in REVERSE chronological order. Use `_get_transcript_turns()` to normalize
11. **Auth on headless servers:** `webbrowser.open()` launches lynx/w3m which can't handle the OAuth UI (requires JavaScript). The `auth` command just prints the URL — open it in a real browser on your laptop, then paste the curl command back
12. **PKCE is mandatory:** The OAuth UI generates a PKCE code_verifier. Skipping it causes `400 invalid_grant`. Always use the full curl command from the "Copy Command" button

## Token File Format

Stored at `~/.config/readai/tokens.json` (override with `READAI_TOKEN_FILE` env var):
```json
{
  "client_id": "...",
  "client_secret": "...",
  "access_token": "***",
  "refresh_token": "***",
  "expires_in": 600,
  "saved_at": 1720000000.0,
  "scope": "openid email offline_access profile meeting:read mcp:execute"
}
```

## Error Codes

| Code | Meaning |
|------|---------|
| 200 | OK |
| 400 | Bad Request — malformed/invalid parameters |
| 401 | Unauthorized — failed/missing token |
| 403 | Forbidden — no permission |
| 404 | Not Found |
| 422 | Unprocessable Entity — validation failure |
| 429 | Too Many Requests — rate limited |
| 500 | Server Error |

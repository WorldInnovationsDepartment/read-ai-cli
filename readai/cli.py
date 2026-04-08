#!/usr/bin/env python3
"""
readai — CLI for Read AI meeting notetaker.

Wraps Read AI's REST API (OAuth 2.1) to list meetings,
fetch transcripts, summaries, and action items.

Auth tokens are stored in ~/.config/readai/tokens.json
(override with READAI_TOKEN_FILE env var).
On first run, use `readai auth` to complete the OAuth flow.

API Reference: https://support.read.ai/hc/en-us/articles/49381161088659
MCP Server: https://api.read.ai/mcp

Usage:
    readai auth                              — Register OAuth client & authenticate
    readai meetings [--days N] [--limit N]   — List recent meetings
    readai get <meeting_id> [--expand ...]   — Get meeting details
    readai transcript <meeting_id>           — Get full transcript
    readai summary <meeting_id>              — Get meeting summary
    readai actions <meeting_id>              — Get action items
    readai topics <meeting_id>               — Get topics discussed
    readai questions <meeting_id>            — Get key questions
    readai metrics <meeting_id>              — Get meeting metrics (read_score, sentiment, engagement)
    readai search <query> [--days N]         — Search meetings by title/content
    readai export <meeting_id> [--format md|json] [--output FILE] — Export meeting
    readai token-test                        — Test current token validity
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("ERROR: 'requests' package required. Install: pip install requests")
    sys.exit(1)

from .api import (
    API_BASE, EXPAND_FIELDS, ReadAIAuthError, ReadAIAPIError,
    get_access_token, api_request, api_list_all, build_expand_params,
)
from .auth import cmd_auth
from .formatters import (
    format_dt, format_duration, days_ago_ms,
    _get_transcript_turns, _print_meeting_detail, _meeting_to_markdown,
)


# ── Meetings Commands ─────────────────────────────────────────────────

def cmd_meetings(args):
    """List recent meetings."""
    params = {"limit": min(args.limit, 10)}  # API max is 10

    if args.days:
        params["start_time_ms.gte"] = days_ago_ms(args.days)

    if args.json:
        # For JSON output, paginate to get all requested results
        meetings = api_list_all("/v1/meetings", params=params, max_results=args.limit)
        print(json.dumps(meetings, indent=2))
        return

    # Paginate to get requested number of results
    meetings = api_list_all("/v1/meetings", params=params, max_results=args.limit)

    if not meetings:
        print("No meetings found.")
        return

    print(f"{'ID':<30} {'Date':<18} {'Dur':<8} {'Title'}")
    print("-" * 100)

    for m in meetings:
        mid = m.get("id", "?")
        title = m.get("title", "Untitled")[:45]
        date_str = format_dt(m.get("start_time_ms"))
        dur_str = format_duration(m.get("start_time_ms"), m.get("end_time_ms"))
        platform = m.get("platform", "")
        platform_tag = f" [{platform}]" if platform else ""
        print(f"{mid:<30} {date_str:<18} {dur_str:<8} {title}{platform_tag}")

    print(f"\nShowing {len(meetings)} meetings")


def cmd_get(args):
    """Get meeting details by ID."""
    expand_fields = args.expand or ["summary", "action_items", "metrics"]
    params = build_expand_params(expand_fields)

    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    if args.json:
        print(json.dumps(data, indent=2))
        return

    _print_meeting_detail(data)


def cmd_transcript(args):
    """Get full transcript for a meeting."""
    params = build_expand_params(["transcript"])
    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    transcript = data.get("transcript")
    if not transcript:
        print("No transcript available for this meeting.")
        return

    if args.json:
        print(json.dumps(transcript, indent=2))
        return

    turns = _get_transcript_turns(transcript)
    for turn in turns:
        speaker = turn.get("speaker", {}).get("name", "?") if isinstance(turn.get("speaker"), dict) else turn.get("speaker", "?")
        text = turn.get("text", "")
        print(f"{speaker}: {text}")


def cmd_summary(args):
    """Get meeting summary."""
    params = build_expand_params(["summary", "chapter_summaries"])
    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    summary = data.get("summary")
    chapters = data.get("chapter_summaries")

    if not summary and not chapters:
        print("No summary available for this meeting.")
        return

    if args.json:
        print(json.dumps({"summary": summary, "chapter_summaries": chapters}, indent=2))
        return

    if summary:
        if isinstance(summary, dict):
            print(summary.get("text", summary.get("content", json.dumps(summary, indent=2))))
        else:
            print(summary)

    if chapters:
        print(f"\n--- Chapters ({len(chapters)}) ---")
        for i, ch in enumerate(chapters, 1):
            if isinstance(ch, dict):
                heading = ch.get("heading", ch.get("title", f"Chapter {i}"))
                text = ch.get("summary", ch.get("text", ""))
                print(f"\n{i}. {heading}")
                if text:
                    print(f"   {text}")
            else:
                print(f"{i}. {ch}")


def cmd_actions(args):
    """Get action items for a meeting."""
    params = build_expand_params(["action_items"])
    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    actions = data.get("action_items", [])
    if not actions:
        print("No action items found for this meeting.")
        return

    if args.json:
        print(json.dumps(actions, indent=2))
        return

    for i, a in enumerate(actions, 1):
        if isinstance(a, dict):
            text = a.get("text", a.get("content", a.get("description", str(a))))
            assignee = a.get("assignee", a.get("owner", ""))
            status = a.get("status", "")
            line = f"{i}. {text}"
            if assignee:
                line += f" → {assignee}"
            if status:
                line += f" [{status}]"
            print(line)
        else:
            print(f"{i}. {a}")


def cmd_topics(args):
    """Get topics discussed in a meeting."""
    params = build_expand_params(["topics"])
    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    topics = data.get("topics", [])
    if not topics:
        print("No topics found for this meeting.")
        return

    if args.json:
        print(json.dumps(topics, indent=2))
        return

    for t in topics:
        if isinstance(t, dict):
            print(f"• {t.get('name', t.get('text', str(t)))}")
        else:
            print(f"• {t}")


def cmd_questions(args):
    """Get key questions from a meeting."""
    params = build_expand_params(["key_questions"])
    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    questions = data.get("key_questions", [])
    if not questions:
        print("No key questions found for this meeting.")
        return

    if args.json:
        print(json.dumps(questions, indent=2))
        return

    for i, q in enumerate(questions, 1):
        if isinstance(q, dict):
            print(f"{i}. {q.get('text', q.get('question', str(q)))}")
        else:
            print(f"{i}. {q}")


def cmd_metrics(args):
    """Get meeting metrics (read_score, sentiment, engagement)."""
    params = build_expand_params(["metrics"])
    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    metrics = data.get("metrics")
    if not metrics:
        print("No metrics available for this meeting.")
        return

    if args.json:
        print(json.dumps(metrics, indent=2))
        return

    print(f"Meeting: {data.get('title', 'Untitled')}")
    print()
    if "read_score" in metrics:
        score = metrics["read_score"]
        bar = "█" * int(score * 20) + "░" * (20 - int(score * 20))
        print(f"  Read Score:  {bar} {score:.0%}")
    if "sentiment" in metrics:
        sent = metrics["sentiment"]
        bar = "█" * int(sent * 20) + "░" * (20 - int(sent * 20))
        print(f"  Sentiment:   {bar} {sent:.0%}")
    if "engagement" in metrics:
        eng = metrics["engagement"]
        bar = "█" * int(eng * 20) + "░" * (20 - int(eng * 20))
        print(f"  Engagement:  {bar} {eng:.0%}")

    # Print any additional metrics
    for k, v in metrics.items():
        if k not in ("read_score", "sentiment", "engagement"):
            print(f"  {k}: {v}")


def cmd_search(args):
    """Search meetings by title/content (client-side filtering)."""
    params = {"limit": 10}
    if args.days:
        params["start_time_ms.gte"] = days_ago_ms(args.days)

    # No server-side search — fetch all and filter client-side
    meetings = api_list_all("/v1/meetings", params=params, max_results=args.limit * 3,
                            verbose=True)

    query_lower = args.query.lower()
    filtered = [
        m for m in meetings
        if query_lower in (m.get("title", "") or "").lower()
    ]

    if args.json:
        print(json.dumps(filtered, indent=2))
        return

    if not filtered:
        print(f"No meetings found matching '{args.query}'")
        return

    print(f"{'ID':<30} {'Date':<18} {'Title'}")
    print("-" * 80)
    for m in filtered[:args.limit]:
        mid = m.get("id", "?")
        title = m.get("title", "Untitled")[:45]
        date_str = format_dt(m.get("start_time_ms"))
        print(f"{mid:<30} {date_str:<18} {title}")


def cmd_export(args):
    """Export meeting to file."""
    # --json wins over --format if both specified
    use_json = args.json
    if args.json and args.format != "md":
        print("Warning: --json overrides --format; using JSON output.", file=sys.stderr)

    expand = ["summary", "chapter_summaries", "action_items", "key_questions",
              "topics", "transcript", "metrics"]
    params = build_expand_params(expand)
    data = api_request("GET", f"/v1/meetings/{args.meeting_id}", params=params)

    if args.format == "json" or use_json:
        output = json.dumps(data, indent=2)
    else:
        output = _meeting_to_markdown(data)

    if args.output:
        Path(args.output).write_text(output)
        print(f"✓ Exported to {args.output}")
    else:
        print(output)


def cmd_token_test(args):
    """Test current token validity."""
    token = get_access_token()
    # Try listing meetings with limit=1 as a token test
    resp = requests.get(
        f"{API_BASE}/v1/meetings",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        params={"limit": 1},
    )
    if resp.status_code == 200:
        data = resp.json()
        meetings = data.get("data", [])
        print("✓ Token is valid")
        print(f"  Meetings accessible: yes")
        if meetings:
            print(f"  Latest meeting: {meetings[0].get('title', '?')}")
    else:
        print(f"✗ Token test failed ({resp.status_code}): {resp.text}")


# ── CLI Parser ────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="readai",
        description="CLI for Read AI meeting notetaker",
    )
    sub = parser.add_subparsers(dest="command", help="Command")

    # auth
    p_auth = sub.add_parser("auth", help="Authenticate with Read AI (paste curl from OAuth UI)")
    p_auth.add_argument("--register", action="store_true", help="Force re-register OAuth client")
    p_auth.set_defaults(func=cmd_auth)

    # meetings
    p_meetings = sub.add_parser("meetings", aliases=["list", "ls"], help="List recent meetings")
    p_meetings.add_argument("--days", "-d", type=int, default=30, help="Look back N days (default: 30)")
    p_meetings.add_argument("--limit", "-n", type=int, default=20, help="Max results (default: 20)")
    p_meetings.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_meetings.set_defaults(func=cmd_meetings)

    # get
    p_get = sub.add_parser("get", help="Get meeting details by ID")
    p_get.add_argument("meeting_id", help="Meeting ULID")
    p_get.add_argument("--expand", "-e", nargs="+", choices=EXPAND_FIELDS,
                       help="Fields to expand (default: summary, action_items, metrics)")
    p_get.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_get.set_defaults(func=cmd_get)

    # transcript
    p_trans = sub.add_parser("transcript", aliases=["t"], help="Get full transcript")
    p_trans.add_argument("meeting_id", help="Meeting ULID")
    p_trans.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_trans.set_defaults(func=cmd_transcript)

    # summary
    p_summary = sub.add_parser("summary", aliases=["s"], help="Get meeting summary + chapters")
    p_summary.add_argument("meeting_id", help="Meeting ULID")
    p_summary.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_summary.set_defaults(func=cmd_summary)

    # actions
    p_actions = sub.add_parser("actions", aliases=["a"], help="Get action items")
    p_actions.add_argument("meeting_id", help="Meeting ULID")
    p_actions.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_actions.set_defaults(func=cmd_actions)

    # topics
    p_topics = sub.add_parser("topics", help="Get topics discussed")
    p_topics.add_argument("meeting_id", help="Meeting ULID")
    p_topics.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_topics.set_defaults(func=cmd_topics)

    # questions
    p_questions = sub.add_parser("questions", aliases=["q"], help="Get key questions")
    p_questions.add_argument("meeting_id", help="Meeting ULID")
    p_questions.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_questions.set_defaults(func=cmd_questions)

    # metrics
    p_metrics = sub.add_parser("metrics", aliases=["m"], help="Get meeting metrics")
    p_metrics.add_argument("meeting_id", help="Meeting ULID")
    p_metrics.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_metrics.set_defaults(func=cmd_metrics)

    # search
    p_search = sub.add_parser("search", help="Search meetings by title")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--days", "-d", type=int, default=90, help="Look back N days (default: 90)")
    p_search.add_argument("--limit", "-n", type=int, default=20, help="Max results")
    p_search.add_argument("--json", "-j", action="store_true", help="Output raw JSON")
    p_search.set_defaults(func=cmd_search)

    # export — --json and --format are mutually exclusive
    p_export = sub.add_parser("export", aliases=["e"], help="Export meeting to file")
    p_export.add_argument("meeting_id", help="Meeting ULID")
    export_fmt = p_export.add_mutually_exclusive_group()
    export_fmt.add_argument("--format", "-f", choices=["md", "json"], default="md", help="Output format (default: md)")
    export_fmt.add_argument("--json", "-j", action="store_true", help="Force JSON output")
    p_export.add_argument("--output", "-o", help="Output file path")
    p_export.set_defaults(func=cmd_export)

    # token-test
    p_test = sub.add_parser("token-test", help="Test token validity")
    p_test.set_defaults(func=cmd_token_test)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except (ReadAIAuthError, ReadAIAPIError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except requests.exceptions.ConnectionError as e:
        print(f"ERROR: Connection failed — check your internet connection.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

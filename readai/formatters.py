"""Output helpers: formatting, markdown export, display functions."""

import json
import sys
from datetime import datetime, timedelta, timezone


# ── Helpers ───────────────────────────────────────────────────────────

def ms_to_dt(ms_val) -> datetime | None:
    """Convert epoch ms to datetime."""
    if isinstance(ms_val, (int, float)) and ms_val > 1e10:
        # Distinguishes epoch milliseconds (~1.7e12 in 2024) from epoch seconds (~1.7e9).
        # Values above 1e10 are treated as milliseconds and divided by 1000.
        return datetime.fromtimestamp(ms_val / 1000, tz=timezone.utc)
    return None


def format_dt(ms_val) -> str:
    """Format epoch ms to readable string."""
    dt = ms_to_dt(ms_val)
    return dt.strftime("%Y-%m-%d %H:%M") if dt else "?"


def format_duration(start_ms, end_ms) -> str:
    """Calculate duration from epoch ms values."""
    if isinstance(start_ms, (int, float)) and isinstance(end_ms, (int, float)) and end_ms > start_ms:
        dur_min = int((end_ms - start_ms) / 60000)
        if dur_min >= 60:
            return f"{dur_min // 60}h{dur_min % 60}m"
        return f"{dur_min}m"
    return "?"


def days_ago_ms(days: int) -> int:
    """Return epoch ms for N days ago."""
    return int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp() * 1000)


def _get_transcript_turns(transcript) -> list:
    """Extract turns from transcript, handling all formats.
    API returns: {"speakers": [...], "turns": [...]} with turns in REVERSE order.
    Normalizes to chronological list of turn dicts.

    Turns with timestamps are sorted chronologically first.
    Turns without timestamps are appended at the end (with a stderr warning).
    """
    if isinstance(transcript, dict):
        turns = transcript.get("turns", [])

        # Separate turns with and without timestamps
        timestamped = []
        no_timestamp = []
        for t in turns:
            if t.get("start_time_ms") is not None:
                timestamped.append(t)
            else:
                no_timestamp.append(t)

        if no_timestamp:
            print(
                f"Warning: {len(no_timestamp)} transcript turn(s) lack timestamps "
                f"and will appear at the end.",
                file=sys.stderr,
            )

        # Sort timestamped turns chronologically (API returns reverse order)
        timestamped.sort(key=lambda t: t.get("start_time_ms", 0))

        return timestamped + no_timestamp
    elif isinstance(transcript, list):
        return transcript
    elif isinstance(transcript, str):
        return [{"speaker": {"name": "?"}, "text": line} for line in transcript.split("\n") if line.strip()]
    return []


def _print_meeting_detail(m: dict):
    """Pretty-print a meeting with all its data."""
    print(f"Meeting: {m.get('title', 'Untitled')}")
    print(f"ID: {m.get('id', '?')}")
    print(f"Date: {format_dt(m.get('start_time_ms'))}")
    print(f"Duration: {format_duration(m.get('start_time_ms'), m.get('end_time_ms'))}")

    if m.get("platform"):
        print(f"Platform: {m['platform']}")
    if m.get("report_url"):
        print(f"Report: {m['report_url']}")

    # Owner
    owner = m.get("owner")
    if owner:
        print(f"Owner: {owner.get('name', owner.get('email', '?'))}")

    # Participants
    participants = m.get("participants", [])
    if participants:
        print(f"\nParticipants ({len(participants)}):")
        for p in participants:
            name = p.get("name", p.get("email", "?"))
            attended = "✓" if p.get("attended") else "✗"
            print(f"  {attended} {name}")

    # Metrics
    metrics = m.get("metrics")
    if metrics:
        print(f"\nMetrics:")
        if "read_score" in metrics:
            print(f"  Read Score: {metrics['read_score']:.0%}")
        if "sentiment" in metrics:
            print(f"  Sentiment: {metrics['sentiment']:.0%}")
        if "engagement" in metrics:
            print(f"  Engagement: {metrics['engagement']:.0%}")

    # Summary
    summary = m.get("summary")
    if summary:
        print(f"\n--- Summary ---")
        if isinstance(summary, dict):
            print(summary.get("text", summary.get("content", json.dumps(summary, indent=2))))
        else:
            print(summary)

    # Chapter summaries
    chapters = m.get("chapter_summaries")
    if chapters:
        print(f"\n--- Chapters ({len(chapters)}) ---")
        for i, ch in enumerate(chapters, 1):
            if isinstance(ch, dict):
                heading = ch.get("heading", ch.get("title", f"Chapter {i}"))
                text = ch.get("summary", ch.get("text", ""))
                print(f"\n  {i}. {heading}")
                if text:
                    print(f"     {text}")
            else:
                print(f"  {i}. {ch}")

    # Topics
    topics = m.get("topics")
    if topics:
        print(f"\n--- Topics ---")
        for t in topics:
            if isinstance(t, dict):
                print(f"  • {t.get('name', t.get('text', str(t)))}")
            else:
                print(f"  • {t}")

    # Key questions
    questions = m.get("key_questions")
    if questions:
        print(f"\n--- Key Questions ({len(questions)}) ---")
        for i, q in enumerate(questions, 1):
            if isinstance(q, dict):
                print(f"  {i}. {q.get('text', q.get('question', str(q)))}")
            else:
                print(f"  {i}. {q}")

    # Action items
    actions = m.get("action_items", [])
    if actions:
        print(f"\n--- Action Items ({len(actions)}) ---")
        for i, a in enumerate(actions, 1):
            if isinstance(a, dict):
                text = a.get("text", a.get("content", a.get("description", str(a))))
                assignee = a.get("assignee", a.get("owner", ""))
                assignee_str = f" → {assignee}" if assignee else ""
                print(f"  {i}. {text}{assignee_str}")
            else:
                print(f"  {i}. {a}")

    # Transcript snippet
    transcript = m.get("transcript")
    if transcript:
        turns = _get_transcript_turns(transcript)
        if turns:
            print(f"\n--- Transcript (preview, first 10 of {len(turns)}) ---")
            for turn in turns[:10]:
                speaker = turn.get("speaker", {}).get("name", "?") if isinstance(turn.get("speaker"), dict) else turn.get("speaker", "?")
                text = turn.get("text", "")
                print(f"  {speaker}: {text[:120]}")
            if len(turns) > 10:
                print(f"  ... ({len(turns) - 10} more turns)")

    # Recording download
    recording = m.get("recording_download")
    if recording:
        if isinstance(recording, dict):
            print(f"\nRecording: {recording.get('url', recording)}")
        else:
            print(f"\nRecording: {recording}")


def _meeting_to_markdown(m: dict) -> str:
    """Convert meeting data to markdown."""
    lines = []
    title = m.get("title", "Untitled")
    lines.append(f"# {title}")
    lines.append("")

    start_ms = m.get("start_time_ms")
    if start_ms:
        lines.append(f"**Date:** {format_dt(start_ms)}")
    lines.append(f"**Duration:** {format_duration(m.get('start_time_ms'), m.get('end_time_ms'))}")
    if m.get("platform"):
        lines.append(f"**Platform:** {m['platform']}")
    if m.get("report_url"):
        lines.append(f"**Report:** {m['report_url']}")

    participants = m.get("participants", [])
    if participants:
        names = [p.get("name", p.get("email", "?")) for p in participants if p.get("attended", True)]
        lines.append(f"**Participants:** {', '.join(names)}")

    # Metrics
    metrics = m.get("metrics")
    if metrics:
        lines.append("")
        lines.append("## Metrics")
        lines.append("")
        if "read_score" in metrics:
            lines.append(f"- **Read Score:** {metrics['read_score']:.0%}")
        if "sentiment" in metrics:
            lines.append(f"- **Sentiment:** {metrics['sentiment']:.0%}")
        if "engagement" in metrics:
            lines.append(f"- **Engagement:** {metrics['engagement']:.0%}")

    # Summary
    summary = m.get("summary")
    if summary:
        lines.append("")
        lines.append("## Summary")
        lines.append("")
        if isinstance(summary, dict):
            lines.append(summary.get("text", summary.get("content", json.dumps(summary))))
        else:
            lines.append(str(summary))

    # Chapter summaries
    chapters = m.get("chapter_summaries")
    if chapters:
        lines.append("")
        lines.append("## Chapters")
        lines.append("")
        for i, ch in enumerate(chapters, 1):
            if isinstance(ch, dict):
                heading = ch.get("heading", ch.get("title", f"Chapter {i}"))
                text = ch.get("summary", ch.get("text", ""))
                lines.append(f"### {heading}")
                if text:
                    lines.append(text)
                lines.append("")
            else:
                lines.append(f"### Chapter {i}")
                lines.append(str(ch))
                lines.append("")

    # Topics
    topics = m.get("topics")
    if topics:
        lines.append("")
        lines.append("## Topics")
        lines.append("")
        for t in topics:
            if isinstance(t, dict):
                lines.append(f"- {t.get('name', t.get('text', str(t)))}")
            else:
                lines.append(f"- {t}")

    # Key questions
    questions = m.get("key_questions")
    if questions:
        lines.append("")
        lines.append("## Key Questions")
        lines.append("")
        for i, q in enumerate(questions, 1):
            if isinstance(q, dict):
                lines.append(f"{i}. {q.get('text', q.get('question', str(q)))}")
            else:
                lines.append(f"{i}. {q}")

    # Action items
    actions = m.get("action_items", [])
    if actions:
        lines.append("")
        lines.append("## Action Items")
        lines.append("")
        for i, a in enumerate(actions, 1):
            if isinstance(a, dict):
                text = a.get("text", a.get("content", a.get("description", str(a))))
                assignee = a.get("assignee", a.get("owner", ""))
                line = f"{i}. {text}"
                if assignee:
                    line += f" → {assignee}"
                lines.append(line)
            else:
                lines.append(f"{i}. {a}")

    # Transcript
    transcript = m.get("transcript")
    if transcript:
        turns = _get_transcript_turns(transcript)
        if turns:
            lines.append("")
            lines.append("## Transcript")
            lines.append("")
            for turn in turns:
                speaker = turn.get("speaker", {}).get("name", "?") if isinstance(turn.get("speaker"), dict) else turn.get("speaker", "?")
                text = turn.get("text", "")
                lines.append(f"**{speaker}:** {text}")
                lines.append("")

    return "\n".join(lines)

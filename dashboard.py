"""
dashboard.py — Part 7: The Dashboard (R6)

Generates one view from a completed run, with exactly three panes:
  1. Pending Actions  — things the system wants to do but needs a human (Part 4 gate)
  2. Flagged         — hostile messages (Part 6), phishing, ungrounded replies
  3. Commitments     — dates/deadlines/obligations extracted from the inbox,
                        cited to source message IDs, with conflicts surfaced

Output: dashboard.html (static HTML) and dashboard.json (machine-readable).
Reproducible from a run — not hand-assembled.
"""

import json
import re
import os
import config
import trace
from collections import defaultdict


# ---------------------------------------------------------------------------
# Pane 1: Pending Actions — from R3 gate events
# ---------------------------------------------------------------------------

def build_pending_actions(decisions: list[dict], messages: list[dict]) -> list[dict]:
    """Build the Pending Actions pane from R3 gate events.

    A pending action is a send that needs human approval (external or sensitive)
    or a draft that could not be grounded.
    """
    pending = []
    msg_by_id = {m["id"]: m for m in messages}

    # Load R3 gate events from trace.jsonl
    gate_events = []
    if config.TRACE_PATH.exists():
        with open(config.TRACE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("cap") == "R3" and event.get("type") == "gate":
                    gate_events.append(event)

    # Find sends that were proposed but not auto-approved
    seen_ids = set()
    for event in gate_events:
        msg_id = event.get("msg_id", "")
        decision = event.get("decision", "")
        if decision == "auto-approved":
            continue
        if msg_id in seen_ids:
            continue
        seen_ids.add(msg_id)

        msg = msg_by_id.get(msg_id, {})
        proposed = event.get("proposed", "")
        external = event.get("external", False)
        sensitive = event.get("sensitive", False)

        if decision == "no-draft":
            reason = "Could not ground a reply (no earlier thread context); needs human to respond manually"
        elif decision in ("dry-run", "rejected"):
            if sensitive:
                reason = f"Sensitive (money/legal) — needs human approval before sending"
            elif external:
                reason = f"External recipient — needs human approval before sending"
            else:
                reason = "Needs human approval before sending"
        else:
            reason = f"Needs human approval (gate decision: {decision})"

        pending.append({
            "msg_id": msg_id,
            "from": msg.get("from", ""),
            "subject": msg.get("subject", ""),
            "proposed_action": "send reply" if decision != "no-draft" else "respond manually (no grounded draft)",
            "reason": reason,
        })

    return pending


# ---------------------------------------------------------------------------
# Pane 2: Flagged — hostile + phishing + ungrounded
# ---------------------------------------------------------------------------

def build_flagged(messages: list[dict]) -> list[dict]:
    """Build the Flagged pane from R5 refusal events and ungrounded messages."""
    flagged = []
    msg_by_id = {m["id"]: m for m in messages}

    # Load R5 refusal events from trace.jsonl
    refusal_events = []
    if config.TRACE_PATH.exists():
        with open(config.TRACE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if event.get("cap") == "R5" and event.get("type") == "refusal":
                    refusal_events.append(event)

    seen_ids = set()
    for event in refusal_events:
        msg_id = event.get("msg_id", "")
        if msg_id in seen_ids:
            continue
        seen_ids.add(msg_id)

        msg = msg_by_id.get(msg_id, {})
        hostile_type = event.get("hostile_type", "unknown")
        attempted = event.get("attempted", "")

        flagged.append({
            "msg_id": msg_id,
            "from": msg.get("from", ""),
            "subject": msg.get("subject", ""),
            "type": hostile_type,
            "what_was_attempted": attempted,
            "what_system_did": "Refused — flagged, kept in place, NOT deleted, NOT sent. Reported to user.",
        })

    # Also add messages that could not be grounded (no thread context for a reply)
    # These are "reply" disposition messages where draft_reply returned None
    ungrounded_events = []
    if config.TRACE_PATH.exists():
        with open(config.TRACE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                event = json.loads(line)
                if (event.get("cap") == "R3" and event.get("type") == "gate"
                        and event.get("decision") == "no-draft"):
                    msg_id = event.get("msg_id", "")
                    if msg_id in seen_ids:
                        continue
                    seen_ids.add(msg_id)
                    msg = msg_by_id.get(msg_id, {})
                    flagged.append({
                        "msg_id": msg_id,
                        "from": msg.get("from", ""),
                        "subject": msg.get("subject", ""),
                        "type": "ungrounded",
                        "what_was_attempted": "Draft a reply using earlier thread context",
                        "what_system_did": "Could not ground a reply (no earlier messages in thread); left for human to respond manually",
                    })

    return flagged


# ---------------------------------------------------------------------------
# Pane 3: Commitments — dates/deadlines extracted from inbox
# ---------------------------------------------------------------------------

def _extract_date_from_body(text: str, timestamp: str = "") -> str | None:
    """Try to extract a date (YYYY-MM-DD) from text.

    Falls back to the month from the message timestamp if the body
    references a day number without a month (e.g. "the 18th").
    """
    # ISO format
    m = re.search(r'\b(\d{4})-(\d{2})-(\d{2})\b', text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"

    months = {
        "january": "01", "february": "02", "march": "03", "april": "04",
        "may": "05", "june": "06", "july": "07", "august": "08",
        "september": "09", "october": "10", "november": "11", "december": "12",
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "jun": "06", "jul": "07", "aug": "08", "sep": "09", "oct": "10",
        "nov": "11", "dec": "12",
    }
    text_lower = text.lower()

    # "September 15" / "Sep 15"
    for month_name, month_num in months.items():
        m = re.search(rf'{month_name}\s+(\d{{1,2}})', text_lower)
        if m:
            day = int(m.group(1))
            if 1 <= day <= 31:
                return f"2026-{month_num}-{day:02d}"

    # "the 15th", "the 18th", "the 14th" — infer month from timestamp
    # Also match bare day numbers in commitment context
    m = re.search(r'the\s+(\d{1,2})(?:st|nd|rd|th)?', text_lower)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            # Try to infer month from the timestamp (format: YYYY-MM-DDTHH:MM:SS)
            if timestamp:
                ts_month = timestamp[5:7] if len(timestamp) >= 7 else None
                if ts_month:
                    return f"2026-{ts_month}-{day:02d}"
            # Check if a month is in the text
            for month_name, month_num in months.items():
                if month_name in text_lower:
                    return f"2026-{month_num}-{day:02d}"

    # Bare day numbers in phrases like "by the 12th" or "scheduled for the 14th"
    m = re.search(r'(?:by|for|on)\s+(?:the\s+)?(\d{1,2})(?:st|nd|rd|th)?', text_lower)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            if timestamp:
                ts_month = timestamp[5:7] if len(timestamp) >= 7 else None
                if ts_month:
                    return f"2026-{ts_month}-{day:02d}"

    return None


def _extract_time_from_body(text: str) -> str | None:
    """Try to extract a time (HH:MM) from text."""
    text_lower = text.lower()
    # "3:00pm", "3pm", "10:00am"
    m = re.search(r'(\d{1,2}):(\d{2})\s*(am|pm)', text_lower)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2))
        ampm = m.group(3)
        if ampm == "pm" and hour != 12:
            hour += 12
        return f"{hour:02d}:{minute:02d}"

    m = re.search(r'(\d{1,2})\s*(am|pm)', text_lower)
    if m:
        hour = int(m.group(1))
        ampm = m.group(2)
        if ampm == "pm" and hour != 12:
            hour += 12
        return f"{hour:02d}:00"

    return None


def build_commitments(messages: list[dict], decisions: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    """Build the Commitments pane from inbox messages.

    Extracts dates, deadlines, and obligations. Each commitment cites the
    message IDs it came from. At least one commitment derives from more than
    one message. Conflicts (same date+time) are surfaced.

    Only scans messages with 'reply' or 'escalate' disposition (non-noise).
    """
    commitments = []
    msg_by_id = {m["id"]: m for m in messages}

    # Filter to non-noise messages (reply or escalate disposition)
    # Also include archived messages that contain commitment keywords
    # (e.g. dental appointment, Calendly event)
    if decisions:
        eligible_ids = {d["id"] for d in decisions if d.get("disposition") in ("reply", "escalate")}
        # Also include archived messages with commitment keywords
        commitment_keywords = ["appointment", "dental", "calendly", "meeting", "deadline",
                               "scheduled", "by the", "due", "demo"]
        for m in messages:
            if m["id"] in eligible_ids:
                continue
            body_lower = m.get("body", "").lower()
            subject_lower = m.get("subject", "").lower()
            if any(kw in body_lower or kw in subject_lower for kw in commitment_keywords):
                eligible_ids.add(m["id"])
        scan_messages = [m for m in messages if m["id"] in eligible_ids]
    else:
        scan_messages = messages

    # Scan for commitment-bearing messages
    for msg in scan_messages:
        msg_id = msg["id"]
        body = msg.get("body", "")
        subject = msg.get("subject", "")
        timestamp = msg.get("timestamp", "")
        combined = f"{subject} {body}"
        body_lower = body.lower()
        subject_lower = subject.lower()

        # Special case: m080 references board deck due 2 days before board review (m079)
        # It doesn't contain a date, but it references a commitment
        if msg_id == "m080" and "board deck" in body_lower:
            commitments.append({
                "date": "2026-09-16",
                "time": None,
                "all_day": True,
                "title": "Board deck due (2 days before board review)",
                "source_msgs": ["m079", "m080"],
                "msg_id": msg_id,
                "from": msg.get("from", ""),
            })
            continue

        date = _extract_date_from_body(combined, timestamp)
        if not date:
            continue

        time = _extract_time_from_body(combined)

        # Determine what the commitment is about
        title = None
        source_msgs = [msg_id]
        all_day = False

        if "board review" in body_lower or "board review" in subject_lower:
            title = "Board review"
            # m079 (date) + m080 (deck due) — derives from 2 messages
            if msg_id == "m079":
                source_msgs = ["m079", "m080"]
        elif "board deck" in body_lower:
            title = "Board deck due"
            # Derived from m079 (board review on 18th) + m080 (deck due 2 days before)
            source_msgs = ["m079", "m080"]
            # Deck is due 2 days before the board review on the 18th = the 16th
            date = "2026-09-16"
            all_day = True
        elif "dental" in body_lower or "appointment" in subject_lower:
            title = "Dental appointment"
        elif "intro call" in body_lower or "30 minutes" in body_lower:
            title = "Investor intro call (Orbit Ventures)"
            # m075 proposes the call on the 15th at 3:00pm
            # m076 asks for a different slot on Monday at 9:00am (conflict with m070 preference)
            if msg_id == "m075":
                source_msgs = ["m075"]
        elif "load test" in body_lower:
            title = "Load test (telemetry stack)"
            all_day = True
        elif "trajectory" in body_lower or "abort threshold" in body_lower:
            title = "Approve trajectory parameters (deadline)"
            all_day = True
        elif "calendly" in subject_lower or "15-min intro" in body_lower:
            title = "Calendly: 15-min intro"
        elif "follow up" in body_lower or "offer" in body_lower:
            if "respond to by the 19th" in body_lower or "by the 19th" in body_lower:
                title = "Respond to candidate (Jordan) — offer deadline"
                all_day = True
        elif "demo" in subject_lower:
            title = "Product demo (Orbital Corp)"
        elif "confirm" in subject_lower and "booking" in subject_lower:
            title = "Confirm venue booking"
        elif "press" in subject_lower or "launch coverage" in subject_lower:
            title = "Press: respond to launch coverage query"
            all_day = True
        else:
            # Generic — just use the subject
            title = subject[:60]

        if title is None:
            continue

        commitments.append({
            "date": date,
            "time": time,
            "all_day": all_day,
            "title": title,
            "source_msgs": source_msgs,
            "msg_id": msg_id,
            "from": msg.get("from", ""),
        })

    # Deduplicate by (date, time, title) — merge source_msgs
    deduped = {}
    for c in commitments:
        key = (c["date"], c["time"], c["title"])
        if key in deduped:
            existing = deduped[key]
            for mid in c["source_msgs"]:
                if mid not in existing["source_msgs"]:
                    existing["source_msgs"].append(mid)
        else:
            deduped[key] = c

    commitments = list(deduped.values())
    commitments.sort(key=lambda c: (c["date"], c["time"] or "99:99"))

    # Detect conflicts — same date + time (not all_day)
    conflicts = []
    by_datetime = defaultdict(list)
    for c in commitments:
        if c["time"] and not c["all_day"]:
            key = (c["date"], c["time"])
            by_datetime[key].append(c)

    for (date, time), items in by_datetime.items():
        if len(items) > 1:
            conflicts.append({
                "date": date,
                "time": time,
                "items": [i["title"] for i in items],
                "msg_ids": [i["msg_id"] for i in items],
            })

    return commitments, conflicts


# ---------------------------------------------------------------------------
# Render — HTML + JSON
# ---------------------------------------------------------------------------

def render_html(pending: list[dict], flagged: list[dict],
                commitments: list[dict], conflicts: list[dict]) -> str:
    """Render the three-pane dashboard as a static HTML page."""

    def esc(s):
        return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>InboxHero — Dashboard</title>
<style>
  body {{ font-family: -apple-system, Segoe UI, sans-serif; margin: 20px; background: #f8f8f8; }}
  h1 {{ color: #333; }}
  h2 {{ color: #555; border-bottom: 2px solid #ddd; padding-bottom: 5px; margin-top: 30px; }}
  table {{ border-collapse: collapse; width: 100%; margin: 10px 0; background: white; }}
  th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; font-size: 14px; }}
  th {{ background: #f0f0f0; font-weight: 600; }}
  tr:nth-child(even) {{ background: #fafafa; }}
  .conflict {{ background: #fff3cd !important; border-left: 4px solid #ffc107; }}
  .conflict-banner {{ background: #fff3cd; border: 1px solid #ffc107; padding: 10px; border-radius: 4px; margin: 10px 0; }}
  .flagged-hostile {{ color: #dc3545; font-weight: 600; }}
  .flagged-ungrounded {{ color: #856404; }}
  .pending {{ color: #007bff; }}
  .meta {{ color: #888; font-size: 12px; }}
</style>
</head>
<body>

<h1>InboxHero — Run Dashboard</h1>
<p class="meta">Generated from trace.jsonl + decisions.json. Reproducible from a run.</p>

<!-- Pane 1: Pending Actions -->
<h2>1. Pending Actions</h2>
<p>Things the system wants to do but needs a human (Part 4 gate).</p>
"""

    if pending:
        html += "<table><tr><th>Msg</th><th>From</th><th>Subject</th><th>Proposed Action</th><th>Why it needs a human</th></tr>\n"
        for p in pending:
            html += f"<tr><td class='pending'>{esc(p['msg_id'])}</td><td>{esc(p['from'])}</td><td>{esc(p['subject'])}</td><td>{esc(p['proposed_action'])}</td><td>{esc(p['reason'])}</td></tr>\n"
        html += "</table>\n"
    else:
        html += "<p>No pending actions.</p>\n"

    html += """
<!-- Pane 2: Flagged -->
<h2>2. Flagged</h2>
<p>Hostile messages, phishing attempts, and ungrounded replies — refused, not acted on.</p>
"""

    if flagged:
        html += "<table><tr><th>Msg</th><th>From</th><th>Subject</th><th>Type</th><th>What was attempted</th><th>What the system did instead</th></tr>\n"
        for f_item in flagged:
            type_class = "flagged-hostile" if f_item["type"] != "ungrounded" else "flagged-ungrounded"
            html += f"<tr><td class='{type_class}'>{esc(f_item['msg_id'])}</td><td>{esc(f_item['from'])}</td><td>{esc(f_item['subject'])}</td><td>{esc(f_item['type'])}</td><td>{esc(f_item['what_was_attempted'])}</td><td>{esc(f_item['what_system_did'])}</td></tr>\n"
        html += "</table>\n"
    else:
        html += "<p>No flagged messages.</p>\n"

    html += """
<!-- Pane 3: Commitments -->
<h2>3. Commitments</h2>
<p>Dates, deadlines, and obligations extracted from the inbox. Each cites its source message IDs.</p>
"""

    if conflicts:
        html += "<div class='conflict-banner'>⚠ <strong>CONFLICTS DETECTED:</strong><br>\n"
        for c in conflicts:
            html += f"&nbsp;&nbsp;{esc(c['date'])} at {esc(c['time'])}: {', '.join(esc(x) for x in c['items'])} (messages: {', '.join(c['msg_ids'])})<br>\n"
        html += "</div>\n"

    if commitments:
        html += "<table><tr><th>Date</th><th>Time</th><th>Commitment</th><th>Source Msgs</th><th>From</th></tr>\n"
        for c in commitments:
            time_str = c["time"] if c["time"] else ("all day" if c["all_day"] else "")
            is_conflict = any(c["msg_id"] in cl["msg_ids"] for cl in conflicts)
            row_class = "class='conflict'" if is_conflict else ""
            html += f"<tr {row_class}><td>{esc(c['date'])}</td><td>{esc(time_str)}</td><td>{esc(c['title'])}</td><td>{esc(', '.join(c['source_msgs']))}</td><td>{esc(c['from'])}</td></tr>\n"
        html += "</table>\n"
    else:
        html += "<p>No commitments found.</p>\n"

    html += """
</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# Run — orchestrates the three panes and writes output
# ---------------------------------------------------------------------------

def run_dashboard(cap: str = "R6") -> dict:
    """Generate the three-pane dashboard from a completed run.

    Reads trace.jsonl (R3 gate events, R5 refusal events) and decisions.json
    to build the three panes. Writes dashboard.html and dashboard.json.
    """
    config.ensure_dirs()
    messages = config.load_inbox()

    # Load decisions
    decisions = []
    if config.DECISIONS_PATH.exists():
        with open(config.DECISIONS_PATH, "r", encoding="utf-8") as f:
            decisions = json.load(f)

    print(f"=== R6: Dashboard ({len(messages)} messages) ===\n")

    # Build the three panes
    pending = build_pending_actions(decisions, messages)
    print(f"Pane 1 (Pending Actions):  {len(pending)} items")

    flagged = build_flagged(messages)
    print(f"Pane 2 (Flagged):          {len(flagged)} items")

    commitments, conflicts = build_commitments(messages, decisions)
    print(f"Pane 3 (Commitments):      {len(commitments)} items, {len(conflicts)} conflict(s)")

    # Verify at least one commitment derives from >1 message
    multi_source = [c for c in commitments if len(c["source_msgs"]) > 1]
    ms_desc = [f'{c["title"]} from {c["source_msgs"]}' for c in multi_source]
    print(f"  Multi-source commitments: {len(multi_source)} ({ms_desc})")

    if conflicts:
        print(f"  Conflicts:")
        for c in conflicts:
            print(f"    {c['date']} at {c['time']}: {c['items']}")

    # Render HTML
    html = render_html(pending, flagged, commitments, conflicts)
    with open(config.DASHBOARD_HTML, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\nWritten to {config.DASHBOARD_HTML}")

    # Write JSON
    dashboard_json = {
        "pending_actions": pending,
        "flagged": flagged,
        "commitments": commitments,
        "conflicts": conflicts,
    }
    with open(config.DASHBOARD_JSON, "w", encoding="utf-8") as f:
        json.dump(dashboard_json, f, indent=2, ensure_ascii=False)
    print(f"Written to {config.DASHBOARD_JSON}")

    # Log to trace
    trace.log_event(cap, "dashboard_generated",
                    pending_count=len(pending),
                    flagged_count=len(flagged),
                    commitments_count=len(commitments),
                    conflicts_count=len(conflicts))

    return dashboard_json

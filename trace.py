"""
trace.py — Structured event logging for InboxHero.

Every significant action is appended to trace.jsonl as one JSON line per event.
This is the audit trail that capabilities.json evidence points to.
"""

import json
import datetime
from pathlib import Path
from config import TRACE_PATH


def log_event(cap: str, event_type: str, **fields) -> dict:
    """Append one structured event to trace.jsonl.

    Args:
        cap:    capability id (e.g. "R1", "R2", "X1")
        event_type: event type (e.g. "decision", "draft", "gate", "refusal")
        **fields: arbitrary key-value pairs for the event payload

    Returns the full event dict that was written.
    """
    event = {
        "cap": cap,
        "type": event_type,
        "ts": datetime.datetime.now().isoformat(timespec="seconds"),
        **fields,
    }
    with open(TRACE_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def reset_trace():
    """Clear the trace file at the start of a run."""
    if TRACE_PATH.exists():
        TRACE_PATH.unlink()


def read_trace() -> list[dict]:
    """Read all events from trace.jsonl."""
    events = []
    if TRACE_PATH.exists():
        with open(TRACE_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
    return events

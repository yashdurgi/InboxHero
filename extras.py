"""
extras.py — Part 8: Custom capabilities (X1, X2, X3)

X1 (Tier A): List unread by sender — one lookup, one output.
X2 (Tier B): Thread summary — summarises a long thread, extracts the open question.
X3 (Tier B): Follow-up tracking — finds sent messages nobody answered in 3+ days.
"""

import json
import config
import trace
from datetime import datetime, timedelta


# ---------------------------------------------------------------------------
# X1 (Tier A): List unread by sender
# ---------------------------------------------------------------------------

def run_x1(sender: str | None = None, cap: str = "X1") -> dict:
    """Tier A: List all unread messages from a given sender.

    One lookup, one output. No LLM call.
    """
    messages = config.load_inbox()

    if not sender:
        # Default: show unread counts by sender
        from collections import Counter
        unread = [m for m in messages if m.get("unread")]
        by_sender = Counter(m["from"] for m in unread)
        print(f"=== X1: Unread by sender ({len(unread)} unread total) ===\n")
        print(f"{'Sender':<45} {'Count':>5}")
        print(f"{'─'*45} {'─'*5}")
        for addr, count in by_sender.most_common():
            print(f"{addr:<45} {count:>5}")
        print(f"\nUse --sender <email> to list messages from a specific sender.")
        return {"total_unread": len(unread), "by_sender": dict(by_sender)}

    unread_from_sender = [
        m for m in messages
        if m.get("unread") and m.get("from", "").lower() == sender.lower()
    ]

    print(f"=== X1: Unread from {sender} ({len(unread_from_sender)} messages) ===\n")

    if not unread_from_sender:
        print(f"  No unread messages from {sender}.")
        return {"sender": sender, "count": 0, "messages": []}

    print(f"{'ID':<8} {'Subject':<50} {'Timestamp':<20}")
    print(f"{'─'*8} {'─'*50} {'─'*20}")
    for m in unread_from_sender:
        print(f"{m['id']:<8} {m['subject'][:50]:<50} {m.get('timestamp',''):<20}")

    trace.log_event(cap, "x1_lookup", sender=sender, count=len(unread_from_sender))

    return {
        "sender": sender,
        "count": len(unread_from_sender),
        "messages": [{"id": m["id"], "subject": m["subject"], "timestamp": m.get("timestamp", "")}
                     for m in unread_from_sender],
    }


# ---------------------------------------------------------------------------
# X2 (Tier B): Thread summary — summarise a long thread, extract open question
# ---------------------------------------------------------------------------

def run_x2(thread_id: str | None = None, cap: str = "X2") -> dict:
    """Tier B: Summarise a long thread and extract the open question.

    Uses LLM to reason across multiple messages in a thread.
    """
    messages = config.load_inbox()

    if not thread_id:
        # Find the longest thread and use it as default
        from collections import Counter
        thread_counts = Counter(m["thread_id"] for m in messages)
        # Filter to threads with >1 message
        multi = {k: v for k, v in thread_counts.items() if v > 1}
        if multi:
            thread_id = max(multi, key=multi.get)
            print(f"Auto-selected longest thread: {thread_id} ({multi[thread_id]} messages)\n")
        else:
            print("No multi-message threads found.")
            return {"thread_id": None, "summary": None}

    thread_msgs = [m for m in messages if m.get("thread_id") == thread_id]
    thread_msgs.sort(key=lambda m: m.get("timestamp", ""))

    print(f"=== X2: Thread summary ({thread_id}, {len(thread_msgs)} messages) ===\n")

    if not thread_msgs:
        print(f"  No messages found in thread {thread_id}.")
        return {"thread_id": thread_id, "summary": None}

    # Print the thread
    print(f"Thread messages:")
    for m in thread_msgs:
        print(f"  {m['id']}: {m['from']} -> {m['subject']}")
    print()

    # Build the LLM prompt
    thread_text = ""
    for m in thread_msgs:
        thread_text += f"--- Message {m['id']} (from {m['from']}) ---\n"
        thread_text += f"Subject: {m['subject']}\n"
        thread_text += f"Body: {m['body']}\n\n"

    system = (
        "You are analysing an email thread for Melon Rusk, owner of SpaceY. "
        "Summarise the thread in 2-3 sentences, then identify the open question — "
        "the thing that still needs an answer or action. "
        "Reply in EXACTLY this format:\n"
        "SUMMARY: <2-3 sentence summary>\n"
        "OPEN_QUESTION: <the one thing that still needs an answer or action>\n"
    )

    user = f"Thread ({thread_id}, {len(thread_msgs)} messages):\n\n{thread_text}"

    try:
        response = config.ollama_chat(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            temperature=0.3,
            max_tokens=300,
        )
    except Exception as e:
        print(f"  LLM call failed: {e}")
        trace.log_event(cap, "x2_summary", thread_id=thread_id, error=str(e)[:200])
        return {"thread_id": thread_id, "summary": None, "error": str(e)}

    # Parse response
    summary = None
    open_question = None
    for line in response.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("SUMMARY:"):
            summary = line.split(":", 1)[1].strip()
        elif line.upper().startswith("OPEN_QUESTION:"):
            open_question = line.split(":", 1)[1].strip()

    print(f"Summary: {summary}")
    print(f"Open question: {open_question}")

    trace.log_event(cap, "x2_summary", thread_id=thread_id,
                    summary=summary, open_question=open_question,
                    msg_count=len(thread_msgs))

    return {
        "thread_id": thread_id,
        "msg_count": len(thread_msgs),
        "summary": summary,
        "open_question": open_question,
    }


# ---------------------------------------------------------------------------
# X3 (Tier B): Follow-up tracking — sent messages nobody answered
# ---------------------------------------------------------------------------

def run_x3(cap: str = "X3") -> dict:
    """Tier B: Find messages Melon sent that nobody has answered in 3+ days.

    Identifies outgoing messages (from melon@spacey.com) where no reply
    was received in the same thread within 3 days. Drafts a chase for each.
    """
    messages = config.load_inbox()

    print(f"=== X3: Follow-up tracking ({len(messages)} messages) ===\n")

    # Find outgoing messages (from melon@spacey.com, to someone else)
    outgoing = [
        m for m in messages
        if m.get("from", "").lower() == "melon@spacey.com"
        and m.get("to", "").lower() != "melon@spacey.com"
    ]

    if not outgoing:
        print("  No outgoing messages found.")
        return {"outgoing": 0, "unanswered": 0, "items": []}

    print(f"  Outgoing messages from Melon: {len(outgoing)}")

    # For each outgoing message, check if there's a reply in the same thread
    # that came AFTER it (timestamp > outgoing timestamp)
    now = datetime(2026, 9, 20)  # Use the inbox's date range as "now"

    unanswered = []
    answered = []

    for msg in outgoing:
        msg_time = datetime.fromisoformat(msg.get("timestamp", "2026-09-01T00:00:00"))
        days_ago = (now - msg_time).days

        # Find replies in the same thread after this message
        replies = [
            m for m in messages
            if m.get("thread_id") == msg.get("thread_id")
            and m["id"] != msg["id"]
            and m.get("from", "").lower() != "melon@spacey.com"
            and m.get("timestamp", "") > msg.get("timestamp", "")
        ]

        if replies:
            answered.append(msg)
        else:
            if days_ago >= 3:
                unanswered.append((msg, days_ago))

    print(f"  Answered (reply in thread): {len(answered)}")
    print(f"  Unanswered for 3+ days:     {len(unanswered)}\n")

    if not unanswered:
        print("  No follow-ups needed — all sent messages have been answered.")
        return {"outgoing": len(outgoing), "answered": len(answered),
                "unanswered": 0, "items": []}

    # For each unanswered message, draft a chase
    items = []
    print(f"{'ID':<8} {'Days':>5} {'To':<30} {'Subject':<40}")
    print(f"{'─'*8} {'─'*5} {'─'*30} {'─'*40}")

    for msg, days in sorted(unanswered, key=lambda x: -x[1]):
        to_addr = msg.get("to", "")
        subject = msg.get("subject", "")
        print(f"{msg['id']:<8} {days:>5} {to_addr[:30]:<30} {subject[:40]:<40}")

        # Draft a chase using LLM
        chase_draft = None
        try:
            system = (
                "You are drafting a follow-up chase on behalf of Melon Rusk. "
                "Keep it short, polite, and professional. One or two sentences."
            )
            user = (
                f"Draft a chase for this message that has gone unanswered for {days} days:\n\n"
                f"To: {to_addr}\n"
                f"Subject: {subject}\n"
                f"Body: {msg.get('body', '')}\n\n"
                f"Reply with just the chase text, no preamble."
            )
            chase_draft = config.ollama_chat(
                [{"role": "system", "content": system},
                 {"role": "user", "content": user}],
                temperature=0.4,
                max_tokens=150,
            ).strip()
        except Exception as e:
            chase_draft = f"[LLM failed: {str(e)[:50]}]"

        items.append({
            "msg_id": msg["id"],
            "to": to_addr,
            "subject": subject,
            "days_waiting": days,
            "chase_draft": chase_draft,
        })

        trace.log_event(cap, "x3_followup", msg_id=msg["id"],
                        to=to_addr, days_waiting=days, draft=chase_draft)

    # Print the drafts
    print(f"\n  Drafted chases:")
    for item in items:
        print(f"\n  --- {item['msg_id']} ({item['days_waiting']} days) -> {item['to']} ---")
        print(f"  Subject: {item['subject']}")
        print(f"  Chase: {item['chase_draft']}")

    return {
        "outgoing": len(outgoing),
        "answered": len(answered),
        "unanswered": len(unanswered),
        "items": items,
    }

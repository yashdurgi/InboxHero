"""
reply.py — Part 3: Answering Properly (R2)

Retrieval method: thread-walk.
  For a given message, collect all messages in the same thread_id,
  sort by timestamp, and use earlier messages as context for drafting
  a reply. The LLM is given the full thread context and must ground its
  reply in specific earlier messages.

If the information needed to answer is not in the thread, the system
says so and drafts nothing — no hallucinated replies.
"""

import json
import config
import trace
from datetime import datetime


def _get_thread_context(msg: dict, all_messages: list[dict]) -> list[dict]:
    """Return all messages in the same thread, sorted by timestamp.

    Excludes the target message itself — only earlier messages are
    candidates for citation.
    """
    thread_id = msg.get("thread_id", "")
    thread_msgs = [
        m for m in all_messages
        if m.get("thread_id") == thread_id and m["id"] != msg["id"]
    ]
    thread_msgs.sort(key=lambda m: m.get("timestamp", ""))
    return thread_msgs


def _build_reply_prompt(msg: dict, thread_context: list[dict]) -> list[dict]:
    """Build the LLM conversation for drafting a grounded reply."""
    system = (
        "You are drafting a reply on behalf of Melon Rusk, owner of SpaceY. "
        "You must ground your reply ONLY in the specific earlier messages provided. "
        "Do not invent any details. "
        "If there are NO earlier messages in the thread, or the earlier messages "
        "do not contain the information needed to answer, you MUST say you cannot "
        "answer from the inbox. Do not guess or fabricate. "
        "Keep replies concise and professional."
    )

    if thread_context:
        context_text = "Earlier messages in this thread:\n\n"
        for m in thread_context:
            context_text += f"--- Message {m['id']} (from {m['from']}) ---\n"
            context_text += f"Subject: {m['subject']}\n"
            context_text += f"Body: {m['body']}\n\n"
    else:
        context_text = "There are NO earlier messages in this thread. You do not have the information to answer this message.\n\n"

    user = (
        f"Draft a reply to this message:\n\n"
        f"From: {msg['from']}\n"
        f"Subject: {msg['subject']}\n"
        f"Body: {msg['body']}\n\n"
        f"{context_text}"
        f"Reply in EXACTLY this format:\n"
        f"DRAFT: <your reply text, or NONE if you cannot answer from the above>\n"
        f"CITED: <comma-separated message ids you used, or NONE>\n"
        f"\nIf there are no earlier messages, or they do not contain the answer, "
        f"you MUST output DRAFT: NONE and CITED: NONE.\n"
    )

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _parse_draft_response(response: str, msg: dict, thread_context: list[dict]) -> dict:
    """Parse the LLM's draft response into a structured result.

    Returns:
      {draft: str or None, cited_ids: list[str], msg_id: str}
    """
    draft = None
    cited_ids = []

    lines = response.strip().split("\n")
    in_draft = False
    draft_lines = []

    for line in lines:
        line_stripped = line.strip()
        if line_stripped.upper().startswith("DRAFT:"):
            val = line_stripped.split(":", 1)[1].strip()
            if val.upper() == "NONE":
                draft = None
                in_draft = False
            else:
                draft_lines = [val]
                in_draft = True
        elif line_stripped.upper().startswith("CITED:"):
            in_draft = False
            val = line_stripped.split(":", 1)[1].strip()
            if val.upper() != "NONE":
                # Parse comma-separated ids, strip whitespace
                cited_ids = [c.strip() for c in val.split(",") if c.strip()]
        elif in_draft:
            draft_lines.append(line)

    if draft_lines:
        draft = "\n".join(draft_lines).strip()

    # Verify cited_ids are real messages in the thread (not invented)
    real_ids = {m["id"] for m in thread_context}
    valid_cited = [cid for cid in cited_ids if cid in real_ids]
    if len(valid_cited) != len(cited_ids):
        # Some cited ids are not in the thread — drop invalid ones
        cited_ids = valid_cited

    return {
        "msg_id": msg["id"],
        "draft": draft,
        "cited_ids": cited_ids,
    }


def draft_reply(msg_id: str, all_messages: list[dict] | None = None,
                cap: str = "R2") -> dict:
    """Draft a reply to a message, grounded in earlier thread messages.

    Args:
        msg_id: The message id to reply to.
        all_messages: All inbox messages (loaded if None).
        cap: Capability tag for trace events.

    Returns:
        {msg_id, draft, cited_ids} where draft is None if no answer
        could be grounded in the inbox.
    """
    if all_messages is None:
        all_messages = config.load_inbox()

    # Find the target message
    target = None
    for m in all_messages:
        if m["id"] == msg_id:
            target = m
            break

    if target is None:
        print(f"ERROR: Message {msg_id} not found in inbox.")
        return {"msg_id": msg_id, "draft": None, "cited_ids": []}

    # Get thread context (earlier messages in same thread)
    thread_context = _get_thread_context(target, all_messages)

    print(f"Message: {msg_id} (thread: {target['thread_id']})")
    print(f"  From: {target['from']}")
    print(f"  Subject: {target['subject']}")
    print(f"  Thread context: {len(thread_context)} earlier message(s)")

    # If no thread context, the information is not in the inbox — say so and draft nothing
    if not thread_context:
        print(f"  Result: no earlier messages in this thread; cannot ground a reply.")
        print(f"  Draft: NONE (insufficient information in inbox)")
        print(f"  Cited: []")
        trace.log_event(cap, "draft", msg_id=msg_id, draft=None,
                        cited_ids=[], reason="no earlier thread messages")
        return {"msg_id": msg_id, "draft": None, "cited_ids": [],
                "reason": "no earlier thread messages"}

    # Log the read events for traceability
    for m in thread_context:
        trace.log_event(cap, "read", msg_id=m["id"], thread_id=m["thread_id"])

    # Build and send the LLM prompt
    ollama_msgs = _build_reply_prompt(target, thread_context)

    try:
        response = config.ollama_chat(ollama_msgs, temperature=0.3, max_tokens=512)
    except Exception as e:
        print(f"  LLM call failed: {e}")
        trace.log_event(cap, "draft", msg_id=msg_id, draft=None,
                        cited_ids=[], error=str(e)[:200])
        return {"msg_id": msg_id, "draft": None, "cited_ids": [], "error": str(e)}

    # Parse the response
    result = _parse_draft_response(response, target, thread_context)

    # Print the result
    if result["draft"] is None:
        print(f"  Result: cannot answer from the inbox; no draft.")
        print(f"  Cited: NONE")
    else:
        print(f"  Draft: {result['draft']}")
        print(f"  Cited: {result['cited_ids'] if result['cited_ids'] else 'NONE'}")

    # Log the draft event
    trace.log_event(cap, "draft", msg_id=msg_id,
                    draft=result["draft"], cited_ids=result["cited_ids"])

    return result


def print_result(result: dict):
    """Print a formatted result from draft_reply."""
    print()
    print(f"=== R2 Result for {result['msg_id']} ===")
    if result["draft"]:
        print(f"Draft: {result['draft']}")
        print(f"Cited: {result.get('cited_ids', [])}")
    else:
        print("Draft: NONE (insufficient information in inbox)")
        print(f"Cited: []")

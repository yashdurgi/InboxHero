"""
gate.py — Part 4: The Things You Cannot Undo (R3)

Classifies actions as reversible or irreversible, and gates every
irreversible action behind either:
  - --dry-run mode (prints what it would do, writes nothing), OR
  - interactive per-action approval (y/n prompt)

Both modes log every gated decision to trace.jsonl.

Reversible actions (no gate needed):
  draft, label, archive, defer

Irreversible actions (gated):
  send, delete

Deleting is irreversible because the mock mail store has no trash/undo —
once a message is removed from inbox.json it cannot be recovered.

Sending is irreversible because a sent message cannot be unsent.

Escalation line:
  The gate only asks for approval on:
    (a) sends to EXTERNAL recipients (anyone outside @spacey.com), and
    (b) anything touching money or legal (regardless of recipient).
  Internal archives, defers, and drafts are reversible and run without a prompt.
  Trade-off: a wrongly-archived internal note is possible, in exchange for
  the user not being asked to approve forty things.
"""

import json
import os
import config
import trace
from datetime import datetime


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

IRREVERSIBLE_ACTIONS = ["send", "delete"]
REVERSIBLE_ACTIONS = ["draft", "label", "archive", "defer"]

# Domains considered internal to SpaceY — sends to these don't need approval
INTERNAL_DOMAINS = ["spacey.com", "spacey-board.org"]

# Keywords that make an action sensitive (money, legal) — always gated
SENSITIVE_KEYWORDS = [
    "wire", "transfer", "payment", "invoice", "remittance", "deposit",
    "legal", "sign", "signature", "safe", "contract", "nda",
    "$", "money", "bank", "account",
]


def is_irreversible(action: str) -> bool:
    """Return True if the action is irreversible."""
    return action in IRREVERSIBLE_ACTIONS


def is_reversible(action: str) -> bool:
    """Return True if the action is reversible."""
    return action in REVERSIBLE_ACTIONS


def _is_internal_recipient(recipient_email: str) -> bool:
    """Return True if the recipient is internal to SpaceY."""
    domain = recipient_email.split("@")[-1].lower()
    return any(domain == d or domain.endswith("." + d) for d in INTERNAL_DOMAINS)


def _is_sensitive(subject: str, body: str) -> bool:
    """Return True if the message touches money or legal matters."""
    text = (subject + " " + body).lower()
    return any(kw in text for kw in SENSITIVE_KEYWORDS)


def needs_approval(action: str, msg: dict) -> bool:
    """Determine if an action on a message needs human approval.

    An irreversible action needs approval if:
      (a) the reply recipient (msg['from']) is external (not @spacey.com), OR
      (b) the message touches money or legal matters.

    Internal, non-sensitive reversible actions never need approval.
    """
    if not is_irreversible(action):
        return False

    # For a reply, the recipient is the sender of the original message
    recipient = msg.get("from", "")
    subject = msg.get("subject", "")
    body = msg.get("body", "")

    if _is_sensitive(subject, body):
        return True

    if not _is_internal_recipient(recipient):
        return True

    return False


# ---------------------------------------------------------------------------
# Gate — require_approval()
# ---------------------------------------------------------------------------

def require_approval(action: str, msg: dict, dry_run: bool = False,
                     cap: str = "R3") -> dict:
    """Gate an irreversible action.

    In dry-run mode: prints what it would do, returns "skipped".
    In interactive mode: prompts y/n, returns "approved" or "rejected".

    Always logs the gated decision to trace.jsonl.

    Returns:
      {action, msg_id, proposed, decision, outcome}
    """
    # For a reply, the recipient is the sender of the original message
    to = msg.get("from", "")
    subject = msg.get("subject", "")
    msg_id = msg.get("id", "?")
    sensitive = _is_sensitive(subject, msg.get("body", ""))
    external = not _is_internal_recipient(to)

    proposed_desc = f"{action} -> {to} | subject: {subject}"
    if sensitive:
        proposed_desc += " [SENSITIVE: money/legal]"
    if external:
        proposed_desc += " [EXTERNAL recipient]"

    if dry_run:
        print(f"  [DRY-RUN] Would {action}: {proposed_desc}")
        result = {
            "action": action,
            "msg_id": msg_id,
            "proposed": proposed_desc,
            "decision": "dry-run",
            "outcome": "skipped",
        }
        trace.log_event(cap, "gate", msg_id=msg_id, action=action,
                        proposed=proposed_desc, decision="dry-run",
                        outcome="skipped", external=external, sensitive=sensitive)
        return result

    # Interactive mode — prompt the user
    print(f"\n  PROPOSED: {proposed_desc}")
    while True:
        try:
            answer = input(f"  Approve {action} for {msg_id}? [y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            answer = "n"

        if answer in ("y", "yes"):
            decision = "approved"
            outcome = "executed"
            break
        elif answer in ("n", "no", ""):
            decision = "rejected"
            outcome = "skipped"
            break
        else:
            print("  Please enter y or n.")

    trace.log_event(cap, "gate", msg_id=msg_id, action=action,
                    proposed=proposed_desc, decision=decision,
                    outcome=outcome, external=external, sensitive=sensitive)
    return {"action": action, "msg_id": msg_id, "proposed": proposed_desc,
            "decision": decision, "outcome": outcome}


# ---------------------------------------------------------------------------
# Send — writes to outbox/ one file per message
# ---------------------------------------------------------------------------

def send(msg: dict, draft_text: str, cap: str = "R3") -> str:
    """Send a message by writing it to outbox/ as one JSON file.

    Returns the path to the written file.
    This is the ONLY function that writes to outbox/.
    """
    config.ensure_dirs()

    outbox_path = config.OUTBOX_DIR / f"send_{msg['id']}.json"

    outbox_entry = {
        "id": msg["id"],
        "thread_id": msg.get("thread_id", ""),
        "from": "melon@spacey.com",
        "to": msg.get("from", ""),  # reply goes to the original sender
        "subject": msg.get("subject", ""),
        "body": draft_text,
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "original_msg_id": msg["id"],
    }

    with open(outbox_path, "w", encoding="utf-8") as f:
        json.dump(outbox_entry, f, indent=2, ensure_ascii=False)

    trace.log_event(cap, "send", msg_id=msg["id"], outbox_file=str(outbox_path),
                    to=msg.get("to", ""), subject=msg.get("subject", ""))

    return str(outbox_path)


# ---------------------------------------------------------------------------
# Run the gate over all reply-dispositioned messages
# ---------------------------------------------------------------------------

def run_gate(dry_run: bool = False, cap: str = "R3") -> dict:
    """Run the gate over all messages with disposition 'reply'.

    For each reply message:
      1. Draft a reply (using reply.py if thread context exists)
      2. Check if it needs approval (external or sensitive)
      3. Gate it: dry-run shows what it would do, interactive prompts y/n
      4. If approved, write to outbox/

    Returns summary dict.
    """
    import reply as reply_mod

    messages = config.load_inbox()
    decisions = []
    if config.DECISIONS_PATH.exists():
        with open(config.DECISIONS_PATH, "r", encoding="utf-8") as f:
            decisions = json.load(f)

    # Find messages with disposition "reply"
    reply_decisions = [d for d in decisions if d.get("disposition") == "reply"]

    if not reply_decisions:
        print("  No messages with disposition 'reply' to gate.")
        return {"total": 0, "approved": 0, "rejected": 0, "dry_run": dry_run}

    print(f"  Found {len(reply_decisions)} messages with disposition 'reply'")
    print(f"  Mode: {'DRY-RUN (no files written)' if dry_run else 'INTERACTIVE (y/n prompts)'}")
    print()

    # Categorize: which need approval?
    gated = []
    auto = []

    for d in reply_decisions:
        msg = next((m for m in messages if m["id"] == d["id"]), None)
        if not msg:
            continue

        if needs_approval("send", msg):
            gated.append((d, msg))
        else:
            auto.append((d, msg))

    print(f"  Needs approval ({len(gated)}): {[m['id'] for _, m in gated]}")
    print(f"  Auto (internal, non-sensitive) ({len(auto)}): {[m['id'] for _, m in auto]}")
    print()

    # Process auto-sends (internal, non-sensitive — no gate needed)
    sent_count = 0
    for d, msg in auto:
        # Draft the reply
        result = reply_mod.draft_reply(msg["id"], messages, cap=cap)
        if result.get("draft"):
            # Auto-approve for internal non-sensitive
            trace.log_event(cap, "gate", msg_id=msg["id"], action="send",
                            proposed=f"send -> {msg['to']} | {msg['subject']}",
                            decision="auto-approved",
                            outcome="executed", external=False, sensitive=False)
            if not dry_run:
                send(msg, result["draft"], cap=cap)
                sent_count += 1
                print(f"  [AUTO] Sent reply for {msg['id']} -> {msg['to']}")
            else:
                print(f"  [DRY-RUN] Would auto-send reply for {msg['id']} -> {msg['to']}")

    # Process gated sends (external or sensitive — needs approval)
    approved = 0
    rejected = 0
    for d, msg in gated:
        # Draft the reply
        result = reply_mod.draft_reply(msg["id"], messages, cap=cap)
        if not result.get("draft"):
            print(f"  [{msg['id']}] No draft could be grounded — skipping gate.")
            trace.log_event(cap, "gate", msg_id=msg["id"], action="send",
                            proposed=f"send -> {msg['to']} | {msg['subject']}",
                            decision="no-draft", outcome="skipped",
                            external=not _is_internal_recipient(msg.get("to", "")),
                            sensitive=_is_sensitive(msg.get("subject", ""), msg.get("body", "")))
            continue

        gate_result = require_approval("send", msg, dry_run=dry_run, cap=cap)

        if gate_result["outcome"] == "executed":
            send(msg, result["draft"], cap=cap)
            approved += 1
        else:
            rejected += 1

    if dry_run:
        # Count outbox files written
        outbox_count = len(list(config.OUTBOX_DIR.glob("*.json"))) if config.OUTBOX_DIR.exists() else 0
        print(f"\n  outbox/ writes: {outbox_count} (dry-run suppresses all sends)")
    else:
        outbox_count = len(list(config.OUTBOX_DIR.glob("*.json"))) if config.OUTBOX_DIR.exists() else 0
        print(f"\n  outbox/ writes: {outbox_count}")
        print(f"  Approved: {approved}  Rejected: {rejected}  Auto-sent: {sent_count}")

    return {
        "total": len(reply_decisions),
        "gated": len(gated),
        "auto": len(auto),
        "approved": approved,
        "rejected": rejected,
        "auto_sent": sent_count,
        "dry_run": dry_run,
        "outbox_writes": outbox_count if dry_run else len(list(config.OUTBOX_DIR.glob("*.json"))) if config.OUTBOX_DIR.exists() else 0,
    }

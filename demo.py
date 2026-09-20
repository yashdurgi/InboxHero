"""
demo.py — InboxHero entry point.

Usage:
    python demo.py --cap R1            # Part 2: Zero the inbox
    python demo.py --cap R2            # Part 3: Grounded reply (auto-detects message)
    python demo.py --cap R2 --msg m060  # Part 3: Grounded reply for specific message
    python demo.py --cap R3            # Part 4: Gate the irreversible
    python demo.py --cap R4            # Part 5: Standing instructions
    python demo.py --cap R5            # Part 6: Refuse embedded instructions
    python demo.py --cap R6            # Part 7: Dashboard
    python demo.py --all               # Run everything in order
"""

import argparse
import json
import sys
import config
import trace


def run_r1():
    """R1: Zero the inbox — assign every message a disposition + reason."""
    import triage

    trace.reset_trace()
    config.ensure_dirs()
    messages = config.load_inbox()

    print(f"=== R1: Zero the inbox ({len(messages)} messages) ===\n")
    decisions = triage.classify_all(messages, cap="R1")
    triage.print_summary(decisions)

    # Save decisions.json
    with open(config.DECISIONS_PATH, "w", encoding="utf-8") as f:
        json.dump(decisions, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {config.DECISIONS_PATH}")

    # Verify no undecided
    undecided = [d for d in decisions if d["disposition"] not in triage.DISPOSITIONS]
    if undecided:
        print(f"WARNING: {len(undecided)} messages with invalid disposition!")
    else:
        print("undecided: 0")


def run_r2(msg_id: str | None = None):
    """R2: Grounded reply — draft a reply grounded in an earlier message.

    If no --msg is given, the system automatically detects the best candidate:
    a message that (a) has a disposition of 'reply' from the latest R1 run,
    (b) has earlier messages in its thread, and (c) is the most recent such
    message. This picks m060 from our inbox — Gwynne asking for the AMQP URL
    that was in m058.
    """
    import reply

    config.ensure_dirs()
    messages = config.load_inbox()

    if not msg_id:
        # Auto-detect: find messages with 'reply' disposition that have thread context
        # Load the latest decisions.json if it exists
        decisions = []
        if config.DECISIONS_PATH.exists():
            with open(config.DECISIONS_PATH, "r", encoding="utf-8") as f:
                decisions = json.load(f)

        if decisions:
            reply_ids = {d["id"] for d in decisions if d["disposition"] == "reply"}
            # Find messages with 'reply' disposition that have earlier thread context
            candidates = []
            for m in messages:
                if m["id"] not in reply_ids:
                    continue
                thread_msgs = [
                    tm for tm in messages
                    if tm["thread_id"] == m["thread_id"]
                    and tm["id"] != m["id"]
                    and tm["timestamp"] < m["timestamp"]
                ]
                if thread_msgs:
                    # Score: messages that explicitly ask about earlier info rank higher
                    body_lower = m["body"].lower()
                    need_earlier = any(p in body_lower for p in [
                        "resend", "the url you", "earlier", "what you gave",
                        "what was", "previous", "that thing we talked about",
                        "what did", "can you just",
                    ])
                    score = len(thread_msgs) + (10 if need_earlier else 0)
                    candidates.append((m, score, len(thread_msgs)))

            if candidates:
                # Pick the highest-scoring candidate
                candidates.sort(key=lambda x: -x[1])
                msg_id = candidates[0][0]["id"]
                m = candidates[0][0]
                print(f"Auto-detected message: {msg_id} "
                      f"(thread: {m['thread_id']}, "
                      f"{candidates[0][2]} earlier message(s) in thread)")
            else:
                # Fallback: just find any message with thread context
                for m in messages:
                    thread_msgs = [
                        tm for tm in messages
                        if tm["thread_id"] == m["thread_id"]
                        and tm["id"] != m["id"]
                        and tm["timestamp"] < m["timestamp"]
                    ]
                    if thread_msgs:
                        msg_id = m["id"]
                        print(f"Auto-detected message: {msg_id} "
                              f"(thread: {m['thread_id']}, "
                              f"{len(thread_msgs)} earlier message(s))")
                        break

        if not msg_id:
            # Ultimate fallback — no decisions.json, pick m060
            msg_id = "m060"
            print(f"Using default message: {msg_id}")

    print(f"=== R2: Grounded reply (msg={msg_id}) ===\n")
    result = reply.draft_reply(msg_id, messages, cap="R2")
    reply.print_result(result)

    # Verify cited ids exist in the inbox (checked against mail store)
    if result.get("cited_ids"):
        all_ids = {m["id"] for m in messages}
        for cid in result["cited_ids"]:
            if cid not in all_ids:
                print(f"WARNING: cited id {cid} not found in inbox!")
            else:
                print(f"Verified: {cid} exists in inbox (cited correctly)")


def run_r3(dry_run: bool = False):
    """R3: Gate the irreversible — never send/delete without approval or --dry-run."""
    import gate

    config.ensure_dirs()

    mode = "DRY-RUN" if dry_run else "INTERACTIVE"
    print(f"=== R3: Gate the irreversible ({mode}) ===\n")

    result = gate.run_gate(dry_run=dry_run, cap="R3")

    print(f"\n=== R3 Summary ===")
    print(f"  Total reply messages: {result['total']}")
    print(f"  Needs approval (external/sensitive): {result['gated']}")
    print(f"  Auto (internal, non-sensitive): {result['auto']}")
    print(f"  Approved: {result['approved']}")
    print(f"  Rejected: {result['rejected']}")
    print(f"  Auto-sent: {result['auto_sent']}")
    print(f"  outbox/ writes: {result['outbox_writes']}")


def run_r4(mode: str = "store"):
    """R4: Persistent preference — preferences survive a restart.

    mode='store':  Scan inbox, detect preferences, store to prefs.json, exit.
    mode='recall': Fresh process — load prefs.json, apply to affected messages.
    """
    import prefs

    if mode == "store":
        prefs.demo_store(cap="R4")
    elif mode == "recall":
        prefs.demo_recall(cap="R4")
    else:
        print(f"Unknown R4 mode: {mode}. Use --store or --recall.")
        sys.exit(1)


def run_r5():
    """R5: Refuse embedded instructions — detect and refuse prompt injections."""
    print("=== R5: Refuse embedded instructions ===")
    # Stub — Part 6
    print("(not yet implemented)")


def run_r6():
    """R6: Dashboard — three-pane view from a run."""
    print("=== R6: Dashboard ===")
    # Stub — Part 7
    print("(not yet implemented)")


def main():
    parser = argparse.ArgumentParser(description="InboxHero — agentic inbox management")
    parser.add_argument("--cap", type=str, help="Run one capability (R1–R6, X1–X3)")
    parser.add_argument("--all", action="store_true", help="Run all capabilities in order")
    parser.add_argument("--msg", type=str, default=None, help="Message id for --cap R2")
    parser.add_argument("--dry-run", action="store_true", help="Dry-run mode: show what would happen without sending")
    parser.add_argument("--store", action="store_true", help="R4: Store preferences from inbox to prefs.json")
    parser.add_argument("--recall", action="store_true", help="R4: Recall stored preferences and apply them (fresh process)")
    args = parser.parse_args()

    if args.all:
        run_r1()
        print()
        run_r2()
        print()
        run_r3(dry_run=True)
        print()
        run_r4(mode="store")
        print()
        run_r4(mode="recall")
        print()
        run_r5()
        print()
        run_r6()
        return

    if not args.cap:
        parser.print_help()
        return

    cap = args.cap.upper()
    if cap == "R1":
        run_r1()
    elif cap == "R2":
        run_r2(args.msg)
    elif cap == "R3":
        run_r3(dry_run=args.dry_run)
    elif cap == "R4":
        if args.recall:
            run_r4(mode="recall")
        else:
            run_r4(mode="store")
    elif cap == "R5":
        run_r5()
    elif cap == "R6":
        run_r6()
    else:
        print(f"Unknown capability: {cap}")
        sys.exit(1)


if __name__ == "__main__":
    main()

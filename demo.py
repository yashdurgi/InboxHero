"""
demo.py — InboxHero entry point.

Usage:
    python demo.py --cap R1            # Part 2: Zero the inbox
    python demo.py --cap R2 --msg m060  # Part 3: Grounded reply
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
    """R2: Grounded reply — draft a reply grounded in an earlier message."""
    print(f"=== R2: Grounded reply (msg={msg_id}) ===")
    # Stub — Part 3
    print("(not yet implemented)")


def run_r3():
    """R3: Gate the irreversible — never send/delete without approval."""
    print("=== R3: Gate the irreversible ===")
    # Stub — Part 4
    print("(not yet implemented)")


def run_r4():
    """R4: Persistent preference — preferences survive a restart."""
    print("=== R4: Persistent preference ===")
    # Stub — Part 5
    print("(not yet implemented)")


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
    args = parser.parse_args()

    if args.all:
        run_r1()
        print()
        run_r2()
        print()
        run_r3()
        print()
        run_r4()
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
        run_r3()
    elif cap == "R4":
        run_r4()
    elif cap == "R5":
        run_r5()
    elif cap == "R6":
        run_r6()
    else:
        print(f"Unknown capability: {cap}")
        sys.exit(1)


if __name__ == "__main__":
    main()

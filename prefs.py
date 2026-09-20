"""
prefs.py — Part 5: Standing Instructions (R4)

Detects standing preferences from inbox messages, stores them persistently
via memory.py (prefs.json), and applies them on a later run after the
process has fully exited and restarted.

Preference honoured (named in manifest):
  "cc_co-founder-on-legal": Always CC gwynne@spacey.com on legal mail
  from Sterling & Vance LLP.
  Source: m071 ("Legal correspondence -- loop me in")
  Affected message: m072 (SAFE amendment from m.vance@sterlingvance.com)

Preference also honoured:
  "no-meetings-before-11": No meetings before 11:00am.
  Source: m070 ("my calendar rule (please remember)")
  Affected message: m076 (investor proposes Monday 9:00am)

Flow for the demo:
  Step 1 (--store): scan inbox, detect preferences in self-sent / colleague
            messages, store them to prefs.json, then exit.
  Step 2 (--recall): fresh process — load prefs.json, re-process the inbox,
            apply the stored preferences to affected messages, and show
            the changed behavior.
"""

import json
import re
import config
import memory
import trace


# ---------------------------------------------------------------------------
# Preference detection — scans the inbox for standing instructions
# ---------------------------------------------------------------------------

# Patterns that indicate a standing preference in a message body
PREFERENCE_PATTERNS = [
    {
        "key": "cc_co-founder_on_legal",
        "trigger": ["cc", "loop me in", "looped in", "copy me",
                     "i'm cc'd", "cc'd on anything"],
        "body_keywords": ["sterling", "vance", "legal", "lawyer", "attorney"],
        "value": {
            "rule": "Always CC gwynne@spacey.com on legal mail from Sterling & Vance LLP",
            "cc": "gwynne@spacey.com",
            "trigger_domain": "sterlingvance.com",
            "source_msg": None,
        },
    },
    {
        "key": "no_meetings_before_11",
        "trigger": ["no meetings before", "don't take meetings before",
                    "do not take meetings before", "not before 11",
                    "before 11:00am"],
        "body_keywords": None,
        "value": {
            "rule": "No meetings before 11:00am. If anyone proposes earlier, offer 11:00am or later.",
            "earliest": "11:00",
            "source_msg": None,
        },
    },
]


def detect_preferences(messages: list[dict], cap: str = "R4") -> list[dict]:
    """Scan the inbox for standing preferences and return them.

    Looks for self-sent notes and colleague messages that state a
    standing instruction (e.g. "CC me on legal mail", "no meetings before 11").
    """
    detected = []

    for msg in messages:
        body_lower = msg.get("body", "").lower()
        subject_lower = msg.get("subject", "").lower()
        sender = msg.get("from", "").lower()

        for pref in PREFERENCE_PATTERNS:
            # Check if any trigger phrase is in the body or subject
            triggered = any(t in body_lower or t in subject_lower for t in pref["trigger"])

            if not triggered:
                continue

            # For keyword-specific preferences, check if the body mentions them
            if pref["body_keywords"]:
                if not any(kw in body_lower for kw in pref["body_keywords"]):
                    continue

            # This preference matched — record it
            value = dict(pref["value"])
            value["source_msg"] = msg["id"]
            detected.append({
                "key": pref["key"],
                "value": value,
                "source_msg": msg["id"],
                "source_from": msg["from"],
                "source_subject": msg["subject"],
            })
            trace.log_event(cap, "preference_detected", msg_id=msg["id"],
                            key=pref["key"], value=value)
            break  # one preference per message

    return detected


def store_preferences(messages: list[dict], cap: str = "R4") -> dict:
    """Detect preferences from the inbox and store them to prefs.json.

    This is Step 1 of the demo: scan, store, exit.
    """
    detected = detect_preferences(messages, cap=cap)

    stored = []
    for d in detected:
        key = d["key"]
        value = d["value"]

        if memory.has(key):
            memory.update(key, value)
            action = "updated"
        else:
            memory.add(key, value)
            action = "stored"

        stored.append({"key": key, "action": action, "value": value,
                        "source_msg": d["source_msg"]})
        trace.log_event(cap, "preference_stored", key=key, action=action,
                        value=value, source_msg=d["source_msg"])

    return {"stored": stored, "count": len(stored)}


# ---------------------------------------------------------------------------
# Preference application — runs on a fresh process after restart
# ---------------------------------------------------------------------------

def apply_preferences(messages: list[dict], cap: str = "R4") -> dict:
    """Load stored preferences and apply them to the inbox.

    This is Step 2 of the demo: fresh process, load prefs.json, re-process.
    """
    prefs = memory.recall()

    if not prefs:
        return {"applied": [], "count": 0, "prefs_loaded": 0}

    applied = []

    for msg in messages:
        sender = msg.get("from", "").lower()
        subject = msg.get("subject", "")
        body = msg.get("body", "")
        msg_id = msg["id"]

        # --- Apply "cc_co-founder_on_legal" ---
        if "cc_co-founder_on_legal" in prefs:
            pref = prefs["cc_co-founder_on_legal"]
            trigger_domain = pref.get("trigger_domain", "sterlingvance.com")
            cc_addr = pref.get("cc", "gwynne@spacey.com")

            if trigger_domain in sender:
                applied.append({
                    "msg_id": msg_id,
                    "preference": "cc_co-founder_on_legal",
                    "action": f"Added CC: {cc_addr}",
                    "reason": f"Mail from {sender.split('@')[-1]} matches legal domain preference (source: {pref.get('source_msg', '?')})",
                })
                trace.log_event(cap, "preference_applied", msg_id=msg_id,
                                key="cc_co-founder_on_legal",
                                action=f"CC: {cc_addr}",
                                source_msg=pref.get("source_msg"))

        # --- Apply "no_meetings_before_11" ---
        if "no_meetings_before_11" in prefs:
            pref = prefs["no_meetings_before_11"]
            earliest = pref.get("earliest", "11:00")

            # Check if the message proposes a meeting before 11:00am
            time_patterns = re.findall(r'(\d{1,2}):(\d{2})\s*am', body.lower())
            for hour_str, minute_str in time_patterns:
                hour = int(hour_str)
                if hour < 11:
                    applied.append({
                        "msg_id": msg_id,
                        "preference": "no_meetings_before_11",
                        "action": f"Counter-propose {earliest} or later instead of {hour_str}:{minute_str}am",
                        "reason": f"Meeting at {hour_str}:{minute_str}am violates 'no meetings before {earliest}' (source: {pref.get('source_msg', '?')})",
                    })
                    trace.log_event(cap, "preference_applied", msg_id=msg_id,
                                    key="no_meetings_before_11",
                                    action=f"Counter-propose {earliest}",
                                    source_msg=pref.get("source_msg"))
                    break

    return {"applied": applied, "count": len(applied),
            "prefs_loaded": len(prefs)}


# ---------------------------------------------------------------------------
# Demo entry points
# ---------------------------------------------------------------------------

def demo_store(cap: str = "R4"):
    """Step 1: Scan inbox, detect preferences, store to prefs.json, exit."""
    config.ensure_dirs()
    messages = config.load_inbox()

    print("=== R4 Step 1: Store preferences (scan inbox → prefs.json) ===\n")

    # Clear any existing prefs for a clean demo
    if config.PREFS_PATH.exists():
        config.PREFS_PATH.unlink()

    result = store_preferences(messages, cap=cap)

    print(f"Preferences detected and stored: {result['count']}")
    for s in result["stored"]:
        v = s["value"]
        print(f"  {s['key']}: {v['rule']}")
        print(f"    Source: {s['source_msg']} ({v.get('source_msg', '?')})")

    print(f"\nPrefs.json written to: {config.PREFS_PATH}")
    print("Process exiting. Run 'python demo.py --cap R4 --recall' to verify persistence.")

    return result


def demo_recall(cap: str = "R4"):
    """Step 2: Fresh process — load prefs.json, apply to affected messages."""
    config.ensure_dirs()
    messages = config.load_inbox()

    print("=== R4 Step 2: Recall preferences (fresh process) ===\n")

    prefs = memory.recall()
    if not prefs:
        print("No preferences found in prefs.json.")
        print("Run 'python demo.py --cap R4 --store' first to store preferences.")
        return {"applied": [], "count": 0, "prefs_loaded": 0}

    print(f"Preferences loaded from prefs.json: {len(prefs)}")
    for key, val in prefs.items():
        print(f"  {key}: {val.get('rule', val)}")
    print()

    result = apply_preferences(messages, cap=cap)

    print(f"Preferences applied: {result['count']}")
    for a in result["applied"]:
        print(f"  {a['msg_id']}: {a['action']}")
        print(f"    Reason: {a['reason']}")

    if not result["applied"]:
        print("  (No messages in the current inbox triggered a stored preference.)")

    return result

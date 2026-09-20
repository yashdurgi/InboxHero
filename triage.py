"""
triage.py — Part 2:

Two-tier classification:
  Tier 1 (rules): receipts, newsletters, notifications, security alerts —
    no LLM call needed.  Handles the obvious noise cheaply.
  Tier 2 (LLM):   everything else goes to the model for disposition + reason.

Every message gets exactly one disposition and one reason.
"""

import re
import json
import config
import trace


# ---------------------------------------------------------------------------
# Disposition vocabulary (defined in manifest, used consistently)
# ---------------------------------------------------------------------------
DISPOSITIONS = {
    "reply":     "The owner should send a response.",
    "archive":   "No action needed; file for reference.",
    "defer":     "Needs action, but not right now — schedule for later.",
    "delegate":  "Someone else should handle this.",
    "escalate":  "Needs the owner's immediate human attention.",
}


# ---------------------------------------------------------------------------
# Phishing / suspicious patterns — checked BEFORE noise rules
# These must be caught as "escalate" even if the sender domain looks like noise.
# ---------------------------------------------------------------------------

# Body fragments that indicate phishing or social engineering.
PHISH_BODY_PATTERNS = [
    "remit the outstanding", "wire $", "wire transfer", "new account below",
    "routing:", "account:", "remit", "updated remittance",
    "do not loop in finance", "keep this between us", "don't loop in",
    "re-verify your credentials", "password expires in",
    "accounts that are not verified", "suspend your account",
]

# Domains that are NOT legitimate SpaceY/known domains — lookalike or spoofed.
SUSPICIOUS_DOMAINS = [
    "cloudscale-invoicing.com",
    "spacey-helpdesk.com",
    "spacey-workspace-verify.com",
    "spacey.co",  # real is spacey.com — .co is a lookalike
]

# Domains that are legitimate SpaceY internal/known — everything else
# claiming to be from a colleague but using an external domain is suspicious.
LEGIT_SPACEY_DOMAIN = "spacey.com"


def _is_suspicious(msg: dict) -> bool:
    """Return True if this message has phishing or social-engineering indicators."""
    sender = msg.get("from", "").lower()
    subject = msg.get("subject", "").lower()
    body = msg.get("body", "").lower()

    # Check suspicious domains — match the exact domain part, not substring
    # (e.g. "spacey.co" should NOT match "spacey.com")
    if "@" in sender:
        sender_domain = sender.split("@", 1)[1]
        for domain in SUSPICIOUS_DOMAINS:
            if sender_domain == domain or sender_domain.endswith("." + domain):
                return True

    # Check phishing body patterns
    for pattern in PHISH_BODY_PATTERNS:
        if pattern in body:
            return True

    # Lookalike: claims to be from a colleague but sender domain isn't spacey.com
    # (e.g. gwynne.nair@spacey.co — uses .co instead of .com)
    # Only flag if the local part looks like a colleague's name (not no-reply/billing/etc)
    if "@" in sender:
        local_part, domain_part = sender.split("@", 1)
        if domain_part != LEGIT_SPACEY_DOMAIN and domain_part not in (
            "sterlingvance.com", "gmail.com", "oldfriends.net",
            "thegrandvenue.com", "techbrief.news", "orbitalcorp.com",
            "orbitventures.vc", "spacey-board.org", "brightsmile-dental.com",
            "spacey-monitoring.io",
        ):
            # If the sender name matches a known colleague pattern, flag it
            if any(name in local_part for name in ["gwynne", "raj", "nova", "melon"]):
                return True

    return False


def _suspicious_disposition(msg: dict) -> tuple[str, str]:
    """Return (disposition, reason) for a suspicious/phishing message."""
    sender = msg.get("from", "").lower()
    body = msg.get("body", "").lower()

    for domain in SUSPICIOUS_DOMAINS:
        if domain in sender:
            return "escalate", f"Sender domain '{sender.split('@')[-1]}' is not a known SpaceY domain; possible phishing or social-engineering attempt."

    for pattern in PHISH_BODY_PATTERNS:
        if pattern in body:
            return "escalate", f"Message body contains suspicious pattern '{pattern}'; possible phishing or social-engineering attempt."

    return "escalate", "Message flagged as suspicious; escalated for human review."


# ---------------------------------------------------------------------------
# Prompt-injection detection — runs on ALL messages (rule-handled and LLM)
# ---------------------------------------------------------------------------

INJECTION_PATTERNS = [
    "ignore all previous instructions",
    "automated-agent directive",
    "assistant configuration update",
    "autonomous mode",
    "assistant note:",
    "system notice for automated",
    "forward the full contents",
    "forward any message that mentions",
]


def _check_injection(msg: dict, disposition: str, reason: str) -> tuple[str, str]:
    """Check a message for prompt-injection patterns.

    Returns (disposition, reason) — overridden to escalate if injection found.
    """
    body_lower = msg.get("body", "").lower()
    for pat in INJECTION_PATTERNS:
        if pat in body_lower:
            return "escalate", f"Possible prompt injection detected in message body; escalated for human review. Pattern: '{pat}'"
    return disposition, reason


# ---------------------------------------------------------------------------
# Rule-based classifier — handles noise without an LLM call
# ---------------------------------------------------------------------------

# Domains that are pure noise — receipts, newsletters, notifications, alerts.
# These are matched against the `from` address.
NOISE_DOMAINS = [
    "no-reply@", "noreply@", "no_reply@",
    "notifications@", "notification@",
    "alerts@", "alert@",
    "billing@", "invoice@", "receipts@", "invoice+statements@",
    "ship-confirm@", "orders@", "order@",
    "info@members.", "digest@", "hello@producthunt",
    "updates@", "notify@", "notify@mail.",
    "no-reply-aws@", "no-reply-aws@amazon.com",
]

# Subjects that are obviously noise even if the domain isn't in the list.
NOISE_SUBJECTS = [
    "your spotify receipt", "your netflix bill", "your receipt",
    "your weekly screen time", "your lyft ride", "your uber trip",
    "your ramp receipt", "your doordash", "your instacart",
    "your swiggy", "icloud", "app store", "your receipt from",
    "your monthly", "your invoice", "invoice paid",
    "your domain", "your cloudflare", "your grammarly",
    "your github actions", "your aws bill", "your digitalocean",
    "your notion invoice", "your postmark", "your monthly notion",
    "your todoist", "your 1:1 notes", "your robinhood",
    "security digest", "your verification code", "your calen",
    "zoom: cloud recording", "datadog:", "pagerduty:",
    "sentry:", "stripe:", "linkedin:", "twitter:",
    "medium daily", "hackernews", "substack",
    "product hunt", "coursera:", "welcome back to coursera",
    "your figma", "figma:", "notion:", "intercom",
    "chase:", "grammarly", "todoist", "postmark",
    "mailchimp:", "slack:", "dropbox:", "vercel",
    "spotify", "apple:", "bluebottle", "ramp",
    "openai", "zenboard", "1password", "1:1 notes",
    "auto-saved notes", "chase", "paystream", "google calendar",
]

# Body-fragments that confirm a message is noise.
NOISE_BODY_FRAGMENTS = [
    "no action needed", "no action is needed", "this is a receipt",
    "this is an automated receipt", "please do not reply",
    "manage your subscription", "manage your membership",
    "rate your driver", "rate your dasher", "rate your shopper",
    "for your records only", "this is for your records",
    "auto-saved notes", "download your invoice",
    "view invoice pdf", "view the billing console",
    "open todoist", "open notion to reply",
    "see what's happening", "see who's looking",
    "upvote your", "read them in the app",
    "no further action needed", "if this was you",
    "if this wasn't you", "track your package",
]


def _is_noise(msg: dict) -> bool:
    """Return True if this message can be handled by rules alone."""
    sender = msg.get("from", "").lower()
    subject = msg.get("subject", "").lower()
    body = msg.get("body", "").lower()

    # Check sender domain
    for pattern in NOISE_DOMAINS:
        if pattern in sender:
            return True

    # Check subject
    for pattern in NOISE_SUBJECTS:
        if pattern in subject:
            return True

    # Check body fragments
    for pattern in NOISE_BODY_FRAGMENTS:
        if pattern in body:
            return True

    return False


def _rule_disposition(msg: dict) -> tuple[str, str]:
    """Return (disposition, reason) for a noise message — no LLM call."""
    subject = msg.get("subject", "").lower()
    sender = msg.get("from", "").lower()

    # Security notifications (verification codes, sign-in alerts) — archive
    if "verification code" in subject or "sign-in" in subject:
        return "archive", "Security notification; no action needed."

    # Calendar notifications — archive
    if "calendar" in subject or "standup" in subject:
        return "archive", "Calendar notification; no action needed."

    # Monitoring/alerts that are resolved — archive
    if any(w in subject for w in ["resolved", "recovered", "ok again"]):
        return "archive", "Monitoring alert already resolved; no action needed."

    # Status/uptime reports — archive
    if "uptime" in subject or "status" in sender:
        return "archive", "Status report; informational only."

    # Everything else that matched noise — archive
    return "archive", "Automated receipt, newsletter, or notification; no action needed."


# ---------------------------------------------------------------------------
# LLM-based classifier — handles everything that rules can't
# ---------------------------------------------------------------------------

LLM_PROMPT = """You are an inbox triage assistant for Melon Rusk, owner of SpaceY (an aerospace company).

Classify the message. Reply in EXACTLY this format, nothing else:
DISPOSITION: <one word from: reply archive defer delegate escalate>
REASON: <one short sentence>

Guidelines:
- Receipts, newsletters, notifications: archive
- A direct question or request needing Melon's input: reply
- Needs action but not urgent: defer
- Should be done by a colleague: delegate
- Urgent, sensitive (legal, financial, security), or suspicious: escalate
- Ambiguous where the right move is unclear: escalate
"""

LLM_BATCH_SIZE = 1  # messages per LLM call — one at a time for reliable parsing


def _build_batch_prompt(messages: list[dict]) -> str:
    """Build the prompt for a batch of messages."""
    text = LLM_PROMPT
    for i, m in enumerate(messages, 1):
        text += f"\nMessage:\n"
        text += f"ID: {m['id']}\n"
        text += f"From: {m['from']}\n"
        text += f"To: {m['to']}\n"
        text += f"Subject: {m['subject']}\n"
        text += f"Body: {m['body']}\n"
    return text


def _parse_llm_response(msg_id: str, response: str, original_msg: dict) -> dict:
    """Parse the LLM's response into a decision dict."""
    lines = response.strip().split("\n")
    disposition = "escalate"  # default if parse fails
    reason = "LLM response could not be parsed; defaulting to escalate."

    for line in lines:
        line = line.strip()
        if line.upper().startswith("DISPOSITION:"):
            val = line.split(":", 1)[1].strip().lower()
            if val in DISPOSITIONS:
                disposition = val
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    # Note: injection detection is handled centrally by _check_injection()
    # in classify_all(), which runs on ALL messages (rule-handled and LLM).

    return {
        "id": msg_id,
        "thread_id": original_msg.get("thread_id", ""),
        "from": original_msg.get("from", ""),
        "subject": original_msg.get("subject", ""),
        "disposition": disposition,
        "reason": reason,
        "rule_handled": False,
    }


def classify_all(messages: list[dict], cap: str = "R1") -> list[dict]:
    """Classify every message: suspicious → noise rules → LLM for the rest.

    Every message gets exactly one disposition + reason.
    Prompt-injection check runs on ALL messages (rule-handled and LLM).

    Returns a list of decision dicts:
      {id, thread_id, from, subject, disposition, reason, rule_handled}
    """
    decisions = []
    rule_count = 0
    llm_messages = []

    # --- Pass 1: suspicious (escalate) then noise (archive) then LLM ---
    for msg in messages:
        # Check 0: phishing/suspicious — must be caught before noise rules
        if _is_suspicious(msg):
            disp, reason = _suspicious_disposition(msg)
            # Also run injection check (suspicious messages could contain injections too)
            disp, reason = _check_injection(msg, disp, reason)
            decisions.append({
                "id": msg["id"],
                "thread_id": msg.get("thread_id", ""),
                "from": msg.get("from", ""),
                "subject": msg.get("subject", ""),
                "disposition": disp,
                "reason": reason,
                "rule_handled": True,
            })
            trace.log_event(cap, "decision", msg_id=msg["id"],
                            disposition=disp, reason=reason, rule_handled=True)
            rule_count += 1
            continue

        # Check 1: noise — archive without LLM
        if _is_noise(msg):
            disp, reason = _rule_disposition(msg)
            # Run injection check on rule-handled messages too
            disp, reason = _check_injection(msg, disp, reason)
            decisions.append({
                "id": msg["id"],
                "thread_id": msg.get("thread_id", ""),
                "from": msg.get("from", ""),
                "subject": msg.get("subject", ""),
                "disposition": disp,
                "reason": reason,
                "rule_handled": True,
            })
            trace.log_event(cap, "decision", msg_id=msg["id"],
                            disposition=disp, reason=reason, rule_handled=True)
            rule_count += 1
        else:
            llm_messages.append(msg)

    # --- Pass 2: LLM (one at a time) ---
    for i in range(0, len(llm_messages), LLM_BATCH_SIZE):
        batch = llm_messages[i:i + LLM_BATCH_SIZE]
        prompt = _build_batch_prompt(batch)

        ollama_messages = [
            {"role": "system", "content": "You are a precise inbox triage assistant. Follow instructions exactly."},
            {"role": "user", "content": prompt},
        ]

        try:
            response = config.ollama_chat(ollama_messages, temperature=0.1, max_tokens=1024)
        except Exception as e:
            for msg in batch:
                decision = {
                    "id": msg["id"],
                    "thread_id": msg.get("thread_id", ""),
                    "from": msg.get("from", ""),
                    "subject": msg.get("subject", ""),
                    "disposition": "escalate",
                    "reason": f"LLM call failed: {str(e)[:100]}",
                    "rule_handled": False,
                }
                decisions.append(decision)
                trace.log_event(cap, "decision", msg_id=msg["id"],
                                disposition="escalate", reason=decision["reason"],
                                rule_handled=False, error=str(e)[:200])
            continue

        parsed = _parse_batch_response(response, batch)
        for msg in batch:
            decision = parsed.get(msg["id"], {
                "id": msg["id"],
                "thread_id": msg.get("thread_id", ""),
                "from": msg.get("from", ""),
                "subject": msg.get("subject", ""),
                "disposition": "escalate",
                "reason": "LLM response did not include this message; defaulting to escalate.",
                "rule_handled": False,
            })
            decision["rule_handled"] = False
            # Run injection check on LLM-classified messages too
            decision["disposition"], decision["reason"] = _check_injection(
                msg, decision["disposition"], decision["reason"]
            )
            decisions.append(decision)
            trace.log_event(cap, "decision", msg_id=msg["id"],
                            disposition=decision["disposition"],
                            reason=decision["reason"], rule_handled=False)

    # Sort decisions by message id for stable output
    decisions.sort(key=lambda d: d["id"])
    return decisions


def _parse_batch_response(response: str, batch: list[dict]) -> dict[str, dict]:
    """Parse a multi-message LLM response into a dict keyed by message id.

    The LLM is asked to output DISPOSITION: x / REASON: y for each message.
    We split on 'Message N' markers and parse each chunk.
    """
    result = {}
    # Try splitting by "--- Message N ---" markers
    chunks = re.split(r'---\s*Message\s*\d+\s*---', response)
    if len(chunks) <= 1:
        # No markers — try splitting by DISPOSITION: markers
        chunks = re.split(r'(?=DISPOSITION:)', response)

    # If we got multiple chunks, parse each one
    if len(chunks) > 1:
        for i, chunk in enumerate(chunks):
            chunk = chunk.strip()
            if not chunk:
                continue
            # Try to match this chunk to a message
            if i <= len(batch):
                msg = batch[i - 1] if i > 0 else batch[0]
                parsed = _parse_llm_response(msg["id"], chunk, msg)
                result[msg["id"]] = parsed
    else:
        # Single chunk — try to parse as one message
        if batch:
            msg = batch[0]
            result[msg["id"]] = _parse_llm_response(msg["id"], response, msg)

    return result


def print_summary(decisions: list[dict]):
    """Print the triage table and summary."""
    rule_count = sum(1 for d in decisions if d["rule_handled"])
    llm_count = len(decisions) - rule_count
    undecided = sum(1 for d in decisions if d["disposition"] not in DISPOSITIONS)

    print(f"\n{'ID':<6} {'Disposition':<12} {'Rule?':<6} Reason")
    print(f"{'─'*6} {'─'*12} {'─'*6} {'─'*50}")
    for d in decisions:
        rule_str = "yes" if d["rule_handled"] else "LLM"
        print(f"{d['id']:<6} {d['disposition']:<12} {rule_str:<6} {d['reason']}")

    print(f"\nTotal: {len(decisions)}  |  Rule-handled: {rule_count}  |  LLM: {llm_count}  |  undecided: {undecided}")

    # Disposition breakdown
    from collections import Counter
    counts = Counter(d["disposition"] for d in decisions)
    print(f"Breakdown: {dict(counts)}")

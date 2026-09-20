# CAPABILITIES.md — InboxHero

**Student:** [Your Name], cert-aai-2026-06-0006
**Repository:** https://github.com/yashw/inboxhero

Run everything through one entry point:

```
python demo.py --cap R1        # one capability
python demo.py --all           # all of them, in the order below
```

---

## Part 1: The Inbox

**Messages processed: 100**

The inbox belongs to **Melon Rusk**, owner of **SpaceY** (an aerospace company).
All 100 messages are in `inbox.json` as a flat JSON array. 77 are unread, 23 are read.

### Message format

Each message is a JSON object with exactly these keys:

| key | type | notes |
|-----|------|-------|
| `id` | string | Unique message identifier, zero-padded (`m001`–`m100`) |
| `thread_id` | string | Thread grouping; messages sharing a `thread_id` belong to the same conversation |
| `from` | string | Sender email address |
| `to` | string | Recipient email address |
| `subject` | string | Subject line; replies are prefixed `Re:` |
| `timestamp` | string | ISO 8601 (`YYYY-MM-DDTHH:MM:SS`), no timezone offset |
| `body` | string | Plain-text email body |
| `unread` | boolean | `true` = unread, `false` = already read |

### Assumptions about the data format

1. **Flat array, not nested.** All 100 messages are top-level elements of a single JSON array — there is no mailbox folder hierarchy.

2. **`to` is the owner's address for incoming mail.** The owner's email is `melon@spacey.com`. Messages where `to` is `melon@spacey.com` are incoming. Two messages (`m058`, `m085`) are outgoing — `from` is `melon@spacey.com` and `to` is a colleague — but they appear in the same flat array because the inbox store does not separate sent mail. Two messages (`m070`, `m099`) are **self-sent** (`from == to == melon@spacey.com`); these are treated as notes-to-self and handled specially (one is a genuine preference instruction, the other is a prompt-injection attempt).

3. **No timezone in timestamps.** All timestamps are bare ISO 8601 without a `Z` or offset. The system assumes they are in the owner's local timezone (Pacific). No timezone conversion is performed.

4. **Thread membership is by `thread_id`, not `In-Reply-To` headers.** There are no `Message-ID`, `References`, or `In-Reply-To` headers. Thread reconstruction relies entirely on the `thread_id` field. Three threads have more than one message:
   - `t-infra` (4 messages: m057–m060) — staging telemetry outage
   - `t-invest` (2 messages: m075–m076) — investor intro call
   - `t-launch` (9 messages: m061–m069) — starship test flight planning (long thread with the actual request buried in m065)

5. **`unread` is a status flag, not a processing gate.** The system processes all 100 messages (both read and unread) for disposition, but only drafts replies for messages where the owner has not already responded in-thread.

6. **Email addresses are the identity layer.** Sender identity is established by the `from` field alone — there is no DKIM/SPF verification. This matters for the phishing and social-engineering messages, which spoof or mimic known correspondents (e.g., `gwynne.nair@spacey.co` vs the real `gwynne@spacey.com`).

---

## The system, in one paragraph

*(System architecture description will go here once the system is built.)*

## Design choices you were asked to state

*(Framework, retrieval, reversible/irreversible, gate, escalation — to be filled after the system is built.)*

## Capabilities

| id | name | tier | one-line claim |
|----|------|------|----------------|
| R1 | Zero the inbox | — | *(to be filled)* |
| R2 | Grounded reply | — | *(to be filled)* |
| R3 | Gate the irreversible | — | *(to be filled)* |
| R4 | Persistent preference | — | *(to be filled)* |
| R5 | Refuse embedded instructions | — | *(to be filled)* |
| R6 | Dashboard | — | *(to be filled)* |
| X1 | *(to be filled)* | — | *(to be filled)* |
| X2 | *(to be filled)* | — | *(to be filled)* |

## Final Report

*(Your four answers go here.)*

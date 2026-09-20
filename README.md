# InboxHero

**Repository:** https://github.com/yashdurgi/InboxHero

InboxHero is an agentic system that takes an inbox from unread to empty by deciding what to do with every message, doing the parts it should do, and refusing the parts it should not.

---

## Architecture

```
inbox.json (100 messages)
    │
    ▼
┌──────────────────────────────────────────────────┐
│  triage.py  (Router)                             │
│  1. Suspicious check  → escalate (rule)          │
│  2. Noise check       → archive  (rule)          │
│  3. Injection check   → escalate (rule)          │
│  4. Everything else   → LLM classify            │
│  → decisions.json, trace.jsonl                   │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  reply.py  (Agent — thread-walk retrieval)       │
│  Walks thread_id, drafts grounded reply,         │
│  records cited_ids. No context → no draft.       │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  gate.py  (Crew coordinator — irreversible gate)│
│  require_approval() → y/n or --dry-run           │
│  send() → outbox/send_<msgid>.json               │
│  Internal non-sensitive = auto-approved           │
│  External/sensitive = human approval required     │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  prefs.py + memory.py  (Persistent preferences)  │
│  prefs.json survives process restart             │
│  CC on legal mail, no meetings before 11am        │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  hostile.py  (Architectural defence)             │
│  Scans for phishing + prompt injection            │
│  Refuses, flags, reports — never deletes         │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  dashboard.py  (Three-pane view)                 │
│  1. Pending Actions  2. Flagged  3. Commitments   │
│  → dashboard.html + dashboard.json                │
└──────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────┐
│  extras.py  (X1, X2, X3 — custom capabilities)   │
│  X1: List unread by sender (Tier A)              │
│  X2: Thread summary (Tier B)                     │
│  X3: Follow-up tracking (Tier B)                │
└──────────────────────────────────────────────────┘
```

## Framework choice

**No framework.** The pipeline is linear (load → triage → draft → gate → dashboard) with one branch (rule-path vs model-path). A crew or graph would have been overhead. See Final Report Q4 below.

## Model

**`gemma3:4b` via Ollama (local, `localhost:11434`)** — used for triage of non-noise messages, reply drafting, thread summaries, and follow-up chases. 60 of 100 messages never reached the model — they were handled by rules. No external API was used.

Configure through environment variables in `config.py`:
- `OLLAMA_URL` (default: `http://localhost:11434`)
- `INBOXHERO_MODEL` (default: `gemma3:4b`)
- `LLM_TIMEOUT` (default: `120`)

## Disposition vocabulary

| Disposition | Meaning |
|---|---|
| `reply` | The owner should send a response |
| `archive` | No action needed; file for reference |
| `defer` | Needs action, but not right now |
| `delegate` | Someone else should handle this |
| `escalate` | Needs the owner's immediate human attention |

## Reversible vs irreversible

| Action | Class | Gate? |
|---|---|---|
| `send` | Irreversible | Yes — `require_approval()` |
| `delete` | Irreversible | Yes — `require_approval()` |
| `draft` | Reversible | No |
| `label` | Reversible | No |
| `archive` | Reversible | No |
| `defer` | Reversible | No |

Deleting is irreversible because the mock mail store has no trash/undo.

## Gate

Both modes are implemented:
- `--dry-run`: prints what it would do, writes nothing to `outbox/`
- Interactive: prompts `y/n` before each external/sensitive send

Only sends to **external recipients** (not `@spacey.com`) or **sensitive messages** (money/legal keywords) are gated. Internal, non-sensitive sends are auto-approved.

## Retrieval

**Thread-walk:** for a given message, collect all messages sharing the same `thread_id`, sort by timestamp, and use earlier messages as context. If no earlier messages exist in the thread, the system says so and drafts nothing.

## Preference demo

- **m071**: "Always CC `gwynne@spacey.com` on legal mail from Sterling & Vance LLP" — affects m072, m073, m074
- **m070**: "No meetings before 11:00am" — affects m009 (9:30am standup), m076 (9:00am investor), m079 (10:00am board review)

Both stored in `prefs.json`, survive a full process restart.

## Running


# One capability at a time
python demo.py --cap R1                    # Processing the inbox and ROuting
python demo.py --cap R2 --msg m060         # Grounded reply (auto-detects m060 if no --msg)
python demo.py --cap R3 --dry-run          # Gate (dry-run)
python demo.py --cap R3                     # Gate (interactive)
python demo.py --cap R4 --store             # Store preferences
python demo.py --cap R4 --recall            # Recall + apply preferences (fresh process)
python demo.py --cap R5                     # Refuse embedded instructions
python demo.py --cap R6                     # Dashboard
python demo.py --cap X1 --sender raj@spacey.com  # List unread by sender
python demo.py --cap X2                     # Thread summary (auto-selects longest)
python demo.py --cap X3                     # Follow-up tracking

# Everything in order
python demo.py --all

## Files

| File | Purpose |
|---|---|
| `demo.py` | Entry point with `--cap` interface |
| `config.py` | Configuration, model access, paths |
| `trace.py` | Structured event logging to `trace.jsonl` |
| `triage.py` | Part 2: Zero the inbox (rules + LLM) |
| `reply.py` | Part 3: Grounded reply (thread-walk retrieval) |
| `gate.py` | Part 4: Gate the irreversible |
| `prefs.py` | Part 5: Standing instructions |
| `memory.py` | Persistent preference store (reused from Assignment 5) |
| `hostile.py` | Part 6: Refuse embedded instructions |
| `dashboard.py` | Part 7: Three-pane dashboard |
| `extras.py` | Part 8: X1, X2, X3 custom capabilities |
| `inbox.json` | The inbox (100 messages) |
| `decisions.json` | R1 output — all 100 dispositions |
| `prefs.json` | R4 output — stored preferences |
| `trace.jsonl` | Full audit trail |
| `outbox/` | Sent messages (one JSON file per message) |
| `dashboard.html` | R6 output — rendered dashboard |
| `dashboard.json` | R6 output — machine-readable dashboard |
| `CAPABILITIES.md` | Human-readable manifest |
| `capabilities.json` | Machine-readable manifest |
| `.env.example` | Example environment variables |

## Final Report

### 1. What did you refuse to automate?

The system deliberately does **not** auto-send any reply to an external recipient or anything touching money or legal. Even when the LLM produces a well-grounded draft (e.g. m075 — investor intro call from aria.f@orbitventures.vc), the send is gated behind a y/n prompt or a --dry-run flag. internal, non-sensitive sends are auto-approved because they are reversible in practice (Melon can walk over to the colleague and correct it), but an email sent to an external investor or a wire instruction cannot be unsent. 

### 2. Where does untrusted text enter your system?

Untrusted text enters through inbox.json — the body and subject fields of every message. The boundary is architectural: email content is passed to the LLM as data inside a user-role message (Draft a reply to this message: ...), never as a system-role instruction. The LLM's output (a draft) is then subjected to a injection checker (check_injection()), which scans for known injection patterns and overrides any disposition to escalate. But the real defence is that even if an injection survives into a draft, it cannot reach send() without passing require_approval() — the Part 4 gate. An attacker would have to defeat the gate (convince a human to type y) to make the system act on their behalf. No instruction in email content can bypass this.

### 3. Who is accountable when it sends the wrong thing?

The human who approved the send is accountable — the gate logs the proposed action, the human's decision (approved/rejected/dry-run), and the outcome to trace.jsonl. Every outbox/send_<msgid>.json file records the message id, the draft text, the timestamp, and the recipient. If the draft is badly worded or factually wrong, the trace shows which earlier messages were cited (cited_ids in the draft event) — so the failure can be traced to either the retrieval (wrong thread messages) or the LLM (hallucinated details). If it was sent to the wrong person, the gate log shows who approved it. The system helps trace back the failure by recording the full chain: read → draft → gate → send, each in trace.jsonl.

### 4. Name your own machinery.

The codebase maps to  concepts as follows: 

----> triage.py is the Router — it inspects each message and decides rule-path vs model-path. 
----> config.py holds the Tasks (dispositions, noise patterns, the ollama_chat() call that every LLM invocation goes through). 
----> gate.py is the coordinator — it orchestrates draft → approve → send and enforces the irreversible-action boundary.
----> reply.py is the Agent that drafts grounded replies using thread-walk retrieval.
----> memory.py + prefs.py are the **Memory** store that persists across runs.
-----> A framework like CrewAI would have given us task delegation and state management for free, but the pipeline here is linear (load → triage → draft → gate → dashboard), and the only branching is rule-vs-LLM and gate-vs-auto — both are simple if statements. Using a framework would have added configuration overhead without simplifying the logic. The one thing we built ourselves that a framework would have provided is the structured trace log (trace.jsonl) — CrewAI has built-in logging, but our version is simpler and tailored to the assignment's evidence requirements.

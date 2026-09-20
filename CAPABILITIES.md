# CAPABILITIES.md 



Run everything through one entry point:

```
python demo.py --cap R1        # one capability
python demo.py --all           # all of them, in the order below
```

---

## The system, in one paragraph

A single Python pipeline, no framework. Messages are loaded from `inbox.json` (100 messages belonging to Melon Rusk, owner of SpaceY). Cheap ones — receipts, newsletters, notifications (60 of 100) — are dispatched by rules before any model is touched. The remaining 40 go through a classify → retrieve → draft → gate sequence. Suspicious domains and prompt-injection patterns are checked first, overriding any disposition to `escalate`. A final pass builds the three-pane dashboard. State that must outlive a run (preferences, the action log) is kept in small JSON files on disk (`prefs.json`, `trace.jsonl`).

## Part 1: The Inbox

**Messages processed: 100**

The inbox belongs to **Melon Rusk**, owner of **SpaceY** (an aerospace company). 77 unread, 23 read.

### Message format

| key | type | notes |
|-----|------|-------|
| `id` | string | Unique, zero-padded (`m001`–`m100`) |
| `thread_id` | string | Thread grouping |
| `from` | string | Sender email |
| `to` | string | Recipient email |
| `subject` | string | Subject line |
| `timestamp` | string | ISO 8601, no timezone |
| `body` | string | Plain-text body |
| `unread` | boolean | `true` = unread |

### Assumptions

1. **Flat JSON array** — all 100 messages are top-level elements, no folder hierarchy.
2. **Owner email is `melon@spacey.com`** — messages where `to` is this address are incoming. Two messages are outgoing (`from` = `melon@spacey.com`). Two are self-sent (`from == to == melon@spacey.com`).
3. **Timestamps are ISO 8601 without timezone** — assumed to be the owner's local timezone. No conversion performed.
4. **Thread membership is by `thread_id` only** — no `Message-ID` or `In-Reply-To` headers. Three threads have >1 message: `t-infra` (4), `t-invest` (2), `t-launch` (9).
5. **`unread` is a status flag, not a processing gate** — all 100 messages are processed for disposition regardless of read state.
6. **Sender identity is the `from` field alone** — no DKIM/SPF. Phishing messages spoof or mimic known correspondents (e.g. `gwynne.nair@spacey.co` vs the real `gwynne@spacey.com`).

## Design choices

- **Framework: none.** The work is a linear pipeline with one branch (rule-path vs model-path). A crew or graph would have been overhead. See Final Report Q4.
- **Model: `gemma3:4b` via Ollama (local).** Used for triage of non-noise messages, reply drafting, thread summaries, and follow-up chases. 60 of 100 messages never reached the model — they were handled by rules.
- **Retrieval: thread-walk.** An inbox carries its own structure in `thread_id`, so walking the thread is both cheaper and more precise than embeddings for this task. Keyword search is the fallback for cross-thread lookups.
- **Reversible vs irreversible.** `send` and `delete` are irreversible and gated. `draft`, `label`, `archive`, and `defer` are reversible and run without a prompt. Deleting is irreversible because the mock store has no trash — once removed, a message cannot be recovered.
- **Where the gate sits.** Only `send()` and `delete()` can cause an irreversible effect, and both call `require_approval()` first. Nothing else in the system can reach them. This is also the Part 6 defence: a hostile message can influence a *draft* but cannot reach a send without passing the gate.
- **Escalation line.** The gate asks for approval only on sends to **external recipients** (not `@spacey.com`) or anything **touching money or legal** (keywords: wire, transfer, payment, invoice, legal, sign, $, etc.). Internal, non-sensitive sends are auto-approved. The trade-off: a wrongly-sent internal reply is possible, in exchange for the user not being asked to approve 18 internal messages.
- **Preference demo.** `m071`: always CC co-founder (`gwynne@spacey.com`) on legal mail from Sterling & Vance LLP. `m070`: no meetings before 11:00am. Both stored in `prefs.json`, survive a full process restart, and change behaviour on the next run.

## Capabilities

| id | name | tier | one-line claim |
|----|------|------|----------------|
| R1 | Zero the inbox | B | every message gets one disposition + reason, 60 by rules, none left |
| R2 | Grounded reply | B | drafts cite the earlier thread message they used; no context → no draft |
| R3 | Gate the irreversible | C | no send/delete without approval or --dry-run; both modes implemented |
| R4 | Persistent preference | C | a stated preference survives a restart; two honoured |
| R5 | Refuse embedded instructions | C | detects, refuses, flags, reports injections; outbox stays empty |
| R6 | Dashboard | C | three panes, commitments cited, multi-source commitment, conflict surfaced |
| X1 | List unread by sender | A | one lookup: lists unread messages from a given sender, no LLM |
| X2 | Thread summary | B | summarises a long thread, extracts the open question |
| X3 | Follow-up tracking | B | finds sent messages nobody answered in 3+ days, drafts a chase |


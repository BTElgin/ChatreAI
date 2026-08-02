# CLAUDE.md

## What this is
A customer support chatbot for **Cadre AI**, an AI strategy and implementation consultancy. It handles common inbound questions from prospective clients, existing clients, and curious visitors, so Cadre's inbound team can focus on high-value conversations. This is a technical assessment project — the goal is a focused, working MVP with explicit trade-offs, not a finished product.

## Scope — what the bot handles
- What Cadre AI does, and whether it serves the asker's industry
- How to book a call with an AI strategist
- How to access the Cadre client portal (to track AI tools, agents, results)
- What the AI Maturity Index is and how to get scored
- Cadre's approach to LLM selection and data security
- What Cadre's services cost (Phase 10) — answered honestly: no published rate card, pricing is scoped per engagement, next step is a call
- Case studies / results Cadre has delivered for clients (Phase 10) — real, client-anonymized results pulled from cadreai.com, not invented
- Anything outside the above → escalate, don't guess

**Why this scope:** these are the exact inbound patterns called out in the brief. Building beyond them risks burning the time budget on cases nobody asked about; not covering all of them risks missing the stated minimum bar.

**Guiding principle — escalation over silent failure:** if the bot isn't confident an answer is correct, it hands off to a human rather than guessing. A wrong answer erodes trust faster than an honest "let me connect you with someone who can help."

## Explicitly out of scope (do not build unless asked)
- No user auth / accounts — **why:** nothing in scope requires identifying the user; adding it would be unused complexity.
- No persistent *multi-session* memory (recalling a prior visit after the browser closes) — **why:** no scenario in the brief requires the bot to recall a prior visit. Memory *within* one open session is a separate matter — now built, see Phase 5 in plan.md.

**Revisited with extra time (see plan.md):** RAG/embeddings retrieval (Phase 8) and real booking integration (Phase 7, shipped) were both originally excluded from the MVP —
- RAG: the knowledge base was small and static enough that a structured file injected into the system prompt was right-sized; reaching for embeddings/a vector store/retrieval tuning before the knowledge base outgrew that would have read as over-engineering, not sophistication.
- Booking integration: a real scheduling integration was a project on its own, not what the MVP was evaluated on.

Both reasons still explain why the *original* MVP didn't include them — extra time is what changed, not the original judgment call.

## Architecture
Flow: **classify intent → answer from knowledge base → escalation check → respond → suggest follow-ups**, implemented as an explicit LangGraph graph — mirroring the same phase-based state machine pattern used in Benchr (TRIAGE → PLANNING → ... → DONE) — rather than folding the logic into one large prompt.

Built around four principles — the same design cornerstones behind a production AI ticket-triage system I've shipped (measured 45% ticket reduction):
- **Fallback logic** — every response either answers from the knowledge base or escalates. Never a silent failure, never a fabricated guess.
- **Observability** — every classification, the knowledge entry used to answer (if any), and every escalation gets logged, so behavior can be measured rather than assumed.
- **Auditability** — it should always be possible to trace *why* the bot answered the way it did, back to a specific knowledge entry.
- **Accountability** — the bot never projects confidence it doesn't have. Outside its scope, it says so plainly and hands off.

- `knowledge/cadre.json` — structured content: services, industries served, AI Maturity Index description, LLM/data-security stance, pricing approach, case studies, booking + portal info. Kept separate from code — this is the data model, treat it as such.
- The system prompt is assembled from that file plus tone/scope instructions at request time. Do not hardcode knowledge directly into a prompt string — load it from the file.
- If a question falls outside the knowledge base's coverage, the bot says so plainly and redirects to booking a call with a human strategist. Never fabricate an answer.
- **Model routing (Phase 10):** `classify` and `suggest_followups` run on `claude-haiku-4-5` (cheap/fast, structured-output-only tasks); `answer` — the one place quality genuinely matters — stays on `claude-opus-5`. `output_config.effort` is omitted for Haiku calls (it 400s there) and kept at `"low"` for Opus calls.
- **Quick-prompt chips:** `STARTER_PROMPTS` in `graph.py` are the 7 common inquiries shown before the first message; `suggest_followups` generates up to 3 contextual follow-ups after every answer, replacing the starter chips — the "grows as you chat deeper" behavior. Gracefully degrades to no chips on failure, same as every other node.
- **Intent taxonomy (Phase 11):** the 7 intents live in one `INTENTS` dict in `graph.py` (description + knowledge keys per intent) — `KNOWN_INTENTS`, `INTENT_KNOWLEDGE_KEYS`, and `INTENT_DESCRIPTIONS` all derive from it. Add a new intent by adding one entry there, not three separate structures. `load_knowledge()` is memoized (`@functools.lru_cache`) since it's called on every chat turn but the file never changes at runtime; `/api/chat` is a sync `def`, not `async def`, so FastAPI runs the blocking Anthropic call in its threadpool instead of stalling the event loop.

## Bot voice
Professional but approachable — matches a B2B consultancy talking to business leaders, not overly casual. If asked something off-topic or silly, redirect politely rather than refusing bluntly.

## Stack
- FastAPI backend, React frontend, single repo
- Backend calls the Anthropic API server-side — the key is never exposed to the client
- Deployed as a single service: FastAPI serves the built React static files, so there's one deploy target and one public URL, not two separate services to wire together
- Chat UI is on-brand, not just functional — colors, fonts, and button/card shapes are pulled directly from cadreai.com's live stylesheet (Phase 9 in plan.md), not guessed. Still minimal in scope: one screen, no dark mode, no animations.
- Two-tier model routing (Phase 10): `claude-haiku-4-5` for classification and follow-up-suggestion generation, `claude-opus-5` for the actual knowledge-grounded answer. Same Anthropic API key, no second provider.

**Why FastAPI + React over Next.js:** lets the classify → answer → escalate flow be built as an explicit LangGraph graph rather than plain functions — a more direct architectural echo of the Benchr pattern, and a stronger System Design & Architecture story than reproducing the same logic in a different language.
**Why single-service deploy:** two separate services would cost real time under the 4-6 hour budget and cut against "deploy early." Serving the built frontend from FastAPI keeps this to one deploy, one URL — the same speed advantage the Next.js option had.
**Why Claude/Anthropic:** Cadre is a named Anthropic partner, and this whole exercise is evaluated through Claude Code — using Claude as the underlying model is thematically and practically consistent.

## Where to use subagents
- `knowledge/cadre.json` content and the React chat UI scaffold are independent of each other — good candidate for splitting into parallel subagent tasks rather than doing serially.
- The LangGraph nodes (classify/answer/escalate) and the FastAPI route wiring around them are another reasonable split.
- The test pass against the 6 scenarios can run as its own subagent once the core loop is wired, rather than blocking main development.

## Conventions
- Small, frequent commits with descriptive messages — never one giant commit at the end
- Python type hints on the backend, TypeScript on the frontend — don't over-engineer either for a project this size
- Read and verify generated code before moving to the next step — don't chain multiple unverified changes
- If something breaks, give me (Claude) the actual error output and relevant context rather than re-running the same prompt

## Known limitations (expected, not hidden)
- Booking links to a real scheduling flow (a Google Calendar Appointment Schedule, configured via the `BOOKING_URL` env var — Phase 7), surfaced both as a header button and as a real markdown link wherever the bot mentions booking. No env var set yet, so it currently points at an obviously-fake placeholder URL. No CRM integration beyond that single link — no lead capture, no sync back to any system.
- No RAG — knowledge base is static and small by design; noted above as the scaling path if needed (Phase 8, not yet built)
- No persistent memory *across* sessions (a closed-and-reopened browser starts fresh) — memory *within* one open session is built (Phase 5)
- UI is on-brand (Phase 9) but still narrow in scope — one screen, no dark mode, no animations, no mobile-specific breakpoints beyond what naturally reflows at a smaller width
- `knowledge/cadre.json` content is a mix now (Phase 10): **services, industries served, and the 7 case studies are pulled from the real cadreai.com** (case studies are anonymized by Cadre themselves, not by us). The **AI Maturity Index tiers, LLM/data-security narrative, and the client portal's exact URL remain plausible content written for this assessment** — no source brief covered those specifics. Pricing is real in *approach* (no published rate card, custom-quoted) but the exact phrasing is written, not copied verbatim.
- Follow-up suggestion quality (Phase 10) isn't covered by the automated test suite beyond "did it return a list without crashing" — judging whether the *specific* suggestions are good is a manual/qualitative call, same limitation as judging classify's real-world accuracy

## Automated tests
`backend/tests/` — pytest coverage (55 tests) for the LangGraph nodes (`classify`, `answer`, `escalation_check`, `respond`, `suggest_followups`, `run_chat`) and the `/api/chat` / `/api/config` endpoints, including the 6 core scenarios below, the 2 Phase 10 topics (pricing, case studies), the Phase 3 edge cases (multi-part, partial-scope, ambiguous, simulated API failure), and model routing (classify/suggest on Haiku, answer on Opus). The Anthropic client is mocked throughout, so the suite is fast, free, deterministic, and needs no `ANTHROPIC_API_KEY`. It regression-tests the deterministic plumbing — escalation logic, knowledge scoping, request validation, error fallback — not Claude's actual classification judgment; that's what the manual pass below is for.

**Mocking isn't a substitute for the manual pass.** Phase 10 shipped a bug (`suggest_followups` always silently returning empty suggestions) that every mocked test passed, because the mock never exercised the real API's structured-output constraints. It only surfaced when tested against a live key. Don't treat green mocked tests as proof a new API-calling code path actually works.

```
cd backend
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest
```

## Manual scenario pass (real Claude — before calling any phase done)
Manually run these six scenarios end to end (the original assessment bar — kept as-is, not renumbered as scope grew):
1. "What does Cadre AI do, and do you work with [industry]?"
2. "How do I book a call with an AI strategist?"
3. "How do I access the client portal?"
4. "What's the AI Maturity Index and how do I get scored?"
5. "How do you decide which LLM to use, and how do you handle data security?"
6. Something clearly outside scope — confirm it escalates instead of guessing

Plus, since Phase 10: "What do your services cost?" (should answer honestly, no invented numbers) and "Do you have case studies?" (should cite the real ones). And check that a full chip-to-chip conversation flows naturally — starter chips on load, contextual follow-up chips after every answer.

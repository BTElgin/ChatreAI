# CLAUDE.md

## What this is
A customer support chatbot for **Cadre AI**, an AI strategy and implementation consultancy. It handles common inbound questions from prospective clients, existing clients, and curious visitors, so Cadre's inbound team can focus on high-value conversations. This is a technical assessment project — the goal is a focused, working MVP with explicit trade-offs, not a finished product.

## Scope — what the bot handles
- What Cadre AI does, and whether it serves the asker's industry
- How to book a call with an AI strategist
- How to access the Cadre client portal (to track AI tools, agents, results)
- What the AI Maturity Index is and how to get scored
- Cadre's approach to LLM selection and data security
- Anything outside the above → escalate, don't guess

**Why this scope:** these are the exact inbound patterns called out in the brief. Building beyond them risks burning the time budget on cases nobody asked about; not covering all of them risks missing the stated minimum bar.

**Guiding principle — escalation over silent failure:** if the bot isn't confident an answer is correct, it hands off to a human rather than guessing. A wrong answer erodes trust faster than an honest "let me connect you with someone who can help."

## Explicitly out of scope (do not build unless asked)
- No user auth / accounts — **why:** nothing in scope requires identifying the user; adding it would be unused complexity.
- No persistent *multi-session* memory (recalling a prior visit after the browser closes) — **why:** no scenario in the brief requires the bot to recall a prior visit. Memory *within* one open session is a separate matter — see Phase 5 in plan.md.

**Revisited with extra time (see Phase 5 in plan.md):** RAG/embeddings retrieval and real booking integration were both originally excluded from the MVP —
- RAG: the knowledge base was small and static enough that a structured file injected into the system prompt was right-sized; reaching for embeddings/a vector store/retrieval tuning before the knowledge base outgrew that would have read as over-engineering, not sophistication.
- Booking integration: a real scheduling integration was a project on its own, not what the MVP was evaluated on.

Both reasons still explain why the *original* MVP didn't include them — extra time is what changed, not the original judgment call.

## Architecture
Flow: **classify intent → answer from knowledge base → escalation check → respond**, implemented as an explicit LangGraph graph — mirroring the same phase-based state machine pattern used in Benchr (TRIAGE → PLANNING → ... → DONE) — rather than folding the logic into one large prompt.

Built around four principles — the same design cornerstones behind a production AI ticket-triage system I've shipped (measured 45% ticket reduction):
- **Fallback logic** — every response either answers from the knowledge base or escalates. Never a silent failure, never a fabricated guess.
- **Observability** — every classification, the knowledge entry used to answer (if any), and every escalation gets logged, so behavior can be measured rather than assumed.
- **Auditability** — it should always be possible to trace *why* the bot answered the way it did, back to a specific knowledge entry.
- **Accountability** — the bot never projects confidence it doesn't have. Outside its scope, it says so plainly and hands off.

- `knowledge/cadre.json` — structured content: services, industries served, AI Maturity Index description, LLM/data-security stance, booking + portal info. Kept separate from code — this is the data model, treat it as such.
- The system prompt is assembled from that file plus tone/scope instructions at request time. Do not hardcode knowledge directly into a prompt string — load it from the file.
- If a question falls outside the knowledge base's coverage, the bot says so plainly and redirects to booking a call with a human strategist. Never fabricate an answer.

## Bot voice
Professional but approachable — matches a B2B consultancy talking to business leaders, not overly casual. If asked something off-topic or silly, redirect politely rather than refusing bluntly.

## Stack
- FastAPI backend, React frontend, single repo
- Backend calls the Anthropic API server-side — the key is never exposed to the client
- Deployed as a single service: FastAPI serves the built React static files, so there's one deploy target and one public URL, not two separate services to wire together
- Minimal chat UI — functional over polished. Don't spend time on styling beyond readable.

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
- No real booking/CRM integration — the bot describes the next step rather than completing it
- No RAG — knowledge base is static and small by design; noted above as the scaling path if needed
- No persistent memory across sessions
- Minimal UI polish — functionality prioritized over visual design given the time budget
- `knowledge/cadre.json` content (services, AI Maturity Index tiers, portal URL) is plausible content written for this assessment, not pulled from real Cadre AI marketing collateral — no source brief with those specifics was available while building

## Test before calling any phase done
Manually run these six scenarios end to end:
1. "What does Cadre AI do, and do you work with [industry]?"
2. "How do I book a call with an AI strategist?"
3. "How do I access the client portal?"
4. "What's the AI Maturity Index and how do I get scored?"
5. "How do you decide which LLM to use, and how do you handle data security?"
6. Something clearly outside scope — confirm it escalates instead of guessing

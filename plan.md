# plan.md

## Phase 0 — Skeleton & Deploy (do this first, before any real logic)
- [x] Scaffold the FastAPI backend with one endpoint (`/api/chat`) that just echoes input back, and a minimal React frontend
- [x] Wire the build so FastAPI serves the built React static files — one service, one deploy target
- [x] Deploy to Render immediately — confirm the public URL works before building anything else — https://chatreai.onrender.com
- [x] Push the initial commit to GitHub

## Phase 1 — Knowledge Base & System Prompt
- [x] Write `knowledge/cadre.json` covering: services, industries served, AI Maturity Index, LLM/data-security approach, booking process, portal access
- [x] Build the system prompt assembly: base instructions + injected knowledge + scope/escalation rules
- [x] Wire `/api/chat` to call the Anthropic API with the assembled prompt

*Subagent opportunity: the knowledge file content and the React chat UI scaffold (Phase 2) don't depend on each other — good candidate to split.*

## Phase 2 — Core Chat Loop
- [x] Build the classify → answer → escalation-check → respond flow as an explicit LangGraph graph (mirroring the Benchr pattern)
- [x] Basic chat UI: message list + input, calling `/api/chat`
- [x] Manually test the 6 scenarios from CLAUDE.md against localhost

--- MVP CUT LINE — everything above this must ship. Everything below is stretch; if time runs out, that's a deliberate, documented call, not a scramble. ---

## Phase 3 — Escalation & Edge Cases
- [x] Handle ambiguous questions, multi-part questions, and questions that are only partially in scope
- [x] Keep escalation language consistent — always points toward booking a call with a human strategist
- [x] Handle basic API failure states (timeout, error) gracefully in the UI, not a blank screen

## Phase 4 — Polish & Redeploy
- [x] Clean up error handling and loading states
- [x] Final commit, redeploy, confirm the public URL reflects the latest build
- [x] Re-run all 6 test scenarios against the deployed URL, not just localhost

## Stretch — only if time remains, note explicitly if skipped
- [x] Log each interaction — classified intent, which knowledge entry answered it (if any), and every escalation with why. Same observability lens used to measure a 45% ticket reduction on a past production AI system. Even console logging counts here; the point is traceability, not infrastructure. — done in Phase 2 as part of the graph itself: `classify`, `answer`, and `escalation_check` each log via `logger.info` (intents matched, knowledge keys used, escalate decision), console-only, no infra added.
- [ ] Note 2-3 specific "if I had more time" items here for the Decisions & Trade-offs segment — e.g. moving the knowledge base to embeddings + retrieval at scale, real CRM/booking integration, session persistence — skipped; substance already covered by the Known limitations section in CLAUDE.md

*Subagent opportunity: the 6-scenario test pass can run as its own subagent once Phase 2 is wired, freeing up the main thread to keep building.*

## Definition of Done (pre-submission gate)
- [x] Deployed public URL is live and current — https://chatreai.onrender.com
- [x] Code pushed to the shared GitHub repo
- [x] CLAUDE.md present at project root
- [x] plan.md present at project root, reflecting what actually got built (update if scope shifted)
- [x] All 6 test scenarios pass against the deployed URL
- [x] Known limitations section in CLAUDE.md reflects reality, not the original plan

--- MVP + polish shipped and verified above. Everything below is additional scope taken on because extra time became available, not part of the original bar. ---

## Phase 5 — Multi-turn Conversation Memory
- [x] Thread message history from the frontend to `/api/chat` (send prior turns, not just the latest message)
- [x] Extend the LangGraph state to carry that history into `classify` and `answer` so follow-up questions ("what about healthcare?") are understood in context instead of answered in isolation
- [x] Decide how far back history goes (whole session vs. a capped window) and whether it affects classify's intent accuracy — capped at the last 20 messages (~10 exchanges); verified against a real multi-turn conversation, not just single messages
- [x] Re-run the 6 core scenarios to confirm single-turn behavior is unaffected

## Phase 6 — Automated Test Suite
- [x] Add pytest and test dependencies to the backend — `requirements-dev.txt` + `pytest.ini`, kept separate from `requirements.txt` so Render's build doesn't install test tooling
- [x] Unit tests for the `classify` / `answer` / `escalation_check` / `respond` / `run_chat` graph nodes, with the Anthropic client mocked so tests don't depend on a live API key or burn real tokens (19 tests, `backend/tests/test_graph.py`)
- [x] Integration tests for `/api/chat` covering the 6 core scenarios plus the Phase 3 edge cases (multi-part, partial-scope, ambiguous, simulated API failure), plus request validation and history threading (14 tests, `backend/tests/test_api.py`)
- [x] Document how to run the suite — new "Automated tests" section in CLAUDE.md

33 tests, runs in well under a second, no API key required.

*If time allows: wire this into GitHub Actions so it runs on every push — not required, just the natural next step once the suite exists. Not done here — left as the noted next step, per this phase's own framing.*

## Phase 7 — Real Booking Integration
- [ ] Set up a Google Calendar Appointment Schedule (Google's own public booking-page feature) to stand in for a real Cadre AI strategist's calendar — there's no real Cadre account to connect to, so this is a working booking flow, not a live integration with an actual Cadre system
- [ ] Wire the appointment link into the frontend, reachable from wherever the bot currently says "book a call" (e.g. a button/link surfaced in the chat UI)
- [ ] Update `knowledge/cadre.json`'s booking section and the bot's booking language to point at the real link instead of describing a website page
- [ ] Re-run the 6 core scenarios, particularly the booking one, to confirm the bot's response still makes sense end to end

## Phase 8 — RAG / Embeddings Retrieval
- [ ] Pick an embedding approach and a vector store appropriately lightweight for a knowledge base this size (this is the one item where the added complexity is the whole point being explored, not a means to an end)
- [ ] Chunk `knowledge/cadre.json` into retrievable units and embed them
- [ ] Replace `answer`'s fixed knowledge-key lookup with a retrieval step: embed the user's message, retrieve the top-k relevant chunks, inject those into the answer prompt
- [ ] Confirm answers stay grounded (no fabrication) and the 6 core scenarios still pass with retrieval in place of the fixed intent → knowledge-key mapping

*Subagent opportunity: Phases 5-8 are largely independent of each other (memory, tests, booking, retrieval each touch different parts of the system) — reasonable to parallelize rather than doing them strictly in order.*

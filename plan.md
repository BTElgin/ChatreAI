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
- [x] Set up a Google Calendar Appointment Schedule (Google's own public booking-page feature) to stand in for a real Cadre AI strategist's calendar — there's no real Cadre account to connect to, so this is a working booking flow, not a live integration with an actual Cadre system. **Decision: placeholder for now** (see `app/config.py`'s `BOOKING_URL` env var, defaults to an obviously-fake URL) — set the real appointment-schedule link on Render whenever it exists, no code change needed
- [x] Wire the appointment link into the frontend, reachable from wherever the bot currently says "book a call" — a persistent "Book a Call" button in the header (fetched from a new `GET /api/config` endpoint), plus the bot's own escalation/booking text now renders the phrase as a real markdown link instead of plain text
- [x] Update `knowledge/cadre.json`'s booking section and the bot's booking language to point at the real link instead of describing a website page — `load_knowledge()` injects `BOOKING_URL` into `booking.url` at load time; `ANSWER_VOICE` instructs the model to format it as a markdown link
- [x] Re-run the 6 core scenarios, particularly the booking one, to confirm the bot's response still makes sense end to end

## Phase 8 — RAG / Embeddings Retrieval
- [ ] Pick an embedding approach and a vector store appropriately lightweight for a knowledge base this size (this is the one item where the added complexity is the whole point being explored, not a means to an end)
- [ ] Chunk `knowledge/cadre.json` into retrievable units and embed them
- [ ] Replace `answer`'s fixed knowledge-key lookup with a retrieval step: embed the user's message, retrieve the top-k relevant chunks, inject those into the answer prompt
- [ ] Confirm answers stay grounded (no fabrication) and the 6 core scenarios still pass with retrieval in place of the fixed intent → knowledge-key mapping

*Subagent opportunity: Phases 5-8 are largely independent of each other (memory, tests, booking, retrieval each touch different parts of the system) — reasonable to parallelize rather than doing them strictly in order.*

## Phase 9 — Brand Alignment (unplanned, requested after Phase 7)
- [x] Pull real design tokens from cadreai.com's live stylesheet — colors, fonts, button/card shapes — rather than guessing at a brand palette
- [x] Rebrand the chat UI to match: sand/cream background (`#faf9f6`/`#f2efe4`), Inter Tight headline with their red-accent-on-part-of-the-title treatment, Inter body text, black pill buttons (Send, Book a Call), red user bubbles, cream assistant bubbles with a hairline border, blue in-message links — error state kept visually distinct from both
- [x] Verify in a real browser, locally and on the live deployed URL — no console errors, no regression to the backend (36/36 tests still pass, this was a frontend-only change)

## Phase 10 — Quick-Prompt Chips, Model Routing & Real Content (unplanned, requested instead of Phase 8)
- [x] Pull real content from cadreai.com (services, industries, 7 real client-anonymized case studies, confirmed no public pricing page) and replace the Phase 1 invented services/industries lists with it; add honest `pricing` content ("custom-quoted, book a call" — not fabricated numbers) and a `case_studies` knowledge section
- [x] Add `pricing` and `case_studies` as two new classifiable intents (7 known intents total)
- [x] Model routing: `classify` and the new `suggest_followups` node run on `claude-haiku-4-5` (cheap/fast, structured-output-only tasks); `answer` stays on `claude-opus-5` (the one place answer quality matters). Note: `output_config.effort` errors on Haiku 4.5 — must be omitted for Haiku calls, unlike the Opus calls which keep `effort: "low"`
- [x] Starter quick-prompt chips for the 7 common inquiries, shown before the first message; clicking one sends it immediately
- [x] Dynamic follow-up chips: after every answer, a new `suggest_followups` graph node (Haiku) generates up to 3 contextual follow-up questions, replacing the starter chips — this is the "grows as you chat deeper" behavior. Gracefully degrades to no chips on failure, same fallback philosophy as the rest of the graph
- [x] Bug found and fixed during manual (non-mocked) verification: `suggest_followups` initially appended the just-given answer as a trailing `assistant` message, which Anthropic's structured-output mode rejects as a disallowed prefill (400) — silently and gracefully degraded to empty suggestions every time in the mocked tests, never actually surfaced until tested against the real API. Fixed by folding the exchange into a final `user`-role message instead. **Lesson: mocked tests alone can't catch a real API contract violation — the manual pass against a live key remains essential, not just a formality.**
- [x] Re-verified all core scenarios (including the 2 new topics) and a full chip-to-chip conversation in a real browser, locally and confirmed no regressions (54/54 backend tests)

## Phase 11 — Code Cleanup (unplanned, requested after "is the written code clean?")
- [x] Reviewed the full hand-written codebase (backend + frontend) via 4 parallel review agents, each on a distinct angle — Reuse, Simplification, Efficiency, Altitude — same methodology as the `/simplify` skill, applied to full files rather than a diff since the repo had nothing uncommitted at review time
- [x] `graph.py`: consolidated `KNOWN_INTENTS` / `INTENT_KNOWLEDGE_KEYS` / `INTENT_DESCRIPTIONS` (three hand-kept-in-sync structures) into one `INTENTS` dict that the other three now derive from — adding an intent is now one entry, not three
- [x] `graph.py`: extracted a `_first_text()` helper for pulling the text block out of an Anthropic response (was duplicated identically in `classify`, `answer`, and `suggest_followups`); extended `_conversation()` to take an optional `final_message` override so `suggest_followups` reuses it instead of hand-rolling its own messages list
- [x] `graph.py`: fixed an O(n²) dedup loop in `answer()` (`keys.extend(... if k not in keys)` inside a loop) to a single `dict.fromkeys(...)` pass — no behavior change, matters only as the intent-to-knowledge-key lists grow
- [x] `prompt.py`: `load_knowledge()` now memoized with `@functools.lru_cache` — it was re-reading and re-parsing `cadre.json` from disk on every single chat turn; confirmed safe since nothing downstream mutates the returned dict in place
- [x] `main.py`: `/api/chat` changed from `async def` to `def` — it does a blocking synchronous Anthropic API call, so under `async def` it was blocking the whole event loop for the duration of every request; FastAPI/Starlette now runs it in its threadpool executor instead
- [x] Test suite: `classify_response()` / `suggestions_response()` helpers were duplicated identically across `test_graph.py` and `test_api.py` — moved into `conftest.py`, both test files import them now instead of redefining
- [x] Added a new test (`test_every_intent_knowledge_key_exists_in_the_knowledge_base`) asserting every `INTENT_KNOWLEDGE_KEYS` value actually exists as a key in `load_knowledge()` — a silent-narrowing risk the Altitude review flagged: a typo'd knowledge key would previously fail silently (`answer()` filters to keys present in the dict) rather than erroring
- [x] Skipped one review finding: removing the LangGraph `StateGraph` machinery in favor of a plain function chain. Not applied — it contradicts a documented, intentional architectural decision (see CLAUDE.md's Architecture section on why LangGraph was chosen to mirror the Benchr pattern), and the reviewing agent itself flagged that tension rather than treating it as a clear-cut simplification
- [x] Full backend suite re-run after every change (55/55 passing, up from 54 — the one new test), plus a live-API smoke test (not just mocks) of `run_chat()` covering a fresh single-turn question and a multi-turn follow-up, confirming the refactored `_conversation`/`_first_text`/`INTENTS` code paths still produce correct real-API requests and responses

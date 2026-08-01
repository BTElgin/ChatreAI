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

## Phase 5 — Extended Capabilities (extra time available post-MVP)
- [ ] Multi-turn conversation memory: thread message history through `/api/chat` and the LangGraph state so follow-up questions ("what about healthcare?") use context from earlier in the same session, instead of every message being answered in isolation
- [ ] Automated test suite: pytest coverage for the classify/answer/escalation_check graph nodes and the `/api/chat` endpoint, covering the 6 core scenarios plus the Phase 3 edge cases (multi-part, partial-scope, ambiguous, simulated API failure) — replaces manual curl/browser testing as the regression check
- [ ] Real booking integration: replace the text-only "book a call" redirect with an embedded scheduling widget, so booking happens in-product
- [ ] RAG / embeddings retrieval: move `knowledge/cadre.json` from a static file to embeddings + vector retrieval — the scaling path CLAUDE.md's original "out of scope" reasoning named for once the knowledge base outgrows a single file

*Subagent opportunity: the test suite and the booking widget are independent of each other and of the memory/RAG changes — reasonable to parallelize.*

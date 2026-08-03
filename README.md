# ChatreAI

A support chatbot for [Cadre AI](https://cadreai.com), an AI strategy and implementation consultancy. It answers common inbound questions from prospects and existing clients — what Cadre does, pricing, booking a call, case studies — and hands off to a human the moment a question falls outside what it actually knows.

**Live:** https://chatreai.onrender.com
**Built with:** [Claude Code](https://claude.com/claude-code), as a technical take-home assessment for Cadre AI.

## Stack

- **Backend:** FastAPI (Python), with the chat logic as an explicit [LangGraph](https://github.com/langchain-ai/langgraph) state machine: `classify → answer → escalation_check → respond → lead_capture → suggest_followups`
- **Frontend:** React + TypeScript (Vite), a floating chat widget styled to match cadreai.com
- **Model:** Anthropic Claude — `claude-haiku-4-5` for classification/follow-up suggestions, `claude-opus-5` for the knowledge-grounded answer
- **Deploy:** single Render web service — FastAPI serves the built React app as static files, so there's one deploy target and one URL

## Running it locally

**Requirements:** Python 3.11+, Node 20+, an Anthropic API key.

```bash
# backend
cd backend
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
cp .env.example .env   # then fill in ANTHROPIC_API_KEY (see Environment variables below)

# frontend
cd ../frontend
npm install
npm run build           # builds into frontend/dist, which FastAPI serves

# run
cd ../backend
.venv/bin/uvicorn app.main:app --reload
```

Open `http://localhost:8000`.

For frontend-only iteration with hot reload, `npm run dev` in `frontend/` runs Vite's dev server separately (proxying API calls to the backend running on port 8000).

### Environment variables

| Variable | Required | Purpose |
|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | Calls the Claude API server-side; the key is never exposed to the client. |
| `BOOKING_URL` | No | Real scheduling link surfaced in-conversation when the bot offers to book a call. Defaults to a placeholder. |
| `LEAD_WEBHOOK_URL` | No | Where captured lead/customer-signal info is POSTed. Until set, the bot logs instead of delivering, and says so honestly rather than faking a confirmation. |

## Tests

```bash
cd backend
.venv/bin/pytest
```

129 tests covering the LangGraph nodes, the lead-capture helpers, and the API endpoints — the Anthropic client is mocked throughout, so the suite is fast, free, and needs no API key. Runs in CI on every push to `main` and every pull request (`.github/workflows/backend-tests.yml`).

Mocked tests aren't a substitute for exercising the real API — see "Automated tests" in [CLAUDE.md](CLAUDE.md) for two real bugs that only surfaced against a live key.

## Project layout

```
backend/
  app/
    main.py       FastAPI app: /api/chat, /api/config, static file mount
    graph.py       LangGraph state machine + prompts
    lead.py         Progressive lead-capture logic
    config.py       Env var loading
    knowledge/
      cadre.json    Structured knowledge base the bot answers from
  tests/
frontend/
  src/
    App.tsx         Chat widget UI
```

## Docs

- [CLAUDE.md](CLAUDE.md) — architecture, scope decisions, bot voice, known limitations
- [plan.md](plan.md) — the phase-by-phase build log, each phase tagged `[MVP]` / `[Polish]` / `[Extension]`

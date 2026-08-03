import logging
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.graph import ESCALATION_MESSAGE, STARTER_PROMPTS, run_chat

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("cadre_chat")

app = FastAPI(title="Cadre AI Chat")


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    text: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]


class ChatResponse(BaseModel):
    message: str
    suggestions: list[str] = []


class ConfigResponse(BaseModel):
    starterPrompts: list[str]


@app.get("/api/config", response_model=ConfigResponse)
async def config() -> ConfigResponse:
    return ConfigResponse(starterPrompts=STARTER_PROMPTS)


@app.post("/api/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    if not request.messages or request.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="messages must end with a user message")

    *history, current = request.messages
    history_dicts = [{"role": m.role, "content": m.text} for m in history]

    try:
        state = run_chat(current.text, history_dicts)
        return ChatResponse(message=state["response"], suggestions=state.get("suggestions", []))
    except Exception:
        logger.exception("chat endpoint failed unexpectedly")
        return ChatResponse(message=ESCALATION_MESSAGE)


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="static")

import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.graph import run_chat

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Cadre AI Chat")


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    state = run_chat(request.message)
    return ChatResponse(message=state["response"])


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="static")

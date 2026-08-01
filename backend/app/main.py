from pathlib import Path

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.prompt import build_system_prompt

load_dotenv()

app = FastAPI(title="Cadre AI Chat")
client = anthropic.Anthropic()
SYSTEM_PROMPT = build_system_prompt()


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    message: str


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    response = client.messages.create(
        model="claude-opus-5",
        max_tokens=1024,
        output_config={"effort": "low"},
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": request.message}],
    )
    text = next((block.text for block in response.content if block.type == "text"), "")
    return ChatResponse(message=text)


FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="static")

import functools
import json
from pathlib import Path

from app.config import BOOKING_URL

KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge" / "cadre.json"


@functools.lru_cache
def load_knowledge() -> dict:
    with KNOWLEDGE_PATH.open() as f:
        data = json.load(f)
    data["booking"]["url"] = BOOKING_URL
    return data

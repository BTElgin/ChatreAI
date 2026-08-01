import json
from pathlib import Path

KNOWLEDGE_PATH = Path(__file__).resolve().parent / "knowledge" / "cadre.json"


def load_knowledge() -> dict:
    with KNOWLEDGE_PATH.open() as f:
        return json.load(f)

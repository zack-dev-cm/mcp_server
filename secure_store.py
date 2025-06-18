import json
import os
from typing import Any, Optional

DATA_DIR = os.path.join(os.path.dirname(__file__), "user_store")
os.makedirs(DATA_DIR, exist_ok=True)


def _path(user_id: str) -> str:
    return os.path.join(DATA_DIR, f"{user_id}.json")


def load_user_data(user_id: str) -> Optional[Any]:
    """Return stored data for *user_id* or ``None`` if not found."""
    path = _path(user_id)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def save_user_data(user_id: str, data: Any) -> None:
    """Persist ``data`` for *user_id*."""
    with open(_path(user_id), "w", encoding="utf-8") as fh:
        json.dump(data, fh)


def delete_user_data(user_id: str) -> None:
    """Delete stored data for *user_id*."""
    try:
        os.remove(_path(user_id))
    except FileNotFoundError:
        pass

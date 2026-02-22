"""CLI authentication — stores credentials locally in ~/.mandarin/auth.json."""

import json
from pathlib import Path
from typing import Optional

AUTH_DIR = Path.home() / ".mandarin"
AUTH_FILE = AUTH_DIR / "auth.json"


def get_cli_user_id() -> Optional[int]:
    """Read ~/.mandarin/auth.json and return user_id, or None if not logged in."""
    auth = get_cli_auth()
    if auth:
        return auth.get("user_id")
    return None


def get_cli_auth() -> Optional[dict]:
    """Read ~/.mandarin/auth.json and return full dict {user_id, email}, or None."""
    if not AUTH_FILE.exists():
        return None
    try:
        data = json.loads(AUTH_FILE.read_text())
        if "user_id" in data and "email" in data:
            return data
        return None
    except (json.JSONDecodeError, OSError):
        return None


def save_cli_auth(user_id: int, email: str) -> None:
    """Write auth.json to ~/.mandarin/."""
    AUTH_DIR.mkdir(parents=True, exist_ok=True)
    AUTH_FILE.write_text(json.dumps({"user_id": user_id, "email": email}))


def clear_cli_auth() -> None:
    """Remove auth.json."""
    if AUTH_FILE.exists():
        AUTH_FILE.unlink()

"""In-memory, per-session state only. No database, no disk persistence --
everything here vanishes when the server process stops, matching the "no
persistent storage of my data" requirement.
"""
import secrets
from dataclasses import dataclass
from typing import Optional


@dataclass
class SessionData:
    token_info: Optional[dict] = None      # access_token, refresh_token, expires_at
    oauth_state: Optional[str] = None       # CSRF state for the in-flight OAuth request
    last_analysis: Optional[dict] = None    # {source_playlist_id, tracks, breakdown}
    analyze_progress: Optional[dict] = None  # {current, total, done, error} for the in-flight/last /api/analyze run


SESSIONS: dict[str, SessionData] = {}

COOKIE_NAME = "sid"


def new_session_id() -> str:
    return secrets.token_urlsafe(32)


def get_or_create(session_id: Optional[str]) -> tuple[str, SessionData]:
    if session_id and session_id in SESSIONS:
        return session_id, SESSIONS[session_id]
    sid = new_session_id()
    data = SessionData()
    SESSIONS[sid] = data
    return sid, data


def get(session_id: Optional[str]) -> Optional[SessionData]:
    if not session_id:
        return None
    return SESSIONS.get(session_id)

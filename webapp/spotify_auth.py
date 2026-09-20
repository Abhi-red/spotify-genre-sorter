"""Spotify OAuth (Authorization Code flow), implemented directly against
Spotify's Accounts service (not spotipy's file-caching SpotifyOAuth) so
tokens live only in the per-session in-memory store, never on disk.
"""
import os
import time
import secrets
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "secrets.env"))

CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public"

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"


def build_authorize_url(state: str) -> str:
    params = {
        "client_id": CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
    }
    return f"{AUTHORIZE_URL}?{urlencode(params)}"


def new_state() -> str:
    return secrets.token_urlsafe(16)


def _to_token_info(data: dict) -> dict:
    return {
        "access_token": data["access_token"],
        "refresh_token": data.get("refresh_token"),
        "expires_at": time.time() + data.get("expires_in", 3600) - 30,
    }


def exchange_code(code: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    if not resp.ok:
        # Spotify's error body (e.g. "invalid_client", "invalid_grant") is
        # swallowed by raise_for_status()'s generic message -- surface it.
        raise RuntimeError(f"Spotify token exchange failed ({resp.status_code}): {resp.text}")
    return _to_token_info(resp.json())


def do_refresh(refresh_token_value: str) -> dict:
    resp = requests.post(TOKEN_URL, data={
        "grant_type": "refresh_token",
        "refresh_token": refresh_token_value,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
    })
    resp.raise_for_status()
    data = resp.json()
    token_info = _to_token_info(data)
    if not token_info.get("refresh_token"):
        token_info["refresh_token"] = refresh_token_value
    return token_info


def get_valid_access_token(token_info: dict) -> tuple[str, dict]:
    """Returns (access_token, possibly-refreshed token_info)."""
    if time.time() >= token_info["expires_at"]:
        token_info = do_refresh(token_info["refresh_token"])
    return token_info["access_token"], token_info

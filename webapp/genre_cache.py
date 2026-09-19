"""Disk-backed cache of per-source genre/tag lookups, keyed by artist (for
Spotify and MusicBrainz, which are artist-level) or by artist+track (for
Last.fm, which is queried at both artist and track level). This only
caches genre metadata about artists/tracks, not user/session data, so it
doesn't conflict with the session store's "no persistent storage of my
data" design (see session_store.py) -- it's app-wide, not per-user.

Only successful lookups are cached, including a genuinely empty tag list --
a failed request (timeout, non-2xx) must never be cached, so it gets
retried on a later run instead of being permanently treated as "no genres."
"""
import json
import os
from datetime import datetime, timezone

CACHE_FILE = os.path.join(os.path.dirname(__file__), "genre_cache.json")


def _empty():
    return {"artists": {}, "tracks": {}}


def load():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data.setdefault("artists", {})
            data.setdefault("tracks", {})
            return data
        except (json.JSONDecodeError, OSError):
            pass
    return _empty()


def save(cache):
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def _artist_key(artist_name):
    return artist_name.lower()


def _track_key(artist_name, track_name):
    return f"{artist_name.lower()}|{track_name.lower()}"


def get_artist(cache, source, artist_name):
    """Cached tags for (source, artist), or None if not cached yet."""
    entry = cache["artists"].get(_artist_key(artist_name), {}).get(source)
    return entry["tags"] if entry else None


def set_artist(cache, source, artist_name, tags):
    key = _artist_key(artist_name)
    cache["artists"].setdefault(key, {})[source] = {
        "tags": tags,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def get_track(cache, source, artist_name, track_name):
    entry = cache["tracks"].get(_track_key(artist_name, track_name), {}).get(source)
    return entry["tags"] if entry else None


def set_track(cache, source, artist_name, track_name, tags):
    key = _track_key(artist_name, track_name)
    cache["tracks"].setdefault(key, {})[source] = {
        "tags": tags,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }

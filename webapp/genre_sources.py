"""Three independent genre-tag sources used to vote on a track's genre
bucket: Spotify artist genres, Last.fm artist+track tags, and MusicBrainz
artist genre tags. Each function is cache-first, retries transient
failures a couple of times, and never raises -- a source that's down just
returns [] (no vote) so the caller can still proceed with whatever other
sources succeeded.
"""
import os
import time

import requests
from dotenv import load_dotenv

import genre_cache

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "secrets.env"))

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_URL = "https://ws.audioscrobbler.com/2.0/"
LASTFM_MIN_TAG_COUNT = 10
LASTFM_MAX_TAGS = 8

MUSICBRAINZ_URL = "https://musicbrainz.org/ws/2"
MUSICBRAINZ_USER_AGENT = os.getenv(
    "MUSICBRAINZ_USER_AGENT", "SpotifyGenreSorter/1.0 ( contact-not-set )"
)
MUSICBRAINZ_MIN_INTERVAL = 1.05  # MusicBrainz usage policy: max 1 req/sec
_mb_last_call = [0.0]

RETRY_BACKOFFS = [0.5, 1.5]  # seconds between attempts, after the first try


def _get_with_retries(url, **kwargs):
    """GET with a couple of short retries on network errors / 5xx. Returns
    the Response on success, or None if every attempt failed -- callers
    treat None as "source unavailable," not "confirmed no data."""
    last_error = None
    for backoff in [0] + RETRY_BACKOFFS:
        if backoff:
            time.sleep(backoff)
        try:
            resp = requests.get(url, timeout=10, **kwargs)
            if resp.status_code >= 500:
                last_error = f"HTTP {resp.status_code}"
                continue
            resp.raise_for_status()
            return resp
        except requests.RequestException as e:
            last_error = e
    print(f"[genre_sources] giving up on {url}: {last_error}")
    return None


# ---------------------------------------------------------------------
# Spotify -- genres come from GET /artists?ids=... (batched elsewhere via
# spotify_api.get_artists_genres). This function is just the cache-first
# read of a single artist's already-fetched genres.
# ---------------------------------------------------------------------
def get_spotify_artist_genres(artist_id, artist_name, cache):
    cached = genre_cache.get_artist(cache, "spotify", artist_name)
    return cached if cached is not None else []


def prefetch_spotify_genres(access_token, artists, cache, spotify_api_module):
    """artists: iterable of {"id", "name"} dicts. Batch-fetches genres for
    every artist not already cached and stores them, so per-track lookups
    are pure cache reads."""
    to_fetch = {}
    for a in artists:
        aid, name = a.get("id"), a.get("name")
        if not aid or not name:
            continue
        if genre_cache.get_artist(cache, "spotify", name) is None:
            to_fetch[aid] = name
    if not to_fetch:
        return
    try:
        genres_by_id = spotify_api_module.get_artists_genres(access_token, list(to_fetch.keys()))
    except Exception as e:
        print(f"[genre_sources] spotify genre batch fetch failed: {e}")
        return
    for aid, name in to_fetch.items():
        genre_cache.set_artist(cache, "spotify", name, genres_by_id.get(aid, []))


# ---------------------------------------------------------------------
# Last.fm -- artist.gettoptags + track.gettoptags merged, cached per
# artist|track pair.
# ---------------------------------------------------------------------
def _lastfm_tags(params):
    resp = _get_with_retries(LASTFM_URL, params=dict(params, api_key=LASTFM_API_KEY, format="json"))
    if resp is None:
        return None  # source unavailable, don't cache
    data = resp.json()
    raw_tags = data.get("toptags", {}).get("tag", [])
    tags = []
    for t in raw_tags:
        name = t.get("name", "")
        try:
            count = int(t.get("count", 0))
        except (TypeError, ValueError):
            count = 0
        if name and count >= LASTFM_MIN_TAG_COUNT:
            tags.append(name)
    return tags


def get_lastfm_tags(artist_name, track_name, cache):
    cached = genre_cache.get_track(cache, "lastfm", artist_name, track_name)
    if cached is not None:
        return cached

    artist_tags = _lastfm_tags({"method": "artist.gettoptags", "artist": artist_name})
    track_tags = _lastfm_tags({"method": "track.gettoptags", "artist": artist_name, "track": track_name}) \
        if track_name else []

    if artist_tags is None and track_tags is None:
        return []  # both calls failed -- no vote, not cached

    merged = []
    seen = set()
    for tag in (track_tags or []) + (artist_tags or []):
        key = tag.lower()
        if key not in seen:
            seen.add(key)
            merged.append(tag)
    merged = merged[:LASTFM_MAX_TAGS]

    genre_cache.set_track(cache, "lastfm", artist_name, track_name, merged)
    return merged


# ---------------------------------------------------------------------
# MusicBrainz -- search for the artist's MBID, then fetch its genre tags.
# Rate-limited to 1 request/sec across both calls per their usage policy.
# ---------------------------------------------------------------------
def _mb_get(path, params):
    elapsed = time.monotonic() - _mb_last_call[0]
    if elapsed < MUSICBRAINZ_MIN_INTERVAL:
        time.sleep(MUSICBRAINZ_MIN_INTERVAL - elapsed)
    resp = _get_with_retries(
        f"{MUSICBRAINZ_URL}/{path}",
        params=dict(params, fmt="json"),
        headers={"User-Agent": MUSICBRAINZ_USER_AGENT},
    )
    _mb_last_call[0] = time.monotonic()
    return resp


def get_musicbrainz_artist_genres(artist_name, cache):
    cached = genre_cache.get_artist(cache, "musicbrainz", artist_name)
    if cached is not None:
        return cached

    search_resp = _mb_get("artist", {"query": f'artist:"{artist_name}"', "limit": 1})
    if search_resp is None:
        return []  # unavailable, don't cache

    artists = search_resp.json().get("artists", [])
    if not artists:
        genre_cache.set_artist(cache, "musicbrainz", artist_name, [])
        return []

    mbid = artists[0]["id"]
    lookup_resp = _mb_get(f"artist/{mbid}", {"inc": "genres"})
    if lookup_resp is None:
        return []  # unavailable, don't cache

    genres = [g["name"] for g in lookup_resp.json().get("genres", []) if g.get("name")]
    genre_cache.set_artist(cache, "musicbrainz", artist_name, genres)
    return genres

"""Thin wrapper over the Spotify Web API using `requests` directly (token
handling stays in the per-session store, not spotipy's own client).
Handles pagination and 429 rate-limit backoff.

Deliberately never calls /audio-features, /audio-analysis, /recommendations
or /related-artists -- Spotify 403s those for apps created after Nov 2024.
Genre detection instead comes entirely from Last.fm (see genre.py).
"""
import time
import requests

BASE = "https://api.spotify.com/v1"


class SpotifyAPIError(Exception):
    pass


def _request(method, url, access_token, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {access_token}"
    for _ in range(5):
        resp = requests.request(method, url, headers=headers, **kwargs)
        if resp.status_code == 429:
            retry_after = int(resp.headers.get("Retry-After", "1"))
            time.sleep(retry_after + 0.5)
            continue
        if resp.status_code >= 400:
            raise SpotifyAPIError(f"{method} {url} -> {resp.status_code}: {resp.text[:300]}")
        return resp
    raise SpotifyAPIError(f"{method} {url} -> repeated 429, giving up")


def get_current_user(access_token):
    return _request("GET", f"{BASE}/me", access_token).json()


def get_artists_genres(access_token, artist_ids):
    """artist_id -> genres list, batched 50 ids per call via GET /artists.
    Apps without Extended Quota Mode get back an empty genres array per
    artist rather than a 403, so this call succeeds but may yield []."""
    genres_by_id = {}
    for i in range(0, len(artist_ids), 50):
        chunk = artist_ids[i:i + 50]
        resp = _request("GET", f"{BASE}/artists", access_token, params={"ids": ",".join(chunk)}).json()
        for artist in resp.get("artists", []) or []:
            if artist and artist.get("id"):
                genres_by_id[artist["id"]] = artist.get("genres", []) or []
    return genres_by_id


def _extract_track_count(playlist_obj):
    # This app's API has been observed returning the track summary block
    # under "items" instead of the documented "tracks" key -- handle both.
    for key in ("tracks", "items"):
        block = playlist_obj.get(key)
        if isinstance(block, dict) and "total" in block:
            return block["total"]
    return None


def get_owned_playlists(access_token, user_id):
    playlists = []
    url = f"{BASE}/me/playlists"
    params = {"limit": 50}
    while url:
        resp = _request("GET", url, access_token, params=params).json()
        for p in resp.get("items", []):
            if p.get("owner", {}).get("id") == user_id:
                playlists.append({
                    "id": p["id"],
                    "name": p["name"],
                    "track_count": _extract_track_count(p),
                })
        url = resp.get("next")
        params = None  # `next` already carries its own query string
    return playlists


def _extract_track(entry):
    # Same schema quirk seen throughout this project: this app's API wraps
    # the track under "item" rather than the documented "track" key.
    # Handle both to be safe.
    track = entry.get("item")
    if track is None:
        track = entry.get("track")
    if track is None or track.get("id") is None or track.get("episode") or track.get("is_local"):
        return None
    return track


def get_all_playlist_tracks(access_token, playlist_id):
    """Every track in a playlist, following pagination. Skips local files,
    unavailable tracks, and podcast episodes.

    Uses /playlists/{id}/items, not the documented /playlists/{id}/tracks --
    this app's API returns 403 on /tracks (observed throughout this
    project; spotipy 2.26.0 itself calls /items under the hood, matching)."""
    tracks = []
    url = f"{BASE}/playlists/{playlist_id}/items"
    params = {"limit": 100}
    while url:
        resp = _request("GET", url, access_token, params=params).json()
        for entry in resp.get("items", []):
            track = _extract_track(entry)
            if track:
                tracks.append(track)
        url = resp.get("next")
        params = None
    return tracks


def add_tracks_to_playlist(access_token, playlist_id, uris):
    # Same /items endpoint, and this app's API takes a bare list of URIs as
    # the payload rather than the documented {"uris": [...]} wrapper.
    for i in range(0, len(uris), 100):
        chunk = uris[i:i + 100]
        _request("POST", f"{BASE}/playlists/{playlist_id}/items", access_token, json=chunk)


def remove_tracks_from_playlist(access_token, playlist_id, uris):
    for i in range(0, len(uris), 100):
        chunk = uris[i:i + 100]
        payload = {"items": [{"uri": u} for u in chunk]}
        _request("DELETE", f"{BASE}/playlists/{playlist_id}/items", access_token, json=payload)

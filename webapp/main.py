"""FastAPI backend for the Spotify genre-sorter web app.

Run with: uvicorn main:app --host 127.0.0.1 --port 8080
(port 8080 is fixed by SPOTIFY_REDIRECT_URI = http://127.0.0.1:8080 already
registered in the Spotify Developer Dashboard for this app -- no path, so
the OAuth callback is handled at "/" itself, disambiguated by query params.)
"""
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.concurrency import run_in_threadpool

import session_store
import spotify_auth
import spotify_api
import genre as genre_mod
import genre_cache
import genre_sources

app = FastAPI()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

COOKIE = session_store.COOKIE_NAME

# Shared, disk-backed genre-source cache (artist/track tag metadata, not
# user data -- app-wide, loaded once and saved as /api/analyze progresses).
GENRE_CACHE = genre_cache.load()


def _sid(request: Request) -> str | None:
    return request.cookies.get(COOKIE)


def _require_session(request: Request):
    """Returns (sid, session_data) or None if not logged in / no valid token."""
    sess = session_store.get(_sid(request))
    if sess is None or sess.token_info is None:
        return None
    return sess


def _access_token(sess: session_store.SessionData) -> str:
    token, refreshed = spotify_auth.get_valid_access_token(sess.token_info)
    sess.token_info = refreshed
    return token


# ---------------------------------------------------------------------
# Root: OAuth callback lands here (redirect_uri has no path), otherwise
# serve the frontend SPA.
# ---------------------------------------------------------------------
@app.get("/")
def root(request: Request, code: str | None = None, state: str | None = None, error: str | None = None):
    if error is not None:
        return JSONResponse({"error": error}, status_code=400)

    if code is not None:
        sid, sess = session_store.get_or_create(_sid(request))
        if state != sess.oauth_state:
            return JSONResponse({"error": "state mismatch, possible CSRF"}, status_code=400)
        token_info = spotify_auth.exchange_code(code)
        sess.token_info = token_info
        sess.oauth_state = None
        resp = RedirectResponse(url="/")
        resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax")
        return resp

    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/login")
def login(request: Request):
    sid, sess = session_store.get_or_create(_sid(request))
    state = spotify_auth.new_state()
    sess.oauth_state = state
    resp = RedirectResponse(url=spotify_auth.build_authorize_url(state))
    resp.set_cookie(COOKIE, sid, httponly=True, samesite="lax")
    return resp


@app.get("/api/logout")
def logout(request: Request):
    sid = _sid(request)
    if sid and sid in session_store.SESSIONS:
        del session_store.SESSIONS[sid]
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(COOKIE)
    return resp


@app.get("/api/me")
def me(request: Request):
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"logged_in": False})
    token = _access_token(sess)
    user = spotify_api.get_current_user(token)
    return {"logged_in": True, "id": user.get("id"), "display_name": user.get("display_name") or user.get("id")}


@app.get("/api/playlists")
def playlists(request: Request):
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    token = _access_token(sess)
    user = spotify_api.get_current_user(token)
    pls = spotify_api.get_owned_playlists(token, user["id"])
    return {"playlists": pls}


def _classify_playlist(token, raw_tracks):
    """All blocking work for one analyze pass (Spotify batch genre fetch +
    per-track multi-source voting). Runs off the event loop via
    run_in_threadpool -- this does real network I/O (including
    MusicBrainz's mandatory 1 req/sec throttle), which would otherwise
    freeze every other request the server needs to handle for the whole
    duration of the analysis."""
    # One batched pass to populate Spotify genres for every artist on this
    # page, so the per-track classification below is a pure cache read for
    # that source instead of one API call per track.
    genre_sources.prefetch_spotify_genres(
        token,
        (t["artists"][0] for t in raw_tracks if t.get("artists")),
        GENRE_CACHE,
        spotify_api,
    )

    total = len(raw_tracks)
    tracks = []
    breakdown = {}
    for i, t in enumerate(raw_tracks):
        name = t.get("name", "<unknown>")
        artists = t.get("artists", [])
        artist = artists[0]["name"] if artists else "<unknown artist>"
        uri = t.get("uri")
        result = genre_mod.classify_track_multi_source(t, GENRE_CACHE)

        if result["confidence"] == "high":
            label = result["bucket"]
        elif result["confidence"] == "low":
            label = genre_mod.NEEDS_REVIEW
        else:
            label = genre_mod.UNMATCHED

        tracks.append({
            "uri": uri,
            "name": name,
            "artist": artist,
            "genre": label,
            "confidence": result["confidence"],
            "votes": result["votes"],
            "raw_tags": result["raw_tags"],
        })
        breakdown[label] = breakdown.get(label, 0) + 1

        if (i + 1) % 10 == 0 or i + 1 == total:
            print(f"[analyze] classified {i + 1}/{total} tracks")
        if i % 25 == 24:
            genre_cache.save(GENRE_CACHE)  # incremental save so a mid-run crash doesn't lose lookups

    genre_cache.save(GENRE_CACHE)
    return tracks, breakdown


@app.post("/api/analyze")
async def analyze(request: Request):
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    body = await request.json()
    source_playlist_id = body.get("source_playlist_id")
    if not source_playlist_id:
        return JSONResponse({"error": "source_playlist_id required"}, status_code=400)

    token = _access_token(sess)
    raw_tracks = await run_in_threadpool(spotify_api.get_all_playlist_tracks, token, source_playlist_id)
    print(f"[analyze] fetched {len(raw_tracks)} tracks, classifying...")
    tracks, breakdown = await run_in_threadpool(_classify_playlist, token, raw_tracks)

    sess.last_analysis = {
        "source_playlist_id": source_playlist_id,
        "tracks": tracks,
        "breakdown": breakdown,
    }
    sess.pending_plan = None  # invalidate any stale preview from a prior analysis

    return {
        "source_playlist_id": source_playlist_id,
        "total_tracks": len(tracks),
        "breakdown": breakdown,
        "tracks": tracks,
    }


@app.post("/api/resolve_review")
async def resolve_review(request: Request):
    """body: {resolutions: {uri: bucket_name_or_null}}. Manually assigns a
    genre bucket to "Needs Review" tracks (or leaves them for later, if
    the resolution is null/absent). Recomputes breakdown and invalidates
    any stale preview so mapping/preview reflect the updated genres."""
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if sess.last_analysis is None:
        return JSONResponse({"error": "run /api/analyze first"}, status_code=400)

    body = await request.json()
    resolutions = body.get("resolutions", {})

    tracks = sess.last_analysis["tracks"]
    for t in tracks:
        if t["uri"] in resolutions and resolutions[t["uri"]]:
            t["genre"] = resolutions[t["uri"]]

    breakdown = {}
    for t in tracks:
        breakdown[t["genre"]] = breakdown.get(t["genre"], 0) + 1
    sess.last_analysis["breakdown"] = breakdown
    sess.pending_plan = None  # stale preview from before this resolution

    return {
        "total_tracks": len(tracks),
        "breakdown": breakdown,
        "tracks": tracks,
    }


@app.post("/api/preview")
async def preview(request: Request):
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if sess.last_analysis is None:
        return JSONResponse({"error": "run /api/analyze first"}, status_code=400)

    body = await request.json()
    mapping = body.get("mapping", {})  # genre label -> target playlist id (falsy = don't sort)

    token = _access_token(sess)
    user = spotify_api.get_current_user(token)
    owned = {p["id"]: p["name"] for p in spotify_api.get_owned_playlists(token, user["id"])}

    tracks = sess.last_analysis["tracks"]
    by_target: dict[str, list] = {}
    unmapped = []
    for t in tracks:
        target_id = mapping.get(t["genre"])
        if not target_id:
            unmapped.append(t)
            continue
        if target_id not in owned:
            return JSONResponse({"error": f"unknown target playlist {target_id}"}, status_code=400)
        by_target.setdefault(target_id, []).append(t)

    result = {
        "targets": [
            {"playlist_id": pid, "playlist_name": owned[pid], "tracks": ts, "count": len(ts)}
            for pid, ts in by_target.items()
        ],
        "unmapped": unmapped,
        "unmapped_count": len(unmapped),
    }
    sess.pending_plan = {"mapping": mapping, "preview": result}
    return result


@app.post("/api/confirm")
async def confirm(request: Request):
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if sess.pending_plan is None:
        return JSONResponse({"error": "run /api/preview first"}, status_code=400)

    body = await request.json()
    remove_from_source = bool(body.get("remove_from_source", False))

    token = _access_token(sess)
    preview_data = sess.pending_plan["preview"]
    source_playlist_id = sess.last_analysis["source_playlist_id"]

    results = []
    all_moved_uris = []
    for target in preview_data["targets"]:
        uris = [t["uri"] for t in target["tracks"]]
        spotify_api.add_tracks_to_playlist(token, target["playlist_id"], uris)
        results.append({
            "playlist_id": target["playlist_id"],
            "playlist_name": target["playlist_name"],
            "added": len(uris),
        })
        all_moved_uris.extend(uris)

    removed_count = 0
    if remove_from_source and all_moved_uris:
        spotify_api.remove_tracks_from_playlist(token, source_playlist_id, all_moved_uris)
        removed_count = len(all_moved_uris)

    sess.pending_plan = None  # consumed -- can't double-apply the same plan

    return {
        "results": results,
        "removed_from_source": removed_count,
        "unmapped_left_in_place": preview_data["unmapped_count"],
    }

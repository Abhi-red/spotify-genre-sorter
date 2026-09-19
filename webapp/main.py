"""FastAPI backend for the Spotify genre-sorter web app.

Run with: uvicorn main:app --host 127.0.0.1 --port 8080
(port 8080 is fixed by SPOTIFY_REDIRECT_URI = http://127.0.0.1:8080 already
registered in the Spotify Developer Dashboard for this app -- no path, so
the OAuth callback is handled at "/" itself, disambiguated by query params.)
"""
import asyncio
import os

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
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


def _index_html() -> str:
    """Cache-busts app.js with its mtime so a browser that already cached
    an old copy (from before this file existed, so it never saw the
    no-store header below) is forced onto a URL it has never fetched,
    instead of silently continuing to run stale JS against a newer
    backend -- see the /api/analyze response-shape mismatch this caused."""
    path = os.path.join(STATIC_DIR, "index.html")
    js_mtime = int(os.path.getmtime(os.path.join(STATIC_DIR, "app.js")))
    with open(path, "r", encoding="utf-8") as f:
        html = f.read()
    return html.replace('/static/app.js"', f'/static/app.js?v={js_mtime}"')


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """Local dev tool, not a deployed site -- a stale cached app.js/index.html
    silently talking to a newer backend (mismatched response shapes) is a
    worse failure mode than always refetching a few small static files."""
    response = await call_next(request)
    if request.url.path.startswith("/static/") or request.url.path == "/":
        response.headers["Cache-Control"] = "no-store"
    return response

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

    return HTMLResponse(_index_html())


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


def _classify_playlist(token, raw_tracks, progress):
    """All blocking work for one analyze pass (Spotify batch genre fetch +
    per-track multi-source voting). Runs off the event loop via
    run_in_threadpool -- this does real network I/O (including
    MusicBrainz's mandatory 1 req/sec throttle), which would otherwise
    freeze every other request the server needs to handle for the whole
    duration of the analysis.

    progress is a plain dict the caller polls from another request
    (/api/analyze/status) -- mutated in place as tracks are classified."""
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
        label = result["genre"]

        tracks.append({
            "uri": uri,
            "name": name,
            "artist": artist,
            "genre": label,
            "raw_tags": result["raw_tags"],
            "display_genres": result["display_genres"],
        })
        breakdown[label] = breakdown.get(label, 0) + 1
        progress["current"] = i + 1

        if (i + 1) % 10 == 0 or i + 1 == total:
            print(f"[analyze] classified {i + 1}/{total} tracks")
        if i % 25 == 24:
            genre_cache.save(GENRE_CACHE)  # incremental save so a mid-run crash doesn't lose lookups

    genre_cache.save(GENRE_CACHE)
    return tracks, breakdown


async def _run_analysis(sess: session_store.SessionData, token: str, source_playlist_id: str, raw_tracks: list):
    """Background job: classifies every track and, when done, stores the
    result on the session. sess.analyze_progress is the only channel back
    to the polling /api/analyze/status handler, so every exit path
    (success or failure) must set progress["done"] = True."""
    progress = sess.analyze_progress
    try:
        tracks, breakdown = await run_in_threadpool(_classify_playlist, token, raw_tracks, progress)
        sess.last_analysis = {
            "source_playlist_id": source_playlist_id,
            "tracks": tracks,
            "breakdown": breakdown,
        }
    except Exception as e:
        progress["error"] = str(e)
    finally:
        progress["done"] = True


@app.post("/api/analyze")
async def analyze(request: Request):
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)

    # A run already in flight for this session -- reattach instead of
    # kicking off a duplicate (e.g. a page reload while the first run was
    # still classifying, followed by hitting Analyse again).
    if sess.analyze_progress is not None and not sess.analyze_progress["done"]:
        return {"already_running": True, **sess.analyze_progress}

    body = await request.json()
    source_playlist_id = body.get("source_playlist_id")
    if not source_playlist_id:
        return JSONResponse({"error": "source_playlist_id required"}, status_code=400)

    token = _access_token(sess)
    raw_tracks = await run_in_threadpool(spotify_api.get_all_playlist_tracks, token, source_playlist_id)
    print(f"[analyze] fetched {len(raw_tracks)} tracks, classifying...")

    sess.analyze_progress = {"current": 0, "total": len(raw_tracks), "done": False, "error": None}
    asyncio.create_task(_run_analysis(sess, token, source_playlist_id, raw_tracks))

    return {"started": True, "total": len(raw_tracks)}


@app.get("/api/analyze/status")
def analyze_status(request: Request):
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if sess.analyze_progress is None:
        return JSONResponse({"error": "no analysis has been started"}, status_code=400)

    progress = sess.analyze_progress
    resp = dict(progress)
    if progress["done"] and not progress["error"] and sess.last_analysis is not None:
        resp["source_playlist_id"] = sess.last_analysis["source_playlist_id"]
        resp["total_tracks"] = len(sess.last_analysis["tracks"])
        resp["breakdown"] = sess.last_analysis["breakdown"]
        resp["tracks"] = sess.last_analysis["tracks"]
    return resp


@app.post("/api/move")
async def move(request: Request):
    """body: {uris: [...], target_playlist_id, remove_from_source}. Adds
    the given tracks to target_playlist_id and, if remove_from_source is
    true, removes them from the analyzed source playlist. Works
    identically for a single track or an entire genre bucket's worth --
    the caller decides scope via which uris it sends. No separate preview
    endpoint: the frontend already holds full track data client-side
    after analyze and builds its own confirm dialog before calling
    this."""
    sess = _require_session(request)
    if sess is None:
        return JSONResponse({"error": "not logged in"}, status_code=401)
    if sess.last_analysis is None:
        return JSONResponse({"error": "run /api/analyze first"}, status_code=400)

    body = await request.json()
    uris = body.get("uris") or []
    target_playlist_id = body.get("target_playlist_id")
    remove_from_source = bool(body.get("remove_from_source", False))
    if not uris:
        return JSONResponse({"error": "uris required"}, status_code=400)
    if not target_playlist_id:
        return JSONResponse({"error": "target_playlist_id required"}, status_code=400)

    token = _access_token(sess)
    await run_in_threadpool(spotify_api.add_tracks_to_playlist, token, target_playlist_id, uris)

    removed = 0
    if remove_from_source:
        source_playlist_id = sess.last_analysis["source_playlist_id"]
        await run_in_threadpool(spotify_api.remove_tracks_from_playlist, token, source_playlist_id, uris)
        removed = len(uris)

    return {"added": len(uris), "removed": removed, "target_playlist_id": target_playlist_id}

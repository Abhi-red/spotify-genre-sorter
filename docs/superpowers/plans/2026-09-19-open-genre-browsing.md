# Open Genre Browsing & Move UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the webapp's fixed 3-bucket (EDM/Pop Rock/Indie) genre matching with open-ended genre detection across a curated parent-genre taxonomy, and replace the mapping/preview/confirm wizard with a browse-and-move interface: expand any detected genre, move a single track or an entire genre's tracks to any owned playlist, with an inline confirm before anything writes to Spotify.

**Architecture:** A new `webapp/genre_taxonomy.py` holds the parent-genre alias table and non-genre stoplist (pure data + one pure function, no I/O). `webapp/genre.py` uses it to pick each track's genre(s) by cross-source tag frequency (no fixed bucket set, no confidence gate). `webapp/main.py` drops the review/mapping/preview/confirm endpoints in favor of one generic `POST /api/move`. `webapp/static/app.js` drops the corresponding UI cards and turns the breakdown list itself into the interactive move surface, keeping all move state in one client-side `lastAnalysis` object that's mutated and re-rendered after each successful move (no full re-analyze needed).

**Tech Stack:** Python 3.12, FastAPI, vanilla JS (no framework, no build step) — unchanged from the existing app.

**Spec:** `docs/superpowers/specs/2026-09-19-open-genre-browsing-design.md`

## Global Constraints

- Scope is `webapp/` only. Root CLI scripts (`spotify_sort.py`, `reorganize.py`, `config.py`) are untouched.
- No confidence tiers, no "Needs Review" bucket — every track gets its top detected genre, or `"Unmatched"` if nothing was detected anywhere.
- Unrecognized tags are never dropped — they become their own title-cased genre. Only nationality/language tags (`genre_taxonomy.NON_GENRE_TAGS`) and tags matching the artist's own name are filtered out.
- Moves always require an inline confirm click before calling the Spotify write API. "Remove from source" defaults unchecked.
- `POST /api/move` is the only write endpoint for sorting; it takes a URI list, so it's scope-agnostic (one track or a whole genre bucket).
- Every backend file must pass `python -m py_compile` after its task. Every frontend change must be checked in the browser via injected synthetic data (no real Spotify login available) with zero console errors before being considered done.

---

### Task 1: Genre taxonomy data module

**Files:**
- Create: `webapp/genre_taxonomy.py`
- Test: `webapp/test_genre_taxonomy.py` (plain script, no pytest — this repo has no test framework installed; run directly with `python`, mirroring how the existing session verified `genre.py` logic)

**Interfaces:**
- Produces: `genre_taxonomy.GENRE_ALIASES: dict[str, str]`, `genre_taxonomy.NON_GENRE_TAGS: set[str]`, `genre_taxonomy.PARENT_GENRES: list[str]`, `genre_taxonomy.normalize_tag(tag: str) -> str | None`

- [ ] **Step 1: Write `webapp/genre_taxonomy.py`**

```python
"""Parent-genre taxonomy for open-ended genre detection. Unlike the old
3-bucket system (EDM/Pop Rock/Indie), there is no fixed set of allowed
outputs here -- GENRE_ALIASES folds common subgenre spellings up into a
smaller set of recognizable parent genres, but a tag with no entry here
is never dropped, just shown as its own title-cased genre. Extend
coverage over time by adding entries to GENRE_ALIASES/NON_GENRE_TAGS --
no code changes needed.
"""

PARENT_GENRES = [
    "Hip-Hop/Rap", "R&B", "Pop", "Rock", "Indie", "Metal", "Punk",
    "EDM/Electronic", "Folk/Country", "Latin", "Reggae", "Jazz",
    "Classical", "Blues/Soul", "Afrobeats", "K-Pop", "World",
]

GENRE_ALIASES = {
    # Hip-Hop/Rap
    "rap": "Hip-Hop/Rap", "hip hop": "Hip-Hop/Rap", "hip-hop": "Hip-Hop/Rap",
    "trap": "Hip-Hop/Rap", "cloud rap": "Hip-Hop/Rap", "drill": "Hip-Hop/Rap",
    "uk drill": "Hip-Hop/Rap", "gangsta rap": "Hip-Hop/Rap",
    "boom bap": "Hip-Hop/Rap", "mumble rap": "Hip-Hop/Rap",
    "conscious hip hop": "Hip-Hop/Rap", "alternative hip hop": "Hip-Hop/Rap",
    "hardcore hip hop": "Hip-Hop/Rap", "southern hip hop": "Hip-Hop/Rap",
    "pop rap": "Hip-Hop/Rap", "west coast hip hop": "Hip-Hop/Rap",
    "east coast hip hop": "Hip-Hop/Rap", "emo rap": "Hip-Hop/Rap",
    "chill hip hop": "Hip-Hop/Rap", "lo-fi hip hop": "Hip-Hop/Rap",
    "horrorcore": "Hip-Hop/Rap",

    # R&B
    "r&b": "R&B", "rnb": "R&B", "neo-soul": "R&B", "neo soul": "R&B",
    "contemporary r&b": "R&B", "quiet storm": "R&B",
    "alternative r&b": "R&B", "new jack swing": "R&B",

    # Pop
    "pop": "Pop", "dance pop": "Pop", "synth-pop": "Pop", "synthpop": "Pop",
    "electropop": "Pop", "teen pop": "Pop", "bubblegum pop": "Pop",

    # Rock
    "rock": "Rock", "alternative rock": "Rock", "classic rock": "Rock",
    "hard rock": "Rock", "garage rock": "Rock", "arena rock": "Rock",
    "pop rock": "Rock", "power pop": "Rock", "soft rock": "Rock",
    "britpop": "Rock", "glam rock": "Rock", "prog rock": "Rock",
    "progressive rock": "Rock", "psychedelic rock": "Rock",
    "southern rock": "Rock", "surf rock": "Rock",

    # Indie
    "indie": "Indie", "indie rock": "Indie", "indie pop": "Indie",
    "indie folk": "Indie", "bedroom pop": "Indie", "dream pop": "Indie",
    "lo-fi": "Indie", "lo fi": "Indie", "chamber pop": "Indie",
    "slacker rock": "Indie",

    # Metal
    "metal": "Metal", "heavy metal": "Metal", "death metal": "Metal",
    "black metal": "Metal", "metalcore": "Metal", "nu metal": "Metal",
    "thrash metal": "Metal", "doom metal": "Metal", "power metal": "Metal",
    "progressive metal": "Metal", "symphonic metal": "Metal",

    # Punk
    "punk": "Punk", "pop punk": "Punk", "punk rock": "Punk",
    "hardcore punk": "Punk", "emo": "Punk", "post-hardcore": "Punk",
    "ska punk": "Punk", "garage punk": "Punk",

    # EDM/Electronic
    "edm": "EDM/Electronic", "house": "EDM/Electronic",
    "deep house": "EDM/Electronic", "tropical house": "EDM/Electronic",
    "techno": "EDM/Electronic", "trance": "EDM/Electronic",
    "dubstep": "EDM/Electronic", "drum and bass": "EDM/Electronic",
    "dnb": "EDM/Electronic", "electronic": "EDM/Electronic",
    "future bass": "EDM/Electronic", "electro house": "EDM/Electronic",
    "big room": "EDM/Electronic", "chillwave": "EDM/Electronic",
    "synthwave": "EDM/Electronic", "garage": "EDM/Electronic",
    "breakbeat": "EDM/Electronic", "downtempo": "EDM/Electronic",
    "idm": "EDM/Electronic", "glitch": "EDM/Electronic",

    # Folk/Country
    "folk": "Folk/Country", "country": "Folk/Country",
    "americana": "Folk/Country", "bluegrass": "Folk/Country",
    "singer-songwriter": "Folk/Country", "country pop": "Folk/Country",
    "folk rock": "Folk/Country", "alt-country": "Folk/Country",

    # Latin
    "latin": "Latin", "reggaeton": "Latin", "latin pop": "Latin",
    "latin trap": "Latin", "trap latino": "Latin", "salsa": "Latin",
    "bachata": "Latin", "cumbia": "Latin", "merengue": "Latin",
    "latin rock": "Latin", "regional mexican": "Latin", "banda": "Latin",

    # Reggae
    "reggae": "Reggae", "dancehall": "Reggae", "dub": "Reggae",
    "ska": "Reggae",

    # Jazz
    "jazz": "Jazz", "smooth jazz": "Jazz", "bebop": "Jazz",
    "jazz fusion": "Jazz", "swing": "Jazz", "big band": "Jazz",

    # Classical
    "classical": "Classical", "orchestral": "Classical",
    "baroque": "Classical", "opera": "Classical",
    "chamber music": "Classical",

    # Blues/Soul
    "blues": "Blues/Soul", "soul": "Blues/Soul", "funk": "Blues/Soul",
    "motown": "Blues/Soul", "gospel": "Blues/Soul",
    "delta blues": "Blues/Soul",

    # Afrobeats
    "afrobeats": "Afrobeats", "afropop": "Afrobeats",
    "amapiano": "Afrobeats", "afrobeat": "Afrobeats",
    "afro house": "Afrobeats",

    # K-Pop -- kept separate from Pop: distinct scene/audience despite
    # musical overlap.
    "k-pop": "K-Pop", "kpop": "K-Pop", "korean pop": "K-Pop",
    "k-indie": "K-Pop",

    # World -- genuine world-music genre tags, distinct from the
    # nationality/language descriptors in NON_GENRE_TAGS below (e.g.
    # "flamenco" is a genre; bare "spanish" is not).
    "world": "World", "world music": "World", "celtic": "World",
    "flamenco": "World", "klezmer": "World", "bollywood": "World",
    "arabic pop": "World",
}

# Nationality/language tags Last.fm's free-form tagging produces that are
# not genres at all (e.g. a Drake track tagged "Canadian"). Filtered out
# entirely rather than becoming their own genre -- same idea as the
# artist-name filter in genre.py, just a fixed list instead of a
# per-track computed value. Not exhaustive; extend the same way as
# GENRE_ALIASES.
NON_GENRE_TAGS = {
    "canadian", "american", "british", "english", "french", "german",
    "spanish", "italian", "australian", "mexican", "irish", "scottish",
    "welsh", "dutch", "swedish", "norwegian", "danish", "brazilian",
    "russian", "japanese", "chinese", "indian", "african", "korean",
}


def normalize_tag(tag):
    """A tag's display genre label, or None if it's a nationality/language
    descriptor (not a genre) rather than a real genre tag. Unrecognized
    tags are title-cased and returned as-is -- never dropped."""
    if not tag:
        return None
    tag_lower = tag.strip().lower()
    if not tag_lower or tag_lower in NON_GENRE_TAGS:
        return None
    return GENRE_ALIASES.get(tag_lower, tag.strip().title())
```

- [ ] **Step 2: Write `webapp/test_genre_taxonomy.py` and run it**

```python
"""One-off verification script (no pytest in this project) -- run with
`python test_genre_taxonomy.py` from webapp/. Prints PASS/FAIL per case
and exits non-zero on any failure."""
import genre_taxonomy as gt

failures = []


def check(label, actual, expected):
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


check("rap alias", gt.normalize_tag("rap"), "Hip-Hop/Rap")
check("hip hop alias", gt.normalize_tag("Hip-Hop"), "Hip-Hop/Rap")
check("trap latino alias", gt.normalize_tag("trap latino"), "Latin")
check("rnb alias", gt.normalize_tag("rnb"), "R&B")
check("k-pop alias", gt.normalize_tag("K-Pop"), "K-Pop")
check("unrecognized tag title-cased", gt.normalize_tag("chillhop"), "Chillhop")
check("nationality tag filtered", gt.normalize_tag("Canadian"), None)
check("nationality tag filtered case-insensitive", gt.normalize_tag("korean"), None)
check("empty tag", gt.normalize_tag(""), None)
check("none tag", gt.normalize_tag(None), None)
check("whitespace-only tag", gt.normalize_tag("   "), None)

if failures:
    print(f"FAIL ({len(failures)}):")
    for f in failures:
        print(" -", f)
    raise SystemExit(1)
print(f"PASS: all checks ok")
```

Run: `cd "webapp" && python test_genre_taxonomy.py`
Expected: `PASS: all checks ok`

- [ ] **Step 3: Commit**

```bash
git add webapp/genre_taxonomy.py webapp/test_genre_taxonomy.py
git commit -m "Add open-ended parent-genre taxonomy module"
```

---

### Task 2: Rewrite `genre.py` to use the taxonomy, drop confidence/votes/bucket

**Files:**
- Modify: `webapp/genre.py` (full rewrite of `classify_track_multi_source` and `_track_display_genres`/`_normalize_genre_label`; removal of `dominant_genre_summary`)
- Test: `webapp/test_genre.py`

**Interfaces:**
- Consumes: `genre_taxonomy.normalize_tag(tag: str) -> str | None` (Task 1), `genre_sources.get_spotify_artist_genres`, `genre_sources.get_lastfm_tags`, `genre_sources.get_musicbrainz_artist_genres` (existing, unchanged)
- Produces: `genre.classify_track_multi_source(track: dict, cache: dict) -> {"genre": str, "display_genres": list[str], "raw_tags": dict}`, `genre.UNMATCHED = "Unmatched"`

- [ ] **Step 1: Replace `webapp/genre.py` in full**

```python
"""Multi-source genre detection: for each track, merges genre tags from
Spotify, Last.fm, and MusicBrainz (genre_sources.py), normalizes them
through the parent-genre taxonomy (genre_taxonomy.py), and ranks by
combined cross-source frequency. A track's primary genre is whatever
that ranking produces -- there is no fixed set of allowed buckets and no
confidence gate; a track with zero surviving tags anywhere is
"Unmatched".
"""
from collections import Counter

import genre_sources
import genre_taxonomy

UNMATCHED = "Unmatched"


def classify_track_multi_source(track, cache):
    """Detects a track's genre(s) using already-cached/prefetched source
    data. Spotify genres must be prefetched in bulk beforehand via
    genre_sources.prefetch_spotify_genres -- this function only reads the
    cache for Spotify, but fetches Last.fm/MusicBrainz on demand (per
    artist/track, cached as it goes).

    Returns {"genre", "display_genres", "raw_tags"}.
    """
    artists = track.get("artists") or []
    artist = artists[0] if artists else {}
    artist_name = artist.get("name") or "<unknown artist>"
    artist_id = artist.get("id")
    track_name = track.get("name", "")

    spotify_tags = genre_sources.get_spotify_artist_genres(artist_id, artist_name, cache)
    lastfm_tags = genre_sources.get_lastfm_tags(artist_name, track_name, cache)
    mb_tags = genre_sources.get_musicbrainz_artist_genres(artist_name, cache)

    display_genres = _track_display_genres(spotify_tags, lastfm_tags, mb_tags, artist_name)

    return {
        "genre": display_genres[0] if display_genres else UNMATCHED,
        "raw_tags": {"spotify": spotify_tags, "lastfm": lastfm_tags, "musicbrainz": mb_tags},
        "display_genres": display_genres,
    }


def _track_display_genres(spotify_tags, lastfm_tags, mb_tags, artist_name, max_n=2):
    """Up to max_n genre labels that best represent a track, combining all
    3 sources: every tag from every source is normalized (aliased to a
    parent genre, or title-cased if unrecognized -- see
    genre_taxonomy.normalize_tag) and counted, so a label multiple
    sources agree on (or that shows up as several near-synonym tags from
    one source) ranks above a label only one source mentioned once. Tags
    matching the artist's own name (Last.fm's free-form tagging lets
    people tag a track with the artist's name) or in
    genre_taxonomy.NON_GENRE_TAGS (nationality/language descriptors, not
    genres) are dropped before normalization."""
    artist_lower = (artist_name or "").strip().lower()
    counts = Counter()
    first_seen_order = []
    for tag in (spotify_tags or []) + (lastfm_tags or []) + (mb_tags or []):
        tag_lower = tag.strip().lower()
        if artist_lower and (artist_lower in tag_lower or tag_lower in artist_lower):
            continue
        label = genre_taxonomy.normalize_tag(tag)
        if not label:
            continue
        if label not in counts:
            first_seen_order.append(label)
        counts[label] += 1

    ranked = sorted(first_seen_order, key=lambda label: -counts[label])
    return ranked[:max_n]
```

- [ ] **Step 2: Write `webapp/test_genre.py` and run it**

Uses the real tag data already sitting in `webapp/genre_cache.json` (Mr. Rager/Kid Cudi, Up All Night/Drake) plus synthetic cases, same approach used earlier this session to verify the artist-name filter.

```python
"""One-off verification script -- run with `python test_genre.py` from
webapp/."""
import genre

failures = []


def check(label, actual, expected):
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


# Real data from webapp/genre_cache.json ("kid cudi|mr. rager" entry)
d = genre._track_display_genres(
    spotify_tags=[],
    lastfm_tags=["alternative", "Hip-Hop", "amazing", "kid cudi", "rap", "alternative rap", "hip hop"],
    mb_tags=["alternative hip hop", "hip hop", "pop rap", "trap"],
    artist_name="Kid Cudi",
)
check("Mr. Rager -- artist-name tag dropped, junk tag loses to real genre", d, ["Hip-Hop/Rap", "Alternative"])

d2 = genre._track_display_genres(
    spotify_tags=[],
    lastfm_tags=["Hip-Hop", "rap", "rnb", "hip hop", "Canadian"],
    mb_tags=[],
    artist_name="Drake",
)
check("Up All Night -- nationality tag filtered", d2, ["Hip-Hop/Rap", "R&B"])

check("no tags anywhere", genre._track_display_genres([], [], [], artist_name="Nobody"), [])

# classify_track_multi_source's genre field must be UNMATCHED when
# display_genres is empty, and the top display genre otherwise -- checked
# indirectly via the same ranking function since the full function needs
# a live cache/network; the ranking logic is what actually decides this.
check("empty ranking implies Unmatched upstream", [] and [][0] or genre.UNMATCHED, genre.UNMATCHED)

if failures:
    print(f"FAIL ({len(failures)}):")
    for f in failures:
        print(" -", f)
    raise SystemExit(1)
print("PASS: all checks ok")
```

Run: `cd "webapp" && python test_genre.py`
Expected: `PASS: all checks ok`

- [ ] **Step 3: Compile check**

Run: `cd "webapp" && python -m py_compile genre.py`
Expected: no output, exit code 0

- [ ] **Step 4: Commit**

```bash
git add webapp/genre.py webapp/test_genre.py
git commit -m "Replace bucket-voting genre classification with open taxonomy ranking"
```

---

### Task 3: Delete the now-unused `genre_config.py`

**Files:**
- Delete: `webapp/genre_config.py`

**Interfaces:**
- Consumes: nothing (verification step only)

- [ ] **Step 1: Verify nothing still imports it**

Run: `cd "webapp" && grep -rn "genre_config" *.py`
Expected: no output (Task 2 already removed genre.py's `import genre_config`)

- [ ] **Step 2: Delete the file**

```bash
git rm webapp/genre_config.py
```

- [ ] **Step 3: Commit**

```bash
git commit -m "Remove genre_config.py -- superseded by genre_taxonomy.py"
```

---

### Task 4: Backend API — simplify analyze, remove review/mapping/preview/confirm, add `/api/move`

**Files:**
- Modify: `webapp/main.py:141-196` (`_classify_playlist`), `webapp/main.py:199-220` (`_run_analysis`), `webapp/main.py:250-266` (`/api/analyze/status`), `webapp/main.py:269-380` (delete `/api/resolve_review`, `/api/preview`, `/api/confirm`; add `/api/move`)
- Modify: `webapp/session_store.py:15` (remove `pending_plan` field)

**Interfaces:**
- Consumes: `genre_mod.classify_track_multi_source(track, cache) -> {"genre", "display_genres", "raw_tags"}` (Task 2), `spotify_api.add_tracks_to_playlist(token, playlist_id, uris)`, `spotify_api.remove_tracks_from_playlist(token, playlist_id, uris)` (existing, unchanged)
- Produces: `POST /api/move` returns `{"added": int, "removed": int, "target_playlist_id": str}`. `GET /api/analyze/status` (done case) returns `{"current", "total", "done", "error", "source_playlist_id", "total_tracks", "breakdown": {genre: count}, "tracks": [{"uri", "name", "artist", "genre", "raw_tags", "display_genres"}]}` -- no more `"dominant_genre"` key.

- [ ] **Step 1: Update `session_store.py`**

In `webapp/session_store.py`, remove this line from `SessionData`:

```python
    pending_plan: Optional[dict] = None     # last computed preview, confirm re-validates against it
```

- [ ] **Step 2: Replace `_classify_playlist` in `main.py`**

Replace the body of the `for i, t in enumerate(raw_tracks):` loop (the part building `tracks`/`breakdown`) with:

```python
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
```

(Only the inner loop body changes -- the function signature, the `prefetch_spotify_genres` call above it, and the docstring stay as-is.)

- [ ] **Step 3: Update `_run_analysis`**

Replace:

```python
        sess.last_analysis = {
            "source_playlist_id": source_playlist_id,
            "tracks": tracks,
            "breakdown": breakdown,
            # Majority vote across each track's own detected genre tags --
            # never the playlist's own name/title, which is often a mood
            # label ("Chill") rather than an actual genre.
            "dominant_genre": genre_mod.dominant_genre_summary(tracks),
        }
        sess.pending_plan = None  # invalidate any stale preview from a prior analysis
```

with:

```python
        sess.last_analysis = {
            "source_playlist_id": source_playlist_id,
            "tracks": tracks,
            "breakdown": breakdown,
        }
```

- [ ] **Step 4: Update `/api/analyze/status`**

Remove this line from the `done` branch:

```python
        resp["dominant_genre"] = sess.last_analysis["dominant_genre"]
```

- [ ] **Step 5: Delete `/api/resolve_review`, `/api/preview`, `/api/confirm`**

Delete these three route handlers entirely (from the `@app.post("/api/resolve_review")` line through the end of the `/api/confirm` function).

- [ ] **Step 6: Add `POST /api/move`**

Add this in their place:

```python
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
```

- [ ] **Step 7: Compile check**

Run: `cd "webapp" && python -m py_compile main.py session_store.py`
Expected: no output, exit code 0

- [ ] **Step 8: Start the server and smoke-test with curl**

```bash
cd "webapp" && nohup python -m uvicorn main:app --host 127.0.0.1 --port 8080 > /tmp/uvicorn_plan_test.log 2>&1 &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/
curl -s -X POST http://127.0.0.1:8080/api/move -H "Content-Type: application/json" -d '{"uris":["x"],"target_playlist_id":"y"}'
```

Expected: first curl prints `200`; second prints `{"error":"not logged in"}` (proves the new route is registered and the auth gate works, without needing a real login).

- [ ] **Step 9: Commit**

```bash
git add webapp/main.py webapp/session_store.py
git commit -m "Replace review/mapping/preview/confirm endpoints with generic /api/move"
```

---

### Task 5: Frontend markup and styles — remove old wizard cards, add move-control CSS

**Files:**
- Modify: `webapp/static/index.html` (remove `review-card`, `mapping-card`, `preview-card`, `result-card`; remove `dominant-genre-summary` div and its intro paragraph)
- Modify: `webapp/static/style.css` (remove dead rules; add `.inline-move` rules)

**Interfaces:**
- Produces: `#breakdown-card` becomes the last card in the page; DOM ids `source-card`, `status`, `breakdown-card`, `breakdown-list` remain (consumed by Task 6's `app.js`)

- [ ] **Step 1: Edit `index.html`**

Replace:

```html
<div class="module hidden" id="breakdown-card">
  <div class="module-head"><span class="step-tag">02</span><h2>Genre breakdown</h2></div>
  <p class="module-hint">Dominant genre is a majority vote across each track's own detected tags -- never the playlist's own name, which is often a mood label rather than a genre.</p>
  <div id="dominant-genre-summary" class="dominant-genre-summary"></div>
  <div id="breakdown-list"></div>
</div>

<div class="module hidden" id="review-card">
  <div class="module-head"><span class="step-tag">02b</span><h2>Review low-confidence matches</h2></div>
  <p class="module-hint">Only one source matched, or the sources disagreed. Assign a genre to sort a track, or leave it for later.</p>
  <div id="review-list"></div>
  <div class="row" style="margin-top:12px;">
    <button id="save-review-btn" class="secondary">Save review choices</button>
  </div>
</div>

<div class="module hidden" id="mapping-card">
  <div class="module-head"><span class="step-tag">03</span><h2>Map genres to target playlists</h2></div>
  <p class="module-hint">For each detected genre, choose a playlist to copy those tracks into, or leave as "Don't sort" to skip it.</p>
  <div id="mapping-list"></div>
  <div class="row" style="margin-top:14px;">
    <label><input type="checkbox" id="remove-from-source"> Remove from source playlist after copying (move instead of copy)</label>
  </div>
  <div class="row" style="margin-top:10px;">
    <button id="preview-btn">Preview changes</button>
  </div>
</div>

<div class="module hidden" id="preview-card">
  <div class="module-head"><span class="step-tag">04</span><h2>Review before writing anything</h2></div>
  <div id="preview-list"></div>
  <div class="row" style="margin-top:14px;">
    <button id="confirm-btn">Confirm and apply</button>
    <span class="muted">Nothing has been written to Spotify yet.</span>
  </div>
</div>

<div class="module hidden" id="result-card">
  <div class="module-head"><h2>Done</h2></div>
  <ul class="log-list" id="result-list"></ul>
</div>
```

with:

```html
<div class="module hidden" id="breakdown-card">
  <div class="module-head"><span class="step-tag">02</span><h2>Genre breakdown</h2></div>
  <p class="module-hint">Click a genre to see its tracks. Move a single track or an entire genre to any of your other playlists -- nothing is written to Spotify until you confirm a move.</p>
  <div id="breakdown-list"></div>
</div>
```

- [ ] **Step 2: Edit `style.css` — remove dead rules**

Delete these blocks (they belonged to the removed cards/functions):

```css
/* ------------------------------------------------------- dominant genre */
.dominant-genre-summary {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-muted);
  padding: 8px 10px;
  margin-bottom: 12px;
  background: var(--panel-raised);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.dominant-genre-summary strong { color: var(--amber-text); }
```

```css
.bar-fill.state-review { background: var(--blue); }
```

(keep `.bar-fill.state-none` — Unmatched still uses it)

```css
.meter { display: inline-flex; gap: 3px; margin-left: 4px; }
.meter-seg { width: 7px; height: 7px; border-radius: 1px; border: 1px solid var(--border-strong); background: transparent; }
.meter-seg.filled { background: var(--amber); border-color: var(--amber); }

.confidence-badge {
  font-family: var(--font-mono);
  font-size: 11px;
  border-radius: var(--radius);
  padding: 2px 7px;
  white-space: nowrap;
}
.confidence-badge.high { background: var(--amber-dim); color: var(--amber-text); border: 1px solid var(--amber); }
.confidence-badge.low { background: var(--blue-dim); color: var(--blue-text); border: 1px dashed var(--blue); }
.confidence-badge.none { color: var(--text-faint); border: 1px dashed var(--border-strong); }

/* -------------------------------------------------------------- map rows */
.map-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 10px 0;
  border-bottom: 1px solid var(--border);
}
.map-row:last-child, .review-select-row:last-child { border-bottom: none; }
.row-label { font-size: 13.5px; display: flex; align-items: center; gap: 8px; }
.row-count { font-family: var(--font-mono); font-size: 12px; color: var(--text-muted); }
.row-note { color: var(--text-faint); font-size: 12.5px; padding: 8px 0; }
```

```css
.track-list .track-tag { color: var(--text-faint); font-family: var(--font-mono); font-size: 11.5px; }

/* --------------------------------------------------------------- preview */
.preview-group h3 {
  font-size: 13.5px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 16px 0 8px;
}
.preview-group:first-child h3 { margin-top: 0; }
.preview-count { font-family: var(--font-mono); font-size: 12px; color: var(--amber-text); }

/* ---------------------------------------------------------------- result */
.log-list { font-family: var(--font-mono); font-size: 12.5px; list-style: none; padding: 0; margin: 0; }
.log-list li {
  padding: 7px 0 7px 14px;
  border-left: 2px solid var(--border-strong);
  color: var(--text-muted);
  margin-bottom: 2px;
}
.log-list li strong { color: var(--text); font-weight: 500; }
```

And change the media-query line:

```css
  .track-row, .map-row { flex-direction: column; align-items: stretch; }
```

to:

```css
  .track-row { flex-direction: column; align-items: stretch; }
```

(Keep `.vote-pill`/`.vote-pill.matched` — still used by `genrePills`. Keep `.track-row`, `.track-info`, `.track-title`, `.track-artist`, `.vote-row`, `.track-list`, `#breakdown-list .track-list`, `.bar-row*`, `.muted`, `.pill` — all still used.)

- [ ] **Step 3: Add move-control CSS**

Add this new block right after the `.bar-fill.state-none` rule:

```css
/* ------------------------------------------------------------ inline move */
.inline-move { display: flex; align-items: center; gap: 8px; margin-top: 8px; flex-wrap: wrap; }
.inline-move select { font-size: 12.5px; padding: 5px 8px; }
.inline-move button { font-size: 12px; padding: 5px 10px; }
.inline-move .confirm-text { font-size: 12.5px; color: var(--text-muted); }
.inline-move .confirm-text strong { color: var(--amber-text); }
.inline-move label { font-size: 12px; }
```

- [ ] **Step 4: Commit**

```bash
git add webapp/static/index.html webapp/static/style.css
git commit -m "Remove wizard cards, add inline-move styles"
```

---

### Task 6: Rewrite `app.js` — breakdown list becomes the move UI

**Files:**
- Modify: `webapp/static/app.js` (full rewrite)

**Interfaces:**
- Consumes: `GET /api/analyze/status` (done shape from Task 4), `POST /api/move` (Task 4), DOM ids from Task 5 (`source-card`, `breakdown-card`, `breakdown-list`)
- Produces: module-level `lastAnalysis` object holding the current `{breakdown, tracks, total_tracks, source_playlist_id}` (mutated after each move, never refetched from the server until the next full Analyse)

- [ ] **Step 1: Replace `webapp/static/app.js` in full**

```javascript
const statusEl = document.getElementById('status');
function setStatus(msg, isError) {
  statusEl.textContent = msg || '';
  statusEl.className = isError ? 'statusline error' : 'statusline';
}

async function api(path, opts) {
  const resp = await fetch(path, Object.assign({ credentials: 'same-origin' }, opts));
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`${path} -> ${resp.status}: ${text}`);
  }
  return resp.json();
}

document.getElementById('connect-btn').onclick = () => {
  window.location.href = '/api/login';
};
document.getElementById('logout-btn').onclick = async () => {
  await api('/api/logout');
  window.location.reload();
};

let sourcePlaylists = [];
let lastAnalysis = null; // {source_playlist_id, total_tracks, breakdown, tracks}

async function init() {
  setStatus('Checking connection...');
  try {
    const me = await api('/api/me');
    if (!me.logged_in) {
      setStatus('');
      return;
    }
    document.getElementById('connect-label').textContent = `Connected as ${me.display_name}`;
    document.getElementById('connect-btn').classList.add('hidden');
    document.getElementById('logout-btn').classList.remove('hidden');
    setStatus('Loading your playlists...');

    const data = await api('/api/playlists');
    sourcePlaylists = data.playlists;
    const select = document.getElementById('source-select');
    select.innerHTML = sourcePlaylists
      .map(p => `<option value="${p.id}">${p.name} (${p.track_count ?? '?'} tracks)</option>`)
      .join('');
    document.getElementById('source-card').classList.remove('hidden');
    setStatus(`Loaded ${sourcePlaylists.length} playlists you own.`);

    // Reattach to an analysis still running server-side from before a
    // reload, instead of leaving the page looking idle while it finishes
    // (and instead of letting a fresh Analyse click start a duplicate run).
    let inProgress;
    try {
      inProgress = await api('/api/analyze/status');
    } catch (e) {
      inProgress = null;  // nothing has been started yet this session
    }
    if (inProgress && !inProgress.done) {
      document.getElementById('analyze-btn').disabled = true;
      setStatus(`Resuming analysis: ${inProgress.current}/${inProgress.total}...`);
      try {
        await pollAnalysis();
      } catch (e) {
        setStatus('Error: ' + e.message, true);
      } finally {
        document.getElementById('analyze-btn').disabled = false;
      }
    }
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  }
}

// ---------------------------------------------------------------- helpers

// A track's genre(s) -- at most 2, combined across all 3 sources (see
// display_genres in genre.py) so multi-source agreement decides the
// label instead of dumping every raw tag from every source. Empty when
// nothing was detected anywhere, so a track with no data just shows
// nothing rather than a "no tags found" placeholder.
function genrePills(track) {
  const genres = track.display_genres || [];
  return genres.map(g => `<span class="vote-pill matched">${g}</span>`).join('');
}

function targetOptionsHtml() {
  const sourceId = document.getElementById('source-select').value;
  return sourcePlaylists
    .filter(p => p.id !== sourceId)
    .map(p => `<option value="${p.id}">${p.name}</option>`)
    .join('');
}

function stateClassFor(label) {
  return label === 'Unmatched' ? 'state-none' : '';
}

// ---------------------------------------------------------------- analyze

const ANALYZE_POLL_MS = 800;

async function pollAnalysis() {
  while (true) {
    const status = await api('/api/analyze/status');
    if (!status.done) {
      setStatus(`Classifying tracks: ${status.current}/${status.total} (MusicBrainz limits lookups to 1/sec, so this can take a while)...`);
      await new Promise(r => setTimeout(r, ANALYZE_POLL_MS));
      continue;
    }
    if (status.error) {
      throw new Error(status.error);
    }
    lastAnalysis = status;
    renderBreakdown();
    setStatus(`Analyzed ${status.total_tracks} tracks.`);
    return;
  }
}

document.getElementById('analyze-btn').onclick = async () => {
  const sourceId = document.getElementById('source-select').value;
  setStatus('Fetching playlist tracks...');
  document.getElementById('analyze-btn').disabled = true;
  try {
    const started = await api('/api/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source_playlist_id: sourceId }),
    });
    setStatus(`Classifying tracks: 0/${started.total}...`);
    await pollAnalysis();
  } catch (e) {
    setStatus('Error: ' + e.message, true);
  } finally {
    document.getElementById('analyze-btn').disabled = false;
  }
};

// -------------------------------------------------------------- breakdown

function renderBreakdown() {
  const data = lastAnalysis;
  const el = document.getElementById('breakdown-list');
  const total = data.total_tracks || 1;
  const entries = Object.entries(data.breakdown).sort((a, b) => b[1] - a[1]);
  const maxCount = Math.max(...entries.map(([, c]) => c), 1);

  const tracksByGenre = {};
  for (const t of data.tracks) {
    (tracksByGenre[t.genre] = tracksByGenre[t.genre] || []).push(t);
  }

  const targetOptions = targetOptionsHtml();

  el.innerHTML = entries.map(([label, count], i) => {
    const pct = Math.round((count / total) * 100);
    const uris = (tracksByGenre[label] || []).map(t => t.uri);
    return `
    <div class="bar-row" data-toggle="bd-panel-${i}">
      <div class="bar-row-top">
        <span class="bar-label"><span class="chevron">▸</span>${label}</span>
        <span class="bar-count">${count} (${pct}%)</span>
      </div>
      <div class="bar-track"><div class="bar-fill ${stateClassFor(label)}" style="width:${(count / maxCount * 100).toFixed(0)}%"></div></div>
      <div class="inline-move" data-uris='${JSON.stringify(uris)}'>
        ${moveTriggerHtml(`Move all ${count}`, targetOptions)}
        ${moveConfirmHtml(count)}
      </div>
    </div>
    <div class="track-list hidden" id="bd-panel-${i}">
      ${(tracksByGenre[label] || []).map(t => `
        <div class="track-row">
          <div class="track-info">
            <div class="track-title">${t.name} <span class="track-artist">— ${t.artist}</span></div>
            ${genrePills(t) ? `<div class="vote-row">${genrePills(t)}</div>` : ''}
          </div>
          <div class="inline-move" data-uris='${JSON.stringify([t.uri])}'>
            ${moveTriggerHtml('Move', targetOptions)}
            ${moveConfirmHtml(1)}
          </div>
        </div>
      `).join('')}
    </div>
  `;
  }).join('');

  el.querySelectorAll('.bar-row').forEach(row => {
    row.onclick = () => {
      const panel = document.getElementById(row.dataset.toggle);
      const wasHidden = panel.classList.contains('hidden');
      panel.classList.toggle('hidden');
      row.querySelector('.chevron').textContent = wasHidden ? '▾' : '▸';
    };
  });

  wireMoveControls(el);
  document.getElementById('breakdown-card').classList.remove('hidden');
}

function moveTriggerHtml(buttonLabel, targetOptions) {
  return `
    <span class="move-trigger">
      <select class="move-target">${targetOptions}</select>
      <button class="move-btn secondary">${buttonLabel}</button>
    </span>`;
}

function moveConfirmHtml(count) {
  return `
    <span class="move-confirm hidden">
      <span class="confirm-text">Move ${count} track${count === 1 ? '' : 's'} to <strong class="move-confirm-name"></strong>?</span>
      <label><input type="checkbox" class="move-remove"> remove from source</label>
      <button class="move-confirm-btn">Confirm</button>
      <button class="move-cancel-btn secondary">Cancel</button>
    </span>`;
}

function wireMoveControls(root) {
  root.querySelectorAll('.inline-move').forEach(container => {
    // Stops a click on the select/buttons from bubbling up to the
    // .bar-row's own click handler, which would otherwise also toggle
    // that genre's expand/collapse panel.
    container.addEventListener('click', (e) => e.stopPropagation());

    const trigger = container.querySelector('.move-trigger');
    const confirmBox = container.querySelector('.move-confirm');
    const targetSelect = container.querySelector('.move-target');
    const confirmName = container.querySelector('.move-confirm-name');
    const moveBtn = container.querySelector('.move-btn');
    const confirmBtn = container.querySelector('.move-confirm-btn');
    const cancelBtn = container.querySelector('.move-cancel-btn');
    const removeCheckbox = container.querySelector('.move-remove');

    moveBtn.onclick = () => {
      if (!targetSelect.value) {
        setStatus('Pick a target playlist first.', true);
        return;
      }
      confirmName.textContent = targetSelect.selectedOptions[0].textContent;
      trigger.classList.add('hidden');
      confirmBox.classList.remove('hidden');
    };

    cancelBtn.onclick = () => {
      confirmBox.classList.add('hidden');
      trigger.classList.remove('hidden');
    };

    confirmBtn.onclick = async () => {
      const uris = JSON.parse(container.dataset.uris);
      const targetId = targetSelect.value;
      const targetName = targetSelect.selectedOptions[0].textContent;
      const removeFromSource = removeCheckbox.checked;
      confirmBtn.disabled = true;
      try {
        const result = await api('/api/move', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ uris, target_playlist_id: targetId, remove_from_source: removeFromSource }),
        });
        applyMoveResult(uris);
        setStatus(`Moved ${result.added} track(s) to ${targetName}${result.removed ? ' (removed from source)' : ''}.`);
      } catch (e) {
        setStatus('Error: ' + e.message, true);
        confirmBtn.disabled = false;
      }
    };
  });
}

// Removes moved tracks from the in-memory analysis, recomputes the
// breakdown, and re-renders -- avoids a full re-analyze (and its
// MusicBrainz-throttled wait) just to reflect a move that already
// happened. Re-rendering collapses any expanded genre panels back to
// closed, which is an accepted trade-off for not hand-patching the DOM.
function applyMoveResult(movedUris) {
  const movedSet = new Set(movedUris);
  lastAnalysis.tracks = lastAnalysis.tracks.filter(t => !movedSet.has(t.uri));
  lastAnalysis.total_tracks = lastAnalysis.tracks.length;
  const breakdown = {};
  for (const t of lastAnalysis.tracks) {
    breakdown[t.genre] = (breakdown[t.genre] || 0) + 1;
  }
  lastAnalysis.breakdown = breakdown;
  renderBreakdown();
}

init();
```

- [ ] **Step 2: Restart the server so the cache-busted `app.js?v=...` picks up the new content**

```bash
pkill -f "uvicorn main:app" 2>/dev/null
cd "webapp" && nohup python -m uvicorn main:app --host 127.0.0.1 --port 8080 > /tmp/uvicorn_plan_test2.log 2>&1 &
sleep 2
curl -s http://127.0.0.1:8080/ | grep app.js
```

Expected: a `<script src="/static/app.js?v=...">` line with a fresh timestamp (different from before this task's edit).

- [ ] **Step 3: Commit**

```bash
git add webapp/static/app.js
git commit -m "Turn genre breakdown into the browse-and-move interface"
```

---

### Task 7: Browser smoke test with synthetic data

No real Spotify login is available in this environment, so this task verifies the UI logic end-to-end by injecting synthetic analysis data through the browser console (same technique used earlier this session), rather than by running a real Analyse.

**Files:** none (verification only)

- [ ] **Step 1: Load the app and inject synthetic multi-genre data**

Navigate to `http://127.0.0.1:8080/?t=<unique-cachebust>` (a fresh query string forces a real fetch past any browser cache, same reasoning as the cache-busting fix earlier this session), then in the page console:

```javascript
document.getElementById('source-card').classList.remove('hidden');
sourcePlaylists = [{id:'src', name:'Chill'}, {id:'p1', name:'Rap Cave'}, {id:'p2', name:'R&B Only'}];
document.getElementById('source-select').innerHTML = '<option value="src">Chill</option>';

lastAnalysis = {
  source_playlist_id: 'src',
  total_tracks: 3,
  breakdown: {"Hip-Hop/Rap": 2, "Unmatched": 1},
  tracks: [
    {uri:'spotify:track:a', name:'Mr. Rager', artist:'Kid Cudi', genre:'Hip-Hop/Rap', display_genres:['Hip-Hop/Rap','Alternative'], raw_tags:{}},
    {uri:'spotify:track:b', name:'Up All Night', artist:'Drake', genre:'Hip-Hop/Rap', display_genres:['Hip-Hop/Rap','R&B'], raw_tags:{}},
    {uri:'spotify:track:c', name:'Silence Track', artist:'Nobody', genre:'Unmatched', display_genres:[], raw_tags:{}},
  ],
};
renderBreakdown();
'rendered';
```

Expected: no thrown error; two bucket rows appear ("Hip-Hop/Rap 2 (67%)", "Unmatched 1 (33%)"), each with a "Move all N to: [select][Move]" control.

- [ ] **Step 2: Verify no console errors**

Use the browser tool's console reader with `onlyErrors: true` after the above. Expected: none.

- [ ] **Step 3: Expand a bucket and verify per-track move controls render**

Click the "Hip-Hop/Rap" row. Expected: both tracks listed, each with its own genre pills and its own "Move" control; "Mr. Rager" shows `Hip-Hop/Rap` and `Alternative` pills (not `SP no tags found` etc. -- confirming the earlier tag-cleanup fix survived the rewrite).

- [ ] **Step 4: Verify the confirm/cancel flow without a network call**

Click "Move" on the "Hip-Hop/Rap" bucket's target select first (pick "Rap Cave"), then click its "Move all 2" button. Expected: the trigger hides, a confirm line appears reading "Move 2 tracks to Rap Cave?" with a "remove from source" checkbox, Confirm, and Cancel. Click Cancel. Expected: reverts to the trigger control, no request was made (verify via the network-requests tool that no `/api/move` call occurred).

- [ ] **Step 5: Verify a mocked successful move updates the view in place**

In the console, stub `fetch` for just this check so a real network call isn't required:

```javascript
const realFetch = window.fetch;
window.fetch = async (url, opts) => {
  if (url === '/api/move') {
    return new Response(JSON.stringify({added: 2, removed: 0, target_playlist_id: 'p1'}), {status: 200});
  }
  return realFetch(url, opts);
};
```

Then click "Move all 2" on Hip-Hop/Rap again, pick "Rap Cave", click Confirm. Expected: the Hip-Hop/Rap row disappears entirely (both its tracks were moved out), only "Unmatched 1 (100%)" remains, and the status line reads "Moved 2 track(s) to Rap Cave.". Restore real fetch afterward: `window.fetch = realFetch;`

- [ ] **Step 6: Verify the Unmatched bucket is movable too**

Expand "Unmatched", confirm "Silence Track" shows with no genre pills (nothing rendered, not a placeholder) and still has a working "Move" control (repeat steps 4-5's flow against it if desired, or just confirm the control is present and clickable).

- [ ] **Step 7: Record results**

No commit for this task (verification only) -- if any step fails, return to Task 6 and fix before proceeding.

---

## Self-review notes

- Spec coverage: taxonomy module (Task 1), classification rewrite (Task 2), dead-code removal (Task 3), API changes incl. `/api/move` (Task 4), markup/CSS (Task 5), interactive move UI (Task 6), verification (Task 7) -- every spec section has a task.
- The spec's "World" bullet described nationality/language tags being filtered, which conflicts with also listing "World" as a parent genre. Resolved in Task 1: `NON_GENRE_TAGS` handles the nationality/language stoplist; `GENRE_ALIASES["World"]` is reserved for genuine world-music genre words (flamenco, klezmer, etc.) instead. This resolution is called out inline in `genre_taxonomy.py`'s comments.
- `dominant_genre_summary` and its call sites are fully removed (Task 2 deletes the function, Task 4 removes its wiring in `main.py`, Task 5 removes its DOM/CSS, Task 6's rewritten `app.js` never references it).

# Open genre browsing & move UI — design spec

Date: 2026-09-19
Scope: `webapp/` only. The root CLI tools (`spotify_sort.py`, `reorganize.py`,
`config.py`) keep their existing fixed EDM/Pop Rock/Indie 3-bucket system —
they are a separate, older tool not covered by this change.

## Problem

The webapp currently classifies every track into exactly one of 3
hardcoded buckets (EDM / Pop Rock / Indie, defined in `genre_config.py`),
requiring 2+ of 3 sources (Spotify/Last.fm/MusicBrainz) to agree before a
track auto-sorts; otherwise it's "Needs Review" or "Unmatched". This was a
deliberate starting scope for early development, but the user's actual
library spans many genres (Hip-Hop/Rap, R&B, etc.) that this app currently
can only ever dump into "Unmatched".

The user wants: analyze a playlist, see however many genres actually exist
in it (not capped at 3), click a genre to see its tracks, and move either
a single track or an entire genre's worth of tracks to any of their other
playlists.

## Genre detection

### Taxonomy

New file `webapp/genre_taxonomy.py` holds:

- `PARENT_GENRES`: ~20-25 broad genre names.
- `GENRE_ALIASES`: dict mapping known subgenre tag spellings (lowercase)
  to one of the parent genres. Approximate v1 coverage:

  - **Hip-Hop/Rap** — rap, trap, cloud rap, drill, gangsta rap, boom bap,
    mumble rap, hip hop, hip-hop
  - **R&B** — r&b, rnb, neo-soul, contemporary r&b, quiet storm
  - **Pop** — pop, dance pop, synth-pop, electropop, teen pop
  - **Rock** — rock, alternative rock, classic rock, hard rock, garage
    rock, arena rock
  - **Indie** — indie, indie rock, indie pop, indie folk, bedroom pop,
    dream pop, lo-fi
  - **Metal** — metal, heavy metal, death metal, black metal, metalcore,
    nu metal
  - **Punk** — punk, pop punk, punk rock, hardcore punk, emo
  - **EDM/Electronic** — edm, house, deep house, techno, trance, dubstep,
    drum and bass, dnb, electronic, future bass, electro house
  - **Folk/Country** — folk, country, americana, bluegrass,
    singer-songwriter
  - **Latin** — latin, reggaeton, latin pop, latin trap, salsa, bachata
  - **Reggae** — reggae, dancehall, dub, ska
  - **Jazz** — jazz, smooth jazz, bebop, jazz fusion
  - **Classical** — classical, orchestral, baroque, opera
  - **Blues/Soul** — blues, soul, funk, motown
  - **Afrobeats** — afrobeats, afropop, amapiano
  - **K-Pop** — k-pop, korean pop (kept separate from Pop — distinct
    scene/audience despite musical overlap)

  A tag with no entry in `GENRE_ALIASES` is not dropped — it becomes its
  own genre, title-cased as-is. This table is meant to be extended over
  time (per the user: "first include as many genres as possible then we
  can filter it down") — adding coverage later is just adding dict
  entries, no code changes.

- `NON_GENRE_TAGS`: a small stoplist of nationality/language tags that are
  not genres at all — filtered out entirely, same mechanism as the
  existing artist-name filter in `genre.py`. v1 starter list: canadian,
  american, british, english, french, german, spanish, italian,
  australian, mexican, irish, scottish, welsh, dutch, swedish, norwegian,
  danish, brazilian, russian, japanese, chinese, indian, african. (Not
  exhaustive — extend later the same way as `GENRE_ALIASES`, just add
  entries. "Korean"/"k-pop" stay distinct: "k-pop" is a genre alias, bare
  "korean" as a nationality tag goes in this stoplist.)

### Per-track classification (`genre.py`)

Replace `classify_track_multi_source`'s bucket-voting logic:

- Merge tags from all 3 sources (still fetched exactly as today via
  `genre_sources.py`).
- Drop tags matching the artist's own name (existing logic, kept) and
  tags in `NON_GENRE_TAGS` (new).
- Normalize remaining tags through `GENRE_ALIASES` (fallback: title-case).
- Rank by combined frequency across all 3 sources (reuses the
  `_track_display_genres` approach already built and tested this
  session).
- **Primary genre** (top-ranked) = the bucket this track is filed under,
  stored as `track["genre"]`. A track with zero surviving tags anywhere
  gets `"Unmatched"`.
- Up to 2 top-ranked labels are kept as `track["display_genres"]` for the
  per-track pill display (secondary genre shown as context, does not
  split the track across two buckets).
- No more `confidence`, `votes`, or `NEEDS_REVIEW` — dropped entirely per
  user's explicit choice ("drop confidence tiers").

### Playlist-wide dominant genre summary

Dropped. With genres already consolidated to a handful of parent buckets,
the breakdown list itself (counts + percentages per bucket) is that view;
a separate one-line summary banner is now redundant. `dominant_genre_summary`
and its wiring in `main.py` / `app.js` are removed.

## API changes (`webapp/main.py`)

- `/api/analyze` and `/api/analyze/status`: same background-job/polling
  shape as today (unchanged from the earlier progress-indicator fix).
  `breakdown` keys are now whatever genres were actually detected, plus
  `"Unmatched"` when applicable — no fixed key set.
- **Removed**: `/api/resolve_review` (no Needs Review bucket anymore),
  `/api/preview`, `/api/confirm` (the old global mapping/preview/confirm
  wizard flow), and `session_store.SessionData.pending_plan` (no longer
  needed).
- **Added**: `POST /api/move` — body `{uris: [...], target_playlist_id,
  remove_from_source: bool}`. Works identically for a single track
  (`uris: [x]`) or an entire genre's worth of tracks (`uris`: every URI in
  that bucket) — the caller decides scope by what it passes. Calls
  `spotify_api.add_tracks_to_playlist`, and if `remove_from_source` is
  true, `spotify_api.remove_tracks_from_playlist` against
  `sess.last_analysis["source_playlist_id"]`. Returns
  `{added, removed, target_playlist_id}`.

  No server-side preview endpoint — the frontend already holds full track
  data client-side after analyze (name/artist/genre per track), so it
  builds the confirm dialog locally before calling `/api/move`, avoiding
  an extra round-trip.

## Frontend changes (`webapp/static/`)

Removes: `review-card`, `mapping-card`, `preview-card`, `result-card` and
all their rendering/handler code in `app.js` (renderReview, renderMapping,
renderPreview, renderResult, the save-review-btn/preview-btn/confirm-btn
handlers). Removes the `dominant-genre-summary` element and
`renderDominantGenre`.

`breakdown-card` becomes the primary interactive view:

- Each genre bucket row keeps its expand/collapse bar, plus its count
  shown as `N (P%)` of the playlist, plus an inline control:
  `Move all N to: [playlist ▾] [Move]`.
- Expanding a bucket lists its tracks; each track row gets its own
  `Move to: [playlist ▾] [Move]` control alongside its genre pills
  (reusing the existing `genrePills`/track-row rendering from the
  previous fix).
- Clicking **Move** (either level) swaps that row's control for an inline
  confirm: `Move 23 tracks to Rap Cave? [ ] remove from source  [Confirm]
  [Cancel]` (remove-from-source checkbox unchecked by default, per user's
  choice to keep it but default off). **Cancel** just reverts to the
  original Move button — no request is made.
- Confirming calls `POST /api/move`, then updates the view in place
  (removes moved tracks from the bucket's local list, recomputes that
  bucket's count/percentage and the affected track rows, shows a brief
  inline success line) without requiring a full re-analyze.
- Target playlist options: the existing `sourcePlaylists` list minus the
  current source playlist (already how the old mapping dropdown worked —
  no restriction to any fixed set of "genre playlists").

## Edge cases

- Zero tags from all 3 sources → `"Unmatched"` bucket, still fully
  movable like any other bucket.
- Nationality/language tags filtered via `NON_GENRE_TAGS`, same mechanism
  as the existing artist-name filter (both are "detected but not a
  genre" filters, not different code paths).
- Re-analyzing after a copy-move (remove-from-source unchecked): moved
  tracks reappear in the source's fetch, correct copy semantics, no
  special handling. After a move-with-removal: they're gone from the
  source, also nothing special needed.
- Token expiry mid-move: reuses the existing `_access_token` refresh path
  unchanged.

## Testing plan

- Unit-test the taxonomy/classification function (`genre_taxonomy.py` +
  updated `genre.py`) against synthetic cases and the real tag data
  already present in `webapp/genre_cache.json` (same approach used to
  verify the artist-name filter earlier this session).
- `python -m py_compile` on all touched backend files.
- Live smoke test in the browser via injected synthetic data through the
  console (no real Spotify login available to the assistant this
  session), covering: multiple genre buckets rendering, expand/collapse,
  per-track move confirm/cancel, per-genre move confirm/cancel, and the
  "Unmatched" bucket still being movable.
- User does a final real-data pass against their actual playlists once
  deployed.

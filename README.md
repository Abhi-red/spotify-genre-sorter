# Spotify Genre Sorter

A tool that listens to your Spotify playlists and figures out what's actually
in them. Genre tags on Spotify are messy and inconsistent, so this project
cross-references **Spotify, Last.fm, and MusicBrainz** for every track,
votes across the three sources, and rolls the result up into a broad,
human-readable genre. From there you can browse a playlist genre-by-genre
and move tracks — one at a time or a whole genre at once — into any other
playlist.

There are two parts in this repo:

- **`webapp/`** — a FastAPI + vanilla-JS web app: log in with Spotify,
  pick a playlist, analyze it, browse the genre breakdown, move tracks.
  This is the actively developed piece.
- **Root-level CLI scripts** (`spotify_sort.py`, `reorganize.py`,
  `config.py`) — an earlier, single-purpose script that sorts one specific
  playlist into a fixed EDM / Pop Rock / Indie split. Kept for reference;
  superseded by the webapp's open-ended genre detection.

## How genre detection works

For each track, three independent sources are queried for genre tags:

1. **Spotify** — genres attached to the track's primary artist (fetched in
   one batched call per playlist, not per track).
2. **Last.fm** — community tags on the specific artist + track.
3. **MusicBrainz** — artist-level genre tags (rate-limited to the
   1 req/sec MusicBrainz allows, and cached so it's only paid once per
   artist).

Every source is cache-first and fails soft — if one API is down or rate
limited, the vote just proceeds with whatever sources responded. Tags are
normalized through a ~25-genre parent taxonomy (`webapp/genre_taxonomy.py`)
so `"deep house"`, `"electro house"`, and `"edm"` all roll up to
**EDM/Electronic** instead of fragmenting the breakdown. A tag with no
mapping becomes its own genre rather than being dropped, so the taxonomy
grows to fit whatever's actually in your library instead of forcing
everything into a fixed bucket list.

Everything is cached to disk per artist/track, so re-analyzing the same
playlist (or a playlist that shares artists with one you've already run)
is fast.

## Live demo

**[spotify-genre-sorter-production-e3a9.up.railway.app](https://spotify-genre-sorter-production-e3a9.up.railway.app)**

Spotify apps start in **Development Mode**, which caps login to a manually
allow-listed set of Spotify accounts (25 max) until the app goes through
Spotify's extension review. That means the hosted instance only works for
allow-listed accounts right now — a stranger hitting "Connect Spotify"
will get an access-restricted error, not a bug in the app itself. Reach
out if you'd like your Spotify account added, or run it locally against
your own Spotify app credentials (below) to try it with your own library.

## Tech stack

- **Backend:** Python, FastAPI, `uvicorn`
- **Frontend:** vanilla JS/HTML/CSS (no framework, no build step)
- **Data sources:** Spotify Web API, Last.fm API, MusicBrainz API
- **Deploy:** Railway (`webapp/Procfile`)
- **Tests:** `pytest` (`webapp/test_genre.py`, `webapp/test_genre_taxonomy.py`)

## Running locally

Requires a [Spotify Developer app](https://developer.spotify.com/dashboard)
(free) with a redirect URI of `http://127.0.0.1:8080`.

```bash
cd webapp
pip install -r requirements.txt
```

Create `secrets.env` in the repo root:

```
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8080

# Optional — improves genre coverage but the app works without them
LASTFM_API_KEY=your_lastfm_api_key
MUSICBRAINZ_USER_AGENT=YourAppName/1.0 ( your_contact_info )
```

Run it:

```bash
cd webapp
uvicorn main:app --host 127.0.0.1 --port 8080
```

Open `http://127.0.0.1:8080`, connect Spotify, pick a playlist, and analyze.

Run the tests:

```bash
cd webapp
pytest
```

## Project structure

```
webapp/
  main.py               FastAPI routes (auth, playlists, analyze, move)
  genre.py               Multi-source genre classification per track
  genre_sources.py       Spotify / Last.fm / MusicBrainz tag fetching + caching
  genre_taxonomy.py      Parent-genre list and subgenre → parent mapping
  genre_cache.py         Disk-backed cache for genre lookups
  spotify_api.py         Spotify Web API calls (playlists, tracks, moves)
  spotify_auth.py        OAuth flow + token refresh
  session_store.py       In-memory session storage
  static/                Frontend (HTML/CSS/JS)

spotify_sort.py           Legacy CLI: fixed 3-bucket playlist sort
reorganize.py              Legacy CLI: playlist reorg helper
config.py                  Legacy CLI config (genre keyword lists)
```

## Notes / limitations

- The webapp's genre taxonomy is a work in progress — new subgenres are
  added to `genre_taxonomy.py` as they show up unmapped in a real library.
- Session state is in-memory, so restarting the server logs everyone out.
  Fine for a personal tool; would move to a real session store for
  multi-instance deploys.
- The root-level CLI scripts predate the webapp and use a different,
  fixed-bucket classification approach — see the docstring in
  `spotify_sort.py`.

## License

MIT — see [LICENSE](LICENSE).

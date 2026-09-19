"""Sort tracks from the "FG" Spotify playlist into EDM / Pop Rock / Indie
playlists based on the genres of each track's artists.

Usage:
    python spotify_sort.py            # actually add tracks to target playlists
    python spotify_sort.py --dry-run  # print the plan, write nothing to Spotify

Tracks that don't match any category (by keyword lists in config.py) are
logged to leftover.txt instead of being guessed into a playlist. FG itself
is never modified -- tracks are only added to the target playlists.
"""

import argparse
import sys

from dotenv import load_dotenv
import os
import requests
import spotipy
from spotipy import SpotifyOAuth

import config

# Spotify's playlist_add_items caps at 100 URIs per call.
ADD_ITEMS_CHUNK_SIZE = 100


def get_client():
    load_dotenv("secrets.env")
    client_id = os.getenv("SPOTIFY_CLIENT_ID")
    client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
    redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")

    auth_manager = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=config.SPOTIFY_SCOPE,
    )
    return spotipy.Spotify(auth_manager=auth_manager)


def get_lastfm_api_key():
    load_dotenv("secrets.env")
    api_key = os.getenv("LASTFM_API_KEY")
    if not api_key:
        sys.exit(
            "LASTFM_API_KEY is not set in secrets.env.\n"
            "Get a free key at https://www.last.fm/api/account/create and "
            "add it as: LASTFM_API_KEY = <your key>"
        )
    return api_key


def fetch_all_playlist_items(sp, playlist_id):
    """Return every item in a playlist, following pagination."""
    items = []
    results = sp.playlist_items(playlist_id)
    items.extend(results["items"])
    while results.get("next"):
        results = sp.next(results)
        items.extend(results["items"])
    return items


def get_artist_genres(artist_name, api_key, genre_cache):
    """Look up an artist's genre tags via Last.fm's artist.getTopTags,
    caching per artist name (Last.fm has no stable numeric ID we can key on
    the way Spotify does).

    Spotify's own artist endpoint no longer returns genre data for apps
    without Extended Quota Mode, so Last.fm's community tags are used as a
    substitute -- they map onto the same kind of keyword lists (e.g.
    "alternative rock", "indie pop").
    """
    cache_key = artist_name.lower()
    if cache_key in genre_cache:
        return genre_cache[cache_key]

    genres = []
    try:
        response = requests.get(
            config.LASTFM_API_URL,
            params={
                "method": "artist.gettoptags",
                "artist": artist_name,
                "api_key": api_key,
                "format": "json",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        tags = data.get("toptags", {}).get("tag", [])
        for tag in tags[: config.LASTFM_MAX_TAGS]:
            name = tag.get("name", "")
            try:
                count = int(tag.get("count", 0))
            except (TypeError, ValueError):
                count = 0
            if name and count >= config.LASTFM_MIN_TAG_COUNT:
                genres.append(name)
    except requests.RequestException as exc:
        print(f"  Warning: Last.fm lookup failed for '{artist_name}': {exc}")

    genre_cache[cache_key] = genres
    return genres


def resolve_track_genres(track, api_key, genre_cache):
    """Get genres for a track: try the primary artist first, then fall back
    to other (featured) artists in order if the primary artist has none."""
    artists = track.get("artists", [])
    for artist in artists:
        artist_name = artist.get("name")
        if not artist_name:
            continue
        genres = get_artist_genres(artist_name, api_key, genre_cache)
        if genres:
            return genres
    return []


def _categories_matching(genre_lower):
    """Which categories' keyword lists match a single (already-lowercased)
    genre tag."""
    return [
        category for category in config.CATEGORY_PRIORITY
        if any(keyword.lower() in genre_lower for keyword in config.GENRE_KEYWORDS[category])
    ]


def classify_track(genres):
    """Classify a track's genre tags into one of config.CATEGORY_PRIORITY's
    categories, or None if nothing matches.

    Primary method: walk the tags in rank order (Last.fm returns them
    pre-sorted by tag weight/count, and get_artist_genres preserves that
    order) and use the first tag that unambiguously identifies a single
    category -- i.e. look at the top tag first, the way you'd eyeball an
    artist's Last.fm page yourself, falling through to the next tag only if
    the current one is itself ambiguous (matches more than one category).

    Fallback: if no single tag ever resolves cleanly, score all tags by
    total keyword-hit count per category and break ties using
    CATEGORY_PRIORITY order (the original approach, kept as a safety net).
    """
    genres_lower = [g.lower() for g in genres]

    for genre in genres_lower:
        matches = _categories_matching(genre)
        if len(matches) == 1:
            return matches[0]
        # len == 0: this tag matches nothing, move to the next tag.
        # len > 1: this tag is itself ambiguous, move to the next tag
        # rather than guessing.

    best_category = None
    best_score = 0
    for category in config.CATEGORY_PRIORITY:
        keywords = config.GENRE_KEYWORDS[category]
        score = sum(
            1 for keyword in keywords for genre in genres_lower
            if keyword.lower() in genre
        )
        if score > best_score:
            best_score = score
            best_category = category
        # Equal scores: since we iterate CATEGORY_PRIORITY in order and only
        # replace on a strictly greater score, the first category in
        # priority order naturally wins ties.

    return best_category


def chunked(seq, size):
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sort tracks from the FG playlist into EDM / Pop Rock / Indie "
            "based on artist genres. Unmatched tracks are logged to "
            f"{config.LEFTOVER_FILE} instead of being guessed."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Print what would happen without adding tracks to any Spotify "
            f"playlist. {config.LEFTOVER_FILE} is still written so you can "
            "inspect it."
        ),
    )
    args = parser.parse_args()

    sp = get_client()
    lastfm_api_key = get_lastfm_api_key()

    print(f"Fetching tracks from FG ({config.SOURCE_PLAYLIST_ID})...")
    items = fetch_all_playlist_items(sp, config.SOURCE_PLAYLIST_ID)
    print(f"Fetched {len(items)} item(s).")

    genre_cache = {}
    plan = {category: [] for category in config.TARGET_PLAYLISTS}
    leftovers = []
    skipped_unavailable = 0

    for item in items:
        track = item.get("item")
        if track is None or track.get("id") is None or track.get("episode"):
            skipped_unavailable += 1
            continue

        track_name = track.get("name", "<unknown>")
        artists = track.get("artists", [])
        artist_name = artists[0]["name"] if artists else "<unknown artist>"
        uri = track.get("uri")

        genres = resolve_track_genres(track, lastfm_api_key, genre_cache)
        category = classify_track(genres) if genres else None

        track_info = {
            "name": track_name,
            "artist": artist_name,
            "uri": uri,
            "genres": genres,
        }

        if category is None:
            leftovers.append(track_info)
        else:
            plan[category].append(track_info)

    if skipped_unavailable:
        print(f"Skipped {skipped_unavailable} unavailable item(s) (local files or removed tracks).")

    # --- Print the plan ---
    for category, tracks in plan.items():
        print(f"\n{category} ({len(tracks)}):")
        for t in tracks:
            genre_str = ", ".join(t["genres"]) if t["genres"] else "(no genres)"
            print(f"  {t['name']} - {t['artist']}  [{genre_str}]")

    print(f"\nLeftovers ({len(leftovers)}):")
    for t in leftovers:
        genre_str = ", ".join(t["genres"]) if t["genres"] else "(no genre data)"
        print(f"  {t['name']} - {t['artist']}  [{genre_str}]")

    # --- Write leftover.txt (both modes) ---
    with open(config.LEFTOVER_FILE, "w", encoding="utf-8") as f:
        for t in leftovers:
            genre_str = ", ".join(t["genres"]) if t["genres"] else "(no genre data)"
            f.write(f"{t['name']} - {t['artist']} (genres: {genre_str})\n")

    # --- Add to target playlists (live mode only) ---
    if not args.dry_run:
        for category, tracks in plan.items():
            if not tracks:
                continue
            playlist_id = config.TARGET_PLAYLISTS[category]
            uris = [t["uri"] for t in tracks if t["uri"]]
            for chunk in chunked(uris, ADD_ITEMS_CHUNK_SIZE):
                sp.playlist_add_items(playlist_id, chunk)
            print(f"Added {len(uris)} track(s) to {category}.")

    # --- Summary ---
    print("\n=== Summary ===")
    total = len(items) - skipped_unavailable
    print(f"Total tracks processed: {total}")
    for category, tracks in plan.items():
        print(f"  {category}: {len(tracks)}")
    print(f"  Leftovers: {len(leftovers)} (see {config.LEFTOVER_FILE})")
    if args.dry_run:
        print("\nDry run: no tracks were added to Spotify.")
    else:
        print("\nDone. FG playlist was not modified.")


if __name__ == "__main__":
    main()

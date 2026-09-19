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

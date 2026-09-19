"""Multi-source genre classification: votes a track into one of the fixed
EDM / Pop Rock / Indie buckets (genre_config.py) using three independent
tag sources (Spotify artist genres, Last.fm artist+track tags, MusicBrainz
artist genre tags, all in genre_sources.py). A track is auto-sorted only
when 2+ sources agree on the same bucket ("high" confidence); a single
matching source, or sources that disagree, is "low" confidence and left
for manual review; no source matching at all is "none" (unmatched).
"""
from collections import Counter

import genre_config
import genre_sources

NEEDS_REVIEW = "Needs Review"
UNMATCHED = "Unmatched"


def classify_track_multi_source(track, cache):
    """Votes on a track's genre bucket using already-cached/prefetched
    source data. Spotify genres must be prefetched in bulk beforehand via
    genre_sources.prefetch_spotify_genres -- this function only reads the
    cache for Spotify, but fetches Last.fm/MusicBrainz on demand (per
    artist/track, cached as it goes).

    Returns {"bucket", "confidence", "votes", "raw_tags"}.
    """
    artists = track.get("artists") or []
    artist = artists[0] if artists else {}
    artist_name = artist.get("name") or "<unknown artist>"
    artist_id = artist.get("id")
    track_name = track.get("name", "")

    spotify_tags = genre_sources.get_spotify_artist_genres(artist_id, artist_name, cache)
    lastfm_tags = genre_sources.get_lastfm_tags(artist_name, track_name, cache)
    mb_tags = genre_sources.get_musicbrainz_artist_genres(artist_name, cache)

    votes = {
        "spotify": genre_config.classify_bucket(spotify_tags),
        "lastfm": genre_config.classify_bucket(lastfm_tags),
        "musicbrainz": genre_config.classify_bucket(mb_tags),
    }

    counts = Counter(v for v in votes.values() if v)
    if counts:
        bucket, n = counts.most_common(1)[0]
        if n >= 2:
            confidence = "high"
        else:
            confidence = "low"
            bucket = None
    else:
        bucket, confidence = None, "none"

    return {
        "bucket": bucket,
        "confidence": confidence,
        "votes": votes,
        "raw_tags": {"spotify": spotify_tags, "lastfm": lastfm_tags, "musicbrainz": mb_tags},
    }

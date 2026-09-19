"""Configuration for the FG genre-sorter CLI.

Edit GENRE_KEYWORDS / CATEGORY_PRIORITY / TARGET_PLAYLISTS here to change
behavior without touching spotify_sort.py.
"""

# Source playlist to read tracks from (never modified by this tool).
SOURCE_PLAYLIST_ID = "2T5Xhq3EnEA8k40MFW2cb4"  # FG

# Existing target playlists tracks get added to.
TARGET_PLAYLISTS = {
    "EDM": "1J2WtcgD7ZlR7Fr5r8vXx2",
    "Pop Rock": "5IZP8BfGte2HjR2KpT3WcB",
    "Indie": "7IazXkJ6fCrD0ptG4rh1CD",
}

# Tie-break order when a track scores equally across multiple categories.
# First entry wins ties.
CATEGORY_PRIORITY = ["Pop Rock", "EDM", "Indie"]

# Keyword lists used to score a track's combined artist genres against each
# category. Matching is case-insensitive substring matching (e.g. "electro"
# matches the Spotify genre "electro house").
GENRE_KEYWORDS = {
    "EDM": [
        "edm", "electro", "house", "deep house", "tropical house", "dubstep",
        "trance", "techno", "drum and bass", "dnb", "electronic", "dance pop",
        "big room", "future bass", "electropop", "electro house",
    ],
    "Pop Rock": [
        "pop rock", "alternative rock", "soft rock", "classic rock",
        "punk rock", "pop punk", "arena rock", "power pop", "glam rock",
        "hard rock", "garage rock", "britpop",
        # NOTE: deliberately no bare "rock" keyword -- it substring-matches
        # any "*-rock" compound genre (post-rock, math rock, space rock,
        # desert rock...) that isn't actually pop/mainstream rock, causing
        # false positives (e.g. Scenic's "post-rock" tag wrongly winning
        # Pop Rock). A track whose only rock-related tag is the bare word
        # "rock" with no more specific qualifier will land in Unsorted
        # instead -- rare, and reviewable there.
    ],
    "Indie": [
        "indie", "bedroom pop", "indie pop", "indie rock", "indie folk",
        "dream pop", "lo-fi", "singer-songwriter", "chamber pop",
    ],
}

# File leftover (unmatched) tracks are logged to, relative to this directory.
LEFTOVER_FILE = "leftover.txt"

# --- Full-library reorganizer settings (reorganize.py) ---

# Genre-shaped playlists eligible as sort destinations. Same dict as
# TARGET_PLAYLISTS above (kept as one alias so both scripts share one
# source of truth) -- add more entries here as you designate new genre
# playlists (e.g. a future "Hip-Hop/R&B" playlist).
GENRE_PLAYLISTS = TARGET_PLAYLISTS

# Playlist IDs the reorganizer will NEVER read tracks from or write tracks
# to, no matter what genre their contents might detect as. These are
# mood/language/curated playlists, not genre buckets, matched by ID (not
# name) to avoid trailing-whitespace footguns in playlist names.
PROTECTED_PLAYLIST_IDS = {
    "1RNPHeWHOITWt1nxqmVE23",  # Chill
    "2scIuvmJKgLwm03lEhjfWQ",  # Instrumental
    "6O3zWbPGLiL2F6ruOmrgx8",  # Calm
    "6KYytXohsxnxtFDjjDQpsS",  # Hindi
    "53r0AifCLpgUtGvcYSnvTb",  # WG
    "0MRyKKpke2fKFRWdkiDjcg",  # Telugu
    "2fDe030X5djsKb56UxeM1p",  # Hype
}

# Minimum size of an unclaimed genre cluster before the reorganizer will
# suggest creating a brand new playlist for it (smaller clusters fall
# through to the unsorted list instead).
NEW_PLAYLIST_MIN_TRACKS = 5

# When clustering tracks that matched none of GENRE_KEYWORDS, group by each
# track's top (highest-weighted) Last.fm tag. Near-synonym tags get folded
# into one cluster label here so e.g. "Hip-Hop", "hip hop" and "rap" count
# as the same cluster instead of three separate ones each below threshold.
# Keys are lowercase raw tag text; values are the cluster's display name.
# A top tag not listed here becomes its own title-cased cluster.
NEW_PLAYLIST_TAG_ALIASES = {
    "hip-hop": "Hip-Hop/Rap",
    "hip hop": "Hip-Hop/Rap",
    "rap": "Hip-Hop/Rap",
    "trap": "Hip-Hop/Rap",
    "rnb": "R&B",
    "r&b": "R&B",
    "neo-soul": "R&B",
    "neo soul": "R&B",
}

# Where the persistent (disk-backed) artist->genre cache lives, so repeated
# runs don't re-hit Last.fm for artists already resolved.
GENRE_CACHE_FILE = "genre_cache.json"

# Where the reorganizer's computed plan is saved for review before any
# writes happen.
REORG_PLAN_FILE = "reorg_plan.json"

UNSORTED_FILE = "unsorted.txt"

# OAuth scopes required (read source playlist, write to target playlists).
SPOTIFY_SCOPE = "playlist-read-private playlist-modify-private playlist-modify-public"

# Spotify's artist endpoint no longer returns genre data for apps without
# Extended Quota Mode, so genre tags are fetched from Last.fm instead
# (artist.getTopTags). Get a free key at https://www.last.fm/api/account/create
# and put it in secrets.env as LASTFM_API_KEY.
LASTFM_API_URL = "https://ws.audioscrobbler.com/2.0/"
# Only keep tags with at least this much relative weight (Last.fm's "count",
# 0-100 scale) to filter out noisy/unrelated tags.
LASTFM_MIN_TAG_COUNT = 10
# Max number of top tags to use per artist.
LASTFM_MAX_TAGS = 8

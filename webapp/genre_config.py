"""Genre bucket taxonomy for multi-source classification, mirroring the
root CLI's config.py (GENRE_KEYWORDS / CATEGORY_PRIORITY) so both tools
agree on what "EDM" / "Pop Rock" / "Indie" mean. Kept as its own copy here
rather than imported from the root config.py -- the webapp is run via
`uvicorn main:app` from inside webapp/, so the root package isn't on its
import path, and the webapp is otherwise self-contained from the CLI
scripts by design.
"""

CATEGORY_PRIORITY = ["Pop Rock", "EDM", "Indie"]

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
        # Deliberately no bare "rock" -- it substring-matches any "*-rock"
        # compound genre (post-rock, math rock, space rock...) that isn't
        # actually pop/mainstream rock.
    ],
    "Indie": [
        "indie", "bedroom pop", "indie pop", "indie rock", "indie folk",
        "dream pop", "lo-fi", "singer-songwriter", "chamber pop",
    ],
}


def _categories_matching(tag_lower):
    return [
        category for category in CATEGORY_PRIORITY
        if any(keyword.lower() in tag_lower for keyword in GENRE_KEYWORDS[category])
    ]


def classify_bucket(tags):
    """One source's best-guess bucket for a tag list, or None if nothing
    matches. Same two-stage logic as the CLI's classify_track(): first tag
    (in rank order) that unambiguously matches exactly one category wins;
    otherwise fall back to the highest keyword-hit score across all tags,
    tie-broken by CATEGORY_PRIORITY order."""
    tags_lower = [t.lower() for t in tags]
    for tag in tags_lower:
        matches = _categories_matching(tag)
        if len(matches) == 1:
            return matches[0]

    best_category = None
    best_score = 0
    for category in CATEGORY_PRIORITY:
        keywords = GENRE_KEYWORDS[category]
        score = sum(1 for keyword in keywords for tag in tags_lower if keyword.lower() in tag)
        if score > best_score:
            best_score = score
            best_category = category
    return best_category

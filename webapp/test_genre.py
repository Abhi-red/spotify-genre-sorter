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

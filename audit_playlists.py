"""Read-only audit for the FG genre-sort:

Step 1 - Reconcile: confirm every FG track landed in a target playlist or is
         a logged leftover.
Step 3 - Cross-verify Indie / Pop Rock / EDM against each other: find
         cross-playlist duplicate URIs, same-playlist duplicate URIs, and
         tracks sitting in a playlist that does not match their own
         Last.fm-derived genre (using the exact keyword lists / tie-break
         priority from config.py, via spotify_sort.py's own functions).

This script makes ZERO write/delete calls to Spotify. It only reads, prints
a findings report, and saves the computed plan to audit_plan.json so a
follow-up "apply" step can act on exactly what was reviewed here (instead of
re-deriving genres, which could drift if Last.fm's tags change between now
and when you approve the plan).
"""

import json
import re
from collections import defaultdict

import config
from spotify_sort import (
    get_client,
    get_lastfm_api_key,
    fetch_all_playlist_items,
    resolve_track_genres,
    classify_track,
)

LEFTOVER_LINE_RE = re.compile(r"^(?P<rest>.*) \(genres: .*\)$")


def parse_leftover_file(path):
    """Parse leftover.txt back into a list of (name, artist) tuples."""
    entries = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.rstrip("\n").rstrip("\r")
                if not line.strip():
                    continue
                m = LEFTOVER_LINE_RE.match(line)
                if not m:
                    entries.append((line, None))
                    continue
                rest = m.group("rest")
                # Artist is the last " - "-separated segment; track names can
                # themselves contain " - ", so split from the right.
                if " - " in rest:
                    name, artist = rest.rsplit(" - ", 1)
                else:
                    name, artist = rest, None
                entries.append((name, artist))
    except FileNotFoundError:
        pass
    return entries


def track_name_artist(track):
    name = track.get("name", "<unknown>")
    artists = track.get("artists", [])
    artist = artists[0]["name"] if artists else "<unknown artist>"
    return name, artist


def extract_track(item):
    """Return the track dict for a playlist item, or None if unavailable."""
    track = item.get("item")
    if track is None or track.get("id") is None or track.get("episode"):
        return None
    return track


def main():
    sp = get_client()
    lastfm_api_key = get_lastfm_api_key()
    genre_cache = {}

    print("Fetching current playlist contents...")
    fg_items = fetch_all_playlist_items(sp, config.SOURCE_PLAYLIST_ID)
    target_raw_items = {
        name: fetch_all_playlist_items(sp, pid)
        for name, pid in config.TARGET_PLAYLISTS.items()
    }

    fg_tracks = [t for t in (extract_track(i) for i in fg_items) if t]
    target_tracks = {
        name: [t for t in (extract_track(i) for i in items) if t]
        for name, items in target_raw_items.items()
    }

    print("FG: " + str(len(fg_tracks)) + " tracks")
    for name, tracks in target_tracks.items():
        print(name + ": " + str(len(tracks)) + " tracks")

    # ------------------------------------------------------------------
    # STEP 1: Reconcile FG against (EDM union Pop Rock union Indie union leftover.txt)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 1: FG RECONCILIATION")
    print("=" * 70)

    # uri -> set of playlist names it currently appears in
    uri_to_playlists = defaultdict(set)
    for name, tracks in target_tracks.items():
        for t in tracks:
            uri_to_playlists[t["uri"]].add(name)

    leftover_entries = parse_leftover_file(config.LEFTOVER_FILE)
    # Exact-match set, plus a case-insensitive fallback set.
    leftover_exact = set(leftover_entries)
    leftover_ci = set((n.lower(), (a or "").lower()) for n, a in leftover_entries)

    sorted_count = 0
    leftover_matched = 0
    missing = []
    fg_status = []  # (name, artist, status, detail)

    for t in fg_tracks:
        name, artist = track_name_artist(t)
        uri = t["uri"]
        playlists_containing = uri_to_playlists.get(uri, set())
        if playlists_containing:
            sorted_count += 1
            fg_status.append((name, artist, "sorted", ", ".join(sorted(playlists_containing))))
            continue
        if (name, artist) in leftover_exact or (name.lower(), artist.lower()) in leftover_ci:
            leftover_matched += 1
            fg_status.append((name, artist, "leftover", "matched in leftover.txt"))
            continue
        missing.append((name, artist, uri))
        fg_status.append((name, artist, "MISSING", "not in any target playlist or leftover.txt"))

    total_fg = len(fg_tracks)
    accounted = sorted_count + leftover_matched
    print("\n" + str(total_fg) + " FG tracks = " + str(sorted_count) + " sorted + "
          + str(leftover_matched) + " leftover-matched + " + str(len(missing)) + " missing")

    if missing:
        print("\n*** " + str(len(missing)) + " FG TRACK(S) UNACCOUNTED FOR ***")
        for name, artist, uri in missing:
            print("  MISSING: " + name + " - " + artist + "  (uri: " + str(uri) + ")")
        step1_passed = False
    else:
        print(str(total_fg) + " FG tracks = " + str(sorted_count) + " sorted + "
              + str(leftover_matched) + " leftover = " + str(total_fg) + "  [OK]")
        step1_passed = True

    if step1_passed:
        print("\nFG deletion eligibility: PASS - safe to delete once you confirm")
    else:
        print("\nFG deletion eligibility: FAIL - do NOT delete FG")

    # ------------------------------------------------------------------
    # STEP 3: Cross-verify + de-duplicate Indie / Pop Rock / EDM
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("STEP 3: CROSS-PLAYLIST AUDIT (Indie / Pop Rock / EDM)")
    print("=" * 70)

    # Same-playlist duplicates: count uri occurrences within each playlist's
    # own item list (not deduped by set).
    same_playlist_dupes = []  # (playlist, name, artist, uri, count)
    for pname, tracks in target_tracks.items():
        counts = defaultdict(int)
        for t in tracks:
            counts[t["uri"]] += 1
        for uri, count in counts.items():
            if count > 1:
                sample = next(t for t in tracks if t["uri"] == uri)
                name, artist = track_name_artist(sample)
                same_playlist_dupes.append((pname, name, artist, uri, count))

    # Cross-playlist duplicates: uri present in more than one playlist.
    cross_dupes = {uri: pls for uri, pls in uri_to_playlists.items() if len(pls) > 1}

    # Classify every unique track (by uri) across the three target playlists.
    unique_uri_track = {}
    for pname, tracks in target_tracks.items():
        for t in tracks:
            unique_uri_track.setdefault(t["uri"], t)

    print("\nClassifying " + str(len(unique_uri_track)) + " unique tracks across target playlists via Last.fm...")
    detected_category = {}
    for i, (uri, t) in enumerate(unique_uri_track.items(), 1):
        genres = resolve_track_genres(t, lastfm_api_key, genre_cache)
        detected_category[uri] = (classify_track(genres) if genres else None, genres)
        if i % 20 == 0:
            print("  ..." + str(i) + "/" + str(len(unique_uri_track)))

    # Cross-playlist duplicate resolution via CATEGORY_PRIORITY.
    dupe_report = []
    for uri, playlists in cross_dupes.items():
        t = unique_uri_track[uri]
        name, artist = track_name_artist(t)
        keep = next(p for p in config.CATEGORY_PRIORITY if p in playlists)
        remove_from = sorted(playlists - {keep})
        dupe_report.append({
            "uri": uri, "name": name, "artist": artist,
            "in_playlists": sorted(playlists), "keep": keep, "remove_from": remove_from,
        })

    # Genre mismatches: track's current playlist(s) vs detected_category,
    # evaluated per (uri, playlist) pair the track is actually sitting in.
    mismatch_report = []
    for uri, playlists in uri_to_playlists.items():
        cat, genres = detected_category[uri]
        if cat is None:
            continue  # no positive signal, nothing to move to, leave alone
        t = unique_uri_track[uri]
        name, artist = track_name_artist(t)
        for p in playlists:
            if p != cat:
                mismatch_report.append({
                    "uri": uri, "name": name, "artist": artist,
                    "current_playlist": p, "detected_genres": genres,
                    "target_playlist": cat,
                })

    print("\nCross-playlist duplicates found: " + str(len(dupe_report)))
    for d in dupe_report:
        print("  DUPLICATE: " + d["name"] + " - " + d["artist"])
        print("    in: " + ", ".join(d["in_playlists"]))
        print("    keep in: " + d["keep"] + "  (config.py CATEGORY_PRIORITY order)  |  remove from: " + ", ".join(d["remove_from"]))

    print("\nGenre mismatches found: " + str(len(mismatch_report)))
    for m in mismatch_report:
        genre_str = ", ".join(m["detected_genres"]) if m["detected_genres"] else "(none)"
        print("  MISMATCH: " + m["name"] + " - " + m["artist"])
        print("    currently in: " + m["current_playlist"] + "  ->  should move to: " + m["target_playlist"])
        print("    detected genres: " + genre_str)

    print("\nSame-playlist duplicates found: " + str(len(same_playlist_dupes)))
    for pname, name, artist, uri, count in same_playlist_dupes:
        print("  SAME-PLAYLIST DUP: " + name + " - " + artist + "  in " + pname + "  (appears " + str(count) + "x)")

    print("\n" + "-" * 70)
    print("SUMMARY: " + str(len(dupe_report)) + " cross-playlist duplicates, "
          + str(len(mismatch_report)) + " genre-mismatches, "
          + str(len(same_playlist_dupes)) + " same-playlist duplicates")
    print("-" * 70)

    # ------------------------------------------------------------------
    # Save plan for the (separate, confirmation-gated) apply step.
    # ------------------------------------------------------------------
    plan = {
        "step1": {
            "passed": step1_passed,
            "total_fg": total_fg,
            "sorted_count": sorted_count,
            "leftover_matched": leftover_matched,
            "missing": [{"name": n, "artist": a, "uri": u} for n, a, u in missing],
        },
        "step3": {
            "cross_playlist_duplicates": dupe_report,
            "genre_mismatches": mismatch_report,
            "same_playlist_duplicates": [
                {"playlist": p, "name": n, "artist": a, "uri": u, "count": c}
                for p, n, a, u, c in same_playlist_dupes
            ],
        },
        "playlist_counts_before": {name: len(tracks) for name, tracks in target_tracks.items()},
    }
    with open("audit_plan.json", "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)
    print("\nFull plan saved to audit_plan.json for review.")
    print("NOTHING has been written or deleted on Spotify. Awaiting your go-ahead.")


if __name__ == "__main__":
    main()

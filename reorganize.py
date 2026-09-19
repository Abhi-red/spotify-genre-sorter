"""Full-library genre reorganizer (read-only dry-run, no Spotify writes).

Generalizes the FG one-shot sorter into a repeatable tool that:
  1. Reads every playlist you OWN (never a followed/collaborative one --
     Spotify's API won't even let this app read those, and this tool has
     no business restructuring someone else's playlist anyway).
  2. Skips anything in config.PROTECTED_PLAYLIST_IDS entirely (mood/language
     collections you told it never to touch).
  3. Treats config.GENRE_PLAYLISTS as the only eligible sort destinations --
     no guessing from playlist names.
  4. Classifies every track currently sitting in a genre playlist using the
     same keyword + Last.fm approach as spotify_sort.py (top-tag-first,
     falling back to aggregate keyword scoring + CATEGORY_PRIORITY).
  5. Works out each track's single best home, resolving cross-playlist
     duplicates and same-playlist duplicates along the way.
  6. Prints a structured before/after plan and saves it to
     config.REORG_PLAN_FILE. Makes ZERO write/delete calls to Spotify.

Any owned playlist that is neither protected nor a known genre playlist is
flagged, not touched -- you decide what it is before this tool acts on it.
"""

import json
import os
from collections import defaultdict

import config
from spotify_sort import (
    get_client,
    get_lastfm_api_key,
    fetch_all_playlist_items,
    resolve_track_genres,
    classify_track,
)


def load_genre_cache():
    if os.path.exists(config.GENRE_CACHE_FILE):
        with open(config.GENRE_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_genre_cache(cache):
    with open(config.GENRE_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


def extract_track(item):
    track = item.get("item")
    if track is None or track.get("id") is None or track.get("episode"):
        return None
    return track


def track_name_artist(track):
    name = track.get("name", "<unknown>")
    artists = track.get("artists", [])
    artist = artists[0]["name"] if artists else "<unknown artist>"
    return name, artist


def get_owned_playlists(sp):
    me = sp.current_user()
    my_id = me["id"]
    results = sp.current_user_playlists(limit=50)
    items = results["items"]
    while results.get("next"):
        results = sp.next(results)
        items.extend(results["items"])
    return [p for p in items if p.get("owner", {}).get("id") == my_id]


def main():
    sp = get_client()
    lastfm_api_key = get_lastfm_api_key()
    genre_cache = load_genre_cache()
    cache_size_before = len(genre_cache)

    print("Fetching your owned playlists...")
    owned = get_owned_playlists(sp)
    genre_ids = set(config.GENRE_PLAYLISTS.values())
    protected_ids = config.PROTECTED_PLAYLIST_IDS

    genre_playlists = {p["name"]: p["id"] for p in owned if p["id"] in genre_ids}
    protected_playlists = [p for p in owned if p["id"] in protected_ids]
    other_owned = [
        p for p in owned
        if p["id"] not in genre_ids and p["id"] not in protected_ids
    ]

    print(f"Owned playlists: {len(owned)}")
    print(f"  Genre playlists in scope: {list(config.GENRE_PLAYLISTS.keys())}")
    print(f"  Protected (untouched): {[p['name'] for p in protected_playlists]}")
    if other_owned:
        print(f"  UNCLASSIFIED (owned, not protected, not a genre playlist -- SKIPPING, please classify):")
        for p in other_owned:
            print(f"    - {p['name']} ({p['id']})")
    else:
        print("  Unclassified owned playlists: none")

    # ------------------------------------------------------------------
    # Fetch current contents of every genre playlist.
    # ------------------------------------------------------------------
    target_tracks = {}
    for canonical_name, pid in config.GENRE_PLAYLISTS.items():
        items = fetch_all_playlist_items(sp, pid)
        target_tracks[canonical_name] = [t for t in (extract_track(i) for i in items) if t]

    print()
    for name, tracks in target_tracks.items():
        print(f"{name}: {len(tracks)} tracks (current)")

    # uri -> set of canonical playlist names it currently appears in
    uri_to_playlists = defaultdict(set)
    for name, tracks in target_tracks.items():
        for t in tracks:
            uri_to_playlists[t["uri"]].add(name)

    # Same-playlist duplicates (exact URI repeated within one playlist's own list).
    same_playlist_dupes = []
    for pname, tracks in target_tracks.items():
        counts = defaultdict(int)
        for t in tracks:
            counts[t["uri"]] += 1
        for uri, count in counts.items():
            if count > 1:
                sample = next(t for t in tracks if t["uri"] == uri)
                name, artist = track_name_artist(sample)
                same_playlist_dupes.append({"playlist": pname, "name": name, "artist": artist, "uri": uri, "count": count})

    # ------------------------------------------------------------------
    # Classify every unique track currently in a genre playlist.
    # ------------------------------------------------------------------
    unique_uri_track = {}
    for tracks in target_tracks.values():
        for t in tracks:
            unique_uri_track.setdefault(t["uri"], t)

    print(f"\nClassifying {len(unique_uri_track)} unique tracks via Last.fm "
          f"(cache has {cache_size_before} artists already resolved)...")
    detected = {}  # uri -> (category_or_None, genres)
    for i, (uri, t) in enumerate(unique_uri_track.items(), 1):
        genres = resolve_track_genres(t, lastfm_api_key, genre_cache)
        detected[uri] = (classify_track(genres) if genres else None, genres)
        if i % 25 == 0:
            print(f"  ...{i}/{len(unique_uri_track)}")
    save_genre_cache(genre_cache)
    print(f"Genre cache saved ({len(genre_cache)} artists total, "
          f"{len(genre_cache) - cache_size_before} newly resolved this run).")

    # ------------------------------------------------------------------
    # Work out each track's single final home.
    #
    # Resolution rule: a positive genre detection always wins (that's the
    # whole point of the tool). CATEGORY_PRIORITY is only consulted when a
    # track is duplicated across playlists AND has no positive genre signal
    # at all -- there's nothing else to break the tie with in that case. A
    # non-duplicated track with no genre signal is left exactly where it
    # already is (no evidence to justify moving it).
    # ------------------------------------------------------------------
    final_home = {}
    no_signal_singleton = []  # tracks left in place, no genre match, not a dup
    for uri, playlists in uri_to_playlists.items():
        cat, genres = detected[uri]
        if cat is not None:
            final_home[uri] = cat
        elif len(playlists) > 1:
            final_home[uri] = next(p for p in config.CATEGORY_PRIORITY if p in playlists)
        else:
            final_home[uri] = next(iter(playlists))
            no_signal_singleton.append(uri)

    # ------------------------------------------------------------------
    # Build the before/after report per playlist.
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("REORGANIZATION PLAN (dry run -- nothing written to Spotify)")
    print("=" * 70)

    per_playlist_report = {}
    for pname in config.GENRE_PLAYLISTS:
        raw_count = len(target_tracks[pname])
        before_uris = {t["uri"] for t in target_tracks[pname]}
        stays = []
        moving_out = []
        for uri in before_uris:
            if final_home[uri] == pname:
                stays.append(uri)
            else:
                moving_out.append(uri)
        moving_in = [uri for uri, home in final_home.items() if home == pname and uri not in before_uris]

        after_count = len(stays) + len(moving_in)
        per_playlist_report[pname] = {
            "before": len(before_uris),
            "stays": len(stays),
            "moving_out": moving_out,
            "moving_in": moving_in,
            "after": after_count,
        }

        before_label = f"{raw_count} tracks" if raw_count == len(before_uris) else (
            f"{raw_count} tracks, {len(before_uris)} unique (has same-playlist duplicates, see below)"
        )
        print(f"\n{pname.upper()} (currently {before_label})")
        print(f"  Stays: {len(stays)}")
        print(f"  Moving OUT: {len(moving_out)}")
        for uri in moving_out:
            t = unique_uri_track[uri]
            name, artist = track_name_artist(t)
            cat, genres = detected[uri]
            reason = f"detected genre -> {cat}" if cat else "duplicate, kept elsewhere per CATEGORY_PRIORITY"
            genre_str = ", ".join(genres) if genres else "(none)"
            print(f"    - {name} - {artist}  =>  {final_home[uri]}  [{reason}; tags: {genre_str}]")
        print(f"  Moving IN: {len(moving_in)}")
        for uri in moving_in:
            t = unique_uri_track[uri]
            name, artist = track_name_artist(t)
            src = ", ".join(sorted(uri_to_playlists[uri]))
            cat, genres = detected[uri]
            genre_str = ", ".join(genres) if genres else "(none)"
            print(f"    - {name} - {artist}  <=  from {src}  [tags: {genre_str}]")
        print(f"  Result: {after_count} tracks")

    if same_playlist_dupes:
        print(f"\nSAME-PLAYLIST DUPLICATES ({len(same_playlist_dupes)}):")
        for d in same_playlist_dupes:
            print(f"  {d['name']} - {d['artist']}  in {d['playlist']}  (appears {d['count']}x, extra copies removed)")
    else:
        print("\nSAME-PLAYLIST DUPLICATES: none")

    # Cluster the no-genre-signal tracks by their top Last.fm tag (folding
    # near-synonyms together via config.NEW_PLAYLIST_TAG_ALIASES) to see if
    # any group is large enough to warrant a brand new playlist suggestion.
    clusters = defaultdict(list)
    no_cluster = []
    for uri in no_signal_singleton:
        _, genres = detected[uri]
        if not genres:
            no_cluster.append(uri)
            continue
        top_tag = genres[0].lower()
        label = config.NEW_PLAYLIST_TAG_ALIASES.get(top_tag, genres[0].title())
        clusters[label].append(uri)

    suggested_playlists = {
        label: uris for label, uris in clusters.items()
        if len(uris) >= config.NEW_PLAYLIST_MIN_TRACKS
    }
    unsorted_uris = no_cluster + [
        uri for label, uris in clusters.items()
        if len(uris) < config.NEW_PLAYLIST_MIN_TRACKS
        for uri in uris
    ]

    if suggested_playlists:
        print(f"\nSUGGESTED NEW PLAYLISTS ({len(suggested_playlists)}):")
        for label, uris in suggested_playlists.items():
            print(f"\n  \"{label}\" ({len(uris)} tracks)")
            for uri in uris:
                t = unique_uri_track[uri]
                name, artist = track_name_artist(t)
                pname = next(iter(uri_to_playlists[uri]))
                _, genres = detected[uri]
                print(f"    - {name} - {artist}  (currently in {pname}; tags: {', '.join(genres)})")
    else:
        print("\nSUGGESTED NEW PLAYLISTS: none")

    if unsorted_uris:
        print(f"\nUNSORTED, LEFT IN PLACE -- no cluster reached the "
              f"{config.NEW_PLAYLIST_MIN_TRACKS}-track minimum ({len(unsorted_uris)}):")
        with open(config.UNSORTED_FILE, "w", encoding="utf-8") as f:
            for uri in unsorted_uris:
                t = unique_uri_track[uri]
                name, artist = track_name_artist(t)
                pname = next(iter(uri_to_playlists[uri]))
                _, genres = detected[uri]
                genre_str = ", ".join(genres) if genres else "(no genre data)"
                print(f"  {name} - {artist}  (stays in {pname}; tags: {genre_str})")
                f.write(f"{name} - {artist} (currently in {pname}; tags: {genre_str})\n")
        print(f"  (also written to {config.UNSORTED_FILE})")
    else:
        print("\nUNSORTED: none")

    if other_owned:
        print(f"\nUNCLASSIFIED OWNED PLAYLISTS (not read, not touched -- decide protect vs. genre-home): "
              f"{[p['name'] for p in other_owned]}")

    print("\n" + "-" * 70)
    total_moves = sum(len(r["moving_out"]) for r in per_playlist_report.values())
    print(f"SUMMARY: {total_moves} track moves, "
          f"{len(same_playlist_dupes)} same-playlist duplicates to remove, "
          f"{len(suggested_playlists)} new playlist(s) suggested "
          f"({sum(len(u) for u in suggested_playlists.values())} tracks), "
          f"{len(unsorted_uris)} left unsorted in place")
    print("-" * 70)

    # ------------------------------------------------------------------
    # Save the plan.
    # ------------------------------------------------------------------
    plan = {
        "per_playlist": {
            pname: {
                "before": r["before"],
                "after": r["after"],
                "moving_out": [
                    {
                        "uri": uri,
                        "name": track_name_artist(unique_uri_track[uri])[0],
                        "artist": track_name_artist(unique_uri_track[uri])[1],
                        "to": final_home[uri],
                    }
                    for uri in r["moving_out"]
                ],
                "moving_in": [
                    {
                        "uri": uri,
                        "name": track_name_artist(unique_uri_track[uri])[0],
                        "artist": track_name_artist(unique_uri_track[uri])[1],
                        "from": sorted(uri_to_playlists[uri]),
                    }
                    for uri in r["moving_in"]
                ],
            }
            for pname, r in per_playlist_report.items()
        },
        "same_playlist_duplicates": same_playlist_dupes,
        "suggested_new_playlists": {
            label: [
                {
                    "uri": uri,
                    "name": track_name_artist(unique_uri_track[uri])[0],
                    "artist": track_name_artist(unique_uri_track[uri])[1],
                    "current_playlist": next(iter(uri_to_playlists[uri])),
                    "tags": detected[uri][1],
                }
                for uri in uris
            ]
            for label, uris in suggested_playlists.items()
        },
        "unsorted": [
            {
                "uri": uri,
                "name": track_name_artist(unique_uri_track[uri])[0],
                "artist": track_name_artist(unique_uri_track[uri])[1],
                "current_playlist": next(iter(uri_to_playlists[uri])),
                "tags": detected[uri][1],
            }
            for uri in unsorted_uris
        ],
        "unclassified_owned_playlists": [{"name": p["name"], "id": p["id"]} for p in other_owned],
        "genre_playlist_ids": config.GENRE_PLAYLISTS,
    }
    with open(config.REORG_PLAN_FILE, "w", encoding="utf-8") as f:
        json.dump(plan, f, indent=2, ensure_ascii=False)

    print(f"\nFull plan saved to {config.REORG_PLAN_FILE}.")
    print("NOTHING has been written or deleted on Spotify. Awaiting your review and explicit go-ahead.")


if __name__ == "__main__":
    main()

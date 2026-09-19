"""Apply STEP 1 ONLY of reorg_plan.json:
  - the cross-genre mismatch moves ("moving_out" entries) among EDM/Pop
    Rock/Indie
  - the same-playlist duplicate cleanup (Capital Cities in EDM)

Deliberately does NOT create the suggested new playlists (Hip-Hop/Rap,
R&B) and does NOT touch the unsorted tracks -- those are separate,
still-pending decisions the user has not approved yet.

Re-verifies current playlist membership live before acting (the plan may
have gone stale between dry-run and approval), skips anything that no
longer matches what the plan expected instead of failing outright, and
never re-adds a track that's already correctly sitting in its target
playlist (handles the cross-playlist-duplicate case without recreating the
very duplicate being resolved).
"""

import json
from collections import defaultdict

import config
from spotify_sort import get_client, fetch_all_playlist_items
from reorganize import extract_track

CHUNK_SIZE = 100


def chunked(seq, size):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


def fetch_current_uris(sp):
    current = {}
    for pname, pid in config.GENRE_PLAYLISTS.items():
        items = fetch_all_playlist_items(sp, pid)
        uris = set()
        for it in items:
            t = extract_track(it)
            if t:
                uris.add(t["uri"])
        current[pname] = uris
    return current


def main():
    with open(config.REORG_PLAN_FILE, "r", encoding="utf-8") as f:
        plan = json.load(f)

    sp = get_client()

    print("Re-fetching live playlist state (plan may be stale)...")
    current_uris = fetch_current_uris(sp)
    before_counts = {p: len(u) for p, u in current_uris.items()}

    remove_actions = defaultdict(set)
    add_actions = defaultdict(set)
    skipped = []
    already_in_target = []

    for pname, data in plan["per_playlist"].items():
        for entry in data["moving_out"]:
            uri, to = entry["uri"], entry["to"]
            if uri not in current_uris.get(pname, set()):
                skipped.append((pname, entry["name"], entry["artist"], "no longer in source playlist"))
                continue
            remove_actions[pname].add(uri)
            if uri in current_uris.get(to, set()):
                already_in_target.append((pname, to, entry["name"], entry["artist"]))
            else:
                add_actions[to].add(uri)

    dup_fixes = []
    for d in plan["same_playlist_duplicates"]:
        pname, uri = d["playlist"], d["uri"]
        if uri in current_uris.get(pname, set()):
            dup_fixes.append((pname, uri, d["name"], d["artist"]))
        else:
            skipped.append((pname, d["name"], d["artist"], "duplicate track no longer present"))

    print("\nApplying Step 1: genre-mismatch moves + same-playlist duplicate cleanup")
    print(f"  Removals across playlists: {sum(len(v) for v in remove_actions.values())}")
    print(f"  Additions across playlists: {sum(len(v) for v in add_actions.values())}")
    print(f"  Already correctly in target (duplicate resolution, remove-only): {len(already_in_target)}")
    for pname, to, name, artist in already_in_target:
        print(f"    - {name} - {artist}: removing from {pname} (already present in {to})")
    print(f"  Same-playlist duplicate fixes: {len(dup_fixes)}")
    if skipped:
        print(f"  SKIPPED (stale vs. live state, {len(skipped)}):")
        for pname, name, artist, reason in skipped:
            print(f"    - {name} - {artist} ({pname}): {reason}")

    # --- Execute removals ---
    for pname, uris in remove_actions.items():
        pid = config.GENRE_PLAYLISTS[pname]
        for chunk in chunked(uris, CHUNK_SIZE):
            sp.playlist_remove_all_occurrences_of_items(pid, chunk)
        print(f"Removed {len(uris)} track(s) from {pname}")

    # --- Execute additions ---
    for pname, uris in add_actions.items():
        pid = config.GENRE_PLAYLISTS[pname]
        for chunk in chunked(uris, CHUNK_SIZE):
            sp.playlist_add_items(pid, chunk)
        print(f"Added {len(uris)} track(s) to {pname}")

    # --- Execute same-playlist duplicate cleanup ---
    for pname, uri, name, artist in dup_fixes:
        pid = config.GENRE_PLAYLISTS[pname]
        sp.playlist_remove_all_occurrences_of_items(pid, [uri])
        sp.playlist_add_items(pid, [uri])
        print(f"Deduplicated '{name} - {artist}' in {pname} (now 1 copy)")

    # --- Verify final state ---
    print("\n=== Verification ===")
    after_uris = fetch_current_uris(sp)
    after_counts = {p: len(u) for p, u in after_uris.items()}

    print(f"{'Playlist':<12} {'Before':>8} {'After':>8}")
    for pname in config.GENRE_PLAYLISTS:
        print(f"{pname:<12} {before_counts[pname]:>8} {after_counts[pname]:>8}")

    total_before = sum(before_counts.values())
    total_after = sum(after_counts.values())
    print(f"\nTotal unique tracks before (summed per-playlist, cross-playlist dup counted once per playlist it was in): {total_before}")
    print(f"Total unique tracks after: {total_after}")

    # Sanity check: no track should have vanished entirely. Every uri that
    # was somewhere before should be somewhere after.
    before_union = set()
    for u in current_uris.values():
        before_union |= u
    after_union = set()
    for u in after_uris.values():
        after_union |= u
    vanished = before_union - after_union
    if vanished:
        print(f"\n*** WARNING: {len(vanished)} track(s) present before are missing entirely after! ***")
        for uri in vanished:
            print(f"  {uri}")
    else:
        print("\nNo tracks vanished -- every track that existed before still exists in at least one playlist.")


if __name__ == "__main__":
    main()

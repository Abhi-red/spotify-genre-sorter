"""One-off verification script (no pytest in this project) -- run with
`python test_genre_taxonomy.py` from webapp/. Prints PASS/FAIL per case
and exits non-zero on any failure."""
import genre_taxonomy as gt

failures = []


def check(label, actual, expected):
    if actual != expected:
        failures.append(f"{label}: expected {expected!r}, got {actual!r}")


check("rap alias", gt.normalize_tag("rap"), "Hip-Hop/Rap")
check("hip hop alias", gt.normalize_tag("Hip-Hop"), "Hip-Hop/Rap")
check("trap latino alias", gt.normalize_tag("trap latino"), "Latin")
check("rnb alias", gt.normalize_tag("rnb"), "R&B")
check("k-pop alias", gt.normalize_tag("K-Pop"), "K-Pop")
check("unrecognized tag title-cased", gt.normalize_tag("chillhop"), "Chillhop")
check("nationality tag filtered", gt.normalize_tag("Canadian"), None)
check("nationality tag filtered case-insensitive", gt.normalize_tag("korean"), None)
check("empty tag", gt.normalize_tag(""), None)
check("none tag", gt.normalize_tag(None), None)
check("whitespace-only tag", gt.normalize_tag("   "), None)

if failures:
    print(f"FAIL ({len(failures)}):")
    for f in failures:
        print(" -", f)
    raise SystemExit(1)
print(f"PASS: all checks ok")

"""Parent-genre taxonomy for open-ended genre detection. Unlike the old
3-bucket system (EDM/Pop Rock/Indie), there is no fixed set of allowed
outputs here -- GENRE_ALIASES folds common subgenre spellings up into a
smaller set of recognizable parent genres, but a tag with no entry here
is never dropped, just shown as its own title-cased genre. Extend
coverage over time by adding entries to GENRE_ALIASES/NON_GENRE_TAGS --
no code changes needed.
"""

PARENT_GENRES = [
    "Hip-Hop/Rap", "R&B", "Pop", "Rock", "Indie", "Metal", "Punk",
    "EDM/Electronic", "Folk/Country", "Latin", "Reggae", "Jazz",
    "Classical", "Blues/Soul", "Afrobeats", "K-Pop", "World",
]

GENRE_ALIASES = {
    # Hip-Hop/Rap
    "rap": "Hip-Hop/Rap", "hip hop": "Hip-Hop/Rap", "hip-hop": "Hip-Hop/Rap",
    "trap": "Hip-Hop/Rap", "cloud rap": "Hip-Hop/Rap", "drill": "Hip-Hop/Rap",
    "uk drill": "Hip-Hop/Rap", "gangsta rap": "Hip-Hop/Rap",
    "boom bap": "Hip-Hop/Rap", "mumble rap": "Hip-Hop/Rap",
    "conscious hip hop": "Hip-Hop/Rap", "alternative hip hop": "Hip-Hop/Rap",
    "hardcore hip hop": "Hip-Hop/Rap", "southern hip hop": "Hip-Hop/Rap",
    "pop rap": "Hip-Hop/Rap", "west coast hip hop": "Hip-Hop/Rap",
    "east coast hip hop": "Hip-Hop/Rap", "emo rap": "Hip-Hop/Rap",
    "chill hip hop": "Hip-Hop/Rap", "lo-fi hip hop": "Hip-Hop/Rap",
    "horrorcore": "Hip-Hop/Rap",

    # R&B
    "r&b": "R&B", "rnb": "R&B", "neo-soul": "R&B", "neo soul": "R&B",
    "contemporary r&b": "R&B", "quiet storm": "R&B",
    "alternative r&b": "R&B", "new jack swing": "R&B",

    # Pop
    "pop": "Pop", "dance pop": "Pop", "synth-pop": "Pop", "synthpop": "Pop",
    "electropop": "Pop", "teen pop": "Pop", "bubblegum pop": "Pop",

    # Rock
    "rock": "Rock", "alternative rock": "Rock", "classic rock": "Rock",
    "hard rock": "Rock", "garage rock": "Rock", "arena rock": "Rock",
    "pop rock": "Rock", "power pop": "Rock", "soft rock": "Rock",
    "britpop": "Rock", "glam rock": "Rock", "prog rock": "Rock",
    "progressive rock": "Rock", "psychedelic rock": "Rock",
    "southern rock": "Rock", "surf rock": "Rock",

    # Indie
    "indie": "Indie", "indie rock": "Indie", "indie pop": "Indie",
    "indie folk": "Indie", "bedroom pop": "Indie", "dream pop": "Indie",
    "lo-fi": "Indie", "lo fi": "Indie", "chamber pop": "Indie",
    "slacker rock": "Indie",

    # Metal
    "metal": "Metal", "heavy metal": "Metal", "death metal": "Metal",
    "black metal": "Metal", "metalcore": "Metal", "nu metal": "Metal",
    "thrash metal": "Metal", "doom metal": "Metal", "power metal": "Metal",
    "progressive metal": "Metal", "symphonic metal": "Metal",

    # Punk
    "punk": "Punk", "pop punk": "Punk", "punk rock": "Punk",
    "hardcore punk": "Punk", "emo": "Punk", "post-hardcore": "Punk",
    "ska punk": "Punk", "garage punk": "Punk",

    # EDM/Electronic
    "edm": "EDM/Electronic", "house": "EDM/Electronic",
    "deep house": "EDM/Electronic", "tropical house": "EDM/Electronic",
    "techno": "EDM/Electronic", "trance": "EDM/Electronic",
    "dubstep": "EDM/Electronic", "drum and bass": "EDM/Electronic",
    "dnb": "EDM/Electronic", "electronic": "EDM/Electronic",
    "future bass": "EDM/Electronic", "electro house": "EDM/Electronic",
    "big room": "EDM/Electronic", "chillwave": "EDM/Electronic",
    "synthwave": "EDM/Electronic", "garage": "EDM/Electronic",
    "breakbeat": "EDM/Electronic", "downtempo": "EDM/Electronic",
    "idm": "EDM/Electronic", "glitch": "EDM/Electronic",

    # Folk/Country
    "folk": "Folk/Country", "country": "Folk/Country",
    "americana": "Folk/Country", "bluegrass": "Folk/Country",
    "singer-songwriter": "Folk/Country", "country pop": "Folk/Country",
    "folk rock": "Folk/Country", "alt-country": "Folk/Country",

    # Latin
    "latin": "Latin", "reggaeton": "Latin", "latin pop": "Latin",
    "latin trap": "Latin", "trap latino": "Latin", "salsa": "Latin",
    "bachata": "Latin", "cumbia": "Latin", "merengue": "Latin",
    "latin rock": "Latin", "regional mexican": "Latin", "banda": "Latin",

    # Reggae
    "reggae": "Reggae", "dancehall": "Reggae", "dub": "Reggae",
    "ska": "Reggae",

    # Jazz
    "jazz": "Jazz", "smooth jazz": "Jazz", "bebop": "Jazz",
    "jazz fusion": "Jazz", "swing": "Jazz", "big band": "Jazz",

    # Classical
    "classical": "Classical", "orchestral": "Classical",
    "baroque": "Classical", "opera": "Classical",
    "chamber music": "Classical",

    # Blues/Soul
    "blues": "Blues/Soul", "soul": "Blues/Soul", "funk": "Blues/Soul",
    "motown": "Blues/Soul", "gospel": "Blues/Soul",
    "delta blues": "Blues/Soul",

    # Afrobeats
    "afrobeats": "Afrobeats", "afropop": "Afrobeats",
    "amapiano": "Afrobeats", "afrobeat": "Afrobeats",
    "afro house": "Afrobeats",

    # K-Pop -- kept separate from Pop: distinct scene/audience despite
    # musical overlap.
    "k-pop": "K-Pop", "kpop": "K-Pop", "korean pop": "K-Pop",
    "k-indie": "K-Pop",

    # World -- genuine world-music genre tags, distinct from the
    # nationality/language descriptors in NON_GENRE_TAGS below (e.g.
    # "flamenco" is a genre; bare "spanish" is not).
    "world": "World", "world music": "World", "celtic": "World",
    "flamenco": "World", "klezmer": "World", "bollywood": "World",
    "arabic pop": "World",
}

# Nationality/language tags Last.fm's free-form tagging produces that are
# not genres at all (e.g. a Drake track tagged "Canadian"). Filtered out
# entirely rather than becoming their own genre -- same idea as the
# artist-name filter in genre.py, just a fixed list instead of a
# per-track computed value. Not exhaustive; extend the same way as
# GENRE_ALIASES.
NON_GENRE_TAGS = {
    "canadian", "american", "british", "english", "french", "german",
    "spanish", "italian", "australian", "mexican", "irish", "scottish",
    "welsh", "dutch", "swedish", "norwegian", "danish", "brazilian",
    "russian", "japanese", "chinese", "indian", "african", "korean",
}


def normalize_tag(tag):
    """A tag's display genre label, or None if it's a nationality/language
    descriptor (not a genre) rather than a real genre tag. Unrecognized
    tags are title-cased and returned as-is -- never dropped."""
    if not tag:
        return None
    tag_lower = tag.strip().lower()
    if not tag_lower or tag_lower in NON_GENRE_TAGS:
        return None
    return GENRE_ALIASES.get(tag_lower, tag.strip().title())

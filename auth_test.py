from dotenv import load_dotenv
import os
import spotipy
from spotipy import SpotifyOAuth


load_dotenv("secrets.env")
client_id = os.getenv("SPOTIFY_CLIENT_ID")
client_secret = os.getenv("SPOTIFY_CLIENT_SECRET")
redirect_uri = os.getenv("SPOTIFY_REDIRECT_URI")


auth_manager = SpotifyOAuth(
    client_id = client_id,
    client_secret = client_secret,
    redirect_uri = redirect_uri,
    scope = "playlist-read-private playlist-modify-private playlist-modify-public"

)

sp = spotipy.Spotify(auth_manager = auth_manager)

user = sp.current_user()

playlists = sp.current_user_playlists()

#for playlist in playlists["items"]:
    #print(playlist["name"])
    #print(playlist["id"])

source_items = sp.playlist_items(
    playlist_id= "2T5Xhq3EnEA8k40MFW2cb4"
)

genre_cache = {}

def get_artist_genres(artist_id):
    if artist_id in genre_cache:
        # return the genre_cache
    artist = sp.artist(artist_id)
    genres = artist["genres"]

for playlist_item in source_items["items"]:
    track = playlist_item.get("item")
    artist_id = artist["id"]
    genres = get_artist_genres(artist_id)

    if track is None:
        print("Skipping unavailable item")
        continue

    print(track["name"], "-", artist["name"], genres)













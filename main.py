import os
import spotipy
from flask import Flask, redirect, request, session, url_for, render_template
from flask_session import Session
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
import redis

# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

# --- Redis session configuration ---
# Make sure Redis server is running locally or remotely
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    password=os.getenv("REDIS_PASSWORD", None),
)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
Session(app)  # initialize server-side session

# --- Spotify credentials ---
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:5000/spotify_callback"
SCOPE = "playlist-read-private playlist-read-collaborative"
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SCOPE
)

# --- Portal page ---
@app.route("/")
def index():
    spotify_logged_in = "spotify" in session

    return render_template(
        "index.html",
        spotify_logged_in=spotify_logged_in
    )

# --- Spotify OAuth login ---
@app.route("/spotify_login")
def spotify_login():
    auth_url = sp_oauth.get_authorize_url()
    return redirect(auth_url)

# --- Spotify OAuth callback ---
@app.route("/spotify_callback")
def spotify_callback():
    code = request.args.get("code")
    if not code:
        return "Authorization failed", 400

    token_info = sp_oauth.get_access_token(code, check_cache=False)

    session["spotify"] = {
        "token": token_info["access_token"],
        "refresh_token": token_info.get("refresh_token")
    }

    # Redirect back to portal
    return redirect(url_for("index"))

@app.route("/spotify_playlists")
def spotify_playlists():
    if "spotify" not in session:
        return redirect(url_for("spotify_login"))

    sp = spotipy.Spotify(auth=session["spotify"]["token"])
    playlists = sp.current_user_playlists(limit=50)["items"]  # get first 50 playlists

    return render_template(
        "spotify_playlists.html",
        playlists=playlists
    )

@app.route("/spotify_playlist/<playlist_id>")
def spotify_playlist(playlist_id):
    if "spotify" not in session:
        return redirect(url_for("spotify_login"))

    sp = spotipy.Spotify(auth=session["spotify"]["token"])
    playlist_name = sp.playlist(playlist_id, fields="name")["name"]
    items = sp.playlist_items(playlist_id, fields="items.track(name,artists.name,album(name,images.url))")

    # Prepare Discogs search links
    track_links = []
    for item in items["items"]:
        track = item["track"]
        album = track["album"]
        track_name = track["name"]
        album_name = album["name"]
        try:
            album_img = album["images"][-1]["url"]
        except IndexError:
            album_img = ""
        artists = ", ".join([a["name"] for a in track["artists"]])

        query = f"{album_name} {artists}"

        search_url = f"https://www.discogs.com/sell/list?format=Vinyl&ships_from=United+States&q={query}"
        track_links.append({
            "name": track_name,
            "album_img": album_img,
            "artists": artists,
            "discogs_url": search_url
        })

    return render_template(
        "playlist.html",
        playlist_name=playlist_name,
        tracks=track_links,
    )


# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True)

import os
import time
import spotipy
import redis
import secrets
from flask import Flask, redirect, request, session, url_for, render_template, jsonify
from flask_session import Session
from flask_talisman import Talisman
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth
from urllib.parse import quote_plus
# Load environment variables
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")
if not os.getenv("FLASK_SECRET_KEY"):
    raise RuntimeError("FLASK_SECRET_KEY is not set")

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
app.config["SESSION_COOKIE_SECURE"] = True
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = 'Lax'
Session(app)  # initialize server-side session
Talisman(app, content_security_policy="default-src 'self'; img-src 'self' https: data:;")

# --- Spotify credentials ---
SPOTIFY_REDIRECT_URI = "http://127.0.0.1:5000/spotify_callback"
SCOPE = "playlist-read-private playlist-read-collaborative"
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SCOPE
)

# Helper: ensure we have a valid Spotify client (refresh token if needed)
class AuthError(Exception):
    pass

def get_spotify_client():
    """
    Return a spotipy.Spotify client guaranteed to have a valid access token.
    Will refresh the token if it's expired. Raises AuthError if not authenticated.
    """
    if "spotify" not in session:
        raise AuthError("not_authenticated")

    token_info = session.get("spotify", {})
    access_token = token_info.get("access_token") or token_info.get("token")  # support older key names
    refresh_token = token_info.get("refresh_token")
    expires_at = token_info.get("expires_at")  # epoch seconds

    # If we don't have expiry info, try to treat token as valid (but prefer to refresh)
    now = int(time.time())
    buffer = 30  # seconds before expiry to proactively refresh

    need_refresh = False
    if not access_token:
        need_refresh = True
    elif expires_at is None:
        # no expiry info; try to refresh if refresh_token exists
        need_refresh = bool(refresh_token)
    elif now > (expires_at - buffer):
        need_refresh = True

    if need_refresh:
        if not refresh_token:
            # can't refresh, need re-auth
            raise AuthError("missing_refresh_token")
        try:
            new_token = sp_oauth.refresh_access_token(refresh_token)
        except Exception as e:
            # refresh failed
            app.logger.exception("Failed to refresh Spotify token")
            raise AuthError("refresh_failed")

        # new_token usually contains 'access_token' and 'expires_in'
        new_access = new_token.get("access_token")
        expires_in = new_token.get("expires_in") or new_token.get("expires_at")
        if expires_in and not isinstance(expires_in, int):
            # If refresh returned expires_at directly, attempt to use it
            try:
                expires_in = int(expires_in)
            except Exception:
                expires_in = None

        new_expires_at = None
        if expires_in and expires_in > 1000000000:
            # server returned an epoch timestamp for some versions
            new_expires_at = expires_in
        elif expires_in:
            new_expires_at = int(time.time()) + int(expires_in)
        else:
            # fallback: set a 1-hour expiry if we don't know
            new_expires_at = int(time.time()) + 3600

        # Update session token info
        session["spotify"].update({
            "access_token": new_access,
            "token": new_access,  # keep compatibility (older code used 'token')
            "expires_at": new_expires_at,
            # keep refresh_token the same (Spotify often doesn't return refresh_token on refresh)
            "refresh_token": refresh_token
        })
        access_token = new_access

    # Build spotipy client with the valid token
    return spotipy.Spotify(auth=access_token)


# New helper: turn Spotify playlist item objects into simplified track dicts
def simplify_playlist_items(items):
    """
    Given a list of playlist item objects (as returned by Spotify API),
    return a list of simplified dicts with fields:
      - name
      - album_img
      - artists
      - discogs_url
    If include_album_and_artist_search is True, also add:
      - album_search_url
      - artist_search_url
    """
    result = []
    for item in items:
        track = item.get("track")
        if not track:
            continue
        album = track.get("album", {})
        track_name = track.get("name", "")
        album_name = album.get("name", "")
        images = album.get("images") or []
        album_img = ""
        if images:
            # prefer the last image (usually smallest) to match previous behavior
            try:
                album_img = images[-1].get("url", "") or ""
            except Exception:
                album_img = ""
        artists = ", ".join([a.get("name", "") for a in track.get("artists", [])])

        query = quote_plus(f"{album_name} {artists}")
        discogs_url = f"https://www.discogs.com/sell/list?format=Vinyl&ships_from=United+States&q={query}"

        item_dict = {
            "name": track_name,
            "album_img": album_img,
            "artists": artists,
            "discogs_url": discogs_url
        }

        item_dict["album_search_url"] = f"https://www.discogs.com/search?q={query}&type=release&format_exact=Vinyl&layout=med"
        item_dict["artist_search_url"] = f"https://www.discogs.com/search?q={quote_plus(artists)}&type=artist"

        result.append(item_dict)
    return result


# --- Portal page ---
@app.route("/")
def index():
    spotify_username = ""
    spotify_logged_in = "spotify" in session
    if spotify_logged_in:
        sp = get_spotify_client()
        spotify_username = sp.me()["display_name"]
    return render_template(
        "index.html",
        spotify_logged_in=spotify_logged_in,
        spotify_username=spotify_username
    )

# --- Spotify OAuth login ---
@app.route("/spotify_login")
def spotify_login():
    state = secrets.token_urlsafe(16)
    session["spotify_auth_state"] = state
    auth_url = sp_oauth.get_authorize_url(state=state)
    return redirect(auth_url)

# --- Spotify OAuth callback ---
@app.route("/spotify_callback")
def spotify_callback():
    state = request.args.get("state")
    saved = session.pop("spotify_auth_state", None)
    if not saved or state != saved:
        return "Invalid state", 400
    code = request.args.get("code")
    if not code:
        return "Authorization failed", 400

    token_info = sp_oauth.get_access_token(code, check_cache=False)

    # token_info may contain: access_token, refresh_token, expires_at or expires_in
    access_token = token_info.get("access_token")
    refresh_token = token_info.get("refresh_token")
    expires_at = token_info.get("expires_at")
    expires_in = token_info.get("expires_in")

    if expires_at is None and expires_in is not None:
        try:
            expires_at = int(time.time()) + int(expires_in)
        except Exception:
            expires_at = None

    session["spotify"] = {
        "access_token": access_token,
        "token": access_token,  # keep compatibility with older code
        "refresh_token": refresh_token,
        "expires_at": expires_at
    }

    # Redirect back to portal
    return redirect(url_for("index"))

@app.route("/spotify_playlists")
def spotify_playlists():
    try:
        sp = get_spotify_client()
    except AuthError:
        return redirect(url_for("spotify_login"))

    # initial page
    limit = 50
    offset = 0
    playlists_obj = sp.current_user_playlists(limit=limit, offset=offset)
    playlists = playlists_obj["items"]
    total = playlists_obj.get("total", len(playlists))

    return render_template(
        "spotify_playlists.html",
        playlists=playlists,
        total_playlists=total,
        page_limit=limit
    )

@app.route("/spotify_playlists_data")
def spotify_playlists_data():
    # returns a compact JSON payload for the front-end including a playlist image
    if "spotify" not in session:
        return jsonify({"error": "not_authenticated"}), 401

    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 50))
    except ValueError:
        return jsonify({"error": "invalid_params"}), 400

    sp = spotipy.Spotify(auth=session["spotify"]["access_token"])
    playlists_obj = sp.current_user_playlists(limit=limit, offset=offset)
    items = playlists_obj.get("items", [])

    # Simplify response payload for the client and choose a single image (if available)
    result_items = []
    for p in items:
        images = p.get("images") or []
        img_url = ""
        if images:
            # prefer the first image (usually largest). You can choose the last for smaller.
            img_url = images[0].get("url", "") or ""
        result_items.append({
            "id": p.get("id"),
            "name": p.get("name"),
            "tracks_total": p.get("tracks", {}).get("total", 0),
            "image": img_url
        })

    return jsonify({
        "items": result_items,
        "next": playlists_obj.get("next"),
        "total": playlists_obj.get("total", len(result_items)),
        "offset": offset,
        "limit": limit
    })

@app.route("/spotify_playlist/<playlist_id>")
def spotify_playlist(playlist_id):
    try:
        sp = get_spotify_client()
    except AuthError:
        return redirect(url_for("spotify_login"))

    playlist_meta = sp.playlist(playlist_id, fields="name,tracks.total")
    playlist_name = playlist_meta.get("name", "Playlist")
    total_tracks = playlist_meta.get("tracks", {}).get("total", 0)

    limit = 100
    offset = 0
    items_obj = sp.playlist_items(playlist_id, fields="items.track(name,artists.name,album(name,images.url)),total", limit=limit, offset=offset)
    items = items_obj.get("items", [])

    # Use helper to build track links (include album & artist search URLs for the page)
    track_links = simplify_playlist_items(items)

    return render_template(
        "playlist.html",
        playlist_name=playlist_name,
        tracks=track_links,
        playlist_id=playlist_id,
        total_tracks=total_tracks,
        page_limit=limit,
        initial_offset=offset
    )

@app.route("/spotify_playlist_tracks")
def spotify_playlist_tracks():
    try:
        sp = get_spotify_client()
    except AuthError:
        return jsonify({"error": "not_authenticated"}), 401

    playlist_id = request.args.get("playlist_id")
    if not playlist_id:
        return jsonify({"error": "missing_playlist_id"}), 400

    try:
        offset = int(request.args.get("offset", 0))
        limit = int(request.args.get("limit", 100))
    except ValueError:
        return jsonify({"error": "invalid_params"}), 400

    items_obj = sp.playlist_items(playlist_id, fields="items.track(name,artists.name,album(name,images.url)),total", limit=limit, offset=offset)
    items = items_obj.get("items", [])
    total = items_obj.get("total", 0)

    # Use helper to build simplified track items (no extra album/artist search URLs needed for the API)
    result = simplify_playlist_items(items)

    return jsonify({
        "items": result,
        "offset": offset,
        "limit": limit,
        "total": total,
        "next_offset": offset + len(result) if len(result) else None
    })

@app.route("/logout")
def logout():
    session.pop("spotify", None)
    session.clear()
    return redirect(url_for('index'))

# --- Run app ---
if __name__ == "__main__":
    app.run(debug=True)
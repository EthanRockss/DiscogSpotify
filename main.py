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

# Determine environment (simple heuristic)
IS_PRODUCTION = os.getenv("FLASK_ENV", "production") == "production" and os.getenv("FORCE_LOCAL", "0") != "1"
# For local development, set FLASK_ENV=development or set FORCE_LOCAL=1

# --- Session / cookie configuration ---
app.config["SESSION_TYPE"] = "redis"
app.config["SESSION_REDIS"] = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", 6379)),
    password=os.getenv("REDIS_PASSWORD", None),
)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True

# Only require SESSION_COOKIE_SECURE in production (HTTPS). For local dev (HTTP) it must be False.
app.config["SESSION_COOKIE_SECURE"] = bool(os.getenv("SESSION_COOKIE_SECURE", "1")) and IS_PRODUCTION
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = 'Lax'
# You can set PERMANENT_SESSION_LIFETIME if desired
Session(app)

# --- Security headers / CSP ---
# Use nonces for inline scripts/styles. We'll add CSP entries that expect nonces.
csp = {
    "default-src": ["'self'"],
    # Allow images from self, any https provider (Spotify images are https), and data: URIs for placeholders
    "img-src": ["'self'", "https:", "data:"],
    # Allow scripts/styles only from self; inline blocks must include the nonce via {{ csp_nonce() }} in templates
    "script-src": ["'self'"],
    "style-src": ["'self'"],
    # Optionally allow fonts if you load webfonts externally:
    # "font-src": ["'self'", "https:"],
}

# In development you may want Talisman not to force HTTPS (so it won't redirect)
talisman_force_https = IS_PRODUCTION
Talisman(app, content_security_policy=csp, force_https=talisman_force_https)

# --- Spotify credentials ---
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:5000/spotify_callback")
SCOPE = "playlist-read-private playlist-read-collaborative"
sp_oauth = SpotifyOAuth(
    client_id=os.getenv("SPOTIFY_CLIENT_ID"),
    client_secret=os.getenv("SPOTIFY_CLIENT_SECRET"),
    redirect_uri=SPOTIFY_REDIRECT_URI,
    scope=SCOPE
)

class AuthError(Exception):
    pass

def get_spotify_client():
    if "spotify" not in session:
        raise AuthError("not_authenticated")

    token_info = session.get("spotify", {})
    access_token = token_info.get("access_token") or token_info.get("token")
    refresh_token = token_info.get("refresh_token")
    expires_at = token_info.get("expires_at")

    now = int(time.time())
    buffer = 30
    need_refresh = False
    if not access_token:
        need_refresh = True
    elif expires_at is None:
        need_refresh = bool(refresh_token)
    elif now > (expires_at - buffer):
        need_refresh = True

    if need_refresh:
        if not refresh_token:
            raise AuthError("missing_refresh_token")
        try:
            new_token = sp_oauth.refresh_access_token(refresh_token)
        except Exception:
            app.logger.exception("Failed to refresh Spotify token")
            raise AuthError("refresh_failed")

        new_access = new_token.get("access_token")
        expires_in = new_token.get("expires_in") or new_token.get("expires_at")
        if expires_in and not isinstance(expires_in, int):
            try:
                expires_in = int(expires_in)
            except Exception:
                expires_in = None

        if expires_in and expires_in > 1000000000:
            new_expires_at = expires_in
        elif expires_in:
            new_expires_at = int(time.time()) + int(expires_in)
        else:
            new_expires_at = int(time.time()) + 3600

        session["spotify"].update({
            "access_token": new_access,
            "token": new_access,
            "expires_at": new_expires_at,
            "refresh_token": refresh_token
        })
        access_token = new_access

    return spotipy.Spotify(auth=access_token)

def simplify_playlist_items(items):
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

@app.route("/")
def index():
    spotify_username = ""
    spotify_logged_in = "spotify" in session
    if spotify_logged_in:
        sp = get_spotify_client()
        spotify_username = sp.me().get("display_name", "")
    return render_template(
        "index.html",
        spotify_logged_in=spotify_logged_in,
        spotify_username=spotify_username
    )

@app.route("/spotify_login")
def spotify_login():
    state = secrets.token_urlsafe(16)
    session["spotify_auth_state"] = state
    auth_url = sp_oauth.get_authorize_url(state=state)
    return redirect(auth_url)

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
        "token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at
    }

    return redirect(url_for("index"))

@app.route("/spotify_playlists")
def spotify_playlists():
    try:
        sp = get_spotify_client()
    except AuthError:
        return redirect(url_for("spotify_login"))

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

    result_items = []
    for p in items:
        images = p.get("images") or []
        img_url = ""
        if images:
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

if __name__ == "__main__":
    # Only enable debug on explicit env flag (development); otherwise default to production-safe behavior
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1" or os.getenv("FLASK_ENV", "") == "development"
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5000))
    app.run(host=host, port=port, debug=debug_mode)
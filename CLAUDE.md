# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Spotify Vinyl Finder - A Flask web app that connects to Spotify to browse playlists and generate Discogs search links for finding vinyl records.

## Development Setup

```bash
# Create and activate virtual environment
python -m venv env
source env/bin/activate

# Install dependencies
pip install -r requirements.txt

# Required: Local Redis server on port 6379
# Redis is used for Flask session storage

# Environment variables (create .env file):
# SPOTIFY_CLIENT_ID=
# SPOTIFY_CLIENT_SECRET=
# FLASK_SECRET_KEY=
# Optional: REDIS_HOST, REDIS_PORT, REDIS_PASSWORD

# Run the development server
python main.py
```

The app runs at http://127.0.0.1:5000. The Spotify OAuth redirect URI must be set to `http://127.0.0.1:5000/spotify_callback` in the Spotify Developer Dashboard.

## Architecture

**Single-file Flask application** (`main.py`) with:
- Spotify OAuth flow using spotipy library
- Redis-backed server-side sessions (Flask-Session)
- Token refresh handling with automatic expiry detection
- JSON API endpoints for infinite scroll pagination

**Key routes:**
- `/` - Portal page (login prompt or playlist browser link)
- `/spotify_login`, `/spotify_callback` - OAuth flow
- `/spotify_playlists` - Lists user's playlists (HTML)
- `/spotify_playlists_data` - Playlists JSON endpoint for pagination
- `/spotify_playlist/<id>` - Individual playlist view (HTML)
- `/spotify_playlist_tracks` - Tracks JSON endpoint for pagination

**Templates** (Jinja2):
- `templates/index.html` - Landing portal
- `templates/spotify_playlists.html` - Playlist grid with infinite scroll
- `templates/playlist.html` - Track list with Discogs search links

**Core helper functions:**
- `get_spotify_client()` - Returns authenticated Spotify client, handles token refresh
- `simplify_playlist_items()` - Transforms Spotify track data into simplified dicts with Discogs URLs

## Discogs URL Generation

The app generates three types of Discogs search URLs per track:
1. Vinyl marketplace search (album + artist, filtered to vinyl format, US shipping)
2. Album/release search
3. Artist search

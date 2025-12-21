# Spotify Vinyl Finder

Uses Spotify playlists to aid in searching for vinyls on Discogs. 

## Setup

I suggest creating a venv.
```bash
python -m venv env
```

**A local redis server is expected on 6379.**

### Install dependencies:
```bash
pip install -r requirements.txt
```

### Create Discog App:

[Discog Dev Dashboard](https://www.discogs.com/settings/developers)

Callback URL: `http://localhost:5000/callback`

### Create Spotify App:

[Spotify Dev Dashboard](https://developer.spotify.com/dashboard)

Redirect URI: `http://127.0.0.1:5000/spotify_callback`

### Configure environment variables:

```env
DISCOGS_CONSUMER_KEY=
DISCOGS_CONSUMER_SECRET=
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
FLASK_SECRET_KEY=
```

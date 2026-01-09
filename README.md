# Spotify Vinyl Finder

Uses Spotify playlists to aid in searching for vinyls on Discogs. Shows currently playing track with real-time vinyl prices from Discogs.

## Setup

I suggest creating a venv.
```bash
python -m venv env
source env/bin/activate
```

**A local redis server is expected on 6379.**

### Install dependencies:
```bash
pip install -r requirements.txt
```

### Create Spotify App:

[Spotify Dev Dashboard](https://developer.spotify.com/dashboard)

Redirect URI: `http://127.0.0.1:5000/spotify_callback`

### Create Discogs Token:

1. Go to [Discogs Developer Settings](https://www.discogs.com/settings/developers)
2. Click "Generate new token"
3. Copy the token for use in your `.env` file

### Configure environment variables:

Create a `.env` file in the project root with the following:

```env
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
FLASK_SECRET_KEY=any_random_secret_string
DISCOGS_USER_TOKEN=your_discogs_token
```

### Run the app:

```bash
source env/bin/activate
python main.py
```

Then visit http://127.0.0.1:5000

## Endpoints

- `/` - Portal page
- `/now_playing` - Shows currently playing track with vinyl prices
- `/spotify_playlists` - Browse your Spotify playlists
- `/logout` - Clear session and re-authenticate (useful after adding new OAuth scopes)

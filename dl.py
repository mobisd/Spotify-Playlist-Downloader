import os
import urllib.request
import requests
import re
import string
import logging
import customtkinter as ctk
from tkinter import StringVar
from dotenv import load_dotenv
from spotipy import SpotifyOAuth, Spotify
from spotipy.oauth2 import SpotifyOauthError
import yt_dlp as youtube_dl
from mutagen.id3 import ID3, APIC, TIT2, TPE1, TALB, TDRC, TCON, TRCK, USLT, error
from mutagen.mp3 import MP3
import lyricsgenius

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables
load_dotenv(dotenv_path='.env')

# Setup Spotify API credentials
client_id = os.getenv("CLIENT_ID")
client_secret = os.getenv("CLIENT_SECRET")
redirect_uri = os.getenv("REDIRECT_URL")
genius_api_key = os.getenv("GENIUS_API_KEY")

# Ensure environment variables are loaded correctly
if not client_id or not client_secret or not redirect_uri or not genius_api_key:
    logging.error("Please set CLIENT_ID, CLIENT_SECRET, REDIRECT_URL, and GENIUS_API_KEY in the .env file")
    exit(1)

# Create an instance of the SpotifyOAuth class
try:
    sp_oauth = SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope="user-library-read playlist-read-private playlist-read-collaborative",
    )
    sp = Spotify(auth_manager=sp_oauth)
except SpotifyOauthError as e:
    logging.error(f"Spotify OAuth setup error: {e}")
    exit(1)

# Initialize Genius API client
genius = lyricsgenius.Genius(genius_api_key)

# Get access token
token_info = sp_oauth.get_cached_token()
if not token_info:
    auth_url = sp_oauth.get_authorize_url()
    logging.info(f"Please go to this URL and authorize the app: {auth_url}")
    auth_code = input("Enter the authorization code: ")
    token_info = sp_oauth.get_access_token(auth_code)

access_token = token_info["access_token"]
playlists = {}

def get_auth_header(token):
    return {"Authorization": "Bearer " + token}

# Function to update the dropdown menu
def update_playlist_dropdown():
    playlist_names = list(playlists.keys())
    playlist_dropdown.configure(values=playlist_names)
    if playlist_names:
        selected_playlist.set(playlist_names[0])

# Function to fetch user playlists
def get_user_playlists(token):
    logging.info("Retrieving user playlists...")
    headers = get_auth_header(token)
    response = requests.get("https://api.spotify.com/v1/me/playlists", headers=headers)
    response_json = response.json()
    for item in response_json["items"]:
        playlists[item["name"]] = item["id"]
    logging.info("Playlists retrieved successfully.")
    update_playlist_dropdown()

def sanitize_filename(filename):
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    return ''.join(c for c in filename if c in valid_chars)

# Global variable to control the downloading process
is_downloading = False

def stop_downloading():
    global is_downloading
    is_downloading = False
    status_label.configure(text="Downloading stopped.")
    logging.info("Downloading stopped by user.")

def get_playlist_tracks(token, playlist_id):
    logging.info(f"Retrieving tracks for playlist ID: {playlist_id}")
    headers = get_auth_header(token)
    tracks = []
    limit = 100
    offset = 0
    while True:
        response = requests.get(f"https://api.spotify.com/v1/playlists/{playlist_id}/tracks", headers=headers, params={'limit': limit, 'offset': offset})
        response_json = response.json()
        for item in response_json["items"]:
            track = item["track"]
            artist_id = track["artists"][0]["id"]
            artist_info = sp.artist(artist_id)
            genre = artist_info["genres"][0] if artist_info["genres"] else "Unknown"
            tracks.append((
                track["name"],
                track["artists"][0]["name"],
                track["album"]["name"],
                track["album"]["release_date"],
                track["album"]["images"][0]["url"],
                track["album"]["artists"][0]["name"],
                track["album"]["total_tracks"],
                genre
            ))
        if len(response_json["items"]) < limit:
            break
        offset += limit
    logging.info(f"Total tracks retrieved: {len(tracks)}")
    return tracks

def read_downloaded_tracks(file_path):
    if os.path.exists(file_path):
        with open(file_path, 'r') as file:
            return set(line.strip() for line in file)
    return set()

def write_downloaded_track(file_path, track_name):
    with open(file_path, 'a') as file:
        file.write(track_name + '\n')

def fetch_lyrics(track_name, artist_name):
    try:
        song = genius.search_song(track_name, artist_name)
        if song:
            return song.lyrics
    except Exception as e:
        logging.error(f"Error fetching lyrics for {track_name} by {artist_name}: {e}")
    return None

def embed_metadata(mp3_file, track_info, lyrics=None):
    audio = MP3(mp3_file, ID3=ID3)
    try:
        audio.add_tags()
    except error:
        pass

    audio.tags.add(TIT2(encoding=3, text=track_info['title']))
    audio.tags.add(TPE1(encoding=3, text=track_info['artist']))
    audio.tags.add(TALB(encoding=3, text=track_info['album']))
    audio.tags.add(TDRC(encoding=3, text=track_info['year']))
    audio.tags.add(TCON(encoding=3, text=track_info['genre']))
    audio.tags.add(TRCK(encoding=3, text=f"{track_info['track_number']}/{track_info['total_tracks']}"))

    if lyrics:
        audio.tags.add(USLT(encoding=3, lang='eng', desc='Lyrics', text=lyrics))

    response = requests.get(track_info['cover_url'])
    img_data = response.content

    audio.tags.add(
        APIC(
            encoding=3,  # 3 is for utf-8
            mime='image/jpeg',  # image/jpeg or image/png
            type=3,  # 3 is for the cover image
            desc=u'Cover',
            data=img_data
        )
    )
    audio.save()

def download_songs(selected_playlist):
    global is_downloading
    is_downloading = True
    status_label.configure(text="Downloading...")
    download_button.configure(state='disabled')
    stop_button.configure(state='normal')

    # Create folder for the playlist
    playlist_name = sanitize_filename(selected_playlist)
    download_folder = os.path.join(os.getcwd(), playlist_name)
    os.makedirs(download_folder, exist_ok=True)

    downloaded_tracks_file = os.path.join(download_folder, "downloaded_tracks.txt")
    downloaded_tracks = read_downloaded_tracks(downloaded_tracks_file)
    retry_count = 3
    min_file_size = 1024 * 1024  # Minimum file size in bytes (1MB)

    playlist_id = playlists[selected_playlist]
    tracks = get_playlist_tracks(access_token, playlist_id)
    total_tracks = len(tracks)

    for index, track in enumerate(tracks):
        if not is_downloading:
            logging.info("Downloading stopped by user.")
            break

        track_name = f"{track[1]} - {track[0]}"
        sanitized_track_name = sanitize_filename(track_name)
        final_file = os.path.join(download_folder, f"{sanitized_track_name}.mp3")

        # Check if the track is already in the downloaded tracks file and if the file exists and is larger than 1MB
        if track_name in downloaded_tracks and os.path.exists(final_file) and os.path.getsize(final_file) > min_file_size:
            logging.info(f"Skipping, already downloaded: {track_name}")
            continue

        for attempt in range(retry_count):
            try:
                logging.info(f"Processing {track[0]} by {track[1]}... (Attempt {attempt + 1}/{retry_count})")
                search_query = urllib.parse.quote(f"{track[0]} {track[1]}")
                html = urllib.request.urlopen(f"https://www.youtube.com/results?search_query={search_query}")
                video_ids = re.findall(r"watch\?v=(\S{11})", html.read().decode())
                if not video_ids:
                    logging.warning(f"No videos found for {track[0]} by {track[1]}")
                    break

                for video_id in video_ids:
                    try:
                        yt_url = f"https://youtube.com/watch?v={video_id}"
                        ydl_opts = {
                            'format': 'bestaudio/best',
                            'outtmpl': os.path.join(download_folder, f"{sanitized_track_name}.%(ext)s"),
                            'postprocessors': [{
                                'key': 'FFmpegExtractAudio',
                                'preferredcodec': 'mp3',
                                'preferredquality': '192',
                            }],
                        }
                        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                            ydl.download([yt_url])
                        
                        if os.path.exists(final_file) and os.path.getsize(final_file) > min_file_size:
                            logging.info(f"Downloaded successfully: {final_file}")
                            write_downloaded_track(downloaded_tracks_file, track_name)

                            track_info = {
                                'title': track[0],
                                'artist': track[1],
                                'album': track[2],
                                'year': track[3].split('-')[0],
                                'genre': track[7],
                                'track_number': str(index + 1),
                                'total_tracks': str(track[6]),
                                'cover_url': track[4]
                            }

                            lyrics = fetch_lyrics(track[0], track[1])
                            embed_metadata(final_file, track_info, lyrics)  # Embed detailed metadata and lyrics into MP3
                            break
                        else:
                            logging.warning(f"Download failed or incomplete: {final_file}")
                    except Exception as e:
                        logging.error(f"Error downloading video: {e}")
                        continue
                else:
                    continue
                break
            except urllib.error.HTTPError as e:
                if e.code == 410:
                    logging.error(f"Error processing track {track}: Video not available (HTTP 410)")
                    break
                elif e.code == 403:
                    logging.error(f"Error processing track {track}: Access forbidden (HTTP 403)")
                    break
                else:
                    logging.error(f"Error processing track {track}: {e}")
            except Exception as e:
                logging.error(f"Error processing track {track}: {e}")
        else:
            logging.error(f"Failed to download {track[0]} by {track[1]} after {retry_count} attempts")

    status_label.configure(text="Download completed.")
    download_button.configure(state='normal')
    stop_button.configure(state='disabled')
    logging.info("Download completed.")

# GUI setup
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

screen = ctk.CTk()
screen.title('Spotify Downloader')
screen.geometry("600x400")

# Layout
frame = ctk.CTkFrame(screen, corner_radius=15)
frame.pack(pady=20, padx=20, fill="both", expand=True)

# Add title label
title_label = ctk.CTkLabel(frame, text="Spotify Playlist Downloader", font=ctk.CTkFont(size=20, weight="bold"))
title_label.pack(pady=(0, 20))

# Playlist dropdown
selected_playlist = StringVar()
playlist_dropdown_label = ctk.CTkLabel(frame, text="Select Playlist:", anchor="w")
playlist_dropdown_label.pack(fill="x", padx=10)
playlist_dropdown = ctk.CTkComboBox(frame, variable=selected_playlist)
playlist_dropdown.pack(pady=10, padx=10, fill="x")

# Fetch playlists and update dropdown
get_user_playlists(access_token)

# Download button
download_button = ctk.CTkButton(frame, text="Download", command=lambda: download_songs(selected_playlist.get()))
download_button.pack(pady=10, padx=10, fill="x")

# Stop Downloading button
stop_button = ctk.CTkButton(frame, text="Stop Downloading", command=stop_downloading)
stop_button.pack(pady=10, padx=10, fill="x")
stop_button.configure(state='disabled')

# Status label
status_label = ctk.CTkLabel(frame, text="")
status_label.pack(pady=10, padx=10, fill="x")

# Start GUI
screen.mainloop()
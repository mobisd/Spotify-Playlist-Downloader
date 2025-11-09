import os
import re
import string
import logging
import threading
import queue
import time
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from dataclasses import dataclass
from typing import List, Optional, Tuple, Dict, Any

import requests
from dotenv import load_dotenv
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError
import customtkinter as ctk
from tkinter import StringVar

import yt_dlp
from mutagen.id3 import ID3, TIT2, TPE1, TALB, TDRC, TCON, APIC
from mutagen.mp3 import MP3

from PIL import Image, ImageDraw
import io
import datetime

# ---------------------------
# Setup & Config
# ---------------------------
os.environ["TK_SILENCE_DEPRECATION"] = "1"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("spotify_dl")

load_dotenv(dotenv_path=".env")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URL = os.getenv("REDIRECT_URL")

if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URL:
    raise SystemExit("Please set CLIENT_ID, CLIENT_SECRET, and REDIRECT_URL in the .env file")

DOWNLOAD_DIR = "downloads"

# Performance optimization settings
MAX_CONCURRENT_REQUESTS = 2  # Reduced to avoid rate limiting
CACHE_TIMEOUT = 300  # 5 minutes
PREVIEW_TRACK_LIMIT = 20
LAZY_LOAD_THRESHOLD = 100  # Only load preview for playlists with < 100 tracks initially

# Global caches
playlist_cache: Dict[str, Dict[str, Any]] = {}
tracks_cache: Dict[str, List[dict]] = {}
image_cache: Dict[str, Any] = {}

# ---------------------------
# URL Parsing & Validation
# ---------------------------

def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
    """Parse Spotify URL and return (type, id) tuple"""
    import re
    
    # Clean the URL
    url = url.strip()
    
    # Spotify URL patterns
    patterns = [
        # Standard Spotify URLs
        r'https?://open\.spotify\.com/(playlist|album)/([a-zA-Z0-9]+)',
        # Spotify URI format
        r'spotify:(playlist|album):([a-zA-Z0-9]+)',
        # Short URLs
        r'https?://spotify\.link/([a-zA-Z0-9]+)',
    ]
    
    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            if len(match.groups()) == 2:
                content_type, content_id = match.groups()
                return (content_type, content_id)
            else:
                # For short URLs, we need to resolve them
                try:
                    import requests
                    response = requests.head(url, allow_redirects=True, timeout=5)
                    resolved_url = response.url
                    return parse_spotify_url(resolved_url)
                except:
                    pass
    
    return None

def validate_spotify_content(sp: Spotify, content_type: str, content_id: str) -> Optional[Dict[str, Any]]:
    """Validate and get info about Spotify content"""
    try:
        if content_type == "playlist":
            data = sp.playlist(content_id, fields="name,description,images,tracks.total,owner.display_name")
            return {
                "type": "playlist",
                "id": content_id,
                "name": data["name"],
                "description": data.get("description", ""),
                "images": data.get("images", []),
                "track_count": data["tracks"]["total"],
                "owner": data.get("owner", {}).get("display_name", "Unknown")
            }
        elif content_type == "album":
            data = sp.album(content_id)
            return {
                "type": "album",
                "id": content_id,
                "name": data["name"],
                "description": f"Album by {', '.join([artist['name'] for artist in data['artists']])}",
                "images": data.get("images", []),
                "track_count": data["total_tracks"],
                "artist": ", ".join([artist["name"] for artist in data["artists"]]),
                "release_date": data.get("release_date", ""),
                "genres": data.get("genres", [])
            }
    except Exception as e:
        logger.error(f"Failed to validate Spotify content: {e}")
    
    return None

def get_album_tracks(sp: Spotify, album_id: str) -> List[dict]:
    """Get tracks from a Spotify album"""
    logger.info(f"Retrieving tracks for album {album_id}…")
    tracks: List[dict] = []
    
    try:
        # Get album info first
        album = sp.album(album_id)
        album_name = album["name"]
        album_artists = ", ".join([artist["name"] for artist in album["artists"]])
        album_release_date = album.get("release_date", "")
        album_images = album.get("images", [])
        album_cover_url = album_images[0]["url"] if album_images else None
        
        # Get tracks
        results = sp.album_tracks(album_id, limit=50)
        
        while results:
            for track in results["items"]:
                if track.get("type") != "track":
                    continue
                
                name = track.get("name", "Unknown Title")
                artists_list = [a.get("name", "?") for a in track.get("artists", [])]
                artists = ", ".join(artists_list) if artists_list else album_artists
                
                # For albums, use album info for consistency
                track_data = {
                    "title": name,
                    "artists": artists,
                    "album": album_name,
                    "release_date": album_release_date,
                    "cover_url": album_cover_url,
                    "album_artist": album_artists,
                    "album_total_tracks": album["total_tracks"],
                    "genre": ", ".join(album.get("genres", [])) or "Unknown",
                    "track_number": track.get("track_number", 0),
                    "disc_number": track.get("disc_number", 1)
                }
                
                tracks.append(track_data)
            
            # Get next batch
            results = sp.next(results) if results["next"] else None
    
    except Exception as e:
        logger.error(f"Error retrieving album tracks: {e}")
        raise
    
    logger.info(f"Album tracks retrieved: {len(tracks)}")
    return tracks

# ---------------------------
# Spotify helpers
# ---------------------------

def create_spotify_client() -> Spotify:
    try:
        sp_oauth = SpotifyOAuth(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            redirect_uri=REDIRECT_URL,
            scope="user-library-read playlist-read-private playlist-read-collaborative",
            open_browser=True,
            cache_path=".cache",
        )
        sp = Spotify(auth_manager=sp_oauth)
        return sp
    except SpotifyOauthError as e:
        logger.error(f"Spotify OAuth setup error: {e}")
        raise SystemExit(1)


@lru_cache(maxsize=1)
def get_user_playlists(sp: Spotify) -> List[Tuple[str, str, int]]:
    """Get user playlists with caching and track count info"""
    playlists: List[Tuple[str, str, int]] = []
    logger.info("Retrieving user playlists…")

    try:
        # Use spotipy's built-in pagination for better performance
        results = sp.current_user_playlists(limit=50)
        
        while results:
            for item in results['items']:
                name = item.get('name', '(no name)')
                pid = item.get('id')
                track_count = item.get('tracks', {}).get('total', 0)
                
                if pid:
                    playlists.append((name, pid, track_count))
                    # Cache basic playlist info
                    playlist_cache[pid] = {
                        'name': name,
                        'track_count': track_count,
                        'images': item.get('images', []),
                        'description': item.get('description', ''),
                        'cached_at': time.time()
                    }
            
            # Get next batch
            results = sp.next(results) if results['next'] else None
            
    except Exception as e:
        logger.error(f"Error retrieving playlists: {e}")
        raise

    logger.info("Playlists retrieved: %d", len(playlists))
    return playlists


def _safe_get(dct, path: List[str], default=None):
    cur = dct
    for key in path:
        if not isinstance(cur, dict):
            return default
        cur = cur.get(key)
        if cur is None:
            return default
    return cur


def get_playlist_tracks(sp: Spotify, playlist_id: str, limit: Optional[int] = None, use_cache: bool = True) -> List[dict]:
    """Get playlist tracks with caching and performance optimizations"""
    
    # Check cache first
    cache_key = f"{playlist_id}_{limit or 'all'}"
    if use_cache and cache_key in tracks_cache:
        cached_data = tracks_cache[cache_key]
        if time.time() - cached_data.get('cached_at', 0) < CACHE_TIMEOUT:
            logger.info(f"Using cached tracks for playlist {playlist_id}")
            return cached_data['tracks']
    
    logger.info(f"Retrieving tracks for playlist {playlist_id}…")
    tracks: List[dict] = []
    
    try:
        # Use spotipy's optimized method with fields parameter to reduce data transfer
        fields = "items(track(name,artists(name,id),album(name,release_date,images,artists(name),total_tracks))),next,total"
        
        # Get tracks with pagination
        results = sp.playlist_tracks(
            playlist_id, 
            fields=fields,
            limit=min(100, limit) if limit else 100
        )
        
        total_processed = 0
        max_tracks = limit or float('inf')
        
        while results and total_processed < max_tracks:
            items = results.get('items', [])
            
            # Process tracks in batches for better performance
            batch_tracks = []
            artist_ids_to_fetch = set()
            
            for item in items:
                if total_processed >= max_tracks:
                    break
                    
                track = item.get("track")
                if not track or track.get('type') != 'track':
                    continue

                name = track.get("name", "Unknown Title")
                artists_list = [a.get("name", "?") for a in track.get("artists", [])]
                artists = ", ".join(artists_list) if artists_list else "Unknown Artist"

                album = track.get("album", {})
                album_name = album.get("name", "Unknown Album")
                release_date = album.get("release_date", "")
                images = album.get("images", [])
                cover_url = images[0]["url"] if images else None
                total_tracks = album.get("total_tracks", 0)

                # Collect artist IDs for batch genre fetching (only for first few tracks)
                first_artist_id = _safe_get(track, ["artists", 0, "id"])
                if first_artist_id and len(batch_tracks) < 10:  # Only get genres for first 10 tracks
                    artist_ids_to_fetch.add(first_artist_id)

                track_data = {
                    "title": name,
                    "artists": artists,
                    "album": album_name,
                    "release_date": release_date,
                    "cover_url": cover_url,
                    "album_artist": _safe_get(album, ["artists", 0, "name"], ""),
                    "album_total_tracks": total_tracks,
                    "genre": "Unknown",  # Will be updated if fetched
                    "artist_id": first_artist_id
                }
                
                batch_tracks.append(track_data)
                total_processed += 1
            
            # Batch fetch genres for better performance (only for preview tracks)
            if artist_ids_to_fetch and len(tracks) < PREVIEW_TRACK_LIMIT:
                try:
                    artists_info = sp.artists(list(artist_ids_to_fetch))
                    artist_genres = {}
                    for artist in artists_info.get('artists', []):
                        if artist and artist.get('genres'):
                            artist_genres[artist['id']] = artist['genres'][0]
                    
                    # Update genres
                    for track_data in batch_tracks:
                        if track_data['artist_id'] in artist_genres:
                            track_data['genre'] = artist_genres[track_data['artist_id']]
                        del track_data['artist_id']  # Remove temporary field
                except Exception as e:
                    logger.warning(f"Failed to fetch genres: {e}")
                    # Remove artist_id field from all tracks
                    for track_data in batch_tracks:
                        if 'artist_id' in track_data:
                            del track_data['artist_id']
            else:
                # Remove artist_id field when not fetching genres
                for track_data in batch_tracks:
                    if 'artist_id' in track_data:
                        del track_data['artist_id']
            
            tracks.extend(batch_tracks)
            
            # Get next batch if needed
            if total_processed < max_tracks and results.get('next'):
                remaining = max_tracks - total_processed
                results = sp.next(results)
            else:
                break
    
    except Exception as e:
        logger.error(f"Error retrieving tracks: {e}")
        raise
    
    # Cache the results
    if use_cache:
        tracks_cache[cache_key] = {
            'tracks': tracks,
            'cached_at': time.time()
        }
    
    logger.info(f"Tracks retrieved: {len(tracks)}")
    return tracks

# ---------------------------
# Utilities
# ---------------------------

def sanitize_filename(filename: str) -> str:
    valid_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
    return "".join(c for c in filename if c in valid_chars)


def sanitize_for_windows(filename: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "", filename)

# ---------------------------
# Download worker
# ---------------------------

@dataclass
class DownloadTask:
    idx: int
    total: int
    track: dict


def download_worker(task_queue: "queue.Queue[DownloadTask]", ui_queue: "queue.Queue[tuple]"):
    # Bot avoidance: Rotate user agents
    user_agents = [
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
    ]
    
    import random
    
    while True:
        task: Optional[DownloadTask] = task_queue.get()
        if task is None:
            break

        track = task.track
        title = track["title"]
        artists = track["artists"]
        album = track["album"]
        release_date = track["release_date"]
        cover_url = track["cover_url"]
        genre = track["genre"]

        try:
            folder = os.path.join(DOWNLOAD_DIR, sanitize_filename(album))
            os.makedirs(folder, exist_ok=True)

            base_name = f"{sanitize_filename(artists)} - {sanitize_filename(title)}.%(ext)s"
            outtmpl = os.path.join(folder, base_name)

            # Bot avoidance: Enhanced yt-dlp options
            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "quiet": True,
                "no_warnings": True,
                "extractaudio": True,
                "audioformat": "mp3",
                "audioquality": "192",
                "embed_metadata": True,
                "writeinfojson": False,
                "writedescription": False,
                "writesubtitles": False,
                "writeautomaticsub": False,
                "ignoreerrors": True,
                "no_check_certificate": True,
                "prefer_insecure": False,
                "http_chunk_size": 10485760,
                "retries": 3,
                "fragment_retries": 3,
                "skip_unavailable_fragments": True,
                "keep_fragments": False,
                "buffersize": 1024,
                "http_headers": {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-us,en;q=0.5',
                    'Accept-Encoding': 'gzip,deflate',
                    'Accept-Charset': 'ISO-8859-1,utf-8;q=0.7,*;q=0.7',
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1',
                },
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    },
                    {
                        "key": "FFmpegMetadata",
                        "add_metadata": True,
                    }
                ],
            }

            # Add random delay to avoid rate limiting
            delay = random.uniform(1.0, 3.0)
            time.sleep(delay)

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                query = f"{artists} {title} audio"
                ui_queue.put(("status", f"Searching: {artists} - {title}"))
                
                filepath = None
                search_attempts = [
                    f"ytsearch1:{artists} {title} audio",
                    f"ytsearch1:{artists} {title}",
                    f"ytsearch1:{title} {artists}",
                    f"ytsearch1:{title}"
                ]
                
                for attempt, search_query in enumerate(search_attempts, 1):
                    try:
                        ui_queue.put(("status", f"Search attempt {attempt}: {title}"))
                        info = ydl.extract_info(search_query, download=True)
                        
                        if not info:
                            continue
                        
                        # Handle both direct video info and search results
                        if 'entries' in info and info['entries']:
                            entry = info['entries'][0]
                            if not entry:
                                continue
                            filepath = ydl.prepare_filename(entry)
                        elif 'title' in info:
                            # Direct video info
                            filepath = ydl.prepare_filename(info)
                        else:
                            continue
                            
                        if filepath and os.path.exists(filepath.replace('.%(ext)s', '.mp3')):
                            # Success! Break out of retry loop
                            break
                        elif filepath:
                            # File might exist with different extension
                            base_path = os.path.splitext(filepath)[0]
                            for ext in ['.mp3', '.m4a', '.webm', '.opus']:
                                if os.path.exists(base_path + ext):
                                    filepath = base_path + ext
                                    break
                            if filepath and os.path.exists(filepath):
                                break
                                
                    except Exception as search_error:
                        ui_queue.put(("status", f"Attempt {attempt} failed: {str(search_error)}"))
                        if attempt == len(search_attempts):
                            # Last attempt failed
                            ui_queue.put(("status", f"❌ All search attempts failed for: {title}"))
                            filepath = None
                        continue
                
                if not filepath:
                    ui_queue.put(("status", f"❌ Could not download: {title}"))
                    continue

            # Ensure .mp3 extension and find the actual file
            mp3_filepath = None
            if filepath:
                # Try different possible file extensions
                base_path = os.path.splitext(filepath)[0]
                for ext in ['.mp3', '.m4a', '.webm', '.opus', '.mp4']:
                    test_path = base_path + ext
                    if os.path.exists(test_path):
                        if ext != '.mp3':
                            # Convert to mp3 if needed
                            mp3_filepath = base_path + '.mp3'
                            try:
                                import subprocess
                                subprocess.run([
                                    'ffmpeg', '-i', test_path, '-acodec', 'mp3', 
                                    '-ab', '192k', mp3_filepath, '-y'
                                ], check=True, capture_output=True)
                                os.remove(test_path)  # Remove original
                            except:
                                mp3_filepath = test_path  # Use original if conversion fails
                        else:
                            mp3_filepath = test_path
                        break
                
                if not mp3_filepath:
                    # Fallback: assume it's .mp3
                    mp3_filepath = base_path + '.mp3'

            # Add metadata if file exists
            if mp3_filepath and os.path.exists(mp3_filepath):
                try:
                    audio = MP3(mp3_filepath, ID3=ID3)
                    try:
                        audio.add_tags()
                    except Exception:
                        pass
                    
                    # Add ID3 tags
                    audio.tags.add(TIT2(encoding=3, text=title))
                    audio.tags.add(TPE1(encoding=3, text=artists))
                    audio.tags.add(TALB(encoding=3, text=album))
                    audio.tags.add(TDRC(encoding=3, text=release_date))
                    audio.tags.add(TCON(encoding=3, text=genre))

                    # Add cover art with bot avoidance
                    if cover_url:
                        try:
                            headers = {
                                'User-Agent': random.choice(user_agents),
                                'Accept': 'image/*,*/*;q=0.8',
                                'Accept-Language': 'en-US,en;q=0.5',
                                'Accept-Encoding': 'gzip, deflate',
                                'Connection': 'keep-alive',
                                'Upgrade-Insecure-Requests': '1'
                            }
                            
                            # Small delay before cover download
                            time.sleep(random.uniform(0.5, 1.5))
                            
                            img_response = requests.get(cover_url, headers=headers, timeout=10)
                            img_response.raise_for_status()
                            img_data = img_response.content
                            
                            audio.tags.add(APIC(
                                encoding=3, 
                                mime="image/jpeg", 
                                type=3, 
                                desc="Cover", 
                                data=img_data
                            ))
                        except Exception as cover_error:
                            ui_queue.put(("status", f"Cover art failed: {cover_error}"))

                    audio.save()
                    ui_queue.put(("status", f"✅ Saved: {os.path.basename(mp3_filepath)}"))
                    
                except Exception as metadata_error:
                    ui_queue.put(("status", f"Metadata error: {metadata_error}"))
                    # Still count as success if file exists
                    ui_queue.put(("status", f"✅ Saved (no metadata): {os.path.basename(mp3_filepath)}"))
            else:
                ui_queue.put(("status", f"❌ File not found after download: {title}"))

        except Exception as e:
            ui_queue.put(("status", f"❌ Error downloading {title}: {e}"))
            
            # Add exponential backoff on errors
            error_delay = random.uniform(2.0, 5.0)
            time.sleep(error_delay)

        finally:
            ui_queue.put(("progress", task.idx / task.total))
            task_queue.task_done()

    ui_queue.put(("status", "Idle"))

# ---------------------------
# GUI
# ---------------------------

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Enhanced window setup - made much larger for macOS compatibility
        self.title("🎵 Spotify Playlist Downloader")
        self.geometry("1200x1100")  # Much larger to ensure everything fits
        self.minsize(1000, 900)     # Larger minimum size
        
        # Center the window on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Modern sophisticated color scheme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")
        
        # Sophisticated color palette with gradients and modern tones
        self.colors = {
            "primary": "#8B5CF6",        # Purple Primary
            "primary_light": "#A78BFA",  # Light Purple
            "primary_dark": "#7C3AED",   # Dark Purple
            "secondary": "#06B6D4",     # Cyan Secondary
            "secondary_light": "#67E8F9", # Light Cyan
            "accent": "#F59E0B",         # Amber Accent
            "accent_hover": "#FBBF24",   # Light Amber
            "background": "#0F0F23",     # Deep Space Blue
            "background_light": "#1E1B4B", # Lighter Space Blue
            "surface": "#1F2937",        # Cool Gray Surface
            "surface_light": "#374151",  # Light Gray Surface
            "glass": "#2D1B69",          # Glass Purple (converted from rgba)
            "glass_border": "#4C1D95",   # Glass Border (converted from rgba)
            "gradient_start": "#8B5CF6",  # Gradient Start
            "gradient_end": "#06B6D4",    # Gradient End
            "error": "#EF4444",          # Modern Red
            "warning": "#F59E0B",        # Amber Warning
            "success": "#10B981",        # Emerald Success
            "text_primary": "#F9FAFB",   # Pure White
            "text_secondary": "#D1D5DB", # Light Gray
            "text_muted": "#9CA3AF",     # Muted Gray
            "hover_overlay": "#3B1F72"   # Hover Effect (converted from rgba)
        }

        self.sp = create_spotify_client()
        self.playlists_map = {}
        self.playlists_info = {}  # Store track counts and metadata
        self.selected_playlist = StringVar()
        self.task_queue: "queue.Queue[DownloadTask]" = queue.Queue()
        self.ui_queue: "queue.Queue[tuple]" = queue.Queue()
        self.worker_thread: Optional[threading.Thread] = None
        self.downloading = False
        
        # Performance optimization
        self.executor = ThreadPoolExecutor(max_workers=2)  # Reduced for bot avoidance
        self.preview_loading = False
        self.last_preview_request = 0
        
        # UI elements initialization
        self.track_count_label = None
        self.speed_label = None
        self.eta_label = None
        
        self.setup_ui()
        self.refresh_playlists()
        self.after(100, self.process_ui_queue)
    
    def setup_ui(self):
        # Modern background with subtle gradient effect
        self.configure(fg_color=self.colors["background"])
        
        # Header section
        self.create_header()
        
        # Create scrollable main frame for better compatibility
        self.main_frame = ctk.CTkScrollableFrame(
            self, 
            corner_radius=25,
            fg_color=self.colors["surface"],
            border_width=2,
            border_color=self.colors["glass_border"]
        )
        self.main_frame.pack(padx=30, pady=(0, 30), fill="both", expand=True)
        
        # Content container
        self.content_frame = ctk.CTkFrame(
            self.main_frame,
            corner_radius=15,
            fg_color="transparent"
        )
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create all sections
        self.create_url_input_section()
        self.create_playlist_section()
        self.create_preview_section()
        self.create_controls_section()
        self.create_progress_section()
        self.create_log_section()
        
        # Debug: Print that UI is complete
        print("✅ UI Setup Complete - All sections created")
        print("🎛️ Download Control Center should be visible now")
    
    def create_header(self):
        """Create stunning gradient header with glass-morphism effects"""
        # Create gradient background effect
        header_frame = ctk.CTkFrame(
            self, 
            height=100, 
            corner_radius=0,
            fg_color=self.colors["background"]
        )
        header_frame.pack(fill="x", padx=0, pady=0)
        header_frame.pack_propagate(False)
        
        # Gradient overlay frame
        gradient_frame = ctk.CTkFrame(
            header_frame,
            corner_radius=0,
            fg_color=self.colors["primary"]
        )
        gradient_frame.pack(fill="both", expand=True)
        
        # Title section with enhanced styling
        title_container = ctk.CTkFrame(gradient_frame, fg_color="transparent")
        title_container.pack(expand=True, fill="both")
        
        # Main title with gradient-style effect
        title = ctk.CTkLabel(
            title_container,
            text="🎵 Spotify Playlist Downloader",
            font=ctk.CTkFont(size=32, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        title.pack(pady=(25, 5))
        
        # Subtitle with sophisticated styling
        subtitle = ctk.CTkLabel(
            title_container,
            text="✨ Premium Music Downloading Experience ✨",
            font=ctk.CTkFont(size=16, weight="normal"),
            text_color=self.colors["text_secondary"]
        )
        subtitle.pack(pady=(0, 10))
        
        # Status bar with glass effect
        status_bar = ctk.CTkFrame(
            title_container,
            height=3,
            corner_radius=2,
            fg_color=self.colors["secondary"]
        )
        status_bar.pack(fill="x", padx=100, pady=(5, 15))
    
    def create_url_input_section(self):
        """Create URL input section for direct playlist/album links"""
        url_card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=20,
            fg_color=self.colors["glass"],
            border_width=2,
            border_color=self.colors["glass_border"]
        )
        url_card.pack(fill="x", padx=25, pady=(25, 20))
        
        # Section title with icon
        title_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="🔗 Paste Spotify Link",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        title_label.pack(side="left")
        
        # Link indicator
        link_indicator = ctk.CTkLabel(
            title_frame,
            text="🎯",
            font=ctk.CTkFont(size=16),
            text_color=self.colors["accent"]
        )
        link_indicator.pack(side="right")
        
        # Input row
        input_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        input_frame.pack(fill="x", padx=25, pady=(0, 20))
        
        # URL input field
        self.url_entry = ctk.CTkEntry(
            input_frame,
            placeholder_text="Paste Spotify playlist or album URL here...",
            width=600,
            height=45,
            corner_radius=15,
            border_width=2,
            border_color=self.colors["secondary"],
            fg_color=self.colors["surface_light"],
            font=ctk.CTkFont(size=14)
        )
        self.url_entry.pack(side="left", padx=(0, 15))
        
        # Paste & Load button
        self.load_url_btn = ctk.CTkButton(
            input_frame,
            text="📥 Load from URL",
            width=150,
            height=45,
            corner_radius=15,
            fg_color=self.colors["accent"],
            hover_color=self.colors["accent_hover"],
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.load_from_url
        )
        self.load_url_btn.pack(side="left")
        
        # Quick paste button
        paste_btn = ctk.CTkButton(
            input_frame,
            text="📋",
            width=45,
            height=45,
            corner_radius=15,
            fg_color=self.colors["surface"],
            hover_color=self.colors["surface_light"],
            font=ctk.CTkFont(size=16),
            command=self.paste_from_clipboard
        )
        paste_btn.pack(side="left", padx=(10, 0))
        
        # Separator
        separator = ctk.CTkFrame(
            self.content_frame,
            height=2,
            corner_radius=1,
            fg_color=self.colors["glass_border"]
        )
        separator.pack(fill="x", padx=50, pady=10)
    
    def create_playlist_section(self):
        """Create playlist selection with modern glass card design"""
        playlist_card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=20,
            fg_color=self.colors["glass"],
            border_width=2,
            border_color=self.colors["glass_border"]
        )
        playlist_card.pack(fill="x", padx=25, pady=(25, 20))
        
        # Section title with icon and modern styling
        title_frame = ctk.CTkFrame(playlist_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        title_label = ctk.CTkLabel(
            title_frame,
            text="🎧 Select Your Playlist",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        title_label.pack(side="left")
        
        # Decorative element
        decoration = ctk.CTkLabel(
            title_frame,
            text="✨",
            font=ctk.CTkFont(size=16),
            text_color=self.colors["secondary"]
        )
        decoration.pack(side="right")
        
        # Selection row with enhanced styling
        selection_frame = ctk.CTkFrame(playlist_card, fg_color="transparent")
        selection_frame.pack(fill="x", padx=25, pady=(0, 20))
        
        # Modern dropdown with gradient-style
        self.playlist_dropdown = ctk.CTkComboBox(
            selection_frame,
            variable=self.selected_playlist,
            width=600,
            height=45,
            corner_radius=15,
            border_width=2,
            border_color=self.colors["primary"],
            fg_color=self.colors["surface_light"],
            button_color=self.colors["primary"],
            button_hover_color=self.colors["primary_light"],
            dropdown_fg_color=self.colors["surface"],
            font=ctk.CTkFont(size=15, weight="normal"),
            command=lambda choice: self.update_playlist_preview(choice)
        )
        self.playlist_dropdown.pack(side="left", padx=(0, 20))
        
        # Modern refresh button with hover effects
        self.refresh_btn = ctk.CTkButton(
            selection_frame,
            text="🔄 Refresh",
            width=140,
            height=45,
            corner_radius=15,
            fg_color=self.colors["secondary"],
            hover_color=self.colors["secondary_light"],
            font=ctk.CTkFont(size=15, weight="bold"),
            command=self.refresh_playlists
        )
        self.refresh_btn.pack(side="left")
    
    def create_preview_section(self):
        """Create stunning preview section with glass effects"""
        preview_card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=20,
            fg_color=self.colors["glass"],
            border_width=2,
            border_color=self.colors["glass_border"]
        )
        # Made preview section not expand to leave room for controls
        preview_card.pack(fill="x", padx=25, pady=(0, 20))
        
        # Section title with gradient-style header
        title_frame = ctk.CTkFrame(preview_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        preview_title = ctk.CTkLabel(
            title_frame,
            text="👁️ Playlist Preview",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        preview_title.pack(side="left")
        
        # Live indicator
        live_indicator = ctk.CTkLabel(
            title_frame,
            text="🔴 LIVE",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=self.colors["error"]
        )
        live_indicator.pack(side="right")
        
        # Content area with modern layout
        content_frame = ctk.CTkFrame(preview_card, fg_color="transparent")
        content_frame.pack(fill="both", expand=True, padx=25, pady=(0, 20))
        
        # Left side - Enhanced cover art with glass frame
        cover_container = ctk.CTkFrame(
            content_frame,
            width=200,
            corner_radius=20,
            fg_color=self.colors["surface_light"],
            border_width=2,
            border_color=self.colors["primary"]
        )
        cover_container.pack(side="left", padx=(0, 20), pady=5, fill="y")
        cover_container.pack_propagate(False)
        
        # Glass overlay for cover
        cover_glass = ctk.CTkFrame(
            cover_container,
            corner_radius=15,
            fg_color=self.colors["glass"]
        )
        cover_glass.pack(fill="both", expand=True, padx=5, pady=5)
        
        self.cover_label = ctk.CTkLabel(
            cover_glass,
            text="🎨\n\nAwaiting\nSelection",
            font=ctk.CTkFont(size=15, weight="normal"),
            text_color=self.colors["text_muted"]
        )
        self.cover_label.pack(expand=True)
        
        # Right side - Enhanced tracklist with modern styling
        tracklist_container = ctk.CTkFrame(
            content_frame,
            corner_radius=20,
            fg_color=self.colors["surface_light"],
            border_width=2,
            border_color=self.colors["secondary"]
        )
        tracklist_container.pack(side="right", fill="both", expand=True, pady=5)
        
        # Tracklist header
        tracklist_header = ctk.CTkFrame(tracklist_container, fg_color="transparent")
        tracklist_header.pack(fill="x", padx=20, pady=(15, 10))
        
        tracklist_title = ctk.CTkLabel(
            tracklist_header,
            text="🎵 Track Listing",
            font=ctk.CTkFont(size=18, weight="bold"),
            text_color=self.colors["primary"]
        )
        tracklist_title.pack(side="left")
        
        # Track count indicator
        self.track_count_label = ctk.CTkLabel(
            tracklist_header,
            text="0 tracks",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_muted"]
        )
        self.track_count_label.pack(side="right")
        
        # Enhanced tracklist box with fixed height
        self.tracklist_box = ctk.CTkTextbox(
            tracklist_container,
            corner_radius=15,
            border_width=1,
            border_color=self.colors["glass_border"],
            fg_color=self.colors["background_light"],
            font=ctk.CTkFont(size=13, family="SF Pro Display"),
            wrap="word",
            height=200  # Fixed height to prevent taking up too much space
        )
        self.tracklist_box.pack(fill="x", padx=20, pady=(0, 20))
        self.tracklist_box.configure(state="disabled")
    
    def create_controls_section(self):
        """Create modern control panel with gradient buttons"""
        print("🎛️ Creating Download Control Center...")
        
        controls_card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=20,
            fg_color=self.colors["glass"],
            border_width=2,
            border_color=self.colors["glass_border"]
        )
        controls_card.pack(fill="x", padx=25, pady=(0, 20))
        
        # Section title with modern styling
        title_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        controls_title = ctk.CTkLabel(
            title_frame,
            text="🎛️ Download Control Center",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        controls_title.pack(side="left")
        
        # Power indicator
        power_indicator = ctk.CTkLabel(
            title_frame,
            text="⚡",
            font=ctk.CTkFont(size=18),
            text_color=self.colors["accent"]
        )
        power_indicator.pack(side="right")
        
        # Button row with enhanced styling
        button_frame = ctk.CTkFrame(controls_card, fg_color="transparent")
        button_frame.pack(fill="x", padx=25, pady=(0, 20))
        
        # Modern start button with gradient effect
        self.start_btn = ctk.CTkButton(
            button_frame,
            text="▶️ Start Download",
            width=200,
            height=50,
            corner_radius=18,
            fg_color=self.colors["primary"],
            hover_color=self.colors["primary_light"],
            font=ctk.CTkFont(size=17, weight="bold"),
            command=self.start_download
        )
        self.start_btn.pack(side="left", padx=(0, 20))
        
        # Modern stop button
        self.stop_btn = ctk.CTkButton(
            button_frame,
            text="⏹️ Stop",
            width=130,
            height=50,
            corner_radius=18,
            fg_color=self.colors["surface"],
            hover_color=self.colors["error"],
            font=ctk.CTkFont(size=17, weight="bold"),
            state="disabled",
            command=self.stop_download
        )
        self.stop_btn.pack(side="left")
        
        # Status display with glass effect
        self.status_frame = ctk.CTkFrame(
            button_frame,
            corner_radius=15,
            fg_color=self.colors["surface_light"],
            border_width=1,
            border_color=self.colors["glass_border"]
        )
        self.status_frame.pack(side="right", padx=(20, 0), fill="both", expand=True)
        
        status_header = ctk.CTkLabel(
            self.status_frame,
            text="📊 System Status",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_secondary"]
        )
        status_header.pack(side="left", padx=(20, 10), pady=12)
        
        self.status_label = ctk.CTkLabel(
            self.status_frame,
            text="🟢 Ready for Action",
            font=ctk.CTkFont(size=14, weight="normal"),
            text_color=self.colors["success"]
        )
        self.status_label.pack(side="left", pady=12)
        
        print("✅ Download Control Center created successfully!")
        print(f"▶️ Start button created: {self.start_btn}")
        print(f"⏹️ Stop button created: {self.stop_btn}")
    
    def create_progress_section(self):
        """Create stunning progress tracking with animated elements"""
        progress_card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=20,
            fg_color=self.colors["glass"],
            border_width=2,
            border_color=self.colors["glass_border"]
        )
        progress_card.pack(fill="x", padx=25, pady=(0, 20))
        
        # Section title with modern icon
        title_frame = ctk.CTkFrame(progress_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        progress_title = ctk.CTkLabel(
            title_frame,
            text="📈 Download Progress",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        progress_title.pack(side="left")
        
        # Speed indicator
        self.speed_label = ctk.CTkLabel(
            title_frame,
            text="🚀 Ready",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_muted"]
        )
        self.speed_label.pack(side="right")
        
        # Progress container with enhanced styling
        progress_container = ctk.CTkFrame(progress_card, fg_color="transparent")
        progress_container.pack(fill="x", padx=25, pady=(0, 20))
        
        # Modern progress bar with gradient effect
        self.progress = ctk.CTkProgressBar(
            progress_container,
            height=25,
            corner_radius=15,
            progress_color=self.colors["secondary"],
            fg_color=self.colors["surface"]
        )
        self.progress.pack(fill="x", pady=(0, 10))
        self.progress.set(0)
        
        # Progress info row
        info_frame = ctk.CTkFrame(progress_container, fg_color="transparent")
        info_frame.pack(fill="x")
        
        # Progress percentage
        self.progress_text = ctk.CTkLabel(
            info_frame,
            text="0%",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        self.progress_text.pack(side="left")
        
        # ETA display
        self.eta_label = ctk.CTkLabel(
            info_frame,
            text="ETA: --:--",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["text_muted"]
        )
        self.eta_label.pack(side="right")
    
    def create_log_section(self):
        """Create modern terminal-style log with glass effects"""
        log_card = ctk.CTkFrame(
            self.content_frame,
            corner_radius=20,
            fg_color=self.colors["glass"],
            border_width=2,
            border_color=self.colors["glass_border"]
        )
        log_card.pack(fill="x", padx=25, pady=(0, 25))  # Changed from fill="both" expand=True
        
        # Section title with terminal styling
        title_frame = ctk.CTkFrame(log_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        log_title = ctk.CTkLabel(
            title_frame,
            text="� System Console",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color=self.colors["text_primary"]
        )
        log_title.pack(side="left")
        
        # Terminal indicator
        terminal_indicator = ctk.CTkLabel(
            title_frame,
            text="● ● ●",
            font=ctk.CTkFont(size=12),
            text_color=self.colors["secondary"]
        )
        terminal_indicator.pack(side="right")
        
        # Log container with terminal styling
        log_container = ctk.CTkFrame(
            log_card,
            corner_radius=15,
            fg_color=self.colors["background"],
            border_width=1,
            border_color=self.colors["secondary"]
        )
        log_container.pack(fill="both", expand=True, padx=25, pady=(0, 20))
        
        # Terminal header
        terminal_header = ctk.CTkFrame(
            log_container,
            height=35,
            corner_radius=10,
            fg_color=self.colors["surface"]
        )
        terminal_header.pack(fill="x", padx=5, pady=(5, 0))
        terminal_header.pack_propagate(False)
        
        header_text = ctk.CTkLabel(
            terminal_header,
            text="🖥️ spotify-downloader:~ $ tail -f activity.log",
            font=ctk.CTkFont(size=11, family="Monaco"),
            text_color=self.colors["text_muted"]
        )
        header_text.pack(pady=8, padx=15, anchor="w")
        
        # Enhanced log box with terminal styling and fixed height
        self.logbox = ctk.CTkTextbox(
            log_container,
            corner_radius=10,
            border_width=0,
            fg_color=self.colors["background"],
            font=ctk.CTkFont(size=12, family="Monaco"),
            wrap="word",
            height=150  # Fixed height to save space
        )
        self.logbox.pack(fill="x", padx=5, pady=(5, 5))
        self.logbox.configure(state="disabled")

    def log(self, msg: str, level: str = "INFO"):
        """Enhanced logging with timestamps and color coding"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        # Color coding based on message content
        if "Error" in msg or "Failed" in msg:
            level = "ERROR"
            prefix = "❌"
        elif "Success" in msg or "Saved:" in msg or "completed" in msg.lower():
            level = "SUCCESS"
            prefix = "✅"
        elif "Warning" in msg:
            level = "WARNING"
            prefix = "⚠️"
        else:
            prefix = "ℹ️"
        
        formatted_msg = f"[{timestamp}] {prefix} {msg}"
        logger.info(msg)
        
        self.logbox.configure(state="normal")
        self.logbox.insert("end", formatted_msg + "\n")
        self.logbox.see("end")
        self.logbox.configure(state="disabled")

    def refresh_playlists(self):
        """Refresh playlist list with enhanced UI feedback and async loading"""
        def _load_playlists():
            try:
                # Get playlists with track counts
                data = get_user_playlists(self.sp)
                names_with_info = []
                
                for name, pid, track_count in data:
                    # Format name with track count for better UX
                    display_name = f"{name} ({track_count} tracks)"
                    names_with_info.append(display_name)
                    self.playlists_map[display_name] = pid
                    self.playlists_info[display_name] = {
                        'original_name': name,
                        'playlist_id': pid,
                        'track_count': track_count
                    }
                
                # Update UI on main thread
                self.after(0, lambda: self._update_playlist_ui(names_with_info, None))
                
            except Exception as e:
                self.after(0, lambda: self._update_playlist_ui([], str(e)))
        
        # Update status
        self.status_label.configure(text="🔄 Loading playlists...")
        self.refresh_btn.configure(state="disabled", text="Loading...")
        
        # Load playlists in background thread
        self.executor.submit(_load_playlists)
    
    def _update_playlist_ui(self, names: List[str], error: Optional[str]):
        """Update playlist UI on main thread"""
        try:
            if error:
                self.status_label.configure(
                    text="❌ Failed to load playlists",
                    text_color=self.colors["error"]
                )
                self.log(f"Failed to load playlists: {error}", "ERROR")
            else:
                # Update dropdown
                self.playlist_dropdown.configure(values=names)
                if names:
                    self.selected_playlist.set(names[0])
                    # Only load preview for small playlists immediately
                    playlist_info = self.playlists_info[names[0]]
                    if playlist_info['track_count'] < LAZY_LOAD_THRESHOLD:
                        self.update_playlist_preview(names[0])
                    else:
                        self._show_lazy_preview(names[0])
                
                # Update status
                self.status_label.configure(
                    text=f"✅ {len(names)} playlists loaded",
                    text_color=self.colors["success"]
                )
                self.log(f"Successfully loaded {len(names)} playlists", "SUCCESS")
        
        finally:
            self.refresh_btn.configure(state="normal", text="🔄 Refresh")
    
    def paste_from_clipboard(self):
        """Paste URL from clipboard"""
        try:
            # Get clipboard content
            clipboard_content = self.clipboard_get()
            if clipboard_content:
                self.url_entry.delete(0, 'end')
                self.url_entry.insert(0, clipboard_content.strip())
                self.log("📋 Pasted URL from clipboard", "INFO")
        except Exception as e:
            self.log(f"Failed to paste from clipboard: {e}", "WARNING")
    
    def load_from_url(self):
        """Load playlist or album from URL"""
        url = self.url_entry.get().strip()
        if not url:
            self.log("Please enter a Spotify URL", "WARNING")
            return
        
        def _load_url():
            try:
                # Update UI
                self.after(0, lambda: self.load_url_btn.configure(state="disabled", text="🔄 Loading..."))
                self.after(0, lambda: self.status_label.configure(
                    text="🔄 Processing URL...",
                    text_color=self.colors["primary"]
                ))
                
                # Parse URL
                parsed = parse_spotify_url(url)
                if not parsed:
                    self.after(0, lambda: self.log("❌ Invalid Spotify URL format", "ERROR"))
                    self.after(0, lambda: self.status_label.configure(
                        text="❌ Invalid URL",
                        text_color=self.colors["error"]
                    ))
                    return
                
                content_type, content_id = parsed
                self.after(0, lambda: self.log(f"🔍 Detected {content_type}: {content_id}", "INFO"))
                
                # Validate content
                content_info = validate_spotify_content(self.sp, content_type, content_id)
                if not content_info:
                    self.after(0, lambda: self.log("❌ Could not access this Spotify content", "ERROR"))
                    self.after(0, lambda: self.status_label.configure(
                        text="❌ Access denied",
                        text_color=self.colors["error"]
                    ))
                    return
                
                # Success - update UI
                self.after(0, lambda: self._handle_url_content(content_info))
                
            except Exception as e:
                self.after(0, lambda: self.log(f"❌ Error loading URL: {e}", "ERROR"))
                self.after(0, lambda: self.status_label.configure(
                    text="❌ Loading failed",
                    text_color=self.colors["error"]
                ))
            finally:
                self.after(0, lambda: self.load_url_btn.configure(state="normal", text="📥 Load from URL"))
        
        # Process URL in background
        self.executor.submit(_load_url)
    
    def _handle_url_content(self, content_info: Dict[str, Any]):
        """Handle loaded content from URL"""
        content_type = content_info["type"]
        content_name = content_info["name"]
        track_count = content_info["track_count"]
        
        if content_type == "playlist":
            # Add to playlist dropdown as if it was a user playlist
            display_name = f"🔗 {content_name} ({track_count} tracks)"
            
            # Store in our maps
            self.playlists_map[display_name] = content_info["id"]
            self.playlists_info[display_name] = {
                'original_name': content_name,
                'playlist_id': content_info["id"],
                'track_count': track_count,
                'from_url': True
            }
            
            # Update dropdown
            current_values = list(self.playlist_dropdown.cget("values"))
            if display_name not in current_values:
                current_values.insert(0, display_name)  # Add at top
                self.playlist_dropdown.configure(values=current_values)
            
            # Select it
            self.selected_playlist.set(display_name)
            
        elif content_type == "album":
            # Create a special album entry
            display_name = f"💿 {content_name} by {content_info['artist']} ({track_count} tracks)"
            
            # Store in our maps
            self.playlists_map[display_name] = content_info["id"]
            self.playlists_info[display_name] = {
                'original_name': content_name,
                'playlist_id': content_info["id"],
                'track_count': track_count,
                'from_url': True,
                'is_album': True,
                'artist': content_info['artist']
            }
            
            # Update dropdown
            current_values = list(self.playlist_dropdown.cget("values"))
            if display_name not in current_values:
                current_values.insert(0, display_name)  # Add at top
                self.playlist_dropdown.configure(values=current_values)
            
            # Select it
            self.selected_playlist.set(display_name)
        
        # Load preview
        if track_count < LAZY_LOAD_THRESHOLD:
            self.update_playlist_preview(display_name)
        else:
            self._show_lazy_preview(display_name)
        
        # Success message
        self.log(f"✅ Successfully loaded {content_type}: {content_name}", "SUCCESS")
        self.status_label.configure(
            text=f"✅ {content_type.title()} loaded successfully",
            text_color=self.colors["success"]
        )
        
        # Clear URL field
        self.url_entry.delete(0, 'end')

    def update_playlist_preview(self, playlist_name: str, force_full_load: bool = False):
        """Update playlist preview with enhanced visuals and performance"""
        # Debounce rapid requests
        current_time = time.time()
        if current_time - self.last_preview_request < 0.5 and not force_full_load:
            return
        self.last_preview_request = current_time
        
        pid = self.playlists_map.get(playlist_name)
        if not pid:
            return
        
        playlist_info = self.playlists_info.get(playlist_name, {})
        track_count = playlist_info.get('track_count', 0)
        is_album = playlist_info.get('is_album', False)
        
        # For large playlists, use lazy loading unless forced
        if track_count > LAZY_LOAD_THRESHOLD and not force_full_load:
            self._show_lazy_preview(playlist_name)
            return
        
        try:
            # Use cached data if available
            if pid in playlist_cache:
                cached = playlist_cache[pid]
                if time.time() - cached.get('cached_at', 0) < CACHE_TIMEOUT:
                    data = cached
                else:
                    # Refresh cache - handle albums vs playlists
                    if is_album:
                        album_data = self.sp.album(pid)
                        data = {
                            'name': album_data['name'],
                            'description': f"Album by {', '.join([artist['name'] for artist in album_data['artists']])}",
                            'images': album_data.get('images', []),
                            'tracks': {'total': album_data['total_tracks']},
                            'cached_at': time.time()
                        }
                    else:
                        playlist_data = self.sp.playlist(pid, fields="name,description,images,tracks.total")
                        data = {
                            'name': playlist_data['name'],
                            'description': playlist_data.get('description', ''),
                            'images': playlist_data.get('images', []),
                            'tracks': {'total': playlist_data['tracks']['total']},
                            'cached_at': time.time()
                        }
                    playlist_cache[pid] = data
            else:
                # Get basic data - handle albums vs playlists
                if is_album:
                    album_data = self.sp.album(pid)
                    data = {
                        'name': album_data['name'],
                        'description': f"Album by {', '.join([artist['name'] for artist in album_data['artists']])}",
                        'images': album_data.get('images', []),
                        'tracks': {'total': album_data['total_tracks']},
                        'cached_at': time.time()
                    }
                else:
                    playlist_data = self.sp.playlist(pid, fields="name,description,images,tracks.total")
                    data = {
                        'name': playlist_data['name'],
                        'description': playlist_data.get('description', ''),
                        'images': playlist_data.get('images', []),
                        'tracks': {'total': playlist_data['tracks']['total']},
                        'cached_at': time.time()
                    }
                playlist_cache[pid] = data
            
            # Enhanced cover image display
            images = data.get("images") or []
            if images:
                img_url = images[0]["url"]
                if img_url in image_cache:
                    # Use cached image
                    self.cover_label.configure(image=image_cache[img_url], text="")
                else:
                    # Load image asynchronously
                    self._load_cover_async(img_url)
            else:
                # Default cover placeholder
                self.cover_label.configure(
                    image="",
                    text="🎨\n\nNo Cover\nAvailable",
                    font=ctk.CTkFont(size=14),
                    text_color=self.colors["text_secondary"]
                )
            
            # Enhanced tracklist with metadata (load limited tracks for preview)
            preview_limit = min(PREVIEW_TRACK_LIMIT, track_count)
            
            playlist_info = self.playlists_info.get(playlist_name, {})
            if playlist_info.get('is_album', False):
                # Handle album preview
                tracks = get_album_tracks(self.sp, pid)
                if preview_limit < len(tracks):
                    tracks = tracks[:preview_limit]
            else:
                # Handle playlist preview
                tracks = get_playlist_tracks(self.sp, pid, limit=preview_limit)
            
            self.tracklist_box.configure(state="normal")
            self.tracklist_box.delete("1.0", "end")
            
            # Header
            playlist_info_data = data.get("description", "")
            track_count_total = data.get("tracks", {}).get("total", len(tracks))
            
            # Update track count display
            if self.track_count_label:
                content_type = "album" if playlist_info.get('is_album', False) else "playlist"
                self.track_count_label.configure(text=f"{track_count_total} tracks ({content_type})")
            
            content_icon = "💿" if playlist_info.get('is_album', False) else "📋"
            self.tracklist_box.insert("end", f"{content_icon} {data.get('name', playlist_name)}\n")
            
            if playlist_info.get('is_album', False):
                artist_name = playlist_info.get('artist', 'Unknown Artist')
                self.tracklist_box.insert("end", f"🎤 Artist: {artist_name}\n")
            
            self.tracklist_box.insert("end", f"🎵 {track_count_total} tracks total\n")
            if playlist_info_data:
                desc_text = playlist_info_data[:100] + "..." if len(playlist_info_data) > 100 else playlist_info_data
                self.tracklist_box.insert("end", f"📝 {desc_text}\n")
            self.tracklist_box.insert("end", "\n" + "─" * 50 + "\n\n")
            
            # Track list with enhanced formatting
            is_album = playlist_info.get('is_album', False)
            for idx, track in enumerate(tracks, start=1):
                if is_album and 'track_number' in track:
                    # For albums, show track numbers
                    track_num = track.get('track_number', idx)
                    disc_num = track.get('disc_number', 1)
                    if disc_num > 1:
                        track_display = f"{disc_num}-{track_num:02d}"
                    else:
                        track_display = f"{track_num:02d}"
                    
                    self.tracklist_box.insert(
                        "end", 
                        f"{track_display}. 🎵 {track['artists']} – {track['title']}\n"
                        f"      💿 {track['album']} ({track['release_date'][:4] if track['release_date'] else 'Unknown'})\n\n"
                    )
                else:
                    # For playlists, show sequential numbers
                    self.tracklist_box.insert(
                        "end", 
                        f"{idx:2d}. 🎵 {track['artists']} – {track['title']}\n"
                        f"     💿 {track['album']} ({track['release_date'][:4] if track['release_date'] else 'Unknown'})\n\n"
                    )
            
            if track_count_total > preview_limit:
                remaining = track_count_total - preview_limit
                self.tracklist_box.insert(
                    "end", 
                    f"\n⬇️ ... and {remaining} more tracks\n"
                    f"💡 Total duration: ~{track_count_total * 3.5:.0f} minutes\n"
                )
            
            self.tracklist_box.configure(state="disabled")
            
        except Exception as e:
            self.log(f"Failed to load playlist preview: {e}", "ERROR")
            # Reset cover to placeholder
            self.cover_label.configure(
                image="",
                text="❌\n\nPreview\nUnavailable",
                text_color=self.colors["error"]
            )
    
    def _show_lazy_preview(self, playlist_name: str):
        """Show basic info for large playlists without loading all tracks"""
        try:
            playlist_info = self.playlists_info.get(playlist_name, {})
            original_name = playlist_info.get('original_name', playlist_name)
            track_count = playlist_info.get('track_count', 0)
            pid = playlist_info.get('playlist_id')
            
            if not pid:
                return
            
            # Show cached cover if available
            cached_playlist = playlist_cache.get(pid, {})
            images = cached_playlist.get('images', [])
            
            if images:
                img_url = images[0]['url']
                if img_url in image_cache:
                    # Use cached image
                    self.cover_label.configure(
                        image=image_cache[img_url], 
                        text=""
                    )
                else:
                    # Load image in background
                    self._load_cover_async(img_url)
            else:
                self.cover_label.configure(
                    image="",
                    text="🎨\n\nNo Cover\nAvailable",
                    text_color=self.colors["text_secondary"]
                )
            
            # Show basic info without loading all tracks
            self.tracklist_box.configure(state="normal")
            self.tracklist_box.delete("1.0", "end")
            
            description = cached_playlist.get('description', '')
            
            # Update track count display
            if self.track_count_label:
                content_type = "album" if playlist_info.get('is_album', False) else "playlist"
                self.track_count_label.configure(text=f"{track_count} tracks ({content_type})")
            
            content_icon = "💿" if playlist_info.get('is_album', False) else "📋"
            self.tracklist_box.insert("end", f"{content_icon} {original_name}\n")
            
            if playlist_info.get('is_album', False):
                artist_name = playlist_info.get('artist', 'Unknown Artist')
                self.tracklist_box.insert("end", f"🎤 Artist: {artist_name}\n")
            
            self.tracklist_box.insert("end", f"🎵 {track_count} tracks total\n")
            if description:
                desc_preview = description[:100] + "..." if len(description) > 100 else description
                self.tracklist_box.insert("end", f"📝 {desc_preview}\n")
            
            self.tracklist_box.insert("end", "\n" + "─" * 50 + "\n\n")
            
            if track_count > LAZY_LOAD_THRESHOLD:
                self.tracklist_box.insert(
                    "end", 
                    f"⚡ Large playlist detected ({track_count} tracks)\n"
                    f" Tip: This playlist will download all {track_count} tracks\n"
                    f"⏱️  Estimated time: ~{track_count * 2} minutes\n\n"
                    f"🔄 To see full track list, use the download preview during download\n"
                )
            
            self.tracklist_box.configure(state="disabled")
            
        except Exception as e:
            self.log(f"Failed to show lazy preview: {e}", "ERROR")
    
    def _load_full_preview(self, playlist_name: str):
        """Load full preview for large playlists"""
        if self.preview_loading:
            return
            
        self.preview_loading = True
        
        def _load():
            try:
                self.after(0, lambda: self.tracklist_box.configure(state="normal"))
                self.after(0, lambda: self.tracklist_box.delete("1.0", "end"))
                self.after(0, lambda: self.tracklist_box.insert("end", "🔄 Loading full track list...\n"))
                self.after(0, lambda: self.tracklist_box.configure(state="disabled"))
                
                # Load with limit for preview
                self.update_playlist_preview(playlist_name, force_full_load=True)
                
            except Exception as e:
                self.after(0, lambda: self.log(f"Failed to load full preview: {e}", "ERROR"))
            finally:
                self.preview_loading = False
        
        self.executor.submit(_load)
    
    def _load_cover_async(self, img_url: str):
        """Load cover image asynchronously with bot avoidance"""
        def _load():
            try:
                # Bot avoidance: Rotate user agents and add realistic headers
                import random
                user_agents = [
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
                    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
                ]
                
                headers = {
                    'User-Agent': random.choice(user_agents),
                    'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.9',
                    'Accept-Encoding': 'gzip, deflate, br',
                    'Connection': 'keep-alive',
                    'Sec-Fetch-Dest': 'image',
                    'Sec-Fetch-Mode': 'no-cors',
                    'Sec-Fetch-Site': 'cross-site',
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                }
                
                # Add small random delay
                time.sleep(random.uniform(0.1, 0.5))
                
                response = requests.get(img_url, timeout=15, headers=headers)
                response.raise_for_status()
                
                img_data = response.content
                img = Image.open(io.BytesIO(img_data))
                img = img.resize((160, 160), Image.Resampling.LANCZOS)
                ctk_img = ctk.CTkImage(light_image=img, dark_image=img, size=(160, 160))
                
                # Cache the image
                image_cache[img_url] = ctk_img
                
                # Update UI on main thread
                self.after(0, lambda: self.cover_label.configure(image=ctk_img, text=""))
                
            except Exception as e:
                logger.warning(f"Failed to load cover image: {e}")
                # Show a better fallback
                self.after(0, lambda: self.cover_label.configure(
                    image="",
                    text="🎨\n\nCover\nLoading...",
                    text_color=self.colors["text_muted"]
                ))
        
        self.executor.submit(_load)

    def start_download(self):
        """Start download with enhanced UI feedback and validation"""
        if self.downloading:
            self.log("Download already in progress", "WARNING")
            return
            
        playlist_name = self.selected_playlist.get()
        if not playlist_name:
            self.log("Please select a playlist first", "WARNING")
            self.status_label.configure(
                text="⚠️ No playlist selected",
                text_color=self.colors["warning"]
            )
            return
            
        playlist_id = self.playlists_map.get(playlist_name)
        if not playlist_id:
            self.log("Invalid playlist selection", "ERROR")
            return

        try:
            # Update UI to show loading state
            self.start_btn.configure(state="disabled", text="🔄 Preparing...")
            self.status_label.configure(
                text="🔄 Fetching track list...",
                text_color=self.colors["primary"]
            )
            
            # For large playlists, get all tracks (not just preview)
            playlist_info = self.playlists_info.get(playlist_name, {})
            if playlist_info.get('is_album', False):
                # Handle album
                tracks = get_album_tracks(self.sp, playlist_id)
            else:
                # Handle playlist
                tracks = get_playlist_tracks(self.sp, playlist_id)
            
        except Exception as e:
            self.log(f"Failed to retrieve tracks: {e}", "ERROR")
            self.status_label.configure(
                text="❌ Failed to fetch tracks",
                text_color=self.colors["error"]
            )
            self.start_btn.configure(state="normal", text="▶️ Start Download")
            return

        if not tracks:
            self.log("No tracks found in this playlist", "WARNING")
            self.status_label.configure(
                text="⚠️ Empty playlist",
                text_color=self.colors["warning"]
            )
            self.start_btn.configure(state="normal", text="▶️ Start Download")
            return

        # Clear existing queue
        total = len(tracks)
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except queue.Empty:
                break
                
        # Queue all tracks
        for idx, track in enumerate(tracks, start=1):
            self.task_queue.put(DownloadTask(idx=idx, total=total, track=track))

        # Update UI for active download
        self.downloading = True
        self.progress.set(0)
        self.progress_text.configure(text="0%")
        
        self.status_label.configure(
            text=f"🚀 Downloading {total} tracks...",
            text_color=self.colors["primary"]
        )
        
        # Update buttons
        self.start_btn.configure(
            state="disabled", 
            text="⏳ Downloading...",
            fg_color="#666666"
        )
        self.stop_btn.configure(state="normal")
        
        self.log(f"Started downloading {total} tracks from '{playlist_name.split(' (')[0]}'", "SUCCESS")

        # Start worker thread
        self.worker_thread = threading.Thread(
            target=download_worker, 
            args=(self.task_queue, self.ui_queue), 
            daemon=True
        )
        self.worker_thread.start()

    def stop_download(self):
        """Stop download with enhanced feedback"""
        if not self.downloading:
            self.log("No download in progress", "WARNING")
            return
            
        self.downloading = False
        
        # Clear queue
        while not self.task_queue.empty():
            try:
                self.task_queue.get_nowait()
                self.task_queue.task_done()
            except queue.Empty:
                break
                
        self.task_queue.put(None)
        
        # Update UI
        self.status_label.configure(
            text="⏹️ Stopping download...",
            text_color=self.colors["warning"]
        )
        
        self.start_btn.configure(
            state="normal", 
            text="▶️ Start Download",
            fg_color=self.colors["success"]
        )
        self.stop_btn.configure(state="disabled")
        
        self.log("Download stopped by user request", "WARNING")

    def process_ui_queue(self):
        """Process UI updates with enhanced feedback"""
        try:
            while True:
                msg_type, payload = self.ui_queue.get_nowait()
                
                if msg_type == "status":
                    status_text = str(payload)
                    
                    # Determine status color and icon
                    if "Error" in status_text:
                        color = self.colors["error"]
                        icon = "❌"
                    elif "Saved:" in status_text:
                        color = self.colors["success"]
                        icon = "✅"
                    elif "Idle" in status_text:
                        color = self.colors["success"]
                        icon = "🟢"
                        # Reset UI when idle
                        self.downloading = False
                        self.start_btn.configure(
                            state="normal", 
                            text="▶️ Start Download",
                            fg_color=self.colors["success"]
                        )
                        self.stop_btn.configure(state="disabled")
                    else:
                        color = self.colors["primary"]
                        icon = "🔄"
                    
                    self.status_label.configure(
                        text=f"{icon} {status_text}",
                        text_color=color
                    )
                    self.log(status_text)
                    
                elif msg_type == "progress":
                    try:
                        val = float(payload)
                        val = max(0.0, min(1.0, val))
                        self.progress.set(val)
                        
                        # Update progress text
                        percentage = int(val * 100)
                        self.progress_text.configure(text=f"{percentage}%")
                        
                        # Update window title with progress
                        if val > 0:
                            self.title(f"🎵 Spotify Downloader - {percentage}% Complete")
                        else:
                            self.title("🎵 Spotify Playlist Downloader")
                            
                    except Exception:
                        pass
                        
        except queue.Empty:
            pass
        finally:
            self.after(100, self.process_ui_queue)


if __name__ == "__main__":
    app = App()
    app.mainloop()
#!/usr/bin/env python3
"""
Spotify Downloader - Bot-Detection-Free Version
This version avoids all external web requests that could trigger bot detection
"""

import os
import logging
from typing import List, Optional, Tuple, Dict, Any
from tkinter import StringVar
import customtkinter as ctk
from dotenv import load_dotenv
from spotipy import Spotify
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

# Setup
os.environ["TK_SILENCE_DEPRECATION"] = "1"
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger("spotify_dl")

load_dotenv(dotenv_path=".env")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
REDIRECT_URL = os.getenv("REDIRECT_URL")

if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URL:
    raise SystemExit("Please set CLIENT_ID, CLIENT_SECRET, and REDIRECT_URL in the .env file")

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

def parse_spotify_url(url: str) -> Optional[Tuple[str, str]]:
    """Parse Spotify URL and return (type, id) tuple"""
    import re
    url = url.strip()
    patterns = [
        r'https?://open\.spotify\.com/(playlist|album)/([a-zA-Z0-9]+)',
        r'spotify:(playlist|album):([a-zA-Z0-9]+)',
    ]
    
    for pattern in patterns:
        match = re.match(pattern, url)
        if match and len(match.groups()) == 2:
            return match.groups()
    return None

def validate_spotify_content(sp: Spotify, content_type: str, content_id: str) -> Optional[Dict[str, Any]]:
    """Validate Spotify content without loading images"""
    try:
        if content_type == "playlist":
            data = sp.playlist(content_id, fields="name,description,tracks.total,owner.display_name")
            return {
                "type": "playlist",
                "id": content_id,
                "name": data["name"],
                "description": data.get("description", ""),
                "track_count": data["tracks"]["total"],
                "owner": data.get("owner", {}).get("display_name", "Unknown")
            }
        elif content_type == "album":
            data = sp.album(content_id, market=None)  # No market to avoid issues
            return {
                "type": "album",
                "id": content_id,
                "name": data["name"],
                "description": f"Album by {', '.join([artist['name'] for artist in data['artists']])}",
                "track_count": data["total_tracks"],
                "artist": ", ".join([artist["name"] for artist in data["artists"]]),
                "release_date": data.get("release_date", ""),
            }
    except Exception as e:
        logger.error(f"Failed to validate Spotify content: {e}")
    return None

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        
        # Large window for macOS
        self.title("🎵 Spotify Playlist Downloader - Bot-Free Version")
        self.geometry("1200x1000")
        self.minsize(1000, 800)
        
        # Center window
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f"{width}x{height}+{x}+{y}")
        
        # Dark theme
        ctk.set_appearance_mode("dark")
        
        # Colors
        self.colors = {
            "primary": "#8B5CF6",
            "secondary": "#06B6D4", 
            "accent": "#F59E0B",
            "surface": "#1F2937",
            "glass": "#2D1B69",
            "glass_border": "#4C1D95",
            "success": "#10B981",
            "error": "#EF4444",
            "warning": "#F59E0B",
            "text_primary": "#F9FAFB",
            "text_secondary": "#D1D5DB",
            "text_muted": "#9CA3AF",
            "background": "#0F0F23"
        }
        
        self.configure(fg_color=self.colors["background"])
        
        # Initialize Spotify
        try:
            self.sp = create_spotify_client()
            logger.info("✅ Spotify client created successfully")
        except Exception as e:
            logger.error(f"❌ Failed to create Spotify client: {e}")
            self.sp = None
        
        # Data
        self.playlists_map = {}
        self.playlists_info = {}
        self.selected_playlist = StringVar()
        
        # Create UI
        self.create_ui()
        
        # Load playlists if Spotify is available
        if self.sp:
            self.load_playlists()
    
    def create_ui(self):
        # Header
        header = ctk.CTkFrame(self, height=100, corner_radius=0, fg_color=self.colors["primary"])
        header.pack(fill="x", padx=0, pady=0)
        header.pack_propagate(False)
        
        title_container = ctk.CTkFrame(header, fg_color="transparent")
        title_container.pack(expand=True, fill="both")
        
        title = ctk.CTkLabel(title_container, text="🎵 Spotify Playlist Downloader", 
                           font=ctk.CTkFont(size=32, weight="bold"),
                           text_color=self.colors["text_primary"])
        title.pack(pady=(25, 5))
        
        subtitle = ctk.CTkLabel(title_container, text="✨ Bot-Detection-Free Version ✨", 
                              font=ctk.CTkFont(size=16, weight="normal"),
                              text_color=self.colors["text_secondary"])
        subtitle.pack(pady=(0, 10))
        
        # Main scrollable content
        self.main_frame = ctk.CTkScrollableFrame(self, corner_radius=25, fg_color=self.colors["surface"],
                                               border_width=2, border_color=self.colors["glass_border"])
        self.main_frame.pack(padx=30, pady=(0, 30), fill="both", expand=True)
        
        # Content container
        self.content_frame = ctk.CTkFrame(self.main_frame, corner_radius=15, fg_color="transparent")
        self.content_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Create sections
        self.create_url_section()
        self.create_playlist_section()
        self.create_preview_section()
        self.create_download_section()  # THE IMPORTANT PART
        self.create_log_section()
        
        print("✅ UI Created - Download section included")
    
    def create_url_section(self):
        url_card = ctk.CTkFrame(self.content_frame, corner_radius=20, fg_color=self.colors["glass"],
                              border_width=2, border_color=self.colors["glass_border"])
        url_card.pack(fill="x", padx=25, pady=(25, 20))
        
        # Title
        title_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        title_label = ctk.CTkLabel(title_frame, text="🔗 Paste Spotify Link", 
                                 font=ctk.CTkFont(size=20, weight="bold"),
                                 text_color=self.colors["text_primary"])
        title_label.pack(side="left")
        
        # Input
        input_frame = ctk.CTkFrame(url_card, fg_color="transparent")
        input_frame.pack(fill="x", padx=25, pady=(0, 20))
        
        self.url_entry = ctk.CTkEntry(input_frame, placeholder_text="Paste Spotify URL here...",
                                    width=600, height=45, corner_radius=15,
                                    border_width=2, border_color=self.colors["secondary"],
                                    fg_color=self.colors["surface"], font=ctk.CTkFont(size=14))
        self.url_entry.pack(side="left", padx=(0, 15))
        
        self.load_url_btn = ctk.CTkButton(input_frame, text="📥 Load from URL", width=150, height=45,
                                        corner_radius=15, fg_color=self.colors["accent"],
                                        hover_color="#FBBF24", font=ctk.CTkFont(size=15, weight="bold"),
                                        command=self.load_from_url)
        self.load_url_btn.pack(side="left")
        
        paste_btn = ctk.CTkButton(input_frame, text="📋", width=45, height=45, corner_radius=15,
                                fg_color=self.colors["surface"], hover_color=self.colors["glass"],
                                font=ctk.CTkFont(size=16), command=self.paste_from_clipboard)
        paste_btn.pack(side="left", padx=(10, 0))
    
    def create_playlist_section(self):
        playlist_card = ctk.CTkFrame(self.content_frame, corner_radius=20, fg_color=self.colors["glass"],
                                   border_width=2, border_color=self.colors["glass_border"])
        playlist_card.pack(fill="x", padx=25, pady=(0, 20))
        
        # Title
        title_frame = ctk.CTkFrame(playlist_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        title_label = ctk.CTkLabel(title_frame, text="🎧 Select Your Playlist", 
                                 font=ctk.CTkFont(size=20, weight="bold"),
                                 text_color=self.colors["text_primary"])
        title_label.pack(side="left")
        
        # Selection
        selection_frame = ctk.CTkFrame(playlist_card, fg_color="transparent")
        selection_frame.pack(fill="x", padx=25, pady=(0, 20))
        
        self.playlist_dropdown = ctk.CTkComboBox(selection_frame, variable=self.selected_playlist,
                                               width=600, height=45, corner_radius=15,
                                               border_width=2, border_color=self.colors["primary"],
                                               fg_color=self.colors["surface"], 
                                               button_color=self.colors["primary"],
                                               button_hover_color="#A78BFA",
                                               dropdown_fg_color=self.colors["surface"],
                                               font=ctk.CTkFont(size=15, weight="normal"),
                                               command=self.update_preview)
        self.playlist_dropdown.pack(side="left", padx=(0, 20))
        
        self.refresh_btn = ctk.CTkButton(selection_frame, text="🔄 Refresh", width=140, height=45,
                                       corner_radius=15, fg_color=self.colors["secondary"],
                                       hover_color="#67E8F9", font=ctk.CTkFont(size=15, weight="bold"),
                                       command=self.load_playlists)
        self.refresh_btn.pack(side="left")
    
    def create_preview_section(self):
        preview_card = ctk.CTkFrame(self.content_frame, corner_radius=20, fg_color=self.colors["glass"],
                                  border_width=2, border_color=self.colors["glass_border"])
        preview_card.pack(fill="x", padx=25, pady=(0, 20))
        
        # Title
        title_frame = ctk.CTkFrame(preview_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        preview_title = ctk.CTkLabel(title_frame, text="👁️ Content Preview", 
                                   font=ctk.CTkFont(size=20, weight="bold"),
                                   text_color=self.colors["text_primary"])
        preview_title.pack(side="left")
        
        # Preview content
        self.preview_box = ctk.CTkTextbox(preview_card, corner_radius=15, border_width=1,
                                        border_color=self.colors["glass_border"], 
                                        fg_color=self.colors["surface"],
                                        font=ctk.CTkFont(size=13), wrap="word", height=150)
        self.preview_box.pack(fill="x", padx=25, pady=(0, 20))
        self.preview_box.configure(state="disabled")
        
        # Set initial text
        self.preview_box.configure(state="normal")
        self.preview_box.insert("0.0", "🎵 No content selected\n\nSelect a playlist from the dropdown above or paste a Spotify URL to see preview information.")
        self.preview_box.configure(state="disabled")
    
    def create_download_section(self):
        """THE MOST IMPORTANT SECTION - Download Controls"""
        print("🎛️ Creating Download Control Section...")
        
        # Make this section extra visible with bright border
        download_card = ctk.CTkFrame(self.content_frame, corner_radius=20, fg_color=self.colors["glass"],
                                   border_width=4, border_color=self.colors["accent"])  # Thick bright border
        download_card.pack(fill="x", padx=25, pady=(0, 20))
        
        # Big obvious title
        title_frame = ctk.CTkFrame(download_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(25, 20))
        
        download_title = ctk.CTkLabel(title_frame, text="🎛️ DOWNLOAD CONTROL CENTER", 
                                    font=ctk.CTkFont(size=24, weight="bold"),
                                    text_color=self.colors["accent"])  # Bright orange
        download_title.pack(side="left")
        
        # Arrow pointing to buttons
        arrow = ctk.CTkLabel(title_frame, text="👇 BUTTONS BELOW 👇", 
                           font=ctk.CTkFont(size=14, weight="bold"),
                           text_color=self.colors["accent"])
        arrow.pack(side="right")
        
        # Button container
        button_frame = ctk.CTkFrame(download_card, fg_color="transparent")
        button_frame.pack(fill="x", padx=25, pady=(0, 25))
        
        # HUGE download button
        self.download_btn = ctk.CTkButton(button_frame, text="▶️ START DOWNLOAD", 
                                        width=280, height=70, corner_radius=20,
                                        fg_color=self.colors["success"], hover_color="#059669",
                                        font=ctk.CTkFont(size=22, weight="bold"),
                                        command=self.start_download)
        self.download_btn.pack(side="left", padx=(0, 25))
        
        # Stop button
        self.stop_btn = ctk.CTkButton(button_frame, text="⏹️ STOP", 
                                    width=150, height=70, corner_radius=20,
                                    fg_color="#DC2626", hover_color="#B91C1C",
                                    font=ctk.CTkFont(size=22, weight="bold"),
                                    state="disabled", command=self.stop_download)
        self.stop_btn.pack(side="left")
        
        # Status display
        self.status_frame = ctk.CTkFrame(button_frame, corner_radius=15, fg_color=self.colors["surface"],
                                       border_width=2, border_color=self.colors["success"])
        self.status_frame.pack(side="right", padx=(25, 0), fill="both", expand=True)
        
        self.status_label = ctk.CTkLabel(self.status_frame, text="🟢 Ready to Download!", 
                                       font=ctk.CTkFont(size=18, weight="bold"),
                                       text_color=self.colors["success"])
        self.status_label.pack(pady=20)
        
        print("✅ Download Control Section Created!")
        print(f"▶️ Download button: {self.download_btn}")
        print(f"⏹️ Stop button: {self.stop_btn}")
    
    def create_log_section(self):
        log_card = ctk.CTkFrame(self.content_frame, corner_radius=20, fg_color=self.colors["glass"],
                              border_width=2, border_color=self.colors["glass_border"])
        log_card.pack(fill="x", padx=25, pady=(0, 25))
        
        # Title
        title_frame = ctk.CTkFrame(log_card, fg_color="transparent")
        title_frame.pack(fill="x", padx=25, pady=(20, 15))
        
        log_title = ctk.CTkLabel(title_frame, text="📝 Activity Log", 
                               font=ctk.CTkFont(size=20, weight="bold"),
                               text_color=self.colors["text_primary"])
        log_title.pack(side="left")
        
        # Log box
        self.log_box = ctk.CTkTextbox(log_card, corner_radius=15, border_width=1,
                                    border_color=self.colors["glass_border"], 
                                    fg_color=self.colors["background"],
                                    font=ctk.CTkFont(size=12, family="Monaco"), 
                                    wrap="word", height=120)
        self.log_box.pack(fill="x", padx=25, pady=(0, 20))
        self.log_box.configure(state="disabled")
        
        # Add initial log
        self.log("Application started successfully", "SUCCESS")
        self.log("Download buttons are visible and ready", "INFO")
    
    def log(self, msg: str, level: str = "INFO"):
        """Add message to log"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        if level == "ERROR":
            prefix = "❌"
        elif level == "SUCCESS":
            prefix = "✅"
        elif level == "WARNING":
            prefix = "⚠️"
        else:
            prefix = "ℹ️"
        
        formatted_msg = f"[{timestamp}] {prefix} {msg}"
        
        self.log_box.configure(state="normal")
        self.log_box.insert("end", formatted_msg + "\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")
        
        logger.info(msg)
    
    def load_playlists(self):
        """Load user playlists without images"""
        if not self.sp:
            self.log("Spotify client not available", "ERROR")
            return
        
        try:
            self.log("Loading playlists...", "INFO")
            self.status_label.configure(text="🔄 Loading playlists...")
            
            # Get playlists without images
            results = self.sp.current_user_playlists(limit=50)
            playlists = []
            
            while results:
                for item in results['items']:
                    name = item.get('name', '(no name)')
                    pid = item.get('id')
                    track_count = item.get('tracks', {}).get('total', 0)
                    
                    if pid:
                        display_name = f"{name} ({track_count} tracks)"
                        playlists.append(display_name)
                        self.playlists_map[display_name] = pid
                        self.playlists_info[display_name] = {
                            'original_name': name,
                            'playlist_id': pid,
                            'track_count': track_count,
                            'type': 'playlist'
                        }
                
                results = self.sp.next(results) if results['next'] else None
            
            # Update dropdown
            self.playlist_dropdown.configure(values=playlists)
            if playlists:
                self.selected_playlist.set(playlists[0])
                self.update_preview(playlists[0])
            
            self.log(f"Loaded {len(playlists)} playlists successfully", "SUCCESS")
            self.status_label.configure(text="🟢 Ready to Download!", text_color=self.colors["success"])
            
        except Exception as e:
            self.log(f"Failed to load playlists: {e}", "ERROR")
            self.status_label.configure(text="❌ Failed to load playlists", text_color=self.colors["error"])
    
    def paste_from_clipboard(self):
        """Paste URL from clipboard"""
        try:
            clipboard_content = self.clipboard_get()
            if clipboard_content:
                self.url_entry.delete(0, 'end')
                self.url_entry.insert(0, clipboard_content.strip())
                self.log("Pasted URL from clipboard", "SUCCESS")
        except Exception as e:
            self.log(f"Failed to paste from clipboard: {e}", "WARNING")
    
    def load_from_url(self):
        """Load content from URL"""
        url = self.url_entry.get().strip()
        if not url:
            self.log("Please enter a Spotify URL", "WARNING")
            return
        
        if not self.sp:
            self.log("Spotify client not available", "ERROR")
            return
        
        try:
            self.log(f"Processing URL: {url}", "INFO")
            
            # Parse URL
            parsed = parse_spotify_url(url)
            if not parsed:
                self.log("Invalid Spotify URL format", "ERROR")
                return
            
            content_type, content_id = parsed
            self.log(f"Detected {content_type}: {content_id}", "INFO")
            
            # Validate content
            content_info = validate_spotify_content(self.sp, content_type, content_id)
            if not content_info:
                self.log("Could not access this Spotify content", "ERROR")
                return
            
            # Add to dropdown
            content_name = content_info["name"]
            track_count = content_info["track_count"]
            
            if content_type == "playlist":
                display_name = f"🔗 {content_name} ({track_count} tracks)"
            else:  # album
                artist = content_info.get("artist", "Unknown Artist")
                display_name = f"💿 {content_name} by {artist} ({track_count} tracks)"
            
            # Store info
            self.playlists_map[display_name] = content_info["id"]
            self.playlists_info[display_name] = {
                'original_name': content_name,
                'playlist_id': content_info["id"],
                'track_count': track_count,
                'type': content_type,
                'from_url': True
            }
            if content_type == "album":
                self.playlists_info[display_name]['artist'] = content_info.get("artist", "")
            
            # Update dropdown
            current_values = list(self.playlist_dropdown.cget("values"))
            if display_name not in current_values:
                current_values.insert(0, display_name)
                self.playlist_dropdown.configure(values=current_values)
            
            self.selected_playlist.set(display_name)
            self.update_preview(display_name)
            
            self.log(f"Successfully loaded {content_type}: {content_name}", "SUCCESS")
            self.url_entry.delete(0, 'end')
            
        except Exception as e:
            self.log(f"Error loading URL: {e}", "ERROR")
    
    def update_preview(self, selection: str):
        """Update preview without loading images"""
        if not selection or selection not in self.playlists_info:
            return
        
        info = self.playlists_info[selection]
        content_type = info.get('type', 'playlist')
        name = info.get('original_name', 'Unknown')
        track_count = info.get('track_count', 0)
        
        self.preview_box.configure(state="normal")
        self.preview_box.delete("1.0", "end")
        
        if content_type == "album":
            icon = "💿"
            artist = info.get('artist', 'Unknown Artist')
            self.preview_box.insert("end", f"{icon} {name}\n")
            self.preview_box.insert("end", f"🎤 Artist: {artist}\n")
        else:
            icon = "📋"
            self.preview_box.insert("end", f"{icon} {name}\n")
        
        self.preview_box.insert("end", f"🎵 {track_count} tracks\n")
        self.preview_box.insert("end", f"📊 Type: {content_type.title()}\n")
        
        if info.get('from_url'):
            self.preview_box.insert("end", f"🔗 Loaded from URL\n")
        
        self.preview_box.insert("end", f"\n✅ Ready to download!")
        self.preview_box.configure(state="disabled")
        
        self.log(f"Preview updated for {content_type}: {name}", "INFO")
    
    def start_download(self):
        """Start download process"""
        selection = self.selected_playlist.get()
        if not selection:
            self.log("Please select a playlist or album first", "WARNING")
            self.status_label.configure(text="⚠️ No content selected", text_color=self.colors["warning"])
            return
        
        info = self.playlists_info.get(selection)
        if not info:
            self.log("Invalid selection", "ERROR")
            return
        
        name = info.get('original_name', 'Unknown')
        track_count = info.get('track_count', 0)
        content_type = info.get('type', 'playlist')
        
        # Update UI
        self.download_btn.configure(state="disabled", text="🔄 Starting...", fg_color="#666666")
        self.stop_btn.configure(state="normal")
        self.status_label.configure(text=f"🚀 Starting download of {track_count} tracks...", 
                                  text_color=self.colors["primary"])
        
        self.log(f"Starting download of {content_type}: {name} ({track_count} tracks)", "SUCCESS")
        self.log("🎉 DOWNLOAD BUTTON IS WORKING!", "SUCCESS")
        self.log("This version avoids bot detection - ready for full implementation", "INFO")
        
        # For now, just simulate success
        self.after(2000, self.simulate_download_complete)
    
    def simulate_download_complete(self):
        """Simulate download completion"""
        self.download_btn.configure(state="normal", text="▶️ START DOWNLOAD", fg_color=self.colors["success"])
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="🟢 Ready to Download!", text_color=self.colors["success"])
        self.log("Download simulation complete - UI working perfectly!", "SUCCESS")
    
    def stop_download(self):
        """Stop download"""
        self.download_btn.configure(state="normal", text="▶️ START DOWNLOAD", fg_color=self.colors["success"])
        self.stop_btn.configure(state="disabled")
        self.status_label.configure(text="⏹️ Download stopped", text_color=self.colors["warning"])
        self.log("Download stopped by user", "WARNING")

if __name__ == "__main__":
    print("🚀 Starting Bot-Detection-Free Spotify Downloader...")
    print("✅ This version avoids all external requests that trigger bot detection")
    print("🎛️ Look for the bright 'DOWNLOAD CONTROL CENTER' section")
    
    app = App()
    app.mainloop()
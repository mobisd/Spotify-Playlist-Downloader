## If you experience an Issue or have a Idea on how to make it better please contact me here or on Discord "mobisd".

# Spotify Playlist Downloader - Professional Edition

A sophisticated, high-performance Spotify playlist and album downloader featuring a **stunning modern UI**, **enterprise-grade performance**, and **direct URL support**. Download any Spotify content with professional quality and lightning-fast speed.


### Direct URL Support
- **Paste any Spotify URL** for instant downloads
- **Support for playlists AND albums**
- **Multiple URL formats**: open.spotify.com, spotify: URIs, short links
- **One-click paste** from clipboard
- **Smart content detection** with visual indicators

### Advanced Features
- **Metadata embedding** with lyrics integration
- **High-quality audio** downloads via yt-dlp
- **Progress tracking** with real-time status updates
- **Error handling** with graceful recovery
- **Batch processing** for efficient downloads

## Quick Start

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/Spotify-Playlist-Downloader.git
   cd Spotify-Playlist-Downloader
   ```

2. **Setup Python environment**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Setup Spotify credentials** (create `.env` file)
   ```env
   CLIENT_ID=your_spotify_client_id
   CLIENT_SECRET=your_spotify_client_secret
   REDIRECT_URL=http://localhost:8888/callback
   ```

5. **Run the application**
   ```bash
   python dl.py
   ```

6. **Start downloading!**
   - Select playlists from dropdown OR
   - Paste any Spotify URL for instant download

### Python Dependencies
```txt
customtkinter==5.1.0      # Modern UI framework
requests==2.32.2          # HTTP requests
spotipy==2.22.1           # Spotify API client
yt-dlp==2024.7.9          # YouTube downloader
mutagen==1.45.1           # Audio metadata
beautifulsoup4==4.9.3     # HTML parsing for lyrics
python-dotenv==0.19.1     # Environment variables
pygame==2.1.0             # Audio playback
Pillow==9.5.0             # Image processing
```

### Prerequisites
- **Python 3.8+** - Download from [python.org](https://www.python.org/)
- **FFmpeg** - Required for audio processing
- **Spotify Developer Account** - For API access

### FFmpeg Installation

#### Windows
```bash
# Download from https://ffmpeg.org/download.html
# Extract and add to PATH environment variable
# Verify with: ffmpeg -version
```

#### macOS
```bash
brew install ffmpeg
```

#### Linux (Ubuntu/Debian)
```bash
sudo apt update
sudo apt install ffmpeg
```

### Python Environment Setup

1. **Create virtual environment**
   ```bash
   python -m venv venv
   ```

2. **Activate environment**
   ```bash
   # Windows
   venv\Scripts\activate
   
   # macOS/Linux
   source venv/bin/activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

### Spotify API Configuration

1. **Create Spotify App**
   - Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/)
   - Click "Create App"
   - Name: "Playlist Downloader"
   - Description: "Personal playlist downloader"
   - Redirect URI: `http://localhost:8888/callback`

2. **Get Credentials**
   - Copy `Client ID` and `Client Secret`
   - Create `.env` file in project directory

3. **Configure .env file**
   ```env
   CLIENT_ID=your_client_id_here
   CLIENT_SECRET=your_client_secret_here
   REDIRECT_URL=http://localhost:8888/callback
   ```

### Supported Formats
- **Playlists**: `https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M`
- **Albums**: `https://open.spotify.com/album/4yP0hdKOZPNshxUOjY0cZj`
- **Spotify URIs**: `spotify:playlist:37i9dQZF1DXcBWIGoYBM5M`
- **Short Links**: `https://spotify.link/abc123`

### How to Use
1. **Copy any Spotify URL** from the app or web player
2. **Paste in the URL input field** or click the paste button (📋)
3. **Click "Load from URL"** - content loads instantly
4. **Preview and download** - same beautiful interface

## Usage Guide

### Method 1: Browse Your Playlists
1. **Launch the application** - Beautiful interface loads with your playlists
2. **Select from dropdown** - All your playlists appear instantly (cached)
3. **Preview content** - See cover art, track count, and metadata
4. **Click download** - Professional progress tracking begins

### Method 2: Direct URL Download
1. **Copy Spotify URL** - From any playlist or album
2. **Paste in URL field** - Large input field with paste button
3. **Auto-detection** - System identifies content type automatically
4. **Instant preview** - See what you're downloading before starting
5. **One-click download** - Same powerful download engine

### User Interface Elements

#### **Control Panel**
- **Playlist dropdown** - Instant loading with search capability
- **URL input section** - Large field with clipboard integration
- **Download controls** - Start, stop, and progress management
- **Status indicators** - Real-time feedback and error messages

#### **Preview Section**
- **Cover art display** - High-quality album artwork
- **Metadata panel** - Artist, track count, release info
- **Content type badges** - Visual distinction between playlists/albums
- **Track listing** - Expandable for large collections

## Troubleshooting

### Common Issues

#### **Authentication Problems**
```
Error: "Invalid client credentials"
```
**Solution**: 
- Verify `.env` file exists in project directory
- Check `CLIENT_ID` and `CLIENT_SECRET` are correct
- Ensure no extra spaces in credentials
- Confirm redirect URI matches Spotify app settings

#### **FFmpeg Not Found**
```
Error: "ffmpeg not found in PATH"
```
**Solution**:
- Install FFmpeg following setup instructions above
- Restart terminal after installation
- Verify with `ffmpeg -version` command
- Check PATH environment variable includes FFmpeg

#### **Slow Performance**
```
Issue: "Playlists loading slowly"
```
**Solution**:
- Clear application cache (restart app)
- Check internet connection stability
- Reduce concurrent downloads in settings
- Enable lazy loading for large playlists

#### **Download Failures**
```
Error: "Failed to download track"
```
**Solution**:
- Check track availability in your region
- Verify YouTube access is not blocked
- Try different audio quality settings
- Check available disk space

### Performance Tips

#### **Speed Optimization**
- **Enable caching** - Keeps playlists loaded for instant access
- **Use URL input** - Fastest method for specific content
- **Limit preview tracks** - Reduces initial loading time
- **Close other apps** - Free up system resources

#### **Memory Management**
- **Restart periodically** - Clears accumulated cache
- **Monitor disk space** - Ensure adequate storage
- **Adjust thread count** - Balance speed vs. system load
- **Use selective downloads** - Download only needed tracks

### Advanced Troubleshooting

#### **Debug Mode**
Enable detailed logging for issue diagnosis:
```python
# Add to dl.py for debugging
import logging
logging.basicConfig(level=logging.DEBUG)
```

#### **Network Issues**
- **Check firewall settings** - Ensure Spotify/YouTube access
- **Test with VPN** - Rule out regional restrictions
- **Verify DNS settings** - Use public DNS if needed
- **Monitor bandwidth** - Ensure sufficient connection speed

#### **Configuration Reset**
If issues persist, reset configuration:
1. Delete cache folder (if exists)
2. Remove `.env` file and recreate
3. Reinstall dependencies: `pip install -r requirements.txt --force-reinstall`
4. Restart application

## Support

### Getting Help
- **Issues**: Create GitHub issue with error details
- **Discord**: Contact "mobisd" for direct support
- **Documentation**: Check `URL_FEATURE.md` for feature details
- **Community**: Join discussions in repository

### Bug Reports
Include when reporting issues:
- **Operating system** and version
- **Python version** (`python --version`)
- **Error message** (full traceback)
- **Steps to reproduce** the problem
- **Expected vs actual behavior**

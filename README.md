## If you experience an Issue or have a Idea on how to make it better please contact me here or on Discord "mobisd".

# Spotify Playlist Downloader with Lyrics Embedding

This tutorial will guide you through setting up and using the Spotify Playlist Downloader, a Python script that downloads songs from Spotify playlists, embeds metadata and lyrics into the downloaded MP3 files, and saves them in a designated folder. The script leverages the Spotify API and scrapes lyrics from AZLyrics.

## Table of Contents
- Requirements
- Setting Up the Environment
- Script Overview
- Running the Script
- GitHub Repository Setup
- Common Issues and Troubleshooting

## Requirements
To run this script, you need to have the following installed on your system:

- Python 3.8 or higher
- pip (Python package installer)
- A Spotify Developer account

### Python Packages
The script requires several Python packages, which can be installed via pip. The required packages are listed in the `requirements.txt` file.

**requirements.txt:**
```
customtkinter==5.1.0
requests==2.32.2
spotipy==2.22.1
yt-dlp==2024.7.9
mutagen==1.45.1
beautifulsoup4==4.9.3
python-dotenv==0.19.1
pygame==2.1.0
```

### Text Editors
You can use any text editor or IDE for editing Python scripts. Some popular options include:
- Visual Studio Code
- PyCharm
- Sublime Text
- Atom
- Jupyter Notebook

## Setting Up the Environment

### Install Python and pip:
1. Download and install Python from the [official Python website](https://www.python.org/).
2. Ensure pip is installed by running `python -m ensurepip --upgrade` in your terminal or command prompt.

### Install FFmpeg
# FFmpeg is a required dependency for the downloader to function properly. Follow the steps below to install FFmpeg on your system.

## Windows
- Download: Go to the FFmpeg download page and download the latest release.
- Extract: Extract the downloaded zip file to a directory of your choice.

## Add to Path:

- Open the Start Menu and search for "Environment Variables".
- Click on "Edit the system environment variables".
- In the System Properties window, click on the "Environment Variables" button.
- In the Environment Variables window, find the Path variable in the "System variables" section, and click "Edit".
- Click "New" and add the path to the bin directory of the extracted FFmpeg folder (e.g., C:\ffmpeg\bin).
- Click "OK" to close all windows.

## Verify Installation:

- Open Command Prompt and type ffmpeg -version.
- You should see the version information of FFmpeg if it's installed correctly.

### Clone or download the script:
1. Clone the repository or download the script files to your local machine.

### Create a virtual environment:
1. Navigate to the directory where you downloaded the script.
2. Create a virtual environment by running `python -m venv venv`.

### Activate the virtual environment:
- On Windows: `venv\Scripts\activate`
- On macOS and Linux: `source venv/bin/activate`

### Install the required Python packages:
1. Run `pip install -r requirements.txt` to install the necessary packages.

### Set up the `.env` file:
1. Create a file named `.env` in the same directory as the script.
2. Add your Spotify API credentials to the `.env` file in the following format:
```
CLIENT_ID=your_spotify_client_id
CLIENT_SECRET=your_spotify_client_secret
REDIRECT_URL= [Example: http://localhost:8888/callback]
```


## Spotify Developer Account Setup:
1. Go to the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard/).
2. Log in and create a new application to get your `CLIENT_ID` and `CLIENT_SECRET`.
3. Set the `REDIRECT_URL` in the app settings to `http://localhost:8888/callback`.

## Script Overview
The script downloads songs from Spotify playlists, embeds metadata and lyrics into the MP3 files, and saves them in a folder named after the playlist. Here's an overview of the key components:

- **Environment Variables**: The script uses environment variables stored in a `.env` file to manage API credentials securely.
- **Spotify Authentication**: The script authenticates with the Spotify API using OAuth.
- **Fetching Playlist Tracks**: The script retrieves the tracks from the specified Spotify playlist.
- **Downloading Songs**: The script searches for the songs on YouTube and downloads the best audio quality available using `yt-dlp`.
- **Embedding Metadata and Lyrics**: The script embeds song metadata and lyrics into the downloaded MP3 files using the `mutagen` library.
- **User Interface**: The script provides a simple GUI using `customtkinter`.

## Running the Script

### Start the Script:
1. Activate your virtual environment if it's not already active.
2. Run the script by executing `python dl.py` in your terminal or command prompt.

### Using the GUI:
1. The GUI window will open.
2. Select the playlist you want to download from the dropdown menu. Note that it may take some time to load the playlist, depending on the number of songs.
3. Click the "Download" button to start downloading the playlist.
4. The status and progress of the download will be displayed in the GUI.
5. To stop the download, click the "Stop Downloading" button. Note that you need to restart the script to download another playlist.

### Restarting the Script:
After downloading a playlist, you need to restart the script to download another playlist due to token handling and session management.

## GitHub Repository Setup
To set up a GitHub repository for your project, follow these steps:

### Create a GitHub Repository:
1. Go to [GitHub](https://github.com/) and log in.
2. Click on the "New" button to create a new repository.
3. Fill in the repository name, description, and other details. Click "Create repository".

### Initialize the Local Repository:
1. Navigate to your project directory in the terminal.
2. Initialize a new Git repository: `git init`.
3. Add all files to the repository: `git add .`.
4. Commit the files: `git commit -m "Initial commit"`.

### Add Remote Repository:
1. Add the remote repository: `git remote add origin https://github.com/yourusername/your-repository.git`.

### Push to GitHub:
1. Push the local repository to GitHub: `git push -u origin master`.

## Common Issues and Troubleshooting

### Environment Variables Not Set:

### Error 403: Forbidden
- This Error appears sometimes but **dont** Panic it will still download the Song.

- Ensure the `.env` file is correctly named and located in the same directory as the script.
- Verify that all required environment variables are set in the `.env` file.

### Package Installation Issues:
- Ensure your virtual environment is activated.
- Run `pip install -r requirements.txt` to install all required packages.

### Spotify Authentication Issues:
- Ensure your Spotify API credentials are correct.
- Verify the `REDIRECT_URL` is correctly set in both the Spotify Developer Dashboard and the `.env` file.

### Downloading and Embedding Issues:
- Ensure `yt-dlp` is installed and working correctly.
- Verify that the downloaded MP3 files exist and are not corrupted.


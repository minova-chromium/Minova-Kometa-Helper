# Kometa Helper

Kometa Helper is a Windows desktop control panel for Plex + Kometa users who want the power of Kometa without living in YAML files or the Kometa dashboard every day.

It is designed for a local, no-Docker Kometa setup on Windows.

## What It Does

- Installs or updates a local Kometa copy.
- Stores app data in `Documents\Kometa-Helper\runtime`.
- Connects to Plex using a Plex URL and token.
- Saves movie/show library folders for Plex refreshes.
- Lets users browse for movie/show folders with a Windows folder picker.
- Runs all-poster refreshes without opening the Kometa dashboard.
- Creates Plex collections from public IMDb list IDs.
- Hides created collection tiles from the normal Plex library grid.
- Lets users update/delete saved app-created collections.
- Provides collection poster tools with logo/poster search.
- Provides global overlay setup for Kometa-style movie/show poster overlays.
- Opens as a desktop app with remembered tabs.

## Important Privacy Note

Do not commit runtime data from your own PC.

The app can store Plex tokens, saved collection IDs, logs, generated posters, and local library paths. The `.gitignore` in this folder excludes those files and folders.

## Requirements

- Windows 10 or Windows 11
- Python 3.11 or newer
- Plex Media Server
- A Plex token
- A TMDb API key
- Internet access for installing/updating Kometa and looking up posters/logos

The current app assumes the default local paths:

- Kometa: `Documents\Kometa`
- Kometa Quickstart config: `Documents\Kometa-Quickstart\config\jolly_goodall_config.yml`
- Helper runtime data: `Documents\Kometa-Helper\runtime`

## Quick Start For Users

1. Download the latest release zip.
2. Extract it somewhere permanent, such as `C:\Kometa Helper`.
3. Run `Kometa Helper.exe`.
4. Open the `Setup` tab.
5. Install/update Kometa if needed.
6. Save Plex URL/token.
7. Save TMDb API key.
8. Choose Plex libraries.
9. Add movie/show folder locations by pressing the Browse buttons or typing one folder per line.
10. Use `Collections` and `Add IMDb` for day-to-day work.

## Run From Source

Install dependencies:

```powershell
python -m pip install -r requirements.txt
```

Start the app:

```powershell
python .\imdb_collection_ui.py
```

Or double-click:

```text
Start-Kometa-Helper.bat
```

## Build The Windows App

Double-click:

```text
Build-Kometa-Helper-App.bat
```

The packaged app will be created at:

```text
dist\Kometa Helper\Kometa Helper.exe
```

## Documentation

- [User Manual](docs/USER_MANUAL.md)
- [GitHub Upload Guide](docs/GITHUB_UPLOAD.md)
- [Developer Notes](docs/DEVELOPER_NOTES.md)

## Disclaimer

This is an unofficial helper app. Kometa, Plex, IMDb, and TMDb are separate projects/services with their own terms and APIs.

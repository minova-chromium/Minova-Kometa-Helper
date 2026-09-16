# Developer Notes

## Project Shape

This is currently a single-file Python desktop app with helper scripts.

Main files:

- `imdb_collection_ui.py`: app server, UI rendering, Plex/Kometa workflows
- `refresh-plex-movie-show-libraries.ps1`: asks Plex to scan saved movie/show folder paths
- `Run-Kometa-Helper-Refresh-All-Posters.bat`: scheduled refresh runner
- `Start-Kometa-Helper.bat`: source runner
- `Build-Kometa-Helper-App.bat`: PyInstaller build runner

## Runtime Data

Runtime data is intentionally outside the repository:

```text
%USERPROFILE%\Documents\Kometa-Helper\runtime
```

Do not commit runtime files. They can contain personal paths, logs, tokens, and generated artwork.

## Build

Use:

```powershell
.\Build-Kometa-Helper-App.bat
```

The Windows app is built with:

- PyInstaller
- pywebview
- pythonnet/clr_loader for the Windows desktop webview runtime

## Source Run

Use:

```powershell
python .\imdb_collection_ui.py
```

The app opens a desktop window by default. Use this to force browser mode:

```powershell
python .\imdb_collection_ui.py --browser
```

Use this for a quick startup/render check:

```powershell
python .\imdb_collection_ui.py --self-test
```

## Current Windows Assumptions

The app is Windows-first and assumes these local defaults:

- Kometa: `%USERPROFILE%\Documents\Kometa`
- Kometa Python venv: `%USERPROFILE%\Documents\Kometa\.venv`
- Kometa Quickstart config: `%USERPROFILE%\Documents\Kometa-Quickstart\config\jolly_goodall_config.yml`
- Runtime app data: `%USERPROFILE%\Documents\Kometa-Helper\runtime`

Future work could add a first-run installer/settings screen to choose these paths.

## Release Checklist

1. Run source self-test.
2. Build with `Build-Kometa-Helper-App.bat`.
3. Run packaged `Kometa Helper.exe --self-test`.
4. Open the app normally and verify tabs.
5. Confirm no runtime data exists in the repository.
6. Zip `dist\Kometa Helper`.
7. Upload the zip to GitHub Releases.

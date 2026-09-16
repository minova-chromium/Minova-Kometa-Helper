# GitHub Upload Guide

This folder is prepared so it can be uploaded as a GitHub repository.

## Before Uploading

Make sure these private files are not included:

- `runtime/`
- `dist/`
- `build/`
- `Documents\Kometa-Helper\runtime`
- Plex tokens
- TMDb keys
- personal logs
- generated posters/logos
- `.zip` release files

The included `.gitignore` already excludes the common private/generated files.

## Create A New GitHub Repository

1. Go to GitHub.
2. Press `New repository`.
3. Name it something like:

```text
kometa-helper
```

4. Choose public or private.
5. Do not add a README on GitHub if you are uploading this folder, because this folder already has one.
6. Create the repository.

## Upload From GitHub Website

This is easiest for non-developers.

1. Open the new GitHub repository.
2. Press `Add file`.
3. Press `Upload files`.
4. Drag the contents of this folder into GitHub.
5. Commit the upload.

Important: upload the contents of the folder, not your private runtime/build folders.

## Upload With Git Commands

Open PowerShell inside this folder:

```powershell
cd "PATH\TO\Kometa-Helper-GitHub-Ready"
git init
git add .
git commit -m "Initial Kometa Helper release"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/kometa-helper.git
git push -u origin main
```

Replace `YOUR-USERNAME` and repository name with your GitHub details.

## Create A Release Zip

After building the app with `Build-Kometa-Helper-App.bat`, zip this folder:

```text
dist\Kometa Helper
```

Upload that zip to a GitHub Release, not directly into the source repository.

Suggested release title:

```text
Kometa Helper Windows v0.1.0
```

Suggested release notes:

```text
Initial Windows desktop release.

Includes:
- Local Kometa install/update flow
- Plex setup
- TMDb setup
- IMDb collection creation
- Collection poster tools
- Global overlay setup
- All-poster refresh workflow
```

## Recommended Repository Settings

- Add a short description:

```text
Windows desktop helper for managing local Kometa + Plex poster overlays and IMDb collections.
```

- Add topics:

```text
kometa
plex
plex-media-server
posters
collections
windows
python
pywebview
```

## Security Reminder

Never share your own Plex token or TMDb API key in GitHub screenshots, logs, issues, or commits.

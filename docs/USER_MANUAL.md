# User Manual

## First Run

1. Open `Kometa Helper.exe`.
2. Go to the `Setup` tab.
3. Press `Install / Update Kometa`.
4. Enter your Plex URL, usually:

```text
http://127.0.0.1:32400
```

5. Paste your Plex token and press `Save + Test Plex`.
6. Paste your TMDb API key and press `Save TMDb Key`.
7. Choose the Plex libraries Kometa should manage.
8. Add all movie and show folders. Use `Browse Movie Folder` / `Browse Show Folder`, or type one folder per line.

After setup, the app remembers your last tab, so you do not have to look at setup every time.

## Main Tabs

### Setup

Use this for first-time configuration or fixing a broken setup.

This tab manages:

- Kometa install/update
- Plex connection
- TMDb key
- Plex library selection
- Movie/show folder locations
- Browse buttons for selecting movie/show folders
- Optional daily scheduled refresh

### Posters

Use this to refresh posters and overlays.

`Refresh All Posters` asks Plex to rescan your configured movie/show folders, then runs Kometa for Movies and TV Shows.

`Global Overlay Setup` lets you choose which Kometa overlays should appear on posters, such as resolution, audio codec, video format, and show status.

### Collections

This shows collections created through Kometa Helper.

For each collection, you can:

- Update it
- Open poster tools
- Delete the saved collection and remove the Plex collection

### Add IMDb

Use this to create a Plex collection from an IMDb list.

You can paste either:

```text
ls006405458
```

or a full IMDb list URL:

```text
https://www.imdb.com/list/ls006405458/
```

The app previews the collection setup before creating it. If a TMDb collection match is found, the app can use that because it is often more reliable than IMDb scraping.

## Collection Posters

After creating a collection, the app can take you to the poster page.

There you can:

- Generate collection poster layouts.
- Search for a logo by name.
- Search for poster art.
- Upload a custom poster.
- Apply the selected poster directly to the Plex collection.

Collection posters do not use movie/show overlay badges like AAC, Dolby Atmos, WEB, or 4K. Those are meant for individual movie/show posters through global overlays.

## Global Movie/Show Overlays

Global overlays are for normal movie and show posters.

The overlay setup lets users enable and position:

- Resolution
- Audio codec
- Video format/source
- Show status

Press `Refresh All Posters` after saving overlay settings.

## Scheduled Refresh

In `Setup`, enter a time such as:

```text
05:00
```

Then press `Create Daily Schedule`.

Windows Task Scheduler will run the all-poster refresh workflow daily.

## Where Data Is Saved

Runtime data is saved here:

```text
%USERPROFILE%\Documents\Kometa-Helper\runtime
```

This can include:

- Saved collections
- UI tab state
- Media folder locations
- Logs
- Generated poster/logo cache

## Troubleshooting

### Plex says it cannot connect

Check:

- Plex is running.
- The Plex URL is correct.
- The token is correct.
- Windows Firewall is not blocking Plex.

### IMDb collection has fewer items than expected

IMDb lists can include unreleased movies or items not currently in Plex.

The app can also use TMDb collection fallback when available. If one item is missing, make sure the movie exists in Plex and has matched metadata.

### Poster refresh runs but nothing changes

Check:

- The selected libraries are correct.
- Media locations are saved.
- Kometa config exists.
- Global overlays are enabled.
- Plex items have clean metadata matches.

### The app opens the wrong tab

The last tab is saved in:

```text
Documents\Kometa-Helper\runtime\ui-state.json
```

Delete that file to reset the remembered tab.

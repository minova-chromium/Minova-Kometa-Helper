import html
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from ruamel.yaml.comments import CommentedMap
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import urlopen

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps
from plexapi.exceptions import NotFound
from plexapi.server import PlexServer
from ruamel.yaml import YAML


USERPROFILE = Path(os.environ["USERPROFILE"])
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
APP_DATA_DIR = USERPROFILE / "Documents" / "Kometa-Helper"
KOMETA_DIR = USERPROFILE / "Documents" / "Kometa"
KOMETA_PYTHON = KOMETA_DIR / ".venv" / "Scripts" / "python.exe"
KOMETA_SCRIPT = KOMETA_DIR / "kometa.py"
QUICKSTART_CONFIG = USERPROFILE / "Documents" / "Kometa-Quickstart" / "config" / "jolly_goodall_config.yml"
QUICKSTART_DIR = USERPROFILE / "Documents" / "Kometa-Quickstart"
QUICKSTART_EXE = QUICKSTART_DIR / "Quickstart-v0.10.4-Windows.exe"
COLLECTION_DIR = KOMETA_DIR / "config" / "user-imdb-collections"
ASSET_DIR = KOMETA_DIR / "config" / "assets"
LEGACY_RUNTIME_DIR = APP_DIR / "runtime"
RUNTIME_DIR = APP_DATA_DIR / "runtime"
OUTPUTS_DIR = APP_DIR.parent
LOCAL_PLEX_REFRESH_SCRIPT = APP_DIR / "refresh-plex-movie-show-libraries.ps1"
PLEX_REFRESH_SCRIPT = LOCAL_PLEX_REFRESH_SCRIPT if LOCAL_PLEX_REFRESH_SCRIPT.exists() else OUTPUTS_DIR / "refresh-plex-movie-show-libraries.ps1"
KOMETA_RUN_CONFIG = KOMETA_DIR / "config" / "quickstart-run-config.yml"
SCHEDULE_REFRESH_BAT = APP_DIR / "Run-Kometa-Helper-Refresh-All-Posters.bat"
DASHBOARD_URL = "http://127.0.0.1:7171"
REGISTRY_FILE = RUNTIME_DIR / "collections.json"
UI_STATE_FILE = RUNTIME_DIR / "ui-state.json"
LIBRARY_LOCATIONS_FILE = RUNTIME_DIR / "library-locations.json"
POSTER_DIR = RUNTIME_DIR / "posters"
PROGRESS_POSTER_DIR = RUNTIME_DIR / "progress-posters"
LOGO_DIR = RUNTIME_DIR / "logos"
LOGO_RESULT_DIR = RUNTIME_DIR / "logo-results"
POSTER_RESULT_DIR = RUNTIME_DIR / "poster-results"
TEMPLATE_FILE = RUNTIME_DIR / "poster-templates.json"
MEDIA_TEMPLATE_FILE = RUNTIME_DIR / "media-poster-templates.json"

POSTER_CHOICES = {
    "classic": "Classic movie grid",
    "spotlight": "Spotlight collage",
    "wall": "Poster wall",
}

TITLE_MODES = {
    "logo": "Auto logo",
    "text": "Text title",
    "none": "No title",
}

RUNS = {}
RUNS_LOCK = threading.Lock()


def copy_newer_file(source, destination):
    if not source.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and destination.stat().st_mtime >= source.stat().st_mtime:
        return
    shutil.copy2(source, destination)


def migrate_legacy_runtime():
    if LEGACY_RUNTIME_DIR.resolve() == RUNTIME_DIR.resolve() or not LEGACY_RUNTIME_DIR.exists():
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        return

    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    for source in LEGACY_RUNTIME_DIR.rglob("*"):
        if not source.is_file():
            continue
        destination = RUNTIME_DIR / source.relative_to(LEGACY_RUNTIME_DIR)
        try:
            copy_newer_file(source, destination)
        except OSError:
            continue


def make_yaml():
    yaml = YAML()
    yaml.indent(mapping=2, sequence=4, offset=2)
    yaml.preserve_quotes = True
    return yaml


def starter_config():
    config = CommentedMap()
    config.yaml_set_start_comment(
        "yaml-language-server: $schema=https://raw.githubusercontent.com/kometa-team/kometa/nightly/json-schema/config-schema.json\n"
        "Kometa Helper starter config. Use the app UI to fill Plex, TMDb, libraries, and media folders."
    )

    plex = CommentedMap()
    plex["url"] = "http://127.0.0.1:32400"
    plex["token"] = ""
    plex["timeout"] = 60
    plex["db_cache"] = 40
    plex["clean_bundles"] = False
    plex["empty_trash"] = False
    plex["optimize"] = False
    plex["verify_ssl"] = True
    config["plex"] = plex

    tmdb = CommentedMap()
    tmdb["apikey"] = ""
    tmdb["cache_expiration"] = 60
    tmdb["language"] = "en"
    tmdb["region"] = "US"
    config["tmdb"] = tmdb

    config["libraries"] = CommentedMap()

    settings = CommentedMap()
    settings["run_order"] = ["operations", "metadata", "collections", "overlays"]
    settings["cache"] = True
    settings["cache_expiration"] = 60
    settings["asset_directory"] = ["config/assets"]
    settings["asset_folders"] = True
    settings["asset_depth"] = 0
    settings["create_asset_folders"] = False
    settings["prioritize_assets"] = False
    settings["dimensional_asset_rename"] = False
    settings["download_url_assets"] = False
    settings["show_missing_season_assets"] = False
    settings["show_missing_episode_assets"] = False
    settings["show_asset_not_needed"] = True
    settings["sync_mode"] = "append"
    settings["minimum_items"] = 1
    settings["default_collection_order"] = "release"
    settings["delete_below_minimum"] = True
    settings["delete_not_scheduled"] = False
    settings["run_again_delay"] = 2
    settings["missing_only_released"] = False
    settings["only_filter_missing"] = False
    settings["show_unmanaged"] = True
    settings["show_unconfigured"] = True
    settings["show_filtered"] = False
    settings["show_unfiltered"] = False
    settings["show_options"] = True
    settings["show_missing"] = True
    settings["show_missing_assets"] = True
    settings["save_report"] = False
    settings["tvdb_language"] = "eng"
    settings["ignore_ids"] = None
    settings["ignore_imdb_ids"] = None
    settings["item_refresh_delay"] = 0
    settings["playlist_sync_to_users"] = None
    settings["playlist_exclude_users"] = None
    settings["playlist_report"] = False
    settings["verify_ssl"] = True
    settings["custom_repo"] = None
    settings["overlay_artwork_filetype"] = "webp_lossy"
    settings["overlay_artwork_quality"] = 90
    settings["auto_sort_hubs"] = None
    config["settings"] = settings

    webhooks = CommentedMap()
    for key in ("changes", "delete", "error", "run_end", "run_start", "version"):
        webhooks[key] = None
    config["webhooks"] = webhooks
    return config


def ensure_starter_config():
    QUICKSTART_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if QUICKSTART_CONFIG.exists():
        return False
    yaml = make_yaml()
    with QUICKSTART_CONFIG.open("w", encoding="utf-8") as f:
        yaml.dump(starter_config(), f)
    return True


def read_config():
    yaml = make_yaml()
    with QUICKSTART_CONFIG.open("r", encoding="utf-8") as f:
        return yaml.load(f)


def write_config(config):
    QUICKSTART_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    if QUICKSTART_CONFIG.exists():
        backup = QUICKSTART_CONFIG.with_suffix(f".backup-{time.strftime('%Y%m%d-%H%M%S')}.yml")
        shutil.copyfile(QUICKSTART_CONFIG, backup)
    yaml = make_yaml()
    with QUICKSTART_CONFIG.open("w", encoding="utf-8") as f:
        yaml.dump(config, f)


def get_libraries():
    try:
        config = read_config()
        libraries = config.get("libraries", {})
        return list(libraries.keys()) or ["Movies"]
    except Exception:
        return ["Movies", "TV Shows"]


def unique_existing(paths):
    seen = set()
    results = []
    for path in paths:
        value = str(path).strip().rstrip("\\/")
        if not value or value.lower() in seen:
            continue
        seen.add(value.lower())
        results.append(value)
    return results


def discover_media_locations():
    movies = []
    shows = []
    for letter in "CDEFGHIJKLMNOPQRSTUVWXYZ":
        root = Path(f"{letter}:\\")
        if not root.exists():
            continue
        for name in ("Movies", "Movie", "Films"):
            path = root / name
            if path.exists():
                movies.append(str(path))
        for number in range(2, 16):
            for name in (f"Movies {number}", f"Movie {number}", f"Films {number}"):
                path = root / name
                if path.exists():
                    movies.append(str(path))
        for name in ("Shows", "TV Shows", "Series"):
            path = root / name
            if path.exists():
                shows.append(str(path))
        for number in range(2, 16):
            for name in (f"Shows {number}", f"TV Shows {number}", f"Series {number}"):
                path = root / name
                if path.exists():
                    shows.append(str(path))
    return {"movies": unique_existing(movies), "shows": unique_existing(shows)}


def plex_configured_locations():
    locations = {"movies": [], "shows": []}
    try:
        plex = plex_connection()
        for section in plex.library.sections():
            if section.type not in {"movie", "show"}:
                continue
            key = "movies" if section.type == "movie" else "shows"
            for location in getattr(section, "locations", []) or []:
                locations[key].append(str(location))
    except Exception:
        pass
    locations["movies"] = unique_existing(locations["movies"])
    locations["shows"] = unique_existing(locations["shows"])
    return locations


def default_media_locations():
    discovered = discover_media_locations()
    plex_locations = plex_configured_locations()
    return {
        "movies": unique_existing(discovered["movies"] + plex_locations["movies"]),
        "shows": unique_existing(discovered["shows"] + plex_locations["shows"]),
    }


def load_media_locations():
    defaults = default_media_locations()
    if not LIBRARY_LOCATIONS_FILE.exists():
        return defaults
    try:
        saved = json.loads(LIBRARY_LOCATIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return defaults
    return {
        "movies": unique_existing(saved.get("movies") or defaults["movies"]),
        "shows": unique_existing(saved.get("shows") or defaults["shows"]),
    }


def path_lines_to_list(text):
    paths = []
    for line in str(text or "").splitlines():
        value = line.strip().strip('"').strip("'").rstrip("\\/")
        if value:
            paths.append(value)
    return unique_existing(paths)


def save_media_locations(movie_text, show_text):
    locations = {
        "movies": path_lines_to_list(movie_text),
        "shows": path_lines_to_list(show_text),
    }
    if not locations["movies"] and not locations["shows"]:
        raise ValueError("Add at least one Movies or Shows folder.")
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    LIBRARY_LOCATIONS_FILE.write_text(json.dumps(locations, indent=2), encoding="utf-8")
    return f"Saved {len(locations['movies'])} movie folder(s) and {len(locations['shows'])} show folder(s)."


def browse_for_media_folder(kind):
    title = "Select a movie folder" if kind == "movies" else "Select a show folder"
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        raise ValueError(f"The Windows folder picker could not load: {exc}") from exc

    root = tk.Tk()
    root.withdraw()
    try:
        root.attributes("-topmost", True)
        path = filedialog.askdirectory(parent=root, title=title, mustexist=True)
    finally:
        root.destroy()
    return str(Path(path)) if path else ""


def status_badge(ok, text):
    cls = "ok" if ok else "warn"
    return f'<span class="badge {cls}">{html.escape(text)}</span>'


def secret_preview(value):
    value = str(value or "")
    if len(value) <= 8:
        return "not set" if not value else "*" * len(value)
    return f"{value[:4]}...{value[-4:]}"


def get_config_value(path, default=None):
    try:
        data = read_config()
    except Exception:
        return default
    cur = data
    for key in path:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def kometa_version_text():
    version_file = KOMETA_DIR / "VERSION"
    if version_file.exists():
        return version_file.read_text(encoding="utf-8", errors="replace").strip()
    return "unknown"


def python_prerequisite_text():
    for name in ("py", "python", "python3"):
        path = shutil.which(name)
        if path:
            return f"Found {name}: {path}"
    return "Python was not found. Install Python 3.11+ from python.org, then run this step again."


def system_status():
    status = {
        "quickstart": QUICKSTART_EXE.exists(),
        "kometa_dir": KOMETA_DIR.exists(),
        "venv": KOMETA_PYTHON.exists(),
        "kometa_script": KOMETA_SCRIPT.exists(),
        "config": QUICKSTART_CONFIG.exists(),
        "refresh_helper": PLEX_REFRESH_SCRIPT.exists(),
        "python_ready": any(shutil.which(name) for name in ("py", "python", "python3")),
        "python_message": python_prerequisite_text(),
        "kometa_version": kometa_version_text(),
        "data_dir": str(RUNTIME_DIR),
        "plex_ok": False,
        "plex_message": "Not tested",
        "tmdb_key": secret_preview(get_config_value(["tmdb", "apikey"], "")),
        "libraries": [],
    }
    try:
        config = read_config()
        status["libraries"] = list((config.get("libraries") or {}).keys())
        plex = config.get("plex") or {}
        status["plex_url"] = str(plex.get("url") or "")
        status["plex_token"] = secret_preview(plex.get("token") or "")
    except Exception as exc:
        status["plex_url"] = ""
        status["plex_token"] = "not set"
        status["plex_message"] = f"Config read failed: {exc}"
        return status
    try:
        plex = plex_connection()
        status["plex_ok"] = True
        status["plex_message"] = f"Connected to {plex.friendlyName}"
    except Exception as exc:
        status["plex_message"] = str(exc)
    return status


def list_plex_library_sections():
    plex = plex_connection()
    sections = []
    for section in plex.library.sections():
        if section.type in {"movie", "show"}:
            sections.append({"title": section.title, "type": section.type})
    return sections


def save_plex_settings(url, token):
    url = str(url or "").strip().rstrip("/")
    token = str(token or "").strip()
    if not url or not token:
        raise ValueError("Plex URL and token are required.")
    ensure_starter_config()
    config = read_config()
    plex = config.setdefault("plex", CommentedMap())
    plex["url"] = url
    plex["token"] = token
    write_config(config)
    plex_connection()
    return "Plex settings saved and connection tested."


def save_tmdb_settings(apikey):
    apikey = str(apikey or "").strip()
    if not apikey:
        raise ValueError("TMDb API key is required.")
    ensure_starter_config()
    config = read_config()
    tmdb = config.setdefault("tmdb", CommentedMap())
    tmdb["apikey"] = apikey
    write_config(config)
    return "TMDb API key saved."


def save_library_selection(selected_libraries):
    selected_libraries = [name for name in selected_libraries if str(name).strip()]
    if not selected_libraries:
        raise ValueError("Choose at least one Plex library.")
    ensure_starter_config()
    config = read_config()
    existing = config.get("libraries") or CommentedMap()
    new_libraries = CommentedMap()
    for name in selected_libraries:
        new_libraries[name] = existing.get(name) or CommentedMap()
    config["libraries"] = new_libraries
    write_config(config)
    return f"Saved {len(selected_libraries)} library/libraries for Kometa."


def library_type_map():
    types = {}
    try:
        for section in list_plex_library_sections():
            types[section["title"]] = section["type"]
    except Exception:
        pass
    for name in get_libraries():
        lower = name.lower()
        if name not in types:
            types[name] = "show" if any(word in lower for word in ("show", "tv", "series")) else "movie"
    return types


def default_overlay_position(overlay_id, library_type):
    defaults = {
        "resolution": {"x": 20, "y": 15},
        "audio_codec": {"x": 300, "y": 15},
        "video_format": {"x": 20, "y": 1390},
        "status": {"x": 681, "y": 1382},
    }
    if overlay_id == "video_format" and library_type == "show":
        return {"x": 20, "y": 15}
    return defaults.get(overlay_id, {"x": 20, "y": 15})


def overlay_entry(overlay_id, library_type, position=None):
    position = position or default_overlay_position(overlay_id, library_type)
    entry = CommentedMap()
    if overlay_id == "audio_codec":
        entry["default"] = "audio_codec"
        template_variables = CommentedMap()
        template_variables["horizontal_offset"] = clamp_int(position.get("x"), 0, 999)
        template_variables["vertical_offset"] = clamp_int(position.get("y"), 0, 1499)
        entry["template_variables"] = template_variables
    elif overlay_id == "resolution":
        entry["default"] = "resolution"
        template_variables = CommentedMap()
        template_variables["use_edition"] = True
        template_variables["horizontal_offset"] = clamp_int(position.get("x"), 0, 999)
        template_variables["vertical_offset"] = clamp_int(position.get("y"), 0, 1499)
        entry["template_variables"] = template_variables
    elif overlay_id == "video_format":
        entry["default"] = "video_format"
        template_variables = CommentedMap()
        template_variables["horizontal_offset"] = clamp_int(position.get("x"), 0, 999)
        template_variables["vertical_offset"] = clamp_int(position.get("y"), 0, 1499)
        entry["template_variables"] = template_variables
    elif overlay_id == "status":
        entry["default"] = "status"
        template_variables = CommentedMap()
        template_variables["back_color_airing"] = "#016920FF"
        template_variables["back_color_returning"] = "#81007FFF"
        template_variables["back_color_canceled"] = "#B52222FF"
        template_variables["back_color_ended"] = "#000847FF"
        template_variables["horizontal_offset"] = clamp_int(position.get("x"), 0, 999)
        template_variables["vertical_offset"] = clamp_int(position.get("y"), 0, 1499)
        entry["template_variables"] = template_variables
    else:
        raise ValueError("Unknown overlay option.")
    return entry


def overlay_ids_for_library(library_config):
    ids = set()
    for item in (library_config or {}).get("overlay_files") or []:
        if isinstance(item, dict) and item.get("default"):
            ids.add(str(item.get("default")))
    return ids


def overlay_positions_for_library(library_config, library_type):
    positions = {}
    for overlay_id in ("audio_codec", "resolution", "video_format", "status"):
        positions[overlay_id] = default_overlay_position(overlay_id, library_type)
    for item in (library_config or {}).get("overlay_files") or []:
        if not isinstance(item, dict):
            continue
        overlay_id = str(item.get("default") or "")
        if overlay_id not in positions:
            continue
        template_variables = item.get("template_variables") or {}
        positions[overlay_id] = {
            "x": clamp_int(template_variables.get("horizontal_offset", positions[overlay_id]["x"]), 0, 999),
            "y": clamp_int(template_variables.get("vertical_offset", positions[overlay_id]["y"]), 0, 1499),
        }
    return positions


def parse_overlay_positions(values):
    positions = {}
    for value in values or []:
        parts = str(value).split("\t")
        if len(parts) != 4:
            continue
        library_name, overlay_id, x, y = parts
        if library_name and overlay_id:
            positions[(library_name, overlay_id)] = {
                "x": clamp_int(x, 0, 999),
                "y": clamp_int(y, 0, 1499),
            }
    return positions


def save_global_overlay_settings(selected_overlay_values, reset_libraries, overlay_position_values=None):
    ensure_starter_config()
    config = read_config()
    libraries = config.setdefault("libraries", CommentedMap())
    type_map = library_type_map()
    positions = parse_overlay_positions(overlay_position_values)
    selected = {}
    for value in selected_overlay_values:
        if "\t" not in value:
            continue
        library_name, overlay_id = value.split("\t", 1)
        if library_name:
            selected.setdefault(library_name, set()).add(overlay_id)
    reset_libraries = set(reset_libraries or [])

    saved_count = 0
    for library_name in get_libraries():
        library_type = type_map.get(library_name, "movie")
        library_config = libraries.setdefault(library_name, CommentedMap())
        overlay_ids = selected.get(library_name, set())
        overlay_files = []
        for overlay_id in ("status", "audio_codec", "resolution", "video_format"):
            if overlay_id not in overlay_ids:
                continue
            if overlay_id == "status" and library_type != "show":
                continue
            overlay_files.append(overlay_entry(overlay_id, library_type, positions.get((library_name, overlay_id))))
        if overlay_files:
            library_config["overlay_files"] = overlay_files
            saved_count += 1
        elif "overlay_files" in library_config:
            del library_config["overlay_files"]

        if library_name in reset_libraries:
            library_config["reset_overlays"] = "tmdb"
        elif "reset_overlays" in library_config:
            del library_config["reset_overlays"]

    write_config(config)
    return f"Saved global overlay setup for {saved_count} library/libraries. Press Refresh All Posters to apply it."


def launch_kometa_update():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    ensure_starter_config()
    run_id = f"kometa-update-{uuid.uuid4().hex[:8]}"
    log_path = RUNTIME_DIR / f"{run_id}.log"
    powershell = shutil.which("powershell") or "powershell"
    script = f"""
$ErrorActionPreference = 'Continue'
$OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output '============================================================'
Write-Output ('Kometa install/update started at ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Output '============================================================'

$pythonExe = $null
$pythonArgs = @()
$py = Get-Command py -ErrorAction SilentlyContinue
if ($py) {{
  $pythonExe = $py.Source
  $pythonArgs = @('-3')
}} else {{
  $python = Get-Command python -ErrorAction SilentlyContinue
  if ($python) {{
    $pythonExe = $python.Source
  }} else {{
    $python3 = Get-Command python3 -ErrorAction SilentlyContinue
    if ($python3) {{
      $pythonExe = $python3.Source
    }}
  }}
}}
if (-not $pythonExe) {{
  Write-Output 'Python was not found on this PC.'
  Write-Output 'Install Python 3.11 or newer from https://www.python.org/downloads/windows/ and make sure "Add python.exe to PATH" is enabled.'
  exit 9009
}}
Write-Output ('Using system Python command: ' + $pythonExe)

if (-not (Test-Path -LiteralPath {ps_quote(KOMETA_DIR)})) {{
  New-Item -ItemType Directory -Path {ps_quote(KOMETA_DIR)} -Force | Out-Null
}}

if (Test-Path -LiteralPath (Join-Path {ps_quote(KOMETA_DIR)} '.git')) {{
  Write-Output 'Pulling latest Kometa from Git...'
  git -C {ps_quote(KOMETA_DIR)} pull
}} else {{
  Write-Output 'Installing/updating Kometa from the official GitHub zip...'
  $zipUrl = 'https://codeload.github.com/kometa-team/Kometa/zip/refs/heads/master'
  $workRoot = Join-Path $env:TEMP ('kometa-helper-install-' + [guid]::NewGuid().ToString('N'))
  $zipPath = Join-Path $workRoot 'kometa-master.zip'
  $extractPath = Join-Path $workRoot 'extract'
  try {{
    New-Item -ItemType Directory -Path $workRoot -Force | Out-Null
    Invoke-WebRequest -Uri $zipUrl -OutFile $zipPath -UseBasicParsing
    Expand-Archive -LiteralPath $zipPath -DestinationPath $extractPath -Force
    $source = Get-ChildItem -LiteralPath $extractPath -Directory | Select-Object -First 1
    if (-not $source) {{
      Write-Output 'Kometa zip extracted, but no source folder was found.'
      exit 1
    }}
    Get-ChildItem -LiteralPath $source.FullName -Force | Copy-Item -Destination {ps_quote(KOMETA_DIR)} -Recurse -Force
    Write-Output ('Kometa files are ready in {ps_quote(KOMETA_DIR)}')
  }} catch {{
    Write-Output 'Kometa download/install failed.'
    Write-Output $_.Exception.Message
    exit 1
  }} finally {{
    if (Test-Path -LiteralPath $workRoot) {{
      Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
    }}
  }}
}}

if (-not (Test-Path -LiteralPath {ps_quote(KOMETA_PYTHON)})) {{
  Write-Output 'Creating Kometa Python virtual environment...'
  & $pythonExe @pythonArgs -m venv {ps_quote(KOMETA_DIR / '.venv')}
  $venvExit = $LASTEXITCODE
  if ($venvExit -ne 0) {{
    Write-Output ('Virtual environment creation failed with exit code ' + $venvExit)
    exit $venvExit
  }}
}}

if (-not (Test-Path -LiteralPath {ps_quote(KOMETA_PYTHON)})) {{
  Write-Output 'Kometa virtual environment was requested, but python.exe was not created.'
  exit 1
}}

if (-not (Test-Path -LiteralPath {ps_quote(KOMETA_DIR / 'requirements.txt')})) {{
  Write-Output 'Kometa requirements.txt was not found after install.'
  exit 1
}}

Write-Output 'Updating Python packages from requirements.txt...'
& {ps_quote(KOMETA_PYTHON)} -m pip install --upgrade pip
& {ps_quote(KOMETA_PYTHON)} -m pip install -r {ps_quote(KOMETA_DIR / 'requirements.txt')}
$pipExit = $LASTEXITCODE

Write-Output ''
Write-Output 'Kometa version file:'
if (Test-Path -LiteralPath {ps_quote(KOMETA_DIR / 'VERSION')}) {{ Get-Content -LiteralPath {ps_quote(KOMETA_DIR / 'VERSION')} }}
Write-Output '============================================================'
Write-Output ('Kometa install/update finished at ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' with exit code ' + $pipExit)
Write-Output '============================================================'
exit $pipExit
"""
    command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    log = log_path.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(command, cwd=str(APP_DIR), stdout=log, stderr=subprocess.STDOUT, text=True)
    log.close()
    with RUNS_LOCK:
        RUNS[run_id] = {
            "process": proc,
            "log": str(log_path),
            "library": "",
            "collection": "Kometa install/update",
            "list_id": "",
            "started": now_text(),
            "kind": "kometa_update",
            "finalized": False,
        }
    return run_id


def create_refresh_schedule(run_time):
    run_time = str(run_time or "").strip()
    if not re.match(r"^\d{2}:\d{2}$", run_time):
        raise ValueError("Use a time like 05:00.")
    task_name = "Kometa Helper Poster Refresh"
    action = f'"{SCHEDULE_REFRESH_BAT}"'
    cmd = [
        "schtasks",
        "/Create",
        "/TN",
        task_name,
        "/SC",
        "DAILY",
        "/ST",
        run_time,
        "/TR",
        action,
        "/F",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout or "Task Scheduler failed.").strip())
    return f"Scheduled daily poster refresh at {run_time}."


def now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def load_registry_raw():
    if not REGISTRY_FILE.exists():
        return []
    try:
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def save_registry(entries):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    REGISTRY_FILE.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def load_ui_state():
    default_state = {"active_tab": "collections"}
    if not UI_STATE_FILE.exists():
        return default_state
    try:
        state = json.loads(UI_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return default_state
    active_tab = str(state.get("active_tab", default_state["active_tab"]))
    if active_tab not in {"setup", "posters", "collections", "add"}:
        active_tab = default_state["active_tab"]
    return {"active_tab": active_tab}


def save_ui_state(update):
    state = load_ui_state()
    active_tab = str(update.get("active_tab", state["active_tab"]))
    if active_tab not in {"setup", "posters", "collections", "add"}:
        raise ValueError("Unknown app tab.")
    state["active_tab"] = active_tab
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    UI_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    return state


def collection_info_from_file(path):
    yaml = make_yaml()
    with Path(path).open("r", encoding="utf-8") as f:
        data = yaml.load(f)
    collections = (data or {}).get("collections", {})
    if not collections:
        return None
    name = next(iter(collections.keys()))
    body = collections[name] or {}
    imdb_list = body.get("imdb_list") or {}
    if isinstance(imdb_list, list):
        imdb_item = imdb_list[0] if imdb_list else {}
    else:
        imdb_item = imdb_list
    list_id = str(imdb_item.get("list_id", "")).strip().lower()
    if not list_id:
        return None
    return {
        "collection_name": str(name),
        "list_id": list_id,
        "limit": int(imdb_item.get("limit", 0) or 0),
        "sort_by": str(imdb_item.get("sort_by", "custom.asc")),
    }


def load_registry():
    entries = load_registry_raw()
    existing_files = {str(Path(e.get("file", "")).resolve()).lower() for e in entries if e.get("file")}
    COLLECTION_DIR.mkdir(parents=True, exist_ok=True)
    changed = False
    for path in COLLECTION_DIR.glob("*.yml"):
        resolved = str(path.resolve()).lower()
        if resolved in existing_files:
            continue
        try:
            info = collection_info_from_file(path)
        except Exception:
            info = None
        if not info:
            continue
        info.update(
            {
                "id": uuid.uuid4().hex,
                "library": "Movies",
                "file": str(path),
                "created_at": now_text(),
                "updated_at": now_text(),
                "last_status": "Imported from existing YAML file",
            }
        )
        entries.append(info)
        changed = True
    if changed:
        save_registry(entries)
    return entries


def get_registry_entry(entry_id):
    for entry in load_registry():
        if entry.get("id") == entry_id:
            return entry
    return None


def upsert_registry_entry(library, collection_name, list_id, limit, sort_by, collection_file):
    entries = load_registry()
    existing = None
    for entry in entries:
        if entry.get("library") == library and entry.get("collection_name", "").lower() == collection_name.lower():
            existing = entry
            break
    if not existing:
        existing = {"id": uuid.uuid4().hex, "created_at": now_text()}
        entries.append(existing)
    existing.update(
        {
            "library": library,
            "collection_name": collection_name,
            "list_id": list_id,
            "limit": int(limit),
            "sort_by": sort_by,
            "file": str(collection_file),
            "updated_at": now_text(),
            "last_status": "Saved; Kometa run started",
        }
    )
    save_registry(entries)
    return existing


def update_registry_status(entry_id, status):
    entries = load_registry()
    for entry in entries:
        if entry.get("id") == entry_id:
            entry["last_run"] = now_text()
            entry["last_status"] = status
            save_registry(entries)
            return


def remove_registry_entry(entry_id):
    entries = load_registry()
    kept = [entry for entry in entries if entry.get("id") != entry_id]
    save_registry(kept)


def plex_connection():
    config = read_config()
    plex = config.get("plex") or {}
    url = str(plex.get("url", "")).rstrip("/")
    token = str(plex.get("token", ""))
    if not url or not token:
        raise ValueError("Plex URL/token was not found in the Kometa config.")
    return PlexServer(url, token)


def delete_plex_collection(library_name, collection_name):
    plex = plex_connection()
    section = plex.library.section(library_name)
    try:
        collection = section.collection(collection_name)
    except NotFound:
        return "Plex collection was not found; local entry removed."
    collection.delete()
    return "Plex collection deleted."


def get_plex_collection(library_name, collection_name):
    plex = plex_connection()
    section = plex.library.section(library_name)
    try:
        return plex, section.collection(collection_name)
    except NotFound as exc:
        raise ValueError("Plex collection was not found. Run Update first so Kometa creates it, then choose a poster.") from exc


def get_font(size, bold=False):
    names = ["segoeuib.ttf", "arialbd.ttf"] if bold else ["segoeui.ttf", "arial.ttf"]
    font_dir = Path(os.environ.get("WINDIR", "C:\\Windows")) / "Fonts"
    for name in names:
        path = font_dir / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = str(text).split()
    lines = []
    current = ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] <= max_width:
            current = test
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:3]


def tmdb_api_key():
    try:
        config = read_config()
        return str((config.get("tmdb") or {}).get("apikey") or "").strip()
    except Exception:
        return ""


def read_json_url(url, timeout=15):
    with urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def normalized_title(text):
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


def collection_match_key(text):
    words = normalized_title(text).split()
    drop_words = {"the", "collection", "trilogy", "series", "saga", "franchise", "movies"}
    return " ".join(word for word in words if word not in drop_words)


def tmdb_collection_search_terms(collection_name):
    base = re.sub(r"\bcollection\b", "", collection_name, flags=re.IGNORECASE).strip()
    base = re.sub(r"^\s*the\s+", "", base, flags=re.IGNORECASE).strip()
    without_group_word = re.sub(r"\b(trilogy|series|saga|franchise)\b", "", base, flags=re.IGNORECASE).strip()
    terms = [
        collection_name,
        base,
        f"{without_group_word} Collection" if without_group_word else "",
        re.sub(r"\b(trilogy|series|saga|franchise)\b", "Collection", base, flags=re.IGNORECASE).strip(),
    ]

    clean = []
    seen = set()
    for term in terms:
        term = re.sub(r"\s+", " ", term).strip()
        key = term.lower()
        if term and key not in seen:
            clean.append(term)
            seen.add(key)
    return clean


def find_tmdb_collection(collection_name):
    key = tmdb_api_key()
    if not key:
        return None

    wanted = collection_match_key(collection_name)
    if not wanted:
        return None

    if wanted == "spider man":
        return {
            "id": [556, 125574, 531241, 573436],
            "name": "Spider-Man movie collections",
            "query": "Spider-Man Movies",
        }

    for term in tmdb_collection_search_terms(collection_name):
        search_url = f"https://api.themoviedb.org/3/search/collection?api_key={quote(key)}&query={quote(term)}"
        try:
            results = read_json_url(search_url, timeout=20).get("results") or []
        except Exception:
            continue
        exact_match = None
        fuzzy_match = None
        for result in results[:8]:
            name = result.get("name") or ""
            found = collection_match_key(name)
            if not found:
                continue
            if wanted == found:
                exact_match = {"id": int(result["id"]), "name": name, "query": term}
                break
            if not fuzzy_match and (wanted in found or found in wanted):
                fuzzy_match = {"id": int(result["id"]), "name": name, "query": term}
        if exact_match:
            return exact_match
        if fuzzy_match:
            return fuzzy_match
    return None


def supplemental_tmdb_movies(collection_name):
    wanted = collection_match_key(collection_name)
    if wanted == "hunger games":
        return [695721]
    return []


def local_logo_path(title):
    asset_folder = ASSET_DIR / title
    for name in ("logo.png", "logo.jpg", "logo.jpeg", "clearlogo.png", "clearlogo.jpg", "clearlogo.jpeg"):
        path = asset_folder / name
        if path.exists():
            return path
    return None


def logo_search_terms(title):
    terms = [
        title,
        re.sub(r"\s*-\s*", " ", title),
        re.sub(r"\bcollection\b", "", title, flags=re.IGNORECASE).strip(),
    ]
    if "-" in title:
        terms.append(title.split("-", 1)[1].strip())

    clean = []
    seen = set()
    for term in terms:
        term = re.sub(r"\bcollection\b", "", term, flags=re.IGNORECASE).strip()
        if term and term.lower() not in seen:
            clean.append(term)
            seen.add(term.lower())
    return clean


def best_tmdb_logo(logos):
    if not logos:
        return None
    logos.sort(
        key=lambda item: (
            item.get("iso_639_1") == "en",
            item.get("vote_count") or 0,
            item.get("vote_average") or 0,
            item.get("width") or 0,
        ),
        reverse=True,
    )
    return logos[0].get("file_path")


def download_tmdb_logo(file_path, cache_path):
    if not file_path:
        return None
    with urlopen(f"https://image.tmdb.org/t/p/original{file_path}", timeout=20) as response:
        cache_path.write_bytes(response.read())
    return cache_path


def logo_result_dir(entry_id):
    path = LOGO_RESULT_DIR / safe_filename(entry_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def logo_result_path(entry_id, logo_id):
    logo_id = safe_filename(logo_id)
    if not logo_id:
        raise ValueError("Logo choice was missing.")
    return logo_result_dir(entry_id) / f"{logo_id}.png"


def add_logo_results(entry_id, media_label, source, media_id, logos, seen, results, limit):
    sorted_logos = list(logos or [])
    sorted_logos.sort(
        key=lambda item: (
            item.get("iso_639_1") == "en",
            item.get("vote_count") or 0,
            item.get("vote_average") or 0,
            item.get("width") or 0,
        ),
        reverse=True,
    )
    for index, logo in enumerate(sorted_logos[:4]):
        file_path = logo.get("file_path")
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        logo_id = safe_filename(f"{source}-{media_id}-{index}-{Path(file_path).stem}")
        cache_path = logo_result_path(entry_id, logo_id)
        if not cache_path.exists():
            download_tmdb_logo(file_path, cache_path)
        results.append(
            {
                "id": logo_id,
                "label": media_label,
                "source": source.title(),
                "path": str(cache_path),
            }
        )
        if len(results) >= limit:
            return


def search_logo_choices(entry_id, query, limit=18):
    query = (query or "").strip()
    if not query:
        return []
    key = tmdb_api_key()
    if not key:
        raise ValueError("TMDb API key was not found in the Kometa config.")

    results = []
    seen = set()
    collection_url = f"https://api.themoviedb.org/3/search/collection?api_key={quote(key)}&query={quote(query)}"
    for item in (read_json_url(collection_url).get("results") or [])[:8]:
        collection_id = item.get("id")
        if not collection_id:
            continue
        name = item.get("name") or query
        images_url = (
            f"https://api.themoviedb.org/3/collection/{collection_id}/images"
            f"?api_key={quote(key)}&include_image_language=en,null"
        )
        add_logo_results(entry_id, name, "collection", collection_id, read_json_url(images_url).get("logos") or [], seen, results, limit)
        if len(results) >= limit:
            return results

    movie_url = f"https://api.themoviedb.org/3/search/movie?api_key={quote(key)}&query={quote(query)}"
    for item in (read_json_url(movie_url).get("results") or [])[:10]:
        movie_id = item.get("id")
        if not movie_id:
            continue
        title = item.get("title") or query
        year = (item.get("release_date") or "")[:4]
        label = f"{title} ({year})" if year else title
        images_url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={quote(key)}&include_image_language=en,null"
        add_logo_results(entry_id, label, "movie", movie_id, read_json_url(images_url).get("logos") or [], seen, results, limit)
        if len(results) >= limit:
            return results
    return results


def select_collection_logo(entry, logo_id):
    source = logo_result_path(entry["id"], logo_id)
    if not source.exists():
        raise ValueError("That logo choice was not found. Search again and select the logo.")
    asset_folder = ASSET_DIR / entry["collection_name"]
    asset_folder.mkdir(parents=True, exist_ok=True)
    asset_path = asset_folder / "logo.png"
    shutil.copyfile(source, asset_path)
    status = "Logo selected for generated posters"
    update_registry_status(entry["id"], status)
    return status


def poster_result_dir(entry_id):
    path = POSTER_RESULT_DIR / safe_filename(entry_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def searched_poster_path(entry_id, poster_id):
    poster_id = safe_filename(poster_id)
    if not poster_id:
        raise ValueError("Poster choice was missing.")
    return poster_result_dir(entry_id) / f"{poster_id}.jpg"


def add_poster_results(entry_id, media_label, source, media_id, posters, seen, results, limit):
    sorted_posters = list(posters or [])
    sorted_posters.sort(
        key=lambda item: (
            item.get("iso_639_1") == "en",
            item.get("vote_count") or 0,
            item.get("vote_average") or 0,
            item.get("width") or 0,
        ),
        reverse=True,
    )
    for index, poster in enumerate(sorted_posters[:5]):
        file_path = poster.get("file_path")
        if not file_path or file_path in seen:
            continue
        seen.add(file_path)
        poster_id = safe_filename(f"{source}-{media_id}-{index}-{Path(file_path).stem}")
        cache_path = searched_poster_path(entry_id, poster_id)
        if not cache_path.exists():
            with urlopen(f"https://image.tmdb.org/t/p/original{file_path}", timeout=20) as response:
                cache_path.write_bytes(response.read())
        results.append(
            {
                "id": poster_id,
                "label": media_label,
                "source": source.title(),
                "path": str(cache_path),
            }
        )
        if len(results) >= limit:
            return


def search_poster_choices(entry_id, query, limit=18):
    query = (query or "").strip()
    if not query:
        return []
    key = tmdb_api_key()
    if not key:
        raise ValueError("TMDb API key was not found in the Kometa config.")

    results = []
    seen = set()
    collection_url = f"https://api.themoviedb.org/3/search/collection?api_key={quote(key)}&query={quote(query)}"
    for item in (read_json_url(collection_url).get("results") or [])[:8]:
        collection_id = item.get("id")
        if not collection_id:
            continue
        name = item.get("name") or query
        images_url = (
            f"https://api.themoviedb.org/3/collection/{collection_id}/images"
            f"?api_key={quote(key)}&include_image_language=en,null"
        )
        add_poster_results(entry_id, name, "collection", collection_id, read_json_url(images_url).get("posters") or [], seen, results, limit)
        if len(results) >= limit:
            return results

    movie_url = f"https://api.themoviedb.org/3/search/movie?api_key={quote(key)}&query={quote(query)}"
    for item in (read_json_url(movie_url).get("results") or [])[:10]:
        movie_id = item.get("id")
        if not movie_id:
            continue
        title = item.get("title") or query
        year = (item.get("release_date") or "")[:4]
        label = f"{title} ({year})" if year else title
        images_url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={quote(key)}&include_image_language=en,null"
        add_poster_results(entry_id, label, "movie", movie_id, read_json_url(images_url).get("posters") or [], seen, results, limit)
        if len(results) >= limit:
            return results
    return results


def default_poster_search_query(collection_name):
    name = re.sub(r"\s+", " ", str(collection_name or "")).strip()
    if not name:
        return ""
    if re.search(r"\bcollection$", name, re.IGNORECASE):
        return name
    return f"{name} Collection"


def select_searched_poster(entry, poster_id):
    source = searched_poster_path(entry["id"], poster_id)
    if not source.exists():
        raise ValueError("That poster choice was not found. Search again and select the poster.")

    asset_folder = ASSET_DIR / entry["collection_name"]
    asset_folder.mkdir(parents=True, exist_ok=True)
    asset_path = asset_folder / "poster.jpg"
    image = Image.open(source)
    image = ImageOps.exif_transpose(image).convert("RGB")
    fit_image(image, (1000, 1500)).save(asset_path, "JPEG", quality=94)

    _, collection = get_plex_collection(entry["library"], entry["collection_name"])
    collection.uploadPoster(filepath=str(asset_path))
    status = "Searched poster selected and applied to Plex"
    update_registry_status(entry["id"], status)
    return status


def find_collection_logo(title):
    local = local_logo_path(title)
    if local:
        return local

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = LOGO_DIR / f"{safe_filename(title)}-v2.png"
    if cache_path.exists():
        return cache_path

    key = tmdb_api_key()
    if not key:
        return None

    for term in logo_search_terms(title):
        try:
            search_url = f"https://api.themoviedb.org/3/search/collection?api_key={quote(key)}&query={quote(term)}"
            results = read_json_url(search_url).get("results") or []
            if not results:
                continue
            collection_id = results[0].get("id")
            if not collection_id:
                continue
            images_url = (
                f"https://api.themoviedb.org/3/collection/{collection_id}/images"
                f"?api_key={quote(key)}&include_image_language=en,null"
            )
            logo_path = best_tmdb_logo(read_json_url(images_url).get("logos") or [])
            if logo_path:
                return download_tmdb_logo(logo_path, cache_path)
        except Exception:
            continue

    for term in logo_search_terms(title):
        try:
            search_url = f"https://api.themoviedb.org/3/search/movie?api_key={quote(key)}&query={quote(term)}"
            results = read_json_url(search_url).get("results") or []
            if not results:
                continue
            wanted = normalized_title(term)
            exact_results = [item for item in results if normalized_title(item.get("title", "")) == wanted]
            if not exact_results:
                continue
            results = exact_results
            results.sort(
                key=lambda item: (
                    item.get("popularity") or 0,
                    item.get("vote_count") or 0,
                ),
                reverse=True,
            )
            movie_id = results[0].get("id")
            if not movie_id:
                continue
            images_url = f"https://api.themoviedb.org/3/movie/{movie_id}/images?api_key={quote(key)}&include_image_language=en,null"
            logo_path = best_tmdb_logo(read_json_url(images_url).get("logos") or [])
            if logo_path:
                return download_tmdb_logo(logo_path, cache_path)
        except Exception:
            continue
    return None


def paste_logo(canvas, logo_path, box):
    logo = Image.open(logo_path).convert("RGBA")
    logo.thumbnail((box[2] - box[0], box[3] - box[1]), Image.Resampling.LANCZOS)
    x = box[0] + ((box[2] - box[0]) - logo.width) // 2
    y = box[1] + ((box[3] - box[1]) - logo.height) // 2
    shadow = Image.new("RGBA", logo.size, (0, 0, 0, 180)).filter(ImageFilter.GaussianBlur(8))
    canvas.alpha_composite(shadow, (x + 5, y + 7))
    canvas.alpha_composite(logo, (x, y))


def draw_centered_title(canvas, title, subtitle=None, title_mode="logo"):
    title_mode = title_mode if title_mode in TITLE_MODES else "logo"
    if title_mode == "none":
        return canvas.convert("RGB")

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    footer_top = 1320
    draw.rectangle((0, footer_top, canvas.width, canvas.height), fill=(6, 10, 14, 205))
    small = get_font(23)

    logo = find_collection_logo(title) if title_mode == "logo" else None
    if logo:
        paste_logo(overlay, logo, (220, footer_top + 14, 780, footer_top + 126))
        y = footer_top + 132
    else:
        font = get_font(46, bold=True)
        lines = wrap_text(draw, title, font, 880)
        line_height = 54
        total_height = len(lines) * line_height + (34 if subtitle else 0)
        y = footer_top + max(12, (canvas.height - footer_top - total_height) // 2)
        for line in lines:
            box = draw.textbbox((0, 0), line, font=font)
            draw.text(((canvas.width - (box[2] - box[0])) // 2, y), line, fill=(248, 250, 252, 255), font=font)
            y += line_height

    if subtitle:
        box = draw.textbbox((0, 0), subtitle, font=small)
        draw.text(((canvas.width - (box[2] - box[0])) // 2, y + 3), subtitle, fill=(179, 194, 209, 255), font=small)
    return Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")


def fit_image(image, size):
    return ImageOps.fit(image.convert("RGB"), size, method=Image.Resampling.LANCZOS)


def clamp_int(value, minimum, maximum):
    try:
        number = int(round(float(value)))
    except Exception:
        number = minimum
    return max(minimum, min(maximum, number))


def default_poster_template(collection_name="Collection"):
    return {
        "name": "Default Collection Template",
        "snap": 20,
        "elements": [
            {"id": "collage", "type": "collage", "label": "Poster collage", "x": 50, "y": 70, "w": 900, "h": 1030},
            {"id": "resolution", "type": "badge", "label": "Resolution", "text": "4K UHD", "x": 82, "y": 92, "w": 145, "h": 46},
            {"id": "audio", "type": "badge", "label": "Audio codec", "text": "AAC", "x": 245, "y": 92, "w": 120, "h": 46},
            {"id": "format", "type": "badge", "label": "Format", "text": "BLU-RAY", "x": 82, "y": 1062, "w": 160, "h": 42},
            {"id": "logo", "type": "logo", "label": "Logo", "text": collection_name, "x": 175, "y": 1190, "w": 650, "h": 170},
        ],
    }


def load_template_store():
    if not TEMPLATE_FILE.exists():
        return {}
    try:
        data = json.loads(TEMPLATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def sanitize_template(template, collection_name="Collection"):
    if not isinstance(template, dict):
        template = default_poster_template(collection_name)
    clean = {
        "name": str(template.get("name") or "Collection Template")[:80],
        "snap": clamp_int(template.get("snap", 20), 5, 100),
        "elements": [],
    }
    allowed = {"collage", "poster", "logo", "title", "badge"}
    seen = set()
    for raw in template.get("elements") or []:
        if not isinstance(raw, dict):
            continue
        element_type = str(raw.get("type") or "").strip().lower()
        if element_type not in allowed:
            continue
        element_id = safe_filename(str(raw.get("id") or f"{element_type}-{len(clean['elements'])}"))[:48]
        if not element_id or element_id in seen:
            element_id = f"{element_type}-{len(clean['elements']) + 1}"
        seen.add(element_id)
        x = clamp_int(raw.get("x", 0), 0, 980)
        y = clamp_int(raw.get("y", 0), 0, 1480)
        w = clamp_int(raw.get("w", 200), 20, 1000 - x)
        h = clamp_int(raw.get("h", 80), 20, 1500 - y)
        clean["elements"].append(
            {
                "id": element_id,
                "type": element_type,
                "label": str(raw.get("label") or element_type.title())[:80],
                "text": str(raw.get("text") or "")[:120],
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )
    if not clean["elements"]:
        return default_poster_template(collection_name)
    return clean


def load_entry_template(entry):
    store = load_template_store()
    template = store.get(entry["id"]) or default_poster_template(entry.get("collection_name", "Collection"))
    return sanitize_template(template, entry.get("collection_name", "Collection"))


def save_entry_template(entry, template):
    clean = sanitize_template(template, entry.get("collection_name", "Collection"))
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    store = load_template_store()
    store[entry["id"]] = clean
    TEMPLATE_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return clean


def poster_cache_dir(entry_id):
    path = POSTER_DIR / safe_filename(entry_id)
    path.mkdir(parents=True, exist_ok=True)
    return path


def template_poster_path(entry_id):
    return poster_cache_dir(entry_id) / "custom-template.jpg"


def media_template_key(rating_key):
    match = re.search(r"\d+", str(rating_key or ""))
    if not match:
        raise ValueError("Plex item key was missing.")
    return match.group(0)


def media_template_cache_dir(rating_key):
    path = POSTER_DIR / "media-items" / media_template_key(rating_key)
    path.mkdir(parents=True, exist_ok=True)
    return path


def media_template_poster_path(rating_key):
    return media_template_cache_dir(rating_key) / "custom-media-template.jpg"


def media_base_poster_path(rating_key):
    return media_template_cache_dir(rating_key) / "base-poster.jpg"


def default_media_poster_template(title="Poster"):
    return {
        "name": "Movie / Show Poster Badges",
        "snap": 10,
        "elements": [
            {"id": "resolution", "type": "badge", "label": "Resolution", "text": "4K", "x": 20, "y": 16, "w": 112, "h": 46},
            {"id": "video", "type": "badge", "label": "Video format", "text": "DOVI HDR10", "x": 128, "y": 16, "w": 130, "h": 46},
            {"id": "audio", "type": "badge", "label": "Audio", "text": "DD+ATMOS", "x": 272, "y": 16, "w": 225, "h": 46},
            {"id": "source", "type": "badge", "label": "Source", "text": "WEB", "x": 20, "y": 1390, "w": 150, "h": 54},
        ],
    }


def load_media_template_store():
    if not MEDIA_TEMPLATE_FILE.exists():
        return {}
    try:
        data = json.loads(MEDIA_TEMPLATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def sanitize_media_template(template, title="Poster"):
    if not isinstance(template, dict):
        template = default_media_poster_template(title)
    clean = {
        "name": str(template.get("name") or "Movie / Show Poster Badges")[:80],
        "snap": clamp_int(template.get("snap", 10), 5, 100),
        "elements": [],
    }
    allowed = {"badge", "title"}
    seen = set()
    for raw in template.get("elements") or []:
        if not isinstance(raw, dict):
            continue
        element_type = str(raw.get("type") or "").strip().lower()
        if element_type not in allowed:
            continue
        element_id = safe_filename(str(raw.get("id") or f"{element_type}-{len(clean['elements'])}"))[:48]
        if not element_id or element_id in seen:
            element_id = f"{element_type}-{len(clean['elements']) + 1}"
        seen.add(element_id)
        x = clamp_int(raw.get("x", 0), 0, 980)
        y = clamp_int(raw.get("y", 0), 0, 1480)
        w = clamp_int(raw.get("w", 150), 20, 1000 - x)
        h = clamp_int(raw.get("h", 52), 20, 1500 - y)
        clean["elements"].append(
            {
                "id": element_id,
                "type": element_type,
                "label": str(raw.get("label") or element_type.title())[:80],
                "text": str(raw.get("text") or "")[:120],
                "x": x,
                "y": y,
                "w": w,
                "h": h,
            }
        )
    if not clean["elements"]:
        return default_media_poster_template(title)
    return clean


def load_media_template(rating_key, title="Poster"):
    store = load_media_template_store()
    template = store.get(media_template_key(rating_key)) or default_media_poster_template(title)
    return sanitize_media_template(template, title)


def save_media_template(rating_key, title, template):
    clean = sanitize_media_template(template, title)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    store = load_media_template_store()
    store[media_template_key(rating_key)] = clean
    MEDIA_TEMPLATE_FILE.write_text(json.dumps(store, indent=2), encoding="utf-8")
    return clean


def poster_path(entry_id, poster_id, title_mode="logo"):
    if poster_id not in POSTER_CHOICES:
        raise ValueError("Unknown poster choice.")
    if title_mode not in TITLE_MODES:
        raise ValueError("Unknown title option.")
    return poster_cache_dir(entry_id) / f"{poster_id}-{title_mode}.jpg"


def scaled_poster_count(total):
    if total <= 0:
        return 1
    if total <= 12:
        return total
    if total <= 24:
        return min(total, 18)
    return min(total, 30)


def load_collection_posters(entry, count=None):
    plex, collection = get_plex_collection(entry["library"], entry["collection_name"])
    items = list(collection.items())
    target = count or scaled_poster_count(len(items))
    images = []
    for item in items:
        thumb = getattr(item, "thumb", None)
        if not thumb:
            continue
        try:
            url = plex.url(thumb, includeToken=True)
            with urlopen(url, timeout=15) as response:
                image = Image.open(BytesIO(response.read())).convert("RGB")
            images.append(image)
        except Exception:
            continue
        if len(images) >= target:
            break
    if not images:
        raise ValueError("No movie posters were available from Plex for this collection.")
    while len(images) < target:
        images.append(images[len(images) % len(images)])
    return images


def build_classic_poster(images, title, title_mode="logo"):
    canvas = Image.new("RGB", (1000, 1500), (8, 12, 16))
    positions = [(0, 0), (500, 0), (0, 500), (500, 500), (0, 1000), (500, 1000)]
    for pos, image in zip(positions, images[:6]):
        canvas.paste(fit_image(image, (500, 500)), pos)
    canvas = ImageEnhance.Color(canvas).enhance(0.9)
    return draw_centered_title(canvas, title, None, title_mode)


def build_spotlight_poster(images, title, title_mode="logo"):
    background = fit_image(images[0], (1000, 1500)).filter(ImageFilter.GaussianBlur(24))
    background = ImageEnhance.Brightness(background).enhance(0.35)
    canvas = background.convert("RGBA")
    count = len(images)
    columns = 2 if count <= 4 else 3 if count <= 9 else 4 if count <= 18 else 5
    rows = (count + columns - 1) // columns
    art_height = 1365 if title_mode == "none" else 1245
    art_left = 50
    art_top = 54
    art_width = 900
    width_by_column_count = {2: 310, 3: 260, 4: 220, 5: 178}
    card_w = width_by_column_count[columns]
    if count > 24:
        card_w = 188
    if count <= 6:
        card_w += 16
    card_h = int(card_w * 1.5)
    x_step = 0 if columns == 1 else (art_width - card_w) / (columns - 1)
    if rows == 1:
        y_step = 0
    else:
        y_step = max(card_h * 0.58, (art_height - card_h) / (rows - 1))
        y_step = min(y_step, card_h * 0.82)
    rotations = [-9, 5, 10, -5, 7, -8, 4, -3, 8, -7, 6, -4, 9, -6, 3]

    for index, image in enumerate(images):
        row = index // columns
        col = index % columns
        row_count = min(columns, count - row * columns)
        row_offset = ((columns - row_count) * x_step) / 2 if row_count < columns else 0
        x = int(art_left + row_offset + col * x_step)
        y = int(art_top + row * y_step)
        x += int(((index % 3) - 1) * 14)
        y += int(((-1) ** index) * 12)
        angle = rotations[index % len(rotations)]
        inset = max(8, int(card_w * 0.045))
        card = Image.new("RGBA", (card_w, card_h), (242, 245, 248, 255))
        card.paste(fit_image(image, (card_w - inset * 2, card_h - inset * 3)), (inset, inset))
        rotated = card.rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        shadow = Image.new("RGBA", rotated.size, (0, 0, 0, 95)).filter(ImageFilter.GaussianBlur(12))
        canvas.alpha_composite(shadow, (x + 18, y + 24))
        canvas.alpha_composite(rotated, (x, y))
    return draw_centered_title(canvas.convert("RGB"), title, None, title_mode)


def build_wall_poster(images, title, title_mode="logo"):
    canvas = Image.new("RGB", (1000, 1500), (7, 10, 14))
    idx = 0
    for y in range(-60, 1260, 300):
        for x in range(-40, 1040, 250):
            canvas.paste(fit_image(images[idx % len(images)], (235, 330)), (x, y))
            idx += 1
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 105))
    canvas = Image.alpha_composite(canvas.convert("RGBA"), overlay).convert("RGB")
    return draw_centered_title(canvas, title, None, title_mode)


def draw_template_collage(canvas, images, box):
    x, y, w, h = box
    area = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    count = len(images)
    columns = 2 if count <= 4 else 3 if count <= 9 else 4 if count <= 18 else 5
    rows = max(1, (count + columns - 1) // columns)
    card_w = max(90, min(int(w / max(1.8, columns - 0.45)), 280))
    card_h = int(card_w * 1.5)
    x_step = 0 if columns == 1 else max(1, (w - card_w) / (columns - 1))
    y_step = 0 if rows == 1 else max(card_h * 0.50, min(card_h * 0.82, (h - card_h) / max(1, rows - 1)))
    rotations = [-8, 5, 9, -5, 6, -7, 4, -3, 8, -6, 5, -4]
    for index, image in enumerate(images):
        row = index // columns
        col = index % columns
        row_count = min(columns, count - row * columns)
        row_offset = ((columns - row_count) * x_step) / 2 if row_count < columns else 0
        px = int(row_offset + col * x_step + ((index % 3) - 1) * 10)
        py = int(row * y_step + ((-1) ** index) * 8)
        inset = max(7, int(card_w * 0.045))
        card = Image.new("RGBA", (card_w, card_h), (242, 245, 248, 255))
        card.paste(fit_image(image, (card_w - inset * 2, card_h - inset * 3)), (inset, inset))
        rotated = card.rotate(rotations[index % len(rotations)], resample=Image.Resampling.BICUBIC, expand=True)
        shadow = Image.new("RGBA", rotated.size, (0, 0, 0, 105)).filter(ImageFilter.GaussianBlur(10))
        area.alpha_composite(shadow, (px + 14, py + 18))
        area.alpha_composite(rotated, (px, py))
    canvas.alpha_composite(area, (x, y))


def draw_template_badge(canvas, box, text):
    x, y, w, h = box
    text = str(text or "BADGE").upper()
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    radius = max(6, min(18, h // 3))
    draw.rounded_rectangle((x, y, x + w, y + h), radius=radius, fill=(7, 10, 13, 225), outline=(255, 255, 255, 65), width=2)
    font_size = max(16, min(44, int(h * 0.56)))
    font = get_font(font_size, bold=True)
    while font_size > 12 and draw.textbbox((0, 0), text, font=font)[2] > w - 18:
        font_size -= 2
        font = get_font(font_size, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    tx = x + (w - (bbox[2] - bbox[0])) // 2
    ty = y + (h - (bbox[3] - bbox[1])) // 2 - 1
    draw.text((tx, ty), text, fill=(248, 250, 252, 255), font=font)
    canvas.alpha_composite(overlay)


def draw_template_text(canvas, box, text, bold=True):
    x, y, w, h = box
    text = str(text or "").strip()
    if not text:
        return
    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font_size = max(18, min(76, int(h * 0.45)))
    font = get_font(font_size, bold=bold)
    lines = wrap_text(draw, text, font, max(40, w - 20))
    line_height = int(font_size * 1.18)
    total = len(lines) * line_height
    ty = y + max(0, (h - total) // 2)
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tx = x + (w - (bbox[2] - bbox[0])) // 2
        draw.text((tx + 3, ty + 4), line, fill=(0, 0, 0, 190), font=font)
        draw.text((tx, ty), line, fill=(248, 250, 252, 255), font=font)
        ty += line_height
    canvas.alpha_composite(overlay)


def build_template_poster(entry, template=None):
    template = sanitize_template(template or load_entry_template(entry), entry.get("collection_name", "Collection"))
    images = load_collection_posters(entry)
    title = entry.get("collection_name", "Collection")
    background = fit_image(images[0], (1000, 1500)).filter(ImageFilter.GaussianBlur(26))
    background = ImageEnhance.Brightness(background).enhance(0.34)
    canvas = background.convert("RGBA")
    dark = Image.new("RGBA", canvas.size, (3, 6, 10, 72))
    canvas = Image.alpha_composite(canvas, dark)

    for element in template.get("elements", []):
        x = clamp_int(element.get("x"), 0, 980)
        y = clamp_int(element.get("y"), 0, 1480)
        w = clamp_int(element.get("w"), 20, 1000 - x)
        h = clamp_int(element.get("h"), 20, 1500 - y)
        box = (x, y, w, h)
        element_type = element.get("type")
        text = element.get("text") or ""
        if element_type == "collage":
            draw_template_collage(canvas, images, box)
        elif element_type == "poster":
            poster = fit_image(images[0], (w, h)).convert("RGBA")
            shadow = Image.new("RGBA", (w, h), (0, 0, 0, 110)).filter(ImageFilter.GaussianBlur(14))
            canvas.alpha_composite(shadow, (x + 16, y + 18))
            canvas.alpha_composite(poster, (x, y))
        elif element_type == "logo":
            logo = find_collection_logo(title)
            if logo:
                paste_logo(canvas, logo, (x, y, x + w, y + h))
            else:
                draw_template_text(canvas, box, text or title, True)
        elif element_type == "title":
            draw_template_text(canvas, box, text or title, True)
        elif element_type == "badge":
            draw_template_badge(canvas, box, text)
    return canvas.convert("RGB")


def get_plex_item(rating_key):
    key = media_template_key(rating_key)
    plex = plex_connection()
    return plex, plex.fetchItem(f"/library/metadata/{key}")


def plex_item_poster_image(plex, item):
    thumb = getattr(item, "thumb", None)
    if not thumb:
        raise ValueError("This Plex item does not have a poster.")
    with urlopen(plex.url(thumb, includeToken=True), timeout=20) as response:
        return Image.open(BytesIO(response.read())).convert("RGB")


def plex_item_base_poster_image(rating_key):
    base_path = media_base_poster_path(rating_key)
    if base_path.exists():
        return Image.open(base_path).convert("RGB")
    plex, item = get_plex_item(rating_key)
    image = fit_image(plex_item_poster_image(plex, item), (1000, 1500))
    image.save(base_path, "JPEG", quality=94)
    return image


def search_plex_media(query, limit=24):
    query = str(query or "").strip()
    if not query:
        return []
    plex = plex_connection()
    results = []
    seen = set()
    for section in plex.library.sections():
        if section.type not in {"movie", "show"}:
            continue
        try:
            items = section.search(title=query)
        except TypeError:
            items = section.search(query)
        for item in items:
            key = str(getattr(item, "ratingKey", "") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            year = getattr(item, "year", "") or ""
            results.append(
                {
                    "key": key,
                    "title": getattr(item, "title", "Untitled"),
                    "year": str(year),
                    "library": section.title,
                    "type": section.type,
                }
            )
            if len(results) >= limit:
                return results
    return results


def build_media_template_poster(rating_key, template=None):
    plex, item = get_plex_item(rating_key)
    title = getattr(item, "title", "Poster")
    template = sanitize_media_template(template or load_media_template(rating_key, title), title)
    canvas = plex_item_base_poster_image(rating_key).convert("RGBA")
    for element in template.get("elements", []):
        x = clamp_int(element.get("x"), 0, 980)
        y = clamp_int(element.get("y"), 0, 1480)
        w = clamp_int(element.get("w"), 20, 1000 - x)
        h = clamp_int(element.get("h"), 20, 1500 - y)
        box = (x, y, w, h)
        element_type = element.get("type")
        text = element.get("text") or ""
        if element_type == "title":
            draw_template_text(canvas, box, text or title, True)
        elif element_type == "badge":
            draw_template_badge(canvas, box, text)
    return canvas.convert("RGB")


def save_media_template_json(rating_key, raw_json):
    plex, item = get_plex_item(rating_key)
    title = getattr(item, "title", "Poster")
    try:
        template = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Template JSON was not valid. Try saving again.") from exc
    save_media_template(rating_key, title, template)
    path = media_template_poster_path(rating_key)
    build_media_template_poster(rating_key, template).save(path, "JPEG", quality=93)
    return "Movie/show poster template saved."


def apply_media_template_poster(rating_key, raw_json):
    plex, item = get_plex_item(rating_key)
    title = getattr(item, "title", "Poster")
    try:
        template = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Template JSON was not valid. Try saving again.") from exc
    template = save_media_template(rating_key, title, template)
    source = media_template_poster_path(rating_key)
    build_media_template_poster(rating_key, template).save(source, "JPEG", quality=93)
    item.uploadPoster(filepath=str(source))
    return f"Poster updated in Plex for {title}."


def generate_poster_choices(entry, title_mode="logo"):
    title_mode = title_mode if title_mode in TITLE_MODES else "logo"
    images = load_collection_posters(entry)
    title = entry["collection_name"]
    builders = {
        "classic": build_classic_poster,
        "spotlight": build_spotlight_poster,
        "wall": build_wall_poster,
    }
    choices = []
    for poster_id, builder in builders.items():
        path = poster_path(entry["id"], poster_id, title_mode)
        builder(images, title, title_mode).save(path, "JPEG", quality=92)
        choices.append({"id": poster_id, "label": POSTER_CHOICES[poster_id], "path": str(path)})
    return choices


def apply_collection_poster(entry, poster_id, title_mode="logo"):
    title_mode = title_mode if title_mode in TITLE_MODES else "logo"
    source = poster_path(entry["id"], poster_id, title_mode)
    if not source.exists():
        generate_poster_choices(entry, title_mode)
    if not source.exists():
        raise ValueError("Poster file was not generated.")

    asset_folder = ASSET_DIR / entry["collection_name"]
    asset_folder.mkdir(parents=True, exist_ok=True)
    asset_path = asset_folder / "poster.jpg"
    shutil.copyfile(source, asset_path)

    _, collection = get_plex_collection(entry["library"], entry["collection_name"])
    collection.uploadPoster(filepath=str(asset_path))
    status = f"Poster updated: {POSTER_CHOICES[poster_id]} ({TITLE_MODES[title_mode]})"
    update_registry_status(entry["id"], status)
    return status


def save_template_json(entry, raw_json):
    try:
        template = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Template JSON was not valid. Try saving again.") from exc
    save_entry_template(entry, template)
    path = template_poster_path(entry["id"])
    build_template_poster(entry, template).save(path, "JPEG", quality=93)
    status = "Poster template saved."
    update_registry_status(entry["id"], status)
    return status


def apply_template_poster(entry, raw_json):
    try:
        template = json.loads(raw_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("Template JSON was not valid. Try saving again.") from exc
    template = save_entry_template(entry, template)
    source = template_poster_path(entry["id"])
    build_template_poster(entry, template).save(source, "JPEG", quality=93)

    asset_folder = ASSET_DIR / entry["collection_name"]
    asset_folder.mkdir(parents=True, exist_ok=True)
    asset_path = asset_folder / "poster.jpg"
    shutil.copyfile(source, asset_path)
    _, collection = get_plex_collection(entry["library"], entry["collection_name"])
    collection.uploadPoster(filepath=str(asset_path))
    status = "Template poster saved and applied to Plex."
    update_registry_status(entry["id"], status)
    return status


def apply_custom_poster(entry, filename, content):
    if not content:
        raise ValueError("Choose a poster image file first.")
    try:
        image = Image.open(BytesIO(content))
        image = ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise ValueError("That file did not look like a usable image.") from exc

    asset_folder = ASSET_DIR / entry["collection_name"]
    asset_folder.mkdir(parents=True, exist_ok=True)
    asset_path = asset_folder / "poster.jpg"
    fit_image(image, (1000, 1500)).save(asset_path, "JPEG", quality=94)

    cache_path = poster_cache_dir(entry["id"]) / "custom-upload.jpg"
    shutil.copyfile(asset_path, cache_path)

    _, collection = get_plex_collection(entry["library"], entry["collection_name"])
    collection.uploadPoster(filepath=str(asset_path))
    status = f"Custom poster uploaded: {filename or 'poster image'}"
    update_registry_status(entry["id"], status)
    return status


def extract_list_id(value):
    value = (value or "").strip()
    match = re.search(r"(ls\d+)", value, re.IGNORECASE)
    if not match:
        raise ValueError("Paste an IMDb list ID like ls006405458, or a full IMDb list URL.")
    return match.group(1).lower()


def safe_filename(text):
    text = re.sub(r"[^A-Za-z0-9._ -]+", "", text or "").strip()
    text = re.sub(r"\s+", "-", text)
    return text[:80] or "imdb-collection"


def imdb_collection_builder(list_id, limit, sort_by):
    return (
        "imdb_list",
        {
            "list_id": list_id,
            "limit": int(limit),
            "sort_by": sort_by,
        },
        f"IMDb list {list_id}",
    )


def collection_builder(collection_name, list_id, limit, sort_by, setup_mode="auto"):
    if setup_mode == "imdb":
        return imdb_collection_builder(list_id, limit, sort_by)

    tmdb_collection = find_tmdb_collection(collection_name)
    if tmdb_collection and setup_mode in {"auto", "tmdb"}:
        return (
            "tmdb_collection",
            tmdb_collection["id"],
            f"TMDb collection {tmdb_collection['id']} ({tmdb_collection['name']})",
        )
    if setup_mode == "tmdb":
        raise ValueError("No matching TMDb collection was found for that collection name.")
    return imdb_collection_builder(list_id, limit, sort_by)


def tmdb_collection_parts(collection_id):
    key = tmdb_api_key()
    if not key:
        return []
    data = read_json_url(f"https://api.themoviedb.org/3/collection/{collection_id}?api_key={quote(key)}", timeout=20)
    return [
        {
            "id": item.get("id"),
            "title": item.get("title") or item.get("name") or "Untitled",
            "year": str(item.get("release_date") or "")[:4],
        }
        for item in data.get("parts") or []
    ]


def tmdb_movie_preview(movie_id):
    key = tmdb_api_key()
    if not key:
        return {"id": movie_id, "title": f"TMDb movie {movie_id}", "year": ""}
    data = read_json_url(f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={quote(key)}", timeout=20)
    return {
        "id": movie_id,
        "title": data.get("title") or f"TMDb movie {movie_id}",
        "year": str(data.get("release_date") or "")[:4],
    }


def preview_collection_setup(collection_name, list_id, limit, sort_by):
    builder_name, builder_value, builder_label = collection_builder(collection_name, list_id, limit, sort_by)
    extra_movies = supplemental_tmdb_movies(collection_name) if builder_name == "tmdb_collection" else []
    sources = []
    preview_items = []
    seen_ids = set()
    if builder_name == "tmdb_collection":
        collection_ids = builder_value if isinstance(builder_value, list) else [builder_value]
        for collection_id in collection_ids:
            parts = tmdb_collection_parts(collection_id)
            sources.append({"kind": "TMDb collection", "label": str(collection_id), "count": len(parts)})
            for item in parts:
                item_id = item.get("id")
                if item_id and item_id in seen_ids:
                    continue
                if item_id:
                    seen_ids.add(item_id)
                preview_items.append(item)
        for movie_id in extra_movies:
            if movie_id in seen_ids:
                continue
            item = tmdb_movie_preview(movie_id)
            seen_ids.add(movie_id)
            preview_items.append(item)
            sources.append({"kind": "Extra TMDb movie", "label": str(movie_id), "count": 1})
    else:
        sources.append({"kind": "IMDb list", "label": list_id, "count": int(limit) if int(limit or 0) > 0 else 0})

    return {
        "recommended_mode": "tmdb" if builder_name == "tmdb_collection" else "imdb",
        "builder": builder_name,
        "builder_label": builder_label,
        "sources": sources,
        "items": preview_items[:40],
        "item_count": len(preview_items) if preview_items else None,
        "extra_movie_count": len(extra_movies),
        "imdb_list": list_id,
        "note": (
            "Recommended because IMDb list lookup is currently unreliable in Kometa."
            if builder_name == "tmdb_collection"
            else "No TMDb collection match was found, so this will use the IMDb list directly."
        ),
    }


def write_collection_file(collection_name, list_id, limit, sort_by, setup_mode="auto"):
    COLLECTION_DIR.mkdir(parents=True, exist_ok=True)
    slug = safe_filename(f"{collection_name}-{list_id}")
    path = COLLECTION_DIR / f"{slug}.yml"
    builder_name, builder_value, _builder_label = collection_builder(collection_name, list_id, limit, sort_by, setup_mode)
    collection_order = "release" if builder_name == "tmdb_collection" else "custom"
    collection_data = {
        builder_name: builder_value,
        "collection_order": collection_order,
        "collection_mode": "hide",
        "sync_mode": "sync",
    }
    extra_movies = supplemental_tmdb_movies(collection_name) if builder_name == "tmdb_collection" else []
    if extra_movies:
        collection_data["tmdb_movie"] = extra_movies
    data = {
        "collections": {
            collection_name: collection_data
        }
    }
    yaml = make_yaml()
    with path.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return path


def make_run_config(library_name, collection_file):
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    config = read_config()
    libraries = config.setdefault("libraries", {})
    if library_name not in libraries:
        raise ValueError(f"Library '{library_name}' was not found in the Kometa config.")

    rel_file = collection_file.relative_to(KOMETA_DIR).as_posix()
    existing_library = libraries[library_name] or {}
    clean_library = CommentedMap()
    clean_library["collection_files"] = [{"file": rel_file}]
    for key, value in existing_library.items():
        if key != "collection_files":
            clean_library[key] = value
    libraries[library_name] = clean_library

    run_id = uuid.uuid4().hex[:8]
    run_config = RUNTIME_DIR / f"run-config-{run_id}.yml"
    yaml = make_yaml()
    with run_config.open("w", encoding="utf-8") as f:
        yaml.dump(config, f)
    return run_config, run_id


def tail_text(path, max_chars=20000):
    try:
        data = Path(path).read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    return data[-max_chars:]


def parse_progress(text):
    matches = re.findall(r"Processing:\s*(\d+)\s*/\s*(\d+)\s+([^\r\n|]+)", text or "", flags=re.IGNORECASE)
    if not matches:
        return {"active": False}
    current_raw, total_raw, title = matches[-1]
    current = int(current_raw)
    total = max(1, int(total_raw))
    percent = min(100, max(0, round((current / total) * 100)))
    left = max(0, total - current)
    clean_title = re.sub(r"\s+", " ", title).strip()
    return {
        "active": True,
        "current": current,
        "total": total,
        "left": left,
        "percent": percent,
        "title": clean_title,
    }


def progress_poster_path(title):
    title = re.sub(r"\s+", " ", str(title or "")).strip()
    if not title:
        return None
    PROGRESS_POSTER_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = PROGRESS_POSTER_DIR / f"{safe_filename(title)}.jpg"
    if cache_path.exists():
        return cache_path
    try:
        plex = plex_connection()
        wanted = normalized_title(title)
        for section in plex.library.sections():
            if section.type not in {"movie", "show"}:
                continue
            try:
                results = section.search(title=title)
            except TypeError:
                results = section.search(title)
            for item in results[:8]:
                item_title = normalized_title(getattr(item, "title", ""))
                if wanted and wanted not in item_title and item_title not in wanted:
                    continue
                thumb = getattr(item, "thumb", None)
                if not thumb:
                    continue
                with urlopen(plex.url(thumb, includeToken=True), timeout=15) as response:
                    cache_path.write_bytes(response.read())
                return cache_path
    except Exception:
        return None
    return None


def launch_kometa(library_name, collection_name, list_id, run_config, run_id, registry_id=None):
    log_path = RUNTIME_DIR / f"kometa-run-{run_id}.log"
    command = [
        str(KOMETA_PYTHON),
        str(KOMETA_SCRIPT),
        "--run",
        "--collections-only",
        "--ignore-schedules",
        "--run-libraries",
        library_name,
        "--run-collections",
        collection_name,
        "--config",
        str(run_config),
    ]
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"Kometa IMDb collection run\n")
        log.write(f"Library: {library_name}\n")
        log.write(f"Collection: {collection_name}\n")
        log.write(f"IMDb List: {list_id}\n")
        log.write(f"Command: {' '.join(command)}\n\n")
        log.flush()
        proc = subprocess.Popen(
            command,
            cwd=str(KOMETA_DIR),
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )

    with RUNS_LOCK:
        RUNS[run_id] = {
            "process": proc,
            "log": str(log_path),
            "library": library_name,
            "collection": collection_name,
            "list_id": list_id,
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "registry_id": registry_id,
            "finalized": False,
        }
    return run_id


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def launch_all_poster_refresh():
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    if not LIBRARY_LOCATIONS_FILE.exists():
        defaults = default_media_locations()
        LIBRARY_LOCATIONS_FILE.write_text(json.dumps(defaults, indent=2), encoding="utf-8")
    run_id = f"all-posters-{uuid.uuid4().hex[:8]}"
    log_path = RUNTIME_DIR / f"{run_id}.log"
    plex_scan_log = RUNTIME_DIR / f"{run_id}-plex-scan.log"
    powershell = shutil.which("powershell") or "powershell"
    checks = [
        ("Kometa Python", KOMETA_PYTHON),
        ("Kometa script", KOMETA_SCRIPT),
        ("Kometa config", QUICKSTART_CONFIG),
        ("Plex refresh helper", PLEX_REFRESH_SCRIPT),
        ("Media locations", LIBRARY_LOCATIONS_FILE),
    ]
    missing = [f"{label}: {path}" for label, path in checks if not Path(path).exists()]
    if missing:
        log_path.write_text("Missing required file(s):\n" + "\n".join(missing), encoding="utf-8")
        raise ValueError("Cannot start poster refresh because a required file is missing:\n" + "\n".join(missing))

    script = f"""
$ErrorActionPreference = 'Continue'
$OutputEncoding = [System.Text.Encoding]::UTF8
Write-Output '============================================================'
Write-Output ('Kometa all-poster refresh started at ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
Write-Output '============================================================'
Write-Output 'Running directly from Kometa Helper; the Kometa dashboard is not required.'

Write-Output ''
Write-Output 'Asking Plex to scan movie and show library folders...'
& {ps_quote(powershell)} -NoProfile -ExecutionPolicy Bypass -File {ps_quote(PLEX_REFRESH_SCRIPT)} -ConfigPath {ps_quote(QUICKSTART_CONFIG)} -LogFile {ps_quote(plex_scan_log)} -LocationsJson {ps_quote(LIBRARY_LOCATIONS_FILE)}
if ($LASTEXITCODE -ne 0) {{
  Write-Output 'Plex refresh helper reported a problem. Kometa will still run.'
}}
if (Test-Path -LiteralPath {ps_quote(plex_scan_log)}) {{
  Get-Content -LiteralPath {ps_quote(plex_scan_log)} | ForEach-Object {{ Write-Output $_ }}
}}

Write-Output ''
Write-Output 'Copying Quickstart config for Kometa run...'
try {{
  Copy-Item -LiteralPath {ps_quote(QUICKSTART_CONFIG)} -Destination {ps_quote(KOMETA_RUN_CONFIG)} -Force -ErrorAction Stop
}} catch {{
  Write-Output 'Could not copy Quickstart config to Kometa run config.'
  Write-Output $_.Exception.Message
  exit 1
}}

Write-Output ''
Write-Output 'Running Kometa for Movies and TV Shows now. This can take a while...'
Push-Location {ps_quote(KOMETA_DIR)}
& {ps_quote(KOMETA_PYTHON)} {ps_quote(KOMETA_SCRIPT)} --run --ignore-schedules --run-libraries 'Movies|TV Shows' --config {ps_quote(KOMETA_RUN_CONFIG)}
$kometaExit = $LASTEXITCODE
Pop-Location

Write-Output ''
Write-Output '============================================================'
Write-Output ('Kometa finished at ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss') + ' with exit code ' + $kometaExit)
Write-Output '============================================================'
exit $kometaExit
"""
    command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script]
    log = log_path.open("w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        command,
        cwd=str(OUTPUTS_DIR),
        stdout=log,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log.close()
    with RUNS_LOCK:
        RUNS[run_id] = {
            "process": proc,
            "log": str(log_path),
            "library": "Movies|TV Shows",
            "collection": "All poster refresh",
            "list_id": "",
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "all_posters",
            "finalized": False,
        }
    return run_id


def summarize_log(text, running, exit_code):
    lower = text.lower()
    if running:
        if "kometa install/update started" in lower:
            if "updating python packages" in lower:
                return "Running: Updating Kometa Python packages."
            if "pulling latest kometa" in lower:
                return "Running: Pulling latest Kometa update."
            return "Running: Kometa install/update started."
        if "running kometa for movies and tv shows" in lower or "starting collections run" in lower:
            return "Running: Kometa is updating Movies and TV Shows."
        if "asking plex to scan" in lower or "triggering" in lower:
            return "Running: Plex library scans were requested."
        if "running directly from kometa helper" in lower:
            return "Running: Kometa Helper is refreshing without the dashboard."
        if "processing:" in lower:
            return "Running: Kometa is matching your Plex library and IMDb list."
        if "loading collection file" in lower:
            return "Running: Kometa loaded the collection file."
        return "Running: Kometa has started."
    if "kometa all-poster refresh started" in lower and exit_code == 0:
        return "Finished: Plex scan requested and Kometa poster refresh completed."
    if "kometa install/update started" in lower and exit_code == 0:
        return "Finished: Kometa install/update completed."
    if exit_code == 0 and "finished" in lower and "error summary" not in lower:
        return "Finished: Kometa completed without reported errors."
    if "expecting value" in lower and "unknown error" in lower:
        return "Failed: IMDb returned an empty/unusable response. Check that the list ID is correct and public, then try again."
    if "persistedquerynotfound" in lower:
        return "Failed: IMDb rejected Kometa's list lookup. This app now uses a TMDb collection fallback when one is available; update this saved collection and try again."
    if "kometa failure" in lower or "traceback (most recent call last)" in lower:
        return "Failed: Kometa reported a collection failure. Review the log below."
    if "no items found" in lower:
        return "Finished with warning: Kometa ran, but found no matching Plex items for that IMDb list."
    if exit_code == 0:
        return "Finished: Kometa completed. Review the log below for warnings."
    return f"Failed: Kometa exited with code {exit_code}. Review the log below."


def render_saved_collections():
    entries = sorted(load_registry(), key=lambda e: (e.get("library", ""), e.get("collection_name", "").lower()))
    if not entries:
        return """
        <section class="panel">
          <div class="row-title">Saved Collections</div>
          <p class="empty">No collections have been added through this app yet.</p>
        </section>
        """
    cards = []
    for entry in entries:
        entry_id = html.escape(entry.get("id", ""))
        name = html.escape(entry.get("collection_name", "Untitled"))
        library = html.escape(entry.get("library", "Movies"))
        list_id = html.escape(entry.get("list_id", ""))
        limit = html.escape(str(entry.get("limit", 0)))
        sort_by = html.escape(entry.get("sort_by", "custom.asc"))
        updated = html.escape(entry.get("updated_at", ""))
        status = html.escape(entry.get("last_status", ""))
        cards.append(
            f"""
            <article class="collection-card">
              <div>
                <h3>{name}</h3>
                <p class="meta"><strong>{library}</strong> · IMDb <code>{list_id}</code> · {sort_by} · limit {limit} · hidden from library grid</p>
                <p class="meta">Updated {updated}</p>
                <p class="status-small">{status}</p>
              </div>
              <div class="actions">
                <form method="post" action="/update">
                  <input type="hidden" name="id" value="{entry_id}">
                  <button class="secondary" type="submit">Update</button>
                </form>
                <form method="get" action="/posters">
                  <input type="hidden" name="id" value="{entry_id}">
                  <button class="secondary" type="submit">Poster</button>
                </form>
                <form method="post" action="/delete" onsubmit="return confirm('Delete this saved entry and remove the Plex collection if it exists?');">
                  <input type="hidden" name="id" value="{entry_id}">
                  <button class="danger" type="submit">Delete</button>
                </form>
              </div>
            </article>
            """
        )
    return f"""
    <section class="panel">
      <div class="row-title">Saved Collections</div>
      <div class="collection-list">{''.join(cards)}</div>
    </section>
    """


def render_poster_page(entry_id, message="", title_mode="logo", logo_query="", poster_query=""):
    entry = get_registry_entry(entry_id)
    if not entry:
        return render_page("Saved collection was not found.")

    title_mode = title_mode if title_mode in TITLE_MODES else "logo"
    logo_query = (logo_query or "").strip()
    poster_query = (poster_query or "").strip()
    if not poster_query:
        poster_query = default_poster_search_query(entry.get("collection_name", ""))
    name = html.escape(entry.get("collection_name", "Untitled"))
    library = html.escape(entry.get("library", "Movies"))
    logo_results = []
    logo_error = ""
    if logo_query:
        try:
            logo_results = search_logo_choices(entry_id, logo_query)
            if not logo_results:
                logo_error = "No TMDb logos were found for that search."
        except Exception as exc:
            logo_error = str(exc)
    poster_results = []
    poster_error = ""
    if poster_query:
        try:
            poster_results = search_poster_choices(entry_id, poster_query)
            if not poster_results:
                poster_error = "No TMDb posters were found for that search."
        except Exception as exc:
            poster_error = str(exc)
    try:
        choices = generate_poster_choices(entry, title_mode)
        error = ""
    except Exception as exc:
        choices = []
        error = str(exc)

    mode_buttons = []
    for mode_id, label in TITLE_MODES.items():
        checked = "checked" if mode_id == title_mode else ""
        mode_buttons.append(
            f"""
            <label class="mode-choice">
              <input type="radio" name="title_mode" value="{html.escape(mode_id)}" {checked} onchange="this.form.submit()">
              <span>{html.escape(label)}</span>
            </label>
            """
        )

    logo_cards = []
    for result in logo_results:
        logo_id = html.escape(result["id"])
        label = html.escape(result["label"])
        source = html.escape(result["source"])
        logo_cards.append(
            f"""
            <article class="logo-card">
              <div class="logo-preview">
                <img src="/logo-result-image?id={html.escape(entry_id)}&logo={logo_id}&t={uuid.uuid4().hex}" alt="{label}">
              </div>
              <p>{label}</p>
              <span>{source}</span>
              <form method="post" action="/select-logo">
                <input type="hidden" name="id" value="{html.escape(entry_id)}">
                <input type="hidden" name="logo" value="{logo_id}">
                <button type="submit">Select Logo</button>
              </form>
            </article>
            """
        )

    poster_cards = []
    for result in poster_results:
        poster_id = html.escape(result["id"])
        label = html.escape(result["label"])
        source = html.escape(result["source"])
        poster_cards.append(
            f"""
            <article class="search-poster-card">
              <img src="/poster-result-image?id={html.escape(entry_id)}&poster={poster_id}&t={uuid.uuid4().hex}" alt="{label}">
              <p>{label}</p>
              <span>{source}</span>
              <form method="post" action="/select-search-poster">
                <input type="hidden" name="id" value="{html.escape(entry_id)}">
                <input type="hidden" name="poster" value="{poster_id}">
                <button type="submit">Use Poster</button>
              </form>
            </article>
            """
        )

    cards = []
    for choice in choices:
        poster_id = html.escape(choice["id"])
        label = html.escape(choice["label"])
        cards.append(
            f"""
            <article class="poster-card">
              <img src="/poster-image?id={html.escape(entry_id)}&poster={poster_id}&title_mode={html.escape(title_mode)}&t={uuid.uuid4().hex}" alt="{label}">
              <form method="post" action="/apply-poster">
                <input type="hidden" name="id" value="{html.escape(entry_id)}">
                <input type="hidden" name="poster" value="{poster_id}">
                <input type="hidden" name="title_mode" value="{html.escape(title_mode)}">
                <button type="submit">Apply {label}</button>
              </form>
            </article>
            """
        )

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Poster Selection - {name}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0e1116;
      --panel: #171d24;
      --line: #303b47;
      --text: #f0f6fb;
      --muted: #9fadba;
      --accent: #2dd4bf;
      --accent2: #60a5fa;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: #0e1116;
      color: var(--text);
      min-height: 100vh;
    }}
    main {{
      width: min(1120px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 38px 0;
    }}
    a {{ color: #9be7d8; text-decoration: none; }}
    h1 {{ margin: 8px 0 8px; font-size: clamp(30px, 5vw, 48px); letter-spacing: 0; }}
    .sub {{ color: var(--muted); margin: 0 0 24px; font-size: 16px; }}
    .msg {{
      border-left: 4px solid var(--accent2);
      padding: 12px 14px;
      background: #12202a;
      border-radius: 6px;
      margin-bottom: 18px;
      white-space: pre-wrap;
    }}
    .toolbar {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 14px;
      margin: 18px 0;
      display: grid;
      gap: 14px;
    }}
    .mode-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
    }}
    .mode-choice input {{ position: absolute; opacity: 0; pointer-events: none; }}
    .mode-choice span {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 12px;
      border-radius: 6px;
      border: 1px solid var(--line);
      color: var(--text);
      background: #101820;
      cursor: pointer;
    }}
    .mode-choice input:checked + span {{
      border-color: var(--accent);
      background: #12332f;
      color: #d8fff8;
    }}
    .upload {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
    }}
    .logo-search {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
    }}
    input[type=file], input[type=text] {{
      width: 100%;
      border: 1px solid var(--line);
      background: #101820;
      color: var(--text);
      border-radius: 6px;
      min-height: 44px;
      padding: 9px 11px;
    }}
    .upload button, .logo-search button {{
      width: auto;
      margin: 0;
      min-width: 160px;
    }}
    .search-title {{
      color: var(--muted);
      font-size: 13px;
      margin: 4px 0 -6px;
    }}
    .logo-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 8px;
    }}
    .search-poster-grid {{
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 12px;
      margin-top: 8px;
    }}
    .logo-card {{
      border: 1px solid var(--line);
      background: #101820;
      border-radius: 8px;
      padding: 10px;
      display: grid;
      gap: 8px;
    }}
    .logo-preview {{
      display: grid;
      place-items: center;
      min-height: 96px;
      border-radius: 6px;
      background:
        linear-gradient(45deg, #27313b 25%, transparent 25%),
        linear-gradient(-45deg, #27313b 25%, transparent 25%),
        linear-gradient(45deg, transparent 75%, #27313b 75%),
        linear-gradient(-45deg, transparent 75%, #27313b 75%);
      background-color: #121a22;
      background-size: 24px 24px;
      background-position: 0 0, 0 12px, 12px -12px, -12px 0;
    }}
    .logo-preview img {{
      max-width: 92%;
      max-height: 86px;
      object-fit: contain;
    }}
    .logo-card p {{
      margin: 0;
      color: var(--text);
      font-size: 13px;
      min-height: 34px;
    }}
    .logo-card span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .logo-card button {{
      margin-top: 0;
      min-height: 38px;
      font-size: 13px;
    }}
    .search-poster-card {{
      border: 1px solid var(--line);
      background: #101820;
      border-radius: 8px;
      padding: 10px;
      display: grid;
      gap: 8px;
    }}
    .search-poster-card img {{
      width: 100%;
      aspect-ratio: 2 / 3;
      object-fit: cover;
      border-radius: 6px;
      background: #080d11;
    }}
    .search-poster-card p {{
      margin: 0;
      color: var(--text);
      font-size: 13px;
      min-height: 34px;
    }}
    .search-poster-card span {{
      color: var(--muted);
      font-size: 12px;
    }}
    .search-poster-card button {{
      margin-top: 0;
      min-height: 38px;
      font-size: 13px;
    }}
    .poster-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 18px;
    }}
    .poster-card {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 14px;
    }}
    .poster-card img {{
      display: block;
      width: 100%;
      aspect-ratio: 2 / 3;
      object-fit: cover;
      border-radius: 6px;
      background: #080d11;
    }}
    button {{
      width: 100%;
      border: 0;
      background: var(--accent);
      color: #07130f;
      min-height: 44px;
      padding: 0 14px;
      border-radius: 6px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      margin-top: 12px;
    }}
    .secondary {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #18222c;
      color: var(--text);
      margin-bottom: 18px;
    }}
    .empty {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 18px;
      color: var(--muted);
    }}
    @media (max-width: 840px) {{
      .poster-grid {{ grid-template-columns: 1fr; }}
      .logo-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .search-poster-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .logo-search {{ grid-template-columns: 1fr; }}
      .upload {{ grid-template-columns: 1fr; }}
      .upload button, .logo-search button {{ width: 100%; }}
    }}
  </style>
</head>
<body>
  <main>
    <a class="secondary" href="/">Back to collections</a>
    <h1>{name}</h1>
    <p class="sub">{library} collection posters generated from the movies already in Plex. The collage scales to the collection size, and Auto logo searches by the collection name you entered.</p>
    {f'<div class="msg">{html.escape(message)}</div>' if message else ''}
    <section class="toolbar">
      <form class="mode-row" method="get" action="/posters">
        <input type="hidden" name="id" value="{html.escape(entry_id)}">
        {''.join(mode_buttons)}
      </form>
      <p class="search-title">Search Logo</p>
      <form class="logo-search" method="get" action="/search-logo">
        <input type="hidden" name="id" value="{html.escape(entry_id)}">
        <input type="hidden" name="title_mode" value="logo">
        <input type="text" name="q" value="{html.escape(logo_query)}" placeholder="Search logo, for example Star Wars">
        <button type="submit">Search Logo</button>
      </form>
      {f'<div class="empty">{html.escape(logo_error)}</div>' if logo_error else ''}
      {f'<section class="logo-grid">{"".join(logo_cards)}</section>' if logo_cards else ''}
      <p class="search-title">Search Poster</p>
      <form class="logo-search" method="get" action="/search-poster">
        <input type="hidden" name="id" value="{html.escape(entry_id)}">
        <input type="hidden" name="title_mode" value="{html.escape(title_mode)}">
        <input type="text" name="q" value="{html.escape(poster_query)}" placeholder="Search poster, for example Star Wars">
        <button type="submit">Search Poster</button>
      </form>
      {f'<div class="empty">{html.escape(poster_error)}</div>' if poster_error else ''}
      {f'<section class="search-poster-grid">{"".join(poster_cards)}</section>' if poster_cards else ''}
      <form class="upload" method="post" action="/upload-poster" enctype="multipart/form-data">
        <input type="hidden" name="id" value="{html.escape(entry_id)}">
        <input type="file" name="poster_file" accept="image/png,image/jpeg,image/webp" required>
        <button type="submit">Use Custom Poster</button>
      </form>
    </section>
    {f'<div class="empty">{html.escape(error)}</div>' if error else ''}
    {f'<section class="poster-grid">{"".join(cards)}</section>' if cards else ''}
  </main>
</body>
</html>"""


def render_template_page(entry_id, message=""):
    entry = get_registry_entry(entry_id)
    if not entry:
        return render_page("Saved collection was not found.")
    template = load_entry_template(entry)
    preview_error = ""
    try:
        build_template_poster(entry, template).save(template_poster_path(entry_id), "JPEG", quality=92)
    except Exception as exc:
        preview_error = str(exc)
    name = html.escape(entry.get("collection_name", "Untitled"))
    template_json = json.dumps(template)
    default_json = json.dumps(default_poster_template(entry.get("collection_name", "Collection")))
    collection_name_json = json.dumps(entry.get("collection_name", "Collection"))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Poster Template - {name}</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0e1116;
      --panel: #171d24;
      --panel2: #202832;
      --line: #303b47;
      --text: #f0f6fb;
      --muted: #9fadba;
      --accent: #2dd4bf;
      --accent2: #60a5fa;
      --danger: #ff6b6b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: #0e1116;
      color: var(--text);
      min-height: 100vh;
    }}
    main {{
      width: min(1320px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 34px 0;
    }}
    a {{ color: #9be7d8; text-decoration: none; }}
    h1 {{ margin: 8px 0 8px; font-size: clamp(30px, 5vw, 48px); letter-spacing: 0; }}
    .sub {{ color: var(--muted); margin: 0 0 22px; font-size: 16px; max-width: 820px; }}
    .secondary {{
      display: inline-flex;
      align-items: center;
      min-height: 38px;
      padding: 0 12px;
      border: 1px solid var(--line);
      border-radius: 6px;
      background: #18222c;
      color: var(--text);
      margin-bottom: 18px;
    }}
    .msg, .empty {{
      border-left: 4px solid var(--accent2);
      padding: 12px 14px;
      background: #12202a;
      border-radius: 6px;
      margin-bottom: 16px;
      white-space: pre-wrap;
    }}
    .empty {{ border-left-color: var(--danger); color: #ffd5db; }}
    .layout {{
      display: grid;
      grid-template-columns: 300px minmax(360px, 1fr) 320px;
      gap: 16px;
      align-items: start;
    }}
    .panel {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 16px;
    }}
    .row-title {{
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 10px;
    }}
    label {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 7px;
    }}
    input, select {{
      width: 100%;
      border: 1px solid var(--line);
      background: #101820;
      color: var(--text);
      border-radius: 6px;
      min-height: 40px;
      padding: 8px 10px;
      font-size: 15px;
      outline: none;
    }}
    input:focus, select:focus {{ border-color: var(--accent2); }}
    button {{
      width: 100%;
      border: 0;
      background: var(--accent);
      color: #07130f;
      min-height: 42px;
      padding: 0 14px;
      border-radius: 6px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
      margin-top: 10px;
    }}
    button.muted {{
      background: #263340;
      color: var(--text);
      border: 1px solid var(--line);
    }}
    button.danger {{
      background: #3a1d23;
      color: #ffd5db;
      border: 1px solid #7f2b38;
    }}
    .tool-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
    .control-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }}
    .control-grid .wide {{ grid-column: 1 / -1; }}
    .hint {{ color: var(--muted); font-size: 13px; line-height: 1.45; margin: 8px 0 0; }}
    .stage-shell {{
      display: grid;
      place-items: center;
      border: 1px solid var(--line);
      background: #080d11;
      border-radius: 8px;
      padding: 18px;
      overflow: auto;
    }}
    #posterStage {{
      position: relative;
      width: min(100%, 520px);
      aspect-ratio: 2 / 3;
      overflow: hidden;
      border-radius: 6px;
      background:
        linear-gradient(rgba(255,255,255,.035) 1px, transparent 1px),
        linear-gradient(90deg, rgba(255,255,255,.035) 1px, transparent 1px),
        radial-gradient(circle at 40% 18%, rgba(96,165,250,.25), transparent 28%),
        linear-gradient(160deg, #151d26, #080d11 55%, #1c1715);
      background-size: 20px 20px, 20px 20px, auto, auto;
      box-shadow: 0 24px 70px rgba(0,0,0,.45);
      user-select: none;
    }}
    .element {{
      position: absolute;
      border: 2px solid rgba(96,165,250,.85);
      background: rgba(96,165,250,.14);
      border-radius: 6px;
      display: grid;
      place-items: center;
      color: #eaf6ff;
      font-weight: 800;
      text-align: center;
      overflow: hidden;
      cursor: grab;
      padding: 4px;
      text-shadow: 0 1px 2px rgba(0,0,0,.75);
    }}
    .element.badge {{
      border-color: rgba(45,212,191,.88);
      background: rgba(7,10,13,.82);
      border-radius: 999px;
      font-size: 12px;
    }}
    .element.collage {{
      border-color: rgba(248,250,252,.72);
      background:
        linear-gradient(12deg, rgba(255,255,255,.9) 0 10%, transparent 10% 100%),
        repeating-linear-gradient(90deg, rgba(255,255,255,.18) 0 12px, rgba(0,0,0,.25) 12px 28px);
    }}
    .element.logo {{
      border-color: rgba(251,191,36,.9);
      background: rgba(251,191,36,.12);
    }}
    .element.selected {{
      outline: 3px solid var(--accent);
      outline-offset: 2px;
    }}
    .preview img {{
      display: block;
      width: 100%;
      aspect-ratio: 2 / 3;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid var(--line);
      background: #080d11;
    }}
    .forms {{ display: grid; gap: 8px; margin-top: 12px; }}
    @media (max-width: 1050px) {{
      .layout {{ grid-template-columns: 1fr; }}
      #posterStage {{ width: min(100%, 430px); }}
    }}
  </style>
</head>
<body>
  <main>
    <a class="secondary" href="/posters?id={html.escape(entry_id)}">Back to poster selection</a>
    <h1>{name}</h1>
    <p class="sub">Build a reusable collection poster layout. Drag elements on the canvas; movement snaps to the grid. Select an element to edit badge text, position, and size.</p>
    {f'<div class="msg">{html.escape(message)}</div>' if message else ''}
    {f'<div class="empty">{html.escape(preview_error)}</div>' if preview_error else ''}
    <section class="layout">
      <aside class="panel">
        <div class="row-title">Template</div>
        <label for="templateName">Template name</label>
        <input id="templateName" value="{html.escape(template.get('name', 'Collection Template'))}">
        <p class="hint">Saved locally for this collection. The rendered poster still goes into Plex as the collection poster.</p>
        <div class="row-title" style="margin-top:18px">Add Element</div>
        <div class="tool-grid">
          <button type="button" class="muted" onclick="addElement('badge')">Badge</button>
          <button type="button" class="muted" onclick="addElement('title')">Title</button>
          <button type="button" class="muted" onclick="addElement('logo')">Logo</button>
          <button type="button" class="muted" onclick="addElement('collage')">Collage</button>
          <button type="button" class="muted" onclick="addElement('poster')">Poster</button>
          <button type="button" class="danger" onclick="deleteSelected()">Delete</button>
        </div>
        <button type="button" class="muted" onclick="resetTemplate()">Reset Default</button>
      </aside>

      <section class="stage-shell">
        <div id="posterStage"></div>
      </section>

      <aside class="panel">
        <div class="row-title">Selected Element</div>
        <div class="control-grid">
          <div class="wide">
            <label for="elementType">Type</label>
            <input id="elementType" disabled>
          </div>
          <div class="wide">
            <label for="elementText">Text</label>
            <input id="elementText" placeholder="4K UHD, AAC, BLU-RAY">
          </div>
          <div>
            <label for="elementX">X</label>
            <input id="elementX" type="number" step="10">
          </div>
          <div>
            <label for="elementY">Y</label>
            <input id="elementY" type="number" step="10">
          </div>
          <div>
            <label for="elementW">Width</label>
            <input id="elementW" type="number" step="10">
          </div>
          <div>
            <label for="elementH">Height</label>
            <input id="elementH" type="number" step="10">
          </div>
          <div class="wide">
            <label for="snapSize">Snap grid</label>
            <input id="snapSize" type="number" min="5" max="100" step="5">
          </div>
        </div>
        <div class="forms">
          <form method="post" action="/save-template" onsubmit="syncTemplateJson()">
            <input type="hidden" name="id" value="{html.escape(entry_id)}">
            <input type="hidden" id="saveTemplateJson" name="template_json">
            <button type="submit">Save Template</button>
          </form>
          <form method="post" action="/apply-template" onsubmit="syncTemplateJson()">
            <input type="hidden" name="id" value="{html.escape(entry_id)}">
            <input type="hidden" id="applyTemplateJson" name="template_json">
            <button type="submit">Apply Template Poster</button>
          </form>
        </div>
        <div class="preview" style="margin-top:16px">
          <div class="row-title">Rendered Preview</div>
          <img src="/template-image?id={html.escape(entry_id)}&t={uuid.uuid4().hex}" alt="Rendered poster preview">
          <p class="hint">Save to refresh this rendered preview. Apply sends it straight to Plex.</p>
        </div>
      </aside>
    </section>
  </main>
  <script>
    const initialTemplate = {template_json};
    const defaultTemplate = {default_json};
    let template = JSON.parse(JSON.stringify(initialTemplate));
    let selectedId = template.elements[0]?.id || null;
    let dragging = null;
    const stage = document.getElementById('posterStage');
    const controls = {{
      type: document.getElementById('elementType'),
      text: document.getElementById('elementText'),
      x: document.getElementById('elementX'),
      y: document.getElementById('elementY'),
      w: document.getElementById('elementW'),
      h: document.getElementById('elementH'),
      snap: document.getElementById('snapSize'),
      name: document.getElementById('templateName')
    }};

    function snapValue(value) {{
      const snap = Math.max(5, Number(template.snap || 20));
      return Math.round(value / snap) * snap;
    }}
    function clamp(value, min, max) {{
      return Math.max(min, Math.min(max, value));
    }}
    function selectedElement() {{
      return template.elements.find(el => el.id === selectedId) || null;
    }}
    function labelFor(el) {{
      if (el.type === 'badge') return el.text || 'BADGE';
      if (el.type === 'logo') return 'Logo';
      if (el.type === 'collage') return 'Poster Collage';
      if (el.type === 'poster') return 'Main Poster';
      return el.text || 'Title';
    }}
    function renderStage() {{
      stage.innerHTML = '';
      for (const el of template.elements) {{
        const div = document.createElement('div');
        div.className = 'element ' + el.type + (el.id === selectedId ? ' selected' : '');
        div.dataset.id = el.id;
        div.textContent = labelFor(el);
        div.style.left = (el.x / 10) + '%';
        div.style.top = (el.y / 15) + '%';
        div.style.width = (el.w / 10) + '%';
        div.style.height = (el.h / 15) + '%';
        div.addEventListener('pointerdown', startDrag);
        stage.appendChild(div);
      }}
      updateControls();
    }}
    function updateControls() {{
      const el = selectedElement();
      controls.name.value = template.name || 'Collection Template';
      controls.snap.value = template.snap || 20;
      const disabled = !el;
      for (const key of ['text', 'x', 'y', 'w', 'h']) controls[key].disabled = disabled;
      controls.type.value = el ? el.type : '';
      controls.text.value = el ? (el.text || '') : '';
      controls.x.value = el ? el.x : '';
      controls.y.value = el ? el.y : '';
      controls.w.value = el ? el.w : '';
      controls.h.value = el ? el.h : '';
    }}
    function startDrag(event) {{
      const el = template.elements.find(item => item.id === event.currentTarget.dataset.id);
      if (!el) return;
      selectedId = el.id;
      const rect = stage.getBoundingClientRect();
      dragging = {{
        id: el.id,
        offsetX: ((event.clientX - rect.left) / rect.width * 1000) - el.x,
        offsetY: ((event.clientY - rect.top) / rect.height * 1500) - el.y
      }};
      event.currentTarget.setPointerCapture(event.pointerId);
      renderStage();
    }}
    window.addEventListener('pointermove', event => {{
      if (!dragging) return;
      const el = selectedElement();
      if (!el) return;
      const rect = stage.getBoundingClientRect();
      let x = ((event.clientX - rect.left) / rect.width * 1000) - dragging.offsetX;
      let y = ((event.clientY - rect.top) / rect.height * 1500) - dragging.offsetY;
      el.x = clamp(snapValue(x), 0, 1000 - el.w);
      el.y = clamp(snapValue(y), 0, 1500 - el.h);
      renderStage();
    }});
    window.addEventListener('pointerup', () => dragging = null);
    function addElement(type) {{
      const id = type + '-' + Date.now().toString(36);
      const defaults = {{
        badge: {{ text: 'DOLBY', w: 145, h: 46 }},
        title: {{ text: {collection_name_json}, w: 620, h: 110 }},
        logo: {{ text: {collection_name_json}, w: 620, h: 150 }},
        collage: {{ text: '', w: 820, h: 900 }},
        poster: {{ text: '', w: 260, h: 390 }}
      }};
      const base = defaults[type] || defaults.badge;
      template.elements.push({{ id, type, label: type, text: base.text, x: 100, y: 120, w: base.w, h: base.h }});
      selectedId = id;
      renderStage();
    }}
    function deleteSelected() {{
      if (!selectedId) return;
      template.elements = template.elements.filter(el => el.id !== selectedId);
      selectedId = template.elements[0]?.id || null;
      renderStage();
    }}
    function resetTemplate() {{
      template = JSON.parse(JSON.stringify(defaultTemplate));
      selectedId = template.elements[0]?.id || null;
      renderStage();
    }}
    function applyControlChanges() {{
      template.name = controls.name.value || 'Collection Template';
      template.snap = clamp(Number(controls.snap.value || 20), 5, 100);
      const el = selectedElement();
      if (!el) return;
      el.text = controls.text.value;
      el.x = clamp(snapValue(Number(controls.x.value || 0)), 0, 980);
      el.y = clamp(snapValue(Number(controls.y.value || 0)), 0, 1480);
      el.w = clamp(snapValue(Number(controls.w.value || 20)), 20, 1000 - el.x);
      el.h = clamp(snapValue(Number(controls.h.value || 20)), 20, 1500 - el.y);
      renderStage();
    }}
    for (const key of ['text', 'x', 'y', 'w', 'h', 'snap', 'name']) {{
      controls[key].addEventListener('change', applyControlChanges);
      controls[key].addEventListener('input', () => {{
        if (key === 'text' || key === 'name') applyControlChanges();
      }});
    }}
    function syncTemplateJson() {{
      template.name = controls.name.value || 'Collection Template';
      template.snap = clamp(Number(controls.snap.value || 20), 5, 100);
      document.getElementById('saveTemplateJson').value = JSON.stringify(template);
      document.getElementById('applyTemplateJson').value = JSON.stringify(template);
    }}
    renderStage();
  </script>
</body>
</html>"""


def render_media_template_page(query="", rating_key="", message=""):
    query = str(query or "").strip()
    rating_key = str(rating_key or "").strip()
    if not rating_key:
        results = []
        error = ""
        if query:
            try:
                results = search_plex_media(query)
                if not results:
                    error = "No matching movies or shows were found in Plex."
            except Exception as exc:
                error = str(exc)
        cards = []
        for item in results:
            key = html.escape(item["key"])
            label = html.escape(item["title"])
            year = f" ({html.escape(item['year'])})" if item.get("year") else ""
            meta = html.escape(f"{item['library']} - {item['type']}")
            cards.append(
                f"""
                <article class="result-card">
                  <img src="/media-thumb?key={key}&t={uuid.uuid4().hex}" alt="{label}">
                  <div>
                    <h3>{label}{year}</h3>
                    <p>{meta}</p>
                    <a class="button-link" href="/media-template?key={key}">Edit Poster Template</a>
                  </div>
                </article>
                """
            )
        return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Movie / Show Poster Template Editor</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0e1116; --panel:#171d24; --line:#303b47; --text:#f0f6fb; --muted:#9fadba; --accent:#2dd4bf; --accent2:#60a5fa; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }}
    main {{ width:min(980px,calc(100vw - 32px)); margin:0 auto; padding:38px 0; }}
    a {{ color:#9be7d8; text-decoration:none; }}
    h1 {{ margin:8px 0; font-size:clamp(30px,5vw,48px); letter-spacing:0; }}
    .sub,.hint,p {{ color:var(--muted); }}
    .secondary,.button-link {{ display:inline-flex; align-items:center; min-height:38px; padding:0 12px; border:1px solid var(--line); border-radius:6px; background:#18222c; color:var(--text); }}
    .panel,.result-card {{ border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:16px; }}
    form.search {{ display:grid; grid-template-columns:minmax(0,1fr) auto; gap:10px; margin-top:16px; }}
    input {{ width:100%; border:1px solid var(--line); background:#101820; color:var(--text); border-radius:6px; min-height:44px; padding:10px 12px; font-size:16px; }}
    button {{ border:0; background:var(--accent); color:#07130f; min-height:44px; padding:0 18px; border-radius:6px; font-size:16px; font-weight:700; cursor:pointer; }}
    .results {{ display:grid; gap:12px; margin-top:18px; }}
    .result-card {{ display:grid; grid-template-columns:86px minmax(0,1fr); gap:14px; align-items:center; }}
    .result-card img {{ width:86px; aspect-ratio:2/3; object-fit:cover; border-radius:6px; background:#080d11; }}
    .result-card h3 {{ margin:0 0 6px; }}
    .result-card p {{ margin:0 0 10px; font-size:13px; }}
    .msg,.empty {{ border-left:4px solid var(--accent2); padding:12px 14px; background:#12202a; border-radius:6px; margin:16px 0; white-space:pre-wrap; }}
    @media (max-width:680px) {{ form.search {{ grid-template-columns:1fr; }} .result-card {{ grid-template-columns:64px minmax(0,1fr); }} .result-card img {{ width:64px; }} }}
  </style>
</head>
<body>
  <main>
    <a class="secondary" href="/">Back to Kometa Helper</a>
    <h1>Movie / Show Poster Template Editor</h1>
    <p class="sub">Search Plex for any movie or show, then place snapped overlay badges directly on that item poster.</p>
    {f'<div class="msg">{html.escape(message)}</div>' if message else ''}
    <section class="panel">
      <form class="search" method="get" action="/media-template">
        <input name="q" value="{html.escape(query)}" placeholder="Search Plex, for example Toy Story 5">
        <button type="submit">Search Plex</button>
      </form>
    </section>
    {f'<div class="empty">{html.escape(error)}</div>' if error else ''}
    {f'<section class="results">{"".join(cards)}</section>' if cards else ''}
  </main>
</body>
</html>"""

    try:
        plex, item = get_plex_item(rating_key)
    except Exception as exc:
        return render_media_template_page(query, "", str(exc))
    title = getattr(item, "title", "Poster")
    template = load_media_template(rating_key, title)
    preview_error = ""
    try:
        build_media_template_poster(rating_key, template).save(media_template_poster_path(rating_key), "JPEG", quality=92)
    except Exception as exc:
        preview_error = str(exc)
    template_json = json.dumps(template)
    default_json = json.dumps(default_media_poster_template(title))
    title_json = json.dumps(title)
    safe_key = html.escape(media_template_key(rating_key))
    safe_title = html.escape(title)
    year = getattr(item, "year", "") or ""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Poster Template - {safe_title}</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0e1116; --panel:#171d24; --line:#303b47; --text:#f0f6fb; --muted:#9fadba; --accent:#2dd4bf; --accent2:#60a5fa; --danger:#ff6b6b; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }}
    main {{ width:min(1320px,calc(100vw - 32px)); margin:0 auto; padding:34px 0; }}
    a {{ color:#9be7d8; text-decoration:none; }}
    h1 {{ margin:8px 0; font-size:clamp(30px,5vw,48px); letter-spacing:0; }}
    .sub,.hint {{ color:var(--muted); }}
    .secondary {{ display:inline-flex; align-items:center; min-height:38px; padding:0 12px; border:1px solid var(--line); border-radius:6px; background:#18222c; color:var(--text); margin-bottom:18px; }}
    .layout {{ display:grid; grid-template-columns:300px minmax(360px,1fr) 320px; gap:16px; align-items:start; }}
    .panel {{ border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:16px; }}
    .row-title {{ font-size:18px; font-weight:700; margin-bottom:10px; }}
    label {{ display:block; color:var(--muted); font-size:13px; margin-bottom:7px; }}
    input {{ width:100%; border:1px solid var(--line); background:#101820; color:var(--text); border-radius:6px; min-height:40px; padding:8px 10px; font-size:15px; outline:none; }}
    button {{ width:100%; border:0; background:var(--accent); color:#07130f; min-height:42px; padding:0 14px; border-radius:6px; font-size:15px; font-weight:700; cursor:pointer; margin-top:10px; }}
    button.muted {{ background:#263340; color:var(--text); border:1px solid var(--line); }}
    button.danger {{ background:#3a1d23; color:#ffd5db; border:1px solid #7f2b38; }}
    .tool-grid,.control-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:10px; }}
    .wide {{ grid-column:1 / -1; }}
    .stage-shell {{ display:grid; place-items:center; border:1px solid var(--line); background:#080d11; border-radius:8px; padding:18px; overflow:auto; }}
    #posterStage {{ position:relative; width:min(100%,520px); aspect-ratio:2/3; overflow:hidden; border-radius:6px; background:#080d11; background-image:url('/media-thumb?key={safe_key}&t={uuid.uuid4().hex}'); background-size:cover; background-position:center; box-shadow:0 24px 70px rgba(0,0,0,.45); user-select:none; }}
    .element {{ position:absolute; border:2px solid rgba(45,212,191,.9); background:rgba(7,10,13,.82); border-radius:999px; display:grid; place-items:center; color:#f8fafc; font-weight:900; text-align:center; overflow:hidden; cursor:grab; padding:4px; text-shadow:0 1px 2px rgba(0,0,0,.75); }}
    .element.title {{ border-color:rgba(96,165,250,.9); background:rgba(13,24,38,.48); border-radius:6px; }}
    .element.selected {{ outline:3px solid var(--accent); outline-offset:2px; }}
    .preview img {{ display:block; width:100%; aspect-ratio:2/3; object-fit:cover; border-radius:6px; border:1px solid var(--line); background:#080d11; }}
    .msg,.empty {{ border-left:4px solid var(--accent2); padding:12px 14px; background:#12202a; border-radius:6px; margin-bottom:16px; white-space:pre-wrap; }}
    .empty {{ border-left-color:var(--danger); color:#ffd5db; }}
    .forms {{ display:grid; gap:8px; margin-top:12px; }}
    @media (max-width:1050px) {{ .layout {{ grid-template-columns:1fr; }} #posterStage {{ width:min(100%,430px); }} }}
  </style>
</head>
<body>
  <main>
    <a class="secondary" href="/media-template">Back to poster search</a>
    <h1>{safe_title}{f' ({html.escape(str(year))})' if year else ''}</h1>
    <p class="sub">This editor is for the movie/show poster itself. Drag badges onto the poster; movement snaps to the grid.</p>
    {f'<div class="msg">{html.escape(message)}</div>' if message else ''}
    {f'<div class="empty">{html.escape(preview_error)}</div>' if preview_error else ''}
    <section class="layout">
      <aside class="panel">
        <div class="row-title">Template</div>
        <label for="templateName">Template name</label>
        <input id="templateName" value="{html.escape(template.get('name', 'Movie / Show Poster Badges'))}">
        <p class="hint">Use this for item posters only: resolution, audio, HDR, source, or any custom text badge.</p>
        <div class="row-title" style="margin-top:18px">Add Element</div>
        <div class="tool-grid">
          <button type="button" class="muted" onclick="addElement('badge')">Badge</button>
          <button type="button" class="muted" onclick="addElement('title')">Text</button>
          <button type="button" class="danger" onclick="deleteSelected()">Delete</button>
          <button type="button" class="muted" onclick="resetTemplate()">Reset</button>
        </div>
      </aside>
      <section class="stage-shell"><div id="posterStage"></div></section>
      <aside class="panel">
        <div class="row-title">Selected Element</div>
        <div class="control-grid">
          <div class="wide"><label for="elementType">Type</label><input id="elementType" disabled></div>
          <div class="wide"><label for="elementText">Text</label><input id="elementText" placeholder="4K, DOVI HDR10, DD+ATMOS, WEB"></div>
          <div><label for="elementX">X</label><input id="elementX" type="number" step="10"></div>
          <div><label for="elementY">Y</label><input id="elementY" type="number" step="10"></div>
          <div><label for="elementW">Width</label><input id="elementW" type="number" step="10"></div>
          <div><label for="elementH">Height</label><input id="elementH" type="number" step="10"></div>
          <div class="wide"><label for="snapSize">Snap grid</label><input id="snapSize" type="number" min="5" max="100" step="5"></div>
        </div>
        <div class="forms">
          <form method="post" action="/save-media-template" onsubmit="syncTemplateJson()">
            <input type="hidden" name="key" value="{safe_key}">
            <input type="hidden" id="saveTemplateJson" name="template_json">
            <button type="submit">Save Template</button>
          </form>
          <form method="post" action="/apply-media-template" onsubmit="syncTemplateJson()">
            <input type="hidden" name="key" value="{safe_key}">
            <input type="hidden" id="applyTemplateJson" name="template_json">
            <button type="submit">Apply To Plex Poster</button>
          </form>
        </div>
        <div class="preview" style="margin-top:16px">
          <div class="row-title">Rendered Preview</div>
          <img src="/media-template-image?key={safe_key}&t={uuid.uuid4().hex}" alt="Rendered poster preview">
          <p class="hint">Save refreshes this preview. Apply uploads the rendered image to Plex for this item.</p>
        </div>
      </aside>
    </section>
  </main>
  <script>
    const initialTemplate = {template_json};
    const defaultTemplate = {default_json};
    const itemTitle = {title_json};
    let template = JSON.parse(JSON.stringify(initialTemplate));
    let selectedId = template.elements[0]?.id || null;
    let dragging = null;
    const stage = document.getElementById('posterStage');
    const controls = {{ type:document.getElementById('elementType'), text:document.getElementById('elementText'), x:document.getElementById('elementX'), y:document.getElementById('elementY'), w:document.getElementById('elementW'), h:document.getElementById('elementH'), snap:document.getElementById('snapSize'), name:document.getElementById('templateName') }};
    function snapValue(value) {{ const snap = Math.max(5, Number(template.snap || 10)); return Math.round(value / snap) * snap; }}
    function clamp(value, min, max) {{ return Math.max(min, Math.min(max, value)); }}
    function selectedElement() {{ return template.elements.find(el => el.id === selectedId) || null; }}
    function labelFor(el) {{ return el.text || (el.type === 'title' ? itemTitle : 'BADGE'); }}
    function renderStage() {{
      stage.innerHTML = '';
      for (const el of template.elements) {{
        const div = document.createElement('div');
        div.className = 'element ' + el.type + (el.id === selectedId ? ' selected' : '');
        div.dataset.id = el.id;
        div.textContent = labelFor(el);
        div.style.left = (el.x / 10) + '%';
        div.style.top = (el.y / 15) + '%';
        div.style.width = (el.w / 10) + '%';
        div.style.height = (el.h / 15) + '%';
        div.addEventListener('pointerdown', startDrag);
        stage.appendChild(div);
      }}
      updateControls();
    }}
    function updateControls() {{
      const el = selectedElement();
      controls.name.value = template.name || 'Movie / Show Poster Badges';
      controls.snap.value = template.snap || 10;
      for (const key of ['text','x','y','w','h']) controls[key].disabled = !el;
      controls.type.value = el ? el.type : '';
      controls.text.value = el ? (el.text || '') : '';
      controls.x.value = el ? el.x : '';
      controls.y.value = el ? el.y : '';
      controls.w.value = el ? el.w : '';
      controls.h.value = el ? el.h : '';
    }}
    function startDrag(event) {{
      const el = template.elements.find(item => item.id === event.currentTarget.dataset.id);
      if (!el) return;
      selectedId = el.id;
      const rect = stage.getBoundingClientRect();
      dragging = {{ offsetX: ((event.clientX - rect.left) / rect.width * 1000) - el.x, offsetY: ((event.clientY - rect.top) / rect.height * 1500) - el.y }};
      event.currentTarget.setPointerCapture(event.pointerId);
      renderStage();
    }}
    window.addEventListener('pointermove', event => {{
      if (!dragging) return;
      const el = selectedElement();
      if (!el) return;
      const rect = stage.getBoundingClientRect();
      el.x = clamp(snapValue(((event.clientX - rect.left) / rect.width * 1000) - dragging.offsetX), 0, 1000 - el.w);
      el.y = clamp(snapValue(((event.clientY - rect.top) / rect.height * 1500) - dragging.offsetY), 0, 1500 - el.h);
      renderStage();
    }});
    window.addEventListener('pointerup', () => dragging = null);
    function addElement(type) {{
      const id = type + '-' + Date.now().toString(36);
      const base = type === 'title' ? {{ text: itemTitle, w: 560, h: 90 }} : {{ text: 'BADGE', w: 170, h: 52 }};
      template.elements.push({{ id, type, label: type, text: base.text, x: 40, y: 80, w: base.w, h: base.h }});
      selectedId = id;
      renderStage();
    }}
    function deleteSelected() {{
      template.elements = template.elements.filter(el => el.id !== selectedId);
      selectedId = template.elements[0]?.id || null;
      renderStage();
    }}
    function resetTemplate() {{
      template = JSON.parse(JSON.stringify(defaultTemplate));
      selectedId = template.elements[0]?.id || null;
      renderStage();
    }}
    function applyControlChanges() {{
      template.name = controls.name.value || 'Movie / Show Poster Badges';
      template.snap = clamp(Number(controls.snap.value || 10), 5, 100);
      const el = selectedElement();
      if (!el) return;
      el.text = controls.text.value;
      el.x = clamp(snapValue(Number(controls.x.value || 0)), 0, 980);
      el.y = clamp(snapValue(Number(controls.y.value || 0)), 0, 1480);
      el.w = clamp(snapValue(Number(controls.w.value || 20)), 20, 1000 - el.x);
      el.h = clamp(snapValue(Number(controls.h.value || 20)), 20, 1500 - el.y);
      renderStage();
    }}
    for (const key of ['text','x','y','w','h','snap','name']) {{
      controls[key].addEventListener('change', applyControlChanges);
      controls[key].addEventListener('input', () => {{ if (key === 'text' || key === 'name') applyControlChanges(); }});
    }}
    function syncTemplateJson() {{
      template.name = controls.name.value || 'Movie / Show Poster Badges';
      template.snap = clamp(Number(controls.snap.value || 10), 5, 100);
      document.getElementById('saveTemplateJson').value = JSON.stringify(template);
      document.getElementById('applyTemplateJson').value = JSON.stringify(template);
    }}
    renderStage();
  </script>
</body>
</html>"""


def render_overlay_setup_page(message=""):
    try:
        config = read_config()
    except Exception as exc:
        return render_page(f"Kometa config could not be read: {exc}")

    libraries = get_libraries()
    type_map = library_type_map()
    rows = []
    for library_name in libraries:
        library_type = type_map.get(library_name, "movie")
        library_config = (config.get("libraries") or {}).get(library_name) or {}
        selected = overlay_ids_for_library(library_config)
        positions = overlay_positions_for_library(library_config, library_type)
        reset_checked = "checked" if library_config.get("reset_overlays") else ""
        status_disabled = "disabled" if library_type != "show" else ""
        status_hint = "Show libraries only" if library_type != "show" else "Airing/returning/canceled/ended badges"

        def checked(overlay_id):
            return "checked" if overlay_id in selected else ""

        def preview_chip(overlay_id, label):
            pos = positions[overlay_id]
            active = " active" if overlay_id in selected else ""
            disabled = " disabled" if overlay_id == "status" and library_type != "show" else ""
            return f"""
              <div class="overlay-chip {html.escape(overlay_id)}{active}{disabled}" data-library="{html.escape(library_name)}" data-overlay="{html.escape(overlay_id)}" style="left:{pos['x'] / 10:.2f}%; top:{pos['y'] / 15:.2f}%;">
                {html.escape(label)}
              </div>
              <input type="hidden" name="overlay_position" data-position="{html.escape(library_name)}::{html.escape(overlay_id)}" value="{html.escape(library_name)}&#9;{html.escape(overlay_id)}&#9;{pos['x']}&#9;{pos['y']}">
            """

        rows.append(
            f"""
            <article class="library-card">
              <div>
                <h3>{html.escape(library_name)}</h3>
                <p>{html.escape(library_type.title())} library</p>
              </div>
              <label class="check-row">
                <input type="checkbox" name="overlay" value="{html.escape(library_name)}&#9;audio_codec" {checked("audio_codec")}>
                <span>Audio Codec <small>AAC, DD+, Atmos style audio overlays</small></span>
              </label>
              <label class="check-row">
                <input type="checkbox" name="overlay" value="{html.escape(library_name)}&#9;resolution" {checked("resolution")}>
                <span>Resolution <small>4K, 1080p, edition-aware resolution overlays</small></span>
              </label>
              <label class="check-row">
                <input type="checkbox" name="overlay" value="{html.escape(library_name)}&#9;video_format" {checked("video_format")}>
                <span>Video Format <small>HDR, Dolby Vision, WEB/Blu-ray style source overlays</small></span>
              </label>
              <label class="check-row {'disabled' if status_disabled else ''}">
                <input type="checkbox" name="overlay" value="{html.escape(library_name)}&#9;status" {checked("status")} {status_disabled}>
                <span>Show Status <small>{html.escape(status_hint)}</small></span>
              </label>
              <label class="check-row">
                <input type="checkbox" name="reset_overlays" value="{html.escape(library_name)}" {reset_checked}>
                <span>Reset overlays from TMDb art <small>Rebuilds overlays from a clean poster base when Kometa runs</small></span>
              </label>
              <div class="overlay-preview-wrap">
                <div class="overlay-preview" data-library="{html.escape(library_name)}">
                  {preview_chip("resolution", "4K")}
                  {preview_chip("video_format", "DOVI HDR10")}
                  {preview_chip("audio_codec", "DD+ATMOS")}
                  {preview_chip("status", "STATUS")}
                </div>
                <p class="hint">Drag the enabled overlay labels. Positions are saved globally for this library and used the next time Kometa refreshes posters.</p>
              </div>
            </article>
            """
        )

    if not rows:
        rows.append('<p class="empty">Choose Plex libraries first, then come back to set global overlays.</p>')

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Global Overlay Setup</title>
  <style>
    :root {{ color-scheme: dark; --bg:#0e1116; --panel:#171d24; --line:#303b47; --text:#f0f6fb; --muted:#9fadba; --accent:#2dd4bf; --accent2:#60a5fa; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:"Segoe UI",system-ui,sans-serif; background:var(--bg); color:var(--text); min-height:100vh; }}
    main {{ width:min(980px,calc(100vw - 32px)); margin:0 auto; padding:38px 0; }}
    a {{ color:#9be7d8; text-decoration:none; }}
    h1 {{ margin:8px 0; font-size:clamp(30px,5vw,48px); letter-spacing:0; }}
    .sub,.hint,p {{ color:var(--muted); }}
    .secondary {{ display:inline-flex; align-items:center; min-height:38px; padding:0 12px; border:1px solid var(--line); border-radius:6px; background:#18222c; color:var(--text); margin-bottom:18px; }}
    .panel,.library-card {{ border:1px solid var(--line); background:var(--panel); border-radius:8px; padding:16px; }}
    .library-list {{ display:grid; gap:14px; margin-top:16px; }}
    .library-card {{ display:grid; gap:10px; }}
    .library-card h3 {{ margin:0 0 4px; font-size:20px; }}
    .library-card p {{ margin:0; font-size:13px; }}
    .check-row {{ display:flex; align-items:center; gap:10px; border:1px solid var(--line); background:#101820; border-radius:6px; padding:10px 12px; margin:0; color:var(--text); }}
    .check-row.disabled {{ opacity:.45; }}
    .check-row input {{ width:auto; min-height:auto; }}
    .check-row small {{ display:block; color:var(--muted); margin-top:2px; }}
    .overlay-preview-wrap {{ display:grid; grid-template-columns:minmax(180px, 240px) minmax(0,1fr); gap:14px; align-items:center; margin-top:6px; }}
    .overlay-preview {{ position:relative; width:100%; aspect-ratio:2/3; border:1px solid var(--line); border-radius:8px; overflow:hidden; background:linear-gradient(160deg,#31405a,#111820 55%,#3a2430); box-shadow:inset 0 0 0 1px rgba(255,255,255,.04); }}
    .overlay-preview::before {{ content:""; position:absolute; inset:0; background:radial-gradient(circle at 50% 22%,rgba(255,255,255,.20),transparent 24%), linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px); background-size:auto,20px 20px,20px 20px; opacity:.75; }}
    .overlay-chip {{ position:absolute; z-index:2; display:none; min-width:54px; max-width:92%; min-height:24px; align-items:center; justify-content:center; padding:2px 10px; border-radius:999px; background:rgba(5,8,12,.86); border:1px solid rgba(255,255,255,.22); color:#f8fafc; font-size:11px; font-weight:900; line-height:1.05; cursor:grab; user-select:none; box-shadow:0 8px 18px rgba(0,0,0,.28); }}
    .overlay-chip.video_format {{ color:#9be7ff; }}
    .overlay-chip.audio_codec {{ color:#b8d5ff; }}
    .overlay-chip.status {{ background:rgba(1,105,32,.88); }}
    .overlay-chip.active {{ display:inline-flex; }}
    .overlay-chip.disabled {{ display:none !important; }}
    .overlay-chip.dragging {{ cursor:grabbing; outline:2px solid var(--accent); outline-offset:2px; }}
    button {{ border:0; background:var(--accent); color:#07130f; min-height:46px; padding:0 18px; border-radius:6px; font-size:16px; font-weight:700; cursor:pointer; margin-top:16px; }}
    .msg,.empty {{ border-left:4px solid var(--accent2); padding:12px 14px; background:#12202a; border-radius:6px; margin:16px 0; white-space:pre-wrap; }}
    @media (max-width:760px) {{ .overlay-preview-wrap {{ grid-template-columns:1fr; }} .overlay-preview {{ max-width:240px; }} }}
  </style>
</head>
<body>
  <main>
    <a class="secondary" href="/">Back to Kometa Helper</a>
    <h1>Global Overlay Setup</h1>
    <p class="sub">Set up Kometa overlays once, then press Refresh All Posters to apply them across the selected Plex libraries. This edits Kometa's global library overlay configuration, like Quickstart does.</p>
    {f'<div class="msg">{html.escape(message)}</div>' if message else ''}
    <section class="panel">
      <p class="hint">These presets match the common Quickstart-style setup: audio codec, resolution, video format, and show status overlays. Use Reset overlays if you want Kometa to rebuild from clean TMDb artwork before applying overlays.</p>
      <form method="post" action="/save-overlays">
        <div class="library-list">{''.join(rows)}</div>
        <button type="submit">Save Global Overlay Setup</button>
      </form>
    </section>
  </main>
  <script>
    let dragState = null;
    const snap = 10;

    function updateHiddenPosition(chip) {{
      const key = chip.dataset.library + '::' + chip.dataset.overlay;
      const input = document.querySelector('input[data-position="' + CSS.escape(key) + '"]');
      if (!input) return;
      const x = Math.round(parseFloat(chip.style.left || '0') * 10);
      const y = Math.round(parseFloat(chip.style.top || '0') * 15);
      input.value = chip.dataset.library + '\\t' + chip.dataset.overlay + '\\t' + x + '\\t' + y;
    }}

    function setChipActive(libraryName, overlayId, active) {{
      const chip = document.querySelector('.overlay-chip[data-library="' + CSS.escape(libraryName) + '"][data-overlay="' + CSS.escape(overlayId) + '"]');
      if (!chip) return;
      chip.classList.toggle('active', active);
    }}

    document.querySelectorAll('input[name="overlay"]').forEach(input => {{
      input.addEventListener('change', () => {{
        const parts = input.value.split('\\t');
        if (parts.length === 2) setChipActive(parts[0], parts[1], input.checked);
      }});
    }});

    document.querySelectorAll('.overlay-chip').forEach(chip => {{
      chip.addEventListener('pointerdown', event => {{
        if (!chip.classList.contains('active') || chip.classList.contains('disabled')) return;
        const preview = chip.closest('.overlay-preview');
        const previewRect = preview.getBoundingClientRect();
        const chipRect = chip.getBoundingClientRect();
        dragState = {{
          chip,
          preview,
          dx: event.clientX - chipRect.left,
          dy: event.clientY - chipRect.top,
          maxX: previewRect.width - chipRect.width,
          maxY: previewRect.height - chipRect.height
        }};
        chip.classList.add('dragging');
        chip.setPointerCapture(event.pointerId);
      }});
    }});

    window.addEventListener('pointermove', event => {{
      if (!dragState) return;
      const rect = dragState.preview.getBoundingClientRect();
      let px = event.clientX - rect.left - dragState.dx;
      let py = event.clientY - rect.top - dragState.dy;
      px = Math.max(0, Math.min(dragState.maxX, px));
      py = Math.max(0, Math.min(dragState.maxY, py));
      const x = Math.round((px / rect.width * 1000) / snap) * snap;
      const y = Math.round((py / rect.height * 1500) / snap) * snap;
      dragState.chip.style.left = (x / 10) + '%';
      dragState.chip.style.top = (y / 15) + '%';
      updateHiddenPosition(dragState.chip);
    }});

    window.addEventListener('pointerup', () => {{
      if (!dragState) return;
      dragState.chip.classList.remove('dragging');
      updateHiddenPosition(dragState.chip);
      dragState = null;
    }});
  </script>
</body>
</html>"""


def render_setup_panels():
    status = system_status()
    try:
        plex_sections = list_plex_library_sections() if status["plex_ok"] else []
        plex_error = ""
    except Exception as exc:
        plex_sections = []
        plex_error = str(exc)
    selected = set(status.get("libraries") or [])

    checks = [
        ("Kometa Helper files", status["refresh_helper"], "Bundled refresh helper"),
        ("Windows Python", status["python_ready"], status["python_message"]),
        ("Kometa install", status["kometa_dir"] and status["kometa_script"], f"Version {status['kometa_version']}"),
        ("Python venv", status["venv"], "Local non-Docker Python environment"),
        ("Kometa config", status["config"], str(QUICKSTART_CONFIG)),
        ("Helper data", RUNTIME_DIR.exists(), status["data_dir"]),
        ("Plex", status["plex_ok"], status["plex_message"]),
        ("TMDb", status["tmdb_key"] != "not set", f"Key: {status['tmdb_key']}"),
    ]
    step_cards = []
    for title, ok, detail in checks:
        step_cards.append(
            f"""
            <article class="step-card">
              <div>{status_badge(ok, 'Ready' if ok else 'Needs setup')}</div>
              <h3>{html.escape(title)}</h3>
              <p>{html.escape(str(detail))}</p>
            </article>
            """
        )

    library_rows = []
    if plex_sections:
        for section in plex_sections:
            title = section["title"]
            checked = "checked" if title in selected else ""
            library_rows.append(
                f"""
                <label class="check-row">
                  <input type="checkbox" name="library" value="{html.escape(title)}" {checked}>
                  <span>{html.escape(title)} <small>{html.escape(section['type'])}</small></span>
                </label>
                """
            )
    else:
        library_rows.append(f'<p class="empty">{html.escape(plex_error or "Connect Plex first to choose libraries.")}</p>')

    media_locations = load_media_locations()
    movie_locations_text = html.escape("\n".join(media_locations["movies"]))
    show_locations_text = html.escape("\n".join(media_locations["shows"]))
    current_url = html.escape(status.get("plex_url") or "")
    return f"""
    <section class="panel">
      <div class="row-title">Guided Setup</div>
      <p class="hint">Work through these in order. The app checks what is already ready and leaves your existing working setup alone unless you press a save or run button.</p>
      <div class="setup-grid">{''.join(step_cards)}</div>
    </section>

    <section class="panel">
      <div class="row-title">1. Install / Update Kometa</div>
      <p class="hint">Fresh install or update for local non-Docker Kometa. If Kometa is missing, this downloads it from GitHub, creates the Python environment, installs requirements, and creates the starter config for this app.</p>
      <form method="post" action="/update-kometa">
        <button type="submit">Install / Update Kometa</button>
      </form>
      <p class="hint">Prerequisite: {html.escape(status["python_message"])}</p>
    </section>

    <section class="panel">
      <div class="row-title">2. Connect Plex</div>
      <p class="hint">Current status: {html.escape(status['plex_message'])}</p>
      <form method="post" action="/save-plex" class="mini-form">
        <div>
          <label for="plex_url">Plex URL</label>
          <input id="plex_url" name="plex_url" value="{current_url}" placeholder="http://127.0.0.1:32400">
        </div>
        <div>
          <label for="plex_token">Plex token</label>
          <input id="plex_token" name="plex_token" placeholder="Paste token to save or replace">
          <p class="hint">Current token: {html.escape(status.get('plex_token', 'not set'))}</p>
        </div>
        <button type="submit">Save + Test Plex</button>
      </form>
    </section>

    <section class="panel">
      <div class="row-title">3. TMDb Key</div>
      <p class="hint">TMDb powers logo/poster lookup and many Kometa defaults. Current key: {html.escape(status['tmdb_key'])}</p>
      <form method="post" action="/save-tmdb" class="mini-form">
        <div>
          <label for="tmdb_key">TMDb API key</label>
          <input id="tmdb_key" name="tmdb_key" placeholder="Paste TMDb API key">
        </div>
        <button type="submit">Save TMDb Key</button>
      </form>
    </section>

    <section class="panel">
      <div class="row-title">4. Choose Libraries</div>
      <p class="hint">Select the Plex movie/show libraries Kometa should manage.</p>
      <form method="post" action="/save-libraries">
        <div class="library-list">{''.join(library_rows)}</div>
        <p style="margin-top:14px"><button type="submit">Save Libraries</button></p>
      </form>
    </section>

    <section class="panel">
      <div class="row-title">5. Media Locations</div>
      <p class="hint">List every folder Plex uses for movies and shows. Put one folder per line. These paths are used when Kometa Helper asks Plex to rescan before a poster refresh.</p>
      <form method="post" action="/save-media-locations">
        <div class="location-grid">
          <div>
            <label for="movie_locations">Movie folders</label>
            <textarea id="movie_locations" name="movie_locations" placeholder="D:\\Movies&#10;E:\\Movies 2&#10;F:\\Movies 3">{movie_locations_text}</textarea>
            <div class="location-actions">
              <button type="button" class="secondary browse-folder" data-target="movie_locations" data-kind="movies">Browse Movie Folder</button>
            </div>
          </div>
          <div>
            <label for="show_locations">Show folders</label>
            <textarea id="show_locations" name="show_locations" placeholder="D:\\Shows&#10;E:\\Shows 2&#10;F:\\Shows 3">{show_locations_text}</textarea>
            <div class="location-actions">
              <button type="button" class="secondary browse-folder" data-target="show_locations" data-kind="shows">Browse Show Folder</button>
            </div>
          </div>
        </div>
        <p style="margin-top:14px"><button type="submit">Save Media Locations</button></p>
      </form>
    </section>

    <section class="panel">
      <div class="row-title">6. Schedule</div>
      <p class="hint">Optional: create or replace a daily Windows Task Scheduler job using the all-poster refresh workflow.</p>
      <form method="post" action="/schedule-refresh" class="mini-form compact">
        <div>
          <label for="run_time">Daily run time</label>
          <input id="run_time" name="run_time" value="05:00" placeholder="05:00">
        </div>
        <button type="submit">Create Daily Schedule</button>
      </form>
    </section>
    """


def render_page(message="", status_id=""):
    libraries = get_libraries()
    status = system_status()
    active_tab = "posters" if status_id else load_ui_state()["active_tab"]
    saved_collection_count = len(load_registry())
    ready_checks = [
        status["refresh_helper"],
        status["python_ready"],
        status["kometa_dir"] and status["kometa_script"],
        status["venv"],
        status["config"],
        RUNTIME_DIR.exists(),
        status["plex_ok"],
        status["tmdb_key"] != "not set",
    ]
    ready_count = sum(1 for check in ready_checks if check)
    plex_state = "Connected" if status["plex_ok"] else "Needs setup"
    tmdb_state = "Saved" if status["tmdb_key"] != "not set" else "Needs key"
    library_options = "\n".join(
        f'<option value="{html.escape(lib)}" {"selected" if lib == "Movies" else ""}>{html.escape(lib)}</option>'
        for lib in libraries
    )
    status_panel = ""
    if status_id:
        status_panel = f"""
        <section class="panel">
          <div class="row-title">Run status</div>
          <p id="summary" class="statusline">Starting...</p>
          <div class="run-layout">
            <div class="progress-card">
              <div class="progress-poster-wrap">
                <img id="progressPoster" alt="" style="display:none">
                <div id="progressPlaceholder">Waiting for item progress...</div>
              </div>
              <div id="progressTitle" class="progress-title">Preparing...</div>
              <div class="progress-bar">
                <div id="progressFill"></div>
                <div id="progressText">0%</div>
              </div>
              <div id="progressLeft" class="progress-left">Movies/shows left: unknown</div>
            </div>
            <pre id="log">Loading...</pre>
          </div>
        </section>
        <script>
          const runId = {json.dumps(status_id)};
          async function refreshLog() {{
            const r = await fetch('/status?id=' + encodeURIComponent(runId));
            const data = await r.json();
            document.getElementById('summary').textContent = data.summary;
            document.getElementById('log').textContent = data.text;
            document.getElementById('log').scrollTop = document.getElementById('log').scrollHeight;
            const progress = data.progress || {{}};
            const fill = document.getElementById('progressFill');
            const text = document.getElementById('progressText');
            const title = document.getElementById('progressTitle');
            const left = document.getElementById('progressLeft');
            const poster = document.getElementById('progressPoster');
            const placeholder = document.getElementById('progressPlaceholder');
            if (progress.active) {{
              fill.style.width = progress.percent + '%';
              text.textContent = progress.percent + '%';
              title.textContent = progress.title || 'Processing item';
              left.textContent = progress.left + ' movies/shows left · ' + progress.current + ' / ' + progress.total;
              if (progress.poster_url) {{
                poster.src = progress.poster_url + '&t=' + encodeURIComponent(progress.title || '');
                poster.style.display = 'block';
                placeholder.style.display = 'none';
              }} else {{
                poster.style.display = 'none';
                placeholder.style.display = 'grid';
              }}
            }} else {{
              fill.style.width = '0%';
              text.textContent = '0%';
              title.textContent = 'Preparing...';
              left.textContent = 'Movies/shows left: unknown';
              poster.style.display = 'none';
              placeholder.style.display = 'grid';
            }}
            if (!data.running) {{
              document.body.classList.add(data.exit_code === 0 ? 'done' : 'failed');
            }} else {{
              setTimeout(refreshLog, 3000);
            }}
          }}
          refreshLog();
        </script>
        """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Kometa Helper</title>
  <style>
    :root {{
      color-scheme: dark;
      --bg: #0b1117;
      --panel: #121a22;
      --panel2: #17222d;
      --line: #24313d;
      --text: #edf4fa;
      --muted: #9aa9b6;
      --accent: #2dd4bf;
      --accent2: #60a5fa;
      --danger: #ff6b6b;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }}
    main {{
      width: min(1180px, calc(100vw - 32px));
      margin: 0 auto;
      padding: 24px 0 34px;
    }}
    .app-header {{
      display: flex;
      justify-content: space-between;
      gap: 18px;
      align-items: flex-end;
      border-bottom: 1px solid var(--line);
      padding: 0 0 18px;
      margin-bottom: 18px;
    }}
    .app-kicker {{
      margin: 0 0 8px;
      color: var(--accent);
      font-size: 12px;
      font-weight: 800;
      letter-spacing: 0.12em;
      text-transform: uppercase;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(28px, 4vw, 40px);
      letter-spacing: 0;
      line-height: 1.1;
    }}
    .sub {{
      margin: 8px 0 0;
      color: var(--muted);
      font-size: 15px;
      max-width: 700px;
    }}
    .app-status-pill {{
      flex: 0 0 auto;
      border: 1px solid var(--line);
      background: #0f171f;
      border-radius: 999px;
      padding: 9px 12px;
      color: var(--muted);
      font-size: 12px;
    }}
    .panel {{
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 8px;
      padding: 18px;
      margin: 14px 0;
      box-shadow: 0 10px 24px rgba(0,0,0,.18);
    }}
    label {{
      display: block;
      color: var(--muted);
      font-size: 13px;
      margin-bottom: 7px;
    }}
    input, select, textarea {{
      width: 100%;
      border: 1px solid var(--line);
      background: #0d151d;
      color: var(--text);
      border-radius: 6px;
      min-height: 42px;
      padding: 10px 12px;
      font-size: 15px;
      outline: none;
    }}
    textarea {{
      min-height: 156px;
      resize: vertical;
      line-height: 1.45;
      font-family: Consolas, "Cascadia Mono", monospace;
      white-space: pre;
      overflow: auto;
    }}
    input:focus, select:focus, textarea:focus {{ border-color: var(--accent2); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
    }}
    .wide {{ grid-column: 1 / -1; }}
    .setup-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .step-card {{
      border: 1px solid var(--line);
      background: #111820;
      border-radius: 8px;
      padding: 14px;
      min-height: 134px;
    }}
    .step-card h3 {{
      margin: 10px 0 6px;
      font-size: 16px;
    }}
    .step-card p {{
      margin: 0;
      color: var(--muted);
      font-size: 13px;
      overflow-wrap: anywhere;
    }}
    .badge {{
      display: inline-flex;
      min-height: 24px;
      align-items: center;
      border-radius: 999px;
      padding: 0 9px;
      font-size: 12px;
      font-weight: 700;
      border: 1px solid var(--line);
    }}
    .badge.ok {{
      color: #bff8d3;
      background: #123321;
      border-color: #23643e;
    }}
    .badge.warn {{
      color: #ffe0a3;
      background: #3a2b11;
      border-color: #785819;
    }}
    .mini-form {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) auto;
      gap: 12px;
      align-items: end;
      margin-top: 12px;
    }}
    .mini-form.compact {{
      grid-template-columns: minmax(0, 240px) auto;
      justify-content: start;
    }}
    .library-list {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
      margin-top: 12px;
    }}
    .location-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 16px;
      margin-top: 12px;
    }}
    .location-actions {{
      display: flex;
      justify-content: flex-end;
      gap: 8px;
      margin-top: 8px;
    }}
    .location-actions button {{
      min-height: 36px;
      font-size: 13px;
      padding: 0 12px;
    }}
    .check-row {{
      display: flex;
      align-items: center;
      gap: 10px;
      border: 1px solid var(--line);
      background: #101820;
      border-radius: 6px;
      padding: 10px 12px;
      margin: 0;
      color: var(--text);
    }}
    .check-row input {{
      width: auto;
      min-height: auto;
    }}
    .check-row small {{
      color: var(--muted);
      margin-left: 6px;
    }}
    button {{
      border: 0;
      background: var(--accent);
      color: #07130f;
      min-height: 42px;
      padding: 0 16px;
      border-radius: 6px;
      font-size: 15px;
      font-weight: 700;
      cursor: pointer;
    }}
    button.secondary {{
      background: #263340;
      color: var(--text);
      border: 1px solid var(--line);
    }}
    button.danger {{
      background: #3a1d23;
      color: #ffd5db;
      border: 1px solid #7f2b38;
    }}
    button:hover {{ filter: brightness(1.08); }}
    .hint {{
      color: var(--muted);
      font-size: 13px;
      margin: 8px 0 0;
    }}
    .msg {{
      border-left: 4px solid var(--accent2);
      padding: 12px 14px;
      background: #12202a;
      border-radius: 6px;
      margin-bottom: 16px;
      white-space: pre-wrap;
    }}
    .statusline {{
      border: 1px solid var(--line);
      background: #101820;
      border-radius: 6px;
      padding: 12px;
      color: var(--text);
      font-weight: 700;
    }}
    .run-layout {{
      display: grid;
      grid-template-columns: 260px minmax(0, 1fr);
      gap: 16px;
      align-items: stretch;
    }}
    .progress-card {{
      border: 1px solid var(--line);
      background: #101820;
      border-radius: 8px;
      padding: 14px;
      display: grid;
      align-content: start;
      gap: 12px;
      min-height: 420px;
    }}
    .progress-poster-wrap {{
      width: 100%;
      aspect-ratio: 2 / 3;
      border-radius: 6px;
      overflow: hidden;
      border: 1px solid #26313b;
      background: #080d11;
      display: grid;
      place-items: center;
    }}
    .progress-poster-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    #progressPlaceholder {{
      display: grid;
      place-items: center;
      height: 100%;
      padding: 18px;
      color: var(--muted);
      text-align: center;
      font-size: 13px;
    }}
    .progress-title {{
      color: var(--text);
      font-weight: 700;
      text-align: center;
      min-height: 42px;
      overflow-wrap: anywhere;
    }}
    .progress-bar {{
      position: relative;
      height: 28px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: #080d11;
      overflow: hidden;
    }}
    #progressFill {{
      height: 100%;
      width: 0%;
      background: linear-gradient(90deg, var(--accent), var(--accent2));
      transition: width .25s ease;
    }}
    #progressText {{
      position: absolute;
      inset: 0;
      display: grid;
      place-items: center;
      color: #f8fbff;
      font-size: 13px;
      font-weight: 800;
      text-shadow: 0 1px 2px rgba(0,0,0,.55);
    }}
    .progress-left {{
      color: var(--muted);
      text-align: center;
      font-size: 13px;
    }}
    .row-title {{
      font-size: 18px;
      font-weight: 700;
      margin-bottom: 8px;
    }}
    .collection-list {{
      display: grid;
      gap: 12px;
    }}
    .collection-card {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 16px;
      align-items: center;
      border: 1px solid var(--line);
      background: #111820;
      border-radius: 8px;
      padding: 16px;
    }}
    .collection-card h3 {{
      margin: 0 0 6px;
      font-size: 19px;
    }}
    .meta, .empty, .status-small {{
      margin: 4px 0;
      color: var(--muted);
      font-size: 13px;
    }}
    code {{
      background: #0a1015;
      border: 1px solid #25313c;
      border-radius: 4px;
      padding: 1px 5px;
      color: #9be7d8;
    }}
    .actions {{
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
      justify-content: flex-end;
    }}
    .actions form {{ margin: 0; }}
    .poster-management-actions {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
      margin-top: 14px;
    }}
    .poster-management-actions form {{
      margin: 0;
    }}
    pre {{
      background: #080d11;
      border: 1px solid #26313b;
      border-radius: 6px;
      padding: 14px;
      min-height: 240px;
      max-height: 520px;
      overflow: auto;
      white-space: pre-wrap;
      font-size: 13px;
      line-height: 1.45;
    }}
    .preview-modal {{
      position: fixed;
      inset: 0;
      z-index: 20;
      display: none;
      align-items: center;
      justify-content: center;
      padding: 22px;
      background: rgba(3, 7, 12, .76);
    }}
    .preview-modal.open {{ display: flex; }}
    .preview-dialog {{
      width: min(760px, 100%);
      max-height: min(820px, calc(100vh - 44px));
      overflow: auto;
      border: 1px solid var(--line);
      background: #111820;
      border-radius: 8px;
      box-shadow: 0 24px 80px rgba(0,0,0,.5);
      padding: 18px;
    }}
    .preview-dialog h2 {{ margin: 0 0 8px; font-size: 22px; }}
    .preview-options {{
      display: grid;
      gap: 10px;
      margin: 14px 0;
    }}
    .preview-option {{
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 10px;
      align-items: start;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 12px;
      background: #0c131a;
    }}
    .preview-option strong {{ display: block; margin-bottom: 3px; }}
    .preview-list {{
      margin: 12px 0 0;
      padding: 0;
      list-style: none;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px;
    }}
    .preview-list li {{
      border: 1px solid #26313b;
      border-radius: 6px;
      background: #0a1015;
      padding: 8px 10px;
      color: var(--muted);
      font-size: 13px;
    }}
    .preview-dialog footer {{
      display: flex;
      justify-content: flex-end;
      gap: 10px;
      margin-top: 16px;
      flex-wrap: wrap;
    }}
    .app-shell {{
      min-height: 100vh;
      display: grid;
      grid-template-columns: 238px minmax(0, 1fr);
      background:
        linear-gradient(180deg, rgba(96,165,250,.08), transparent 240px),
        var(--bg);
    }}
    .side-nav {{
      position: sticky;
      top: 0;
      height: 100vh;
      border-right: 1px solid var(--line);
      background: #080d12;
      padding: 22px 18px;
      display: flex;
      flex-direction: column;
      gap: 22px;
    }}
    .brand {{
      display: grid;
      grid-template-columns: 42px minmax(0, 1fr);
      gap: 12px;
      align-items: center;
    }}
    .brand-mark {{
      width: 42px;
      height: 42px;
      border-radius: 8px;
      display: grid;
      place-items: center;
      background: #142b32;
      color: #8df4e8;
      border: 1px solid #235d61;
      font-weight: 900;
      font-size: 14px;
    }}
    .brand strong {{
      display: block;
      font-size: 15px;
    }}
    .brand span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-top: 2px;
    }}
    .nav-links {{
      display: grid;
      gap: 6px;
    }}
    .nav-links button {{
      appearance: none;
      color: #c7d2de;
      background: transparent;
      min-height: 38px;
      display: flex;
      align-items: center;
      gap: 10px;
      border-radius: 8px;
      padding: 0 10px;
      border: 1px solid transparent;
      font-weight: 700;
      font-size: 14px;
      cursor: pointer;
      text-align: left;
    }}
    .nav-links button:hover,
    .nav-links button.active {{
      background: #101820;
      border-color: var(--line);
      color: var(--text);
      transform: none;
    }}
    .nav-links button.active {{
      border-color: #235d61;
      background: #102026;
    }}
    .nav-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--accent);
      box-shadow: 0 0 0 3px rgba(45,212,191,.12);
    }}
    .side-note {{
      margin-top: auto;
      border: 1px solid var(--line);
      background: #0f171f;
      border-radius: 8px;
      padding: 12px;
      color: var(--muted);
      font-size: 12px;
      line-height: 1.45;
    }}
    main.workspace {{
      width: min(1240px, calc(100vw - 238px));
      margin: 0;
      padding: 26px 28px 38px;
    }}
    .app-header {{
      border: 0;
      align-items: center;
      margin-bottom: 18px;
      padding: 0;
    }}
    .app-kicker {{
      color: #8df4e8;
      font-size: 11px;
      margin-bottom: 7px;
    }}
    h1 {{
      font-size: 34px;
    }}
    .app-status-pill {{
      border-radius: 8px;
      padding: 10px 12px;
      background: #101820;
    }}
    .metric-strip {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 12px;
      margin: 0 0 18px;
    }}
    .metric {{
      border: 1px solid var(--line);
      background: #101820;
      border-radius: 8px;
      padding: 14px;
    }}
    .metric span {{
      display: block;
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 6px;
    }}
    .metric strong {{
      display: block;
      font-size: 22px;
      line-height: 1.1;
    }}
    .section-stack {{
      scroll-margin-top: 20px;
    }}
    .tab-panel {{
      display: none;
    }}
    .tab-panel.active {{
      display: block;
    }}
    .section-heading {{
      display: flex;
      align-items: end;
      justify-content: space-between;
      gap: 14px;
      margin: 26px 0 10px;
    }}
    .section-heading h2 {{
      margin: 0;
      font-size: 20px;
      letter-spacing: 0;
    }}
    .section-heading p {{
      margin: 5px 0 0;
      color: var(--muted);
      font-size: 13px;
    }}
    .panel {{
      background: #101820;
      border-color: #24313d;
      box-shadow: none;
    }}
    .panel + .panel {{
      margin-top: 10px;
    }}
    .step-card, .collection-card, .check-row, .progress-card {{
      background: #0c131a;
    }}
    .poster-management-actions {{
      grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
    }}
    button {{
      transition: transform .12s ease, border-color .12s ease, background-color .12s ease, filter .12s ease;
    }}
    button:hover {{
      transform: translateY(-1px);
    }}
    @media (max-width: 720px) {{
      .app-header {{ align-items: flex-start; flex-direction: column; }}
      .grid {{ grid-template-columns: 1fr; }}
      .setup-grid {{ grid-template-columns: 1fr; }}
      .mini-form, .mini-form.compact {{ grid-template-columns: 1fr; }}
      .library-list {{ grid-template-columns: 1fr; }}
      .location-grid {{ grid-template-columns: 1fr; }}
      .run-layout {{ grid-template-columns: 1fr; }}
      .collection-card {{ grid-template-columns: 1fr; }}
      .actions {{ justify-content: flex-start; }}
      .poster-management-actions {{ grid-template-columns: 1fr; }}
      .preview-list {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 980px) {{
      .app-shell {{ grid-template-columns: 1fr; }}
      .side-nav {{
        position: static;
        height: auto;
        border-right: 0;
        border-bottom: 1px solid var(--line);
        padding: 14px 16px;
      }}
      .nav-links {{
        grid-template-columns: repeat(4, minmax(0, 1fr));
      }}
      .side-note {{ display: none; }}
      main.workspace {{
        width: 100%;
        padding: 20px 16px 30px;
      }}
      .metric-strip {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
  </style>
</head>
<body>
  <div class="app-shell">
    <aside class="side-nav">
      <div class="brand">
        <div class="brand-mark">KH</div>
        <div>
          <strong>Kometa Helper</strong>
          <span>Desktop control panel</span>
        </div>
      </div>
      <nav class="nav-links" aria-label="Main sections">
        <button type="button" class="tab-link {'active' if active_tab == 'setup' else ''}" data-tab="setup"><span class="nav-dot"></span>Setup</button>
        <button type="button" class="tab-link {'active' if active_tab == 'posters' else ''}" data-tab="posters"><span class="nav-dot"></span>Posters</button>
        <button type="button" class="tab-link {'active' if active_tab == 'collections' else ''}" data-tab="collections"><span class="nav-dot"></span>Collections</button>
        <button type="button" class="tab-link {'active' if active_tab == 'add' else ''}" data-tab="add"><span class="nav-dot"></span>Add IMDb</button>
      </nav>
      <div class="side-note">Local app. Your Plex token, saved collections, posters, and setup files stay on this PC.</div>
    </aside>
    <main class="workspace">
    <header class="app-header">
      <div>
        <p class="app-kicker">Local Plex + Kometa control</p>
        <h1>Kometa Helper</h1>
        <p class="sub">Manage setup, global overlays, poster refreshes, IMDb collections, logos, and collection posters from one place.</p>
      </div>
      <div class="app-status-pill">Data saved in Documents\\Kometa-Helper</div>
    </header>
    <section class="metric-strip" aria-label="Status summary">
      <div class="metric"><span>Setup</span><strong>{ready_count}/8 ready</strong></div>
      <div class="metric"><span>Plex</span><strong>{html.escape(plex_state)}</strong></div>
      <div class="metric"><span>TMDb</span><strong>{html.escape(tmdb_state)}</strong></div>
      <div class="metric"><span>Collections</span><strong>{saved_collection_count}</strong></div>
    </section>
    {f'<div class="msg">{html.escape(message)}</div>' if message else ''}
    <div id="tab-setup" class="section-stack tab-panel {'active' if active_tab == 'setup' else ''}" data-tab-panel="setup">
      <div class="section-heading">
        <div>
          <h2>Setup</h2>
          <p>Connect the pieces once, then run everything from here.</p>
        </div>
      </div>
      {render_setup_panels()}
    </div>
    <div id="tab-posters" class="section-stack tab-panel {'active' if active_tab == 'posters' else ''}" data-tab-panel="posters">
      <div class="section-heading">
        <div>
          <h2>Poster Tools</h2>
          <p>Apply your Kometa overlays and refresh poster artwork.</p>
        </div>
      </div>
    <section class="panel">
      <div class="row-title">Poster Management</div>
      <p class="hint">Configure global Kometa overlays once, then refresh every movie/show poster using that setup.</p>
      <div class="poster-management-actions">
        <form method="post" action="/refresh-all-posters">
          <button type="submit">Refresh All Posters</button>
        </form>
        <form method="get" action="/overlay-setup">
          <button type="submit" class="secondary">Global Overlay Setup</button>
        </form>
      </div>
    </section>
    </div>
    <div id="tab-collections" class="section-stack tab-panel {'active' if active_tab == 'collections' else ''}" data-tab-panel="collections">
      <div class="section-heading">
        <div>
          <h2>Collections</h2>
          <p>Update, edit posters for, or remove collections created by this app.</p>
        </div>
      </div>
      {render_saved_collections()}
    </div>
    <div id="tab-add" class="section-stack tab-panel {'active' if active_tab == 'add' else ''}" data-tab-panel="add">
      <div class="section-heading">
        <div>
          <h2>Add IMDb Collection</h2>
          <p>Paste an IMDb list ID and preview the setup before Kometa runs.</p>
        </div>
      </div>
    <section class="panel">
      <div class="row-title">Add New Collection</div>
      <form id="addCollectionForm" method="post" action="/create">
        <div class="grid">
          <div>
            <label for="library">Plex library</label>
            <select id="library" name="library">{library_options}</select>
          </div>
          <div>
            <label for="sort_by">IMDb order</label>
            <select id="sort_by" name="sort_by">
              <option value="custom.asc">IMDb list order</option>
              <option value="rating.desc">Highest IMDb rating first</option>
              <option value="title.asc">Title A-Z</option>
              <option value="release.desc">Newest release first</option>
            </select>
          </div>
          <div class="wide">
            <label for="list_input">IMDb list URL or ID</label>
            <input id="list_input" name="list_input" required placeholder="ls006405458 or https://www.imdb.com/list/ls006405458/">
            <p class="hint">Only the <strong>ls...</strong> part is needed. Full IMDb list URLs work too. The list must be public on IMDb. The collection tile will be hidden from the normal library grid.</p>
          </div>
          <div>
            <label for="collection_name">Collection name in Plex</label>
            <input id="collection_name" name="collection_name" required placeholder="James Bond Collection">
          </div>
          <div>
            <label for="limit">Item limit</label>
            <input id="limit" name="limit" type="number" min="0" value="0">
            <p class="hint">Use 0 for the whole IMDb list.</p>
          </div>
        </div>
        <p style="margin-top:18px"><button type="submit">Preview Setup</button></p>
      </form>
    </section>
    </div>
    <div id="previewModal" class="preview-modal" aria-hidden="true">
      <div class="preview-dialog" role="dialog" aria-modal="true" aria-labelledby="previewTitle">
        <h2 id="previewTitle">Review Collection Setup</h2>
        <p id="previewNote" class="hint">Loading preview...</p>
        <div id="previewSources" class="meta"></div>
        <div class="preview-options">
          <label class="preview-option">
            <input type="radio" name="preview_mode" value="tmdb" checked>
            <span>
              <strong>Recommended setup</strong>
              <span id="recommendedText" class="hint">Use detected TMDb collection data.</span>
            </span>
          </label>
          <label class="preview-option">
            <input type="radio" name="preview_mode" value="imdb">
            <span>
              <strong>IMDb list directly</strong>
              <span class="hint">Uses the pasted IMDb list order, but IMDb list lookup may fail when IMDb rejects Kometa's query.</span>
            </span>
          </label>
        </div>
        <ul id="previewItems" class="preview-list"></ul>
        <footer>
          <button id="previewCancel" type="button" class="secondary">Go Back</button>
          <button id="previewConfirm" type="button">Use This Setup</button>
        </footer>
      </div>
    </div>
    {status_panel}
    </main>
  </div>
  <script>
    const rememberedTab = {json.dumps(active_tab)};
    const tabButtons = Array.from(document.querySelectorAll('.tab-link'));
    const tabPanels = Array.from(document.querySelectorAll('[data-tab-panel]'));

    function setActiveTab(tab, persist = true) {{
      const valid = tabButtons.some(button => button.dataset.tab === tab);
      const nextTab = valid ? tab : 'collections';
      tabButtons.forEach(button => {{
        const active = button.dataset.tab === nextTab;
        button.classList.toggle('active', active);
        button.setAttribute('aria-selected', active ? 'true' : 'false');
      }});
      tabPanels.forEach(panel => {{
        panel.classList.toggle('active', panel.dataset.tabPanel === nextTab);
      }});
      if (persist) {{
        fetch('/ui-state', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
          body: new URLSearchParams({{active_tab: nextTab}}),
        }}).catch(() => {{}});
      }}
    }}

    tabButtons.forEach(button => {{
      button.addEventListener('click', () => setActiveTab(button.dataset.tab));
    }});
    setActiveTab(rememberedTab, false);

    function appendFolderPath(textarea, path) {{
      const cleanPath = (path || '').trim();
      if (!cleanPath) return;
      const lines = textarea.value
        .split(/\\r?\\n/)
        .map(line => line.trim())
        .filter(Boolean);
      const exists = lines.some(line => line.toLowerCase() === cleanPath.toLowerCase());
      if (!exists) lines.push(cleanPath);
      textarea.value = lines.join('\\n');
      textarea.dispatchEvent(new Event('input', {{bubbles: true}}));
    }}

    document.querySelectorAll('.browse-folder').forEach(button => {{
      button.addEventListener('click', async () => {{
        const target = document.getElementById(button.dataset.target);
        if (!target) return;
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = 'Choose Folder...';
        try {{
          const response = await fetch('/browse-folder', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
            body: new URLSearchParams({{kind: button.dataset.kind || 'movies'}}),
          }});
          const data = await response.json();
          if (!response.ok) throw new Error(data.error || 'Folder picker failed.');
          appendFolderPath(target, data.path);
        }} catch (error) {{
          alert(error.message || String(error));
        }} finally {{
          button.disabled = false;
          button.textContent = originalText;
        }}
      }});
    }});

    const addForm = document.getElementById('addCollectionForm');
    const modal = document.getElementById('previewModal');
    const previewNote = document.getElementById('previewNote');
    const previewSources = document.getElementById('previewSources');
    const previewItems = document.getElementById('previewItems');
    const recommendedText = document.getElementById('recommendedText');
    const previewCancel = document.getElementById('previewCancel');
    const previewConfirm = document.getElementById('previewConfirm');
    let previewReady = false;

    function setHidden(name, value) {{
      let input = addForm.querySelector('input[name="' + name + '"]');
      if (!input) {{
        input = document.createElement('input');
        input.type = 'hidden';
        input.name = name;
        addForm.appendChild(input);
      }}
      input.value = value;
    }}

    function openPreview() {{
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
    }}

    function closePreview() {{
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
    }}

    addForm.addEventListener('submit', async (event) => {{
      if (previewReady) return;
      event.preventDefault();
      previewNote.textContent = 'Checking the collection setup...';
      previewSources.textContent = '';
      previewItems.innerHTML = '';
      recommendedText.textContent = 'Use detected TMDb collection data.';
      openPreview();
      try {{
        const response = await fetch('/preview-collection', {{
          method: 'POST',
          headers: {{'Content-Type': 'application/x-www-form-urlencoded'}},
          body: new URLSearchParams(new FormData(addForm)),
        }});
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || 'Could not preview this setup.');
        const recommended = data.recommended_mode || 'imdb';
        const recommendedInput = modal.querySelector('input[name="preview_mode"][value="' + recommended + '"]');
        if (recommendedInput) recommendedInput.checked = true;
        recommendedText.textContent = data.builder === 'tmdb_collection'
          ? 'Use TMDb sources shown below, including any extra movie supplements.'
          : 'Use the IMDb list directly.';
        previewNote.textContent = data.note || 'Review the setup before creating this collection.';
        const sourceText = (data.sources || []).map((source) => {{
          const count = source.count ? ' · ' + source.count + ' items' : '';
          return source.kind + ' ' + source.label + count;
        }}).join(' | ');
        previewSources.textContent = sourceText || 'No external preview items were found.';
        previewItems.innerHTML = '';
        (data.items || []).forEach((item) => {{
          const li = document.createElement('li');
          li.textContent = item.title + (item.year ? ' (' + item.year + ')' : '');
          previewItems.appendChild(li);
        }});
        if (!(data.items || []).length) {{
          const li = document.createElement('li');
          li.textContent = 'IMDb list contents cannot be previewed locally right now.';
          previewItems.appendChild(li);
        }}
      }} catch (error) {{
        previewNote.textContent = error.message || String(error);
        previewSources.textContent = '';
      }}
    }});

    previewCancel.addEventListener('click', () => closePreview());
    previewConfirm.addEventListener('click', () => {{
      const mode = (modal.querySelector('input[name="preview_mode"]:checked') || {{value: 'auto'}}).value;
      setHidden('setup_mode', mode);
      setHidden('after_create', 'posters');
      previewReady = true;
      closePreview();
      addForm.submit();
    }});
  </script>
</body>
</html>"""


def parse_multipart_form(content_type, body):
    match = re.search(r'boundary="?([^";]+)"?', content_type or "")
    if not match:
        raise ValueError("Upload form boundary was missing.")
    boundary = ("--" + match.group(1)).encode("utf-8")
    fields = {}
    files = {}
    for part in body.split(boundary):
        part = part.strip()
        if not part or part == b"--":
            continue
        if part.endswith(b"--"):
            part = part[:-2].strip()
        if b"\r\n\r\n" not in part:
            continue
        header_blob, content = part.split(b"\r\n\r\n", 1)
        content = content.rstrip(b"\r\n")
        headers = header_blob.decode("utf-8", errors="replace")
        name_match = re.search(r'name="([^"]+)"', headers)
        if not name_match:
            continue
        name = name_match.group(1)
        filename_match = re.search(r'filename="([^"]*)"', headers)
        if filename_match:
            files[name] = {"filename": filename_match.group(1), "content": content}
        else:
            fields[name] = content.decode("utf-8", errors="replace")
    return fields, files


class Handler(BaseHTTPRequestHandler):
    def _send_html(self, body, code=200):
        encoded = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, body, code=200):
        encoded = json.dumps(body).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_file(self, path, content_type):
        path = Path(path)
        data = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/status":
            run_id = (query.get("id") or [""])[0]
            with RUNS_LOCK:
                run = RUNS.get(run_id)
            if not run:
                self._send_json({"running": False, "exit_code": 1, "text": "Run not found."}, 404)
                return
            proc = run["process"]
            exit_code = proc.poll()
            running = exit_code is None
            text = tail_text(run["log"])
            summary = summarize_log(text, running, exit_code)
            progress = parse_progress(text)
            if progress.get("active"):
                poster_file = progress_poster_path(progress.get("title"))
                progress["poster_url"] = (
                    "/progress-poster?title=" + quote(progress["title"]) if poster_file else ""
                )
            if not running and not run.get("finalized"):
                if run.get("registry_id"):
                    update_registry_status(run["registry_id"], summary)
                run["finalized"] = True
            if not running:
                text += f"\n\nFinished with exit code {exit_code}."
            self._send_json({"running": running, "exit_code": exit_code, "summary": summary, "text": text, "progress": progress})
            return
        if parsed.path == "/posters":
            entry_id = (query.get("id") or [""])[0]
            title_mode = (query.get("title_mode") or ["logo"])[0]
            self._send_html(render_poster_page(entry_id, title_mode=title_mode))
            return
        if parsed.path == "/search-logo":
            entry_id = (query.get("id") or [""])[0]
            title_mode = (query.get("title_mode") or ["logo"])[0]
            logo_query = (query.get("q") or [""])[0]
            self._send_html(render_poster_page(entry_id, title_mode=title_mode, logo_query=logo_query))
            return
        if parsed.path == "/search-poster":
            entry_id = (query.get("id") or [""])[0]
            title_mode = (query.get("title_mode") or ["logo"])[0]
            poster_query = (query.get("q") or [""])[0]
            self._send_html(render_poster_page(entry_id, title_mode=title_mode, poster_query=poster_query))
            return
        if parsed.path == "/template":
            entry_id = (query.get("id") or [""])[0]
            self._send_html(render_template_page(entry_id))
            return
        if parsed.path == "/media-template":
            media_query = (query.get("q") or [""])[0]
            rating_key = (query.get("key") or [""])[0]
            self._send_html(render_media_template_page(media_query, rating_key))
            return
        if parsed.path == "/overlay-setup":
            self._send_html(render_overlay_setup_page())
            return
        if parsed.path == "/media-thumb":
            rating_key = (query.get("key") or [""])[0]
            try:
                cache_path = media_template_cache_dir(rating_key) / "plex-thumb.jpg"
                fit_image(plex_item_base_poster_image(rating_key), (600, 900)).save(cache_path, "JPEG", quality=88)
                self._send_file(cache_path, "image/jpeg")
            except Exception:
                self.send_error(404)
            return
        if parsed.path == "/poster-image":
            entry_id = (query.get("id") or [""])[0]
            poster_id = (query.get("poster") or [""])[0]
            title_mode = (query.get("title_mode") or ["logo"])[0]
            try:
                self._send_file(poster_path(entry_id, poster_id, title_mode), "image/jpeg")
            except Exception:
                self.send_error(404)
            return
        if parsed.path == "/logo-result-image":
            entry_id = (query.get("id") or [""])[0]
            logo_id = (query.get("logo") or [""])[0]
            try:
                self._send_file(logo_result_path(entry_id, logo_id), "image/png")
            except Exception:
                self.send_error(404)
            return
        if parsed.path == "/poster-result-image":
            entry_id = (query.get("id") or [""])[0]
            poster_id = (query.get("poster") or [""])[0]
            try:
                self._send_file(searched_poster_path(entry_id, poster_id), "image/jpeg")
            except Exception:
                self.send_error(404)
            return
        if parsed.path == "/template-image":
            entry_id = (query.get("id") or [""])[0]
            entry = get_registry_entry(entry_id)
            try:
                if not entry:
                    raise ValueError("Saved collection was not found.")
                path = template_poster_path(entry_id)
                if not path.exists():
                    build_template_poster(entry, load_entry_template(entry)).save(path, "JPEG", quality=92)
                self._send_file(path, "image/jpeg")
            except Exception:
                self.send_error(404)
            return
        if parsed.path == "/media-template-image":
            rating_key = (query.get("key") or [""])[0]
            try:
                plex, item = get_plex_item(rating_key)
                title = getattr(item, "title", "Poster")
                path = media_template_poster_path(rating_key)
                build_media_template_poster(rating_key, load_media_template(rating_key, title)).save(path, "JPEG", quality=92)
                self._send_file(path, "image/jpeg")
            except Exception:
                self.send_error(404)
            return
        if parsed.path == "/progress-poster":
            title = (query.get("title") or [""])[0]
            path = progress_poster_path(title)
            if path:
                self._send_file(path, "image/jpeg")
            else:
                self.send_error(404)
            return
        self._send_html(render_page())

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path not in {
            "/ui-state",
            "/browse-folder",
            "/preview-collection",
            "/create",
            "/update",
            "/delete",
            "/apply-poster",
            "/upload-poster",
            "/select-logo",
            "/select-search-poster",
            "/save-template",
            "/apply-template",
            "/save-media-template",
            "/apply-media-template",
            "/save-overlays",
            "/refresh-all-posters",
            "/update-kometa",
            "/save-plex",
            "/save-tmdb",
            "/save-libraries",
            "/save-media-locations",
            "/schedule-refresh",
        }:
            self._send_html(render_page("Unknown action."), 404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw_body = self.rfile.read(length)
        if parsed.path == "/upload-poster":
            fields, files = parse_multipart_form(self.headers.get("Content-Type", ""), raw_body)
            data = {key: [value] for key, value in fields.items()}
        else:
            files = {}
            data = parse_qs(raw_body.decode("utf-8", errors="replace"))
        try:
            if parsed.path == "/ui-state":
                state = save_ui_state({"active_tab": (data.get("active_tab") or ["collections"])[0]})
                self._send_json({"ok": True, "active_tab": state["active_tab"]})
                return

            if parsed.path == "/browse-folder":
                kind = (data.get("kind") or ["movies"])[0]
                if kind not in {"movies", "shows"}:
                    raise ValueError("Unknown folder type.")
                self._send_json({"path": browse_for_media_folder(kind)})
                return

            if parsed.path == "/preview-collection":
                collection_name = (data.get("collection_name") or [""])[0].strip()
                list_id = extract_list_id((data.get("list_input") or [""])[0])
                limit_raw = (data.get("limit") or ["0"])[0].strip() or "0"
                limit = max(0, int(limit_raw))
                sort_by = (data.get("sort_by") or ["custom.asc"])[0]
                if not collection_name:
                    raise ValueError("Collection name is required.")
                if sort_by not in {"custom.asc", "rating.desc", "title.asc", "release.desc"}:
                    raise ValueError("Unsupported sort option.")
                self._send_json(preview_collection_setup(collection_name, list_id, limit, sort_by))
                return

            if parsed.path == "/refresh-all-posters":
                run_id = launch_all_poster_refresh()
                msg = "Started all-poster refresh.\n\nPlex scan requests will run for the saved media locations, then Kometa will update Movies and TV Shows."
                self._send_html(render_page(msg, run_id))
                return

            if parsed.path == "/update-kometa":
                run_id = launch_kometa_update()
                self._send_html(render_page("Started Kometa install/update.", run_id))
                return

            if parsed.path == "/save-plex":
                plex_url = (data.get("plex_url") or [""])[0]
                plex_token = (data.get("plex_token") or [""])[0].strip() or str(get_config_value(["plex", "token"], "") or "")
                msg = save_plex_settings(plex_url, plex_token)
                self._send_html(render_page(msg))
                return

            if parsed.path == "/save-tmdb":
                msg = save_tmdb_settings((data.get("tmdb_key") or [""])[0])
                self._send_html(render_page(msg))
                return

            if parsed.path == "/save-libraries":
                msg = save_library_selection(data.get("library") or [])
                self._send_html(render_page(msg))
                return

            if parsed.path == "/save-media-locations":
                msg = save_media_locations(
                    (data.get("movie_locations") or [""])[0],
                    (data.get("show_locations") or [""])[0],
                )
                self._send_html(render_page(msg))
                return

            if parsed.path == "/schedule-refresh":
                msg = create_refresh_schedule((data.get("run_time") or [""])[0])
                self._send_html(render_page(msg))
                return

            if parsed.path == "/save-overlays":
                msg = save_global_overlay_settings(
                    data.get("overlay") or [],
                    data.get("reset_overlays") or [],
                    data.get("overlay_position") or [],
                )
                self._send_html(render_overlay_setup_page(msg))
                return

            if parsed.path == "/create":
                library = (data.get("library") or ["Movies"])[0]
                collection_name = (data.get("collection_name") or [""])[0].strip()
                list_id = extract_list_id((data.get("list_input") or [""])[0])
                limit_raw = (data.get("limit") or ["0"])[0].strip() or "0"
                limit = max(0, int(limit_raw))
                sort_by = (data.get("sort_by") or ["custom.asc"])[0]
                setup_mode = (data.get("setup_mode") or ["auto"])[0]
                after_create = (data.get("after_create") or [""])[0]

                if not collection_name:
                    raise ValueError("Collection name is required.")
                if sort_by not in {"custom.asc", "rating.desc", "title.asc", "release.desc"}:
                    raise ValueError("Unsupported sort option.")
                if setup_mode not in {"auto", "tmdb", "imdb"}:
                    raise ValueError("Unsupported collection setup choice.")

                collection_file = write_collection_file(collection_name, list_id, limit, sort_by, setup_mode)
                entry = upsert_registry_entry(library, collection_name, list_id, limit, sort_by, collection_file)
                run_config, run_short_id = make_run_config(library, collection_file)
                run_id = launch_kometa(library, collection_name, list_id, run_config, run_short_id, entry["id"])
                msg = f"Saved collection:\n{collection_name}\n\nStarted Kometa for {library}."
                if after_create == "posters":
                    self._send_html(render_poster_page(entry["id"], msg))
                    return
                self._send_html(render_page(msg, run_id))
                return

            if parsed.path == "/save-media-template":
                rating_key = (data.get("key") or [""])[0]
                status = save_media_template_json(rating_key, (data.get("template_json") or [""])[0])
                self._send_html(render_media_template_page("", rating_key, status))
                return

            if parsed.path == "/apply-media-template":
                rating_key = (data.get("key") or [""])[0]
                status = apply_media_template_poster(rating_key, (data.get("template_json") or [""])[0])
                self._send_html(render_media_template_page("", rating_key, status))
                return

            entry_id = (data.get("id") or [""])[0]
            entry = get_registry_entry(entry_id)
            if not entry:
                raise ValueError("Saved collection was not found.")

            if parsed.path == "/apply-poster":
                poster_id = (data.get("poster") or [""])[0]
                title_mode = (data.get("title_mode") or ["logo"])[0]
                status = apply_collection_poster(entry, poster_id, title_mode)
                self._send_html(render_poster_page(entry_id, status, title_mode))
                return

            if parsed.path == "/select-logo":
                logo_id = (data.get("logo") or [""])[0]
                status = select_collection_logo(entry, logo_id)
                self._send_html(render_poster_page(entry_id, status, "logo"))
                return

            if parsed.path == "/select-search-poster":
                poster_id = (data.get("poster") or [""])[0]
                status = select_searched_poster(entry, poster_id)
                self._send_html(render_poster_page(entry_id, status))
                return

            if parsed.path == "/upload-poster":
                upload = files.get("poster_file") or {}
                status = apply_custom_poster(entry, upload.get("filename", ""), upload.get("content", b""))
                self._send_html(render_poster_page(entry_id, status))
                return

            if parsed.path == "/save-template":
                status = save_template_json(entry, (data.get("template_json") or [""])[0])
                self._send_html(render_template_page(entry_id, status))
                return

            if parsed.path == "/apply-template":
                status = apply_template_poster(entry, (data.get("template_json") or [""])[0])
                self._send_html(render_template_page(entry_id, status))
                return

            if parsed.path == "/update":
                collection_file = write_collection_file(
                    entry["collection_name"],
                    entry["list_id"],
                    int(entry.get("limit", 0) or 0),
                    entry.get("sort_by", "custom.asc"),
                )
                run_config, run_short_id = make_run_config(entry["library"], collection_file)
                update_registry_status(entry_id, "Update started")
                run_id = launch_kometa(
                    entry["library"],
                    entry["collection_name"],
                    entry["list_id"],
                    run_config,
                    run_short_id,
                    entry_id,
                )
                msg = f"Updating collection:\n{entry['collection_name']}"
                self._send_html(render_page(msg, run_id))
                return

            if parsed.path == "/delete":
                plex_message = delete_plex_collection(entry["library"], entry["collection_name"])
                file_path = Path(entry.get("file", ""))
                if file_path.exists():
                    file_path.unlink()
                remove_registry_entry(entry_id)
                self._send_html(render_page(f"Deleted {entry['collection_name']}.\n{plex_message}"))
                return
        except Exception as e:
            if parsed.path in {"/preview-collection", "/browse-folder", "/ui-state"}:
                self._send_json({"error": str(e)}, 400)
                return
            self._send_html(render_page(str(e)), 400)

    def log_message(self, fmt, *args):
        return


def find_port(start=7192, end=7200):
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free local port found between 7192 and 7200.")


def run_desktop_window(server, url):
    try:
        import webview
    except Exception as exc:
        print(f"Desktop window unavailable, falling back to browser: {exc}")
        return False

    threading.Thread(target=server.serve_forever, daemon=True).start()
    webview.create_window(
        "Kometa Helper",
        url,
        width=1280,
        height=860,
        min_size=(980, 680),
    )
    try:
        webview.start()
    finally:
        server.shutdown()
        server.server_close()
    return True


def main():
    migrate_legacy_runtime()
    if "--self-test" in sys.argv:
        html_text = render_page()
        status = system_status()
        print("Kometa Helper self-test OK")
        print(f"Rendered bytes: {len(html_text.encode('utf-8'))}")
        print(f"Kometa version: {status.get('kometa_version')}")
        print(f"Plex connected: {status.get('plex_ok')}")
        print(f"Runtime data: {RUNTIME_DIR}")
        return

    port = find_port()
    url = f"http://127.0.0.1:{port}"
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Kometa Helper running at {url}")

    if "--browser" not in sys.argv and "--no-browser" not in sys.argv:
        if run_desktop_window(server, url):
            return

    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
        print("Opening Kometa Helper in your browser.")
    else:
        print("Browser launch disabled. Open the URL above manually.")
    print("Keep this window open while using the UI. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

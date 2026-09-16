param(
  [Parameter(Mandatory = $true)]
  [string]$ConfigPath,

  [Parameter(Mandatory = $true)]
  [string]$LogFile,

  [Parameter(Mandatory = $false)]
  [string]$LocationsJson
)

function Write-RunLog {
  param([string]$Message)
  $stamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -LiteralPath $LogFile -Value "[$stamp] $Message"
}

function Get-ConfigValue {
  param(
    [string]$Block,
    [string]$Key
  )
  $match = [regex]::Match($Block, "(?m)^[ \t]+$([regex]::Escape($Key)):\s*(?<value>.+?)\s*$")
  if ($match.Success) {
    return $match.Groups["value"].Value.Trim().Trim("'`"").TrimEnd("/")
  }
  return $null
}

$expectedMoviePaths = @()
$expectedShowPaths = @()

if ($LocationsJson -and (Test-Path -LiteralPath $LocationsJson)) {
  try {
    $locations = Get-Content -LiteralPath $LocationsJson -Raw | ConvertFrom-Json
    $expectedMoviePaths = @($locations.movies | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    $expectedShowPaths = @($locations.shows | ForEach-Object { [string]$_ } | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
    Write-RunLog "Loaded media locations from $LocationsJson."
  } catch {
    Write-RunLog "Could not read media locations JSON: $($_.Exception.Message)"
  }
}

if ($expectedMoviePaths.Count -eq 0) {
  Write-RunLog "No saved movie folder list was found. Add movie folders in Kometa Helper > Setup > Media Locations."
}

if ($expectedShowPaths.Count -eq 0) {
  Write-RunLog "No saved show folder list was found. Add show folders in Kometa Helper > Setup > Media Locations."
}

if (-not (Test-Path -LiteralPath $ConfigPath)) {
  throw "Kometa config was not found: $ConfigPath"
}

$configText = Get-Content -LiteralPath $ConfigPath -Raw
$plexBlock = [regex]::Match($configText, "(?ms)^plex:\s*\r?\n(?<body>(?:^[ \t]+.*\r?\n?)*)").Groups["body"].Value

if ([string]::IsNullOrWhiteSpace($plexBlock)) {
  throw "Could not find the plex: block in the Kometa config."
}

$plexUrl = Get-ConfigValue -Block $plexBlock -Key "url"
$plexToken = Get-ConfigValue -Block $plexBlock -Key "token"

if ([string]::IsNullOrWhiteSpace($plexUrl) -or [string]::IsNullOrWhiteSpace($plexToken)) {
  throw "Plex URL/token is blank in the Kometa config."
}

$headers = @{ "X-Plex-Token" = $plexToken }
$sections = Invoke-RestMethod -Uri "$plexUrl/library/sections" -Headers $headers -TimeoutSec 30
$targetSections = @($sections.MediaContainer.Directory | Where-Object { $_.type -in @("movie", "show") })

if ($targetSections.Count -eq 0) {
  Write-RunLog "No Plex movie/show library sections were found."
  return
}

Write-RunLog "Refreshing Plex movie/show libraries from $plexUrl."

foreach ($section in $targetSections) {
  $title = [string]$section.title
  $type = [string]$section.type
  $key = [string]$section.key
  $configuredLocations = @($section.Location | ForEach-Object { [string]$_.path })
  $expectedPaths = if ($type -eq "movie") { $expectedMoviePaths } else { $expectedShowPaths }

  Write-RunLog "Triggering full Plex refresh for '$title' ($type, key $key). Configured locations: $($configuredLocations -join '; ')"
  Invoke-RestMethod -Uri "$plexUrl/library/sections/$key/refresh?force=1" -Headers $headers -TimeoutSec 30 | Out-Null

  foreach ($path in $expectedPaths) {
    $exists = Test-Path -LiteralPath $path
    $isConfigured = $configuredLocations -contains $path

    if ($exists -and $isConfigured) {
      $encodedPath = [uri]::EscapeDataString($path)
      Write-RunLog "Triggering path refresh for '$title': $path"
      Invoke-RestMethod -Uri "$plexUrl/library/sections/$key/refresh?force=1&path=$encodedPath" -Headers $headers -TimeoutSec 30 | Out-Null
    } elseif ($exists -and -not $isConfigured) {
      Write-RunLog "Folder exists but is not attached to Plex library '$title' yet: $path"
    } elseif (-not $exists) {
      Write-RunLog "Folder does not exist yet: $path"
    }
  }
}

Write-RunLog "Plex refresh requests completed for $($targetSections.Count) movie/show section(s)."

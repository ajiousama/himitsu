param(
    [string]$BaseM3U = "freewifi",
    [string]$LocalStationM3U = "local_station_private.m3u",
    [string]$OutM3U = "freewifi_with_local_station.m3u"
)

$ErrorActionPreference = "Stop"

function Read-TextUtf8BomAware {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        throw "File not found: $Path"
    }
    return [System.IO.File]::ReadAllText((Resolve-Path -LiteralPath $Path), [System.Text.UTF8Encoding]::new($true))
}

function Write-TextUtf8NoBom {
    param(
        [string]$Path,
        [string]$Text
    )
    [System.IO.File]::WriteAllText((Join-Path (Get-Location) $Path), $Text, [System.Text.UTF8Encoding]::new($false))
}

if (-not (Test-Path -LiteralPath $BaseM3U)) {
    throw "Base M3U not found: $BaseM3U"
}

$baseText = Read-TextUtf8BomAware -Path $BaseM3U
$baseText = $baseText.TrimEnd() + "`n"

if (-not (Test-Path -LiteralPath $LocalStationM3U)) {
    Write-Host "Local station M3U not found. Nothing to merge: $LocalStationM3U"
    Write-TextUtf8NoBom -Path $OutM3U -Text $baseText
    Write-Host "Wrote base-only output: $OutM3U"
    exit 0
}

$localText = Read-TextUtf8BomAware -Path $LocalStationM3U
$localLines = $localText -split "`r?`n" | Where-Object {
    $line = $_.Trim()
    $line -and $line -ne "#EXTM3U" -and -not $line.StartsWith("# Generated entries:") -and -not $line.StartsWith("# Skipped blank stream_url rows:")
}

$merged = New-Object System.Collections.Generic.List[string]
$merged.Add($baseText.TrimEnd())
$merged.Add("")
$merged.Add("# --- Optional local station private M3U ---")
foreach ($line in $localLines) {
    $merged.Add($line)
}
$merged.Add("")
$merged.Add("# --- End optional local station private M3U ---")

Write-TextUtf8NoBom -Path $OutM3U -Text (($merged -join "`n") + "`n")
Write-Host "Merged optional local station M3U."
Write-Host "Base:  $BaseM3U"
Write-Host "Local: $LocalStationM3U"
Write-Host "Out:   $OutM3U"

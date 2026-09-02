$ErrorActionPreference = 'Continue'

$venues = @(
  @{ Code='01kiryu';       Id='boat.kiryu' },
  @{ Code='02toda';        Id='boat.toda' },
  @{ Code='03edogawa';     Id='boat.edogawa' },
  @{ Code='04heiwajima';   Id='boat.heiwajima' },
  @{ Code='05tamagawa';    Id='boat.tamagawa' },
  @{ Code='06hamanako';    Id='boat.hamanako' },
  @{ Code='07gamagori';    Id='boat.gamagori' },
  @{ Code='08tokoname';    Id='boat.tokoname' },
  @{ Code='09tsu';         Id='boat.tsu' },
  @{ Code='10mikuni';      Id='boat.mikuni' },
  @{ Code='11biwako';      Id='boat.biwako' },
  @{ Code='12suminoe';     Id='boat.suminoe' },
  @{ Code='13amagasaki';   Id='boat.amagasaki' },
  @{ Code='14naruto';      Id='boat.naruto' },
  @{ Code='15marugame';    Id='boat.marugame' },
  @{ Code='16kojima';      Id='boat.kojima' },
  @{ Code='17miyajima';    Id='boat.miyajima' },
  @{ Code='18tokuyama';    Id='boat.tokuyama' },
  @{ Code='19shimonoseki'; Id='boat.shimonoseki' },
  @{ Code='20wakamatsu';   Id='boat.wakamatsu' },
  @{ Code='21ashiya';      Id='boat.ashiya' },
  @{ Code='22fukuoka';     Id='boat.fukuoka' },
  @{ Code='23karatsu';     Id='boat.karatsu' },
  @{ Code='24omura';       Id='boat.omura' }
)

$ua = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'
$settingHeaders = @{
  'User-Agent' = $ua
  'Accept' = 'application/json,text/plain,*/*'
  'Referer' = 'https://front.player.boatrace-cdn.jp/'
}

function New-PlaybackHeaders([string]$apiKey) {
  $h = @{
    'Accept'     = 'application/json'
    'Origin'     = 'https://front.player.boatrace-cdn.jp'
    'Referer'    = 'https://front.player.boatrace-cdn.jp/'
    'User-Agent' = $ua
  }
  if (-not [string]::IsNullOrWhiteSpace($apiKey)) {
    $h['X-Streaks-Api-Key'] = $apiKey
  }
  return $h
}

function Get-HttpStatus($err) {
  try { return [int]$err.Exception.Response.StatusCode } catch { return $null }
}

function Get-CurrentSetting([string]$stadium) {
  $epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $url = "https://front.player.boatrace-cdn.jp/setting/live/$stadium/setting.json?t=$epoch"
  try {
    $r = Invoke-WebRequest -Uri $url -Headers $settingHeaders -TimeoutSec 12 -ErrorAction Stop
    return ($r.Content | ConvertFrom-Json)
  }
  catch {
    $status = Get-HttpStatus $_
    if ($status) { Write-Host "SETTING WAIT $stadium: HTTP $status" }
    else { Write-Host "SETTING WAIT $stadium: $($_.Exception.GetType().Name)" }
    return $null
  }
}

function Test-TimeWindow($item) {
  if ($null -eq $item) { return $false }
  try {
    $now = [DateTimeOffset]::UtcNow
    $start = [DateTimeOffset]::Parse([string]$item.start_at)
    $end = [DateTimeOffset]::Parse([string]$item.end_at)
    return ($now -ge $start -and $now -le $end)
  }
  catch {
    # If BOATCAST changes timestamp formatting, still let playback decide.
    return $true
  }
}

function Resolve-Playback([string]$refId, [string]$apiKey) {
  if ([string]::IsNullOrWhiteSpace($refId)) { return '' }
  $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:${refId}?audio_only=false"

  # Current BOATCAST player works as a public front player. Try without a
  # secret first; retain the optional secret only as a compatibility retry.
  foreach ($key in @('', $apiKey)) {
    if ($key -ne '' -and [string]::IsNullOrWhiteSpace($key)) { continue }
    try {
      $r = Invoke-WebRequest -Uri $url -Headers (New-PlaybackHeaders $key) -TimeoutSec 12 -ErrorAction Stop
      $j = $r.Content | ConvertFrom-Json
      if ($j.sources -and $j.sources.Count -gt 0 -and $j.sources[0].src) {
        return ([string]$j.sources[0].src).Trim()
      }
    }
    catch {
      $status = Get-HttpStatus $_
      if ($status -and $status -notin @(401,403,404)) {
        Write-Host "PLAYBACK $refId: HTTP $status"
      }
    }
    if ([string]::IsNullOrWhiteSpace($apiKey)) { break }
  }
  return ''
}

$apiKey = [Environment]::GetEnvironmentVariable('BOATRACE_STREAKS_API_KEY')
$result = [ordered]@{}

foreach ($v in $venues) {
  $setting = Get-CurrentSetting $v.Code
  if ($null -eq $setting) { continue }

  # The current BOATCAST player is opened with sourceType=mix and dvr=1.
  # Prefer exactly that public setting, then gracefully fall back to the
  # live mix and broadcast-only variants if the service changes per venue.
  $candidates = @('mix_dvr', 'mix_live', 'br_dvr', 'br_live')
  $resolved = ''
  $usedRef = ''

  foreach ($name in $candidates) {
    $prop = $setting.PSObject.Properties[$name]
    if ($null -eq $prop) { continue }
    $item = $prop.Value
    if (-not (Test-TimeWindow $item)) { continue }
    $refId = [string]$item.ref_id
    if ([string]::IsNullOrWhiteSpace($refId)) { continue }

    $resolved = Resolve-Playback $refId $apiKey
    if ($resolved) {
      $usedRef = $refId
      break
    }
  }

  if ($resolved) {
    $result[$v.Code] = $resolved
    Write-Host "STREAM OK $($v.Id) ref=$usedRef"
  }
  else {
    Write-Host "STREAM WAIT $($v.Id): no active BOATCAST source"
  }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$json = $result | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'boat_stream_urls.json'), $json, $utf8)
Write-Host "BOAT stream URLs fetched: $($result.Count)"
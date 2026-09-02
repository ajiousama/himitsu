$ErrorActionPreference = 'Continue'

$venues = @(
  @{ Stadium='01'; Code='01kiryu';       Id='boat.kiryu' },
  @{ Stadium='02'; Code='02toda';        Id='boat.toda' },
  @{ Stadium='03'; Code='03edogawa';     Id='boat.edogawa' },
  @{ Stadium='04'; Code='04heiwajima';   Id='boat.heiwajima' },
  @{ Stadium='05'; Code='05tamagawa';    Id='boat.tamagawa' },
  @{ Stadium='06'; Code='06hamanako';    Id='boat.hamanako' },
  @{ Stadium='07'; Code='07gamagori';    Id='boat.gamagori' },
  @{ Stadium='08'; Code='08tokoname';    Id='boat.tokoname' },
  @{ Stadium='09'; Code='09tsu';         Id='boat.tsu' },
  @{ Stadium='10'; Code='10mikuni';      Id='boat.mikuni' },
  @{ Stadium='11'; Code='11biwako';      Id='boat.biwako' },
  @{ Stadium='12'; Code='12suminoe';     Id='boat.suminoe' },
  @{ Stadium='13'; Code='13amagasaki';   Id='boat.amagasaki' },
  @{ Stadium='14'; Code='14naruto';      Id='boat.naruto' },
  @{ Stadium='15'; Code='15marugame';    Id='boat.marugame' },
  @{ Stadium='16'; Code='16kojima';      Id='boat.kojima' },
  @{ Stadium='17'; Code='17miyajima';    Id='boat.miyajima' },
  @{ Stadium='18'; Code='18tokuyama';    Id='boat.tokuyama' },
  @{ Stadium='19'; Code='19shimonoseki'; Id='boat.shimonoseki' },
  @{ Stadium='20'; Code='20wakamatsu';   Id='boat.wakamatsu' },
  @{ Stadium='21'; Code='21ashiya';      Id='boat.ashiya' },
  @{ Stadium='22'; Code='22fukuoka';     Id='boat.fukuoka' },
  @{ Stadium='23'; Code='23karatsu';     Id='boat.karatsu' },
  @{ Stadium='24'; Code='24omura';       Id='boat.omura' }
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
    if ($status) { Write-Host "SETTING WAIT ${stadium}: HTTP $status" }
    else { Write-Host "SETTING WAIT ${stadium}: $($_.Exception.GetType().Name)" }
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
  catch { return $true }
}

function Resolve-Playback([string]$refId, [string]$apiKey) {
  if ([string]::IsNullOrWhiteSpace($refId)) { return '' }
  $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:${refId}?audio_only=false"
  $keys = @('')
  if (-not [string]::IsNullOrWhiteSpace($apiKey)) { $keys += $apiKey }
  foreach ($key in $keys) {
    try {
      $r = Invoke-WebRequest -Uri $url -Headers (New-PlaybackHeaders $key) -TimeoutSec 12 -ErrorAction Stop
      $j = $r.Content | ConvertFrom-Json
      if ($j.sources -and $j.sources.Count -gt 0 -and $j.sources[0].src) {
        return ([string]$j.sources[0].src).Trim()
      }
    }
    catch {
      $status = Get-HttpStatus $_
      if ($status -and $status -notin @(401,403,404)) { Write-Host "PLAYBACK ${refId}: HTTP $status" }
    }
  }
  return ''
}

$apiKey = [Environment]::GetEnvironmentVariable('BOATRACE_STREAKS_API_KEY')
$result = [ordered]@{}

foreach ($v in $venues) {
  $setting = Get-CurrentSetting $v.Stadium
  if ($null -eq $setting) { continue }

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
    if ($resolved) { $usedRef = $refId; break }
  }

  if ($resolved) {
    $result[$v.Code] = $resolved
    Write-Host "STREAM OK $($v.Id) stadium=$($v.Stadium) ref=$usedRef"
  }
  else {
    Write-Host "STREAM WAIT $($v.Id): no active BOATCAST source"
  }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$json = $result | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'boat_stream_urls.json'), $json, $utf8)
Write-Host "BOAT stream URLs fetched: $($result.Count)"
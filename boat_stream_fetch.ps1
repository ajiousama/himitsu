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
  if (-not [string]::IsNullOrWhiteSpace($apiKey)) { $h['X-Streaks-Api-Key'] = $apiKey }
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
  } catch { return $true }
}

function Resolve-Playback([string]$refId, [string]$apiKey) {
  if ([string]::IsNullOrWhiteSpace($refId)) { return '' }
  $mediaIds = @("ref:$refId", $refId)
  $keys = @('')
  if (-not [string]::IsNullOrWhiteSpace($apiKey)) { $keys += $apiKey }

  foreach ($mediaId in $mediaIds) {
    $escaped = [Uri]::EscapeDataString($mediaId)
    foreach ($encoded in @($mediaId, $escaped)) {
      $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/${encoded}?audio_only=false"
      foreach ($key in $keys) {
        try {
          $r = Invoke-WebRequest -Uri $url -Headers (New-PlaybackHeaders $key) -TimeoutSec 12 -ErrorAction Stop
          $j = $r.Content | ConvertFrom-Json
          if ($j.sources -and $j.sources.Count -gt 0 -and $j.sources[0].src) {
            return ([string]$j.sources[0].src).Trim()
          }
          Write-Host "PLAYBACK EMPTY ref=$refId media=$encoded"
        }
        catch {
          $status = Get-HttpStatus $_
          if ($status) { Write-Host "PLAYBACK WAIT ref=$refId media=$encoded HTTP=$status" }
          else { Write-Host "PLAYBACK WAIT ref=$refId media=$encoded type=$($_.Exception.GetType().Name)" }
        }
      }
    }
  }
  return ''
}

$apiKey = [Environment]::GetEnvironmentVariable('BOATRACE_STREAKS_API_KEY')
$result = [ordered]@{}
foreach ($v in $venues) {
  $setting = Get-CurrentSetting $v.Code
  if ($null -eq $setting) { continue }

  $resolved = ''
  $usedRef = ''
  foreach ($name in @('mix_dvr', 'mix_live', 'br_dvr', 'br_live')) {
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
    Write-Host "STREAM OK $($v.Id) ref=$usedRef"
  } else {
    Write-Host "STREAM WAIT $($v.Id): no active BOATCAST source"
  }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$json = $result | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'boat_stream_urls.json'), $json, $utf8)
Write-Host "BOAT stream URLs fetched: $($result.Count)"
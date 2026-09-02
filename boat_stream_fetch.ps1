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
  } catch {
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

function Test-PlaybackKey([string]$refId, [string]$candidate) {
  if ([string]::IsNullOrWhiteSpace($refId) -or [string]::IsNullOrWhiteSpace($candidate)) { return $false }
  $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:${refId}?audio_only=false"
  try {
    $r = Invoke-WebRequest -Uri $url -Headers (New-PlaybackHeaders $candidate) -TimeoutSec 10 -ErrorAction Stop
    $j = $r.Content | ConvertFrom-Json
    return [bool]($j.sources -and $j.sources.Count -gt 0 -and $j.sources[0].src)
  } catch { return $false }
}

function Get-PlayerBodies {
  $playerUrl = 'https://front.player.boatrace-cdn.jp/player/live?service=boatcast&stadium=12suminoe&sourceType=mix&dvr=1&audioMode=0&autoplay=1&bitrate=high'
  $headers = @{ 'User-Agent'=$ua; 'Accept'='text/html,application/xhtml+xml,application/javascript,*/*' }
  $bodies = New-Object System.Collections.Generic.List[string]
  try {
    $page = Invoke-WebRequest -Uri $playerUrl -Headers $headers -TimeoutSec 15 -ErrorAction Stop
    $bodies.Add([string]$page.Content)
    $base = [Uri]$playerUrl
    $seen = @{}
    foreach ($m in [regex]::Matches([string]$page.Content, '(?is)<script[^>]+src=["'']([^"'']+)["'']')) {
      if ($bodies.Count -ge 32) { break }
      try {
        $src = [Uri]::new($base, $m.Groups[1].Value).AbsoluteUri
        if ($seen.ContainsKey($src)) { continue }
        $seen[$src] = $true
        $js = Invoke-WebRequest -Uri $src -Headers $headers -TimeoutSec 12 -ErrorAction Stop
        $bodies.Add([string]$js.Content)
      } catch {}
    }
  } catch {}
  return ,$bodies.ToArray()
}

function Discover-PlaybackKey([string]$probeRef) {
  $configured = [Environment]::GetEnvironmentVariable('BOATRACE_STREAKS_API_KEY')
  if (-not [string]::IsNullOrWhiteSpace($configured) -and (Test-PlaybackKey $probeRef $configured)) {
    Write-Host 'BOATCAST playback key: configured key validated'
    return $configured
  }

  $candidates = New-Object System.Collections.Generic.List[string]
  $seen = @{}
  foreach ($body in (Get-PlayerBodies)) {
    foreach ($pattern in @(
      '(?<![A-Za-z0-9_$])Wa\s*=\s*["'']([^"'']{8,200})["'']',
      '(?i)apiKey\s*[:=]\s*["'']([^"'']{8,200})["'']',
      '(?i)x-streaks-api-key[^"'']*["'']([^"'']{8,200})["'']'
    )) {
      foreach ($m in [regex]::Matches([string]$body, $pattern)) {
        $c = [string]$m.Groups[1].Value
        if (-not $seen.ContainsKey($c)) { $seen[$c] = $true; $candidates.Add($c) }
      }
    }
  }
  Write-Host "BOATCAST playback key candidates=$($candidates.Count)"
  foreach ($c in $candidates) {
    if (Test-PlaybackKey $probeRef $c) {
      Write-Host 'BOATCAST playback key: public player key auto-detected and validated'
      return $c
    }
  }
  return ''
}

function Resolve-Playback([string]$refId, [string]$apiKey) {
  if ([string]::IsNullOrWhiteSpace($refId)) { return '' }
  $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:${refId}?audio_only=false"
  try {
    $r = Invoke-WebRequest -Uri $url -Headers (New-PlaybackHeaders $apiKey) -TimeoutSec 12 -ErrorAction Stop
    $j = $r.Content | ConvertFrom-Json
    if ($j.sources -and $j.sources.Count -gt 0 -and $j.sources[0].src) {
      return ([string]$j.sources[0].src).Trim()
    }
  } catch {
    $status = Get-HttpStatus $_
    if ($status) { Write-Host "PLAYBACK WAIT ref=$refId HTTP=$status" }
  }
  return ''
}

# Use one currently scheduled BOATCAST ref only to validate the public player
# API key. The key value itself is never printed to Actions logs.
$probeSetting = Get-CurrentSetting '12suminoe'
$probeRef = ''
if ($probeSetting) {
  foreach ($n in @('mix_dvr','mix_live','br_dvr','br_live')) {
    $p = $probeSetting.PSObject.Properties[$n]
    if ($p -and (Test-TimeWindow $p.Value)) { $probeRef = [string]$p.Value.ref_id; if ($probeRef) { break } }
  }
}
$apiKey = ''
if ($probeRef) { $apiKey = Discover-PlaybackKey $probeRef }
if ([string]::IsNullOrWhiteSpace($apiKey)) {
  Write-Host '::warning::BOATCAST playback API key could not be validated from current public player'
}

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
$ErrorActionPreference = 'Continue'

$jst = [System.TimeZoneInfo]::FindSystemTimeZoneById('Asia/Tokyo')
$nowJst = [System.TimeZoneInfo]::ConvertTime([DateTimeOffset]::UtcNow, $jst)
$d = $nowJst.ToString('yyyyMMdd')

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

function New-PlaybackHeaders([string]$apiKey) {
  $h = @{
    'Accept'     = 'application/json'
    'Origin'     = 'https://players.streaks.jp'
    'Referer'    = 'https://front.player.boatrace-cdn.jp/'
    'User-Agent' = $ua
  }
  if (-not [string]::IsNullOrWhiteSpace($apiKey)) {
    $h['X-Streaks-Api-Key'] = $apiKey
  }
  return $h
}

function Test-StreaksKey([string]$candidate) {
  if ([string]::IsNullOrWhiteSpace($candidate)) { return $false }
  # Use several current-day venue refs. 200 with or without sources proves that
  # the key is accepted; 403 means the candidate is not the BOATCAST key.
  foreach ($v in $venues) {
    $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:lm-br-$($v.Code)-tokyo-$d?audio_only=false"
    try {
      $r = Invoke-WebRequest -Uri $url -Headers (New-PlaybackHeaders $candidate) -TimeoutSec 8 -ErrorAction Stop
      if ($r.StatusCode -eq 200) { return $true }
    }
    catch {
      $status = $null
      try { $status = [int]$_.Exception.Response.StatusCode } catch {}
      if ($status -eq 403) { return $false }
      # 404/non-event does not disprove the key; try the next venue.
    }
  }
  return $false
}

function Find-StreaksKeyFromPlayer {
  $playerUrl = 'https://front.player.boatrace-cdn.jp/player/live?service=boatcast&stadium=12suminoe&sourceType=mix&dvr=1&audioMode=0&autoplay=1&bitrate=high'
  $webHeaders = @{ 'User-Agent'=$ua; 'Accept'='text/html,application/xhtml+xml,application/javascript,*/*' }
  $bodies = New-Object System.Collections.Generic.List[string]
  try {
    $page = Invoke-WebRequest -Uri $playerUrl -Headers $webHeaders -TimeoutSec 20 -ErrorAction Stop
    $bodies.Add([string]$page.Content)
    $base = [Uri]$playerUrl
    $seen = @{}
    $matches = [regex]::Matches([string]$page.Content, '(?is)<script[^>]+src=["'']([^"'']+)["'']')
    foreach ($m in $matches) {
      if ($bodies.Count -ge 25) { break }
      try {
        $src = [Uri]::new($base, $m.Groups[1].Value).AbsoluteUri
        if ($seen.ContainsKey($src)) { continue }
        $seen[$src] = $true
        $js = Invoke-WebRequest -Uri $src -Headers $webHeaders -TimeoutSec 15 -ErrorAction Stop
        $bodies.Add([string]$js.Content)
      }
      catch {}
    }
  }
  catch {
    Write-Host "BOATCAST player scan unavailable: $($_.Exception.GetType().Name)"
    return ''
  }

  $candidates = New-Object System.Collections.Generic.List[string]
  $candidateSeen = @{}
  foreach ($body in $bodies) {
    $patterns = @(
      '(?i)x-streaks-api-key[^A-Za-z0-9_-]{0,80}["'']([A-Za-z0-9_-]{8,128})["'']',
      '(?i)(?:streaksApiKey|streaks_api_key)[^A-Za-z0-9_-]{0,40}["'']([A-Za-z0-9_-]{8,128})["'']'
    )
    foreach ($pattern in $patterns) {
      foreach ($m in [regex]::Matches($body, $pattern)) {
        $c = $m.Groups[1].Value
        if (-not $candidateSeen.ContainsKey($c)) {
          $candidateSeen[$c] = $true
          $candidates.Add($c)
        }
      }
    }
    # Minified bundles sometimes assign the header through a variable. Search
    # only near STREAKS/API-key text, then validate every token against playback.
    foreach ($m in [regex]::Matches($body, '(?i)(?:streaks|api-key)')) {
      $start = [Math]::Max(0, $m.Index - 350)
      $len = [Math]::Min(700, $body.Length - $start)
      $near = $body.Substring($start, $len)
      foreach ($t in [regex]::Matches($near, '(?<![A-Za-z0-9_-])([A-Fa-f0-9]{24,64})(?![A-Za-z0-9_-])')) {
        $c = $t.Groups[1].Value
        if (-not $candidateSeen.ContainsKey($c)) {
          $candidateSeen[$c] = $true
          $candidates.Add($c)
        }
      }
    }
  }

  Write-Host "BOATCAST key candidates discovered: $($candidates.Count)"
  $tested = 0
  foreach ($c in $candidates) {
    if ($tested -ge 30) { break }
    $tested++
    if (Test-StreaksKey $c) {
      Write-Host 'BOATCAST API key auto-detected and validated'
      return $c
    }
  }
  return ''
}

$apiKey = [Environment]::GetEnvironmentVariable('BOATRACE_STREAKS_API_KEY')
if (-not [string]::IsNullOrWhiteSpace($apiKey)) {
  if (Test-StreaksKey $apiKey) {
    Write-Host 'BOATCAST API key from GitHub secret validated'
  }
  else {
    Write-Host 'BOATCAST API key secret is missing/invalid for current player; trying auto-detection'
    $apiKey = ''
  }
}
if ([string]::IsNullOrWhiteSpace($apiKey)) {
  $apiKey = Find-StreaksKeyFromPlayer
}
if ([string]::IsNullOrWhiteSpace($apiKey)) {
  Write-Host '::warning::BOATCAST API key could not be resolved; direct playback API may return 403'
}

$headers = New-PlaybackHeaders $apiKey
$result = [ordered]@{}
foreach ($v in $venues) {
  $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:lm-br-$($v.Code)-tokyo-$d?audio_only=false"
  try {
    $r = Invoke-WebRequest -Uri $url -Headers $headers -TimeoutSec 20 -ErrorAction Stop
    $j = $r.Content | ConvertFrom-Json
    if ($j.sources -and $j.sources.Count -gt 0 -and $j.sources[0].src) {
      $result[$v.Code] = [string]$j.sources[0].src
      Write-Host "STREAM OK $($v.Id)"
    } else {
      Write-Host "STREAM WAIT $($v.Id): no source"
    }
  }
  catch {
    $status = $null
    try { $status = [int]$_.Exception.Response.StatusCode } catch {}
    if ($status) {
      Write-Host "STREAM WAIT $($v.Id): HTTP $status"
    } else {
      Write-Host "STREAM WAIT $($v.Id): $($_.Exception.GetType().Name)"
    }
  }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$json = $result | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'boat_stream_urls.json'), $json, $utf8)
Write-Host "BOAT stream URLs fetched: $($result.Count)"

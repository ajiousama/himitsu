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
$webHeaders = @{ 'User-Agent'=$ua; 'Accept'='application/json,text/plain,*/*'; 'Referer'='https://front.player.boatrace-cdn.jp/' }

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

function Get-PlayerBodies([string]$stadium, [int]$maxScripts = 30) {
  $playerUrl = "https://front.player.boatrace-cdn.jp/player/live?service=boatcast&stadium=$stadium&sourceType=mix&dvr=1&audioMode=0&autoplay=1&bitrate=high"
  $headers = @{ 'User-Agent'=$ua; 'Accept'='text/html,application/xhtml+xml,application/javascript,*/*' }
  $bodies = New-Object System.Collections.Generic.List[string]
  try {
    $page = Invoke-WebRequest -Uri $playerUrl -Headers $headers -TimeoutSec 15 -ErrorAction Stop
    $bodies.Add([string]$page.Content)
    $base = [Uri]$playerUrl
    $seen = @{}
    foreach ($m in [regex]::Matches([string]$page.Content, '(?is)<script[^>]+src=["'']([^"'']+)["'']')) {
      if ($bodies.Count -ge ($maxScripts + 1)) { break }
      try {
        $src = [Uri]::new($base, $m.Groups[1].Value).AbsoluteUri
        if ($seen.ContainsKey($src)) { continue }
        $seen[$src] = $true
        $js = Invoke-WebRequest -Uri $src -Headers $headers -TimeoutSec 12 -ErrorAction Stop
        $bodies.Add([string]$js.Content)
      } catch {}
    }
  } catch { Write-Host "BOATCAST player scan unavailable: $($_.Exception.GetType().Name)" }
  return ,$bodies.ToArray()
}

function Write-CurrentSettingDiagnostic {
  $epoch = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
  $settingUrl = "https://front.player.boatrace-cdn.jp/setting/live/12suminoe/setting.json?t=$epoch"
  try {
    $r = Invoke-WebRequest -Uri $settingUrl -Headers $webHeaders -TimeoutSec 15 -ErrorAction Stop
    $j = $r.Content | ConvertFrom-Json
    Write-Host "BOATCAST SETTING URL: $settingUrl"
    Write-Host ('BOATCAST SETTING JSON: ' + ($j | ConvertTo-Json -Depth 20 -Compress))
  } catch {
    $status = $null; try { $status = [int]$_.Exception.Response.StatusCode } catch {}
    Write-Host "BOATCAST SETTING ERROR: status=$status type=$($_.Exception.GetType().Name)"
  }

  $bodies = Get-PlayerBodies '12suminoe' 30
  $bodyNo = 0
  foreach ($body0 in $bodies) {
    $bodyNo++
    $body = ([string]$body0).Replace('\/','/').Replace('\u002F','/').Replace('\u0026','&').Replace('&amp;','&')
    foreach ($needle in @('/setting/live/','media_id','mediaId','mix_live','mix_dvr','playback.api.streaks.jp')) {
      $idx = $body.IndexOf($needle, [System.StringComparison]::OrdinalIgnoreCase)
      if ($idx -ge 0) {
        $start = [Math]::Max(0, $idx - 350)
        $len = [Math]::Min(1800, $body.Length - $start)
        $snippet = $body.Substring($start, $len) -replace "[\r\n\t]+", ' '
        Write-Host "BOATCAST CODE DIAG $needle body=$bodyNo :: $snippet"
        break
      }
    }
  }
}

# The old date-derived media refs now return 404. Dump the current public
# setting contract once per run so the resolver can follow BOATCAST's actual
# media IDs rather than guessing them.
Write-CurrentSettingDiagnostic

$apiKey = [Environment]::GetEnvironmentVariable('BOATRACE_STREAKS_API_KEY')
$headers = New-PlaybackHeaders $apiKey
$result = [ordered]@{}
foreach ($v in $venues) {
  $url = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:lm-br-$($v.Code)-tokyo-$d?audio_only=false"
  try {
    $r = Invoke-WebRequest -Uri $url -Headers $headers -TimeoutSec 10 -ErrorAction Stop
    $j = $r.Content | ConvertFrom-Json
    if ($j.sources -and $j.sources.Count -gt 0 -and $j.sources[0].src) {
      $result[$v.Code] = [string]$j.sources[0].src
      Write-Host "STREAM OK $($v.Id)"
    } else { Write-Host "STREAM WAIT $($v.Id): no source" }
  } catch {
    $status = $null; try { $status = [int]$_.Exception.Response.StatusCode } catch {}
    if ($status) { Write-Host "STREAM WAIT $($v.Id): HTTP $status" }
    else { Write-Host "STREAM WAIT $($v.Id): $($_.Exception.GetType().Name)" }
  }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$json = $result | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'boat_stream_urls.json'), $json, $utf8)
Write-Host "BOAT stream URLs fetched: $($result.Count)"
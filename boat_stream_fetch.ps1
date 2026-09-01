$ErrorActionPreference = 'Continue'

$jst = [System.TimeZoneInfo]::FindSystemTimeZoneById('Asia/Tokyo')
$nowJst = [System.TimeZoneInfo]::ConvertTime([DateTimeOffset]::UtcNow, $jst)
$d = $nowJst.ToString('yyyyMMdd')

$headers = @{
  'Origin'     = 'https://front.player.boatrace-cdn.jp'
  'Referer'    = 'https://front.player.boatrace-cdn.jp/'
  'User-Agent' = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'
}

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
      Write-Host "STREAM WAIT $($v.Id)"
    }
  }
  catch {
    Write-Host "STREAM WAIT $($v.Id): $($_.Exception.GetType().Name)"
  }
}

$utf8 = New-Object System.Text.UTF8Encoding($false)
$json = $result | ConvertTo-Json -Depth 4
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot 'boat_stream_urls.json'), $json, $utf8)
Write-Host "BOAT stream URLs fetched: $($result.Count)"

# ============================================================
# BOAT RACE 当日更新 - GitHub Actions / PowerShell 7 対応版
# 出力:
#   boatrace_today.json
#   boatrace_today.m3u
# ============================================================

$ErrorActionPreference = "Continue"

# JST固定
$jst = [System.TimeZoneInfo]::FindSystemTimeZoneById("Asia/Tokyo")
$nowJst = [System.TimeZoneInfo]::ConvertTime([DateTimeOffset]::UtcNow, $jst)
$d = $nowJst.ToString("yyyyMMdd")

$headers = @{
    "Origin"     = "https://front.player.boatrace-cdn.jp"
    "Referer"    = "https://front.player.boatrace-cdn.jp/"
    "User-Agent" = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36"
}

$webHeaders = @{
    "User-Agent" = $headers["User-Agent"]
}

Add-Type -AssemblyName System.Net.Http

$httpHandler = New-Object System.Net.Http.HttpClientHandler
$httpClient  = New-Object System.Net.Http.HttpClient($httpHandler)
$httpClient.Timeout = [TimeSpan]::FromSeconds(20)
$httpClient.DefaultRequestHeaders.UserAgent.ParseAdd($headers["User-Agent"])

$venues = @(
    @{Name="01 桐生";       Jcd="01"; Code="01kiryu";       TvgId="boat.kiryu";       Logo="https://www.boatrace.jp/static/uploads/sites/8/01_N.jpg"},
    @{Name="02 戸田";       Jcd="02"; Code="02toda";        TvgId="boat.toda";        Logo="https://www.boatrace.jp/static/uploads/sites/8/02_N-1.jpg"},
    @{Name="03 江戸川";     Jcd="03"; Code="03edogawa";     TvgId="boat.edogawa";     Logo="https://www.boatrace.jp/static/uploads/sites/8/03_N-1.jpg"},
    @{Name="04 平和島";     Jcd="04"; Code="04heiwajima";   TvgId="boat.heiwajima";   Logo="https://www.boatrace.jp/static/uploads/sites/8/04_N-1.jpg"},
    @{Name="05 多摩川";     Jcd="05"; Code="05tamagawa";    TvgId="boat.tamagawa";    Logo="https://www.boatrace.jp/static/uploads/sites/8/05_N-1.jpg"},
    @{Name="06 浜名湖";     Jcd="06"; Code="06hamanako";    TvgId="boat.hamanako";    Logo="https://www.boatrace.jp/static/uploads/sites/8/06_N-1.jpg"},
    @{Name="07 蒲郡";       Jcd="07"; Code="07gamagori";    TvgId="boat.gamagori";    Logo="https://www.boatrace.jp/static/uploads/sites/8/07_N-1.jpg"},
    @{Name="08 常滑";       Jcd="08"; Code="08tokoname";    TvgId="boat.tokoname";    Logo="https://www.boatrace.jp/static/uploads/sites/8/08_N-1.jpg"},
    @{Name="09 津";         Jcd="09"; Code="09tsu";         TvgId="boat.tsu";         Logo="https://www.boatrace.jp/static/uploads/sites/8/09_N-1-1.jpg"},
    @{Name="10 三国";       Jcd="10"; Code="10mikuni";      TvgId="boat.mikuni";      Logo="https://www.boatrace.jp/static/uploads/sites/8/10_N-1-1.jpg"},
    @{Name="11 びわこ";     Jcd="11"; Code="11biwako";      TvgId="boat.biwako";      Logo="https://www.boatrace.jp/static/uploads/sites/8/11_N-1.jpg"},
    @{Name="12 住之江";     Jcd="12"; Code="12suminoe";     TvgId="boat.suminoe";     Logo="https://www.boatrace.jp/static/uploads/sites/8/12_N-1-1.jpg"},
    @{Name="13 尼崎";       Jcd="13"; Code="13amagasaki";   TvgId="boat.amagasaki";   Logo="https://www.boatrace.jp/static/uploads/sites/8/13_N-1.jpg"},
    @{Name="14 鳴門";       Jcd="14"; Code="14naruto";      TvgId="boat.naruto";      Logo="https://www.boatrace.jp/static/uploads/sites/8/14_N-1.jpg"},
    @{Name="15 丸亀";       Jcd="15"; Code="15marugame";    TvgId="boat.marugame";    Logo="https://www.boatrace.jp/static/uploads/sites/8/15_N-1.jpg"},
    @{Name="16 児島";       Jcd="16"; Code="16kojima";      TvgId="boat.kojima";      Logo="https://www.boatrace.jp/static/uploads/sites/8/16_N-1.jpg"},
    @{Name="17 宮島";       Jcd="17"; Code="17miyajima";    TvgId="boat.miyajima";    Logo="https://www.boatrace.jp/static/uploads/sites/8/17_N-1.jpg"},
    @{Name="18 徳山";       Jcd="18"; Code="18tokuyama";    TvgId="boat.tokuyama";    Logo="https://www.boatrace.jp/static/uploads/sites/8/18_N-1.jpg"},
    @{Name="19 下関";       Jcd="19"; Code="19shimonoseki"; TvgId="boat.shimonoseki"; Logo="https://www.boatrace.jp/static/uploads/sites/8/19_N-1.jpg"},
    @{Name="20 若松";       Jcd="20"; Code="20wakamatsu";   TvgId="boat.wakamatsu";   Logo="https://www.boatrace.jp/static/uploads/sites/8/20_N-1.jpg"},
    @{Name="21 芦屋";       Jcd="21"; Code="21ashiya";      TvgId="boat.ashiya";      Logo="https://www.boatrace.jp/static/uploads/sites/8/21_N-1.jpg"},
    @{Name="22 福岡";       Jcd="22"; Code="22fukuoka";     TvgId="boat.fukuoka";     Logo="https://www.boatrace.jp/static/uploads/sites/8/22_N-1-1.jpg"},
    @{Name="23 唐津";       Jcd="23"; Code="23karatsu";     TvgId="boat.karatsu";     Logo="https://www.boatrace.jp/static/uploads/sites/8/23_N-1.jpg"},
    @{Name="24 大村";       Jcd="24"; Code="24omura";       TvgId="boat.omura";       Logo="https://www.boatrace.jp/static/uploads/sites/8/24_N-1.jpg"}
)

function Convert-ToJstDateTime {
    param([string]$IsoText)

    if (-not $IsoText) { return $null }

    try {
        $dto = [DateTimeOffset]::Parse($IsoText)
        return [System.TimeZoneInfo]::ConvertTime($dto, $jst).DateTime
    }
    catch {
        return $null
    }
}

function Get-DayType {
    param([datetime]$Start, [datetime]$End)

    $startMinutes = ($Start.Hour * 60) + $Start.Minute
    $endMinutes   = ($End.Hour * 60) + $End.Minute

    if ($endMinutes -ge (23 * 60)) { return @{ Name="ミッドナイト"; Emoji="🌟" } }
    if ($endMinutes -ge (20 * 60)) { return @{ Name="ナイター"; Emoji="🌙" } }
    if ($startMinutes -lt (9 * 60)) { return @{ Name="モーニング"; Emoji="🌅" } }
    if ($endMinutes -ge (18 * 60)) { return @{ Name="サマータイム"; Emoji="🌇" } }
    return @{ Name="デイ"; Emoji="🌞" }
}

function Convert-HtmlToText {
    param([string]$Html)

    if (-not $Html) { return "" }

    $text = $Html
    $text = [regex]::Replace($text, "<script[\s\S]*?</script>", " ", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    $text = [regex]::Replace($text, "<style[\s\S]*?</style>", " ", [System.Text.RegularExpressions.RegexOptions]::IgnoreCase)
    $text = [regex]::Replace($text, "<[^>]+>", " ")
    $text = [System.Net.WebUtility]::HtmlDecode($text)
    $text = [regex]::Replace($text, "\s+", " ")
    return $text.Trim()
}

function Get-RaceNamesFast {
    param([string]$Jcd, [hashtable]$RaceTimes)

    $result = @{}
    $tasks = @{}

    for ($rno = 1; $rno -le 12; $rno++) {
        if (-not $RaceTimes.ContainsKey($rno)) { continue }

        $url = "https://www.boatrace.jp/owpc/pc/race/racelist?hd=$d&jcd=$Jcd&rno=$rno"
        try {
            $tasks[$rno] = $script:httpClient.GetStringAsync($url)
        }
        catch {
            $result[$rno] = ""
        }
    }

    foreach ($rno in @($tasks.Keys | Sort-Object)) {
        $name = ""

        try {
            $html = $tasks[$rno].GetAwaiter().GetResult()

            $m = [regex]::Match(
                $html,
                '<h[1-6][^>]*>([\s\S]*?)1800m[\s\S]*?</h[1-6]>',
                [System.Text.RegularExpressions.RegexOptions]::IgnoreCase
            )

            if ($m.Success) {
                $name = $m.Groups[1].Value
                $name = [regex]::Replace($name, '<[^>]+>', ' ')
                $name = [System.Net.WebUtility]::HtmlDecode($name)
                $name = [regex]::Replace($name, '\s+', ' ').Trim()
                $name = $name -replace '締切予定時刻.*$', '' -replace '1800m.*$', ''
                $name = $name.Trim()

                if ($name.Length -gt 50) { $name = "" }
            }

            if (-not $name) {
                $plain = Convert-HtmlToText $html
                $m2 = [regex]::Match(
                    $plain,
                    '([^\s]{1,30}(?:戦|Ｒ|R|選抜|特選|優勝戦|予選|一般))\s+1800m'
                )
                if ($m2.Success) { $name = $m2.Groups[1].Value.Trim() }
            }
        }
        catch {
            $name = ""
        }

        $result[$rno] = $name
    }

    return $result
}

function Get-RaceTimes {
    param([string]$Jcd)

    $result = @{}
    $url = "https://www.boatrace.jp/owpc/pc/race/raceindex?hd=$d&jcd=$Jcd"

    try {
        $response = Invoke-WebRequest `
            -Uri $url `
            -Headers $webHeaders `
            -TimeoutSec 20 `
            -ErrorAction Stop

        $text = Convert-HtmlToText $response.Content

        $matches = [regex]::Matches(
            $text,
            "(?<!\d)(1[0-2]|[1-9])R\s+([0-2][0-9]:[0-5][0-9])"
        )

        foreach ($m in $matches) {
            $rno = [int]$m.Groups[1].Value
            $time = $m.Groups[2].Value
            if (-not $result.ContainsKey($rno)) { $result[$rno] = $time }
        }
    }
    catch {}

    return $result
}

function Make-Time {
    param([string]$Date, [string]$Time)
    return "$($Date.Substring(0,4))-$($Date.Substring(4,2))-$($Date.Substring(6,2)) $Time"
}

$count = 0
$boatLines = @("#EXTM3U")
$todayData = [ordered]@{}

Write-Host ""
Write-Host "=============================================="
Write-Host " BOAT RACE GitHub Actions版"
Write-Host " 日付: $d"
Write-Host "=============================================="

foreach ($v in $venues) {
    Write-Host ""
    Write-Host "CHECK $($v.Name) ..." -NoNewline

    $settingUrl = "https://front.player.boatrace-cdn.jp/setting/live/$($v.Code)/setting.json?t=$([DateTimeOffset]::UtcNow.ToUnixTimeSeconds())"

    $startAt = $null
    $endAt = $null
    $dayTypeName = ""
    $dayTypeEmoji = "🚤"

    try {
        $setting = Invoke-RestMethod `
            -Uri $settingUrl `
            -Headers $headers `
            -Method Get `
            -TimeoutSec 20 `
            -ErrorAction Stop

        if ($setting.br_live) {
            $startAt = Convert-ToJstDateTime $setting.br_live.start_at
            $endAt   = Convert-ToJstDateTime $setting.br_live.end_at

            if ($startAt -and $endAt) {
                $typeInfo = Get-DayType -Start $startAt -End $endAt
                $dayTypeName  = $typeInfo.Name
                $dayTypeEmoji = $typeInfo.Emoji
            }
        }
    }
    catch {}

    $playbackUrl = "https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:lm-br-$($v.Code)-tokyo-$d`?audio_only=false"
    $m3u8 = $null

    try {
        $r = Invoke-WebRequest `
            -Uri $playbackUrl `
            -Headers $headers `
            -TimeoutSec 20 `
            -ErrorAction Stop

        $j = $r.Content | ConvertFrom-Json

        if ($j.sources -and $j.sources.Count -gt 0) {
            $m3u8 = $j.sources[0].src
        }
    }
    catch {}

    $raceTimes = Get-RaceTimes -Jcd $v.Jcd
    $isHeld = ($raceTimes.Count -gt 0)

    $raceNames = @{}
    if ($isHeld) {
        $raceNames = Get-RaceNamesFast -Jcd $v.Jcd -RaceTimes $raceTimes
    }

    if ($m3u8) {
        Write-Host " OK" -ForegroundColor Green

        $boatLines += "#EXTINF:-1 tvg-id=`"$($v.TvgId)`" tvg-name=`"$($v.Name)`" tvg-logo=`"$($v.Logo)`" group-title=`"ボートレース`",$($v.Name)"
        $boatLines += $m3u8
        $boatLines += ""

        $count++
    }
    elseif ($isHeld) {
        Write-Host " 開催あり / 配信待ち" -ForegroundColor Yellow
    }
    else {
        Write-Host " 本日非開催" -ForegroundColor DarkGray
    }

    $item = [ordered]@{
        tvg_id   = $v.TvgId
        logo     = $v.Logo
        live     = [bool]$m3u8
        held     = $isHeld
        day_type = $dayTypeName
        emoji    = $dayTypeEmoji
        races    = @()
    }

    if ($m3u8) { $item["url"] = $m3u8 }
    if ($startAt) { $item["start"] = $startAt.ToString("HH:mm") }
    if ($endAt) { $item["end"] = $endAt.ToString("HH:mm") }

    if (-not $isHeld) {
        $item["status_title"] = "⛔ $($v.Name) 本日非開催"
        $todayData[$v.Name] = $item
        continue
    }

    $previousTime = $null

    for ($rno = 1; $rno -le 12; $rno++) {
        if (-not $raceTimes.ContainsKey($rno)) { continue }

        $deadline = $raceTimes[$rno]
        $raceName = ""

        if ($raceNames.ContainsKey($rno)) {
            $raceName = $raceNames[$rno]
        }

        Write-Host "  EPG $($v.Name) ${rno}R $deadline $raceName"

        if ($rno -eq 1) {
            if ($startAt) {
                $epgStart = $startAt.ToString("yyyy-MM-dd HH:mm")
            }
            else {
                $firstDeadline = [datetime]::ParseExact($deadline, "HH:mm", $null)
                $epgStart = Make-Time -Date $d -Time $firstDeadline.AddMinutes(-30).ToString("HH:mm")
            }
        }
        else {
            $epgStart = Make-Time -Date $d -Time $previousTime
        }

        $epgEnd = Make-Time -Date $d -Time $deadline

        if ($raceName) {
            $title = "$dayTypeEmoji $($v.Name) ${rno}R $raceName【$deadline】"
        }
        else {
            $title = "$dayTypeEmoji $($v.Name) ${rno}R【$deadline】"
        }

        $item.races += [ordered]@{
            rno       = $rno
            time      = $deadline
            race_name = $raceName
            title     = $title
            epg_start = $epgStart
            epg_end   = $epgEnd
        }

        $previousTime = $deadline
    }

    if ($previousTime) {
        $item["finish_title"] = "🏁 $($v.Name) 本日開催終了"
        $item["finish_start"] = Make-Time -Date $d -Time $previousTime

        if ($endAt) {
            $item["finish_end"] = $endAt.ToString("yyyy-MM-dd HH:mm")
        }
        else {
            $last = [datetime]::ParseExact($previousTime, "HH:mm", $null)
            $item["finish_end"] = Make-Time -Date $d -Time $last.AddHours(2).ToString("HH:mm")
        }
    }

    $todayData[$v.Name] = $item
}

$utf8 = New-Object System.Text.UTF8Encoding($false)

$m3uPath = Join-Path $PSScriptRoot "boatrace_today.m3u"
$jsonPath = Join-Path $PSScriptRoot "boatrace_today.json"

[System.IO.File]::WriteAllText(
    $m3uPath,
    ($boatLines -join "`n").TrimEnd() + "`n",
    $utf8
)

$json = $todayData | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($jsonPath, $json, $utf8)

Write-Host ""
Write-Host "=============================================="
Write-Host " BOAT RACE 更新完了！" -ForegroundColor Green
Write-Host " 取得できた場: $count / 24"
Write-Host " M3U : $m3uPath"
Write-Host " JSON: $jsonPath"
Write-Host "=============================================="

try { $httpClient.Dispose() } catch {}
try { $httpHandler.Dispose() } catch {}

exit 0

#!/usr/bin/env python3
from __future__ import annotations

"""BOAT Auto v3.

One self-contained updater owns today's BOAT schedule, current-day stream cache,
FreeWiFi playlist block, BOAT EPG overlay and alert state.  A venue that has
appeared never disappears before the JST date changes.
"""

import argparse
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time, timedelta, timezone
import json
from pathlib import Path
import re
import time as time_module
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET


FREEWIFI = Path("freewifi")
STATUS = Path("today_boat_status.json")
STATE = Path("boat_auto_state.json")
ALERT = Path("boat_auto_alert.json")
SEED = Path("boat_stream_seed.m3u")
LOCAL_EPG = Path("public_sports_epg_local.xml")
GUIDES = Path("guides.xml")

START = "# === TODAY_BOAT_START ==="
END = "# === TODAY_BOAT_END ==="
PUBLIC_START = "# === TODAY_PUBLIC_SPORTS_START ==="
PUBLIC_END = "# === TODAY_PUBLIC_SPORTS_END ==="
GROUP = "今日の開催場"

JST = timezone(timedelta(hours=9))
ALERT_LEAD_MINUTES = 30
RACE_SWITCH_MINUTES = 3
END_GUIDANCE_MINUTES = 45
SCHEDULE_API = "https://boatraceopenapi.github.io/api/v1/{year}/{ymd}.json"
SCHEDULE_TODAY_API = "https://boatraceopenapi.github.io/api/v1/today.json"
SEED_API = "https://himitsu-six.vercel.app/api/boat-seed?venue={jcd}"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
LOGO_PROXY = "https://images.weserv.nl/?url=raw.githubusercontent.com/ajiousama/himitsu/main"
FULLWIDTH = str.maketrans("0123456789", "０１２３４５６７８９")


VENUES = {
    "01": ("桐生", "boat.kiryu", "boat_kiryu.png"),
    "02": ("戸田", "boat.toda", "boat_toda.png"),
    "03": ("江戸川", "boat.edogawa", "boat_edogawa.png"),
    "04": ("平和島", "boat.heiwajima", "boat_heiwajima.png"),
    "05": ("多摩川", "boat.tamagawa", "boat_tamagawa.png"),
    "06": ("浜名湖", "boat.hamanako", "boat_hamanako.png"),
    "07": ("蒲郡", "boat.gamagori", "boat_gamagori.png"),
    "08": ("常滑", "boat.tokoname", "boat_tokoname.png"),
    "09": ("津", "boat.tsu", "boat_tsu.png"),
    "10": ("三国", "boat.mikuni", "boat_mikuni.png"),
    "11": ("びわこ", "boat.biwako", "boat_biwako.png"),
    "12": ("住之江", "boat.suminoe", "boat_suminoe.png"),
    "13": ("尼崎", "boat.amagasaki", "boat_amagasaki.png"),
    "14": ("鳴門", "boat.naruto", "boat_naruto.png"),
    "15": ("丸亀", "boat.marugame", "boat_marugame.png"),
    "16": ("児島", "boat.kojima", "boat_kojima.png"),
    "17": ("宮島", "boat.miyajima", "boat_miyajima.png"),
    "18": ("徳山", "boat.tokuyama", "boat_tokuyama.png"),
    "19": ("下関", "boat.shimonoseki", "boat_shimonoseki.png"),
    "20": ("若松", "boat.wakamatsu", "boat_wakamatsu.png"),
    "21": ("芦屋", "boat.ashiya", "boat_ashiya.png"),
    "22": ("福岡", "boat.fukuoka", "boat_fukuoka.png"),
    "23": ("唐津", "boat.karatsu", "boat_karatsu.png"),
    "24": ("大村", "boat.omura", "boat_omura.png"),
}
MODE_LABEL = {"morning": "モーニング", "day": "デイ", "night": "ナイター"}
MODE_ICON = {"morning": "🌅", "day": "☀️", "night": "🌙"}
MODE_ORDER = {"morning": 0, "day": 1, "night": 2}


def now_jst() -> datetime:
    return datetime.now(JST)


def json_read(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def json_write(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def request_json(url: str, timeout: int = 18, attempts: int = 3) -> dict:
    error = None
    for attempt in range(1, attempts + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "application/json,*/*",
                "Cache-Control": "no-cache, no-store",
                "Pragma": "no-cache",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8", "replace"))
        except Exception as exc:
            error = exc
            if attempt < attempts:
                time_module.sleep(0.4 * attempt)
    raise RuntimeError(f"{type(error).__name__}: {error}")


def parse_race_datetime(value: object, day: date) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        try:
            parsed = datetime.strptime(text[:19], "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=JST)
    else:
        parsed = parsed.astimezone(JST)
    return parsed if parsed.date() == day else None


def cards_from_snapshot(data: dict, day: date) -> dict[str, list[dict]]:
    stadiums = (((data or {}).get("programs") or {}).get("stadiums") or {})
    cards: dict[str, list[dict]] = {}
    for raw_code, stadium in stadiums.items():
        try:
            jcd = f"{int(raw_code):02d}"
        except (TypeError, ValueError):
            continue
        if jcd not in VENUES:
            continue
        races = []
        for raw_number, race in ((stadium or {}).get("races") or {}).items():
            race = race or {}
            try:
                number = int(race.get("race_number") or raw_number)
            except (TypeError, ValueError):
                continue
            if not 1 <= number <= 12:
                continue
            start = parse_race_datetime(race.get("closed_at"), day)
            if start is None:
                continue
            subtitle = str(race.get("subtitle") or race.get("title") or "ボートレース").strip()
            races.append({"race": number, "start": start, "name": subtitle})
        races.sort(key=lambda item: item["race"])
        if len(races) >= 10:
            cards[jcd] = races
    return cards


def schedule_not_published_error(exc: Exception) -> bool:
    """Return True only for the provider's normal 'not published yet' 404."""
    text = str(exc)
    return "HTTP Error 404" in text or "404: Not Found" in text


def fetch_cards(day: date) -> dict[str, list[dict]]:
    # Right after JST midnight the dated GitHub Pages snapshot can briefly be 404
    # even though the API's rolling today.json is already available. Prefer the
    # dated immutable snapshot, then fall back to today.json for the actual JST day.
    url = SCHEDULE_API.format(year=day.strftime("%Y"), ymd=day.strftime("%Y%m%d"))
    try:
        return cards_from_snapshot(request_json(url), day)
    except RuntimeError as dated_error:
        if day != now_jst().date():
            raise
        try:
            cards = cards_from_snapshot(request_json(SCHEDULE_TODAY_API), day)
            if cards:
                print(f"BOAT AUTO schedule fallback: today.json ({len(cards)} venues)")
                return cards
        except RuntimeError as today_error:
            raise RuntimeError(f"dated={dated_error}; today={today_error}") from today_error
        raise dated_error


def jwt_payload(url: str) -> dict:
    try:
        token = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("token") or [None])[0]
        if not token or token.count(".") < 2:
            return {}
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        value = json.loads(base64.urlsafe_b64decode(payload.encode()).decode("utf-8"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def token_start_day(url: str) -> date | None:
    try:
        stamp = int(jwt_payload(url).get("start") or 0)
        return datetime.fromtimestamp(stamp, JST).date() if stamp else None
    except Exception:
        return None


def token_expired(url: str, margin: int = 300) -> bool:
    try:
        stamp = int(jwt_payload(url).get("exp") or 0)
        return bool(stamp and stamp <= int(time_module.time()) + margin)
    except Exception:
        return False


def current_day_stream(url: object, day: date) -> bool:
    value = str(url or "")
    return (
        value.startswith("https://manifest.streaks.jp/")
        and ".m3u8" in value
        and token_start_day(value) == day
    )


def parse_m3u_urls(text: str) -> dict[str, str]:
    lines = text.splitlines()
    output: dict[str, str] = {}
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        match = re.search(r'tvg-id="([^"]+)"', line)
        if not match:
            continue
        for next_index in range(index + 1, min(index + 6, len(lines))):
            value = lines[next_index].strip()
            if value.startswith(("http://", "https://")):
                output[match.group(1)] = value
                break
            if value.startswith("#EXTINF:"):
                break
    return output


def managed_playlist_urls() -> dict[str, str]:
    if not FREEWIFI.exists():
        return {}
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    match = re.search(re.escape(START) + r"(.*?)" + re.escape(END), text, re.S)
    return parse_m3u_urls(match.group(1) if match else "")


def load_current_streams(day: date) -> dict[str, dict]:
    streams: dict[str, dict] = {}
    state = json_read(STATE)
    if state.get("date") == day.isoformat():
        for tvg_id, item in (state.get("streams") or {}).items():
            url = str((item or {}).get("url") or "")
            if current_day_stream(url, day):
                streams[tvg_id] = dict(item)

    sources = [
        ("previous FreeWiFi entry", managed_playlist_urls()),
        ("manual iPhone SEED", parse_m3u_urls(SEED.read_text(encoding="utf-8-sig", errors="replace")) if SEED.exists() else {}),
    ]
    acquired = now_jst().isoformat()
    for origin, urls in sources:
        for tvg_id, url in urls.items():
            if current_day_stream(url, day):
                previous_url = str((streams.get(tvg_id) or {}).get("url") or "")
                previous_exp = int(jwt_payload(previous_url).get("exp") or 0)
                candidate_exp = int(jwt_payload(url).get("exp") or 0)
                # Keep the newest current-day token. A stale manual fallback
                # must never replace a fresher URL already acquired by cloud.
                if not previous_url or candidate_exp > previous_exp:
                    streams[tvg_id] = {"url": url, "source": origin, "acquired_at": acquired}
    return streams


def fetch_seed(jcd: str, day: date) -> tuple[str, str, str]:
    try:
        data = request_json(SEED_API.format(jcd=jcd), timeout=12, attempts=2)
    except Exception as exc:
        return jcd, "", str(exc)
    url = str(data.get("url") or "") if data.get("ok") is True else ""
    if not url:
        return jcd, "", f"no current stream (region={data.get('region')})"
    if not current_day_stream(url, day):
        return jcd, "", f"rejected stream start={token_start_day(url)}"
    return jcd, url, ""


def refresh_cloud_streams(cards: dict[str, list[dict]], streams: dict[str, dict], day: date) -> dict:
    failures = []
    fetched = 0
    acquired = now_jst().isoformat()
    workers = min(8, max(1, len(cards)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_seed, jcd, day): jcd for jcd in cards}
        for future in as_completed(futures):
            jcd = futures[future]
            try:
                _jcd, url, error = future.result()
            except Exception as exc:
                url, error = "", f"{type(exc).__name__}: {exc}"
            name, tvg_id, _logo = VENUES[jcd]
            if url:
                streams[tvg_id] = {
                    "url": url,
                    "source": "Vercel KIX automatic acquisition",
                    "acquired_at": acquired,
                }
                fetched += 1
                print(f"BOAT AUTO {name}: cloud SEED OK")
            else:
                failures.append({"jcd": jcd, "name": name, "error": error})
                print(f"BOAT AUTO {name}: cloud SEED pending: {error}")
    return {"requested": len(cards), "fetched": fetched, "failures": failures}


def mode_for(races: list[dict]) -> str:
    first = races[0]["start"]
    last = races[-1]["start"]
    if first.hour < 10:
        return "morning"
    if last.hour >= 20 or first.hour >= 14:
        return "night"
    return "day"


def next_race(races: list[dict], now: datetime) -> dict | None:
    for race in races:
        if race["start"] >= now:
            return {"race": race["race"], "start": race["start"].strftime("%H:%M")}
    return None


def logo_url(filename: str) -> str:
    return f"{LOGO_PROXY}/logos/public_sports/venues/{filename}&output=png"


def make_entry(name: str, tvg_id: str, logo: str, url: str) -> list[str]:
    return [
        f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="BOATRACE{name}" tvg-logo="{logo}" group-title="{GROUP}",BOATRACE{name}',
        url,
    ]


def strip_boat_from_public(text: str) -> str:
    match = re.search(re.escape(PUBLIC_START) + r"(.*?)" + re.escape(PUBLIC_END), text, re.S)
    if not match:
        return text
    lines = match.group(1).splitlines()
    kept = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if line.startswith("#EXTINF:") and re.search(r'tvg-id="boat\.[^"]+"', line):
            index += 1
            while index < len(lines) and not lines[index].startswith(("#EXTINF:", "## ", "# ===")):
                index += 1
            continue
        kept.append(line)
        index += 1
    replacement = PUBLIC_START + "\n".join(kept) + PUBLIC_END
    return text[: match.start()] + replacement + text[match.end() :]


def replace_boat_block(text: str, payload: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)
    if pattern.search(text):
        return pattern.sub(payload + "\n", text, count=1)
    if PUBLIC_START in text:
        return text.replace(PUBLIC_START, payload + "\n\n" + PUBLIC_START, 1)
    return text.rstrip() + "\n\n" + payload + "\n"


def build_venue_state(cards: dict[str, list[dict]], streams: dict[str, dict], now: datetime) -> tuple[dict, list[dict], dict]:
    venues = {}
    rows = []
    phase_counts = {
        mode: {"held": 0, "acquired": 0, "active": 0, "ended": 0, "seed_required": 0}
        for mode in MODE_ORDER
    }
    for jcd, races in sorted(cards.items()):
        name, tvg_id, logo = VENUES[jcd]
        first = races[0]["start"]
        last = races[-1]["start"]
        mode = mode_for(races)
        alert_from = first - timedelta(minutes=ALERT_LEAD_MINUTES)
        finish = last + timedelta(minutes=RACE_SWITCH_MINUTES)
        guidance_switch = last + timedelta(minutes=END_GUIDANCE_MINUTES)
        ended = now >= finish
        active = alert_from <= now < finish
        stream = streams.get(tvg_id) or {}
        url = str(stream.get("url") or "")
        current_url = current_day_stream(url, now.date())
        expired = token_expired(url) if current_url else False
        visible = bool(current_url)
        source_ready = bool(current_url and not expired)
        seed_required = bool(active and not source_ready)
        race_rows = [
            {"race": race["race"], "start": race["start"].strftime("%H:%M"), "name": race["name"]}
            for race in races
        ]
        item = {
            "jcd": jcd,
            "name": name,
            "held": True,
            "visible": visible,
            "ended": ended,
            "active": active,
            "mode": mode,
            "mode_label": MODE_LABEL[mode],
            "first_race": first.strftime("%H:%M"),
            "last_race": last.strftime("%H:%M"),
            "alert_from": alert_from.isoformat(),
            "next_race": next_race(races, now),
            "stream_window": "ended_kept" if ended else ("live_or_prestart" if active else "scheduled"),
            "guidance_switch_at": guidance_switch.isoformat(),
            "seed_required": seed_required,
            "races": race_rows,
        }
        if visible:
            item.update({"url": url, "source": stream.get("source") or "current-day cache", "token_expired": expired})
            rows.append({
                "name": name,
                "mode": mode,
                "first": first,
                "block": make_entry(name, tvg_id, logo_url(logo), url),
            })
        else:
            item["source"] = "automatic cloud SEED pending"
        venues[tvg_id] = item
        phase_counts[mode]["held"] += 1
        phase_counts[mode]["acquired"] += int(visible)
        phase_counts[mode]["active"] += int(active)
        phase_counts[mode]["ended"] += int(ended)
        phase_counts[mode]["seed_required"] += int(seed_required)

    rows.sort(key=lambda row: (MODE_ORDER[row["mode"]], row["first"], row["name"]))
    return venues, rows, phase_counts


def update_playlist(rows: list[dict]) -> None:
    if not FREEWIFI.exists():
        raise RuntimeError("freewifi not found")
    body = []
    for mode in MODE_ORDER:
        selected = [row for row in rows if row["mode"] == mode]
        if not selected:
            continue
        body.append(f"## {MODE_ICON[mode]} {MODE_LABEL[mode]}場")
        for row in selected:
            body.extend(row["block"])
            body.append("")
    payload = "\n".join(body).rstrip()
    managed = (
        START
        + "\n## 今日の開催場 / BOAT AUTO v3（終了場も当日中保持）\n"
        + payload
        + ("\n" if payload else "")
        + END
    )
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    text = strip_boat_from_public(text)
    FREEWIFI.write_text(replace_boat_block(text, managed).rstrip() + "\n", encoding="utf-8")


def xmltv_time(value: datetime) -> str:
    return value.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def ensure_channel(root: ET.Element, cid: str, name: str) -> None:
    if any(channel.get("id") == cid for channel in root.findall("channel")):
        return
    channel = ET.Element("channel", {"id": cid})
    ET.SubElement(channel, "display-name").text = name
    first_programme = next((index for index, child in enumerate(root) if child.tag == "programme"), len(root))
    root.insert(first_programme, channel)


def add_programme(root: ET.Element, cid: str, start: datetime, stop: datetime, title: str, description: str) -> None:
    if stop <= start:
        return
    programme = ET.Element("programme", {"channel": cid, "start": xmltv_time(start), "stop": xmltv_time(stop)})
    ET.SubElement(programme, "title", {"lang": "ja"}).text = title
    ET.SubElement(programme, "desc", {"lang": "ja"}).text = description
    root.append(programme)


def programme_day(programme: ET.Element) -> str:
    return str(programme.get("start") or "")[:8]


def overlay_epg_file(path: Path, cards: dict[str, list[dict]], day: date) -> int:
    if path.exists() and path.stat().st_size:
        try:
            tree = ET.parse(path)
            root = tree.getroot()
        except Exception as exc:
            raise RuntimeError(f"{path} XML parse failed: {exc}") from exc
    else:
        root = ET.Element("tv", {"generator-info-name": "ajiousama/himitsu BOAT Auto v3"})
        tree = ET.ElementTree(root)

    ymd = day.strftime("%Y%m%d")
    boat_ids = {item[1] for item in VENUES.values()}
    for programme in list(root.findall("programme")):
        if programme.get("channel") in boat_ids and programme_day(programme) == ymd:
            root.remove(programme)

    count = 0
    end_of_day = datetime.combine(day + timedelta(days=1), time(0, 0), tzinfo=JST)
    for jcd, races in sorted(cards.items()):
        name, cid, _logo = VENUES[jcd]
        mode = mode_for(races)
        ensure_channel(root, cid, f"BOATRACE{name}")
        for index, race in enumerate(races):
            start = races[0]["start"] - timedelta(minutes=20) if index == 0 else races[index - 1]["start"] + timedelta(minutes=RACE_SWITCH_MINUTES)
            stop = race["start"] + timedelta(minutes=RACE_SWITCH_MINUTES)
            number = str(race["race"]).translate(FULLWIDTH)
            title = f"【{number}Ｒ】 {race['start'].strftime('%H:%M')}発走  🚤【BOATRACE{name} 🚤】"
            description = (
                f"ボートレース BOATRACE{name}\n"
                f"開催区分: {MODE_LABEL[mode]}\n"
                f"発走予定: {race['start'].strftime('%H:%M')}\n"
                f"{race['name']}"
            )
            add_programme(root, cid, start, stop, title, description)
            count += 1
        ended_at = races[-1]["start"] + timedelta(minutes=RACE_SWITCH_MINUTES)
        guidance_at = races[-1]["start"] + timedelta(minutes=END_GUIDANCE_MINUTES)
        future_days = []
        for programme in root.findall("programme"):
            if programme.get("channel") != cid:
                continue
            raw = str(programme.get("start") or "")[:8]
            if len(raw) != 8 or not raw.isdigit() or raw <= ymd:
                continue
            try:
                future_days.append(datetime.strptime(raw, "%Y%m%d").date())
            except ValueError:
                pass
        next_day = min(future_days) if future_days else None
        if ended_at < end_of_day:
            finish_stop = min(guidance_at, end_of_day)
            add_programme(
                root,
                cid,
                ended_at,
                finish_stop,
                "本日の開催は終了しました",
                f"BOATRACE{name}の本日の開催は終了しました。",
            )
            count += 1
            if guidance_at < end_of_day and next_day:
                if next_day == day + timedelta(days=1):
                    title = "翌日開催予定（仮時間）"
                    desc = f"BOATRACE{name}は翌日{next_day.month}月{next_day.day}日開催予定です。実発走時刻は取得後に自動更新します。"
                else:
                    title = f"次回開催：{next_day.month}月{next_day.day}日"
                    desc = f"BOATRACE{name}の次回開催予定日は{next_day.month}月{next_day.day}日です。"
                add_programme(root, cid, guidance_at, end_of_day, title, desc)
                count += 1

    channels = [item for item in list(root) if item.tag == "channel"]
    programmes = [item for item in list(root) if item.tag == "programme"]
    other = [item for item in list(root) if item.tag not in {"channel", "programme"}]
    programmes.sort(key=lambda item: (item.get("start", ""), item.get("channel", "")))
    root[:] = channels + other + programmes
    ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return count


def write_alert(now: datetime, system_errors: list[str], seed_required: list[str], cloud: dict) -> dict:
    active = bool(system_errors or seed_required)
    if system_errors:
        kind = "system_error"
        title = "BOAT自動更新エラー"
        message = " / ".join(system_errors)
    elif seed_required:
        kind = "seed_required"
        title = "BOAT 手動SEEDが必要です"
        message = "公営これ一発 v17を実行してください: " + "、".join(seed_required)
    else:
        kind = "healthy"
        title = "BOAT自動更新 正常"
        message = "朝・デイ・ナイターを自動取得中です。"
    value = {
        "system": "boat-auto-v3",
        "date": now.date().isoformat(),
        "checked_at": now.isoformat(),
        "active": active,
        "kind": kind,
        "title": title,
        "message": message,
        "seed_required_venues": seed_required,
        "system_errors": system_errors,
        "cloud_failures": cloud.get("failures") or [],
        "manual_recovery": "公営これ一発 v17（緊急SEED用）",
    }
    json_write(ALERT, value)
    return value


def preserve_on_schedule_error(now: datetime, message: str) -> int:
    previous = json_read(STATUS)
    if previous.get("date") != now.date().isoformat():
        # A prior-day URL can show yesterday's VTR. At the JST date boundary,
        # clear it even when the new official schedule is temporarily down.
        update_playlist([])
        previous = {
            "date": now.date().isoformat(),
            "card_count": 0,
            "held_count": 0,
            "visible_count": 0,
            "active_count": 0,
            "ended_kept": [],
            "seed_required": False,
            "seed_required_venues": [],
            "phase_counts": {},
            "streams": {},
            "venues": {},
        }
    previous.update({
        "system": "boat-auto-v3",
        "generated_at": now.isoformat(),
        "last_update_ok": False,
        "system_errors": [message],
    })
    json_write(STATUS, previous)
    json_write(STATE, previous)
    write_alert(now, [message], [], {"failures": []})
    print(f"::error::{message}")
    print("BOAT AUTO: previous playlist and EPG preserved")
    return 0


def write_schedule_pending(now: datetime) -> int:
    """Reset yesterday at midnight without alerting before cards are published."""
    update_playlist([])
    epg_counts = {"public_sports_epg_local.xml": overlay_epg_file(LOCAL_EPG, {}, now.date())}
    if GUIDES.exists() and GUIDES.stat().st_size:
        epg_counts["guides.xml"] = overlay_epg_file(GUIDES, {}, now.date())
    alert = write_alert(now, [], [], {"failures": []})
    state = {
        "system": "boat-auto-v3",
        "date": now.date().isoformat(),
        "generated_at": now.isoformat(),
        "last_update_ok": True,
        "schedule_pending": True,
        "retention_policy": "開催場はJST日付変更まで保持。終了しても削除しない。",
        "epg_finished_title": "本日の開催は終了しました",
        "card_count": 0,
        "held_count": 0,
        "visible_count": 0,
        "active_count": 0,
        "ended_kept": [],
        "seed_required": False,
        "seed_required_venues": [],
        "system_errors": [],
        "phase_counts": {},
        "cloud_acquisition": {"requested": 0, "fetched": 0, "failures": []},
        "epg_programmes_written": epg_counts,
        "alert": {"active": alert["active"], "kind": alert["kind"]},
        "streams": {},
        "venues": {},
    }
    json_write(STATE, state)
    json_write(STATUS, state)
    print("BOAT AUTO: 05:00 JST前の開催表準備待ち; prior-day URLs cleared")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-guides", action="store_true", help="Do not overlay guides.xml")
    args = parser.parse_args()

    now = now_jst()
    day = now.date()
    try:
        cards = fetch_cards(day)
    except Exception as exc:
        # The upstream API explicitly returns 404 until the new JST day's data is
        # published. Treat that as a normal pre-dawn waiting state, not a system
        # failure. From 05:00 onward the same 404 is abnormal and must alert.
        if now.hour < 5 and schedule_not_published_error(exc):
            return write_schedule_pending(now)
        return preserve_on_schedule_error(now, f"BOAT EPG/開催表取得失敗: {type(exc).__name__}: {exc}")
    if not cards:
        if now.hour < 5:
            return write_schedule_pending(now)
        return preserve_on_schedule_error(now, "BOAT EPG/開催表が0場です")

    streams = load_current_streams(day)
    cloud = refresh_cloud_streams(cards, streams, day)
    held_ids = {VENUES[jcd][1] for jcd in cards}
    streams = {tvg_id: item for tvg_id, item in streams.items() if tvg_id in held_ids}
    venues, rows, phase_counts = build_venue_state(cards, streams, now)
    update_playlist(rows)

    epg_counts = {"public_sports_epg_local.xml": overlay_epg_file(LOCAL_EPG, cards, day)}
    if not args.skip_guides and GUIDES.exists() and GUIDES.stat().st_size:
        epg_counts["guides.xml"] = overlay_epg_file(GUIDES, cards, day)

    seed_required = [item["name"] for item in venues.values() if item.get("seed_required")]
    ended_kept = [item["name"] for item in venues.values() if item.get("ended") and item.get("visible")]
    system_errors = []
    hard_cloud_failures = [
        item for item in (cloud.get("failures") or [])
        if "no current stream" not in str(item.get("error") or "")
    ]
    if cloud.get("fetched") == 0 and hard_cloud_failures and not any(
        item.get("visible") and not item.get("token_expired") for item in venues.values()
    ):
        system_errors.append("Vercel KIXから当日BOAT SEEDを取得できません")

    alert = write_alert(now, system_errors, seed_required, cloud)
    state_streams = {
        tvg_id: streams[tvg_id]
        for tvg_id, item in venues.items()
        if item.get("visible") and tvg_id in streams
    }
    state = {
        "system": "boat-auto-v3",
        "date": day.isoformat(),
        "generated_at": now.isoformat(),
        "last_update_ok": not system_errors,
        "schedule_source": SCHEDULE_API.format(year=day.strftime("%Y"), ymd=day.strftime("%Y%m%d")),
        "stream_source": "Vercel KIX automatic acquisition; 公営これ一発 v17 is emergency SEED only",
        "retention_policy": "開催場はJST日付変更まで保持。終了しても削除しない。",
        "epg_finished_title": "本日の開催は終了しました",
        "alert_lead_minutes": ALERT_LEAD_MINUTES,
        "card_count": len(cards),
        "held_count": len(cards),
        "visible_count": len(rows),
        "active_count": sum(1 for item in venues.values() if item.get("active")),
        "ended_kept": ended_kept,
        "seed_required": bool(seed_required),
        "seed_required_venues": seed_required,
        "system_errors": system_errors,
        "phase_counts": phase_counts,
        "cloud_acquisition": cloud,
        "epg_programmes_written": epg_counts,
        "alert": {"active": alert["active"], "kind": alert["kind"]},
        "streams": state_streams,
        "venues": venues,
    }
    json_write(STATE, state)
    json_write(STATUS, state)

    print(
        "BOAT AUTO v3:",
        f"held={len(cards)} visible={len(rows)} active={state['active_count']}",
        f"ended-kept={len(ended_kept)} seed-required={len(seed_required)}",
    )
    for mode in MODE_ORDER:
        values = phase_counts[mode]
        print(
            f"  {MODE_LABEL[mode]}: held={values['held']} acquired={values['acquired']} "
            f"active={values['active']} ended={values['ended']}"
        )
    if seed_required:
        print("::warning::公営これ一発 v17 SEED required: " + "、".join(seed_required))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

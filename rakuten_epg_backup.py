from __future__ import annotations

import copy
import json
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

GUIDES = Path("guides.xml")
REPORT = Path("epg_coverage.txt")
KARENDA_GUIDES_URL = "https://raw.githubusercontent.com/karenda-jp/etc/refs/heads/main/guides.xml"
JST = timezone(timedelta(hours=9))

RAKUTEN_CHANNELS = {
    "rch_30": "鉄道・旅",
    "rch_35": "パチンコ・パチスロ",
    "rch_37": "エンタメ～テレDEEP",
    "rch_86": "ワンニャンチャンネル",
    "rch_113": "ぷれいば！ ～ゲーム専門チャンネル～",
    "rch_46": "釣り",
    "rch_125": "セクシーエンタメチャンネル",
    "rch_124": "おとなの歓楽街 by MEN'S NECO",
    "rch_41": "アイドル・グラビア",
    "rch_123": "刺激ストロング",
    "rch_122": "映画（年齢制限あり）",
}

RAKUTEN_OFFICIAL_NUMBERS = {
    186: "rch_30",
    207: "rch_35",
    218: "rch_37",
    192: "rch_86",
    196: "rch_113",
    198: "rch_46",
    239: "rch_125",
    240: "rch_124",
    241: "rch_41",
    242: "rch_123",
    243: "rch_122",
}

TITLE_KEYS = {
    "title", "programtitle", "programmetitle", "programname", "name",
    "episodetitle", "displaytitle",
}
START_KEYS = {
    "start", "startat", "starttime", "startdatetime", "startdate",
    "broadcaststart", "broadcaststartat", "from", "begin", "begintime",
}
END_KEYS = {
    "end", "endat", "endtime", "enddatetime", "enddate", "stop",
    "broadcastend", "broadcastendat", "to", "finish", "finishtime",
}


def norm_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def parse_dt(value: Any) -> datetime | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if number > 10_000_000_000:
            number /= 1000.0
        if number > 1_000_000_000:
            try:
                return datetime.fromtimestamp(number, timezone.utc).astimezone(JST)
            except Exception:
                return None
        return None
    text = str(value).strip()
    if not text:
        return None
    if re.fullmatch(r"\d{13}", text):
        try:
            return datetime.fromtimestamp(int(text) / 1000, timezone.utc).astimezone(JST)
        except Exception:
            return None
    if re.fullmatch(r"\d{10}", text):
        try:
            return datetime.fromtimestamp(int(text), timezone.utc).astimezone(JST)
        except Exception:
            return None
    text = text.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        return dt.astimezone(JST)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=JST)
        except ValueError:
            continue
    return None


def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def parse_xmltv_time(value: str | None) -> datetime | None:
    if not value:
        return None
    m = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", value.strip())
    if not m:
        return None
    stamp, offset = m.groups()
    try:
        if offset:
            return datetime.strptime(f"{stamp} {offset}", "%Y%m%d%H%M%S %z").astimezone(JST)
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    except ValueError:
        return None


def is_synthetic(programme: ET.Element) -> bool:
    desc = (programme.findtext("desc") or "")
    category = (programme.findtext("category") or "")
    return "番組詳細EPG未取得" in desc or "実EPG未対応" in desc or category in {"その他", "24H"}


def current_real_programmes(root: ET.Element, channel_id: str) -> list[ET.Element]:
    now = datetime.now(JST)
    window_start = now - timedelta(hours=2)
    window_end = now + timedelta(days=3)
    result: list[ET.Element] = []
    for programme in root.findall("programme"):
        if programme.get("channel") != channel_id or is_synthetic(programme):
            continue
        start = parse_xmltv_time(programme.get("start"))
        stop = parse_xmltv_time(programme.get("stop"))
        if start is None:
            continue
        if stop is None or stop <= start:
            stop = start + timedelta(hours=1)
        if stop >= window_start and start <= window_end:
            result.append(programme)
    return result


class ScriptCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_script = False
        self.parts: list[str] = []
        self.scripts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "script":
            self.in_script = True
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.in_script:
            self.parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "script" and self.in_script:
            text = "".join(self.parts).strip()
            if text:
                self.scripts.append(text)
            self.in_script = False
            self.parts = []


def fetch_html(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
            "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
            "Referer": "https://channel.rakuten.co.jp/",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return response.read().decode("utf-8", errors="replace")


def channel_from_value(value: Any) -> str | None:
    if isinstance(value, (int, float)) and int(value) == value:
        number = int(value)
        if number in RAKUTEN_OFFICIAL_NUMBERS:
            return RAKUTEN_OFFICIAL_NUMBERS[number]
        cid = f"rch_{number}"
        return cid if cid in RAKUTEN_CHANNELS else None
    if isinstance(value, str):
        text = value.strip()
        m = re.fullmatch(r"(?:rch[_-]?)?(\d{1,3})", text, re.I)
        if m:
            number = int(m.group(1))
            if number in RAKUTEN_OFFICIAL_NUMBERS:
                return RAKUTEN_OFFICIAL_NUMBERS[number]
            cid = f"rch_{number}"
            return cid if cid in RAKUTEN_CHANNELS else None
    if isinstance(value, dict):
        for key, nested in value.items():
            nk = norm_key(str(key))
            if nk in {"id", "channelid", "rchchannelid", "channelno", "channelnumber"}:
                cid = channel_from_value(nested)
                if cid:
                    return cid
    return None


def item_channel(item: dict[str, Any]) -> str | None:
    for key, value in item.items():
        nk = norm_key(str(key))
        if nk in {"channelid", "rchchannelid", "channelno", "channelnumber", "channel"}:
            cid = channel_from_value(value)
            if cid:
                return cid
    # Some payloads keep the channel object one level below the programme object.
    for key, value in item.items():
        if "channel" in norm_key(str(key)):
            cid = channel_from_value(value)
            if cid:
                return cid
    return None


def first_value(item: dict[str, Any], accepted: set[str]) -> Any:
    for key, value in item.items():
        if norm_key(str(key)) in accepted:
            return value
    return None


def walk_json(value: Any, found: dict[str, list[tuple[datetime, datetime, str]]]) -> None:
    if isinstance(value, dict):
        cid = item_channel(value)
        if cid:
            title_value = first_value(value, TITLE_KEYS)
            start_value = first_value(value, START_KEYS)
            end_value = first_value(value, END_KEYS)
            title = str(title_value or "").strip()
            start = parse_dt(start_value)
            end = parse_dt(end_value)
            if title and start:
                if end is None or end <= start:
                    end = start + timedelta(hours=1)
                if end - start <= timedelta(hours=12):
                    found[cid].append((start, end, title))
        for child in value.values():
            walk_json(child, found)
    elif isinstance(value, list):
        for child in value:
            walk_json(child, found)


def parse_official_html(html: str) -> dict[str, list[tuple[datetime, datetime, str]]]:
    found = {cid: [] for cid in RAKUTEN_CHANNELS}
    parser = ScriptCollector()
    parser.feed(html)
    blobs = list(parser.scripts)

    # Some frameworks put escaped JSON directly in the document rather than a
    # dedicated application/json script. Extract only large object/array blobs.
    for match in re.finditer(r"(?:__NEXT_DATA__|__NUXT__|initialState|pageProps)[^=]*=\s*({.*?})\s*;", html, re.S | re.I):
        blobs.append(match.group(1))

    for blob in blobs:
        candidate = blob.strip()
        if not candidate or candidate[0] not in "[{":
            continue
        try:
            data = json.loads(candidate)
        except Exception:
            continue
        walk_json(data, found)

    now = datetime.now(JST)
    lo = now - timedelta(hours=6)
    hi = now + timedelta(days=4)
    for cid, rows in found.items():
        dedup: dict[tuple[str, str, str], tuple[datetime, datetime, str]] = {}
        for start, end, title in rows:
            if end < lo or start > hi:
                continue
            key = (start.isoformat(), end.isoformat(), title)
            dedup[key] = (start, end, title)
        found[cid] = sorted(dedup.values(), key=lambda row: row[0])
    return found



def parse_rakuten_browser_text(text: str, day) -> dict[str, list[tuple[datetime, datetime, str]]]:
    """Parse the visible restricted-channel schedule rendered by Rakuten's own web app."""
    found = {cid: [] for cid in RAKUTEN_CHANNELS}
    if not text:
        return found
    markers = list(re.finditer(r"(?im)^\s*CH\s*(239|240|241|242|243)\b.*$", text))
    for idx, marker in enumerate(markers):
        number = int(marker.group(1))
        cid = RAKUTEN_OFFICIAL_NUMBERS.get(number)
        if not cid:
            continue
        end_pos = markers[idx + 1].start() if idx + 1 < len(markers) else len(text)
        segment = text[marker.end():end_pos]
        times = list(re.finditer(
            r"(?m)^\s*(\d{1,2}):(\d{2})\s*[-–—〜～~]\s*(\d{1,2}):(\d{2})\s*$",
            segment,
        ))
        for t_idx, tm in enumerate(times):
            sh, sm, eh, em = map(int, tm.groups())
            if sh > 23 or eh > 23 or sm > 59 or em > 59:
                continue
            title_end = times[t_idx + 1].start() if t_idx + 1 < len(times) else len(segment)
            title_lines = [
                line.strip()
                for line in segment[tm.end():title_end].splitlines()
                if line.strip()
            ]
            if not title_lines:
                continue
            title = " ".join(title_lines)
            # Trim trailing page furniture if this is the last card in a channel column.
            title = re.split(r"\s+(?:スマホアプリ|その他（年齢制限）チャンネル)\b", title, maxsplit=1)[0].strip()
            if not title:
                continue
            start = datetime(day.year, day.month, day.day, sh, sm, tzinfo=JST)
            stop = datetime(day.year, day.month, day.day, eh, em, tzinfo=JST)
            if stop <= start:
                stop += timedelta(days=1)
            found[cid].append((start, stop, title))
    return found


def fetch_official_browser(days) -> tuple[dict[str, list[tuple[datetime, datetime, str]]], list[str]]:
    """Render Rakuten's schedule with Chrome and select the age-restricted group.

    The public JSON endpoint has changed repeatedly.  The browser fallback follows
    the same public UI a viewer sees, so it also picks up CH241 when that API
    requires page-generated request parameters.
    """
    merged = {cid: [] for cid in RAKUTEN_CHANNELS}
    errors: list[str] = []
    helper = Path("rakuten_schedule_browser.mjs")
    if not helper.exists():
        return merged, ["Rakuten browser helper missing"]
    try:
        proc = subprocess.run(
            ["node", str(helper), *[d.isoformat() for d in days]],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=75,
            check=False,
        )
    except Exception as exc:
        return merged, [f"Rakuten browser fallback: {type(exc).__name__}: {exc}"]
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-3:]
        return merged, ["Rakuten browser fallback failed: " + " | ".join(tail)]
    try:
        payload = json.loads(proc.stdout.strip().splitlines()[-1])
    except Exception as exc:
        return merged, [f"Rakuten browser fallback JSON: {type(exc).__name__}: {exc}"]

    pages = payload.get("pages") or {}
    for date_text, page in pages.items():
        try:
            day = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError:
            continue
        text = str((page or {}).get("text") or "")
        selected = bool((page or {}).get("selected"))
        parsed = parse_rakuten_browser_text(text, day)
        count = sum(len(rows) for rows in parsed.values())
        if not selected:
            errors.append(f"Rakuten browser {date_text}: age-restricted selector not found")
        if not count:
            snippet = str((page or {}).get("snippet241") or "").replace("\n", " | ").strip()
            if len(snippet) > 900:
                snippet = snippet[:900] + "..."
            net = [str(x) for x in ((page or {}).get("network") or [])]
            net_text = " || ".join(net[-20:])
            if len(net_text) > 1800:
                net_text = net_text[-1800:]
            api_items = (page or {}).get("api") or []
            api_texts = []
            for item in api_items[-6:]:
                url = str(item.get("url") or "")
                method = str(item.get("method") or "")
                status = str(item.get("status") or "")
                post = str(item.get("postData") or "")
                body = str(item.get("body") or "")
                sample = body[:5000].replace("\n"," ")
                api_texts.append(f"{method} {status} {url} POST={post[:1200]} BODY={sample}")
            api_text = " || ".join(api_texts)
            if len(api_text) > 12000:
                api_text = api_text[:12000]
            errors.append(f"Rakuten browser {date_text}: parsed 0 restricted programmes; CH241={snippet!r}; NET={net_text}; API={api_text}")
        for cid, rows in parsed.items():
            merged[cid].extend(rows)
    return merged, errors

def fetch_official() -> tuple[dict[str, list[tuple[datetime, datetime, str]]], list[str]]:
    merged = {cid: [] for cid in RAKUTEN_CHANNELS}
    errors: list[str] = []
    today = datetime.now(JST).date()

    # Primary path: Rakuten's public backend API used by the schedule page.
    # The API exposes visible channel numbers (e.g. 241 for アイドル・グラビア),
    # not our legacy rch_41 ID, so channel_from_value() maps them explicitly.
    api_base = "https://backendapi.channel.rakuten.co.jp/platform/content/programs"
    for i in range(4):
        date = (today + timedelta(days=i)).isoformat()
        api_ok = False
        for platform in ("web", "pc"):
            url = f"{api_base}?platform={platform}&date={date}"
            try:
                req = urllib.request.Request(
                    url,
                    headers={
                        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/138 Safari/537.36",
                        "Accept": "application/json,text/plain,*/*",
                        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
                        "Referer": "https://channel.rakuten.co.jp/schedule",
                    },
                )
                with urllib.request.urlopen(req, timeout=20) as response:
                    data = json.load(response)
                parsed = {cid: [] for cid in RAKUTEN_CHANNELS}
                walk_json(data, parsed)
                count = sum(len(rows) for rows in parsed.values())
                if count:
                    for cid, rows in parsed.items():
                        merged[cid].extend(rows)
                    api_ok = True
                    break
                errors.append(f"{url}: parsed 0 target programmes")
            except Exception as exc:
                errors.append(f"{url}: {type(exc).__name__}: {exc}")
        if not api_ok:
            errors.append(f"Rakuten API yielded no target programmes for {date}")

    # Secondary path kept as a compatibility fallback in case Rakuten changes
    # the backend API but starts embedding schedule JSON in the HTML again.
    urls = ["https://channel.rakuten.co.jp/schedule"]
    urls.extend(f"https://channel.rakuten.co.jp/schedule/{(today + timedelta(days=i)).isoformat()}" for i in range(4))
    for url in urls:
        try:
            parsed = parse_official_html(fetch_html(url))
            for cid, rows in parsed.items():
                merged[cid].extend(rows)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")

    # Final public-page fallback for the restricted group.  Karenda intentionally
    # omits R-18 schedules, while Rakuten's current web UI still displays them.
    # Render the official page, select the restricted group, and read the same
    # visible programme grid instead of hard-coding a transient signed API URL.
    restricted_ids = {"rch_125", "rch_124", "rch_41", "rch_123", "rch_122"}
    if any(not merged.get(cid) for cid in restricted_ids):
        days = [today + timedelta(days=i) for i in range(4)]
        browser_rows, browser_errors = fetch_official_browser(days)
        errors.extend(browser_errors)
        for cid, rows in browser_rows.items():
            if rows:
                merged[cid].extend(rows)

    for cid, rows in merged.items():
        dedup: dict[tuple[str, str, str], tuple[datetime, datetime, str]] = {}
        for row in rows:
            dedup[(row[0].isoformat(), row[1].isoformat(), row[2])] = row
        merged[cid] = sorted(dedup.values(), key=lambda row: row[0])
    return merged, errors


def fetch_karenda_root() -> tuple[ET.Element | None, str | None]:
    """Fetch karenda-jp guides.xml as a secondary Rch EPG source."""
    try:
        req = urllib.request.Request(
            KARENDA_GUIDES_URL,
            headers={"User-Agent": "Mozilla/5.0 (FreeWiFi Rch EPG backup)"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            return ET.fromstring(response.read()), None
    except Exception as exc:
        return None, f"{KARENDA_GUIDES_URL}: {type(exc).__name__}: {exc}"


def replace_with_external(root: ET.Element, external: ET.Element, channel_id: str) -> int:
    programmes = current_real_programmes(external, channel_id)
    if not programmes:
        return 0
    for programme in list(root.findall("programme")):
        if programme.get("channel") == channel_id:
            root.remove(programme)
    for channel in list(root.findall("channel")):
        if channel.get("id") == channel_id:
            root.remove(channel)
    external_channel = external.find(f"channel[@id='{channel_id}']")
    if external_channel is not None:
        root.append(copy.deepcopy(external_channel))
    else:
        channel = ET.SubElement(root, "channel", {"id": channel_id})
        ET.SubElement(channel, "display-name").text = RAKUTEN_CHANNELS[channel_id]
    for programme in programmes:
        root.append(copy.deepcopy(programme))
    return len(programmes)


def previous_guides_root() -> ET.Element | None:
    try:
        proc = subprocess.run(
            ["git", "show", "HEAD:guides.xml"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
        if proc.returncode != 0 or not proc.stdout:
            return None
        return ET.fromstring(proc.stdout)
    except Exception:
        return None


def replace_with_official(root: ET.Element, channel_id: str, rows: list[tuple[datetime, datetime, str]]) -> int:
    for programme in list(root.findall("programme")):
        if programme.get("channel") == channel_id:
            root.remove(programme)
    for channel in list(root.findall("channel")):
        if channel.get("id") == channel_id:
            root.remove(channel)
    channel = ET.SubElement(root, "channel", {"id": channel_id})
    ET.SubElement(channel, "display-name").text = RAKUTEN_CHANNELS[channel_id]
    for start, stop, title in rows:
        programme = ET.SubElement(
            root,
            "programme",
            {"start": xmltv_time(start), "stop": xmltv_time(stop), "channel": channel_id},
        )
        ET.SubElement(programme, "title", {"lang": "ja"}).text = title
        ET.SubElement(programme, "category", {"lang": "ja"}).text = "楽天Rチャンネル"
    return len(rows)


def replace_with_previous(root: ET.Element, previous: ET.Element, channel_id: str) -> int:
    programmes = current_real_programmes(previous, channel_id)
    if not programmes:
        return 0
    for programme in list(root.findall("programme")):
        if programme.get("channel") == channel_id:
            root.remove(programme)
    for channel in list(root.findall("channel")):
        if channel.get("id") == channel_id:
            root.remove(channel)
    previous_channel = previous.find(f"channel[@id='{channel_id}']")
    if previous_channel is not None:
        root.append(copy.deepcopy(previous_channel))
    else:
        channel = ET.SubElement(root, "channel", {"id": channel_id})
        ET.SubElement(channel, "display-name").text = RAKUTEN_CHANNELS[channel_id]
    for programme in programmes:
        root.append(copy.deepcopy(programme))
    return len(programmes)


def update_report(rescued: dict[str, tuple[str, int]], errors: list[str]) -> None:
    if not REPORT.exists():
        return
    lines = REPORT.read_text(encoding="utf-8", errors="replace").splitlines()
    fallback_delta = 0
    real_delta = 0
    for index, line in enumerate(lines):
        parts = line.split("\t")
        if len(parts) < 2 or parts[1] not in rescued:
            continue
        cid = parts[1]
        source, count = rescued[cid]
        if line.startswith("FALLBACK\t"):
            fallback_delta -= 1
            real_delta += 1
        lines[index] = f"OK_BACKUP\t{cid}\t{RAKUTEN_CHANNELS[cid]}\t{source}\t{count} programmes"

    def adjust(prefix: str, delta: int) -> None:
        if not delta:
            return
        for idx, line in enumerate(lines):
            if line.startswith(prefix):
                try:
                    value = int(line.split("=", 1)[1])
                except Exception:
                    return
                lines[idx] = f"{prefix}{value + delta}"
                return

    adjust("matched_real=", real_delta)
    adjust("fallback=", fallback_delta)
    adjust("unmatched_real=", fallback_delta)
    if errors:
        lines.append("")
        lines.append("[Rakuten official backup diagnostics]")
        lines.extend(errors[-8:])
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    if not GUIDES.exists():
        print("RAKUTEN BACKUP: guides.xml missing; skipped")
        return 0
    root = ET.parse(GUIDES).getroot()
    missing = [cid for cid in RAKUTEN_CHANNELS if not current_real_programmes(root, cid)]
    if not missing:
        print("RAKUTEN BACKUP: all target channels already have current real EPG")
        return 0

    official, errors = fetch_official()
    karenda, karenda_error = fetch_karenda_root()
    if karenda_error:
        errors.append(karenda_error)
    previous = previous_guides_root()
    rescued: dict[str, tuple[str, int]] = {}

    for cid in missing:
        rows = official.get(cid) or []
        if rows:
            count = replace_with_official(root, cid, rows)
            rescued[cid] = ("rakuten-official", count)
            continue
        if karenda is not None:
            count = replace_with_external(root, karenda, cid)
            if count:
                rescued[cid] = ("karenda-jp", count)
                continue
        if previous is not None:
            count = replace_with_previous(root, previous, cid)
            if count:
                rescued[cid] = ("previous-good-cache", count)

    ET.ElementTree(root).write(GUIDES, encoding="utf-8", xml_declaration=True)
    update_report(rescued, errors)

    still_missing = [cid for cid in RAKUTEN_CHANNELS if not current_real_programmes(root, cid)]
    print(f"RAKUTEN BACKUP: missing_before={missing} rescued={rescued} remaining={still_missing}")
    if errors:
        print("RAKUTEN BACKUP: official diagnostics:")
        for line in errors[-5:]:
            print("  " + line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

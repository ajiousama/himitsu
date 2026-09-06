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
JST = timezone(timedelta(hours=9))

RAKUTEN_CHANNELS = {
    "rch_30": "鉄道・旅",
    "rch_98": "セクシーエンタメチャンネル",
    "rch_59": "おとなの歓楽街 by MEN'S NECO",
    "rch_41": "アイドル・グラビア",
    "rch_40": "刺激ストロング",
    "rch_42": "映画（年齢制限あり）",
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
        cid = f"rch_{int(value)}"
        return cid if cid in RAKUTEN_CHANNELS else None
    if isinstance(value, str):
        text = value.strip()
        m = re.fullmatch(r"(?:rch[_-]?)?(\d{1,3})", text, re.I)
        if m:
            cid = f"rch_{int(m.group(1))}"
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


def fetch_official() -> tuple[dict[str, list[tuple[datetime, datetime, str]]], list[str]]:
    merged = {cid: [] for cid in RAKUTEN_CHANNELS}
    errors: list[str] = []
    today = datetime.now(JST).date()
    urls = ["https://channel.rakuten.co.jp/schedule"]
    urls.extend(f"https://channel.rakuten.co.jp/schedule/{(today + timedelta(days=i)).isoformat()}" for i in range(4))
    for url in urls:
        try:
            parsed = parse_official_html(fetch_html(url))
            for cid, rows in parsed.items():
                merged[cid].extend(rows)
        except Exception as exc:
            errors.append(f"{url}: {type(exc).__name__}: {exc}")
    for cid, rows in merged.items():
        dedup: dict[tuple[str, str, str], tuple[datetime, datetime, str]] = {}
        for row in rows:
            dedup[(row[0].isoformat(), row[1].isoformat(), row[2])] = row
        merged[cid] = sorted(dedup.values(), key=lambda row: row[0])
    return merged, errors


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
    previous = previous_guides_root()
    rescued: dict[str, tuple[str, int]] = {}

    for cid in missing:
        rows = official.get(cid) or []
        if rows:
            count = replace_with_official(root, cid, rows)
            rescued[cid] = ("rakuten-official", count)
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

#!/usr/bin/env python3
from radiko_freewifi import discover_stations, replace_radiko_block, write_radio_playlist


def main():
    stations = discover_stations()
    if len(stations) < 100:
        raise SystemExit(f"radiko station discovery too small: {len(stations)}")
    free_count, removed = replace_radiko_block(stations)
    radio_count = write_radio_playlist(stations)
    print(f"old/duplicate radiko entries removed: {removed}")
    print(f"FreeWiFi selected radio stations: {free_count}")
    print(f"radio.m3u other Radiko stations: {radio_count}")
    if free_count < 10 or radio_count < 80:
        raise SystemExit("radio split result too small")


if __name__ == "__main__":
    main()

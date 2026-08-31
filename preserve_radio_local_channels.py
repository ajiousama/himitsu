#!/usr/bin/env python3
from radiko_freewifi import discover_stations, write_radio_playlist


def main():
    stations = discover_stations()
    if len(stations) < 100:
        raise SystemExit(f"radiko station discovery too small: {len(stations)}")
    radio_count = write_radio_playlist(stations)
    print(f"radio.m3u all Radiko stations: {radio_count}")
    print("FreeWiFi untouched")
    if radio_count < 100:
        raise SystemExit("radio catalog result too small")


if __name__ == "__main__":
    main()

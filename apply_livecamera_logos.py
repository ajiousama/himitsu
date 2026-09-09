from pathlib import Path
import json
import re

RAW = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/'
SOURCES = [
    Path('general_youtube_sources.json'),
    Path('general_youtube_sources_airports.json'),
    Path('general_youtube_sources_ports.json'),
]
TARGETS = [Path('general_youtube.m3u'), Path('freewifi')]

# New filenames are used from 44 onward because some APTV clients kept the
# old generic YouTube-card image even after a query-string cache revision.
CACHE_REV = '20260909-photo-v4'

CANONICAL = {
    'youtube.kana_tube': 'yt43_01_kana_tube.png',
    'youtube.natsu_shiba': 'yt43_02_natsu_shiba.png',
    'youtube.konodo1': 'yt43_03_konodo_horse_1.png',
    'youtube.konodo2': 'yt43_04_konodo_horse_2.png',
    'youtube.osaka_station': 'yt43_05_jr_osaka.png',
    'youtube.kobe_waterfront': 'yt43_06_kobe_waterfront.png',
    'youtube.kyoto_rail': 'yt43_07_kyoto_rail_4k.png',
    'youtube.kyoto_station': 'yt43_08_kyoto_bus_terminal.png',
    'youtube.itami_airport': 'yt43_09_itami_airport.png',
    'youtube.haneda_t2': 'yt43_10_haneda_t2.png',
    'youtube.centrair': 'yt43_11_centrair.png',
    'youtube.new_chitose': 'yt43_12_new_chitose.png',
    'youtube.fukuoka_ube': 'yt43_13_fukuoka_ube.png',
    'youtube.narita_a': 'yt43_14_narita_a.png',
    'youtube.kix': 'yt43_15_kix_t1.png',
    'youtube.muko': 'yt43_16_muko.png',
    'youtube.katsuragawa': 'yt43_17_katsuragawa.png',
    'youtube.matsuyama_airport_ebc': 'yt43_18_matsuyama_airport_ebc.png',
    'youtube.matsuyama_castle_rnb': 'yt43_19_matsuyama_castle_rnb.png',
    'youtube.matsuyama_clean': 'yt43_20_matsuyama_clean.png',
    'youtube.namibia': 'yt43_21_namibia.png',
    'youtube.dogo': 'yt43_22_dogo.png',
    'youtube.honmachi': 'yt43_23_matsuyama_honmachi.png',
    'youtube.yawatahama_sea': 'yt43_24_yawatahama_sea.png',
    'youtube.yawatahama_parking': 'yt43_25_yawatahama_parking.png',
    'youtube.uwajima': 'yt43_26_uwajima.png',
    'youtube.shimanami': 'yt43_27_shimanami.png',
    'youtube.beppu_matsuyama': 'yt43_28_matsuyama_beppu.png',
    'youtube.akashi_sa_up': 'yt43_29_akashi_sa_up.png',
    'youtube.kbn_seto_bridge': 'yt43_30_kbn_seto_bridge.png',
    'youtube.awaji_monkey': 'yt43_31_awaji_monkey.png',
    'youtube.ehime_mandarin': 'yt43_32_ehime_mandarin.png',
    'youtube.chinchilla_room': 'yt43_33_chinchilla_room.png',
    'youtube.kobe_airport_ytv': 'yt43_34_kobe_airport_ytv.png',
    'youtube.narita_t1': 'yt43_35_narita_t1.png',
    'youtube.kix_mbs': 'yt43_36_kix_mbs.png',
    'youtube.kix_ytv': 'yt43_37_kix_ytv.png',
    'youtube.tokyo_haneda': 'yt43_38_tokyo_haneda.png',
    'youtube.kurushima_bridge': 'yt43_39_kurushima_bridge.png',
    'youtube.akashi_bridge': 'yt43_40_akashi_bridge.png',
    'youtube.kobe_waterfront2': 'yt43_41_kobe_waterfront2.png',
    'youtube.osaka_loop': 'yt43_42_osaka_loop.png',
    'youtube.nomura_dam': 'yt43_43_nomura_dam.png',
    'youtube.maiko_villa_akashi': 'yt43_44_maiko_villa_akashi_v4.png',
    'youtube.tokyo_dome_city': 'yt43_45_tokyo_dome_city_v4.png',
    'youtube.shinhotaka_ropeway': 'yt43_46_shinhotaka_ropeway_v4.png',
    'youtube.airport_okayama': 'yt43_47_airport_okayama_v4.png',
    'youtube.airport_hiroshima': 'yt43_48_airport_hiroshima_v4.png',
    'youtube.airport_nagasaki': 'yt43_49_airport_nagasaki_v4.png',
    'youtube.airport_goto': 'yt43_50_airport_goto_v4.png',
    'youtube.airport_kumamoto': 'yt43_51_airport_kumamoto_v4.png',
    'youtube.airport_oita': 'yt43_52_airport_oita_v4.png',
    'youtube.airport_miyazaki': 'yt43_53_airport_miyazaki_v4.png',
    'youtube.airport_amami': 'yt43_54_airport_amami_v4.png',
    'youtube.airport_naha': 'yt43_55_airport_naha_v4.png',
    'youtube.airport_sendai': 'yt43_56_airport_sendai_v4.png',
    'youtube.airport_hanamaki': 'yt43_57_airport_hanamaki_v4.png',
    'youtube.airport_yamagata': 'yt43_58_airport_yamagata_v4.png',
    'youtube.airport_fukushima': 'yt43_59_airport_fukushima_v4.png',
    'youtube.airport_obihiro': 'yt43_60_airport_obihiro_v4.png',
    'youtube.ehime_mishima_kawanoe_port': 'yt43_61_ehime_port_mishima_kawanoe_v4.png',
    'youtube.ehime_toyo_port': 'yt43_62_ehime_port_toyo_v4.png',
    'youtube.ehime_hashihama_port': 'yt43_63_ehime_port_hashihama_v4.png',
    'youtube.ehime_misaki_port': 'yt43_64_ehime_port_misaki_v4.png',
    'youtube.ehime_misho_port': 'yt43_65_ehime_port_misho_v4.png',
    'youtube.ehime_kuma_skiland': 'yt43_66_ehime_kuma_skiland_v4.png',
    'youtube.ehime_saragamine': 'yt43_67_ehime_saragamine_v4.png',
    'youtube.ehime_omogo_ishizuchi': 'yt43_68_ehime_omogo_ishizuchi_v4.png',
    'youtube.ehime_ainan_ebc': 'yt43_69_ehime_ainan_ebc_v4.png',
    'youtube.ehime_dogo_honkan': 'yt43_70_ehime_dogo_honkan_v4.png',
}


def logo_url(filename):
    url = RAW + filename
    m = re.match(r'yt43_(\d+)_', filename)
    if m and int(m.group(1)) >= 44:
        url += '?v=' + CACHE_REV
    return url


def logo_map():
    return {cid: logo_url(filename) for cid, filename in CANONICAL.items()}


def patch_sources(wanted):
    changed = 0
    for path in SOURCES:
        if not path.exists():
            continue
        items = json.loads(path.read_text(encoding='utf-8'))
        file_changed = 0
        for item in items:
            cid = str(item.get('id') or '').strip()
            logo = wanted.get(cid)
            if logo and item.get('logo') != logo:
                item['logo'] = logo
                file_changed += 1
        if file_changed:
            path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changed += file_changed
        print(path, 'source logos changed:', file_changed)
    return changed


def patch_line(line, wanted):
    if not line.startswith('#EXTINF:'):
        return line, False
    m = re.search(r'tvg-id="([^"]+)"', line)
    if not m:
        return line, False
    logo = wanted.get(m.group(1))
    if not logo:
        return line, False

    old = line
    if re.search(r'tvg-logo="[^"]*"', line):
        line = re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{logo}"', line, count=1)
    elif ' group-title=' in line:
        line = line.replace(' group-title=', f' tvg-logo="{logo}" group-title=', 1)
    else:
        comma = line.find(',')
        if comma >= 0:
            line = line[:comma] + f' tvg-logo="{logo}"' + line[comma:]
    return line, line != old


def patch_file(path, wanted):
    if not path.exists():
        print('skip missing', path)
        return 0
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    out = []
    changed = 0
    for line in text.splitlines():
        line, hit = patch_line(line, wanted)
        changed += int(hit)
        out.append(line)
    path.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
    print(path, 'playlist logo lines changed:', changed)
    return changed


def verify(path, wanted):
    if not path.exists():
        return
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    bad = []
    seen = set()
    for line in text.splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m or m.group(1) not in wanted:
            continue
        cid = m.group(1)
        seen.add(cid)
        expected = f'tvg-logo="{wanted[cid]}"'
        if expected not in line:
            bad.append(cid)
    if bad:
        raise SystemExit(f'{path}: wrong yt43 logo mapping: {bad}')
    print(path, 'canonical yt43 IDs verified:', len(seen))


def main():
    wanted = logo_map()
    print('canonical yt43 mappings:', len(wanted))
    patch_sources(wanted)
    for path in TARGETS:
        patch_file(path, wanted)
        verify(path, wanted)


if __name__ == '__main__':
    main()

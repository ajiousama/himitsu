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
    'youtube.kana_tube': 'unified/yt_kana_tube.png',
    'youtube.natsu_shiba': 'unified/yt_natsu_shiba.png',
    'youtube.konodo1': 'unified/yt_konodo1.png',
    'youtube.konodo2': 'unified/yt_konodo2.png',
    'youtube.osaka_station': 'unified/yt_osaka_station.png',
    'youtube.kobe_waterfront': 'unified/yt_kobe_waterfront.png',
    'youtube.kyoto_rail': 'unified/yt_kyoto_rail.png',
    'youtube.kyoto_station': 'unified/yt_kyoto_station.png',
    'youtube.itami_airport': 'unified/yt_itami_airport.png',
    'youtube.haneda_t2': 'unified/yt_haneda_t2.png',
    'youtube.centrair': 'unified/yt_centrair.png',
    'youtube.new_chitose': 'unified/yt_new_chitose.png',
    'youtube.fukuoka_ube': 'unified/yt_fukuoka_ube.png',
    'youtube.narita_a': 'unified/yt_narita_a.png',
    'youtube.kix': 'unified/yt_kix.png',
    'youtube.muko': 'unified/yt_muko.png',
    'youtube.katsuragawa': 'unified/yt_katsuragawa.png',
    'youtube.matsuyama_airport_ebc': 'unified/yt_matsuyama_airport_ebc.png',
    'youtube.matsuyama_castle_rnb': 'unified/yt_matsuyama_castle_rnb.png',
    'youtube.matsuyama_clean': 'unified/yt_matsuyama_clean.png',
    'youtube.namibia': 'unified/yt_namibia.png',
    'youtube.dogo': 'unified/yt_dogo.png',
    'youtube.honmachi': 'unified/yt_honmachi.png',
    'youtube.yawatahama_sea': 'unified/yt_yawatahama_sea.png',
    'youtube.yawatahama_parking': 'unified/yt_yawatahama_parking.png',
    'youtube.uwajima': 'unified/yt_uwajima.png',
    'youtube.shimanami': 'unified/yt_shimanami.png',
    'youtube.beppu_matsuyama': 'unified/yt_beppu_matsuyama.png',
    'youtube.akashi_sa_up': 'unified/yt_akashi_sa_up.png',
    'youtube.kbn_seto_bridge': 'unified/yt_kbn_seto_bridge.png',
    'youtube.awaji_monkey': 'unified/yt_awaji_monkey.png',
    'youtube.ehime_mandarin': 'unified/yt_ehime_mandarin.png',
    'youtube.chinchilla_room': 'unified/yt_chinchilla_room.png',
    'youtube.kobe_airport_ytv': 'unified/yt_kobe_airport_ytv.png',
    'youtube.narita_t1': 'unified/yt_narita_t1.png',
    'youtube.kix_mbs': 'unified/yt_kix.png',
    'youtube.kix_ytv': 'unified/yt_kix.png',
    'youtube.tokyo_haneda': 'unified/yt_tokyo_haneda.png',
    'youtube.kurushima_bridge': 'unified/yt_kurushima_bridge.png',
    'youtube.akashi_bridge': 'unified/yt_akashi_bridge.png',
    'youtube.kobe_waterfront2': 'unified/yt_kobe_waterfront2.png',
    'youtube.osaka_loop': 'unified/yt_osaka_loop.png',
    'youtube.nomura_dam': 'unified/yt_nomura_dam.png',
    'youtube.maiko_villa_akashi': 'yt43_44_maiko_villa_akashi_illustration.png',
    'youtube.tokyo_dome_city': 'yt43_45_tokyo_dome_city_illustration.png',
    'youtube.shinhotaka_ropeway': 'yt43_46_shinhotaka_ropeway_illustration.png',
    'youtube.airport_okayama': 'yt43_47_airport_okayama_illustration.png',
    'youtube.airport_hiroshima': 'yt43_48_airport_hiroshima_illustration.png',
    'youtube.airport_nagasaki': 'yt43_49_airport_nagasaki_illustration.png',
    'youtube.airport_goto': 'yt43_50_airport_goto_illustration.png',
    'youtube.airport_kumamoto': 'yt43_51_airport_kumamoto_illustration.png',
    'youtube.airport_oita': 'yt43_52_airport_oita_illustration.png',
    'youtube.airport_miyazaki': 'yt43_53_airport_miyazaki_illustration.png',
    'youtube.airport_amami': 'yt43_54_airport_amami_illustration.png',
    'youtube.airport_naha': 'yt43_55_airport_naha_illustration.png',
    'youtube.airport_sendai': 'yt43_56_airport_sendai_illustration.png',
    'youtube.airport_hanamaki': 'yt43_57_airport_hanamaki_illustration.png',
    'youtube.airport_yamagata': 'yt43_58_airport_yamagata_illustration.png',
    'youtube.airport_fukushima': 'yt43_59_airport_fukushima_illustration.png',
    'youtube.airport_obihiro': 'yt43_60_airport_obihiro_illustration.png',
    'youtube.ehime_mishima_kawanoe_port': 'yt43_61_ehime_mishima_kawanoe_port_illustration.png',
    'youtube.ehime_toyo_port': 'yt43_62_ehime_toyo_port_illustration.png',
    'youtube.ehime_hashihama_port': 'yt43_63_ehime_hashihama_port_illustration.png',
    'youtube.ehime_misaki_port': 'yt43_64_ehime_misaki_port_illustration.png',
    'youtube.ehime_misho_port': 'yt43_65_ehime_misho_port_illustration.png',
    'youtube.ehime_kuma_skiland': 'yt43_66_ehime_kuma_skiland_illustration.png',
    'youtube.ehime_saragamine': 'yt43_67_ehime_saragamine_illustration.png',
    'youtube.ehime_omogo_ishizuchi': 'yt43_68_ehime_omogo_ishizuchi_illustration.png',
    'youtube.ehime_ainan_ebc': 'yt43_69_ehime_ainan_ebc_illustration.png',
    'youtube.ehime_dogo_honkan': 'yt43_70_ehime_dogo_honkan_illustration.png',
}


def logo_url(filename):
    url = RAW + filename
    m = re.match(r'yt43_(\d+)_', filename)
    if m and int(m.group(1)) >= 44:
        rev = '20260919-illustration-v1' if 'illustration' in filename else CACHE_REV
        url += '?v=' + rev
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

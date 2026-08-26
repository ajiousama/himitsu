from pathlib import Path
import re
import xml.etree.ElementTree as ET

P = Path('freewifi')
GUIDES = Path('guides.xml')
END = '# === NAORI_MANAGED_END ==='
BASE = 'https://naori-test.netgenx.site/pxx.php?shk_cid='

# Confirmed by user playback. Metadata is copied from the existing Kansai entries
# so logo + tvg-id use the same values already covered by guides.xml.
KANSAI = {
    'gx01': ('毎日テレビ_jp', '毎日放送 (naori)', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FD2-041-400x400.png?'),
    'gx02': ('ABCテレビ_jp', '朝日放送 (naori)', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FD3-061-400x400.png?'),
    'gx03': ('関西テレビ_jp', '関西テレビ (naori)', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FD4-081-400x400.png?'),
    'gx04': ('読売テレビ_jp', '読売テレビ (naori)', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FD5-101-400x400.png?'),
    'gx05': ('テレビ大阪_jp', 'テレビ大阪 (naori)', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7D76-071-400x400.png?'),
    'gx06': ('NHK大阪・総合_jp', 'NHK G Osaka (naori)', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE0-011-400x400.png?'),
}

# tvg-id corrections found by comparing NAORI metadata with current guides.xml coverage.
ID_FIX = {
    'hdgd08': 'TOKYO・MX_jp',
    'bs11': 'NHK・BS_jp',
    'bs01': 'NHK・BSP_jp',
    'bs18': 'J-SPORTS-1_jp',
    'bs19': 'J-SPORTS-2_jp',
    'bs21': 'J-SPORTS-3_jp',
    'bs22': 'J-SPORTS-4_jp',
    'bs31': 'J-COM-BS_jp',
    'cs17': 'GAORA-SPORTS_jp',
    'cs21': 'MONDOTV_jp',
}


def cid_from_url(url):
    m = re.search(r'shk_cid=([^&#\s]+)', url)
    return m.group(1) if m else None


def replace_tvg_id(extinf, tvg_id):
    if re.search(r'tvg-id="[^"]*"', extinf):
        return re.sub(r'tvg-id="[^"]*"', f'tvg-id="{tvg_id}"', extinf, count=1)
    return extinf.replace('#EXTINF:-1', f'#EXTINF:-1 tvg-id="{tvg_id}"', 1)


text = P.read_text(encoding='utf-8-sig', errors='replace')
if END not in text:
    raise RuntimeError('NAORI managed block missing')

# Remove old gx01-gx06 entries so repeated runs stay idempotent.
lines = text.splitlines()
out = []
i = 0
while i < len(lines):
    if lines[i].startswith('#EXTINF:') and i + 1 < len(lines):
        cid = cid_from_url(lines[i + 1].strip())
        if cid in KANSAI:
            i += 2
            continue
    out.append(lines[i])
    i += 1
text = '\n'.join(out) + '\n'

# Add the six confirmed Kansai channels immediately before the managed-block end.
block = []
for cid, (tvg_id, name, logo) in KANSAI.items():
    block += [
        f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="関西(naori)",{name}',
        BASE + cid,
    ]
text = text.replace(END, '\n'.join(block) + '\n' + END)

# Correct known tvg-id mismatches for the rest of NAORI while preserving their logos/names.
lines = text.splitlines()
for i in range(len(lines) - 1):
    if not lines[i].startswith('#EXTINF:'):
        continue
    cid = cid_from_url(lines[i + 1].strip())
    if cid in ID_FIX:
        lines[i] = replace_tvg_id(lines[i], ID_FIX[cid])
text = '\n'.join(lines).rstrip() + '\n'

# Hard validation: every NAORI entry must have a logo and a tvg-id that exists in guides.xml.
root = ET.parse(GUIDES).getroot()
guide_ids = {c.get('id') for c in root.findall('channel') if c.get('id')}
missing_epg = []
missing_logo = []
naori_count = 0
lines = text.splitlines()
for i in range(len(lines) - 1):
    if not lines[i].startswith('#EXTINF:') or 'naori-test.netgenx.site/pxx.php?shk_cid=' not in lines[i + 1]:
        continue
    naori_count += 1
    m = re.search(r'tvg-id="([^"]+)"', lines[i])
    tvg_id = m.group(1) if m else ''
    if not tvg_id or tvg_id not in guide_ids:
        missing_epg.append((cid_from_url(lines[i + 1]), tvg_id))
    logo = re.search(r'tvg-logo="([^"]+)"', lines[i])
    if not logo or not logo.group(1).strip():
        missing_logo.append(cid_from_url(lines[i + 1]))

if missing_epg:
    raise RuntimeError(f'NAORI tvg-id not covered by guides.xml: {missing_epg}')
if missing_logo:
    raise RuntimeError(f'NAORI entries missing logo: {missing_logo}')

P.write_text(text, encoding='utf-8')
print('NAORI metadata OK:', naori_count, 'channels; Kansai gx01-gx06 confirmed; EPG ids/logos validated')

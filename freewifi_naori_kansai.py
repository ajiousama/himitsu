from pathlib import Path

P = Path('freewifi')
END = '# === NAORI_MANAGED_END ==='
BASE = 'https://naori-test.netgenx.site/pxx.php?shk_cid='

# Primehome/Kaiteki Kansai CID candidates for user-side playback testing.
# gx04/gx06 have prior NAORI observations; the others are test candidates.
CHANNELS = [
    ('毎日テレビ_jp', '毎日放送 (naori TEST)', 'gx01'),
    ('朝日放送_jp', 'ABCテレビ (naori TEST)', 'gx02'),
    ('関西テレビ_jp', '関西テレビ (naori TEST)', 'gx03'),
    ('読売テレビ_jp', '読売テレビ (naori)', 'gx04'),
    ('テレビ大阪_jp', 'テレビ大阪 (naori TEST)', 'gx05'),
    ('NHK大阪・総合_jp', 'NHK大阪 (naori)', 'gx06'),
]

text = P.read_text(encoding='utf-8-sig', errors='replace')
if END not in text:
    raise RuntimeError('NAORI managed block missing')

# Avoid duplicates on repeated runs.
for _, _, cid in CHANNELS:
    url = BASE + cid
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF:') and i + 1 < len(lines) and lines[i + 1].strip() == url:
            i += 2
            continue
        out.append(lines[i])
        i += 1
    text = '\n'.join(out) + '\n'

block = []
for tvg_id, name, cid in CHANNELS:
    block += [f'#EXTINF:-1 tvg-id="{tvg_id}" group-title="関西(naori)",{name}', BASE + cid]

text = text.replace(END, '\n'.join(block) + '\n' + END)
P.write_text(text, encoding='utf-8')
print('NAORI Kansai candidates added:', ', '.join(cid for _,_,cid in CHANNELS))

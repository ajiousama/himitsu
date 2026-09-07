from pathlib import Path
import re
import subprocess

CLEAN_REF = "98a3b8a899cc47af61685002b0893c0e45bab963"
TARGET = Path("freewifi_today_public_sports.py")

clean = subprocess.check_output(
    ["git", "show", f"{CLEAN_REF}:freewifi_today_public_sports.py"],
    text=True,
)

block = '''def local_logo(cid):
    if cid.startswith('chihou.'):
        slug = cid.split('.', 1)[1]
        slug = {'kawasaki_keiba': 'kawasaki', 'nagoya_keiba': 'nagoya', 'kochi_keiba': 'kochi'}.get(slug, slug)
        return f'{RAW_BASE}/logos/public_sports/venues/localrace_{slug}.png'
    if cid.startswith('keirin.'):
        slug = cid.split('.', 1)[1]
        return f'{RAW_BASE}/logos/public_sports/venues/keirin_{slug}.png'
    if cid.startswith('auto.'):
        slug = cid.split('.', 1)[1]
        return f'{RAW_BASE}/logos/public_sports/venues/autorace_{slug}.png'
    return None

'''

clean, n = re.subn(
    r"LOCAL_LOGOS = \{.*?\}\nJST =",
    block + "JST =",
    clean,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit("LOCAL_LOGOS block replacement failed")
clean = clean.replace("logo = LOCAL_LOGOS.get(cid)", "logo = local_logo(cid)")
TARGET.write_text(clean, encoding="utf-8")
print("restored", TARGET)

import re
import unicodedata

START = "# === AKARIKO_HARU_MANAGED_START ==="
END = "# === AKARIKO_HARU_MANAGED_END ==="


def _tvg_id(block):
    m = re.search(r'tvg-id="([^"]+)"', block)
    return m.group(1) if m else None


def _display_name(block):
    if ',' not in block:
        return ''
    name = block.split(',', 1)[1].splitlines()[0]
    name = re.sub(r'\s*\((?:haruka|akariko)\)\s*$', '', name, flags=re.I)
    name = unicodedata.normalize('NFKC', name)
    return re.sub(r'\s+', '', name).lower()


def _parse_managed_entries(body):
    lines = [line for line in body.splitlines() if line.strip()]
    entries = []
    i = 0
    while i < len(lines):
        if (
            lines[i].startswith('#EXTINF:')
            and i + 1 < len(lines)
            and not lines[i + 1].lstrip().startswith('#')
        ):
            entries.append(lines[i] + '\n' + lines[i + 1])
            i += 2
        else:
            i += 1
    return entries


def normalize_layout(text):
    # APTV accepts the Akariko source over HTTPS; normalize any stale HTTP form.
    text = text.replace(
        'http://haru.charandom.blog/',
        'https://haru.charandom.blog/',
    )

    start = text.find(START)
    end = text.find(END)
    managed_entries = []

    if start >= 0 and end > start:
        body = text[start + len(START):end]
        managed_entries = _parse_managed_entries(body)
        base = text[:start].rstrip()
        suffix = text[end + len(END):].strip()
    else:
        base = text.rstrip()
        suffix = ''

    remaining = list(managed_entries)
    by_id = {}
    by_name = {}
    for entry in managed_entries:
        tid = _tvg_id(entry)
        if tid:
            by_id.setdefault(tid, []).append(entry)
        name = _display_name(entry)
        if name:
            by_name.setdefault(name, []).append(entry)

    def take_match(block):
        candidates = []
        tid = _tvg_id(block)
        if tid:
            candidates.extend(by_id.get(tid, []))
        name = _display_name(block)
        if name:
            candidates.extend(by_name.get(name, []))

        for entry in candidates:
            if entry in remaining:
                remaining.remove(entry)
                return entry
        return None

    blocks = re.split(r'\n\s*\n', base.strip())
    out = []

    for block in blocks:
        if block.startswith('#EXTINF:') and (
            'group-title="haruka1 ' in block
            or 'group-title="haruka3 ' in block
            or 'ハルカ1' in block
            or 'ハルカ3' in block
        ):
            continue

        block = block.replace('group-title="haruka2 ', 'group-title="haruka ')
        block = block.replace('ハルカ2', 'haruka')
        out.append(block)

        if block.startswith('#EXTINF:') and 'group-title="haruka ' in block:
            match = take_match(block)
            if match:
                out.append(match)

    # Akariko channels without a matching Haruka entry remain available at the end.
    if remaining:
        residual = [START]
        residual.extend(remaining)
        residual.append(END)
        out.append('\n'.join(residual))

    if suffix:
        out.append(suffix)

    result = '\n\n'.join(part for part in out if part.strip()).rstrip() + '\n'

    forbidden = [
        'group-title="haruka1 ',
        'group-title="haruka2 ',
        'group-title="haruka3 ',
        'ハルカ1',
        'ハルカ2',
        'ハルカ3',
        'http://haru.charandom.blog/',
    ]
    stale = [value for value in forbidden if value in result]
    if stale:
        raise RuntimeError('stale Haruka/Akariko values remain: ' + repr(stale))

    return result

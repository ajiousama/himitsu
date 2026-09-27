#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "logos" / "fixed_logo_manifest.json"

def git_blob_sha(data: bytes) -> str:
    header = b"blob " + str(len(data)).encode("ascii") + bytes([0])
    return hashlib.sha1(header + data).hexdigest()

def main() -> int:
    spec = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assets = spec.get("assets") or {}
    if len(assets) != 29:
        raise SystemExit(f"fixed logo manifest must contain 29 assets, got {len(assets)}")

    bad = []
    for rel, meta in sorted(assets.items()):
        path = ROOT / rel
        expected = str((meta or {}).get("git_blob_sha") or "")
        if not path.is_file():
            bad.append(f"MISSING {rel}")
            continue
        actual = git_blob_sha(path.read_bytes())
        if actual != expected:
            bad.append(f"CHANGED {rel}: expected={expected} actual={actual}")

    if bad:
        raise SystemExit("Pinned sports logo validation failed:" + chr(10) + chr(10).join(bad))

    print(f"Pinned sports logos OK: {len(assets)} assets")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

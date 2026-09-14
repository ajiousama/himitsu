from __future__ import annotations

import argparse
import hashlib
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("source")
    p.add_argument("destination")
    args = p.parse_args()

    src = Path(args.source)
    if not src.exists():
        raise SystemExit(f"missing source: {src}")

    data = src.read_bytes()
    digest = hashlib.sha256(data).hexdigest()[:16]
    dest_dir = Path(args.destination)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"{digest}{src.suffix or '.txt'}"

    if dest.exists():
        print(f"snapshot already exists: {dest}")
        return

    dest.write_bytes(data)
    print(f"snapshot created: {dest}")


if __name__ == "__main__":
    main()

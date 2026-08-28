#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import urllib.request

CORE_PATH = pathlib.Path(__file__).with_name("radiko_proxy_core.py")
CORE_URL = "https://raw.githubusercontent.com/ajiousama/himitsu/main/radiko_proxy_core.py"


def refresh_core():
    try:
        req = urllib.request.Request(CORE_URL, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if not data.startswith(b"#!/usr/bin/env python3"):
            raise RuntimeError("downloaded core did not look like Python source")
        tmp = CORE_PATH.with_suffix(".py.tmp")
        tmp.write_bytes(data)
        tmp.replace(CORE_PATH)
        print("[radiko] core auto-update: OK", flush=True)
    except Exception as e:
        if CORE_PATH.exists():
            print(f"[radiko] core auto-update skipped: {type(e).__name__}: {e}", flush=True)
        else:
            raise RuntimeError(f"radiko_proxy_core.py download failed: {type(e).__name__}: {e}") from e


refresh_core()

if not CORE_PATH.exists():
    raise RuntimeError("radiko_proxy_core.py is missing")

spec = importlib.util.spec_from_file_location("radiko_proxy_core_runtime", CORE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("could not load radiko_proxy_core.py")
_core = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = _core
spec.loader.exec_module(_core)

for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

if __name__ == "__main__":
    _core.main()

#!/usr/bin/env python3
import importlib.util
import os
import pathlib
import sys
import urllib.request

CORE_URL = "https://raw.githubusercontent.com/ajiousama/himitsu/main/radiko_proxy_core.py"
CORE_PATH = pathlib.Path(__file__).with_name("radiko_proxy_core.py")
TMP_PATH = pathlib.Path(str(CORE_PATH) + ".tmp")

try:
    req = urllib.request.Request(CORE_URL, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read()
    if len(data) < 5000:
        raise RuntimeError("downloaded Radiko runtime is unexpectedly small")
    TMP_PATH.write_bytes(data)
    os.replace(TMP_PATH, CORE_PATH)
except Exception as e:
    try:
        TMP_PATH.unlink(missing_ok=True)
    except Exception:
        pass
    if not CORE_PATH.exists():
        raise RuntimeError(f"could not download radiko_proxy_core.py: {e}") from e

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
